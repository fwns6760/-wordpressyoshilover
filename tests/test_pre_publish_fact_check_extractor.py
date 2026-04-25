import unittest

from src.pre_publish_fact_check import extractor


class ExtractorTests(unittest.TestCase):
    def test_source_urls_are_deduped_with_order_preserved(self):
        body_html = (
            '<p><a href="https://example.com/a">A</a></p>'
            '<p>https://example.com/b</p>'
            '<p>https://example.com/a</p>'
        )
        urls = extractor.extract_post_record(
            {
                "id": 1,
                "title": {"raw": "巨人が勝利"},
                "content": {"raw": body_html},
                "date": "2026-04-25T10:00:00",
                "modified": "2026-04-25T11:00:00",
                "categories": [1],
                "tags": [2],
            }
        )["source_urls"]
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/b"])

    def test_source_block_present_absent_and_multiline(self):
        present = extractor.extract_post_record(
            {
                "id": 1,
                "title": {"raw": "巨人が勝利"},
                "content": {"raw": "<p>本文</p><p>参照元: https://example.com/source</p>"},
            }
        )
        absent = extractor.extract_post_record(
            {
                "id": 1,
                "title": {"raw": "巨人が勝利"},
                "content": {"raw": "<p>本文だけ</p>"},
            }
        )
        multiline = extractor.extract_post_record(
            {
                "id": 1,
                "title": {"raw": "巨人が勝利"},
                "content": {
                    "raw": (
                        "<p>本文</p>"
                        "<div>参照元 :</div>"
                        "<p>https://example.com/1</p>"
                        "<p>https://example.com/2</p>"
                    )
                },
            }
        )
        self.assertEqual(present["source_block"], "参照元: https://example.com/source")
        self.assertIsNone(absent["source_block"])
        self.assertEqual(
            multiline["source_block"],
            "参照元 :\nhttps://example.com/1\nhttps://example.com/2",
        )

    def test_body_text_cleanup_strips_tags_decodes_entities_and_collapses_blank_lines(self):
        record = extractor.extract_post_record(
            {
                "id": 1,
                "title": {"raw": "巨人が勝利"},
                "content": {
                    "raw": "<p>一行目&nbsp;&amp; 二行目</p><div></div><p>三行目<br>四行目</p>",
                },
            }
        )
        self.assertEqual(record["body_text"], "一行目 & 二行目\n三行目\n四行目")

    def test_inferred_subtype_branches(self):
        cases = {
            "巨人スタメン発表": "lineup",
            "巨人の予告先発が決定": "probable_starter",
            "二軍で好投": "farm",
            "公示で入れ替え": "notice",
            "【コメント】阿部監督が試合を総括": "comment",
            "主力が故障で離脱": "injury",
            "巨人が3-2で勝利": "postgame",
            "明日の見どころ": "pregame",
            "テレビ出演情報": "program",
            "球団トピック": "other",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(extractor.infer_subtype(title), expected)

    def test_json_shape_conformance(self):
        record = extractor.extract_post_record(
            {
                "id": 99,
                "title": {"raw": "試合前情報"},
                "content": {"raw": "<p>本文</p>"},
                "date": "2026-04-25T09:00:00",
                "modified": "2026-04-25T10:00:00",
                "categories": [11, 12],
                "tags": [21],
            }
        )
        self.assertEqual(
            sorted(record.keys()),
            sorted(
                [
                    "post_id",
                    "title",
                    "body_html",
                    "body_text",
                    "source_urls",
                    "source_block",
                    "created_at",
                    "modified_at",
                    "categories",
                    "tags",
                    "inferred_subtype",
                ]
            ),
        )
        self.assertEqual(record["post_id"], 99)
        self.assertEqual(record["categories"], [11, 12])
        self.assertEqual(record["tags"], [21])


if __name__ == "__main__":
    unittest.main()
