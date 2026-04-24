"""Dry-run CLI for x_source_notice builder + validator."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.x_source_notice_builder import build_x_source_notice_article
from src.x_source_notice_contract import XSourceNoticePayload
from src.x_source_notice_validator import validate_x_source_notice


JST = timezone(timedelta(hours=9))


def _published_at(hour: int) -> datetime:
    return datetime(2026, 4, 24, hour, 0, tzinfo=JST)


def _fixtures() -> list[dict[str, object]]:
    return [
        {
            "name": "fact-team-official-post",
            "payload": XSourceNoticePayload(
                source_platform="x",
                source_url="https://x.com/giants/status/1001",
                source_account_name="読売ジャイアンツ",
                source_account_type="team_official",
                source_tier="fact",
                post_kind="post",
                post_text="巨人は坂本勇人を出場選手登録した",
                published_at=_published_at(1),
                supplement_note="球団公式アカウントの告知",
            ),
            "topic_recheck_passed": False,
        },
        {
            "name": "fact-press-major-quote",
            "payload": XSourceNoticePayload(
                source_platform="x",
                source_url="https://x.com/hochi_giants/status/1002",
                source_account_name="スポーツ報知 巨人担当",
                source_account_type="press_major",
                source_tier="fact",
                post_kind="quote",
                post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
                published_at=_published_at(2),
                supplement_note=None,
            ),
            "topic_recheck_passed": False,
        },
        {
            "name": "topic-press-reporter-post-without-recheck",
            "payload": XSourceNoticePayload(
                source_platform="x",
                source_url="https://x.com/reporter/status/1003",
                source_account_name="報知プロ野球担当",
                source_account_type="press_reporter",
                source_tier="topic",
                post_kind="post",
                post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
                published_at=_published_at(3),
                supplement_note=None,
            ),
            "topic_recheck_passed": False,
            "force_fact_title": True,
        },
        {
            "name": "topic-press-major-post-with-recheck",
            "payload": XSourceNoticePayload(
                source_platform="x",
                source_url="https://x.com/nikkan_giants/status/1004",
                source_account_name="日刊スポーツ 巨人担当",
                source_account_type="press_major",
                source_tier="topic",
                post_kind="post",
                post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
                published_at=_published_at(4),
                supplement_note="一次確認済みフラグを想定",
            ),
            "topic_recheck_passed": True,
        },
        {
            "name": "reaction-tier-rejected",
            "payload": XSourceNoticePayload(
                source_platform="x",
                source_url="https://x.com/fan/status/1005",
                source_account_name="巨人ファン速報",
                source_account_type="press_misc",
                source_tier="reaction",
                post_kind="reply",
                post_text="坂本勇人の復帰は楽しみだ",
                published_at=_published_at(5),
                supplement_note=None,
            ),
            "topic_recheck_passed": False,
        },
        {
            "name": "repost-rejected",
            "payload": XSourceNoticePayload(
                source_platform="x",
                source_url="https://x.com/npb/status/1006",
                source_account_name="NPB",
                source_account_type="league_official",
                source_tier="fact",
                post_kind="repost",
                post_text="セ・リーグ公式戦の日程を告知した",
                published_at=_published_at(6),
                supplement_note=None,
            ),
            "topic_recheck_passed": False,
        },
    ]


def main() -> int:
    for fixture in _fixtures():
        payload = fixture["payload"]
        topic_recheck_passed = bool(fixture["topic_recheck_passed"])
        article = build_x_source_notice_article(payload, topic_recheck_passed=topic_recheck_passed)
        if fixture.get("force_fact_title"):
            article = replace(article, title=f"{payload.source_account_name}、{article.nucleus_event or payload.post_text}")
        result = validate_x_source_notice(payload, article, topic_recheck_passed=topic_recheck_passed)
        if result.ok:
            print(f"[OK] {fixture['name']}")
        else:
            print(f"[REJECT {result.reason_code}] {fixture['name']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
