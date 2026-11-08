"""
scripts/pizza_bot.py - otomatis sidejob Pizza Delivery untuk PyRakSamp (v4).

Taruh di folder `scripts/` (sejajar bot.py). Otomatis dimuat oleh Bot._load_scripts().
Log & status dikirim ke panel lewat event "onPizzaLog" / "onPizzaStatus".

Alur satu siklus:
  1. jalan ke titik tunggu (posisi 10) -> motor pizza ke-1..8 ter-stream
  2. naik motor terdekat -> Start Job -> /engine kalau mati
     (kalau tidak ada dialog Start Job & chat menyebut sisa delay -> tunggu sebanyak itu)
  3. ulangi 10x: kumpulkan kandidat tujuan beberapa detik -> pilih CHECKPOINT TERBESAR (milik NPC
     pelanggan, bukan checkpoint kecil di depan rumah) -> berkendara -> turun -> masuk checkpoint
     -> tekan Y -> tunggu pesan "You gave the pizza..." -> kembali ke motor (ada batas waktu ~60 dtk)
  4. setelah 10 pizza: berkendara ke titik akhir (posisi 9), turun
  5. jalan ke titik tunggu (posisi 10), tunggu delay (~1250 dtk, atau sesuai yang tertulis di chat)

Environment variable (opsional):
  PIZZA_AUTO=0         mulai dalam keadaan dijeda (nyalakan dari panel)
  PIZZA_DELIVERIES=10  jumlah pizza per sesi (set 1 untuk tes)
  PIZZA_DELAY=1250     delay cadangan (detik) kalau chat tidak menyebut delay
  PIZZA_TARGET=auto    sumber tujuan: auto (default, checkpoint terbesar) | checkpoint | icon
  PIZZA_COLLECT=6      detik mengumpulkan kandidat tujuan sebelum memilih
  PIZZA_ROADS=...      lokasi roads.json.gz (default: di samping script ini / folder repo)
  PIZZA_RUN_SPEED=5    kecepatan jalan kaki (m/s)    PIZZA_BIKE_SPEED=13  kecepatan motor (m/s)

Rute kendaraan mengikuti jaringan jalan GTA SA (roads.json.gz, dibuat dari nodes0-63.dat) dengan A*.
Kalau roads.json.gz tidak ada, bot kembali bergerak lurus ke tujuan.
"""
import gzip
import heapq
import json
import math
import os
import re
import threading
import time

from core import logger
from logic.events import emitter

ENABLED = os.environ.get("PIZZA_AUTO", "1") != "0"
PIZZA_MODEL = 448                      # Pizzaboy
DELIVERIES = int(os.environ.get("PIZZA_DELIVERIES", "10"))
FALLBACK_DELAY = float(os.environ.get("PIZZA_DELAY", "1250"))
TARGET_SOURCE = os.environ.get("PIZZA_TARGET", "auto").strip().lower()
BIG_WINDOW = float(os.environ.get("PIZZA_COLLECT", "6"))
DELAY_MARGIN = 5.0
# Kecepatan gerak (meter/detik). Default pustaka (coord_delay vehicle 5.0 per interval ~ 100 m/s) terlalu
# kencang dan memicu anti speed-hack, jadi kecepatan dipasang eksplisit.
RUN_SPEED = float(os.environ.get("PIZZA_RUN_SPEED", "5.0"))     # jalan kaki (lari biasa)
BIKE_SPEED = float(os.environ.get("PIZZA_BIKE_SPEED", "13.0"))  # motor pizza di kota (~47 km/jam)
MOVE_KEYS = os.environ.get("PIZZA_MOVE_KEYS", "1") != "0"       # tahan tombol sprint/gas saat bergerak

# (x, y, z, heading) - posisi motor pizza 1..8
BIKE_SPOTS = [
    (-2693.9517, 265.9214, 4.3545, 342.67),
    (-2693.9312, 268.1600, 4.3545, 115.77),
    (-2694.3423, 269.7650, 4.3545, 127.26),
    (-2694.0586, 271.3400, 4.3545, 121.32),
    (-2694.2361, 272.9054, 4.3545, 104.37),
    (-2694.4001, 273.7947, 4.3545, 3.93),
    (-2694.5320, 275.5810, 4.3545, 1.11),
    (-2694.5601, 277.0222, 4.3545, 5.68),
]
END_POS = (-2688.7083, 234.4671, 4.3536, 73.27)    # posisi 9: titik akhir setelah 10 pizza
WAIT_POS = (-2692.0859, 264.0220, 4.6505, 351.34)  # posisi 10: titik tunggu delay

OK, FAIL, DELAYED = "ok", "fail", "delay"

COLOR_TAG = re.compile(r"\{[0-9a-fA-F]{6}\}")
TD_CODE = re.compile(r"~[a-zA-Z0-9]~")
COUNT_RE = re.compile(r"pizzas?\s*:?\s*(\d+)\s*/\s*(\d+)", re.I)
DIST_RE = re.compile(r"distance\s*:?\s*([\d.]+)\s*m", re.I)
CONFIRM_RE = re.compile(r"you gave the pizza|\+1 delivery|delivery is confirmed", re.I)
AT_CUSTOMER_RE = re.compile(r"you have to deliver the pizza|press 'y' to deliver", re.I)
DELAY_WORDS = re.compile(r"delay|cooldown|tunggu|menunggu|tersisa|remaining|wait", re.I)
UNITS = {"second": 1, "sec": 1, "detik": 1, "minute": 60, "min": 60,
         "menit": 60, "hour": 3600, "jam": 3600}
TIME_RE = re.compile(r"(\d+)\s*(second|sec|detik|minute|min|menit|hour|jam)", re.I)


class State:
    def __init__(self):
        self.api = None
        self.spawned = threading.Event()
        self.vehicles = {}             # id -> (model, x, y, z)
        self.bike_id = 0
        self.bike_pos = None
        self.job_active = False
        self.cands = []                # kandidat tujuan: {t, kind, x, y, z, r}
        self.tdist = None              # (meter, waktu) dari textdraw "distance: 7.9m"
        self.deliver_ver = 0           # naik tiap pesan "You gave the pizza..."
        self.at_customer_t = 0.0       # waktu pesan "You have to deliver the pizza..."
        self.pizza_count = 0
        self.pizza_total = 0
        self.count_ver = 0
        self.chat_delay = None         # (detik, waktu_terbaca)
        self.engine_off = False
        self.job_started = threading.Event()
        self.want_delays = False
        self.delays_evt = threading.Event()
        self.delays_secs = None
        self.ended_moves = set()
        self.next_ok = 0.0
        self.wait_kind = "delay"       # "delay" = delay pizza | "retry" = coba ulang setelah gagal
        self.paused = not ENABLED
        self.abort = False
        self.stats = {
            "state": "Dijeda" if not ENABLED else "Memulai",
            "paused": not ENABLED,
            "current": 0,
            "total": DELIVERIES,
            "sessions_ok": 0,
            "sessions_fail": 0,
            "pizzas": 0,
            "next_run": 0.0,
            "last_error": "",
        }


st = State()


def log(msg, level="info"):
    """level: info | ok | warn | error"""
    logger.info(f"[pizza] {msg}")
    try:
        emitter.emit("onPizzaLog", st.api, level, str(msg))
    except Exception:  # noqa: BLE001
        pass


def _status(**kw):
    st.stats.update(kw)
    try:
        emitter.emit("onPizzaStatus", st.api, dict(st.stats))
    except Exception:  # noqa: BLE001
        pass


def _fail(reason, level="error"):
    log(reason, level)
    _status(last_error=reason)
    return FAIL


def _s(x):
    if isinstance(x, (bytes, bytearray)):
        x = bytes(x).decode("cp1252", "replace")
    return COLOR_TAG.sub("", "" if x is None else str(x))


def _check():
    if st.abort:
        raise RuntimeError("dihentikan dari panel")
    if not st.api.is_connected() or not st.spawned.is_set():
        raise RuntimeError("bot terputus / belum spawn")


def _sleep(sec):
    end = time.time() + sec
    while time.time() < end:
        _check()
        time.sleep(min(1.0, max(0.0, end - time.time())))


def _wait_event(ev, timeout):
    end = time.time() + timeout
    while time.time() < end:
        _check()
        if ev.wait(0.5):
            return True
    return False


def _dist2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _parse_seconds(text):
    return sum(int(n) * UNITS[u.lower()] for n, u in TIME_RE.findall(text))


def _recent_chat_delay(window):
    d = st.chat_delay
    if d and time.time() - d[1] <= window:
        return d[0]
    return None


# ------------------------------------------------------------------ event

@emitter.on("onBotCreated")
def _on_created(bot, *_):
    st.api = bot
    threading.Thread(target=_worker, name="pizza-bot", daemon=True).start()


@emitter.on("onPizzaControl", sync=True)
def _control(bot, action, *_):
    if action == "pause":
        st.paused = True
        log("Dijeda: berlaku setelah sesi yang sedang berjalan selesai", "warn")
    elif action == "stop":
        st.paused, st.abort = True, True
        log("Dihentikan sekarang dari panel", "warn")
    elif action == "resume":
        st.paused, st.abort = False, False
        log("Dilanjutkan dari panel", "info")
    _status(paused=st.paused)


@emitter.on("onSpawn")
def _on_spawn(bot, *_):
    st.spawned.set()
    log("bot spawn", "info")


@emitter.on("disconnect")
def _on_disconnect(bot, *_):
    st.spawned.clear()
    st.vehicles.clear()
    log("koneksi bot terputus", "warn")


@emitter.on("onVehicleStreamIn")
def _veh_in(bot, model_id, vehicle_id, x, y, z, *_):
    st.vehicles[int(vehicle_id)] = (int(model_id), float(x), float(y), float(z))


@emitter.on("onVehicleStreamOut")
def _veh_out(bot, vehicle_id, *_):
    st.vehicles.pop(int(vehicle_id), None)


def _add_cand(kind, x, y, z, r):
    """Catat kandidat tujuan (checkpoint / race / icon) selama sesi berjalan."""
    if not st.job_active:
        return
    st.cands.append({"t": time.time(), "kind": kind, "x": float(x), "y": float(y),
                     "z": float(z), "r": float(r or 0.0)})
    del st.cands[:-60]
    log(f"kandidat {kind}: {x:.1f}, {y:.1f}, {z:.1f} radius={float(r or 0.0):.1f}", "info")


@emitter.on("OnSetCheckpoint")
def _cp(bot, x, y, z, radius, *_):
    _add_cand("checkpoint", x, y, z, radius)


@emitter.on("OnSetRaceCheckpoint")
def _rcp(bot, cp_type, position, next_position, radius, *_):
    _add_cand("race", position[0], position[1], position[2], radius)


@emitter.on("onSetMapIcon")
def _icon(bot, icon_id, xyz, marker_type, style, *_):
    _add_cand("icon", xyz[0], xyz[1], xyz[2], 0.0)


@emitter.on("onShowChat")
def _chat(bot, message, *_):
    line = _s(message).strip()
    low = line.lower()
    if "mesin masih mati" in low:
        st.engine_off = True
    if "sidejob" in low or (st.job_active and "pizza" in low):
        log("chat: " + line[:220], "info")
        if CONFIRM_RE.search(low):
            st.deliver_ver += 1
        if AT_CUSTOMER_RE.search(low):
            st.at_customer_t = time.time()
        if DELAY_WORDS.search(low):
            secs = _parse_seconds(low)
            if secs > 0:
                st.chat_delay = (secs, time.time())
                log(f"Delay terdeteksi dari chat: {secs} detik", "warn")


def _feed_textdraw(text):
    t = TD_CODE.sub("", _s(text))
    m = COUNT_RE.search(t)
    if m:
        n, total = int(m.group(1)), int(m.group(2))
        if (n, total) != (st.pizza_count, st.pizza_total):
            st.pizza_count, st.pizza_total = n, total
            st.count_ver += 1
            if st.job_active:
                log(f"Penghitung server: {n}/{total}", "info")
    d = DIST_RE.search(t)
    if d:
        try:
            st.tdist = (float(d.group(1)), time.time())
        except ValueError:
            pass


@emitter.on("OnShowTextDraw")
def _td_show(bot, textdraw_id, info, *_):
    text = info.get("text") if isinstance(info, dict) else getattr(info, "text", info)
    _feed_textdraw(text)


@emitter.on("OnTextDrawSetString")
def _td_set(bot, textdraw_id, text, *_):
    _feed_textdraw(text)


@emitter.on("OnCoordMoveEnd", sync=True)
def _move_end(bot, movement, status, *_):
    try:
        st.ended_moves.add(int(movement.get("movement_id")))
    except Exception:  # noqa: BLE001
        pass


@emitter.on("onShowDialog")
def _dialog(bot, dialog_id, style, title, info, button1, button2, *_):
    title, info = _s(title), _s(info)
    b1, b2 = _s(button1).lower(), _s(button2).lower()
    low = (title + " " + info).lower()

    # dialog Start Job
    if "pizza" in low and ("start" in b1 or "start" in b2):
        resp = 1 if "start" in b1 else 0
        st.job_started.set()
        threading.Timer(0.8, bot.SendDialogResponse, (dialog_id, resp, -1, "")).start()
        return

    # dialog /delays
    if st.want_delays and title.lower().startswith("delay"):
        rows = [r.replace("\t", " = ") for r in info.replace("\r", "").split("\n") if r.strip()]
        log("isi /delays: " + " | ".join(rows)[:400], "info")
        secs = None
        for line in info.replace("\r", "").split("\n"):
            if "pizza" in line.lower():
                secs = _parse_seconds(line)
                break
        st.delays_secs = secs
        st.delays_evt.set()
        threading.Timer(0.5, bot.SendDialogResponse, (dialog_id, 0, -1, "")).start()


# ------------------------------------------------------------------ aksi dasar

def _remaining_delay():
    st.delays_secs = None
    st.delays_evt.clear()
    st.want_delays = True
    st.api.sendchat("/delays")
    if not st.delays_evt.wait(8):
        log("dialog /delays tidak muncul (8s)", "warn")
    st.want_delays = False
    return st.delays_secs          # None = baris pizza tidak ditemukan


def _veh_pos(vid):
    try:
        v = st.api.session.stream.get_vehicle(vid)
        if v is not None:
            return (float(v.x), float(v.y), float(v.z))
    except Exception:  # noqa: BLE001
        pass
    return None


def _find_bike():
    """Pilih motor pizza (model 448) yang berada di salah satu posisi 1-8 dan terdekat dari bot."""
    me = st.api.getbotposition()
    cand = []
    for vid, (model, x, y, z) in list(st.vehicles.items()):
        if model != PIZZA_MODEL:
            continue
        pos = _veh_pos(vid) or (x, y, z)
        spot = min(_dist2(pos, s) for s in BIKE_SPOTS)
        cand.append((spot, _dist2(me, pos), vid, pos))
    at_spot = [c for c in cand if c[0] <= 12.0]
    pool = at_spot or [c for c in cand if c[1] <= 80.0]
    if not pool:
        log(f"Motor pizza tidak ditemukan | kendaraan di stream={len(st.vehicles)}, "
            f"model 448={len(cand)}", "warn")
        return None
    if not at_spot:
        log("tidak ada motor di posisi 1-8, memakai motor 448 terdekat", "warn")
    best = min(pool, key=lambda c: c[1])
    return best[1], best[2], best[3]


def _nominal_interval(mode):
    """Interval sync nominal yang dipakai pustaka (sama dengan perhitungan di BotAPI.MoveToCoord)."""
    sync = st.api.session.sync
    if mode == "vehicle":
        lo, hi = sync.rate_vehicle_min, sync.rate_vehicle_max
    else:
        lo, hi = sync.rate_player_min, sync.rate_player_max
    return max(0.001, (float(lo) + float(hi)) * 0.5)


def _move_kwargs(mode, speed=None):
    """Kecepatan = coord_delay / interval  ->  coord_delay = kecepatan x interval."""
    if speed is None:
        speed = BIKE_SPEED if mode == "vehicle" else RUN_SPEED
    kw = {
        "coord_delay": speed * _nominal_interval(mode),
        # hadap ke arah gerak, tanpa deviasi acak, belok halus
        "movement_direction_control": (True, False, 0, 60 if mode == "walk" else 40),
    }
    if MOVE_KEYS:
        kw["movement_keys_mode"] = "throttle:8" if mode == "vehicle" else "always:8"
    return kw


def _go(target, mode, radius=0.0, timeout=240, cd=None, reach=None,
        accel_time=None, brake_time=None, speed=None):
    api = st.api
    x, y, z = target[0], target[1], target[2]
    if cd is None:
        cd = max(1.5, min(radius * 0.4, 6.0)) if radius else 2.0
    if reach is None:
        reach = max(cd + 1.5, min(radius * 0.7, 9.0), 4.0)
    extra = {}
    if accel_time is not None:
        extra["accel_time"] = accel_time
    if brake_time is not None:
        extra["brake_time"] = brake_time
    mid = api.MoveToCoord(x, y, z, mode=mode, completion_distance=cd,
                          stop_on_dialog=False, **_move_kwargs(mode, speed), **extra)
    end = time.time() + timeout
    while time.time() < end:
        _check()
        if _dist2(api.getbotposition(), (x, y, z)) <= reach:
            try:
                api.StopMoveToCoord(mid, reason="arrived")
            except Exception:  # noqa: BLE001
                pass
            return True
        if mid in st.ended_moves:
            return _dist2(api.getbotposition(), (x, y, z)) <= reach + 4.0
        time.sleep(0.05)               # polling rapat supaya tidak ada jeda antar titik rute
    return False


def _enter(vid):
    if not st.api.setbotvehicle(vid, 0, 3.0):
        return False
    _sleep(4.0)
    return True


def _exit_vehicle():
    api = st.api
    try:  # simpan posisi motor supaya jarak naik berikutnya benar
        x, y, z = api.getbotposition()
        st.bike_pos = (x, y, z)
        if st.bike_id:
            v = api.session.stream.get_vehicle(st.bike_id)
            if v is not None:
                v.x, v.y, v.z = x, y, z
    except Exception:  # noqa: BLE001
        pass
    api.setbotvehicle(0)
    _sleep(1.5)


def _engine_if_off():
    _sleep(1.0)
    if st.engine_off:
        st.engine_off = False
        log("mesin mati, mengirim /engine", "info")
        st.api.sendchat("/engine")
        _sleep(1.5)


def _press_y():
    """Tombol Y di SA-MP 0.3.7 dikirim lewat field `additional_key` (1 = Y) di paket sync,
    BUKAN lewat `keys` (16 bit, tidak muat nilai 65536)."""
    log("menekan Y", "info")
    api = st.api
    bp = api.session.players.bot
    sync = getattr(api.session, "sync", None)

    def _flush():                       # kirim paket sync sekarang juga (jangan menunggu idle-backoff)
        try:
            if sync is not None and sync.enabled and getattr(bp, "sync_state", "onfoot") == "onfoot":
                sync.send_player_sync()
        except Exception:  # noqa: BLE001
            pass

    try:
        bp.additional_key = 1
        _flush()
        time.sleep(0.8)                 # lewati beberapa siklus sync, termasuk saat idle-backoff
        bp.additional_key = 0
        _flush()
        time.sleep(0.4)
    except Exception as exc:  # noqa: BLE001
        log(f"gagal menekan Y: {exc}", "error")
        try:
            bp.additional_key = 0
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ jaringan jalan (A*)

class RoadNet:
    def __init__(self, pts, adj):
        self.pts, self.adj = pts, adj
        self.grid = {}
        for k, (x, y, z) in enumerate(pts):
            self.grid.setdefault((int(x // 100), int(y // 100)), []).append(k)

    def nearest(self, x, y, z=None, maxd=150.0):
        cx, cy = int(x // 100), int(y // 100)
        r = int(maxd // 100) + 1
        best = None
        for gx in range(cx - r, cx + r + 1):
            for gy in range(cy - r, cy + r + 1):
                for k in self.grid.get((gx, gy), ()):
                    px, py, pz = self.pts[k]
                    d = math.hypot(px - x, py - y)
                    if z is not None:
                        d += abs(pz - z) * 0.5          # utamakan node di ketinggian yang sama (jembatan/flyover)
                    if d <= maxd and (best is None or d < best[0]):
                        best = (d, k)
        return best

    def route(self, start, goal):
        pts, adj = self.pts, self.adj
        gx, gy, gz = pts[goal]
        openq = [(0.0, start)]
        cost = {start: 0.0}
        came = {}
        while openq:
            _, u = heapq.heappop(openq)
            if u == goal:
                path = [u]
                while u in came:
                    u = came[u]
                    path.append(u)
                return path[::-1]
            for v in adj[u]:
                c = cost[u] + math.dist(pts[u], pts[v])
                if c < cost.get(v, 1e18):
                    cost[v] = c
                    came[v] = u
                    heapq.heappush(openq, (c + math.dist(pts[v], (gx, gy, gz)), v))
        return None


_ROADS = {"net": None, "tried": False}


def _roads():
    if _ROADS["tried"]:
        return _ROADS["net"]
    _ROADS["tried"] = True
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.environ.get("PIZZA_ROADS", ""), os.path.join(here, "roads.json.gz"),
             os.path.join(os.path.dirname(here), "roads.json.gz"), "roads.json.gz"]
    for path in cands:
        if path and os.path.isfile(path):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    d = json.load(f)
                pts = [tuple(p) for p in d["p"]]
                adj = [[] for _ in pts]
                for i, nb in enumerate(d["e"]):
                    for j in nb:
                        adj[i].append(j)
                        adj[j].append(i)
                _ROADS["net"] = RoadNet(pts, adj)
                log(f"data jalan dimuat: {len(pts)} node dari {path}", "info")
                return _ROADS["net"]
            except Exception as exc:  # noqa: BLE001
                log(f"gagal memuat data jalan {path}: {exc}", "warn")
    log("roads.json.gz tidak ditemukan, bot bergerak lurus ke tujuan", "warn")
    return None


def _angle(a, b, c):
    """Sudut belok (derajat) di titik b untuk jalur a -> b -> c."""
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cosv = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cosv))


def _plan_route(start, target):
    """Daftar titik (x, y, z) mengikuti jalan dari `start` ke `target`; None kalau tidak ada rute."""
    net = _roads()
    if net is None:
        return None
    a = net.nearest(start[0], start[1], start[2] if len(start) > 2 else None)
    b = net.nearest(target[0], target[1], target[2] if len(target) > 2 else None)
    if not a or not b:
        log("tujuan/posisi bot terlalu jauh dari jalan (>150 m), bergerak lurus", "warn")
        return None
    ids = net.route(a[1], b[1])
    if not ids:
        log("tidak ada rute jalan antara posisi bot dan tujuan, bergerak lurus", "warn")
        return None
    pts = [net.pts[k] for k in ids]
    # buang node di belakang bot / di belakang tujuan supaya tidak berputar balik
    while len(pts) >= 2 and math.dist(start[:2], pts[1][:2]) < math.dist(pts[0][:2], pts[1][:2]):
        pts.pop(0)
    while len(pts) >= 2 and math.dist(target[:2], pts[-2][:2]) < math.dist(pts[-1][:2], pts[-2][:2]):
        pts.pop()
    # sederhanakan: buang node yang hampir lurus
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        if _angle(out[-1], pts[i], pts[i + 1]) >= 6.0 or math.dist(out[-1][:2], pts[i][:2]) > 80.0:
            out.append(pts[i])
    out.append(pts[-1])
    out.append((float(target[0]), float(target[1]), float(target[2])))
    return out


def _turn_speed(angle):
    if angle < 20:
        return BIKE_SPEED
    if angle < 60:
        return BIKE_SPEED * 0.8
    if angle < 100:
        return BIKE_SPEED * 0.55
    return BIKE_SPEED * 0.35


def _follow(points, radius):
    """Ikuti titik-titik rute dengan kendaraan: kecepatan konstan, melambat di tikungan, rem di titik akhir."""
    api = st.api
    n = len(points)
    prev = api.getbotposition()
    for i, (x, y, z) in enumerate(points):
        last = i == n - 1
        speed = BIKE_SPEED if last else max(4.0, _turn_speed(_angle(prev, (x, y), points[i + 1])))
        if i == 0:
            accel = None                               # percepatan awal bawaan pustaka
        else:
            accel = 0.0                                # lanjut tanpa mulai dari nol lagi
        cd = (max(1.5, min(radius * 0.4, 6.0)) if radius else 2.0) if last else 0.5
        ok = _go((x, y, z), "vehicle", radius if last else 0.0,
                 timeout=max(25.0, math.dist(prev[:2], (x, y)) / max(1.0, speed * 0.4) + 15.0),
                 cd=cd, reach=cd + 1.5, accel_time=accel, brake_time=None if last else 0.0, speed=speed)
        if not ok:
            return False
        prev = (x, y)
    return True


def _drive(tgt):
    if not st.api.session.players.bot.is_in_vehicle():
        raise RuntimeError("bot tidak berada di kendaraan")
    radius = tgt[3] if len(tgt) > 3 else 0.0
    me = st.api.getbotposition()
    route = _plan_route(me, tgt) if math.dist(me[:2], tgt[:2]) > 40.0 else None
    if route:
        length = sum(math.dist(route[i][:2], route[i + 1][:2]) for i in range(len(route) - 1))
        log(f"rute jalan: {len(route)} titik, {length:.0f} m (lurus {math.dist(me[:2], tgt[:2]):.0f} m)", "info")
        return _follow(route, radius)
    return _go(tgt, "vehicle", radius)


def _kind_ok(kind):
    if TARGET_SOURCE == "icon":
        return kind == "icon"
    if TARGET_SOURCE == "checkpoint":
        return kind in ("checkpoint", "race")
    return True


def _choose(cands):
    """Pilih checkpoint dengan radius TERBESAR (checkpoint NPC); checkpoint kecil di depan rumah kalah."""
    me = st.api.getbotposition()
    cps = [c for c in cands if c["kind"] in ("checkpoint", "race")]
    pool = cps or cands
    best_r = max(c["r"] for c in pool)
    top = [c for c in pool if c["r"] >= best_r * 0.8]
    if len(top) > 1 and st.tdist and time.time() - st.tdist[1] < 5:
        td = st.tdist[0]
        top.sort(key=lambda c: abs(_dist2(me, (c["x"], c["y"])) - td))
    else:
        top.sort(key=lambda c: c["t"])
    c = top[0]
    ringkas = ", ".join(f"{k['kind']} r={k['r']:.1f}" for k in cands)
    log(f"dipilih {c['kind']} radius={c['r']:.1f} dari {len(cands)} kandidat [{ringkas}]", "info")
    return (c["x"], c["y"], c["z"], c["r"]), f"{c['kind']} r={c['r']:.1f}"


def _pick_target(since, timeout=40):
    """Kumpulkan kandidat sejak `since`, tunggu BIG_WINDOW detik, lalu pilih yang terbesar."""
    end = max(time.time() + 25, since + BIG_WINDOW + timeout)
    while time.time() < end:
        _check()
        cands = [c for c in st.cands if c["t"] >= since and _kind_ok(c["kind"])]
        if cands and time.time() - since >= BIG_WINDOW:
            return _choose(cands)
        time.sleep(0.25)
    return None, None


def _wait_customer(t_exit, timeout):
    """Tunggu pesan 'You have to deliver the pizza...' (tanda sudah di checkpoint pelanggan)."""
    end = time.time() + timeout
    while time.time() < end:
        _check()
        if st.at_customer_t >= t_exit:
            return True
        time.sleep(0.25)
    return False


def _deliver(last):
    """Tekan Y sampai ada konfirmasi (chat 'You gave the pizza' atau counter naik)."""
    for attempt in range(3):
        ver, cnt_ver, n_before = st.deliver_ver, st.count_ver, st.pizza_count
        _press_y()
        end = time.time() + 8
        while time.time() < end:
            _check()
            if st.deliver_ver != ver:
                return True
            if st.count_ver != cnt_ver and st.pizza_count > n_before:
                return True
            time.sleep(0.25)
        log(f"belum ada konfirmasi antar, mencoba lagi ({attempt + 1}/3)", "warn")
    if last:
        log("tidak ada konfirmasi untuk pizza terakhir, lanjut ke titik akhir", "warn")
        return True
    return False


def _return_to_bike():
    if st.bike_pos and _dist2(st.api.getbotposition(), st.bike_pos) > 7.0:
        _go(st.bike_pos, "walk", 0.0, 90, cd=2.0, reach=4.0)


# ------------------------------------------------------------------ siklus

def _goto_wait():
    api = st.api
    try:
        if api.session.players.bot.is_in_vehicle():
            _exit_vehicle()
    except Exception:  # noqa: BLE001
        pass
    if _dist2(api.getbotposition(), WAIT_POS) > 3.0:
        _status(state="Berjalan ke titik tunggu")
        _go(WAIT_POS, "walk", 0.0, 600, cd=1.5, reach=3.0)
    try:
        api.setbotrotation(WAIT_POS[3])
    except Exception:  # noqa: BLE001
        pass


def _idle_wait(ts, state):
    left = int(ts - time.time())
    if st.wait_kind == "retry":
        state = "Menunggu coba ulang di titik tunggu"
        log(f"Sesi gagal. Mencoba lagi dalam {left} detik (menunggu di titik tunggu)", "info")
    else:
        state = "Menunggu delay pizza di titik tunggu"
        log(f"Menunggu delay pizza {left} detik di titik tunggu", "info")
    _status(state=state, next_run=ts)
    while time.time() < ts and not st.paused and not st.abort:
        time.sleep(1)
        if not st.api.is_connected():
            break
    _status(next_run=0.0)


def _run_job():
    st.job_active = True
    st.cands.clear()
    try:
        return _run_job_inner()
    finally:
        st.job_active = False


def _run_job_inner():
    api = st.api
    _status(state="Mencari motor pizza", current=0, total=DELIVERIES)
    log("mulai sesi pizza", "info")

    if _dist2(api.getbotposition(), WAIT_POS) > 15.0:   # dekati area agar motor ter-stream
        _status(state="Berjalan ke area motor")
        if not _go(WAIT_POS, "walk", 0.0, 600, cd=1.5, reach=3.0):
            return _fail("Gagal sampai ke area motor pizza")
        _sleep(2.0)

    found = _find_bike()
    if not found:
        return _fail("Motor pizza tidak ditemukan di sekitar posisi 1-8")
    _, vid, pos = found
    st.bike_id, st.bike_pos = vid, pos

    if _dist2(api.getbotposition(), pos) > 6.0:
        _status(state="Berjalan ke motor pizza")
        log(f"jalan ke motor id={vid}", "info")
        if not _go(pos, "walk", 0.0, 120):
            return _fail("Gagal sampai ke motor pizza (waktu habis)")

    st.job_started.clear()
    t_enter = time.time()               # kandidat tujuan dihitung sejak sebelum naik motor
    _status(state="Naik motor")
    if not _enter(vid):
        return _fail("Gagal naik motor (terlalu jauh atau tidak ada di stream)")
    _engine_if_off()

    _status(state="Menunggu dialog Start Job")
    if not _wait_event(st.job_started, 15):
        secs = _recent_chat_delay(40)
        if secs is None:
            secs = _remaining_delay() or None
        if secs:
            st.next_ok = time.time() + secs + DELAY_MARGIN
            log(f"Pekerjaan masih delay {int(secs)} detik, menunggu", "warn")
            _exit_vehicle()
            return DELAYED
        return _fail("Dialog Start Job tidak muncul dan delay tidak terdeteksi di chat "
                     "(lihat baris 'chat:' di log untuk pesan servernya)")
    log("Start Job ditekan", "ok")
    t_start = t_enter
    _engine_if_off()

    _status(state="Memilih tujuan pertama")
    tgt, src = _pick_target(t_start)
    if tgt is None:
        return _fail("Tujuan antar pertama tidak muncul setelah Start Job")

    delivered = 0
    while True:
        _status(state=f"Berkendara ke tujuan {delivered + 1}/{DELIVERIES}")
        log(f"tujuan {delivered + 1}/{DELIVERIES} ({src}): "
            f"{tgt[0]:.1f}, {tgt[1]:.1f}, {tgt[2]:.1f}", "info")
        if not _drive(tgt):
            return _fail("Gagal sampai ke tujuan antar (waktu habis / tersangkut)")
        t_exit = time.time()
        _exit_vehicle()

        _status(state=f"Mengantar pizza {delivered + 1}/{DELIVERIES}")
        if _dist2(api.getbotposition(), tgt) > 2.5:     # masuk ke tengah checkpoint pelanggan
            _go(tgt, "walk", 0.0, 60, cd=1.0, reach=2.0)

        t_press = time.time()           # tujuan berikutnya bisa datang sebelum _deliver selesai
        if not _deliver(last=(delivered + 1 >= DELIVERIES)):
            return _fail("Pizza tidak terkonfirmasi terkirim setelah menekan Y "
                         "(Y mungkin tidak terkirim atau posisi kurang dekat NPC)")
        delivered += 1
        st.stats["pizzas"] += 1
        _status(current=delivered)
        log(f"Pizza terkirim {delivered}/{DELIVERIES}", "ok")

        if delivered >= DELIVERIES:
            break

        _status(state="Kembali ke motor")       # server memberi batas waktu ~60 dtk
        _return_to_bike()
        if not _enter(vid):
            return _fail("Gagal naik motor lagi setelah mengantar")
        _engine_if_off()
        _status(state="Memilih tujuan berikutnya")
        tgt, src = _pick_target(t_press)
        if tgt is None:
            return _fail("Tujuan antar berikutnya tidak muncul")

    # 10 pizza selesai -> titik akhir (posisi 9)
    _status(state="Mengembalikan motor ke titik akhir")
    log("10 pizza selesai, menuju titik akhir", "info")
    _return_to_bike()
    if not _enter(vid):
        return _fail("Gagal naik motor untuk menuju titik akhir")
    _engine_if_off()
    if not _drive(END_POS):
        return _fail("Gagal sampai ke titik akhir (posisi 9)")
    _sleep(3.0)
    _exit_vehicle()
    log("Motor dikembalikan di titik akhir, sesi selesai", "ok")
    return OK


def _worker():
    api = st.api
    log(f"worker aktif | pizza/sesi={DELIVERIES} | delay cadangan={FALLBACK_DELAY:g}s "
        f"| sumber tujuan={TARGET_SOURCE} | kecepatan jalan={RUN_SPEED:g} m/s, "
        f"motor={BIKE_SPEED:g} m/s", "info")
    _status()
    while True:
        try:
            if st.paused:
                _status(state="Dijeda")
                time.sleep(1)
                continue
            if not api.is_connected() or not st.spawned.is_set():
                _status(state="Menunggu bot terhubung & spawn")
                time.sleep(2)
                continue

            if st.next_ok > time.time():
                _goto_wait()
                _idle_wait(st.next_ok, "Menunggu delay di titik tunggu")
                continue

            _status(state="Memeriksa delay (/delays)")
            remain = _remaining_delay()
            if remain:
                st.next_ok = time.time() + remain + DELAY_MARGIN
                st.wait_kind = "delay"
                continue

            result = _run_job()
            if result == OK:
                secs = _recent_chat_delay(40) or FALLBACK_DELAY
                st.next_ok = time.time() + secs + DELAY_MARGIN
                st.wait_kind = "delay"
                log(f"Delay berikutnya {int(secs)} detik", "info")
                _status(sessions_ok=st.stats["sessions_ok"] + 1)
            elif result == DELAYED:
                st.wait_kind = "delay"    # next_ok sudah diisi dari delay yang terdeteksi
            else:
                _status(sessions_fail=st.stats["sessions_fail"] + 1,
                        state="Gagal, mencoba lagi sebentar lagi")
                st.next_ok = time.time() + 75     # server menghentikan job setelah 60 dtk di luar motor
                st.wait_kind = "retry"
        except RuntimeError as exc:
            log(f"Sesi dihentikan: {exc}", "warn")
            _status(last_error=str(exc))
            time.sleep(5)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[pizza] error: {exc}")
            log(f"Error tak terduga: {exc}", "error")
            _status(last_error=str(exc))
            time.sleep(10)
