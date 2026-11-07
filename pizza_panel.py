"""
pizza_panel.py - panel web terpisah untuk log & kontrol bot pizza.

Taruh sejajar dashboard.py, lalu jalankan patch_dashboard.py sekali (atau edit manual 4 baris).
Halaman: /pizza   (memakai login Basic yang sama dengan dashboard)
"""
import json
import threading
import time
from collections import deque

from logic.events import emitter

LOCK = threading.RLock()
LOG = deque(maxlen=400)
_log_id = 0
BOT = {"api": None}
STATS = {
    "state": "Belum aktif", "paused": False, "current": 0, "total": 0,
    "sessions_ok": 0, "sessions_fail": 0, "pizzas": 0,
    "next_run": 0.0, "last_error": "",
}


def _add(level, msg):
    global _log_id
    with LOCK:
        _log_id += 1
        LOG.append((_log_id, time.strftime("%H:%M:%S"), level, str(msg)))


@emitter.on("onBotCreated", sync=True)
def _created(bot, *_):
    BOT["api"] = bot


@emitter.on("onPizzaLog", sync=True)
def _plog(bot, level, msg, *_):
    if bot is not None:
        BOT["api"] = bot
    _add(level, msg)


@emitter.on("onPizzaStatus", sync=True)
def _pstat(bot, stats, *_):
    with LOCK:
        STATS.update(stats)


def _state(since):
    with LOCK:
        return {
            "stats": dict(STATS),
            "now": time.time(),
            "log": [{"id": i, "t": t, "lv": lv, "m": m} for (i, t, lv, m) in LOG if i > since],
            "last_id": _log_id,
            "has_bot": BOT["api"] is not None,
        }


def handle_get(path, query):
    if path == "/pizza":
        return 200, PAGE, "text/html"
    if path == "/api/pizza/state":
        try:
            since = int(query.get("since", ["0"])[0])
        except ValueError:
            since = 0
        return 200, json.dumps(_state(since)), "application/json"
    return None


def handle_post(path, body):
    if path == "/api/pizza/control":
        action = str(body.get("action", ""))
        if action not in ("pause", "resume", "stop"):
            return {"ok": False, "msg": "Aksi tidak dikenal."}
        bot = BOT["api"]
        if bot is None:
            return {"ok": False, "msg": "Bot belum dibuat. Tekan Connect di dashboard dulu."}
        emitter.emit("onPizzaControl", bot, action)
        return {"ok": True}
    if path == "/api/pizza/clear":
        with LOCK:
            LOG.clear()
        return {"ok": True}
    return {"ok": False, "msg": "Endpoint tidak dikenal."}


PAGE = r"""<!doctype html>
<html lang="id"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pizza Bot</title>
<style>
:root{color-scheme:dark;--bg:#12151a;--card:#1b2028;--line:#2a313c;--fg:#e6e9ee;--mut:#8b95a5;--acc:#3b82f6;--ok:#22c55e;--warn:#eab308;--bad:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif;padding:12px;max-width:640px;margin:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:12px}
h2{margin:0 0 8px;font-size:15px}a{color:var(--acc);text-decoration:none}
.row{display:flex;gap:8px}.row>*{flex:1}
button{padding:10px 12px;border:0;border-radius:8px;background:var(--acc);color:#fff;font-size:15px;cursor:pointer}
button.sec{background:#2a313c}button.bad{background:var(--bad)}
#state{font-size:18px;font-weight:600}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;background:#2a313c;margin-left:6px}
.badge.run{background:#14532d}.badge.pause{background:#713f12}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}
.stat{background:#0f1217;border-radius:8px;padding:8px;text-align:center}
.stat b{display:block;font-size:20px}.stat span{color:var(--mut);font-size:12px}
.bar{height:8px;background:#0f1217;border-radius:99px;overflow:hidden;margin-top:10px}
.bar>div{height:100%;background:var(--acc);width:0}
#log,#issues{background:#0f1217;border:1px solid var(--line);border-radius:8px;padding:8px;font-size:13px}
#log{height:320px;overflow:auto}
#log div,#issues div{white-space:pre-wrap;word-break:break-word;margin-bottom:2px}
.t{color:var(--mut)}.info{color:var(--fg)}.ok{color:var(--ok)}.warn{color:var(--warn)}.error{color:var(--bad)}
.chk{display:flex;gap:8px;align-items:center;margin:8px 0;color:var(--mut);font-size:13px}
</style></head><body>

<div class="card"><a href="/">&larr; Kembali ke dashboard</a></div>

<div class="card">
<div><span id="state">...</span><span class="badge" id="badge"></span></div>
<div id="cd" style="color:var(--mut);margin-top:4px"></div>
<div class="bar"><div id="prog"></div></div>
<div class="grid">
<div class="stat"><b id="cur">0/0</b><span>Pizza sesi ini</span></div>
<div class="stat"><b id="pz">0</b><span>Total terkirim</span></div>
<div class="stat"><b><span id="sok" class="ok">0</span> / <span id="sfl" class="error">0</span></b><span>Sesi sukses / gagal</span></div>
</div>
<div class="row" style="margin-top:12px">
<button id="bt" onclick="toggle()">Jeda</button>
<button class="bad" onclick="ctl('stop')">Stop sekarang</button>
</div>
<div id="hint" style="color:var(--mut);font-size:12px;margin-top:6px">Jeda: berhenti setelah sesi berjalan selesai. Stop: berhenti seketika.</div>
</div>

<div class="card"><h2>Kendala terakhir</h2><div id="issues"><div class="t">Belum ada kendala.</div></div></div>

<div class="card"><h2>Log bot pizza</h2>
<div class="chk"><input type="checkbox" id="only"><span>Hanya tampilkan hasil &amp; kendala (sembunyikan info)</span></div>
<div id="log"></div>
<div style="margin-top:8px"><button class="sec" style="width:100%" onclick="clr()">Hapus log</button></div></div>

<script>
const $=id=>document.getElementById(id);
let since=0,all=[],paused=false,nextRun=0,skew=0;
async function api(p,b){const r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json();}
async function ctl(a){const r=await api('/api/pizza/control',{action:a});if(r.ok===false)alert(r.msg);}
function toggle(){ctl(paused?'resume':'pause');}
async function clr(){await api('/api/pizza/clear',{});all=[];since=0;redraw();$('issues').innerHTML='<div class="t">Belum ada kendala.</div>';}
function line(l){const d=document.createElement('div');d.className=l.lv;const t=document.createElement('span');t.className='t';t.textContent=l.t+' ';d.appendChild(t);d.appendChild(document.createTextNode(l.m));return d;}
function redraw(){
  const box=$('log'),only=$('only').checked,near=box.scrollHeight-box.scrollTop-box.clientHeight<40;
  box.textContent='';
  for(const l of all){if(only&&l.lv==='info')continue;box.appendChild(line(l));}
  if(near)box.scrollTop=box.scrollHeight;
  const bad=all.filter(l=>l.lv==='warn'||l.lv==='error').slice(-5).reverse();
  if(bad.length){const iss=$('issues');iss.textContent='';bad.forEach(l=>iss.appendChild(line(l)));}
}
$('only').addEventListener('change',redraw);
function render(s){
  const st=s.stats;paused=st.paused;nextRun=st.next_run;skew=s.now-Date.now()/1000;
  $('state').textContent=st.state;
  const b=$('badge');b.textContent=paused?'dijeda':'aktif';b.className='badge '+(paused?'pause':'run');
  $('bt').textContent=paused?'Lanjutkan':'Jeda';
  $('cur').textContent=st.current+'/'+st.total;$('pz').textContent=st.pizzas;
  $('sok').textContent=st.sessions_ok;$('sfl').textContent=st.sessions_fail;
  $('prog').style.width=(st.total?Math.min(100,st.current/st.total*100):0)+'%';
  if(s.log.length){all=all.concat(s.log).slice(-400);redraw();}
  since=s.last_id;
}
function tick(){
  if(nextRun>0){const left=Math.max(0,Math.round(nextRun-(Date.now()/1000+skew)));
    $('cd').textContent='Sesi berikutnya dalam '+Math.floor(left/60)+' mnt '+(left%60)+' dtk';}
  else $('cd').textContent='';
}
async function poll(){try{render(await api('/api/pizza/state?since='+since));}catch(e){$('state').textContent='Panel tidak terjangkau...';}setTimeout(poll,1500);}
setInterval(tick,1000);poll();
</script></body></html>
"""
