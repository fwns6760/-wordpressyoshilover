"""Tests for 404 (Phase 2 ETL、 登板 inning 別): derive_pitcher_innings + backfill_pitcher_innings。

NPB box の inning 別 pitcher table を parse せず、 既存 pitching_logs の
IP cumsum + appearance_order から start_inning / end_inning を derive する
narrow approach。

[[415]] (vs 左右投手) は別 ticket、 本 ticket では touch しない。
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from src.analysis import insight_etl


class DerivePitcherInningsTests(unittest.TestCase):
    """derive_pitcher_innings logic (pure function、 DB なし)."""

    def test_starter_only_5_full_innings(self):
        """starter 5.0 IP = 第 1-5 回投球完了。"""
        result = insight_etl.derive_pitcher_innings([(1, 5.0)])
        self.assertEqual(result, [(1, 5)])

    def test_starter_only_5_with_one_out_in_6th(self):
        """starter 5.1 (= 5 inning + 1 out in 6th) → start=1, end=6 (entered 6th)."""
        result = insight_etl.derive_pitcher_innings([(1, 5.333)])
        self.assertEqual(result, [(1, 6)])

    def test_starter_and_reliever_clean_handoff(self):
        """starter 6.0 (clean) → reliever start=7."""
        result = insight_etl.derive_pitcher_innings([(1, 6.0), (2, 1.0)])
        # starter: start=1, end=6 (cleared 6th)
        # relief: start=7, end=7 (worked 7th)
        self.assertEqual(result, [(1, 6), (7, 7)])

    def test_starter_and_reliever_mid_inning_handoff(self):
        """starter 6.1 (1 out in 7th) → reliever start=7 (continues 7th)."""
        result = insight_etl.derive_pitcher_innings([(1, 6.333), (2, 0.667)])
        # starter: start=1, end=7 (entered 7th)
        # relief: start=7 (continues 7th), end=7
        self.assertEqual(result, [(1, 7), (7, 7)])

    def test_three_pitcher_chain(self):
        """starter 5.0 + setup 2.0 + closer 1.0 = 8-inning game (extra inning shape)."""
        result = insight_etl.derive_pitcher_innings([(1, 5.0), (2, 2.0), (3, 1.0)])
        # starter: start=1, end=5
        # setup: start=6, end=7
        # closer: start=8, end=8
        self.assertEqual(result, [(1, 5), (6, 7), (8, 8)])

    def test_typical_reliever_setup_closer(self):
        """starter 6.0 + setup 1.0 (7th) + setup 1.0 (8th) + closer 1.0 (9th)."""
        result = insight_etl.derive_pitcher_innings(
            [(1, 6.0), (2, 1.0), (3, 1.0), (4, 1.0)]
        )
        self.assertEqual(result, [(1, 6), (7, 7), (8, 8), (9, 9)])

    def test_zero_ip_skipped(self):
        """IP=0 の row (1 batter face only no out) は (None, None) を返す。"""
        result = insight_etl.derive_pitcher_innings([(1, 0.0)])
        self.assertEqual(result, [(None, None)])

    def test_none_ip_skipped(self):
        """IP=None の row は (None, None)."""
        result = insight_etl.derive_pitcher_innings([(1, None)])
        self.assertEqual(result, [(None, None)])

    def test_malformed_ip_skipped(self):
        """IP=string malformed は (None, None)、 例外なく fallthrough。"""
        result = insight_etl.derive_pitcher_innings([(1, "abc")])
        self.assertEqual(result, [(None, None)])


class BackfillPitcherInningsTests(unittest.TestCase):
    """backfill_pitcher_innings: 既存 pitching_logs row を update。"""

    def _open_db(self, tmp_path: Path) -> sqlite3.Connection:
        return insight_etl.open_db(
            db_path=tmp_path / "insight.db",
            schema_path=insight_etl.DEFAULT_SCHEMA,
        )

    def _seed_game_with_pitchers(
        self,
        conn: sqlite3.Connection,
        *,
        game_id: str,
        team_role: str,
        pitchers: list[tuple[int, str, float]],  # (order, name, ip)
    ) -> None:
        conn.execute(
            "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
            "opp_score, result, source_url, source_kind, ingested_at) "
            "VALUES (?, '2026-05-19', 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
            (game_id,),
        )
        for order, name, ip in pitchers:
            conn.execute(
                "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
                "player_display, player_canonical, result_mark, pitches, BF, IP, "
                "H_allowed, HR_allowed, BB, HBP, K, R, ER, team_name) "
                "VALUES (?, ?, ?, ?, ?, '', 100, 25, ?, 5, 0, 2, 0, 5, 1, 1, '巨人')",
                (game_id, team_role, order, name, name, ip),
            )
        conn.commit()

    def test_backfill_populates_start_end_innings(self, tmp_path=None):
        """1 試合の 4 投手を seed、 backfill 後 start/end が正しく set される。"""
        # pytest fixture を使えるよう __init__ で tmp_path
        import tempfile
        tmpdir = Path(tempfile.mkdtemp())
        try:
            conn = self._open_db(tmpdir)
            self._seed_game_with_pitchers(
                conn,
                game_id="g-404",
                team_role="home",
                pitchers=[
                    (1, "戸郷翔征", 6.0),
                    (2, "大勢", 1.0),
                    (3, "マルティネス", 1.0),
                    (4, "高梨雄平", 1.0),
                ],
            )
            updated = insight_etl.backfill_pitcher_innings(conn)
            self.assertGreaterEqual(updated, 4)
            rows = [tuple(r) for r in conn.execute(
                "SELECT player_display, start_inning, end_inning "
                "FROM pitching_logs WHERE game_id='g-404' "
                "ORDER BY appearance_order"
            ).fetchall()]
            self.assertEqual(rows, [
                ("戸郷翔征", 1, 6),
                ("大勢", 7, 7),
                ("マルティネス", 8, 8),
                ("高梨雄平", 9, 9),
            ])
            conn.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_open_db_auto_backfills_existing_null_rows(self):
        """404 wire-fix (2026-05-21): open_db 経由で既存 NULL row が自動 backfill される。

        regression guard: commit 159d491 で backfill 定義はあったが open_db
        wire 抜けで prod 全 row NULL のまま inning publisher silent skip した
        bug の再発防止。
        """
        import tempfile
        tmpdir = Path(tempfile.mkdtemp())
        try:
            # 1) open_db で schema migration、 row なし
            conn = self._open_db(tmpdir)
            self._seed_game_with_pitchers(
                conn,
                game_id="g-404-3",
                team_role="home",
                pitchers=[(1, "戸郷翔征", 6.0), (2, "大勢", 1.0)],
            )
            # 2) start_inning / end_inning を明示 NULL に戻し、 conn close
            conn.execute(
                "UPDATE pitching_logs SET start_inning = NULL, end_inning = NULL "
                "WHERE game_id = 'g-404-3'"
            )
            conn.commit()
            conn.close()
            # 3) 再 open_db で auto backfill 走るか
            conn2 = self._open_db(tmpdir)
            rows = [tuple(r) for r in conn2.execute(
                "SELECT player_display, start_inning, end_inning "
                "FROM pitching_logs WHERE game_id='g-404-3' "
                "ORDER BY appearance_order"
            ).fetchall()]
            self.assertEqual(rows, [
                ("戸郷翔征", 1, 6),
                ("大勢", 7, 7),
            ])
            conn2.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_backfill_idempotent(self):
        """既に start/end set 済 row は backfill で touch されない (idempotent)."""
        import tempfile
        tmpdir = Path(tempfile.mkdtemp())
        try:
            conn = self._open_db(tmpdir)
            self._seed_game_with_pitchers(
                conn,
                game_id="g-404-2",
                team_role="home",
                pitchers=[(1, "戸郷翔征", 6.0)],
            )
            # 1 回目 backfill
            first = insight_etl.backfill_pitcher_innings(conn)
            # 2 回目 (既 set なので skip 期待、 affected rows=0)
            second = insight_etl.backfill_pitcher_innings(conn)
            self.assertGreaterEqual(first, 1)
            self.assertEqual(second, 0)
            conn.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
