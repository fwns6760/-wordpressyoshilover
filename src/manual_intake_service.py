"""MANUAL-INTAKE-GCP-001 — small Cloud Run-friendly HTTP service that
exposes ``manual_intake.run_manual_intake`` to a mobile-first GUI.

Routes:
    GET  /            — mobile-first single-screen HTML form
    GET  /health      — liveness probe (no auth)
    GET  /manifest.webmanifest — minimal PWA manifest (no auth)
    POST /manual-intake — JSON or form-encoded submission (token required)
    GET  /x-post-draft  — 346: NL question → X post draft (no LLM)
    POST /x-post-direct — 346: post arbitrary text to X via x_api_client

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
from src import manual_intake_insight_query as miq  # noqa: E402

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
  /* INSIGHT-006: tab navigation */
  .tab-nav { display: flex; gap: 6px; margin-bottom: 14px; }
  .tab-btn { flex: 1; padding: 10px 6px; border: 1px solid #ccc; border-radius: 8px; background: #fff; color: #555; font-size: 14px; cursor: pointer; }
  .tab-btn.active { background: #f57f17; color: #fff; border-color: #f57f17; font-weight: 600; }
  .tab-panel[hidden] { display: none; }
  table.result-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }
  table.result-table th, table.result-table td { padding: 6px 4px; text-align: left; border-bottom: 1px solid #eee; vertical-align: top; }
  table.result-table th { background: #f5f5f5; font-weight: 600; color: #333; }
  table.result-table tr:hover { background: #fafafa; }
  .insight-row-grid { display: grid; gap: 8px; grid-template-columns: 1fr 1fr; }
  .insight-row-grid .field { margin: 0; }
  .insight-meta { font-size: 12px; opacity: 0.7; margin-top: 4px; }
  @media (prefers-color-scheme: dark) {
    .tab-btn { background: #1c1c1c; color: #aaa; border-color: #555; }
    .tab-btn.active { background: #f57f17; color: #fff; border-color: #f57f17; }
    table.result-table th { background: #2a2a2a; color: #ddd; }
    table.result-table th, table.result-table td { border-bottom-color: #333; }
    table.result-table tr:hover { background: #1a1a1a; }
  }
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
  <nav class=\"tab-nav\">
    <button type=\"button\" class=\"tab-btn active\" data-tab=\"intake\" id=\"tab-btn-intake\">📝 手動投入</button>
    <button type=\"button\" class=\"tab-btn\" data-tab=\"insight\" id=\"tab-btn-insight\">🐦 X 投稿 (データ)</button>
  </nav>
  <section class=\"tab-panel\" data-tab=\"intake\" id=\"tab-panel-intake\">
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
  </section>
  <section class=\"tab-panel\" data-tab=\"insight\" id=\"tab-panel-insight\" hidden>
    <h2 style=\"font-size:16px;margin:6px 0 8px;\">🐦 X 投稿用 post 案 (LLM 不使用)</h2>
    <p class=\"insight-meta\">質問を 1 行で入力 → insight.db (verified data) から rank query → 280 字以内の X 投稿文を生成。<strong>LLM 呼出ゼロ</strong>、Python テンプレで整形。例:<br>
      ・「OPS 10 位」<br>
      ・「セ・リーグ OPS 上位 5」<br>
      ・「岡本和真の wOBA は何位？」<br>
      ・「先発 FIP ランキング top 10」</p>
    <form id=\"x-post-draft-form\">
      <div class=\"field\">
        <input id=\"x-post-q\" name=\"q\" type=\"text\" required placeholder=\"例: OPS 10 位\" autocomplete=\"off\" class=\"big\">
      </div>
      <div class=\"actions\">
        <button class=\"primary\" type=\"submit\" id=\"x-post-draft-btn\">📝 post 案を作る</button>
      </div>
    </form>
    <div id=\"x-post-draft-result\" hidden></div>
    <hr style=\"margin:24px 0 18px;border:none;border-top:1px solid #ddd;\">
    <h2 style=\"font-size:16px;margin:6px 0 8px;\">🗣️ 質問入力 (一番簡単)</h2>
    <p class=\"insight-meta\">質問を 1 行で入力 → 自動で「指標」「守備位置」「件数」「選手」を読み取り、12 球団 rank + 記事 draft まで生成。例:<br>
      ・「セリーグのセカンドUZRトップ10は？」<br>
      ・「先発のFIPランキングトップ5」<br>
      ・「巨人の戸郷翔征のFIPは何位？」<br>
      ・「ショートOPSトップ10」</p>
    <form id=\"ask-form\">
      <div class=\"field\">
        <input id=\"ask-q\" name=\"q\" type=\"text\" required placeholder=\"例: セリーグのセカンドUZRトップ10は？\" autocomplete=\"off\" class=\"big\">
      </div>
      <div class=\"actions\">
        <button class=\"primary\" type=\"submit\" id=\"ask-submit-btn\">🗣️ 質問して記事生成</button>
      </div>
    </form>
    <div id=\"ask-result\" hidden></div>

    <details style=\"margin-top:24px;border-top:1px solid #ddd;padding-top:14px;\">
      <summary style=\"cursor:pointer;font-weight:600;\">⚙️ 詳細検索 (上級者向け、手動で条件指定)</summary>
    <p class=\"insight-meta\">蓄積された article_candidates を選手 / 種類 / 期間で検索。検出ロジックは z-score / streak / workload / lineup_jump。data が日々 GCS に蓄積され、2-3 週間後に anomaly が出始める。</p>
    <h2 style=\"font-size:15px;margin:18px 0 8px;\">🔎 1. signal 検索</h2>
    <form id=\"insight-form\">
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"q-player\">選手</label>
          <select id=\"q-player\" name=\"player\">__INSIGHT_PLAYER_OPTIONS__</select>
        </div>
        <div class=\"field\">
          <label for=\"q-signal\">検出軸</label>
          <select id=\"q-signal\" name=\"signal_type\">__INSIGHT_SIGNAL_OPTIONS__</select>
        </div>
      </div>
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"q-since\">From (YYYY-MM-DD)</label>
          <input id=\"q-since\" name=\"since\" type=\"text\" placeholder=\"2026-05-01\" autocomplete=\"off\">
        </div>
        <div class=\"field\">
          <label for=\"q-until\">To (YYYY-MM-DD)</label>
          <input id=\"q-until\" name=\"until\" type=\"text\" placeholder=\"2026-05-31\" autocomplete=\"off\">
        </div>
      </div>
      <div class=\"actions\">
        <button class=\"primary\" type=\"submit\" id=\"insight-submit-btn\">🔍 検索</button>
        <button class=\"secondary\" type=\"reset\">クリア</button>
      </div>
    </form>
    <div id=\"insight-result\" hidden></div>

    <h2 style=\"font-size:15px;margin:24px 0 8px;\">📊 2. 12 球団 rank (INSIGHT-007)</h2>
    <p class=\"insight-meta\">advanced metrics (OPS / FIP / wOBA / RF_proxy etc.) で全球団内 rank を出す。UZR は厳密版でない近似 (RF_proxy / UZR_proxy)。data 蓄積 (2〜3 週) 後に意味を持つ。</p>
    <form id=\"rank-form\">
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"r-metric\">指標</label>
          <select id=\"r-metric\" name=\"metric\">__INSIGHT_METRIC_OPTIONS__</select>
        </div>
        <div class=\"field\">
          <label for=\"r-position\">守備位置 (RF/UZR proxy 必須)</label>
          <select id=\"r-position\" name=\"position\">__INSIGHT_POSITION_OPTIONS__</select>
        </div>
      </div>
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"r-player\">注目選手 (rank highlight)</label>
          <select id=\"r-player\" name=\"player\">__INSIGHT_PLAYER_OPTIONS__</select>
        </div>
        <div class=\"field\">
          <label for=\"r-min-sample\">最低サンプル (AB/IP/opps)</label>
          <input id=\"r-min-sample\" name=\"min_sample\" type=\"number\" min=\"1\" value=\"1\">
        </div>
      </div>
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"r-since\">From (YYYY-MM-DD)</label>
          <input id=\"r-since\" name=\"since\" type=\"text\" placeholder=\"2026-04-01\" autocomplete=\"off\">
        </div>
        <div class=\"field\">
          <label for=\"r-until\">To (YYYY-MM-DD)</label>
          <input id=\"r-until\" name=\"until\" type=\"text\" placeholder=\"2026-05-31\" autocomplete=\"off\">
        </div>
      </div>
      <div class=\"actions\">
        <button class=\"primary\" type=\"submit\" id=\"rank-submit-btn\">📊 rank 検索</button>
      </div>
    </form>
    <div id=\"rank-result\" hidden></div>

    <h2 style=\"font-size:15px;margin:24px 0 8px;\">📝 3. rank → 記事 draft 生成 (INSIGHT-008)</h2>
    <p class=\"insight-meta\">上の rank 条件で markdown 記事 draft を生成。テンプレ + 解釈 + 注意書きが入った形で、コピーして WordPress に貼り付け or 既存「手動投入」タブから投入できる。Gemini は使わない、無料完結。</p>
    <form id=\"article-form\">
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"a-metric\">指標</label>
          <select id=\"a-metric\" name=\"metric\">__INSIGHT_METRIC_OPTIONS__</select>
        </div>
        <div class=\"field\">
          <label for=\"a-position\">守備位置</label>
          <select id=\"a-position\" name=\"position\">__INSIGHT_POSITION_OPTIONS__</select>
        </div>
      </div>
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"a-player\">注目選手</label>
          <select id=\"a-player\" name=\"player\">__INSIGHT_PLAYER_OPTIONS__</select>
        </div>
        <div class=\"field\">
          <label for=\"a-top-n\">表示件数 (top_n)</label>
          <input id=\"a-top-n\" name=\"top_n\" type=\"number\" min=\"3\" max=\"30\" value=\"10\">
        </div>
      </div>
      <div class=\"insight-row-grid\">
        <div class=\"field\">
          <label for=\"a-since\">From (YYYY-MM-DD)</label>
          <input id=\"a-since\" name=\"since\" type=\"text\" placeholder=\"2026-04-01\" autocomplete=\"off\">
        </div>
        <div class=\"field\">
          <label for=\"a-until\">To (YYYY-MM-DD)</label>
          <input id=\"a-until\" name=\"until\" type=\"text\" placeholder=\"2026-05-31\" autocomplete=\"off\">
        </div>
      </div>
      <div class=\"actions\">
        <button class=\"primary\" type=\"submit\" id=\"article-submit-btn\">📝 記事 draft 生成</button>
      </div>
    </form>
    <div id=\"article-result\" hidden></div>
    </details>
  </section>
</main>
<script>
(function() {
  // INSIGHT-006: tab switching
  var tabBtns = document.querySelectorAll('.tab-btn');
  var tabPanels = document.querySelectorAll('.tab-panel');
  tabBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      var tab = btn.getAttribute('data-tab');
      tabBtns.forEach(function(b) { b.classList.toggle('active', b.getAttribute('data-tab') === tab); });
      tabPanels.forEach(function(p) { p.hidden = (p.getAttribute('data-tab') !== tab); });
    });
  });

  // INSIGHT-006: insight query form
  var iform = document.getElementById('insight-form');
  var iresult = document.getElementById('insight-result');
  var isubmit = document.getElementById('insight-submit-btn');
  function renderInsight(payload) {
    iresult.hidden = false;
    if (!payload || !payload.ok) {
      iresult.className = 'err';
      iresult.textContent = '失敗: ' + (payload && payload.reason ? payload.reason : 'unknown');
      return;
    }
    var rows = payload.rows || [];
    if (rows.length === 0) {
      iresult.className = '';
      iresult.textContent = '該当データなし（蓄積中、または条件に合う signal が無い）。';
      return;
    }
    iresult.className = '';
    iresult.innerHTML = '';
    var meta = document.createElement('div');
    meta.className = 'insight-meta';
    meta.textContent = payload.count + ' 件 ヒット';
    iresult.appendChild(meta);
    var table = document.createElement('table');
    table.className = 'result-table';
    var thead = document.createElement('thead');
    thead.innerHTML = '<tr><th>P</th><th>signal</th><th>選手</th><th>試合日</th><th>current</th><th>baseline</th><th>notes</th></tr>';
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    rows.forEach(function(r) {
      var tr = document.createElement('tr');
      function td(text) { var c = document.createElement('td'); c.textContent = text == null ? '' : String(text); return c; }
      tr.appendChild(td('P' + (r.priority || '-')));
      tr.appendChild(td(r.signal_type || ''));
      tr.appendChild(td(r.player_canonical || r.player_display || ''));
      tr.appendChild(td(r.game_date || ''));
      tr.appendChild(td(r.current_value || ''));
      tr.appendChild(td(r.baseline_value || ''));
      tr.appendChild(td(r.notes || ''));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    iresult.appendChild(table);
  }
  iform.addEventListener('submit', async function(ev) {
    ev.preventDefault();
    iresult.hidden = true;
    if (isubmit) { isubmit.disabled = true; isubmit.textContent = '📡 検索中...'; }
    var data = new FormData(iform);
    var params = new URLSearchParams();
    data.forEach(function(v, k) { if (v) params.append(k, v); });
    try {
      var resp = await fetch('/insight-query?' + params.toString(), {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      var json = await resp.json().catch(function() { return {}; });
      renderInsight(json);
    } catch (e) {
      renderInsight({ ok: false, reason: String(e) });
    } finally {
      if (isubmit) { isubmit.disabled = false; isubmit.textContent = '🔍 検索'; }
    }
  });

  // INSIGHT-007: rank query form
  var rform = document.getElementById('rank-form');
  var rresult = document.getElementById('rank-result');
  var rsubmit = document.getElementById('rank-submit-btn');
  function renderRank(payload) {
    rresult.hidden = false;
    if (!payload || !payload.ok) {
      rresult.className = 'err';
      rresult.textContent = '失敗: ' + (payload && payload.reason ? payload.reason : 'unknown');
      return;
    }
    var rows = payload.rows || [];
    if (rows.length === 0) {
      rresult.className = '';
      rresult.textContent = '該当データなし（蓄積中、または条件に合う選手がいない）。';
      return;
    }
    rresult.className = '';
    rresult.innerHTML = '';
    var meta = document.createElement('div');
    meta.className = 'insight-meta';
    var focus = payload.focus_player;
    if (focus) {
      meta.textContent = '注目選手「' + focus.player_canonical + '」 → ' + focus.rank + '位 / 全' + focus.total + '人 (値=' + focus.metric_value + ', サンプル=' + focus.sample_size + ')';
    } else {
      meta.textContent = payload.count + ' 件表示 / 全' + payload.total + ' 人';
    }
    rresult.appendChild(meta);
    var table = document.createElement('table');
    table.className = 'result-table';
    table.innerHTML = '<thead><tr><th>順位</th><th>選手</th><th>team</th><th>値</th><th>サンプル</th></tr></thead>';
    var tbody = document.createElement('tbody');
    var focusName = focus ? focus.player_canonical : null;
    rows.forEach(function(r) {
      var tr = document.createElement('tr');
      if (focusName && r.player_canonical === focusName) {
        tr.style.background = '#fff3e0';
        tr.style.fontWeight = '600';
      }
      function td(t) { var c = document.createElement('td'); c.textContent = t == null ? '' : String(t); return c; }
      tr.appendChild(td(r.rank + '/' + r.total));
      tr.appendChild(td(r.player_canonical || ''));
      tr.appendChild(td(r.team_code || ''));
      tr.appendChild(td(r.metric_value));
      tr.appendChild(td(r.sample_size));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    rresult.appendChild(table);
  }
  rform.addEventListener('submit', async function(ev) {
    ev.preventDefault();
    rresult.hidden = true;
    if (rsubmit) { rsubmit.disabled = true; rsubmit.textContent = '📡 検索中...'; }
    var data = new FormData(rform);
    var params = new URLSearchParams();
    data.forEach(function(v, k) { if (v) params.append(k, v); });
    try {
      var resp = await fetch('/insight-rank?' + params.toString(), {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      var json = await resp.json().catch(function() { return {}; });
      renderRank(json);
    } catch (e) {
      renderRank({ ok: false, reason: String(e) });
    } finally {
      if (rsubmit) { rsubmit.disabled = false; rsubmit.textContent = '📊 rank 検索'; }
    }
  });

  // INSIGHT-008: article generator form
  var aform = document.getElementById('article-form');
  var aresult = document.getElementById('article-result');
  var asubmit = document.getElementById('article-submit-btn');
  function renderArticle(payload) {
    aresult.hidden = false;
    if (!payload || !payload.ok) {
      aresult.className = 'err';
      aresult.textContent = '失敗: ' + (payload && payload.reason ? payload.reason : 'unknown');
      return;
    }
    var art = payload.article || {};
    aresult.className = '';
    aresult.innerHTML = '';
    var meta = document.createElement('div');
    meta.className = 'insight-meta';
    meta.textContent = '生成完了。下のテキストをコピーして WP に貼り付け、または手動投入タブで投入してください。';
    aresult.appendChild(meta);
    var titleDiv = document.createElement('div');
    titleDiv.style.cssText = 'font-weight:600;margin:8px 0 4px;font-size:15px;';
    titleDiv.textContent = '提案タイトル: ' + (art.title || '');
    aresult.appendChild(titleDiv);
    var ta = document.createElement('textarea');
    ta.style.cssText = 'width:100%;min-height:300px;font-family:ui-monospace,monospace;font-size:12px;padding:10px;';
    ta.value = art.body_md || '';
    aresult.appendChild(ta);
    var tagDiv = document.createElement('div');
    tagDiv.className = 'insight-meta';
    tagDiv.style.cssText = 'margin-top:6px;';
    tagDiv.textContent = 'タグ候補: ' + ((art.suggested_tags || []).join(', '));
    aresult.appendChild(tagDiv);
    var copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'secondary';
    copyBtn.textContent = '📋 markdown コピー';
    copyBtn.style.cssText = 'margin-top:8px;padding:8px 16px;';
    copyBtn.addEventListener('click', function() {
      ta.select();
      try { navigator.clipboard.writeText(ta.value); copyBtn.textContent = '✅ コピー済'; }
      catch (e) { document.execCommand('copy'); copyBtn.textContent = '✅ コピー済'; }
      setTimeout(function() { copyBtn.textContent = '📋 markdown コピー'; }, 2000);
    });
    aresult.appendChild(copyBtn);
  }
  aform.addEventListener('submit', async function(ev) {
    ev.preventDefault();
    aresult.hidden = true;
    if (asubmit) { asubmit.disabled = true; asubmit.textContent = '📡 生成中...'; }
    var data = new FormData(aform);
    var params = new URLSearchParams();
    data.forEach(function(v, k) { if (v) params.append(k, v); });
    try {
      var resp = await fetch('/insight-article?' + params.toString(), {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      var json = await resp.json().catch(function() { return {}; });
      renderArticle(json);
    } catch (e) {
      renderArticle({ ok: false, reason: String(e) });
    } finally {
      if (asubmit) { asubmit.disabled = false; asubmit.textContent = '📝 記事 draft 生成'; }
    }
  });

  // INSIGHT-009: ask form (natural language input → article)
  var qform = document.getElementById('ask-form');
  var qresult = document.getElementById('ask-result');
  var qsubmit = document.getElementById('ask-submit-btn');
  // Convert every Markdown pipe-table block in `md` to an HTML
  // <table>. Returns a container element wrapping the rendered tables
  // and any surrounding paragraph text. Returns null when no tables
  // were found (caller falls back to the textarea alone).
  function renderMarkdownTables(md) {
    if (!md) return null;
    var lines = md.split('\n');
    var container = document.createElement('div');
    container.className = 'insight-rendered';
    container.style.cssText = 'margin-top:8px;';
    var i = 0;
    var foundTable = false;
    var paraBuf = [];
    function flushPara() {
      if (!paraBuf.length) return;
      var txt = paraBuf.join('\n').trim();
      paraBuf = [];
      if (!txt) return;
      // Skip a leading h1 (rendered separately as title).
      if (txt.charAt(0) === '#') {
        var stripped = txt.replace(/^#+\s*/, '');
        if (stripped) {
          var h = document.createElement('div');
          h.style.cssText = 'font-weight:600;font-size:14px;margin:10px 0 4px;color:#333;';
          h.textContent = stripped;
          container.appendChild(h);
        }
        return;
      }
      var p = document.createElement('p');
      p.style.cssText = 'margin:6px 0;font-size:13px;line-height:1.7;color:#222;';
      p.textContent = txt;
      container.appendChild(p);
    }
    while (i < lines.length) {
      var line = lines[i];
      // Detect table header: a line starting with `|` followed by a
      // separator line of `|---|---|...|`.
      var isHeader = /^\s*\|.+\|\s*$/.test(line);
      var nextLine = lines[i + 1] || '';
      var isSep = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/.test(nextLine);
      if (isHeader && isSep) {
        flushPara();
        foundTable = true;
        var headers = line.split('|').map(function(s) { return s.trim(); })
                          .filter(function(s) { return s.length > 0; });
        i += 2;
        var rows = [];
        while (i < lines.length && /^\s*\|.+\|\s*$/.test(lines[i])) {
          var cells = lines[i].split('|').map(function(s) { return s.trim(); })
                              .filter(function(s, idx, arr) {
                                // Drop the leading/trailing empty cells the
                                // pipe split produces.
                                return !(s === '' && (idx === 0 || idx === arr.length - 1));
                              });
          rows.push(cells);
          i++;
        }
        var tbl = document.createElement('table');
        tbl.style.cssText = 'width:100%;border-collapse:collapse;margin:8px 0;font-size:13px;background:#fff;';
        var thead = document.createElement('thead');
        var tr = document.createElement('tr');
        headers.forEach(function(h) {
          var th = document.createElement('th');
          th.textContent = h;
          th.style.cssText = 'padding:6px 8px;background:#003da5;color:#fff;text-align:left;font-weight:600;border-bottom:2px solid #002a73;position:sticky;top:0;';
          tr.appendChild(th);
        });
        thead.appendChild(tr);
        tbl.appendChild(thead);
        var tbody = document.createElement('tbody');
        rows.forEach(function(row, rowIdx) {
          var rtr = document.createElement('tr');
          var hasStar = row.some(function(c) { return c.indexOf('★') !== -1; });
          rtr.style.cssText = (hasStar
            ? 'background:#fff3cd;font-weight:600;'
            : (rowIdx % 2 === 0 ? 'background:#fafafa;' : 'background:#fff;'));
          row.forEach(function(cell) {
            var td = document.createElement('td');
            td.textContent = cell;
            td.style.cssText = 'padding:6px 8px;border-bottom:1px solid #eee;';
            rtr.appendChild(td);
          });
          tbody.appendChild(rtr);
        });
        tbl.appendChild(tbody);
        // Wrap in a scroll container so wide tables don't break
        // mobile layout.
        var wrap = document.createElement('div');
        wrap.style.cssText = 'overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #ddd;border-radius:4px;';
        wrap.appendChild(tbl);
        container.appendChild(wrap);
        continue;
      }
      paraBuf.push(line);
      i++;
    }
    flushPara();
    return foundTable ? container : null;
  }
  function renderAsk(payload) {
    qresult.hidden = false;
    qresult.innerHTML = '';
    if (!payload || !payload.ok) {
      qresult.className = 'err';
      var msg = '失敗: ' + (payload && payload.reason ? payload.reason : 'unknown');
      if (payload && payload.unresolved && payload.unresolved.length) {
        msg += ' (不足: ' + payload.unresolved.join(', ') + ')';
      }
      if (payload && payload.parsed) {
        msg += '\\n\\n読み取れた条件: ' + JSON.stringify(payload.parsed);
      }
      qresult.textContent = msg;
      return;
    }
    qresult.className = '';
    var parsed = payload.parsed || {};
    var pmeta = document.createElement('div');
    pmeta.className = 'insight-meta';
    pmeta.textContent = '読み取り: 指標=' + (parsed.metric || '?')
      + ' / 守備=' + (parsed.position || '指定なし')
      + ' / 件数=' + (parsed.top_n || 10)
      + (parsed.focus_player ? ' / 選手=' + parsed.focus_player : '')
      + (parsed.league ? ' / リーグ=' + parsed.league : '');
    qresult.appendChild(pmeta);
    var art = payload.article || {};
    var titleDiv = document.createElement('div');
    titleDiv.style.cssText = 'font-weight:600;margin:8px 0 4px;font-size:15px;';
    titleDiv.textContent = '提案タイトル: ' + (art.title || '');
    qresult.appendChild(titleDiv);
    // Render every Markdown pipe-table found in body_md as an actual
    // HTML <table> so the operator sees a real grid instead of raw
    // markdown lines. Keeps the textarea below for copy/paste.
    var rendered = renderMarkdownTables(art.body_md || '');
    if (rendered) qresult.appendChild(rendered);
    var detailsBox = document.createElement('details');
    detailsBox.style.cssText = 'margin-top:10px;';
    var summary = document.createElement('summary');
    summary.style.cssText = 'cursor:pointer;font-size:13px;color:#555;';
    summary.textContent = '📄 Markdown 全文 (コピー用)';
    detailsBox.appendChild(summary);
    var ta = document.createElement('textarea');
    ta.style.cssText = 'width:100%;min-height:220px;margin-top:8px;font-family:ui-monospace,monospace;font-size:12px;padding:10px;';
    ta.value = art.body_md || '';
    detailsBox.appendChild(ta);
    qresult.appendChild(detailsBox);
    var tagDiv = document.createElement('div');
    tagDiv.className = 'insight-meta';
    tagDiv.style.cssText = 'margin-top:6px;';
    tagDiv.textContent = 'タグ候補: ' + ((art.suggested_tags || []).join(', '));
    qresult.appendChild(tagDiv);
    var copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'secondary';
    copyBtn.textContent = '📋 markdown コピー';
    copyBtn.style.cssText = 'margin-top:8px;padding:8px 16px;';
    copyBtn.addEventListener('click', function() {
      ta.select();
      try { navigator.clipboard.writeText(ta.value); copyBtn.textContent = '✅ コピー済'; }
      catch (e) { document.execCommand('copy'); copyBtn.textContent = '✅ コピー済'; }
      setTimeout(function() { copyBtn.textContent = '📋 markdown コピー'; }, 2000);
    });
    qresult.appendChild(copyBtn);
  }
  qform.addEventListener('submit', async function(ev) {
    ev.preventDefault();
    qresult.hidden = true;
    if (qsubmit) { qsubmit.disabled = true; qsubmit.textContent = '📡 処理中...'; }
    var q = document.getElementById('ask-q').value || '';
    try {
      var resp = await fetch('/insight-ask?' + new URLSearchParams({q: q}).toString(), {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      var json = await resp.json().catch(function() { return {}; });
      renderAsk(json);
    } catch (e) {
      renderAsk({ ok: false, reason: String(e) });
    } finally {
      if (qsubmit) { qsubmit.disabled = false; qsubmit.textContent = '🗣️ 質問して記事生成'; }
    }
  });

  // 346: X post draft generation tab.
  var xpForm = document.getElementById('x-post-draft-form');
  var xpResult = document.getElementById('x-post-draft-result');
  var xpBtn = document.getElementById('x-post-draft-btn');
  function renderXPost(payload) {
    xpResult.hidden = false;
    xpResult.innerHTML = '';
    if (!payload || !payload.ok) {
      xpResult.className = 'err';
      var msg = '失敗: ' + (payload && payload.reason ? payload.reason : 'unknown');
      if (payload && payload.unresolved && payload.unresolved.length) {
        msg += ' (不足: ' + payload.unresolved.join(', ') + ')';
      }
      if (payload && payload.parsed) {
        msg += '\n\n読み取れた条件: ' + JSON.stringify(payload.parsed);
      }
      xpResult.textContent = msg;
      return;
    }
    xpResult.className = '';
    var parsed = payload.parsed || {};
    var meta = document.createElement('div');
    meta.className = 'insight-meta';
    meta.textContent = '読み取り: 指標=' + (parsed.metric || '?')
      + ' / 守備=' + (parsed.position || '指定なし')
      + ' / 件数=' + (parsed.top_n || 10)
      + (parsed.focus_player ? ' / 選手=' + parsed.focus_player : '')
      + (parsed.league ? ' / リーグ=' + parsed.league : '')
      + ' / rank行=' + (payload.row_count || 0);
    xpResult.appendChild(meta);
    var ta = document.createElement('textarea');
    ta.id = 'x-post-text';
    ta.rows = 12;
    ta.style.cssText = 'width:100%;min-height:200px;margin-top:8px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:14px;padding:10px;white-space:pre-wrap;';
    ta.value = payload.draft_text || '';
    xpResult.appendChild(ta);
    var counter = document.createElement('div');
    counter.className = 'insight-meta';
    counter.style.cssText = 'margin-top:4px;';
    function updateCount() {
      var n = (ta.value || '').length;
      counter.textContent = n + ' / 280 字' + (n > 280 ? ' ⚠️ 超過' : '');
      counter.style.color = (n > 280) ? '#b71c1c' : '';
    }
    updateCount();
    ta.addEventListener('input', updateCount);
    xpResult.appendChild(counter);
    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:10px;margin-top:10px;flex-wrap:wrap;';
    var postBtn = document.createElement('button');
    postBtn.type = 'button';
    postBtn.className = 'primary';
    postBtn.textContent = '🐦 X 投稿';
    postBtn.style.cssText = 'flex:1;padding:12px;font-size:15px;';
    var copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'secondary';
    copyBtn.textContent = '📋 コピー';
    copyBtn.style.cssText = 'flex:0 0 auto;padding:12px 16px;font-size:15px;';
    copyBtn.addEventListener('click', function() {
      ta.select();
      try { navigator.clipboard.writeText(ta.value); copyBtn.textContent = '✅ コピー済'; }
      catch (e) { document.execCommand('copy'); copyBtn.textContent = '✅ コピー済'; }
      setTimeout(function() { copyBtn.textContent = '📋 コピー'; }, 2000);
    });
    postBtn.addEventListener('click', async function() {
      var text = ta.value || '';
      if (!text.trim()) { return; }
      if (text.length > 280) {
        alert('280 字を超過しています。短くしてから投稿してください。');
        return;
      }
      postBtn.disabled = true;
      postBtn.textContent = '🚀 投稿中...';
      try {
        var resp = await fetch('/x-post-direct', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ text: text }),
        });
        var json = await resp.json().catch(function() { return {}; });
        if (json && json.ok) {
          postBtn.textContent = '✅ 投稿成功 (id=' + (json.tweet_id || '?') + ')';
          postBtn.disabled = true;
        } else {
          postBtn.textContent = '❌ 失敗: ' + (json.reason || ('status ' + resp.status));
          postBtn.disabled = false;
        }
      } catch (e) {
        postBtn.textContent = '❌ エラー: ' + String(e);
        postBtn.disabled = false;
      }
    });
    actions.appendChild(postBtn);
    actions.appendChild(copyBtn);
    xpResult.appendChild(actions);
  }
  if (xpForm) {
    xpForm.addEventListener('submit', async function(ev) {
      ev.preventDefault();
      xpResult.hidden = true;
      if (xpBtn) { xpBtn.disabled = true; xpBtn.textContent = '📡 生成中...'; }
      var q = document.getElementById('x-post-q').value || '';
      try {
        var resp = await fetch('/x-post-draft?' + new URLSearchParams({q: q}).toString(), {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          credentials: 'same-origin',
        });
        var json = await resp.json().catch(function() { return {}; });
        renderXPost(json);
      } catch (e) {
        renderXPost({ ok: false, reason: String(e) });
      } finally {
        if (xpBtn) { xpBtn.disabled = false; xpBtn.textContent = '📝 post 案を作る'; }
      }
    });
  }
})();
</script>
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
    # INSIGHT-006: roster + signal options for the data-query tab.
    player_options = ['<option value="">— 全選手 —</option>']
    for row in miq.roster_options():
        name = row["name"]
        label = name + (f" ({row['position']})" if row.get("position") else "")
        player_options.append(f'<option value="{name}">{label}</option>')
    signal_options = ['<option value="">— 全 signal —</option>']
    for sig in miq.signal_type_options():
        signal_options.append(f'<option value="{sig}">{sig}</option>')
    # INSIGHT-007: rank-tab option lists
    metric_options = ['<option value="">— metric を選択 —</option>']
    for met in miq.metric_options():
        metric_options.append(f'<option value="{met}">{met}</option>')
    position_options = ['<option value="">— 全 position (打撃/投球指標は不問) —</option>']
    for pos in miq.position_options():
        position_options.append(f'<option value="{pos}">{pos}</option>')
    return (
        _HTML_FORM
        .replace("__ARTICLE_TYPE_OPTIONS__", "".join(options))
        .replace("__INSIGHT_PLAYER_OPTIONS__", "".join(player_options))
        .replace("__INSIGHT_SIGNAL_OPTIONS__", "".join(signal_options))
        .replace("__INSIGHT_METRIC_OPTIONS__", "".join(metric_options))
        .replace("__INSIGHT_POSITION_OPTIONS__", "".join(position_options))
    )


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
            if path == "/insight-ask":
                # INSIGHT-009: NL question → parser → article generator.
                expected_token = _require_token()
                if expected_token:
                    cookie_token = ""
                    raw_cookie = self.headers.get("Cookie") or ""
                    for part in raw_cookie.split(";"):
                        kv = part.strip().split("=", 1)
                        if len(kv) == 2 and kv[0].strip() == "manual_intake_session":
                            cookie_token = kv[1].strip()
                            break
                    query_token = ""
                    qtok = parse_qs(parsed.query, keep_blank_values=False).get("token") or []
                    if qtok:
                        query_token = (qtok[0] or "").strip()
                    if cookie_token != expected_token and query_token != expected_token:
                        _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                        return
                params = parse_qs(parsed.query, keep_blank_values=False)
                miq.ensure_local_db()
                question = (params.get("q") or [""])[0]
                if not question.strip():
                    _json_response(self, 400, {"ok": False, "reason": "empty_question"})
                    return
                try:
                    result = miq.ask(question=question)
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("insight_ask_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"ask_error:{exc!r}"})
                    return
                _json_response(self, 200, result)
                return
            if path == "/insight-article":
                # INSIGHT-008: generate article draft markdown from rank query.
                expected_token = _require_token()
                if expected_token:
                    cookie_token = ""
                    raw_cookie = self.headers.get("Cookie") or ""
                    for part in raw_cookie.split(";"):
                        kv = part.strip().split("=", 1)
                        if len(kv) == 2 and kv[0].strip() == "manual_intake_session":
                            cookie_token = kv[1].strip()
                            break
                    query_token = ""
                    qtok = parse_qs(parsed.query, keep_blank_values=False).get("token") or []
                    if qtok:
                        query_token = (qtok[0] or "").strip()
                    if cookie_token != expected_token and query_token != expected_token:
                        _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                        return
                params = parse_qs(parsed.query, keep_blank_values=False)
                miq.ensure_local_db()
                try:
                    result = miq.generate_article(
                        metric_name=(params.get("metric") or [""])[0],
                        player_canonical=(params.get("player") or [""])[0] or None,
                        position_filter=(params.get("position") or [""])[0] or None,
                        since=(params.get("since") or [""])[0] or None,
                        until=(params.get("until") or [""])[0] or None,
                        min_sample=int((params.get("min_sample") or ["1"])[0]),
                        top_n=int((params.get("top_n") or ["10"])[0]),
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("insight_article_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"article_error:{exc!r}"})
                    return
                _json_response(self, 200, result)
                return
            if path == "/insight-rank":
                # INSIGHT-007: cross-team rank query.
                expected_token = _require_token()
                if expected_token:
                    cookie_token = ""
                    raw_cookie = self.headers.get("Cookie") or ""
                    for part in raw_cookie.split(";"):
                        kv = part.strip().split("=", 1)
                        if len(kv) == 2 and kv[0].strip() == "manual_intake_session":
                            cookie_token = kv[1].strip()
                            break
                    query_token = ""
                    qtok = parse_qs(parsed.query, keep_blank_values=False).get("token") or []
                    if qtok:
                        query_token = (qtok[0] or "").strip()
                    if cookie_token != expected_token and query_token != expected_token:
                        _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                        return
                params = parse_qs(parsed.query, keep_blank_values=False)
                miq.ensure_local_db()
                try:
                    result = miq.query_rank(
                        metric_name=(params.get("metric") or [""])[0],
                        player_canonical=(params.get("player") or [""])[0] or None,
                        position_filter=(params.get("position") or [""])[0] or None,
                        since=(params.get("since") or [""])[0] or None,
                        until=(params.get("until") or [""])[0] or None,
                        min_sample=int((params.get("min_sample") or ["1"])[0]),
                        limit=int((params.get("limit") or ["200"])[0]),
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("insight_rank_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"rank_error:{exc!r}", "rows": []})
                    return
                _json_response(self, 200, result)
                return
            if path == "/insight-query":
                # INSIGHT-006: read-only data-query endpoint. Auth flow
                # mirrors POST /manual-intake: when MANUAL_INTAKE_TOKEN is
                # set, require either the query token or the session
                # cookie. When unset, OPEN mode (same as the form POST).
                expected_token = _require_token()
                if expected_token:
                    cookie_token = ""
                    raw_cookie = self.headers.get("Cookie") or ""
                    for part in raw_cookie.split(";"):
                        kv = part.strip().split("=", 1)
                        if len(kv) == 2 and kv[0].strip() == "manual_intake_session":
                            cookie_token = kv[1].strip()
                            break
                    query_token = ""
                    qtok = parse_qs(parsed.query, keep_blank_values=False).get("token") or []
                    if qtok:
                        query_token = (qtok[0] or "").strip()
                    if cookie_token != expected_token and query_token != expected_token:
                        _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                        return
                params = parse_qs(parsed.query, keep_blank_values=False)
                miq.ensure_local_db()
                try:
                    result = miq.query_candidates(
                        player=(params.get("player") or [""])[0],
                        signal_type=(params.get("signal_type") or [""])[0],
                        since_game_date=(params.get("since") or [""])[0],
                        until_game_date=(params.get("until") or [""])[0],
                        limit=int((params.get("limit") or ["100"])[0]),
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("insight_query_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"query_error:{exc!r}", "rows": []})
                    return
                _json_response(self, 200, result)
                return
            if path == "/x-post-draft":
                # 346: natural-language question → parse → rank query
                # → format_as_x_post → ready-to-post X draft. Mirrors the
                # auth flow of /insight-ask: when MANUAL_INTAKE_TOKEN is
                # set, require cookie or query token. No X API call here;
                # the operator reviews the draft and submits via
                # POST /x-post-direct.
                expected_token = _require_token()
                if expected_token:
                    cookie_token = ""
                    raw_cookie = self.headers.get("Cookie") or ""
                    for part in raw_cookie.split(";"):
                        kv = part.strip().split("=", 1)
                        if len(kv) == 2 and kv[0].strip() == "manual_intake_session":
                            cookie_token = kv[1].strip()
                            break
                    query_token = ""
                    qtok = parse_qs(parsed.query, keep_blank_values=False).get("token") or []
                    if qtok:
                        query_token = (qtok[0] or "").strip()
                    if cookie_token != expected_token and query_token != expected_token:
                        _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                        return
                params = parse_qs(parsed.query, keep_blank_values=False)
                question = (params.get("q") or [""])[0]
                if not question.strip():
                    _json_response(self, 400, {"ok": False, "reason": "empty_question"})
                    return
                miq.ensure_local_db()
                try:
                    from src.analysis import insight_nl_query as _nlq
                    from src.format_as_x_post import format_as_x_post as _fmt

                    parsed_q = _nlq.parse_question(question)
                    if parsed_q.get("unresolved"):
                        _json_response(
                            self,
                            200,
                            {
                                "ok": False,
                                "reason": "unresolved_fields",
                                "parsed": parsed_q,
                                "unresolved": parsed_q.get("unresolved"),
                            },
                        )
                        return
                    if not parsed_q.get("metric"):
                        _json_response(
                            self,
                            200,
                            {
                                "ok": False,
                                "reason": "metric_not_detected",
                                "parsed": parsed_q,
                            },
                        )
                        return
                    rank_result = miq.query_rank(
                        metric_name=parsed_q["metric"],
                        player_canonical=parsed_q.get("focus_player"),
                        position_filter=parsed_q.get("position"),
                        min_sample=1,
                        limit=max(parsed_q.get("top_n") or 10, 30),
                    )
                    formatted = _fmt(parsed_q, rank_result)
                    formatted["parsed"] = parsed_q
                    formatted["row_count"] = rank_result.get("count", 0)
                    _json_response(self, 200, formatted)
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("x_post_draft_failed")
                    _json_response(
                        self,
                        500,
                        {"ok": False, "reason": f"x_post_draft_error:{exc!r}"},
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
            if parsed.path == "/x-post-direct":
                # 346: post arbitrary text to X. Reuses the same
                # MANUAL_INTAKE_TOKEN auth so cookie / header / body
                # token all work. Body: {"text": str}. Never calls
                # Gemini; only x_api_client.create_tweet().
                expected_token = _require_token()
                body, body_err = _read_body(self)
                if body_err == "body_too_large":
                    _json_response(self, 413, {"ok": False, "reason": "body_too_large"})
                    return
                content_type = self.headers.get("Content-Type", "")
                payload, parse_err = _parse_request_body(body, content_type)
                if parse_err:
                    _json_response(self, 400, {"ok": False, "reason": parse_err})
                    return
                if expected_token:
                    supplied = _request_token(self, payload.get("token") or "")
                    if supplied != expected_token:
                        _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                        return
                text = (payload.get("text") or "").strip()
                if not text:
                    _json_response(self, 400, {"ok": False, "reason": "empty_text"})
                    return
                if len(text) > 280:
                    _json_response(
                        self,
                        400,
                        {"ok": False, "reason": "text_too_long", "char_count": len(text)},
                    )
                    return
                try:
                    from src import x_api_client as _xc

                    client = _xc.get_client()
                    resp = client.create_tweet(text=text)
                except KeyError as exc:
                    bound_logger.exception("x_post_direct_env_missing")
                    _json_response(
                        self,
                        503,
                        {"ok": False, "reason": f"env_missing:{exc!s}"},
                    )
                    return
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("x_post_direct_failed")
                    _json_response(
                        self,
                        502,
                        {"ok": False, "reason": f"x_api_error:{exc!r}"},
                    )
                    return
                tweet_id = None
                try:
                    data = getattr(resp, "data", None) or {}
                    if isinstance(data, dict):
                        tweet_id = data.get("id")
                except Exception:  # noqa: BLE001
                    tweet_id = None
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "tweet_id": tweet_id,
                        "char_count": len(text),
                    },
                )
                return
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
