"""NOMOTOKE-BROADCAST-FROM-YAHOO-001 — operator CLI that turns the
Yahoo Sportsnavi `/top` page's 放送予定 table into a
``nomotoke_card_broadcast_v1`` WP draft for any upcoming Giants game.

The 放送予定 block is only present in the static HTML when the game has
not started yet — once first pitch is thrown, Yahoo replaces the section
with the live score. So this CLI is intended for試合日朝〜試合直前 use.

Cost: 1 fetch per invocation, ondemand. No Gemini, no Scheduler.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
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

from src.source_yahoo_boxscore_extractor import (  # noqa: E402
    broadcast_card_payload,
    parse_yahoo_broadcast_html,
)


EXIT_OK = 0
EXIT_INVALID_URL = 10
EXIT_FETCH_FAILED = 11
EXIT_PARSE_FAILED = 12
EXIT_RENDER_FAILED = 13
EXIT_WP_FAILED = 20


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.run_broadcast_from_yahoo",
        description=(
            "Turn the 放送予定 table of a Yahoo Sportsnavi `/top` page "
            "into a broadcast_v1 WP draft. Default --mode dry-run. "
            "Source-only — never adds tokens; never calls Gemini."
        ),
    )
    p.add_argument(
        "url",
        nargs="?",
        default="",
        help="Yahoo Sportsnavi game URL (https://baseball.yahoo.co.jp/npb/game/<id>/top)",
    )
    p.add_argument(
        "--mode",
        choices=("dry-run", "draft"),
        default="dry-run",
    )
    p.add_argument(
        "--auto-discover",
        action="store_true",
        help=(
            "Skip explicit URL: probe the Yahoo schedule for today's "
            "pre-game Giants game (not yet completed) and use that. "
            "Intended for Cloud Scheduler / cron use in the morning."
        ),
    )
    p.add_argument(
        "--from-file",
        default="",
        help="(test-only) read HTML from a local file instead of fetching",
    )
    return p


def _auto_discover_giants_pregame_url(
    *, logger: logging.Logger, lookahead_days: int = 3
) -> tuple[str, str]:
    """Probe Yahoo schedule for the *next* Giants pre-game URL.

    Returns ``(url, error)``. Looks at today first, then up to
    ``lookahead_days`` days forward — so a job that runs at 11:30 JST
    on an off-day can still find tomorrow's pre-game and create the
    broadcast draft a day in advance. The URL points to the ``/top``
    page (which carries the 放送予定 table).
    """
    from datetime import datetime, timedelta

    from zoneinfo import ZoneInfo
    from src.source_html_fetcher import RequestsHttpClient
    from src.source_yahoo_schedule_extractor import find_giants_pregame_games

    http = RequestsHttpClient()
    today = datetime.now(ZoneInfo("Asia/Tokyo"))
    for delta in range(0, lookahead_days + 1):
        d = today + timedelta(days=delta)
        date_param = f"{d.year}-{d.month:02d}-{d.day:02d}"
        url = f"https://baseball.yahoo.co.jp/npb/schedule/?date={date_param}"
        try:
            resp = http.get(
                url,
                headers={"User-Agent": "YoshiloverBot/1.0"},
                timeout=15.0,
            )
        except Exception as exc:
            logger.warning("schedule_fetch_failed (%s): %s", date_param, exc)
            continue
        if resp.status_code >= 400:
            logger.warning("schedule_status_%s for %s", resp.status_code, date_param)
            continue
        pregame = find_giants_pregame_games(resp.text)
        if pregame:
            target = pregame[0]
            # /top carries 放送予定; the schedule URL points to /index (or
            # any page suffix). Replace the trailing path segment with /top.
            top_url = re.sub(r"/[^/]+$", "/top", target["url"])
            return top_url, ""
    return "", "no_pregame_giants_game_within_lookahead"


def _fetch_html(url: str, *, logger: logging.Logger) -> tuple[str, str]:
    from src.source_html_fetcher import RequestsHttpClient

    http = RequestsHttpClient()
    try:
        resp = http.get(
            url,
            headers={"User-Agent": "YoshiloverBot/1.0"},
            timeout=15.0,
        )
    except Exception as exc:
        logger.error("http_fetch_failed: %s", exc)
        return "", f"http_fetch_failed:{exc.__class__.__name__}"
    if resp.status_code >= 400:
        return "", f"http_status_{resp.status_code}"
    return resp.text, ""


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("broadcast_from_yahoo")

    output: dict = {
        "ok": False,
        "mode": args.mode,
        "url": args.url,
        "skip_reason": "",
    }

    url = (args.url or "").strip()
    if args.auto_discover and not url:
        discovered_url, err = _auto_discover_giants_pregame_url(logger=logger)
        if err:
            output["skip_reason"] = err
            output["ok"] = True  # idempotent "nothing-to-do" for cron
            print(json.dumps(output, ensure_ascii=False))
            # exit 0 so Cloud Scheduler doesn't alarm on the routine
            # "no pre-game game today" condition (off-days, evenings).
            return EXIT_OK
        url = discovered_url
        output["url"] = url
        output["auto_discovered"] = True
    if not (url.startswith("http://") or url.startswith("https://")):
        output["skip_reason"] = "invalid_url"
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_INVALID_URL

    if args.from_file:
        try:
            html = Path(args.from_file).read_text(encoding="utf-8")
        except Exception as exc:
            output["skip_reason"] = f"read_failed:{exc.__class__.__name__}"
            print(json.dumps(output, ensure_ascii=False))
            return EXIT_FETCH_FAILED
    else:
        html, err = _fetch_html(url, logger=logger)
        if err:
            output["skip_reason"] = err
            print(json.dumps(output, ensure_ascii=False))
            return EXIT_FETCH_FAILED

    parsed = parse_yahoo_broadcast_html(html)
    if parsed is None:
        output["skip_reason"] = "parse_failed_or_game_already_started"
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_PARSE_FAILED

    payload = broadcast_card_payload(parsed=parsed, source_url=url)
    os.environ.setdefault("ENABLE_NOMOTOKE_CARD_TEMPLATES", "1")
    from src.nomotoke_card_renderer import select_renderer

    try:
        renderer = select_renderer("nomotoke_card_broadcast_v1")
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
    output["broadcast_rows"] = len(parsed["rows"])
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

        # Dedup is delegated to WPClient.create_post →
        # find_recent_post_by_title (24h source_url-aware match).

        try:
            categories_map = json.loads(
                (ROOT / "config" / "categories.json").read_text(encoding="utf-8")
            )
            category_id = int(categories_map.get("コラム") or 0)
        except Exception:
            category_id = 0
        try:
            post_id = wp.create_post(
                title=result["title"],
                content=result["content_html"],
                categories=[category_id] if category_id else None,
                status="draft",
                source_url=url,
                caller="broadcast_from_yahoo",
                source_lane="broadcast_from_yahoo",
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
