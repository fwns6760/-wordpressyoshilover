"""
Cloud Run用HTTPサーバー
POST /run → rss_fetcher.pyを実行
GET  /health → ヘルスチェック
"""
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = os.environ.get("RUN_SECRET", "sebata1413")
PORT   = int(os.environ.get("PORT", 8080))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # アクセスログ抑制

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, "OK")
        elif self.path == "/test-gemini":
            try:
                result = subprocess.run(
                    ["gemini", "-p", "読売ジャイアンツについて一言"],
                    capture_output=True, text=True, timeout=90, cwd="/app"
                )
                out = result.stdout.strip() or result.stderr.strip() or "(no output)"
                self._respond(200, out[:500])
            except Exception as e:
                self._respond(200, f"ERROR: {e}")
        else:
            self._respond(404, "Not Found")

    def do_POST(self):
        if self.path != "/run":
            self._respond(404, "Not Found")
            return
        key = self.headers.get("X-Secret", "")
        if key != SECRET:
            self._respond(403, "Forbidden")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else ""
        limit = "1" if "limit=1" in body else "10"

        def run():
            subprocess.run(
                ["python3", "src/rss_fetcher.py", "--limit", limit],
                cwd="/app"
            )

        threading.Thread(target=run, daemon=True).start()
        self._respond(200, "started")

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())


if __name__ == "__main__":
    print(f"起動: port={PORT}")
    HTTPServer(("", PORT), Handler).serve_forever()
