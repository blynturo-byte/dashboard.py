"""
scripts/pizza_bot.py - otomatis sidejob Pizza Delivery untuk PyRakSamp (v2, dengan status/log untuk panel).

Taruh di folder `scripts/` (sejajar bot.py). Otomatis dimuat oleh Bot._load_scripts().
Log & status dikirim ke panel lewat event "onPizzaLog" / "onPizzaStatus" (lihat pizza_panel.py).

Alur satu sesi:
  cek /delays -> jalan ke motor pizza (model 448) -> naik -> Start Job -> /engine kalau mati
  -> ulangi: checkpoint -> berkendara -> turun -> Y -> naik -> ... -> kembalikan motor -> tunggu delay

Environment variable (opsional):
  PIZZA_AUTO=0         mulai dalam keadaan dijeda (nyalakan dari panel)
  PIZZA_DELIVERIES=10  jumlah pizza per sesi (set 1 untuk tes)
  PIZZA_DELAY=1200      delay cadangan (detik) kalau /delays tidak memuat baris pizza
"""
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
FALLBACK_DELAY = float(os.environ.get("PIZZA_DELAY", "1200"))
DELAY_MARGIN = 5.0
KEY_YES = 65536                        # tombol Y di SA-MP

COLOR_TAG = re.compile(r"\{[0-9a-fA-F]{6}\}")
UNITS = {"second": 1, "sec": 1, "detik": 1, "minute": 60, "min": 60,
         "menit": 60, "hour": 3600, "jam": 3600}


class State:
    def __init__(self):
        self.api = None
        self.spawned = threading.Event()
        self.vehicles = {}             # id -> (model, x, y, z)
        self.bike_id = 0
        self.start_pos = None
        self.target = None             # (x, y, z, radius)
        self.target_ver = 0
        self.icon = None
        self.engine_off = False
        self.job_started = threading.Event()
        self.want_delays = False
        self.delays_evt = threading.Event()
        self.delays_secs = None
        self.ended_moves = set()
        self.next_ok = 0.0
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
    return False


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
    st.target = None
    st.vehicles.clear()
    log("koneksi bot terputus", "warn")


@emitter.on("onVehicleStreamIn")
def _veh_in(bot, model_id, vehicle_id, x, y, z, *_):
    st.vehicles[int(vehicle_id)] = (int(model_id), float(x), float(y), float(z))


@emitter.on("onVehicleStreamOut")
def _veh_out(bot, vehicle_id, *_):
    st.vehicles.pop(int(vehicle_id), None)


def _set_target(x, y, z, radius, src):
    st.target = (float(x), float(y), float(z), float(radius or 0.0))
    st.target_ver += 1
    log(f"target baru ({src}): {x:.0f}, {y:.0f}, {z:.0f} r={radius}", "info")


@emitter.on("OnSetCheckpoint")
def _cp(bot, x, y, z, radius, *_):
    _set_target(x, y, z, radius, "checkpoint")


@emitter.on("OnSetRaceCheckpoint")
def _rcp(bot, cp_type, position, next_position, radius, *_):
    _set_target(position[0], position[1], position[2], radius, "race-checkpoint")


@emitter.on("OnDisableCheckpoint")
def _cp_off(bot, *_):
    st.target = None


@emitter.on("OnDisableRaceCheckpoint")
def _rcp_off(bot, *_):
    st.target = None


@emitter.on("onSetMapIcon")
def _icon(bot, icon_id, xyz, marker_type, style, *_):
    st.icon = (float(xyz[0]), float(xyz[1]), float(xyz[2]))


@emitter.on("onShowChat")
def _chat(bot, message, *_):
    if "mesin masih mati" in _s(message).lower():
        st.engine_off = True


@emitter.on("OnCoordMoveEnd")
def _move_end(bot, movement, status, *_):
    try:
        st.ended_moves.add(int(movement.get("movement_id")))
    except Exception:  # noqa: BLE001
        pass


def _parse_seconds(text):
    total = 0
    for n, unit in re.findall(
        r"(\d+)\s*(second|sec|detik|minute|min|menit|hour|jam)", text.lower()
    ):
        total += int(n) * UNITS[unit]
    return total


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


# ------------------------------------------------------------------ aksi

def _remaining_delay():
    st.delays_secs = None
    st.delays_evt.clear()
    st.want_delays = True
    st.api.sendchat("/delays")
    if not st.delays_evt.wait(8):
        log("dialog /delays tidak muncul (8s), pakai delay cadangan", "warn")
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
    me = st.api.getbotposition()
    best = None
    for vid, (model, x, y, z) in list(st.vehicles.items()):
        if model != PIZZA_MODEL:
            continue
        pos = _veh_pos(vid) or (x, y, z)
        d = _dist2(me, pos)
        if best is None or d < best[0]:
            best = (d, vid, pos)
    return best


def _go(target, mode, radius=0.0, timeout=240):
    api = st.api
    x, y, z = target[0], target[1], target[2]
    cd = max(1.5, min(radius * 0.5, 6.0)) if radius else 2.0
    reach = max(cd + 1.5, 4.0)
    mid = api.MoveToCoord(x, y, z, mode=mode, completion_distance=cd,
                          stop_on_dialog=False)
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
        time.sleep(0.5)
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
    bp = st.api.session.players.bot
    for val in (KEY_YES, 0):
        try:
            if hasattr(bp, "set_keys"):
                bp.set_keys(val)
            else:
                bp.keys = val
        except Exception as exc:  # noqa: BLE001
            log(f"gagal menekan Y: {exc}", "error")
            return
        time.sleep(0.4 if val else 0.1)


def _wait_new_target(ver, timeout):
    end = time.time() + timeout
    while time.time() < end:
        _check()
        if st.target is not None and st.target_ver != ver:
            return st.target
        time.sleep(0.25)
    return None


def _deliver():
    for attempt in range(3):
        ver = st.target_ver
        _press_y()
        t = _wait_new_target(ver, 8)
        if t:
            return t
        log(f"server belum merespons Y, mencoba lagi ({attempt + 1}/3)", "warn")
    return None


def _drive(tgt):
    if not st.api.session.players.bot.is_in_vehicle():
        raise RuntimeError("bot tidak berada di kendaraan")
    return _go(tgt, "vehicle", tgt[3] if len(tgt) > 3 else 0.0)


# ------------------------------------------------------------------ siklus

def _run_job():
    api = st.api
    _status(state="Mencari motor pizza", current=0, total=DELIVERIES)
    log("mulai sesi pizza", "info")

    found = _find_bike()
    if not found:
        return _fail("Motor pizza tidak ditemukan di sekitar bot (spawn dekat tempat pizza)")
    _, vid, pos = found
    st.bike_id, st.start_pos = vid, pos

    if _dist2(api.getbotposition(), pos) > 6.0:
        _status(state="Berjalan ke motor pizza")
        log(f"jalan ke motor id={vid}", "info")
        if not _go(pos, "walk", 0.0, 120):
            return _fail("Gagal sampai ke motor pizza (waktu habis)")

    ver = st.target_ver
    st.job_started.clear()
    _status(state="Naik motor")
    if not _enter(vid):
        return _fail("Gagal naik motor (terlalu jauh atau tidak ada di stream)")
    _engine_if_off()

    _status(state="Menunggu dialog Start Job")
    if not _wait_event(st.job_started, 15):
        return _fail("Dialog Start Job tidak muncul (mungkin masih delay atau salah motor)")
    log("Start Job ditekan", "ok")
    _engine_if_off()

    tgt = _wait_new_target(ver, 30)
    if tgt is None and st.icon:
        tgt = (*st.icon, 3.0)
        log("checkpoint tidak ada, memakai map icon sebagai target", "warn")
    if tgt is None:
        return _fail("Checkpoint pertama tidak muncul setelah Start Job")

    delivered = 0
    while tgt:
        _status(state=f"Berkendara ke tujuan {min(delivered + 1, DELIVERIES)}/{DELIVERIES}"
                if delivered < DELIVERIES else "Mengembalikan motor")
        if not _drive(tgt):
            return _fail("Gagal sampai ke target (waktu habis / tersangkut)")
        _exit_vehicle()

        if delivered >= DELIVERIES:
            log("Motor dikembalikan, sesi selesai", "ok")
            return True

        _status(state=f"Mengantar pizza {delivered + 1}/{DELIVERIES}")
        t = _deliver()
        delivered += 1
        st.stats["pizzas"] += 1
        _status(current=delivered)
        log(f"Pizza terkirim {delivered}/{DELIVERIES}", "ok")

        if t is None and delivered >= DELIVERIES and st.start_pos:
            t = (*st.start_pos, 3.0)        # titik awal untuk kembalikan motor
            log("tidak ada checkpoint kembali, menuju titik awal motor", "warn")
        if t is None:
            return _fail("Checkpoint berikutnya tidak muncul setelah menekan Y "
                         "(Y mungkin tidak terkirim)")

        _status(state="Naik motor lagi")
        if not _enter(vid):
            return _fail("Gagal naik motor lagi setelah mengantar")
        _engine_if_off()
        tgt = t
    return True


def _worker():
    api = st.api
    log(f"worker aktif | pizza/sesi={DELIVERIES} | delay cadangan={FALLBACK_DELAY:g}s", "info")
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

            _status(state="Memeriksa delay (/delays)")
            remain = _remaining_delay()
            if remain is None:
                remain = max(0.0, st.next_ok - time.time())
            if remain > 0:
                log(f"Menunggu delay pizza {int(remain)} detik", "info")
                _status(state="Menunggu delay", next_run=time.time() + remain + DELAY_MARGIN)
                end = time.time() + remain + DELAY_MARGIN
                while time.time() < end and not st.paused:
                    _check()
                    time.sleep(1)
                _status(next_run=0.0)
                continue

            if _run_job():
                st.next_ok = time.time() + FALLBACK_DELAY
                _status(sessions_ok=st.stats["sessions_ok"] + 1)
            else:
                _status(sessions_fail=st.stats["sessions_fail"] + 1,
                        state="Gagal, coba lagi 60 detik")
                end = time.time() + 60
                while time.time() < end and not st.paused:
                    _check()
                    time.sleep(1)
        except RuntimeError as exc:
            log(f"Sesi dihentikan: {exc}", "warn")
            _status(sessions_fail=st.stats["sessions_fail"] + 1, last_error=str(exc))
            time.sleep(5)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[pizza] error: {exc}")
            log(f"Error tak terduga: {exc}", "error")
            _status(last_error=str(exc))
            time.sleep(10)
