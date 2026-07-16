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

from datetime import datetime, timezone
import html
import json
import logging
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
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
RSS_SOURCES_FILE = ROOT / "config" / "rss_sources.json"
SOURCE_CANDIDATE_SOURCE_LIMIT = 32
SOURCE_CANDIDATE_ENTRY_LIMIT = 5
SOURCE_CANDIDATE_TOTAL_LIMIT = 20
SOURCE_CANDIDATE_TIMEOUT_SECONDS = 8
SOURCE_CANDIDATE_TYPES = {"news", "tag_scrape"}
SOURCE_CANDIDATE_GIANTS_KEYWORDS = ("巨人", "読売ジャイアンツ", "ジャイアンツ")


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
# Source candidate helpers
# ---------------------------------------------------------------------------


def _roles_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _source_candidate_has_giants_topic(title: str, summary: str) -> bool:
    haystack = f"{title} {summary}"
    return any(keyword in haystack for keyword in SOURCE_CANDIDATE_GIANTS_KEYWORDS)


def _source_candidate_is_giants_specific(source: dict[str, Any]) -> bool:
    text = f"{source.get('name') or ''} {source.get('url') or ''}"
    return _source_candidate_has_giants_topic(text, "")


def _load_manual_source_sources(
    path: Path = RSS_SOURCES_FILE,
) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for source in raw:
        if not isinstance(source, dict):
            continue
        source_type = str(source.get("type") or "").strip()
        if source_type not in SOURCE_CANDIDATE_TYPES:
            continue
        roles = _roles_list(source.get("role"))
        if roles and "article_source" not in roles:
            continue
        if source_type == "tag_scrape" and not str(source.get("scraper") or "").strip():
            continue
        url = str(source.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        name = str(source.get("name") or "").strip()
        if not name:
            continue
        out.append(source)
    return out


def _published_struct_to_iso(published: Any) -> str:
    if not isinstance(published, time.struct_time):
        return ""
    try:
        return datetime(*published[:6], tzinfo=timezone.utc).astimezone(mi.JST).isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _manual_source_entry_payload(
    source: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, str] | None:
    title = str(entry.get("title") or "").strip()
    url = str(entry.get("link") or entry.get("url") or entry.get("id") or "").strip()
    summary = str(
        entry.get("summary") or entry.get("description") or entry.get("subtitle") or ""
    ).strip()
    if not title or not url.startswith(("http://", "https://")):
        return None
    if not _source_candidate_is_giants_specific(source) and not _source_candidate_has_giants_topic(title, summary):
        return None
    source_name = str(source.get("name") or "").strip()
    article_type = mi._auto_guess_article_type(url=url, title=title, summary=summary)
    return {
        "source_name": source_name,
        "source_type": str(source.get("type") or "").strip(),
        "title": title,
        "url": url,
        "summary": summary,
        "published_at": _published_struct_to_iso(entry.get("published_parsed")),
        "article_type": article_type if article_type in mi.ARTICLE_TYPE_CHOICES else mi.ARTICLE_TYPE_AUTO,
    }


def _fetch_rss_source_entries(
    source: dict[str, Any],
    *,
    timeout_seconds: int = SOURCE_CANDIDATE_TIMEOUT_SECONDS,
    entry_limit: int = SOURCE_CANDIDATE_ENTRY_LIMIT,
) -> list[dict[str, Any]]:
    try:
        import feedparser
    except Exception:  # noqa: BLE001
        return []
    req = urlrequest.Request(
        str(source.get("url") or ""),
        headers={"User-Agent": "YOSHILOVERManualIntake/1.0"},
    )
    with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310
        parsed = feedparser.parse(resp.read())
    entries = list(getattr(parsed, "entries", []) or [])
    return [dict(entry) for entry in entries[: max(1, entry_limit)]]


def _fetch_manual_source_entries(
    source: dict[str, Any],
    *,
    timeout_seconds: int = SOURCE_CANDIDATE_TIMEOUT_SECONDS,
    entry_limit: int = SOURCE_CANDIDATE_ENTRY_LIMIT,
    logger: logging.Logger | None = None,
) -> list[dict[str, Any]]:
    source_type = str(source.get("type") or "").strip()
    try:
        if source_type == "tag_scrape":
            from src import tag_page_scraper

            article_limit = int(source.get("article_limit") or entry_limit)
            article_limit = max(1, min(article_limit, entry_limit))
            return tag_page_scraper.fetch_tag_page_entries(
                scraper=str(source.get("scraper") or ""),
                url=str(source.get("url") or ""),
                max_age_days=int(source.get("max_age_days") or 7),
                article_limit=article_limit,
                logger=logger,
            )
        return _fetch_rss_source_entries(
            source,
            timeout_seconds=timeout_seconds,
            entry_limit=entry_limit,
        )
    except Exception as exc:  # noqa: BLE001
        if logger is not None:
            logger.warning(
                "manual_source_candidate_fetch_failed source=%s reason=%r",
                source.get("name"),
                exc,
            )
        return []


def _source_candidates_payload(
    *,
    source_name: str = "",
    limit: int = SOURCE_CANDIDATE_TOTAL_LIMIT,
    source_limit: int = SOURCE_CANDIDATE_SOURCE_LIMIT,
    entry_limit: int = SOURCE_CANDIDATE_ENTRY_LIMIT,
    logger: logging.Logger | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    loaded_sources = list(sources) if sources is not None else _load_manual_source_sources()
    selected = (source_name or "").strip()
    if selected:
        fetch_sources = [
            source for source in loaded_sources
            if str(source.get("name") or "").strip() == selected
        ]
    else:
        fetch_sources = loaded_sources[: max(1, source_limit)]

    items: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for source in fetch_sources:
        for entry in _fetch_manual_source_entries(
            source,
            entry_limit=entry_limit,
            logger=logger,
        ):
            payload = _manual_source_entry_payload(source, entry)
            if not payload:
                continue
            url = payload["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(payload)
            if len(items) >= max(1, limit):
                break
        if len(items) >= max(1, limit):
            break

    return {
        "ok": True,
        "source": selected,
        "source_count": len(loaded_sources),
        "fetched_source_count": len(fetch_sources),
        "count": len(items),
        "items": items,
    }


def _get_cookie_session_token(handler: BaseHTTPRequestHandler) -> str:
    raw_cookie = handler.headers.get("Cookie") or ""
    for part in raw_cookie.split(";"):
        kv = part.strip().split("=", 1)
        if len(kv) == 2 and kv[0].strip() == SESSION_COOKIE_NAME:
            return kv[1].strip()
    return ""


def _is_authorized_get(handler: BaseHTTPRequestHandler, parsed) -> bool:
    expected_token = _require_token()
    if not expected_token:
        return True
    header_token = (handler.headers.get(TOKEN_HEADER, "") or "").strip()
    params = parse_qs(parsed.query, keep_blank_values=False)
    query_token = ""
    qtok = params.get("token") or []
    if qtok:
        query_token = (qtok[0] or "").strip()
    return (
        header_token == expected_token
        or _get_cookie_session_token(handler) == expected_token
        or query_token == expected_token
    )


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
  .tab-nav { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
  .tab-btn { flex: 1 1 30%; padding: 10px 6px; border: 1px solid #ccc; border-radius: 8px; background: #fff; color: #555; font-size: 14px; cursor: pointer; text-align: center; box-sizing: border-box; }
  .tab-btn.active { background: #f57f17; color: #fff; border-color: #f57f17; font-weight: 600; }
  .tab-panel[hidden] { display: none; }
  table.result-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }
  table.result-table th, table.result-table td { padding: 6px 4px; text-align: left; border-bottom: 1px solid #eee; vertical-align: top; }
  table.result-table th { background: #f5f5f5; font-weight: 600; color: #333; }
  table.result-table tr:hover { background: #fafafa; }
  .insight-row-grid { display: grid; gap: 8px; grid-template-columns: 1fr 1fr; }
  .insight-row-grid .field { margin: 0; }
  .insight-meta { font-size: 12px; opacity: 0.7; margin-top: 4px; }
  .source-item { padding: 10px 0; border-bottom: 1px solid #eee; }
  .source-item-title { font-weight: 600; font-size: 14px; line-height: 1.5; }
  .source-item-meta { font-size: 12px; opacity: 0.72; margin-top: 3px; }
  .source-item-url { display: block; font-size: 12px; margin-top: 4px; word-break: break-all; color: #003da5; }
  .source-use-btn { width: auto; flex: 0 0 auto; margin-top: 8px; padding: 8px 12px; font-size: 13px; }
  @media (prefers-color-scheme: dark) {
    .tab-btn { background: #1c1c1c; color: #aaa; border-color: #555; }
    .tab-btn.active { background: #f57f17; color: #fff; border-color: #f57f17; }
    table.result-table th { background: #2a2a2a; color: #ddd; }
    table.result-table th, table.result-table td { border-bottom-color: #333; }
    table.result-table tr:hover { background: #1a1a1a; }
    .source-item { border-bottom-color: #333; }
    .source-item-url { color: #90caf9; }
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
    <button type=\"button\" class=\"tab-btn\" data-tab=\"sources\" id=\"tab-btn-sources\">📰 ソース候補</button>
    <button type=\"button\" class=\"tab-btn\" data-tab=\"insight\" id=\"tab-btn-insight\">🐦 X 投稿 (データ)</button>
    <button type=\"button\" class=\"tab-btn\" data-tab=\"xshare\" id=\"tab-btn-xshare\">🔗 記事共有</button>
    <a class=\"tab-btn\" href=\"/live\" style=\"text-decoration:none;display:inline-block\">⚾ 観戦</a>
    <a class=\"tab-btn\" href=\"/friends\" style=\"text-decoration:none;display:inline-block\">👥 常連</a>
    <a class=\"tab-btn\" href=\"/trend\" style=\"text-decoration:none;display:inline-block\">🔥 トレンド</a>
    <a class=\"tab-btn\" href=\"/scout\" style=\"text-decoration:none;display:inline-block\">🎯 開拓</a>
    <a class=\"tab-btn\" href=\"/profile\" style=\"text-decoration:none;display:inline-block\">📌 固定</a>
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
        <label for=\"table_markdown\">表データ (Markdown table、 任意)</label>
        <textarea id=\"table_markdown\" name=\"table_markdown\" rows=\"6\" placeholder=\"| 日付 | 対戦 | 球場 | 席種 | 価格 |\n|---|---|---|---|---|\n| 5/22 18:00 | 巨人 vs DeNA | 東京ドーム | 内野指定 | ¥5,800 |\"></textarea>
      </div>
      <div class=\"field\">
        <label for=\"memo\">メモ（本文には流れません）</label>
        <textarea id=\"memo\" name=\"memo\" rows=\"2\"></textarea>
      </div>
      <div class=\"field\">
        <label><input type=\"checkbox\" id=\"save-as-draft-toggle\"> 下書きで保存（公開しない）— 既定は即時公開。チェック時は status=draft で作成し guarded-publish の昇格を待つ</label>
      </div>
      <div class=\"field\">
        <label><input type=\"checkbox\" id=\"dry-run-toggle\"> 確認のみ（dry-run）— チェック時は WP に書き込まずレスポンスだけ返す</label>
      </div>
    </details>
    <div class=\"actions\">
      <button class=\"primary\" type=\"submit\" id=\"submit-btn\">記事化 → 公開</button>
      <button class=\"secondary\" type=\"reset\">クリア</button>
    </div>
  </form>
  <div id=\"result\" hidden></div>
  </section>
  <section class=\"tab-panel\" data-tab=\"sources\" id=\"tab-panel-sources\" hidden>
    <h2 style=\"font-size:16px;margin:6px 0 8px;\">📰 巨人ソース候補</h2>
    <p class=\"insight-meta\">rss_sources.json の article source から最新候補を取得します。候補の「このURLを投入」で手動投入フォームへ反映します。</p>
    <form id=\"source-form\">
      <div class=\"field\">
        <label for=\"source-name\">ソース</label>
        <select id=\"source-name\" name=\"source\">__SOURCE_OPTIONS__</select>
      </div>
      <div class=\"actions\">
        <button class=\"primary\" type=\"submit\" id=\"source-submit-btn\">候補を取得</button>
      </div>
    </form>
    <div id=\"source-result\" hidden></div>
  </section>
  <section class=\"tab-panel\" data-tab=\"insight\" id=\"tab-panel-insight\" hidden>
    <h2 style=\"font-size:16px;margin:6px 0 8px;\">🐦 X 投稿用 post 案 (LLM 不使用)</h2>
    <p class=\"insight-meta\">質問を 1 行で入力 → insight.db (verified data) から rank query → 280 字以内の X 投稿文を生成。<strong>LLM 呼出ゼロ</strong>、Python テンプレで整形。例:<br>
      ・「OPS 10 位」<br>
      ・「セ・リーグ OPS 上位 5」<br>
      ・「岡本和真の打率は何位？」<br>
      ・「先発 防御率 ランキング top 10」</p>
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
      ・「セリーグのセカンドOPSトップ10は？」<br>
      ・「先発の防御率ランキングトップ5」<br>
      ・「巨人の戸郷翔征の防御率は何位？」<br>
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
    <p class=\"insight-meta\">許可済みのデータ指標で全球団内 rank を出す。data 蓄積 (2〜3 週) 後に意味を持つ。</p>
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
  <section class=\"tab-panel\" data-tab=\"xshare\" id=\"tab-panel-xshare\" hidden>
    <h2 style=\"font-size:16px;margin:6px 0 8px;\">🔗 記事をXで共有 (おりポス+リプ)</h2>
    <p class=\"insight-meta\" style=\"margin:0 0 10px;\">おりポス=最強の発言1個で引き込む本文+画像 (URLなし・末尾にリプ誘導行)、リプ=残りのチラ見せ+URL。ボタン1回で連続投稿。</p>
    <button type=\"button\" id=\"xshare-thread-btn\" class=\"primary\" style=\"width:100%;padding:12px;font-size:15px;margin-bottom:8px;\">🧵 今日の試合スレ案を作る (結果→データ→記事)</button>
    <button type=\"button\" id=\"xshare-refresh\" class=\"secondary\" style=\"width:100%;padding:12px;font-size:15px;\">🔄 最近の公開記事を読み込む</button>
    <div style=\"display:flex;gap:8px;margin-top:8px;\">
      <input id=\"xshare-manual-input\" type=\"text\" inputmode=\"url\" placeholder=\"記事URL または post_id を直接入力\" style=\"flex:1;padding:10px;font-size:14px;\">
      <button type=\"button\" id=\"xshare-manual-btn\" class=\"secondary\" style=\"flex:0 0 auto;padding:10px 14px;\">案を作る</button>
    </div>
    <div id=\"xshare-posts\" style=\"margin-top:10px;\"></div>
    <div id=\"xshare-editor\" hidden style=\"margin-top:14px;\"></div>
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
    var lines = md.split('\\n');
    var container = document.createElement('div');
    container.className = 'insight-rendered';
    container.style.cssText = 'margin-top:8px;';
    var i = 0;
    var foundTable = false;
    var paraBuf = [];
    function flushPara() {
      if (!paraBuf.length) return;
      var txt = paraBuf.join('\\n').trim();
      paraBuf = [];
      if (!txt) return;
      // Skip a leading h1 (rendered separately as title).
      if (txt.charAt(0) === '#') {
        var stripped = txt.replace(/^#+\\s*/, '');
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
      var isHeader = /^\\s*\\|.+\\|\\s*$/.test(line);
      var nextLine = lines[i + 1] || '';
      var isSep = /^\\s*\\|?\\s*:?-+:?\\s*(\\|\\s*:?-+:?\\s*)+\\|?\\s*$/.test(nextLine);
      if (isHeader && isSep) {
        flushPara();
        foundTable = true;
        var headers = line.split('|').map(function(s) { return s.trim(); })
                          .filter(function(s) { return s.length > 0; });
        i += 2;
        var rows = [];
        while (i < lines.length && /^\\s*\\|.+\\|\\s*$/.test(lines[i])) {
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

  // 2026-07-06: 記事共有タブ (おりポス+リプ連続投稿)。
  var xsRefresh = document.getElementById('xshare-refresh');
  var xsPosts = document.getElementById('xshare-posts');
  var xsEditor = document.getElementById('xshare-editor');
  function xsCounter(ta, label, limit) {
    // 2026-07-07 user「プレミアプランだからでかくして。俺も追加するし」:
    // おりポスは Premium 長文 (900 weighted)、リプは従来 280。
    limit = limit || 280;
    var div = document.createElement('div');
    div.className = 'insight-meta';
    div.style.cssText = 'margin:4px 0 10px;';
    function upd() {
      var t = ta.value || '';
      var w = 0;
      var rest = t.replace(new RegExp('https?://' + String.fromCharCode(92) + 'S+', 'g'), function() { w += 23; return ''; });
      for (var i = 0; i < rest.length; i++) { w += (rest.charCodeAt(i) >= 0x1100) ? 2 : 1; }
      div.textContent = label + ': ' + w + ' / ' + limit + ' weighted' + (w > limit ? ' ⚠️ 超過' : '');
      div.style.color = (w > limit) ? '#b71c1c' : '';
    }
    upd();
    ta.addEventListener('input', upd);
    return div;
  }
  function xsRenderEditor(draft) {
    xsEditor.hidden = false;
    xsEditor.innerHTML = '';
    var meta = document.createElement('div');
    meta.className = 'insight-meta';
    meta.textContent = '型=' + (draft.share_type || '?') + (draft.used_llm ? ' / LLM下書き' : ' / 簡易下書き(LLMなし)') + ' / ' + (draft.title || '');
    xsEditor.appendChild(meta);
    if (draft.post_status && draft.post_status !== 'publish') {
      var warn = document.createElement('div');
      warn.className = 'err';
      warn.style.cssText = 'padding:10px;border-radius:8px;margin-top:8px;font-size:13px;';
      warn.textContent = '⚠️ この記事はまだ公開前 (status=' + draft.post_status + ') です。先に公開しないと、リプのURLが404になります。';
      xsEditor.appendChild(warn);
    }
    if (draft.image_url) {
      var img = document.createElement('img');
      img.src = draft.image_url;
      img.style.cssText = 'max-width:100%;border-radius:8px;margin:8px 0;';
      xsEditor.appendChild(img);
      var imeta = document.createElement('div');
      imeta.className = 'insight-meta';
      imeta.textContent = '↑この画像をおりポスに添付します';
      xsEditor.appendChild(imeta);
    } else {
      var noimg = document.createElement('div');
      noimg.className = 'insight-meta';
      noimg.textContent = '⚠️ アイキャッチ画像なし (テキストのみで投稿)';
      xsEditor.appendChild(noimg);
    }
    var l1 = document.createElement('div');
    l1.style.cssText = 'font-weight:600;margin-top:10px;';
    l1.textContent = '① おりポス (URLなし・画像付き)';
    xsEditor.appendChild(l1);
    var mainTa = document.createElement('textarea');
    mainTa.rows = 6;
    mainTa.style.cssText = 'width:100%;margin-top:6px;font-size:14px;padding:10px;white-space:pre-wrap;';
    mainTa.value = draft.main_text || '';
    xsEditor.appendChild(mainTa);
    xsEditor.appendChild(xsCounter(mainTa, 'おりポス', 900));
    // 2026-07-07 試合後スレ: data_text があれば ②データリプ を挟んで3連にする
    var dataTa = null;
    if (draft.is_thread) {
      var ld = document.createElement('div');
      ld.style.cssText = 'font-weight:600;';
      ld.textContent = '② データリプ (insight.db verified数字)' + (draft.data_text ? '' : ' — 取得できず (空なら2連で投稿)');
      xsEditor.appendChild(ld);
      dataTa = document.createElement('textarea');
      dataTa.rows = 4;
      dataTa.style.cssText = 'width:100%;margin-top:6px;font-size:14px;padding:10px;white-space:pre-wrap;';
      dataTa.value = draft.data_text || '';
      xsEditor.appendChild(dataTa);
      xsEditor.appendChild(xsCounter(dataTa, 'データリプ'));
    }
    var l2 = document.createElement('div');
    l2.style.cssText = 'font-weight:600;';
    l2.textContent = (draft.is_thread ? '③' : '②') + ' リプ (記事の続き + URL)';
    xsEditor.appendChild(l2);
    var replyTa = document.createElement('textarea');
    replyTa.rows = 4;
    replyTa.style.cssText = 'width:100%;margin-top:6px;font-size:14px;padding:10px;white-space:pre-wrap;';
    replyTa.value = draft.reply_text || '';
    xsEditor.appendChild(replyTa);
    xsEditor.appendChild(xsCounter(replyTa, 'リプ'));
    var postBtn = document.createElement('button');
    postBtn.type = 'button';
    postBtn.className = 'primary';
    postBtn.textContent = draft.is_thread ? '🚀 スレを連続投稿 (最大3連)' : '🚀 おりポス+リプを連続投稿';
    postBtn.style.cssText = 'width:100%;padding:14px;font-size:15px;margin-top:6px;';
    postBtn.addEventListener('click', async function() {
      var nParts = 2 + ((dataTa && dataTa.value.trim()) ? 1 : 0);
      if (!confirm('X に' + nParts + '連投稿します。よろしいですか？')) { return; }
      postBtn.disabled = true;
      postBtn.textContent = '🚀 投稿中...';
      try {
        var resp = await fetch('/x-share-thread', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({
            main_text: mainTa.value || '',
            reply_text: replyTa.value || '',
            data_text: (dataTa && dataTa.value) || '',
            image_url: draft.image_url || '',
            share_type: draft.share_type || (draft.is_thread ? 'postgame_thread' : ''),
          }),
        });
        var json = await resp.json().catch(function() { return {}; });
        if (json && json.ok) {
          postBtn.textContent = '✅ 投稿成功 (おりポス id=' + (json.main_tweet_id || '?') + (json.image_attached ? ' / 画像付き' : ' / ⚠️画像なし') + ')';
        } else {
          postBtn.textContent = '❌ 失敗: ' + (json.reason || ('status ' + resp.status));
          postBtn.disabled = false;
        }
      } catch (e) {
        postBtn.textContent = '❌ エラー: ' + String(e);
        postBtn.disabled = false;
      }
    });
    xsEditor.appendChild(postBtn);
  }
  async function xsLoadDraft(postId) {
    xsEditor.hidden = true;
    try {
      var resp = await fetch('/x-share-draft?' + new URLSearchParams({post_id: String(postId)}).toString(), {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      var json = await resp.json().catch(function() { return {}; });
      if (json && json.ok) {
        xsRenderEditor(json);
        xsEditor.scrollIntoView({behavior: 'smooth'});
        return true;
      }
      alert('下書き生成に失敗: ' + (json.reason || resp.status));
    } catch (e) {
      alert('エラー: ' + String(e));
    }
    return false;
  }
  async function xsPickPost(postId, btn) {
    btn.disabled = true;
    var orig = btn.textContent;
    btn.textContent = '📡 下書き生成中...';
    await xsLoadDraft(postId);
    btn.disabled = false;
    btn.textContent = orig;
  }
  // 2026-07-07 試合後スレ: 最新の試合結果記事から3部品を自動生成
  async function xsLoadThreadDraft() {
    xsEditor.hidden = true;
    try {
      var resp = await fetch('/x-thread-draft', {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      var json = await resp.json().catch(function() { return {}; });
      if (json && json.ok) {
        xsRenderEditor(json);
        xsEditor.scrollIntoView({behavior: 'smooth'});
        return true;
      }
      alert(resp.status === 404 ? '試合結果の記事がまだありません (試合後に自動生成されてから使えます)。' : 'スレ案生成に失敗: ' + (json.reason || resp.status));
    } catch (e) {
      alert('エラー: ' + String(e));
    }
    return false;
  }
  var xsThreadBtn = document.getElementById('xshare-thread-btn');
  if (xsThreadBtn) {
    xsThreadBtn.addEventListener('click', async function() {
      xsThreadBtn.disabled = true;
      xsThreadBtn.textContent = '📡 スレ案 生成中...';
      await xsLoadThreadDraft();
      xsThreadBtn.disabled = false;
      xsThreadBtn.textContent = '🧵 今日の試合スレ案を作る (結果→データ→記事)';
    });
  }
  // mail の「🧵 スレを組む」リンク (?thread=postgame) から開いた時は自動でスレ案を出す
  if (new URLSearchParams(location.search).get('thread')) {
    var xsTabBtn = document.getElementById('tab-btn-xshare');
    if (xsTabBtn) xsTabBtn.click();
    xsLoadThreadDraft();
  }
  // 手動投入の結果画面から呼ぶ: 記事共有タブへ切替して下書きを開く
  window.xsOpenForPost = async function(postId, btn) {
    var tabBtn = document.getElementById('tab-btn-xshare');
    if (tabBtn) tabBtn.click();
    if (btn) { btn.disabled = true; btn.textContent = '📡 おりポス+リプ案 生成中...'; }
    await xsLoadDraft(postId);
    if (btn) { btn.disabled = false; btn.textContent = '🐦 おりポス+リプ案を作る'; }
  };
  var xsManualBtn = document.getElementById('xshare-manual-btn');
  if (xsManualBtn) {
    xsManualBtn.addEventListener('click', async function() {
      var raw = (document.getElementById('xshare-manual-input').value || '').trim();
      // 記事URL (https://yoshilover.com/102490 等) から末尾の数字ID を拾う
      var m = raw.match(new RegExp('([0-9]+)/?$'));
      if (!m) { alert('post_id が読み取れません。記事URLか数字IDを入れてください。'); return; }
      xsManualBtn.disabled = true;
      xsManualBtn.textContent = '📡 生成中...';
      await xsLoadDraft(m[1]);
      xsManualBtn.disabled = false;
      xsManualBtn.textContent = '案を作る';
    });
  }
  if (xsRefresh) {
    xsRefresh.addEventListener('click', async function() {
      xsRefresh.disabled = true;
      xsRefresh.textContent = '📡 読み込み中...';
      xsPosts.innerHTML = '';
      try {
        var resp = await fetch('/x-share-recent', {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          credentials: 'same-origin',
        });
        var json = await resp.json().catch(function() { return {}; });
        if (json && json.ok && json.posts && json.posts.length) {
          json.posts.forEach(function(p) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'secondary';
            b.style.cssText = 'width:100%;text-align:left;padding:10px;margin-top:6px;font-size:13px;';
            b.textContent = (p.date ? p.date.slice(5, 16).replace('T', ' ') + ' ' : '') + (p.title || ('#' + p.id));
            b.addEventListener('click', function() { xsPickPost(p.id, b); });
            xsPosts.appendChild(b);
          });
        } else {
          xsPosts.textContent = '公開記事が取得できませんでした: ' + (json.reason || '');
        }
      } catch (e) {
        xsPosts.textContent = 'エラー: ' + String(e);
      }
      xsRefresh.disabled = false;
      xsRefresh.textContent = '🔄 最近の公開記事を読み込む';
    });
  }

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
        msg += '\\n\\n読み取れた条件: ' + JSON.stringify(payload.parsed);
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
      counter.textContent = n + ' / 900 字' + (n > 900 ? ' ⚠️ 超過' : '');
      counter.style.color = (n > 900) ? '#b71c1c' : '';
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
      if (text.length > 900) {
        alert('900 字を超過しています。短くしてから投稿してください。');
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
    '監督談話': '監督談話を記事化 → 公開',
    '選手コメント': '選手コメントを記事化 → 公開',
    '予告先発': '予告先発を記事化 → 公開',
    '公示': '公示を記事化 → 公開',
    '動画': '動画を記事化 → 公開',
    '試合結果': '試合結果を記事化 → 公開',
    '試合速報': '試合速報を記事化 → 公開',
    '成績': '成績を記事化 → 公開',
    '番組情報': '番組情報を記事化 → 公開',
    'コラム': 'コラムを記事化 → 公開',
    'ニュース': 'ニュースを記事化 → 公開',
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
    if (submitBtn) submitBtn.textContent = SUBMIT_LABEL[t] || '記事化 → 公開';
    if (typeHint) typeHint.textContent = TYPE_HINT[t] || DEFAULT_HINT;
    factsBlocks.forEach(function(block) {
      const types = (block.getAttribute('data-types') || '').split(',').map(s => s.trim());
      const visible = types.indexOf(t) >= 0;
      block.hidden = !visible;
    });
  }
  if (articleType) articleType.addEventListener('change', syncTypeUI);
  syncTypeUI();

  var sourceForm = document.getElementById('source-form');
  var sourceResult = document.getElementById('source-result');
  var sourceSubmit = document.getElementById('source-submit-btn');
  function setInputValue(id, value) {
    var el = document.getElementById(id);
    if (el && value) el.value = value;
  }
  function fillIntakeFromSource(item) {
    setInputValue('url', item.url || '');
    setInputValue('title', item.title || '');
    setInputValue('summary', item.summary || '');
    setInputValue('source_published_at', item.published_at || '');
    if (articleType && item.article_type) {
      articleType.value = item.article_type;
      syncTypeUI();
    }
    var intakeTab = document.getElementById('tab-btn-intake');
    if (intakeTab) intakeTab.click();
    var urlInput = document.getElementById('url');
    if (urlInput) urlInput.focus();
  }
  function renderSourceCandidates(payload) {
    if (!sourceResult) return;
    sourceResult.hidden = false;
    sourceResult.innerHTML = '';
    if (!payload || !payload.ok) {
      sourceResult.className = 'err';
      sourceResult.textContent = '失敗: ' + (payload && payload.reason ? payload.reason : 'unknown');
      return;
    }
    var items = payload.items || [];
    if (!items.length) {
      sourceResult.className = '';
      sourceResult.textContent = '候補なし。該当ソースに巨人記事が無い、または鮮度条件で除外されています。';
      return;
    }
    sourceResult.className = '';
    var meta = document.createElement('div');
    meta.className = 'insight-meta';
    meta.textContent = items.length + ' 件 / source ' + (payload.fetched_source_count || 0) + ' 件取得';
    sourceResult.appendChild(meta);
    items.forEach(function(item) {
      var row = document.createElement('div');
      row.className = 'source-item';
      var title = document.createElement('div');
      title.className = 'source-item-title';
      title.textContent = item.title || '';
      row.appendChild(title);
      var m = document.createElement('div');
      m.className = 'source-item-meta';
      m.textContent = (item.source_name || '') + (item.published_at ? ' / ' + item.published_at : '') + (item.article_type ? ' / ' + item.article_type : '');
      row.appendChild(m);
      var a = document.createElement('a');
      a.className = 'source-item-url';
      a.href = item.url || '#';
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = item.url || '';
      row.appendChild(a);
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'primary source-use-btn';
      btn.textContent = 'このURLを投入';
      btn.addEventListener('click', function() { fillIntakeFromSource(item); });
      row.appendChild(btn);
      sourceResult.appendChild(row);
    });
  }
  if (sourceForm) {
    sourceForm.addEventListener('submit', async function(ev) {
      ev.preventDefault();
      if (sourceResult) sourceResult.hidden = true;
      if (sourceSubmit) {
        sourceSubmit.disabled = true;
        sourceSubmit.textContent = '取得中...';
      }
      var data = new FormData(sourceForm);
      var params = new URLSearchParams();
      data.forEach(function(v, k) { if (v) params.append(k, v); });
      try {
        var resp = await fetch('/source-candidates?' + params.toString(), {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
          credentials: 'same-origin',
        });
        var json = await resp.json().catch(function() { return {}; });
        renderSourceCandidates(json);
      } catch (e) {
        renderSourceCandidates({ ok: false, reason: String(e) });
      } finally {
        if (sourceSubmit) {
          sourceSubmit.disabled = false;
          sourceSubmit.textContent = '候補を取得';
        }
      }
    });
  }

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
    const _resultLabel = (
      payload.mode === 'publish' ? '✅ 公開 OK (status=publish)'
      : payload.mode === 'draft' ? '✅ 下書き作成 OK'
      : '✅ 確認 OK'
    );
    const lines = [
      '結果: ' + _resultLabel,
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
      link.textContent = (payload.mode === 'publish' ? '🔗 公開記事を開く' : '🔗 下書きを開く');
      link.style.cssText = 'display:inline-block;margin-top:10px;';
      result.appendChild(document.createElement('br'));
      result.appendChild(link);
    }
    // 2026-07-06 user「記事化公開とおりポスリプのボタンにしといて」:
    // 記事化した記事の post_id からそのまま X 共有下書きへ (既存機能は残す)。
    if (payload.post_id && payload.mode !== 'dry-run') {
      const shareBtn = document.createElement('button');
      shareBtn.type = 'button';
      shareBtn.textContent = '🐦 おりポス+リプ案を作る';
      shareBtn.style.cssText = 'display:block;width:100%;margin-top:10px;padding:12px;font-size:15px;background:#1d9bf0;color:#fff;border:none;border-radius:8px;font-weight:600;cursor:pointer;';
      shareBtn.addEventListener('click', function() {
        if (window.xsOpenForPost) window.xsOpenForPost(payload.post_id, shareBtn);
      });
      result.appendChild(shareBtn);
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
    const saveAsDraftToggle = document.getElementById('save-as-draft-toggle');
    let _mode;
    if (dryRunToggle && dryRunToggle.checked) { _mode = 'dry-run'; }
    else if (saveAsDraftToggle && saveAsDraftToggle.checked) { _mode = 'draft'; }
    else { _mode = 'publish'; }
    body.set('mode', _mode);
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
        submitBtn.textContent = originalLabel || '記事化 → 公開';
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


# 2026-07-15 観戦モード共通: フーガ直近30本の再分析を反映した voice 上乗せ。
# 本体 prompt (x_post_branding_gen) は変えず、手動観戦系 endpoint のみに適用。
_LIVE_VOICE_NOTE = (
    "観戦LIVE手動モード: 入力は投稿者が今まさに見た場面のメモ。"
    "①入力に選手が複数いれば全員フルネームで使ってよい (束ね列挙OK)。"
    "②決定的な場面 (本塁打/同点/勝ち越し等が入力にある時) は"
    "『実名＋感嘆連打の絶叫型』の超短文でよい (例: 俺たちの坂本勇人！！！ 一振りで決めた！！)。"
    "③口語のツッコミ・自問 (「魔改造か」「どういうこと？」) や"
    "祈り形の願い (「頼む」「この調子で頼む」) はフーガ節としてOK。"
    "④劣勢場面の締めは説教ではなく切り替え (「全て明日だ」「切り替えだ」)。"
    "⑤【最重要】入力に無い場面の細部を創作しない: 打席経過 (初球/追い込まれて/"
    "フルカウント等)・カウント・球種・打球方向・スコア・ベンチや表情の描写・"
    "確信歩き等の仕草。入力に無い細部が欲しくても、打った事実と感情だけで書く。"
    "⑥締めは読者がリプで答えたくなる短い問いかけにする"
    " (「どう見た？」「〜と思わんか？」「〜に期待でいいよな？」)。"
    "断定の「だよな。」で閉じるより、読者が一言返せる形を優先する。"
)

# 観戦手動系で追加破棄する創作細部語 (claim語gate の局所補強)
_LIVE_LOCAL_CLAIM_WORDS = (
    "初球", "追い込まれ", "フルカウント", "確信歩き",
    "ベンチ", "表情", "スタンドへ確信",
)

# ネタボタン (2026-07-15 user「アプリに入れると面白いネタ」「リアルタイムで拾って」)
_LIVE_NETA_KINDS: dict[str, dict[str, str]] = {
    "next": {
        "label": "🎯 次に期待",
        "note": "型=次の一打・次の展開への期待。事実行の流れを受けて「ここで一本欲しい」"
                "「この展開はもう◯◯しかないやろ」の先回り期待型で短く。"
                "次の打者名は事実行に無ければ書かない (勝手に打順を推測しない)。",
    },
    "saihai": {
        "label": "🧠 采配ひとこと",
        "note": "型=采配への問いかけ。事実行の継投/起用の事実だけを受けて"
                "「ここで交代か」「引っ張るのか」と読者に賛否を問う。"
                "監督個人への攻撃・無能呼ばわりは絶対禁止、あくまで議論の提起。",
    },
    "keika": {
        "label": "📊 中間経過",
        "note": "型=定点の中間経過。スコアと回を必ず本文に入れ、ここまでの試合の"
                "空気を一言添え、締めは「ここからどう見る？」系の問いかけ。",
    },
    "makeso": {
        "label": "😤 劣勢の歯がゆさ",
        "note": "型=劣勢の歯がゆさ・疑問視。悔しさは同じファン目線で吐き出すが、"
                "個人攻撃・戦犯探し・「使えない」系は絶対禁止。"
                "締めは「切り替えだ」「まだ分からんぞ」系の粘り。",
    },
    "kuji": {
        "label": "🎰 くじ型ユーモア",
        "note": "型=ユーモアの飛び道具 (フーガの「ドリームサマーリチャードくじ」風)。"
                "事実行にいる選手だけを使い、「ここで当てなかったらどこで当てるんや」"
                "のような笑える願掛けを1本。ふざけすぎず野球ファンの愛嬌の範囲で。",
    },
}


def _fmt_live_play(p: dict) -> str:
    """一球速報 play dict を 1 行の日本語事実行に (live-plays / ネタ便共用)。"""
    oc = (p.get("outcome") or "").strip()
    if not oc:
        return ""
    if p.get("giants_batting"):
        return f"{p['inning']}回{p['half']} {p.get('batter', '')} {oc}".strip()
    pit = (p.get("pitcher") or "").strip()
    who = (p.get("batter") or "").strip()
    if pit:
        return f"{p['inning']}回{p['half']} {pit}、{who}を{oc}".strip()
    return f"{p['inning']}回{p['half']} {who} {oc}".strip()


def _recent_giants_pitching_change(plays: list) -> tuple[str, str]:
    """巨人側投手の直近交代 (prev, cur) を返す。交代なし/古い交代は ("", "")。

    「古い」= 現投手が既に 9 打者以上投げている (≒交代から3イニング相当)。"""
    seq = [
        (p.get("pitcher") or "").strip()
        for p in plays
        if not p.get("giants_batting") and (p.get("pitcher") or "").strip()
    ]
    order: list[str] = []
    for name in seq:
        if not order or order[-1] != name:
            order.append(name)
    if len(order) < 2:
        return "", ""
    cur = order[-1]
    cur_batters = 0
    for name in reversed(seq):
        if name != cur:
            break
        cur_batters += 1
    if cur_batters > 9:
        return "", ""
    return order[-2], cur


# ── リプ返し (2026-07-15 user「リプが来た人・良い関係リストを作って私がリプを作る」) ──
_TWEET_URL_ID_RE = re.compile(r"(?:x|twitter)\.com/[^/]+/status/(\d+)")


def _extract_tweet_id(url: str) -> str:
    m = _TWEET_URL_ID_RE.search(url or "")
    return m.group(1) if m else ""


def _fetch_tweet_syndication(tweet_id: str) -> dict[str, str]:
    """公開 tweet の本文/作者を X syndication API から取る (認証不要・読み取り¥0)。
    失敗時は空 dict (caller で fail-open)。"""
    try:
        req = urlrequest.Request(
            f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=a",
            headers={"User-Agent": "Mozilla/5.0 (yoshilover-live-reply)"},
        )
        with urlrequest.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        user = data.get("user") or {}
        return {
            "text": (data.get("text") or "").strip(),
            "handle": (user.get("screen_name") or "").strip(),
            "name": (user.get("name") or "").strip(),
        }
    except Exception:  # noqa: BLE001
        logging.getLogger("manual_intake_service").info(
            "tweet_syndication_fetch_failed id=%s", tweet_id
        )
        return {}


def _friends_blob():
    bucket_name = (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()
    if not bucket_name:
        return None
    from google.cloud import storage

    return storage.Client().bucket(bucket_name).blob("live_reply/friends.json")


def _load_friends() -> dict[str, dict[str, Any]]:
    """常連リスト (handle → {count, name, last})。読めない時は空 (fail-open)。"""
    try:
        blob = _friends_blob()
        if blob is None or not blob.exists():
            return {}
        return json.loads(blob.download_as_bytes().decode("utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


# ヤジ判定 (2026-07-15 user「ただのヤジは消す機能」): 侮辱・煽り語の決定的 check。
# 該当リプには文案を作らず (LLM節約 + 燃え防止)、🚫登録を促す。
_YAJI_WORDS = (
    "使えない", "戦犯", "クビ", "最悪", "酷い", "ひどすぎ", "論外", "引退しろ",
    "辞めろ", "やめろ", "無能", "ゴミ", "カス", "ザコ", "雑魚", "バカ", "馬鹿",
    "アホ", "死ね", "消えろ", "give up", "才能ない", "金返せ", "解任",
)


def _looks_like_yaji(text: str) -> bool:
    t = (text or "").lower()
    return any(w.lower() in t for w in _YAJI_WORDS)


def _remove_friend(handle: str) -> bool:
    """常連リストから完全削除 (2026-07-15 user「消すこともできるんでしょ？」)。"""
    handle = (handle or "").lstrip("@").strip()
    if not handle:
        return False
    try:
        blob = _friends_blob()
        friends = _load_friends()
        if handle not in friends:
            return True
        del friends[handle]
        if blob is not None:
            blob.upload_from_string(
                json.dumps(friends, ensure_ascii=False),
                content_type="application/json",
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def _flag_friend_yaji(handle: str) -> bool:
    """handle をヤジ認定 (常連リストから恒久除外)。成功 True。"""
    handle = (handle or "").lstrip("@").strip()
    if not handle:
        return False
    try:
        blob = _friends_blob()
        friends = _load_friends()
        ent = friends.get(handle) or {"count": 0, "name": ""}
        ent["yaji"] = True
        friends[handle] = ent
        if blob is not None:
            blob.upload_from_string(
                json.dumps(friends, ensure_ascii=False),
                content_type="application/json",
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def _bump_friend(handle: str, name: str) -> int:
    """リプ返し投稿の成功時に常連カウントを +1。返り値=更新後 count (失敗 0)。"""
    handle = (handle or "").lstrip("@").strip()
    if not handle:
        return 0
    try:
        blob = _friends_blob()
        friends = _load_friends()
        ent = friends.get(handle) or {"count": 0, "name": name}
        ent["count"] = int(ent.get("count") or 0) + 1
        if name:
            ent["name"] = name
        ent["last"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # リプ返しした = 常連認定 (候補/非表示から自動昇格)
        ent.pop("candidate", None)
        ent.pop("dismissed", None)
        friends[handle] = ent
        if blob is not None:
            blob.upload_from_string(
                json.dumps(friends, ensure_ascii=False),
                content_type="application/json",
            )
        return int(ent["count"])
    except Exception:  # noqa: BLE001
        logging.getLogger("manual_intake_service").info(
            "friend_bump_failed handle=%s", handle
        )
        return 0


_TREND_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
_TREND_CACHE_TTL_SECONDS = 600


def _fetch_trend_items() -> list[dict[str, str]]:
    """急上昇ワード (news 情報つき full dict) を 10 分 cache で返す。

    2026-07-16 user「フォロワーを増やすのに何かアプリ作れない？」: 実測の当たり枠
    = トレンド反応を、mail 便を待たず即応で打つための素材。失敗は空 (fail-open)。
    """
    now_ts = time.time()
    if _TREND_CACHE["items"] and now_ts - _TREND_CACHE["ts"] < _TREND_CACHE_TTL_SECONDS:
        return _TREND_CACHE["items"]
    try:
        from src import search_trend_note as stn

        roster = stn._giants_name_tokens()
        relevant: list[dict] = []
        for t in stn.fetch_jp_trends():
            kw = t.get("keyword") or ""
            cat = stn.categorize_trend_keyword(kw, roster)
            if cat:
                relevant.append({**t, "category": cat})
        stn.merge_yahoo_topics_into_relevant(relevant, roster)
        stn.fill_mlb_from_mentions(relevant)
        _TREND_CACHE["items"] = relevant
        _TREND_CACHE["ts"] = now_ts
        return relevant
    except Exception:  # noqa: BLE001
        logging.getLogger("manual_intake_service").exception("trend_items_failed")
        return _TREND_CACHE["items"] or []


def _news_lookup_for_keyword(kw: str) -> dict[str, str]:
    """Bing News RSS 検索で keyword の最新記事 1 本 (title/url/source)。

    2026-07-16 user「巨人/MLBの語が全部押せない」: 急上昇語の多く (言及数由来の
    MLB 語等) は news 情報を持たない。タップ時にここで記事を探して接地する。
    Google News RSS はリダイレクト interstitial で本文が読めないため Bing。
    見つからなければ {} (生成は no_article で止まる、捏造はしない)。
    """
    import urllib.parse
    import urllib.request
    from xml.etree import ElementTree

    try:
        q = urllib.parse.quote(f"{kw} 野球")
        url = f"https://www.bing.com/news/search?q={q}&format=rss&setmkt=ja-JP"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            xml_text = r.read()
        root = ElementTree.fromstring(xml_text)
        item = root.find("./channel/item")
        if item is None:
            return {}
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            return {}
        return {"news_title": title, "news_url": link, "news_source": "Bing News"}
    except Exception:  # noqa: BLE001
        return {}


_MAIN_X_HANDLE = "yoshilover6760"
_OUR_X_HANDLES = {_MAIN_X_HANDLE, "yoshilover_naka"}
_CANDIDATE_SYNDICATION_CAP = 10

# フォロー開拓 (2026-07-16 user「フォロワーを増やしたいアプリ」):
# 公式/媒体アカはフォロー対象にしない (フォロバが無い)
_SCOUT_MEDIA_HANDLES = {
    "tokyogiants", "hochi_giants", "hochi_baseball", "sportshochi",
    "sanspo_giants", "sanspo", "nikkansports", "ntv_sports_jp",
    "sponichiyakyu", "mlbjapan", "mlb", "npb", "yomiuri_online",
    "asahi_koshien", "dailysportsbb", "tospo_prores", "yakyu_kozo",
}
# 開拓の検索クエリ: 公式/MLB公式へリプしている人 = 活発なファンでフォロバ期待層
_SCOUT_QUERIES = (
    ("@TokyoGiants", "巨人公式にリプ"),
    ("@hochi_giants", "報知巨人にリプ"),
    ("@MLBJapan", "MLB公式にリプ"),
)
_SCOUT_MAX_AGE_MINUTES = 30


def _scout_blob():
    bucket_name = (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()
    if not bucket_name:
        return None
    from google.cloud import storage

    return storage.Client().bucket(bucket_name).blob("follow_scout/seen.json")


def _load_scout_seen() -> dict[str, dict[str, Any]]:
    """開拓済み台帳 (handle → {status: followed|skip, date, name})。失敗は空。"""
    try:
        blob = _scout_blob()
        if blob is None or not blob.exists():
            return {}
        return json.loads(blob.download_as_bytes().decode("utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _mark_scout(handle: str, status: str, name: str = "") -> bool:
    """開拓台帳の更新。status: followed / skip / undo (=記録取り消し)。"""
    handle = (handle or "").lstrip("@").strip()
    if not handle or status not in ("followed", "skip", "undo"):
        return False
    try:
        blob = _scout_blob()
        seen = _load_scout_seen()
        if status == "undo":
            if handle not in seen:
                return True
            del seen[handle]
        else:
            seen[handle] = {
                "status": status,
                "name": name,
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
        if blob is not None:
            blob.upload_from_string(
                json.dumps(seen, ensure_ascii=False),
                content_type="application/json",
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def _collect_scout_candidates() -> list[dict[str, Any]]:
    """活発なファン (公式アカへの最近のリプ主) を Yahoo リアルタイム検索で収集。

    フォロー済み/スキップ済み/媒体/自アカ/既知の常連・ヤジは除外。¥0・LLMなし。
    """
    try:
        from src.rss_fetcher import fetch_yahoo_realtime_entries
    except Exception:  # noqa: BLE001
        return []
    seen = _load_scout_seen()
    friends = _load_friends()
    excluded = (
        {h.lower() for h in seen}
        | {h.lower() for h in friends}
        | _SCOUT_MEDIA_HANDLES
        | _OUR_X_HANDLES
    )
    out: list[dict[str, Any]] = []
    got: set[str] = set()
    for query, origin in _SCOUT_QUERIES:
        try:
            entries = fetch_yahoo_realtime_entries(query) or []
        except Exception:  # noqa: BLE001
            continue
        for e in entries:
            url = str(e.get("link") or "")
            m = re.search(r"(?:x|twitter)\.com/(\w{1,15})/status/\d+", url)
            if not m:
                continue
            handle = m.group(1)
            hl = handle.lower()
            if hl in excluded or hl in got or "公式" in handle:
                continue
            text = str(e.get("title") or e.get("summary") or "").strip()
            if _looks_like_yaji(text):
                continue
            # 鮮度 (2026-07-16 user「短くないと」): 今まさに X を開いている人が
            # フォロバ率最高なので、60分以内のリプ主のみ。時刻不明も除外。
            age_min = -1
            try:
                created = float(e.get("created_at") or 0)
                if created > 0:
                    age_min = max(0, int((time.time() - created) / 60))
            except Exception:  # noqa: BLE001
                age_min = -1
            if age_min < 0 or age_min > _SCOUT_MAX_AGE_MINUTES:
                continue
            got.add(hl)
            out.append(
                {
                    "handle": handle,
                    "text": text[:120],
                    "origin": origin,
                    "url": url.split("?")[0],
                    "age_min": age_min,
                }
            )
    out.sort(key=lambda c: c["age_min"] if c["age_min"] >= 0 else 10**6)
    return out[:30]


def _set_friend_flags(handle: str, *, mode: str) -> bool:
    """常連 entry の状態変更。mode: dismiss=候補を非表示 / keep=常連へ昇格。"""
    handle = (handle or "").lstrip("@").strip()
    if not handle:
        return False
    try:
        blob = _friends_blob()
        friends = _load_friends()
        ent = friends.get(handle)
        if ent is None:
            return False
        if mode == "dismiss":
            ent["dismissed"] = True
            ent.pop("candidate", None)
        elif mode == "keep":
            ent.pop("candidate", None)
            ent.pop("dismissed", None)
            ent.pop("yaji_hint", None)
        else:
            return False
        friends[handle] = ent
        if blob is not None:
            blob.upload_from_string(
                json.dumps(friends, ensure_ascii=False),
                content_type="application/json",
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def _collect_reply_candidates() -> int:
    """2026-07-16 user「自動化で入れないと手間」: 自分宛リプを Yahoo リアルタイム
    検索 (¥0) で拾い、未知の相手を常連「候補」として friends.json へ追記する。

    - 既に friends.json にいる handle (常連/候補/dismissed/ヤジ) は再追加しない
    - 自アカは除外。ヤジ語入りは yaji_hint を立てて候補に出す (自動ヤジ認定はしない)
    - 返り値 = 新規追加数。取得失敗は 0 (fail-open、ページ表示は止めない)
    """
    try:
        from src.rss_fetcher import fetch_yahoo_realtime_entries

        entries = fetch_yahoo_realtime_entries("@" + _MAIN_X_HANDLE) or []
    except Exception:  # noqa: BLE001
        return 0
    if not entries:
        return 0
    try:
        friends = _load_friends()
        known = {h.lower() for h in friends}
        added = 0
        synd_used = 0
        for e in entries:
            url = str(e.get("link") or "")
            m = re.search(r"(?:x|twitter)\.com/(\w{1,15})/status/(\d+)", url)
            if not m:
                continue
            handle, tweet_id = m.group(1), m.group(2)
            if handle.lower() in _OUR_X_HANDLES or handle.lower() in known:
                continue
            text = str(e.get("title") or e.get("summary") or "").strip()
            name = ""
            if synd_used < _CANDIDATE_SYNDICATION_CAP:
                synd_used += 1
                try:
                    name = _fetch_tweet_syndication(tweet_id).get("name", "")
                except Exception:  # noqa: BLE001
                    name = ""
            ent: dict[str, Any] = {
                "count": 0,
                "name": name,
                "last": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "candidate": True,
                "text": text[:120],
                "url": url.split("?")[0],
            }
            if _looks_like_yaji(text):
                ent["yaji_hint"] = True
            friends[handle] = ent
            known.add(handle.lower())
            added += 1
        if added:
            blob = _friends_blob()
            if blob is not None:
                blob.upload_from_string(
                    json.dumps(friends, ensure_ascii=False),
                    content_type="application/json",
                )
        return added
    except Exception:  # noqa: BLE001
        return 0


def _render_live_page() -> str:
    """2026-07-15 user「キーワード入れたらポストが出てくる手動アプリ」観戦モード。

    場面の一言 → /live-fuga (Gemini 2案 + claim語gate) → 直接投稿 or コピー。
    auth は cookie (manual_intake_session) 前提。同一 origin fetch で自動送信。
    """
    return """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>観戦モード｜ヨシラバー</title>
<style>
body{font-family:sans-serif;background:#fafafa;margin:0;padding:12px;max-width:640px;margin:auto}
h1{font-size:1.1rem;color:#f57f17}
textarea{width:100%;box-sizing:border-box;font-size:1.05rem;padding:10px;border:1px solid #ccc;border-radius:8px;min-height:64px}
input[type=text]{width:100%;box-sizing:border-box;font-size:1rem;padding:8px;border:1px solid #ccc;border-radius:8px}
button{font-size:1rem;padding:10px 16px;border:0;border-radius:8px;cursor:pointer}
#gen{background:#f57f17;color:#fff;width:100%;margin-top:10px;font-weight:bold}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px;margin-top:12px;white-space:pre-wrap}
.card .style{font-size:.8rem;color:#888}
.card .cnt{font-size:.75rem;color:#aaa}
.row{display:flex;gap:8px;margin-top:8px}
.post{background:#1d9bf0;color:#fff;flex:1}
.copy{background:#eee;flex:1}
#status{margin-top:10px;font-size:.9rem;color:#666}
.note{font-size:.75rem;color:#999;margin-top:6px}
</style></head><body>
<h1>⚾ 観戦モード — 一言→ヨシラバー文体 <a href="/" style="font-size:.8rem;float:right;color:#888">← 戻る</a></h1>
<textarea id="scene" placeholder="例: 岡本 逆方向に2ラン 5-3"></textarea>
<input type="text" id="player" placeholder="主役の選手名 (任意)。複数選手は場面欄にそのまま書けば全員使われます" style="margin-top:8px">
<div class="row" style="margin-top:10px">
<button id="gen-short" onclick="gen('short')" style="background:#f57f17;color:#fff;flex:1;font-weight:bold">⚡ 短文をつくる</button>
<button id="gen-long" onclick="gen('long')" style="background:#e65100;color:#fff;flex:1;font-weight:bold">📜 長文をつくる</button>
</div>
<div class="row" style="margin-top:8px">
<button onclick="pickPlays()" style="background:#efebe9;flex:1">📡 今の場面を拾う</button>
<button onclick="recap()" style="background:#fff8e1;flex:1">🐰 今日のまとめ</button>
</div>
<div class="row" style="margin-top:8px;flex-wrap:wrap">
<button onclick="neta('next')" style="background:#e8f5e9;font-size:.85rem;flex:1;min-width:30%">🎯 次に期待</button>
<button onclick="neta('saihai')" style="background:#e3f2fd;font-size:.85rem;flex:1;min-width:30%">🧠 采配</button>
<button onclick="neta('keika')" style="background:#f3e5f5;font-size:.85rem;flex:1;min-width:30%">📊 経過</button>
<button onclick="neta('makeso')" style="background:#fbe9e7;font-size:.85rem;flex:1;min-width:30%">😤 劣勢</button>
<button onclick="neta('kuji')" style="background:#fffde7;font-size:.85rem;flex:1;min-width:30%">🎰 くじ</button>
</div>
<div style="margin-top:14px;border-top:1px dashed #ccc;padding-top:10px">
<input type="text" id="rurl" placeholder="💬 相手リプのURL または @ハンドル名を貼る">
<div class="row" style="margin-top:6px">
<button onclick="replyDraft()" style="background:#e0f2f1;flex:2">💬 リプ返し案をつくる</button>
<button onclick="friendAdd()" style="background:#e8eaf6;flex:1">➕ 常連に追加</button>
<button onclick="location.href='/friends'" style="background:#ede7f6;flex:1">👥 常連</button>
</div>
</div>
<div id="chips" style="margin-top:8px"></div>
<div id="status"></div>
<div id="out"></div>
<p class="note">※ 入力した事実だけが使われます (入力に無い展開語・打席経過の創作は自動破棄)。投稿前に一読を。</p>
<script>
function makeCard(d, regenFn, postExtra){
  const div=document.createElement('div'); div.className='card';
  div.innerHTML='<div class="style">'+d.style+' (編集して投稿できます)</div>'+
    '<textarea class="txt" style="margin-top:6px"></textarea>'+
    '<div class="cnt"></div>'+
    '<div class="row"><button class="post">Xに投稿</button><button class="regen" style="background:#fff3e0">🔄 再作成</button><button class="copy">コピー</button></div>';
  const ta=div.querySelector('.txt'), cnt=div.querySelector('.cnt');
  ta.value=d.text;
  const fit=()=>{cnt.textContent=ta.value.length+'字'; ta.style.height='auto'; ta.style.height=(ta.scrollHeight+4)+'px';};
  ta.oninput=fit;
  div.querySelector('.copy').onclick=()=>{navigator.clipboard.writeText(ta.value);div.querySelector('.copy').textContent='コピー済';};
  div.querySelector('.regen').onclick=()=>{regenFn(div);};
  div.querySelector('.post').onclick=async(ev)=>{
    const text=ta.value.trim();
    if(!text) return;
    if(!confirm('この内容でXに投稿します:\\n\\n'+text.slice(0,120)+(text.length>120?'…':'')+'\\n\\nよい？')) return;
    ev.target.disabled=true; ev.target.textContent='投稿中…';
    const pr=await fetch('/x-post-direct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({text:text}, postExtra||{}))});
    const pj=await pr.json();
    ev.target.textContent=pj.ok?(pj.friend_count>1?'投稿済✔ 常連'+pj.friend_count+'回目':'投稿済✔'):'失敗: '+(pj.reason||'');
    if(!pj.ok) ev.target.disabled=false;
  };
  setTimeout(fit, 0);
  return div;
}
function showCard(div, replaceCard){
  const out=document.getElementById('out');
  if(replaceCard){ out.replaceChild(div, replaceCard); } else { out.prepend(div); }
}
async function gen(style, replaceCard){
  const q = document.getElementById('scene').value.trim();
  if(!q){ document.getElementById('status').textContent='場面を入力してください (📡で拾えます)'; return; }
  const p = document.getElementById('player').value.trim();
  document.getElementById('status').textContent='生成中… (数秒)';
  try{
    const r = await fetch('/live-fuga?q='+encodeURIComponent(q)+'&player='+encodeURIComponent(p)+'&style='+style);
    const j = await r.json();
    if(!j.ok){ document.getElementById('status').textContent='生成できず (もう一度押してください): '+(j.reason||''); return; }
    document.getElementById('status').textContent = j.live_context ? ('📡 現況を反映: '+j.live_context) : '';
    showCard(makeCard(j.drafts[0], (card)=>gen(style, card)), replaceCard);
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function pickPlays(){
  document.getElementById('status').textContent='一球速報から取得中…';
  try{
    const r = await fetch('/live-plays');
    const j = await r.json();
    const chips=document.getElementById('chips'); chips.innerHTML='';
    if(!j.ok || !j.plays || !j.plays.length){ document.getElementById('status').textContent='直近プレーが取れませんでした (試合前/中断中？)'; return; }
    document.getElementById('status').textContent='タップで入力欄へ:';
    for(const pl of j.plays){
      const b=document.createElement('button');
      b.textContent=pl; b.style.cssText='display:block;width:100%;text-align:left;background:#fff;border:1px solid #ddd;margin-top:4px;font-size:.9rem';
      b.onclick=()=>{ document.getElementById('scene').value=pl; document.getElementById('status').textContent='場面をセット。⚡短文か📜長文を押してください'; };
      chips.appendChild(b);
    }
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function replyDraft(replaceCard){
  const u = document.getElementById('rurl').value.trim();
  if(!u){ document.getElementById('status').textContent='相手リプのURLを貼ってください'; return; }
  document.getElementById('status').textContent='相手の文面を取得して生成中… (数秒)';
  try{
    const r = await fetch('/live-reply-draft?url='+encodeURIComponent(u));
    const j = await r.json();
    if(!j.ok){
      if(j.reason==='yaji_suspected'){
        document.getElementById('status').textContent='⚠ ヤジっぽい内容です。返信すると燃えやすいので無視推奨: 「'+(j.their_text||'').slice(0,60)+'」';
        const chips=document.getElementById('chips'); chips.innerHTML='';
        const b=document.createElement('button');
        b.textContent='🚫 '+(j.name||'')+' @'+j.handle+' をヤジ登録する (常連対象外に)';
        b.style.cssText='display:block;width:100%;background:#ffebee;border:1px solid #ef9a9a;margin-top:4px';
        b.onclick=async()=>{ await fetch('/live-friend-flag?handle='+encodeURIComponent(j.handle)); b.textContent='🚫 登録済み'; b.disabled=true; };
        chips.appendChild(b);
        return;
      }
      const msgs={bad_tweet_url:'URLが読めません (x.com/…/status/… の形式で)', tweet_fetch_failed:'相手の文面を取得できませんでした (鍵アカ？)', generation_empty:'生成できず。もう一度どうぞ', yaji_flagged:'🚫 この人はヤジ登録済みです。無視が最善'};
      document.getElementById('status').textContent = msgs[j.reason] || ('生成できず: '+(j.reason||''));
      return;
    }
    const who = j.name+' @'+j.handle+(j.friend_count>0?' (常連'+(j.friend_count+1)+'回目)':' (初)');
    document.getElementById('status').textContent = '💬 '+who+': 「'+j.their_text.slice(0,80)+'」';
    showCard(makeCard(j.drafts[0], (card)=>replyDraft(card), {in_reply_to:j.reply_to_id, reply_to_handle:j.handle, reply_to_name:j.name}), replaceCard);
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function friendAdd(){
  const u = document.getElementById('rurl').value.trim();
  if(!u){ document.getElementById('status').textContent='過去リプのURLか @ハンドル名を貼ってください'; return; }
  document.getElementById('status').textContent='登録中…';
  try{
    const r = await fetch('/live-friend-add?who='+encodeURIComponent(u));
    const j = await r.json();
    if(!j.ok){
      const msgs={bad_who:'@ハンドル名かURLで入れてください (複数は空白区切り)'};
      document.getElementById('status').textContent = msgs[j.reason] || ('登録できず: '+(j.reason||''));
      return;
    }
    const names = j.added.map(a=>'@'+a.handle).join(' ');
    const skip = (j.skipped&&j.skipped.length) ? (' / 読めず・除外: '+j.skipped.join(' ')) : '';
    document.getElementById('status').textContent='➕ '+j.added.length+'人登録: '+names+skip;
    document.getElementById('rurl').value='';
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function neta(kind, replaceCard){
  document.getElementById('status').textContent='一球速報を拾って生成中… (数秒)';
  try{
    const r = await fetch('/live-neta?kind='+kind);
    const j = await r.json();
    if(!j.ok){
      const msgs={no_live_game:'今日は試合がない/試合前です', no_recent_change:'直近の継投がありません', not_losing:'いま劣勢ではないです(良いこと)', generation_empty:'生成できず。もう一度どうぞ'};
      document.getElementById('status').textContent = msgs[j.reason] || ('生成できず: '+(j.reason||''));
      return;
    }
    document.getElementById('status').textContent = j.live_context ? ('📡 '+j.live_context) : '';
    showCard(makeCard(j.drafts[0], (card)=>neta(kind, card)), replaceCard);
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function recap(replaceCard){
  document.getElementById('status').textContent='今日のまとめを生成中… (数秒)';
  try{
    const r = await fetch('/live-recap');
    const j = await r.json();
    if(!j.ok){
      document.getElementById('status').textContent = (j.reason==='game_not_finished') ? '試合終了後に使えます' : ('生成できず: '+(j.reason||''));
      return;
    }
    document.getElementById('status').textContent = j.live_context ? ('📡 '+j.live_context) : '';
    showCard(makeCard(j.drafts[0], (card)=>recap(card)), replaceCard);
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
</script></body></html>"""


def _render_friends_page() -> str:
    """2026-07-16 user「常連だけのページを作って分かりやすくして」。

    入るのは ①アプリからリプ返しを投稿した相手 (自動+1) ②手動追加 のみ。
    受信リプだけでは入らない。data は /live-friends (cookie auth) から取得。
    """
    return """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>常連さん｜ヨシラバー</title>
<style>
body{font-family:sans-serif;background:#fafafa;margin:0;padding:12px;max-width:640px;margin:auto}
h1{font-size:1.1rem;color:#5e35b1}
input[type=text]{width:100%;box-sizing:border-box;font-size:1rem;padding:8px;border:1px solid #ccc;border-radius:8px}
button{font-size:1rem;padding:10px 16px;border:0;border-radius:8px;cursor:pointer}
.row{display:flex;gap:8px;margin-top:8px}
#status{margin-top:10px;font-size:.9rem;color:#666}
.note{font-size:.78rem;color:#999;margin-top:6px;line-height:1.5}
.friend{background:#fff;border:1px solid #ddd;border-radius:10px;padding:10px 12px;margin-top:8px;display:flex;align-items:center;gap:10px}
.friend .rank{font-size:.85rem;color:#aaa;min-width:1.6em;text-align:right}
.friend .who{flex:1;min-width:0}
.friend .name{font-weight:bold;font-size:.95rem}
.friend .handle{font-size:.85rem}
.friend .handle a{color:#1d9bf0;text-decoration:none}
.friend .meta{font-size:.78rem;color:#888;margin-top:2px}
.badge{background:#ede7f6;color:#5e35b1;border-radius:12px;padding:2px 10px;font-size:.85rem;font-weight:bold;white-space:nowrap}
.friend button{padding:6px 10px;font-size:.85rem}
</style></head><body>
<h1>👥 常連さん <a href="/live" style="font-size:.8rem;float:right;color:#888">← 観戦モード</a></h1>
<p class="note">リプをくれた人は自動でこの下の<b>候補</b>に入ります (ページを開くたび新着を取得)。✔で常連へ、✕は消す (もう出ない)、🚫はヤジ登録 (恒久除外・リプ案も作らない)。リプ返しを投稿した相手は自動で常連になります。</p>
<div id="cand-head" style="margin-top:10px;font-size:.9rem;color:#5e35b1;font-weight:bold"></div>
<div id="cands"></div>
<input type="text" id="who" placeholder="➕ 手動追加: 過去リプのURL または @ハンドル名 (空白区切りで複数可)" style="margin-top:12px">
<div class="row">
<button onclick="addFriend()" style="background:#e8eaf6;flex:1">➕ 常連に追加</button>
<button onclick="load()" style="background:#eee;flex:1">🔄 更新</button>
</div>
<div id="status"></div>
<div id="list"></div>
<script>
function candRow(f){
  const div=document.createElement('div'); div.className='friend';
  div.style.borderColor='#b39ddb';
  div.innerHTML='<span class="who"><span class="name"></span>'+
    '<span class="handle"> <a target="_blank" rel="noopener"></a></span>'+
    '<div class="meta"></div></span>';
  div.querySelector('.name').textContent=(f.yaji_hint?'⚠ ':'')+(f.name||'(名前未取得)');
  const a=div.querySelector('.handle a');
  a.textContent='@'+f.handle; a.href=f.url||('https://x.com/'+encodeURIComponent(f.handle));
  div.querySelector('.meta').textContent='「'+(f.text||'')+'」'+(f.yaji_hint?' ← ヤジっぽい語あり':'');
  const keep=document.createElement('button');
  keep.textContent='✔'; keep.title='常連にする'; keep.style.background='#e8f5e9';
  keep.onclick=async()=>{ await fetch('/live-friend-flag?mode=keep&handle='+encodeURIComponent(f.handle)); div.remove(); load(); };
  const del=document.createElement('button');
  del.textContent='✕'; del.title='消す (もう表示しない)'; del.style.background='#eee';
  del.onclick=async()=>{ await fetch('/live-friend-flag?mode=dismiss&handle='+encodeURIComponent(f.handle)); div.remove(); };
  const ng=document.createElement('button');
  ng.textContent='🚫'; ng.title='ヤジ登録 (恒久除外)'; ng.style.background='#ffebee';
  ng.onclick=async()=>{ if(!confirm('@'+f.handle+' をヤジ登録 (恒久除外) する？')) return; await fetch('/live-friend-flag?handle='+encodeURIComponent(f.handle)); div.remove(); };
  div.appendChild(keep); div.appendChild(del); div.appendChild(ng);
  return div;
}
async function loadCands(){
  const head=document.getElementById('cand-head');
  head.textContent='📥 新着リプを確認中…';
  try{
    const r = await fetch('/live-friend-candidates');
    if(r.status===403){ head.textContent=''; return; }
    const j = await r.json();
    const box=document.getElementById('cands'); box.innerHTML='';
    if(!j.ok || !j.candidates || !j.candidates.length){ head.textContent='📥 新しいリプ相手はいません'; return; }
    head.textContent='📥 リプをくれた人 (候補 '+j.candidates.length+'人'+(j.new?'・新着'+j.new:'')+')';
    for(const f of j.candidates){ box.appendChild(candRow(f)); }
  }catch(e){ head.textContent='候補取得エラー: '+e; }
}
async function load(){
  document.getElementById('status').textContent='常連リストを取得中…';
  try{
    const r = await fetch('/live-friends?limit=200');
    if(r.status===403){ document.getElementById('status').textContent='認証切れです。トップページ ( / ) を token 付きで開き直してから戻ってきてください'; return; }
    const j = await r.json();
    const list=document.getElementById('list'); list.innerHTML='';
    if(!j.ok || !j.friends || !j.friends.length){ document.getElementById('status').textContent='常連はまだいません (リプ返しすると育ちます)'; return; }
    document.getElementById('status').textContent='👥 '+j.friends.length+'人 (リプ返し回数順)';
    j.friends.forEach((f, i)=>{
      const div=document.createElement('div'); div.className='friend';
      div.innerHTML='<span class="rank">'+(i+1)+'</span>'+
        '<span class="who"><span class="name"></span>'+
        '<span class="handle"> <a target="_blank" rel="noopener"></a></span>'+
        '<div class="meta"></div></span>'+
        '<span class="badge"></span>';
      div.querySelector('.name').textContent=f.name||'(名前未取得)';
      const a=div.querySelector('.handle a');
      a.textContent='@'+f.handle; a.href='https://x.com/'+encodeURIComponent(f.handle);
      div.querySelector('.meta').textContent='最終リプ返し: '+(f.last||'?');
      div.querySelector('.badge').textContent=(f.count||0)+'回';
      const del=document.createElement('button');
      del.textContent='✕'; del.title='リストから削除'; del.style.background='#eee';
      del.onclick=async()=>{ if(!confirm('@'+f.handle+' をリストから削除する？')) return; await fetch('/live-friend-flag?mode=remove&handle='+encodeURIComponent(f.handle)); div.remove(); };
      const ng=document.createElement('button');
      ng.textContent='🚫'; ng.title='ヤジ登録 (恒久除外)'; ng.style.background='#ffebee';
      ng.onclick=async()=>{ if(!confirm('@'+f.handle+' をヤジ登録 (恒久除外) する？')) return; await fetch('/live-friend-flag?handle='+encodeURIComponent(f.handle)); div.remove(); };
      div.appendChild(del); div.appendChild(ng);
      list.appendChild(div);
    });
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function addFriend(){
  const u = document.getElementById('who').value.trim();
  if(!u){ document.getElementById('status').textContent='過去リプのURLか @ハンドル名を貼ってください'; return; }
  document.getElementById('status').textContent='登録中…';
  try{
    const r = await fetch('/live-friend-add?who='+encodeURIComponent(u));
    const j = await r.json();
    if(!j.ok){
      const msgs={bad_who:'@ハンドル名かURLで入れてください (複数は空白区切り)'};
      document.getElementById('status').textContent = msgs[j.reason] || ('登録できず: '+(j.reason||''));
      return;
    }
    document.getElementById('who').value='';
    load();
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
load();
loadCands();
</script></body></html>"""


def _render_trend_page() -> str:
    """2026-07-16 user「フォロワーを増やすのに何かアプリ作れない？」。

    実測の当たり枠 = トレンド反応を、毎時 mail を待たずに即応で打つページ。
    急上昇ワード chips (巨人/MLB) → タップ → 記事接地つき反応ポスト生成 →
    その場で X 投稿。素材・gate は mail 便の trend_react と完全共用。
    """
    return """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>トレンド反応｜ヨシラバー</title>
<style>
body{font-family:sans-serif;background:#fafafa;margin:0;padding:12px;max-width:640px;margin:auto}
h1{font-size:1.1rem;color:#d84315}
button{font-size:1rem;padding:10px 16px;border:0;border-radius:8px;cursor:pointer}
.chip{display:inline-block;background:#fff;border:1px solid #ffab91;color:#d84315;border-radius:16px;padding:8px 14px;margin:4px 4px 0 0;font-size:.95rem}
.chip.mlb{border-color:#90caf9;color:#1565c0}
.chip small{color:#999;font-size:.7rem}
.grp{margin-top:12px;font-size:.85rem;color:#888;font-weight:bold}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px;margin-top:12px;white-space:pre-wrap}
.card .style{font-size:.8rem;color:#888}
.card .cnt{font-size:.75rem;color:#aaa}
.row{display:flex;gap:8px;margin-top:8px}
.post{background:#1d9bf0;color:#fff;flex:1}
.copy{background:#eee;flex:1}
#status{margin-top:10px;font-size:.9rem;color:#666}
.note{font-size:.75rem;color:#999;margin-top:6px}
textarea{width:100%;box-sizing:border-box;font-size:1.05rem;padding:10px;border:1px solid #ccc;border-radius:8px}
</style></head><body>
<h1>🔥 トレンド反応 — 急上昇に即乗る <a href="/" style="font-size:.8rem;float:right;color:#888">← 戻る</a></h1>
<p class="note">いま検索で急上昇中の野球ワード。タップすると記事を読んで反応ポストを作ります (事実は見出し+記事内のみ、捏造gateあり)。伸びてる語に早く乗るほどインプ・フォロワーに効きます。</p>
<div class="row">
<button onclick="loadWords()" style="background:#fbe9e7;flex:1">🔄 いまの急上昇を取得</button>
</div>
<div id="words"></div>
<div id="status"></div>
<div id="out"></div>
<script>
function makeCard(d, kw){
  const div=document.createElement('div'); div.className='card';
  div.innerHTML='<div class="style">'+d.style+' (編集して投稿できます)</div>'+
    '<textarea class="txt" style="margin-top:6px"></textarea>'+
    '<div class="cnt"></div>'+
    '<div class="row"><button class="post">Xに投稿</button><button class="regen" style="background:#fff3e0">🔄 再作成</button><button class="copy">コピー</button></div>';
  const ta=div.querySelector('.txt'), cnt=div.querySelector('.cnt');
  ta.value=d.text;
  const fit=()=>{cnt.textContent=ta.value.length+'字'; ta.style.height='auto'; ta.style.height=(ta.scrollHeight+4)+'px';};
  ta.oninput=fit;
  div.querySelector('.copy').onclick=()=>{navigator.clipboard.writeText(ta.value);div.querySelector('.copy').textContent='コピー済';};
  div.querySelector('.regen').onclick=()=>{draft(kw, div);};
  div.querySelector('.post').onclick=async(ev)=>{
    const text=ta.value.trim();
    if(!text) return;
    if(!confirm('この内容でXに投稿します:\\n\\n'+text.slice(0,120)+(text.length>120?'…':'')+'\\n\\nよい？')) return;
    ev.target.disabled=true; ev.target.textContent='投稿中…';
    const pr=await fetch('/x-post-direct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text})});
    const pj=await pr.json();
    ev.target.textContent=pj.ok?'投稿済✔':'失敗: '+(pj.reason||'');
    if(!pj.ok) ev.target.disabled=false;
  };
  setTimeout(fit,0);
  return div;
}
async function draft(kw, replaceCard){
  document.getElementById('status').textContent='「'+kw+'」の記事を読んで生成中… (数秒〜10秒)';
  try{
    const r = await fetch('/trend-draft?kw='+encodeURIComponent(kw));
    const j = await r.json();
    if(!j.ok){
      const msgs={no_article:'この語はニュース記事ソースが無く、安全に書けません (捏造防止)。別の語でどうぞ', unknown_kw:'一覧を更新してから選び直してください', generation_empty:'生成できず (gate落ち)。もう一度押すか別の語で'};
      document.getElementById('status').textContent = msgs[j.reason] || ('生成できず: '+(j.reason||''));
      return;
    }
    document.getElementById('status').textContent = j.news_title ? ('📰 '+j.news_title) : '';
    const card = makeCard(j.drafts[0], kw);
    const out=document.getElementById('out');
    if(replaceCard){ out.replaceChild(card, replaceCard); } else { out.prepend(card); }
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function loadWords(){
  document.getElementById('status').textContent='急上昇ワードを取得中…';
  try{
    const r = await fetch('/trend-words');
    if(r.status===403){ document.getElementById('status').textContent='認証切れです。トップ ( / ) を token 付きで開き直してください'; return; }
    const j = await r.json();
    const box=document.getElementById('words'); box.innerHTML='';
    if(!j.ok || !j.words || !j.words.length){ document.getElementById('status').textContent='いま野球系の急上昇ワードがありません (時間をおいてもう一度)'; return; }
    document.getElementById('status').textContent='タップで反応ポストを生成:';
    const groups=[['giants','🔥 巨人'],['mlb','🌍 MLB'],['npb','⚾ その他野球 (参考・生成対象外)']];
    for(const [cat,label] of groups){
      const ws=j.words.filter(w=>w.category===cat);
      if(!ws.length) continue;
      const g=document.createElement('div'); g.className='grp'; g.textContent=label;
      box.appendChild(g);
      for(const w of ws){
        const b=document.createElement('button');
        b.className='chip'+(cat==='mlb'?' mlb':'');
        b.innerHTML='';
        b.textContent=w.keyword+(w.traffic?' ':'');
        if(w.traffic){ const s=document.createElement('small'); s.textContent=w.traffic; b.appendChild(s); }
        if(cat==='npb'){ b.style.opacity=.45; b.onclick=()=>{document.getElementById('status').textContent='巨人/MLB以外のトレンドは生成対象外です (検索インプが他所に流れるだけ)';}; }
        else { b.onclick=()=>draft(w.keyword); }
        box.appendChild(b);
      }
    }
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
loadWords();
</script></body></html>"""


_ENGAGEMENT_BUCKET_DEFAULT = "baseballsite-yoshilover-state"


def _load_latest_engagement_report() -> dict[str, Any] | None:
    """x-engagement 週次レポート (GCS) の最新 1 本。無ければ None。"""
    try:
        from google.cloud import storage

        bucket_name = (
            os.environ.get("X_ENGAGEMENT_BUCKET") or _ENGAGEMENT_BUCKET_DEFAULT
        ).strip()
        bucket = storage.Client().bucket(bucket_name)
        blobs = sorted(
            bucket.list_blobs(prefix="x_engagement/reports/"), key=lambda b: b.name
        )
        if not blobs:
            return None
        return json.loads(blobs[-1].download_as_bytes().decode("utf-8"))
    except Exception:  # noqa: BLE001
        logging.getLogger("manual_intake_service").exception("engagement_report_failed")
        return None


def _engagement_best_rows(report: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    rows = [
        r
        for r in (report.get("rows") or [])
        if not r.get("is_reply") and r.get("metrics_fetched")
    ]
    rows.sort(key=lambda r: -int(r.get("favorite_count") or 0))
    return rows[:limit]


def _render_profile_page() -> str:
    """2026-07-16 user「両方」の転換側: 固定ポスト生成。

    週間ベストポスト (実測 fav) を見せつつ、自己紹介+実績+フォロー CTA の
    固定ポスト案を LLM で作る。投稿後の「プロフィールに固定」は X アプリ側で
    1 タップ (API Free では固定操作不可)。
    """
    return """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>固定ポスト｜ヨシラバー</title>
<style>
body{font-family:sans-serif;background:#fafafa;margin:0;padding:12px;max-width:640px;margin:auto}
h1{font-size:1.1rem;color:#6a1b9a}
button{font-size:1rem;padding:10px 16px;border:0;border-radius:8px;cursor:pointer}
.best{background:#fff;border:1px solid #ddd;border-radius:10px;padding:8px 12px;margin-top:6px;font-size:.85rem;color:#444}
.best .fav{color:#e91e63;font-weight:bold;margin-right:6px}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px;margin-top:12px;white-space:pre-wrap}
.card .style{font-size:.8rem;color:#888}
.card .cnt{font-size:.75rem;color:#aaa}
.row{display:flex;gap:8px;margin-top:8px}
.post{background:#1d9bf0;color:#fff;flex:1}
.copy{background:#eee;flex:1}
#status{margin-top:10px;font-size:.9rem;color:#666}
.note{font-size:.78rem;color:#999;margin-top:6px;line-height:1.5}
textarea{width:100%;box-sizing:border-box;font-size:1.05rem;padding:10px;border:1px solid #ccc;border-radius:8px}
.grp{margin-top:12px;font-size:.85rem;color:#888;font-weight:bold}
</style></head><body>
<h1>📌 固定ポスト <a href="/" style="font-size:.8rem;float:right;color:#888">← 戻る</a></h1>
<p class="note">開拓やトレンドで来た人がプロフィールを見た瞬間に「フォローする価値がある」と分かるための固定ポストを作ります。投稿したら X アプリで「…」→<b>プロフィールに固定</b>を押してください (そこだけ手動)。週1回、数字を更新して作り直すのがおすすめ。</p>
<div class="row">
<button onclick="gen()" style="background:#6a1b9a;color:#fff;flex:1;font-weight:bold">📌 固定ポスト案をつくる</button>
</div>
<div class="grp" id="best-head"></div>
<div id="best"></div>
<div id="status"></div>
<div id="out"></div>
<script>
async function loadBest(){
  try{
    const r = await fetch('/profile-best');
    if(r.status===403){ document.getElementById('status').textContent='認証切れです。トップ ( / ) を token 付きで開き直してください'; return; }
    const j = await r.json();
    if(!j.ok){ document.getElementById('best-head').textContent='週間データがまだありません'; return; }
    document.getElementById('best-head').textContent='📊 先週の実績 ('+j.period+'): '+j.total_posts+'ポスト / fav合計 '+j.total_favorites;
    const box=document.getElementById('best'); box.innerHTML='';
    for(const b of j.best){
      const div=document.createElement('div'); div.className='best';
      div.innerHTML='<span class="fav"></span><span class="txt"></span>';
      div.querySelector('.fav').textContent='♥'+b.favorite_count;
      div.querySelector('.txt').textContent=b.text_head;
      box.appendChild(div);
    }
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
async function gen(replaceCard){
  document.getElementById('status').textContent='実績データから固定ポスト案を生成中… (数秒)';
  try{
    const r = await fetch('/profile-draft');
    const j = await r.json();
    if(!j.ok){ document.getElementById('status').textContent='生成できず: '+(j.reason||'')+' (もう一度どうぞ)'; return; }
    document.getElementById('status').textContent='投稿後、Xアプリで「プロフィールに固定」を忘れずに:';
    const div=document.createElement('div'); div.className='card';
    div.innerHTML='<div class="style">📌 固定ポスト案 (編集して投稿できます)</div>'+
      '<textarea class="txt" style="margin-top:6px"></textarea>'+
      '<div class="cnt"></div>'+
      '<div class="row"><button class="post">Xに投稿</button><button class="regen" style="background:#fff3e0">🔄 再作成</button><button class="copy">コピー</button></div>';
    const ta=div.querySelector('.txt'), cnt=div.querySelector('.cnt');
    ta.value=j.drafts[0].text;
    const fit=()=>{cnt.textContent=ta.value.length+'字'; ta.style.height='auto'; ta.style.height=(ta.scrollHeight+4)+'px';};
    ta.oninput=fit;
    div.querySelector('.copy').onclick=()=>{navigator.clipboard.writeText(ta.value);div.querySelector('.copy').textContent='コピー済';};
    div.querySelector('.regen').onclick=()=>{gen(div);};
    div.querySelector('.post').onclick=async(ev)=>{
      const text=ta.value.trim();
      if(!text) return;
      if(!confirm('この内容でXに投稿します:\\n\\n'+text.slice(0,120)+(text.length>120?'…':'')+'\\n\\nよい？')) return;
      ev.target.disabled=true; ev.target.textContent='投稿中…';
      const pr=await fetch('/x-post-direct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text})});
      const pj=await pr.json();
      ev.target.textContent=pj.ok?'投稿済✔ → Xアプリで固定を':'失敗: '+(pj.reason||'');
      if(!pj.ok) ev.target.disabled=false;
    };
    const out=document.getElementById('out');
    if(replaceCard){ out.replaceChild(div, replaceCard); } else { out.prepend(div); }
    setTimeout(fit,0);
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
loadBest();
</script></body></html>"""


def _render_scout_page() -> str:
    """2026-07-16 user「フォロワーを増やしたいアプリ」(開拓+転換の両方 GO)。

    公式アカに今リプしている活発なファン = フォロバ期待層 を自動リストアップ。
    行をタップ → X プロフィールが開く → フォローボタンを押すだけ。
    ✔フォローした / ✕スキップ で台帳に記録し、同じ人は二度出ない。
    """
    return """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>フォロー開拓｜ヨシラバー</title>
<style>
body{font-family:sans-serif;background:#fafafa;margin:0;padding:12px;max-width:640px;margin:auto}
h1{font-size:1.1rem;color:#00695c}
button{font-size:1rem;padding:10px 14px;border:0;border-radius:8px;cursor:pointer}
#status{margin-top:10px;font-size:.9rem;color:#666}
.note{font-size:.78rem;color:#999;margin-top:6px;line-height:1.5}
.cand{background:#fff;border:1px solid #ddd;border-radius:10px;padding:10px 12px;margin-top:8px;display:flex;align-items:center;gap:10px}
.cand .who{flex:1;min-width:0}
.cand .handle a{color:#1d9bf0;text-decoration:none;font-weight:bold}
.cand .origin{font-size:.72rem;color:#00695c;background:#e0f2f1;border-radius:8px;padding:1px 8px}
.cand .meta{font-size:.8rem;color:#888;margin-top:3px;overflow:hidden}
.cand button{padding:6px 10px;font-size:.85rem}
.stats{font-size:.85rem;color:#00695c;margin-top:8px;font-weight:bold}
</style></head><body>
<h1>🎯 フォロー開拓 <a href="/" style="font-size:.8rem;float:right;color:#888">← 戻る</a></h1>
<p class="note"><b>直近30分以内</b>に公式アカへリプした<b>活発なファン</b> = 今Xを開いていてフォロバが期待できる層です。<b>@名をタップ → プロフィールが開き、その場でフォロー済みとして消えます</b> (フォローしなかったら「戻す」)。✕は以後表示しない。1日10〜20人ペースが安全圏 (一気にやりすぎると制限を踏みます)。</p>
<div style="display:flex;gap:8px;margin-top:8px">
<button onclick="load()" style="background:#e0f2f1;flex:1">🔄 候補を取得</button>
</div>
<div class="stats" id="stats"></div>
<div id="status"></div>
<div id="list"></div>
<script>
function bumpStats(d){
  const s=document.getElementById('stats');
  const n=Math.max(0, parseInt((s.textContent.match(/\\d+/)||[0])[0])+d);
  s.textContent='✔フォロー済 累計 '+n+'人';
}
async function markFollowed(handle, div){
  await fetch('/scout-mark?mode=followed&handle='+encodeURIComponent(handle));
  bumpStats(1);
  const undo=document.createElement('div');
  undo.style.cssText='background:#f1f8e9;border:1px dashed #aed581;border-radius:10px;padding:8px 12px;margin-top:8px;font-size:.85rem;color:#558b2f;display:flex;align-items:center;gap:8px';
  const label=document.createElement('span');
  label.style.flex='1'; label.textContent='✔ @'+handle+' をフォロー済みに記録しました';
  const back=document.createElement('button');
  back.textContent='戻す'; back.style.cssText='background:#eee;padding:4px 12px;font-size:.85rem';
  back.onclick=async()=>{ await fetch('/scout-mark?mode=undo&handle='+encodeURIComponent(handle)); bumpStats(-1); undo.replaceWith(div); };
  undo.appendChild(label); undo.appendChild(back);
  div.replaceWith(undo);
  setTimeout(()=>{ if(undo.parentNode) undo.remove(); }, 20000);
}
async function load(){
  document.getElementById('status').textContent='公式アカへの最近のリプ主を収集中… (数秒)';
  try{
    const r = await fetch('/scout-candidates');
    if(r.status===403){ document.getElementById('status').textContent='認証切れです。トップ ( / ) を token 付きで開き直してください'; return; }
    const j = await r.json();
    const list=document.getElementById('list'); list.innerHTML='';
    document.getElementById('stats').textContent = '✔フォロー済 累計 '+(j.followed_total||0)+'人';
    if(!j.ok || !j.candidates || !j.candidates.length){ document.getElementById('status').textContent='直近30分のリプ主がいません (試合中・試合後に開くとよく取れます)'; return; }
    document.getElementById('status').textContent='候補 '+j.candidates.length+'人:';
    for(const c of j.candidates){
      const div=document.createElement('div'); div.className='cand';
      div.innerHTML='<span class="who"><span class="handle"><a target="_blank" rel="noopener"></a></span>'+
        ' <span class="origin"></span><div class="meta"></div></span>';
      const a=div.querySelector('.handle a');
      a.textContent='@'+c.handle; a.href='https://x.com/'+encodeURIComponent(c.handle);
      const age = (c.age_min>=0) ? (c.age_min<60 ? c.age_min+'分前' : Math.floor(c.age_min/60)+'時間前') : '';
      div.querySelector('.origin').textContent=(c.origin||'')+(age?(' ・'+age):'');
      div.querySelector('.meta').textContent='「'+(c.text||'')+'」';
      // タップ = プロフィールを開く + フォロー済み記録 (行は「戻す」に変わる)
      a.onclick=()=>{ markFollowed(c.handle, div); };
      const ng=document.createElement('button');
      ng.textContent='✕'; ng.title='スキップ (以後表示しない)'; ng.style.background='#eee';
      ng.onclick=async()=>{ await fetch('/scout-mark?mode=skip&handle='+encodeURIComponent(c.handle)); div.remove(); };
      div.appendChild(ng);
      list.appendChild(div);
    }
  }catch(e){ document.getElementById('status').textContent='エラー: '+e; }
}
load();
</script></body></html>"""


def _render_form() -> str:
    options: list[str] = []
    for value in mi.ARTICLE_TYPE_CHOICES:
        label = "自動判定 (auto)" if value == mi.ARTICLE_TYPE_AUTO else value
        options.append(
            f'<option value="{value}">{label}</option>'
        )
    source_options = ['<option value="">すべて（上位ソースから取得）</option>']
    for source in _load_manual_source_sources():
        name = str(source.get("name") or "").strip()
        source_type = str(source.get("type") or "").strip()
        if not name:
            continue
        source_options.append(
            '<option value="{value}">{label}</option>'.format(
                value=html.escape(name, quote=True),
                label=html.escape(f"{name} / {source_type}", quote=False),
            )
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
    from src.analysis import insight_whitelist as wl

    metric_options = ['<option value="">— 指標を選択 —</option>']
    for met in miq.metric_options():
        metric_options.append(f'<option value="{met}">{wl.metric_name_ja(met)}</option>')
    position_options = ['<option value="">— 全ポジション (打撃/投球指標は不問) —</option>']
    for pos in miq.position_options():
        position_options.append(f'<option value="{pos}">{pos}</option>')
    return (
        _HTML_FORM
        .replace("__ARTICLE_TYPE_OPTIONS__", "".join(options))
        .replace("__SOURCE_OPTIONS__", "".join(source_options))
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
    if mode not in {"dry-run", "draft", "publish"}:
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
    # ticket 417: optional Markdown table input. Renderer converts to a
    # Gutenberg <!-- wp:table --> block when non-empty / well-formed,
    # otherwise skips silently (no regression).
    table_markdown = (payload.get("table_markdown") or "").strip()

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
        table_markdown=table_markdown,
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
            if path == "/source-candidates":
                if not _is_authorized_get(self, parsed):
                    _json_response(self, 403, {"ok": False, "reason": "forbidden"})
                    return
                params = parse_qs(parsed.query, keep_blank_values=False)
                source_name = (params.get("source") or [""])[0].strip()
                try:
                    limit = int((params.get("limit") or [str(SOURCE_CANDIDATE_TOTAL_LIMIT)])[0])
                except ValueError:
                    limit = SOURCE_CANDIDATE_TOTAL_LIMIT
                limit = max(1, min(limit, SOURCE_CANDIDATE_TOTAL_LIMIT))
                try:
                    payload = _source_candidates_payload(
                        source_name=source_name,
                        limit=limit,
                        logger=bound_logger,
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("source_candidates_failed")
                    _json_response(
                        self,
                        500,
                        {"ok": False, "reason": f"source_candidates_error:{exc!r}"},
                    )
                    return
                _json_response(self, 200, payload)
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
            if path == "/live-fuga":
                # 2026-07-15 user「キーワード入れたらポストが出てくる手動アプリ」:
                # 観戦中の場面キーワード (q) → ヨシラバー voice 2案 (試合中帯は
                # ライブ短文 + フーガ長文)。Gemini は打鍵時のみ消費 (scheduler 無し)。
                # auth は /x-post-draft と同じ cookie / query token。
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
                scene = ((params.get("q") or [""])[0] or "").strip()
                player = ((params.get("player") or [""])[0] or "").strip()
                if not scene:
                    _json_response(self, 400, {"ok": False, "reason": "empty_scene"})
                    return
                api_key = (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                    or ""
                ).strip()
                if not api_key:
                    _json_response(self, 500, {"ok": False, "reason": "gemini_key_missing"})
                    return
                try:
                    from src import x_post_branding_gen as _bgen
                    from src.live_game_watch import find_unsupported_claim as _claim_gate

                    # voice 上乗せと局所claim語は module-level 共通定義を使う
                    # (_LIVE_VOICE_NOTE / _LIVE_LOCAL_CLAIM_WORDS、ネタ便と共用)。
                    _live_note = _LIVE_VOICE_NOTE
                    # 2026-07-15 user「ひとつでよくないか？再作成が良いのでは。短文と長文で」:
                    # 1押し = 1案 (style param で短文/長文を選択、LLM 1call)。気に入らなければ
                    # UI の再作成ボタンで同 style をもう 1 call。2案同時生成は廃止 (LLM半減)。
                    style_param = ((params.get("style") or ["short"])[0] or "short").strip()
                    _force_long = style_param == "long"
                    _style = "フーガ長文" if _force_long else "ライブ短文"
                    # 2026-07-15 user「ミックスがよいのでは」: user の一言 (現場の真実) に
                    # 一球速報の検証済み現況 (スコア/回/相手) を混ぜる。LLM の記憶ではなく
                    # source 裏付きの事実だけを注入するので hallucination 対策と両立する。
                    # 取得失敗 / 試合前 / 試合なし → 従来どおり入力のみ (fail-open)。
                    live_ctx = ""
                    try:
                        from src import live_game_watch as _lgw

                        _st = _lgw.fetch_today_live_game()
                        if _st is not None and _st.status in ("試合中", "試合終了"):
                            _inn = f" {_st.inning_label}" if _st.inning_label else ""
                            live_ctx = (
                                f"{_st.status}{_inn} 巨人{_st.giants_score}-"
                                f"{_st.opp_score}{_st.opp_name}"
                            )
                            # 2026-07-16 user「リアルタイムが欲しい」: スコアだけでなく
                            # 一球速報の直近プレーも検証済み事実として注入する
                            # (短文/長文とも)。取れなければスコアのみ (fail-open)。
                            try:
                                _plays = _lgw.apply_fullname_map(
                                    _lgw.fetch_today_plays(),
                                    _lgw.giants_fullname_map(),
                                )
                                _recent = [
                                    ln
                                    for ln in (
                                        _fmt_live_play(p) for p in _plays[-2:]
                                    )
                                    if ln
                                ]
                                if _recent:
                                    live_ctx += " / 直近プレー: " + "、".join(_recent)
                            except Exception:  # noqa: BLE001
                                bound_logger.exception("live_fuga_recent_plays_failed")
                    except Exception:  # noqa: BLE001
                        bound_logger.exception("live_fuga_live_state_failed")
                        live_ctx = ""
                    scene_for_gen = (
                        f"{scene}\n【現況・一球速報より検証済み】{live_ctx}"
                        if live_ctx
                        else scene
                    )
                    # hallucination gate (7/10 観戦便の claim語gate + 手動観戦特有の創作細部)。
                    # 2026-07-15 実演で「初球から」「追い込まれてから」の矛盾創作を実測。
                    _local_claim_words = _LIVE_LOCAL_CLAIM_WORDS
                    txt = ""
                    for _attempt in range(2):  # gate落ち時のみ 1 回だけ作り直し
                        try:
                            txt = (
                                _bgen.build_quote_rt_comment(
                                    scene_for_gen,
                                    player,
                                    gemini_api_key=api_key,
                                    subject="観戦LIVE手動",
                                    budget_site="quote_rt",
                                    require_db_fact=False,
                                    force_long=_force_long,
                                    extra_voice_note=_live_note,
                                )
                                or ""
                            ).strip()
                        except Exception:  # noqa: BLE001
                            bound_logger.exception("live_fuga_variant_failed")
                            txt = ""
                        if not txt:
                            break
                        bad_word = _claim_gate(txt, scene_for_gen) or next(
                            (
                                w
                                for w in _local_claim_words
                                if w in txt and w not in scene_for_gen
                            ),
                            "",
                        )
                        if not bad_word:
                            break
                        bound_logger.info(
                            "live_fuga_claim_gate_drop style=%s word=%s attempt=%d",
                            _style,
                            bad_word,
                            _attempt + 1,
                        )
                        txt = ""
                    if not txt:
                        _json_response(self, 200, {"ok": False, "reason": "generation_empty"})
                        return
                    _json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "scene": scene,
                            "live_context": live_ctx,
                            "drafts": [{"style": _style, "text": txt}],
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("live_fuga_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"live_fuga_error:{exc!r}"})
                return
            if path == "/live-plays":
                # 2026-07-15 user「リアルタイム拾えない？」: 一球速報の直近プレーを
                # タップ可能な候補として返す (typing 不要化)。LLM は使わない (¥0)。
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
                try:
                    from src import live_game_watch as _lgw

                    plays = _lgw.apply_fullname_map(
                        _lgw.fetch_today_plays(), _lgw.giants_fullname_map()
                    )
                    items = [
                        line
                        for line in (_fmt_live_play(p) for p in plays[-10:])
                        if line
                    ]
                    items.reverse()  # 新しいプレーを先頭に
                    _json_response(self, 200, {"ok": True, "plays": items})
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("live_plays_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"live_plays_error:{exc!r}"})
                return
            if path == "/live-friends":
                # 常連リスト閲覧 (read-only、LLM/課金なし)
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
                try:
                    limit = int((params.get("limit") or ["30"])[0])
                except ValueError:
                    limit = 30
                limit = max(1, min(limit, 200))
                friends = _load_friends()
                ranked = sorted(
                    (
                        {"handle": h, **(v or {})}
                        for h, v in friends.items()
                        # ヤジ=恒久除外 / candidate=候補欄 / dismissed=非表示
                        if not (v or {}).get("yaji")
                        and not (v or {}).get("candidate")
                        and not (v or {}).get("dismissed")
                    ),
                    key=lambda x: -int(x.get("count") or 0),
                )[:limit]
                _json_response(self, 200, {"ok": True, "friends": ranked})
                return
            if path == "/live-friend-candidates":
                # 2026-07-16: 自分宛リプの自動取り込み + 候補一覧 (LLMなし・¥0)
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
                new_count = _collect_reply_candidates()
                friends = _load_friends()
                candidates = sorted(
                    (
                        {"handle": h, **(v or {})}
                        for h, v in friends.items()
                        if (v or {}).get("candidate")
                        and not (v or {}).get("yaji")
                        and not (v or {}).get("dismissed")
                    ),
                    key=lambda x: str(x.get("last") or ""),
                    reverse=True,
                )[:50]
                _json_response(
                    self,
                    200,
                    {"ok": True, "new": new_count, "candidates": candidates},
                )
                return
            if path == "/live-friend-add":
                # 2026-07-15 user「既にリプくれた人は入れたい」: 過去リプの URL または
                # @handle を貼るだけで常連リストへ登録 (投稿なし・LLMなし・¥0)。
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
                who_raw = ((params.get("who") or [""])[0] or "").strip()
                # 2026-07-15 user「1件ずつはきつい」: 空白/カンマ/改行区切りの
                # まとめ貼り対応 (@handle と URL 混在可、最大20件)。
                tokens = [t for t in re.split(r"[\s,、]+", who_raw) if t][:20]
                friends = _load_friends()
                added: list[dict[str, Any]] = []
                skipped: list[str] = []
                for tok in tokens:
                    handle, name = "", ""
                    tweet_id = _extract_tweet_id(tok)
                    if tweet_id:
                        tw = _fetch_tweet_syndication(tweet_id)
                        handle, name = tw.get("handle", ""), tw.get("name", "")
                    elif re.fullmatch(r"@?\w{1,15}", tok):
                        handle = tok.lstrip("@")
                    if not handle or (friends.get(handle) or {}).get("yaji"):
                        skipped.append(tok)
                        continue
                    count = _bump_friend(handle, name)
                    added.append({"handle": handle, "name": name, "count": count})
                if not added:
                    _json_response(
                        self, 400, {"ok": False, "reason": "bad_who", "skipped": skipped}
                    )
                    return
                _json_response(
                    self,
                    200,
                    {"ok": True, "added": added, "skipped": skipped},
                )
                return
            if path == "/live-friend-flag":
                # 🚫ヤジ登録 (常連対象外へ恒久マーク)
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
                handle = ((params.get("handle") or [""])[0] or "").strip()
                mode = ((params.get("mode") or ["yaji"])[0] or "yaji").strip()
                if mode == "remove":
                    ok = _remove_friend(handle)
                elif mode in ("dismiss", "keep"):
                    ok = _set_friend_flags(handle, mode=mode)
                else:
                    ok = _flag_friend_yaji(handle)
                _json_response(
                    self, 200 if ok else 400, {"ok": ok, "handle": handle.lstrip("@")}
                )
                return
            if path == "/live-reply-draft":
                # 2026-07-15 user「リプが来た人に私がリプを作る。特に試合中」:
                # 相手リプの URL を貼る → syndication で本文/作者取得 (¥0) →
                # 共感型リプ返し文案を生成 → /x-post-direct (in_reply_to) で返信投稿。
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
                turl = ((params.get("url") or [""])[0] or "").strip()
                tweet_id = _extract_tweet_id(turl)
                if not tweet_id:
                    _json_response(self, 400, {"ok": False, "reason": "bad_tweet_url"})
                    return
                tw = _fetch_tweet_syndication(tweet_id)
                if not tw.get("text"):
                    _json_response(self, 200, {"ok": False, "reason": "tweet_fetch_failed"})
                    return
                # ヤジ gate: 認定済み or 侮辱・煽り語入りは文案を作らない (返すと燃える)
                if (_load_friends().get(tw.get("handle", "")) or {}).get("yaji"):
                    _json_response(
                        self,
                        200,
                        {
                            "ok": False,
                            "reason": "yaji_flagged",
                            "handle": tw.get("handle", ""),
                            "name": tw.get("name", ""),
                        },
                    )
                    return
                if _looks_like_yaji(tw["text"]):
                    _json_response(
                        self,
                        200,
                        {
                            "ok": False,
                            "reason": "yaji_suspected",
                            "handle": tw.get("handle", ""),
                            "name": tw.get("name", ""),
                            "their_text": tw["text"],
                        },
                    )
                    return
                api_key = (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                    or ""
                ).strip()
                if not api_key:
                    _json_response(self, 500, {"ok": False, "reason": "gemini_key_missing"})
                    return
                try:
                    from src import x_post_branding_gen as _bgen
                    from src.live_game_watch import find_unsupported_claim as _cg

                    # 試合中なら現況を混ぜる (検証済み事実のみ)
                    live_ctx = ""
                    try:
                        from src import live_game_watch as _lgw

                        _st = _lgw.fetch_today_live_game()
                        if _st is not None and _st.status in ("試合中", "試合終了"):
                            _inn = f" {_st.inning_label}" if _st.inning_label else ""
                            live_ctx = (
                                f"{_st.status}{_inn} 巨人{_st.giants_score}-"
                                f"{_st.opp_score}{_st.opp_name}"
                            )
                    except Exception:  # noqa: BLE001
                        live_ctx = ""
                    src_text = tw["text"]
                    fact_for_gate = (
                        f"{src_text}\n【現況】{live_ctx}" if live_ctx else src_text
                    )
                    _reply_note = (
                        "型=リプ返し (返礼)。相手はこちらのポストに反応してくれた巨人ファン。"
                        "共感と感謝ベースで短く (15〜45字・1文)、相手の文面の具体に必ず触れる。"
                        "上から目線・講釈・訂正・データ披露は禁止。仲間との野球談義のノリで、"
                        "絵文字は多くて1個。締めは相手がもう一言返しやすい軽い問いかけか同意。"
                    )
                    txt = ""
                    for _attempt in range(2):
                        try:
                            txt = (
                                _bgen.build_quote_rt_comment(
                                    fact_for_gate,
                                    "",
                                    gemini_api_key=api_key,
                                    subject="リプ返し手動",
                                    budget_site="reply",
                                    reply_style="empathy",
                                    require_db_fact=False,
                                    extra_voice_note=_reply_note,
                                )
                                or ""
                            ).strip()
                        except Exception:  # noqa: BLE001
                            bound_logger.exception("live_reply_gen_failed")
                            txt = ""
                        if not txt:
                            break
                        bad_word = _cg(txt, fact_for_gate)
                        if not bad_word:
                            break
                        bound_logger.info(
                            "live_reply_claim_gate_drop word=%s attempt=%d",
                            bad_word,
                            _attempt + 1,
                        )
                        txt = ""
                    if not txt:
                        _json_response(self, 200, {"ok": False, "reason": "generation_empty"})
                        return
                    friends = _load_friends()
                    fc = int((friends.get(tw["handle"]) or {}).get("count") or 0)
                    _json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "reply_to_id": tweet_id,
                            "handle": tw["handle"],
                            "name": tw["name"],
                            "their_text": src_text,
                            "friend_count": fc,
                            "live_context": live_ctx,
                            "drafts": [{"style": "💬 リプ返し", "text": txt}],
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("live_reply_draft_failed")
                    _json_response(
                        self, 500, {"ok": False, "reason": f"live_reply_error:{exc!r}"}
                    )
                return
            if path == "/live-neta":
                # 2026-07-15 user GO「良いね。リアルタイムで拾って」: ネタボタン便。
                # 一球速報のリアルタイム状態 (スコア/回/直近プレー/継投) を事実行に組み、
                # kind 別の型 (期待/采配/経過/劣勢/くじ) で 1 案生成。捏造 gate は共通。
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
                kind = ((params.get("kind") or [""])[0] or "").strip()
                spec = _LIVE_NETA_KINDS.get(kind)
                if spec is None:
                    _json_response(self, 400, {"ok": False, "reason": "unknown_kind"})
                    return
                api_key = (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                    or ""
                ).strip()
                if not api_key:
                    _json_response(self, 500, {"ok": False, "reason": "gemini_key_missing"})
                    return
                try:
                    from src import live_game_watch as _lgw
                    from src import x_post_branding_gen as _bgen

                    st = _lgw.fetch_today_live_game()
                    if st is None or st.status == "試合前":
                        _json_response(self, 200, {"ok": False, "reason": "no_live_game"})
                        return
                    plays = _lgw.apply_fullname_map(
                        _lgw.fetch_today_plays(), _lgw.giants_fullname_map()
                    )
                    _inn = f" {st.inning_label}" if st.inning_label else ""
                    fact_parts = [
                        f"{st.status}{_inn} 巨人{st.giants_score}-{st.opp_score}{st.opp_name}"
                    ]
                    recent = [
                        line
                        for line in (_fmt_live_play(p) for p in plays[-3:])
                        if line
                    ]
                    if recent:
                        fact_parts.append("直近: " + " / ".join(recent))
                    if kind == "saihai":
                        prev_p, cur_p = _recent_giants_pitching_change(plays)
                        if not cur_p:
                            _json_response(
                                self, 200, {"ok": False, "reason": "no_recent_change"}
                            )
                            return
                        fact_parts.append(f"巨人の継投: {prev_p}から{cur_p}へ交代")
                    if kind == "makeso" and st.giants_score >= st.opp_score:
                        _json_response(self, 200, {"ok": False, "reason": "not_losing"})
                        return
                    if kind == "keika" and st.homer_lines:
                        fact_parts.append("ここまでの本塁打: " + " / ".join(st.homer_lines[:4]))
                    fact = "。".join(fact_parts)
                    txt = ""
                    for _attempt in range(2):
                        try:
                            txt = (
                                _bgen.build_quote_rt_comment(
                                    fact,
                                    "",
                                    gemini_api_key=api_key,
                                    subject="観戦LIVE手動",
                                    budget_site="quote_rt",
                                    require_db_fact=False,
                                    force_long=False,
                                    extra_voice_note=_LIVE_VOICE_NOTE + spec["note"],
                                )
                                or ""
                            ).strip()
                        except Exception:  # noqa: BLE001
                            bound_logger.exception("live_neta_gen_failed")
                            txt = ""
                        if not txt:
                            break
                        from src.live_game_watch import find_unsupported_claim as _cg

                        bad_word = _cg(txt, fact) or next(
                            (
                                w
                                for w in _LIVE_LOCAL_CLAIM_WORDS
                                if w in txt and w not in fact
                            ),
                            "",
                        )
                        if not bad_word:
                            break
                        bound_logger.info(
                            "live_neta_claim_gate_drop kind=%s word=%s attempt=%d",
                            kind,
                            bad_word,
                            _attempt + 1,
                        )
                        txt = ""
                    if not txt:
                        _json_response(self, 200, {"ok": False, "reason": "generation_empty"})
                        return
                    _json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "live_context": fact,
                            "drafts": [{"style": spec["label"], "text": txt}],
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("live_neta_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"live_neta_error:{exc!r}"})
                return
            if path == "/live-recap":
                # 2026-07-15 user「今日活躍した選手でうさほーやグータッチのポスト」:
                # 試合終了後、一球速報から活躍選手を実名で束ねた recap を on-demand 生成。
                # 自動観戦便の game_end recap と同じ材料 (build_recap_fact + claim語gate)。
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
                api_key = (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                    or ""
                ).strip()
                if not api_key:
                    _json_response(self, 500, {"ok": False, "reason": "gemini_key_missing"})
                    return
                try:
                    from src import live_game_watch as _lgw
                    from src import x_post_branding_gen as _bgen

                    st = _lgw.fetch_today_live_game()
                    if st is None or st.status != "試合終了":
                        _json_response(
                            self,
                            200,
                            {"ok": False, "reason": "game_not_finished"},
                        )
                        return
                    plays = _lgw.apply_fullname_map(
                        _lgw.fetch_today_plays(), _lgw.giants_fullname_map()
                    )
                    fact = _lgw.build_recap_fact(
                        plays, st.giants_score, st.opp_score, st.opp_name
                    )
                    txt = ""
                    for _attempt in range(2):
                        try:
                            txt = (
                                # 2026-07-16 user「まとめも他と同じくらいの長さでいい」:
                                # force_long を外し、ライブ短文と同じ長さ帯にする。
                                _bgen.build_quote_rt_comment(
                                    fact,
                                    "",
                                    gemini_api_key=api_key,
                                    subject="観戦recap手動",
                                    budget_site="quote_rt",
                                    require_db_fact=False,
                                    force_long=False,
                                )
                                or ""
                            ).strip()
                        except Exception:  # noqa: BLE001
                            bound_logger.exception("live_recap_gen_failed")
                            txt = ""
                        if not txt:
                            break
                        bad = _lgw.find_unsupported_claim(txt, fact)
                        if not bad:
                            break
                        bound_logger.info(
                            "live_recap_claim_gate_drop word=%s attempt=%d",
                            bad,
                            _attempt + 1,
                        )
                        txt = ""
                    if not txt:
                        _json_response(self, 200, {"ok": False, "reason": "generation_empty"})
                        return
                    if st.giants_score > st.opp_score:
                        txt = "うさほー🐰👊 グータッチ！\n\n" + txt
                    elif st.giants_score < st.opp_score:
                        txt = "まけほー🐰\n\n" + txt
                    _json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "live_context": fact,
                            "drafts": [{"style": "🐰 試合後recap", "text": txt}],
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("live_recap_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"live_recap_error:{exc!r}"})
                return
            if path == "/live":
                _text_response(
                    self, 200, _render_live_page(), content_type="text/html; charset=utf-8"
                )
                return
            if path == "/friends":
                _text_response(
                    self, 200, _render_friends_page(), content_type="text/html; charset=utf-8"
                )
                return
            if path == "/trend":
                _text_response(
                    self, 200, _render_trend_page(), content_type="text/html; charset=utf-8"
                )
                return
            if path == "/scout":
                _text_response(
                    self, 200, _render_scout_page(), content_type="text/html; charset=utf-8"
                )
                return
            if path == "/profile":
                _text_response(
                    self, 200, _render_profile_page(), content_type="text/html; charset=utf-8"
                )
                return
            if path in ("/profile-best", "/profile-draft"):
                # 📌固定ポスト (2026-07-16)。best=¥0、draft=LLM 1call
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
                report = _load_latest_engagement_report()
                if report is None:
                    _json_response(self, 200, {"ok": False, "reason": "no_report"})
                    return
                best = _engagement_best_rows(report)
                if path == "/profile-best":
                    _json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "period": f"{report.get('period_start_jst')}〜{report.get('period_end_jst')}",
                            "total_posts": report.get("total_posts") or 0,
                            "total_favorites": report.get("total_favorites") or 0,
                            "best": [
                                {
                                    "favorite_count": b.get("favorite_count") or 0,
                                    "text_head": (b.get("text_head") or "")[:80],
                                }
                                for b in best
                            ],
                        },
                    )
                    return
                api_key = (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                    or ""
                ).strip()
                if not api_key:
                    _json_response(self, 500, {"ok": False, "reason": "gemini_key_missing"})
                    return
                try:
                    from src import x_post_branding_gen as _bgen

                    best_lines = "\n".join(
                        f"- ♥{b.get('favorite_count')}: {(b.get('text_head') or '')[:70]}"
                        for b in best[:3]
                    )
                    fact = (
                        "ヨシラバー (@yoshilover6760) の先週実績: "
                        f"{report.get('total_posts')}ポスト / fav合計 {report.get('total_favorites')}。\n"
                        f"先週特に反響が大きかったポスト:\n{best_lines}"
                    )
                    txt = (
                        _bgen.build_quote_rt_comment(
                            fact,
                            "",
                            gemini_api_key=api_key,
                            subject="プロフィール固定ポスト",
                            budget_site="quote_rt",
                            require_db_fact=False,
                            force_long=False,
                            extra_voice_note=(
                                "X プロフィールの固定ポストを書く。目的 = プロフィール"
                                "に来た人にフォローさせること。構成 (2026-07-16 user 型): "
                                "①前半 = フォローすると何が流れてくるか (巨人の試合実況・"
                                "毎時の話題選手ランキング・データで見る深掘り分析・MLB速報) "
                                "を具体的に ②実績数字を1つだけ自然に入れる ③後半 = "
                                "データサイト誘導ブロック: 『推しの連続安打、いま何試合目か"
                                "即答できる？ 巨人の「今」を数字で1ページに → "
                                "https://yoshilover.com/data/ 。毎試合更新、観戦前の10秒"
                                "チェックにどうぞ』の趣旨を2〜3行で (URL はこのまま必ず"
                                "本文に入れる)。自己紹介の定型文っぽさ"
                                "・絵文字の乱用は避ける。ハッシュタグは付けない。事実は"
                                "与えた実績データの範囲のみ。文体は です・ます調。"
                            ),
                        )
                        or ""
                    ).strip()
                    if not txt:
                        _json_response(self, 200, {"ok": False, "reason": "generation_empty"})
                        return
                    _json_response(
                        self,
                        200,
                        {"ok": True, "drafts": [{"style": "📌 固定ポスト", "text": txt}]},
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("profile_draft_failed")
                    _json_response(
                        self, 500, {"ok": False, "reason": f"profile_draft_error:{exc!r}"}
                    )
                return
            if path in ("/scout-candidates", "/scout-mark"):
                # 🎯フォロー開拓 (2026-07-16)。収集¥0・LLMなし
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
                if path == "/scout-mark":
                    params = parse_qs(parsed.query, keep_blank_values=False)
                    handle = ((params.get("handle") or [""])[0] or "").strip()
                    mode = ((params.get("mode") or [""])[0] or "").strip()
                    ok = _mark_scout(handle, mode)  # followed / skip / undo
                    _json_response(
                        self, 200 if ok else 400, {"ok": ok, "handle": handle.lstrip("@")}
                    )
                    return
                candidates = _collect_scout_candidates()
                seen = _load_scout_seen()
                followed_total = sum(
                    1 for v in seen.values() if (v or {}).get("status") == "followed"
                )
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "candidates": candidates,
                        "followed_total": followed_total,
                    },
                )
                return
            if path in ("/trend-words", "/trend-draft"):
                # 🔥トレンド反応 即応アプリ (2026-07-16)。words=¥0、draft=LLM 1call
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
                if path == "/trend-words":
                    items = _fetch_trend_items()
                    words = [
                        {
                            "keyword": t.get("keyword") or "",
                            "category": t.get("category") or "",
                            "traffic": t.get("traffic") or "",
                            "has_news": bool(t.get("news_title")),
                        }
                        for t in items
                        if t.get("keyword")
                    ]
                    _json_response(self, 200, {"ok": True, "words": words})
                    return
                params = parse_qs(parsed.query, keep_blank_values=False)
                kw = ((params.get("kw") or [""])[0] or "").strip()
                item = next(
                    (t for t in _fetch_trend_items() if (t.get("keyword") or "") == kw),
                    None,
                )
                if item is None:
                    _json_response(self, 400, {"ok": False, "reason": "unknown_kw"})
                    return
                if item.get("category") not in ("giants", "mlb"):
                    _json_response(self, 200, {"ok": False, "reason": "no_article"})
                    return
                if not item.get("news_title"):
                    # news 無し語 (MLB言及数由来等) はタップ時に記事を探して接地
                    found = _news_lookup_for_keyword(item.get("keyword") or "")
                    if not found:
                        _json_response(self, 200, {"ok": False, "reason": "no_article"})
                        return
                    item.update(found)  # cache 内 dict も更新され次タップで再利用
                api_key = (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                    or ""
                ).strip()
                if not api_key:
                    _json_response(self, 500, {"ok": False, "reason": "gemini_key_missing"})
                    return
                try:
                    from zoneinfo import ZoneInfo

                    from src import search_trend_note as stn

                    cand = stn.build_trend_reaction_candidate(
                        [dict(item)],
                        gemini_api_key=api_key,
                        dedup_set=None,
                        now_date=datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d-%H"),
                    )
                    if cand is None or not getattr(cand, "post_text", ""):
                        _json_response(self, 200, {"ok": False, "reason": "generation_empty"})
                        return
                    _json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "news_title": item.get("news_title") or "",
                            "drafts": [
                                {"style": "🔥 トレンド反応", "text": cand.post_text}
                            ],
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("trend_draft_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"trend_draft_error:{exc!r}"})
                return
            if path in ("/x-share-recent", "/x-share-draft", "/x-thread-draft"):
                # 2026-07-06 user GO「Xまで共有でおりポスとリプまでつくって」:
                # 記事共有タブ用 API。auth は /x-post-draft と同じ cookie / query token。
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
                try:
                    from src import manual_intake_x_share as _xshare
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("x_share_import_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"import_error:{exc!r}"})
                    return
                if path == "/x-share-recent":
                    try:
                        posts = _xshare.list_recent_published(limit=10)
                    except Exception as exc:  # noqa: BLE001
                        bound_logger.exception("x_share_recent_failed")
                        _json_response(self, 502, {"ok": False, "reason": f"wp_error:{exc!r}"})
                        return
                    _json_response(self, 200, {"ok": True, "posts": posts})
                    return
                if path == "/x-thread-draft":
                    # 2026-07-07 user GO「今日の試合」: 最新の試合結果記事を自動で
                    # 拾い、 おりポス+dataリプ+URLリプ の 3 部品を返す (記事選択不要)。
                    try:
                        latest = _xshare.find_latest_postgame()
                        if not latest:
                            _json_response(
                                self, 404,
                                {"ok": False, "reason": "no_postgame_article"},
                            )
                            return
                        material = _xshare.fetch_article_material(int(latest["id"]))
                        drafts = _xshare.build_thread_drafts(
                            material,
                            gemini_api_key=(
                                os.environ.get("GEMINI_API_KEY")
                                or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                                or ""
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        bound_logger.exception("x_thread_draft_failed")
                        _json_response(self, 502, {"ok": False, "reason": f"draft_error:{exc!r}"})
                        return
                    drafts["post_id"] = int(latest["id"])
                    drafts["title"] = material.get("title") or ""
                    drafts["is_thread"] = True
                    _json_response(self, 200, drafts)
                    return
                params = parse_qs(parsed.query, keep_blank_values=False)
                raw_id = (params.get("post_id") or [""])[0].strip()
                if not raw_id.isdigit():
                    _json_response(self, 400, {"ok": False, "reason": "post_id_required"})
                    return
                try:
                    material = _xshare.fetch_article_material(int(raw_id))
                    drafts = _xshare.build_share_drafts(
                        material,
                        gemini_api_key=(
                            os.environ.get("GEMINI_API_KEY")
                            or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
                            or ""
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("x_share_draft_failed")
                    _json_response(self, 502, {"ok": False, "reason": f"draft_error:{exc!r}"})
                    return
                drafts["post_id"] = int(raw_id)
                drafts["title"] = material.get("title") or ""
                _json_response(self, 200, drafts)
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
                # 2026-07-07 user「プレミアプランだからでかくして」: Premium 長文可。
                if len(text) > 900:
                    _json_response(
                        self,
                        400,
                        {"ok": False, "reason": "text_too_long", "char_count": len(text)},
                    )
                    return
                # 2026-07-15 リプ返し: in_reply_to (tweet id) があれば返信として投稿。
                # 投稿成功時に常連リスト (GCS) を +1 する (reply_to_handle 必須)。
                in_reply_to = str(payload.get("in_reply_to") or "").strip()
                if in_reply_to and not in_reply_to.isdigit():
                    _json_response(self, 400, {"ok": False, "reason": "bad_in_reply_to"})
                    return
                try:
                    from src import x_api_client as _xc

                    client = _xc.get_client()
                    if in_reply_to:
                        resp = client.create_tweet(
                            text=text, in_reply_to_tweet_id=in_reply_to
                        )
                    else:
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
                friend_count = 0
                if in_reply_to:
                    friend_count = _bump_friend(
                        str(payload.get("reply_to_handle") or ""),
                        str(payload.get("reply_to_name") or ""),
                    )
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "tweet_id": tweet_id,
                        "char_count": len(text),
                        "friend_count": friend_count,
                    },
                )
                return
            if parsed.path == "/x-share-thread":
                # 2026-07-06: おりポス (画像付き) → 自分へのリプ (記事URL) の連続投稿。
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
                main_text = (payload.get("main_text") or "").strip()
                reply_text = (payload.get("reply_text") or "").strip()
                data_text = (payload.get("data_text") or "").strip()
                image_url = (payload.get("image_url") or "").strip()
                share_type = (payload.get("share_type") or "").strip() or "unknown"
                if not main_text or not reply_text:
                    _json_response(self, 400, {"ok": False, "reason": "empty_text"})
                    return
                try:
                    from src import manual_intake_x_share as _xshare
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("x_share_import_failed")
                    _json_response(self, 500, {"ok": False, "reason": f"import_error:{exc!r}"})
                    return
                main_w = _xshare.x_weighted_len(main_text)
                reply_w = _xshare.x_weighted_len(reply_text)
                data_w = _xshare.x_weighted_len(data_text) if data_text else 0
                # おりポス (main) は Premium 長文上限 (default 900 weighted、
                # 生成側 _main_weighted_limit と同一)。リプ/dataリプは従来 280。
                if (
                    main_w > _xshare._main_weighted_limit()
                    or reply_w > 280
                    or data_w > 280
                ):
                    _json_response(
                        self, 400,
                        {"ok": False, "reason": "text_too_long",
                         "main_weighted": main_w, "reply_weighted": reply_w,
                         "data_weighted": data_w},
                    )
                    return
                try:
                    result = _xshare.post_thread(
                        main_text, reply_text, image_url=image_url,
                        data_text=data_text,
                    )
                except KeyError as exc:
                    bound_logger.exception("x_share_thread_env_missing")
                    _json_response(self, 503, {"ok": False, "reason": f"env_missing:{exc!s}"})
                    return
                except Exception as exc:  # noqa: BLE001
                    bound_logger.exception("x_share_thread_failed")
                    _json_response(self, 502, {"ok": False, "reason": f"x_api_error:{exc!r}"})
                    return
                # 型別の実測比較 (x-engagement 週次) 用の構造化ログ
                bound_logger.info(
                    "x_share_thread_posted share_type=%s main_id=%s reply_id=%s "
                    "image=%s main_weighted=%d reply_weighted=%d",
                    share_type, result.get("main_tweet_id"), result.get("reply_tweet_id"),
                    result.get("image_attached"), main_w, reply_w,
                )
                _json_response(self, 200, result)
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
