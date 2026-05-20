"""Unit tests for OB (元巨人) classifier — ticket 408 Phase 1.

Phase 1 scope:
- has_ob_literal_marker: literal marker detection (元巨人 / 巨人OB / 古巣巨人 / 巨人時代 等)
- is_known_ob_name: name table membership (Phase 2 で classifier に接続予定)
- _maybe_apply_ob_subtype: subtype override (non-game subtypes only)
- _detect_article_subtype integration: OB literal marker presence で `ob` subtype を返す

See: docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md §4
"""

from __future__ import annotations

import unittest

from src.ob_name_table import (
    OB_LITERAL_MARKERS,
    OB_NAME_SEED,
    has_ob_literal_marker,
    is_known_ob_name,
)


class OBLiteralMarkerTests(unittest.TestCase):
    def test_marker_set_is_non_empty_frozen(self):
        self.assertTrue(len(OB_LITERAL_MARKERS) >= 5)
        for marker in OB_LITERAL_MARKERS:
            self.assertTrue(isinstance(marker, str) and marker)

    def test_positive_match_motokyojin(self):
        title = "元巨人・高橋由伸氏が解説、阿部監督の采配を絶賛"
        self.assertTrue(has_ob_literal_marker(title))

    def test_positive_match_giants_ob(self):
        title = "巨人OB の上原浩治氏、MLB 引退後初の現役選手に直接アドバイス"
        self.assertTrue(has_ob_literal_marker(title))

    def test_positive_match_kosu_giants(self):
        title = "古巣巨人と対戦、内海哲也氏が NHK 中継で解説"
        self.assertTrue(has_ob_literal_marker(title))

    def test_positive_match_giants_era(self):
        title = "巨人時代の槙原寛己氏が選手会長として若手指導"
        self.assertTrue(has_ob_literal_marker(title))

    def test_negative_no_marker_in_postgame_title(self):
        title = "巨人 阿部監督が試合後にコメント、若手の活躍を称賛"
        self.assertFalse(has_ob_literal_marker(title))

    def test_negative_empty_string(self):
        self.assertFalse(has_ob_literal_marker(""))

    def test_negative_no_giants_context(self):
        title = "DeNA 三浦監督、横浜スタジアムでの逆転勝利を語る"
        self.assertFalse(has_ob_literal_marker(title))


class OBNameTableTests(unittest.TestCase):
    def test_name_seed_includes_well_known_obs(self):
        self.assertIn("高橋由伸", OB_NAME_SEED)
        self.assertIn("上原浩治", OB_NAME_SEED)
        self.assertIn("槙原寛己", OB_NAME_SEED)

    def test_name_seed_excludes_current_giants_staff(self):
        # Phase 1: 現在 巨人 staff (監督 / コーチ) は OB 名簿から除外
        # context judge は Phase 2 で追加
        self.assertNotIn("阿部慎之助", OB_NAME_SEED)
        self.assertNotIn("桑田真澄", OB_NAME_SEED)
        self.assertNotIn("杉内俊哉", OB_NAME_SEED)

    def test_is_known_ob_name_positive(self):
        self.assertTrue(is_known_ob_name("高橋由伸"))
        self.assertTrue(is_known_ob_name("上原浩治"))

    def test_is_known_ob_name_negative(self):
        self.assertFalse(is_known_ob_name("阿部慎之助"))
        self.assertFalse(is_known_ob_name(""))
        self.assertFalse(is_known_ob_name("架空 太郎"))

    def test_is_known_ob_name_strips_whitespace(self):
        self.assertTrue(is_known_ob_name(" 高橋由伸 "))


class MaybeApplyObSubtypeTests(unittest.TestCase):
    """rss_fetcher._maybe_apply_ob_subtype の単体テスト."""

    def _call(self, title: str, resolved_subtype: str) -> str:
        from src.rss_fetcher import _maybe_apply_ob_subtype

        return _maybe_apply_ob_subtype(title, resolved_subtype)

    def test_marker_in_title_general_subtype_overridden(self):
        result = self._call("元巨人・高橋由伸氏が解説", "general")
        self.assertEqual(result, "ob")

    def test_marker_in_title_player_subtype_overridden(self):
        result = self._call("巨人OB の上原浩治氏、MLB 引退語る", "player")
        self.assertEqual(result, "ob")

    def test_marker_in_title_player_notice_overridden(self):
        result = self._call("元巨人・松井秀喜氏、母校の指導者就任", "player_notice")
        self.assertEqual(result, "ob")

    def test_marker_in_title_roster_overridden(self):
        result = self._call("元巨人・矢野謙次氏、新球団との契約を表明", "roster")
        self.assertEqual(result, "ob")

    def test_marker_in_title_fact_notice_overridden(self):
        result = self._call("巨人OB の沢村栄治氏に関する誤報訂正", "fact_notice")
        self.assertEqual(result, "ob")

    def test_marker_in_postgame_title_not_overridden(self):
        # game-specific subtype は marker があっても OB に上書きしない
        result = self._call("巨人OB の上原氏も注目した 巨人 5-3 ヤクルト", "postgame")
        self.assertEqual(result, "postgame")

    def test_marker_in_lineup_title_not_overridden(self):
        result = self._call("元巨人・高橋氏の解説付き 巨人スタメン発表", "lineup")
        self.assertEqual(result, "lineup")

    def test_marker_in_farm_title_not_overridden(self):
        result = self._call("元巨人・矢野氏が二軍練習を視察", "farm")
        self.assertEqual(result, "farm")

    def test_marker_in_manager_title_not_overridden(self):
        result = self._call("元巨人・由伸氏 阿部監督と再会", "manager")
        self.assertEqual(result, "manager")

    def test_no_marker_preserves_subtype(self):
        result = self._call("巨人 阿部監督、若手起用を語る", "manager")
        self.assertEqual(result, "manager")

    def test_no_marker_general_preserved(self):
        result = self._call("読売新聞、新しい球場改修計画を報道", "general")
        self.assertEqual(result, "general")

    def test_empty_title_preserves_subtype(self):
        result = self._call("", "general")
        self.assertEqual(result, "general")


class DetectArticleSubtypeIntegrationTests(unittest.TestCase):
    """_detect_article_subtype 経由で OB override が効くかの統合テスト."""

    def _call(self, title: str, summary: str, category: str, has_game: bool = False) -> str:
        from src.rss_fetcher import _detect_article_subtype

        return _detect_article_subtype(title, summary, category, has_game)

    def test_ob_marker_in_player_category_returns_ob(self):
        result = self._call(
            "元巨人・高橋由伸氏、巨人 OB 会で若手にエール",
            "高橋由伸氏が巨人 OB 会に出席、若手選手へ激励のメッセージを送った。",
            "選手情報",
        )
        self.assertEqual(result, "ob")

    def test_ob_marker_in_kyojin_postgame_does_not_override(self):
        # 試合結果記事に OB が言及されていても postgame 維持
        result = self._call(
            "巨人 5-3 ヤクルト 巨人OB の上原氏も注目の好試合",
            "巨人は 9 回サヨナラ勝ち、5-3 でヤクルトを下した。",
            "試合速報",
            has_game=True,
        )
        self.assertEqual(result, "postgame")


if __name__ == "__main__":
    unittest.main()
