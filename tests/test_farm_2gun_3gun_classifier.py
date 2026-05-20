"""Unit tests for farm 2軍 / 3軍 split classifier — ticket 409 Phase 1.

Phase 1 scope:
- _maybe_apply_farm_2gun_3gun_split: literal marker (3軍 / 三軍 / ３軍) で farm3_practice、
  イースタン / フューチャーズ で farm2_*、 marker なしは既存 subtype 維持 (backward-compat)
- _detect_article_subtype 統合: ドラフト・育成 + 3軍 marker → farm3_practice
- 既存 farm fixture の alias 経路 regression: marker なしの farm 系は不変

See: docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md §4
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class MaybeApplyFarm2gun3gunSplitTests(unittest.TestCase):
    """flag ON 時の split 挙動を verify。 default OFF は別 test class でカバー."""

    def setUp(self) -> None:
        self._env_patch = patch.dict(os.environ, {"ENABLE_FARM_2GUN_3GUN_SPLIT": "1"}, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()

    def _call(self, text: str, resolved_subtype: str) -> str:
        from src.rss_fetcher import _maybe_apply_farm_2gun_3gun_split

        return _maybe_apply_farm_2gun_3gun_split(text, resolved_subtype)

    # ── 3軍 marker → farm3_practice ──────────────────────────────
    def test_3gun_marker_farm_becomes_farm3_practice(self):
        result = self._call("巨人3軍 ヤクルト 練習試合 結果", "farm")
        self.assertEqual(result, "farm3_practice")

    def test_3gun_marker_farm_result_becomes_farm3_practice(self):
        result = self._call("巨人3軍 ヤクルト 5-4 で勝利", "farm_result")
        self.assertEqual(result, "farm3_practice")

    def test_3gun_marker_farm_lineup_becomes_farm3_practice(self):
        result = self._call("巨人3軍 スタメン発表 オープン戦", "farm_lineup")
        self.assertEqual(result, "farm3_practice")

    def test_sangun_kanji_marker_becomes_farm3_practice(self):
        result = self._call("巨人三軍 育成選手の活躍をスポットライト", "farm")
        self.assertEqual(result, "farm3_practice")

    def test_zenkaku_3gun_marker_becomes_farm3_practice(self):
        result = self._call("巨人３軍 練習試合 結果", "farm_result")
        self.assertEqual(result, "farm3_practice")

    # ── 2軍 explicit marker → farm2_* ────────────────────────────
    def test_eastern_marker_farm_becomes_farm2_result(self):
        result = self._call("巨人 イースタンリーグ ヤクルト 5-3 で勝利", "farm")
        self.assertEqual(result, "farm2_result")

    def test_eastern_marker_farm_result_becomes_farm2_result(self):
        result = self._call("イースタン公式戦 巨人 4-2 勝利", "farm_result")
        self.assertEqual(result, "farm2_result")

    def test_eastern_marker_farm_lineup_becomes_farm2_lineup(self):
        result = self._call("イースタン 巨人スタメン発表", "farm_lineup")
        self.assertEqual(result, "farm2_lineup")

    def test_futures_marker_becomes_farm2_result(self):
        result = self._call("フューチャーズ 巨人 西武 1-0 で勝利", "farm")
        self.assertEqual(result, "farm2_result")

    # ── marker なし → 不変 (backward-compat) ─────────────────────
    def test_no_marker_farm_preserved(self):
        result = self._call("巨人 二軍 選手の活躍", "farm")
        self.assertEqual(result, "farm")

    def test_no_marker_farm_result_preserved(self):
        result = self._call("巨人ファーム 3-2 で勝利", "farm_result")
        self.assertEqual(result, "farm_result")

    def test_no_marker_farm_lineup_preserved(self):
        result = self._call("巨人ファームスタメン発表", "farm_lineup")
        self.assertEqual(result, "farm_lineup")

    # ── 非 farm subtype → 不変 ───────────────────────────────────
    def test_non_farm_postgame_preserved(self):
        result = self._call("巨人3軍 引退試合の話題 (一軍試合のリード)", "postgame")
        self.assertEqual(result, "postgame")

    def test_non_farm_lineup_preserved(self):
        result = self._call("巨人スタメン 一軍公式戦", "lineup")
        self.assertEqual(result, "lineup")

    def test_non_farm_general_preserved(self):
        result = self._call("読売新聞報道、3軍 改革案 発表", "general")
        self.assertEqual(result, "general")

    def test_non_farm_ob_preserved(self):
        result = self._call("元巨人OBが3軍 練習を視察", "ob")
        self.assertEqual(result, "ob")

    # ── 3軍 marker 優先 over 2軍 marker (3軍 explicit はより rare) ────
    def test_both_markers_3gun_wins(self):
        # 同 text に両方含まれる場合 (rare)、 3軍 marker を優先
        # (例: 「イースタン 3軍 練習試合」のような曖昧 text)
        result = self._call("イースタン 3軍 練習試合 巨人", "farm")
        self.assertEqual(result, "farm3_practice")

    # ── empty text → 不変 ────────────────────────────────────────
    def test_empty_text_preserved(self):
        result = self._call("", "farm_result")
        self.assertEqual(result, "farm_result")


class DefaultOffPreservesFarmTests(unittest.TestCase):
    """default (flag OFF) では既存挙動を維持 (backward-compat regression)."""

    def _call(self, text: str, resolved_subtype: str) -> str:
        from src.rss_fetcher import _maybe_apply_farm_2gun_3gun_split

        return _maybe_apply_farm_2gun_3gun_split(text, resolved_subtype)

    def test_default_off_3gun_marker_does_not_split(self):
        # default OFF: 既存 ENABLE_FARM_SUBTYPE_SPLIT contract (三軍 → farm) を壊さない
        result = self._call("巨人3軍 ヤクルト 練習試合 結果", "farm")
        self.assertEqual(result, "farm")

    def test_default_off_eastern_marker_does_not_split(self):
        result = self._call("巨人 イースタンリーグ ヤクルト戦", "farm_result")
        self.assertEqual(result, "farm_result")


class DetectArticleSubtypeFarmIntegrationTests(unittest.TestCase):
    """_detect_article_subtype 経由で farm 2/3 split が効くかの統合テスト (flag ON)."""

    def setUp(self) -> None:
        self._env_patch = patch.dict(os.environ, {"ENABLE_FARM_2GUN_3GUN_SPLIT": "1"}, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()

    def _call(self, title: str, summary: str, category: str, has_game: bool = False) -> str:
        from src.rss_fetcher import _detect_article_subtype

        return _detect_article_subtype(title, summary, category, has_game)

    def test_3gun_in_farm_category_returns_farm3_practice(self):
        result = self._call(
            "巨人3軍 ヤクルト 練習試合で勝利",
            "5月20日、巨人3軍はヤクルト3軍と練習試合を行い 5-4 で勝利した。",
            "ドラフト・育成",
        )
        self.assertEqual(result, "farm3_practice")

    def test_eastern_in_farm_category_returns_farm2_result(self):
        result = self._call(
            "巨人 イースタンリーグ 公式戦 ヤクルト戦 結果",
            "イースタンリーグ公式戦、巨人は 4-2 でヤクルトを下した。",
            "ドラフト・育成",
        )
        self.assertEqual(result, "farm2_result")

    def test_farm_no_marker_preserved_backward_compat(self):
        # 既存 farm fixture: marker なしなら以前通り farm
        result = self._call(
            "巨人ファーム 選手の活躍",
            "巨人のファーム選手たちが地道に努力を重ねている。",
            "ドラフト・育成",
        )
        self.assertEqual(result, "farm")


class ValidatorRegistrationTests(unittest.TestCase):
    """新 subtype が validator dict に登録されているかの確認."""

    def test_farm2_result_in_strict_subtypes(self):
        from src.baseball_numeric_fact_consistency import STRICT_SUBTYPES

        self.assertIn("farm2_result", STRICT_SUBTYPES)
        self.assertIn("farm2_lineup", STRICT_SUBTYPES)

    def test_farm3_practice_in_lenient_subtypes(self):
        from src.baseball_numeric_fact_consistency import LENIENT_SUBTYPES

        self.assertIn("farm3_practice", LENIENT_SUBTYPES)
        self.assertIn("farm3_player", LENIENT_SUBTYPES)

    def test_farm3_in_subtype_policy(self):
        from src.long_body_compression_audit import SUBTYPE_POLICY

        self.assertIn("farm3_practice", SUBTYPE_POLICY)
        self.assertIn("farm3_player", SUBTYPE_POLICY)

    def test_farm2_aliases_in_subtype_aliases(self):
        from src.long_body_compression_audit import SUBTYPE_ALIASES

        # farm2_* は farm policy を共有 (backward-compat alias)
        self.assertEqual(SUBTYPE_ALIASES.get("farm2_result"), "farm")
        self.assertEqual(SUBTYPE_ALIASES.get("farm2_lineup"), "farm")

    def test_farm3_in_speculative_phrases(self):
        from src.title_style_validator import SPECULATIVE_PHRASES_BY_SUBTYPE

        self.assertIn("farm3_practice", SPECULATIVE_PHRASES_BY_SUBTYPE)
        self.assertIn("farm3_player", SPECULATIVE_PHRASES_BY_SUBTYPE)


if __name__ == "__main__":
    unittest.main()
