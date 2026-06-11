"""Tests for src/interleague_scraper.py (NPB公式 交流戦成績表 parser)。

fixture は npb.jp/bis/2026/stats/std_c.html / std_p.html の 2026-06-11 取得スナップショット。
"""

from __future__ import annotations

import os

from src.interleague_scraper import (
    merge_standings,
    parse_interleague_table,
    parse_wdl,
)

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name: str) -> str:
    with open(os.path.join(_FIX, name), encoding="utf-8") as fh:
        return fh.read()


def test_parse_wdl_variants() -> None:
    assert parse_wdl("5-2(2)") == [5, 2, 2]
    assert parse_wdl("4-1") == [4, 1, 0]
    assert parse_wdl("--") is None
    assert parse_wdl("***") is None
    assert parse_wdl("") is None


def test_parse_cl_interleague_table() -> None:
    rows = parse_interleague_table(_read("npb_std_c_2026_interleague.html"))
    assert len(rows) == 6
    giants = next(r for r in rows if r["team"] == "巨人")
    # 2026-06-11 時点: 14試合 9勝3敗2分 .750
    assert (giants["g"], giants["w"], giants["l"], giants["t"]) == (14, 9, 3, 2)
    assert giants["pct"] == ".750"
    assert giants["home"] == [5, 2, 2]
    assert giants["road"] == [4, 1, 0]
    # 対西武のみ未対戦 (None)、他5球団は対戦済み
    assert giants["vs"]["l"] is None
    assert giants["vs"]["b"] == [3, 0, 0]
    assert giants["vs"]["m"] == [1, 0, 2]
    # 順位表 (1つ目の table、「差」あり) を誤って拾っていないこと
    assert all(r["g"] <= 18 for r in rows)


def test_parse_pa_interleague_table() -> None:
    rows = parse_interleague_table(_read("npb_std_p_2026_interleague.html"))
    assert len(rows) == 6
    teams = {r["team"] for r in rows}
    assert teams == {"日本ハム", "楽天", "西武", "ロッテ", "オリックス", "ソフトバンク"}


def test_merge_standings_ranks_12_teams() -> None:
    cl = parse_interleague_table(_read("npb_std_c_2026_interleague.html"))
    pa = parse_interleague_table(_read("npb_std_p_2026_interleague.html"))
    merged = merge_standings(cl, pa)
    assert len(merged) == 12
    assert [r["league"] for r in merged].count("セ") == 6
    # 勝率降順 + 順位は1始まり
    pcts = [float(r["pct"]) for r in merged]
    assert pcts == sorted(pcts, reverse=True)
    assert merged[0]["rank"] == 1
    giants = next(r for r in merged if r["team"] == "巨人")
    assert 1 <= giants["rank"] <= 12
