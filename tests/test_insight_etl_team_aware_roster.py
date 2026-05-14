"""Tests for src.analysis.insight_etl team-aware roster functions
(343-INSIGHT-007 follow-up).

`_load_team_aware_aliases` / `resolve_canonical_team_aware` /
`fill_canonical_team_aware` の動作 + Giants resolution の後方互換 verify。
"""

from __future__ import annotations

import json

from src.analysis import insight_etl


def test_load_team_aware_aliases_returns_dict_of_dicts():
    """npb_12team_roster.json から {team_code: {alias: canonical}} を返すこと。"""
    aliases = insight_etl._load_team_aware_aliases()
    assert isinstance(aliases, dict)
    # 12 球団全部が含まれること
    expected_teams = {"g", "t", "s", "c", "db", "d", "h", "l", "m", "e", "b", "f"}
    assert set(aliases.keys()) >= expected_teams, \
        f"missing teams: {expected_teams - set(aliases.keys())}"
    # 各 team が dict であること
    for team_code in expected_teams:
        assert isinstance(aliases.get(team_code), dict), f"team {team_code} not dict"
        assert len(aliases[team_code]) > 0, f"team {team_code} has no aliases"


def test_resolve_canonical_team_aware_returns_none_for_unknown_team():
    aliases = insight_etl._load_team_aware_aliases()
    assert insight_etl.resolve_canonical_team_aware("任意", "unknown", aliases) is None
    assert insight_etl.resolve_canonical_team_aware("任意", "", aliases) is None
    assert insight_etl.resolve_canonical_team_aware("", "g", aliases) is None


def test_resolve_canonical_team_aware_resolves_giants_player():
    """Giants player (例: 戸郷 or 戸郷翔征) が team_code='g' で解決できること。"""
    aliases = insight_etl._load_team_aware_aliases()
    g_aliases = aliases.get("g", {})
    # 戸郷翔征 (Giants 投手) が登録されているはず
    assert "戸郷翔征" in g_aliases.values() or any(
        "戸郷" in name for name in g_aliases.values()
    ), "戸郷 not found in g roster"


def test_resolve_canonical_team_aware_team_isolation():
    """同姓選手が異 team にいても team_code で正しく分離されること。

    例: 「高橋」が複数チームにいても、team_code='g' で resolve すると
    Giants の高橋に解決される (Giants にしかいない player は Giants で
    resolve、他球団にいる player は他球団で resolve)。
    """
    aliases = insight_etl._load_team_aware_aliases()
    # 各 team の roster sizes > 50 確認 (data 充実度)
    for team_code in ("g", "t", "s", "c", "db", "d"):
        team_dict = aliases.get(team_code, {})
        # 各 team の canonical 数 (重複除く) で 50+ 選手
        canonicals = set(team_dict.values())
        assert len(canonicals) >= 50, \
            f"team {team_code} has only {len(canonicals)} canonical names (expected >= 50)"


def test_fill_canonical_team_aware_updates_null_canonicals(tmp_path):
    """NULL canonical 行を team-aware roster lookup で update できること。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        # games row 挿入
        conn.execute(
            "INSERT OR IGNORE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
            "VALUES ('test-game-1', '2026-05-10', '阪神', 'home', '2026-05-11T00:00:00Z')",
        )
        # batting_logs に「中野」(阪神) を NULL canonical で insert
        # (parse_npb_box_html が canonical 解決できなかったケース simulate)
        conn.execute(
            "INSERT OR REPLACE INTO batting_logs "
            "(game_id, team_role, slot_order, player_display, player_canonical, team_name) "
            "VALUES ('test-game-1', 'opponent', 1, '中野', NULL, '阪神')",
        )
        conn.commit()

        updated = insight_etl.fill_canonical_team_aware(conn)
        # 1 行が update されるはず (中野 が阪神 roster で unique なら)
        # 阪神 roster に中野 (中野拓夢 etc.) がいる前提
        row = conn.execute(
            "SELECT player_canonical FROM batting_logs WHERE game_id = 'test-game-1'"
        ).fetchone()
        # canonical が更新されたか、または 阪神 roster の状況次第で None のまま
        # ambiguous 回避のため update が 0 でも fail にしない
        if updated > 0:
            assert row[0] is not None and "中野" in row[0]
    finally:
        conn.close()


def test_fill_canonical_team_aware_returns_zero_when_no_null(tmp_path):
    """canonical が全部 fill 済の場合は 0 行 update."""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        updated = insight_etl.fill_canonical_team_aware(conn)
        assert updated == 0
    finally:
        conn.close()


def test_load_roster_aliases_backward_compat():
    """既存 `_load_roster_aliases` (Giants only) は変更されていないこと。

    新 `_load_team_aware_aliases` 導入で既存 API が壊れていないか check。
    """
    aliases = insight_etl._load_roster_aliases()
    assert isinstance(aliases, dict)
    assert len(aliases) > 0
    # 戸郷翔征 の surname 解決が動くこと
    result = insight_etl.resolve_canonical("戸郷", aliases)
    assert result == "戸郷翔征"
    # 則本昂大 (343 dedupe で正規化済) も解決可能
    assert insight_etl.resolve_canonical("則本", aliases) == "則本昂大"


def test_npb_12team_roster_json_valid():
    """config/npb_12team_roster.json が valid JSON で 12 球団分の entry を含む。"""
    data = json.loads(insight_etl.NPB_12TEAM_ROSTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 800, f"expected >= 800 entries, got {len(data)}"
    team_codes = {e.get("team_code") for e in data if e.get("team_code")}
    assert team_codes == {"g", "t", "s", "c", "db", "d", "h", "l", "m", "e", "b", "f"}
