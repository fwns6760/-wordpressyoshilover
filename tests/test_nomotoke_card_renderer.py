"""Tests for src.nomotoke_card_renderer (NOMOTOKE-TEMPLATE-001 Phase 1)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from src.nomotoke_card_renderer import (
    ENABLE_FLAG,
    TEMPLATE_KEY_LINEUP,
    TEMPLATE_KEY_OFFICIAL_NOTICE,
    TEMPLATE_KEY_POSTGAME,
    TEMPLATE_KEY_PREGAME_PITCHER,
    is_enabled,
    render_lineup_card,
    render_official_notice_card,
    render_postgame_card,
    render_pregame_pitcher_card,
    require_enabled,
    select_renderer,
)


def _full_lineup_data() -> dict:
    return {
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "team_name": "巨人",
        "opponent_name": "阪神",
        "live_url": "https://example.com/live/123",
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


class HappyPathTests(unittest.TestCase):
    def test_lineup_card_happy_path(self):
        out = render_lineup_card(_full_lineup_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["skip_reason"], "")
        self.assertEqual(out["template_key"], TEMPLATE_KEY_LINEUP)
        self.assertIn("巨人、スタメン発表！！！", out["title"])
        self.assertIn("2026年5月6日", out["title"])
        self.assertIn("「巨人vs.阪神」", out["title"])
        self.assertIn("■ 2026年5月6日", out["content_html"])
        self.assertIn("全打席速報はこちら", out["content_html"])
        self.assertIn("丸佳浩", out["content_html"])
        self.assertIn("近本光司", out["content_html"])
        self.assertIn("中継情報", out["content_html"])
        self.assertIn("この日のスタメンです。", out["content_html"])

    def test_postgame_card_happy_path(self):
        out = render_postgame_card(_full_postgame_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_POSTGAME)
        self.assertIn("【試合結果、打席結果】", out["title"])
        self.assertIn("5-3で勝利！！！", out["title"])
        self.assertIn("終盤の集中打で勝利", out["title"])
        self.assertIn("試合スコア", out["content_html"])
        self.assertIn("打席結果", out["content_html"])
        self.assertIn("投球結果", out["content_html"])
        self.assertIn("対戦投手: 青柳晃洋", out["content_html"])
        self.assertIn("勝ちました。", out["content_html"])

    def test_official_notice_card_happy_path(self):
        out = render_official_notice_card(_full_official_notice_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_OFFICIAL_NOTICE)
        self.assertIn("【公示】2026年5月6日のプロ野球公示", out["title"])
        self.assertIn("巨人が登録", out["title"])
        self.assertIn("NPB公式公示", out["content_html"])
        self.assertIn("登録選手", out["content_html"])
        self.assertIn("秋広優人", out["content_html"])
        self.assertIn("現在の登録人数: 28人 / 残り枠: 2枠", out["content_html"])
        self.assertIn("が登録です。", out["content_html"])

    def test_pregame_pitcher_card_happy_path(self):
        out = render_pregame_pitcher_card(_full_pregame_pitcher_data())
        self.assertTrue(out["validation_ok"])
        self.assertEqual(out["template_key"], TEMPLATE_KEY_PREGAME_PITCHER)
        self.assertEqual(out["title"], "2026年5月6日の予告先発が発表される！！！")
        self.assertIn("NPB公式予告先発", out["content_html"])
        self.assertIn("巨人：戸郷翔征 / 阪神：青柳晃洋", out["content_html"])
        self.assertIn("DeNA：東克樹 / 広島：森下暢仁", out["content_html"])
        self.assertIn("中継情報", out["content_html"])
        self.assertIn("戸郷翔征が先発です。", out["content_html"])


class FieldMissingTests(unittest.TestCase):
    def test_lineup_card_missing_team_name(self):
        d = _full_lineup_data()
        d["team_name"] = ""
        out = render_lineup_card(d)
        self.assertFalse(out["validation_ok"])
        self.assertEqual(out["skip_reason"], "missing_team_name")

    def test_lineup_card_missing_lineup(self):
        d = _full_lineup_data()
        d["own_lineup"] = []
        out = render_lineup_card(d)
        self.assertEqual(out["skip_reason"], "missing_lineup_rows")

    def test_postgame_card_missing_score(self):
        d = _full_postgame_data()
        d["score"] = ""
        out = render_postgame_card(d)
        self.assertEqual(out["skip_reason"], "missing_score")

    def test_official_notice_card_missing_action(self):
        d = _full_official_notice_data()
        d["action"] = ""
        out = render_official_notice_card(d)
        self.assertEqual(out["skip_reason"], "missing_action")

    def test_pregame_pitcher_card_missing_matchups(self):
        d = _full_pregame_pitcher_data()
        d["matchups"] = []
        out = render_pregame_pitcher_card(d)
        self.assertEqual(out["skip_reason"], "missing_matchups")


class HtmlEscapeTests(unittest.TestCase):
    def test_lineup_escapes_script_tag(self):
        d = _full_lineup_data()
        d["own_lineup"][0]["player_name"] = "<script>alert(1)</script>"
        out = render_lineup_card(d)
        self.assertNotIn("<script>", out["content_html"])
        self.assertIn("&lt;script&gt;", out["content_html"])

    def test_postgame_escapes_script_tag(self):
        d = _full_postgame_data()
        d["atbat_results"][0]["player_name"] = "<script>x</script>"
        out = render_postgame_card(d)
        self.assertNotIn("<script>", out["content_html"])
        self.assertIn("&lt;script&gt;", out["content_html"])

    def test_official_notice_escapes_script_tag(self):
        d = _full_official_notice_data()
        d["registered"] = ["<script>alert(1)</script>"]
        out = render_official_notice_card(d)
        self.assertNotIn("<script>", out["content_html"])
        self.assertIn("&lt;script&gt;", out["content_html"])

    def test_pregame_pitcher_escapes_script_tag(self):
        d = _full_pregame_pitcher_data()
        d["matchups"][0]["pitcher_a"] = "<script>x</script>"
        out = render_pregame_pitcher_card(d)
        self.assertNotIn("<script>", out["content_html"])
        self.assertIn("&lt;script&gt;", out["content_html"])


class UrlSafetyTests(unittest.TestCase):
    def test_javascript_url_dropped_in_lineup_live_url(self):
        d = _full_lineup_data()
        d["live_url"] = "javascript:alert(1)"
        out = render_lineup_card(d)
        self.assertNotIn("javascript:", out["content_html"])
        self.assertNotIn("全打席速報はこちら", out["content_html"])

    def test_non_http_url_not_rendered_in_official_notice(self):
        d = _full_official_notice_data()
        d["official_url"] = "ftp://example.com/file"
        out = render_official_notice_card(d)
        self.assertNotIn("ftp://", out["content_html"])
        self.assertNotIn("NPB公式公示", out["content_html"])

    def test_javascript_url_dropped_in_link_list(self):
        d = _full_lineup_data()
        d["related_links"] = [
            {"url": "javascript:alert(1)", "label": "evil"},
            {"url": "https://example.com/safe", "label": "safe"},
        ]
        out = render_lineup_card(d)
        self.assertNotIn("javascript:", out["content_html"])
        self.assertIn("https://example.com/safe", out["content_html"])
        self.assertNotIn(">evil<", out["content_html"])


class ForbiddenPhrasingTests(unittest.TestCase):
    def test_postgame_rejects_nomotoke_phrasing_kattaganee(self):
        d = _full_postgame_data()
        d["one_line_summary"] = "ｶｯﾀｶﾞﾈｰ！"
        with self.assertRaises(ValueError):
            render_postgame_card(d)

    def test_postgame_rejects_nomotoke_phrasing_in_nested(self):
        d = _full_postgame_data()
        d["atbat_results"][0]["result"] = "ﾏｹﾀｶﾞﾈｰ"
        with self.assertRaises(ValueError):
            render_postgame_card(d)


class ClosingLineWordingTests(unittest.TestCase):
    def test_postgame_win_closing(self):
        d = _full_postgame_data()
        d["result"] = "win"
        out = render_postgame_card(d)
        self.assertIn("勝ちました。", out["content_html"])
        self.assertNotIn("ｶｯﾀｶﾞﾈｰ", out["content_html"])
        self.assertNotIn("ﾏｹﾀｶﾞﾈｰ", out["content_html"])

    def test_postgame_loss_closing(self):
        d = _full_postgame_data()
        d["result"] = "loss"
        out = render_postgame_card(d)
        self.assertIn("悔しい敗戦です。", out["content_html"])
        self.assertNotIn("ｶｯﾀｶﾞﾈｰ", out["content_html"])
        self.assertNotIn("ﾏｹﾀｶﾞﾈｰ", out["content_html"])

    def test_postgame_draw_closing(self):
        d = _full_postgame_data()
        d["result"] = "draw"
        out = render_postgame_card(d)
        self.assertIn("引き分けでした。", out["content_html"])
        self.assertNotIn("ｶｯﾀｶﾞﾈｰ", out["content_html"])
        self.assertNotIn("ﾏｹﾀｶﾞﾈｰ", out["content_html"])


class FlagGatingTests(unittest.TestCase):
    def test_is_enabled_false_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENABLE_FLAG, None)
            self.assertFalse(is_enabled())

    def test_is_enabled_true_when_set_to_1(self):
        with mock.patch.dict(os.environ, {ENABLE_FLAG: "1"}):
            self.assertTrue(is_enabled())

    def test_require_enabled_raises_when_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENABLE_FLAG, None)
            with self.assertRaises(RuntimeError):
                require_enabled()

    def test_select_renderer_raises_when_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENABLE_FLAG, None)
            with self.assertRaises(RuntimeError):
                select_renderer(TEMPLATE_KEY_LINEUP)

    def test_select_renderer_works_when_on(self):
        with mock.patch.dict(os.environ, {ENABLE_FLAG: "1"}):
            fn = select_renderer(TEMPLATE_KEY_LINEUP)
            self.assertIs(fn, render_lineup_card)
            fn = select_renderer(TEMPLATE_KEY_POSTGAME)
            self.assertIs(fn, render_postgame_card)
            fn = select_renderer(TEMPLATE_KEY_OFFICIAL_NOTICE)
            self.assertIs(fn, render_official_notice_card)
            fn = select_renderer(TEMPLATE_KEY_PREGAME_PITCHER)
            self.assertIs(fn, render_pregame_pitcher_card)


class UnknownTemplateKeyTests(unittest.TestCase):
    def test_unknown_template_key_raises_value_error(self):
        with mock.patch.dict(os.environ, {ENABLE_FLAG: "1"}):
            with self.assertRaises(ValueError):
                select_renderer("nomotoke_card_unknown_v1")


class TagsFormattingTests(unittest.TestCase):
    def test_lineup_tags_filter_empty_and_unique(self):
        d = _full_lineup_data()
        d["opponent_name"] = ""  # empty should be filtered out
        d["own_starter"] = {"name": ""}  # empty should be filtered out
        out = render_lineup_card(d)
        self.assertIn("スタメン", out["tags"])
        self.assertIn("巨人", out["tags"])
        self.assertNotIn("", out["tags"])
        # all unique
        self.assertEqual(len(out["tags"]), len(set(out["tags"])))


if __name__ == "__main__":
    unittest.main()
