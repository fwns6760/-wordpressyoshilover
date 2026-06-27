"""CARE LAND 手動記事化サービス（yoshilover の manual_intake_service を careland 用に真似たもの）。

URL を貼って「記事化」ボタンを押すと、その記事を **careland の引用記事（のもとけ構造）** の
WordPress 下書きにする。自動ではなく人間が1本ずつ作るための画面。

yoshilover (`manual_intake_service.py`) との対応:
  - トークン＋Cookie セッション認証（`CARELAND_MANUAL_INTAKE_TOKEN`）
  - GET /        … 入力フォーム（要ログイン）
  - GET /?token= … トークン検証して Cookie を張る
  - GET /health  … ヘルスチェック
  - POST /       … 記事化（mode=dry-run プレビュー / draft 下書き作成）

careland 固有:
  - 記事本文は `careland_news_article.build_article_draft`（引用1200字・CARE LAND緑・
    絵文字は実体参照・「ファンの声」なし）。
  - Googleニュースのラッパーは実URLに解決してから本文抽出（適法引用・出典は実媒体）。
  - 本文が取れない（有料/Yahoo/解決不可）ときは警告（人間が判断）。
  - WordPress は env の WP_URL / WP_USER / WP_APP_PASSWORD（= careland.org）。下書き固定。
"""

from __future__ import annotations

import hmac
import html
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.careland_news_article import build_article_draft, decide_category_ids, has_quotable_body
from src.careland_news_judgment import NewsVerdict

LOG = logging.getLogger("careland_manual_intake")

TOKEN_ENV = "CARELAND_MANUAL_INTAKE_TOKEN"
TOKEN_HEADER = "X-Careland-Intake-Token"
SESSION_COOKIE_NAME = "careland_manual_intake_session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 days
PORT_ENV = "PORT"
DEFAULT_PORT = 8080
MAX_BODY_BYTES = 256 * 1024

DEFAULT_SOURCE_FILE = (
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "careland_news_sources.example.json")
)

# レーン（config の lanes と対応。手動は記事化が主目的なので welfare_media を既定にする）。
LANES: list[tuple[str, str]] = [
    ("welfare_media", "福祉専門メディア（記事化）"),
    ("official_change", "制度・行政・公式発表"),
    ("it_ai_trend", "AI・ITニュース"),
    ("event_light", "イベント・更新"),
    ("medical_sensitive", "医療・診断・年金可否・法律"),
]
_LANE_LABELS = {k: v.split("（")[0] for k, v in LANES}


# ---------------------------------------------------------------------------
# auth / http helpers（yoshilover と同パターン）
# ---------------------------------------------------------------------------
def _require_token() -> str:
    return (os.environ.get(TOKEN_ENV) or "").strip()


def _cookie_token(handler: BaseHTTPRequestHandler) -> str:
    for chunk in (handler.headers.get("Cookie", "") or "").split(";"):
        chunk = chunk.strip()
        if chunk.startswith(SESSION_COOKIE_NAME + "="):
            return chunk[len(SESSION_COOKIE_NAME) + 1:].strip()
    return ""


def _request_token(handler: BaseHTTPRequestHandler, body_token: str = "") -> str:
    header = (handler.headers.get(TOKEN_HEADER, "") or "").strip()
    if header:
        return header
    if (body_token or "").strip():
        return body_token.strip()
    return _cookie_token(handler)


def _token_ok(supplied: str) -> bool:
    want = _require_token()
    if not want:
        return True  # yoshilover と同じ: トークン未設定なら開放（ログイン手順なしで使える）
    return hmac.compare_digest(supplied.strip(), want)


def _set_cookie(handler: BaseHTTPRequestHandler, value: str) -> None:
    handler.send_header("Set-Cookie", (
        f"{SESSION_COOKIE_NAME}={value}; Max-Age={SESSION_COOKIE_MAX_AGE}; "
        "Path=/; Secure; HttpOnly; SameSite=Lax"
    ))


def _html_response(handler: BaseHTTPRequestHandler, status: int, body: str,
                   *, set_cookie: str = "") -> None:
    enc = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(enc)))
    handler.send_header("Cache-Control", "no-store")
    if set_cookie:
        _set_cookie(handler, set_cookie)
    handler.end_headers()
    handler.wfile.write(enc)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    enc = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(enc)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(enc)


def _read_body(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], str]:
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError:
        length = 0
    if length <= 0:
        return {}, ""
    if length > MAX_BODY_BYTES:
        return {}, "body_too_large"
    raw = handler.rfile.read(length)
    ctype = (handler.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
    if ctype == "application/json":
        try:
            data = json.loads(raw.decode("utf-8"))
            return {str(k): "" if v is None else str(v) for k, v in dict(data).items()}, ""
        except Exception:  # noqa: BLE001
            return {}, "invalid_json"
    parsed = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}, ""


# ---------------------------------------------------------------------------
# core: 記事化
# ---------------------------------------------------------------------------
def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return ""


def _load_wp_config() -> tuple[int, dict[str, int], bool]:
    """config の wordpress 設定（breaking_id / category_map / default_index）。"""
    try:
        with open(DEFAULT_SOURCE_FILE, encoding="utf-8") as fh:
            cfg = json.load(fh)
        wp = cfg.get("wordpress", {})
        cmap = {k: int(v) for k, v in (wp.get("category_map") or {}).items()}
        return int(wp.get("breaking_category_id", 55)), cmap, bool(wp.get("default_index", False))
    except Exception:  # noqa: BLE001
        return 55, {"障害者雇用": 56, "就労支援": 57, "制度": 58}, False


def _make_verdict(*, title: str, summary: str, source_name: str, url: str,
                  lane: str, lane_label: str, body_excerpt: str) -> NewsVerdict:
    """AIが使えれば judge、無理なら fallback。手動は記事化が目的なので x_article に固定。"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    verdict: NewsVerdict | None = None
    if api_key:
        try:
            from src.careland_news_judgment import judge_news
            verdict = judge_news(
                title=title, summary=summary, source_name=source_name, url=url,
                lane=lane, lane_label=lane_label, default_decision="x_article",
                body_excerpt=body_excerpt, api_key=api_key,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("manual_judge_failed error=%s", type(exc).__name__)
    if verdict is None:
        from src.careland_news_judgment import fallback_verdict
        verdict = fallback_verdict(
            title=title, summary=summary, source_name=source_name, url=url,
            lane=lane, lane_label=lane_label, default_decision="x_article",
            body_excerpt=body_excerpt,
        )
    # 医療・煽り等のリスクで hold/discard に倒れたものはそのまま尊重（人間が判断）。
    if verdict.decision in ("hold", "discard"):
        return verdict
    from dataclasses import replace as _replace
    return _replace(verdict, decision="x_article")


def run_careland_manual_intake(*, url: str, mode: str = "dry-run",
                               title_override: str = "", summary_override: str = "",
                               source_name_override: str = "", lane: str = "welfare_media",
                               wp_client_factory=None, logger: logging.Logger = LOG
                               ) -> tuple[int, dict[str, Any]]:
    """URL を careland の引用記事下書きにする。戻り値 (http_status, payload)。"""
    url = (url or "").strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        return 400, {"ok": False, "reason": "invalid_url"}
    mode = (mode or "dry-run").strip().lower()
    if mode not in ("dry-run", "publish", "draft"):
        return 400, {"ok": False, "reason": "invalid_mode"}
    lane = lane if lane in _LANE_LABELS else "welfare_media"
    lane_label = _LANE_LABELS[lane]

    item_url, source_name = url, (source_name_override.strip() or _domain(url))
    title = title_override.strip()

    # Googleニュースのラッパーは実URLに解決（適法引用・実媒体名・実本文のため）。
    try:
        from src.google_news_url_resolver import (
            is_google_news_url, resolve_google_news_url, split_publisher_from_title)
        if is_google_news_url(url):
            resolved = resolve_google_news_url(url, timeout=20)
            if resolved:
                item_url = resolved
                if not source_name_override:
                    _, pub = split_publisher_from_title(title or "")
                    source_name = pub or _domain(resolved)
            else:
                return 502, {"ok": False, "reason": "google_news_unresolved",
                             "message": "Googleニュースのリンクは実URLに解決できませんでした。元記事の直URLを貼ってください。"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("manual_gnews_resolve_failed error=%s", type(exc).__name__)

    # 本文抽出（yoshilover と同じ 1200字）＋元記事の og:image（アイキャッチ用）。
    from src.tools.careland_news_sns_candidates import fetch_excerpt_and_image
    body_excerpt, og_image = fetch_excerpt_and_image(item_url, title or item_url, timeout_seconds=12)
    if not title:
        # タイトル未指定なら抜粋の先頭行を仮タイトルに（人間が編集前提）。改行は混ぜない。
        first_line = next((ln.strip() for ln in (body_excerpt or "").splitlines() if ln.strip()), "")
        title = (first_line or _domain(item_url) or "記事")[:60].strip()
    title = " ".join(title.split())  # WP タイトルに改行/連続空白を入れない

    summary = " ".join((summary_override.strip() or body_excerpt[:200]).split())
    quotable = has_quotable_body(body_excerpt)

    verdict = _make_verdict(title=title, summary=summary, source_name=source_name,
                            url=item_url, lane=lane, lane_label=lane_label, body_excerpt=body_excerpt)
    if verdict.decision in ("hold", "discard"):
        return 200, {"ok": False, "reason": f"judged_{verdict.decision}",
                     "message": f"AI判定で『{verdict.decision}』（医療/煽り等のリスク）と出ました。内容を確認してください。",
                     "verdict_reason": verdict.reason}

    breaking_id, category_map, default_index = _load_wp_config()
    draft = build_article_draft(
        verdict=verdict, title=title, summary=summary, source_name=source_name,
        url=item_url, lane=lane, lane_label=lane_label, breaking_id=breaking_id,
        category_map=category_map, default_index=default_index,
        slug_hint="manual", body_excerpt=body_excerpt, hero_image_url=og_image,
    )
    category_ids = list(decide_category_ids(
        lane=lane, title=title, summary=summary, breaking_id=breaking_id, category_map=category_map))

    base = {
        "ok": True, "mode": mode, "source_url": item_url, "source_name": source_name,
        "title": draft.title, "want_index": draft.want_index,
        "has_quotable_body": quotable, "category_ids": category_ids,
        "content_html": draft.content,
    }
    if not quotable:
        base["warning"] = "本文が取れていません（有料記事/Yahoo/解決不可の可能性）。引用記事として薄くなります。"

    if mode == "dry-run":
        return 200, base

    # mode == publish: 手動はいきなり記事化＝公開（yoshilover と同じ）。mode==draft なら下書き。
    wp_status = "draft" if mode == "draft" else "publish"
    factory = wp_client_factory or (lambda: __import__("src.wp_client", fromlist=["WPClient"]).WPClient())
    try:
        wp = factory()
        # 元記事の og:image をアイキャッチ(featured)に設定（WPメディアへ取り込み）。失敗しても記事は出す。
        featured_media = None
        if og_image:
            try:
                mid = wp.upload_image_from_url(og_image, source_url=item_url)
                featured_media = int(mid) or None
            except Exception as exc:  # noqa: BLE001
                logger.warning("manual_eyecatch_upload_failed error=%s", type(exc).__name__)
        post_id = wp.create_post(
            title=draft.title, content=draft.content, categories=category_ids,
            status=wp_status, source_url=item_url, caller="careland_manual_intake",
            source_lane=lane, featured_media=featured_media,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("manual_wp_post_failed error=%s", type(exc).__name__)
        return 502, {"ok": False, "reason": "wp_post_failed", "message": str(exc)[:300]}

    wp_url = os.environ.get("WP_URL", "https://careland.org").rstrip("/")
    base.update({
        "post_id": post_id,
        "wp_status": wp_status,
        "view_link": f"{wp_url}/?p={post_id}",
        "edit_link": f"{wp_url}/wp-admin/post.php?post={post_id}&action=edit",
        "preview_link": f"{wp_url}/?p={post_id}&preview=true",
    })
    logger.info("careland_manual_post_created status=%s post_id=%s index=%s title=%s",
                wp_status, post_id, draft.want_index, draft.title)
    return 200, base


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def _login_form(error: str = "") -> str:
    msg = f'<p style="color:#c0392b;">{html.escape(error)}</p>' if error else ""
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CARE LAND 手動記事化 — ログイン</title></head>
<body style="font-family:sans-serif;max-width:520px;margin:40px auto;padding:0 16px;">
<h1 style="color:#1b8a3e;font-size:20px;">CARE LAND 手動記事化</h1>{msg}
<form method="get" action="/">
<label>アクセストークン<br><input type="password" name="token" style="width:100%;padding:10px;font-size:16px;"></label>
<p><button type="submit" style="background:#1b8a3e;color:#fff;border:0;padding:10px 22px;border-radius:8px;font-size:16px;">ログイン</button></p>
</form></body></html>"""


def _form(error: str = "") -> str:
    lane_opts = "".join(
        f'<option value="{html.escape(k, quote=True)}">{html.escape(v)}</option>' for k, v in LANES)
    msg = f'<p style="color:#c0392b;">{html.escape(error)}</p>' if error else ""
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CARE LAND 手動記事化</title></head>
<body style="font-family:sans-serif;max-width:680px;margin:32px auto;padding:0 16px;line-height:1.6;">
<h1 style="color:#1b8a3e;font-size:21px;">CARE LAND 手動記事化</h1>
<p style="color:#555;font-size:14px;">記事URLを貼って「記事化（公開）」を押すと、引用記事（のもとけ構造・引用1200字・出典明示）を
careland.org に<b>そのまま公開</b>します（yoshilover と同じ）。まず「プレビュー」で確認できます。</p>{msg}
<form method="post" action="/">
<p><label>記事URL（必須）<br>
<input type="url" name="url" required placeholder="https://..." style="width:100%;padding:10px;font-size:16px;"></label></p>
<p><label>レーン<br><select name="lane" style="width:100%;padding:10px;font-size:16px;">{lane_opts}</select></label></p>
<p><label>タイトル（任意・空なら自動）<br>
<input type="text" name="title" style="width:100%;padding:10px;font-size:16px;"></label></p>
<p><label>媒体名（任意・空ならドメイン/自動）<br>
<input type="text" name="source_name" style="width:100%;padding:10px;font-size:16px;"></label></p>
<p><label>リード/要約（任意・空なら本文先頭）<br>
<textarea name="summary" rows="2" style="width:100%;padding:10px;font-size:15px;"></textarea></label></p>
<p>
<button type="submit" name="mode" value="dry-run" style="background:#2d7d9a;color:#fff;border:0;padding:11px 20px;border-radius:8px;font-size:16px;margin-right:8px;">プレビュー</button>
<button type="submit" name="mode" value="publish" style="background:#1b8a3e;color:#fff;border:0;padding:11px 24px;border-radius:8px;font-size:16px;">記事化（公開）</button>
</p>
</form></body></html>"""


def _result_page(payload: dict[str, Any]) -> str:
    if not payload.get("ok"):
        reason = html.escape(str(payload.get("message") or payload.get("reason") or "失敗"))
        return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<title>CARE LAND 手動記事化 — 結果</title></head>
<body style="font-family:sans-serif;max-width:680px;margin:32px auto;padding:0 16px;">
<h1 style="color:#c0392b;font-size:20px;">記事化できませんでした</h1>
<p>{reason}</p><p><a href="/">← 戻る</a></p></body></html>"""

    warn = (f'<p style="background:#fff3cd;border-left:4px solid #d4a017;padding:10px;">'
            f'⚠ {html.escape(payload["warning"])}</p>') if payload.get("warning") else ""
    if payload.get("mode") in ("publish", "draft"):
        published = payload.get("wp_status") == "publish"
        view = html.escape(payload.get("view_link", ""), quote=True)
        edit = html.escape(payload.get("edit_link", ""), quote=True)
        main_link = view if published else html.escape(payload.get("preview_link", ""), quote=True)
        main_label = "公開した記事を見る" if published else "プレビュー"
        links = (f'<p><a href="{main_link}" target="_blank" style="background:#1b8a3e;color:#fff;'
                 f'padding:10px 20px;border-radius:8px;text-decoration:none;">{main_label}</a> '
                 f'<a href="{edit}" target="_blank" style="margin-left:8px;">WordPressで編集</a></p>'
                 f'<p style="color:#555;">post_id={html.escape(str(payload.get("post_id")))} ／ '
                 f'index={"許可" if payload.get("want_index") else "noindex"}</p>')
        head = "記事を公開しました" if published else "下書きを作成しました"
    else:
        links = '<p style="color:#555;">プレビュー（まだ保存していません）。よければ戻って「記事化（公開）」を押してください。</p>'
        head = "プレビュー"
    title = html.escape(payload.get("title", ""))
    src = html.escape(payload.get("source_name", ""))
    content = payload.get("content_html", "")  # 自分が組んだ安全なHTML
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CARE LAND 手動記事化 — 結果</title></head>
<body style="font-family:sans-serif;max-width:680px;margin:24px auto;padding:0 16px;line-height:1.6;">
<h1 style="color:#1b8a3e;font-size:20px;">{head}</h1>{warn}
<p><b>{title}</b><br><span style="color:#777;font-size:13px;">出典: {src}</span></p>{links}
<hr><h2 style="font-size:15px;color:#555;">記事プレビュー</h2>
<div style="border:1px solid #ddd;border-radius:8px;padding:14px;">{content}</div>
<p style="margin-top:16px;"><a href="/">← 続けてもう1本</a></p></body></html>"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
def build_handler(*, wp_client_factory=None, logger: logging.Logger | None = None):
    log = logger or LOG

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):  # quiet default logging
            return

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                _json_response(self, 200, {"ok": True})
                return
            if parsed.path != "/":
                _html_response(self, 404, "<h1>404</h1>")
                return
            qs = parse_qs(parsed.query)
            token_in_url = (qs.get("token", [""])[0] or "").strip()
            if token_in_url:
                if _token_ok(token_in_url):
                    # Cookie を張って素の / にリダイレクト（URL からトークンを消す）。
                    self.send_response(303)
                    self.send_header("Location", "/")
                    _set_cookie(self, token_in_url)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                _html_response(self, 401, _login_form("トークンが違います"))
                return
            if not _token_ok(_request_token(self)):
                _html_response(self, 401, _login_form())
                return
            _html_response(self, 200, _form())

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/":
                _json_response(self, 404, {"ok": False, "reason": "not_found"})
                return
            payload, err = _read_body(self)
            if err:
                _json_response(self, 413 if err == "body_too_large" else 400, {"ok": False, "reason": err})
                return
            if not _token_ok(_request_token(self, payload.get("token", ""))):
                _html_response(self, 401, _login_form("セッション切れです。再ログインしてください。"))
                return
            wants_json = "application/json" in (self.headers.get("Accept", "") or "")
            status, result = run_careland_manual_intake(
                url=payload.get("url", ""), mode=payload.get("mode", "dry-run"),
                title_override=payload.get("title", ""), summary_override=payload.get("summary", ""),
                source_name_override=payload.get("source_name", ""), lane=payload.get("lane", "welfare_media"),
                wp_client_factory=wp_client_factory, logger=log,
            )
            if wants_json:
                _json_response(self, status, result)
            else:
                _html_response(self, status, _result_page(result))

    return Handler


def serve(port: int | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not _require_token():
        LOG.info("%s 未設定: トークン無しで開放します（yoshilover と同じ）。", TOKEN_ENV)
    bind_port = int(port if port is not None else os.environ.get(PORT_ENV, DEFAULT_PORT))
    httpd = HTTPServer(("0.0.0.0", bind_port), build_handler())
    LOG.info("careland manual intake service on :%s", bind_port)
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
