import unittest
from unittest.mock import Mock

from src.tools import run_title_style_audit as audit


def _make_post(post_id, title, subtype):
    return {
        "id": post_id,
        "status": "draft",
        "title": {"raw": title},
        "content": {"raw": "<p>本文</p>"},
        "meta": {"article_subtype": subtype},
    }


class TitleStyleAuditTests(unittest.TestCase):
    def test_audit_aggregates_by_reason_code(self):
        posts = [
            _make_post(101, "4月25日 巨人阪神戦はどう挑む?", "pregame"),
            _make_post(102, "巨人・阿部監督のコメントから見えるもの整理版", "manager"),
            _make_post(103, "巨人・岡本和真、衝撃の決勝弾！！！", "postgame"),
            _make_post(104, "二軍結果", "farm"),
            _make_post(105, "【LIVE】4月25日 巨人、スタメン発表！！！", "lineup"),
        ]
        wp = Mock()
        wp.list_posts.side_effect = [
            posts,
            [],
        ]

        summary = audit.run_audit(wp, sample_failures=10)

        self.assertEqual(summary["total_scanned"], 5)
        self.assertEqual(summary["pass_count"], 0)
        self.assertEqual(summary["fail_count"], 5)
        self.assertEqual(summary["skipped_count"], 0)
        self.assertEqual(
            summary["fail_by_reason"],
            {
                "TITLE_STYLE_SPECULATIVE": 1,
                "TITLE_STYLE_GENERIC": 1,
                "TITLE_STYLE_CLICKBAIT": 1,
                "TITLE_STYLE_OUT_OF_LENGTH": 1,
                "TITLE_STYLE_FORBIDDEN_PREFIX": 1,
            },
        )
        self.assertEqual(len(summary["sample_failures"]), 5)

    def test_audit_aggregates_by_subtype(self):
        posts = [
            _make_post(201, "4月25日(金)の予告先発が発表される！！！", "pregame"),
            _make_post(202, "巨人・岡本和真、衝撃の決勝弾！！！", "postgame"),
            _make_post(203, "4月25日(金) セ・リーグ公式戦「巨人vs阪神」 巨人、スタメン発表！！！", "lineup"),
            _make_post(204, "巨人・阿部監督のコメントから見えるもの整理版", "manager"),
            _make_post(205, "巨人二軍 浅野翔吾、2安打マルチヒット！！！", "farm"),
        ]
        wp = Mock()
        wp.list_posts.side_effect = [
            posts,
            [],
        ]

        summary = audit.run_audit(wp)

        self.assertEqual(summary["pass_count"], 3)
        self.assertEqual(summary["fail_count"], 2)
        self.assertEqual(summary["by_subtype"]["pregame"], {"pass": 1, "fail": 0, "skipped": 0, "total": 1})
        self.assertEqual(summary["by_subtype"]["postgame"], {"pass": 0, "fail": 1, "skipped": 0, "total": 1})
        self.assertEqual(summary["by_subtype"]["lineup"], {"pass": 1, "fail": 0, "skipped": 0, "total": 1})
        self.assertEqual(summary["by_subtype"]["manager"], {"pass": 0, "fail": 1, "skipped": 0, "total": 1})
        self.assertEqual(summary["by_subtype"]["farm"], {"pass": 1, "fail": 0, "skipped": 0, "total": 1})

    def test_audit_handles_pagination_overflow_gracefully(self):
        paged_posts = {
            1: [_make_post(301, "4月25日(金)の予告先発が発表される！！！", "pregame")],
            2: [_make_post(302, "巨人・岡本和真、衝撃の決勝弾！！！", "postgame")],
            3: [_make_post(303, "巨人二軍 浅野翔吾、2安打マルチヒット！！！", "farm")],
            4: [_make_post(304, "巨人・阿部監督のコメントから見えるもの整理版", "manager")],
        }

        def _list_posts(**kwargs):
            page = int(kwargs["page"])
            if page == 5:
                raise RuntimeError("400 rest_post_invalid_page_number")
            return list(paged_posts.get(page, []))

        wp = Mock()
        wp.list_posts.side_effect = _list_posts

        summary = audit.run_audit(wp, max_pages=5)

        self.assertEqual(summary["pages_fetched"], 5)
        self.assertEqual(summary["total_scanned"], 4)
        self.assertEqual(summary["pass_count"], 2)
        self.assertEqual(summary["fail_count"], 2)
        self.assertEqual(summary["fail_by_reason"]["TITLE_STYLE_CLICKBAIT"], 1)
        self.assertEqual(summary["fail_by_reason"]["TITLE_STYLE_GENERIC"], 1)


if __name__ == "__main__":
    unittest.main()
