from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.lineup_source_priority import compute_lineup_dedup


def _load_pool_from_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("input JSON must be a list or PUB-004 evaluator report object")

    sections: list[dict[str, Any]] = []
    for key in ("green", "yellow", "red"):
        items = payload.get(key)
        if isinstance(items, list):
            sections.extend(item for item in items if isinstance(item, dict))
    if sections:
        return sections
    raise ValueError("input JSON did not contain green/yellow/red entries")


def _load_pool_from_wp(max_posts: int) -> list[dict[str, Any]]:
    from src.wp_client import WPClient

    client = WPClient()
    return list(
        client.list_posts(
            status="draft",
            per_page=max(1, min(int(max_posts), 100)),
            orderby="modified",
            order="desc",
            context="edit",
        )
        or []
    )


def _render_human(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Lineup Source Priority Dry Run",
        "",
        "Summary",
        f"representative={summary['representative_count']}",
        f"duplicate_absorbed={summary['duplicate_absorbed_count']}",
        f"deferred={summary['deferred_count']}",
        f"prefix_violations={summary['prefix_violation_count']}",
    ]
    for label, key in (
        ("Representative", "representatives"),
        ("Duplicate Absorbed", "duplicate_absorbed"),
        ("Deferred", "deferred"),
        ("Prefix Violations", "prefix_violations"),
    ):
        lines.extend(["", label])
        items = report[key]
        if not items:
            lines.append("- none")
            continue
        for item in items:
            lines.append(
                "- "
                f"post_id={item.get('post_id')} "
                f"game_id={item.get('game_id') or '-'} "
                f"reason={item.get('reason')} "
                f"source={item.get('source_name') or item.get('source_domain') or item.get('source_url') or '-'} "
                f"title={item.get('title') or '-'}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run lineup source priority and duplicate suppression")
    parser.add_argument("--input-from", default="", help="PUB-004 evaluator output JSON path")
    parser.add_argument("--format", choices=("json", "human"), default="human")
    parser.add_argument("--max-posts", type=int, default=100, help="WP draft scan size when --input-from is omitted")
    args = parser.parse_args(argv)

    if args.input_from:
        post_pool = _load_pool_from_json(Path(args.input_from))
    else:
        post_pool = _load_pool_from_wp(args.max_posts)

    report = compute_lineup_dedup(post_pool)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_human(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
