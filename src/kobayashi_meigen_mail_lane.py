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
from urllib.parse import urlencode as _urlencode
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
class MeigenSeriesConfig:
    player_name: str
    series_title: str
    source_note: str
    source_handle: str
    permalink_handle: str
    archive_key: str
    cursor_key: str
    hashtags: tuple[str, ...]
    lane_name: str
    footer_schedule: str


KOBAYASHI_CONFIG = MeigenSeriesConfig(
    player_name="小林誠司",
    series_title="小林誠司 名言集",
    source_note="妻 curation アーカイブ (@sakaikkotaiso) からの自動配信。",
    source_handle="@sakaikkotaiso",
    permalink_handle="sakaikkotaiso",
    archive_key=ARCHIVE_KEY,
    cursor_key=CURSOR_KEY,
    hashtags=("#巨人", "#小林誠司"),
    lane_name="kobayashi-meigen",
    footer_schedule="1 日 3 fire 12:00 / 17:00 / 20:00 JST",
)

SAKAMOTO_CONFIG = MeigenSeriesConfig(
    player_name="坂本勇人",
    series_title="坂本勇人 名言集",
    source_note="@hayatocup アーカイブからの自動配信。",
    source_handle="@hayatocup",
    permalink_handle="hayatocup",
    archive_key="archives/sakamoto_meigen/tweets.jsonl",
    cursor_key="archives/sakamoto_meigen/sent_cursor.jsonl",
    hashtags=("#巨人", "#坂本勇人"),
    lane_name="sakamoto-meigen",
    footer_schedule="1 日 1 fire 18:00 JST",
)

# 吉川尚輝は本人 X が無いため、 archive_yoshikawa_meigen feeder が
# スポーツ各紙の取材記事から本人発言を抽出して archive を作る。
# record は記事 URL を permalink、 媒体名を source_name に持つので、
# mail には「出典: 媒体（日付）」が「どこで言ったか」として表示される。
YOSHIKAWA_CONFIG = MeigenSeriesConfig(
    player_name="吉川尚輝",
    series_title="吉川尚輝 名言集",
    source_note="スポーツ各紙の取材コメントから、吉川尚輝本人の発言を自動収集。出典は各名言に記載。",
    source_handle="",
    permalink_handle="",
    archive_key="archives/yoshikawa_meigen/tweets.jsonl",
    cursor_key="archives/yoshikawa_meigen/sent_cursor.jsonl",
    hashtags=("#巨人", "#吉川尚輝"),
    lane_name="yoshikawa-meigen",
    footer_schedule="月水金 15:00 JST 配信",
)

# 原辰徳は監督/レジェンドの語録ライン。 取材・インタビュー・名言から
# リーダー論 / 指導論 / 恩師(長嶋)回顧 / 人生哲学を収録。 吉川と同じく
# 記事 URL を permalink、 媒体名を source_name に持つ。
HARA_CONFIG = MeigenSeriesConfig(
    player_name="原辰徳",
    series_title="原辰徳 語録",
    source_note="原辰徳の取材・インタビュー・名言から、リーダー論や恩師への思いを収録。出典は各項目に記載。",
    source_handle="",
    permalink_handle="",
    archive_key="archives/hara_meigen/tweets.jsonl",
    cursor_key="archives/hara_meigen/sent_cursor.jsonl",
    hashtags=("#巨人", "#原辰徳"),
    lane_name="hara-meigen",
    footer_schedule="毎日 8:00 JST 配信",
)


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
    # archive 内 chronological 位置 (1-based、 oldest=1)。 rotate しても
    # 同じ tweet は同じ番号、 「NO①」「NO②」…の通し番号として使う。
    archive_number: int = 0
    # 記事ソースの媒体名 (吉川尚輝 など、 取材記事から抽出した名言用)。
    # 小林 / 坂本 (本人ツイート由来) は空文字のまま = 従来表示を維持。
    source_name: str = ""
    # 画像つき X 投稿 (Web Share API) 用。 archive build 時に画像 bytes を
    # GCS share_x_cand/ に上げた blob key + content-type。 空なら従来の
    # text-only intent のみ。
    share_blob_key: str = ""
    media_content_type: str = ""


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


def _build_subject(
    now: datetime,
    n: int,
    *,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
) -> str:
    """Subject 形式は yoshilover Gmail folder filter に揃える:
    - prefix `🟠🐦📮` (x-post-mail と同じ orange + bird marker)
    - suffix ` | YOSHILOVER` (publish-notice / alert と同じ brand 名)
    どちらかが filter rule に一致すれば「ヨシラバー」folder へ振り分けられる。
    """
    band = _band_for_hour(now.hour)
    emoji = _TIME_BAND_EMOJI.get(band, "📮")
    return (
        f"🟠🐦📮【{config.player_name} 名言 {n}件】{emoji}{band} "
        f"{now.strftime('%H:%M')} JST | YOSHILOVER"
    )


# 2026-07-07 user「名言集、ポストの引用日間違えてる」: 原/吉川 archive の
# 手動投入時、並び順維持のためのダミー timestamp (2021-01-01T00:00:XX) が
# created_at に入っている record が 58 件ある (原 44 / 吉川 14、実測)。
# 実際の発言日・記事日ではないため、日付としては表示しない (媒体名のみ)。
_PLACEHOLDER_CREATED_AT_PREFIX = "2021-01-01T00:00:"


def _is_placeholder_created_at(iso_utc: str) -> bool:
    return (iso_utc or "").startswith(_PLACEHOLDER_CREATED_AT_PREFIX)


def _format_jst_date(iso_utc: str) -> str:
    if not iso_utc:
        return "?"
    if _is_placeholder_created_at(iso_utc):
        return ""
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%Y年%-m月%-d日")
    except (ValueError, TypeError):
        return iso_utc


def _format_source_credit(iso_utc: str, source_name: str) -> str:
    """X 投稿本文に入れる出典テキスト 「（2026/06/18 スポーツ報知）」。

    リンクは付けない。 X は外部リンク付き投稿のインプレッションを下げるため、
    出典は URL ではなく日付 + 媒体名のテキストで明示する。
    日付がダミー (_is_placeholder_created_at) の時は媒体名のみ 「（スポーツ報知）」。
    """
    if not source_name:
        return ""
    date = ""
    if iso_utc and not _is_placeholder_created_at(iso_utc):
        try:
            dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
            date = dt.astimezone(JST).strftime("%Y/%m/%d")
        except (ValueError, TypeError):
            date = ""
    inner = f"{date} {source_name}".strip()
    return f"（{inner}）"


def _permalink(
    tweet_id: str,
    *,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
) -> str:
    return f"https://twitter.com/{config.permalink_handle}/status/{tweet_id}"


# X 280-char hard limit on Web Intent URL pre-fill (longer text is silently
# dropped by X). Keep a few char margin for the ellipsis.
_X_POST_CHAR_LIMIT = 270


def _compose_x_post_body(
    text: str,
    archive_number: int = 0,
    *,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
    source_url: str = "",
    source_credit: str = "",
) -> str:
    """X 投稿本文 (series header + quote + 出典 + hashtag) を組み立てて返す。

    text-only intent と 画像つき投稿 (Web Share API) で同じ本文を使うため、
    URL 化前の生テキストをここで作る。 X 280 char hard limit を守る。
    """
    raw = text or ""
    header = ""
    footer = ""
    if archive_number and archive_number > 0:
        no_str = str(archive_number)  # plain digit (1, 100, 836 全部統一)
        header = (
            f"🏆 {config.series_title} 🏆\n"
            "━━━━━━━━━━━━\n"
            f"       第 {no_str} 回\n"
            "━━━━━━━━━━━━\n\n"
        )
        footer_lines = []
        if source_credit:
            # 出典 (日付 + 媒体) を先頭に。 リンクは付けない (インプ低下回避)。
            footer_lines.append(source_credit)
        footer_lines.append(" ".join(config.hashtags))
        if source_url:
            footer_lines.append(source_url)
        footer = "\n\n" + "\n".join(footer_lines)
    available_for_text = _X_POST_CHAR_LIMIT - len(header) - len(footer)
    if len(raw) > available_for_text:
        raw = raw[: max(0, available_for_text - 1)] + "…"
    return f"{header}{raw}{footer}"


def _build_x_intent_url(
    text: str,
    archive_number: int = 0,
    *,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
    source_url: str = "",
    source_credit: str = "",
) -> str:
    """X Web Intent (x.com/intent/post、 text-only) で開く 投稿 URL。"""
    body = _compose_x_post_body(
        text, archive_number, config=config,
        source_url=source_url, source_credit=source_credit,
    )
    return f"https://x.com/intent/post?text={_url_quote(body, safe='')}"


def _share_x_cand_button_url(
    candidate: "MeigenCandidate", post_body: str,
) -> str:
    """画像つき X 投稿 (Web Share API) 用 fetcher /share-x-cand URL。

    candidate.share_blob_key (archive build 時に画像 bytes を GCS へ上げた key)
    と env 3 点が揃った時だけ URL を返す。 揃わなければ "" (= ボタン非表示、
    従来の text-only intent のみ)。 token は share_x_cand_token (default secret
    は fetcher と一致) で生成。
    """
    blob_key = getattr(candidate, "share_blob_key", "") or ""
    if not blob_key:
        return ""
    flag = (os.environ.get("ENABLE_SHARE_X_BUTTON") or "").strip().lower()
    fetcher_base = (os.environ.get("FETCHER_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if flag not in {"1", "true", "yes", "on"} or not fetcher_base:
        return ""
    try:
        from src.share_x_cand_token import generate_share_x_cand_token
        token = generate_share_x_cand_token(blob_key)
    except Exception:  # noqa: BLE001
        return ""
    if not token:
        return ""
    params = _urlencode({"key": blob_key, "token": token, "text": post_body, "url": ""})
    return f"{fetcher_base}/share-x-cand?{params}"


_KEYCAP_DIGITS = {
    "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
    "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣",
}


def _emoji_number(n: int) -> str:
    """N の各桁を keycap emoji (0️⃣..9️⃣) で連結。

    例: 1 → 1️⃣、 10 → 1️⃣0️⃣、 100 → 1️⃣0️⃣0️⃣、 836 → 8️⃣3️⃣6️⃣。
    全番号で emoji size が統一されて plain text 環境 (X post / mail
    text body) でも 数字が ちゃんと大きく見える。
    """
    if n <= 0:
        return str(n) if n else "0️⃣"
    return "".join(_KEYCAP_DIGITS.get(c, c) for c in str(n))


def _record_to_candidate(
    rec: dict[str, Any],
    archive_number: int = 0,
    *,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
) -> MeigenCandidate:
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
        # record に permalink があれば優先 (吉川=記事 URL)。 無ければ
        # 従来通り twitter permalink を組む (小林 / 坂本)。
        permalink=rec.get("permalink") or _permalink(tid, config=config),
        archive_number=archive_number,
        source_name=str(rec.get("source_name") or ""),
        share_blob_key=str(rec.get("share_blob_key") or ""),
        media_content_type=str(rec.get("media_content_type") or ""),
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
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
) -> list[MeigenCandidate]:
    """Return up to ``n`` unsent candidates in created_at asc (oldest first).

    archive_number は archive 全体を created_at asc で並べた時の
    1-based position。 同じ tweet は rotate しても同じ番号。
    """
    chronological = sorted(records, key=lambda r: r.get("created_at") or "")
    position_map: dict[str, int] = {
        str(r["tweet_id"]): i + 1 for i, r in enumerate(chronological)
    }
    unsent = [r for r in chronological if str(r.get("tweet_id")) not in sent_ids]
    return [
        _record_to_candidate(
            r,
            archive_number=position_map[str(r["tweet_id"])],
            config=config,
        )
        for r in unsent[:n]
    ]


def _compose_text_body(
    candidates: list[MeigenCandidate],
    now: datetime,
    *,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
) -> str:
    lines = [
        f"📮 {config.player_name} 名言 — {now.strftime('%Y-%m-%d %H:%M')} JST",
        "",
        config.source_note,
        "",
    ]
    for idx, c in enumerate(candidates, start=1):
        no_label = str(c.archive_number) if c.archive_number else str(idx)
        # 記事ソース (吉川) の発言は『』で囲む。 本人ツイート (小林/坂本) はそのまま。
        disp = f"『{c.text}』" if c.source_name else c.text
        lines.append(f"🏆 {config.series_title} 🏆")
        lines.append("━━━━━━━━━━━━")
        lines.append(f"       第 {no_label} 回")
        lines.append("━━━━━━━━━━━━")
        _date_line = _format_jst_date(c.created_at)
        if _date_line:
            lines.append(f"📅 {_date_line}")
        lines.append("")
        lines.append(disp)
        if c.has_media and c.media:
            media_lines = []
            for m in c.media:
                u = m.get("url") or m.get("preview_image_url")
                if not u:
                    continue
                media_type = str(m.get("type") or "").lower()
                label = "動画サムネイル" if media_type == "video" and m.get("preview_image_url") else "メディア"
                media_lines.append(f"{label}: {u}")
            if media_lines:
                lines.append("📎 " + " / ".join(media_lines))
            else:
                lines.append("📎 メディアあり (URL 未取得、元 tweet で確認)")
        elif c.has_media:
            lines.append("📎 メディアあり (URL 未取得、元 tweet で確認)")
        lines.append(
            "🐦 X に投稿: "
            + _build_x_intent_url(
                disp,
                archive_number=c.archive_number,
                config=config,
                source_url=c.permalink if c.has_media else "",
                source_credit=(
                    _format_source_credit(c.created_at, c.source_name)
                    if c.source_name else ""
                ),
            )
        )
        if c.source_name:
            # 記事ソース (吉川): 「どこで言ったか」= 媒体 + 日付 + 記事 URL。
            # 日付ダミー時は媒体のみ。
            _src_date = _format_jst_date(c.created_at)
            lines.append(
                f"🔗 出典: {c.source_name}（{_src_date}）" if _src_date
                else f"🔗 出典: {c.source_name}"
            )
            lines.append(f"   {c.permalink}")
        else:
            lines.append(f"🔗 元 tweet: {c.permalink}")
            lines.append(
                f"♥ {c.like_count}   🔁 {c.retweet_count}"
            )
        lines.append("──────────────")
        lines.append("")
    lines.append(f"配信元: yoshilover archive (small batch、 {config.footer_schedule})")
    return "\n".join(lines)


def _compose_html_body(
    candidates: list[MeigenCandidate],
    now: datetime,
    *,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
) -> str:
    parts = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        f"<title>{_html.escape(config.player_name)} 名言</title></head>",
        "<body style=\"font-family:system-ui,-apple-system,Hiragino Kaku Gothic ProN,Yu Gothic,Meiryo,sans-serif;"
        "max-width:680px;margin:0 auto;padding:16px;color:#222;\">",
        f"<h1 style=\"font-size:18px;margin:0 0 8px;\">📮 {_html.escape(config.player_name)} 名言 — {now.strftime('%Y-%m-%d %H:%M')} JST</h1>",
        "<p style=\"color:#666;font-size:13px;margin:0 0 16px;\">"
        f"{_html.escape(config.source_note)}</p>",
    ]
    for idx, c in enumerate(candidates, start=1):
        date_str = _format_jst_date(c.created_at)
        disp = f"『{c.text}』" if c.source_name else c.text
        text_html = _html.escape(disp).replace("\n", "<br>")
        no_label = str(c.archive_number) if c.archive_number else str(idx)
        parts.append(
            "<div style=\"border:1px solid #e2e2e2;border-radius:8px;"
            "padding:12px 16px;margin:0 0 16px;background:#fff;\">"
        )
        # ヘッダー: X post 本文と同じ装飾 (🏆 + 罫線 + plain digit) を
        # text-align:center で再現、 「mail で見たまま X に投稿される」 体験。
        parts.append(
            "<div style=\"text-align:center;font-family:monospace;"
            "font-size:15px;line-height:1.6;color:#222;"
            "padding:8px 0 12px;margin:0 0 12px;"
            "border-bottom:1px solid #ddd;\">"
            f"🏆 {_html.escape(config.series_title)} 🏆<br>"
            "━━━━━━━━━━━━<br>"
            f"第 {_html.escape(no_label)} 回<br>"
            "━━━━━━━━━━━━"
            "</div>"
        )
        if date_str:
            parts.append(
                f"<div style=\"font-size:12px;color:#888;margin:0 0 8px;\">📅 {date_str}</div>"
            )
        parts.append(
            f"<div style=\"font-size:15px;line-height:1.7;margin:0 0 10px;\">{text_html}</div>"
        )
        if c.has_media:
            url_imgs = []
            for m in c.media:
                u = m.get("url") or m.get("preview_image_url")
                media_type = str(m.get("type") or "").lower()
                if u:
                    label = "動画サムネイル" if media_type == "video" and m.get("preview_image_url") else "メディア"
                    url_imgs.append((_html.escape(u), label))
            if url_imgs:
                for u, label in url_imgs:
                    parts.append(
                        f"<img src=\"{u}\" alt=\"\" "
                        "style=\"max-width:100%;height:auto;border-radius:6px;margin:0 0 8px;\">"
                    )
                    parts.append(
                        "<div style=\"font-size:12px;color:#888;margin:-4px 0 8px;\">"
                        f"📎 {_html.escape(label)}</div>"
                    )
            else:
                parts.append(
                    "<div style=\"font-size:12px;color:#a00;margin:0 0 8px;\">"
                    f"📎 メディアあり (<a href=\"{_html.escape(c.permalink)}\" "
                    "style=\"color:#1d9bf0;text-decoration:none;\">元 tweet で確認</a>)</div>"
                )
        _post_body = _compose_x_post_body(
            disp,
            c.archive_number,
            config=config,
            source_url=c.permalink if c.has_media else "",
            source_credit=(
                _format_source_credit(c.created_at, c.source_name)
                if c.source_name else ""
            ),
        )
        intent_url = f"https://x.com/intent/post?text={_url_quote(_post_body, safe='')}"
        share_url = _share_x_cand_button_url(c, _post_body)
        parts.append("<div style=\"margin:8px 0 4px;\">")
        if share_url:
            # 画像つき投稿 (スマホ Web Share API)。 x_post_mail と同一仕様:
            # メイン = 画像つき、 予備 = テキストのみ intent。
            parts.append(
                f"<a href=\"{_html.escape(share_url)}\" "
                "style=\"display:inline-block;background:#1d9bf0;color:#fff;"
                "text-decoration:none;font-size:14px;font-weight:600;"
                "padding:8px 16px;border-radius:9999px;border:1px solid #1d9bf0;"
                "margin-right:8px;\">"
                "🐦 画像つきで X に投稿"
                "</a>"
                f"<a href=\"{_html.escape(intent_url)}\" "
                "style=\"display:inline-block;background:#fff;color:#000;"
                "text-decoration:none;font-size:13px;font-weight:600;"
                "padding:8px 14px;border-radius:9999px;border:1px solid #000;\">"
                "✍ テキストのみで投稿 (画像は手動添付)"
                "</a>"
            )
        else:
            parts.append(
                f"<a href=\"{_html.escape(intent_url)}\" "
                "style=\"display:inline-block;background:#1d9bf0;color:#fff;"
                "text-decoration:none;font-size:14px;font-weight:600;"
                "padding:8px 16px;border-radius:9999px;"
                "border:1px solid #1d9bf0;\">"
                "🐦 X に投稿"
                "</a>"
            )
        parts.append("</div>")
        if c.source_name:
            _src_date_html = _format_jst_date(c.created_at)
            _src_label = (
                f"{_html.escape(c.source_name)}（{_html.escape(_src_date_html)}）"
                if _src_date_html else _html.escape(c.source_name)
            )
            parts.append(
                f"<div style=\"font-size:12px;color:#888;\">"
                f"📰 出典: {_src_label} "
                f"<a href=\"{_html.escape(c.permalink)}\" "
                "style=\"color:#1d9bf0;text-decoration:none;\">記事を開く</a>"
                "</div>"
            )
        else:
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
        f"配信元: yoshilover archive (small batch、 {_html.escape(config.footer_schedule)})"
        "</div>"
    )
    parts.append("</body></html>")
    return "".join(parts)


def compose_mail(
    candidates: list[MeigenCandidate],
    *,
    now: Optional[datetime] = None,
    config: MeigenSeriesConfig = KOBAYASHI_CONFIG,
) -> ComposedMail:
    if now is None:
        now = datetime.now(JST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    subject = _build_subject(now, len(candidates), config=config)
    return ComposedMail(
        subject=subject,
        text_body=_compose_text_body(candidates, now, config=config),
        html_body=_compose_html_body(candidates, now, config=config),
        candidate_count=len(candidates),
    )
