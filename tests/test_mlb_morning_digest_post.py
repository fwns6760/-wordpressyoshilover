"""毎朝の「今日の大谷・元巨人組」MLB定点ポスト (2026-07-13 user GO)。

network 不要 (data 注入)。LLM 不要 (gemini_api_key 空 = deterministic 締め)。
"""

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.mlb_morning_digest_post import build_mlb_morning_digest_candidate

JST = ZoneInfo("Asia/Tokyo")


def _now8() -> datetime:
    return datetime(2026, 7, 13, 8, 0, tzinfo=JST)


def _data(last_game_date: str = "2026-07-12") -> dict:
    return {
        "season": 2026,
        "as_of": last_game_date,
        "players": [
            {
                "name": "大谷翔平", "group": "hitting", "team": "ドジャース",
                "season": {"games": 90, "avg": ".295", "hr": 33, "rbi": 70, "ops": "1.012", "hits": 101},
                "last_game": {"date": last_game_date, "opponent": "ジャイアンツ",
                              "ab": 4, "hits": 2, "hr": 1, "rbi": 3},
            },
            {
                "name": "岡本和真", "group": "hitting", "team": "ヤンキース",
                "season": {"games": 80, "avg": ".270", "hr": 18, "rbi": 55, "ops": ".840", "hits": 78},
                "last_game": {"date": last_game_date, "opponent": "レッドソックス",
                              "ab": 4, "hits": 1, "hr": 0, "rbi": 0},
            },
            {
                "name": "菅野智之", "group": "pitching", "team": "オリオールズ",
                "season": {"games": 18, "wins": 8, "losses": 4, "era": "3.42", "ip": "101.2", "so": 77},
                # 登板は 5 日前 (rotation) → 直近行は落ち、season 行のみ
                "last_game": {"date": "2026-07-08", "opponent": "レイズ",
                              "ip": "6.0", "runs": 2, "so": 5, "hits": 6},
            },
        ],
    }


class BuildMlbMorningDigestTests(unittest.TestCase):
    def test_builds_daily_candidate_with_fresh_games(self):
        c = build_mlb_morning_digest_candidate(now=_now8(), data=_data())
        self.assertIsNotNone(c)
        self.assertTrue(c.signature.startswith("mlbdigest|"))
        self.assertEqual(c.metric, "MLB_MORNING_DIGEST")
        self.assertIn("8時の日本人メジャーリーガー定点観測", c.post_text)
        self.assertIn("大谷翔平", c.post_text)
        self.assertIn("岡本和真", c.post_text)
        # 数字は statsapi literal がそのまま入る
        self.assertIn("打率.295", c.post_text)
        self.assertIn("4打数2安打", c.post_text)
        # LLM なし → deterministic 締めで成立
        self.assertIn("定点", c.post_text)

    def test_stale_pitcher_keeps_season_line_without_last_game(self):
        c = build_mlb_morning_digest_candidate(now=_now8(), data=_data())
        self.assertIn("菅野智之", c.post_text)          # season 行は残る
        self.assertIn("8勝4敗", c.post_text)
        self.assertNotIn("2026-07-08", c.post_text)     # 5日前の登板は載せない

    def test_skips_when_no_fresh_games(self):
        stale = _data(last_game_date="2026-07-01")
        c = build_mlb_morning_digest_candidate(now=_now8(), data=stale)
        self.assertIsNone(c)

    def test_skips_outside_morning_window(self):
        noon = datetime(2026, 7, 13, 12, 0, tzinfo=JST)
        c = build_mlb_morning_digest_candidate(now=noon, data=_data())
        self.assertIsNone(c)

    def test_dedup_by_date_signature(self):
        first = build_mlb_morning_digest_candidate(now=_now8(), data=_data())
        seen = {first.signature}
        again = build_mlb_morning_digest_candidate(
            now=_now8() + timedelta(hours=1), data=_data(), dedup_set=seen
        )
        self.assertIsNone(again)

    def test_extra_star_specs_cover_japanese_mlb_stars(self):
        # 2026-07-13 user「追加」: 日本人スター組も定点ポスト対象 (503 欠落の均等担保)。
        from src.mlb_morning_digest_post import _DIGEST_SPECS, _EXTRA_STAR_SPECS

        names = {s["name"]: s["group"] for s in _EXTRA_STAR_SPECS}
        self.assertEqual(
            set(names),
            {"山本由伸", "佐々木朗希", "今永昇太", "鈴木誠也", "吉田正尚", "村上宗隆"},
        )
        self.assertEqual(names["山本由伸"], "pitching")
        self.assertEqual(names["鈴木誠也"], "hitting")
        # 全 spec に statsapi 用 mlb_id が入っている
        for s in _DIGEST_SPECS + _EXTRA_STAR_SPECS:
            self.assertIsInstance(s["mlb_id"], int)

    def test_star_player_appears_in_post(self):
        data = _data()
        data["players"].append({
            "name": "山本由伸", "group": "pitching", "team": "ドジャース",
            "season": {"games": 19, "wins": 10, "losses": 3, "era": "2.55", "ip": "120.1", "so": 128},
            "last_game": {"date": "2026-07-12", "opponent": "ジャイアンツ",
                          "ip": "7.0", "runs": 1, "so": 9, "hits": 4},
        })
        c = build_mlb_morning_digest_candidate(now=_now8(), data=data)
        self.assertIsNotNone(c)
        self.assertIn("山本由伸", c.post_text)
        self.assertIn("10勝3敗", c.post_text)


if __name__ == "__main__":
    unittest.main()
