import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from src.repair_playbook import aggregate_fail_tags, format_promotion_summary
from src.tools.run_repair_playbook_aggregator import main as aggregator_main


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ledger"
NOW = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)


def _aggregate(fixture_name: str):
    return aggregate_fail_tags(FIXTURE_DIR / fixture_name, now=NOW)


def _promotions(candidates):
    return [candidate for candidate in candidates if candidate.kind == "promotion"]


class RepairPlaybookAggregatorTests(unittest.TestCase):
    def test_036_24h_hit_emits_user_trigger_and_promotion(self):
        candidates = _aggregate("036_hit.jsonl")

        triggers = [candidate for candidate in candidates if candidate.kind == "trigger"]
        promotions = _promotions(candidates)

        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].window, "24h")
        self.assertEqual(triggers[0].subtype, "postgame")
        self.assertEqual(triggers[0].prompt_version, "v3")
        self.assertEqual(triggers[0].fail_tag, "thin_body")
        self.assertEqual(triggers[0].count, 3)

        self.assertEqual([candidate.promotion_target for candidate in promotions], ["036"])
        self.assertEqual(promotions[0].window, "24h")
        self.assertEqual(promotions[0].sample_candidate_keys, ("k036-1", "k036-2", "k036-3"))

        formatted = format_promotion_summary(candidates)
        self.assertIn("2026-04-22 24h trigger subtype=postgame fail_tag=thin_body prompt_version=v3 count=3", formatted)
        self.assertIn("2026-04-22 24h 036候補 subtype=postgame fail_tag=thin_body prompt_version=v3 count=3", formatted)

    def test_037_hit_emits_source_family_cross_subtype_candidate(self):
        promotions = _promotions(_aggregate("037_hit.jsonl"))

        self.assertEqual(len(promotions), 1)
        self.assertEqual(promotions[0].promotion_target, "037")
        self.assertEqual(promotions[0].window, "7d")
        self.assertEqual(promotions[0].source_family, "official_x")
        self.assertEqual(promotions[0].fail_tag, "attribution_missing")
        self.assertEqual(promotions[0].subtypes, ("lineup_notice", "postgame"))

    def test_035_hit_emits_close_marker_candidate(self):
        promotions = _promotions(_aggregate("035_hit.jsonl"))

        self.assertEqual(len(promotions), 1)
        self.assertEqual(promotions[0].promotion_target, "035")
        self.assertEqual(promotions[0].window, "7d")
        self.assertEqual(promotions[0].fail_tag, "close_marker")
        self.assertEqual(promotions[0].count, 2)
        self.assertAlmostEqual(promotions[0].ratio, 66.6666666667)
        self.assertIn("ratio=66.7%", format_promotion_summary(promotions))

    def test_priority_suppresses_037_when_same_fail_tag_has_036(self):
        promotions = _promotions(_aggregate("036_hit.jsonl"))

        self.assertEqual([candidate.promotion_target for candidate in promotions], ["036"])
        self.assertNotIn("037", {candidate.promotion_target for candidate in promotions})

    def test_priority_suppresses_035_when_same_fail_tag_has_037(self):
        promotions = _promotions(_aggregate("priority_037_over_035.jsonl"))

        self.assertEqual([candidate.promotion_target for candidate in promotions], ["037"])
        self.assertEqual(promotions[0].fail_tag, "close_marker")

    def test_miss_keeps_promotion_empty_but_outputs_7d_fail_tag_summary(self):
        candidates = _aggregate("miss.jsonl")

        self.assertEqual(_promotions(candidates), [])
        summaries = [candidate for candidate in candidates if candidate.kind == "summary"]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].window, "7d")
        self.assertEqual(summaries[0].fail_tag, "thin_body")
        self.assertEqual(summaries[0].count, 1)
        self.assertIn("2026-04-22 7d  summary fail_tag=thin_body count=1", format_promotion_summary(candidates))

    def test_empty_fixture_formats_no_trigger(self):
        candidates = _aggregate("empty.jsonl")

        self.assertEqual(candidates, [])
        self.assertEqual(format_promotion_summary(candidates), "no trigger")

    def test_invalid_json_and_missing_fields_are_skipped_without_crashing(self):
        candidates = _aggregate("invalid_mixed.jsonl")

        self.assertEqual(_promotions(candidates), [])
        summaries = [candidate for candidate in candidates if candidate.kind == "summary"]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].fail_tag, "attribution_missing")
        self.assertEqual(summaries[0].count, 1)
        self.assertEqual(summaries[0].sample_candidate_keys, ("kvalid-after-bad",))

    def test_json_records_fixture_is_read(self):
        candidates = _aggregate("json_records.json")

        self.assertEqual(_promotions(candidates), [])
        summaries = [candidate for candidate in candidates if candidate.kind == "summary"]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].fail_tag, "tags_category_minor")
        self.assertEqual(summaries[0].source_families, ("rss_media",))

    def test_cli_filters_to_requested_window(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = aggregator_main(
                [
                    "--aggregate",
                    "--ledger-dir",
                    str(FIXTURE_DIR / "036_hit.jsonl"),
                    "--window",
                    "24h",
                    "--now",
                    "2026-04-22T12:00:00+00:00",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("24h trigger", output)
        self.assertIn("24h 036候補", output)
        self.assertNotIn("7d  summary", output)


if __name__ == "__main__":
    unittest.main()
