"""Tests for src.nomotoke_card_renderer (NOMOTOKE-SHAPE-001 — 10 templates)."""

from __future__ import annotations

import os
import re
import unittest
from unittest import mock

from src.nomotoke_card_renderer import (
    ENABLE_FLAG,
    TEMPLATE_KEY_BROADCAST,
    TEMPLATE_KEY_LINEUP,
    TEMPLATE_KEY_LIVE_AT_BATS,
    TEMPLATE_KEY_MANAGER_COMMENT,
    TEMPLATE_KEY_OFFICIAL_NOTICE,
    TEMPLATE_KEY_PLAYER_COMMENT,
    TEMPLATE_KEY_PLAYER_STATS,
    TEMPLATE_KEY_POSTGAME,
    TEMPLATE_KEY_PREGAME_PITCHER,
    TEMPLATE_KEY_VIDEO,
    is_enabled,
    render_broadcast_info_card,
    render_lineup_card,
    render_live_at_bats_card,
    render_manager_comment_card,
    render_official_notice_card,
    render_player_comment_card,
    render_player_stats_card,
    render_postgame_card,
    render_pregame_pitcher_card,
    render_video_card,
    require_enabled,
    select_renderer,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _full_lineup_data() -> dict:
    return {
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "team_name": "巨人",
        "opponent_name": "阪神",
        "live_url": "https://example.com/live/123",
        "source_url": "https://example.com/lineup-source",
        "own_lineup": [
            {
                "order": 1,
                "position": "中",
                "player_name": "丸佳浩",
                "batting_average": ".280",
                "starter_era": "",
            },
            {
                "order": 2,
                "position": "二",
                "player_name": "吉川尚輝",
                "batting_average": ".265",
                "starter_era": "",
            },
        ],
        "opponent_lineup": [
            {
                "order": 1,
                "position": "中",
                "player_name": "近本光司",
                "batting_average": ".310",
                "starter_era": "",
            },
        ],
        "own_starter": {"name": "戸郷翔征"},
        "related_links": [
            {"url": "https://example.com/broadcast", "label": "中継情報"},
            {"url": "https://example.com/farm", "label": "ファーム速報"},
        ],
    }


def _full_postgame_data() -> dict:
    return {
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "team_name": "巨人",
        "score": "5-3",
        "result": "win",
        "one_line_summary": "終盤の集中打で勝利",
        "source_url": "https://example.com/postgame-source",
        "inning_score": [
            {
                "name": "巨人",
                "innings": [0, 1, 0, 0, 0, 2, 0, 2, "x"],
                "total": 5,
            },
            {
                "name": "阪神",
                "innings": [1, 0, 0, 1, 0, 0, 1, 0, 0],
                "total": 3,
            },
        ],
        "atbat_results": [
            {"player_name": "丸佳浩", "order": 1, "result": "中安, 三振, 四球, 二塁打"},
        ],
        "pitching_results": [
            {"pitcher_name": "戸郷翔征", "innings": "7", "runs": "2", "summary": "勝利投手"},
        ],
        "opposing_pitcher": "青柳晃洋",
    }


def _full_official_notice_data() -> dict:
    return {
        "date_label": "2026年5月6日",
        "team_name": "巨人",
        "action": "register",
        "official_url": "https://npb.jp/announcement",
        "source_url": "https://example.com/notice-source",
        "registered": ["秋広優人", "山瀬慎之助"],
        "removed": [],
        "current_count": 28,
        "remaining_slots": 2,
        "note": "ファーム調整明け",
    }


def _full_pregame_pitcher_data() -> dict:
    return {
        "date_label": "2026年5月6日",
        "official_url": "https://npb.jp/pregame",
        "source_url": "https://example.com/pregame-source",
        "matchups": [
            {
                "team_a": "巨人",
                "pitcher_a": "戸郷翔征",
                "team_b": "阪神",
                "pitcher_b": "青柳晃洋",
            },
            {
                "team_a": "DeNA",
                "pitcher_a": "東克樹",
                "team_b": "広島",
                "pitcher_b": "森下暢仁",
            },
        ],
        "broadcast_links": [
            {"url": "https://example.com/tv", "label": "TV中継"},
        ],
    }


def _full_live_at_bats_data() -> dict:
    return {
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "own_team_label": "巨人 スタメン",
        "notable_player_1": "岡本和真",
        "notable_player_2": "丸佳浩",
        "starter": "戸郷翔征",
        "status": "in_progress",
        "source_url": "https://example.com/live-source",
        "lineup_rows": [
            {
                "order": 1,
                "position": "中",
                "player_name": "丸佳浩",
                "batting_average": ".280",
                "starter_era": "",
            }
        ],
        "at_bats_rows": [
            {"player_name": "岡本和真", "order": 4, "result": "中安, 四球"},
        ],
        "pitching_rows": [
            {"pitcher_name": "戸郷翔征", "innings": "5", "runs": "1", "summary": "好投"},
        ],
        "broadcast_info": [
            {"url": "https://example.com/broadcast", "label": "TV中継"},
        ],
    }


def _full_broadcast_data() -> dict:
    return {
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "source_url": "https://example.com/broadcast-source",
        "broadcasts": [
            {
                "media": "テレビ",
                "channel": "日テレG+",
                "time": "18:00-21:30",
                "commentator": "桑田真澄",
                "play_by_play": "船越雅史",
            },
            {
                "media": "ラジオ",
                "channel": "ニッポン放送",
                "time": "18:00-21:30",
                "commentator": "",
                "play_by_play": "",
            },
        ],
        "note": "雨天順延の可能性あり",
    }


def _full_video_data() -> dict:
    return {
        "team_name": "巨人",
        "player_name": "岡本和真",
        "play_summary": "決勝3ラン本塁打",
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "source_url": "https://example.com/video-source",
        "embed_html": (
            '<iframe src="https://www.youtube.com/embed/abc123" '
            'width="560" height="315"></iframe>'
        ),
        "description": "8回裏に飛び出した決勝3ラン本塁打。",
        "date_label": "2026年5月6日",
    }


def _full_player_stats_data() -> dict:
    return {
        "team_name": "巨人",
        "player_name": "岡本和真",
        "stat_kind": "batting",
        "date_label": "2026年5月6日時点",
        "source_url": "https://example.com/stats-source",
        "stats_columns": ["試合", "打数", "安打", "本塁打", "打点", "打率"],
        "stats_rows": [
            {
                "試合": 30,
                "打数": 110,
                "安打": 32,
                "本塁打": 8,
                "打点": 25,
                "打率": ".291",
            },
        ],
    }


def _full_manager_comment_data() -> dict:
    return {
        "team_name": "巨人",
        "manager_name": "阿部慎之助",
        "topic": "戸郷の好投",
        "source_url": "https://sponichi.example.com/news/giants",
        "source_name": "スポーツニッポン",
        "published_at": "2026-05-06 22:30",
        "quote_short": "戸郷はよく投げてくれた、明日も期待したい",
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "game_link_url": "https://example.com/game/123",
        "game_link_label": "試合結果はこちら",
    }


def _full_player_comment_data() -> dict:
    return {
        "team_name": "巨人",
        "player_name": "岡本和真",
        "topic": "決勝本塁打",
        "source_url": "https://sponichi.example.com/news/giants/okamoto",
        "source_name": "スポーツニッポン",
        "published_at": "2026-05-06 22:30",
        "quote_short": "甘く入った球をしっかり捉えられた",
        "quote_short_for_title": "甘い球を捉えた",
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "stats_link_url": "https://example.com/stats/okamoto",
    }


# ---------------------------------------------------------------------------
# Happy-path tests (per renderer)
# ---------------------------------------------------------------------------


class HappyPathTests(unittest.TestCase):
    def test_lineup_card_happy_path(self):
        out = render_lineup_card(_full_lineup_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["skip_reason"], "")
        self.assertEqual(out["template_key"], TEMPLATE_KEY_LINEUP)
        self.assertEqual(out["category"], "試合速報")
        self.assertIn("巨人、スタメン発表！！！", out["title"])
        self.assertIn("「巨人vs.阪神」", out["title"])
        self.assertIn("■ 2026年5月6日", out["content_html"])
        self.assertIn("丸佳浩", out["content_html"])
        self.assertIn("近本光司", out["content_html"])
        self.assertIn("関連リンク", out["content_html"])
        self.assertIn("この日のスタメンです。", out["content_html"])
        self.assertEqual(
            out["source_url"], "https://example.com/lineup-source"
        )
        self.assertEqual(out["dedupe_key"], "lineup:2026年5月6日:巨人:阪神")
        self.assertTrue(out["tags"])
        self.assertIn('class="nomotoke-meta"', out["content_html"])

    def test_postgame_card_happy_path(self):
        out = render_postgame_card(_full_postgame_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_POSTGAME)
        self.assertEqual(out["category"], "試合速報")
        self.assertIn("【試合結果、打席結果】", out["title"])
        self.assertIn("5-3で勝利！！！", out["title"])
        self.assertIn("試合スコア", out["content_html"])
        self.assertIn("打席結果", out["content_html"])
        self.assertIn("勝ちました。", out["content_html"])
        self.assertEqual(
            out["dedupe_key"], "postgame:2026年5月6日:巨人:阪神"
        )

    def test_official_notice_card_happy_path(self):
        out = render_official_notice_card(_full_official_notice_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_OFFICIAL_NOTICE)
        self.assertEqual(out["category"], "公示")
        self.assertIn("【公示】2026年5月6日", out["title"])
        self.assertIn("巨人が登録", out["title"])
        self.assertIn("が登録です。", out["content_html"])
        self.assertEqual(out["dedupe_key"], "announce:2026年5月6日:巨人")

    def test_pregame_pitcher_card_happy_path(self):
        out = render_pregame_pitcher_card(_full_pregame_pitcher_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_PREGAME_PITCHER)
        self.assertEqual(out["category"], "試合速報")
        self.assertEqual(
            out["title"], "2026年5月6日の予告先発が発表される！！！"
        )
        self.assertIn("戸郷翔征が先発です。", out["content_html"])
        self.assertEqual(out["dedupe_key"], "pregame:2026年5月6日")

    def test_live_at_bats_card_happy_path(self):
        out = render_live_at_bats_card(_full_live_at_bats_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_LIVE_AT_BATS)
        self.assertEqual(out["category"], "試合速報")
        self.assertIn("【全打席結果速報】", out["title"])
        self.assertIn("岡本和真", out["title"])
        self.assertIn("らが出場！！！", out["title"])
        self.assertIn("打席結果", out["content_html"])
        self.assertIn("投球結果", out["content_html"])
        # status=in_progress closing
        self.assertIn("随時更新します。", out["content_html"])
        self.assertEqual(
            out["dedupe_key"], "live_at_bats:2026年5月6日:巨人:阪神"
        )

    def test_live_at_bats_finished_closing(self):
        d = _full_live_at_bats_data()
        d["status"] = "finished"
        out = render_live_at_bats_card(d)
        self.assertIn("試合経過はこちらです。", out["content_html"])

    def test_broadcast_card_happy_path(self):
        out = render_broadcast_info_card(_full_broadcast_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_BROADCAST)
        self.assertEqual(out["category"], "中継")
        self.assertIn("【テレビ・ネット・ラジオ中継情報】", out["title"])
        self.assertIn("中継予定", out["content_html"])
        self.assertIn("日テレG+", out["content_html"])
        self.assertIn("この日の中継情報です。", out["content_html"])
        self.assertEqual(
            out["dedupe_key"], "broadcast:2026年5月6日:巨人:阪神"
        )

    def test_video_card_happy_path(self):
        out = render_video_card(_full_video_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_VIDEO)
        self.assertEqual(out["category"], "動画")
        self.assertIn("決勝3ラン本塁打", out["title"])
        self.assertIn("【動画】", out["title"])
        self.assertIn("youtube.com/embed/abc123", out["content_html"])
        self.assertIn("岡本和真選手のプレーです。", out["content_html"])
        self.assertEqual(
            out["dedupe_key"],
            "video:https://www.youtube.com/watch?v=abc123",
        )

    def test_player_stats_card_happy_path(self):
        out = render_player_stats_card(_full_player_stats_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_PLAYER_STATS)
        self.assertEqual(out["category"], "個人成績")
        self.assertIn("打撃成績", out["title"])
        self.assertIn("対象日時:", out["content_html"])
        self.assertIn("打率", out["content_html"])
        self.assertIn(".291", out["content_html"])
        self.assertIn("ここまでの成績です。", out["content_html"])
        self.assertEqual(
            out["dedupe_key"],
            "player_stats:2026年5月6日時点:岡本和真:batting",
        )

    def test_manager_comment_card_happy_path(self):
        out = render_manager_comment_card(_full_manager_comment_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_MANAGER_COMMENT)
        self.assertEqual(out["category"], "監督談話")
        self.assertIn("阿部慎之助監督、戸郷の好投についてコメント", out["title"])
        self.assertIn(
            '<blockquote class="nomotoke-quote">', out["content_html"]
        )
        self.assertIn("阿部慎之助監督がコメントです。", out["content_html"])
        self.assertTrue(out["dedupe_key"].startswith(
            "manager_comment:2026年5月6日:阿部慎之助:"
        ))

    def test_player_comment_card_happy_path_short_title(self):
        out = render_player_comment_card(_full_player_comment_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_PLAYER_COMMENT)
        self.assertEqual(out["category"], "選手コメント")
        # short title path (<=20 chars) — quote-style title.
        self.assertIn("「甘い球を捉えた」", out["title"])
        self.assertIn(
            '<blockquote class="nomotoke-quote">', out["content_html"]
        )
        self.assertIn("岡本和真選手がコメントです。", out["content_html"])
        self.assertTrue(out["dedupe_key"].startswith(
            "player_comment:2026年5月6日:岡本和真:"
        ))

    def test_player_comment_topic_title_when_no_short_title(self):
        d = _full_player_comment_data()
        d.pop("quote_short_for_title", None)
        out = render_player_comment_card(d)
        self.assertTrue(out["validation_ok"])
        self.assertIn("決勝本塁打についてコメント", out["title"])

    def test_player_comment_topic_title_when_short_title_too_long(self):
        d = _full_player_comment_data()
        d["quote_short_for_title"] = "あ" * 25  # >20 chars
        out = render_player_comment_card(d)
        self.assertIn("決勝本塁打についてコメント", out["title"])


# ---------------------------------------------------------------------------
# Field-missing / skip_reason tests (per renderer)
# ---------------------------------------------------------------------------


class FieldMissingTests(unittest.TestCase):
    def test_lineup_missing_team_name(self):
        d = _full_lineup_data()
        d["team_name"] = ""
        out = render_lineup_card(d)
        self.assertEqual(out["skip_reason"], "missing_team_name")
        self.assertFalse(out["validation_ok"])
        self.assertEqual(out["dedupe_key"], "")

    def test_lineup_missing_lineup(self):
        d = _full_lineup_data()
        d["own_lineup"] = []
        out = render_lineup_card(d)
        self.assertEqual(out["skip_reason"], "missing_lineup_rows")

    def test_postgame_missing_score(self):
        d = _full_postgame_data()
        d["score"] = ""
        out = render_postgame_card(d)
        self.assertEqual(out["skip_reason"], "missing_score")

    def test_official_notice_missing_action(self):
        d = _full_official_notice_data()
        d["action"] = ""
        out = render_official_notice_card(d)
        self.assertEqual(out["skip_reason"], "missing_action")

    def test_pregame_missing_matchups(self):
        d = _full_pregame_pitcher_data()
        d["matchups"] = []
        out = render_pregame_pitcher_card(d)
        self.assertEqual(out["skip_reason"], "missing_matchups")

    def test_live_at_bats_missing_data(self):
        d = _full_live_at_bats_data()
        d["lineup_rows"] = []
        d["at_bats_rows"] = []
        d["pitching_rows"] = []
        out = render_live_at_bats_card(d)
        self.assertEqual(out["skip_reason"], "missing_at_bats_data")

    def test_broadcast_missing_broadcasts(self):
        d = _full_broadcast_data()
        d["broadcasts"] = []
        out = render_broadcast_info_card(d)
        self.assertEqual(out["skip_reason"], "missing_broadcasts")

    def test_video_missing_fields(self):
        d = _full_video_data()
        d["video_url"] = ""
        out = render_video_card(d)
        self.assertEqual(out["skip_reason"], "missing_video_fields")

    def test_player_stats_missing_fields(self):
        d = _full_player_stats_data()
        d["stats_rows"] = []
        out = render_player_stats_card(d)
        self.assertEqual(out["skip_reason"], "missing_stats_fields")

    def test_player_stats_invalid_stat_kind(self):
        d = _full_player_stats_data()
        d["stat_kind"] = "fielding"
        out = render_player_stats_card(d)
        self.assertEqual(out["skip_reason"], "invalid_stat_kind")

    def test_manager_comment_missing_speaker(self):
        d = _full_manager_comment_data()
        d["manager_name"] = ""
        out = render_manager_comment_card(d)
        self.assertEqual(out["skip_reason"], "missing_speaker")

    def test_player_comment_missing_speaker(self):
        d = _full_player_comment_data()
        d["player_name"] = ""
        out = render_player_comment_card(d)
        self.assertEqual(out["skip_reason"], "missing_speaker")


# ---------------------------------------------------------------------------
# HTML escape (10 renderers)
# ---------------------------------------------------------------------------


class HtmlEscapeTests(unittest.TestCase):
    INJECT = "<script>alert(1)</script>"

    def test_lineup_escapes(self):
        d = _full_lineup_data()
        d["own_lineup"][0]["player_name"] = self.INJECT
        out = render_lineup_card(d)
        self.assertNotIn("<script>", out["content_html"])
        self.assertIn("&lt;script&gt;", out["content_html"])

    def test_postgame_escapes(self):
        d = _full_postgame_data()
        d["atbat_results"][0]["player_name"] = self.INJECT
        out = render_postgame_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_official_notice_escapes(self):
        d = _full_official_notice_data()
        d["registered"] = [self.INJECT]
        out = render_official_notice_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_pregame_escapes(self):
        d = _full_pregame_pitcher_data()
        d["matchups"][0]["pitcher_a"] = self.INJECT
        out = render_pregame_pitcher_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_live_at_bats_escapes(self):
        d = _full_live_at_bats_data()
        d["at_bats_rows"][0]["player_name"] = self.INJECT
        out = render_live_at_bats_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_broadcast_escapes(self):
        d = _full_broadcast_data()
        d["broadcasts"][0]["channel"] = self.INJECT
        out = render_broadcast_info_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_video_escapes(self):
        d = _full_video_data()
        d["description"] = self.INJECT
        d["embed_html"] = ""  # force fallback link path
        out = render_video_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_player_stats_escapes(self):
        d = _full_player_stats_data()
        d["stats_rows"][0]["打率"] = self.INJECT
        out = render_player_stats_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_manager_comment_escapes(self):
        d = _full_manager_comment_data()
        d["quote_short"] = "前置き " + self.INJECT
        out = render_manager_comment_card(d)
        self.assertNotIn("<script>", out["content_html"])

    def test_player_comment_escapes(self):
        d = _full_player_comment_data()
        d["quote_short"] = "前置き " + self.INJECT
        out = render_player_comment_card(d)
        self.assertNotIn("<script>", out["content_html"])


# ---------------------------------------------------------------------------
# URL safety (10 renderers)
# ---------------------------------------------------------------------------


class UrlSafetyTests(unittest.TestCase):
    def test_lineup_javascript_url_dropped(self):
        d = _full_lineup_data()
        d["live_url"] = "javascript:alert(1)"
        d["source_url"] = "javascript:alert(2)"
        d["related_links"] = [
            {"url": "javascript:alert(3)", "label": "evil"},
            {"url": "https://example.com/safe", "label": "safe"},
        ]
        out = render_lineup_card(d)
        self.assertNotIn("javascript:", out["content_html"])
        self.assertNotIn("全打席速報はこちら", out["content_html"])
        self.assertIn("https://example.com/safe", out["content_html"])

    def test_postgame_javascript_url_dropped(self):
        d = _full_postgame_data()
        d["source_url"] = "javascript:alert(1)"
        out = render_postgame_card(d)
        self.assertNotIn("javascript:", out["content_html"])

    def test_official_notice_javascript_url_dropped(self):
        d = _full_official_notice_data()
        d["official_url"] = "javascript:alert(1)"
        d["source_url"] = "javascript:alert(2)"
        out = render_official_notice_card(d)
        self.assertNotIn("javascript:", out["content_html"])
        self.assertNotIn("NPB公式公示", out["content_html"])

    def test_pregame_javascript_url_dropped(self):
        d = _full_pregame_pitcher_data()
        d["official_url"] = "javascript:alert(1)"
        d["source_url"] = "javascript:alert(2)"
        out = render_pregame_pitcher_card(d)
        self.assertNotIn("javascript:", out["content_html"])

    def test_live_at_bats_javascript_url_dropped(self):
        d = _full_live_at_bats_data()
        d["source_url"] = "javascript:alert(1)"
        d["broadcast_info"] = [{"url": "javascript:alert(2)", "label": "evil"}]
        out = render_live_at_bats_card(d)
        self.assertNotIn("javascript:", out["content_html"])

    def test_broadcast_javascript_url_dropped(self):
        d = _full_broadcast_data()
        d["source_url"] = "javascript:alert(1)"
        out = render_broadcast_info_card(d)
        self.assertNotIn("javascript:", out["content_html"])

    def test_video_javascript_url_dropped(self):
        d = _full_video_data()
        d["video_url"] = "javascript:alert(1)"
        out = render_video_card(d)
        self.assertEqual(out["skip_reason"], "missing_video_fields")

    def test_video_javascript_in_source_url_dropped(self):
        d = _full_video_data()
        d["source_url"] = "javascript:alert(1)"
        out = render_video_card(d)
        self.assertNotIn("javascript:", out["content_html"])

    def test_player_stats_javascript_url_dropped(self):
        d = _full_player_stats_data()
        d["source_url"] = "javascript:alert(1)"
        out = render_player_stats_card(d)
        self.assertNotIn("javascript:", out["content_html"])

    def test_manager_comment_javascript_source_url_dropped(self):
        d = _full_manager_comment_data()
        d["source_url"] = "javascript:alert(1)"
        out = render_manager_comment_card(d)
        # source_url required + must be safe.
        self.assertEqual(out["skip_reason"], "missing_source_url")

    def test_player_comment_javascript_link_dropped(self):
        d = _full_player_comment_data()
        d["stats_link_url"] = "javascript:alert(1)"
        out = render_player_comment_card(d)
        self.assertNotIn("javascript:", out["content_html"])


# ---------------------------------------------------------------------------
# Forbidden phrasing guard (10 renderers)
# ---------------------------------------------------------------------------


class ForbiddenPhrasingTests(unittest.TestCase):
    def test_lineup_rejects_phrasing(self):
        d = _full_lineup_data()
        d["team_name"] = "巨人ｶｯﾀｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_lineup_card(d)

    def test_postgame_rejects_phrasing(self):
        d = _full_postgame_data()
        d["one_line_summary"] = "ｶｯﾀｶﾞﾈｰ！"
        with self.assertRaises(ValueError):
            render_postgame_card(d)

    def test_official_notice_rejects_phrasing(self):
        d = _full_official_notice_data()
        d["note"] = "ﾄﾞﾝﾏｲ"
        with self.assertRaises(ValueError):
            render_official_notice_card(d)

    def test_pregame_rejects_phrasing(self):
        d = _full_pregame_pitcher_data()
        d["matchups"][0]["pitcher_a"] = "戸郷ｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_pregame_pitcher_card(d)

    def test_live_at_bats_rejects_phrasing(self):
        d = _full_live_at_bats_data()
        d["notable_player_1"] = "岡本ｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_live_at_bats_card(d)

    def test_broadcast_rejects_phrasing(self):
        d = _full_broadcast_data()
        d["note"] = "ﾄﾞﾝﾏｲ"
        with self.assertRaises(ValueError):
            render_broadcast_info_card(d)

    def test_video_rejects_phrasing(self):
        d = _full_video_data()
        d["description"] = "ｶｯﾀｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_video_card(d)

    def test_player_stats_rejects_phrasing(self):
        d = _full_player_stats_data()
        d["player_name"] = "岡本ｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_player_stats_card(d)

    def test_manager_comment_rejects_phrasing(self):
        d = _full_manager_comment_data()
        d["quote_short"] = "勝てたぞｶｯﾀｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_manager_comment_card(d)

    def test_player_comment_rejects_phrasing(self):
        d = _full_player_comment_data()
        d["quote_short"] = "ﾏｹﾀｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_player_comment_card(d)


# ---------------------------------------------------------------------------
# Common footer + closing wording
# ---------------------------------------------------------------------------


class CommonFooterTests(unittest.TestCase):
    def _all_outputs(self):
        return [
            render_lineup_card(_full_lineup_data()),
            render_postgame_card(_full_postgame_data()),
            render_official_notice_card(_full_official_notice_data()),
            render_pregame_pitcher_card(_full_pregame_pitcher_data()),
            render_live_at_bats_card(_full_live_at_bats_data()),
            render_broadcast_info_card(_full_broadcast_data()),
            render_video_card(_full_video_data()),
            render_player_stats_card(_full_player_stats_data()),
            render_manager_comment_card(_full_manager_comment_data()),
            render_player_comment_card(_full_player_comment_data()),
        ]

    def test_footer_present_exactly_once_per_card(self):
        for out in self._all_outputs():
            with self.subTest(template=out["template_key"]):
                self.assertEqual(
                    out["content_html"].count('class="nomotoke-card-footer"'),
                    1,
                )
                self.assertIn(
                    "コメント・反応はコメント欄からお願いします。",
                    out["content_html"],
                )

    def test_no_nomotoke_phrasing_in_any_output(self):
        for out in self._all_outputs():
            with self.subTest(template=out["template_key"]):
                for bad in ("ｶｯﾀｶﾞﾈｰ", "ﾏｹﾀｶﾞﾈｰ", "ｶﾞﾈｰ", "ﾄﾞﾝﾏｲ"):
                    self.assertNotIn(bad, out["content_html"])


# ---------------------------------------------------------------------------
# Body section order snapshot
# ---------------------------------------------------------------------------


class BodyOrderTests(unittest.TestCase):
    def assert_order(self, html_str: str, markers):
        last = -1
        for marker in markers:
            idx = html_str.find(marker)
            self.assertGreater(
                idx, last, f"order broken at {marker!r}"
            )
            last = idx

    def test_lineup_order(self):
        out = render_lineup_card(_full_lineup_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "■ 2026年5月6日",
                "関連リンク",
                "この日のスタメンです。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_postgame_order(self):
        out = render_postgame_card(_full_postgame_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "試合スコア",
                "勝ちました。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_official_notice_order(self):
        out = render_official_notice_card(_full_official_notice_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "登録選手",
                "が登録です。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_pregame_order(self):
        out = render_pregame_pitcher_card(_full_pregame_pitcher_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "中継情報",
                "が先発です。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_live_at_bats_order(self):
        out = render_live_at_bats_card(_full_live_at_bats_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "■ 2026年5月6日",
                "打席結果",
                "投球結果",
                "随時更新します。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_broadcast_order(self):
        out = render_broadcast_info_card(_full_broadcast_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "中継予定",
                "この日の中継情報です。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_video_order(self):
        out = render_video_card(_full_video_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "<iframe",
                "選手のプレーです。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_player_stats_order(self):
        out = render_player_stats_card(_full_player_stats_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "対象日時:",
                "ここまでの成績です。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_manager_comment_order(self):
        out = render_manager_comment_card(_full_manager_comment_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "■ 2026年5月6日",
                "出典: スポーツニッポン",
                'class="nomotoke-quote"',
                "監督がコメントです。",
                'class="nomotoke-card-footer"',
            ],
        )

    def test_player_comment_order(self):
        out = render_player_comment_card(_full_player_comment_data())
        self.assert_order(
            out["content_html"],
            [
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "■ 2026年5月6日",
                "出典: スポーツニッポン",
                'class="nomotoke-quote"',
                "選手がコメントです。",
                'class="nomotoke-card-footer"',
            ],
        )


# ---------------------------------------------------------------------------
# Flag gating + select_renderer (all 10)
# ---------------------------------------------------------------------------


class FlagGatingTests(unittest.TestCase):
    def test_is_enabled_false_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENABLE_FLAG, None)
            self.assertFalse(is_enabled())

    def test_is_enabled_true_when_set(self):
        with mock.patch.dict(os.environ, {ENABLE_FLAG: "1"}):
            self.assertTrue(is_enabled())

    def test_require_enabled_raises_when_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENABLE_FLAG, None)
            with self.assertRaises(RuntimeError):
                require_enabled()

    def test_select_renderer_off_raises(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENABLE_FLAG, None)
            with self.assertRaises(RuntimeError):
                select_renderer(TEMPLATE_KEY_LINEUP)

    def test_select_renderer_unknown_raises(self):
        with mock.patch.dict(os.environ, {ENABLE_FLAG: "1"}):
            with self.assertRaises(ValueError):
                select_renderer("nomotoke_card_unknown_v1")

    def test_select_renderer_all_keys_on(self):
        expected = {
            TEMPLATE_KEY_LINEUP: render_lineup_card,
            TEMPLATE_KEY_LIVE_AT_BATS: render_live_at_bats_card,
            TEMPLATE_KEY_POSTGAME: render_postgame_card,
            TEMPLATE_KEY_OFFICIAL_NOTICE: render_official_notice_card,
            TEMPLATE_KEY_PREGAME_PITCHER: render_pregame_pitcher_card,
            TEMPLATE_KEY_BROADCAST: render_broadcast_info_card,
            TEMPLATE_KEY_VIDEO: render_video_card,
            TEMPLATE_KEY_PLAYER_STATS: render_player_stats_card,
            TEMPLATE_KEY_MANAGER_COMMENT: render_manager_comment_card,
            TEMPLATE_KEY_PLAYER_COMMENT: render_player_comment_card,
        }
        with mock.patch.dict(os.environ, {ENABLE_FLAG: "1"}):
            for key, fn in expected.items():
                with self.subTest(template=key):
                    self.assertIs(select_renderer(key), fn)


# ---------------------------------------------------------------------------
# Embed whitelist (video)
# ---------------------------------------------------------------------------


class EmbedWhitelistTests(unittest.TestCase):
    def test_youtube_iframe_preserved(self):
        out = render_video_card(_full_video_data())
        self.assertIn(
            "https://www.youtube.com/embed/abc123", out["content_html"]
        )
        self.assertIn("<iframe", out["content_html"])

    def test_evil_iframe_dropped_falls_back_to_link(self):
        d = _full_video_data()
        d["embed_html"] = (
            '<iframe src="https://evil.example.com/embed/x" '
            'width="560" height="315"></iframe>'
        )
        out = render_video_card(d)
        self.assertNotIn("evil.example.com", out["content_html"])
        self.assertNotIn("<iframe", out["content_html"])
        # fallback link present
        self.assertIn("決勝3ラン本塁打", out["content_html"])

    def test_iframe_with_script_dropped(self):
        d = _full_video_data()
        d["embed_html"] = (
            '<iframe src="https://www.youtube.com/embed/abc"></iframe>'
            "<script>alert(1)</script>"
        )
        out = render_video_card(d)
        self.assertNotIn("<iframe", out["content_html"])
        self.assertNotIn("<script>", out["content_html"])


# ---------------------------------------------------------------------------
# Quote-length / multiline guards (manager + player comment)
# ---------------------------------------------------------------------------


class QuoteGuardTests(unittest.TestCase):
    def test_manager_quote_at_cap_passes(self):
        d = _full_manager_comment_data()
        d["quote_short"] = "あ" * 100
        out = render_manager_comment_card(d)
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["skip_reason"], "")

    def test_manager_quote_over_cap_skipped(self):
        d = _full_manager_comment_data()
        d["quote_short"] = "あ" * 101
        out = render_manager_comment_card(d)
        self.assertEqual(out["skip_reason"], "quote_too_long")

    def test_manager_quote_multiline_skipped(self):
        d = _full_manager_comment_data()
        d["quote_short"] = "1行目\n2行目"
        out = render_manager_comment_card(d)
        self.assertEqual(out["skip_reason"], "quote_multiline_not_allowed")

    def test_player_quote_at_cap_passes(self):
        d = _full_player_comment_data()
        d["quote_short"] = "い" * 100
        out = render_player_comment_card(d)
        self.assertTrue(out["validation_ok"])

    def test_player_quote_over_cap_skipped(self):
        d = _full_player_comment_data()
        d["quote_short"] = "い" * 101
        out = render_player_comment_card(d)
        self.assertEqual(out["skip_reason"], "quote_too_long")

    def test_player_quote_multiline_skipped(self):
        d = _full_player_comment_data()
        d["quote_short"] = "A\nB"
        out = render_player_comment_card(d)
        self.assertEqual(out["skip_reason"], "quote_multiline_not_allowed")


# ---------------------------------------------------------------------------
# Comment renderer required field tests
# ---------------------------------------------------------------------------


class CommentRequiredTests(unittest.TestCase):
    def test_manager_missing_source_url(self):
        d = _full_manager_comment_data()
        d["source_url"] = ""
        out = render_manager_comment_card(d)
        self.assertEqual(out["skip_reason"], "missing_source_url")

    def test_player_missing_source_url(self):
        d = _full_player_comment_data()
        d["source_url"] = ""
        out = render_player_comment_card(d)
        self.assertEqual(out["skip_reason"], "missing_source_url")

    def test_manager_missing_quote_short(self):
        d = _full_manager_comment_data()
        d["quote_short"] = ""
        out = render_manager_comment_card(d)
        self.assertEqual(out["skip_reason"], "missing_quote_short")

    def test_player_missing_quote_short(self):
        d = _full_player_comment_data()
        d["quote_short"] = ""
        out = render_player_comment_card(d)
        self.assertEqual(out["skip_reason"], "missing_quote_short")

    def test_manager_html_structure(self):
        out = render_manager_comment_card(_full_manager_comment_data())
        self.assertIn(
            '<blockquote class="nomotoke-quote">', out["content_html"]
        )
        self.assertIn("阿部慎之助監督がコメントです。", out["content_html"])

    def test_player_html_structure(self):
        out = render_player_comment_card(_full_player_comment_data())
        self.assertIn(
            '<blockquote class="nomotoke-quote">', out["content_html"]
        )
        self.assertIn("岡本和真選手がコメントです。", out["content_html"])


# ---------------------------------------------------------------------------
# Tags formatting
# ---------------------------------------------------------------------------


class TagsFormattingTests(unittest.TestCase):
    def test_lineup_tags_filter_empty_and_unique(self):
        d = _full_lineup_data()
        d["opponent_name"] = ""
        d["own_starter"] = {"name": ""}
        out = render_lineup_card(d)
        self.assertIn("スタメン", out["tags"])
        self.assertIn("巨人", out["tags"])
        self.assertNotIn("", out["tags"])
        self.assertEqual(len(out["tags"]), len(set(out["tags"])))


# ---------------------------------------------------------------------------
# dedupe_key shape (per renderer)
# ---------------------------------------------------------------------------


class DedupeKeyShapeTests(unittest.TestCase):
    def test_lineup_shape(self):
        out = render_lineup_card(_full_lineup_data())
        self.assertEqual(out["dedupe_key"], "lineup:2026年5月6日:巨人:阪神")

    def test_postgame_shape(self):
        out = render_postgame_card(_full_postgame_data())
        self.assertEqual(out["dedupe_key"], "postgame:2026年5月6日:巨人:阪神")

    def test_official_notice_shape(self):
        out = render_official_notice_card(_full_official_notice_data())
        self.assertEqual(out["dedupe_key"], "announce:2026年5月6日:巨人")

    def test_pregame_shape(self):
        out = render_pregame_pitcher_card(_full_pregame_pitcher_data())
        self.assertEqual(out["dedupe_key"], "pregame:2026年5月6日")

    def test_live_at_bats_shape(self):
        out = render_live_at_bats_card(_full_live_at_bats_data())
        self.assertEqual(
            out["dedupe_key"], "live_at_bats:2026年5月6日:巨人:阪神"
        )

    def test_broadcast_shape(self):
        out = render_broadcast_info_card(_full_broadcast_data())
        self.assertEqual(
            out["dedupe_key"], "broadcast:2026年5月6日:巨人:阪神"
        )

    def test_video_shape(self):
        out = render_video_card(_full_video_data())
        self.assertEqual(
            out["dedupe_key"],
            "video:https://www.youtube.com/watch?v=abc123",
        )

    def test_player_stats_shape(self):
        out = render_player_stats_card(_full_player_stats_data())
        self.assertEqual(
            out["dedupe_key"],
            "player_stats:2026年5月6日時点:岡本和真:batting",
        )

    def test_manager_comment_shape(self):
        out = render_manager_comment_card(_full_manager_comment_data())
        # manager_comment:{date}:{manager}:{topic_hash 12}
        prefix, rest = out["dedupe_key"].split(":", 1)
        self.assertEqual(prefix, "manager_comment")
        parts = out["dedupe_key"].split(":")
        self.assertEqual(parts[0], "manager_comment")
        self.assertEqual(parts[1], "2026年5月6日")
        self.assertEqual(parts[2], "阿部慎之助")
        self.assertEqual(len(parts[3]), 12)

    def test_player_comment_shape(self):
        out = render_player_comment_card(_full_player_comment_data())
        parts = out["dedupe_key"].split(":")
        self.assertEqual(parts[0], "player_comment")
        self.assertEqual(parts[1], "2026年5月6日")
        self.assertEqual(parts[2], "岡本和真")
        self.assertEqual(len(parts[3]), 12)


# ---------------------------------------------------------------------------
# Closing wording (postgame win / loss / draw)
# ---------------------------------------------------------------------------


class ClosingLineWordingTests(unittest.TestCase):
    def test_postgame_win_closing(self):
        d = _full_postgame_data()
        d["result"] = "win"
        out = render_postgame_card(d)
        self.assertIn("勝ちました。", out["content_html"])

    def test_postgame_loss_closing(self):
        d = _full_postgame_data()
        d["result"] = "loss"
        out = render_postgame_card(d)
        self.assertIn("悔しい敗戦です。", out["content_html"])

    def test_postgame_draw_closing(self):
        d = _full_postgame_data()
        d["result"] = "draw"
        out = render_postgame_card(d)
        self.assertIn("引き分けでした。", out["content_html"])


# ---------------------------------------------------------------------------
# NOMOTOKE-BODY-FIX: short_news_url card body structure
# ---------------------------------------------------------------------------


class ShortNewsUrlBodyFixTests(unittest.TestCase):
    """Cover the のもとけ-style body assembled by render_short_news_url_card.

    The card must be a 事実カード with structured rows, an X tweet embed
    when an X URL is in related_links, and a short closing — never just
    "1 sentence + link". A body that would be too thin must skip with
    ``validation_failed:body_too_thin``.
    """

    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import render_short_news_url_card

        self._render = render_short_news_url_card

    def _data(self, **overrides):
        base = {
            "title": "巨人、ヤクルト戦に敗れ連敗",
            "summary": "巨人は0-5でヤクルトに敗戦、9回まで得点を奪えず連敗となった。",
            "source_url": "https://www.giants.jp/G/game/result/2026/0506.html",
            "source_name": "巨人公式X",
            "date_label": "2026年5月6日",
            "related_links": [
                {
                    "url": "https://x.com/TokyoGiants/status/2051932184391672900",
                    "label": "関連投稿: 巨人公式X",
                }
            ],
        }
        base.update(overrides)
        return base

    def test_body_includes_fact_card_with_extracted_score(self):
        out = self._render(self._data())
        self.assertTrue(out["validation_ok"])
        body = out["content_html"]
        self.assertIn("事実カード", body)
        self.assertIn("<th>スコア</th>", body)
        self.assertIn("<td>0-5</td>", body)
        self.assertIn("<th>出典</th>", body)
        self.assertIn("<td>巨人公式X</td>", body)
        self.assertIn("<th>公開日</th>", body)
        self.assertIn("<td>2026年5月6日</td>", body)

    def test_body_includes_x_tweet_blockquote_embed_when_x_in_related(self):
        out = self._render(self._data())
        body = out["content_html"]
        self.assertIn('class="twitter-tweet"', body)
        self.assertIn("yoshilover-x-embed", body)
        self.assertIn("platform.twitter.com/widgets.js", body)
        self.assertIn(
            "https://x.com/TokyoGiants/status/2051932184391672900", body
        )

    def test_body_uses_named_source_label_not_raw_url(self):
        out = self._render(self._data(source_label="巨人公式 試合結果"))
        body = out["content_html"]
        self.assertIn("巨人公式 試合結果", body)
        self.assertIn("出典記事", body)

    def test_body_lead_uses_summary_when_present(self):
        out = self._render(self._data())
        body = out["content_html"]
        self.assertIn("nomotoke-lead", body)
        self.assertIn(
            "巨人は0-5でヤクルトに敗戦、9回まで得点を奪えず連敗となった",
            body,
        )

    def test_body_too_thin_skipped_when_only_url_card_content(self):
        out = self._render(
            self._data(
                title="詳細はこちら",
                summary="",
                related_links=None,
            )
        )
        self.assertFalse(out["validation_ok"])
        self.assertEqual(out["skip_reason"], "validation_failed:body_too_thin")

    def test_body_too_thin_when_summary_just_repeats_title(self):
        out = self._render(
            self._data(
                title="巨人ニュース更新",
                summary="巨人ニュース更新",
                related_links=None,
            )
        )
        self.assertFalse(out["validation_ok"])
        self.assertEqual(out["skip_reason"], "validation_failed:body_too_thin")

    def test_body_passes_when_score_is_extractable(self):
        out = self._render(
            self._data(
                title="巨人 0-5 ヤクルト",
                summary="完封負け",
                related_links=None,
            )
        )
        self.assertTrue(out["validation_ok"])
        self.assertIn("<td>0-5</td>", out["content_html"])

    def test_game_kind_two_gun_detected_and_tagged(self):
        out = self._render(
            self._data(
                title="【二軍】巨人 1-6 ハヤテ 三塚琉生 本塁打",
                summary="二軍戦で大量失点、三塚は本塁打を放った。",
            )
        )
        self.assertTrue(out["validation_ok"])
        body = out["content_html"]
        self.assertIn("<td>二軍</td>", body)
        self.assertIn("二軍", out["tags"])

    def test_outcome_keywords_extracted_from_text(self):
        out = self._render(
            self._data(
                title="巨人、6-3でサヨナラ勝利 連勝飾る",
                summary="9回逆転サヨナラ勝利、3連勝で勢いを取り戻した。",
            )
        )
        body = out["content_html"]
        self.assertIn("<th>主な出来事</th>", body)
        self.assertTrue(
            "勝利" in body or "サヨナラ" in body or "連勝" in body or "逆転" in body
        )

    def test_summary_truncation_preserves_sentence_boundary(self):
        long_summary = "巨人は0-5でヤクルトに敗戦。" + ("内容を続ける文章。" * 30)
        out = self._render(self._data(summary=long_summary))
        body = out["content_html"]
        lead_para = body.split('class="nomotoke-lead">', 1)[1].split("</p>", 1)[0]
        self.assertLessEqual(len(lead_para), 220)
        self.assertTrue(lead_para.endswith("。") or lead_para.endswith("…"))

    def test_closing_is_short_and_not_seo_padding(self):
        out = self._render(self._data())
        body = out["content_html"]
        self.assertNotIn(
            "<p>詳細は出典をご覧ください。</p>", body
        )
        self.assertIn("ご意見・ご感想はコメント欄", body)

    def test_section_headers_present(self):
        out = self._render(self._data())
        body = out["content_html"]
        self.assertIn("<h3>🔗 出典記事</h3>", body)
        self.assertIn("<h3>📋 事実カード</h3>", body)


# ---------------------------------------------------------------------------
# NOMOTOKE-LINK-LABEL-FIX: anchor texts must be human-readable, not raw URLs
# ---------------------------------------------------------------------------


class LinkLabelFixTests(unittest.TestCase):
    """Render anchor text as ``{site}「{title}」`` / ``{source_name}「関連投稿」``.

    The body never echoes a raw URL outside the ``href`` attribute. Audit
    log + HTML comment keep the URL hash for downstream observers.
    """

    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import render_short_news_url_card

        self._render = render_short_news_url_card

    def _data(self, **overrides):
        base = {
            "title": "巨人、ヤクルト戦に敗れ連敗",
            "summary": "巨人は0-5でヤクルトに敗戦、9回まで得点を奪えず連敗となった。",
            "source_url": "https://www.giants.jp/G/game/result/2026/0506.html",
            "source_name": "巨人公式X",
            "date_label": "2026年5月6日",
            "related_links": [
                {
                    "url": "https://x.com/TokyoGiants/status/9999999",
                    "label": "関連投稿: 巨人公式X",
                }
            ],
        }
        base.update(overrides)
        return base

    @staticmethod
    def _visible_text(body: str) -> str:
        """Strip href values and tags so we only see what readers see."""
        v = re.sub(r'href="[^"]*"', "", body)
        v = re.sub(r"<[^>]+>", " ", v)
        v = re.sub(r"\s+", " ", v).strip()
        return v

    def test_giants_jp_renders_human_anchor_label_no_raw_url_visible(self):
        out = self._render(self._data())
        body = out["content_html"]
        self.assertIn("巨人公式サイト「巨人、ヤクルト戦に敗れ連敗」", body)
        # href attribute still carries the URL.
        self.assertIn(
            'href="https://www.giants.jp/G/game/result/2026/0506.html"',
            body,
        )
        # Visible text (with hrefs and tags removed) has no raw URL.
        visible = self._visible_text(body)
        self.assertNotIn("https://www.giants.jp/G/game/result/2026/0506.html", visible)
        self.assertNotIn("https://", visible)
        self.assertNotIn("http://", visible)

    def test_hochi_news_renders_sports_hochi_label(self):
        out = self._render(
            self._data(
                title="若林楽人、初のマルチ安打",
                source_url="https://hochi.news/articles/20260506-OHT1T51399.html",
                source_name="スポーツ報知 巨人",
            )
        )
        body = out["content_html"]
        self.assertIn(
            'スポーツ報知「若林楽人、初のマルチ安打」', body
        )

    def test_sanspo_renders_sansupo_label(self):
        out = self._render(
            self._data(
                title="竹丸和幸、自己ワースト5失点で2敗目",
                source_url=(
                    "https://www.sanspo.com/article/"
                    "20260506-CU4CQDMNXBG7LKSIVW7Q2V7CXI/"
                ),
                source_name="サンスポ巨人X",
            )
        )
        body = out["content_html"]
        self.assertIn("サンスポ「竹丸和幸、自己ワースト5失点で2敗目」", body)

    def test_x_blockquote_anchor_text_is_source_name_plus_kicker(self):
        out = self._render(self._data())
        body = out["content_html"]
        # Anchor text inside the X blockquote.
        self.assertIn("巨人公式X「関連投稿」", body)
        # href still carries the X URL.
        self.assertIn(
            'href="https://x.com/TokyoGiants/status/9999999"', body
        )
        # The X URL must NOT appear in visible text.
        visible = self._visible_text(body)
        self.assertNotIn("https://x.com/TokyoGiants/status/9999999", visible)

    def test_no_raw_url_anywhere_in_visible_body(self):
        out = self._render(self._data())
        visible = self._visible_text(out["content_html"])
        self.assertNotIn("https://", visible)
        self.assertNotIn("http://", visible)

    def test_unknown_host_falls_back_to_host_name_not_full_url(self):
        out = self._render(
            self._data(
                source_url="https://www.example-news.jp/path/article.html",
                title="不明ドメイン記事",
            )
        )
        body = out["content_html"]
        # Falls back to the host name (curated table miss).
        self.assertIn(
            'www.example-news.jp「不明ドメイン記事」', body
        )
        visible = self._visible_text(body)
        self.assertNotIn("https://www.example-news.jp", visible)

    def test_long_title_truncated_in_anchor_label(self):
        long_title = "巨人試合速報" + "あ" * 60
        out = self._render(self._data(title=long_title))
        body = out["content_html"]
        # Truncated labels end with the ellipsis.
        m = re.search(r"巨人公式サイト「([^」]+)」", body)
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1)), 32)
        self.assertTrue(m.group(1).endswith("…"))

    def test_source_label_override_wins_over_host_derivation(self):
        out = self._render(self._data(source_label="球団公式 試合結果ページ"))
        body = out["content_html"]
        # Override is used verbatim — no host-based prefix.
        self.assertIn("球団公式 試合結果ページ", body)
        # Default host-derived label is NOT used.
        self.assertNotIn("巨人公式サイト「巨人、ヤクルト戦に敗れ連敗」", body)


if __name__ == "__main__":
    unittest.main()
