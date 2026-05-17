"""Tests for issue #44 follow-up: media primary attach 観察 log (post 68872 型 merge bug 診断).

Bug pattern: post 68872 で title=ノック話 / source_url=SANSPO父300HR の merge
が upstream で発生していた。 fix する前に prod log で merge 発生 path を
pinpoint するため、 _select_social_source_quotes で source_class=="media" 時に
構造化 log を出す。 挙動変更なし。
"""

from __future__ import annotations

import json
import logging

from src.media_xpost_selector import _select_social_source_quotes


def test_media_primary_attach_emits_observation_log(caplog):
    """source_class=='media' の場合に media_primary_attach_decision log が出る."""
    entry = {
        "source_url": "https://twitter.com/sanspo_giants/status/2055823505544056999",
        "source_name": "サンスポ",
        "source_type": "social_news",
        "story_kind": "",
        "title": "坂本勇人 選手、ショートで 泉口友汰 選手と一緒にノック",
        "summary": "ショートでノックを受けた後、 2人で言葉を交わしていました",
        "topic_aliases": ["坂本勇人", "泉口友汰"],
        "created_at": "2026-05-17T13:00:00+09:00",
    }
    with caplog.at_level(logging.INFO, logger="media_xpost_selector"):
        quotes = _select_social_source_quotes(entry, [], max_count=1)

    assert len(quotes) == 1, "primary attach 挙動 (1 quote 返す) は不変であること"
    log_lines = [
        rec.message
        for rec in caplog.records
        if "media_primary_attach_decision" in (rec.message or "")
    ]
    assert log_lines, "media_primary_attach_decision log が出ていない"
    payload = json.loads(log_lines[0])
    assert payload["event"] == "media_primary_attach_decision"
    assert payload["source_class"] == "media"
    assert payload["source_handle"] == "@sanspo_giants"
    assert payload["entry_source_type"] == "social_news"
    assert "ノック" in payload["entry_title_head"]
    assert payload["decision"] == "attach_primary"


def test_non_media_source_does_not_emit_observation_log(caplog):
    """非 media handle (fan tweet) の場合は観察 log は出ない (noise 削減)."""
    entry = {
        "source_url": "https://twitter.com/mu_hayateeshi/status/2055160003808592113",
        "source_name": "mu_hayateeshi",
        "source_type": "social_news",
        "story_kind": "",
        "title": "ショートで一緒にノックを受けた",
        "summary": "ショートでノックを受けた",
        "topic_aliases": ["坂本勇人"],
        "created_at": "2026-05-17T13:00:00+09:00",
    }
    with caplog.at_level(logging.INFO, logger="media_xpost_selector"):
        quotes = _select_social_source_quotes(entry, [], max_count=1)

    assert len(quotes) == 1, "non-media でも primary attach 挙動は不変"
    log_lines = [
        rec.message
        for rec in caplog.records
        if "media_primary_attach_decision" in (rec.message or "")
    ]
    assert not log_lines, (
        f"non-media handle で観察 log が出ている: {log_lines}"
    )
