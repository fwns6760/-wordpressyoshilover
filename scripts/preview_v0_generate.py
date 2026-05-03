from __future__ import annotations

import argparse
from pathlib import Path

from lib.preview_facts import (
    extract_preview_facts,
    load_backup,
    load_jsonl_index,
    normalize_html,
)
from lib.preview_render import evaluate_acceptance, render_sample
from lib.preview_rules import apply_preview_pipeline


DEFAULT_HISTORY_PATH = "logs/guarded_publish_history.jsonl"
DEFAULT_YELLOW_LOG_PATH = "logs/guarded_publish_yellow_log.jsonl"
DEFAULT_OUTPUT_DIR = "docs/ops/preview_v0/generated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate preview_v0 sample docs from backup JSON only.",
    )
    parser.add_argument(
        "--post-ids",
        nargs="+",
        type=int,
        required=True,
        help="Target post_ids to render into preview sample docs.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for generated sample markdown files.",
    )
    parser.add_argument(
        "--history-path",
        default=DEFAULT_HISTORY_PATH,
        help="guarded_publish_history jsonl path.",
    )
    parser.add_argument(
        "--yellow-log-path",
        default=DEFAULT_YELLOW_LOG_PATH,
        help="guarded_publish_yellow_log jsonl path.",
    )
    parser.add_argument(
        "--subtype-map",
        nargs="*",
        default=[],
        help="Optional explicit subtype mapping in post_id=subtype form.",
    )
    parser.add_argument(
        "--subtype",
        default=None,
        help="Optional subtype override applied to every post_id not present in --subtype-map.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    history_index = load_jsonl_index(args.history_path)
    yellow_index = load_jsonl_index(args.yellow_log_path)
    subtype_map = _parse_subtype_map(args.subtype_map)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for post_id in args.post_ids:
        history_entry = history_index.get(post_id)
        if history_entry is None:
            raise SystemExit(f"post_id={post_id} not found in {args.history_path}")

        backup_path = history_entry.get("backup_path")
        if not backup_path:
            raise SystemExit(f"post_id={post_id} has no backup_path in history log")

        backup_doc = load_backup(backup_path)
        facts = extract_preview_facts(history_entry, backup_doc)
        original = normalize_html(backup_doc["content"]["rendered"])
        subtype = subtype_map.get(post_id) or args.subtype or facts.get("subtype_hint") or "manager"
        fixed, rule_results = apply_preview_pipeline(original, facts, subtype)
        acceptance = evaluate_acceptance(original, fixed, facts, rule_results)
        quality_flags = _extract_quality_flags(yellow_index.get(post_id))

        sample_id = f"sample_{subtype}_{post_id}"
        output_path = output_dir / f"{sample_id}.md"
        output_path.write_text(
            render_sample(
                sample_id=sample_id,
                subtype=subtype,
                original=original,
                fixed=fixed,
                facts=facts,
                rules=rule_results,
                acceptance=acceptance,
                quality_flags=quality_flags,
            )
        )
        print(output_path)

    return 0


def _parse_subtype_map(items: list[str]) -> dict[int, str]:
    parsed: dict[int, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"invalid subtype map: {item!r}; expected post_id=subtype")
        post_id_text, subtype = item.split("=", 1)
        parsed[int(post_id_text)] = subtype.strip()
    return parsed


def _extract_quality_flags(yellow_entry: dict | None) -> list[str]:
    if not yellow_entry:
        return []
    flags = yellow_entry.get("yellow_reasons") or yellow_entry.get("applied_flags") or []
    return [str(flag) for flag in flags]


if __name__ == "__main__":
    raise SystemExit(main())
