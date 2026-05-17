#!/usr/bin/env python3
"""Create pre-approved Giants person/context WP tags.

This is the only tool that creates WP tags for the person-tag routing
lane. Runtime article creation resolves existing tags only and logs
missing names.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.person_tag_router import all_person_tag_names
from src.wp_client import WPClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Giants player/staff/OB/context tags to WordPress."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended tags without calling WordPress.",
    )
    parser.add_argument(
        "--no-context-tags",
        action="store_true",
        help="Only sync person tags; skip 一軍/二軍/速報/etc.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    tag_names = all_person_tag_names(include_context_tags=not args.no_context_tags)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "count": len(tag_names), "tags": tag_names}, ensure_ascii=False))
        return 0

    wp = WPClient()
    created_or_existing: list[dict] = []
    missing: list[str] = []
    for name in tag_names:
        tag_id = wp.create_tag(name)
        if tag_id:
            created_or_existing.append({"name": name, "id": tag_id})
        else:
            missing.append(name)
    print(
        json.dumps(
            {
                "dry_run": False,
                "ok_count": len(created_or_existing),
                "missing_count": len(missing),
                "missing": missing,
                "tags": created_or_existing,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
