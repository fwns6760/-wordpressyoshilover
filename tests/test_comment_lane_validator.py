import unittest

from src.comment_lane_validator import FAIL_TAG_NORMALIZATION, normalize_fail_tags, validate_comment_lane_draft


class CommentLaneValidatorTests(unittest.TestCase):
    def _base_draft(self):
        return {
            "title": "阿部監督、試合後の浅野に「積極性が良かった」",
            "speaker_name": "阿部監督",
            "scene_type": "試合後",
            "target_entity": "浅野",
            "quote_core": "積極性が良かった",
            "source_ref": "スポーツ報知",
            "quote_source": "スポーツ報知",
            "quote_source_type": "major_web",
            "trust_tier": "fact",
            "game_id": None,
            "opponent": None,
            "scoreline": None,
            "team_result": None,
            "downstream_link": "次戦でも同じ姿勢を求めた",
            "fact_header": "スポーツ報知によると、阿部監督が試合後に浅野の起用意図を説明した。",
            "lede": "阿部監督は試合後に浅野の起用意図として「積極性が良かった」と語り、次戦でも同じ姿勢を求めた。",
            "quote_block": "スポーツ報知が伝えたコメントは「積極性が良かった」。",
            "context": "試合後の振り返りで浅野の初回打席に触れた。",
            "related": "次戦で同じ起用を続けるかが次の焦点になる。",
        }

    def test_good_examples_pass_validator(self):
        cases = [
            (
                "阿部監督、試合後の浅野に「積極性が良かった」",
                "試合後",
                "浅野",
                "積極性が良かった",
            ),
            (
                "岡本、満塁本塁打後に「狙い通り」",
                "満塁本塁打後",
                "岡本",
                "狙い通り",
            ),
            (
                "山崎、オフのキャンプ初日に「今年は打ちます」",
                "オフのキャンプ初日",
                "山崎",
                "今年は打ちます",
            ),
        ]

        for title, scene, speaker, nucleus in cases:
            with self.subTest(title=title):
                draft = self._base_draft()
                draft["title"] = title
                draft["speaker_name"] = speaker
                draft["scene_type"] = scene
                draft["target_entity"] = speaker if speaker != "阿部監督" else "浅野"
                draft["quote_core"] = nucleus
                draft["fact_header"] = f"スポーツ報知によると、{speaker}が{scene}に発言した。"
                draft["lede"] = f"{speaker}は{scene}に「{nucleus}」と話し、次戦でも同じ姿勢を求めた。"
                draft["quote_block"] = f"スポーツ報知が伝えたコメントは「{nucleus}」。"
                draft["context"] = f"{scene}の文脈で{draft['target_entity']}に触れた。"
                result = validate_comment_lane_draft(draft)
                self.assertTrue(result.ok)
                self.assertEqual(result.raw_fail_tags, ())

    def test_bad_examples_trigger_title_generic(self):
        cases = [
            "巨人の試合後コメントをどう見る",
            "選手の本音に迫る",
            "巨人コメントまとめ",
            "Xがコメント",
        ]

        for title in cases:
            with self.subTest(title=title):
                draft = self._base_draft()
                draft["title"] = title
                result = validate_comment_lane_draft(draft)
                self.assertIn("TITLE_GENERIC", result.soft_fail_tags)

    def test_game_result_conflict_is_hard_fail(self):
        draft = self._base_draft()
        draft["scoreline"] = "3-2"
        draft["team_result"] = "win"
        draft["game_id"] = "G20260423"
        draft["fact_header"] = "スポーツ報知によると、阿部監督が試合後に2-3の敗戦を振り返った。"
        draft["lede"] = "阿部監督は試合後に「積極性が良かった」と話し、敗戦でも次戦につながるとした。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("GAME_RESULT_CONFLICT", result.hard_fail_tags)
        self.assertIn("fact_missing", result.normalized_fail_tags)

    def test_no_game_but_result_is_hard_fail(self):
        draft = self._base_draft()
        draft["fact_header"] = "スポーツ報知によると、巨人は3-2で勝利し、阿部監督が試合後に振り返った。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("NO_GAME_BUT_RESULT", result.hard_fail_tags)

    def test_speaker_missing_is_hard_fail(self):
        draft = self._base_draft()
        draft["speaker_name"] = ""

        result = validate_comment_lane_draft(draft)

        self.assertIn("SPEAKER_MISSING", result.hard_fail_tags)

    def test_quote_ungrounded_is_hard_fail(self):
        draft = self._base_draft()
        draft["source_ref"] = ""
        draft["quote_source"] = ""
        draft["fact_header"] = "阿部監督が試合後に浅野の起用意図を説明した。"
        draft["quote_block"] = "「積極性が良かった」。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("QUOTE_UNGROUNDED", result.hard_fail_tags)

    def test_title_body_entity_mismatch_is_hard_fail(self):
        draft = self._base_draft()
        draft["title"] = "阿部監督、試合後に「積極性が良かった」"
        draft["speaker_name"] = "阿部監督"
        draft["fact_header"] = "スポーツ報知によると、岡本が試合後にコメントした。"
        draft["lede"] = "岡本は試合後に「積極性が良かった」と話し、次戦でも同じ姿勢を求めた。"
        draft["context"] = "岡本の打席内容を振り返った。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("TITLE_BODY_ENTITY_MISMATCH", result.hard_fail_tags)
        self.assertIn("title_body_mismatch", result.normalized_fail_tags)

    def test_source_trust_too_low_is_hard_fail(self):
        draft = self._base_draft()
        draft["trust_tier"] = "reaction"
        draft["quote_source_type"] = "fan_reaction"
        draft["source_ref"] = "一般ファン投稿"
        draft["quote_source"] = "一般ファン投稿"
        draft["fact_header"] = "一般ファン投稿によると、阿部監督が試合後にコメントした。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("SOURCE_TRUST_TOO_LOW", result.hard_fail_tags)

    def test_title_missing_scene_is_soft_fail(self):
        draft = self._base_draft()
        draft["title"] = "阿部監督、「積極性が良かった」"

        result = validate_comment_lane_draft(draft)

        self.assertIn("TITLE_MISSING_SCENE", result.soft_fail_tags)

    def test_title_missing_nucleus_is_soft_fail(self):
        draft = self._base_draft()
        draft["title"] = "阿部監督、試合後の浅野を評価"

        result = validate_comment_lane_draft(draft)

        self.assertIn("TITLE_MISSING_NUCLEUS", result.soft_fail_tags)

    def test_lede_too_vague_is_soft_fail(self):
        draft = self._base_draft()
        draft["lede"] = "このコメントは注目を集めた。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("LEDE_TOO_VAGUE", result.soft_fail_tags)

    def test_too_many_headings_is_soft_fail(self):
        draft = self._base_draft()
        draft["context"] = "## 背景\n試合後の文脈を整理する。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("TOO_MANY_HEADINGS", result.soft_fail_tags)

    def test_pronoun_ambiguous_is_soft_fail(self):
        draft = self._base_draft()
        draft["context"] = "彼は次戦でも同じ姿勢を求めた。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("PRONOUN_AMBIGUOUS", result.soft_fail_tags)

    def test_body_order_broken_is_soft_fail(self):
        draft = self._base_draft()
        draft["body_order"] = ("lede", "fact_header", "quote_block", "context", "related")

        result = validate_comment_lane_draft(draft)

        self.assertIn("BODY_ORDER_BROKEN", result.soft_fail_tags)

    def test_normalization_table_covers_all_new_comment_tags(self):
        expected = {
            "GAME_RESULT_CONFLICT": "fact_missing",
            "NO_GAME_BUT_RESULT": "fact_missing",
            "SPEAKER_MISSING": "low_assertability",
            "QUOTE_UNGROUNDED": "attribution_missing",
            "TITLE_BODY_ENTITY_MISMATCH": "title_body_mismatch",
            "SOURCE_TRUST_TOO_LOW": "low_assertability",
            "TITLE_GENERIC": "title_body_mismatch",
            "TITLE_MISSING_SCENE": "title_body_mismatch",
            "TITLE_MISSING_NUCLEUS": "title_body_mismatch",
            "LEDE_TOO_VAGUE": "abstract_lead",
            "TOO_MANY_HEADINGS": "subtype_boundary",
            "PRONOUN_AMBIGUOUS": "low_assertability",
            "BODY_ORDER_BROKEN": "subtype_boundary",
        }
        self.assertEqual(FAIL_TAG_NORMALIZATION, expected)
        self.assertEqual(
            normalize_fail_tags(("TITLE_GENERIC", "TITLE_MISSING_SCENE", "LEDE_TOO_VAGUE")),
            ("title_body_mismatch", "abstract_lead"),
        )


if __name__ == "__main__":
    unittest.main()
