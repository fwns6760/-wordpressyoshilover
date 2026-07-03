import unittest

from src.yt_shorts_standings import (
    STANDINGS_OPENING,
    build_standings_script,
    standings_topic_from_rows,
)
from src.yt_shorts_script import verify_number_guard


def _rows(rank=2, gb="3.5", is_giants_rank=2) -> list[dict]:
    teams = ["阪神", "巨人", "DeNA", "広島", "ヤクルト", "中日"]
    out = []
    for i, team in enumerate(teams, start=1):
        giants = team == "巨人"
        out.append({
            "rank": i,
            "team": team,
            "g": "70",
            "w": "40" if giants else "38",
            "l": "30" if giants else "32",
            "t": "2" if giants else "1",
            "pct": ".571" if giants else ".543",
            "gb": "-" if i == 1 else (gb if giants else "5.0"),
            "is_giants": giants,
        })
    # 巨人を希望順位に置く
    if is_giants_rank != 2:
        for r in out:
            if r["is_giants"]:
                r["rank"] = is_giants_rank
    return out


class YtShortsStandingsTests(unittest.TestCase):
    def test_returns_none_without_giants_row(self):
        rows = [r for r in _rows() if not r["is_giants"]]
        self.assertIsNone(standings_topic_from_rows(rows))

    def test_topic_extracts_giants_row(self):
        topic = standings_topic_from_rows(_rows(), as_of="2026-06-28")
        self.assertIsNotNone(topic)
        self.assertEqual(topic.rank, 2)
        self.assertEqual(topic.wins, "40")
        self.assertFalse(topic.is_leading)

    def test_chasing_script_reads_game_behind_and_passes_guard(self):
        topic = standings_topic_from_rows(_rows(gb="3.5"), as_of="2026-06-28")
        script = build_standings_script(topic)
        self.assertTrue(script.narration.startswith(STANDINGS_OPENING))
        # ゲーム差 3.5 が小数点読みされている
        self.assertIn("三点五", script.narration)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)
        ok_cap, leaked_cap = verify_number_guard(
            "\n".join(c.text for c in script.captions), script.allowed_numbers
        )
        self.assertTrue(ok_cap, leaked_cap)

    def test_npb_double_dash_gb_is_computed_not_rendered(self):
        # 2026-07-02 実事故: 首位と勝率同率の2位で NPB 公式 gb が "--" のまま
        # 「首位とのゲーム差 --」と描画された。gb は勝敗差から自前計算する。
        rows = _rows()
        for r in rows:
            if r["is_giants"]:
                r["rank"] = 2
                r["w"], r["l"] = "38", "32"   # 首位(38勝32敗)と同成績 → ゲーム差 0
                r["gb"] = "--"
        topic = standings_topic_from_rows(rows, as_of="2026-07-02")
        self.assertEqual(topic.gb, "0")
        self.assertFalse(topic.is_leading)
        self.assertTrue(topic.is_co_leading)
        script = build_standings_script(topic)
        self.assertNotIn("--", script.narration)
        self.assertIn("首位に並んでいます", script.narration)
        self.assertIn("首位タイ", "\n".join(c.text for c in script.captions))

    def test_topic_rows_carry_normalized_table_for_render(self):
        rows = _rows(gb="3.5")
        topic = standings_topic_from_rows(rows, as_of="2026-06-28")
        self.assertEqual(len(topic.rows), 6)
        leader = topic.rows[0]
        self.assertEqual(leader[0], 1)
        giants = next(r for r in topic.rows if r[6])
        self.assertEqual(giants[5], "3.5")

    def test_leading_giants_uses_first_place_copy(self):
        # 巨人を1位 gb "-" に
        rows = _rows(is_giants_rank=1)
        for r in rows:
            if r["is_giants"]:
                r["gb"] = "-"
        topic = standings_topic_from_rows(rows, as_of="2026-06-28")
        self.assertTrue(topic.is_leading)
        script = build_standings_script(topic)
        self.assertIn("首位", script.narration)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)


if __name__ == "__main__":
    unittest.main()
