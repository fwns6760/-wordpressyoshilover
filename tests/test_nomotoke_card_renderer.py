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

    def test_postgame_card_adds_structural_emoji_headings(self):
        out = render_postgame_card(_full_postgame_data())
        self.assertIn("<h3>📊 試合スコア</h3>", out["content_html"])
        self.assertIn("<h3>📝 打席結果</h3>", out["content_html"])
        self.assertIn("<h3>⚾ 投球結果</h3>", out["content_html"])

    def test_official_notice_card_happy_path(self):
        out = render_official_notice_card(_full_official_notice_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_OFFICIAL_NOTICE)
        self.assertEqual(out["category"], "公示")
        self.assertIn("【公示】2026年5月6日", out["title"])
        self.assertIn("巨人が登録", out["title"])
        self.assertIn("が登録です。", out["content_html"])
        self.assertEqual(out["dedupe_key"], "announce:2026年5月6日:巨人")

    def test_official_notice_card_adds_structural_emoji_headings(self):
        out = render_official_notice_card(_full_official_notice_data())
        self.assertIn("<h3>✅ 登録選手</h3>", out["content_html"])

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
                'class="nomotoke-news-banner"',
                'class="nomotoke-meta"',
                'class="nomotoke-source"',
                "■ 2026年5月6日",
                "📝 打席結果",
                "⚾ 投球結果",
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
        # NOMOTOKE-BODY-FIX-2: 事実カード rows are now 対戦 / スコア / 種別 /
        # 主な出来事 — 見出し / 出典 / 公開日 are intentionally dropped because
        # they were redundant with the page title, top 出典 line, and meta
        # block. Score row is still required.
        out = self._render(self._data())
        self.assertTrue(out["validation_ok"])
        body = out["content_html"]
        self.assertIn("事実カード", body)
        self.assertIn("<th>スコア</th>", body)
        self.assertIn("<td>0-5</td>", body)
        # Removed-row guards.
        self.assertNotIn("<th>見出し</th>", body)
        self.assertNotIn("<th>出典</th>", body)
        self.assertNotIn("<th>公開日</th>", body)

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
        # NOMOTOKE-BODY-FIX-2 C3: the renderer-level closing line is gone
        # so the comment CTA exists exactly once, via _COMMON_FOOTER_HTML.
        out = self._render(self._data())
        body = out["content_html"]
        self.assertNotIn(
            "<p>詳細は出典をご覧ください。</p>", body
        )
        # The 💬 paragraph that previously appeared just above the common
        # footer must NOT be back — it would re-introduce the dual CTA.
        self.assertNotIn(
            "<p>💬 ご意見・ご感想はコメント欄からお寄せください。</p>", body
        )
        # Common footer remains exactly once.
        self.assertEqual(
            body.count("コメント欄からお願いします"), 1
        )

    def test_section_headers_present(self):
        out = self._render(self._data())
        body = out["content_html"]
        self.assertIn("<h3>🔗 出典記事</h3>", body)
        self.assertIn("<h3>📋 事実カード</h3>", body)


# ---------------------------------------------------------------------------
# NOMOTOKE-BODY-FIX-2: opponent / venue / game-index / inning-marker
# extractors and 対戦 row composition. Role-based 出典記事 label.
# ---------------------------------------------------------------------------


class BodyFix2FactExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import (
            _extract_short_news_facts,
            _build_match_row_value,
            _build_primary_source_role_label,
            render_short_news_url_card,
        )

        self._extract = _extract_short_news_facts
        self._build_match = _build_match_row_value
        self._role_label = _build_primary_source_role_label
        self._render = render_short_news_url_card

    def _data(self, **overrides):
        base = {
            "title": "巨人、ヤクルト戦に敗れ連敗",
            "summary": (
                "巨人は0-5でヤクルトに敗戦、9回まで得点を奪えず連敗となった。"
                "東京ドーム、9回戦。"
            ),
            "source_url": "https://www.giants.jp/G/game/result/2026/0506.html",
            "source_name": "巨人公式X",
            "date_label": "2026年5月6日",
            "related_links": [
                {
                    "url": "https://x.com/TokyoGiants/status/1",
                    "label": "関連投稿: 巨人公式X",
                }
            ],
        }
        base.update(overrides)
        return base

    def test_extract_opponent_picks_first_non_giants_team(self):
        f = self._extract("巨人、阪神戦に敗れ連敗", "")
        self.assertEqual(f.get("opponent"), "阪神")

    def test_extract_opponent_skips_giants_aliases(self):
        f = self._extract("巨人 ジャイアンツ ヤクルト戦", "")
        self.assertEqual(f.get("opponent"), "ヤクルト")

    def test_extract_opponent_returns_none_when_only_giants(self):
        f = self._extract("巨人、本日のスタメン発表", "")
        self.assertIsNone(f.get("opponent"))

    def test_extract_venue_long_alias_wins_over_short(self):
        # 「東京ドーム」 must match before 「東京D」 (long alias first).
        f = self._extract("東京ドームで試合", "")
        self.assertEqual(f.get("venue"), "東京ドーム")

    def test_extract_venue_recognizes_short_alias(self):
        f = self._extract("東京Dで試合", "")
        self.assertEqual(f.get("venue"), "東京ドーム")

    def test_extract_venue_jinguu_recognized(self):
        f = self._extract("神宮で試合", "")
        self.assertEqual(f.get("venue"), "神宮球場")

    def test_extract_game_index_recognized(self):
        f = self._extract("巨人 9回戦", "")
        self.assertEqual(f.get("game_index"), "9")

    def test_extract_inning_marker_recognized(self):
        f = self._extract("巨人 9回完封負け", "")
        self.assertEqual(f.get("inning_marker"), "9回完封")

    def test_match_row_includes_opponent_venue_game_index_inning(self):
        row = self._build_match(
            {
                "opponent": "ヤクルト",
                "venue": "東京ドーム",
                "game_index": "9",
                "inning_marker": "9回完封",
            }
        )
        self.assertEqual(row, "ヤクルト戦 / 東京ドーム / 9回戦 / 9回完封")

    def test_match_row_empty_when_no_opponent(self):
        row = self._build_match(
            {"venue": "東京ドーム", "game_index": "9"}
        )
        self.assertEqual(row, "")

    def test_match_row_skips_missing_components(self):
        row = self._build_match({"opponent": "ヤクルト"})
        self.assertEqual(row, "ヤクルト戦")

    def test_role_label_uses_site_plus_role(self):
        label = self._role_label(
            source_url="https://www.giants.jp/G/game/result.html",
            source_label_override="",
        )
        self.assertEqual(label, "巨人公式サイト 元記事")

    def test_role_label_override_wins(self):
        label = self._role_label(
            source_url="https://www.giants.jp/G/game/result.html",
            source_label_override="球団公式 試合結果ページ",
        )
        self.assertEqual(label, "球団公式 試合結果ページ")

    def test_role_label_unknown_host_falls_back_to_host(self):
        label = self._role_label(
            source_url="https://www.example-news.jp/path",
            source_label_override="",
        )
        self.assertEqual(label, "www.example-news.jp 元記事")

    def test_fact_card_renders_match_row_first(self):
        out = self._render(self._data())
        self.assertTrue(out["validation_ok"])
        body = out["content_html"]
        self.assertIn("<th>対戦</th>", body)
        # 対戦 row appears BEFORE スコア row
        match_pos = body.index("<th>対戦</th>")
        score_pos = body.index("<th>スコア</th>")
        self.assertLess(match_pos, score_pos)

    def test_fact_card_match_row_carries_opponent_venue_game_index(self):
        out = self._render(self._data())
        body = out["content_html"]
        # opponent appears, venue appears, game_index 9回戦 appears.
        self.assertIn("ヤクルト戦", body)
        self.assertIn("東京ドーム", body)
        self.assertIn("9回戦", body)

    def test_fact_card_dropped_rows_are_absent(self):
        out = self._render(self._data())
        body = out["content_html"]
        for label in ("見出し", "出典", "公開日"):
            self.assertNotIn(f"<th>{label}</th>", body)

    def test_h3_source_article_uses_role_label_not_title_echo(self):
        out = self._render(self._data())
        body = out["content_html"]
        # Role label inside the H3 出典記事 段, not the title.
        self.assertIn("巨人公式サイト 元記事", body)
        # The H3 paragraph wording is updated.
        self.assertIn("記事全文は", body)
        self.assertIn("をご覧ください", body)
        # Old wording must NOT remain.
        self.assertNotIn("で確認できます。", body)

    def test_comment_cta_exists_exactly_once(self):
        out = self._render(self._data())
        body = out["content_html"]
        # Single CTA via _COMMON_FOOTER_HTML; the renderer-level 💬
        # paragraph is gone. Both the duplicate paragraph AND the common
        # footer cannot co-exist.
        self.assertEqual(body.count("コメント欄からお願いします"), 1)
        self.assertNotIn(
            "ご意見・ご感想はコメント欄からお寄せください", body
        )

    def test_attribution_split_resolved_x_handle_only_in_related(self):
        # 巨人公式X (source_name) appears only inside the blockquote
        # anchor — no longer inside the fact card 出典 row, and (post
        # 2026-05-14 label unification) no longer inside the fan voice
        # h3 (which is now fixed `💬 ファンの声（Xより）` regardless of
        # source name).
        out = self._render(self._data())
        body = out["content_html"]
        # Count occurrences of the X handle.
        n = body.count("巨人公式X")
        # Only the blockquote anchor (`巨人公式X「...」`) carries the handle.
        self.assertEqual(n, 1)
        # 巨人公式サイト (host label) appears at top 出典 + H3 出典記事 anchor.
        self.assertGreaterEqual(body.count("巨人公式サイト"), 2)


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


# ---------------------------------------------------------------------------
# NOMOTOKE-BODY-EXTRACT-001 Phase 2A: lead extractor + og_description fact scan
# ---------------------------------------------------------------------------


class LeadSentenceExtractorTests(unittest.TestCase):
    """``_extract_lead_sentences`` is the verbatim-transcription guard
    for og:description. It must NEVER return the entire input when the
    input is longer than the cap, and it must collapse to the first
    1〜``max_sentences`` 「。」-terminated sentences within budget.
    """

    def setUp(self) -> None:
        from src.nomotoke_card_renderer import _extract_lead_sentences

        self._lead = _extract_lead_sentences

    def test_returns_first_sentence_when_default_max_two(self):
        text = (
            "巨人は0-5でヤクルトに敗戦、9回まで得点を奪えず連敗となった。"
            "試合詳細は球団公式ページで公開されている。"
            "次戦は阪神戦である。"
        )
        out = self._lead(text)
        self.assertTrue(out.startswith("巨人は0-5"))
        # Two sentences fit under 120 chars, so we get both — but never
        # the third one.
        self.assertNotIn("次戦は阪神戦", out)

    def test_truncates_long_first_sentence_with_ellipsis(self):
        text = "巨人の" + "解説文章" * 60 + "。"
        out = self._lead(text, char_cap=80)
        self.assertLessEqual(len(out), 81)  # 80 + ellipsis
        self.assertTrue(out.endswith("…"))

    def test_no_period_input_falls_back_to_char_cap(self):
        text = "巨人速報" + ("を伝えている" * 30)
        out = self._lead(text, char_cap=80)
        self.assertLessEqual(len(out), 81)
        self.assertTrue(out.endswith("…"))

    def test_short_input_returns_verbatim(self):
        text = "巨人、阪神戦に敗れ連敗。"
        out = self._lead(text)
        self.assertEqual(out, text)

    def test_empty_input_returns_empty(self):
        self.assertEqual(self._lead(""), "")
        self.assertEqual(self._lead(None), "")

    def test_never_returns_full_long_og_description_verbatim(self):
        # Real sanspo-shape og:description is ~250 chars. The lead must
        # NOT pass it through unchanged.
        long_desc = (
            "（セ・リーグ、巨人0-5ヤクルト、9回戦、ヤクルト6勝3敗、6日、東京D）"
            "巨人のドラフト1位・竹丸和幸投手（24）＝鷺宮製作所＝が6度目の先発。"
            "自己最多111球、同最長6回2/3を投じたが、自己ワーストとなる5失点で2敗目を喫した。"
            "巨人は今季4度目の零封負け。GW9連戦は3カード全て1勝2敗で負け越した。"
        )
        out = self._lead(long_desc)
        self.assertNotEqual(out, long_desc)
        self.assertLessEqual(len(out), 121)


class FactsOgDescriptionScanTests(unittest.TestCase):
    """``_extract_short_news_facts`` now scans og_description for opponent
    / venue / game_index / inning_marker. RSS title + summary inputs and
    their existing facts must be unchanged when og_description is empty.
    """

    def setUp(self) -> None:
        from src.nomotoke_card_renderer import _extract_short_news_facts

        self._extract = _extract_short_news_facts

    def test_default_og_description_empty_keeps_existing_behaviour(self):
        f1 = self._extract("巨人 0-5 阪神", "完封負け")
        f2 = self._extract("巨人 0-5 阪神", "完封負け", og_description="")
        self.assertEqual(f1, f2)

    def test_opponent_picked_from_og_description_when_absent_in_title(self):
        # X-feed title may be very sparse: 「巨人ニュース更新」.  og:description
        # is the layer that actually carries the opponent name.
        f = self._extract(
            "巨人ニュース",
            "詳細",
            og_description="（セ・リーグ、巨人0-5ヤクルト、9回戦、東京D）",
        )
        self.assertEqual(f.get("opponent"), "ヤクルト")

    def test_venue_picked_from_og_description(self):
        f = self._extract(
            "巨人ニュース",
            "",
            og_description="（巨人 阪神戦、東京D）",
        )
        self.assertEqual(f.get("venue"), "東京ドーム")

    def test_game_index_picked_from_og_description(self):
        f = self._extract(
            "巨人ニュース",
            "",
            og_description="（セ・リーグ、巨人0-3阪神、9回戦、東京D）",
        )
        self.assertEqual(f.get("game_index"), "9")

    def test_inning_marker_picked_from_og_description(self):
        f = self._extract(
            "巨人ニュース",
            "",
            og_description="9回完封勝ちで連勝",
        )
        self.assertEqual(f.get("inning_marker"), "9回完封")

    def test_score_already_in_title_not_overridden_by_og(self):
        # The first score wins (regex returns the first match across
        # title + summary + og_description), so a title-side score sticks.
        f = self._extract(
            "巨人 1-2 阪神",
            "",
            og_description="（巨人0-5阪神、9回戦）",
        )
        self.assertEqual(f.get("score"), "1-2")

    def test_score_recognizes_fullwidth_hyphen_minus(self):
        # Phase 2B: sanspo og:description uses U+FF0D (fullwidth dash).
        # The captured score still normalises to ASCII for the fact card.
        f = self._extract(
            "巨人ニュース",
            "",
            og_description="巨人0－5ヤクルト、9回戦、東京D",
        )
        self.assertEqual(f.get("score"), "0-5")

    def test_score_recognizes_choo_on_pu(self):
        # U+30FC (katakana-hiragana prolonged sound mark) appears in some
        # hochi articles when 3ー2 is typeset.
        f = self._extract(
            "巨人ニュース",
            "",
            og_description="巨人がわずか２安打で3ー2とヤクルトに競り勝ち",
        )
        self.assertEqual(f.get("score"), "3-2")

    def test_outcome_keyword_negake_detected(self):
        f = self._extract(
            "巨人ニュース",
            "",
            og_description="巨人は今季4度目の零封負け。",
        )
        outcomes = f.get("outcome_keywords", "")
        self.assertIn("負け", outcomes)


class RendererPhase2AOgWiringTests(unittest.TestCase):
    """The renderer reads ``primary_og_description`` from data when present
    and uses it for both lead-text and fact-card enrichment without
    overwriting RSS title / summary in the output payload.
    """

    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import render_short_news_url_card

        self._render = render_short_news_url_card

    def _data(self, **overrides):
        base = {
            "title": "巨人 試合速報",  # sparse RSS title
            "summary": "巨人 試合速報",  # sparse RSS summary
            "source_url": "https://www.sanspo.com/article/abc/",
            "source_name": "サンスポ巨人X",
            "date_label": "2026年5月7日",
            "related_links": [
                {
                    "url": "https://x.com/Sanspo_Giants/status/1",
                    "label": "関連投稿: サンスポ巨人X",
                }
            ],
            # Phase 2A optional fields — populated by the CLI's
            # _attach_source_extractor_facts then mirrored into data_preview.
            "primary_og_title": (
                "巨人D1位・竹丸和幸、自己ワースト5失点で2敗目"
            ),
            "primary_og_description": (
                "（セ・リーグ、巨人0-5ヤクルト、9回戦、ヤクルト6勝3敗、6日、東京D）"
                "巨人のドラフト1位・竹丸和幸投手（24）＝鷺宮製作所＝が6度目の先発。"
                "自己最多111球、同最長6回2/3を投じたが、自己ワーストとなる5失点で2敗目を喫した。"
                "巨人は今季4度目の零封負け。"
            ),
            "primary_published_at": "2026-05-06T17:50:49+09:00",
            "primary_canonical_url": "https://www.sanspo.com/article/abc/",
        }
        base.update(overrides)
        return base

    def test_lead_uses_og_description_first_sentence_not_full_text(self):
        out = self._render(self._data())
        body = out["content_html"]
        # The first og sentence is in the lead.
        self.assertIn(
            "（セ・リーグ、巨人0-5ヤクルト、9回戦、ヤクルト6勝3敗、6日、東京D）",
            body,
        )
        # The 4th sentence (零封負け) is past the cap and must NOT appear.
        self.assertNotIn("巨人は今季4度目の零封負け。", body)

    def test_fact_card_uses_og_description_for_opponent_venue_game_index(self):
        out = self._render(self._data())
        body = out["content_html"]
        # Opponent / venue / game_index / inning_marker came ONLY from
        # og:description — the RSS title / summary contained none of them.
        self.assertIn("<th>対戦</th>", body)
        self.assertIn("ヤクルト戦", body)
        self.assertIn("東京ドーム", body)
        self.assertIn("9回戦", body)

    def test_rss_title_summary_not_modified_in_output(self):
        # The renderer does NOT echo og:title in place of the RSS title.
        # ``out["title"]`` is the sanitized RSS title.
        out = self._render(self._data())
        self.assertEqual(out["title"], "巨人 試合速報")
        self.assertNotIn(
            "<p class=\"nomotoke-source\">出典: <a "
            "href=\"https://www.sanspo.com/article/abc/\" "
            "target=\"_blank\" rel=\"noopener\">竹丸和幸",
            out["content_html"],
        )

    def test_og_description_absent_falls_back_to_rss_summary(self):
        # When og:description is missing, the lead still works (RSS-only
        # behaviour preserved).
        out = self._render(
            self._data(
                primary_og_description="",
                summary="巨人は0-5でヤクルトに敗戦、9回まで得点を奪えず連敗となった。",
            )
        )
        body = out["content_html"]
        self.assertIn(
            "巨人は0-5でヤクルトに敗戦、9回まで得点を奪えず連敗となった",
            body,
        )

    def test_articleBody_sentinel_never_appears_in_body(self):
        # If a caller accidentally feeds the JSON-LD articleBody into
        # primary_og_description (which would be a regression), the lead
        # extractor must still cap it. Here we simulate by passing a
        # sentinel — even if it slipped in, only the first sentence
        # (under cap) would show; the rest is dropped.
        long_body = (
            "BODY_PARAGRAPH_SENTINEL_SHOULD_NOT_APPEAR_FULLY 巨人ニュース。"
            + ("追加文。" * 100)
        )
        out = self._render(self._data(primary_og_description=long_body))
        body = out["content_html"]
        # The 100x repetition is past 120 chars, must NOT all be present.
        self.assertLess(body.count("追加文"), 100)

    def test_visible_raw_url_still_zero_after_phase2a(self):
        out = self._render(self._data())
        body = out["content_html"]
        v = re.sub(r'href="[^"]*"', "", body)
        v = re.sub(r"<[^>]+>", " ", v)
        self.assertNotIn("https://", v)
        self.assertNotIn("http://", v)

    def test_x_only_short_news_path_unchanged(self):
        # X-only X URL with no external article URL still falls through
        # the router's no-draft path. Phase 2A wiring does not affect
        # that — the renderer is never reached. NOMOTOKE-TEMPLATE-
        # ROUTING-AUDIT-001 added a live-inning-blurb skip that triggers
        # earlier; either skip class proves the renderer was bypassed.
        from src.nomotoke_rss_router import route_rss_entry_to_nomotoke_card

        r = route_rss_entry_to_nomotoke_card(
            {
                "title": "【試合終了】巨人 0-5 ヤクルト",
                "summary": "",
                "link": "https://x.com/TokyoGiants/status/1",
                "published": "Wed, 06 May 2026 10:00:00 +0000",
            },
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/1",
        )
        self.assertFalse(r.matched)
        self.assertIn(
            r.skip_reason,
            {"live_inning_blurb_not_article", "x_post_not_article_source"},
        )


class Phase2CLeadSanitizerTests(unittest.TestCase):
    """NOMOTOKE-BODY-EXTRACT-001 Phase 2C: live X-RSS summaries embed
    ``<br>`` / ``<img>`` and visible URLs. The sanitizer must drop them
    BEFORE the lead truncation so the visible body never contains escaped
    HTML or raw http(s) URLs.
    """

    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import (
            _sanitize_lead_text,
            render_short_news_url_card,
        )

        self._sanitize = _sanitize_lead_text
        self._render = render_short_news_url_card

    # ----- _sanitize_lead_text contract -----

    def test_sanitize_strips_html_tags(self):
        self.assertEqual(
            self._sanitize("巨人 0-5 ヤクルト<br /><br />敗戦"),
            "巨人 0-5 ヤクルト 敗戦",
        )

    def test_sanitize_strips_img_tag_with_attributes(self):
        raw = (
            "敗戦"
            '<img height="2048" src="https://pbs.twimg.com/media/X.jpg?format=jpg" width="1365" />'
        )
        out = self._sanitize(raw)
        self.assertNotIn("<img", out)
        self.assertNotIn("pbs.twimg.com", out)
        self.assertEqual(out, "敗戦")

    def test_sanitize_drops_raw_http_urls(self):
        self.assertEqual(
            self._sanitize("詳細はこちら https://www.giants.jp/news/29638/"),
            "詳細はこちら",
        )

    def test_sanitize_decodes_pre_escaped_entities_then_strips(self):
        raw = "巨人&lt;br /&gt;0-5&lt;br /&gt;敗戦"
        self.assertEqual(self._sanitize(raw), "巨人 0-5 敗戦")

    def test_sanitize_collapses_whitespace(self):
        self.assertEqual(self._sanitize("巨人   　\n\n  ヤクルト"), "巨人 ヤクルト")

    def test_sanitize_handles_empty_and_none(self):
        self.assertEqual(self._sanitize(""), "")
        self.assertEqual(self._sanitize(None), "")
        self.assertEqual(self._sanitize(123), "")

    def test_sanitize_drops_trailing_partial_tag_from_router_truncation(self):
        # Router truncates `summary[:200]` and may slice mid-tag — the
        # remaining `<img height="2048" src="https://...` has no closing
        # `>`, so the closed-tag regex misses it. The sanitizer must drop
        # the orphan so it never reaches the visible body.
        raw = "敗戦 試合の詳細はこちら <img height=\"2048\" src=\"https://pbs.twimg.com/me"
        out = self._sanitize(raw)
        self.assertNotIn("<img", out)
        self.assertNotIn("pbs.twimg.com", out)
        self.assertNotIn("https://", out)
        self.assertEqual(out, "敗戦 試合の詳細はこちら")

    def test_sanitize_drops_trailing_partial_anchor_tag(self):
        raw = "詳細 <a href=\"https://example.com/very-long-url-truncated"
        out = self._sanitize(raw)
        self.assertNotIn("<a", out)
        self.assertNotIn("https://", out)
        self.assertEqual(out, "詳細")

    # ----- render-level integration -----

    def _data(self, **overrides):
        base = {
            "title": "【一軍】巨人 0-5 ヤクルト 竹丸6回2/3 5失点",
            "summary": (
                "【一軍】巨人 0-5 ヤクルト<br /><br />"
                "先発の #竹丸和幸 投手は6回2/3を投げ5失点。<br />"
                "得点を奪うことができず敗戦。<br /><br />"
                "試合の詳細はこちら<br />"
                "https://www.giants.jp/game/20260506_8003_1/<br />"
                '<img height="2048" src="https://pbs.twimg.com/media/HHnp.jpg?format=jpg" width="1365" />'
            ),
            "source_url": "https://www.giants.jp/game/20260506_8003_1/",
            "source_name": "巨人公式X",
            "date_label": "2026年5月6日",
            "related_links": [
                {
                    "url": "https://x.com/TokyoGiants/status/1",
                    "label": "関連投稿: 巨人公式X",
                }
            ],
        }
        base.update(overrides)
        return base

    def test_visible_lead_has_no_escaped_html_or_raw_url(self):
        out = self._render(self._data())
        self.assertTrue(out["validation_ok"])
        body = out["content_html"]
        # Pull just the lead block.
        lead_match = re.search(
            r'<p class="nomotoke-lead">([^<]*)</p>', body
        )
        self.assertIsNotNone(lead_match, "lead block missing")
        lead_text = lead_match.group(1) if lead_match else ""
        self.assertNotIn("&lt;br", lead_text)
        self.assertNotIn("&lt;img", lead_text)
        self.assertNotIn("pbs.twimg.com", lead_text)
        self.assertNotIn("https://", lead_text)
        self.assertNotIn("http://", lead_text)

    def test_visible_raw_url_zero_across_full_body_after_sanitize(self):
        out = self._render(self._data())
        body = out["content_html"]
        # Strip href attrs and tags — only the visible text remains.
        visible = re.sub(r'href="[^"]*"', "", body)
        visible = re.sub(r"src=\"[^\"]*\"", "", visible)
        visible = re.sub(r"<[^>]+>", " ", visible)
        self.assertNotIn("https://", visible)
        self.assertNotIn("http://", visible)
        self.assertNotIn("pbs.twimg.com", visible)


class NewsDigestBannerTests(unittest.TestCase):
    """Verify the gradient banner is emitted at the top of every card body
    (parity with the rss_fetcher.build_news_block X-passthrough path).
    """

    BANNER_CLASS = 'class="nomotoke-news-banner"'
    BANNER_GRADIENT = "background:linear-gradient(135deg,#001e62 0%,#e8272a 100%)"

    def _assert_banner_at_top(self, content_html: str, expected_source: str, expected_kicker: str) -> None:
        self.assertIn(self.BANNER_CLASS, content_html)
        self.assertIn(self.BANNER_GRADIENT, content_html)
        self.assertIn(f"📰 {expected_source}", content_html)
        self.assertIn(f"⚾ {expected_kicker}", content_html)
        banner_pos = content_html.find(self.BANNER_CLASS)
        meta_pos = content_html.find('class="nomotoke-meta"')
        source_pos = content_html.find('class="nomotoke-source"')
        if meta_pos >= 0:
            self.assertLess(banner_pos, meta_pos, "banner must precede meta")
        if source_pos >= 0:
            self.assertLess(banner_pos, source_pos, "banner must precede source line")

    def test_postgame_card_emits_banner(self):
        out = render_postgame_card(_full_postgame_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS GAME NOTE")

    def test_lineup_card_emits_banner(self):
        out = render_lineup_card(_full_lineup_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS GAME NOTE")

    def test_live_at_bats_card_emits_banner(self):
        out = render_live_at_bats_card(_full_live_at_bats_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS GAME NOTE")

    def test_pregame_pitcher_card_emits_banner(self):
        out = render_pregame_pitcher_card(_full_pregame_pitcher_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS GAME NOTE")

    def test_official_notice_card_emits_banner(self):
        out = render_official_notice_card(_full_official_notice_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS NEWS DIGEST")

    def test_video_card_emits_banner(self):
        out = render_video_card(_full_video_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS VIDEO")

    def test_player_stats_card_emits_banner(self):
        out = render_player_stats_card(_full_player_stats_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS PLAYER WATCH")

    def test_manager_comment_card_emits_banner(self):
        out = render_manager_comment_card(_full_manager_comment_data())
        # sponichi.* host hits the _PRIMARY_HOST_LABELS curated entry,
        # so the fallback resolves to "スポーツニッポン" not the bare netloc.
        self._assert_banner_at_top(out["content_html"], "スポーツニッポン", "GIANTS MANAGER NOTE")

    def test_player_comment_card_emits_banner(self):
        out = render_player_comment_card(_full_player_comment_data())
        # Player comment fixture uses sponichi.example.com source url.
        self.assertIn(self.BANNER_CLASS, out["content_html"])
        self.assertIn("📰", out["content_html"])
        self.assertIn("⚾ GIANTS PLAYER WATCH", out["content_html"])

    def test_broadcast_card_emits_banner(self):
        out = render_broadcast_info_card(_full_broadcast_data())
        self._assert_banner_at_top(out["content_html"], "example.com", "GIANTS BROADCAST")

    def test_banner_falls_back_to_host_label_when_source_label_missing(self):
        data = _full_postgame_data()
        data["source_label"] = ""
        data["source_url"] = "https://example.com/game/123"
        out = render_postgame_card(data)
        self.assertIn(self.BANNER_CLASS, out["content_html"])
        self.assertIn("📰", out["content_html"])


if __name__ == "__main__":
    unittest.main()
