"""名言メール統合 dispatcher (2026-07-02 scheduler 効率化) のテスト。"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from src.tools import run_meigen_mail_dispatch as disp

JST = timezone(timedelta(hours=9))


class PickLaneTests(unittest.TestCase):
    def _dt(self, day: int, hour: int) -> datetime:
        # 2026-07-06 = 月曜
        return datetime(2026, 7, day, hour, 0, tzinfo=JST)

    def test_hara_at_19(self):
        # 2026-07-07 ゴールデン帯再配置: 原は 8時 → 19時
        self.assertEqual(disp.pick_lane(self._dt(6, 19)), "hara")

    def test_kobayashi_at_12_20(self):
        for h in (12, 20):
            self.assertEqual(disp.pick_lane(self._dt(6, h)), "kobayashi")

    def test_sakamoto_at_18(self):
        self.assertEqual(disp.pick_lane(self._dt(6, 18)), "sakamoto")

    def test_yoshikawa_mon_wed_fri_at_17_else_kobayashi(self):
        # 月(6)水(8)金(10) の17時は吉川、火(7)木(9)土(11)日(12) は小林
        for day in (6, 8, 10):
            self.assertEqual(disp.pick_lane(self._dt(day, 17)), "yoshikawa")
        for day in (7, 9, 11, 12):
            self.assertEqual(disp.pick_lane(self._dt(day, 17)), "kobayashi")

    def test_off_hours_none(self):
        for h in (0, 7, 8, 9, 13, 15, 21, 23):
            self.assertIsNone(disp.pick_lane(self._dt(6, h)))


class LaneEnvTests(unittest.TestCase):
    def test_kobayashi_remaps_koba_env(self):
        with mock.patch.dict(os.environ, {
            "KOBA_SMTP_USERNAME": "koba@example.com",
            "KOBA_GMAIL_APP_PASSWORD": "koba-pass",
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge@example.com",
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "bridge-pass",
        }, clear=False):
            disp.apply_lane_env("kobayashi")
            self.assertEqual(os.environ["MAIL_BRIDGE_SMTP_USERNAME"], "koba@example.com")
            self.assertEqual(os.environ["MAIL_BRIDGE_GMAIL_APP_PASSWORD"], "koba-pass")

    def test_hara_keeps_bridge_env_and_enables_share_button(self):
        with mock.patch.dict(os.environ, {
            "KOBA_SMTP_USERNAME": "koba@example.com",
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge@example.com",
        }, clear=False):
            os.environ.pop("ENABLE_SHARE_X_BUTTON", None)
            disp.apply_lane_env("hara")
            self.assertEqual(os.environ["MAIL_BRIDGE_SMTP_USERNAME"], "bridge@example.com")
            self.assertEqual(os.environ.get("ENABLE_SHARE_X_BUTTON"), "1")

    def test_sakamoto_unsets_share_button(self):
        with mock.patch.dict(os.environ, {"ENABLE_SHARE_X_BUTTON": "1"}, clear=False):
            disp.apply_lane_env("sakamoto")
            self.assertIsNone(os.environ.get("ENABLE_SHARE_X_BUTTON"))


class MainDispatchTests(unittest.TestCase):
    def test_explicit_lane_overrides_clock(self):
        with mock.patch.object(disp, "run_lane", return_value=0) as rl:
            rc = disp.main(["--lane=hara"])
        self.assertEqual(rc, 0)
        rl.assert_called_once_with("hara", ["--n=1"])

    def test_extra_args_pass_through(self):
        with mock.patch.object(disp, "run_lane", return_value=0) as rl:
            disp.main(["--lane=kobayashi", "--dry-run", "--n=2"])
        rl.assert_called_once_with("kobayashi", ["--dry-run", "--n=2"])

    def test_no_lane_hour_is_noop(self):
        fake_now = datetime(2026, 7, 7, 15, 0, tzinfo=JST)  # 火 15時 → 吉川対象外
        with mock.patch.object(disp, "datetime", wraps=datetime) as dt:
            dt.now.return_value = fake_now
            with mock.patch.object(disp, "run_lane") as rl:
                rc = disp.main([])
        self.assertEqual(rc, 0)
        rl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
