"""年俸ページの active フラグを現ロースターと突合する補正のテスト (2026-07-06)。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src import data_site_template_salary as sal


class ReconcileTests(unittest.TestCase):
    def _roster(self):
        return [
            {"name": "坂本 勇人", "role": "player", "active": True},
            {"name": "ウィットリー", "role": "shihaikako", "active": True},
        ]

    def test_retired_player_flipped_to_ob(self):
        data = {"players": [
            {"name": "長野久義", "active": True},
            {"name": "坂本勇人", "active": True},
            {"name": "松井秀喜", "active": False},
        ]}
        with patch("src.giants_roster_loader.load_active_roster", return_value=self._roster()):
            sal._reconcile_actives_with_roster(data)
        by = {p["name"]: p for p in data["players"]}
        self.assertFalse(by["長野久義"]["active"])   # roster不在 → OB枠
        self.assertTrue(by["坂本勇人"]["active"])
        self.assertFalse(by["松井秀喜"]["active"])  # 元からOBは不変

    def test_roster_failure_keeps_baked_flags(self):
        data = {"players": [{"name": "長野久義", "active": True}]}
        with patch("src.giants_roster_loader.load_active_roster", side_effect=RuntimeError):
            sal._reconcile_actives_with_roster(data)
        self.assertTrue(data["players"][0]["active"])  # fail-safe


if __name__ == "__main__":
    unittest.main()
