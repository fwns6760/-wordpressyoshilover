"""Dry-run CLI for ticket 079 nucleus ledger emission."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.nucleus_ledger_emitter import DraftMeta, emit_nucleus_ledger_entry


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run the local nucleus ledger emitter")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--fixture", help="Path to a JSON fixture payload")
    source_group.add_argument("--stdin", action="store_true", help="Read the JSON fixture from stdin")
    parser.add_argument("--enabled", action="store_true", help="Force emitter gate on")
    parser.add_argument("--sink-dir", help="Override the sink directory")
    return parser


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.stdin:
        return json.loads(sys.stdin.read())
    fixture_path = Path(args.fixture)
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _result_payload(result) -> dict[str, Any]:
    return {
        "status": result.status,
        "entry": result.entry,
        "sink_path": str(result.sink_path) if result.sink_path is not None else None,
        "reason": result.reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        payload = _load_payload(args)
        result = emit_nucleus_ledger_entry(
            DraftMeta(
                draft_id=payload.get("draft_id"),
                candidate_key=payload.get("candidate_key"),
                subtype=payload.get("subtype"),
                source_trust=payload.get("source_trust"),
                source_family=payload.get("source_family"),
                chosen_lane=str(payload.get("chosen_lane") or "fixed"),
                chosen_model=payload.get("chosen_model"),
                prompt_version=payload.get("prompt_version"),
                template_version=payload.get("template_version"),
            ),
            title=str(payload.get("title") or ""),
            body=str(payload.get("body") or payload.get("body_html") or ""),
            enabled=True if args.enabled else None,
            sink_dir=args.sink_dir,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(_result_payload(result), ensure_ascii=False))
    return 0 if result.status != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
