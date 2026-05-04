import unittest

from src import article_quality_guards as guards


class ArticleQualityGuardsTests(unittest.TestCase):
    def test_sanitize_forbidden_visible_text_rewrites_headings_and_phrases(self):
        text = "\n".join(
            [
                "【発信内容の要約】",
                "この話題は目を引きます。",
                "【文脈と背景】",
                "source にある範囲だけで整理します。",
            ]
        )

        sanitized = guards.sanitize_forbidden_visible_text(text)

        self.assertIn("【投稿で出ていた内容】", sanitized)
        self.assertIn("【この話が出た流れ】", sanitized)
        self.assertNotIn("目を引きます", sanitized)
        self.assertNotIn("source にある範囲だけで", sanitized)

    def test_find_forbidden_phrase_ignores_source_quote_text(self):
        hit = guards.find_forbidden_phrase("阿部監督は「目を引きます」とだけ話した。")

        self.assertIsNone(hit)

    def test_find_forbidden_phrase_detects_visible_heading(self):
        hit = guards.find_forbidden_phrase("【文脈と背景】\n起用意図を整理する。")

        self.assertIsNotNone(hit)
        self.assertEqual(hit["label"], "heading_context_background")

    def test_find_quote_integrity_issue_detects_unbalanced_quote(self):
        issue = guards.find_quote_integrity_issue("阿部監督は「次も同じ形でいきたいと話した。")

        self.assertIsNotNone(issue)
        self.assertEqual(issue["reason"], "unbalanced_corner_quote")

    def test_find_duplicate_sentence_detects_near_duplicate(self):
        issue = guards.find_duplicate_sentence(
            "戸郷翔征が7回1失点で試合を作った。"
            "戸郷翔征が7回1失点で試合を作った。"
            "打線は終盤に勝ち越した。"
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["reason"], "near_duplicate_sentence")

    def test_detect_source_entity_conflict_detects_non_giants_team_prefix(self):
        issue = guards.detect_source_entity_conflict(
            "ブルージェイズ・岡本和真が実戦復帰へ前進",
            "ブルージェイズでの実戦復帰プランが進んでいる。",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["reason"], "non_giants_team_prefix")
        self.assertEqual(issue["team"], "ブルージェイズ")

    def test_detect_source_entity_conflict_detects_alumni_non_baseball_context(self):
        issue = guards.detect_source_entity_conflict(
            "元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ",
            "ラウンド中に息をするのも忘れるくらいだったとボクシング世界戦を語った。",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["reason"], "alumni_non_baseball_context")

    def test_detect_source_entity_conflict_allows_baseball_story(self):
        issue = guards.detect_source_entity_conflict(
            "巨人・松浦慶斗が緊急リリーフで無失点",
            "二軍戦で松浦慶斗投手が登板し、一軍昇格候補として注目される。",
        )

        self.assertIsNone(issue)


if __name__ == "__main__":
    unittest.main()
