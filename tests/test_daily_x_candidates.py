"""Tests for daily_x_candidates (449 §5 RSS話題ゲート, read-only)."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from src.tools import daily_x_candidates as dxc


class FreshnessGateTests(unittest.TestCase):
    """ゲート②: 最終出場が最新試合日から FRESH_DAYS 以内のみ fresh。"""

    def test_recent_is_fresh(self) -> None:
        self.assertTrue(dxc._is_fresh("2026-05-31", "2026-05-31"))
        self.assertTrue(dxc._is_fresh("2026-05-28", "2026-05-31"))  # 3日差 = 境界内

    def test_stale_excluded(self) -> None:
        # 平山型: 最終出場 5/22、最新試合 5/31 → 9日差で除外
        self.assertFalse(dxc._is_fresh("2026-05-22", "2026-05-31"))

    def test_missing_dates(self) -> None:
        self.assertFalse(dxc._is_fresh(None, "2026-05-31"))
        self.assertFalse(dxc._is_fresh("2026-05-31", None))


class RosterMoveRegexTests(unittest.TestCase):
    """昇格/抹消タイトルから数字を拾う(出典=記事)。"""

    def test_extracts_numbers(self) -> None:
        title = "巨人が森田駿哉を一軍登録 ファーム8登板、防御率1.65と好調の左腕が再昇格"
        nums = []
        for pat in dxc.NUM_PATTERNS:
            nums.extend(pat.findall(title))
        self.assertTrue(any("防御率1.65" in n for n in nums))
        self.assertTrue(any("8登板" in n for n in nums))

    def test_move_keyword_detect(self) -> None:
        self.assertTrue(any(kw in "今季初昇格・登録抹消" for kw in dxc.ROSTER_MOVE_KEYWORDS))


class IchigunPipelineTests(unittest.TestCase):
    """巨人ロスター ∩ 鮮度ゲート ∩ 日付ベース数字 の統合(in-memory DB)。"""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            """
            CREATE TABLE advanced_metric_snapshots(
                snapshot_date TEXT, scope TEXT, player_canonical TEXT, team_code TEXT,
                metric_name TEXT, metric_value REAL, sample_size INT,
                league_rank INT, league_total INT);
            CREATE TABLE article_candidates(
                player_canonical TEXT, signal_type TEXT, current_value TEXT, created_at TEXT);
            CREATE TABLE games(game_id TEXT, game_date TEXT);
            CREATE TABLE batting_logs(game_id TEXT, player_canonical TEXT);
            CREATE TABLE pitching_logs(game_id TEXT, player_canonical TEXT);
            """
        )
        # 巨人2選手: 岸田(fresh, 5/31) と 平山(stale, 5/22)。他球団 佐藤輝明 も混ぜる。
        conn.executemany(
            "INSERT INTO advanced_metric_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("2026-05-31", "last_7d", "岸田 行倫", "g", "AVG", 0.444, 12, 5, 127),
                ("2026-05-31", "last_7d", "平山 功太", "g", "AVG", 0.350, 10, 8, 127),
                ("2026-05-31", "last_7d", "佐藤輝明", "t", "AVG", 0.400, 12, 3, 127),
            ],
        )
        conn.executemany(
            "INSERT INTO article_candidates VALUES (?,?,?,?)",
            [
                ("岸田 行倫", "batter_hit_streak", "5試合連続安打", "2026-05-31T22:00:00"),
                ("平山 功太", "batter_hit_streak", "8試合連続安打", "2026-05-31T22:00:00"),
                ("佐藤輝明", "batter_hit_streak", "5試合連続安打", "2026-05-31T22:00:00"),
            ],
        )
        conn.executemany("INSERT INTO games VALUES (?,?)", [
            ("g1", "2026-05-31"), ("g2", "2026-05-22"),
        ])
        conn.executemany("INSERT INTO batting_logs VALUES (?,?)", [
            ("g1", "岸田 行倫"), ("g2", "平山 功太"), ("g1", "佐藤輝明"),
        ])
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

    def test_giants_only_and_fresh_only(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        cands = dxc.collect_ichigun_candidates(conn.cursor())
        conn.close()
        players = {c.player for c in cands}
        self.assertIn("岸田 行倫", players)        # 巨人 + fresh
        self.assertNotIn("平山 功太", players)      # 巨人だが stale → ゲート②で除外
        self.assertNotIn("佐藤輝明", players)        # fresh だが他球団 → ゲート①で除外

    def test_kishida_uses_date_based_number(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        cands = {c.player: c for c in dxc.collect_ichigun_candidates(conn.cursor())}
        conn.close()
        self.assertIn("直近7日", cands["岸田 行倫"].number)
        self.assertIn(".444", cands["岸田 行倫"].number)


class NewsAnchoredTests(IchigunPipelineTests):
    """ニュース起点: 記事タイトルの巨人選手にデータを紐付ける(ゲート①の DB を継承)。"""

    def test_news_links_giants_player_data(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        posts = [
            {"title": {"rendered": "巨人・岸田行倫が決勝打 好調キープ"}, "link": "https://x/1"},
            {"title": {"rendered": "【巨人データ】岸田行倫 打率セ2位"}, "link": "https://x/2"},  # 自前→除外
            {"title": {"rendered": "阪神・佐藤輝明が満塁弾"}, "link": "https://x/3"},  # 他球団→紐付かない
        ]
        cands = dxc.collect_news_anchored(conn.cursor(), posts)
        conn.close()
        joined = " ".join(c.player + c.number for c in cands)
        self.assertIn("岸田 行倫", joined)         # 記事の巨人選手にデータ紐付け
        self.assertIn(".444", joined)               # last_7d データ
        self.assertNotIn("佐藤輝明", joined)         # 他球団は紐付かない
        # 【巨人データ】post は除外(冗長回避)
        self.assertTrue(all("x/2" not in c.source for c in cands))


class SingleMailTests(unittest.TestCase):
    def test_one_candidate_per_mail(self) -> None:
        c = dxc.Candidate("ニュース連動", "岸田 行倫(記事: …)", "直近7日 打率.444", "旬の話題", "https://x/1")
        subj, text, html = dxc.build_single_mail(c, date_label="2026-06-01", idx=2, total=5)
        self.assertIn("(2/5)", subj)
        self.assertIn("岸田 行倫", subj)
        self.assertIn(".444", text)
        self.assertIn("一言", html)

    def test_flatten_order(self) -> None:
        res = {"news": [dxc.Candidate("ニュース連動", "A", "n", "m", "")],
               "hidden_hot": [dxc.Candidate("直近変化型", "B", "n", "m", "")]}
        flat = dxc.flatten_candidates(res)
        self.assertEqual([c.player for c in flat], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
