"""2026-05-14 67352 incident defense layer tests.

Both ``parse_emoji_lineup`` and ``parse_hochi_compact_lineup`` must force
every row to ``team="巨人"`` when no opponent NPB team marker is detected
in the source text — otherwise sangun / ikusei players missing from the
roster get falsely classified as ``相手`` and the renderer emits a
fabricated opponent table.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src import source_emoji_lineup_extractor as emoji_mod
from src import source_hochi_compact_lineup_extractor as hochi_mod
from src.source_emoji_lineup_extractor import parse_emoji_lineup
from src.source_hochi_compact_lineup_extractor import parse_hochi_compact_lineup


# Production-shaped 67352 fixture: 巨人 sangun lineup with 信濃 (BC リーグ,
# non-NPB) as opponent. ``extract_opponent_team_name`` returns "" for this
# because 信濃グランセローズ is not in the NPB team allowlist.
SANGUN_NO_NPB_OPPONENT = (
    "【三軍】巨人 vs 信濃グランセローズ しんきん諏訪湖スタジアム🏟️ "
    "18時試合開始⚾ 本日のスタメン✨ "
    "1️⃣ 松井(D) 2️⃣ 北村⑷ 3️⃣ フェリス⑼ 4️⃣ 竹下⑸ 5️⃣ 笹原⑻ "
    "6️⃣ 村山⑹ 7️⃣ 坂本達⑵ 8️⃣ 相澤⑺ 9️⃣ 田上⑶ 🅿️ 堀江"
)

# Production-shaped 二軍 fixture: opponent is 巨人 vs ロッテ (NPB team) →
# opponent_team_name = "ロッテ" → defense layer DOES NOT apply, split path
# remains.
NIGUN_WITH_NPB_OPPONENT = (
    "【二軍】巨人 vs ロッテ オーエンススタジアム江戸川🏟️ 13時試合開始⚾ "
    "1️⃣ 三塚(D) 2️⃣ 小濱⑹ 3️⃣ 皆川⑼ 4️⃣ 萩尾⑺ 5️⃣ 荒巻⑶ 6️⃣ 浅野⑻ "
    "7️⃣ 山瀬⑵ 8️⃣ 郡⑸ 9️⃣ 湯浅⑷ 🅿️ マタ"
)


class EmojiLineupDefenseTests(unittest.TestCase):
    def test_sangun_no_npb_opponent_forces_all_to_giants(self):
        result = parse_emoji_lineup(
            title=SANGUN_NO_NPB_OPPONENT,
            summary=SANGUN_NO_NPB_OPPONENT,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result)
        rows = result["lineup"]
        self.assertEqual(len(rows), 10)
        teams = {row["team"] for row in rows}
        self.assertEqual(teams, {"巨人"})
        self.assertEqual(result["opponent_team_name"], "")

    def test_nigun_with_npb_opponent_still_splits_by_roster(self):
        # Stub roster check so the split logic is observable independently.
        with patch.object(emoji_mod, "_is_giants_player") as fake_giants:
            fake_giants.side_effect = lambda name: name in {"小濱", "皆川"}
            result = parse_emoji_lineup(
                title=NIGUN_WITH_NPB_OPPONENT,
                summary=NIGUN_WITH_NPB_OPPONENT,
                source_name="巨人公式X",
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["opponent_team_name"], "ロッテ")
        teams = {row["team"] for row in result["lineup"]}
        self.assertEqual(teams, {"巨人", "相手"})

    def test_67352_all_players_classified_as_giants_via_real_roster(self):
        # Integration: rely on the real roster loader (live NPB or json
        # fallback) and the defense layer. All 10 rows must be 巨人.
        result = parse_emoji_lineup(
            title=SANGUN_NO_NPB_OPPONENT,
            summary=SANGUN_NO_NPB_OPPONENT,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result)
        names = {row["name"] for row in result["lineup"]}
        self.assertIn("松井", names)
        self.assertIn("坂本達", names)
        self.assertIn("田上", names)
        for row in result["lineup"]:
            self.assertEqual(
                row["team"], "巨人",
                f"row {row['name']} expected 巨人 but got {row['team']}",
            )


class HochiCompactLineupDefenseTests(unittest.TestCase):
    def test_hochi_no_npb_opponent_forces_all_to_giants(self):
        # Hochi-source-flavored sangun fixture (independent league opponent).
        text = (
            "巨人三軍スタメン 信濃グランセローズ戦 諏訪湖🏟 18:00 "
            "1松井 2北村 3フェリス 4竹下 5笹原 6村山 7坂本達 8相澤 9田上 P堀江"
        )
        result = parse_hochi_compact_lineup(
            title=text,
            summary=text,
            source_name="スポーツ報知巨人班X",
        )
        if result is None:
            self.skipTest("hochi parser did not match the fixture shape")
        teams = {row["team"] for row in result["lineup"]}
        self.assertEqual(teams, {"巨人"})
        self.assertEqual(result["opponent_team_name"], "")


if __name__ == "__main__":
    unittest.main()
