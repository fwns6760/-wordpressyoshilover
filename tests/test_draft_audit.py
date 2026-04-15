import unittest

from src import draft_audit


class TestDraftAudit(unittest.TestCase):
    def test_extract_source_links_from_reference_section(self):
        html = """
        <p>📰 参照元:
          <a href="https://example.com/1">スポーツ報知 巨人</a> /
          <a href="https://example.com/2">日刊スポーツ 巨人</a>
        </p>
        """

        links = draft_audit.extract_source_links(html)

        self.assertEqual(
            links,
            [
                {"name": "スポーツ報知 巨人", "url": "https://example.com/1"},
                {"name": "日刊スポーツ 巨人", "url": "https://example.com/2"},
            ],
        )

    def test_extract_source_links_falls_back_to_badge(self):
        html = '<span>📰 巨人公式X / スポーツ報知巨人班X</span>'

        links = draft_audit.extract_source_links(html)

        self.assertEqual(
            links,
            [
                {"name": "巨人公式X", "url": ""},
                {"name": "スポーツ報知巨人班X", "url": ""},
            ],
        )

    def test_audit_post_infers_source_bucket_and_subtype(self):
        category_map = {663: "試合速報"}
        source_catalog = {
            draft_audit._normalize_key("巨人公式X"): {"name": "巨人公式X", "type": "social_news"},
        }
        post = {
            "id": 62041,
            "status": "draft",
            "modified": "2026-04-15T07:30:00",
            "title": {"raw": "巨人が阪神に3-2で勝利　決勝打は吉川尚輝"},
            "content": {
                "raw": """
                <h3>📊 今日の試合結果</h3>
                <p>📰 参照元: <a href="https://example.com/post">巨人公式X</a></p>
                """
            },
            "categories": [673, 663],
        }

        row = draft_audit.audit_post(post, category_map, source_catalog, "https://yoshilover.com")

        self.assertEqual(row["primary_category"], "試合速報")
        self.assertEqual(row["article_subtype"], "postgame")
        self.assertEqual(row["source_bucket"], "social_news")
        self.assertEqual(row["source_names"], ["巨人公式X"])
        self.assertEqual(
            row["edit_url"],
            "https://yoshilover.com/wp-admin/post.php?post=62041&action=edit",
        )


if __name__ == "__main__":
    unittest.main()
