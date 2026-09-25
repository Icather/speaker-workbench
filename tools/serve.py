# -*- coding: utf-8 -*-
"""Launcher for the voice-labeling workbench.

Starts a local HTTP server (with Range support, so audio seeking is instant),
optionally refreshes the data pipeline, then opens the browser.

Run:  python tools\\_launcher.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)


def _cfg():
    fp = os.path.join(PROJ, "config.json")
    if os.path.exists(fp):
        try:
            return json.load(open(fp, encoding="utf-8"))
        except Exception:
            pass
    return {}


CFG = _cfg()


def _path(key, default):
    v = os.environ.get("VOICE_DECK_" + key.upper()) or CFG.get(key) or default
    return v if os.path.isabs(v) else os.path.normpath(os.path.join(PROJ, v))


OUT = _path("out", ".")
REC = _path("recordings", "demo/recordings")
CONV = _path("transcripts", "demo/transcripts")
VOICES = os.path.join(OUT, "voices.json")
BAK = os.path.join(OUT, "voices.bak.json")
DATA = os.path.join(OUT, "data.js")


# --------------------------------------------------------------- helpers
def find_python_with_numpy():
    """Prefer the isolated venv that already has numpy; fall back to self."""
    cands = [
        CFG.get("python", ""),
        os.environ.get("VOICE_DECK_PYTHON", ""),
        os.path.join(PROJ, ".venv", "Scripts", "python.exe"),
        os.path.join(PROJ, ".venv", "bin", "python"),
        sys.executable,
    ]
    for c in cands:
        if not os.path.exists(c):
            continue
        try:
            r = subprocess.run([c, "-c", "import numpy"], capture_output=True, timeout=60)
            if r.returncode == 0:
                return c
        except Exception:
            pass
    return None


def seed_demo_voices():
    """Demo mode only (no config.json): initialise voices.json from the seed so
    the suggestion feature is visible the moment the page opens. Real users who
    point config.json at their own data are never touched."""
    if os.path.exists(VOICES) or os.path.exists(os.path.join(PROJ, "config.json")):
        return
    src = os.path.join(PROJ, "demo", "seed_voices.json")
    if not os.path.exists(src):
        return
    try:
        open(VOICES, "wb").write(open(src, "rb").read())
        print("（demo 模式：已用 demo/seed_voices.json 初始化 voices.json）")
    except Exception:
        pass


def needs_sync():
    """True when data.js is missing or older than any recording / transcript."""
    if not os.path.exists(DATA):
        return True
    d = os.path.getmtime(DATA)
    watches = []
    if os.path.isdir(REC):
        watches += [os.path.join(REC, f) for f in os.listdir(REC)
                    if os.path.splitext(f)[1].lower() in
                    (".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".opus", ".wma")]
    conv = CONV
    if os.path.isdir(conv):
        watches += [os.path.join(conv, f) for f in os.listdir(conv) if f.endswith(".moss.srt")]
    return any(os.path.getmtime(w) > d for w in watches if os.path.exists(w))


def run_sync(py):
    print("检测到新录音/新转写稿，正在更新数据（增量）…")
    try:
        subprocess.run([py, os.path.join(HERE, "sync.py")], cwd=HERE, timeout=1800)
    except Exception as e:
        print("  更新失败（不影响使用）：%s" % e)


def free_port(start=8899, tries=20):
    for p in range(start, start + tries):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return None


# --------------------------------------------------------------- server
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=OUT, **kw)

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/load"):
            if os.path.exists(VOICES):
                try:
                    return self._json(json.load(open(VOICES, encoding="utf-8")))
                except Exception as e:
                    return self._json({"error": str(e)}, 500)
            return self._json({})
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/save"):
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n)
            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception as e:
                return self._json({"ok": False, "error": "bad json: %s" % e}, 400)
            if not isinstance(obj, dict) or "voices" not in obj:
                return self._json({"ok": False, "error": "missing 'voices'"}, 400)
            try:
                if os.path.exists(VOICES):
                    try:
                        open(BAK, "wb").write(open(VOICES, "rb").read())
                    except Exception:
                        pass
                with open(VOICES, "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False, indent=1)
                self.server.saved = time.strftime("%H:%M:%S")
                return self._json({"ok": True, "saved": len(obj.get("voices", {})),
                                   "at": self.server.saved})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 500)
        return self._json({"ok": False, "error": "not found"}, 404)

    # ---- Range support so <audio> can seek without downloading the whole file
    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            self._rng = None
            return super().send_head()
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        size = os.fstat(f.fileno()).st_size
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if not m:
            f.close()
            return super().send_head()
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            f.close()
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._rng = (start, end)
        f.seek(start)
        return f

    def copyfile(self, source, outputfile):
        rng = getattr(self, "_rng", None)
        if not rng:
            return super().copyfile(source, outputfile)
        start, end = rng
        left = end - start + 1
        while left > 0:
            chunk = source.read(min(1 << 16, left))
            if not chunk:
                break
            outputfile.write(chunk)
            left -= len(chunk)


# --------------------------------------------------------------- main
def main():
    os.chdir(OUT)
    print("=" * 56)
    print("  声纹标注台")
    print("=" * 56)
    if not os.path.exists(DATA):
        print("！缺少 data.js —— 先跑一次 tools\\sync.py 生成数据")
    seed_demo_voices()
    py = find_python_with_numpy()
    if py and needs_sync():
        run_sync(py)
    elif py is None:
        print("（未找到带 numpy 的 Python，跳过自动更新；新增录音请手动跑 tools\\sync.py）")

    port = free_port()
    if port is None:
        print("！找不到空闲端口，请检查是否已有一个实例在运行")
        return 1
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.saved = None
    url = "http://127.0.0.1:%d/index.html" % port
    print("\n服务已启动：%s" % url)
    print("保存位置：%s" % VOICES)
    print("\n【在这个窗口按 Ctrl+C 可停止服务】\n")
    threading.Timer(0.8, lambda: (None if os.environ.get("TAPE_NO_BROWSER")
                                  else webbrowser.open(url))).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
