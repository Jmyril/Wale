"""Tiny stdlib web server that turns WaleBot into a chat website.

No frameworks, no dependencies. Run it and open http://127.0.0.1:8000

    python3 server.py
    PORT=9000 python3 server.py

Endpoints:
    GET  /            -> chat UI
    GET  /app.js      -> front-end script
    GET  /style.css   -> styles
    POST /chat        -> {"message": "..."} => {"reply": "...", "name": "..."}
    POST /chat/stream -> newline-delimited JSON, one {"t": word} per token,
                         then a final {"done": true, "learned": {...}}
"""

import json
import os
import re
import sys
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)  # the Markov core loads its corpus via relative paths
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from chatbot import get_bot, WaleBot  # noqa: E402

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
WEB_DIR = BASE_DIR

# Per-visitor brains. Off by default (one shared bot, one shared brain). Set
# WALE_MULTIUSER=1 to give every session id its own session + learnable layer.
MULTIUSER = os.environ.get("WALE_MULTIUSER", "0") == "1"
SESSION_DIR = os.path.join(BASE_DIR, "models", "sessions")
MAX_SESSIONS = int(os.environ.get("WALE_MAX_SESSIONS", "64"))

_STATIC = {
    "/": ("chat.html", "text/html; charset=utf-8"),
    "/chat": ("chat.html", "text/html; charset=utf-8"),
    "/chat.html": ("chat.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}

_bot = get_bot()
_lock = threading.Lock()          # serialises generation on a bot
_registry_lock = threading.Lock()  # guards _registry (multi-user only)
_registry = OrderedDict()          # session id -> WaleBot


def _session_bot(session_id):
    """Pick the bot for a session id. Single shared bot unless multiuser."""
    if not MULTIUSER:
        return _bot
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or ""))[:64] or "default"
    with _registry_lock:
        bot = _registry.get(sid)
        if bot is None:
            bot = WaleBot(brain_path=os.path.join(SESSION_DIR, sid + ".json"))
            _registry[sid] = bot
        _registry.move_to_end(sid)
        while len(_registry) > MAX_SESSIONS:
            _registry.popitem(last=False)
    return bot



class ChatHandler(BaseHTTPRequestHandler):
    server_version = "Wale/1.0"

    def log_message(self, fmt, *args):  # keep the console quiet-ish
        sys.stderr.write("[chatbot] " + (fmt % args) + "\n")

    def _send(self, code, body, content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, payload):
        self._send(code, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        entry = _STATIC.get(self.path.split("?")[0])
        if not entry:
            self._send_json(404, {"error": "not found"})
            return
        filename, content_type = entry
        path = os.path.join(WEB_DIR, filename)
        if not os.path.exists(path):
            self._send_json(500, {"error": f"missing {filename}"})
            return
        with open(path, "rb") as f:
            self._send(200, f.read(), content_type)

    def _read_message(self):
        """Parse the POST body. Returns (data, message) or (None, None)."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return None, None
        if not isinstance(data, dict):
            return None, None
        return data, str(data.get("message", ""))[:2000]

    def _send_stream(self, bot, message):
        with _lock:
            chunks = list(bot.reply_stream(message))
            learned = dict(bot.last_learning)
            name = bot.name
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for chunk in chunks:
                line = json.dumps({"t": chunk}, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
            final = json.dumps(
                {"done": True, "name": name, "learned": learned}, ensure_ascii=False
            ) + "\n"
            self.wfile.write(final.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/chat", "/chat/stream"):
            self._send_json(404, {"error": "not found"})
            return
        data, message = self._read_message()
        if data is None:
            self._send_json(400, {"error": "bad json"})
            return
        bot = _session_bot(data.get("session"))
        if path == "/chat/stream":
            self._send_stream(bot, message)
            return
        with _lock:
            reply = bot.reply(message)
            learned = dict(bot.last_learning)
        self._send_json(200, {"reply": reply, "name": bot.name, "learned": learned})


def main():
    httpd = ThreadingHTTPServer((HOST, PORT), ChatHandler)
    mode = "multi-user" if MULTIUSER else "single-user"
    print(f"{_bot.name} is listening on http://{HOST}:{PORT}  ({mode}, ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
