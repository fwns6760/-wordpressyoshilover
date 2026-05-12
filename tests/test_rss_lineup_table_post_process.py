"""Tests for the narrow lineup-table post-process.

The post-process detects 9-batter (or 8-batter for DH-less leagues) prose
lineup patterns in RSS-auto bodies and wraps them in an HTML <table>, plus
the nomotoke-card-* markers so the downstream enrichment fires.

The whole module is gated by ``ENABLE_RSS_LINEUP_TABLE_POST_PROCESS`` env
flag (default OFF). When the flag is OFF, the function MUST return the
input unchanged byte-for-byte.
"""

import unittest

from src.rss_lineup_table_post_process import (
    ENABLE_RSS_LINEUP_TABLE_POST_PROCESS_ENV,
    inject_lineup_table_if_enabled,
)


def _env(flag_on: bool) -> dict:
    return {ENABLE_RSS_LINEUP_TABLE_POST_PROCESS_ENV: "1"} if flag_on else {}


class RssLineupTablePostProcessTests(unittest.TestCase):
    def test_flag_off_returns_input_unchanged(self):
        content = (
            "<p>巨人のスタメンが発表された。スポーツ報知によると、以下の打順になる。</p>"
            "<p>1番 セカンド 吉川尚輝</p>"
            "<p>2番 ショート 中山礼都</p>"
            "<p>3番 センター 丸佳浩</p>"
            "<p>4番 サード 岡本和真</p>"
            "<p>5番 ライト 浅野翔吾</p>"
            "<p>6番 レフト 佐々木俊輔</p>"
            "<p>7番 ファースト ヘルナンデス</p>"
            "<p>8番 キャッチャー 大城卓三</p>"
            "<p>9番 投手 戸郷翔征</p>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="lineup_v1",
            env_getter=_env(False).get,
        )

        self.assertEqual(result, content)

    def test_flag_on_lineup_template_and_pattern_injects_table(self):
        content = (
            "<p>巨人のスタメンが発表された。スポーツ報知によると、以下の打順になる。</p>"
            "<p>1番 セカンド 吉川尚輝</p>"
            "<p>2番 ショート 中山礼都</p>"
            "<p>3番 センター 丸佳浩</p>"
            "<p>4番 サード 岡本和真</p>"
            "<p>5番 ライト 浅野翔吾</p>"
            "<p>6番 レフト 佐々木俊輔</p>"
            "<p>7番 ファースト ヘルナンデス</p>"
            "<p>8番 キャッチャー 大城卓三</p>"
            "<p>9番 投手 戸郷翔征</p>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="lineup_v1",
            env_getter=_env(True).get,
        )

        self.assertNotEqual(result, content)
        self.assertIn("<table", result)
        self.assertIn("吉川尚輝", result)
        self.assertIn("戸郷翔征", result)
        self.assertIn("nomotoke-card-divider", result)
        self.assertIn("nomotoke-card-footer", result)

    def test_flag_on_but_template_not_lineup_returns_unchanged(self):
        content = (
            "<p>1番 セカンド 吉川尚輝</p>"
            "<p>2番 ショート 中山礼都</p>"
            "<p>3番 センター 丸佳浩</p>"
            "<p>4番 サード 岡本和真</p>"
            "<p>5番 ライト 浅野翔吾</p>"
            "<p>6番 レフト 佐々木俊輔</p>"
            "<p>7番 ファースト ヘルナンデス</p>"
            "<p>8番 キャッチャー 大城卓三</p>"
            "<p>9番 投手 戸郷翔征</p>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="postgame_strict_v1",
            env_getter=_env(True).get,
        )

        self.assertEqual(result, content)

    def test_flag_on_lineup_but_no_pattern_returns_unchanged(self):
        # Prose lineup article without the "N番 ..." sequence — leave unchanged.
        content = (
            "<p>巨人のスタメンが発表された。一軍の主力選手が顔をそろえる見込みで、"
            "ベンチワークの意図やコンディションを整理しながら試合に臨む。</p>"
            "<p>参照元: スポーツ報知 https://example.com/lineup</p>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="lineup_v1",
            env_getter=_env(True).get,
        )

        self.assertEqual(result, content)

    def test_flag_on_content_already_has_nomotoke_marker_returns_unchanged(self):
        # If the body already carries the nomotoke marker, the enrichment is
        # already wired through manual_intake / 3-auto-jobs path. Skip silently
        # so we never double-render.
        content = (
            "<p>巨人のスタメン。</p>"
            "<table class=\"nomotoke-card-table\"><tr><td>1番 吉川</td></tr></table>"
            "<hr class=\"nomotoke-card-divider\">"
            "<div class=\"nomotoke-card-footer\">参考: スポーツ報知</div>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="lineup_v1",
            env_getter=_env(True).get,
        )

        self.assertEqual(result, content)

    def test_flag_on_partial_lineup_below_threshold_returns_unchanged(self):
        # Only 2 batter lines — should not be treated as a lineup. Avoid
        # false positives where someone mentions "1番 X 2番 Y" in prose.
        content = (
            "<p>巨人のスタメンが発表された。</p>"
            "<p>1番 セカンド 吉川尚輝</p>"
            "<p>2番 ショート 中山礼都</p>"
            "<p>本日は雨天で開始時刻が遅れる可能性がある。</p>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="lineup_v1",
            env_getter=_env(True).get,
        )

        self.assertEqual(result, content)

    def test_flag_on_farm_lineup_template_also_works(self):
        content = (
            "<p>巨人二軍のスタメンが発表された。</p>"
            "<p>1番 セカンド 増田陸</p>"
            "<p>2番 ショート 湯浅大</p>"
            "<p>3番 センター 萩尾匡也</p>"
            "<p>4番 ファースト 北村拓己</p>"
            "<p>5番 ライト 喜多隆介</p>"
            "<p>6番 レフト 浦田俊輔</p>"
            "<p>7番 サード 三塚琉生</p>"
            "<p>8番 キャッチャー 山瀬慎之助</p>"
            "<p>9番 投手 京本眞</p>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="farm_lineup_v1",
            env_getter=_env(True).get,
        )

        self.assertIn("<table", result)
        self.assertIn("京本眞", result)
        self.assertIn("nomotoke-card-divider", result)

    def test_eight_batter_pa_lineup_also_works(self):
        # DH-less / pitcher hits 9th — 8 position players plus pitcher.
        # The detector should accept 8 or 9 consecutive 番 lines.
        content = (
            "<p>巨人のスタメンが発表された。</p>"
            "<p>1番 セカンド 吉川尚輝</p>"
            "<p>2番 ショート 中山礼都</p>"
            "<p>3番 センター 丸佳浩</p>"
            "<p>4番 サード 岡本和真</p>"
            "<p>5番 ライト 浅野翔吾</p>"
            "<p>6番 レフト 佐々木俊輔</p>"
            "<p>7番 ファースト ヘルナンデス</p>"
            "<p>8番 キャッチャー 大城卓三</p>"
        )

        result = inject_lineup_table_if_enabled(
            content,
            template_key="lineup_v1",
            env_getter=_env(True).get,
        )

        self.assertIn("<table", result)
        self.assertIn("大城卓三", result)

    def test_empty_content_returns_unchanged(self):
        for value in ("", None):
            with self.subTest(value=value):
                result = inject_lineup_table_if_enabled(
                    value or "",
                    template_key="lineup_v1",
                    env_getter=_env(True).get,
                )
                self.assertEqual(result, value or "")


if __name__ == "__main__":
    unittest.main()
