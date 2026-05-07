"""MANUAL-INTAKE-GCP-001 — small Cloud Run-friendly HTTP service that
exposes ``manual_intake.run_manual_intake`` to a mobile-first GUI.

Routes:
    GET  /            — mobile-first single-screen HTML form
    GET  /health      — liveness probe (no auth)
    GET  /manifest.webmanifest — minimal PWA manifest (no auth)
    POST /manual-intake — JSON or form-encoded submission (token required)

Auth:
    The ``MANUAL_INTAKE_TOKEN`` env var is required at runtime. Requests
    must present the token via either the ``X-Manual-Intake-Token`` header
    or a ``token`` field in the form / JSON body. Mismatch → 403.

Hard constraints (mirror the CLI):
    - never publishes; only WP draft creation
    - never calls Gemini / X API
    - never adds an RSS source or scrapes article bodies
    - memo never reaches body / source_text / Gemini prompt
    - article_type is metadata only — never used as a source fact
    - WP receives category_id (int list), never the category name string
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
_VENDOR = str(ROOT / "vendor")
_SRC = str(ROOT / "src")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.tools import manual_intake as mi  # noqa: E402

LOGGER = logging.getLogger("manual_intake_service")

TOKEN_ENV = "MANUAL_INTAKE_TOKEN"
TOKEN_HEADER = "X-Manual-Intake-Token"
PORT_ENV = "PORT"
DEFAULT_PORT = 8080
MAX_BODY_BYTES = 32 * 1024  # 32 KiB — enough for URL + memo + summary


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _require_token() -> str:
    return (os.environ.get(TOKEN_ENV) or "").strip()


def _request_token(handler: BaseHTTPRequestHandler, body_token: str) -> str:
    header = handler.headers.get(TOKEN_HEADER, "") or ""
    return (header.strip() or (body_token or "").strip())


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: str,
    *,
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(encoded)


def _read_body(handler: BaseHTTPRequestHandler) -> tuple[bytes, str]:
    length_raw = handler.headers.get("Content-Length", "0") or "0"
    try:
        length = int(length_raw)
    except ValueError:
        length = 0
    if length <= 0:
        return b"", ""
    if length > MAX_BODY_BYTES:
        # Drain only up to the cap; reject above.
        return b"", "body_too_large"
    body = handler.rfile.read(length)
    return body, ""


def _parse_request_body(
    body: bytes, content_type: str
) -> tuple[dict[str, str], str]:
    """Return (payload_dict, error_reason)."""
    if not body:
        return {}, ""
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if ctype == "application/json":
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}, "invalid_json"
        if not isinstance(data, dict):
            return {}, "invalid_json"
        return {str(k): "" if v is None else str(v) for k, v in data.items()}, ""
    # Default to form-encoded.
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return {}, "invalid_encoding"
    parsed = parse_qs(text, keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}, ""


# ---------------------------------------------------------------------------
# HTML form (mobile-first)
# ---------------------------------------------------------------------------


_HTML_FORM = """<!DOCTYPE html>
<html lang=\"ja\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">
<meta name=\"theme-color\" content=\"#f57f17\">
<meta name=\"apple-mobile-web-app-capable\" content=\"yes\">
<meta name=\"apple-mobile-web-app-status-bar-style\" content=\"default\">
<link rel=\"manifest\" href=\"/manifest.webmanifest\">
<title>YOSHILOVER 手動投入</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", \"Hiragino Sans\", sans-serif; background: #fafafa; color: #222; }
  @media (prefers-color-scheme: dark) { body { background: #111; color: #eee; } input, select, textarea { background: #1c1c1c; color: #eee; border-color: #444; } }
  main { max-width: 560px; margin: 0 auto; padding: 16px 14px 60px; }
  h1 { font-size: 18px; margin: 4px 0 14px; }
  .field { margin-bottom: 12px; }
  label { display: block; font-size: 13px; margin-bottom: 4px; opacity: 0.8; }
  input[type=\"url\"], input[type=\"text\"], input[type=\"datetime-local\"], input[type=\"password\"], select, textarea {
    width: 100%; font-size: 16px; padding: 12px; border: 1px solid #ccc; border-radius: 8px; background: #fff;
  }
  input[type=\"url\"].big { font-size: 18px; padding: 14px; }
  textarea { resize: vertical; min-height: 56px; }
  .mode-row { display: flex; gap: 10px; }
  .mode-row label { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 8px; text-align: center; font-size: 15px; }
  .mode-row input[type=\"radio\"] { margin-right: 6px; }
  .actions { display: flex; gap: 10px; margin-top: 18px; }
  button { flex: 1; font-size: 16px; padding: 14px; border-radius: 8px; border: none; cursor: pointer; }
  button.primary { background: #f57f17; color: #fff; font-weight: 600; }
  button.secondary { background: #455a64; color: #fff; }
  #result { margin-top: 18px; padding: 12px; border-radius: 8px; font-size: 14px; white-space: pre-wrap; word-break: break-all; }
  #result.ok { background: #e8f5e9; color: #1b5e20; }
  #result.err { background: #ffebee; color: #b71c1c; }
  @media (prefers-color-scheme: dark) {
    #result.ok { background: #1b3d1f; color: #c8e6c9; }
    #result.err { background: #3d1b1b; color: #ffcdd2; }
  }
  small.note { display: block; font-size: 12px; opacity: 0.7; margin-top: 4px; }
</style>
</head>
<body>
<main>
  <h1>YOSHILOVER 手動投入</h1>
  <form id=\"intake\">
    <div class=\"field\">
      <label for=\"url\">URL（必須・記事 or X status）</label>
      <input class=\"big\" id=\"url\" name=\"url\" type=\"url\" required placeholder=\"https://...\" autocomplete=\"off\" inputmode=\"url\">
    </div>
    <div class=\"field\">
      <label for=\"article_type\">記事タイプ</label>
      <select id=\"article_type\" name=\"article_type\">__ARTICLE_TYPE_OPTIONS__</select>
      <small class=\"note\">URL/OG情報から自動推定。1タップで上書き可。</small>
    </div>
    <div class=\"field\">
      <label for=\"title\">タイトル（任意・OG title上書き）</label>
      <input id=\"title\" name=\"title\" type=\"text\" autocomplete=\"off\">
    </div>
    <div class=\"field\">
      <label for=\"summary\">サマリー（任意・OG description上書き）</label>
      <textarea id=\"summary\" name=\"summary\" rows=\"2\"></textarea>
    </div>
    <div class=\"field\">
      <label for=\"source_published_at\">出典公開日時（任意・ISO8601 / JST扱い）</label>
      <input id=\"source_published_at\" name=\"source_published_at\" type=\"text\" placeholder=\"2026-05-07T18:30:00+09:00\" autocomplete=\"off\">
    </div>
    <div class=\"field\">
      <label for=\"memo\">メモ（任意・本文には流れません）</label>
      <textarea id=\"memo\" name=\"memo\" rows=\"2\"></textarea>
    </div>
    <div class=\"field\">
      <label>モード</label>
      <div class=\"mode-row\">
        <label><input type=\"radio\" name=\"mode\" value=\"dry-run\" checked>dry-run</label>
        <label><input type=\"radio\" name=\"mode\" value=\"draft\">draft</label>
      </div>
    </div>
    <div class=\"field\">
      <label for=\"token\">アクセストークン（必須）</label>
      <input id=\"token\" name=\"token\" type=\"password\" autocomplete=\"current-password\" required>
    </div>
    <div class=\"actions\">
      <button class=\"primary\" type=\"submit\">送信</button>
      <button class=\"secondary\" type=\"reset\">クリア</button>
    </div>
  </form>
  <div id=\"result\" hidden></div>
</main>
<script>
(function() {
  const form = document.getElementById('intake');
  const result = document.getElementById('result');
  function render(ok, payload) {
    result.hidden = false;
    result.className = ok ? 'ok' : 'err';
    if (!ok) {
      result.textContent = '失敗: ' + (payload.reason || payload.skip_reason || payload.error || JSON.stringify(payload));
      return;
    }
    const lines = [
      '結果: ok',
      'mode: ' + (payload.mode || ''),
      'title: ' + (payload.title || ''),
      'category: ' + (payload.category || '') + (payload.category_ids ? ' ' + JSON.stringify(payload.category_ids) : ''),
      'subtype: ' + (payload.subtype || ''),
      'article_type: ' + (payload.article_type || '') + ' (' + (payload.article_type_source || '') + ')',
      'source_url: ' + (payload.source_url || ''),
    ];
    if (payload.post_id) lines.push('post_id: ' + payload.post_id);
    if (payload.draft_url) lines.push('edit: ' + payload.draft_url);
    if (payload.normalized_source_published_at) lines.push('source_published_at: ' + payload.normalized_source_published_at);
    result.textContent = lines.join('\\n');
  }
  form.addEventListener('submit', async function(ev) {
    ev.preventDefault();
    result.hidden = true;
    const data = new FormData(form);
    const body = new URLSearchParams();
    data.forEach((v, k) => body.append(k, v));
    try {
      const resp = await fetch('/manual-intake', {
        method: 'POST',
        body: body,
        headers: { 'Accept': 'application/json' },
      });
      const json = await resp.json().catch(() => ({}));
      render(resp.ok && json.ok, json);
    } catch (e) {
      render(false, { error: String(e) });
    }
  });
})();
</script>
</body>
</html>
"""


_MANIFEST = {
    "name": "YOSHILOVER 手動投入",
    "short_name": "YL投入",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#fafafa",
    "theme_color": "#f57f17",
    "icons": [],
}


def _render_form() -> str:
    options: list[str] = []
    for value in mi.ARTICLE_TYPE_CHOICES:
        label = "自動判定 (auto)" if value == mi.ARTICLE_TYPE_AUTO else value
        options.append(
            f'<option value="{value}">{label}</option>'
        )
    return _HTML_FORM.replace("__ARTICLE_TYPE_OPTIONS__", "".join(options))


# ---------------------------------------------------------------------------
# Core handler
# ---------------------------------------------------------------------------


def _handle_manual_intake(
    payload: dict[str, str],
    *,
    wp_client_factory,
    logger: logging.Logger,
) -> tuple[int, dict[str, Any]]:
    """Return (http_status, response_dict). Pure-ish — no I/O of its own
    except whatever ``run_manual_intake`` does."""
    url = (payload.get("url") or "").strip()
    if not url:
        return 400, {"ok": False, "reason": "missing_url"}

    mode = (payload.get("mode") or "dry-run").strip().lower()
    if mode not in {"dry-run", "draft"}:
        return 400, {"ok": False, "reason": "invalid_mode"}

    article_type = (payload.get("article_type") or "").strip()
    source_published_at = (payload.get("source_published_at") or "").strip()
    memo = payload.get("memo") or ""
    title_override = (payload.get("title") or "").strip()
    summary_override = (payload.get("summary") or "").strip()

    exit_code, output = mi.run_manual_intake(
        url=url,
        memo=memo,
        mode=mode,
        title_override=title_override,
        summary_override=summary_override,
        source_published_at=source_published_at,
        article_type=article_type or mi.ARTICLE_TYPE_AUTO,
        wp_client_factory=wp_client_factory,
        logger=logger,
    )

    if exit_code == mi.EXIT_OK:
        return 200, output
    if exit_code in (
        mi.EXIT_INVALID_URL,
        mi.EXIT_VALIDATION_FAILED,
        mi.EXIT_INVALID_SOURCE_PUBLISHED_AT,
        mi.EXIT_INVALID_ARTICLE_TYPE,
        mi.EXIT_MISSING_TITLE_OR_SUMMARY,
    ):
        return 400, output
    if exit_code == mi.EXIT_DUPLICATE:
        return 409, output
    if exit_code == mi.EXIT_RATE_LIMITED:
        return 429, output
    if exit_code == mi.EXIT_FETCH_FAILED:
        return 502, output
    return 500, output


# ---------------------------------------------------------------------------
# HTTP routing
# ---------------------------------------------------------------------------


def build_handler(
    *,
    wp_client_factory=None,
    logger: logging.Logger | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Build a Handler class bound to the supplied dependencies. Tests can
    inject their own factory; production passes None to use the WPClient
    default lazily."""
    bound_logger = logger or LOGGER

    def _resolve_wp_factory():
        if wp_client_factory is not None:
            return wp_client_factory
        return mi._default_wp_client_factory

    class Handler(BaseHTTPRequestHandler):
        # Reduce default request log noise (Cloud Run captures stdout).
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            bound_logger.info("%s - %s", self.address_string(), format % args)

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path == "/health":
                _json_response(self, 200, {"ok": True})
                return
            if path == "/manifest.webmanifest":
                _text_response(
                    self,
                    200,
                    json.dumps(_MANIFEST, ensure_ascii=False),
                    content_type="application/manifest+json; charset=utf-8",
                )
                return
            if path in ("/", "/index.html"):
                _text_response(
                    self, 200, _render_form(), content_type="text/html; charset=utf-8"
                )
                return
            _json_response(self, 404, {"ok": False, "reason": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/manual-intake":
                _json_response(self, 404, {"ok": False, "reason": "not_found"})
                return

            expected_token = _require_token()
            if not expected_token:
                _json_response(
                    self,
                    503,
                    {"ok": False, "reason": "service_token_unconfigured"},
                )
                return

            body, body_err = _read_body(self)
            if body_err == "body_too_large":
                _json_response(self, 413, {"ok": False, "reason": "body_too_large"})
                return

            content_type = self.headers.get("Content-Type", "")
            payload, parse_err = _parse_request_body(body, content_type)
            if parse_err:
                _json_response(
                    self, 400, {"ok": False, "reason": parse_err}
                )
                return

            supplied = _request_token(self, payload.get("token") or "")
            if supplied != expected_token:
                _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                return

            # Drop the token from the payload before handing off so we never
            # log it via downstream audit.
            payload.pop("token", None)

            try:
                status, response = _handle_manual_intake(
                    payload,
                    wp_client_factory=_resolve_wp_factory(),
                    logger=bound_logger,
                )
            except Exception as exc:  # noqa: BLE001
                bound_logger.exception("manual_intake_unhandled_error")
                _json_response(
                    self,
                    500,
                    {"ok": False, "reason": f"unexpected:{exc.__class__.__name__}"},
                )
                return

            _json_response(self, status, response)

    return Handler


def serve(port: int | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    bind_port = int(port if port is not None else os.environ.get(PORT_ENV, DEFAULT_PORT))
    handler_cls = build_handler()
    server = HTTPServer(("0.0.0.0", bind_port), handler_cls)
    LOGGER.info("manual_intake_service listening on :%d", bind_port)
    if not _require_token():
        LOGGER.warning(
            "%s is not configured — POST /manual-intake will return 503",
            TOKEN_ENV,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("manual_intake_service shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
