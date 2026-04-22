import unittest

from src.comment_topic_selector import (
    ANALYSIS_LANE,
    COMMENT_LANE,
    REACTION_LANE,
    ROUTE_ANALYSIS,
    ROUTE_POSTGAME_ABSORB,
    ROUTE_REACTION,
    ROUTE_STANDALONE,
    select_comment_topic,
)


class CommentTopicSelectorTests(unittest.TestCase):
    def _base_payload(self):
        return {
            "speaker_name": "阿部監督",
            "scene_type": "試合後",
            "game_context": "試合後",
            "target_entity": "浅野",
            "quote_core": "積極性が良かった",
            "quote_source": "スポーツ報知",
            "source_ref": "スポーツ報知",
            "downstream_link": "次戦でも同じ姿勢を求めた",
            "independence_score": 0.9,
        }

    def test_selects_six_slots_and_allows_standalone_when_gate_passes(self):
        result = select_comment_topic(self._base_payload())

        self.assertEqual(result.lane, COMMENT_LANE)
        self.assertEqual(result.route, ROUTE_STANDALONE)
        self.assertTrue(result.gate_passed)
        self.assertTrue(result.standalone_allowed)
        self.assertFalse(result.absorb_into_postgame)
        self.assertEqual(
            result.slots,
            {
                "speaker": "阿部監督",
                "source_ref": "スポーツ報知",
                "game_context": "試合後",
                "subject_entity": "浅野",
                "quote_core": "積極性が良かった",
                "downstream_link": "次戦でも同じ姿勢を求めた",
            },
        )

    def test_multiple_speakers_do_not_enter_fixed_comment_lane(self):
        payload = self._base_payload()
        payload["speakers"] = ["阿部監督", "岡本"]

        result = select_comment_topic(payload)

        self.assertEqual(result.lane, COMMENT_LANE)
        self.assertEqual(result.route, ROUTE_POSTGAME_ABSORB)
        self.assertFalse(result.gate_passed)
        self.assertFalse(result.standalone_allowed)
        self.assertIn("multiple_speakers", result.gate_failures)
        self.assertTrue(result.absorb_into_postgame)

    def test_missing_slot_absorbs_into_postgame_even_if_gate_facts_exist(self):
        payload = self._base_payload()
        payload["downstream_link"] = ""

        result = select_comment_topic(payload)

        self.assertEqual(result.route, ROUTE_POSTGAME_ABSORB)
        self.assertIn("downstream_link", result.missing_slots)
        self.assertIn("slot_missing", result.gate_failures)
        self.assertTrue(result.absorb_into_postgame)

    def test_how_to_view_angle_routes_to_analysis_lane(self):
        payload = self._base_payload()
        payload["title"] = "巨人の試合後コメントをどう見る"

        result = select_comment_topic(payload)

        self.assertEqual(result.lane, ANALYSIS_LANE)
        self.assertEqual(result.route, ROUTE_ANALYSIS)
        self.assertIn("analysis_boundary", result.gate_failures)
        self.assertFalse(result.standalone_allowed)

    def test_reaction_source_routes_to_reaction_lane(self):
        payload = self._base_payload()
        payload["trust_tier"] = "reaction"
        payload["quote_source_type"] = "fan_reaction"
        payload["source_ref"] = "一般ファン投稿"

        result = select_comment_topic(payload)

        self.assertEqual(result.lane, REACTION_LANE)
        self.assertEqual(result.route, ROUTE_REACTION)
        self.assertIn("reaction_boundary", result.gate_failures)
        self.assertFalse(result.standalone_allowed)


if __name__ == "__main__":
    unittest.main()
