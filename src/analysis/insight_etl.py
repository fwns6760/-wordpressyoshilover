"""INSIGHT-001 — fixture HTML → SQLite ETL + article_candidates.csv prototype.

This module is the smallest viable proof-of-concept for the
data-analysis article-candidate pipeline. It:

* Loads an NPB box-score HTML page (fixture file path; **does not** fetch
  any live URL) via the existing :func:`src.source_npb_postgame_extractor
  .parse_npb_box_html`.
* Upserts the parsed game, inning scores, batting logs, and pitching
  logs into ``data/insight/insight.db`` (SQLite, see
  ``data/insight/schema.sql``).
* Resolves player display names against ``config/giants_roster.json``
  where possible (last-name-only entries are kept as ``player_display``
  with a ``NULL`` canonical until a future enrichment pass).
* Emits a handful of **single-game** detector signals as
  ``article_candidates`` rows and exports them to
  ``data/insight/article_candidates.csv``.

The single-game detectors here are deliberately rudimentary — multi-game
trend detection (z-score, streaks, splits) is a follow-up phase once the
DB has ≥2 weeks of history. The point is to prove the data shape and the
end-to-end pipeline with the existing free fixture.

Hard constraints (per doc/active/INSIGHT-001-data-analysis-pipeline.md):
  * No live URL fetch.
  * No WordPress REST call.
  * No Gemini / X API call.
  * No write to existing logs/*.jsonl.
  * No env / Scheduler / deploy side effects.
  * SQLite + CSV file output only.

CLI::

    python3 -m src.analysis.insight_etl \\
        --fixture tests/fixtures/npb_score_2026_0510_d-g-08_box.html \\
        --game-id 2026-05-10:d-g-08 \\
        --game-date 2026-05-10
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_npb_postgame_extractor import parse_npb_box_html  # noqa: E402
from src.analysis import insight_advanced_metrics, insight_atbats_parser  # noqa: E402

DEFAULT_DB_PATH = ROOT / "data" / "insight" / "insight.db"
DEFAULT_SCHEMA = ROOT / "data" / "insight" / "schema.sql"
DEFAULT_CSV = ROOT / "data" / "insight" / "article_candidates.csv"
ROSTER_PATH = ROOT / "config" / "giants_roster.json"
NPB_12TEAM_ROSTER_PATH = ROOT / "config" / "npb_12team_roster.json"

CSV_COLUMNS = (
    "candidate_id",
    "run_ts",
    "game_id",
    "player_canonical",
    "player_display",
    "signal_type",
    "magnitude",
    "baseline_value",
    "current_value",
    "window_label",
    "comparison_target",
    "evidence_json",
    "priority",
    "status",
    "created_at",
    "notes",
)


# ─── roster lookup ──────────────────────────────────────────────────────────


def _load_roster_aliases() -> dict[str, str]:
    """Return ``{alias_or_name: canonical_name}`` from giants_roster.json.

    The roster file is a list of dicts with ``name`` (canonical) and
    ``aliases`` (list including the canonical itself). Surname-only
    keys (e.g. ``"吉川"``) are added when they uniquely identify a
    single active player; ambiguous surnames fall through unresolved.
    """
    if not ROSTER_PATH.exists():
        return {}
    try:
        roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    surname_buckets: dict[str, list[str]] = {}
    for row in roster:
        canon = (row.get("name") or "").strip()
        if not canon:
            continue
        out[canon] = canon
        for alias in row.get("aliases") or []:
            a = (alias or "").strip()
            if a:
                out.setdefault(a, canon)
        if row.get("active") and len(canon) >= 2:
            surname_buckets.setdefault(canon[:2], []).append(canon)
    for surname, cands in surname_buckets.items():
        if len(cands) == 1:
            out.setdefault(surname, cands[0])
    return out


def resolve_canonical(display: str, aliases: dict[str, str]) -> str | None:
    if not display:
        return None
    raw = display.strip()
    return aliases.get(raw)


# ─── parsers / helpers ──────────────────────────────────────────────────────


_IP_RE = re.compile(r"^\s*(\d+)(?:\.(\d))?\s*$")


def parse_ip(value: str | None) -> float | None:
    """投球回 "5.1" → 5.333, "5.2" → 5.667. Returns None on parse failure."""
    if value is None:
        return None
    m = _IP_RE.match(str(value))
    if not m:
        return None
    whole = int(m.group(1))
    third = int(m.group(2) or 0)
    if third > 2:
        return None
    return round(whole + third / 3.0, 3)


def _int_or_none(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def derive_result(giants_score: int | None, opp_score: int | None) -> str:
    if giants_score is None or opp_score is None:
        return "unknown"
    if giants_score > opp_score:
        return "win"
    if giants_score < opp_score:
        return "loss"
    return "draw"


# ─── DB helpers ─────────────────────────────────────────────────────────────


_TEAM_NAME_TO_CODE_INTERNAL = {
    "巨人": "g", "読売": "g", "ジャイアンツ": "g",
    "阪神": "t", "タイガース": "t",
    "ヤクルト": "s", "スワローズ": "s",
    "広島": "c", "カープ": "c",
    "DeNA": "db", "横浜": "db", "ベイスターズ": "db",
    "中日": "d", "ドラゴンズ": "d",
    "ソフトバンク": "h", "ホークス": "h",
    "西武": "l", "ライオンズ": "l",
    "ロッテ": "m", "マリーンズ": "m",
    "楽天": "e", "イーグルス": "e",
    "オリックス": "b", "バファローズ": "b",
    "日本ハム": "f", "ファイターズ": "f",
}


def _resolve_team_code_from_name(name: str) -> str:
    """team display 名から team_code を resolve。マッチしなければ 'unknown'。"""
    if not name:
        return "unknown"
    for token, code in _TEAM_NAME_TO_CODE_INTERNAL.items():
        if token in name:
            return code
    return "unknown"


def _ensure_team_name_columns(conn: sqlite3.Connection) -> None:
    """INSIGHT-007: batting_logs / pitching_logs / lineups / fielding_logs に
    ``team_name`` 列を additive に追加 (NULL 許容)。既存 row には影響なし、
    既に存在すれば no-op。``ALTER TABLE`` は CREATE TABLE IF NOT EXISTS と
    違って冪等でないので column 存在確認を経由する。"""
    targets = ("batting_logs", "pitching_logs", "lineups", "fielding_logs")
    for table in targets:
        try:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.OperationalError:
            continue
        if "team_name" not in cols:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN team_name TEXT")
            except sqlite3.OperationalError:
                pass


# ─── 343-INSIGHT-007 backfill: teams / players / advanced_metric_snapshots ──
#
# 342-INSIGHT Phase 1 spec で発見した data 不足
# (production DB で teams=0 / players=0 / advanced_metric_snapshots=0)
# を埋めるための backfill 関数群。defense_proxy.rebuild_defense_for_game と
# 同 pattern で run_nightly() から best-effort 呼び出しされる想定。

# 12 球団 fixed roster (NPB 2026 season)
_TEAMS_FIXED_ROSTER: tuple[tuple[str, str, str, str], ...] = (
    ("g", "巨人", "central", "東京ドーム"),
    ("t", "阪神", "central", "甲子園"),
    ("s", "ヤクルト", "central", "明治神宮"),
    ("c", "広島", "central", "マツダスタジアム"),
    ("db", "DeNA", "central", "横浜スタジアム"),
    ("d", "中日", "central", "バンテリンドーム"),
    ("h", "ソフトバンク", "pacific", "PayPayドーム"),
    ("l", "西武", "pacific", "ベルーナドーム"),
    ("m", "ロッテ", "pacific", "ZOZOマリン"),
    ("e", "楽天", "pacific", "楽天モバイル"),
    ("b", "オリックス", "pacific", "京セラドーム大阪"),
    ("f", "日本ハム", "pacific", "エスコンフィールドHOKKAIDO"),
)


def seed_teams(conn: sqlite3.Connection) -> int:
    """12 球団 fixed roster を ``teams`` table に idempotent insert。

    既存 row は ``INSERT OR IGNORE`` で無視。初回 = 12 行 insert、2 回目以降
    = 0 行 insert。
    """
    inserted = 0
    for code, name, league, park in _TEAMS_FIXED_ROSTER:
        cur = conn.execute(
            "INSERT OR IGNORE INTO teams (team_code, team_name, league, home_park) "
            "VALUES (?, ?, ?, ?)",
            (code, name, league, park),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def seed_players_from_logs(conn: sqlite3.Connection) -> int:
    """既存 ``batting_logs`` / ``pitching_logs`` から
    ``(player_canonical, team_name)`` を SELECT DISTINCT して
    ``players`` table に induce + INSERT OR IGNORE。

    role 推定: ``pitching_logs`` のみに出現 = ``pitcher``、
    ``batting_logs`` に出現 = ``player`` (両方なら ``player``)。
    team_name → team_code は ``_resolve_team_code_from_name`` を reuse、
    ``unknown`` は skip。
    """
    batter_rows = list(conn.execute(
        "SELECT DISTINCT player_canonical, team_name FROM batting_logs "
        "WHERE player_canonical IS NOT NULL AND player_canonical != '' "
        "AND team_name IS NOT NULL AND team_name != ''"
    ))
    pitcher_rows = list(conn.execute(
        "SELECT DISTINCT player_canonical, team_name FROM pitching_logs "
        "WHERE player_canonical IS NOT NULL AND player_canonical != '' "
        "AND team_name IS NOT NULL AND team_name != ''"
    ))

    canonical_to_team_role: dict[str, tuple[str, str]] = {}
    for row in pitcher_rows:
        canonical = str(row[0])
        team_name = str(row[1])
        canonical_to_team_role[canonical] = (team_name, "pitcher")
    for row in batter_rows:
        canonical = str(row[0])
        team_name = str(row[1])
        # batter があれば pitcher を上書きして 'player' にする
        canonical_to_team_role[canonical] = (team_name, "player")

    inserted = 0
    for canonical, (team_name, role) in canonical_to_team_role.items():
        team_code = _resolve_team_code_from_name(team_name)
        if team_code == "unknown":
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO players "
            "(player_canonical, team_code, role, active) "
            "VALUES (?, ?, ?, 1)",
            (canonical, team_code, role),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def _scope_window(scope: str, snapshot_date: str) -> tuple[str, str]:
    """``scope`` と ``snapshot_date`` から ``(window_start, window_end)`` ISO date を返す。

    ``last_5_games`` / ``last_10_games`` は per-player なので別 path で扱う
    (本 helper は range scope のみ)。 348 step 3 で monthly / weekly 追加。
    """
    end = snapshot_date
    if scope == "season":
        year = snapshot_date[:4]
        return (f"{year}-01-01", end)
    if scope == "last_7d":
        d = dt.date.fromisoformat(snapshot_date)
        return ((d - dt.timedelta(days=6)).isoformat(), end)
    if scope == "last_30d":
        d = dt.date.fromisoformat(snapshot_date)
        return ((d - dt.timedelta(days=29)).isoformat(), end)
    if scope == "monthly":
        # 348 step 3: 当月 1 日から snapshot_date まで
        d = dt.date.fromisoformat(snapshot_date)
        return (d.replace(day=1).isoformat(), end)
    if scope == "weekly":
        # 348 step 3: ISO 週の月曜から snapshot_date まで
        d = dt.date.fromisoformat(snapshot_date)
        monday = d - dt.timedelta(days=d.weekday())
        return (monday.isoformat(), end)
    raise ValueError(f"unknown range scope: {scope!r}")


def _player_last_n_game_window(
    conn: sqlite3.Connection,
    player_canonical: str,
    n_games: int,
    snapshot_date: str,
    table: str = "batting_logs",
) -> Optional[tuple[str, str]]:
    """player の直近 n_games の (oldest_date, latest_date) を返す。

    試合数が n_games に満たない場合は None (集計 skip)。 348 step 3 で
    last_5_games / last_10_games の per-player rolling window 用 helper。
    """
    if table not in ("batting_logs", "pitching_logs", "fielding_logs"):
        raise ValueError(f"unsupported table: {table!r}")
    rows = conn.execute(
        f"SELECT g.game_date FROM games g "
        f"JOIN {table} bl ON bl.game_id = g.game_id "
        f"WHERE bl.player_canonical = ? AND g.game_date <= ? "
        f"GROUP BY g.game_id "
        f"ORDER BY g.game_date DESC LIMIT ?",
        (player_canonical, snapshot_date, n_games),
    ).fetchall()
    if len(rows) < n_games:
        return None
    return (rows[-1][0], rows[0][0])


def _aggregate_batting_line(
    conn: sqlite3.Connection,
    player_canonical: str,
    window_start: str,
    window_end: str,
) -> insight_advanced_metrics.BattingLine:
    """``batting_logs`` + ``atbats_json`` から指定 player の ``BattingLine`` を集計。

    ``atbats_json`` を ``insight_atbats_parser.parse_atbat`` で各 PA 解析し、
    H1/H2/H3/HR/BB/HBP/SF/SH/SO を導出。AB/H は schema 既存列をそのまま合算。
    """
    rows = conn.execute(
        "SELECT bl.AB, bl.H, bl.atbats_json FROM batting_logs bl "
        "JOIN games g ON bl.game_id = g.game_id "
        "WHERE bl.player_canonical = ? "
        "AND g.game_date >= ? AND g.game_date <= ?",
        (player_canonical, window_start, window_end),
    ).fetchall()

    line = insight_advanced_metrics.BattingLine()
    for row in rows:
        line.AB += int(row[0] or 0)
        line.H += int(row[1] or 0)
        atbats_json = row[2] or "[]"
        try:
            atbats = json.loads(atbats_json) if isinstance(atbats_json, str) else (atbats_json or [])
        except (ValueError, TypeError):
            atbats = []
        if not isinstance(atbats, list):
            atbats = []
        for ab_text in atbats:
            if not isinstance(ab_text, str) or not ab_text.strip() or ab_text.strip() == "-":
                continue
            try:
                parsed = insight_atbats_parser.parse_atbat(ab_text)
            except Exception:  # noqa: BLE001 - parser failure must not block aggregation
                continue
            if parsed.get("is_hr"):
                line.HR += 1
            elif parsed.get("result_class") == "hit":
                bases = int(parsed.get("bases") or 0)
                if bases == 1:
                    line.H1 += 1
                elif bases == 2:
                    line.H2 += 1
                elif bases == 3:
                    line.H3 += 1
            if parsed.get("is_walk") or parsed.get("result_class") == "walk":
                line.BB += 1
            if parsed.get("result_class") == "hbp":
                line.HBP += 1
            if parsed.get("result_class") == "sf":
                line.SF += 1
            if parsed.get("result_class") == "sac":
                line.SH += 1
            if parsed.get("is_strikeout"):
                line.SO += 1
    return line.coerce()


def _aggregate_pitching_line(
    conn: sqlite3.Connection,
    player_canonical: str,
    window_start: str,
    window_end: str,
) -> insight_advanced_metrics.PitchingLine:
    """``pitching_logs`` から指定 player の ``PitchingLine`` を集計。

    schema column → ``PitchingLine`` 名対応:
      H_allowed → H, HR_allowed → HR, K → SO, IP/BB/HBP/ER/R/BF はそのまま。
    ``result_mark`` から W (勝) / L (敗) を count (348 step 2 で勝率計算用)。
    ``IP`` は SQLite 上 REAL なので合算可能 (5.1 → 5.333 形式)。
    """
    rows = conn.execute(
        "SELECT pl.IP, pl.H_allowed, pl.HR_allowed, pl.BB, pl.HBP, pl.K, "
        "pl.R, pl.ER, pl.BF, pl.result_mark "
        "FROM pitching_logs pl "
        "JOIN games g ON pl.game_id = g.game_id "
        "WHERE pl.player_canonical = ? "
        "AND g.game_date >= ? AND g.game_date <= ?",
        (player_canonical, window_start, window_end),
    ).fetchall()

    line = insight_advanced_metrics.PitchingLine()
    for row in rows:
        line.IP += float(row[0] or 0.0)
        line.H += int(row[1] or 0)
        line.HR += int(row[2] or 0)
        line.BB += int(row[3] or 0)
        line.HBP += int(row[4] or 0)
        line.SO += int(row[5] or 0)
        line.R += int(row[6] or 0)
        line.ER += int(row[7] or 0)
        line.BF += int(row[8] or 0)
        mark = (row[9] or "").strip()
        if mark == "勝":
            line.W += 1
        elif mark == "敗":
            line.L += 1
    return line


def _aggregate_fielding_line(
    conn: sqlite3.Connection,
    player_canonical: str,
    window_start: str,
    window_end: str,
) -> insight_advanced_metrics.FieldingLine:
    """``fielding_logs`` から指定 player の ``FieldingLine`` を集計。

    NPB 公式 box に守備 stat が無い場合 fielding_logs は空、 全 0 が返る
    (守備率は None で skip される)。 348 step 2。
    """
    rows = conn.execute(
        "SELECT fl.PO, fl.A, fl.E, fl.DP, fl.innings "
        "FROM fielding_logs fl "
        "JOIN games g ON fl.game_id = g.game_id "
        "WHERE fl.player_canonical = ? "
        "AND g.game_date >= ? AND g.game_date <= ?",
        (player_canonical, window_start, window_end),
    ).fetchall()

    line = insight_advanced_metrics.FieldingLine()
    for row in rows:
        line.PO += int(row[0] or 0)
        line.A += int(row[1] or 0)
        line.E += int(row[2] or 0)
        line.DP += int(row[3] or 0)
        line.innings += float(row[4] or 0.0)
    return line


# 「lower-is-better」な投手指標 (rank 計算で reverse しない)
# key は insight_advanced_metrics.all_pitcher_metrics() の返す dict key と一致させる
_PITCHER_LOWER_IS_BETTER: frozenset[str] = frozenset({
    "ERA", "WHIP", "FIP", "xFIP", "BB_per_9", "HR_per_9",
})

# 「higher-is-better」な投手指標 (打者 metric は全部 higher-is-better と扱う)
_PITCHER_HIGHER_IS_BETTER: frozenset[str] = frozenset({
    "K_per_9", "K_BB",
})


# ─── 343-INSIGHT-007 follow-up: 12 team team-aware roster resolution ────────
#
# giants_roster.json 単独では他 11 球団 player の canonical 解決が不能で、
# パリーグ + セ・リーグ他 5 球団の player が advanced_metric_snapshots に
# 入らない問題を解消する。npb_12team_roster.json (NPB 公式 roster scrape 由来)
# を team-aware lookup の data source として使う。


def _load_team_aware_aliases() -> dict[str, dict[str, str]]:
    """Return ``{team_code: {alias_or_name: canonical}}`` from npb_12team_roster.json.

    各 team 内で surname unique なら surname も alias dict に追加。
    同 team 内で複数選手の surname が一致する場合は surname を除外
    (ambiguous な解決を避ける)。
    """
    if not NPB_12TEAM_ROSTER_PATH.exists():
        return {}
    try:
        roster = json.loads(NPB_12TEAM_ROSTER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    by_team: dict[str, dict[str, str]] = {}
    surname_buckets: dict[str, dict[str, list[str]]] = {}
    for row in roster:
        team_code = (row.get("team_code") or "").strip()
        canon = (row.get("name") or "").strip()
        if not team_code or not canon:
            continue
        team_dict = by_team.setdefault(team_code, {})
        team_dict[canon] = canon
        for alias in row.get("aliases") or []:
            a = (alias or "").strip()
            if a:
                team_dict.setdefault(a, canon)
        if row.get("active") and len(canon) >= 2:
            surname_buckets.setdefault(team_code, {}).setdefault(canon[:2], []).append(canon)
    for team_code, buckets in surname_buckets.items():
        team_dict = by_team[team_code]
        for surname, cands in buckets.items():
            if len(cands) == 1:
                team_dict.setdefault(surname, cands[0])
    return by_team


def resolve_canonical_team_aware(
    display: str,
    team_code: str,
    team_aliases: dict[str, dict[str, str]],
) -> str | None:
    """team_code 内で display を canonical 名に解決。見つからなければ None。"""
    if not display or not team_code:
        return None
    team_dict = team_aliases.get(team_code)
    if not team_dict:
        return None
    return team_dict.get(display.strip())


def fill_canonical_team_aware(conn: sqlite3.Connection) -> int:
    """既存 ``batting_logs`` / ``pitching_logs`` の ``player_canonical`` NULL 行を
    ``npb_12team_roster.json`` + ``team_name`` 解決で UPDATE。

    Giants 戦の opponent player や パ・リーグ player の canonical 解決を
    遡って fill する migration / backfill 用 helper。next nightly run でも
    新 game 由来の NULL 行を fill するため run_nightly() から呼ばれる。

    return: アップデートされた行数 (batting + pitching)。
    """
    team_aliases = _load_team_aware_aliases()
    if not team_aliases:
        return 0
    updated = 0
    for table in ("batting_logs", "pitching_logs"):
        rows = list(conn.execute(
            f"SELECT rowid, player_display, team_name FROM {table} "
            f"WHERE (player_canonical IS NULL OR player_canonical = '') "
            f"AND team_name IS NOT NULL AND team_name != '' "
            f"AND player_display IS NOT NULL AND player_display != ''"
        ))
        for rowid, display, team_name in rows:
            team_code = _resolve_team_code_from_name(team_name or "")
            if team_code == "unknown":
                continue
            canon = resolve_canonical_team_aware(display, team_code, team_aliases)
            if canon:
                conn.execute(
                    f"UPDATE {table} SET player_canonical = ? WHERE rowid = ?",
                    (canon, rowid),
                )
                updated += 1
    conn.commit()
    return updated


_CENTRAL_LEAGUE_TEAM_NAMES_FOR_QUALIFIED: tuple[str, ...] = (
    "巨人", "阪神", "ヤクルト", "広島", "DeNA", "中日",
)
# 空 DB / セ・リーグ試合 0 件時の fallback。 16 試合は qualified_pa ≈ 50 /
# qualified_ip = 16.0 を生み、 legacy 固定値 (min_pa=50, min_ip=15) を
# 概ね再現する保守的下限。
_QUALIFIED_FALLBACK_TEAM_GAMES = 16


def team_games_for_qualified_thresholds(conn: sqlite3.Connection) -> int:
    """セ・リーグ各球団の試合数の max を返す (= リーグ最進行球団基準)。

    NPB 公式 ranking はリーグ最進行球団の試合数を基準に **規定打席
    (試合数 × 3.1)** / **規定投球回 (試合数 × 1.0)** を判定する慣行。
    本 helper は season scope の動的閾値の根拠を返す。

    issue #44 #1: 則本 IP=30 / 竹丸 IP=34 が IP>=15 固定閾値で snapshot
    に入り「セ・リーグ N/M 位」と表示されていた水増しの修正。

    パ・リーグ球団は除外。 空 DB (テスト等) は安全側 fallback
    (``_QUALIFIED_FALLBACK_TEAM_GAMES``) を返す。
    """
    placeholders = ",".join(["?"] * len(_CENTRAL_LEAGUE_TEAM_NAMES_FOR_QUALIFIED))
    rows = conn.execute(
        f"SELECT COUNT(DISTINCT game_id) FROM batting_logs "
        f"WHERE team_name IN ({placeholders}) "
        f"GROUP BY team_name",
        _CENTRAL_LEAGUE_TEAM_NAMES_FOR_QUALIFIED,
    ).fetchall()
    if not rows:
        return _QUALIFIED_FALLBACK_TEAM_GAMES
    return int(max(r[0] for r in rows))


def compute_advanced_metric_snapshots(
    conn: sqlite3.Connection,
    *,
    scope: str,
    snapshot_date: str,
    min_pa: int = 30,
    min_ip: float = 10.0,
) -> int:
    """指定 ``scope`` で全 active player の advanced metrics を計算し、
    ``advanced_metric_snapshots`` に ``INSERT OR REPLACE``。

    対応 scope (348 step 3 で拡張):
      * range scope: ``season`` / ``last_7d`` / ``last_30d`` / ``monthly`` / ``weekly``
      * per-player rolling: ``last_5_games`` / ``last_10_games``

    最小 sample 閾値 (打者: ``PA >= min_pa`` / 投手: ``IP >= min_ip``) で skip。
    league_rank / league_total は同 scope 内 metric 別に sort して付与。
    position_rank / position_total / extra_json は本 phase で NULL。
    """
    _ROLLING_N = {"last_5_games": 5, "last_10_games": 10}
    is_rolling = scope in _ROLLING_N
    if is_rolling:
        n_games = _ROLLING_N[scope]
        window_start = window_end = None
    else:
        # range scope (raise if unknown)
        window_start, window_end = _scope_window(scope, snapshot_date)

    # advanced_metric_snapshots schema は snapshot_id AUTOINCREMENT のみで
    # (snapshot_date, scope, player_canonical, metric_name) に UNIQUE 制約がない。
    # よって INSERT OR REPLACE では dedupe されない。同 (snapshot_date, scope) の
    # 既存 row を先に DELETE してから insert することで idempotent を確保する。
    conn.execute(
        "DELETE FROM advanced_metric_snapshots WHERE snapshot_date = ? AND scope = ?",
        (snapshot_date, scope),
    )

    player_rows = list(conn.execute(
        "SELECT player_canonical, team_code FROM players "
        "WHERE active = 1 AND team_code IS NOT NULL AND team_code != 'unknown'"
    ))

    # {metric_name: {player_canonical: (value, sample_size, team_code)}}
    batter_metrics_by_name: dict[str, dict[str, tuple[float, int, str]]] = {}
    pitcher_metrics_by_name: dict[str, dict[str, tuple[float, int, str]]] = {}

    for player_row in player_rows:
        canonical = str(player_row[0])
        team_code = str(player_row[1] or "")
        if not canonical or not team_code:
            continue

        # 348 step 3: per-player rolling は player ごとに window を再計算
        if is_rolling:
            bat_window = _player_last_n_game_window(
                conn, canonical, n_games, snapshot_date, "batting_logs",
            )
            pit_window = _player_last_n_game_window(
                conn, canonical, n_games, snapshot_date, "pitching_logs",
            )
        else:
            bat_window = (window_start, window_end)
            pit_window = (window_start, window_end)

        # batting metrics (role に関係なく試行、PA 不足なら skip)
        if bat_window is not None:
            batting_line = _aggregate_batting_line(conn, canonical, bat_window[0], bat_window[1])
            if batting_line.PA >= min_pa:
                for metric_name, value in insight_advanced_metrics.all_batter_metrics(batting_line).items():
                    if value is None:
                        continue
                    batter_metrics_by_name.setdefault(metric_name, {})[canonical] = (
                        float(value), int(batting_line.PA), team_code,
                    )

        # pitching metrics (role に関係なく試行、IP 不足なら skip)
        if pit_window is not None:
            pitching_line = _aggregate_pitching_line(conn, canonical, pit_window[0], pit_window[1])
            if pitching_line.IP >= min_ip:
                for metric_name, value in insight_advanced_metrics.all_pitcher_metrics(pitching_line).items():
                    if value is None:
                        continue
                    pitcher_metrics_by_name.setdefault(metric_name, {})[canonical] = (
                        float(value), max(1, int(pitching_line.IP)), team_code,
                    )

    inserted = 0

    # batter metrics: 全部 higher-is-better
    for metric_name, player_map in batter_metrics_by_name.items():
        sorted_players = sorted(player_map.items(), key=lambda kv: kv[1][0], reverse=True)
        league_total = len(sorted_players)
        for rank, (canonical, (value, sample_size, team_code)) in enumerate(sorted_players, start=1):
            cur = conn.execute(
                "INSERT OR REPLACE INTO advanced_metric_snapshots "
                "(snapshot_date, scope, player_canonical, team_code, position, "
                "metric_name, metric_value, sample_size, league_rank, league_total, "
                "position_rank, position_total, extra_json) "
                "VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (snapshot_date, scope, canonical, team_code,
                 metric_name, value, sample_size, rank, league_total),
            )
            inserted += cur.rowcount

    # pitcher metrics: lower-is-better と higher-is-better を分岐
    for metric_name, player_map in pitcher_metrics_by_name.items():
        higher_is_better = metric_name in _PITCHER_HIGHER_IS_BETTER
        sorted_players = sorted(
            player_map.items(),
            key=lambda kv: kv[1][0],
            reverse=higher_is_better,
        )
        league_total = len(sorted_players)
        for rank, (canonical, (value, sample_size, team_code)) in enumerate(sorted_players, start=1):
            cur = conn.execute(
                "INSERT OR REPLACE INTO advanced_metric_snapshots "
                "(snapshot_date, scope, player_canonical, team_code, position, "
                "metric_name, metric_value, sample_size, league_rank, league_total, "
                "position_rank, position_total, extra_json) "
                "VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (snapshot_date, scope, canonical, team_code,
                 metric_name, value, sample_size, rank, league_total),
            )
            inserted += cur.rowcount

    conn.commit()
    return inserted


def open_db(db_path: Path = DEFAULT_DB_PATH, schema_path: Path = DEFAULT_SCHEMA) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if schema_path.exists():
        with schema_path.open(encoding="utf-8") as f:
            conn.executescript(f.read())
    _ensure_team_name_columns(conn)
    return conn


def upsert_game(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    game_date: str,
    parsed: dict,
    source_url: str | None,
    source_kind: str,
    ingested_at: str,
) -> None:
    inning_scores = parsed.get("inning_score") or []
    giants_total = next((row.get("total") for row in inning_scores if "巨人" in str(row.get("name") or "")), None)
    opp_total = next((row.get("total") for row in inning_scores if "巨人" not in str(row.get("name") or "")), None)
    opp_name = parsed.get("opponent_team_name") or ""
    win = parsed.get("winning_pitcher") or {}
    loss = parsed.get("losing_pitcher") or {}
    save = parsed.get("save_pitcher") or {}
    conn.execute(
        """
        INSERT OR REPLACE INTO games (
            game_id, game_date, opponent, home_away,
            giants_score, opp_score, result,
            league_label, one_line_summary,
            winning_pitcher, losing_pitcher, save_pitcher,
            source_url, source_kind, ingested_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            game_id,
            game_date,
            opp_name,
            "unknown",
            giants_total,
            opp_total,
            derive_result(giants_total, opp_total),
            None,
            None,
            win.get("name"),
            loss.get("name"),
            save.get("name") if save else None,
            source_url,
            source_kind,
            ingested_at,
        ),
    )
    # inning_scores
    for row in inning_scores:
        role = "giants" if "巨人" in str(row.get("name") or "") else "opponent"
        conn.execute(
            """
            INSERT OR REPLACE INTO inning_scores (game_id, team_role, inning_json, total)
            VALUES (?,?,?,?)
            """,
            (
                game_id,
                role,
                json.dumps(row.get("innings") or [], ensure_ascii=False),
                int(row.get("total") or 0),
            ),
        )


def _upsert_batters(
    conn: sqlite3.Connection,
    game_id: str,
    team_role: str,
    rows: Iterable[dict],
    aliases: dict[str, str],
    team_name: Optional[str] = None,
) -> int:
    n = 0
    # Each (slot_order, player_display) is unique. Substitutions reuse the slot.
    for row in rows:
        slot_raw = row.get("順")
        try:
            slot = int(slot_raw) if slot_raw else None
        except (TypeError, ValueError):
            slot = None
        if slot is None:
            continue
        display = (row.get("選手") or "").strip()
        if not display:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO batting_logs (
                game_id, team_role, slot_order, position,
                player_display, player_canonical, is_sub,
                AB, R, H, RBI, SB, atbats_json, team_name
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                team_role,
                slot,
                (row.get("守備") or "").strip() or None,
                display,
                resolve_canonical(display, aliases),
                int(bool(row.get("is_sub"))),
                _int_or_none(row.get("打数")),
                _int_or_none(row.get("得点")),
                _int_or_none(row.get("安打")),
                _int_or_none(row.get("打点")),
                _int_or_none(row.get("盗塁")),
                json.dumps(row.get("atbats") or [], ensure_ascii=False),
                team_name,
            ),
        )
        n += 1
    return n


_PITCHER_AGGREGATE_LABELS = {"チーム計", "計", "合計", "全体"}


def _upsert_pitchers(
    conn: sqlite3.Connection,
    game_id: str,
    team_role: str,
    rows: Iterable[dict],
    aliases: dict[str, str],
    team_name: Optional[str] = None,
) -> int:
    n = 0
    order = 0
    for raw in rows:
        display = (raw.get("選手") or "").strip()
        if not display:
            continue
        # NPB box の最終行は「チーム計」集計行。投手 log には含めない。
        if display in _PITCHER_AGGREGATE_LABELS or display.startswith("チーム"):
            continue
        order += 1
        row = raw
        conn.execute(
            """
            INSERT OR REPLACE INTO pitching_logs (
                game_id, team_role, appearance_order,
                player_display, player_canonical,
                result_mark, pitches, BF, IP,
                H_allowed, HR_allowed, BB, HBP, K, WP, BK, R, ER, team_name
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                team_role,
                order,
                display,
                resolve_canonical(display, aliases),
                (row.get("result_mark") or "").strip() or None,
                _int_or_none(row.get("投球数")),
                _int_or_none(row.get("打者")),
                parse_ip(row.get("投球回")),
                _int_or_none(row.get("安打")),
                _int_or_none(row.get("本塁打")),
                _int_or_none(row.get("四球")),
                _int_or_none(row.get("死球")),
                _int_or_none(row.get("三振")),
                _int_or_none(row.get("暴投")),
                _int_or_none(row.get("ボーク")),
                _int_or_none(row.get("失点")),
                _int_or_none(row.get("自責点")),
                team_name,
            ),
        )
        n += 1
    return n


# ─── single-game detectors (stub-grade, multi-game logic is next phase) ─────


def detect_single_game_signals(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    run_id: str,
    created_at: str,
) -> list[dict]:
    """Emit MVP-grade signals from a single game's logs.

    These are intentionally simple — they exist to prove the
    article_candidates row shape end-to-end. Real signals (z-score,
    streaks, splits, lineup deltas) need a multi-game history and live
    in a follow-up phase.
    """
    out: list[dict] = []

    # batter signals (Giants only)
    for row in conn.execute(
        """
        SELECT player_display, player_canonical, slot_order, position,
               AB, R, H, RBI, SB, atbats_json
        FROM batting_logs
        WHERE game_id = ? AND team_role = 'giants'
        ORDER BY slot_order, player_display
        """,
        (game_id,),
    ):
        h = row["H"] or 0
        ab = row["AB"] or 0
        rbi = row["RBI"] or 0
        atbats = json.loads(row["atbats_json"] or "[]")
        had_hr = any("本" in str(a) for a in atbats)

        if had_hr:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="batter_homerun",
                magnitude=1.0,
                baseline_value=None,
                current_value=f"H{h}/AB{ab}, RBI{rbi}",
                window_label="single_game",
                comparison_target=None,
                evidence={"atbats": atbats, "slot": row["slot_order"], "pos": row["position"]},
                priority=2,
                created_at=created_at,
                notes="単発HR検知（MVP単試合）",
            ))
        if h >= 3:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="batter_multi_hit",
                magnitude=float(h),
                baseline_value=None,
                current_value=f"H{h}/AB{ab}",
                window_label="single_game",
                comparison_target=None,
                evidence={"atbats": atbats, "slot": row["slot_order"], "pos": row["position"]},
                priority=3,
                created_at=created_at,
                notes="マルチヒット検知（MVP単試合）",
            ))

    # pitcher signals (Giants only)
    for row in conn.execute(
        """
        SELECT player_display, player_canonical, appearance_order,
               result_mark, pitches, BF, IP,
               H_allowed, HR_allowed, BB, HBP, K, R, ER
        FROM pitching_logs
        WHERE game_id = ? AND team_role = 'giants'
        ORDER BY appearance_order
        """,
        (game_id,),
    ):
        ip = row["IP"] or 0.0
        er = row["ER"] or 0
        pitches = row["pitches"] or 0

        # QS proxy (≥6.0 IP, ≤3 ER) — pitcher が先発したかは appearance_order=1 で代用
        if row["appearance_order"] == 1 and ip >= 6.0 and er <= 3:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="starter_quality_start",
                magnitude=ip,
                baseline_value=None,
                current_value=f"{ip}IP / {er}ER / {pitches}P",
                window_label="single_game",
                comparison_target=None,
                evidence=dict(row),
                priority=3,
                created_at=created_at,
                notes="QS（IP≥6 ER≤3）— 連続性は多試合フェーズで判定",
            ))
        # high pitch count警戒
        if pitches >= 110:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="pitcher_high_pitch_count",
                magnitude=float(pitches),
                baseline_value=None,
                current_value=f"{pitches}球",
                window_label="single_game",
                comparison_target=None,
                evidence=dict(row),
                priority=2,
                created_at=created_at,
                notes="多球数検知（疲労蓄積観測のフラグ）",
            ))

    return out


def _candidate(**kw: Any) -> dict:
    evidence = kw.pop("evidence", None)
    if isinstance(evidence, dict):
        evidence_json = json.dumps(_jsonify(evidence), ensure_ascii=False)
    else:
        evidence_json = None
    return {
        "run_id": kw["run_id"],
        "game_id": kw.get("game_id"),
        "player_canonical": kw.get("player_canonical"),
        "player_display": kw.get("player_display"),
        "signal_type": kw["signal_type"],
        "magnitude": kw.get("magnitude"),
        "baseline_value": kw.get("baseline_value"),
        "current_value": kw.get("current_value"),
        "window_label": kw.get("window_label"),
        "comparison_target": kw.get("comparison_target"),
        "evidence_json": evidence_json,
        "priority": kw.get("priority", 3),
        "status": "NEW",
        "created_at": kw["created_at"],
        "notes": kw.get("notes"),
    }


def _jsonify(obj: Any) -> Any:
    """Coerce sqlite3.Row / nested rows into JSON-serializable shapes."""
    if isinstance(obj, sqlite3.Row):
        return {k: _jsonify(obj[k]) for k in obj.keys()}
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def insert_candidates(
    conn: sqlite3.Connection,
    candidates: list[dict],
) -> list[int]:
    ids: list[int] = []
    for c in candidates:
        cur = conn.execute(
            """
            INSERT INTO article_candidates (
                run_id, game_id, player_canonical, player_display,
                signal_type, magnitude, baseline_value, current_value,
                window_label, comparison_target, evidence_json,
                priority, status, created_at, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                c["run_id"], c["game_id"], c["player_canonical"], c["player_display"],
                c["signal_type"], c["magnitude"], c["baseline_value"], c["current_value"],
                c["window_label"], c["comparison_target"], c["evidence_json"],
                c["priority"], c["status"], c["created_at"], c["notes"],
            ),
        )
        ids.append(cur.lastrowid)
    return ids


def export_candidates_csv(conn: sqlite3.Connection, csv_path: Path, run_id: str | None = None) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # run_ts は insight_runs に住んでいるので JOIN で取得する。
    query = """
        SELECT ac.candidate_id,
               ir.run_ts AS run_ts,
               ac.game_id, ac.player_canonical, ac.player_display,
               ac.signal_type, ac.magnitude, ac.baseline_value, ac.current_value,
               ac.window_label, ac.comparison_target, ac.evidence_json,
               ac.priority, ac.status, ac.created_at, ac.notes
        FROM article_candidates ac
        LEFT JOIN insight_runs ir ON ir.run_id = ac.run_id
    """
    params: tuple = ()
    if run_id:
        query += " WHERE ac.run_id = ?"
        params = (run_id,)
    query += " ORDER BY ac.candidate_id"
    rows = list(conn.execute(query, params))
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] if k in r.keys() else None for k in CSV_COLUMNS})
    return len(rows)


# ─── ETL entry point ─────────────────────────────────────────────────────────


def etl_from_html(
    html: str,
    *,
    game_id: str,
    game_date: str,
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA,
    csv_path: Path = DEFAULT_CSV,
    source_url: str | None = None,
    source_kind: str = "html",
    notes: str | None = None,
    aliases: dict[str, str] | None = None,
) -> dict:
    """Run the full single-game ETL against a raw NPB box HTML string.

    Identical pipeline to :func:`etl_fixture` but accepts the HTML as a
    string so callers (nightly orchestrator) can pass live-fetched or
    cached content without writing it to a temp file first.
    """
    parsed = parse_npb_box_html(html, allow_non_giants=True)
    if parsed is None:
        raise ValueError(f"parse_npb_box_html returned None for game_id={game_id}")

    aliases = aliases or _load_roster_aliases()
    conn = open_db(db_path=db_path, schema_path=schema_path)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = str(uuid.uuid4())

    try:
        upsert_game(
            conn,
            game_id=game_id,
            game_date=game_date,
            parsed=parsed,
            source_url=source_url,
            source_kind=source_kind,
            ingested_at=now_iso,
        )
        giants_team_name = parsed.get("giants_team_name") or "巨人"
        opponent_team_name = parsed.get("opponent_team_name") or ""
        n_g_bat = _upsert_batters(
            conn, game_id, "giants", parsed.get("giants_batters") or [], aliases,
            team_name=giants_team_name,
        )
        n_o_bat = _upsert_batters(
            conn, game_id, "opponent", parsed.get("opponent_batters") or [], aliases,
            team_name=opponent_team_name,
        )
        n_g_pit = _upsert_pitchers(
            conn, game_id, "giants", parsed.get("giants_pitchers") or [], aliases,
            team_name=giants_team_name,
        )
        n_o_pit = _upsert_pitchers(
            conn, game_id, "opponent", parsed.get("opponent_pitchers") or [], aliases,
            team_name=opponent_team_name,
        )

        conn.execute(
            "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, n_candidates, notes) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, now_iso, game_date, game_date, 0, notes or f"etl_from_html game_id={game_id}"),
        )

        candidates = detect_single_game_signals(
            conn,
            game_id=game_id,
            run_id=run_id,
            created_at=now_iso,
        )
        inserted = insert_candidates(conn, candidates)
        conn.execute(
            "UPDATE insight_runs SET n_candidates = ? WHERE run_id = ?",
            (len(inserted), run_id),
        )
        conn.commit()

        csv_rows = export_candidates_csv(conn, csv_path, run_id=run_id)
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "game_id": game_id,
        "batters_giants": n_g_bat,
        "batters_opponent": n_o_bat,
        "pitchers_giants": n_g_pit,
        "pitchers_opponent": n_o_pit,
        "candidates_inserted": len(candidates),
        "csv_rows_written": csv_rows,
        "db_path": str(db_path),
        "csv_path": str(csv_path),
    }


def etl_fixture(
    fixture_path: Path,
    *,
    game_id: str,
    game_date: str,
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA,
    csv_path: Path = DEFAULT_CSV,
    source_url: str | None = None,
    aliases: dict[str, str] | None = None,
) -> dict:
    """Run the full ETL on a fixture HTML file. Returns a summary dict
    that includes a ``fixture`` key (back-compat for INSIGHT-001 tests).
    Internally a thin wrapper over :func:`etl_from_html`."""
    html = fixture_path.read_text(encoding="utf-8")
    summary = etl_from_html(
        html,
        game_id=game_id,
        game_date=game_date,
        db_path=db_path,
        schema_path=schema_path,
        csv_path=csv_path,
        source_url=source_url,
        source_kind="fixture",
        notes=f"etl fixture {fixture_path.name}",
        aliases=aliases,
    )
    summary["fixture"] = str(fixture_path)
    return summary


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="INSIGHT-001 fixture ETL prototype (no live URL, no WP I/O)."
    )
    p.add_argument("--fixture", required=True, help="path to NPB box HTML fixture")
    p.add_argument("--game-id", required=True, help="e.g. '2026-05-10:d-g-08'")
    p.add_argument("--game-date", required=True, help="ISO date e.g. '2026-05-10'")
    p.add_argument("--db", default=str(DEFAULT_DB_PATH))
    p.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    p.add_argument("--csv", default=str(DEFAULT_CSV))
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="parse only; do not write to SQLite/CSV (default: write)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(json.dumps({"error": f"fixture not found: {fixture_path}"}), file=sys.stderr)
        return 2

    if args.dry_run:
        html = fixture_path.read_text(encoding="utf-8")
        parsed = parse_npb_box_html(html, allow_non_giants=True)
        summary = {
            "dry_run": True,
            "fixture": str(fixture_path),
            "parsed_keys": list(parsed.keys()) if parsed else [],
            "n_giants_batters": len((parsed or {}).get("giants_batters") or []),
            "n_giants_pitchers": len((parsed or {}).get("giants_pitchers") or []),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    summary = etl_fixture(
        fixture_path,
        game_id=args.game_id,
        game_date=args.game_date,
        db_path=Path(args.db),
        schema_path=Path(args.schema),
        csv_path=Path(args.csv),
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
