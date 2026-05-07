"""NOMOTOKE-LINEUP-FROM-X-001 — operator CLI / cron entrypoint that
turns a 巨人公式X (TokyoGiants) lineup tweet into a
``nomotoke_card_lineup_v1`` WP draft.

Cost / safety
=============

- Pulls the existing TokyoGiants RSS feed (already a configured source);
  no new external dependency. Each invocation = 1 RSS fetch.
- Cron firing in the pre-game window (typically 17:00–18:30 JST on
  game days) catches the lineup tweet within minutes of posting.
- Title-prefix dedup against WP avoids creating duplicates when the
  cron fires repeatedly while the same tweet is on the feed.
- Source-only fact extraction. No Gemini, no body scraping.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_VENDOR = str(ROOT / "vendor")
_SRC = str(ROOT / "src")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.source_x_lineup_extractor import parse_x_lineup_tweet  # noqa: E402

EXIT_OK = 0
EXIT_FETCH_FAILED = 11
EXIT_NO_TWEET = 13
EXIT_RENDER_FAILED = 14
EXIT_WP_FAILED = 20

_TOKYOGIANTS_RSS_URL = (
    "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/TokyoGiants"
)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.run_lineup_from_x",
        description=(
            "Poll the 巨人公式X RSS feed for today's lineup tweet, parse "
            "the 9-row batting order, and create a lineup_v1 WP draft. "
            "Defaults to dry-run (no WP write)."
        ),
    )
    p.add_argument(
        "--mode",
        choices=("dry-run", "draft"),
        default="dry-run",
    )
    p.add_argument(
        "--rss-url",
        default=_TOKYOGIANTS_RSS_URL,
        help="RSS feed URL; default = TokyoGiants RSSHub bridge",
    )
    p.add_argument(
        "--max-entries",
        type=int,
        default=10,
        help="how many recent feed entries to scan (default 10)",
    )
    return p


def _fetch_lineup_tweet(
    *, rss_url: str, max_entries: int, logger: logging.Logger
):
    try:
        import feedparser
    except Exception as exc:
        logger.error("feedparser_unavailable: %s", exc)
        return None, f"feedparser_unavailable:{exc.__class__.__name__}"
    fp = feedparser.parse(rss_url)
    for entry in fp.entries[:max_entries]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        published = entry.get("published", "") or entry.get("updated", "")
        link = entry.get("link", "")
        parsed = parse_x_lineup_tweet(title, summary)
        if parsed and parsed["lineup"]:
            return (
                {
                    "lineup": parsed["lineup"],
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": published,
                },
                "",
            )
    return None, "no_lineup_tweet_in_feed"


def _build_payload(*, parsed_tweet: dict, today: datetime) -> dict:
    """Build the renderer-shaped data_preview for lineup_v1."""
    date_label = today.strftime("%Y年%-m月%-d日")
    # Without a paired schedule fetch we can't know league_label / home /
    # away precisely. Use safe defaults that the renderer accepts.
    return {
        "team_name": "巨人",
        "own_lineup": parsed_tweet["lineup"],
        "date_label": date_label,
        "league_label": "セ・リーグ 公式戦",
        "home": "巨人",
        "away": "対戦相手",
        "opponent_name": "対戦相手",
        "live_url": parsed_tweet.get("link", ""),
        "source_url": parsed_tweet.get("link", ""),
        "source_name": "巨人公式X",
        "source_label": "巨人公式X",
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("lineup_from_x")

    output: dict = {
        "ok": False,
        "mode": args.mode,
        "skip_reason": "",
    }

    fetched, err = _fetch_lineup_tweet(
        rss_url=args.rss_url,
        max_entries=args.max_entries,
        logger=logger,
    )
    if err:
        output["skip_reason"] = err
        # No lineup tweet in the feed is the routine "nothing to do"
        # condition for the cron — exit 0 so Scheduler doesn't alarm.
        output["ok"] = True
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_OK

    output["lineup_rows"] = len(fetched["lineup"])
    output["source_url"] = fetched.get("link", "")

    payload = _build_payload(parsed_tweet=fetched, today=datetime.now())

    os.environ.setdefault("ENABLE_NOMOTOKE_CARD_TEMPLATES", "1")
    from src.nomotoke_card_renderer import select_renderer

    try:
        renderer = select_renderer("nomotoke_card_lineup_v1")
    except (RuntimeError, ValueError) as exc:
        output["skip_reason"] = f"renderer_unavailable:{exc.__class__.__name__}"
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_RENDER_FAILED

    result = renderer(payload)
    if not result.get("validation_ok"):
        output["skip_reason"] = (
            f"renderer_validation_failed:{result.get('skip_reason', '')}"
        )
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_RENDER_FAILED

    output["title"] = result.get("title") or ""
    output["body_bytes"] = len(result.get("content_html") or "")
    if args.mode == "dry-run":
        output["body_preview"] = (result.get("content_html") or "")[:500]

    if args.mode == "draft":
        from dotenv import load_dotenv

        load_dotenv()
        from src.wp_client import WPClient

        try:
            wp = WPClient()
        except Exception as exc:
            output["skip_reason"] = f"wp_client_unavailable:{exc.__class__.__name__}"
            print(json.dumps(output, ensure_ascii=False))
            return EXIT_WP_FAILED

        # Title-prefix dedup (same rationale as postgame/broadcast).
        try:
            import requests as _r

            search_resp = _r.get(
                f"{os.environ['WP_URL']}/wp-json/wp/v2/posts",
                params={
                    "search": result["title"][:40],
                    "per_page": 5,
                    "status": "any",
                    "context": "edit",
                },
                auth=(os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"]),
                timeout=10,
            )
            existing = None
            if search_resp.status_code < 400:
                for hit in search_resp.json():
                    hit_title = (hit.get("title") or {}).get("rendered", "")
                    if hit_title.startswith(result["title"][:30]):
                        existing = hit
                        break
        except Exception:
            existing = None
        if existing and existing.get("id"):
            output["skip_reason"] = "already_in_wp"
            output["existing_post_id"] = existing.get("id")
            output["existing_status"] = existing.get("status", "")
            output["ok"] = True
            print(json.dumps(output, ensure_ascii=False))
            return EXIT_OK

        try:
            categories_map = json.loads(
                (ROOT / "config" / "categories.json").read_text(encoding="utf-8")
            )
            category_id = int(categories_map.get("試合速報") or 0)
        except Exception:
            category_id = 0
        try:
            post_id = wp.create_post(
                title=result["title"],
                content=result["content_html"],
                categories=[category_id] if category_id else None,
                status="draft",
                source_url=fetched.get("link", ""),
                caller="lineup_from_x",
                source_lane="lineup_from_x",
            )
        except Exception as exc:
            output["skip_reason"] = f"wp_create_failed:{exc.__class__.__name__}"
            print(json.dumps(output, ensure_ascii=False))
            return EXIT_WP_FAILED
        output["post_id"] = post_id

    output["ok"] = True
    print(json.dumps(output, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
