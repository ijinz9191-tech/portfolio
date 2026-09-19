"""Loopback read-only HTTP JSON interface. Not an Internet production server."""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, parse_qs

from .store import Store, ValidationError, packed


def make_server(filename, port=0):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MetricContractLab/1"
        sys_version = ""
        def log_message(self, *_):
            pass

        def respond(self, status, data):
            body = packed(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if len(self.path) > 2048:
                return self.respond(414, {"error": "URL_TOO_LONG"})
            if self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
                return self.respond(403, {"error": "HOST_NOT_ALLOWED"})
            store = None
            try:
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=5)
                if any(len(values) != 1 for values in query.values()):
                    raise ValidationError("DUPLICATE_QUERY_KEY")
                store = Store(filename, readonly=True)
                if parsed.path == "/health" and not query:
                    result = {"status": "ok", "read_only": True, "schema": 1}
                elif parsed.path == "/contracts" and not query:
                    result = {"contracts": store.contracts()}
                elif parsed.path == "/quality" and not query:
                    result = store.quality()
                elif parsed.path == "/metrics" and set(query).issubset({"start", "end", "metric"}) and {"start", "end"}.issubset(query):
                    result = {"metrics": store.metrics(query["start"][0], query["end"][0], query.get("metric", [None])[0])}
                elif re.fullmatch(r"/lineage/[1-9][0-9]{0,9}", parsed.path) and not query:
                    result = store.lineage(int(parsed.path.rsplit("/", 1)[1]))
                else:
                    return self.respond(404, {"error": "ROUTE_NOT_FOUND"})
                self.respond(200, result)
            except (ValidationError, ValueError) as exc:
                self.respond(400, {"error": str(exc) if isinstance(exc, ValidationError) else "INVALID_QUERY"})
            except Exception:
                self.respond(503, {"error": "STORE_UNAVAILABLE"})
            finally:
                if store:
                    store.close()

        def do_POST(self):
            self.respond(405, {"error": "READ_ONLY_API"})
        do_PUT = do_DELETE = do_PATCH = do_POST
    return HTTPServer(("127.0.0.1", port), Handler)
