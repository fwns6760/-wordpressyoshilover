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


if __name__ == "__main__":
    unittest.main()
