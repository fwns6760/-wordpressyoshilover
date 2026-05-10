"""Dry-run CLI for instagram/youtube social_video_notice builder + validator."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from src.instagram_source_registry import find_instagram_source, is_review_candidate
from src.social_video_notice_builder import build_social_video_notice_article
from src.social_video_notice_contract import SocialVideoNoticePayload
from src.social_video_notice_validator import validate_social_video_notice_article
from src.youtube_ob_source_registry import (
    find_youtube_ob_source,
    is_review_candidate as is_youtube_review_candidate,
    normalize_youtube_video_url,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and validate a social_video_notice article from one JSON payload.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture", help="Path to a JSON payload fixture.")
    group.add_argument("--stdin", action="store_true", help="Read a JSON payload from stdin.")
    group.add_argument("--instagram-url", help="Instagram post/reel/tv URL to build from the source registry.")
    group.add_argument("--youtube-url", help="YouTube video URL to build from the OB source registry.")
    parser.add_argument("--account-handle", help="Instagram account handle for --instagram-url.")
    parser.add_argument("--youtube-channel-id", help="YouTube channel id or channel/feed URL for --youtube-url.")
    parser.add_argument("--caption", help="Literal Instagram caption/title excerpt for --instagram-url.")
    parser.add_argument("--video-title", help="Literal YouTube video title/excerpt for --youtube-url.")
    parser.add_argument("--media-kind", default="video", help="Media kind for --instagram-url. Default: video.")
    parser.add_argument("--published-at", help="Published timestamp for --instagram-url.")
    parser.add_argument("--supplement-note", help="Optional source-derived supplement note for --instagram-url.")
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


def _payload_from_instagram_args(args: argparse.Namespace) -> dict[str, Any]:
    if not args.account_handle:
        raise ValueError("--account-handle is required with --instagram-url")
    if not args.caption:
        raise ValueError("--caption is required with --instagram-url")

    source = find_instagram_source(args.account_handle)
    if source is None:
        raise ValueError(f"unknown Instagram source: {args.account_handle}")
    if not is_review_candidate(source):
        raise ValueError(f"Instagram source is not review candidate: {source.handle} status={source.status}")

    return {
        "source_platform": "instagram",
        "source_url": args.instagram_url,
        "source_account_name": source.display_name or source.handle,
        "source_account_handle": source.handle,
        "source_account_type": source.role,
        "media_kind": args.media_kind,
        "caption_or_title": args.caption,
        "published_at": args.published_at,
        "supplement_note": args.supplement_note,
    }


def _payload_from_youtube_args(args: argparse.Namespace) -> dict[str, Any]:
    if not args.youtube_channel_id:
        raise ValueError("--youtube-channel-id is required with --youtube-url")
    video_title = args.video_title or args.caption
    if not video_title:
        raise ValueError("--video-title is required with --youtube-url")

    source = find_youtube_ob_source(args.youtube_channel_id)
    if source is None:
        raise ValueError(f"unknown YouTube source: {args.youtube_channel_id}")
    if not is_youtube_review_candidate(source):
        raise ValueError(f"YouTube source is not review candidate: {source.channel_id} status={source.status}")

    return {
        "source_platform": "youtube",
        "source_url": normalize_youtube_video_url(args.youtube_url),
        "source_account_name": source.display_name or source.channel_id,
        "source_account_handle": source.channel_handle,
        "source_account_type": source.role,
        "media_kind": args.media_kind,
        "caption_or_title": video_title,
        "published_at": args.published_at,
        "supplement_note": args.supplement_note,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.fixture:
            raw_payload = _load_payload_from_fixture(args.fixture)
        elif args.instagram_url:
            raw_payload = _payload_from_instagram_args(args)
        elif args.youtube_url:
            raw_payload = _payload_from_youtube_args(args)
        else:
            raw_payload = _load_payload_from_stdin()
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
