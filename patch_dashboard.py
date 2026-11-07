"""
Jalankan sekali di folder repo (sejajar dashboard.py):   python patch_dashboard.py
Menambahkan panel Pizza ke dashboard.py. Aman dijalankan ulang (tidak menggandakan).
"""
import sys

PATH = "dashboard.py"
src = open(PATH, encoding="utf-8").read()

if "pizza_panel" in src:
    print("dashboard.py sudah dipatch, tidak ada yang diubah.")
    sys.exit(0)

edits = [
    # 1. import
    ("import main as pyrak_main\n",
     "import main as pyrak_main\nimport pizza_panel\n"),
    # 2. route GET
    ('        if url.path == "/":\n            return self._send(200, PAGE, "text/html")\n',
     '        if url.path == "/":\n            return self._send(200, PAGE, "text/html")\n'
     '        if url.path == "/pizza" or url.path.startswith("/api/pizza"):\n'
     '            r = pizza_panel.handle_get(url.path, parse_qs(url.query))\n'
     '            if r:\n'
     '                return self._send(*r)\n'),
    # 3. route POST
    ("        self._send(200, json.dumps(do_action(urlparse(self.path).path, body)))\n",
     "        path = urlparse(self.path).path\n"
     '        if path.startswith("/api/pizza"):\n'
     "            return self._send(200, json.dumps(pizza_panel.handle_post(path, body)))\n"
     "        self._send(200, json.dumps(do_action(path, body)))\n"),
    # 4. link di halaman utama
    ('<div class="card"><h2>Koneksi</h2>',
     '<div class="card"><a href="/pizza" style="color:#3b82f6">Buka panel Pizza Bot &rarr;</a></div>\n'
     '<div class="card"><h2>Koneksi</h2>'),
]

for old, new in edits:
    if src.count(old) != 1:
        print("GAGAL: potongan kode tidak ditemukan persis satu kali:\n" + old)
        sys.exit(1)
    src = src.replace(old, new)

open(PATH, "w", encoding="utf-8").write(src)
print("dashboard.py berhasil dipatch.")
