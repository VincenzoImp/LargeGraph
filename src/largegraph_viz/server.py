"""Read-only loopback viewer, backed by the disk index and bounded queries."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .api import Analysis


def serve(output: Path, port: int = 8765) -> None:
    analysis = Analysis.open(output)
    report = analysis.report

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            params = parse_qs(url.query)

            def argument(name, default=None):
                return params.get(name, [default])[0]

            try:
                if len(self.path) > 16_384:
                    raise ValueError("Request too long")
                if url.path in {"/", "/index.html"}:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(report.stat().st_size))
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    with report.open("rb") as stream:
                        import shutil

                        shutil.copyfileobj(stream, self.wfile)
                    return
                if url.path == "/api/neighbors":
                    result = analysis.neighbors(argument("node", ""), int(argument("limit", "100")))
                elif url.path == "/api/members":
                    result = analysis.members(
                        int(argument("community", "0")),
                        int(argument("limit", "100")),
                        int(argument("after", "-1")),
                    )
                else:
                    self.respond(404, {"error": "Not found"})
                    return
                self.respond(200, result)
            except (ValueError, OSError) as exc:
                self.respond(400, {"error": str(exc)})

        def respond(self, status, data):
            body = json.dumps(data, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            logging.getLogger(__name__).debug(format, *args)

    # The server never binds to a public interface or exposes arbitrary files.
    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as http:
        print(f"Graph explorer: http://127.0.0.1:{http.server_port} (Ctrl-C to stop)", flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass
