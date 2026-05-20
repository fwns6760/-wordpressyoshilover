import logging
import unittest
from unittest.mock import patch

from src import rss_fetcher


ACTIVE_ROSTER = [
    {"name": "浦田俊輔", "aliases": ["浦田俊輔", "浦田"], "role": "player"},
    {"name": "岡本和真", "aliases": ["岡本和真", "岡本"], "role": "player"},
]

OB_ROSTER = [
    {"name": "高橋由伸", "aliases": ["高橋由伸", "高橋由"]},
]


class FakeWP:
    def __init__(self):
        self.created = {}

    def resolve_tag_id(self, name):
        return {
            "浦田俊輔": 101,
            "岡本和真": 102,
            "速報": 201,
            "一軍": 202,
        }.get(name, 0)

    def create_post(self, title, content, **kwargs):
        self.created = {"title": title, "content": content, **kwargs}
        return 999


class RssFetcherPersonTagsTests(unittest.TestCase):
    def test_create_draft_routes_existing_person_and_context_tags(self):
        wp = FakeWP()
        logger = logging.getLogger("test_rss_fetcher_person_tags")

        with (
            patch("src.person_tag_router.giants_roster_loader.load_active_roster", return_value=ACTIVE_ROSTER),
            patch("src.person_tag_router.giants_ob_roster.load_giants_ob_roster", return_value=OB_ROSTER),
            patch.object(rss_fetcher, "_apply_rss_pipeline_enrichment", None),
        ):
            post_id = rss_fetcher._create_draft_with_same_fire_guard(
                wp,
                logger,
                set(),
                {},
                "浦田俊輔と岡本和真がスタメン入り",
                "<p>body</p>",
                [663],
                "https://example.com/source",
                enrichment_summary="一軍戦で2人が先発",
                enrichment_category="試合速報",
                enrichment_template_key="lineup",
            )

        self.assertEqual(post_id, 999)
        self.assertEqual(wp.created["tags"], [101, 102, 201, 202])
        self.assertEqual(wp.created["categories"], [663])

    def test_create_draft_uses_breaking_news_tag_fallback_when_no_person_tags(self):
        """387 part 2 fix: tag_ids が空の場合 [850] 速報 fallback で post に attach。"""
        wp = FakeWP()
        logger = logging.getLogger("test_rss_fetcher_person_tags_fallback")

        # person_tag_router を mock し、 person_tags / context_tags 両方空に
        # → tag_ids 空 → 387 fallback [850] 速報 が attach されるはず
        from src.person_tag_router import PersonTagRouting
        empty_routing = PersonTagRouting(
            person_tags=(),
            context_tags=(),
            skip_reasons=("test_fallback",),
        )
        with (
            patch("src.person_tag_router.route_tag_names", return_value=empty_routing),
            patch("src.person_tag_router.resolve_existing_wp_tag_ids", return_value=([], [])),
            patch.object(rss_fetcher, "_apply_rss_pipeline_enrichment", None),
        ):
            post_id = rss_fetcher._create_draft_with_same_fire_guard(
                wp,
                logger,
                set(),
                {},
                "テレビ番組情報: 今日の野球中継",
                "<p>body</p>",
                [665],
                "https://example.com/no-player",
                enrichment_summary="特定選手名なし",
                enrichment_category="general",
                enrichment_template_key="general",
            )

        self.assertEqual(post_id, 999)
        # 387 fix: tag_ids 空 → fallback [850] 速報 が確実に attach
        self.assertEqual(wp.created["tags"], [850])
        self.assertEqual(wp.created["categories"], [665])


if __name__ == "__main__":
    unittest.main()
