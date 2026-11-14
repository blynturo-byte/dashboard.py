"""
scripts/farm_bot.py - otomatis job Farm (tanam & panen Potato) untuk PyRakSamp.

Taruh di folder `scripts/` (sejajar bot.py), bersama folder `farm_recordings/`
(berisi beli_seed.jsonl, tanam_potato.jsonl, panen_potato.jsonl - diambil dari
rekaman gameplay Anda). Log & status dikirim ke panel lewat event
"onFarmLog" / "onFarmStatus", dikontrol lewat "onFarmControl" (pause/resume/stop),
sama seperti pizza_bot.py.

ASUMSI PENTING (tolong dikonfirmasi dengan mencoba): rekaman Anda dimulai dengan
karakter SUDAH berada di The Farm. Bot ini mengasumsikan itu juga titik spawn
login Anda di server. Kalau ternyata spawn Anda beda, set FARM_WARP_CMD ke
command/teleport yang Anda pakai untuk sampai ke farm (mis. "/myhome farm"),
atau bot akan berhenti dengan pesan error yang jelas di panel alih-alih
menebak rute lintas map yang belum pernah diuji.

Alur:
  1. (opsional) kirim FARM_WARP_CMD, lalu pastikan posisi dekat The Farm.
  2. /mypv -> pilih baris "Sadler" -> Vehicle Info -> "Spawn Vehicle".
  3. ulangi 26x (atau sampai server bilang penuh): /plant plant
     - dialog "My Seed: N" muncul; kalau N < 8 -> Close, ambil seed (trunk lalu
       /buyseed), ulangi dialognya; kalau cukup -> klik Plant.
     - gerakan jalan di antara titik tanam memakai rekaman tanam_potato.jsonl.
  4. /plant harvest sekali untuk membaca sisa waktu tumbuh ("needs MM:SS") ->
     tunggu sebesar itu (+ margin). Kalau pesannya beda, pakai FARM_GROW_FALLBACK.
  5. setelah waktu tumbuh habis: /plant harvest (memanen) lalu /loadplant
     berulang (dialog "Load Plant" -> pilih Potato -> masukkan jumlah maksimum)
     sampai tidak ada lagi Potato untuk dimuat. Setiap muatan dicatat ke HUD.
  6. kembali ke langkah 3.

Environment variable (opsional):
  FARM_AUTO=0            mulai dalam keadaan dijeda
  FARM_WARP_CMD=         command teks untuk pergi ke farm kalau bot tidak spawn di sana
  FARM_PLANT_TARGET=26   jumlah tanaman per sesi (sesuai batas server)
  FARM_SEED_COST=8       seed yang terpakai per tanaman Potato
  FARM_GROW_FALLBACK=1860  detik cadangan kalau waktu tumbuh tidak terbaca dari chat (31 menit)
  FARM_BUY_TARGET=100    target seed dibeli per sesi pengadaan /buyseed (1-100 per panggilan)
  FARM_ROADS=            lokasi roads.json.gz, kalau mau dipakai untuk perjalanan jauh
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

HERE = os.path.dirname(os.path.abspath(__file__))
REC_DIR = os.path.join(HERE, "farm_recordings")

ENABLED = os.environ.get("FARM_AUTO", "1") != "0"
WARP_CMD = os.environ.get("FARM_WARP_CMD", "").strip()
PLANT_TARGET = int(os.environ.get("FARM_PLANT_TARGET", "26"))
SEED_COST = int(os.environ.get("FARM_SEED_COST", "8"))
GROW_FALLBACK = float(os.environ.get("FARM_GROW_FALLBACK", "1860"))
BUY_TARGET = int(os.environ.get("FARM_BUY_TARGET", "100"))
SADLER_MODEL = 445

# Titik acuan (dari rekaman); dipakai untuk cek jarak & sebagai offset replay.
FARM_POS = (-1005.507, -1059.3696, 129.2188)
PATCH_POS = (-1008.7748, -1051.2633, 129.2188)
SHOP_POS = (-378.0, -1435.0, 25.5)

COLOR_TAG = re.compile(r"\{[0-9a-fA-F]{6}\}")
TIME_RE = re.compile(r"(\d+):(\d+)\s*minutes?", re.I)
SEED_NOW_RE = re.compile(r"now you have\s*(\d+)\s*seed", re.I)
MYSEED_RE = re.compile(r"my seed:\s*(\d+)", re.I)  # _s() sudah membuang kode warna sebelum ini
MAXLOAD_RE = re.compile(r"max:\s*(\d+)\)\s*\n?you have:\s*(\d+)", re.I)
LOADED_RE = re.compile(r"loaded\s*(\d+)\s*potato", re.I)
SADLER_SPAWN_RE = re.compile(r"sadler\((\d+)\)", re.I)


def _s(x):
    if isinstance(x, (bytes, bytearray)):
        x = bytes(x).decode("cp1252", "replace")
    return COLOR_TAG.sub("", "" if x is None else str(x))


def _rows(text, style=None):
    """Baris dialog list/table, kolom pertama tiap baris (tanpa kode warna).
    style 5 (DIALOG_STYLE_TABLIST_HEADERS) punya baris header yang TIDAK ikut dihitung
    sebagai pilihan (list index 0 = baris data pertama setelah header)."""
    out = []
    for line in _s(text).split("\n"):
        line = line.strip()
        if not line:
            continue
        out.append(line.split("\t")[0].strip())
    if style == 5 and out:
        out = out[1:]
    return out


def _find_row(rows, prefix):
    pl = prefix.lower()
    for i, r in enumerate(rows):
        if r.lower().startswith(pl):
            return i, r
    return None, None


def log(msg, level="info"):
    logger.info(f"[farm] {msg}")
    try:
        emitter.emit("onFarmLog", st.api, level, str(msg))
    except Exception:  # noqa: BLE001
        pass


def _status(**kw):
    st.stats.update(kw)
    try:
        emitter.emit("onFarmStatus", st.api, dict(st.stats))
    except Exception:  # noqa: BLE001
        pass


def _fail(reason, level="error"):
    log(reason, level)
    _status(last_error=reason)
    return False


# ------------------------------------------------------------------ rekaman

def _load_recording(name):
    path = os.path.join(REC_DIR, name)
    frames = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    frames.append(json.loads(line))
    except Exception as exc:  # noqa: BLE001
        log(f"gagal memuat rekaman {name}: {exc}", "warn")
    return frames


def _slice_by_marker(frames, kind, pred, start=0):
    """Index event pertama (>= start) yang memenuhi pred, atau None."""
    for i in range(start, len(frames)):
        d = frames[i]
        if d.get("ev") == kind and pred(d):
            return i
    return None


def _motion_slice(frames, i0, i1):
    return [d for d in frames[i0:i1] if d.get("ev") in ("foot", "veh")]


class Recordings:
    def __init__(self):
        self.beli = _load_recording("beli_seed.jsonl")
        self.tanam = _load_recording("tanam_potato.jsonl")
        self.panen = _load_recording("panen_potato.jsonl")
        self.ok = bool(self.beli and self.tanam and self.panen)
        if not self.ok:
            log("rekaman farm tidak lengkap/tidak ditemukan di folder scripts/farm_recordings/, "
                "gerakan akan memakai jalan lurus biasa", "warn")
            return
        f = self.beli
        i_enter1 = _slice_by_marker(f, "enter_veh", lambda d: True)
        i_exit1 = _slice_by_marker(f, "exit_veh", lambda d: True)
        i_enter2 = _slice_by_marker(f, "enter_veh", lambda d: True, (i_exit1 or 0) + 1)
        self.drive_go = _motion_slice(f, i_enter1 or 0, i_exit1 or len(f))
        self.shop_idle = _motion_slice(f, i_exit1 or 0, i_enter2 or len(f))
        self.drive_back = _motion_slice(f, i_enter2 or len(f), len(f))

        g = self.tanam
        i_trunk_cmd = _slice_by_marker(g, "cmd", lambda d: d.get("text") == "/trunk")
        self.trunk_idle = _motion_slice(g, 0, i_trunk_cmd or len(g))
        # gap jalan di antara tiap "/plant plant" (dipakai berurutan, lalu diulang)
        plant_cmd_idx = [i for i, d in enumerate(g) if d.get("ev") == "cmd" and d.get("text") == "/plant plant"]
        self.plant_gaps = []
        prev = 0
        for idx in plant_cmd_idx:
            self.plant_gaps.append(_motion_slice(g, prev, idx))
            prev = idx + 1
        if not self.plant_gaps:
            self.plant_gaps = [[]]

        h = self.panen
        self.harvest_idle = _motion_slice(h, 0, len(h))


REC = Recordings()


# ------------------------------------------------------------------ state

class State:
    def __init__(self):
        self.api = None
        self.spawned = threading.Event()
        self.car_id = 0
        self.plant_idx = 0          # indeks gap rekaman tanam berikutnya yang dipakai
        self.dlg = None             # dialog terakhir: dict title/text/rows/b1/b2/id/style
        self.dlg_ver = 0
        self.chat_buf = []          # (waktu, teks) 40 pesan terakhir
        self.paused = not ENABLED
        self.abort = False
        self.next_ok = 0.0
        self.wait_kind = "grow"
        self.stage = "plant"       # "plant" -> "wait_grow" -> "harvest" -> kembali ke "plant"
        self.stats = {
            "state": "Dijeda" if not ENABLED else "Memulai",
            "paused": not ENABLED,
            "plant_sessions": 0,
            "harvest_sessions": 0,
            "potato_total": 0,
            "current_plants": 0,
            "plant_target": PLANT_TARGET,
            "next_run": 0.0,
            "last_error": "",
        }


st = State()


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


# ------------------------------------------------------------------ event

@emitter.on("onBotCreated")
def _on_created(bot, *_):
    st.api = bot
    threading.Thread(target=_worker, name="farm-bot", daemon=True).start()


@emitter.on("onFarmControl", sync=True)
def _control(bot, action, *_):
    if action == "pause":
        st.paused = True
        log("Dijeda: berlaku setelah langkah berjalan selesai", "warn")
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
    log("koneksi bot terputus", "warn")


@emitter.on("onShowChat")
def _chat(bot, message, *_):
    line = _s(message)
    st.chat_buf.append((time.time(), line))
    del st.chat_buf[:-40]


@emitter.on("onShowDialog", sync=True)
def _dialog(bot, dialog_id, style, title, info, button1, button2, *_):
    title, info = _s(title), _s(info)
    st.dlg = {
        "id": dialog_id, "style": style, "title": title, "text": info,
        "rows": _rows(info, style), "b1": _s(button1), "b2": _s(button2),
    }
    st.dlg_ver += 1


# ------------------------------------------------------------------ util dasar

def _send(cmd):
    log(f"kirim: {cmd}", "info")
    st.api.sendchat(cmd)


def _wait_dialog(timeout=10.0):
    ver = st.dlg_ver
    end = time.time() + timeout
    while time.time() < end:
        _check()
        if st.dlg_ver != ver:
            return st.dlg
        time.sleep(0.15)
    return None


def _click(d, btn, list_idx=-1, text=""):
    """Balas dialog d dengan jeda singkat seperti manusia. TIDAK menunggu apa pun sesudahnya
    -- panggil _wait_dialog() kalau mengharapkan dialog berikutnya, atau _wait_chat() kalau
    mengharapkan balasan chat (keduanya butuh waktu mulai yang akurat, jadi tidak digabung di sini)."""
    _check()
    delay = 0.4 + 0.5 * (hash((d["id"], btn, list_idx, time.time())) % 1000) / 1000.0
    time.sleep(min(delay, 0.9))
    st.api.SendDialogResponse(d["id"], btn, list_idx, text)


def _recent_chat(pattern, window=6.0):
    cutoff = time.time() - window
    for t, line in reversed(st.chat_buf):
        if t < cutoff:
            break
        m = pattern.search(line)
        if m:
            return m, line
    return None, None


def _wait_chat(pattern, timeout=8.0):
    """Tunggu pesan chat yang cocok. Memindai dari yang terbaru, bukan hanya pesan yang
    muncul SETELAH baris ini mulai berjalan — chat bisa saja sudah masuk sepersekian detik
    lebih dulu (mis. langsung menyusul respons dialog), dan tetap harus tertangkap."""
    start = time.time()
    end = start + timeout
    while time.time() < end:
        _check()
        for t, line in reversed(st.chat_buf):
            if t < start - 0.5:
                break
            m = pattern.search(line)
            if m:
                return m, line
        time.sleep(0.1)
    return None, None


# ------------------------------------------------------------------ replay gerak

def _apply_frame(d, offset):
    api = st.api
    bp = api.session.players.bot
    pos = d.get("pos") or {}
    x = pos.get("x", bp.x) + offset[0]
    y = pos.get("y", bp.y) + offset[1]
    z = pos.get("z", bp.z) + offset[2]
    try:
        bp._set_position_internal(x, y, z, update_velocity=False)
        spd = d.get("spd") or {}
        bp.velocity_x = float(spd.get("x", 0.0))
        bp.velocity_y = float(spd.get("y", 0.0))
        bp.velocity_z = float(spd.get("z", 0.0))
        if "keys" in d:
            bp.keys = int(d["keys"]) & 0xFFFF
        if "lr" in d:
            bp.lr = int(d["lr"])
        if "ud" in d:
            bp.ud = int(d["ud"])
        if "anim" in d and d["ev"] == "foot":
            bp.animation_id = int(d["anim"])
    except Exception as exc:  # noqa: BLE001
        log(f"replay: gagal set frame: {exc}", "warn")


def _heading_from(frames, i):
    if i + 1 >= len(frames):
        return None
    a, b = frames[i].get("pos"), frames[i + 1].get("pos")
    if not a or not b:
        return None
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    if abs(dx) < 1e-4 and abs(dy) < 1e-4:
        return None
    return (math.degrees(math.atan2(dy, dx)) + 90.0) % 360.0


def _replay(frames, duration=None, loop=False):
    """Putar ulang rekaman foot/veh, digeser (offset) supaya titik awalnya cocok
    dengan posisi bot saat ini. `duration` None = mainkan sekali penuh sesuai rekaman."""
    if not frames:
        return
    api = st.api
    first = frames[0].get("pos") or {}
    me = api.getbotposition()
    offset = (me[0] - first.get("x", me[0]), me[1] - first.get("y", me[1]), me[2] - first.get("z", me[2]))
    t_real0 = time.time()
    t_rec0 = frames[0].get("t", 0.0)
    end_real = None if duration is None else t_real0 + duration
    idx = 0
    while True:
        _check()
        d = frames[idx]
        _apply_frame(d, offset)
        h = _heading_from(frames, idx)
        if h is not None:
            try:
                api.setbotrotation(h)
            except Exception:  # noqa: BLE001
                pass
        target_real = t_real0 + (d.get("t", 0.0) - t_rec0)
        while time.time() < target_real:
            _check()
            time.sleep(min(0.05, max(0.0, target_real - time.time())))
        idx += 1
        if idx >= len(frames):
            if end_real is not None and time.time() < end_real and loop:
                idx = 0
                t_real0 = time.time()
                t_rec0 = frames[0].get("t", 0.0)
                continue
            break
        if end_real is not None and time.time() >= end_real:
            break


def _replay_vehicle(frames, label):
    if not REC.ok or not frames:
        log(f"{label}: rekaman tidak ada, memakai gerak lurus", "warn")
        tgt = SHOP_POS if "toko" in label else FARM_POS
        st.api.MoveToCoord(tgt[0], tgt[1], tgt[2], mode="vehicle", completion_distance=3.0)
        _sleep(2.0)
        return
    log(f"{label}: memutar ulang rekaman berkendara ({len(frames)} frame)", "info")
    _replay(frames)


# ------------------------------------------------------------------ /mypv

def _spawn_sadler():
    _status(state="Memanggil kendaraan (/mypv)")
    _send("/mypv")
    d = _wait_dialog(10.0)
    if d is None or "my vehicle" not in d["title"].lower():
        return _fail("Dialog My Vehicle tidak muncul setelah /mypv")
    idx, _ = _find_row(d["rows"], "sadler")
    if idx is None:
        return _fail(f"Tidak ada baris 'Sadler' di daftar kendaraan: {d['rows']}")
    _click(d, 1, idx)
    d2 = _wait_dialog(8.0)
    if d2 is None or "vehicle info" not in d2["title"].lower():
        return _fail("Dialog Vehicle Info tidak muncul setelah memilih Sadler")
    idx2, _ = _find_row(d2["rows"], "spawn vehicle")
    if idx2 is None:
        return _fail(f"Tidak ada opsi 'Spawn Vehicle': {d2['rows']}")
    _click(d2, 1, idx2)
    m, line = _wait_chat(SADLER_SPAWN_RE, 10.0)
    if m:
        st.car_id = int(m.group(1))
        log(f"Sadler spawn, id kendaraan={st.car_id} ({line[:90]})", "ok")
        return True
    log("pesan spawn Sadler tidak terbaca, mencari lewat stream kendaraan terdekat", "warn")
    best = None
    for vid, v in getattr(st.api, "getallvehicles", lambda: {})().items():
        if v.get("model_id") == SADLER_MODEL:
            d_ = math.hypot(v["x"] - FARM_POS[0], v["y"] - FARM_POS[1])
            if best is None or d_ < best[0]:
                best = (d_, vid)
    if best and best[0] < 60:
        st.car_id = best[1]
        log(f"Sadler ditemukan lewat stream, id={st.car_id}", "ok")
        return True
    return _fail("Sadler tidak ditemukan setelah /mypv (spawn mungkin gagal)")


# ------------------------------------------------------------------ seed

def _peek_seed():
    """Buka dialog /plant plant untuk membaca 'My Seed: N' tanpa menanam (Close)."""
    _send("/plant plant")
    d = _wait_dialog(8.0)
    if d is None:
        return None, None
    m = MYSEED_RE.search(d["title"])
    seed = int(m.group(1)) if m else None
    return d, seed


def _buy_seed():
    """Memanggil /buyseed berulang. HARUS dipanggil saat bot sudah berada di toko seed."""
    _status(state="Membeli seed (/buyseed)")
    seed = None
    for _ in range(6):
        _check()
        _send(f"/buyseed {BUY_TARGET}")
        time.sleep(0.8)
        m, line = _recent_chat(SEED_NOW_RE, 3.0)
        if m:
            seed = int(m.group(1))
            log(f"Seed dibeli, sekarang {seed} seed", "ok")
        full, _l = _recent_chat(re.compile(r"inventory is full", re.I), 3.0)
        if full:
            log("Batas pembelian seed tercapai untuk saat ini", "warn")
            break
        if seed is not None and seed >= SEED_COST * 4:
            break
        time.sleep(0.6)
    return seed


def _get_seed_from_trunk_or_buy():
    _status(state="Mengambil seed dari trunk")
    _send("/trunk")
    d = _wait_dialog(8.0)
    if d is None or "trunk storage" not in d["title"].lower():
        log("dialog Trunk Storage tidak muncul, langsung ke toko untuk membeli seed", "warn")
        _buy_seed_trip()
        return
    idx, _ = _find_row(d["rows"], "seed list")
    if idx is None:
        log("tidak ada 'Seed List' di trunk, langsung ke toko untuk membeli seed", "warn")
        _click(d, 0)       # tutup
        _buy_seed_trip()
        return
    _click(d, 1, idx)
    d2 = _wait_dialog(8.0)
    if d2 is None:
        _buy_seed_trip()
        return
    pidx, prow = _find_row(d2["rows"], "seed plant")
    m = re.search(r"\((\d+)\)", prow or "")
    trunk_seed = int(m.group(1)) if m else 0
    if trunk_seed <= 0 or pidx is None:
        log("seed di trunk kosong, perlu pergi ke toko untuk membeli seed", "info")
        _click(d2, 0)      # Back ke Trunk Storage
        _buy_seed_trip()
        return
    _click(d2, 1, pidx)
    d3 = _wait_dialog(8.0)
    widx, _ = _find_row((d3 or {}).get("rows", []), "withdraw from safe")
    if d3 is None or widx is None:
        log("menu withdraw tidak muncul, langsung ke toko untuk membeli seed", "warn")
        _buy_seed_trip()
        return
    _click(d3, 1, widx)
    d4 = _wait_dialog(8.0)
    if d4 is None:
        _buy_seed_trip()
        return
    _click(d4, 1, -1, str(trunk_seed))
    log(f"Mengambil {trunk_seed} seed dari trunk", "ok")
    d5 = _wait_dialog(8.0)
    if d5 is not None:
        _click(d5, 0)      # tutup Trunk Storage


# ------------------------------------------------------------------ tanam

def _plant_one(attempt_no):
    d, seed = _peek_seed()
    if d is None:
        return _fail("Dialog tanam (My Seed) tidak muncul")
    if seed is not None and seed < SEED_COST:
        _click(d, 0)       # Close, jangan tanam dulu
        _get_seed_from_trunk_or_buy()
        d, seed = _peek_seed()
        if d is None:
            return _fail("Dialog tanam tidak muncul setelah mengambil seed")
    pidx, _ = _find_row(d["rows"], "potato")
    if pidx is None:
        pidx = 0
    _click(d, 1, pidx)
    m, line = _wait_chat(re.compile(r"planting potato|too closes|hanya bisa menanam", re.I), 8.0)
    if m is None:
        log("tidak ada konfirmasi setelah menanam, lanjut mencoba", "warn")
        return "ok"
    low = line.lower()
    if "hanya bisa menanam" in low:
        return "full"
    if "too closes" in low:
        return "retry"
    return "ok"


def _plant_session():
    st.stats["current_plants"] = 0
    _status(state="Menanam Potato")
    planted = 0
    attempt = 0
    while planted < PLANT_TARGET:
        _check()
        gap = REC.plant_gaps[min(st.plant_idx, len(REC.plant_gaps) - 1)]
        st.plant_idx += 1
        if gap:
            _replay(gap)
        result = _plant_one(attempt)
        attempt += 1
        if result == "full":
            log(f"Plot penuh setelah {planted} tanaman", "info")
            break
        if result == "ok":
            planted += 1
            st.stats["current_plants"] = planted
            _status(current_plants=planted)
            log(f"Potato tertanam {planted}/{PLANT_TARGET}", "ok")
        elif result == "retry":
            log("posisi terlalu dekat tanaman lain, mencoba titik berikutnya", "warn")
        elif result is False:
            return False
        if attempt > PLANT_TARGET * 3:
            log("terlalu banyak percobaan, menghentikan sesi tanam", "warn")
            break
    st.stats["plant_sessions"] += 1
    _status(sessions_ok=True)
    return True


# ------------------------------------------------------------------ panen

def _check_grow_time():
    _send("/plant harvest")
    m, line = _wait_chat(re.compile(r"needs|loaded|harvest", re.I), 6.0)
    if m is None:
        log("tidak ada respons /plant harvest, memakai delay cadangan", "warn")
        return GROW_FALLBACK
    tm = TIME_RE.search(line)
    if tm:
        secs = int(tm.group(1)) * 60 + int(tm.group(2))
        log(f"Sisa waktu tumbuh: {secs} detik ({line[:90]})", "info")
        return secs + 20
    log(f"panen langsung jalan: {line[:90]}", "ok")
    return 0.0


def _load_once():
    _send("/loadplant")
    d = _wait_dialog(8.0)
    if d is None or "load plant" not in d["title"].lower():
        return None
    pidx, _ = _find_row(d["rows"], "potato")
    if pidx is None:
        _click(d, 0)
        return 0
    _click(d, 1, pidx)
    d2 = _wait_dialog(8.0)
    if d2 is None:
        return 0
    m = MAXLOAD_RE.search(_s(d2["text"]))
    maxload = int(m.group(1)) if m else 0
    if maxload <= 0:
        _click(d2, 0)
        return 0
    _click(d2, 1, -1, str(maxload))
    mm, line = _wait_chat(LOADED_RE, 8.0)
    loaded = int(mm.group(1)) if mm else maxload
    log(f"Potato dimuat ke Sadler: {loaded} ({line[:90] if line else ''})", "ok")
    return loaded


def _harvest_session():
    _status(state="Memanen Potato (/plant harvest)")
    _send("/plant harvest")
    time.sleep(1.0)
    total = 0
    while True:
        _check()
        n = _load_once()
        if not n:
            break
        total += n
        st.stats["potato_total"] += n
        _status(potato_total=st.stats["potato_total"])
        _replay(REC.harvest_idle, duration=2.0, loop=True) if REC.ok else _sleep(1.0)
    st.stats["harvest_sessions"] += 1
    _status(harvest_sessions=st.stats["harvest_sessions"])
    log(f"Sesi panen selesai, total {total} potato dimuat sesi ini", "ok")
    return True


# ------------------------------------------------------------------ siklus

def _ensure_at_farm():
    me = st.api.getbotposition()
    if math.hypot(me[0] - FARM_POS[0], me[1] - FARM_POS[1]) <= 60.0:
        return True
    if WARP_CMD:
        log(f"posisi jauh dari farm, mengirim perintah warp: {WARP_CMD}", "info")
        _send(WARP_CMD)
        _sleep(3.0)
        me = st.api.getbotposition()
        if math.hypot(me[0] - FARM_POS[0], me[1] - FARM_POS[1]) <= 60.0:
            return True
    return _fail(f"Bot tidak berada di dekat The Farm (jarak {math.hypot(me[0]-FARM_POS[0], me[1]-FARM_POS[1]):.0f} m) "
                 "dan tidak ada FARM_WARP_CMD yang berhasil. Set FARM_WARP_CMD atau pastikan karakter "
                 "login langsung di The Farm.")


def _buy_seed_trip():
    """Replay perjalanan Sadler ke toko seed dan balik, menggunakan rekaman beli_seed.jsonl."""
    if not REC.ok or not st.car_id:
        log("tidak ada rekaman/kendaraan untuk perjalanan beli seed, melewati trip (pakai seed yang ada)", "warn")
        return
    _status(state="Menuju toko seed")
    if not st.api.setbotvehicle(st.car_id, 0, 3.0):
        return _fail("Gagal naik Sadler untuk ke toko seed")
    _sleep(3.0)
    _replay_vehicle(REC.drive_go, "berkendara ke toko seed")
    st.api.setbotvehicle(0)
    _sleep(1.0)
    _status(state="Membeli seed di toko")
    _replay(REC.shop_idle, duration=3.0, loop=True)
    _buy_seed()
    if not st.api.setbotvehicle(st.car_id, 0, 3.0):
        return _fail("Gagal naik Sadler untuk kembali ke farm")
    _sleep(3.0)
    _status(state="Kembali ke farm")
    _replay_vehicle(REC.drive_back, "berkendara balik ke farm")
    st.api.setbotvehicle(0)
    _sleep(1.0)


def _worker():
    api = st.api
    log("worker farm aktif | target tanam=%d | seed/tanam=%d" % (PLANT_TARGET, SEED_COST), "info")
    _status()
    car_ready = False
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

            if not _ensure_at_farm():
                time.sleep(30)
                continue

            if not car_ready:
                if not _spawn_sadler():
                    time.sleep(30)
                    continue
                car_ready = True

            if st.stage == "plant":
                if not _plant_session():
                    time.sleep(30)
                    continue
                secs = _check_grow_time()      # /plant harvest: belum siap -> dapat sisa waktu tumbuh
                if secs > 0:
                    st.next_ok = time.time() + secs
                    st.stage = "wait_grow"
                else:
                    st.stage = "harvest"        # sempat langsung siap saat dicek
                continue

            if st.stage == "wait_grow":
                left = int(st.next_ok - time.time())
                if left > 0:
                    _status(state=f"Menunggu tanaman tumbuh ({left}s)", next_run=st.next_ok)
                    while time.time() < st.next_ok and not st.paused and not st.abort:
                        time.sleep(1)
                    _status(next_run=0.0)
                st.stage = "harvest"
                continue

            if st.stage == "harvest":
                # panggil /plant harvest LAGI di sini: panggilan sebelumnya hanya mengecek waktu
                # tumbuh, dan sekarang (setelah menunggu) panggilan ini yang benar-benar memanen,
                # baru dilanjutkan /loadplant berulang untuk memuatnya ke Sadler.
                if not _harvest_session():
                    time.sleep(30)
                    continue
                st.stage = "plant"
                continue
        except RuntimeError as exc:
            log(f"Dihentikan: {exc}", "warn")
            _status(last_error=str(exc))
            time.sleep(5)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[farm] error: {exc}")
            log(f"Error tak terduga: {exc}", "error")
            _status(last_error=str(exc))
            time.sleep(10)
