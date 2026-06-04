"""⑤ ホット&コールド(絶好調打者)記事 generator のテスト。"""
import unittest

from src.analysis import hotcold_article as hc


class HotColdTests(unittest.TestCase):
    def test_parse_ba(self) -> None:
        self.assertAlmostEqual(hc._parse_ba("recent_ba=0.450 n=5", "recent_ba"), 0.450)
        self.assertAlmostEqual(hc._parse_ba("baseline_ba=0.190 n=30", "baseline_ba"), 0.190)
        self.assertIsNone(hc._parse_ba("", "recent_ba"))

    def test_build_article_title_and_body(self) -> None:
        art = hc.build_article({"player": "丸佳浩", "recent_ba": 0.450, "baseline_ba": 0.190, "z": 1.6})
        # 打率は先頭0除去(.450)、絶好調 case A
        self.assertEqual(art["title"], "【巨人データ】丸佳浩 直近5試合 打率.450、絶好調")
        self.assertIn(".450", art["body_md"])
        self.assertIn(".190", art["body_md"])  # シーズン平均
        self.assertIn("/data/maru-yoshihiro/", art["body_md"])

    def test_find_hot_filters_cold(self) -> None:
        # detector を mock: 1 人 HOT / 1 人 COLD → HOT のみ残る
        orig_players = hc._mg.all_giants_players_in_db
        orig_detect = hc._mg.detect_batter_recent_window_anomaly
        hc._mg.all_giants_players_in_db = lambda conn: (["A選手", "B選手"], [])

        def _fake_detect(conn, *, player_canonical, **kw):
            if player_canonical == "A選手":
                return {"signal_type": "batter_recent_hot", "magnitude": 1.8,
                        "current_value": "recent_ba=0.420 n=5", "baseline_value": "baseline_ba=0.250 n=30"}
            return {"signal_type": "batter_recent_cold", "magnitude": -1.9,
                    "current_value": "recent_ba=0.100 n=5", "baseline_value": "baseline_ba=0.280 n=30"}

        hc._mg.detect_batter_recent_window_anomaly = _fake_detect
        try:
            hot = hc.find_hot_batters(conn=None)
            names = [h["player"] for h in hot]
            self.assertEqual(names, ["A選手"])  # COLD(B選手)は除外
            self.assertAlmostEqual(hot[0]["recent_ba"], 0.420)
        finally:
            hc._mg.all_giants_players_in_db = orig_players
            hc._mg.detect_batter_recent_window_anomaly = orig_detect

    def test_enabled_gate_default_off(self) -> None:
        import os
        old = os.environ.pop("DATA_INSIGHT_HOTCOLD", None)
        try:
            self.assertFalse(hc.enabled())
            os.environ["DATA_INSIGHT_HOTCOLD"] = "1"
            self.assertTrue(hc.enabled())
        finally:
            os.environ.pop("DATA_INSIGHT_HOTCOLD", None)
            if old is not None:
                os.environ["DATA_INSIGHT_HOTCOLD"] = old


if __name__ == "__main__":
    unittest.main()
