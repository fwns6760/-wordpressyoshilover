"""377-ARCHIVE Phase 2: 小林誠司 名言 mail lane.

Goal:
  GCS の archives/kobayashi_meigen/tweets.jsonl から N 件 pick して
  HTML mail で送る。 送信履歴は GCS の sent_cursor.jsonl で管理
  (24h dedup ではなく永続 dedup、 1 度送ったら再送しない)。

Pick 順序: 古い順 (created_at asc)。 妻 curation の時系列で配信。

Hard constraints:
  - X API 呼ばない (archive 済の GCS JSONL のみ参照)
  - WP REST 呼ばない (mail のみ)
  - 公開記事生成しない、 SNS 投稿しない
  - 既存 mail_delivery_bridge / 既存 GCS bucket を流用
"""

from __future__ import annotations

import html as _html
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote as _url_quote
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")

DEFAULT_BUCKET = "baseballsite-yoshilover-insight"
ARCHIVE_KEY = "archives/kobayashi_meigen/tweets.jsonl"
CURSOR_KEY = "archives/kobayashi_meigen/sent_cursor.jsonl"

_TIME_BANDS = (
    (range(11, 14), "昼"),
    (range(14, 19), "夕方"),
    (range(19, 24), "夜"),
    (range(0, 11), "朝"),  # 早朝に手動 fire したとき用 fallback
)
_TIME_BAND_EMOJI = {"朝": "🌅", "昼": "🌞", "夕方": "🌆", "夜": "🌙"}


@dataclass(frozen=True)
class MeigenCandidate:
    tweet_id: str
    text: str
    created_at: str
    like_count: int
    retweet_count: int
    has_media: bool
    media: list[dict[str, Any]] = field(default_factory=list)
    permalink: str = ""


@dataclass(frozen=True)
class ComposedMail:
    subject: str
    text_body: str
    html_body: str
    candidate_count: int


def _band_for_hour(hour: int) -> str:
    for r, label in _TIME_BANDS:
        if hour in r:
            return label
    return "夜"


def _build_subject(now: datetime, n: int) -> str:
    band = _band_for_hour(now.hour)
    emoji = _TIME_BAND_EMOJI.get(band, "📮")
    return f"📮【小林誠司 名言 {n}件】{emoji}{band} {now.strftime('%H:%M')} JST"


def _format_jst_date(iso_utc: str) -> str:
    if not iso_utc:
        return "?"
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%Y年%-m月%-d日")
    except (ValueError, TypeError):
        return iso_utc


def _permalink(tweet_id: str) -> str:
    return f"https://twitter.com/sakaikkotaiso/status/{tweet_id}"


# X 280-char hard limit on Web Intent URL pre-fill (longer text is silently
# dropped by X). Keep a few char margin for the ellipsis.
_X_POST_CHAR_LIMIT = 270


def _build_x_intent_url(text: str) -> str:
    """X Web Intent (twitter.com/intent/tweet) で開く 投稿 URL。

    text は 270 char cap、 超えたら末尾 … で切る。 改行 / 特殊文字は
    quote(safe="") で full encode。
    """
    body = text or ""
    if len(body) > _X_POST_CHAR_LIMIT:
        body = body[: _X_POST_CHAR_LIMIT - 1] + "…"
    return f"https://twitter.com/intent/tweet?text={_url_quote(body, safe='')}"


def _record_to_candidate(rec: dict[str, Any]) -> MeigenCandidate:
    pm = rec.get("public_metrics") or {}
    tid = rec["tweet_id"]
    return MeigenCandidate(
        tweet_id=tid,
        text=rec.get("text") or "",
        created_at=rec.get("created_at") or "",
        like_count=int(pm.get("like_count") or 0),
        retweet_count=int(pm.get("retweet_count") or 0),
        has_media=bool(rec.get("has_media")),
        media=list(rec.get("media") or []),
        permalink=_permalink(tid),
    )


def load_archive(bucket: Any, archive_key: str = ARCHIVE_KEY) -> list[dict[str, Any]]:
    blob = bucket.blob(archive_key)
    if not blob.exists():
        return []
    text = blob.download_as_text()
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def load_sent_cursor(bucket: Any, cursor_key: str = CURSOR_KEY) -> set[str]:
    blob = bucket.blob(cursor_key)
    if not blob.exists():
        return set()
    text = blob.download_as_text()
    out: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            tid = rec.get("tweet_id")
            if tid:
                out.add(str(tid))
        except Exception:  # noqa: BLE001
            continue
    return out


def append_sent_cursor(
    bucket: Any,
    *,
    sent_tweet_ids: list[str],
    now: datetime,
    cursor_key: str = CURSOR_KEY,
) -> bool:
    if not sent_tweet_ids:
        return True
    blob = bucket.blob(cursor_key)
    ts = now.isoformat()
    lines = [
        json.dumps({"ts": ts, "tweet_id": tid}, ensure_ascii=False)
        for tid in sent_tweet_ids
    ]
    new_block = "\n".join(lines) + "\n"
    try:
        existing = blob.download_as_text() if blob.exists() else ""
    except Exception as exc:  # noqa: BLE001
        LOG.warning("append_sent_cursor: read failed: %r", exc)
        existing = ""
    try:
        blob.upload_from_string(existing + new_block, content_type="application/x-ndjson")
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("append_sent_cursor: upload failed: %r", exc)
        return False


def pick_candidates(
    records: list[dict[str, Any]],
    *,
    sent_ids: set[str],
    n: int,
) -> list[MeigenCandidate]:
    """Return up to ``n`` unsent candidates in created_at asc (oldest first)."""
    unsent = [r for r in records if str(r.get("tweet_id")) not in sent_ids]
    unsent.sort(key=lambda r: r.get("created_at") or "")
    return [_record_to_candidate(r) for r in unsent[:n]]


def _compose_text_body(candidates: list[MeigenCandidate], now: datetime) -> str:
    lines = [
        f"📮 小林誠司 名言 — {now.strftime('%Y-%m-%d %H:%M')} JST",
        "",
        "妻 curation アーカイブ (@sakaikkotaiso) からの自動配信。",
        "",
    ]
    for idx, c in enumerate(candidates, start=1):
        lines.append(f"■ {idx}. ({_format_jst_date(c.created_at)})")
        lines.append(c.text)
        if c.has_media and c.media:
            urls = [m.get("url") or m.get("preview_image_url") for m in c.media]
            urls = [u for u in urls if u]
            if urls:
                lines.append("📷 画像: " + ", ".join(urls))
            else:
                lines.append("📷 画像あり (URL 取得は 6/12 cycle reset 後)")
        elif c.has_media:
            lines.append("📷 画像あり (URL 取得は 6/12 cycle reset 後)")
        lines.append(f"🐦 X に投稿: {_build_x_intent_url(c.text)}")
        lines.append(f"🔗 元 tweet: {c.permalink}")
        lines.append(
            f"♥ {c.like_count}   🔁 {c.retweet_count}"
        )
        lines.append("──────────────")
        lines.append("")
    lines.append("配信元: yoshilover archive (small batch、 1 日 3 fire)")
    return "\n".join(lines)


def _compose_html_body(candidates: list[MeigenCandidate], now: datetime) -> str:
    parts = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        "<title>小林誠司 名言</title></head>",
        "<body style=\"font-family:system-ui,-apple-system,Hiragino Kaku Gothic ProN,Yu Gothic,Meiryo,sans-serif;"
        "max-width:680px;margin:0 auto;padding:16px;color:#222;\">",
        f"<h1 style=\"font-size:18px;margin:0 0 8px;\">📮 小林誠司 名言 — {now.strftime('%Y-%m-%d %H:%M')} JST</h1>",
        "<p style=\"color:#666;font-size:13px;margin:0 0 16px;\">"
        "妻 curation アーカイブ (@sakaikkotaiso) からの自動配信</p>",
    ]
    for idx, c in enumerate(candidates, start=1):
        date_str = _format_jst_date(c.created_at)
        text_html = _html.escape(c.text).replace("\n", "<br>")
        parts.append(
            "<div style=\"border:1px solid #e2e2e2;border-radius:8px;"
            "padding:12px 16px;margin:0 0 16px;background:#fff;\">"
        )
        parts.append(
            f"<div style=\"font-size:13px;color:#888;margin:0 0 6px;\">■ {idx}. {date_str}</div>"
        )
        parts.append(
            f"<div style=\"font-size:15px;line-height:1.7;margin:0 0 10px;\">{text_html}</div>"
        )
        if c.has_media:
            url_imgs = []
            for m in c.media:
                u = m.get("url") or m.get("preview_image_url")
                gcs_path = m.get("gcs_path")
                if gcs_path and gcs_path.startswith("gs://"):
                    # 後 fire で public URL or signed URL に置換する想定
                    pass
                if u:
                    url_imgs.append(_html.escape(u))
            if url_imgs:
                for u in url_imgs:
                    parts.append(
                        f"<img src=\"{u}\" alt=\"\" "
                        "style=\"max-width:100%;height:auto;border-radius:6px;margin:0 0 8px;\">"
                    )
            else:
                parts.append(
                    "<div style=\"font-size:12px;color:#a00;margin:0 0 8px;\">"
                    "📷 画像あり (URL backfill 6/12 以降)</div>"
                )
        intent_url = _build_x_intent_url(c.text)
        parts.append(
            "<div style=\"margin:8px 0 4px;\">"
            f"<a href=\"{_html.escape(intent_url)}\" "
            "style=\"display:inline-block;background:#1d9bf0;color:#fff;"
            "text-decoration:none;font-size:14px;font-weight:600;"
            "padding:8px 16px;border-radius:9999px;"
            "border:1px solid #1d9bf0;\">"
            "🐦 X に投稿"
            "</a>"
            "</div>"
        )
        parts.append(
            f"<div style=\"font-size:12px;color:#888;\">"
            f"<a href=\"{_html.escape(c.permalink)}\" "
            "style=\"color:#1d9bf0;text-decoration:none;\">🔗 元 tweet を開く</a>"
            f"   ♥ {c.like_count}   🔁 {c.retweet_count}"
            "</div>"
        )
        parts.append("</div>")
    parts.append(
        "<div style=\"font-size:12px;color:#888;margin:16px 0 0;\">"
        "配信元: yoshilover archive (small batch、 1 日 3 fire 12:00 / 17:00 / 20:00 JST)"
        "</div>"
    )
    parts.append("</body></html>")
    return "".join(parts)


def compose_mail(
    candidates: list[MeigenCandidate], *, now: Optional[datetime] = None
) -> ComposedMail:
    if now is None:
        now = datetime.now(JST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    subject = _build_subject(now, len(candidates))
    return ComposedMail(
        subject=subject,
        text_body=_compose_text_body(candidates, now),
        html_body=_compose_html_body(candidates, now),
        candidate_count=len(candidates),
    )
