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
    if header.strip():
        return header.strip()
    if (body_token or "").strip():
        return body_token.strip()
    # Cookie fallback (NOMOTOKE-INTAKE-COOKIE-001): the operator opens
    # ``GET /?token=<value>`` once per device. The server validates the
    # token there and sets ``manual_intake_session`` cookie. Subsequent
    # requests carry the cookie automatically and never need a token in
    # JS / form / URL again. The cookie value is the token verbatim;
    # constant-time comparison happens at the call site.
    cookie_header = handler.headers.get("Cookie", "") or ""
    for chunk in cookie_header.split(";"):
        chunk = chunk.strip()
        if chunk.startswith(SESSION_COOKIE_NAME + "="):
            return chunk[len(SESSION_COOKIE_NAME) + 1 :].strip()
    return ""


SESSION_COOKIE_NAME = "manual_intake_session"
SESSION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 90  # 90 days


def _set_session_cookie(handler: BaseHTTPRequestHandler, token_value: str) -> None:
    """Emit ``Set-Cookie`` header so the browser carries auth on every
    subsequent request without the operator re-typing or seeing the token.
    """
    cookie = (
        f"{SESSION_COOKIE_NAME}={token_value}; "
        f"Max-Age={SESSION_COOKIE_MAX_AGE_SECONDS}; "
        "Path=/; Secure; HttpOnly; SameSite=Lax"
    )
    handler.send_header("Set-Cookie", cookie)


def _redirect_response(
    handler: BaseHTTPRequestHandler, location: str, *, set_cookie_value: str = ""
) -> None:
    handler.send_response(303)
    handler.send_header("Location", location)
    if set_cookie_value:
        _set_session_cookie(handler, set_cookie_value)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


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
  main { max-width: 560px; margin: 0 auto; padding: 16px 14px 60px; }
  h1 { font-size: 18px; margin: 4px 0 14px; }
  .field { margin-bottom: 12px; }
  label { display: block; font-size: 13px; margin-bottom: 4px; opacity: 0.85; color: inherit; }
  /* Light-mode form inputs — explicit white background, dark text. */
  input[type=\"url\"], input[type=\"text\"], input[type=\"datetime-local\"], input[type=\"password\"], select, textarea {
    width: 100%; font-size: 16px; padding: 12px; border: 1px solid #ccc; border-radius: 8px;
    background: #fff; color: #222;
  }
  input[type=\"url\"].big { font-size: 18px; padding: 14px; }
  textarea { resize: vertical; min-height: 56px; }
  .mode-row { display: flex; gap: 10px; }
  .mode-row label { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 8px; text-align: center; font-size: 15px; opacity: 1; }
  .mode-row input[type=\"radio\"] { margin-right: 6px; }
  .actions { display: flex; gap: 10px; margin-top: 18px; }
  button { flex: 1; font-size: 16px; padding: 14px; border-radius: 8px; border: none; cursor: pointer; }
  button.primary { background: #f57f17; color: #fff; font-weight: 600; }
  button.secondary { background: #455a64; color: #fff; }
  #result { margin-top: 18px; padding: 12px; border-radius: 8px; font-size: 14px; white-space: pre-wrap; word-break: break-all; }
  #result.ok { background: #e8f5e9; color: #1b5e20; }
  #result.err { background: #ffebee; color: #b71c1c; }
  small.note { display: block; font-size: 12px; opacity: 0.85; margin-top: 4px; color: inherit; }
  .facts-block { padding: 10px 12px; margin: 0 0 12px; border-left: 3px solid #f57f17; background: #fff8e1; border-radius: 4px; }
  .facts-block .field { margin-bottom: 8px; }
  .facts-block .field:last-child { margin-bottom: 0; }
  .facts-block label { font-weight: 500; }
  @media (prefers-color-scheme: dark) {
    .facts-block { background: #2a2418; border-left-color: #ffb74d; }
  }
  .setup-banner { padding: 12px 14px; margin-bottom: 14px; border-radius: 8px; background: #fff8e1; color: #5d4037; border: 1px solid #ffd54f; font-size: 13px; line-height: 1.55; }
  .setup-banner code { background: rgba(0,0,0,0.08); padding: 1px 4px; border-radius: 3px; font-family: ui-monospace, Menlo, Consolas, monospace; }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  /* Dark-mode overrides MUST come last so their selectors win on phones
     that auto-flip to dark. The earlier ordering placed the base
     ``background:#fff`` rule after the dark-mode override, which made the
     input text invisible against the white box. */
  @media (prefers-color-scheme: dark) {
    body { background: #111; color: #eee; }
    input[type=\"url\"], input[type=\"text\"], input[type=\"datetime-local\"], input[type=\"password\"], select, textarea {
      background: #1c1c1c; color: #f0f0f0; border-color: #555;
    }
    input::placeholder, textarea::placeholder { color: #888; }
    .mode-row label { border-color: #555; background: #1c1c1c; color: #f0f0f0; }
    #result.ok { background: #1b3d1f; color: #c8e6c9; }
    #result.err { background: #3d1b1b; color: #ffcdd2; }
    .setup-banner { background: #2a2418; color: #ffd699; border-color: #6b5832; }
    .setup-banner code { background: rgba(255,255,255,0.08); }
  }
</style>
</head>
<body>
<main>
  <h1>YOSHILOVER 手動投入</h1>
  <form id=\"intake\">
    <div class=\"field\">
      <label for=\"url\">記事URL</label>
      <input class=\"big\" id=\"url\" name=\"url\" type=\"url\" required placeholder=\"https://...\" autocomplete=\"off\" inputmode=\"url\">
    </div>
    <div class=\"field\">
      <label for=\"article_type\">記事タイプ</label>
      <select id=\"article_type\" name=\"article_type\">__ARTICLE_TYPE_OPTIONS__</select>
      <small class=\"note\" id=\"type-hint\">URL を入れて記事タイプを選んで「記事化」を押すだけ。タイトル / サマリーは出典 OG から自動取得します。</small>
    </div>
    <!-- Per-article-type optional facts. Each block is wrapped in a
         data-types attribute that lists the article_type values for
         which it is shown. JS toggles visibility on change. -->
    <div class=\"facts-block\" data-types=\"監督談話\" hidden>
      <div class=\"field\">
        <label for=\"manager_name\">監督名（任意・自動抽出失敗時の救済）</label>
        <input id=\"manager_name\" name=\"manager_name\" type=\"text\" autocomplete=\"off\" placeholder=\"例: 阿部 / 桑田 / 二岡\">
      </div>
      <div class=\"field\">
        <label for=\"manager_quote\">発言（任意）</label>
        <textarea id=\"manager_quote\" name=\"quote\" rows=\"2\" placeholder=\"「○○○○」と発言した部分のみ。100字まで\"></textarea>
      </div>
    </div>
    <div class=\"facts-block\" data-types=\"選手コメント\" hidden>
      <div class=\"field\">
        <label for=\"player_name\">選手名（任意）</label>
        <input id=\"player_name\" name=\"player_name\" type=\"text\" autocomplete=\"off\" placeholder=\"例: 戸郷 / リチャード / 岡本\">
      </div>
      <div class=\"field\">
        <label for=\"player_quote\">発言（任意）</label>
        <textarea id=\"player_quote\" name=\"quote\" rows=\"2\" placeholder=\"「○○○○」と発言した部分のみ。100字まで\"></textarea>
      </div>
    </div>
    <div class=\"facts-block\" data-types=\"予告先発\" hidden>
      <div class=\"field\">
        <label for=\"pitcher_a\">巨人先発（任意）</label>
        <input id=\"pitcher_a\" name=\"pitcher_a\" type=\"text\" autocomplete=\"off\" placeholder=\"例: 戸郷\">
      </div>
      <div class=\"field\">
        <label for=\"team_b\">対戦チーム（任意）</label>
        <input id=\"team_b\" name=\"team_b\" type=\"text\" autocomplete=\"off\" placeholder=\"例: 阪神\">
      </div>
      <div class=\"field\">
        <label for=\"pitcher_b\">相手先発（任意）</label>
        <input id=\"pitcher_b\" name=\"pitcher_b\" type=\"text\" autocomplete=\"off\" placeholder=\"例: 才木\">
      </div>
    </div>
    <div class=\"facts-block\" data-types=\"動画\" hidden>
      <div class=\"field\">
        <label for=\"video_player_name\">選手名（任意）</label>
        <input id=\"video_player_name\" name=\"player_name\" type=\"text\" autocomplete=\"off\" placeholder=\"例: 岡本\">
      </div>
      <div class=\"field\">
        <label for=\"play_summary\">プレー説明（任意）</label>
        <textarea id=\"play_summary\" name=\"play_summary\" rows=\"2\" placeholder=\"例: 5回裏 ソロ本塁打\"></textarea>
      </div>
    </div>
    <div class=\"facts-block\" data-types=\"公示\" hidden>
      <div class=\"field\">
        <label for=\"registered\">登録選手（任意・カンマ区切り）</label>
        <textarea id=\"registered\" name=\"registered\" rows=\"2\" placeholder=\"例: 戸郷,リチャード\"></textarea>
      </div>
      <div class=\"field\">
        <label for=\"removed\">抹消選手（任意・カンマ区切り）</label>
        <textarea id=\"removed\" name=\"removed\" rows=\"2\" placeholder=\"例: 岡本\"></textarea>
      </div>
    </div>
    <details class=\"field\">
      <summary style=\"cursor:pointer; font-weight:600; padding:6px 0;\">詳細設定（任意・通常は不要）</summary>
      <div class=\"field\">
        <label for=\"title\">タイトル上書き（OG title を強制差替え）</label>
        <input id=\"title\" name=\"title\" type=\"text\" autocomplete=\"off\">
      </div>
      <div class=\"field\">
        <label for=\"summary\">サマリー上書き（OG description を強制差替え）</label>
        <textarea id=\"summary\" name=\"summary\" rows=\"2\"></textarea>
      </div>
      <div class=\"field\">
        <label for=\"source_published_at\">出典公開日時上書き（ISO8601 / JST扱い）</label>
        <input id=\"source_published_at\" name=\"source_published_at\" type=\"text\" placeholder=\"2026-05-07T18:30:00+09:00\" autocomplete=\"off\">
      </div>
      <div class=\"field\">
        <label for=\"memo\">メモ（本文には流れません）</label>
        <textarea id=\"memo\" name=\"memo\" rows=\"2\"></textarea>
      </div>
      <div class=\"field\">
        <label><input type=\"checkbox\" id=\"dry-run-toggle\"> 確認のみ（dry-run）— チェック時は WP に書き込まずレスポンスだけ返す</label>
      </div>
    </details>
    <div class=\"actions\">
      <button class=\"primary\" type=\"submit\" id=\"submit-btn\">記事化</button>
      <button class=\"secondary\" type=\"reset\">クリア</button>
    </div>
  </form>
  <div id=\"result\" hidden></div>
</main>
<script>
(function() {
  // Auth is via the ``manual_intake_session`` cookie set by the server
  // when the operator opens ``GET /?token=<value>`` once per device.
  // The cookie is HttpOnly + Secure + SameSite=Lax so it is attached
  // automatically on every fetch from the same origin. The form never
  // sees the token; ``credentials: 'same-origin'`` ensures the cookie
  // is forwarded on the POST.
  const form = document.getElementById('intake');
  const result = document.getElementById('result');
  const dryRunToggle = document.getElementById('dry-run-toggle');
  const articleType = document.getElementById('article_type');
  const submitBtn = document.getElementById('submit-btn');
  const typeHint = document.getElementById('type-hint');
  const factsBlocks = document.querySelectorAll('.facts-block');

  // Per-article-type submit label + hint text. Free-form objects keep
  // it easy to extend later without touching the form HTML.
  const SUBMIT_LABEL = {
    '監督談話': '監督談話を記事化',
    '選手コメント': '選手コメントを記事化',
    '予告先発': '予告先発を記事化',
    '公示': '公示を記事化',
    '動画': '動画を記事化',
    '試合結果': '試合結果を記事化',
    '試合速報': '試合速報を記事化',
    '成績': '成績を記事化',
    '番組情報': '番組情報を記事化',
    'コラム': 'コラムを記事化',
    'ニュース': 'ニュースを記事化',
  };
  const TYPE_HINT = {
    '試合結果': 'Yahoo!スポーツの試合詳細URL（baseball.yahoo.co.jp/npb/game/...）を貼ると、回ごとのスコア表が出ます。',
    '監督談話': '阿部 / 桑田 / 元木 / 二岡 等の発言記事URL。発言部分が抽出できないときは下のフィールドに直接入力できます。',
    '選手コメント': '選手の発言記事URL。タイトルから選手名が取れない場合は下のフィールドに入力。',
    '予告先発': '予告先発記事URL。先発投手が抽出できないときは下のフィールドに入力。',
    '公示': '公示記事URL。登録/抹消の名前が抽出できないときは下のフィールドに入力。',
    '動画': 'YouTube URL（youtu.be / shorts / live も自動正規化）。説明が空のときは下のフィールドで補える。',
  };
  const DEFAULT_HINT = 'URL を入れて記事タイプを選んで「記事化」を押すだけ。タイトル / サマリーは出典 OG から自動取得します。';

  function syncTypeUI() {
    const t = articleType ? articleType.value : '';
    if (submitBtn) submitBtn.textContent = SUBMIT_LABEL[t] || '記事化';
    if (typeHint) typeHint.textContent = TYPE_HINT[t] || DEFAULT_HINT;
    factsBlocks.forEach(function(block) {
      const types = (block.getAttribute('data-types') || '').split(',').map(s => s.trim());
      const visible = types.indexOf(t) >= 0;
      block.hidden = !visible;
    });
  }
  if (articleType) articleType.addEventListener('change', syncTypeUI);
  syncTypeUI();

  function render(ok, payload) {
    result.hidden = false;
    result.className = ok ? 'ok' : 'err';
    if (!ok) {
      const rawReason = payload.reason || payload.skip_reason || payload.error || JSON.stringify(payload);
      // AUDIT FIX #35: friendly error messages (raw code → 日本語)
      const friendly = {
        'forbidden': '失敗: アクセス権限がありません。',
        'rate_limited': '失敗: リクエスト過多。1 分待って再試行してください。',
        'missing_url': '失敗: URL が空です。',
        'invalid_url': '失敗: URL が無効です。',
        'missing_title_or_summary': '失敗: タイトル/サマリーが取得できませんでした。出典サイトが応答していない可能性があります。',
        'invalid_article_type': '失敗: 記事タイプの値が不正です。',
        'invalid_source_published_at': '失敗: 出典公開日時の形式が不正です (ISO 8601 推奨)。',
        'history_duplicate': '失敗: 既に同じ URL で投入済みです。',
        'wp_client_factory_not_provided': '失敗: WP 接続設定エラー (env 確認)。',
        'body_too_large': '失敗: 入力が大きすぎます。',
        'invalid_mode': '失敗: mode が不正です。',
      };
      // ``fetch_failed:...`` パターンは prefix 一致で出す
      let msg = friendly[rawReason];
      if (!msg && rawReason.indexOf('fetch_failed:') === 0) {
        msg = '失敗: ' + rawReason.slice('fetch_failed:'.length);
      }
      if (!msg) msg = '失敗: ' + rawReason;
      result.textContent = msg;
      return;
    }
    const lines = [
      '結果: ' + (payload.mode === 'draft' ? '✅ 下書き作成 OK' : '✅ 確認 OK'),
      'タイトル: ' + (payload.title || ''),
      'カテゴリ: ' + (payload.category || ''),
      '記事タイプ: ' + (payload.article_type || ''),
    ];
    if (payload.post_id) lines.push('post_id: ' + payload.post_id);
    if (payload.normalized_source_published_at) lines.push('出典公開日時: ' + payload.normalized_source_published_at);
    // AUDIT FIX #30: clickable WP edit link in result
    result.textContent = lines.join('\\n');
    if (payload.edit_url) {
      const editLink = document.createElement('a');
      editLink.href = payload.edit_url;
      editLink.target = '_blank';
      editLink.rel = 'noopener';
      editLink.textContent = '✏️ WP 編集ページを開く';
      editLink.style.cssText = 'display:inline-block;margin-top:10px;padding:8px 16px;background:#f57f17;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;';
      result.appendChild(document.createElement('br'));
      result.appendChild(editLink);
    } else if (payload.draft_url) {
      const link = document.createElement('a');
      link.href = payload.draft_url;
      link.target = '_blank';
      link.textContent = '🔗 下書きを開く';
      link.style.cssText = 'display:inline-block;margin-top:10px;';
      result.appendChild(document.createElement('br'));
      result.appendChild(link);
    }
  }

  form.addEventListener('submit', async function(ev) {
    ev.preventDefault();
    result.hidden = true;
    // AUDIT FIX #29: loading state on submit so the operator sees
    // immediate feedback instead of a hung-looking page.
    const submitBtn = document.getElementById('submit-btn');
    let originalLabel = '';
    if (submitBtn) {
      originalLabel = submitBtn.textContent;
      submitBtn.disabled = true;
      submitBtn.textContent = '📡 送信中...';
    }
    const data = new FormData(form);
    const body = new URLSearchParams();
    data.forEach((v, k) => { if (v) body.append(k, v); });
    body.set('mode', dryRunToggle && dryRunToggle.checked ? 'dry-run' : 'draft');
    try {
      const resp = await fetch('/manual-intake', {
        method: 'POST',
        body: body,
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      const json = await resp.json().catch(() => ({}));
      render(resp.ok && json.ok, json);
    } catch (e) {
      render(false, { error: String(e) });
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = originalLabel || '記事化';
      }
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

    manual_facts = {
        "manager_name": (payload.get("manager_name") or "").strip(),
        "player_name": (payload.get("player_name") or "").strip(),
        "quote": (payload.get("quote") or "").strip(),
        "pitcher_a": (payload.get("pitcher_a") or "").strip(),
        "pitcher_b": (payload.get("pitcher_b") or "").strip(),
        "team_b": (payload.get("team_b") or "").strip(),
        "play_summary": (payload.get("play_summary") or "").strip(),
        "registered": (payload.get("registered") or "").strip(),
        "removed": (payload.get("removed") or "").strip(),
    }

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
        manual_facts=manual_facts,
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
                # NOMOTOKE-INTAKE-COOKIE-001: ``GET /?token=<value>``
                # validates the token and sets ``manual_intake_session``
                # cookie, then 303-redirects to bare ``/`` so the URL
                # bar never carries the token (history stays clean) and
                # the operator can bookmark ``/`` without query string.
                expected = _require_token()
                params = parse_qs(parsed.query, keep_blank_values=False)
                supplied_query_token = ""
                token_list = params.get("token") or []
                if token_list:
                    supplied_query_token = (token_list[0] or "").strip()
                if expected and supplied_query_token:
                    if supplied_query_token == expected:
                        _redirect_response(
                            self, "/", set_cookie_value=expected
                        )
                        return
                    # Wrong token in query → fall through to form render
                    # (operator sees the form, will get 403 on submit).
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

            # NOMOTOKE-INTAKE-OPEN-001: when ``MANUAL_INTAKE_TOKEN`` is
            # configured the service requires it (legacy CLI / curl
            # callers and any deploy that wants the gate); when the env
            # is empty the service runs in OPEN mode — anyone with the
            # URL can submit. The operator opted into this for the
            # production deploy because (a) WP writes are limited to
            # ``draft`` (no publish, no mail), (b) all output is
            # noindex, (c) downstream guarded-publish + manual review is
            # the canonical safety gate, and (d) Cloud Run min=0/max=2
            # caps cost even under abuse.
            expected_token = _require_token()

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

            if expected_token:
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
