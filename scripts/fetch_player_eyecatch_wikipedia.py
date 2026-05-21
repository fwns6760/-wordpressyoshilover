"""Fetch player eyecatch images from Wikipedia / Wikimedia Commons.

Targets: ``config/player_eyecatch_map.json`` entries whose value is ``null``
(image lookup previously failed). Tries ja Wikipedia → en Wikipedia →
Wikimedia Commons direct search, then verifies the license metadata via the
Commons API. Only public-domain / CC-BY / CC-BY-SA images are accepted.

Two-stage operation:

    # 1) preview — no WP write, write structured result to a JSON report.
    python scripts/fetch_player_eyecatch_wikipedia.py --dry-run \
        --report out/eyecatch_wikipedia_preview.json

    # 2) commit — upload accepted images to WP and update the cache.
    python scripts/fetch_player_eyecatch_wikipedia.py --commit \
        --report out/eyecatch_wikipedia_commit.json

The dry-run report lets the operator audit license / attribution / URL
before any mutation. ``--commit`` reads the same cache file directly and
re-resolves; it does not depend on the dry-run report.

Filtering flags:

    --include-only "ウィットリー,キャベッジ,..."   # restrict to specific names
    --limit N                                    # cap probes per run

Cost: Wikipedia / Commons API は無料、 rate limit は 1 req / sec を厳守
(``--sleep`` で調整可)。

Out of scope:
- 巨人公式 / NPB 公式 image scrape (著作権懸念)
- Twitter / Instagram (肖像権 / TOS)
- 既に non-null cache hit がある entry の上書き
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

CACHE_PATH = ROOT / "config" / "player_eyecatch_map.json"
USER_AGENT = (
    "yoshilover-eyecatch-fetcher/1.0 "
    "(https://yoshilover.com; contact: fwns6760@gmail.com)"
)

# Manual romanization hints for foreign players. Empty means the script
# will fall through to ja Wikipedia only.
FOREIGN_ROMAJI: dict[str, list[str]] = {
    "ウィットリー": ["Foster Whitley"],
    "Ｆ．ウィットリー": ["Foster Whitley"],
    "リチャード": ["Richard Sunagawa", "リチャード (野球)"],
    "*キャベッジ": ["Trey Cabbage"],
    "キャベッジ": ["Trey Cabbage"],
    "ハワード": ["Spencer Howard"],
    "マタ": ["Raffy Lantigua"],
    "*マルティネス": ["Carlos Martinez", "C.C. Martinez"],
    "マルティネス": ["Carlos Martinez", "C.C. Martinez"],
    "ルシアーノ": ["Marco Luciano"],
    "ティマ": ["Juan Then"],
    "*バルドナード": ["John Bardonado", "Baldonado"],
}

SAFE_LICENSE_PATTERNS = [
    # CC BY / CC BY-SA, optional version (4.0, 3.0, 2.0, ...). Wiki returns
    # labels like "CC BY-SA 4.0" / "CC BY 3.0" / "CC-BY-SA-4.0" / "cc-by-sa".
    re.compile(r"^cc[\s\-]?by([\s\-]sa)?([\s\-]\d+(\.\d+)?)?$", re.IGNORECASE),
    re.compile(r"^cc0(\s.*)?$", re.IGNORECASE),
    re.compile(r"^public[\s\-]domain(\s.*)?$", re.IGNORECASE),
    re.compile(r"^pd[\s\-]?.*$", re.IGNORECASE),
]

UNSAFE_LICENSE_TOKENS = ("fair use", "non-free", "copyrighted", "all rights reserved")

# Same surname / 同姓異人 ambiguity — these names hit a Wikipedia article
# that is NOT the 巨人 player we mean. Manual review required, do not
# auto-fetch.
MANUAL_REVIEW_NAMES = {
    # 巨人「松本剛」(内野手) ≠ ja wiki「松本剛 (野球)」 (日ハム外野手)
    "松本剛",
    # 巨人「リチャード」(助っ人) ≠ ja wiki「リチャード (野球)」 (ソフトバンク 砂川リチャード)
    "リチャード",
    # 巨人「ルシアーノ・フェルナンド」 ≠ en wiki「Marco Luciano」 (SF Giants /
    # NYY 系 MLB マイナー、 ブラジル系の巨人助っ人とは別人懸念)
    "ルシアーノ",
}

logger = logging.getLogger("eyecatch_wikipedia")


@dataclass
class ProbeResult:
    name: str
    status: str  # accepted | rejected_license | not_found | error | upload_failed | committed
    source: str | None = None  # ja_wiki | en_wiki | commons
    image_url: str | None = None
    license: str | None = None
    artist: str | None = None
    attribution: str | None = None
    commons_file: str | None = None
    wp_media_id: int | None = None
    reason: str | None = None
    aliases_tried: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Wikipedia / Commons API helpers
# ---------------------------------------------------------------------------


def _api_get(endpoint: str, params: dict[str, str], sleep_s: float) -> dict[str, Any] | None:
    params = {**params, "format": "json"}
    qs = urllib.parse.urlencode(params)
    url = f"{endpoint}?{qs}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        time.sleep(sleep_s)
        return resp.json()
    except Exception as exc:
        logger.warning("api_get_failed url=%s err=%s", endpoint, exc)
        return None


def _pageimage_from_wiki(lang: str, title: str, sleep_s: float) -> tuple[str | None, str | None]:
    """Return ``(commons_filename, page_image_url)`` for a Wikipedia page."""
    endpoint = f"https://{lang}.wikipedia.org/w/api.php"
    data = _api_get(
        endpoint,
        {
            "action": "query",
            "prop": "pageimages|pageprops",
            "titles": title,
            "piprop": "original|name",
            "pithumbsize": "800",
            "redirects": "1",
        },
        sleep_s,
    )
    if not data:
        return None, None
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if "missing" in page:
            continue
        commons_filename = page.get("pageimage")
        original = page.get("original") or {}
        image_url = original.get("source")
        if commons_filename or image_url:
            return commons_filename, image_url
    return None, None


def _commons_search(query: str, sleep_s: float) -> str | None:
    """Search Commons for a file whose title contains *query*."""
    data = _api_get(
        "https://commons.wikimedia.org/w/api.php",
        {
            "action": "query",
            "list": "search",
            "srsearch": f"{query} filetype:bitmap",
            "srnamespace": "6",  # File namespace
            "srlimit": "3",
        },
        sleep_s,
    )
    if not data:
        return None
    for hit in (data.get("query") or {}).get("search") or []:
        title = hit.get("title", "")
        if title.startswith("File:") and any(
            ext in title.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
        ):
            return title.removeprefix("File:")
    return None


def _commons_imageinfo(filename: str, sleep_s: float) -> dict[str, Any] | None:
    data = _api_get(
        "https://commons.wikimedia.org/w/api.php",
        {
            "action": "query",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
        },
        sleep_s,
    )
    if not data:
        return None
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if infos:
            return infos[0]
    return None


def _check_license(extmeta: dict[str, Any]) -> tuple[bool, str, str, str]:
    """Return ``(safe, license_label, artist, full_attribution)``."""
    license_name = ((extmeta.get("LicenseShortName") or {}).get("value") or "").strip()
    license_full = ((extmeta.get("License") or {}).get("value") or "").strip()
    artist_html = ((extmeta.get("Artist") or {}).get("value") or "").strip()
    artist = re.sub(r"<[^>]+>", "", artist_html).strip()
    credit_html = ((extmeta.get("Credit") or {}).get("value") or "").strip()
    credit = re.sub(r"<[^>]+>", "", credit_html).strip()

    label = license_name or license_full
    lc = label.lower()
    if any(tok in lc for tok in UNSAFE_LICENSE_TOKENS):
        return False, label, artist, ""
    safe = any(p.match(label) for p in SAFE_LICENSE_PATTERNS)
    full = f"{label} / {artist}" if artist else label
    if credit and credit not in full:
        full = f"{full} (source: {credit})"
    return safe, label, artist, full


# ---------------------------------------------------------------------------
# Resolution logic
# ---------------------------------------------------------------------------


def _candidate_titles(name: str) -> list[tuple[str, str]]:
    """Return ``[(lang, page_title), ...]`` to try in order."""
    bare = name.lstrip("*")  # remove leading marker if any
    out: list[tuple[str, str]] = []
    # ja Wikipedia first
    out.append(("ja", bare))
    out.append(("ja", f"{bare} (野球)"))
    # foreign players: en Wikipedia with romaji
    for romaji in FOREIGN_ROMAJI.get(name, []):
        out.append(("en", romaji))
    return out


def resolve_one(name: str, sleep_s: float, allow_commons_direct: bool = False) -> ProbeResult:
    result = ProbeResult(name=name, status="not_found")

    if name in MANUAL_REVIEW_NAMES:
        result.reason = "manual_review_same_surname_ambiguity"
        return result

    commons_filename: str | None = None
    page_image_url: str | None = None
    source_lang: str | None = None

    for lang, title in _candidate_titles(name):
        result.aliases_tried.append(f"{lang}:{title}")
        cf, url = _pageimage_from_wiki(lang, title, sleep_s)
        if cf or url:
            commons_filename, page_image_url = cf, url
            source_lang = lang
            break

    # Fallback: direct Commons file search (disabled by default because
    # the query is loose enough to hit place names / random objects).
    # Enable per-run with ``--allow-commons-direct`` if needed.
    if not commons_filename and not page_image_url and allow_commons_direct:
        bare = name.lstrip("*")
        for q in [bare, *FOREIGN_ROMAJI.get(name, [])]:
            result.aliases_tried.append(f"commons:{q}")
            cf = _commons_search(q, sleep_s)
            if cf:
                commons_filename = cf
                source_lang = "commons"
                break

    if not commons_filename and not page_image_url:
        result.reason = "no_wiki_page_match"
        return result

    # License check requires the Commons file metadata.
    if commons_filename:
        info = _commons_imageinfo(commons_filename, sleep_s)
        if not info:
            result.reason = "commons_imageinfo_unavailable"
            result.status = "error"
            return result
        result.image_url = info.get("url") or page_image_url
        result.commons_file = commons_filename
        extmeta = info.get("extmetadata") or {}
        safe, label, artist, attribution = _check_license(extmeta)
        result.license = label or "(unknown)"
        result.artist = artist or None
        result.attribution = attribution
        result.source = {"ja": "ja_wiki", "en": "en_wiki", "commons": "commons"}.get(
            source_lang or "", source_lang
        )
        if not safe:
            result.status = "rejected_license"
            result.reason = f"unsafe_or_unknown_license={label!r}"
            return result
        result.status = "accepted"
        return result

    # Page image URL only (no Commons file → cannot verify license)
    result.image_url = page_image_url
    result.source = {"ja": "ja_wiki", "en": "en_wiki"}.get(source_lang or "", source_lang)
    result.status = "rejected_license"
    result.reason = "no_commons_file_for_license_check"
    return result


# ---------------------------------------------------------------------------
# WP upload + cache update
# ---------------------------------------------------------------------------


def _patch_media_attribution(wp: Any, media_id: int, attribution: str, source_url: str) -> bool:
    """PATCH /wp/v2/media/<id> with alt_text + caption for attribution.

    CC-BY / CC-BY-SA requires attribution. The caption is rendered by
    WP themes near the image and satisfies the license attribution.
    """
    try:
        api = wp.api  # e.g. https://yoshilover.com/wp-json/wp/v2
        body = {
            "alt_text": attribution[:250],
            "caption": f"{attribution} (source: {source_url})",
            "description": f"Imported from Wikimedia. {attribution}. Source: {source_url}",
        }
        resp = requests.post(
            f"{api}/media/{media_id}",
            json=body,
            auth=(wp.user, wp.app_password),
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.warning(
                "patch_media_attribution_failed media_id=%s status=%s body=%s",
                media_id,
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True
    except Exception as exc:
        logger.warning("patch_media_attribution_exception media_id=%s err=%s", media_id, exc)
        return False


def upload_to_wp(result: ProbeResult) -> ProbeResult:
    if result.status != "accepted" or not result.image_url:
        return result
    from src.wp_client import WPClient

    wp = WPClient()
    # upload.wikimedia.org rate-limits generic Mozilla UAs with HTTP 429.
    # Fetch the image bytes ourselves with the Wikipedia-compliant UA,
    # then hand the bytes to WPClient.upload_generated_image (which does
    # not re-fetch the URL).
    import hashlib

    try:
        img_resp = requests.get(
            result.image_url,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        img_resp.raise_for_status()
        image_data = img_resp.content
        content_type = (img_resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
    except Exception as exc:
        result.status = "upload_failed"
        result.reason = f"image_fetch_failed={exc!r}"
        return result

    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
    filename = hashlib.md5(result.image_url.encode()).hexdigest()[:12] + f".{ext}"
    media_id = wp.upload_generated_image(image_data, filename, content_type)
    if not media_id:
        result.status = "upload_failed"
        result.reason = "wp_upload_returned_zero"
        return result
    result.wp_media_id = int(media_id)
    # Set CC attribution on the new media item. License is a legal
    # requirement; failure here is logged but not fatal (caller can
    # backfill the caption later).
    if result.attribution:
        ok = _patch_media_attribution(
            wp, result.wp_media_id, result.attribution, result.image_url or ""
        )
        if not ok:
            result.reason = "attribution_patch_failed_but_upload_ok"
    result.status = "committed"
    return result


def update_cache(results: list[ProbeResult]) -> int:
    if not CACHE_PATH.exists():
        raise RuntimeError(f"cache file missing: {CACHE_PATH}")
    data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    updated = 0
    for r in results:
        if r.status != "committed" or not r.wp_media_id:
            continue
        data[r.name] = {
            "id": r.wp_media_id,
            "title": f"{r.name.lstrip('*')} - Wikimedia ({r.license})"
            if r.license
            else r.name.lstrip("*"),
        }
        updated += 1
    if updated:
        CACHE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return updated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="探索のみ、 WP upload しない (既定)")
    p.add_argument("--commit", action="store_true", help="accepted を WP upload し cache 更新")
    p.add_argument("--report", required=True, help="結果 JSON の出力先")
    p.add_argument("--include-only", default="", help="comma-separated names; 空なら全 null")
    p.add_argument("--limit", type=int, default=0, help="0=制限なし、 N で先頭 N 件のみ")
    p.add_argument("--sleep", type=float, default=1.0, help="API 間隔 (秒)")
    p.add_argument(
        "--allow-commons-direct",
        action="store_true",
        help="Commons direct file search を許可 (default OFF、 地名 hit など noise 大)",
    )
    args = p.parse_args(argv)

    if args.commit and args.dry_run:
        print("ERROR: --commit と --dry-run は併用不可", file=sys.stderr)
        return 2
    do_commit = bool(args.commit)
    if not do_commit:
        # dry-run is default
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not CACHE_PATH.exists():
        print(f"ERROR: cache file missing: {CACHE_PATH}", file=sys.stderr)
        return 2
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    null_names = [n for n, v in cache.items() if v is None]
    include = {n.strip() for n in args.include_only.split(",") if n.strip()}
    if include:
        null_names = [n for n in null_names if n in include]
    if args.limit > 0:
        null_names = null_names[: args.limit]

    print(
        f"[plan] mode={'commit' if do_commit else 'dry-run'} "
        f"targets={len(null_names)} sleep={args.sleep}s"
    )
    for n in null_names:
        print(f"  - {n}")

    results: list[ProbeResult] = []
    for i, name in enumerate(null_names, 1):
        print(f"[{i}/{len(null_names)}] {name} ...")
        try:
            r = resolve_one(name, args.sleep, allow_commons_direct=args.allow_commons_direct)
        except Exception as exc:
            r = ProbeResult(name=name, status="error", reason=f"resolve_exception={exc!r}")
        if do_commit:
            try:
                r = upload_to_wp(r)
            except Exception as exc:
                r.status = "upload_failed"
                r.reason = f"upload_exception={exc!r}"
        results.append(r)
        print(
            f"  → status={r.status} source={r.source} license={r.license} "
            f"media_id={r.wp_media_id} reason={r.reason}"
        )

    updated = 0
    if do_commit:
        updated = update_cache(results)
        print(f"[cache] updated entries: {updated}")

    summary = {
        "mode": "commit" if do_commit else "dry-run",
        "total": len(results),
        "accepted": sum(1 for r in results if r.status == "accepted"),
        "rejected_license": sum(1 for r in results if r.status == "rejected_license"),
        "not_found": sum(1 for r in results if r.status == "not_found"),
        "error": sum(1 for r in results if r.status == "error"),
        "upload_failed": sum(1 for r in results if r.status == "upload_failed"),
        "committed": sum(1 for r in results if r.status == "committed"),
        "cache_updated": updated,
        "results": [asdict(r) for r in results],
    }
    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[done] mode={summary['mode']} accepted={summary['accepted']} "
        f"rejected_license={summary['rejected_license']} "
        f"not_found={summary['not_found']} error={summary['error']} "
        f"upload_failed={summary['upload_failed']} committed={summary['committed']} "
        f"report={out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
