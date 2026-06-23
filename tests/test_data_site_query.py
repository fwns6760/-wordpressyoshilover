"""Tests for data_site_query venue split (ticket 447 Phase 1.0c venue)."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from src.data_site_query import (
    giants_venue_from_game_id,
    fetch_contribution_streak,
    fetch_hit_streak,
    fetch_latest_giants_game_date,
    fetch_player_latest_game_date,
    fetch_inning_split_stats,
    fetch_surprise_stats,
    fetch_weekday_split_stats,
    fetch_month_split_stats,
    fetch_interleague_split_stats,
    find_player_featured_image_url,
    _classify_atbat,
)


class GiantsVenueFromGameIdTests(unittest.TestCase):
    """game_id (NPB.jp box score code `{home}-{away}-{no}`) → 巨人視点 home/away。"""

    def test_giants_home_left_code(self) -> None:
        # 巨人 code 'g' が左 (home) = 本拠地
        self.assertEqual(giants_venue_from_game_id("2026-03-27:g-t-01"), "home")
        self.assertEqual(giants_venue_from_game_id("2026-04-03:g-db-01"), "home")

    def test_giants_away_right_code(self) -> None:
        # 巨人 code 'g' が右 (away) = ビジター
        self.assertEqual(giants_venue_from_game_id("2026-03-31:d-g-01"), "away")
        self.assertEqual(giants_venue_from_game_id("2026-04-07:c-g-01"), "away")

    def test_non_giants_game_returns_none(self) -> None:
        # 巨人が含まれない試合 (リーグ全体 ingest 分) は None
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:db-s-01"))
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:c-d-01"))

    def test_malformed_returns_none(self) -> None:
        self.assertIsNone(giants_venue_from_game_id(""))
        self.assertIsNone(giants_venue_from_game_id("no-colon-here"))
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:g"))


class PlayerFeaturedImagePublicFallbackTests(unittest.TestCase):
    """YT Shorts can use curated player media even when WP write creds are absent."""

    def test_public_media_source_url_without_wp_creds(self) -> None:
        class FakeResponse:
            ok = True

            def json(self) -> dict[str, str]:
                return {"source_url": "https://yoshilover.com/wp-content/uploads/kishida.jpg"}

        def fake_get(url: str, **kwargs):
            self.assertIn("/wp-json/wp/v2/media/66557", url)
            self.assertNotIn("auth", kwargs)
            self.assertEqual(kwargs["params"], {"_fields": "source_url"})
            return FakeResponse()

        with (
            mock.patch.dict(os.environ, {"WP_URL": "", "WP_USER": "", "WP_APP_PASSWORD": ""}, clear=False),
            mock.patch("src.data_site_query.requests.get", side_effect=fake_get),
        ):
            url = find_player_featured_image_url("岸田 行倫")

        self.assertEqual(url, "https://yoshilover.com/wp-content/uploads/kishida.jpg")


class ClassifyAtbatTests(unittest.TestCase):
    """NPB box score 打席結果 → (is_ab, is_hit) 分類 (metric pack #5 inning)。"""

    def test_hits(self) -> None:
        for cell in ["右前安", "中前安", "遊安", "投安"]:  # 単打
            self.assertEqual(_classify_atbat(cell), (True, True), cell)
        for cell in ["右越本", "左中本①", "中越本"]:  # 本塁打 (circled num 付き含む)
            self.assertEqual(_classify_atbat(cell), (True, True), cell)
        for cell in ["左線２", "右中２", "左越２"]:  # 二塁打
            self.assertEqual(_classify_atbat(cell), (True, True), cell)

    def test_outs_are_ab_not_hit(self) -> None:
        for cell in ["三 振", "二ゴロ", "遊ゴロ", "中飛", "左飛", "三邪飛",
                     "遊併打", "二直", "三ゴ失", "遊ゴ失"]:
            self.assertEqual(_classify_atbat(cell), (True, False), cell)

    def test_non_ab_outcomes(self) -> None:
        for cell in ["四 球", "敬遠四", "死球", "投犠打", "中犠飛", "一犠打"]:
            self.assertEqual(_classify_atbat(cell), (False, False), cell)

    def test_empty_and_dash(self) -> None:
        self.assertEqual(_classify_atbat("-"), (False, False))
        self.assertEqual(_classify_atbat(""), (False, False))
        self.assertEqual(_classify_atbat("   "), (False, False))


class FetchInningSplitStatsTests(unittest.TestCase):
    """batting_logs.atbats_json (index=イニング) → 序盤/中盤/終盤 集計。"""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.execute(
            "CREATE TABLE batting_logs (player_canonical TEXT, atbats_json TEXT, team_name TEXT)"
        )
        # 2 試合分。 序盤(idx0-2) 中盤(idx3-5) 終盤(idx6-8)。
        games = [
            # game1: 1回 安 / 4回 三振 / 7回 二塁打 / 9回 四球
            ["右前安", "-", "-", "三振", "-", "-", "左線２", "-", "四球"],
            # game2: 2回 ゴロ / 5回 安 / 8回 本塁打
            ["-", "遊ゴロ", "-", "-", "中前安", "-", "-", "右越本", "-"],
        ]
        for g in games:
            conn.execute(
                "INSERT INTO batting_logs VALUES (?, ?, ?)",
                ("吉川尚輝", json.dumps(g, ensure_ascii=False), "巨人"),
            )
        conn.commit()
        conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_buckets_and_avg(self) -> None:
        stats = {s.phase: s for s in fetch_inning_split_stats("吉川尚輝")}
        # 序盤: 安 + ゴロ = 2 AB, 1 H
        self.assertEqual((stats["序盤"].ab, stats["序盤"].hits), (2, 1))
        # 中盤: 三振 + 安 = 2 AB, 1 H
        self.assertEqual((stats["中盤"].ab, stats["中盤"].hits), (2, 1))
        # 終盤: 二塁打 + 本塁打 = 2 AB, 2 H (四球は非 AB)
        self.assertEqual((stats["終盤"].ab, stats["終盤"].hits), (2, 2))
        self.assertAlmostEqual(stats["終盤"].avg, 1.0)

    def test_unknown_player_empty(self) -> None:
        self.assertEqual(fetch_inning_split_stats("存在しない選手"), [])


class FetchStreakFreshnessTests(unittest.TestCase):
    """連続記録は長期欠場選手を active 扱いしない。"""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.execute("CREATE TABLE games(game_id TEXT, game_date TEXT)")
        conn.execute(
            "CREATE TABLE batting_logs("
            "game_id TEXT, player_canonical TEXT, team_name TEXT, H INT, R INT, RBI INT)"
        )
        games = [
            ("2026-05-20:g-t-01", "2026-05-20"),
            ("2026-05-21:g-t-02", "2026-05-21"),
            ("2026-05-22:g-t-03", "2026-05-22"),
            ("2026-05-23:g-t-04", "2026-05-23"),
            ("2026-05-24:g-t-05", "2026-05-24"),
            ("2026-05-25:g-t-06", "2026-05-25"),
        ]
        conn.executemany("INSERT INTO games VALUES (?, ?)", games)
        for gid, _date in games:
            conn.execute(
                "INSERT INTO batting_logs VALUES (?, ?, ?, ?, ?, ?)",
                (gid, "吉川尚輝", "巨人", 1, 0, 0),
            )
        for gid in ["2026-05-20:g-t-01", "2026-05-21:g-t-02", "2026-05-22:g-t-03"]:
            conn.execute(
                "INSERT INTO batting_logs VALUES (?, ?, ?, ?, ?, ?)",
                (gid, "平山 功太", "巨人", 1, 1, 0),
            )
        conn.commit()
        conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_hit_streak_extended_absence_is_not_active(self) -> None:
        streak = fetch_hit_streak("平山 功太")
        self.assertEqual(streak.active, 0)
        self.assertEqual(streak.season_max, 3)

    def test_contribution_streak_extended_absence_is_not_active(self) -> None:
        streak = fetch_contribution_streak("平山 功太")
        self.assertEqual(streak.active, 0)
        self.assertEqual(streak.season_max, 3)

    def test_recently_playing_player_keeps_active_streak(self) -> None:
        streak = fetch_hit_streak("吉川尚輝")
        self.assertEqual(streak.active, 6)
        self.assertEqual(streak.season_max, 6)

    def test_latest_game_dates_are_log_backed(self) -> None:
        self.assertEqual(fetch_latest_giants_game_date(), "2026-05-25")
        self.assertEqual(fetch_player_latest_game_date("吉川尚輝"), "2026-05-25")
        self.assertEqual(fetch_player_latest_game_date("平山 功太"), "2026-05-22")


class FetchSurpriseStatsTests(unittest.TestCase):
    """驚きデータは短期欠場ノイズを除外し、season/last_30d から出す。"""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.execute("CREATE TABLE games(game_id TEXT, game_date TEXT)")
        conn.execute(
            "CREATE TABLE batting_logs("
            "game_id TEXT, player_canonical TEXT, team_name TEXT, H INT, R INT, RBI INT)"
        )
        conn.execute(
            "CREATE TABLE pitching_logs(game_id TEXT, player_canonical TEXT, team_name TEXT)"
        )
        conn.execute(
            "CREATE TABLE advanced_metric_snapshots("
            "snapshot_date TEXT, player_canonical TEXT, team_code TEXT, scope TEXT, "
            "metric_name TEXT, metric_value REAL, sample_size INT, league_rank INT, league_total INT)"
        )
        games = [
            ("2026-05-20:g-t-01", "2026-05-20"),
            ("2026-05-21:g-t-02", "2026-05-21"),
            ("2026-05-22:g-t-03", "2026-05-22"),
            ("2026-05-23:g-t-04", "2026-05-23"),
            ("2026-05-24:g-t-05", "2026-05-24"),
            ("2026-05-25:g-t-06", "2026-05-25"),
        ]
        conn.executemany("INSERT INTO games VALUES (?, ?)", games)
        for gid, _date in games:
            conn.execute(
                "INSERT INTO batting_logs VALUES (?, ?, ?, ?, ?, ?)",
                (gid, "吉川尚輝", "巨人", 1, 0, 0),
            )
        conn.execute("INSERT INTO batting_logs VALUES (?, ?, ?, ?, ?, ?)", ("2026-05-25:g-t-06", "岸田 行倫", "巨人", 1, 0, 0))
        conn.execute("INSERT INTO batting_logs VALUES (?, ?, ?, ?, ?, ?)", ("2026-05-22:g-t-03", "平山 功太", "巨人", 1, 0, 0))
        rows = [
            ("2026-05-25", "吉川尚輝", "g", "season", "OPS", 0.890, 120, 4, 80),
            ("2026-05-25", "岸田 行倫", "g", "last_30d", "OBP", 0.410, 25, 3, 80),
            ("2026-05-25", "平山 功太", "g", "last_30d", "OPS", 0.950, 30, 1, 80),
        ]
        conn.executemany("INSERT INTO advanced_metric_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_surprise_stats_exclude_stale_last_30d_player(self) -> None:
        rows = fetch_surprise_stats(top_n=5)
        names = [r.player for r in rows]
        self.assertIn("吉川尚輝", names)
        self.assertIn("岸田 行倫", names)
        self.assertNotIn("平山 功太", names)
        self.assertTrue(any("リーグ" in r.note for r in rows))


if __name__ == "__main__":
    unittest.main()


class DateBasedSplitTests(unittest.TestCase):
    """曜日別/月別/交流戦別 split (Phase B 452)。"""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            "CREATE TABLE advanced_metric_snapshots(player_canonical TEXT, team_code TEXT);"
            "CREATE TABLE batting_logs(game_id TEXT, player_canonical TEXT, AB INT, H INT, team_name TEXT);"
            "CREATE TABLE games(game_id TEXT, game_date TEXT);"
        )
        # 2026-05-29(金) vs f=交流戦 / 2026-05-22(金) vs t=リーグ戦 / 2026-04-05(日)
        rows = [
            ("2026-05-29:f-g-01", "2026-05-29", 4, 2),
            ("2026-05-22:g-t-09", "2026-05-22", 3, 0),
            ("2026-04-05:g-s-01", "2026-04-05", 4, 1),
        ]
        for gid, gd, ab, h in rows:
            conn.execute("INSERT INTO games VALUES(?,?)", (gid, gd))
            conn.execute("INSERT INTO batting_logs VALUES(?,?,?,?,?)", (gid, "岸田 行倫", ab, h, "巨人"))
        conn.commit(); conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_weekday(self) -> None:
        d = {s.label: s for s in fetch_weekday_split_stats("岸田 行倫")}
        self.assertEqual((d["金"].ab, d["金"].hits), (7, 2))   # 5/29 + 5/22 = 金2試合
        self.assertIn("日", d)                                  # 4/05 日

    def test_interleague(self) -> None:
        d = {s.label: s for s in fetch_interleague_split_stats("岸田 行倫")}
        self.assertEqual((d["交流戦"].ab, d["交流戦"].hits), (4, 2))   # vs f
        self.assertEqual(d["リーグ戦"].ab, 7)                          # vs t + vs s

    def test_month(self) -> None:
        d = {s.label: s for s in fetch_month_split_stats("岸田 行倫")}
        self.assertIn("5月", d); self.assertIn("4月", d)
        self.assertEqual(d["5月"].ab, 7)


class PitcherOpponentSplitTests(unittest.TestCase):
    """投手 vs 各球団 split (456 投手 split 横展開)。"""

    def setUp(self) -> None:
        from data_site_query import (  # noqa: F401
            fetch_pitcher_opponent_split_stats,
            fetch_pitcher_venue_split_stats,
            fetch_pitcher_weekday_split_stats,
            fetch_pitcher_month_split_stats,
            fetch_pitcher_interleague_split_stats,
        )
        self.fn = fetch_pitcher_opponent_split_stats
        self.fn_venue = fetch_pitcher_venue_split_stats
        self.fn_weekday = fetch_pitcher_weekday_split_stats
        self.fn_month = fetch_pitcher_month_split_stats
        self.fn_interleague = fetch_pitcher_interleague_split_stats
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            "CREATE TABLE pitching_logs(game_id TEXT, player_canonical TEXT, IP REAL, "
            "K INT, BB INT, H_allowed INT, HR_allowed INT, ER INT, pitches INT, result_mark TEXT, team_name TEXT);"
            "CREATE TABLE games(game_id TEXT, opponent TEXT, game_date TEXT);"
        )
        # vs 阪神 2登板 (IP 6.0+5.0=11.0, K 9, ER 3) / vs 中日 1登板 (IP 7.0, ER 0)
        data = [
            ("2026-05-01:g-t-01", "阪神", 6.0, 5, 1),
            ("2026-05-08:t-g-02", "阪神", 5.0, 4, 2),
            ("2026-05-15:g-d-03", "中日", 7.0, 8, 0),
            ("2026-06-01:g-h-01", "ソフトバンク", 4.0, 3, 1),  # 交流戦 (パ=h) / 本拠地
        ]
        for gid, opp, ip, k, er in data:
            conn.execute("INSERT INTO games(game_id,opponent,game_date) VALUES(?,?,?)",
                         (gid, opp, gid.split(":")[0]))
            conn.execute(
                "INSERT INTO pitching_logs(game_id,player_canonical,IP,K,BB,H_allowed,"
                "HR_allowed,ER,pitches,result_mark,team_name) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (gid, "戸郷 翔征", ip, k, 0, 0, 0, er, 0, "", "巨人"),
            )
        conn.commit(); conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_aggregation_and_era(self) -> None:
        d = {row[0]: row for row in self.fn("戸郷 翔征")}
        _, g, ip, k, er, era = d["阪神"]
        self.assertEqual((g, k, er), (2, 9, 3))
        self.assertAlmostEqual(ip, 11.0, places=1)
        self.assertAlmostEqual(era, 3 * 9.0 / 11.0, places=2)
        _, g2, _ip2, _k2, er2, era2 = d["中日"]
        self.assertEqual((g2, er2), (1, 0))
        self.assertAlmostEqual(era2, 0.0)

    def test_readside_fuzzy_match(self) -> None:
        # space 有無に依存しない (read-side REPLACE、 batter_canonical backfill 不要)
        self.assertTrue(self.fn("戸郷翔征"))

    def test_unknown_player_empty(self) -> None:
        self.assertEqual(self.fn("存在しない投手"), [])

    def test_venue_split(self) -> None:
        d = {row[0]: row for row in self.fn_venue("戸郷 翔征")}
        # 本拠地 = g-t-01 + g-d-03 + g-h-01 (3登板, IP 6+7+4=17.0)
        self.assertEqual(d["本拠地"][1], 3)
        self.assertAlmostEqual(d["本拠地"][2], 17.0, places=1)
        # ビジター = t-g-02 (1登板, IP 5.0)
        self.assertEqual(d["ビジター"][1], 1)
        self.assertAlmostEqual(d["ビジター"][2], 5.0, places=1)

    def test_interleague_split(self) -> None:
        d = {row[0]: row for row in self.fn_interleague("戸郷 翔征")}
        self.assertEqual(d["リーグ戦"][1], 3)   # 阪神x2 + 中日
        self.assertEqual(d["交流戦"][1], 1)      # ソフトバンク(パ)

    def test_month_split(self) -> None:
        d = {row[0]: row for row in self.fn_month("戸郷 翔征")}
        self.assertEqual(d["5月"][1], 3)
        self.assertEqual(d["6月"][1], 1)

    def test_weekday_split(self) -> None:
        rows = self.fn_weekday("戸郷 翔征")
        self.assertTrue(rows)
        self.assertEqual(sum(r[1] for r in rows), 4)  # 全登板が曜日バケットに帰属


class RispSplitTests(unittest.TestCase):
    """得点圏 (RISP) split + is_official_at_bat (457、 at_bat_details read-side)。"""

    def setUp(self) -> None:
        from data_site_query import fetch_risp_split_stats, is_official_at_bat  # noqa: F401
        self.fn = fetch_risp_split_stats
        self.is_ab = is_official_at_bat
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            "CREATE TABLE at_bat_details(batter TEXT, runner_state TEXT, result_text TEXT, team TEXT);"
        )
        # 吉川尚輝 (姓=吉川): 得点圏 AB=3 H=2 (1塁=非得点圏skip, フォアボール=非AB除外)
        rows = [
            ("吉川", "2塁", "センター前ヒット", "巨人"),          # RISP, AB, H
            ("吉川", "1塁", "ショートゴロ", "巨人"),              # 非得点圏 → skip
            ("吉川", "満塁", "空振り三振", "巨人"),               # RISP, AB, 非H
            ("吉川", "3塁", "フォアボール", "巨人"),              # RISP だが非AB → 除外
            ("代打・ 吉川", "2・3塁", "レフト前タイムリーヒット（打点2）", "巨人"),  # 代打prefix, RISP, AB, H
            ("坂本", "満塁", "センター前ヒット", "巨人"),         # 別姓 → skip
        ]
        for b, rs, rt, tm in rows:
            conn.execute("INSERT INTO at_bat_details VALUES(?,?,?,?)", (b, rs, rt, tm))
        conn.commit(); conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_risp_count_and_avg(self) -> None:
        d = {row[0]: row for row in self.fn("吉川尚輝")}
        risp = d["得点圏"]  # (label, AB, H, AVG)
        self.assertEqual((risp[1], risp[2]), (3, 2))
        self.assertAlmostEqual(risp[3], 2 / 3, places=2)

    def test_other_surname_excluded(self) -> None:
        # 坂本 の満塁ヒットは 吉川 に混入しない (姓 prefix 一致)
        d = {row[0]: row for row in self.fn("吉川尚輝")}
        self.assertEqual(d["得点圏"][1], 3)  # 坂本分が混ざれば 4 になる

    def test_unknown_player_empty(self) -> None:
        self.assertEqual(self.fn("存在しない 選手"), [])

    def test_is_official_at_bat(self) -> None:
        for hit in ("センター前ヒット", "空振り三振", "レフト線ツーベース", "ショートゴロ併殺打"):
            self.assertTrue(self.is_ab(hit), hit)
        for non in ("フォアボール", "敬遠フォアボール", "デッドボール",
                    "サード犠牲バント", "レフト犠牲フライ", "打撃妨害", ""):
            self.assertFalse(self.is_ab(non), non)


class VsLrSplitTests(unittest.TestCase):
    """対左/右投手 split (457、 at_bat_details + throws map)。"""

    def setUp(self) -> None:
        from data_site_query import fetch_vs_lr_split_stats  # noqa: F401
        self.fn = fetch_vs_lr_split_stats
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            "CREATE TABLE at_bat_details(batter TEXT, current_pitcher TEXT, result_text TEXT, team TEXT);"
        )
        rows = [
            ("吉川", "左腕太郎", "センター前ヒット", "巨人"),   # L AB H
            ("吉川", "左腕太郎", "空振り三振", "巨人"),         # L AB 非H
            ("吉川", "右腕次郎", "ライト前ヒット", "巨人"),     # R AB H
            ("吉川", "右腕次郎", "フォアボール", "巨人"),       # R 非AB除外
            ("吉川", "無名投手", "センター前ヒット", "巨人"),   # throws不明 → skip
            ("代打・ 吉川", "左腕太郎", "レフト線ツーベース", "巨人"),  # 代打prefix, L AB H
            ("坂本", "左腕太郎", "センター前ヒット", "巨人"),   # 別姓 → skip
        ]
        for b, p, rt, tm in rows:
            conn.execute("INSERT INTO at_bat_details VALUES(?,?,?,?)", (b, p, rt, tm))
        conn.commit(); conn.close()
        self.throws = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8")
        json.dump({"左腕太郎": {"team": "t", "throws": "L"},
                   "右腕次郎": {"team": "t", "throws": "R"}}, self.throws, ensure_ascii=False)
        self.throws.close()
        self._prev_db = os.environ.get("INSIGHT_DB_PATH")
        self._prev_throws = os.environ.get("NPB_THROWS_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name
        os.environ["NPB_THROWS_PATH"] = self.throws.name

    def tearDown(self) -> None:
        for key, prev in (("INSIGHT_DB_PATH", self._prev_db), ("NPB_THROWS_PATH", self._prev_throws)):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev
        os.unlink(self.tmp.name)
        os.unlink(self.throws.name)

    def test_vs_lr_count_and_avg(self) -> None:
        d = {row[0]: row for row in self.fn("吉川尚輝")}
        # 対左: ヒット+三振+ツーベース = AB3 H2
        self.assertEqual((d["対左投手"][1], d["対左投手"][2]), (3, 2))
        self.assertAlmostEqual(d["対左投手"][3], 2 / 3, places=2)
        # 対右: ヒット(フォアボール除外) = AB1 H1
        self.assertEqual((d["対右投手"][1], d["対右投手"][2]), (1, 1))

    def test_unknown_player_empty(self) -> None:
        self.assertEqual(self.fn("存在しない 選手"), [])


class SabermetricsTests(unittest.TestCase):
    """461 セイバーメトリクス (advanced_metric_snapshots、 最新 snapshot 選択)。"""

    def setUp(self) -> None:
        from data_site_query import fetch_sabermetrics  # noqa: F401
        self.fn = fetch_sabermetrics
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            "CREATE TABLE advanced_metric_snapshots(snapshot_date TEXT, scope TEXT, "
            "player_canonical TEXT, metric_name TEXT, metric_value REAL, "
            "league_rank INT, league_total INT);"
        )
        rows = [
            ("2026-05-01", "last_30d", "吉川尚輝", "OPS", 0.700, 50, 144),   # 古い→不採用
            ("2026-06-01", "last_30d", "吉川尚輝", "OPS", 0.812, 12, 144),   # 最新
            ("2026-06-01", "last_30d", "吉川尚輝", "ISO", 0.150, 30, 144),
            ("2026-06-01", "last_30d", "吉川尚輝", "BB_pct", 0.085, 20, 144),
            ("2026-06-01", "last_30d", "戸郷翔征", "ERA", 3.38, 8, 60),
            ("2026-06-01", "last_30d", "戸郷翔征", "FIP", 3.10, 6, 60),
        ]
        for r in rows:
            conn.execute("INSERT INTO advanced_metric_snapshots VALUES(?,?,?,?,?,?,?)", r)
        conn.commit(); conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_batter_latest_snapshot_and_format(self) -> None:
        d = {lbl: (val, rank, total) for (lbl, val, rank, total) in self.fn("吉川尚輝", False)}
        self.assertEqual(d["OPS"][0], ".812")      # 最新 snapshot (.700 でない)
        self.assertEqual(d["OPS"][1], 12)
        self.assertEqual(d["ISO"][0], ".150")
        self.assertEqual(d["BB%"][0], "8.5%")

    def test_pitcher_spec(self) -> None:
        d = {lbl: val for (lbl, val, rank, total) in self.fn("戸郷翔征", True)}
        self.assertEqual(d["防御率"], "3.38")
        self.assertEqual(d["FIP"], "3.10")

    def test_unknown_player_empty(self) -> None:
        self.assertEqual(self.fn("存在しない", False), [])


class TeamRecordTests(unittest.TestCase):
    """459 巨人 チーム成績 (games 由来)。"""

    def setUp(self) -> None:
        from data_site_query import fetch_giants_team_record  # noqa: F401
        self.fn = fetch_giants_team_record
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            "CREATE TABLE games(game_id TEXT, game_date TEXT, result TEXT, "
            "giants_score INT, opp_score INT);"
        )
        rows = [
            ("2026-04-01:g-t-01", "2026-04-01", "win", 3, 1),    # home win
            ("2026-04-02:t-g-01", "2026-04-02", "loss", 0, 2),   # away loss
            ("2026-04-03:g-d-01", "2026-04-03", "win", 5, 4),    # home win
            ("2026-04-04:g-d-02", "2026-04-04", "draw", 2, 2),   # home draw
            ("2026-04-05:s-g-01", "2026-04-05", "loss", 1, 6),   # away loss (最新→1連敗)
            ("2026-04-06:t-x-01", "2026-04-06", "win", 9, 0),    # 巨人不在 → 除外
        ]
        for r in rows:
            conn.execute("INSERT INTO games VALUES(?,?,?,?,?)", r)
        conn.commit(); conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_record(self) -> None:
        r = self.fn()
        self.assertEqual((r["wins"], r["losses"], r["draws"]), (2, 2, 1))
        self.assertAlmostEqual(r["win_pct"], 0.5)
        self.assertEqual((r["runs_for"], r["runs_against"], r["run_diff"]), (11, 15, -4))
        self.assertEqual((r["streak"], r["streak_kind"]), (1, "L"))
        self.assertEqual(r["home"], (2, 0))
        self.assertEqual(r["away"], (0, 2))
        # 巨人不在 game (t-x-01) は除外されている (win 3 にならない)


class StandingsParseTests(unittest.TestCase):
    """459/C parse_npb_cl_standings (NPB公式 HTML パース、 純粋関数)。"""

    FIXTURE = (
        "<table>"
        "<tr><th>チーム</th><th>試合</th><th>勝利</th><th>敗北</th><th>引分</th>"
        "<th>勝率</th><th>差</th><th>ホーム</th></tr>"
        "<tr><td>東京ヤクルトスワローズ</td><td>52</td><td>31</td><td>20</td><td>1</td>"
        "<td>.608</td><td>--</td><td>13-9</td></tr>"
        "<tr><td>阪神タイガース</td><td>52</td><td>30</td><td>21</td><td>1</td>"
        "<td>.588</td><td>1.0</td><td>14-12</td></tr>"
        "<tr><td>読売ジャイアンツ</td><td>52</td><td>27</td><td>25</td><td>0</td>"
        "<td>.519</td><td>4.5</td><td>14-14</td></tr>"
        "</table>"
        # 2つ目(交流戦)表 — seen+break で除外されるべき
        "<table><tr><td>読売ジャイアンツ</td><td>6</td><td>3</td><td>3</td><td>0</td>"
        "<td>.500</td><td>--</td><td>1-2</td></tr></table>"
    )

    def test_parse(self) -> None:
        from data_site_query import parse_npb_cl_standings
        rows = parse_npb_cl_standings(self.FIXTURE)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["team"], "ヤクルト")
        self.assertEqual(rows[0]["rank"], 1)
        g = rows[2]
        self.assertEqual((g["rank"], g["team"], g["w"], g["l"], g["pct"], g["gb"]),
                         (3, "巨人", "27", "25", ".519", "4.5"))
        self.assertTrue(g["is_giants"])
        # 交流戦表の巨人(.500) は混入しない (seen で重複排除)
        self.assertEqual(sum(1 for r in rows if r["team"] == "巨人"), 1)


class UpcomingParseTests(unittest.TestCase):
    """459/C parse_giants_upcoming (NPB日程 HTML、 未来試合のみ抽出、 純粋関数)。"""

    FIXTURE = (
        '<div>6/1（月）<span class="team1">巨人</span><span class="team2">中日</span>'
        '<span class="score1">3</span><span class="time">18:00</span><span class="place">バンテリンD</span></div>'
        '<div>6/2（火）<span class="team1">巨人</span><span class="team2">オリックス</span>'
        '<span class="score1"></span><span class="time">18:00</span><span class="place">東京ドーム</span></div>'
        '<div>6/2（火）<span class="team1">阪神</span><span class="team2">広島</span>'
        '<span class="score1"></span><span class="time">18:00</span><span class="place">甲子園</span></div>'
    )

    def test_parse_future_only(self) -> None:
        from data_site_query import parse_giants_upcoming
        from datetime import date as _date
        rows = parse_giants_upcoming(self.FIXTURE, 2026, _date(2026, 6, 2))
        self.assertEqual(len(rows), 1)  # 6/1(過去)除外, 阪神戦(非巨人)除外
        u = rows[0]
        self.assertEqual(
            (u["date"], u["opp"], u["home_away"], u["time"], u["place"]),
            ("2026-06-02", "オリックス", "本拠地", "18:00", "東京ドーム"),
        )


class StartersParseTests(unittest.TestCase):
    """459/C parse_giants_starters (予告先発、 (巨)ペア抽出、 純粋関数)。"""

    FIXTURE = (
        '<tr><td>先発</td><td>(巨) <a href="/bis/players/1.html">則　本</a></td></tr>'
        '<tr><td>先発</td><td>(オ) <a href="/bis/players/2.html">九里</a></td></tr>'
        '<tr><td>先発</td><td>(ヤ) <a href="/bis/players/3.html">松本健</a></td></tr>'
        '<tr><td>先発</td><td>(ロ) <a href="/bis/players/4.html">ジャクソン</a></td></tr>'
    )

    def test_parse_giants_pair(self) -> None:
        from data_site_query import parse_giants_starters
        d = parse_giants_starters(self.FIXTURE)
        self.assertEqual(d.get("giants"), "則本")   # 全角space除去
        self.assertEqual(d.get("opp"), "九里")
        self.assertEqual(d.get("opp_abbr"), "オ")    # cross-check 用(=オリックス)

    def test_no_giants(self) -> None:
        from data_site_query import parse_giants_starters
        html = ('<tr><td>先発</td><td>(ヤ) <a href="x">A</a></td></tr>'
                '<tr><td>先発</td><td>(ロ) <a href="y">B</a></td></tr>')
        self.assertEqual(parse_giants_starters(html), {})


class PlayerEyecatchMapTests(unittest.TestCase):
    """選手 pillar 顔写真は curated eyecatch map 最優先 + 巨人マーク fallback。

    旧実装の「最新タグ記事 eyecatch 流用」で対戦相手のチームマーク (戸郷=中日マーク)
    が出ていた事故の回帰防止。
    """

    def test_mapped_player_returns_curated_id(self) -> None:
        from data_site_query import mapped_player_media_id, find_player_featured_media_id
        # 戸郷翔征 は map に curated 写真 66521 がある (中日マークではない)
        self.assertEqual(mapped_player_media_id("戸郷翔征"), 66521)
        self.assertEqual(find_player_featured_media_id("戸郷翔征"), 66521)
        # 全角/半角空白を含む表記でも引ける
        self.assertEqual(mapped_player_media_id("戸郷　翔征"), 66521)

    def test_unmapped_player_falls_back_to_giants_mark(self) -> None:
        from data_site_query import (
            mapped_player_media_id,
            find_player_featured_media_id,
            _GIANTS_MARK_MEDIA_ID,
        )
        self.assertIsNone(mapped_player_media_id("存在しない架空選手ZZZ"))
        # 対戦相手マーク等ではなく巨人マークに落ちる
        self.assertEqual(find_player_featured_media_id("存在しない架空選手ZZZ"), _GIANTS_MARK_MEDIA_ID)


class CareerLeadersTests(unittest.TestCase):
    """468-1 build_career_leaders: career cache から通算ランキングを集計。"""

    @classmethod
    def setUpClass(cls) -> None:
        import os
        from src.npb_career_scraper import parse_player_career
        fix = os.path.join(os.path.dirname(__file__), "fixtures")
        with open(os.path.join(fix, "npb_career_batter_sakamoto_51955114.html"), encoding="utf-8", errors="replace") as fh:
            bat = parse_player_career(fh.read())
        with open(os.path.join(fix, "npb_career_pitcher_togo_41045138.html"), encoding="utf-8", errors="replace") as fh:
            pit = parse_player_career(fh.read())
        cls.cache = {
            "ids": {"坂本勇人": "1", "戸郷翔征": "2"},
            "players": {"1": bat, "2": pit},
        }

    def test_batting_leaders(self) -> None:
        from data_site_query import build_career_leaders
        lead = build_career_leaders(self.cache, top_n=10)
        self.assertIn("通算安打", lead)
        top = lead["通算安打"][0]
        self.assertEqual(top.player, "坂本勇人")
        self.assertEqual(top.display, "2457")
        self.assertEqual(lead["通算本塁打"][0].display, "300本")

    def test_pitching_leaders_only_pitchers(self) -> None:
        from data_site_query import build_career_leaders
        lead = build_career_leaders(self.cache, top_n=10)
        # 投手成績は is_pitcher の戸郷のみ (坂本は混ざらない)
        self.assertIn("通算勝利", lead)
        win = lead["通算勝利"]
        self.assertEqual(len(win), 1)
        self.assertEqual(win[0].player, "戸郷翔征")
        self.assertEqual(win[0].display, "65勝")
        # 防御率は登板50以上の戸郷 (147登板) が入る
        self.assertEqual(lead["通算防御率"][0].player, "戸郷翔征")

    def test_empty_cache_safe(self) -> None:
        from data_site_query import build_career_leaders
        self.assertEqual(build_career_leaders({}), {})
        self.assertEqual(build_career_leaders(None), {})


class AlltimeLeadersTests(unittest.TestCase):
    """Phase1 build_alltime_leaders: 共有部品(OB+現役)全史ランキングの adapter。"""

    def setUp(self) -> None:
        from src.analysis import alltime_ranking as ar
        self._orig = ar.load_ob_stats
        # 小さな OB(現役が top10 に入るよう値を抑える)。
        ar.load_ob_stats = lambda: {
            "王貞治": {"type": "batter", "slug": "oh", "npb": {"hr": 868, "hits": 2786, "rbi": 2170}},
            "長嶋茂雄": {"type": "batter", "slug": "nagashima", "npb": {"hr": 444, "hits": 2471, "rbi": 1522}},
            "中畑清": {"type": "batter", "slug": "nakahata", "npb": {"hr": 171, "hits": 1294, "rbi": 705}},
            "金田正一": {"type": "pitcher", "slug": "kaneda", "npb": {"w": 400, "k": 4490}},
        }
        self.cache = {
            "ids": {"坂本勇人": "1"},
            "players": {"1": {"is_pitcher": False,
                              "batting": {"total": {"本塁打": "300", "安打": "2457", "打点": "1065"}}}},
        }

    def tearDown(self) -> None:
        from src.analysis import alltime_ranking as ar
        ar.load_ob_stats = self._orig

    def test_alltime_marks_current_player(self) -> None:
        from data_site_query import build_alltime_leaders
        al = build_alltime_leaders(self.cache, top_n=10)
        self.assertIn("本塁打", al)
        sakamoto = next(e for e in al["本塁打"] if e.player == "坂本勇人")
        # 868 > 444 > 300(坂本) > 171 → 坂本は3位、★現役マーカー + 単位「本」
        self.assertIn("★現役", sakamoto.display)
        self.assertIn("本", sakamoto.display)
        self.assertEqual(al["本塁打"][0].player, "王貞治")

    def test_alltime_empty_cache_safe(self) -> None:
        from data_site_query import build_alltime_leaders
        al = build_alltime_leaders({})
        # OB のみでもランキングは出る(現役マーカー無し)
        self.assertIn("本塁打", al)
        self.assertFalse(any("★現役" in e.display for e in al["本塁打"]))

    def test_record_room_clubs_threshold(self) -> None:
        from data_site_query import build_record_room
        rec = build_record_room(self.cache)
        # 名球会2000安打: 王2786 がメンバー、中畑(1294)は閾値未満で非掲載
        club = next((m for c, m in rec.items() if "2000安打" in c), None)
        self.assertIsNotNone(club)
        names = [e.player for e in club]
        self.assertIn("王貞治", names)
        self.assertNotIn("中畑清", names)
        # 300本塁打クラブに坂本(300, 現役)が ★現役 付きで入る
        hrclub = next((m for c, m in rec.items() if "300本塁打" in c), None)
        self.assertIsNotNone(hrclub)
        sakamoto = next(e for e in hrclub if e.player == "坂本勇人")
        self.assertIn("★現役", sakamoto.display)

    def test_record_room_empty_clubs_omitted(self) -> None:
        from data_site_query import build_record_room
        # OB を 1 人(閾値未満)に絞ると全クラブ空 → 省略
        from src.analysis import alltime_ranking as ar
        orig = ar.load_ob_stats
        ar.load_ob_stats = lambda: {"中畑清": {"type": "batter", "slug": "n", "npb": {"hr": 171, "hits": 1294, "rbi": 705}}}
        try:
            rec = build_record_room({})
            self.assertEqual(rec, {})
        finally:
            ar.load_ob_stats = orig


class LiveRosterFilterTests(unittest.TestCase):
    """退団選手の self-heal 除外 (NPB 公式現役名簿で player_class を濾過)。"""

    def _reset(self):
        import src.data_site_query as q
        q._player_class_cache = None
        q._npb_active_names_cache = None
        q._npb_active_names_fetched = False

    def test_drops_departed_keeps_active(self):
        import src.data_site_query as q
        self._reset()
        classes = {
            "shihai": {"内野手": ["宇都宮葵星", "岡本和真", "坂本勇人"]},
            "ikusei": {"投手": ["西川歩", "退団投手"]},
        }
        with mock.patch.object(
            q, "_current_npb_norm_names",
            return_value=frozenset({"宇都宮葵星", "坂本勇人", "西川歩"}),
        ):
            out = q._apply_live_roster_filter(classes)
        self.assertEqual(out["shihai"]["内野手"], ["宇都宮葵星", "坂本勇人"])
        self.assertEqual(out["ikusei"]["投手"], ["西川歩"])

    def test_noop_when_npb_unavailable(self):
        import src.data_site_query as q
        self._reset()
        classes = {"shihai": {"内野手": ["岡本和真", "坂本勇人"]}, "ikusei": {}}
        with mock.patch.object(q, "_current_npb_norm_names", return_value=None):
            out = q._apply_live_roster_filter(classes)
        # fetch 不全時は濾過しない (config 尊重 = 安全側)
        self.assertEqual(out["shihai"]["内野手"], ["岡本和真", "坂本勇人"])

    def test_thin_roster_skips_filter(self):
        import src.data_site_query as q
        self._reset()
        with mock.patch("src.giants_roster_loader._fetch_npb_roster",
                        return_value=[{"name": "唯一選手"}]):
            self.assertIsNone(q._current_npb_norm_names())

    def test_flag_off_disables_filter(self):
        import src.data_site_query as q
        self._reset()
        with mock.patch.dict(os.environ, {"DATA_SITE_ROSTER_LIVE_FILTER": "0"}):
            self.assertIsNone(q._current_npb_norm_names())
