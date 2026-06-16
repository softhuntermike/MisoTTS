"""
Local proxy server for BusMap test UI.

Serves test_busmap.html at / and proxies /busmap-api/* → api.busmap.vn
so the browser never hits a CORS wall.

Usage:
    python proxy_server.py [--port 8080]
"""

import argparse
import os
import sys
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BUSMAP_API_BASE = os.environ.get("BUSMAP_API_BASE", "https://api.busmap.vn")
BUSMAP_API_KEY  = os.environ.get("BUSMAP_API_KEY", "")
PROXY_PREFIX    = "/busmap-api"
HTML_FILE       = os.path.join(os.path.dirname(__file__), "test_busmap.html")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Accept, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        qs   = self.path[len(path):]

        # ── Serve the HTML test file ──────────────────────────────────
        if path in ("/", "/test_busmap.html"):
            try:
                with open(HTML_FILE, "rb") as f:
                    body = f.read()
                # Patch the default API base so the page calls our proxy path
                body = body.replace(
                    b'value="https://api.busmap.vn"',
                    b'value=""',
                ).replace(
                    b'"https://api.busmap.vn"',
                    b'""',
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_error(404, "test_busmap.html not found")
            return

        # ── Proxy /busmap-api/* → api.busmap.vn ──────────────────────
        if path.startswith(PROXY_PREFIX):
            upstream_path = path[len(PROXY_PREFIX):]
            upstream_url  = BUSMAP_API_BASE + upstream_path + qs
            headers = {"Accept": "application/json", "User-Agent": "MisoTTS-proxy/1.0"}
            if BUSMAP_API_KEY:
                headers["Authorization"] = f"Bearer {BUSMAP_API_KEY}"
            try:
                req  = Request(upstream_url, headers=headers)
                with urlopen(req, timeout=10) as resp:
                    body        = resp.read()
                    status      = resp.status
                    content_type = resp.headers.get("Content-Type", "application/json")
            except HTTPError as exc:
                body, status, content_type = exc.read(), exc.code, "application/json"
            except URLError as exc:
                body = json.dumps({"error": str(exc.reason)}).encode()
                status, content_type = 502, "application/json"

            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    print(f"\n🚌  BusMap proxy server running on http://0.0.0.0:{args.port}")
    print(f"    HTML  → http://localhost:{args.port}/")
    print(f"    Proxy → http://localhost:{args.port}{PROXY_PREFIX}/* → {BUSMAP_API_BASE}/*")
    print(f"\n    In the test page, set  API Base URL  to an empty string (already patched).")
    print(f"    Set endpoint paths to:  {PROXY_PREFIX}/api/v1/routes  etc.\n")
    print("    Ctrl-C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
