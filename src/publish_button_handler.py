"""379-OPS: /publish-and-tweet endpoint handler (GH #53).

mail 内「公開してX投稿画面へ」ボタン用の HTTP handler。
GET = confirmation page (read-only、 mail scanner が踏んでも state 変化なし)。
POST = token 検証 → draft なら publish → X intent URL に 302 redirect。

publish 自動投稿は行わない (X intent 画面 = user が「ポスト」ボタンを手動で押す画面)。
"""

from __future__ import annotations

import html
import logging
from urllib.parse import quote, urlencode

from src.publish_button_token import verify_publish_button_token


_log = logging.getLogger("server.publish_and_tweet")

_X_INTENT_BASE_URL = "https://x.com/intent/tweet"
_TITLE_MAX_CHARS_FOR_X = 80  # X 280 文字制限 + URL の余裕考慮、 title は 80 字以内


def _result_page(title: str, message: str, *, success: bool) -> str:
    color = "#1b8a3e" if success else "#d73a3a"
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        f'<title>{html.escape(title)}</title></head>'
        '<body style="font-family:sans-serif;padding:32px;max-width:640px;margin:0 auto;">'
        f'<h2 style="color:{color};">{html.escape(title)}</h2>'
        f'<p>{html.escape(message)}</p>'
        '</body></html>'
    )


def _confirmation_page(
    *,
    post_id: str,
    token: str,
    post_title: str,
    current_status: str,
) -> str:
    """GET 時の確認 page。 user が button を click するまで state は変わらない。"""
    if current_status == "publish":
        status_note = "<p>※この記事は既に <strong>公開済</strong> です。 ボタンを押すと X 投稿画面が開きます (記事 status は変わりません)。</p>"
    else:
        status_note = "<p>※この記事は <strong>下書き (draft)</strong> です。 ボタンを押すと <strong>公開 (publish)</strong> に変わり、 続けて X 投稿画面が開きます。</p>"
    escaped_post_id = html.escape(post_id)
    escaped_token = html.escape(token)
    escaped_title = html.escape(post_title or f"post_id={post_id}")
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<title>公開してX投稿画面へ</title></head>'
        '<body style="font-family:sans-serif;padding:32px;max-width:640px;margin:0 auto;">'
        '<h2>公開してX投稿画面へ</h2>'
        f'<p><strong>記事タイトル:</strong> {escaped_title}</p>'
        f'<p><strong>post_id:</strong> {escaped_post_id}</p>'
        f'{status_note}'
        '<form method="POST" action="/publish-and-tweet" style="margin-top:24px;">'
        f'<input type="hidden" name="post_id" value="{escaped_post_id}">'
        f'<input type="hidden" name="token" value="{escaped_token}">'
        '<button type="submit" style="background:#1b8a3e;color:#fff;border:0;padding:12px 32px;font-size:16px;cursor:pointer;border-radius:4px;">公開してX投稿画面へ</button>'
        '</form>'
        '<p style="margin-top:24px;color:#666;font-size:12px;">'
        '※ X 上の「ポスト」ボタンは あなたが押してください (自動投稿はしません)。'
        '</p>'
        '</body></html>'
    )


def _build_x_intent_url(*, title: str, article_url: str) -> str:
    """``https://x.com/intent/tweet?text=...&url=...`` を組み立て。

    Why: title が長すぎると X 投稿画面で truncate されて見栄えが悪いので 80 字に丸める。
    URL escape は ``urllib.parse.urlencode`` 任せで XSS / open redirect を防ぐ。
    """
    compact_title = (title or "").strip()
    if len(compact_title) > _TITLE_MAX_CHARS_FOR_X:
        compact_title = compact_title[: _TITLE_MAX_CHARS_FOR_X - 1] + "…"
    params = {"text": compact_title, "url": article_url or ""}
    return f"{_X_INTENT_BASE_URL}?{urlencode(params, quote_via=quote)}"


def handle_get(
    *,
    post_id_raw: str,
    token: str,
    fetch_post,
    now: int | float | None = None,
) -> tuple[int, str, dict]:
    """GET /publish-and-tweet: token 検証 + confirmation page 表示 (state 変化なし)。

    ``fetch_post(post_id) -> dict | None`` は post 情報取得 callable
    (テスト時 injection、 実本番は WP REST)。
    """
    if not post_id_raw or not post_id_raw.isdigit():
        return 400, _result_page("公開ボタン エラー", "post_id が不正です", success=False), {}
    if not token:
        return 400, _result_page("公開ボタン エラー", "token が無いです", success=False), {}
    if not verify_publish_button_token(post_id_raw, token, now=now):
        return 403, _result_page(
            "公開ボタン エラー",
            "token 検証失敗 (mail link が改ざん or 期限切れ、 publish-notice mail を再送してください)",
            success=False,
        ), {}
    try:
        post = fetch_post(int(post_id_raw))
    except Exception as exc:  # noqa: BLE001
        _log.warning("publish_button_get_fetch_failed post_id=%s err=%s", post_id_raw, exc)
        return 500, _result_page(
            "公開ボタン エラー",
            f"記事情報の取得に失敗しました ({str(exc)[:120]})",
            success=False,
        ), {}
    if not post:
        return 404, _result_page(
            "公開ボタン エラー",
            f"post_id={post_id_raw} は存在しないか、 取得権限がありません",
            success=False,
        ), {}
    post_title = ""
    title_field = post.get("title")
    if isinstance(title_field, dict):
        post_title = str(title_field.get("rendered") or "").strip()
    else:
        post_title = str(title_field or "").strip()
    current_status = str(post.get("status") or "").strip()
    body = _confirmation_page(
        post_id=post_id_raw,
        token=token,
        post_title=post_title,
        current_status=current_status,
    )
    return 200, body, {}


def handle_post(
    *,
    post_id_raw: str,
    token: str,
    fetch_post,
    update_post_status,
    now: int | float | None = None,
) -> tuple[int, str, dict]:
    """POST /publish-and-tweet: token 検証 → draft なら publish → X intent URL に 302 redirect。

    ``fetch_post(post_id) -> dict | None``: post 情報 (status / title / link 取得)
    ``update_post_status(post_id, "publish")``: WP REST で status を flip (caller が wp_client wrap)
    """
    if not post_id_raw or not post_id_raw.isdigit():
        return 400, _result_page("公開ボタン エラー", "post_id が不正です", success=False), {}
    if not token:
        return 400, _result_page("公開ボタン エラー", "token が無いです", success=False), {}
    if not verify_publish_button_token(post_id_raw, token, now=now):
        return 403, _result_page(
            "公開ボタン エラー",
            "token 検証失敗 (改ざん or 期限切れ)",
            success=False,
        ), {}
    post_id = int(post_id_raw)
    try:
        post = fetch_post(post_id)
    except Exception as exc:  # noqa: BLE001
        _log.warning("publish_button_post_fetch_failed post_id=%s err=%s", post_id, exc)
        return 500, _result_page(
            "公開ボタン エラー",
            f"記事情報の取得に失敗しました ({str(exc)[:120]})",
            success=False,
        ), {}
    if not post:
        return 404, _result_page(
            "公開ボタン エラー",
            f"post_id={post_id_raw} は存在しないか、 取得権限がありません",
            success=False,
        ), {}
    current_status = str(post.get("status") or "").strip()
    post_link = str(post.get("link") or "").strip()
    title_field = post.get("title")
    if isinstance(title_field, dict):
        post_title = str(title_field.get("rendered") or "").strip()
    else:
        post_title = str(title_field or "").strip()
    if current_status == "draft":
        try:
            update_post_status(post_id, "publish")
        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)
            _log.warning(
                "publish_button_post_update_failed post_id=%s err=%s",
                post_id,
                err_msg,
            )
            return 500, _result_page(
                "公開ボタン エラー",
                f"WP REST publish 失敗 (post_id={post_id}): {err_msg[:200]}",
                success=False,
            ), {}
        # publish 直後は WP REST の link field がまだ古い slug の可能性があるため
        # 念のため refetch して最新 link を取る。 失敗時は元 link を fallback。
        try:
            refreshed = fetch_post(post_id)
            if refreshed:
                refreshed_link = str(refreshed.get("link") or "").strip()
                if refreshed_link:
                    post_link = refreshed_link
        except Exception:  # noqa: BLE001
            pass
        _log.info(
            "publish_button_publish_success post_id=%s caller=mail_publish_and_tweet_endpoint",
            post_id,
        )
    elif current_status == "publish":
        _log.info(
            "publish_button_already_published post_id=%s caller=mail_publish_and_tweet_endpoint",
            post_id,
        )
    else:
        return 409, _result_page(
            "公開ボタン エラー",
            f"post_id={post_id} の status={current_status} は 公開対象外 (draft / publish 以外は touch しません)",
            success=False,
        ), {}
    if not post_link:
        return 500, _result_page(
            "公開ボタン エラー",
            f"post_id={post_id} の公開 URL が取得できませんでした",
            success=False,
        ), {}
    x_intent_url = _build_x_intent_url(title=post_title, article_url=post_link)
    return 302, "", {"Location": x_intent_url}


__all__ = [
    "handle_get",
    "handle_post",
]
