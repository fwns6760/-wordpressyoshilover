"""
Cloud Run用HTTPサーバー
POST /run → rss_fetcher.pyを実行
GET  /health → ヘルスチェック
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

TRUE_VALUES = {"1", "true", "yes", "on"}

SECRET = os.environ.get("RUN_SECRET", "").strip()
PORT   = int(os.environ.get("PORT", 8080))
ENABLE_TEST_GEMINI = os.environ.get("ENABLE_TEST_GEMINI", "").strip().lower() in TRUE_VALUES
CLOUD_RUN_AUTH_MODES = {"cloud_run", "iam", "oidc"}
OIDC_SERVICE_ACCOUNT = os.environ.get("RUN_OIDC_SERVICE_ACCOUNT", "").strip()
OIDC_AUDIENCE = os.environ.get("RUN_OIDC_AUDIENCE", "").strip()
RUN_SUBPROCESS_TIMEOUT = int(os.environ.get("RUN_SUBPROCESS_TIMEOUT", "285"))


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


RUN_DRAFT_ONLY = _env_flag("RUN_DRAFT_ONLY", False)


def _secret_is_configured() -> bool:
    return bool(SECRET)


def _auth_mode() -> str:
    return os.environ.get("RUN_AUTH_MODE", "secret").strip().lower() or "secret"


def _uses_cloud_run_auth() -> bool:
    return _auth_mode() in CLOUD_RUN_AUTH_MODES


def _extract_bearer_token(handler: BaseHTTPRequestHandler) -> str:
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return ""
    return auth[7:].strip()


def _verify_oidc_token(token: str) -> bool:
    if not token:
        return False
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(
            token,
            GoogleAuthRequest(),
            audience=OIDC_AUDIENCE or None,
        )
    except Exception:
        return False

    issuer = claims.get("iss", "")
    email = claims.get("email", "")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        return False
    if OIDC_SERVICE_ACCOUNT and email != OIDC_SERVICE_ACCOUNT:
        return False
    if claims.get("email_verified") is False:
        return False
    return True


def _is_authorized(handler: BaseHTTPRequestHandler) -> bool:
    if _uses_cloud_run_auth():
        return _verify_oidc_token(_extract_bearer_token(handler))
    return _secret_is_configured() and handler.headers.get("X-Secret", "") == SECRET


def _parse_limit(body: str, content_type: str = "") -> str:
    limit = None

    if body:
        if "application/json" in content_type:
            try:
                payload = json.loads(body)
                limit = payload.get("limit")
            except json.JSONDecodeError:
                limit = None

        if limit is None:
            params = parse_qs(body, keep_blank_values=False)
            values = params.get("limit")
            if values:
                limit = values[0]

    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 10

    if parsed < 1:
        parsed = 1
    return str(parsed)


def _run_started_payload() -> dict:
    return {
        "event": "run_started",
        "run_draft_only": RUN_DRAFT_ONLY,
        "auto_tweet_enabled": _env_flag("AUTO_TWEET_ENABLED", False),
        "publish_require_image": _env_flag("PUBLISH_REQUIRE_IMAGE", True),
        "revision": os.environ.get("K_REVISION", "").strip(),
    }


def _log_run_started() -> None:
    print(json.dumps(_run_started_payload(), ensure_ascii=False), flush=True)


def _run_fetcher(limit: str) -> tuple[int, str]:
    cmd = ["python3", "src/rss_fetcher.py", "--limit", limit]
    if RUN_DRAFT_ONLY:
        cmd.append("--draft-only")
    try:
        result = subprocess.run(
            cmd,
            cwd="/app",
            timeout=RUN_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return 504, f"rss_fetcher timed out after {RUN_SUBPROCESS_TIMEOUT}s"

    if result.returncode != 0:
        return 500, f"rss_fetcher failed with exit code {result.returncode}"
    return 200, "completed"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # アクセスログ抑制

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, "OK")
        elif self.path == "/test-gemini":
            if not ENABLE_TEST_GEMINI:
                self._respond(404, "Not Found")
                return
            if not _uses_cloud_run_auth() and not _secret_is_configured():
                self._respond(503, "RUN_SECRET is not configured")
                return
            if not _is_authorized(self):
                self._respond(403, "Forbidden")
                return
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
        if not _uses_cloud_run_auth() and not _secret_is_configured():
            self._respond(503, "RUN_SECRET is not configured")
            return
        if not _is_authorized(self):
            self._respond(403, "Forbidden")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else ""
        limit = _parse_limit(body, self.headers.get("Content-Type", ""))
        _log_run_started()
        code, message = _run_fetcher(limit)
        self._respond(code, message)

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())


if __name__ == "__main__":
    print(f"起動: port={PORT}")
    HTTPServer(("", PORT), Handler).serve_forever()
