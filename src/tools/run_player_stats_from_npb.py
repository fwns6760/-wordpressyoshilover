"""NOMOTOKE-PLAYER-STATS-FROM-NPB-001 — operator CLI that turns the
NPB.jp Giants team-stat table into a ``nomotoke_card_player_stats_v1``
WP draft for a chosen player.

Usage
=====

    python -m src.tools.run_player_stats_from_npb \\
        --player "石塚裕惺" \\
        --stat-kind batting \\
        --mode dry-run

``--stat-kind batting`` fetches ``idb1_g.html``; ``pitching`` fetches
``idp1_g.html``. ``--mode draft`` writes a WP draft. ``--from-file``
loads a local fixture instead of fetching (used by the tests).

Cost / safety
=============

- 1 fetch per invocation (the team-stat HTML page, ~50-70 KiB).
- robots-aware via ``source_html_fetcher.RequestsHttpClient``.
- Source-only — extracted stats reflect the NPB-published table verbatim.
- production rss_fetcher.py untouched. No Scheduler. No env. No Gemini.
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

from src.source_npb_team_stats_extractor import (  # noqa: E402
    find_player_row,
    parse_npb_team_stats_html,
    stats_card_payload,
)


EXIT_OK = 0
EXIT_INVALID_INPUT = 10
EXIT_FETCH_FAILED = 11
EXIT_PARSE_FAILED = 12
EXIT_PLAYER_NOT_FOUND = 13
EXIT_RENDER_FAILED = 14
EXIT_WP_FAILED = 20


_NPB_BATTING_URL = "https://npb.jp/bis/{year}/stats/idb1_g.html"
_NPB_PITCHING_URL = "https://npb.jp/bis/{year}/stats/idp1_g.html"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.run_player_stats_from_npb",
        description=(
            "Turn an NPB.jp Giants team-stat row into a player_stats_v1 "
            "WP draft. Default --mode dry-run. Source-only — never adds "
            "tokens; never calls Gemini."
        ),
    )
    p.add_argument(
        "--player",
        required=True,
        help="Giants player name (kanji + space tolerated, e.g. '石塚裕惺')",
    )
    p.add_argument(
        "--stat-kind",
        choices=("batting", "pitching"),
        default="batting",
        help="default 'batting' (idb1_g.html); 'pitching' = idp1_g.html",
    )
    p.add_argument(
        "--year",
        default=datetime.now().strftime("%Y"),
        help="NPB stat year (default = current year)",
    )
    p.add_argument(
        "--mode",
        choices=("dry-run", "draft"),
        default="dry-run",
        help="default 'dry-run' (no WP write); 'draft' creates a WP draft",
    )
    p.add_argument(
        "--from-file",
        default="",
        help="(test-only) read HTML from a local file instead of fetching",
    )
    return p


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
    logger = logging.getLogger("player_stats_from_npb")

    output: dict = {
        "ok": False,
        "mode": args.mode,
        "stat_kind": args.stat_kind,
        "player": args.player,
        "skip_reason": "",
    }

    if args.stat_kind == "batting":
        url = _NPB_BATTING_URL.format(year=args.year)
    else:
        url = _NPB_PITCHING_URL.format(year=args.year)
    output["url"] = url

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

    parsed = parse_npb_team_stats_html(html)
    if parsed is None:
        output["skip_reason"] = "parse_failed"
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_PARSE_FAILED

    hit = find_player_row(parsed, args.player)
    if hit is None:
        output["skip_reason"] = "player_not_found"
        output["available_count"] = len(parsed)
        print(json.dumps(output, ensure_ascii=False))
        return EXIT_PLAYER_NOT_FOUND

    _, record = hit
    rendered_name = record["__rendered_name__"]
    payload = stats_card_payload(
        rendered_name=rendered_name,
        record=record,
        stat_kind=args.stat_kind,
        date_label=datetime.now().strftime("%Y年%-m月%-d日"),
        source_url=url,
    )

    os.environ.setdefault("ENABLE_NOMOTOKE_CARD_TEMPLATES", "1")
    from src.nomotoke_card_renderer import select_renderer

    try:
        renderer = select_renderer("nomotoke_card_player_stats_v1")
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
        try:
            categories_map = json.loads(
                (ROOT / "config" / "categories.json").read_text(encoding="utf-8")
            )
            category_id = int(categories_map.get("選手情報") or 0)
        except Exception:
            category_id = 0
        try:
            post_id = wp.create_post(
                title=result["title"],
                content=result["content_html"],
                categories=[category_id] if category_id else None,
                status="draft",
                source_url=url,
                caller="player_stats_from_npb",
                source_lane="player_stats_from_npb",
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
