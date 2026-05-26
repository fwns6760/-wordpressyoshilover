"""437 Phase 2A (2026-05-26): /share-x + /share-x-image-proxy endpoint handlers.

Pixel / Android native Web Share API (``navigator.share({files, text, url})``) で
WP eyecatch (PNG/JPG) を X app に **画像 + 文字** で直接転送するための endpoint。

flow (Pixel + Gmail 想定):
1. mail の「📱 画像つきで X に投稿 (おすすめ)」 button を tap
2. GET /share-x?post_id=X&token=Y → HTML page + JS
3. page 読み込み時に /share-x-image-proxy?post_id=X&token=Y を fetch して
   ``File`` object を構築 (CORS 同一 origin なので blob 取得可)
4. user が「画像つきで X に共有」 button tap
   - ``navigator.canShare({files: [file]})`` true → AJAX POST /publish-and-tweet
     (format=json, draft なら publish + post_link/x_text 返す)
     → ``navigator.share({files, text, url})`` で X app へ
   - canShare false / preloadedFile null → form 通常 submit
     (既存 GET /publish-and-tweet → confirmation → POST → X intent flow)
   - AJAX / share 失敗時 → ``window.location.href = X_INTENT_URL`` で
     text-only X intent fallback

Phase 1 (cairosvg SVG 生成) は CJK tofu で commit e90fcfa で物理削除済。
本 Phase 2A は WP featured_media (実写真 PNG/JPG) を **そのまま proxy** するだけで、
SVG 生成 / CJK render / font 系一切なし。
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any, Callable

from src.publish_button_token import verify_publish_button_token

_log = logging.getLogger("server.share_x")

_X_INTENT_BASE_URL = "https://x.com/intent/post"
_TITLE_MAX_CHARS_FOR_X = 80  # X 280 char 制限考慮、 title は 80 字以内に丸める
# publish_button_handler._X_INTENT_BRAND_TAG と同 literal (重複だが circular import 防ぐ)
_X_INTENT_BRAND_TAG = "\n🐰 ヨシラバー｜⚾ 読売ジャイアンツ速報掲示板"


def _result_page(title: str, message: str, *, success: bool) -> str:
    """share-x 内エラー時の簡易 HTML page (publish_button_handler._result_page と同設計)。"""
    color = "#1b8a3e" if success else "#d73a3a"
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        f'<title>{html.escape(title)}</title></head>'
        '<body style="font-family:sans-serif;padding:32px;max-width:640px;margin:0 auto;">'
        f'<h2 style="color:{color};">{html.escape(title)}</h2>'
        f'<p>{html.escape(message)}</p>'
        '</body></html>'
    )


def _build_x_intent_url(*, title: str, article_url: str) -> str:
    """``https://x.com/intent/post?text=...&url=...`` を組み立て (text-only fallback 用)。

    publish_button_handler._build_x_intent_url と同 logic。
    title 80 字 cap、 brand tag 付与、 urlencode で XSS / open redirect 防ぐ。
    """
    from urllib.parse import quote, urlencode

    compact_title = (title or "").strip()
    if len(compact_title) > _TITLE_MAX_CHARS_FOR_X:
        compact_title = compact_title[: _TITLE_MAX_CHARS_FOR_X - 1] + "…"
    text_with_brand = (
        f"{compact_title}{_X_INTENT_BRAND_TAG}" if compact_title else _X_INTENT_BRAND_TAG.strip()
    )
    params = {"text": text_with_brand, "url": article_url or ""}
    return f"{_X_INTENT_BASE_URL}?{urlencode(params, quote_via=quote)}"


def _extract_post_title(post: dict) -> str:
    title_field = post.get("title")
    if isinstance(title_field, dict):
        return str(title_field.get("rendered") or "").strip()
    return str(title_field or "").strip()


def _extract_featured_media(post: dict) -> int:
    """post から featured_media (image attachment id) を取り出す。0 = 未設定。"""
    try:
        return int(post.get("featured_media") or 0)
    except (TypeError, ValueError):
        return 0


def _build_share_page_html(
    *,
    post_id: str,
    token: str,
    post_title: str,
    article_url: str,
    image_proxy_url: str,
    x_intent_url: str,
    has_image: bool,
) -> str:
    """share-x の HTML page を組み立てる (Web Share API trigger + fallback 内包)。

    JS embed は ``json.dumps`` で文字列を JSON literal にし XSS を防ぐ
    (``html.escape`` ではなく JSON literal で safe)。
    """
    escaped_post_id = html.escape(post_id)
    escaped_token = html.escape(token)
    escaped_title = html.escape(post_title or f"post_id={post_id}")
    safe_image_proxy_attr = html.escape(image_proxy_url)
    # JS embed 用 (JSON literal で escape)
    js_image_proxy = json.dumps(image_proxy_url)
    js_x_intent = json.dumps(x_intent_url)
    js_article_url_default = json.dumps(article_url or "")
    js_x_text_default = json.dumps(
        (post_title or "") + (_X_INTENT_BRAND_TAG if post_title else _X_INTENT_BRAND_TAG.strip())
    )

    # 画像 preview (featured_media あるときだけ)。
    image_html = ""
    if has_image:
        image_html = (
            '<p style="text-align:center;margin:16px 0;">'
            f'<img src="{safe_image_proxy_attr}" alt="記事のアイキャッチ" '
            'style="max-width:100%;height:auto;border-radius:6px;'
            'box-shadow:0 1px 3px rgba(0,0,0,0.1);" /></p>'
        )

    # share button (Web Share API trigger)。
    # form action=/publish-and-tweet は fallback 用 (JS が canShare 不可と判定したら
    # preventDefault せず通常 submit させる)。
    share_button_html = (
        '<form id="share-x-form" method="POST" action="/publish-and-tweet" '
        'style="margin-top:24px;text-align:center;">'
        f'<input type="hidden" name="post_id" value="{escaped_post_id}">'
        f'<input type="hidden" name="token" value="{escaped_token}">'
        '<button type="submit" id="share-x-btn" '
        'style="background:#ef6c00;color:#fff;border:0;padding:14px 32px;'
        'font-size:16px;font-weight:700;cursor:pointer;border-radius:6px;'
        'width:100%;max-width:320px;">'
        '📱 画像つきで X に共有</button>'
        '<p style="margin-top:12px;color:#666;font-size:12px;">'
        '※ ボタンを押すと記事が公開され、 X app の投稿画面が開きます。'
        '</p></form>'
    )

    # JS: image を pre-fetch → File 化 → share button click で navigator.share。
    # canShare 不可 / preloadedFile null → form 通常 submit。
    # AJAX or share 失敗 → text-only X intent に fallback。
    js_block = f"""
<script>
(function() {{
  var IMAGE_URL = {js_image_proxy};
  var X_INTENT_URL = {js_x_intent};
  var DEFAULT_ARTICLE_URL = {js_article_url_default};
  var DEFAULT_X_TEXT = {js_x_text_default};
  var preloadedFile = null;
  var hasImage = {str(has_image).lower()};

  function preloadImage() {{
    if (!hasImage) {{ return; }}
    fetch(IMAGE_URL, {{credentials: 'same-origin'}})
      .then(function(r) {{
        if (!r.ok) {{ throw new Error('image fetch failed: ' + r.status); }}
        return r.blob();
      }})
      .then(function(blob) {{
        var ext = 'jpg';
        if (blob.type === 'image/png') {{ ext = 'png'; }}
        else if (blob.type === 'image/webp') {{ ext = 'webp'; }}
        else if (blob.type === 'image/gif') {{ ext = 'gif'; }}
        preloadedFile = new File([blob], 'yoshilover.' + ext, {{type: blob.type || 'image/jpeg'}});
      }})
      .catch(function(err) {{
        console.warn('share-x preload image failed', err);
        preloadedFile = null;
      }});
  }}
  preloadImage();

  var form = document.getElementById('share-x-form');
  if (!form) {{ return; }}
  form.addEventListener('submit', function(ev) {{
    var canShareFiles = false;
    try {{
      canShareFiles = !!(navigator.canShare && preloadedFile &&
        navigator.canShare({{files: [preloadedFile]}}));
    }} catch (e) {{
      canShareFiles = false;
    }}
    if (!canShareFiles) {{
      // Fall back to normal form submit (existing /publish-and-tweet POST flow).
      return;
    }}
    ev.preventDefault();
    var fd = new FormData(form);
    fd.append('format', 'json');
    fetch(form.action, {{method: 'POST', body: fd, credentials: 'same-origin'}})
      .then(function(r) {{
        if (!r.ok) {{ throw new Error('publish failed: ' + r.status); }}
        return r.json();
      }})
      .then(function(data) {{
        var articleUrl = (data && data.article_url) || DEFAULT_ARTICLE_URL;
        var xText = (data && data.x_text) || DEFAULT_X_TEXT;
        return navigator.share({{
          files: [preloadedFile],
          text: xText,
          url: articleUrl
        }});
      }})
      .catch(function(err) {{
        console.warn('share-x flow failed, falling back to X intent', err);
        window.location.href = X_INTENT_URL;
      }});
  }});
}})();
</script>
"""

    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>画像つきで X に共有</title></head>'
        '<body style="font-family:-apple-system,BlinkMacSystemFont,'
        '\'Hiragino Sans\',\'Yu Gothic\',sans-serif;padding:24px;'
        'max-width:560px;margin:0 auto;color:#222;">'
        '<h2 style="font-size:18px;margin:0 0 16px;">画像つきで X に共有</h2>'
        f'<p style="margin:0 0 8px;font-size:15px;font-weight:700;">{escaped_title}</p>'
        f'{image_html}'
        f'{share_button_html}'
        f'{js_block}'
        '</body></html>'
    )


def handle_share_get(
    *,
    post_id_raw: str,
    token: str,
    fetch_post: Callable[[int], dict | None],
    now: int | float | None = None,
    fetcher_base_url: str = "",
) -> tuple[int, str, dict]:
    """GET /share-x: post / token 検証 → share page HTML を返す。

    ``fetcher_base_url``: image proxy URL を absolute にしたい場合に指定 (空なら relative)。
    """
    if not post_id_raw or not post_id_raw.isdigit():
        return 400, _result_page("共有ページ エラー", "post_id が不正です", success=False), {}
    if not token:
        return 400, _result_page("共有ページ エラー", "token が無いです", success=False), {}
    if not verify_publish_button_token(post_id_raw, token, now=now):
        return 403, _result_page(
            "共有ページ エラー",
            "token 検証失敗 (mail link が改ざん or 期限切れ、 publish-notice mail を再送してください)",
            success=False,
        ), {}
    try:
        post = fetch_post(int(post_id_raw))
    except Exception as exc:  # noqa: BLE001
        _log.warning("share_x_get_fetch_failed post_id=%s err=%s", post_id_raw, exc)
        return 500, _result_page(
            "共有ページ エラー",
            f"記事情報の取得に失敗しました ({str(exc)[:120]})",
            success=False,
        ), {}
    if not post:
        return 404, _result_page(
            "共有ページ エラー",
            f"post_id={post_id_raw} は存在しないか、 取得権限がありません",
            success=False,
        ), {}
    post_title = _extract_post_title(post)
    article_url = str(post.get("link") or "").strip()
    featured_media_id = _extract_featured_media(post)
    has_image = featured_media_id > 0

    base = (fetcher_base_url or "").strip().rstrip("/")
    proxy_qs = f"post_id={post_id_raw}&token={token}"
    image_proxy_url = f"{base}/share-x-image-proxy?{proxy_qs}" if base else f"/share-x-image-proxy?{proxy_qs}"
    x_intent_url = _build_x_intent_url(title=post_title, article_url=article_url)

    body = _build_share_page_html(
        post_id=post_id_raw,
        token=token,
        post_title=post_title,
        article_url=article_url,
        image_proxy_url=image_proxy_url,
        x_intent_url=x_intent_url,
        has_image=has_image,
    )
    return 200, body, {}


def handle_image_proxy(
    *,
    post_id_raw: str,
    token: str,
    fetch_post: Callable[[int], dict | None],
    fetch_media_bytes: Callable[[int], tuple[bytes, str] | None],
    now: int | float | None = None,
) -> tuple[int, bytes, str, dict]:
    """GET /share-x-image-proxy: post / token 検証 → featured_media 画像 bytes を返す。

    Returns ``(status_code, body_bytes, content_type, extra_headers)``。
    成功時は image bytes + Cache-Control private (mail 経由 link のため CDN は避ける)。
    失敗時は text/plain で error msg (caller は content_type を text/plain に上書きする)。
    """
    if not post_id_raw or not post_id_raw.isdigit():
        return 400, b"post_id is invalid", "text/plain; charset=utf-8", {}
    if not token:
        return 400, b"token is missing", "text/plain; charset=utf-8", {}
    if not verify_publish_button_token(post_id_raw, token, now=now):
        return 403, b"token verification failed", "text/plain; charset=utf-8", {}
    try:
        post = fetch_post(int(post_id_raw))
    except Exception as exc:  # noqa: BLE001
        _log.warning("share_x_image_proxy_fetch_post_failed post_id=%s err=%s", post_id_raw, exc)
        return 500, f"fetch post failed: {str(exc)[:120]}".encode("utf-8"), "text/plain; charset=utf-8", {}
    if not post:
        return 404, b"post not found", "text/plain; charset=utf-8", {}
    featured_media_id = _extract_featured_media(post)
    if featured_media_id <= 0:
        return 404, b"featured_media not set", "text/plain; charset=utf-8", {}
    try:
        result = fetch_media_bytes(featured_media_id)
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "share_x_image_proxy_fetch_media_failed post_id=%s media_id=%s err=%s",
            post_id_raw,
            featured_media_id,
            exc,
        )
        return 502, f"fetch media failed: {str(exc)[:120]}".encode("utf-8"), "text/plain; charset=utf-8", {}
    if not result:
        return 502, b"fetch media returned empty", "text/plain; charset=utf-8", {}
    body_bytes, content_type = result
    if not isinstance(body_bytes, (bytes, bytearray)) or not body_bytes:
        return 502, b"fetch media returned invalid bytes", "text/plain; charset=utf-8", {}
    if not content_type or not isinstance(content_type, str):
        content_type = "application/octet-stream"
    return (
        200,
        bytes(body_bytes),
        content_type,
        {"Cache-Control": "private, max-age=600"},
    )


__all__ = ["handle_share_get", "handle_image_proxy"]
