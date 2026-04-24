"""Dry-run CLI for instagram/youtube social_video_notice builder + validator."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from src.social_video_notice_builder import build_social_video_notice_article
from src.social_video_notice_contract import SocialVideoNoticePayload
from src.social_video_notice_validator import validate_social_video_notice_article


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and validate a social_video_notice article from one JSON payload.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture", help="Path to a JSON payload fixture.")
    group.add_argument("--stdin", action="store_true", help="Read a JSON payload from stdin.")
    return parser.parse_args(argv)


def _load_payload_from_fixture(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture must be a JSON object")
    return dict(payload)


def _load_payload_from_stdin() -> dict[str, Any]:
    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        raise ValueError("stdin payload must be a JSON object")
    return dict(payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        raw_payload = _load_payload_from_fixture(args.fixture) if args.fixture else _load_payload_from_stdin()
        payload = SocialVideoNoticePayload(**raw_payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"payload error: {exc}", file=sys.stderr)
        return 1

    article = build_social_video_notice_article(payload)
    validation = validate_social_video_notice_article(article)
    report = {
        "article": asdict(article),
        "validation": asdict(validation),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if validation.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
