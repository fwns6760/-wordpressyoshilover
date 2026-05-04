import os
import unittest
from unittest.mock import patch

from src import rss_fetcher
from src.article_quality_repair import repair_entity_mismatch


def _contaminated_body_text() -> str:
    return "\n".join(
        [
            "【故障・復帰の要旨】",
            "岡本和真の状態を整理する。",
            "【故障の詳細】",
            "読売ジャイアンツ所属の岡本和真は調整を続けている。",
            "【リハビリ状況・復帰見通し】",
            "巨人復帰後のプランを見る。",
            "【チームへの影響と今後の注目点】",
            "どこで復帰するか気になります。",
        ]
    )


def _contaminated_body_html() -> str:
    return (
        "<h2>【故障・復帰の要旨】</h2>"
        "<p>岡本和真の状態を整理する。</p>"
        "<h3>【故障の詳細】</h3>"
        "<p>読売ジャイアンツ所属の岡本和真は調整を続けている。</p>"
        "<h3>【リハビリ状況・復帰見通し】</h3>"
        "<p>巨人復帰後のプランを見る。</p>"
        "<h3>【チームへの影響と今後の注目点】</h3>"
        "<p>どこで復帰するか気になります。</p>"
        '<h3>💬 ファンの声（Xより）</h3><p>応援コメント。</p>'
        '<div class="yoshilover-related-posts">関連記事</div>'
    )


class ArticleQualityRepairTests(unittest.TestCase):
    def test_repair_entity_mismatch_rebuilds_non_giants_status_story(self):
        result = repair_entity_mismatch(
            current_title="岡本和真、昇格・復帰 関連情報",
            body_text=_contaminated_body_text(),
            body_html=_contaminated_body_html(),
            source_title="ブルージェイズ・岡本和真が3戦連発の9号2ラン 9回に反撃の一発放つも及ばず、勝率5割復帰お預け",
            source_summary="ブルージェイズで3試合連続本塁打となる9号2ランを放った。",
        )

        self.assertTrue(result.applied)
        self.assertTrue(result.repairable)
        self.assertNotEqual(result.title, "岡本和真、昇格・復帰 関連情報")
        self.assertTrue(result.title.startswith("ブルージェイズ・岡本和真が3戦連発"))
        self.assertIn("【岡本和真 近況】", result.body_text)
        self.assertIn("元読売ジャイアンツ・現ブルージェイズの岡本和真", result.body_text)
        self.assertNotIn("読売ジャイアンツ所属の岡本和真", result.body_text)
        self.assertIn("entity_mismatch_body_rebuilt", result.repair_flags)
        self.assertIn("yoshilover-related-posts", result.body_html)
        self.assertIn("💬 ファンの声（Xより）", result.body_html)

    def test_repair_entity_mismatch_keeps_stop_for_unrepairable_context(self):
        result = repair_entity_mismatch(
            current_title="上原浩治氏の話題を整理",
            body_text="【ニュースの整理】\n上原浩治氏のコメントを整理する。\n【次の注目】\n反応がどう広がるか気になります。",
            body_html="<h2>【ニュースの整理】</h2><p>上原浩治氏のコメントを整理する。</p>",
            source_title="元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ",
            source_summary="ボクシング世界戦を見て、ラウンド中に息をするのも忘れるくらいだったと語った。",
        )

        self.assertFalse(result.applied)
        self.assertFalse(result.repairable)
        self.assertEqual(result.stop_reason, "entity_mismatch_unrepairable:alumni_non_baseball_context")

    def test_maybe_apply_entity_mismatch_repair_allows_repaired_case_when_flag_is_on(self):
        source_title = "ブルージェイズ・岡本和真が3戦連発の9号2ラン 9回に反撃の一発放つも及ばず、勝率5割復帰お預け"
        source_summary = "ブルージェイズで3試合連続本塁打となる9号2ランを放った。"
        with patch.dict(
            os.environ,
            {
                "ENABLE_ENTITY_MISMATCH_REPAIR": "1",
                "ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "1",
            },
            clear=False,
        ):
            result = rss_fetcher._maybe_apply_entity_mismatch_repair(
                title="岡本和真、昇格・復帰 関連情報",
                body_text=_contaminated_body_text(),
                body_html=_contaminated_body_html(),
                source_title=source_title,
                source_summary=source_summary,
                article_subtype="player_recovery",
                source_refs={
                    "source_title": source_title,
                    "source_summary": source_summary,
                },
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["applied"])
        self.assertTrue(result["validation"]["ok"])
        self.assertNotIn("entity_mismatch:non_giants_team_prefix", result["validation"]["fail_axes"])
        self.assertIn("【岡本和真 近況】", result["body_text"])

    def test_maybe_apply_entity_mismatch_repair_keeps_stop_for_unrepairable_case(self):
        source_title = "元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ"
        source_summary = "ボクシング世界戦を見て、ラウンド中に息をするのも忘れるくらいだったと語った。"
        with patch.dict(
            os.environ,
            {
                "ENABLE_ENTITY_MISMATCH_REPAIR": "1",
                "ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "1",
            },
            clear=False,
        ):
            result = rss_fetcher._maybe_apply_entity_mismatch_repair(
                title="上原浩治氏の話題を整理",
                body_text="【ニュースの整理】\n上原浩治氏のコメントを整理する。\n【次の注目】\n反応がどう広がるか気になります。",
                body_html="<h2>【ニュースの整理】</h2><p>上原浩治氏のコメントを整理する。</p>",
                source_title=source_title,
                source_summary=source_summary,
                article_subtype="general",
                source_refs={
                    "source_title": source_title,
                    "source_summary": source_summary,
                },
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result["applied"])
        self.assertFalse(result["validation"]["ok"])
        self.assertIn(
            "entity_mismatch_repair:entity_mismatch_unrepairable:alumni_non_baseball_context",
            result["validation"]["fail_axes"],
        )

    def test_maybe_apply_entity_mismatch_repair_returns_none_when_flag_is_off(self):
        with patch.dict(os.environ, {"ENABLE_ENTITY_MISMATCH_REPAIR": "0"}, clear=False):
            result = rss_fetcher._maybe_apply_entity_mismatch_repair(
                title="岡本和真、昇格・復帰 関連情報",
                body_text=_contaminated_body_text(),
                body_html=_contaminated_body_html(),
                source_title="ブルージェイズ・岡本和真が3戦連発の9号2ラン",
                source_summary="ブルージェイズで3試合連続本塁打となる9号2ランを放った。",
                article_subtype="player_recovery",
                source_refs={},
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
