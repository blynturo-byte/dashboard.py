#!/usr/bin/env python3
"""
dashboard.py - dashboard web untuk bot SA-MP (PyRakSamp).

Taruh file ini di folder paling atas repo PyRakSamp (sejajar main.py), lalu jalankan:
    python dashboard.py

Environment variable:
    DASH_PASS       (WAJIB) password dashboard. Tanpa ini server menolak jalan.
    DASH_USER       user dashboard (default: admin)
    PORT            port HTTP (diisi otomatis oleh Render/Railway)
    SAMP_HOST, SAMP_PORT, BOT_NICK   nilai awal form koneksi (opsional)
    UCP_USER, UCP_PASS, CHAR_SLOT    nilai awal login otomatis (opsional)
    BOT_FPS         turunkan beban CPU, mis. 30 (opsional)
    BOT_RATE_PLAYER interval sync pemain, mis. 0.3 (opsional)

Bot ini tidak punya renderer sama sekali (klien tanpa game), jadi tidak ada
"render sekitar". Dashboard ini juga tidak membaca daftar pemain/kendaraan/
textdraw sekitar, hanya chat dan dialog.
"""
import argparse
import base64
import hmac
import json
import os
import re
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from logic.events import emitter
from bot import Bot
from samp.sync import PlayerSyncScheduler
import main as pyrak_main

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.ini")

DASH_USER = os.environ.get("DASH_USER", "admin")
DASH_PASS = os.environ.get("DASH_PASS", "")

MAX_TRIES = 4        # batas jawaban otomatis per sesi login
ARM_WINDOW = 90      # detik: auto-login berhenti sendiri setelah ini
MAX_RECONNECT = 10   # batas auto-reconnect beruntun

LOCK = threading.RLock()
LOG = deque(maxlen=500)
_log_id = 0

S = {
    "bot": None,
    "busy": False,
    "status": "Belum terhubung.",
    "connected": False,
    "spawned": False,
    "manual_stop": False,
    "dialog": None,
    "armed": False,
    "armed_at": 0.0,
    "tries": 0,
    "auto_reconnect": False,
    "reconnect_n": 0,
    "params": {
        "host": os.environ.get("SAMP_HOST", ""),
        "port": int(os.environ.get("SAMP_PORT", "7777") or 7777),
        "nick": os.environ.get("BOT_NICK", ""),
    },
    "login": {
        "user": os.environ.get("UCP_USER", ""),
        "pass": os.environ.get("UCP_PASS", ""),
        "slot": int(os.environ.get("CHAR_SLOT", "0") or 0),
        "persist": False,
    },
}

# ---------------------------------------------------------------- util

COLOR_TAG = re.compile(r"\{[0-9a-fA-F]{6}\}")


def _s(x):
    if isinstance(x, (bytes, bytearray)):
        return bytes(x).decode("cp1252", "replace")
    return "" if x is None else str(x)


def clean(x):
    return COLOR_TAG.sub("", _s(x))


def add_log(text):
    global _log_id
    with LOCK:
        _log_id += 1
        LOG.append((_log_id, time.strftime("%H:%M:%S"), clean(text)))


def set_status(text):
    with LOCK:
        S["status"] = text


def parse_items(style, info):
    if style not in (2, 4, 5):
        return None
    lines = info.replace("\r", "").rstrip("\n").split("\n")
    if style == 5 and lines:
        lines = lines[1:]  # baris pertama = header
    return [ln.replace("\t", " | ") for ln in lines]


# ---------------------------------------------------------------- login otomatis

def arm_login():
    with LOCK:
        S["armed"] = True
        S["armed_at"] = time.time()
        S["tries"] = 0


def send_dialog(dialog_id, button, item, text):
    with LOCK:
        d = S["dialog"]
        bot = S["bot"]
        if not bot or not d or d["id"] != dialog_id:
            return False
        S["dialog"] = None
    try:
        bot.api.SendDialogResponse(dialog_id, button, item, text)
        return True
    except Exception as exc:  # noqa: BLE001
        add_log(f"[bot] gagal membalas dialog: {exc}")
        return False


def auto_respond(d):
    with LOCK:
        if not S["armed"]:
            return
        if time.time() - S["armed_at"] > ARM_WINDOW or S["tries"] >= MAX_TRIES:
            S["armed"] = False
            S["status"] = "Auto-login berhenti (batas waktu/percobaan). Balas dialog manual."
            return
        low = d["raw"].lower()
        if "regist" in low or "daftar" in low:
            return  # jangan sentuh dialog pendaftaran
        lg = S["login"]
        style = d["style"]
        if style == 3 or (style == 1 and ("password" in low or "kata sandi" in low)):
            resp, what = (1, 0, lg["pass"]), "password"
        elif style == 1 and ("username" in low or "ucp" in low):
            resp, what = (1, 0, lg["user"]), "username"
        elif style in (2, 4, 5) and lg["slot"] > 0 and ("karakter" in low or "character" in low):
            resp, what = (1, lg["slot"] - 1, ""), f"slot karakter {lg['slot']}"
        else:
            return
        S["tries"] += 1
        S["status"] = f"Auto-login: mengirim {what}..."
    add_log(f"[bot] auto-login mengirim {what}")
    threading.Timer(0.6, send_dialog, (d["id"],) + resp).start()


# ---------------------------------------------------------------- event bot

@emitter.on("onShowChat")
def _ev_chat(bot, message, *_):
    add_log(message)


@emitter.on("onShowDialog")
def _ev_dialog(bot, dialog_id, style, title, info, button1, button2, *_):
    title, info = clean(title), clean(info)
    d = {
        "id": dialog_id,
        "style": style,
        "title": title,
        "text": info,
        "b1": clean(button1),
        "b2": clean(button2),
        "items": parse_items(style, info),
        "raw": title + " " + info,
    }
    with LOCK:
        S["dialog"] = d
    add_log(f"[dialog] {title}")
    auto_respond(d)


@emitter.on("onconnect")
def _ev_connect(bot, *_):
    with LOCK:
        S["connected"] = True
        S["reconnect_n"] = 0
        S["status"] = "Terhubung ke server. Menunggu dialog login..."
        persist = S["login"]["persist"] and S["login"]["pass"]
    add_log("[bot] terhubung ke server")
    if persist:
        arm_login()


@emitter.on("onSpawn")
def _ev_spawn(bot, *_):
    with LOCK:
        S["spawned"] = True
        S["armed"] = False
        S["status"] = "Bot sudah spawn."
    add_log("[bot] spawn")


@emitter.on("disconnect")
def _ev_disconnect(bot, *_):
    with LOCK:
        S["connected"] = False
        S["spawned"] = False
        S["dialog"] = None
        S["status"] = "Terputus."
    add_log("[bot] koneksi terputus")
    maybe_reconnect()


KICK = {1: "versi salah", 2: "nick sudah login", 3: "versi mod salah", 4: "slot penuh"}


@emitter.on("onKick")
def _ev_kick(bot, reason_code=0, *_):
    add_log(f"[bot] ditolak server: {KICK.get(reason_code, reason_code)}")


@emitter.on("onHandshakeFailed")
def _ev_handshake(bot, stage=None, reason=None, *_):
    add_log(f"[bot] handshake gagal ({stage}: {reason})")
    set_status("Handshake gagal. Cek IP/port, atau hosting memblokir UDP.")


@emitter.on("onOpenConnectionReplyTimeout")
def _ev_open_timeout(bot, attempts=0, *_):
    add_log(f"[bot] server belum membalas (percobaan {attempts})")


@emitter.on("onServerTimeout")
def _ev_timeout(bot, elapsed=0, timeout=0, *_):
    add_log(f"[bot] server tidak merespons {elapsed:.0f}s")


@emitter.on("OnGameText")
def _ev_gametext(bot, style=0, time_ms=0, text="", *_):
    add_log(f"[gametext] {text}")


# ---------------------------------------------------------------- koneksi

def _make_bot(host, port, nick):
    ns = argparse.Namespace(
        host=host, port=int(port), nick=nick, proxy=None,
        rate_player=os.environ.get("BOT_RATE_PLAYER") or None,
        coord_delay=None, random_ip=False, random_nick=False,
    )
    cfg = pyrak_main.load_config(CONFIG_PATH, ns)
    if os.environ.get("BOT_FPS"):
        cfg["fps"] = max(1.0, min(1000.0, float(os.environ["BOT_FPS"])))
    sched = PlayerSyncScheduler(
        rate_player=cfg["rate_player"],
        rate_player_min=cfg["rate_player_min"],
        rate_player_max=cfg["rate_player_max"],
        rate_vehicle_min=cfg["rate_vehicle_min"],
        rate_vehicle_max=cfg["rate_vehicle_max"],
        sync_idle_after_min=cfg["sync_idle_after_min"],
        sync_idle_after_max=cfg["sync_idle_after_max"],
        sync_idle_backoff_factor_min=cfg["sync_idle_backoff_factor_min"],
        sync_idle_backoff_factor_max=cfg["sync_idle_backoff_factor_max"],
        player_idle_interval_multiplier_min=cfg["player_idle_interval_multiplier_min"],
        player_idle_interval_multiplier_max=cfg["player_idle_interval_multiplier_max"],
        vehicle_idle_interval_multiplier_min=cfg["vehicle_idle_interval_multiplier_min"],
        vehicle_idle_interval_multiplier_max=cfg["vehicle_idle_interval_multiplier_max"],
        rate_player_jitter_max=cfg["rate_player_jitter_max"],
        rate_player_fluctuation_chance=cfg["rate_player_fluctuation_chance"],
        rate_player_fluctuation_max=cfg["rate_player_fluctuation_max"],
    )
    bot = Bot(
        cfg["host"], cfg["port"], cfg["nick"],
        sync_scheduler=sched,
        fps=cfg["fps"],
        pings_ips_continuous=cfg["pings_ips_continuous"],
        proxy_address=None,
        server_password=cfg["server_password"],
    )
    bot.session.players.bot.set_coord_delay(cfg["coord_delay"])
    return bot


def _connect_worker(host, port, nick):
    try:
        bot = S["bot"]
        if bot is None:
            bot = _make_bot(host, port, nick)
            S["bot"] = bot
        else:
            bot.api.SetConnectionProfile(nick, server_ip=host, server_port=int(port))
        ok = bot.api.connect()
        if not ok:
            reconnecting = False
            try:
                reconnecting = bot.session.is_reconnecting()
            except Exception:  # noqa: BLE001
                pass
            if not reconnecting:
                set_status("Gagal terhubung. Cek IP/port, atau hosting memblokir UDP.")
                add_log("[bot] koneksi gagal")
    except Exception as exc:  # noqa: BLE001
        set_status(f"Error: {exc}")
        add_log(f"[bot] error: {exc}")
    finally:
        with LOCK:
            S["busy"] = False


def start_connect(host, port, nick):
    with LOCK:
        if S["busy"]:
            return False, "Masih memproses koneksi sebelumnya."
        if S["connected"]:
            return False, "Bot sudah terhubung."
        S["busy"] = True
        S["manual_stop"] = False
        S["reconnect_n"] = 0
        S["params"] = {"host": host, "port": int(port), "nick": nick}
        S["status"] = "Menghubungkan..."
    add_log(f"[bot] menghubungkan ke {host}:{port} sebagai {nick}")
    threading.Thread(target=_connect_worker, args=(host, int(port), nick), daemon=True).start()
    return True, "ok"


def stop_bot():
    with LOCK:
        S["manual_stop"] = True
        S["armed"] = False
        bot = S["bot"]
    if bot:
        try:
            bot.api.disconnect()
        except Exception as exc:  # noqa: BLE001
            add_log(f"[bot] error disconnect: {exc}")
    with LOCK:
        S["connected"] = False
        S["spawned"] = False
        S["dialog"] = None
        S["status"] = "Diputuskan manual."
    add_log("[bot] diputuskan manual")


def maybe_reconnect():
    with LOCK:
        if S["manual_stop"] or not S["auto_reconnect"]:
            return
        if S["reconnect_n"] >= MAX_RECONNECT:
            S["status"] = "Auto-reconnect berhenti (batas percobaan)."
            return
        S["reconnect_n"] += 1
        n = S["reconnect_n"]
        bot = S["bot"]
    delay = min(30 * 2 ** (n - 1), 300)
    try:
        if bot and bot.session.is_reconnecting():
            return  # pustaka sudah menjadwalkan reconnect sendiri
    except Exception:  # noqa: BLE001
        pass
    add_log(f"[bot] reconnect dalam {delay}s (percobaan {n}/{MAX_RECONNECT})")
    set_status(f"Reconnect dalam {delay}s...")
    threading.Timer(delay, _reconnect_now).start()


def _reconnect_now():
    with LOCK:
        bot = S["bot"]
        if S["manual_stop"] or S["connected"] or S["busy"] or not bot:
            return
        S["busy"] = True
    try:
        if bot.session.is_reconnecting():
            return
    except Exception:  # noqa: BLE001
        pass
    threading.Thread(
        target=_connect_worker,
        args=(S["params"]["host"], S["params"]["port"], S["params"]["nick"]),
        daemon=True,
    ).start()


# ---------------------------------------------------------------- HTTP

def state_json(since):
    with LOCK:
        d = S["dialog"]
        dialog = None
        if d:
            dialog = {k: d[k] for k in ("id", "style", "title", "text", "b1", "b2", "items")}
        logs = [{"id": i, "t": t, "m": m} for (i, t, m) in LOG if i > since]
        lg = S["login"]
        return {
            "status": S["status"],
            "connected": S["connected"],
            "spawned": S["spawned"],
            "busy": S["busy"],
            "armed": S["armed"],
            "tries": S["tries"],
            "auto_reconnect": S["auto_reconnect"],
            "params": S["params"],
            "login": {"user": lg["user"], "slot": lg["slot"],
                      "persist": lg["persist"], "has_pass": bool(lg["pass"])},
            "dialog": dialog,
            "log": logs,
            "last_id": _log_id,
        }


def do_action(path, body):
    if path == "/api/connect":
        host = str(body.get("host", "")).strip()
        nick = str(body.get("nick", "")).strip()
        try:
            port = int(body.get("port", 7777))
        except (TypeError, ValueError):
            return {"ok": False, "msg": "Port tidak valid."}
        if not host or not nick:
            return {"ok": False, "msg": "Host dan nick wajib diisi."}
        if len(nick) > 20:
            return {"ok": False, "msg": "Nick maksimal 20 karakter."}
        with LOCK:
            S["auto_reconnect"] = bool(body.get("auto_reconnect"))
        ok, msg = start_connect(host, port, nick)
        return {"ok": ok, "msg": msg}

    if path == "/api/disconnect":
        stop_bot()
        return {"ok": True}

    if path == "/api/chat":
        text = str(body.get("text", "")).strip()
        with LOCK:
            bot, ok = S["bot"], S["connected"]
        if not text:
            return {"ok": False, "msg": "Pesan kosong."}
        if not (bot and ok):
            return {"ok": False, "msg": "Bot belum terhubung."}
        try:
            bot.api.sendchat(text)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "msg": str(exc)}
        add_log("> " + text)
        return {"ok": True}

    if path == "/api/login":
        with LOCK:
            lg = S["login"]
            lg["user"] = str(body.get("user", lg["user"]))
            if body.get("pass"):
                lg["pass"] = str(body["pass"])
            try:
                lg["slot"] = max(0, int(body.get("slot", lg["slot"])))
            except (TypeError, ValueError):
                lg["slot"] = 0
            lg["persist"] = bool(body.get("persist"))
            d = S["dialog"]
        arm_login()
        set_status("Auto-login aktif, menunggu dialog server...")
        add_log("[bot] auto-login diaktifkan")
        if d:
            auto_respond(d)
        return {"ok": True}

    if path == "/api/dialog":
        with LOCK:
            d = S["dialog"]
        if not d:
            return {"ok": False, "msg": "Tidak ada dialog aktif."}
        try:
            button = 1 if int(body.get("button", 1)) else 0
            item = int(body.get("item", -1))
        except (TypeError, ValueError):
            return {"ok": False, "msg": "Input tidak valid."}
        if d["items"] is not None and item < 0:
            item = 0
        if d["items"] is None:
            item = -1
        ok = send_dialog(d["id"], button, item, str(body.get("text", "")))
        return {"ok": ok}

    return {"ok": False, "msg": "Endpoint tidak dikenal."}


class Handler(BaseHTTPRequestHandler):
    server_version = "BotDash/1.0"

    def log_message(self, *_):
        pass  # jangan penuhi log hosting

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "):
            return False
        try:
            user, _, pw = base64.b64decode(h[6:]).decode("utf-8").partition(":")
        except Exception:  # noqa: BLE001
            return False
        ok_u = hmac.compare_digest(user.encode(), DASH_USER.encode())
        ok_p = hmac.compare_digest(pw.encode(), DASH_PASS.encode())
        return ok_u and ok_p

    def _guard(self):
        if self._authed():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Bot Dashboard"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/healthz":
            return self._send(200, "ok", "text/plain")
        if not self._guard():
            return
        if url.path == "/":
            return self._send(200, PAGE, "text/html")
        if url.path == "/api/state":
            try:
                since = int(parse_qs(url.query).get("since", ["0"])[0])
            except ValueError:
                since = 0
            return self._send(200, json.dumps(state_json(since)))
        self._send(404, '{"ok":false}')

    def do_POST(self):  # noqa: N802
        if not self._guard():
            return
        try:
            n = min(int(self.headers.get("Content-Length", "0")), 10_000)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except Exception:  # noqa: BLE001
            return self._send(400, '{"ok":false,"msg":"JSON tidak valid"}')
        self._send(200, json.dumps(do_action(urlparse(self.path).path, body)))


PAGE = r"""<!doctype html>
<html lang="id"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bot Dashboard</title>
<style>
:root{color-scheme:dark;--bg:#12151a;--card:#1b2028;--line:#2a313c;--fg:#e6e9ee;--mut:#8b95a5;--acc:#3b82f6;--ok:#22c55e;--bad:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif;padding:12px;max-width:640px;margin:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:12px}
h2{margin:0 0 8px;font-size:15px}label{display:block;color:var(--mut);font-size:12px;margin:8px 0 3px}
input[type=text],input[type=password],input[type=number]{width:100%;padding:9px;border-radius:8px;border:1px solid var(--line);background:#0f1217;color:var(--fg);font-size:16px}
.row{display:flex;gap:8px}.row>*{flex:1}
button{padding:10px 12px;border:0;border-radius:8px;background:var(--acc);color:#fff;font-size:15px;cursor:pointer}
button.sec{background:#2a313c}button.bad{background:var(--bad)}
.chk{display:flex;gap:8px;align-items:center;margin-top:8px;color:var(--mut);font-size:13px}
#st{display:flex;gap:8px;align-items:center}.dot{width:10px;height:10px;border-radius:50%;background:var(--bad)}.dot.on{background:var(--ok)}
#log{height:260px;overflow:auto;background:#0f1217;border:1px solid var(--line);border-radius:8px;padding:8px;font-size:13px}
#log div{white-space:pre-wrap;word-break:break-word;margin-bottom:2px}#log .t{color:var(--mut)}
#dtext{white-space:pre-wrap;max-height:120px;overflow:auto;background:#0f1217;border-radius:8px;padding:8px;font-size:13px}
.it{padding:6px 8px;border-radius:6px;cursor:pointer;font-size:14px}.it.sel{background:var(--acc)}
#items{max-height:150px;overflow:auto;background:#0f1217;border-radius:8px;margin-top:6px}
</style></head><body>

<div class="card"><div id="st"><span class="dot" id="dot"></span><span id="status">...</span></div></div>

<div class="card"><h2>Koneksi</h2>
<label>Host server</label><input type="text" id="host" autocapitalize="off" autocorrect="off">
<div class="row"><div><label>Port</label><input type="number" id="port" value="7777"></div>
<div><label>Nick bot</label><input type="text" id="nick" autocapitalize="off" autocorrect="off"></div></div>
<div class="chk"><input type="checkbox" id="arc"><span>Auto-reconnect (jeda 30s, naik bertahap, maks 10x)</span></div>
<div class="row" style="margin-top:10px"><button onclick="connect()">Connect</button><button class="bad" onclick="disconnect()">Disconnect</button></div></div>

<div class="card"><h2>Login UCP &amp; karakter</h2>
<label>Username UCP</label><input type="text" id="user" autocapitalize="off" autocorrect="off">
<label>Password (kosong = pakai yang sudah tersimpan di server)</label><input type="password" id="pass" autocomplete="off">
<label>Slot karakter (0 = pilih manual)</label><input type="number" id="slot" value="0" min="0">
<div class="chk"><input type="checkbox" id="persist"><span>Aktifkan lagi tiap kali bot tersambung (setelah reconnect)</span></div>
<div style="margin-top:10px"><button style="width:100%" onclick="login()">Aktifkan auto-login</button></div>
<div class="chk" id="armst"></div></div>

<div class="card" id="dlgcard" style="display:none"><h2 id="dtitle"></h2>
<div id="dtext"></div><div id="items"></div>
<input type="text" id="dinput" style="margin-top:6px;display:none" autocapitalize="off" autocorrect="off">
<div class="row" style="margin-top:8px"><button id="db1" onclick="reply(1)"></button><button class="sec" id="db2" onclick="reply(0)"></button></div></div>

<div class="card"><h2>Chat &amp; command</h2><div id="log"></div>
<div class="row" style="margin-top:8px"><input type="text" id="msg" placeholder="teks atau /command" style="flex:4" autocapitalize="off" autocorrect="off">
<button style="flex:1" onclick="send()">Kirim</button></div></div>

<script>
const $=id=>document.getElementById(id);
let since=0,filled=false,sel=-1,curDlg=null;
async function api(p,b){const r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json();}
function toast(r){if(r&&r.ok===false&&r.msg)alert(r.msg);}
async function connect(){toast(await api('/api/connect',{host:$('host').value,port:$('port').value,nick:$('nick').value,auto_reconnect:$('arc').checked}));}
async function disconnect(){await api('/api/disconnect',{});}
async function login(){toast(await api('/api/login',{user:$('user').value,pass:$('pass').value,slot:$('slot').value,persist:$('persist').checked}));$('pass').value='';}
async function send(){const t=$('msg').value;if(!t)return;const r=await api('/api/chat',{text:t});if(r.ok)$('msg').value='';else toast(r);}
async function reply(b){if(!curDlg)return;toast(await api('/api/dialog',{button:b,item:sel,text:$('dinput').value}));}
$('msg').addEventListener('keydown',e=>{if(e.key==='Enter')send();});
function drawDialog(d){
  if(!d){curDlg=null;$('dlgcard').style.display='none';return;}
  const changed=!curDlg||curDlg.id!==d.id||curDlg.title!==d.title;
  $('dlgcard').style.display='block';
  if(!changed)return;
  curDlg=d;sel=-1;$('dinput').value='';
  $('dtitle').textContent=d.title;
  $('dtext').textContent=d.text;$('dtext').style.display=d.items?'none':'block';
  const box=$('items');box.textContent='';
  if(d.items){d.items.forEach((t,i)=>{const e=document.createElement('div');e.className='it';e.textContent=(i+1)+'. '+t;
    e.onclick=()=>{sel=i;[...box.children].forEach((c,j)=>c.classList.toggle('sel',j===i));};box.appendChild(e);});}
  $('dinput').style.display=(d.style===1||d.style===3)?'block':'none';
  $('dinput').type=d.style===3?'password':'text';
  $('db1').textContent=d.b1||'OK';$('db2').textContent=d.b2;$('db2').style.display=d.b2?'block':'none';
}
function render(s){
  $('status').textContent=s.status+(s.busy?' (memproses...)':'');
  $('dot').className='dot'+(s.connected?' on':'');
  $('armst').textContent=s.armed?('Auto-login aktif (percobaan '+s.tries+')'):'';
  if(!filled){filled=true;$('host').value=s.params.host;$('port').value=s.params.port;$('nick').value=s.params.nick;
    $('user').value=s.login.user;$('slot').value=s.login.slot;$('persist').checked=s.login.persist;$('arc').checked=s.auto_reconnect;}
  const log=$('log');const near=log.scrollHeight-log.scrollTop-log.clientHeight<40;
  for(const l of s.log){const d=document.createElement('div');const t=document.createElement('span');t.className='t';t.textContent=l.t+' ';
    d.appendChild(t);d.appendChild(document.createTextNode(l.m));log.appendChild(d);}
  while(log.children.length>500)log.removeChild(log.firstChild);
  if(s.log.length&&near)log.scrollTop=log.scrollHeight;
  since=s.last_id;drawDialog(s.dialog);
}
async function poll(){try{render(await api('/api/state?since='+since));}catch(e){$('status').textContent='Dashboard tidak terjangkau...';}setTimeout(poll,1500);}
poll();
</script></body></html>
"""


def main():
    if not DASH_PASS:
        print("Set environment variable DASH_PASS dulu (password dashboard).", file=sys.stderr)
        sys.exit(1)
    port = int(os.environ.get("PORT", "8080"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    print(f"Dashboard jalan di port {port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
