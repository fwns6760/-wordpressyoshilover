import unittest
from unittest.mock import Mock

from src import draft_inventory_from_logs


class TestDraftInventoryFromLogs(unittest.TestCase):
    def test_extract_candidate_post_ids_dedupes_text_payload(self):
        entries = [
            {"textPayload": "[WP] 記事draft post_id=62518 title='x'"},
            {"textPayload": "[WP] 既存記事を再利用 post_id=62518 title='x'"},
            {"textPayload": "[WP] 下書き作成 post_id=62527 title='y'"},
        ]

        self.assertEqual(draft_inventory_from_logs.extract_candidate_post_ids(entries), [62518, 62527])

    def test_collect_candidate_post_ids_uses_logging_reader(self):
        captured = {}

        def fake_reader(**kwargs):
            captured.update(kwargs)
            return [{"textPayload": "[WP] 記事draft post_id=62518"}]

        ids = draft_inventory_from_logs.collect_candidate_post_ids(
            project_id="baseballsite",
            service_name="svc",
            days=3,
            limit=123,
            reader=fake_reader,
        )

        self.assertEqual(ids, [62518])
        self.assertIn('resource.labels.service_name="svc"', captured["query"])
        self.assertEqual(captured["project_id"], "baseballsite")
        self.assertEqual(captured["limit"], 123)

    def test_audit_current_drafts_filters_non_draft(self):
        wp = Mock()
        wp.base_url = "https://yoshilover.com"
        wp.get_categories.return_value = [{"id": 663, "name": "試合速報", "slug": "game"}]
        wp.get_post.side_effect = [
            {
                "id": 62518,
                "status": "draft",
                "modified": "2026-04-18T09:00:00",
                "title": {"raw": "巨人8-2 勝利の分岐点はどこだったか"},
                "content": {"raw": '<p>📰 参照元: <a href="https://example.com">巨人公式X</a></p>'},
                "categories": [663],
            },
            {
                "id": 62047,
                "status": "publish",
                "modified": "2026-04-14T23:00:57",
                "title": {"raw": "publish post"},
                "content": {"raw": ""},
                "categories": [663],
            },
        ]

        audited = draft_inventory_from_logs.audit_current_drafts([62518, 62047], wp=wp)

        self.assertEqual(len(audited), 1)
        self.assertEqual(audited[0]["id"], 62518)
        self.assertEqual(audited[0]["status"], "draft")

    def test_summarize_inventory_counts_subtypes(self):
        summary = draft_inventory_from_logs.summarize_inventory(
            [
                {"id": 1, "article_subtype": "postgame", "primary_category": "試合速報"},
                {"id": 2, "article_subtype": "lineup", "primary_category": "試合速報"},
                {"id": 3, "article_subtype": "postgame", "primary_category": "試合速報"},
            ]
        )

        self.assertEqual(summary["total_drafts"], 3)
        self.assertEqual(summary["subtype_counts"]["postgame"], 2)
        self.assertEqual(summary["subtype_counts"]["lineup"], 1)
        self.assertEqual(summary["category_subtype_counts"]["試合速報/postgame"], 2)


if __name__ == "__main__":
    unittest.main()
