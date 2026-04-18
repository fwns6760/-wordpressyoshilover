from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from src import rss_fetcher

try:
    import pytest
except ModuleNotFoundError:  # unittest discover on CI does not install pytest
    pytest = None


if pytest is not None:
    pytestmark = pytest.mark.enable_related_posts_lookup


class DummyWP:
    def resolve_category_id(self, _name: str) -> int:
        return 663


def _post(post_id: int, title: str, *, days_ago: int, link: str, excerpt: str = "", categories=None) -> dict:
    published = datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return {
        "id": post_id,
        "title": {"rendered": title},
        "excerpt": {"rendered": excerpt},
        "date_gmt": published.isoformat().replace("+00:00", "Z"),
        "link": link,
        "categories": categories or [663],
    }


class RelatedPostsTests(TestCase):
    def test_related_posts_prioritize_player_match_then_same_subtype_then_same_category(self):
        player_posts = [
            _post(101, "戸郷翔征の直球が戻ってきた", days_ago=2, link="https://yoshilover.com/p101"),
        ]
        category_posts = [
            _post(
                201,
                "【巨人】阪神に3-2で勝利 岡本が決勝打",
                days_ago=1,
                link="https://yoshilover.com/p201",
                excerpt="巨人が阪神に3-2で勝利した。",
            ),
            _post(
                202,
                "【巨人】今日のスタメン発表 1番丸 4番岡本",
                days_ago=3,
                link="https://yoshilover.com/p202",
                excerpt="巨人が阪神戦のスタメンを発表した。",
            ),
        ]

        def search_posts(**kwargs):
            if kwargs["search"] == "戸郷翔征":
                return player_posts
            if kwargs["category_id"] == 663:
                return category_posts
            return []

        related = rss_fetcher._find_related_posts_for_article(
            title="【巨人】戸郷翔征が7回1失点 阪神に3-2で勝利",
            summary="巨人が阪神に3-2で勝利した。戸郷翔征が7回1失点と好投した。",
            category="試合速報",
            article_subtype="postgame",
            current_url="https://example.com/source",
            has_game=True,
            wp_factory=DummyWP,
            search_posts=search_posts,
            now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual([post["id"] for post in related], [101, 201])

    def test_related_posts_cut_off_older_than_30_days(self):
        player_posts = [
            _post(101, "戸郷翔征の復帰プラン", days_ago=31, link="https://yoshilover.com/p101"),
        ]
        category_posts = [
            _post(
                201,
                "【巨人】阪神に3-2で勝利 岡本が決勝打",
                days_ago=4,
                link="https://yoshilover.com/p201",
                excerpt="巨人が阪神に3-2で勝利した。",
            ),
        ]

        def search_posts(**kwargs):
            if kwargs["search"] == "戸郷翔征":
                return player_posts
            if kwargs["category_id"] == 663:
                return category_posts
            return []

        related = rss_fetcher._find_related_posts_for_article(
            title="【巨人】戸郷翔征が7回1失点 阪神に3-2で勝利",
            summary="巨人が阪神に3-2で勝利した。戸郷翔征が7回1失点と好投した。",
            category="試合速報",
            article_subtype="postgame",
            current_url="https://example.com/source",
            has_game=True,
            wp_factory=DummyWP,
            search_posts=search_posts,
            now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual([post["id"] for post in related], [201])

    def test_related_posts_exclude_current_article_and_duplicates(self):
        player_posts = [
            _post(
                101,
                "【巨人】阪神に3-2で勝利 戸郷翔征が7回1失点",
                days_ago=2,
                link="https://yoshilover.com/current",
            ),
            _post(
                102,
                "戸郷翔征の登板内容を振り返る",
                days_ago=1,
                link="https://yoshilover.com/p102",
            ),
        ]
        category_posts = [
            _post(
                102,
                "戸郷翔征の登板内容を振り返る",
                days_ago=1,
                link="https://yoshilover.com/p102",
                excerpt="戸郷翔征の投球内容を振り返る。",
            ),
            _post(
                201,
                "【巨人】今日のスタメン発表 1番丸 4番岡本",
                days_ago=3,
                link="https://yoshilover.com/p201",
                excerpt="巨人が阪神戦のスタメンを発表した。",
            ),
        ]

        def search_posts(**kwargs):
            if kwargs["search"] == "戸郷翔征":
                return player_posts
            if kwargs["category_id"] == 663:
                return category_posts
            return []

        related = rss_fetcher._find_related_posts_for_article(
            title="【巨人】阪神に3-2で勝利 戸郷翔征が7回1失点",
            summary="巨人が阪神に3-2で勝利した。戸郷翔征が7回1失点と好投した。",
            category="試合速報",
            article_subtype="postgame",
            current_url="https://yoshilover.com/current",
            has_game=True,
            wp_factory=DummyWP,
            search_posts=search_posts,
            now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual([post["id"] for post in related], [102, 201])

    def test_related_posts_section_is_omitted_when_empty(self):
        self.assertEqual(rss_fetcher._build_related_posts_section([]), "")

    def test_build_news_block_inserts_related_posts_before_final_cta(self):
        with patch.object(
            rss_fetcher,
            "_find_related_posts_for_article",
            return_value=[
                {"id": 1, "title": "戸郷翔征の登板を振り返る", "link": "https://yoshilover.com/p1"},
                {"id": 2, "title": "巨人投手陣の流れを整理", "link": "https://yoshilover.com/p2"},
            ],
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(
                    rss_fetcher,
                    "generate_article_with_gemini",
                    return_value=(
                        "【ニュースの整理】\n"
                        "巨人が阪神に3-2で勝利した。\n"
                        "【試合のポイント】\n"
                        "戸郷翔征が7回1失点と好投した。\n"
                        "【次の注目】\n"
                        "次戦へどうつなげるかが焦点です。"
                    ),
                ):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】戸郷翔征が7回1失点 阪神に3-2で勝利",
                        summary="巨人が阪神に3-2で勝利した。戸郷翔征が7回1失点と好投した。",
                        url="https://example.com/source",
                        source_name="スポーツ報知",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertIn("【関連記事】", blocks)
        self.assertIn('class="yoshilover-related-posts"', blocks)
        self.assertLess(blocks.index("【関連記事】"), blocks.index("今日のMVPは？"))

    def test_build_news_block_suppresses_empty_related_posts_section(self):
        with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】今日のスタメン発表 1番丸、4番岡本",
                        summary="巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。",
                        url="https://example.com/source",
                        source_name="スポーツ報知",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertNotIn("【関連記事】", blocks)
        self.assertNotIn("yoshilover-related-posts", blocks)
