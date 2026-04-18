import unittest
from unittest.mock import patch

from src import acceptance_auto_fix
from src.acceptance_fact_check import Finding, PostReport


class AcceptanceAutoFixTests(unittest.TestCase):
    def _report(self, post_id: int, findings=None, *, result="red", title="巨人DeNA戦 大城卓三は何を見せたか") -> PostReport:
        return PostReport(
            post_id=post_id,
            title=title,
            status="draft",
            primary_category="試合速報",
            article_subtype="postgame",
            modified="2026-04-18T08:00:00",
            edit_url=f"https://yoshilover.com/wp-admin/post.php?post={post_id}&action=edit",
            result=result,
            findings=findings or [],
            source_urls=["https://example.com/source"],
        )

    def _finding(self, **overrides) -> Finding:
        data = {
            "severity": "red",
            "field": "opponent",
            "current": "DeNA",
            "expected": "ヤクルト",
            "evidence_url": "https://npb.jp/example",
            "message": "opponent が不一致",
            "cause": "title_rewrite_mismatch",
            "proposal": "WP title の `DeNA` を `ヤクルト` に置換する",
            "fix_type": "direct_edit",
            "auto_fix": {"type": "title_replace", "find": "DeNA", "replace": "ヤクルト"},
        }
        data.update(overrides)
        return Finding(**data)

    @patch.object(acceptance_auto_fix, "_fetch_editable_post")
    def test_analyze_reports_marks_single_match_title_replace_as_candidate(self, mock_fetch_post):
        mock_fetch_post.return_value = {
            "status": "draft",
            "modified": "2026-04-18T08:00:00",
            "title": {"raw": "巨人DeNA戦 大城卓三は何を見せたか"},
            "content": {"raw": "<p>本文</p>"},
        }
        summary = acceptance_auto_fix.analyze_reports(
            [self._report(62527, [self._finding()])],
            wp=object(),
            fetch_post_state=True,
        )

        self.assertEqual(len(summary.autofix_candidates), 1)
        candidate = summary.autofix_candidates[0]
        self.assertEqual(candidate.decision, "autofix_candidate")
        self.assertEqual(candidate.proposed_edits[0].target, "title")
        self.assertIn("-巨人DeNA戦", candidate.proposed_edits[0].diff)

    @patch.object(acceptance_auto_fix, "_fetch_editable_post")
    def test_analyze_reports_rejects_multiple_match_body_replace(self, mock_fetch_post):
        mock_fetch_post.return_value = {
            "status": "draft",
            "modified": "2026-04-18T08:00:00",
            "title": {"raw": "巨人ヤクルト戦"},
            "content": {"raw": "<p>神宮で試合。神宮で先発調整。</p>"},
        }
        finding = self._finding(
            field="venue",
            current="神宮",
            expected="PayPay",
            cause="game_fact_alignment_failure",
            auto_fix={"type": "body_replace", "find": "神宮", "replace": "PayPay"},
        )
        summary = acceptance_auto_fix.analyze_reports(
            [self._report(62518, [finding], title="巨人8-2 勝利の分岐点はどこだったか")],
            wp=object(),
            fetch_post_state=True,
        )

        self.assertEqual(len(summary.rejects), 1)
        self.assertIn("match_count=2", summary.rejects[0].notes[0])

    @patch.object(acceptance_auto_fix, "_fetch_editable_post")
    def test_analyze_reports_rejects_when_safe_and_unsafe_red_findings_mix(self, mock_fetch_post):
        mock_fetch_post.return_value = {
            "status": "draft",
            "modified": "2026-04-18T08:00:00",
            "title": {"raw": "巨人8-2 勝利の分岐点はどこだったか"},
            "content": {"raw": "<p>神宮で8-2の勝利。</p>"},
        }
        safe_finding = self._finding(
            field="venue",
            current="神宮",
            expected="PayPay",
            cause="game_fact_alignment_failure",
            auto_fix={"type": "body_replace", "find": "神宮", "replace": "PayPay"},
        )
        unsafe_finding = self._finding(
            field="score",
            current="8-2",
            expected="25-97",
            cause="game_fact_alignment_failure",
            proposal="WP title の `8-2` を `25-97` に置換する",
            auto_fix={"type": "title_replace", "find": "8-2", "replace": "25-97"},
        )
        summary = acceptance_auto_fix.analyze_reports(
            [self._report(62518, [safe_finding, unsafe_finding], title="巨人8-2 勝利の分岐点はどこだったか")],
            wp=object(),
            fetch_post_state=True,
        )

        self.assertEqual(len(summary.rejects), 1)
        self.assertIn("field_not_whitelisted:score", " ".join(summary.rejects[0].notes))

    def test_build_markdown_report_includes_sections_and_diff(self):
        decision = acceptance_auto_fix.AutoFixDecision(
            post_id=62527,
            title="巨人DeNA戦 大城卓三は何を見せたか",
            status="draft",
            primary_category="試合速報",
            article_subtype="postgame",
            modified="2026-04-18T08:00:00",
            edit_url="https://yoshilover.com/wp-admin/post.php?post=62527&action=edit",
            decision="autofix_candidate",
            causes=["title_rewrite_mismatch"],
            findings=[{
                "field": "opponent",
                "cause": "title_rewrite_mismatch",
                "message": "opponent が不一致",
                "proposal": "WP title の `DeNA` を `ヤクルト` に置換する",
            }],
            proposed_edits=[
                acceptance_auto_fix.ProposedEdit(
                    target="title",
                    find="DeNA",
                    replace="ヤクルト",
                    occurrences=1,
                    before="巨人DeNA戦 大城卓三は何を見せたか",
                    after="巨人ヤクルト戦 大城卓三は何を見せたか",
                    diff="--- before\n+++ after\n-巨人DeNA戦 大城卓三は何を見せたか\n+巨人ヤクルト戦 大城卓三は何を見せたか",
                )
            ],
        )
        summary = acceptance_auto_fix.AutoFixSummary(
            checked_posts=1,
            autofix_candidates=[decision],
            rejects=[],
            manual_reviews=[],
            no_action=[],
        )

        markdown = acceptance_auto_fix.build_markdown_report(
            summary,
            date_label="2026-04-18",
            source_scope="post_ids=62527",
            generated_at="2026-04-18T09:00:00+09:00",
        )

        self.assertIn("# Acceptance Auto Fix Dry Run - 2026-04-18", markdown)
        self.assertIn("## 自動修正候補", markdown)
        self.assertIn("```diff", markdown)
        self.assertIn("巨人ヤクルト戦", markdown)


if __name__ == "__main__":
    unittest.main()
