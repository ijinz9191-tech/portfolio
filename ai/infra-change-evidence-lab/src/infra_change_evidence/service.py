from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote
from .storage import EvidenceStore

def create_server(host: str, port: int, store: EvidenceStore) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            elif self.path == "/summary":
                self._send(200, store.summary())
            elif self.path.startswith("/decisions/"):
                item = store.get(unquote(self.path[len("/decisions/"):]))
                self._send(200, item) if item else self._send(404, {"error": "not found"})
            else:
                self._send(404, {"error": "not found"})
        def do_POST(self) -> None:
            self._send(405, {"error": "read-only API"})
        def log_message(self, *_args) -> None:
            return
    return ThreadingHTTPServer((host, port), Handler)
