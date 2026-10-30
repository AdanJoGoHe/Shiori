"""Preview issue #23 with synthetic browser-only data; never loads a memory deployment."""

import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src/second_brain/web/prototype"
ASSETS = {"index.html", "prototype.css", "prototype.js"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.split("?", 1)[0].lstrip("/") or "index.html"
        if name not in ASSETS:
            self.send_error(404)
            return
        content = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(name)[0] + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'none'; connect-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/?variant=A", flush=True)
        print(
            "Synthetic prototype. Changes stay in this tab; Ctrl+C stops the preview.", flush=True
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
