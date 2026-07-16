"""吉川尚輝 名言 feeder: Googleニュース検索RSS から本人発言を抽出して
小林型 meigen archive (NDJSON) を作る。

小林誠司 = 妻 curation の本人ツイート既製 / 坂本勇人 = Hermes x_search。
吉川尚輝は本人 X が無いため、スポーツ紙インタビュー記事 (Googleニュースの
キーワード検索RSS) から「吉川本人が実際に話した発言」だけを Gemini で抽出し、
小林型と同じ archive shape (tweet_id / text / created_at / permalink ...) に
変換する。配信は kobayashi_meigen_mail_lane と完全に同一 (YOSHIKAWA_CONFIG)。

Hard constraints:
  - X API 呼ばない
  - WP REST 呼ばない / 公開記事生成しない / SNS 投稿しない
  - 出力は local JSONL (+ --upload-gcs で GCS archive) のみ
  - Gemini は本人発言の「抽出」だけに使う (創作・要約は禁止する prompt)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser

from src.google_news_url_resolver import (
    is_google_news_url,
    resolve_google_news_url,
    split_publisher_from_title,
)
from src.source_article_body_extractor import extract_article_body_excerpt
from src.gemini_model_policy import generate_content_url, select_gemini_model

LOG = logging.getLogger(__name__)

PLAYER = "吉川尚輝"
DEFAULT_QUERIES = [
    "吉川尚輝 猛打賞",
    "吉川尚輝 決勝打",
    "吉川尚輝 ヒーローインタビュー",
    "吉川尚輝 ズムサタ 熱血ジャイアンツ",
    "吉川尚輝 活躍 巨人",
    "吉川尚輝 サヨナラ",
]
DEFAULT_OUTPUT = "data/yoshikawa_meigen/tweets.jsonl"
DEFAULT_GCS_BUCKET = "baseballsite-yoshilover-insight"
DEFAULT_GCS_KEY = "archives/yoshikawa_meigen/tweets.jsonl"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _rss_url(query: str, *, after: str = "2018-01-01") -> str:
    full = f"{query} after:{after}" if after else query
    q = urllib.parse.quote(full)
    return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"


def _fetch_html(url: str, *, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
            if enc == "gzip":
                import gzip
                raw = gzip.decompress(raw)
        return raw.decode("utf-8", "ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        LOG.info("html_fetch_failed url=%s error=%s", url[:60], type(exc).__name__)
        return ""


_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_OG_IMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I
)


def _extract_og_image(html: str) -> str:
    """記事 HTML から og:image (サムネ = 本人写真) の URL を引き抜く。"""
    if not html:
        return ""
    m = _OG_IMAGE_RE.search(html) or _OG_IMAGE_RE2.search(html)
    return m.group(1).strip() if m else ""


def _entry_published_iso(entry: Any) -> str:
    pp = getattr(entry, "published_parsed", None)
    if pp:
        try:
            return datetime(*pp[:6], tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).isoformat()


def _stable_id(url: str, idx: int) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{h}{idx:02d}"


def _normalize_for_dedup(text: str) -> str:
    import re
    t = re.sub(r"\s+", "", text or "")
    return t.strip()


_QUOTE_PROMPT = """あなたはプロ野球の取材記事から、選手本人が実際に口にした発言だけを正確に抜き出す編集者です。

対象選手: 巨人・吉川尚輝
記事見出し: {title}
記事本文(抜粋):
{body}

この記事の中から【吉川尚輝 本人が実際に話した言葉】だけを抜き出してください。

厳守ルール:
1. 記者が書いた地の文・状況説明・データ・順位や成績の記述は除外する
2. 監督・コーチ・他選手・ファンなど本人以外の発言は除外する
3. 試合での活躍・好打・勝利・チームへの貢献・手応え・ファンへの感謝など、明るく前向きで内容のある発言を優先する
4. 怪我・リハビリ・登録抹消・不調・二軍調整など、苦しい状況に関する発言は採らない（活躍した時の発言だけを選ぶ）
5. 記事に書かれた通り、一字一句変えずに抜き出す(要約・言い換え・創作は一切禁止)
6. 確実に本人の発言だと言えるものだけ。少しでも曖昧なら採らない
7. 30文字未満の短い相槌・断片は採らない（読んで響く、ある程度長いセリフだけ）
8. 本人の発言が無ければ空の配列を返す

出力はJSONのみ。前置きや説明は書かない:
{{"quotes": ["発言1", "発言2"]}}"""


def _extract_json_obj(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def gemini_extract_quotes(
    title: str, body: str, *, api_key: str, timeout: int = 30
) -> list[str]:
    """記事本文から吉川本人の発言だけを抽出。失敗・無ければ空 list。"""
    if not body.strip():
        return []
    prompt = _QUOTE_PROMPT.format(title=title, body=body[:4000])
    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 1024,
                "temperature": 0.2,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode("utf-8")
    try:
        model = select_gemini_model()
        url = generate_content_url(api_key, model)
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.load(res)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:  # noqa: BLE001 - 抽出失敗は空で degrade
        LOG.info("gemini_extract_failed title=%s error=%s", title[:30], type(exc).__name__)
        return []
    obj = _extract_json_obj(text)
    if not obj:
        return []
    quotes = obj.get("quotes")
    if not isinstance(quotes, list):
        return []
    out: list[str] = []
    for q in quotes:
        if not isinstance(q, str):
            continue
        # 前後の括弧 / 引用符を外す (表示側で『』を付けるため二重にしない)
        s = q.strip().strip("「」『』\"'　 ")
        if len(s) < 30:  # 短い相槌・断片は名言にしない (活躍時の長めのセリフだけ)
            continue
        out.append(s)
    return out


# 2026-07-16 user「画像がうまく取れていない」: og:image が媒体サイトの汎用ロゴ
# (jsports の ogp-image.png が 46/47 件、実測) で、X カードがロゴ表示 = 逆効果
# だった。URL pattern + 使い回し頻度で汎用ロゴを判定して archive から外す。
_GENERIC_OG_IMAGE_RE = re.compile(
    r"(ogp?[-_.]?image|logo|default|noimage|no[-_]image|common|favicon|placeholder)",
    re.I,
)


def is_generic_og_image(url: str) -> bool:
    """og:image URL が媒体の汎用ロゴ/プレースホルダらしければ True。"""
    return bool(_GENERIC_OG_IMAGE_RE.search(url or ""))


def strip_generic_images(records: list[dict[str, Any]]) -> int:
    """汎用ロゴ画像を records の media から外す。変更した record 数を返す。

    pattern 判定に加え、同じ画像 URL が 3 記事 (permalink) 以上で使い回されて
    いたらサイト共通ロゴと見なす。matched_x_post (実 X ポスト紐付け) の media
    は対象外。
    """
    img_articles: dict[str, set[str]] = {}
    for r in records:
        if r.get("matched_x_post"):
            continue
        for m in r.get("media") or []:
            u = str(m.get("url") or "")
            if u:
                img_articles.setdefault(u, set()).add(str(r.get("permalink") or ""))
    overused = {u for u, arts in img_articles.items() if len(arts) >= 3}
    changed = 0
    for r in records:
        if r.get("matched_x_post"):
            continue
        media = r.get("media") or []
        kept = [
            m for m in media
            if str(m.get("url") or "")
            and not is_generic_og_image(str(m.get("url") or ""))
            and str(m.get("url") or "") not in overused
        ]
        if len(kept) != len(media):
            r["media"] = kept
            r["has_media"] = bool(kept)
            changed += 1
    return changed


def _parse_iso_utc(value: str) -> datetime | None:
    """ISO 文字列を tz-aware UTC datetime に (naive は UTC と見なす)。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def attach_matching_photo_posts(
    records: list[dict[str, Any]],
    *,
    fetch_fn: Any = None,
    handles: list[str] | None = None,
    max_age_days: float = 3.0,
    player: str = PLAYER,
) -> int:
    """記事発言 record に、記事日付近傍の本人メンション写真付き実 X ポストを紐付ける。

    2026-07-16 user「その記事の写真にあったポストがあれば響く」: 記事 URL の
    OGP カードではなく、巨人系媒体 X アカの写真付き実ポスト (x.com URL) を
    permalink に据えると、配信側 (_embed_permalink_or_empty gate) を通って
    X で写真 embed が出る (坂本型)。

    RSSHub twitter/user timeline は直近分しか返さないため、マッチするのは
    feeder 実行時点に近い新規記事のみ (過去 backlog は対象外 = text-only 配信)。
    マッチした record 数を返す。ネットワーク失敗は silent skip (0 件マッチ扱い)。
    """
    from src import video_radar as vr

    use_handles = handles or vr._BUZZ_HANDLES
    fetch = fetch_fn or vr._cached_default_fetch
    feed_urls = {h: f"{vr._RSSHUB_BASE}/twitter/user/{h}?limit=40" for h in use_handles}
    try:
        fetched = vr.prefetch_feeds(list(feed_urls.values()), fetch)
    except Exception as exc:  # noqa: BLE001
        LOG.info("photo_post_match skip: %r", exc)
        return 0
    name_key = player.replace(" ", "").replace("　", "")
    photo_posts: list[dict[str, Any]] = []
    for h in use_handles:
        xml = fetched.get(feed_urls[h])
        if not isinstance(xml, str):
            continue
        for item in vr._extract_rss_items(xml):
            if not item.get("has_image"):
                continue
            text = str(item.get("text") or "").replace(" ", "").replace("　", "")
            if name_key not in text:
                continue
            if not item.get("url") or item.get("published_at") is None:
                continue
            photo_posts.append(item)
    if not photo_posts:
        return 0
    matched = 0
    for r in records:
        if r.get("matched_x_post"):
            continue
        created = _parse_iso_utc(str(r.get("created_at") or ""))
        if created is None:
            continue
        best: tuple[float, dict[str, Any]] | None = None
        for p in photo_posts:
            delta = abs((p["published_at"] - created).total_seconds())
            if delta <= max_age_days * 86400 and (best is None or delta < best[0]):
                best = (delta, p)
        if best is not None:
            post = best[1]
            r["permalink"] = str(post["url"])
            r["has_media"] = True
            r["media"] = [{"url": str(post["url"]), "type": "photo"}]
            r["matched_x_post"] = True
            matched += 1
    return matched


def build_record(
    *, quote: str, url: str, published_iso: str, publisher: str, idx: int,
    image_url: str = "",
) -> dict[str, Any]:
    media = [{"url": image_url, "type": "photo"}] if image_url else []
    return {
        "tweet_id": _stable_id(url, idx),
        "text": quote,
        "created_at": published_iso,
        "public_metrics": {},
        "lang": "ja",
        "has_media": bool(image_url),
        "media": media,
        "permalink": url,
        "source_name": publisher or "",
        "source_handle": "",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def collect(
    *,
    queries: list[str],
    api_key: str,
    max_scan: int,
    target: int,
    body_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    all_entries: list[Any] = []
    for q in queries:
        feed = feedparser.parse(_rss_url(q))
        LOG.info("rss_entries=%d query=%r", len(feed.entries), q)
        all_entries.extend(feed.entries)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_urls: set[str] = set()
    stats = {"scanned": 0, "resolved": 0, "body_ok": 0, "with_quotes": 0, "quotes": 0}
    for entry in all_entries:
        if len(records) >= target or stats["scanned"] >= max_scan:
            break
        link = getattr(entry, "link", "") or ""
        real = resolve_google_news_url(link) if is_google_news_url(link) else link
        if not real or real in seen_urls:
            continue
        seen_urls.add(real)
        stats["scanned"] += 1
        stats["resolved"] += 1
        html = _fetch_html(real)
        title_clean, publisher = split_publisher_from_title(getattr(entry, "title", ""))
        body = extract_article_body_excerpt(html, real, max_chars=body_chars, title=title_clean)
        if not body:
            continue
        stats["body_ok"] += 1
        og_image = _extract_og_image(html)
        quotes = gemini_extract_quotes(title_clean, body, api_key=api_key)
        if quotes:
            stats["with_quotes"] += 1
        published_iso = _entry_published_iso(entry)
        for i, q in enumerate(quotes):
            key = _normalize_for_dedup(q)
            if not key or key in seen:
                continue
            seen.add(key)
            records.append(
                build_record(
                    quote=q, url=real, published_iso=published_iso,
                    publisher=publisher or "", idx=i, image_url=og_image,
                )
            )
            stats["quotes"] += 1
    return records, stats


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def merge_records(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_text: dict[str, dict[str, Any]] = {}
    for rec in existing + incoming:
        key = _normalize_for_dedup(str(rec.get("text") or ""))
        if not key:
            continue
        by_text.setdefault(key, rec)
    # 古い順 (created_at asc) — 配信は oldest first なので保存も合わせておく
    return sorted(by_text.values(), key=lambda r: r.get("created_at") or "")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def upload_gcs(*, records: list[dict[str, Any]], bucket: str, key: str) -> str:
    from google.cloud import storage
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    payload += "\n" if payload else ""
    storage.Client().bucket(bucket).blob(key).upload_from_string(
        payload, content_type="application/x-ndjson"
    )
    return f"gs://{bucket}/{key}"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO
    )
    parser = argparse.ArgumentParser(description="吉川尚輝 名言 feeder (RSS → 本人発言抽出 → archive)")
    parser.add_argument("--queries", default=",".join(DEFAULT_QUERIES),
                        help="カンマ区切りの検索クエリ (Googleニュース)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--max-scan", type=int, default=30, help="解決を試みる記事数の上限")
    parser.add_argument("--target", type=int, default=15, help="集める名言レコードの上限")
    parser.add_argument("--body-chars", type=int, default=2000)
    parser.add_argument("--gcs-bucket", default=DEFAULT_GCS_BUCKET)
    parser.add_argument("--gcs-key", default=DEFAULT_GCS_KEY)
    parser.add_argument("--upload-gcs", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="保存せず抽出結果を表示")
    args = parser.parse_args(argv)

    # .env から GEMINI_API_KEY を読む (shell source しない、dotenv 経由)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        LOG.error("GEMINI_API_KEY 未設定。abort.")
        return 1

    queries = [s.strip() for s in args.queries.split(",") if s.strip()]
    records, stats = collect(
        queries=queries,
        api_key=api_key,
        max_scan=args.max_scan,
        target=args.target,
        body_chars=args.body_chars,
    )
    LOG.info("collect_stats=%s", json.dumps(stats, ensure_ascii=False))

    print(f"\n=== 抽出された {PLAYER} の名言: {len(records)} 件 ===")
    for r in records:
        date = (r.get("created_at") or "")[:10]
        print(f"[{date}] {r['text']}")
        print(f"    └ {r.get('source_name','')} {r.get('permalink','')[:70]}")

    if args.dry_run:
        print("\n(dry-run: 保存しません)")
        return 0

    out_path = Path(args.output)
    merged = merge_records(_load_jsonl(out_path), records)
    # 2026-07-16: 写真付き実 X ポスト紐付け (新規分のみマッチ可) + 汎用ロゴ除去
    # (backlog 含む全件に適用、jsports ogp-image.png 使い回しの実事故対応)
    matched = attach_matching_photo_posts(merged)
    stripped = strip_generic_images(merged)
    LOG.info("photo_post_matched=%d generic_images_stripped=%d", matched, stripped)
    write_jsonl(out_path, merged)
    LOG.info("wrote local=%s total=%d", out_path, len(merged))

    if args.upload_gcs:
        uri = upload_gcs(records=merged, bucket=args.gcs_bucket, key=args.gcs_key)
        LOG.info("uploaded=%s", uri)
    return 0


if __name__ == "__main__":
    sys.exit(main())
