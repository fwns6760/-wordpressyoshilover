import unittest
from unittest.mock import Mock

from src import person_tag_router


ACTIVE_ROSTER = [
    {
        "name": "浦田俊輔",
        "aliases": ["浦田俊輔", "浦田 俊輔", "浦田"],
        "role": "player",
    },
    {
        "name": "岡本和真",
        "aliases": ["岡本和真", "岡本 和真", "岡本"],
        "role": "player",
    },
    {
        "name": "阿部慎之助",
        "aliases": ["阿部慎之助", "阿部監督"],
        "role": "manager",
    },
    {
        "name": "杉内俊哉",
        "aliases": ["杉内俊哉", "杉内コーチ"],
        "role": "coach",
    },
    {
        "name": "村田善則",
        "aliases": ["村田善則", "村田コーチ"],
        "role": "coach",
    },
]


OB_ROSTER = [
    {
        "name": "高橋由伸",
        "aliases": ["高橋由伸", "高橋由"],
    },
    {
        "name": "村田修一",
        "aliases": ["村田修一", "村田"],
    },
]


class PersonTagRouterTests(unittest.TestCase):
    def test_multiple_players_receive_multiple_person_tags(self):
        routing = person_tag_router.route_tag_names(
            title="浦田俊輔と岡本和真がスタメン入り",
            summary="巨人の一軍戦で2人が出場",
            category="試合速報",
            article_subtype="lineup",
            active_roster=ACTIVE_ROSTER,
            ob_roster=OB_ROSTER,
        )

        self.assertEqual(routing.person_tags, ("浦田俊輔", "岡本和真"))
        self.assertIn("速報", routing.context_tags)
        self.assertIn("一軍", routing.context_tags)

    def test_staff_and_manager_are_person_tags(self):
        routing = person_tag_router.route_tag_names(
            title="阿部監督と杉内コーチが投手陣について語る",
            category="首脳陣",
            active_roster=ACTIVE_ROSTER,
            ob_roster=OB_ROSTER,
        )

        self.assertEqual(routing.person_tags, ("阿部慎之助", "杉内俊哉"))
        self.assertIn("監督コメント", routing.context_tags)

    def test_ob_comment_gets_ob_context(self):
        routing = person_tag_router.route_tag_names(
            title="高橋由伸氏が巨人打線を解説",
            category="OB・解説者",
            active_roster=ACTIVE_ROSTER,
            ob_roster=OB_ROSTER,
        )

        self.assertEqual(routing.person_tags, ("高橋由伸",))
        self.assertIn("OB解説", routing.context_tags)

    def test_ambiguous_short_alias_is_skipped_without_guessing(self):
        routing = person_tag_router.route_tag_names(
            title="村田が打撃を解説",
            category="OB・解説者",
            active_roster=ACTIVE_ROSTER,
            ob_roster=OB_ROSTER,
        )

        self.assertEqual(routing.person_tags, ())
        self.assertIn("ambiguous_alias:村田", routing.skip_reasons)

    def test_all_person_tag_names_includes_context_tags_by_default(self):
        tags = person_tag_router.all_person_tag_names(
            active_roster=ACTIVE_ROSTER,
            ob_roster=OB_ROSTER,
        )

        self.assertIn("浦田俊輔", tags)
        self.assertIn("高橋由伸", tags)
        self.assertIn("速報", tags)

    def test_resolve_existing_wp_tag_ids_never_creates_tags(self):
        wp = Mock()
        wp.resolve_tag_id.side_effect = lambda name: {"浦田俊輔": 101, "速報": 201}.get(name, 0)

        tag_ids, missing = person_tag_router.resolve_existing_wp_tag_ids(
            wp,
            ["浦田俊輔", "未知選手", "速報"],
        )

        self.assertEqual(tag_ids, [101, 201])
        self.assertEqual(missing, ["未知選手"])
        self.assertEqual(wp.resolve_tag_id.call_count, 3)


if __name__ == "__main__":
    unittest.main()
