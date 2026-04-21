import unittest

from src.repair_playbook import decide_outcome, ledger_fields, plan_repair


class RepairPlaybookTests(unittest.TestCase):
    def test_fixed_lane_rejects_full_rewrite_request(self):
        with self.assertRaisesRegex(ValueError, "full_rewrite"):
            plan_repair(["fact_missing", "full_rewrite"], "fixed")

    def test_fixed_lane_allows_only_minimum_diff_scopes(self):
        cases = {
            "title_body_mismatch": "title_only",
            "abstract_lead": "intro_only",
            "attribution_missing": "attribution_only",
            "fact_missing": "block_patch",
        }

        for fail_tag, expected_scope in cases.items():
            with self.subTest(fail_tag=fail_tag):
                plan = plan_repair([fail_tag], "fixed")
                self.assertEqual(plan.changed_scope, expected_scope)

    def test_agent_lane_allows_full_rewrite_request(self):
        plan = plan_repair(["fact_missing", "full_rewrite"], "agent")

        self.assertEqual(plan.changed_scope, "full_rewrite")
        self.assertEqual(plan.repair_actions, ("fact_block_add",))

    def test_plan_repair_orders_fail_tags_by_playbook_priority(self):
        plan = plan_repair(
            ["abstract_lead", "subtype_boundary", "fact_missing", "title_body_mismatch"],
            "fixed",
        )

        self.assertEqual(
            plan.ordered_fail_tags,
            ("subtype_boundary", "fact_missing", "title_body_mismatch", "abstract_lead"),
        )

    def test_fail_tag_map_covers_each_ledger_fail_tag(self):
        cases = {
            "subtype_boundary": (("template_restore", "block_reorder"), "block_patch", "no"),
            "fact_missing": (("fact_block_add",), "block_patch", "yes"),
            "title_body_mismatch": (("title_fix",), "title_only", "no"),
            "thin_body": (("fact_block_add",), "block_patch", "yes"),
            "attribution_missing": (("attribution_add",), "attribution_only", "no"),
            "abstract_lead": (("lead_replace",), "intro_only", "no"),
            "duplicate": ((), None, "no"),
            "low_assertability": ((), None, "no"),
            "pickup_miss": ((), None, "no"),
            "close_marker": ((), None, "no"),
        }

        for fail_tag, (expected_actions, expected_scope, expected_recheck) in cases.items():
            with self.subTest(fail_tag=fail_tag):
                plan = plan_repair([fail_tag], "fixed")
                self.assertEqual(plan.repair_actions, expected_actions)
                self.assertEqual(plan.changed_scope, expected_scope)
                self.assertEqual(plan.source_recheck_used, expected_recheck)

    def test_title_fix_without_ambiguity_skips_source_recheck(self):
        plan = plan_repair(["title_body_mismatch"], "fixed")

        self.assertEqual(plan.repair_actions, ("title_fix",))
        self.assertEqual(plan.source_recheck_used, "no")
        self.assertEqual(plan.search_used, "no")

    def test_ambiguous_title_body_mismatch_requires_recheck_and_not_title_only(self):
        plan = plan_repair(["title_body_mismatch", "title_body_core_ambiguous"], "agent")

        self.assertEqual(plan.repair_actions, ("title_fix", "lead_replace"))
        self.assertEqual(plan.source_recheck_used, "yes")
        self.assertEqual(plan.search_used, "no")
        self.assertEqual(plan.changed_scope, "block_patch")

    def test_fact_block_add_always_rechecks_and_source_weak_enables_search(self):
        plan = plan_repair(["fact_missing", "source_weak"], "fixed")

        self.assertEqual(plan.repair_actions, ("fact_block_add",))
        self.assertEqual(plan.source_recheck_used, "yes")
        self.assertEqual(plan.search_used, "yes")

    def test_template_reorder_attribution_and_lead_replace_skip_source_recheck(self):
        cases = {
            "subtype_boundary": ("template_restore", "block_reorder"),
            "attribution_missing": ("attribution_add",),
            "abstract_lead": ("lead_replace",),
            "ai_tone": ("lead_replace",),
        }

        for fail_tag, expected_actions in cases.items():
            with self.subTest(fail_tag=fail_tag):
                plan = plan_repair([fail_tag], "fixed")
                self.assertEqual(plan.repair_actions, expected_actions)
                self.assertEqual(plan.source_recheck_used, "no")
                self.assertEqual(plan.search_used, "no")

    def test_decide_outcome_accepts_clean_draft_without_repair(self):
        plan = plan_repair([], "fixed")

        self.assertEqual(decide_outcome(plan, validators_pass_after=True, repair_attempts=0), "accept_draft")

    def test_decide_outcome_returns_repair_closed_after_single_successful_repair(self):
        plan = plan_repair(["attribution_missing"], "fixed")

        self.assertEqual(decide_outcome(plan, validators_pass_after=True, repair_attempts=1), "repair_closed")

    def test_decide_outcome_returns_escalated_when_validators_still_fail(self):
        plan = plan_repair(["fact_missing"], "fixed")

        self.assertEqual(decide_outcome(plan, validators_pass_after=False, repair_attempts=1), "escalated")

    def test_decide_outcome_returns_escalated_when_repair_cap_exceeded(self):
        plan = plan_repair(["fact_missing"], "fixed")

        self.assertEqual(decide_outcome(plan, validators_pass_after=True, repair_attempts=2), "escalated")

    def test_decide_outcome_escalates_unrepairable_single_tags(self):
        for fail_tag in ("duplicate", "low_assertability", "close_marker", "pickup_miss"):
            with self.subTest(fail_tag=fail_tag):
                plan = plan_repair([fail_tag], "fixed")
                self.assertEqual(decide_outcome(plan, validators_pass_after=True, repair_attempts=0), "escalated")

    def test_ledger_fields_returns_schema_with_allowed_enums(self):
        plan = plan_repair(["attribution_missing"], "fixed")
        outcome = decide_outcome(plan, validators_pass_after=True, repair_attempts=1)
        fields = ledger_fields(plan, "fixed", outcome)

        self.assertEqual(
            set(fields.keys()),
            {
                "repair_applied",
                "repair_trigger",
                "repair_actions",
                "source_recheck_used",
                "search_used",
                "changed_scope",
                "outcome",
            },
        )
        self.assertIn(fields["repair_applied"], {"yes", "no"})
        self.assertIn(fields["outcome"], {"accept_draft", "repair_closed", "escalated"})

    def test_ledger_fields_marks_no_repair_when_plan_has_no_actions(self):
        plan = plan_repair(["duplicate"], "fixed")
        fields = ledger_fields(plan, "fixed", "escalated")

        self.assertEqual(fields["repair_applied"], "no")
        self.assertIsNone(fields["repair_trigger"])
        self.assertEqual(fields["repair_actions"], [])


if __name__ == "__main__":
    unittest.main()
