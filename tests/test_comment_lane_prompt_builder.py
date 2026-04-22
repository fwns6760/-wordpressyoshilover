import unittest

from src.comment_lane_prompt_builder import (
    COMMENT_INPUT_FIELDS,
    COMMENT_OUTPUT_SLOTS,
    build_comment_lane_prompt,
    build_output_slot_template,
)


class CommentLanePromptBuilderTests(unittest.TestCase):
    def _payload(self):
        return {
            "speaker_name": "阿部監督",
            "speaker_role": "監督",
            "scene_type": "試合後",
            "game_id": None,
            "opponent": None,
            "scoreline": None,
            "team_result": None,
            "quote_core": "積極性が良かった",
            "quote_source": "スポーツ報知",
            "quote_source_type": "major_web",
            "target_entity": "浅野",
            "emotion": "納得",
            "trust_tier": "fact",
        }

    def test_prompt_requires_all_thirteen_input_fields(self):
        payload = self._payload()
        payload.pop("emotion")

        with self.assertRaisesRegex(ValueError, "emotion"):
            build_comment_lane_prompt(payload)

    def test_prompt_contains_six_output_slots_in_fixed_order(self):
        prompt = build_comment_lane_prompt(self._payload())
        start = prompt.index("output_slots:")
        slot_block = prompt[start:]

        positions = [slot_block.index(f'"{slot}"') for slot in COMMENT_OUTPUT_SLOTS]
        self.assertEqual(positions, sorted(positions))

    def test_prompt_contains_input_schema_and_payload_json(self):
        prompt = build_comment_lane_prompt(self._payload())

        for field in COMMENT_INPUT_FIELDS:
            self.assertIn(f'"{field}"', prompt)
        self.assertIn('"speaker_name": "阿部監督"', prompt)
        self.assertIn('"quote_core": "積極性が良かった"', prompt)

    def test_prompt_explicitly_bans_hallucination_and_extra_headings(self):
        prompt = build_comment_lane_prompt(self._payload())

        self.assertIn("入力 JSON に無い選手名・媒体名・試合結果・感想・背景事情を追加しない。", prompt)
        self.assertIn("H2/H3 を付けない。", prompt)
        self.assertIn("JSON only", prompt)

    def test_prompt_includes_null_game_result_rule(self):
        prompt = build_comment_lane_prompt(self._payload())

        self.assertIn("game_id, opponent, scoreline, team_result のどれかが null の場合", prompt)
        self.assertIn("本文で試合結果・スコア・対戦相手を断定しない。", prompt)

    def test_output_slot_template_matches_contract(self):
        template = build_output_slot_template()
        for slot in COMMENT_OUTPUT_SLOTS:
            self.assertIn(f'"{slot}": ""', template)


if __name__ == "__main__":
    unittest.main()
