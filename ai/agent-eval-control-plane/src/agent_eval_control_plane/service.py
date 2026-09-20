from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .evaluator import release_gate
from .storage import Store


def make_server(db_path: str, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = unquote(urlparse(self.path).path)
            if path == "/health":
                self._send(200, {"status": "ok", "mode": "read-only"})
                return
            with Store(db_path) as store:
                store.migrate()
                if path.startswith("/runs/"):
                    report = store.get_run_report(path.removeprefix("/runs/"))
                    self._send(200 if report else 404, report or {"error": "run_not_found"})
                    return
                if path.startswith("/suites/") and path.endswith("/gate"):
                    suite = path[len("/suites/") : -len("/gate")].strip("/")
                    self._send(200, release_gate(store.results_for_suite(suite)))
                    return
            self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            self._send(405, {"error": "read_only_api"})

        def log_message(self, *_: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)
