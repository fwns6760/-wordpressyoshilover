"""NOMOTOKE-POSTGAME-FROM-NPB-BOXSCORE-001 — operator CLI that turns a
Yahoo Sportsnavi NPB game URL into a ``nomotoke_card_postgame_v1`` WP
draft (or dry-run preview).

Cost budget
===========

- 1 HTTP fetch per invocation (the game-detail page).
- Caches the response via the existing ``source_html_fetcher`` ttl cache
  so re-running for the same URL re-uses the cached HTML.
- No Gemini call. No production rss_fetcher.py auto-connection — only
  the operator triggers this tool. No new Scheduler.

Hard constraints (mirror the CLI / service guarantees)
======================================================

- Source-only fact extraction. The parser pulls inning_score / score /
  date / league / teams from the Yahoo HTML and never adds tokens.
- ``--mode dry-run`` (default) prints the rendered card and exits — no
  WP write.
- ``--mode draft`` writes a WP draft and never publishes; downstream
  guarded-publish handles the publish gate.
- robots.txt is honoured via ``source_html_fetcher`` 's RobotsChecker.
- Rate-limited per-host via ``source_html_fetcher`` 's PerHostRateLimiter.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
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
    parse_yahoo_game_html,
)


EXIT_OK = 0
EXIT_INVALID_URL = 10
EXIT_FETCH_FAILED = 11
EXIT_PARSE_FAILED = 12
EXIT_RENDER_FAILED = 13
EXIT_NOT_GIANTS = 14
EXIT_WP_FAILED = 20
EXIT_UNEXPECTED = 2


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.run_postgame_from_yahoo",
        description=(
            "Turn a Yahoo Sportsnavi NPB game URL into a postgame_v1 "
            "WP draft. Default --mode 'dry-run'. No Gemini, no body "
            "scraping; structured-data extraction only."
        ),
    )
    p.add_argument(
        "url",
        nargs="?",
        default="",
        help="Yahoo Sportsnavi game URL (https://baseball.yahoo.co.jp/npb/game/<id>/index)",
    )
    p.add_argument(
        "--mode",
        choices=("dry-run", "draft"),
        default="dry-run",
        help="default 'dry-run' (no WP write); 'draft' creates a WP draft",
    )
    p.add_argument(
        "--auto-discover",
        action="store_true",
        help=(
            "Skip explicit URL: probe the Yahoo schedule for the most "
            "recent completed Giants game and use that. Intended for "
            "Cloud Scheduler / cron use."
        ),
    )
    p.add_argument(
        "--from-file",
        default="",
        help="(test-only) read HTML from a local file instead of fetching",
    )
    p.add_argument(
        "--out",
        default="",
        help="JSON summary output path; default = stdout",
    )
    return p


def _auto_discover_giants_completed_url(*, logger: logging.Logger) -> tuple[str, str]:
    """Probe Yahoo schedule pages for the most-recent completed Giants
    game URL. Returns (url, error). Looks at today first, then up to 3
    days back so a job that runs late at night still finds yesterday's
    game when today had no Giants game."""
    from datetime import datetime, timedelta

    from src.source_html_fetcher import RequestsHttpClient
    from src.source_yahoo_schedule_extractor import find_giants_completed_games

    http = RequestsHttpClient()
    today = datetime.now()
    for delta in range(0, 4):
        d = today - timedelta(days=delta)
        date_param = d.strftime("%Y-%m-%d")
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
            continue
        games = find_giants_completed_games(resp.text)
        completed = [g for g in games if g["is_completed"]]
        if completed:
            target = completed[0]
            return target["url"], ""
    return "", "no_completed_giants_game_found"


def _fetch_html(url: str, *, logger: logging.Logger) -> tuple[str, str]:
    """Return (html, error). Empty html with an error string on failure."""
    from src.source_html_fetcher import (
        FetchCache,
        RequestsHttpClient,
        _DefaultRobotsChecker,
        _PerHostRateLimiter,
        fetch_source_meta,
    )

    # Use the Phase 1A pipeline scaffolding to honour robots / rate-limit /
    # cache, but call the HTTP client directly for the raw HTML we need —
    # the OG-meta path doesn't surface the inning table.
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


def _build_payload(facts_dict: dict, *, source_url: str) -> dict:
    """Add source_url / source_label / source_name to the renderer
    data_preview returned by ``YahooBoxscoreFacts.giants_facts()``."""
    out = dict(facts_dict)
    out["source_url"] = source_url
    out["source_label"] = "Yahoo!スポーツ NPB"
    out["source_name"] = "Yahoo!スポーツ"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("postgame_from_yahoo")

    output: dict = {
        "ok": False,
        "mode": args.mode,
        "url": args.url,
        "skip_reason": "",
    }

    url = (args.url or "").strip()

    # --auto-discover: probe Yahoo schedule for today's / recent
    # completed Giants game. Used by Cloud Scheduler for daily auto runs.
    if args.auto_discover and not url:
        discovered_url, err = _auto_discover_giants_completed_url(logger=logger)
        if err:
            output["skip_reason"] = err
            print(json.dumps(output, ensure_ascii=False))
            return EXIT_INVALID_URL
        url = discovered_url
        output["url"] = url
        output["auto_discovered"] = True

    if not (url.startswith("http://") or url.startswith("https://")):
        output["skip_reason"] = "invalid_url"
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_INVALID_URL

    # Acquire HTML.
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

    # Parse.
    facts = parse_yahoo_game_html(html)
    if facts is None:
        output["skip_reason"] = "parse_failed"
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_PARSE_FAILED

    giants_dp = facts.giants_facts()
    if not giants_dp:
        output["skip_reason"] = "not_giants_game"
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_NOT_GIANTS

    payload = _build_payload(giants_dp, source_url=url)

    # Render via the existing nomotoke postgame_v1 renderer.
    os.environ.setdefault("ENABLE_NOMOTOKE_CARD_TEMPLATES", "1")
    from src.nomotoke_card_renderer import select_renderer

    try:
        renderer = select_renderer("nomotoke_card_postgame_v1")
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

    rendered_title = result.get("title") or ""
    rendered_html = result.get("content_html") or ""

    output["title"] = rendered_title
    output["score"] = giants_dp["score"]
    output["result"] = giants_dp["result"]
    output["league_label"] = giants_dp["league_label"]
    output["body_bytes"] = len(rendered_html)
    if args.mode == "dry-run":
        output["body_preview"] = rendered_html[:500]

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

        # Map nomotoke 試合速報 → WP category id 663.
        try:
            categories_map = json.loads(
                (ROOT / "config" / "categories.json").read_text(encoding="utf-8")
            )
            category_id = int(categories_map.get("試合速報") or 0)
        except Exception:
            category_id = 0

        try:
            post_id = wp.create_post(
                title=rendered_title,
                content=rendered_html,
                categories=[category_id] if category_id else None,
                status="draft",
                source_url=url,
                caller="postgame_from_yahoo",
                source_lane="postgame_from_yahoo",
            )
        except Exception as exc:
            output["skip_reason"] = f"wp_create_failed:{exc.__class__.__name__}"
            print(json.dumps(output, ensure_ascii=False))
            return EXIT_WP_FAILED

        output["post_id"] = post_id

    output["ok"] = True
    if args.out:
        Path(args.out).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(output, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
