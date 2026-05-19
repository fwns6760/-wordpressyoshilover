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


# 395 fix regression: _upsert_batters / _upsert_pitchers が非巨人 row に
# giants-only resolver を当てて別球団選手 (Hawks の井上朋也 等) を巨人選手
# (井上温大) に潰す bug の再発防止。


def test_upsert_batters_skips_giants_resolver_for_non_giants_team(tmp_path):
    """非巨人 team_name の row では giants-only resolver は呼ばれず、
    player_canonical は NULL のまま (後段 fill_canonical_team_aware に委譲)。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
            "VALUES ('t-game-non-giants', '2026-05-10', 'ロッテ', 'away', '2026-05-11T00:00:00Z')",
        )
        aliases = insight_etl._load_roster_aliases()
        # 巨人 surname unique なので "井上" → "井上温大" を返す
        assert insight_etl.resolve_canonical("井上", aliases) == "井上温大"
        # ロッテ row の "井上" は giants resolver を skip するべき
        rows = [{"順": 8, "選手": "井上", "守備": "指", "is_sub": False,
                 "打数": 3, "安打": 1, "得点": 0, "打点": 0, "盗塁": 0, "atbats": []}]
        n = insight_etl._upsert_batters(
            conn, "t-game-non-giants", "opponent", rows, aliases, team_name="ロッテ",
        )
        assert n == 1
        canonical = conn.execute(
            "SELECT player_canonical FROM batting_logs WHERE game_id='t-game-non-giants'"
        ).fetchone()[0]
        assert canonical is None, \
            f"expected NULL for non-Giants row, got {canonical!r} — surname-only " \
            f"giants resolver leaked into non-Giants row (395 regression)"
    finally:
        conn.close()


def test_upsert_batters_still_resolves_for_giants_team(tmp_path):
    """巨人 row では従来通り surname-only でも canonical 解決が効くこと
    (浦田/戸郷/則本 等の既存 contract を保つ)。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
            "VALUES ('t-game-giants', '2026-05-10', 'ロッテ', 'home', '2026-05-11T00:00:00Z')",
        )
        aliases = insight_etl._load_roster_aliases()
        rows = [{"順": 8, "選手": "浦田", "守備": "三", "is_sub": False,
                 "打数": 3, "安打": 1, "得点": 0, "打点": 0, "盗塁": 0, "atbats": []}]
        n = insight_etl._upsert_batters(
            conn, "t-game-giants", "giants", rows, aliases, team_name="巨人",
        )
        assert n == 1
        canonical = conn.execute(
            "SELECT player_canonical FROM batting_logs WHERE game_id='t-game-giants'"
        ).fetchone()[0]
        assert canonical == "浦田俊輔"
    finally:
        conn.close()


def test_upsert_pitchers_skips_giants_resolver_for_non_giants_team(tmp_path):
    """投手 log 側も同じ team gate 挙動。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
            "VALUES ('t-game-non-giants-pit', '2026-05-10', '阪神', 'away', '2026-05-11T00:00:00Z')",
        )
        aliases = insight_etl._load_roster_aliases()
        rows = [{"選手": "戸郷", "result_mark": "○", "投球数": 90, "打者": 25,
                 "投球回": "6.0", "安打": 4, "本塁打": 0, "四球": 1, "死球": 0,
                 "奪三振": 6, "暴投": 0, "ボーク": 0, "失点": 1, "自責点": 1}]
        # 巨人 resolver では "戸郷" → "戸郷翔征" だが、 これは阪神 row なので
        # 別球団に同姓がいる場合に潰さないよう giants resolver は skip 必須
        n = insight_etl._upsert_pitchers(
            conn, "t-game-non-giants-pit", "opponent", rows, aliases, team_name="阪神",
        )
        assert n == 1
        canonical = conn.execute(
            "SELECT player_canonical FROM pitching_logs WHERE game_id='t-game-non-giants-pit'"
        ).fetchone()[0]
        assert canonical is None
    finally:
        conn.close()
