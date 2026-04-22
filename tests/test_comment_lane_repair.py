import unittest

from src.comment_lane_repair import AGENT_SCOPE_BY_HARD_TAG, MAX_SOFT_REPAIR_ROUNDS, SOFT_SCOPE_BY_TAG, plan_comment_repair


class CommentLaneRepairTests(unittest.TestCase):
    def test_title_soft_tags_only_touch_title_scope(self):
        for fail_tag in ("TITLE_GENERIC", "TITLE_MISSING_SCENE", "TITLE_MISSING_NUCLEUS"):
            with self.subTest(fail_tag=fail_tag):
                plan = plan_comment_repair([fail_tag], round_number=0)
                self.assertEqual(plan.status, "repair")
                self.assertEqual(plan.repair_scope, "title")
                self.assertEqual(plan.playbook_plan.changed_scope, "title_only")

    def test_other_soft_tags_follow_scope_map(self):
        cases = {
            "LEDE_TOO_VAGUE": ("lede", "intro_only"),
            "TOO_MANY_HEADINGS": ("body_structure", "block_patch"),
            "PRONOUN_AMBIGUOUS": ("sentence", "intro_only"),
            "BODY_ORDER_BROKEN": ("slot_order", "block_patch"),
        }
        for fail_tag, (expected_scope, expected_changed_scope) in cases.items():
            with self.subTest(fail_tag=fail_tag):
                plan = plan_comment_repair([fail_tag], round_number=0)
                self.assertEqual(plan.status, "repair")
                self.assertEqual(plan.repair_scope, expected_scope)
                self.assertEqual(plan.playbook_plan.changed_scope, expected_changed_scope)

    def test_soft_repairs_delegate_after_two_rounds(self):
        plan = plan_comment_repair(["LEDE_TOO_VAGUE"], round_number=MAX_SOFT_REPAIR_ROUNDS)

        self.assertEqual(plan.status, "delegate")
        self.assertEqual(plan.lane, "agent")
        self.assertEqual(plan.rounds_remaining, 0)

    def test_hard_fail_stops_fixed_lane_and_delegates_to_agent(self):
        plan = plan_comment_repair(["TITLE_BODY_ENTITY_MISMATCH"], round_number=0)

        self.assertEqual(plan.status, "delegate")
        self.assertEqual(plan.lane, "agent")
        self.assertEqual(plan.repair_scope, AGENT_SCOPE_BY_HARD_TAG["TITLE_BODY_ENTITY_MISMATCH"])
        self.assertIsNone(plan.playbook_plan)

    def test_clean_fail_list_accepts_without_repair(self):
        plan = plan_comment_repair([], round_number=0)

        self.assertEqual(plan.status, "accept")
        self.assertEqual(plan.lane, "fixed")
        self.assertIsNone(plan.selected_fail_tag)

    def test_scope_table_matches_contract(self):
        self.assertEqual(
            SOFT_SCOPE_BY_TAG,
            {
                "TITLE_GENERIC": "title",
                "TITLE_MISSING_SCENE": "title",
                "TITLE_MISSING_NUCLEUS": "title",
                "LEDE_TOO_VAGUE": "lede",
                "TOO_MANY_HEADINGS": "body_structure",
                "PRONOUN_AMBIGUOUS": "sentence",
                "BODY_ORDER_BROKEN": "slot_order",
            },
        )


if __name__ == "__main__":
    unittest.main()
