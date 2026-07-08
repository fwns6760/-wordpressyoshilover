"""巨人戦ライブ実況 v0 (2026-07-08) — NPB スコア parse とイベント検出。"""
import unittest

from src.live_game_watch import LiveGameState, detect_events, parse_live_page


def _page(status: str, away_cells: str, home_cells: str, homers: str = "") -> str:
    return f"""
    <html><body>
    <div>【{status}】◇開始 18:00</div>
    <table>
    <tr><th>&nbsp;</th><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th><th>6</th><th>7</th><th>8</th><th>9</th><th>計</th><th>H</th><th>E</th></tr>
    <tr><td>阪神タイガース阪神</td>{away_cells}</tr>
    <tr><td>読売ジャイアンツ巨人</td>{home_cells}</tr>
    </table>
    <div>{homers}</div>
    </body></html>
    """


def _cells(*runs, total, h="5", e="0"):
    tds = "".join(f"<td>{r}</td>" for r in runs)
    tds += "<td></td>" * (9 - len(runs))
    return tds + f"<td>{total}</td><td>{h}</td><td>{e}</td>"


class ParseTests(unittest.TestCase):
    def test_parse_mid_game(self):
        html = _page(
            "試合中 3回裏",
            _cells("1", "0", total="1"),
            _cells("0", "2", total="2"),
            "森下 21号（1回ソロ 西舘）",
        )
        s = parse_live_page(html, game_url="u", date_key="20260708")
        self.assertIsNotNone(s)
        self.assertEqual(s.status, "試合中")
        self.assertEqual(s.inning_label, "3回裏")
        self.assertTrue(s.giants_home)
        self.assertEqual(s.giants_score, 2)
        self.assertEqual(s.opp_score, 1)
        self.assertIn("森下 21号（1回ソロ 西舘）", s.homer_lines)

    def test_parse_game_end(self):
        html = _page("試合終了", _cells("1", total="1"), _cells("0", "2", "1", total="3"))
        s = parse_live_page(html, game_url="u", date_key="20260708")
        self.assertEqual(s.status, "試合終了")
        self.assertEqual((s.giants_score, s.opp_score), (3, 1))


def _state(g, o, status="試合中", inning="5回表", homers=()):
    return LiveGameState(
        date_key="20260708", game_url="u", status=status, inning_label=inning,
        giants_home=True, giants_score=g, opp_score=o, opp_name="阪神",
        homer_lines=list(homers),
    )


class DetectEventTests(unittest.TestCase):
    def test_first_run_emits_nothing(self):
        self.assertEqual(detect_events(None, _state(3, 1)), [])

    def test_giants_score_up(self):
        ev = detect_events(_state(0, 0).to_dict(), _state(1, 0))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["kind"], "giants_score")
        self.assertIn("先制", ev[0]["fact"])
        self.assertIn("巨人1-0阪神", ev[0]["fact"])

    def test_lead_change(self):
        ev = detect_events(_state(1, 2).to_dict(), _state(3, 2))
        self.assertEqual(ev[0]["kind"], "lead_change")
        self.assertIn("逆転", ev[0]["fact"])

    def test_opp_score_with_new_homer(self):
        prev = _state(2, 0, homers=["岡本和真 20号（3回ソロ）"])
        cur = _state(2, 1, homers=["岡本和真 20号（3回ソロ）", "森下 21号（5回ソロ 西舘）"])
        ev = detect_events(prev.to_dict(), cur)
        self.assertEqual(ev[0]["kind"], "opp_score")
        self.assertIn("森下 21号", ev[0]["fact"])
        self.assertNotIn("岡本和真 20号", ev[0]["fact"])

    def test_game_end_once(self):
        prev = _state(3, 1)
        cur = _state(3, 1, status="試合終了", inning="")
        ev = detect_events(prev.to_dict(), cur)
        self.assertEqual(ev[0]["kind"], "game_end")
        self.assertIn("勝利", ev[0]["fact"])
        # 終了後にもう一度見てもイベントを繰り返さない
        again = detect_events(cur.to_dict(), cur)
        self.assertEqual(again, [])

    def test_no_change_no_event(self):
        self.assertEqual(detect_events(_state(2, 2).to_dict(), _state(2, 2)), [])


if __name__ == "__main__":
    unittest.main()
