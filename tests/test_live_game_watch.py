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


_PBP_HTML = (
    '<h5 name="c1" id="c1">1回表（阪神の攻撃）</h5><table>'
    '<tr><td colspan="5">（先発投手） <a href="/bis/players/1.html">西舘</a></td></tr>'
    '<tr><td>0アウト</td><td>&nbsp;</td><td><a href="/bis/players/2.html">森下</a></td>'
    '<td>0-0より</td><td>レフトソロホームラン（打点1）</td></tr>'
    '</table>'
    '<h5 name="c2" id="c2">1回裏（巨人の攻撃）</h5><table>'
    '<tr><td colspan="5">（先発投手） <a href="/bis/players/3.html">才木</a></td></tr>'
    '<tr><td>1アウト</td><td>1・2塁</td><td><a href="/bis/players/4.html">キャベッジ</a></td>'
    '<td>2-1より</td><td>ライト前ヒット</td></tr>'
    '<tr><td>2アウト</td><td>&nbsp;</td><td><a href="/bis/players/5.html">泉口</a></td>'
    '<td>1-2より</td><td>見逃し三振</td></tr>'
    '</table>'
)


class ParsePlaysTests(unittest.TestCase):
    def test_parse_plays_fields_and_pitcher(self):
        plays = gate_pbp().parse_plays(_PBP_HTML)
        self.assertEqual(len(plays), 3)
        hr = plays[0]
        self.assertEqual(hr["batter"], "森下")
        self.assertEqual(hr["pitcher"], "西舘")       # 表 → 巨人投手
        self.assertFalse(hr["giants_batting"])
        self.assertIn("ホームラン", hr["outcome"])
        hit = plays[1]
        self.assertEqual(hit["batter"], "キャベッジ")
        self.assertEqual(hit["pitcher"], "才木")       # 裏 → 相手投手
        self.assertTrue(hit["giants_batting"])
        self.assertEqual(hit["runners"], "1・2塁")


class DetectPlayEventsTests(unittest.TestCase):
    def setUp(self):
        self.plays = gate_pbp().parse_plays(_PBP_HTML)

    def test_first_flush_no_emit(self):
        # prev_count=None (便の初回) は baseline のみ = 0 件 (洪水防止)
        self.assertEqual(gate_pbp().detect_play_events(None, self.plays), [])

    def test_lower_trigger_hit_and_hr_bundle_names(self):
        evs = gate_pbp().detect_play_events(0, self.plays, score_ctx="巨人0-1阪神", max_count=3)
        facts = " / ".join(e["fact"] for e in evs)
        # 得点でない出塁(ヒット)でも出る = トリガー低
        self.assertIn("キャベッジ", facts)
        # 長打は投手名も束ねる = 複数選手
        self.assertTrue(any("森下" in e["fact"] and "西舘" in e["fact"] for e in evs))

    def test_no_new_plays_returns_empty(self):
        self.assertEqual(gate_pbp().detect_play_events(len(self.plays), self.plays), [])


def gate_pbp():
    from src import live_game_watch as lgw
    return lgw


class RecapFactTests(unittest.TestCase):
    def test_recap_bundles_giants_names_only(self):
        plays = gate_pbp().parse_plays(_PBP_HTML)
        fact = gate_pbp().build_recap_fact(plays, 4, 3, "阪神")
        self.assertIn("勝利", fact)
        self.assertIn("キャベッジ", fact)   # 巨人の安打者
        self.assertIn("西舘", fact)         # 巨人投手 (表で登板)
        self.assertNotIn("才木", fact)      # 才木=相手投手、巨人側に混ぜない
        self.assertNotIn("森下", fact)      # 森下=相手打者、巨人安打に混ぜない

    def test_recap_loss_label(self):
        plays = gate_pbp().parse_plays(_PBP_HTML)
        self.assertIn("敗戦", gate_pbp().build_recap_fact(plays, 1, 5, "阪神"))


class PitcherChangeTests(unittest.TestCase):
    def test_pitcher_change_uses_incoming_not_outgoing(self):
        html = (
            '<h5 name="c1" id="c1">1回表（阪神の攻撃）</h5><table>'
            '<tr><td colspan="5">（先発投手） <a href="/bis/players/1.html">西舘</a></td></tr>'
            '<tr><td>0アウト</td><td>&nbsp;</td><td><a href="/bis/players/2.html">中野</a></td>'
            '<td>0-0より</td><td>セカンドゴロ</td></tr>'
            '</table><table>'
            '<tr><td colspan="5">（投手交代） <a href="/bis/players/1.html">西舘</a> → '
            '<a href="/bis/players/3.html">田和</a></td></tr>'
            '<tr><td>1アウト</td><td>&nbsp;</td><td><a href="/bis/players/4.html">大山</a></td>'
            '<td>1-1より</td><td>見逃し三振</td></tr>'
            '</table>'
        )
        plays = gate_pbp().parse_plays(html)
        # 交代後の大山は 田和(登板側) に帰属。西舘(交代前) ではない
        oyama = [p for p in plays if p["batter"] == "大山"][0]
        self.assertEqual(oyama["pitcher"], "田和")
        self.assertNotEqual(oyama["pitcher"], "西舘")


class FullnameMapTests(unittest.TestCase):
    """姓→フルネーム解決 (2026-07-10 user 検索インプ)。roster は mock。"""

    _ROSTER = [
        {"name": "泉口 友汰"},
        {"name": "西舘 勇陽"},
        {"name": "キャベッジ"},          # 一語登録名 → 置換対象外
        {"name": "岡本 和真"},
        {"name": "岡本 大翔"},           # 同姓複数 → 置換対象外
    ]

    def _map(self):
        from unittest.mock import patch

        from src import live_game_watch as lgw

        with patch(
            "src.giants_roster_loader.load_active_roster",
            return_value=self._ROSTER,
        ):
            return lgw.giants_fullname_map()

    def test_unique_surname_resolves(self):
        m = self._map()
        self.assertEqual(m.get("泉口"), "泉口友汰")
        self.assertEqual(m.get("西舘"), "西舘勇陽")

    def test_ambiguous_and_single_word_not_mapped(self):
        m = self._map()
        self.assertNotIn("岡本", m)      # 同姓 2 人
        self.assertNotIn("キャベッジ", m)  # full == 姓

    def test_apply_only_to_giants_side(self):
        from src.live_game_watch import apply_fullname_map

        plays = [
            # 巨人の攻撃: batter=巨人 → 置換 / pitcher=相手 → 触らない
            {"giants_batting": True, "batter": "泉口", "pitcher": "才木"},
            # 相手の攻撃: pitcher=巨人 → 置換 / batter=相手 → 触らない
            {"giants_batting": False, "batter": "泉口", "pitcher": "西舘"},
        ]
        out = apply_fullname_map(plays, {"泉口": "泉口友汰", "西舘": "西舘勇陽"})
        self.assertEqual(out[0]["batter"], "泉口友汰")
        self.assertEqual(out[0]["pitcher"], "才木")
        self.assertEqual(out[1]["batter"], "泉口")  # 相手の同姓は誤置換しない
        self.assertEqual(out[1]["pitcher"], "西舘勇陽")

    def test_empty_map_returns_same(self):
        from src.live_game_watch import apply_fullname_map

        plays = [{"giants_batting": True, "batter": "泉口", "pitcher": ""}]
        self.assertIs(apply_fullname_map(plays, {}), plays)

    def test_roster_failure_returns_empty(self):
        from unittest.mock import patch

        from src import live_game_watch as lgw

        with patch(
            "src.giants_roster_loader.load_active_roster",
            side_effect=RuntimeError("net down"),
        ):
            self.assertEqual(lgw.giants_fullname_map(), {})


class MvpPollLineTests(unittest.TestCase):
    """試合後 MVP Poll 案 (2026-07-10 小手先インプ策)。"""

    _PLAYS = [
        {"giants_batting": True, "batter": "岡本和真", "pitcher": "才木",
         "outcome": "ライトへのホームラン"},
        {"giants_batting": True, "batter": "泉口友汰", "pitcher": "才木",
         "outcome": "センターへのヒット"},
        {"giants_batting": True, "batter": "キャベッジ", "pitcher": "才木",
         "outcome": "レフトへのツーベース"},
        {"giants_batting": False, "batter": "大山", "pitcher": "戸郷翔征",
         "outcome": "空振り三振"},
    ]

    def test_win_poll_bundles_names(self):
        from src.live_game_watch import build_mvp_poll_line

        line = build_mvp_poll_line(self._PLAYS, True)
        self.assertIn("今日のMVPは？", line)
        self.assertIn("岡本和真", line)
        self.assertIn("戸郷翔征", line)

    def test_loss_uses_forward_looking_question(self):
        from src.live_game_watch import build_mvp_poll_line

        line = build_mvp_poll_line(self._PLAYS, False)
        self.assertIn("明日、期待したいのは？", line)

    def test_too_few_names_returns_empty(self):
        from src.live_game_watch import build_mvp_poll_line

        self.assertEqual(build_mvp_poll_line([], True), "")
        one = [{"giants_batting": True, "batter": "岡本和真", "outcome": "ヒット"}]
        self.assertEqual(build_mvp_poll_line(one, True), "")
