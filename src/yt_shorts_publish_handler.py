"""HTTP handlers for YouTube Shorts mail approval buttons."""

from __future__ import annotations

import html

from src.yt_shorts_youtube import set_video_privacy
from src.yt_shorts_youtube_token import is_valid_video_id, verify_yt_shorts_publish_token


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _studio_url(video_id: str) -> str:
    return f"https://studio.youtube.com/video/{video_id}/edit"


def _result_page(title: str, message: str, *, success: bool, video_id: str = "") -> str:
    color = "#1b8a3e" if success else "#d73a3a"
    links = ""
    if success and video_id:
        escaped_watch = html.escape(_watch_url(video_id))
        escaped_studio = html.escape(_studio_url(video_id))
        links = (
            f'<p><a href="{escaped_watch}">YouTubeで開く</a></p>'
            f'<p><a href="{escaped_studio}">YouTube Studioで確認</a></p>'
        )
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title></head>"
        '<body style="font-family:sans-serif;padding:32px;max-width:680px;margin:0 auto;">'
        f'<h2 style="color:{color};">{html.escape(title)}</h2>'
        f"<p>{html.escape(message)}</p>"
        f"{links}"
        "</body></html>"
    )


def _confirmation_page(video_id: str, token: str) -> str:
    escaped_video_id = html.escape(video_id)
    escaped_token = html.escape(token)
    escaped_watch = html.escape(_watch_url(video_id))
    escaped_studio = html.escape(_studio_url(video_id))
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        "<title>YouTube Shortsを公開</title></head>"
        '<body style="font-family:sans-serif;padding:32px;max-width:680px;margin:0 auto;">'
        "<h2>YouTube Shortsを公開</h2>"
        f"<p><strong>video_id:</strong> {escaped_video_id}</p>"
        "<p>このボタンを押すと、対象動画の公開範囲を <strong>public</strong> に変更します。</p>"
        f'<p><a href="{escaped_watch}">YouTubeで確認</a> / <a href="{escaped_studio}">Studioで編集</a></p>'
        '<form method="POST" action="/yt-shorts-publish" style="margin-top:24px;">'
        f'<input type="hidden" name="video_id" value="{escaped_video_id}">'
        f'<input type="hidden" name="token" value="{escaped_token}">'
        '<button type="submit" style="background:#1b8a3e;color:#fff;border:0;'
        'padding:12px 32px;font-size:16px;cursor:pointer;border-radius:4px;">'
        "公開する</button>"
        "</form>"
        '<p style="margin-top:24px;color:#666;font-size:12px;">'
        "※ 生成済みの非公開動画だけを公開します。動画ファイルの再生成や再アップロードは行いません。"
        "</p>"
        "</body></html>"
    )


def handle_get(
    *,
    video_id: str,
    token: str,
    now: int | float | None = None,
) -> tuple[int, str, dict]:
    vid = str(video_id or "").strip()
    raw_token = str(token or "").strip()
    if not is_valid_video_id(vid):
        return 400, _result_page("YouTube公開ボタン エラー", "video_id が不正です", success=False), {}
    if not raw_token:
        return 400, _result_page("YouTube公開ボタン エラー", "token がありません", success=False), {}
    if not verify_yt_shorts_publish_token(vid, raw_token, now=now):
        return 403, _result_page("YouTube公開ボタン エラー", "token 検証失敗または期限切れです", success=False), {}
    return 200, _confirmation_page(vid, raw_token), {}


def handle_post(
    *,
    video_id: str,
    token: str,
    publish_video=None,
    now: int | float | None = None,
) -> tuple[int, str, dict]:
    vid = str(video_id or "").strip()
    raw_token = str(token or "").strip()
    if not is_valid_video_id(vid):
        return 400, _result_page("YouTube公開ボタン エラー", "video_id が不正です", success=False), {}
    if not raw_token:
        return 400, _result_page("YouTube公開ボタン エラー", "token がありません", success=False), {}
    if not verify_yt_shorts_publish_token(vid, raw_token, now=now):
        return 403, _result_page("YouTube公開ボタン エラー", "token 検証失敗または期限切れです", success=False), {}

    publish_fn = publish_video or (lambda target: set_video_privacy(target, "public"))
    try:
        result = publish_fn(vid)
    except Exception as exc:  # noqa: BLE001
        return 500, _result_page(
            "YouTube公開ボタン エラー",
            f"YouTube 公開化に失敗しました: {str(exc)[:180]}",
            success=False,
        ), {}
    privacy = str(getattr(result, "privacy_status", "public") or "public")
    return 200, _result_page(
        "YouTube Shorts 公開完了",
        f"video_id={vid} を {privacy} に変更しました。",
        success=True,
        video_id=vid,
    ), {}


__all__ = ["handle_get", "handle_post"]
