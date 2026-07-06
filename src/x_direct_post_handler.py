"""mail ボタン → 確認ページ → X API 直投稿 (アカウント自動選択)。2026-07-06 user GO。

背景: user はスマホで 2 アカウント運用 (野球=@yoshilover6760 / マーケ・FIRE系=
@yoshilover_naka)。X の intent / deep link には「どのアカウントで開くか」を指定する
パラメータが存在しないため、mail ボタンからアプリ側アカウントを切り替えることは
仕様上不可能。代わりに server 側で該当アカウントの API key を使って直接投稿する
(X app を開かない = 切替そのものを無くす)。

flow (スマホ Gmail 想定):
1. mail の「⚡ @…から即投稿」button → GET /x-direct-post?acct=..&text=..&token=..
2. 確認ページ (textarea 編集可 + weighted 文字数) → 投稿ボタン tap で POST
3. token 検証 (HMAC + expiry、原文 sha16 に署名) → tweepy create_tweet → 結果ページ

安全側:
- 投稿実行は確認ページでの明示 tap のみ (mail 内 1 tap 即投稿にはしない)
- token は原文にバインド。確認ページでの編集は user 自身の行為として許容
- reply / 引用RT は in_reply_to_tweet_id / quote_tweet_id で API 側に引き継ぐ
- naka の key 未設定時は投稿せずエラーページ (mail 導線は落とさない)
"""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import re
import time
from urllib.parse import urlencode

from src.publish_button_token import _resolve_secret

LOG = logging.getLogger("x_direct_post")

_TOKEN_HMAC_LENGTH = 24
_DEFAULT_TTL_SECONDS = 172800  # mail は数時間〜翌日に開かれるので 48h
_STATUS_ID_RE = re.compile(r"/status(?:es)?/(\d+)")

# account registry。env_prefix + {API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET}
_ACCOUNTS = {
    "baseball": {
        "handle": "yoshilover6760",
        "label": "⚾ ヨシラバー (@yoshilover6760)",
        "env_prefix": "X_",
        "color": "#f57f17",
    },
    "naka": {
        "handle": "yoshilover_naka",
        "label": "💰 マーケ/FIRE (@yoshilover_naka)",
        "env_prefix": "X_NAKA_",
        "color": "#1b5e20",
    },
}


def _text_digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _compute_token_hmac(acct: str, digest: str, expiry: int) -> str:
    secret = _resolve_secret().encode("utf-8")
    payload = f"xdp:{acct}:{digest}:{expiry}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:_TOKEN_HMAC_LENGTH]


def generate_direct_post_token(
    acct: str, text: str, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    if acct not in _ACCOUNTS or not (text or "").strip() or ttl_seconds <= 0:
        return ""
    expiry = int(now if now is not None else time.time()) + int(ttl_seconds)
    return f"{expiry}.{_compute_token_hmac(acct, _text_digest(text), expiry)}"


def verify_direct_post_token(
    acct: str, digest: str, token: str, *, now: float | None = None
) -> bool:
    try:
        expiry_raw, provided = (token or "").split(".", 1)
        expiry = int(expiry_raw)
    except ValueError:
        return False
    if int(now if now is not None else time.time()) > expiry:
        return False
    expected = _compute_token_hmac(acct, digest, expiry)
    return hmac.compare_digest(expected, provided)


def build_direct_post_button_url(
    text: str,
    *,
    account: str,
    base_url: str,
    reply_to_id: str = "",
    quote_url: str = "",
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> str:
    """mail に埋める GET URL。base_url or text が無ければ空 (caller はボタンを出さない)。"""
    base = (base_url or "").strip().rstrip("/")
    if not base or account not in _ACCOUNTS or not (text or "").strip():
        return ""
    token = generate_direct_post_token(account, text, ttl_seconds=ttl_seconds)
    if not token:
        return ""
    params = {"acct": account, "text": text, "token": token}
    if reply_to_id:
        params["reply_to"] = reply_to_id
    if quote_url:
        params["quote"] = quote_url
    return f"{base}/x-direct-post?{urlencode(params)}"


def _account_creds(acct: str) -> dict | None:
    prefix = _ACCOUNTS[acct]["env_prefix"]
    creds = {
        "consumer_key": os.environ.get(f"{prefix}API_KEY", "").strip(),
        "consumer_secret": os.environ.get(f"{prefix}API_SECRET", "").strip(),
        "access_token": os.environ.get(f"{prefix}ACCESS_TOKEN", "").strip(),
        "access_token_secret": os.environ.get(f"{prefix}ACCESS_TOKEN_SECRET", "").strip(),
    }
    if not all(creds.values()):
        return None
    return creds


def _get_client_for(acct: str):
    creds = _account_creds(acct)
    if creds is None:
        return None
    import tweepy

    return tweepy.Client(**creds)


def _quote_tweet_id(quote_url: str) -> str:
    m = _STATUS_ID_RE.search(quote_url or "")
    return m.group(1) if m else ""


def _weighted_len(text: str) -> int:
    from src.manual_intake_x_share import x_weighted_len

    return x_weighted_len(text)


def _page(title: str, body_html: str) -> str:
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        '<body style="font-family:sans-serif;padding:20px;max-width:640px;'
        'margin:0 auto;background:#fafafa;">'
        f"{body_html}</body></html>"
    )


def _error_page(message: str, *, code: int = 400) -> tuple[int, str, dict]:
    body = (
        '<h2 style="color:#d73a3a;">投稿できません</h2>'
        f"<p>{html.escape(message)}</p>"
    )
    return code, _page("X直投稿エラー", body), {}


def handle_direct_post_get(
    acct: str, text: str, token: str, *, reply_to: str = "", quote: str = ""
) -> tuple[int, str, dict]:
    """GET /x-direct-post → 確認ページ (textarea 編集可 + 投稿ボタン)。"""
    if acct not in _ACCOUNTS:
        return _error_page("アカウント指定が不正です。")
    if not (text or "").strip():
        return _error_page("本文が空です。")
    if not verify_direct_post_token(acct, _text_digest(text), token):
        return _error_page("リンクの有効期限切れか、URLが壊れています。mail のボタンから開き直してください。", code=403)
    meta = _ACCOUNTS[acct]
    creds_note = ""
    if _account_creds(acct) is None:
        creds_note = (
            '<p style="color:#d73a3a;font-weight:600;">⚠ このアカウントの API key が'
            "未設定のため、いま投稿ボタンを押してもエラーになります。</p>"
        )
    weighted = _weighted_len(text)
    body = (
        f'<div style="display:inline-block;padding:6px 12px;border-radius:16px;'
        f'background:{meta["color"]};color:#fff;font-weight:700;font-size:14px;">'
        f'{html.escape(meta["label"])} から投稿</div>'
        f"{creds_note}"
        '<form method="POST" action="/x-direct-post" style="margin-top:14px;">'
        f'<input type="hidden" name="acct" value="{html.escape(acct)}">'
        f'<input type="hidden" name="token" value="{html.escape(token)}">'
        f'<input type="hidden" name="orig_digest" value="{_text_digest(text)}">'
        f'<input type="hidden" name="reply_to" value="{html.escape(reply_to)}">'
        f'<input type="hidden" name="quote" value="{html.escape(quote)}">'
        '<textarea name="text" id="xdp-text" rows="8" style="width:100%;'
        'font-size:15px;line-height:1.5;padding:10px;border:1px solid #ccc;'
        f'border-radius:8px;box-sizing:border-box;">{html.escape(text)}</textarea>'
        f'<div id="xdp-count" style="font-size:12px;color:#666;margin:4px 0 12px;">'
        f"weighted {weighted}/280</div>"
        '<button type="submit" style="width:100%;padding:14px;border:none;'
        f'border-radius:8px;background:{meta["color"]};color:#fff;font-size:16px;'
        'font-weight:700;">🚀 このアカウントで投稿する</button>'
        "</form>"
        "<script>"
        "var t=document.getElementById('xdp-text'),c=document.getElementById('xdp-count');"
        "t.addEventListener('input',function(){var n=0,s=t.value;"
        "for(var i=0;i<s.length;i++){n+=s.charCodeAt(i)>=4352?2:1;}"
        "c.textContent='weighted '+n+'/280';"
        "c.style.color=n>280?'#d73a3a':'#666';});"
        "</script>"
    )
    return 200, _page("X直投稿の確認", body), {}


def handle_direct_post_post(
    acct: str, text: str, token: str, orig_digest: str,
    *, reply_to: str = "", quote: str = ""
) -> tuple[int, str, dict]:
    """POST /x-direct-post → token 検証 + create_tweet + 結果ページ。"""
    if acct not in _ACCOUNTS:
        return _error_page("アカウント指定が不正です。")
    if not (text or "").strip():
        return _error_page("本文が空です。")
    if not verify_direct_post_token(acct, orig_digest, token):
        return _error_page("リンクの有効期限切れです。mail のボタンから開き直してください。", code=403)
    weighted = _weighted_len(text)
    if weighted > 280:
        return _error_page(f"weighted {weighted}/280 で超過しています。本文を短くしてください。")
    client = _get_client_for(acct)
    meta = _ACCOUNTS[acct]
    if client is None:
        return _error_page(
            f'{meta["handle"]} の API key (env {meta["env_prefix"]}API_KEY 等 4 点) が'
            "未設定です。key 登録後に再度押してください。", code=503,
        )
    kwargs: dict = {"text": text}
    if reply_to:
        kwargs["in_reply_to_tweet_id"] = reply_to
    qid = _quote_tweet_id(quote)
    if qid:
        kwargs["quote_tweet_id"] = qid
    try:
        resp = client.create_tweet(**kwargs)
        tweet_id = str((getattr(resp, "data", None) or {}).get("id") or "")
    except Exception as exc:  # noqa: BLE001
        LOG.warning("x_direct_post failed acct=%s err=%r", acct, exc)
        return _error_page(f"X API エラー: {exc}", code=502)
    LOG.info("x_direct_post ok acct=%s tweet_id=%s weighted=%d", acct, tweet_id, weighted)
    status_url = f'https://x.com/{meta["handle"]}/status/{tweet_id}' if tweet_id else ""
    link_html = (
        f'<p><a href="{html.escape(status_url)}" style="font-size:16px;">'
        "投稿を確認する →</a></p>" if status_url else ""
    )
    body = (
        '<h2 style="color:#1b8a3e;">✅ 投稿しました</h2>'
        f'<p>{html.escape(meta["label"])}</p>{link_html}'
        '<p style="color:#666;font-size:13px;">このページは閉じて大丈夫です。</p>'
    )
    return 200, _page("投稿完了", body), {}
