"""DATA-INSIGHT-continuous: 巨人中心 + 12 球団 ranking article 自動 publish.

342-INSIGHT (data-driven ranking 自動 publish) + 343-INSIGHT-007 (12 球団
data 基盤) の合流 module。既存 `insight_article_generator.render_article`
を wrap し、`advanced_metric_snapshots` から取得した ranking rows + 巨人
top player を focus にして article を構築、`wp_client.create_post(status=
'draft')` で WP に draft として landed させる。

設計方針:
  * pure rule-based、LLM 不使用
  * `status='draft'` 固定 (auto-publish は env flag gate、本 module 範囲外)
  * 既存 `wp_client.find_recent_post_by_title` で重複 draft 防止 (idempotent)
  * `ENABLE_DATA_INSIGHT_AUTO_PUBLISH=1` の検知は呼び出し側で行う (本 module
    は常に status='draft' 投入)
  * markdown body は inline 簡易 converter で HTML 化 (vendored markdown lib
    不在のため)

Hard constraints (work record §7):
  * env / secret / scheduler 一切 touch しない
  * X 自動投稿 / 既存 publish post mutation しない
  * LLM call を path に混入させない
  * `status='draft'` 以外を許容しない
  * 「データで見る巨人」category 以外への投入は許容しない (誤投入回避)
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import insight_article_generator  # noqa: E402
from src.analysis import insight_atbats_parser  # noqa: E402
from src.analysis import insight_dedup_gate as dedup_gate  # noqa: E402
from src.analysis import insight_quality_gate as quality_gate  # noqa: E402
from src.analysis import insight_title_guard as title_guard  # noqa: E402
from src.analysis.insight_article_generator import (  # noqa: E402
    ArticleContext,
    RankRow,
)
from src.giants_news_banner import (  # noqa: E402
    giants_news_banner_html as _giants_news_banner_html,
)


# NEWS-BANNER-FIX-2026-05-15: insight 系 publisher 共通の source label。
# 外部メディア由来ではなく ヨシラバー の独自データ分析記事を示す。
_BANNER_SOURCE_LABEL = "ヨシラバー巨人ラボ"


# 新 category 名 (work record §4)
DEFAULT_CATEGORY_NAME = "データで見る巨人"


# ─── SVG chart renderer (表の下に inline 埋め込み、user 指示) ────────────


_TEAM_LABEL_JP = {
    "g": "巨人", "t": "阪神", "s": "ヤクルト", "c": "広島",
    "db": "DeNA", "d": "中日", "h": "ソフトバンク", "l": "西武",
    "m": "ロッテ", "e": "楽天", "b": "オリックス", "f": "日本ハム",
}


def render_ranking_svg_bar_chart(
    rows: list[dict],
    *,
    focus_player: str,
    metric_name: str,
    title: str = "",
    subtitle: str = "",
    width: int = 760,
) -> str:
    """横棒 ranking chart の SVG markup (inline 埋め込み用、外部依存なし).

    Args:
        rows: list of {player, team, value, sample, rank}
        focus_player: 該当選手 (赤太字 highlight)
        metric_name: 'OPS' / 'ERA' 等 (X 軸ラベル)
        title / subtitle: 上部 text
        width: SVG 幅 (default 760、WP 標準コラム幅)
    """
    if not rows:
        return ""
    h = 80 + len(rows) * 32
    margin_l, margin_top, margin_b = 180, 70 if title else 30, 40
    chart_w = width - margin_l - 60
    bar_h = 22

    values = [r["value"] for r in rows if r.get("value") is not None]
    if not values:
        return ""
    max_val = max(values)
    min_val = min(values) * 0.95 if min(values) > 0 else 0

    # inline style: WP の wpautop は SVG 内 <style> block を見て前後に </p><p> を
    # 挿入してしまうため、class を使わず style 属性で書く。同じ理由で改行も入れない。
    S_T = 'font-size:18px;font-weight:bold;fill:#222'
    S_ST = 'font-size:12px;fill:#555'
    S_LB = 'font-size:13px;fill:#333'
    S_V = 'font-size:13px;font-weight:bold;fill:#fff'
    S_VO = 'font-size:13px;fill:#222'
    S_FB = 'fill:#c0392b'
    S_NB = 'fill:#7faed5'
    S_FL = 'font-size:13px;font-weight:bold;fill:#c0392b'
    S_AX = 'stroke:#999;stroke-width:1;fill:none'

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {h}" '
        f'style="max-width:100%;height:auto;font-family:sans-serif;display:block;margin:1em 0;">',
    ]
    if title:
        parts.append(f'<text x="{width//2}" y="26" text-anchor="middle" style="{S_T}">{title}</text>')
    if subtitle:
        parts.append(f'<text x="{width//2}" y="50" text-anchor="middle" style="{S_ST}">{subtitle}</text>')

    for i, r in enumerate(rows, start=1):
        y = margin_top + (i - 1) * (bar_h + 10)
        is_focus = (r["player"] == focus_player)
        bar_style = S_FB if is_focus else S_NB
        label_style = S_FL if is_focus else S_LB
        val = r["value"] or 0
        bar_w = int((val - min_val) / (max_val - min_val) * chart_w) if max_val > min_val else chart_w
        bar_w = max(20, bar_w)
        team_disp = _TEAM_LABEL_JP.get(r.get("team", ""), r.get("team", "?"))
        star = " ★" if is_focus else ""
        label_text = f"{i}. {r['player']}({team_disp}){star}"
        parts.append(f'<text x="{margin_l-10}" y="{y+bar_h//2+5}" text-anchor="end" style="{label_style}">{label_text}</text>')
        parts.append(f'<rect x="{margin_l}" y="{y}" width="{bar_w}" height="{bar_h}" style="{bar_style}" rx="3"/>')
        if bar_w > 70:
            parts.append(f'<text x="{margin_l+bar_w-6}" y="{y+bar_h//2+5}" text-anchor="end" style="{S_V}">{val:.3f}</text>')
        else:
            parts.append(f'<text x="{margin_l+bar_w+6}" y="{y+bar_h//2+5}" text-anchor="start" style="{S_VO}">{val:.3f}</text>')

    parts.append(f'<line x1="{margin_l}" y1="{h-margin_b+5}" x2="{margin_l+chart_w}" y2="{h-margin_b+5}" style="{S_AX}"/>')
    parts.append(f'<text x="{margin_l}" y="{h-margin_b+22}" style="{S_LB}">{min_val:.2f}</text>')
    parts.append(f'<text x="{margin_l+chart_w}" y="{h-margin_b+22}" text-anchor="end" style="{S_LB}">{max_val:.2f}</text>')
    parts.append(f'<text x="{margin_l+chart_w//2}" y="{h-margin_b+22}" text-anchor="middle" style="{S_LB}">{metric_name}</text>')
    parts.append('</svg>')
    # 1 行で返す: WP の wpautop が改行を見て前後に </p><p> を入れるのを防ぐ
    return ''.join(parts)

# 348 step 3 part 2: counting stats ranking helper (D-1 minimum impl)
# 完全な publisher integration は別 ticket、 現状は aggregate のみ提供。


_CENTRAL_TEAM_NAMES = ("巨人", "阪神", "ヤクルト", "広島", "DeNA", "横浜", "中日")
_PACIFIC_TEAM_NAMES = ("ソフトバンク", "西武", "ロッテ", "楽天", "オリックス", "日本ハム")


def _scope_window(
    scope: str,
    today: Optional[Any] = None,
    *,
    conn: Optional[sqlite3.Connection] = None,
    focus_player: Optional[str] = None,
) -> tuple[Any, Any]:
    """Common scope-to-(start, end) date computation. Returns (date, date).

    403 (2026-05-20): 新 scope vocabulary 対応。 game-count / PA / appearance /
    IP cumsum scope は ``conn`` 引数経由で DB lookup し、 該当 game の最古日付
    を start とする (filter は依然 date range で表現、 既存 SQL 構造維持)。

    新 scope の追加は additive。 既存 scope (`last_7d` / `last_30d` / `season`
    / `monthly` / `weekly`) は不変。

    Args:
        scope: scope vocabulary 文字列
        today: 計算 base 日付 (default: 今日)
        conn: DB connection (game-count / PA / appearance / IP scope で必須)
        focus_player: 選手名 (PA / appearance / IP scope で必須、 player_canonical)

    Returns:
        (start_date, end_date) tuple
    """
    import datetime as _dt
    if today is None:
        today = _dt.date.today()
    # 既存 date-based scope (変更なし)
    if scope == "last_7d":
        return today - _dt.timedelta(days=6), today
    if scope == "last_30d":
        return today - _dt.timedelta(days=29), today
    if scope == "season":
        return _dt.date(today.year, 1, 1), today
    if scope == "monthly":
        return today.replace(day=1), today
    if scope == "weekly":
        return today - _dt.timedelta(days=today.weekday()), today
    # 新 scope vocabulary (403)
    if scope.startswith("last_") and scope.endswith("_games"):
        n_games = int(scope[len("last_"):-len("_games")])
        if conn is None:
            raise ValueError(f"scope {scope!r} requires conn")
        return _compute_giants_game_window(conn, n_games=n_games, today=today)
    if scope.startswith("last_") and scope.endswith("_pa"):
        n_pa = int(scope[len("last_"):-len("_pa")])
        if conn is None or focus_player is None:
            raise ValueError(f"scope {scope!r} requires conn + focus_player")
        return _compute_player_pa_window(
            conn, player=focus_player, n_pa=n_pa, today=today,
        )
    if scope.startswith("last_") and scope.endswith("_appearances"):
        n_apps = int(scope[len("last_"):-len("_appearances")])
        if conn is None or focus_player is None:
            raise ValueError(f"scope {scope!r} requires conn + focus_player")
        return _compute_pitcher_appearance_window(
            conn, pitcher=focus_player, n_apps=n_apps, today=today,
        )
    if scope.startswith("last_") and scope.endswith("_ip"):
        n_ip = int(scope[len("last_"):-len("_ip")])
        if conn is None or focus_player is None:
            raise ValueError(f"scope {scope!r} requires conn + focus_player")
        return _compute_pitcher_ip_window(
            conn, pitcher=focus_player, n_ip=n_ip, today=today,
        )
    raise ValueError(f"unsupported scope: {scope!r}")


def _compute_giants_game_window(
    conn: sqlite3.Connection,
    *,
    n_games: int,
    today: Any,
) -> tuple[Any, Any]:
    """直近 n 試合の巨人試合の game_date 範囲を返す。 403 fix。

    巨人試合数 cnt (出場有無関係なし、 ベンチ含む) ベース。 batting_logs から
    巨人 row を持つ game を today 以前で游 desc 並べ、 n 試合目の game_date を
    start として返す。
    """
    import datetime as _dt
    rows = conn.execute(
        "SELECT DISTINCT g.game_date FROM games g "
        "JOIN batting_logs bl ON g.game_id = bl.game_id "
        "WHERE bl.team_name = '巨人' AND g.game_date <= ? "
        "ORDER BY g.game_date DESC LIMIT ?",
        (today.isoformat(), n_games),
    ).fetchall()
    if not rows:
        # 巨人試合なし: today 単日を返す (空 sample になる)
        return today, today
    earliest_date_str = rows[-1][0]
    start = _dt.date.fromisoformat(earliest_date_str)
    return start, today


def _compute_player_pa_window(
    conn: sqlite3.Connection,
    *,
    player: str,
    n_pa: int,
    today: Any,
) -> tuple[Any, Any]:
    """選手の直近 n 打席 (PA cumsum) を満たす game_date 範囲を返す。 403 fix。

    PA = atbats_json entry 数。 today 以前の batting_logs を game_date desc で
    游り、 PA cumsum >= n_pa に達した行の game_date を start とする。
    """
    import datetime as _dt
    import json as _json
    rows = conn.execute(
        "SELECT g.game_date, bl.atbats_json FROM batting_logs bl "
        "JOIN games g ON bl.game_id = g.game_id "
        "WHERE bl.player_canonical = ? AND g.game_date <= ? "
        "ORDER BY g.game_date DESC",
        (player, today.isoformat()),
    ).fetchall()
    cumsum = 0
    for date_str, atb_json in rows:
        try:
            atbs = _json.loads(atb_json) if atb_json else []
        except Exception:
            atbs = []
        if isinstance(atbs, list):
            cumsum += len(atbs)
        if cumsum >= n_pa:
            return _dt.date.fromisoformat(date_str), today
    # n_pa 未達: 取得できた最古 row まで返す (sample 不足は呼出側で判定)
    if rows:
        return _dt.date.fromisoformat(rows[-1][0]), today
    return today, today


def _compute_pitcher_appearance_window(
    conn: sqlite3.Connection,
    *,
    pitcher: str,
    n_apps: int,
    today: Any,
) -> tuple[Any, Any]:
    """投手の直近 n 登板を含む game_date 範囲を返す。 403 fix。"""
    import datetime as _dt
    rows = conn.execute(
        "SELECT g.game_date FROM pitching_logs pl "
        "JOIN games g ON pl.game_id = g.game_id "
        "WHERE pl.player_canonical = ? AND g.game_date <= ? "
        "ORDER BY g.game_date DESC LIMIT ?",
        (pitcher, today.isoformat(), n_apps),
    ).fetchall()
    if not rows:
        return today, today
    return _dt.date.fromisoformat(rows[-1][0]), today


def _compute_pitcher_ip_window(
    conn: sqlite3.Connection,
    *,
    pitcher: str,
    n_ip: float,
    today: Any,
) -> tuple[Any, Any]:
    """投手の直近 n 投球回 (IP cumsum) を満たす game_date 範囲を返す。 403 fix。"""
    import datetime as _dt
    rows = conn.execute(
        "SELECT g.game_date, pl.IP FROM pitching_logs pl "
        "JOIN games g ON pl.game_id = g.game_id "
        "WHERE pl.player_canonical = ? AND g.game_date <= ? "
        "ORDER BY g.game_date DESC",
        (pitcher, today.isoformat()),
    ).fetchall()
    cumsum = 0.0
    for date_str, ip in rows:
        try:
            cumsum += float(ip or 0)
        except (TypeError, ValueError):
            continue
        if cumsum >= n_ip:
            return _dt.date.fromisoformat(date_str), today
    if rows:
        return _dt.date.fromisoformat(rows[-1][0]), today
    return today, today


def aggregate_player_hr_from_atbats(
    conn: sqlite3.Connection,
    *,
    scope: str,
    today: Optional[Any] = None,
    top_n: int = 10,
    league: Optional[str] = None,
    focus_player: Optional[str] = None,
) -> list[dict]:
    """選手別 HR 数を ``atbats_json`` から集計 (issue #44 G follow-up).

    ``batting_logs`` schema には HR 列が存在せず、 HR は ``atbats_json`` の
    各打席文字列 (例 ``中本``) に格納されている。 SQL ``SUM(bl.HR)`` は
    ``OperationalError`` を出すため、 ``insight_atbats_parser.parse_atbat``
    を経由して per-row count。 ``team_ranking_publisher.aggregate_team_hr``
    と同じ pattern を player level に extend。

    403 (2026-05-20): focus_player kw 追加 (PA / appearance / IP scope の
    window 計算用、 game-count scope は不要)。

    Returns: list of {"player": str, "team": str, "value": int} (top_n)
    """
    start, end = _scope_window(
        scope, today, conn=conn, focus_player=focus_player,
    )
    league_clause = ""
    league_params: tuple = ()
    if league == "central":
        placeholders = ",".join("?" * len(_CENTRAL_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _CENTRAL_TEAM_NAMES
    elif league == "pacific":
        placeholders = ",".join("?" * len(_PACIFIC_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _PACIFIC_TEAM_NAMES
    rows = conn.execute(
        f"SELECT bl.player_canonical, bl.team_name, bl.atbats_json "
        f"FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
        f"WHERE g.game_date >= ? AND g.game_date <= ? "
        f"AND bl.player_canonical IS NOT NULL "
        f"AND bl.player_canonical != '' "
        f"AND bl.atbats_json IS NOT NULL"
        f"{league_clause}",
        (start.isoformat(), end.isoformat(), *league_params),
    ).fetchall()

    import json as _json
    hr_by_key: dict[tuple[str, str], int] = {}
    for player, team_name, atbats_json in rows:
        try:
            atbats = _json.loads(atbats_json) if isinstance(atbats_json, str) else atbats_json
        except Exception:
            continue
        if not isinstance(atbats, list):
            continue
        hrs = 0
        for ab in atbats:
            if not isinstance(ab, str):
                continue
            try:
                if insight_atbats_parser.parse_atbat(ab).get("is_hr"):
                    hrs += 1
            except Exception:
                continue
        if hrs <= 0:
            continue
        key = (player, team_name or "")
        hr_by_key[key] = hr_by_key.get(key, 0) + hrs

    ranked = sorted(
        (
            {"player": p, "team": _team_name_to_code(t), "value": v}
            for (p, t), v in hr_by_key.items()
        ),
        key=lambda r: r["value"],
        reverse=True,
    )
    return ranked[:top_n]


def aggregate_player_hr_from_atbats_split(
    conn: sqlite3.Connection,
    *,
    scope: str,
    split_field: str,  # "home_away" or "opponent"
    split_value: str,
    today: Optional[Any] = None,
    top_n: int = 10,
    league: Optional[str] = None,
    focus_player: Optional[str] = None,
) -> list[dict]:
    """ホーム/アウェイ別 / 対戦相手別 HR 数を ``atbats_json`` から集計 (406 fix).

    ``aggregate_player_hr_from_atbats`` の split 対応版。 ``batting_logs.HR``
    列が無いため ``aggregate_player_counting_stat_split`` の ``SUM(bl.HR)``
    が ``OperationalError`` を返す問題を、 split 経路でも atbats_json 集計に
    dispatch して回避する。

    403: focus_player kw 追加 (PA / appearance / IP scope window 計算用)。
    """
    if split_field not in ("home_away", "opponent"):
        raise ValueError(f"unsupported split_field: {split_field!r}")
    start, end = _scope_window(
        scope, today, conn=conn, focus_player=focus_player,
    )
    league_clause = ""
    league_params: tuple = ()
    if league == "central":
        placeholders = ",".join("?" * len(_CENTRAL_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _CENTRAL_TEAM_NAMES
    elif league == "pacific":
        placeholders = ",".join("?" * len(_PACIFIC_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _PACIFIC_TEAM_NAMES
    rows = conn.execute(
        f"SELECT bl.player_canonical, bl.team_name, bl.atbats_json "
        f"FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
        f"WHERE g.game_date >= ? AND g.game_date <= ? "
        f"AND g.{split_field} = ? "
        f"AND bl.player_canonical IS NOT NULL "
        f"AND bl.player_canonical != '' "
        f"AND bl.atbats_json IS NOT NULL"
        f"{league_clause}",
        (start.isoformat(), end.isoformat(), split_value, *league_params),
    ).fetchall()

    import json as _json
    hr_by_key: dict[tuple[str, str], int] = {}
    for player, team_name, atbats_json in rows:
        try:
            atbats = _json.loads(atbats_json) if isinstance(atbats_json, str) else atbats_json
        except Exception:
            continue
        if not isinstance(atbats, list):
            continue
        hrs = 0
        for ab in atbats:
            if not isinstance(ab, str):
                continue
            try:
                if insight_atbats_parser.parse_atbat(ab).get("is_hr"):
                    hrs += 1
            except Exception:
                continue
        if hrs <= 0:
            continue
        key = (player, team_name or "")
        hr_by_key[key] = hr_by_key.get(key, 0) + hrs

    ranked = sorted(
        (
            {"player": p, "team": _team_name_to_code(t), "value": v}
            for (p, t), v in hr_by_key.items()
        ),
        key=lambda r: r["value"],
        reverse=True,
    )
    return ranked[:top_n]


def aggregate_player_counting_stat(
    conn: sqlite3.Connection,
    *,
    stat_col: str,
    table: str,
    scope: str,
    today: Optional[Any] = None,
    top_n: int = 10,
    league: Optional[str] = None,
    focus_player: Optional[str] = None,
) -> list[dict]:
    """指定 counting stat (HR / H / RBI / SB / W / K 等) を player 別集計、 top_n 返却。

    348 step 3 spec §2.5: 「セ / パ リーグ別 ranking (リーグ横断 NG)」適用、
    `league='central'` / `'pacific'` で filter (default None は後方互換で全 12 球団)。

    403 (2026-05-20): 新 scope vocabulary (last_N_games / last_N_pa /
    last_N_appearances / last_N_ip) 対応。 ``focus_player`` は PA / appearance
    / IP scope で必須 (game-count scope は不要)。

    Args:
        stat_col: SQL column 名 (例 'H' / 'HR' / 'RBI' / 'K')
        table: 'batting_logs' / 'pitching_logs' / 'fielding_logs'
        scope: 'season' / 'last_30d' / 'last_5_games' 等
        league: 'central' / 'pacific' / None (= 12 球団全体、 spec 違反、 deprecated)
        focus_player: PA / appearance / IP scope で必須 (window 計算用)

    return: list of {"player": str, "team": str, "value": int}
    """
    # issue #44 G follow-up: HR は batting_logs に列が無く atbats_json 集計が必要。
    # SQL SUM(bl.HR) は OperationalError を出すため、 専用 helper に dispatch。
    if stat_col == "HR" and table == "batting_logs":
        return aggregate_player_hr_from_atbats(
            conn, scope=scope, today=today, top_n=top_n, league=league,
            focus_player=focus_player,
        )
    import datetime as _dt
    if today is None:
        today = _dt.date.today()
    start, end = _scope_window(
        scope, today, conn=conn, focus_player=focus_player,
    )
    safe_col = "".join(c for c in stat_col if c.isalnum() or c == "_")
    if safe_col != stat_col:
        raise ValueError(f"unsafe stat_col: {stat_col!r}")
    if table not in ("batting_logs", "pitching_logs", "fielding_logs"):
        raise ValueError(f"unsupported table: {table!r}")
    # 348 step 3 spec: league filter (セ/パ 横断 NG)
    league_clause = ""
    league_params: tuple = ()
    if league == "central":
        placeholders = ",".join("?" * len(_CENTRAL_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _CENTRAL_TEAM_NAMES
    elif league == "pacific":
        placeholders = ",".join("?" * len(_PACIFIC_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _PACIFIC_TEAM_NAMES
    rows = conn.execute(
        f"SELECT bl.player_canonical, bl.team_name, SUM(bl.{safe_col}) AS total "
        f"FROM {table} bl JOIN games g ON bl.game_id = g.game_id "
        f"WHERE g.game_date >= ? AND g.game_date <= ? "
        f"AND bl.player_canonical IS NOT NULL "
        f"AND bl.player_canonical != ''"
        f"{league_clause} "
        f"GROUP BY bl.player_canonical "
        f"ORDER BY total DESC LIMIT ?",
        (start.isoformat(), end.isoformat(), *league_params, top_n),
    ).fetchall()
    return [
        {"player": p, "team": _team_name_to_code(t), "value": int(v or 0)}
        for p, t, v in rows
    ]


def _team_name_to_code(team_name: Optional[str]) -> str:
    if not team_name:
        return "?"
    name = str(team_name)
    for token, code in {
        "巨人": "g", "読売": "g", "阪神": "t", "ヤクルト": "s",
        "広島": "c", "DeNA": "db", "横浜": "db", "中日": "d",
        "ソフトバンク": "h", "西武": "l", "ロッテ": "m",
        "楽天": "e", "オリックス": "b", "日本ハム": "f",
    }.items():
        if token in name:
            return code
    return "?"


# 新 subtype の prefix (extractor + publish_evaluator 拡張時に対応)
SUBTYPE_DATA_RANKING_PREFIX = "data_ranking_"

# 1 trigger で publish する最大 article 数 (暴走防止、env で override 可)
DEFAULT_MAX_PER_RUN = int(os.environ.get("DATA_INSIGHT_PUBLISH_MAX_PER_RUN", "3") or "3")

# auto-publish env flag (本 module は draft 固定、auto-publish は呼び出し側)
ENABLE_DATA_INSIGHT_AUTO_PUBLISH = (
    os.environ.get("ENABLE_DATA_INSIGHT_AUTO_PUBLISH", "0").strip() == "1"
)

# 巨人記事のみ auto-publish (user 明示 GO「巨人は自動公開でもいいよ」)
# focus_player が巨人 (team_code='g') の ranking 記事のみ status='publish'、
# 他球団は draft 維持 (§11 user 判断境界)
ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS = (
    os.environ.get("ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS", "0").strip() == "1"
)


def _ensure_player_tag(wp_client_obj: Any, player_name: str) -> int:
    """player 名で WP タグ search、なければ create、tag id を返す."""
    if not player_name:
        return 0
    import requests as _req
    try:
        resp = wp_client_obj._request_with_retry(
            _req.get, f"{wp_client_obj.api}/tags",
            action="tag_search", params={"search": player_name, "per_page": 10},
        )
        for t in resp.json():
            if t.get("name") == player_name:
                return int(t["id"])
    except Exception:
        pass
    try:
        resp = wp_client_obj._request_with_retry(
            _req.post, f"{wp_client_obj.api}/tags",
            action="tag_create", json={"name": player_name},
        )
        return int(resp.json().get("id", 0) or 0)
    except Exception:
        return 0


def _resolve_publish_status(*, focus_team_code: Optional[str] = None) -> str:
    """env flag + team_code から WP publish status を決定。

    - ENABLE_DATA_INSIGHT_AUTO_PUBLISH=1: 全 record auto publish
    - ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1 + focus_team_code='g': 巨人のみ publish
    - 上記以外: 'draft' (user 確認待ち)
    """
    if ENABLE_DATA_INSIGHT_AUTO_PUBLISH:
        return "publish"
    if ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS and (focus_team_code or "").strip() == "g":
        return "publish"
    return "draft"


# ─── snapshot DB query ──────────────────────────────────────────────────────


def fetch_ranking_rows(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    scope: str,
    snapshot_date: Optional[str] = None,
    top_n: int = 30,
) -> list[RankRow]:
    """``advanced_metric_snapshots`` から指定 metric/scope の ranking 行を取得。

    ``snapshot_date`` 省略時は table の最新 ``snapshot_date`` を採用。
    取得行は ``league_rank`` 昇順 (1 位から) で ``top_n`` 件まで。
    各行は ``RankRow`` 形式に変換して返す。
    """
    if snapshot_date is None:
        latest = conn.execute(
            "SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
            "WHERE metric_name = ? AND scope = ?",
            (metric_name, scope),
        ).fetchone()
        snapshot_date = latest[0] if latest else None
    if not snapshot_date:
        return []
    rows = conn.execute(
        "SELECT player_canonical, team_code, metric_value, sample_size, "
        "league_rank, league_total "
        "FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
        "AND league_rank IS NOT NULL "
        "ORDER BY league_rank ASC LIMIT ?",
        (metric_name, scope, snapshot_date, top_n),
    ).fetchall()
    result: list[RankRow] = []
    for player_canonical, team_code, metric_value, sample_size, league_rank, league_total in rows:
        result.append(RankRow(
            player_canonical=str(player_canonical or ""),
            team_code=str(team_code or "") or None,
            metric_value=float(metric_value) if metric_value is not None else None,
            sample_size=int(sample_size or 0),
            rank=int(league_rank or 0),
            total=int(league_total or 0),
        ))
    return result


def find_giants_top(rows: list[RankRow]) -> Optional[str]:
    """``rows`` の中で最も上位の巨人選手 ``player_canonical`` を返す。
    不在なら ``None`` (= 巨人選手が ranking top_n 圏外)。
    """
    for r in rows:
        if r.team_code == "g":
            return r.player_canonical
    return None


# ─── markdown → HTML 簡易 converter ─────────────────────────────────────────


_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)_([^_\n]+)_(?!\*)")


def _md_table_to_html(lines: list[str], start: int) -> tuple[str, int]:
    """Markdown table block (start at ``lines[start]``) を ``<table>`` HTML に変換。

    Markdown table format:
      | h1 | h2 |
      |---|---|
      | c1 | c2 |
    return: (html, end_index_exclusive)
    """
    header_cells = [c.strip() for c in lines[start].strip("|").split("|")]
    end = start + 2  # skip header + separator
    body_rows: list[list[str]] = []
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        cells = [c.strip() for c in lines[end].strip("|").split("|")]
        body_rows.append(cells)
        end += 1
    parts = ["<table>", "<thead><tr>"]
    for h in header_cells:
        parts.append(f"<th>{_inline_md(h)}</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in body_rows:
        parts.append("<tr>")
        for c in row:
            parts.append(f"<td>{_inline_md(c)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts), end


def _inline_md(text: str) -> str:
    text = _MD_BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _MD_ITALIC_RE.sub(r"<em>\1</em>", text)
    return text


def markdown_to_html(md: str) -> str:
    """簡易 markdown → HTML converter (render_article の出力を WP body に変換)。

    対応: # h1 (h2 化) / ## h2 (h3 化) / ### h3 (h4 化) / table / **bold** /
          _italic_ / --- (hr) / 空行 paragraph 区切り。
    h1 を h2 化するのは WP title が h1 の役割を担うため。
    """
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    paragraph_buf: list[str] = []

    def flush_paragraph():
        if paragraph_buf:
            joined = " ".join(p.rstrip() for p in paragraph_buf if p.strip())
            if joined:
                out.append(f"<p>{_inline_md(joined)}</p>")
            paragraph_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            i += 1
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            out.append(f"<h2>{_inline_md(stripped[2:].strip())}</h2>")
            i += 1
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            out.append(f"<h3>{_inline_md(stripped[3:].strip())}</h3>")
            i += 1
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            out.append(f"<h4>{_inline_md(stripped[4:].strip())}</h4>")
            i += 1
            continue
        if stripped == "---":
            flush_paragraph()
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            html, end = _md_table_to_html(lines, i)
            out.append(html)
            i = end
            continue
        paragraph_buf.append(line)
        i += 1
    flush_paragraph()
    return "\n".join(out)


# ─── public API ─────────────────────────────────────────────────────────────


_CENTRAL_TEAMS = frozenset({"g", "t", "s", "c", "db", "d"})


def render_giants_centric_ranking(
    conn: sqlite3.Connection,
    *,
    metric_name: str = "OPS",
    scope: str = "last_30d",
    snapshot_date: Optional[str] = None,
    top_n: int = 30,
    sample_window_label: Optional[str] = None,
) -> Optional[dict]:
    """巨人中心 + セ・リーグ ranking article を render (user 指示「セとパ別」)。

    Returns: ``{title, body_html, body_md, suggested_tags, meta}`` or ``None``
    """
    # セ・リーグ 6 球団のみで rank 再計算
    rows_all = fetch_ranking_rows(
        conn, metric_name=metric_name, scope=scope,
        snapshot_date=snapshot_date, top_n=200,
    )
    rows_central = [r for r in rows_all if (r.team_code or "") in _CENTRAL_TEAMS]
    # rank 再付与
    from src.analysis.insight_article_generator import RankRow
    rows = []
    for i, r in enumerate(rows_central[:top_n], start=1):
        rows.append(RankRow(
            player_canonical=r.player_canonical, team_code=r.team_code,
            metric_value=r.metric_value, sample_size=r.sample_size,
            rank=i, total=len(rows_central),
        ))
    if not rows:
        return None

    focus_player = find_giants_top(rows)
    if focus_player is None:
        # 巨人選手不在の場合は本 module で記事化しない (focus 取れない)
        return None

    if sample_window_label is None:
        sample_window_label = title_guard.period_label_for_scope(scope) or scope

    ctx = ArticleContext(
        metric_name=metric_name,
        rows=rows,
        focus_player=focus_player,
        sample_window_label=sample_window_label,
    )
    # insight_article_generator は text 多めの body を生成するため、本実装では
    # title のみ流用、body は table-only で組み立て直す (user 指示「文字少なめ、
    # 表が目立つ感じ」)
    result = insight_article_generator.render_article(ctx, top_n=top_n)
    base_title = result["title"]
    # insight_article_generator は「12 球団中」固定文言、セ・リーグ用に置換
    base_title = base_title.replace("12 球団中", "セ・リーグ").replace("全 30 人中", "セ・リーグ")
    if not base_title.startswith("【"):
        base_title = f"【巨人データ】{base_title}"
    title_check = title_guard.ensure_title_period(base_title, scope=scope)
    if not title_check.ok:
        return None
    base_title = title_check.title

    # rebuild table from rows
    team_label_map = {
        "g": "巨人", "t": "阪神", "s": "ヤクルト", "c": "広島",
        "db": "DeNA", "d": "中日", "h": "ソフトバンク", "l": "西武",
        "m": "ロッテ", "e": "楽天", "b": "オリックス", "f": "日本ハム",
    }
    metric_formula_map = {
        "OPS": "出塁率(OBP) + 長打率(SLG)",
        "AVG": "安打数 ÷ 打数",
        "wOBA": "SABR 打撃指標(長打を得点期待値で重み付け)",
        "ISO": "SLG - AVG(純粋な長打力)",
        "ERA": "(自責点 × 9) ÷ 投球回",
        "FIP": "((13×HR + 3×(BB+HBP) - 2×K) ÷ IP) + 定数",
        "WHIP": "(被安打 + 四球) ÷ 投球回",
    }
    formula = metric_formula_map.get(metric_name, f"{metric_name} 標準式")
    scope_label_text = title_guard.period_label_for_scope(scope) or scope

    # ranking table (top_n 行、focus_player は赤太字 highlight)
    def _red_bold(text: str) -> str:
        return f'<span style="color:#c0392b"><strong>{text}</strong></span>'

    table_lines = [
        f"| 順位 | 選手 | チーム | {metric_name} | サンプル |",
        "|---|---|---|---|---|",
    ]
    focus_row_obj = None
    for r in rows[:top_n]:
        is_focus = (r.player_canonical == focus_player)
        if is_focus:
            focus_row_obj = r
        team_disp = team_label_map.get(r.team_code or "", r.team_code or "?")
        val = f"{r.metric_value:.3f}" if r.metric_value is not None else "-"
        if is_focus:
            rank_disp = _red_bold(str(r.rank))
            player_disp = _red_bold(f"{r.player_canonical} ★")
            team_cell = _red_bold(team_disp)
            val_disp = _red_bold(val)
            sample_disp = _red_bold(str(r.sample_size))
        else:
            rank_disp = str(r.rank)
            player_disp = r.player_canonical
            team_cell = team_disp
            val_disp = val
            sample_disp = str(r.sample_size)
        table_lines.append(
            f"| {rank_disp} | {player_disp} | {team_cell} | {val_disp} | {sample_disp} |"
        )

    table_md = "\n".join(table_lines)

    # focus row metadata
    focus_team = team_label_map.get(focus_row_obj.team_code if focus_row_obj else "g", "巨人")
    focus_val = f"{focus_row_obj.metric_value:.3f}" if focus_row_obj and focus_row_obj.metric_value is not None else "-"
    focus_rank = f"{focus_row_obj.rank}/{focus_row_obj.total}" if focus_row_obj else "-"
    focus_sample = f"{focus_row_obj.sample_size}" if focus_row_obj else "-"

    # period date range (試合数削除、user 指示で全12球団合計は誤解招くため)
    today = dt.date.today()
    if scope == "last_7d":
        start_d = today - dt.timedelta(days=6)
    elif scope == "last_30d":
        start_d = today - dt.timedelta(days=29)
    elif scope == "season":
        start_d = dt.date(today.year, 3, 27)
    else:
        start_d = today
    period_full = f"{start_d.isoformat()} 〜 {today.isoformat()}"

    # 348 step 3 spec §2.5: 「大手にない」 banner 廃止 (全種類で省略)。
    # 同じ lock で SVG chart も廃止。本文は表形式だけで構成する。
    intro_banner = ""

    body_md = f"""# {base_title}

{intro_banner}

## セ・リーグ ranking

{table_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 選手 | **{focus_player}({focus_team})** / サンプル {focus_sample} |
| 指標 | {metric_name} = **{focus_val}** / セ・リーグ **{focus_rank} 位** |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計期間 | {period_full} |
| 計算式 | {formula} |
| 比較 | この期間の セ・リーグ 6 球団 内 全選手 |
"""
    body_html = markdown_to_html(body_md)
    return {
        "title": base_title,
        "body_md": body_md,
        "body_html": body_html,
        "suggested_tags": result["suggested_tags"],
        "meta": result["meta"],
        "focus_player": focus_player,
        "metric_name": metric_name,
        "scope": scope,
        "focus_value": focus_row_obj.metric_value if focus_row_obj else None,
        "focus_rank": focus_row_obj.rank if focus_row_obj else None,
        "focus_total": focus_row_obj.total if focus_row_obj else None,
    }


def publish_giants_centric_ranking_draft(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    metric_name: str = "OPS",
    scope: str = "last_30d",
    snapshot_date: Optional[str] = None,
    top_n: int = 30,
    category_name: str = DEFAULT_CATEGORY_NAME,
    dry_run: bool = False,
) -> dict:
    """巨人中心 ranking article を WP draft として投入 (idempotent)。

    Args:
        conn: production DB sqlite connection (read-only 利用)
        wp_client_obj: wp_client.WPClient instance (create_category +
            create_post 利用)
        metric_name: 'OPS' / 'wOBA' / 'FIP' / etc.
        scope: 'last_7d' / 'last_30d' / 'season'
        snapshot_date: 省略時は最新 snapshot を採用
        top_n: ranking 表示行数
        category_name: 投入先 WP category (idempotent 作成)
        dry_run: ``True`` なら WP 投入せず article dict を返す

    Returns:
        ``{status, title, post_id, category_id, focus_player}`` or
        ``{status: 'skip', reason: ...}``
    """
    # 348 step 1 defense-in-depth: × metric (WHIP/FIP/xFIP/wOBA/BABIP/ISO/K_BB/
    # K_pct/BB_pct/UZR_proxy/RF_proxy) を publisher 入口で reject。
    # insight_anomaly_detector の z-score gate に加え、 publish_default_set
    # default_jobs 経由の path もここで gate (future leak risk 撤去)。
    from src.analysis import insight_whitelist as _wl
    if not _wl.is_metric_allowed(metric_name):
        return {
            "status": "skip",
            "reason": "x_metric_blocked",
            "metric_name": metric_name,
            "scope": scope,
        }
    article = render_giants_centric_ranking(
        conn, metric_name=metric_name, scope=scope,
        snapshot_date=snapshot_date, top_n=top_n,
    )
    if article is None:
        return {
            "status": "skip",
            "reason": "no_data_or_giants_not_in_top_n",
            "metric_name": metric_name,
            "scope": scope,
        }
    title_check = title_guard.ensure_title_period(article["title"], scope=scope)
    if not title_check.ok:
        return {
            "status": "skip_title_period_guard",
            "reason": title_check.reason,
            "metric_name": metric_name,
            "scope": scope,
            "title": article["title"],
        }
    article["title"] = title_check.title
    quality_decision = quality_gate.validate_player_snapshot_article(
        conn,
        article,
        metric_name=metric_name,
        scope=scope,
        focus_player=article.get("focus_player"),
        snapshot_date=snapshot_date,
    )
    if not quality_decision.allowed:
        return quality_gate.skip_result(
            quality_decision,
            focus_player=article.get("focus_player"),
            metric_name=metric_name,
            scope=scope,
            title=article["title"],
        )
    dedup_context = {
        "subject_key": article["focus_player"],
        "metric_name": metric_name,
        "scope": scope,
        "value": article.get("focus_value"),
        "rank": article.get("focus_rank"),
        "total": article.get("focus_total"),
    }
    dedup_decision = dedup_gate.evaluate_metric_cooldown(conn, **dedup_context)
    if not dedup_decision.get("allowed"):
        return {
            "status": "skip_dedup_cooldown",
            "reason": dedup_decision.get("reason"),
            "focus_player": article["focus_player"],
            "metric_name": metric_name,
            "scope": scope,
            "dedup": dedup_decision,
        }

    if dry_run:
        return {
            "status": "dry_run",
            "title": article["title"],
            "body_html": article["body_html"],
            "focus_player": article["focus_player"],
            "metric_name": metric_name,
            "scope": scope,
        }

    # category 作成 (idempotent)
    category_id = 0
    try:
        category_id = wp_client_obj.create_category(category_name)
    except Exception as e:  # noqa: BLE001
        return {
            "status": "error",
            "stage": "create_category",
            "error": f"{type(e).__name__}: {e}",
        }
    if not category_id:
        # 既存 ID 取得 fallback
        try:
            category_id = wp_client_obj.resolve_category_id(category_name)
        except Exception:  # noqa: BLE001
            category_id = 0

    if not category_id:
        return {
            "status": "error",
            "stage": "category_resolve",
            "error": f"category {category_name!r} unresolvable",
        }

    # WP 投入 status 決定 (env flag + 巨人判定)
    rows = article.get("meta", {}) or {}
    focus_team_code = "g"
    publish_status = _resolve_publish_status(focus_team_code=focus_team_code)
    # player tag 自動付与 (回遊 navigation、user 指示)
    tag_id = _ensure_player_tag(wp_client_obj, article["focus_player"])
    tags_list = [tag_id] if tag_id else None
    # 387: focus_player 不在 (team-level metric 等) でも最低 1 tag を保証
    # する fallback。 既存 WP tag「速報」 (id=850) を attach することで
    # c-tagList chip 0 = 内部リンク 0 を防ぐ。
    if not tags_list:
        tags_list = [850]
    # NEWS-BANNER-FIX-2026-05-15: insight 記事も赤紫グラデ banner を冒頭に
    # prepend し、全 publish 経路で content の先頭に banner が立つ状態を維持。
    _banner = _giants_news_banner_html(
        article["title"], _BANNER_SOURCE_LABEL, category_name
    )
    dedup_history_id = 0
    dedup_record_error = ""
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=_banner + article["body_html"],
            categories=[category_id],
            status=publish_status,
            caller="ranking_article_publisher",
        )
        # tag は別 PUT で post に attach (create_post に tags param がないため)
        if post_id and tags_list:
            try:
                import requests as _req
                wp_client_obj._request_with_retry(
                    _req.post, f"{wp_client_obj.api}/posts/{post_id}",
                    action="add_tags", json={"tags": tags_list},
                )
            except Exception:
                pass
        try:
            dedup_history_id = dedup_gate.record_metric_publish(
                conn,
                **dedup_context,
                title=article["title"],
                post_id=int(post_id or 0),
                wp_status=publish_status,
            )
        except Exception as exc:  # noqa: BLE001
            dedup_record_error = f"{type(exc).__name__}: {exc}"
    except Exception as e:  # noqa: BLE001
        return {
            "status": "error",
            "stage": "create_post",
            "error": f"{type(e).__name__}: {e}",
        }

    return {
        "status": "published" if publish_status == "publish" else "published_draft",
        "wp_status": publish_status,
        "title": article["title"],
        "post_id": int(post_id or 0),
        "category_id": int(category_id),
        "focus_player": article["focus_player"],
        "metric_name": metric_name,
        "scope": scope,
        "dedup_history_id": dedup_history_id,
        "dedup_record_error": dedup_record_error,
    }


# ─── CLI / wire helper ──────────────────────────────────────────────────────


def aggregate_player_counting_stat_split(
    conn: sqlite3.Connection,
    *,
    stat_col: str,
    table: str,
    scope: str,
    split_field: str,  # "home_away" or "opponent"
    split_value: str,  # "home" / "away" / 'g' / 't' / ...
    today: Optional[Any] = None,
    top_n: int = 10,
    league: Optional[str] = None,
    focus_player: Optional[str] = None,
) -> list[dict]:
    """ホーム/アウェイ別 / 対戦相手別 counting 集計 (348 step 3 完全達成、 §4 file list).

    403: focus_player kw 追加 (PA / appearance / IP scope window 計算用)。
    """
    # 406 fix: HR は batting_logs に列が無く atbats_json 集計が必要。
    # SQL SUM(bl.HR) は OperationalError を出すため、 split 対応 helper に dispatch。
    if stat_col == "HR" and table == "batting_logs":
        return aggregate_player_hr_from_atbats_split(
            conn, scope=scope,
            split_field=split_field, split_value=split_value,
            today=today, top_n=top_n, league=league,
            focus_player=focus_player,
        )
    if split_field not in ("home_away", "opponent"):
        raise ValueError(f"unsupported split_field: {split_field!r}")
    start, end = _scope_window(
        scope, today, conn=conn, focus_player=focus_player,
    )
    safe_col = "".join(c for c in stat_col if c.isalnum() or c == "_")
    if safe_col != stat_col:
        raise ValueError(f"unsafe stat_col: {stat_col!r}")
    if table not in ("batting_logs", "pitching_logs", "fielding_logs"):
        raise ValueError(f"unsupported table: {table!r}")
    # 348 step 3 spec: league filter (セ/パ 横断 NG)
    league_clause = ""
    league_params: tuple = ()
    if league == "central":
        placeholders = ",".join("?" * len(_CENTRAL_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _CENTRAL_TEAM_NAMES
    elif league == "pacific":
        placeholders = ",".join("?" * len(_PACIFIC_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _PACIFIC_TEAM_NAMES
    rows = conn.execute(
        f"SELECT bl.player_canonical, bl.team_name, SUM(bl.{safe_col}) AS total "
        f"FROM {table} bl JOIN games g ON bl.game_id = g.game_id "
        f"WHERE g.game_date >= ? AND g.game_date <= ? "
        f"AND g.{split_field} = ? "
        f"AND bl.player_canonical IS NOT NULL "
        f"AND bl.player_canonical != ''"
        f"{league_clause} "
        f"GROUP BY bl.player_canonical "
        f"ORDER BY total DESC LIMIT ?",
        (start.isoformat(), end.isoformat(), split_value, *league_params, top_n),
    ).fetchall()
    return [
        {"player": p, "team": _team_name_to_code(t), "value": int(v or 0)}
        for p, t, v in rows
    ]


def render_player_counting_split_article(
    conn: sqlite3.Connection,
    *,
    stat_col: str,
    table: str,
    metric_label_jp: str,
    scope: str,
    split_field: str,
    split_value: str,
    split_label_jp: str,  # "ホーム" / "アウェイ" / "vs 阪神" 等
    top_n: int = 10,
) -> Optional[dict]:
    """ホーム/アウェイ別 / 対戦相手別 counting ranking 記事 (348 step 3 完全達成)."""
    # 348 step 3 spec §2.5: セ・リーグ別 ranking (巨人 = central 固定)
    rows = aggregate_player_counting_stat_split(
        conn, stat_col=stat_col, table=table, scope=scope,
        split_field=split_field, split_value=split_value,
        top_n=max(top_n, 30), league="central",
    )
    if not rows:
        return None
    giants_rows = [r for r in rows if r.get("team") == "g"]
    if not giants_rows:
        return None
    top_giants = giants_rows[0]
    top_player = top_giants["player"]
    top_value = top_giants["value"]
    giants_rank = next(
        (i + 1 for i, r in enumerate(rows) if r["player"] == top_player), len(rows),
    )
    # 403 (2026-05-20): inline dict 廃止、 title_guard.period_label_for_scope に
    # 統一 (新 scope last_N_games / last_N_pa / last_N_appearances / last_N_ip
    # が raw code として title / body に出る二重 label bug を回避)。
    scope_label = title_guard.period_label_for_scope(scope) or scope
    title = (
        f"【巨人データ】{top_player} {metric_label_jp} {top_value} で"
        f"{split_label_jp} セ・リーグ {giants_rank} 位 ({scope_label})"
    )
    title = title_guard.ensure_title_period(title, scope=scope).title
    table_lines = [
        f"| 順位 | 選手 | チーム | {metric_label_jp}({split_label_jp}) |",
        "|---|---|---|---|",
    ]
    focus_in_top_n = False
    for i, r in enumerate(rows[:top_n], start=1):
        team_disp = _TEAM_LABEL_JP.get(r.get("team", ""), r.get("team", "?"))
        is_focus = r["player"] == top_player
        if is_focus:
            focus_in_top_n = True
            r_disp = f'<span style="color:#c0392b"><strong>{i}</strong></span>'
            p_disp = f'<span style="color:#c0392b"><strong>{r["player"]} ★</strong></span>'
            v_disp = f'<span style="color:#c0392b"><strong>{r["value"]}</strong></span>'
        else:
            r_disp = str(i)
            p_disp = r["player"]
            v_disp = str(r["value"])
        table_lines.append(f"| {r_disp} | {p_disp} | {team_disp} | {v_disp} |")
    # 圏外 focus_player を末尾別行で表示 (spec §2.5「焦点選手 = 赤太字 + ★」必須)
    if not focus_in_top_n:
        team_disp = _TEAM_LABEL_JP.get(top_giants.get("team", ""), "?")
        r_disp = f'<span style="color:#c0392b"><strong>{giants_rank}</strong></span>'
        p_disp = f'<span style="color:#c0392b"><strong>{top_player} ★</strong></span>'
        v_disp = f'<span style="color:#c0392b"><strong>{top_value}</strong></span>'
        table_lines.append(f"| {r_disp} | {p_disp} | {team_disp} | {v_disp} |")
    table_md = "\n".join(table_lines)
    body_md = f"""# {title}

## ひとこと

巨人 {top_player} の **{split_label_jp}** での {metric_label_jp} は **{top_value}**
({scope_label} 時点)、 セ・リーグ内 **{giants_rank} 位**。

## リーグ TOP {top_n}({split_label_jp})

{table_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 選手 | **{top_player}**(巨人) |
| 指標 | {metric_label_jp}({split_label_jp}) = **{top_value}** |
| 順位 | リーグ {giants_rank} 位 |
| split | {split_field}={split_value}({split_label_jp}) |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計式 | SUM({stat_col}) over {table} WHERE games.{split_field}=:{split_value} |
| 集計期間 | {scope_label} |
"""
    body_html = markdown_to_html(body_md)
    return {
        "title": title, "body_md": body_md, "body_html": body_html,
        "stat_col": stat_col, "scope": scope,
        "split_field": split_field, "split_value": split_value,
        "top_player": top_player,
        "top_value": top_value,
        "giants_rank": giants_rank,
        "league_total": len(rows),
        "team_coverage": len({r.get("team") for r in rows if r.get("team")}),
    }


def publish_player_counting_split_draft(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    stat_col: str,
    table: str,
    metric_label_jp: str,
    scope: str,
    split_field: str,
    split_value: str,
    split_label_jp: str,
    category_name: str = DEFAULT_CATEGORY_NAME,
    dry_run: bool = False,
) -> dict:
    article = render_player_counting_split_article(
        conn, stat_col=stat_col, table=table,
        metric_label_jp=metric_label_jp, scope=scope,
        split_field=split_field, split_value=split_value,
        split_label_jp=split_label_jp, top_n=10,
    )
    if article is None:
        return {"status": "skip", "reason": "no_data_or_no_giants",
                "stat_col": stat_col, "scope": scope,
                "split": f"{split_field}={split_value}"}
    title_check = title_guard.ensure_title_period(article["title"], scope=scope)
    if not title_check.ok:
        return {
            "status": "skip_title_period_guard",
            "reason": title_check.reason,
            "stat_col": stat_col,
            "scope": scope,
            "split": f"{split_field}={split_value}",
            "title": article["title"],
        }
    article["title"] = title_check.title
    quality_decision = quality_gate.validate_counting_article(article)
    if not quality_decision.allowed:
        return quality_gate.skip_result(
            quality_decision,
            stat_col=stat_col,
            scope=scope,
            split=f"{split_field}={split_value}",
            title=article["title"],
        )
    metric_key = f"{stat_col}:{split_field}={split_value}"
    dedup_context = {
        "subject_key": article["top_player"],
        "metric_name": metric_key,
        "scope": scope,
        "value": article.get("top_value"),
        "rank": article.get("giants_rank"),
        "total": article.get("league_total"),
    }
    dedup_decision = dedup_gate.evaluate_metric_cooldown(conn, **dedup_context)
    if not dedup_decision.get("allowed"):
        return {
            "status": "skip_dedup_cooldown",
            "reason": dedup_decision.get("reason"),
            "stat_col": stat_col,
            "scope": scope,
            "split": f"{split_field}={split_value}",
            "dedup": dedup_decision,
        }
    if dry_run:
        return {"status": "dry_run", "title": article["title"]}
    try:
        category_id = wp_client_obj.create_category(category_name)
    except Exception:
        category_id = 0
    if not category_id:
        try:
            category_id = wp_client_obj.resolve_category_id(category_name)
        except Exception:
            category_id = 0
    if not category_id:
        return {"status": "error", "stage": "category"}
    publish_status = _resolve_publish_status(focus_team_code="g")
    _banner = _giants_news_banner_html(
        article["title"], _BANNER_SOURCE_LABEL, category_name,
    )
    dedup_history_id = 0
    dedup_record_error = ""
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=_banner + article["body_html"],
            categories=[category_id],
            status=publish_status,
            caller="ranking_article_publisher_counting_split",
        )
        try:
            dedup_history_id = dedup_gate.record_metric_publish(
                conn,
                **dedup_context,
                title=article["title"],
                post_id=int(post_id or 0),
                wp_status=publish_status,
            )
        except Exception as exc:  # noqa: BLE001
            dedup_record_error = f"{type(exc).__name__}: {exc}"
        return {
            "status": "published" if publish_status == "publish" else "published_draft",
            "title": article["title"], "post_id": int(post_id or 0),
            "stat_col": stat_col, "scope": scope,
            "split": f"{split_field}={split_value}",
            "dedup_history_id": dedup_history_id,
            "dedup_record_error": dedup_record_error,
        }
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


# ─── 403 Stage B: 打順別 publisher (band 化: 上位 / クリーンナップ / 下位) ───
#
# batting_logs.slot_order を split key にした打順別 ranking publisher。
# audit (2026-05-20) で個別 slot publish は 4 番固定 (= 岡本ばかり) リスク
# あったため、 3 band に集約: 上位打線 (1-2) / クリーンナップ (3-5) /
# 下位打線 (6-9)。 is_sub=0 で先発 lineup のみ集計。
#
# 既存 split publisher (home_away / opponent) と分離した dedicated function
# とした (slot_order は games ではなく batting_logs の列、 SQL 構造が異なる)。

_SLOT_BANDS: dict[str, tuple[tuple[int, ...], str]] = {
    "top": ((1, 2), "上位打線"),
    "cleanup": ((3, 4, 5), "クリーンナップ"),
    "bottom": ((6, 7, 8, 9), "下位打線"),
}


def aggregate_player_counting_stat_by_slot_band(
    conn: sqlite3.Connection,
    *,
    stat_col: str,
    scope: str,
    slot_band: str,
    today: Optional[Any] = None,
    top_n: int = 10,
    league: Optional[str] = None,
    focus_player: Optional[str] = None,
) -> list[dict]:
    """打順 band 別の counting 集計 (403 Stage B、 打者専用).

    batting_logs.slot_order ∈ band の先発 (is_sub=0) 出場時の集計のみ。
    HR は atbats_json 集計 (batting_logs に列無し) に dispatch するが、
    slot 別の atbats_json 集計は本実装では未対応 (skip)。
    """
    if slot_band not in _SLOT_BANDS:
        raise ValueError(f"unsupported slot_band: {slot_band!r}")
    slots, _label = _SLOT_BANDS[slot_band]
    # HR は batting_logs に列が無いので、 slot 別の HR は本実装で未対応 (skip)
    if stat_col == "HR":
        return []
    safe_col = "".join(c for c in stat_col if c.isalnum() or c == "_")
    if safe_col != stat_col:
        raise ValueError(f"unsafe stat_col: {stat_col!r}")
    start, end = _scope_window(
        scope, today, conn=conn, focus_player=focus_player,
    )
    league_clause = ""
    league_params: tuple = ()
    if league == "central":
        placeholders = ",".join("?" * len(_CENTRAL_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _CENTRAL_TEAM_NAMES
    elif league == "pacific":
        placeholders = ",".join("?" * len(_PACIFIC_TEAM_NAMES))
        league_clause = f" AND bl.team_name IN ({placeholders})"
        league_params = _PACIFIC_TEAM_NAMES
    slot_placeholders = ",".join("?" * len(slots))
    rows = conn.execute(
        f"SELECT bl.player_canonical, bl.team_name, SUM(bl.{safe_col}) AS total "
        f"FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
        f"WHERE g.game_date >= ? AND g.game_date <= ? "
        f"AND bl.slot_order IN ({slot_placeholders}) "
        f"AND bl.is_sub = 0 "
        f"AND bl.player_canonical IS NOT NULL "
        f"AND bl.player_canonical != ''"
        f"{league_clause} "
        f"GROUP BY bl.player_canonical "
        f"ORDER BY total DESC LIMIT ?",
        (start.isoformat(), end.isoformat(), *slots, *league_params, top_n),
    ).fetchall()
    return [
        {"player": p, "team": _team_name_to_code(t), "value": int(v or 0)}
        for p, t, v in rows
    ]


def render_player_counting_by_slot_band_article(
    conn: sqlite3.Connection,
    *,
    stat_col: str,
    metric_label_jp: str,
    scope: str,
    slot_band: str,
    top_n: int = 10,
) -> Optional[dict]:
    """打順 band 別の counting ranking 記事 (403 Stage B)."""
    if slot_band not in _SLOT_BANDS:
        return None
    _slots, band_label = _SLOT_BANDS[slot_band]
    rows = aggregate_player_counting_stat_by_slot_band(
        conn, stat_col=stat_col, scope=scope, slot_band=slot_band,
        top_n=max(top_n, 30), league="central",
    )
    if not rows:
        return None
    giants_rows = [r for r in rows if r.get("team") == "g"]
    if not giants_rows:
        return None
    top_giants = giants_rows[0]
    top_player = top_giants["player"]
    top_value = top_giants["value"]
    giants_rank = next(
        (i + 1 for i, r in enumerate(rows) if r["player"] == top_player), len(rows),
    )
    scope_label = title_guard.period_label_for_scope(scope) or scope
    title = (
        f"【巨人データ】{top_player} {band_label} {metric_label_jp} {top_value} "
        f"でセ・リーグ {giants_rank} 位 ({scope_label})"
    )
    title = title_guard.ensure_title_period(title, scope=scope).title
    table_lines = [
        f"| 順位 | 選手 | チーム | {metric_label_jp}({band_label}) |",
        "|---|---|---|---|",
    ]
    focus_in_top_n = False
    for i, r in enumerate(rows[:top_n], start=1):
        team_disp = _TEAM_LABEL_JP.get(r.get("team", ""), r.get("team", "?"))
        is_focus = r["player"] == top_player
        if is_focus:
            focus_in_top_n = True
            r_disp = f'<span style="color:#c0392b"><strong>{i}</strong></span>'
            p_disp = f'<span style="color:#c0392b"><strong>{r["player"]} ★</strong></span>'
            v_disp = f'<span style="color:#c0392b"><strong>{r["value"]}</strong></span>'
        else:
            r_disp = str(i)
            p_disp = r["player"]
            v_disp = str(r["value"])
        table_lines.append(f"| {r_disp} | {p_disp} | {team_disp} | {v_disp} |")
    if not focus_in_top_n:
        team_disp = _TEAM_LABEL_JP.get(top_giants.get("team", ""), "?")
        r_disp = f'<span style="color:#c0392b"><strong>{giants_rank}</strong></span>'
        p_disp = f'<span style="color:#c0392b"><strong>{top_player} ★</strong></span>'
        v_disp = f'<span style="color:#c0392b"><strong>{top_value}</strong></span>'
        table_lines.append(f"| {r_disp} | {p_disp} | {team_disp} | {v_disp} |")
    table_md = "\n".join(table_lines)
    body_md = f"""# {title}

## ひとこと

巨人 {top_player} の **{band_label}** での {metric_label_jp} は **{top_value}**
({scope_label} 時点)、 セ・リーグ内 **{giants_rank} 位**。

## リーグ TOP {top_n}({band_label})

{table_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 選手 | **{top_player}**(巨人) |
| 指標 | {metric_label_jp}({band_label}) = **{top_value}** |
| 順位 | リーグ {giants_rank} 位 |
| 打順 band | {band_label}(打順 {','.join(str(s) for s in _slots)} 番) |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計式 | SUM({stat_col}) over batting_logs WHERE slot_order IN ({','.join(str(s) for s in _slots)}) AND is_sub=0 |
| 集計期間 | {scope_label} |
"""
    body_html = markdown_to_html(body_md)
    return {
        "title": title, "body_md": body_md, "body_html": body_html,
        "stat_col": stat_col, "scope": scope,
        "slot_band": slot_band, "band_label": band_label,
        "top_player": top_player,
        "top_value": top_value,
        "giants_rank": giants_rank,
        "league_total": len(rows),
        "team_coverage": len({r.get("team") for r in rows if r.get("team")}),
    }


def publish_player_counting_by_slot_band_draft(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    stat_col: str,
    metric_label_jp: str,
    scope: str,
    slot_band: str,
    category_name: str = DEFAULT_CATEGORY_NAME,
    dry_run: bool = False,
) -> dict:
    """打順 band 別の counting ranking publish (403 Stage B、 mirror of split publish)."""
    article = render_player_counting_by_slot_band_article(
        conn, stat_col=stat_col, metric_label_jp=metric_label_jp,
        scope=scope, slot_band=slot_band, top_n=10,
    )
    if article is None:
        return {"status": "skip", "reason": "no_data_or_no_giants",
                "stat_col": stat_col, "scope": scope,
                "slot_band": slot_band}
    title_check = title_guard.ensure_title_period(article["title"], scope=scope)
    if not title_check.ok:
        return {
            "status": "skip_title_period_guard",
            "reason": title_check.reason,
            "stat_col": stat_col,
            "scope": scope,
            "slot_band": slot_band,
            "title": article["title"],
        }
    article["title"] = title_check.title
    quality_decision = quality_gate.validate_counting_article(article)
    if not quality_decision.allowed:
        return quality_gate.skip_result(
            quality_decision,
            stat_col=stat_col,
            scope=scope,
            slot_band=slot_band,
            title=article["title"],
        )
    metric_key = f"{stat_col}:slot_band={slot_band}"
    dedup_context = {
        "subject_key": article["top_player"],
        "metric_name": metric_key,
        "scope": scope,
        "value": article.get("top_value"),
        "rank": article.get("giants_rank"),
        "total": article.get("league_total"),
    }
    dedup_decision = dedup_gate.evaluate_metric_cooldown(conn, **dedup_context)
    if not dedup_decision.get("allowed"):
        return {
            "status": "skip_dedup_cooldown",
            "reason": dedup_decision.get("reason"),
            "stat_col": stat_col,
            "scope": scope,
            "slot_band": slot_band,
            "dedup": dedup_decision,
        }
    if dry_run:
        return {"status": "dry_run", "title": article["title"]}
    try:
        category_id = wp_client_obj.create_category(category_name)
    except Exception:
        category_id = 0
    if not category_id:
        try:
            category_id = wp_client_obj.resolve_category_id(category_name)
        except Exception:
            category_id = 0
    if not category_id:
        return {
            "status": "skip", "reason": "category_resolution_failed",
            "stat_col": stat_col, "scope": scope, "slot_band": slot_band,
        }
    publish_status = _resolve_publish_status()
    tags_list = _resolve_post_tags(wp_client_obj, focus_player=article["top_player"])
    if not tags_list:
        tags_list = [850]
    _banner = _giants_news_banner_html(
        article["title"], _BANNER_SOURCE_LABEL, category_name
    )
    dedup_history_id = 0
    dedup_record_error = ""
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=_banner + article["body_html"],
            categories=[category_id],
            status=publish_status,
            caller="ranking_article_publisher",
        )
        if post_id and tags_list:
            try:
                import requests as _req
                wp_client_obj._request_with_retry(
                    _req.post, f"{wp_client_obj.api}/posts/{post_id}",
                    action="add_tags", json={"tags": tags_list},
                )
            except Exception:
                pass
        try:
            dedup_history_id = dedup_gate.record_metric_publish(
                conn,
                **dedup_context,
                title=article["title"],
                post_id=int(post_id or 0),
                wp_status=publish_status,
            )
        except Exception as exc:  # noqa: BLE001
            dedup_record_error = f"{type(exc).__name__}: {exc}"
        return {
            "status": "published" if publish_status == "publish" else "published_draft",
            "wp_status": publish_status,
            "title": article["title"],
            "post_id": int(post_id or 0),
            "category_id": int(category_id),
            "stat_col": stat_col,
            "scope": scope,
            "slot_band": slot_band,
            "dedup_history_id": dedup_history_id,
            "dedup_record_error": dedup_record_error,
        }
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def render_player_counting_article(
    conn: sqlite3.Connection,
    *,
    stat_col: str,
    table: str,
    metric_label_jp: str,
    scope: str,
    top_n: int = 10,
) -> Optional[dict]:
    """player counting stat ranking 記事を render (348 step 3 part 2 D-1)。

    例: stat_col='HR', table='batting_logs', metric_label_jp='本塁打数'
        → 「本塁打数 ranking、 巨人 N/M 位」 記事を生成
    """
    # 348 step 3 spec §2.5: セ・リーグ別 ranking (巨人 = central 固定)
    rows = aggregate_player_counting_stat(
        conn, stat_col=stat_col, table=table, scope=scope,
        top_n=max(top_n, 30), league="central",
    )
    if not rows:
        return None
    # 巨人選手を抽出
    giants_rows = [r for r in rows if r.get("team") == "g"]
    if not giants_rows:
        return None
    top_giants = giants_rows[0]
    top_player = top_giants["player"]
    top_value = top_giants["value"]
    # giants_rank in the league: position of top_giants in full sorted rows
    giants_rank = next(
        (i + 1 for i, r in enumerate(rows) if r["player"] == top_player),
        len(rows),
    )

    # 403 (2026-05-20): inline dict 廃止、 title_guard.period_label_for_scope に統一
    scope_label = title_guard.period_label_for_scope(scope) or scope

    # 348 step 3 part 2 fix: body 集計期間 を実日付範囲で表示 (title variation
    # 補完 + 透明性、 user 指摘「期間がない」反映)
    # 403: 新 scope (last_N_games / last_N_pa / etc) は _scope_window で window
    # 計算、 raw code が period_range に出ないようにする
    import datetime as _dt
    _today = _dt.date.today()
    try:
        _start, _ = _scope_window(scope, _today, conn=conn, focus_player=top_player)
    except (ValueError, TypeError):
        _start = _today
    period_range = f"{_start.isoformat()} 〜 {_today.isoformat()}"

    title = (
        f"【巨人データ】{top_player} {metric_label_jp} {top_value} で"
        f"セ・リーグ {giants_rank} 位 ({scope_label})"
    )
    title = title_guard.ensure_title_period(title, scope=scope).title

    # 表 (TOP 10)、 348 step 3 spec §2.5: 焦点選手 = 赤太字 + ★ (圏外時は別行追加)
    table_lines = [f"| 順位 | 選手 | チーム | {metric_label_jp} |", "|---|---|---|---|"]
    focus_in_top_n = False
    for i, r in enumerate(rows[:top_n], start=1):
        team_disp = _TEAM_LABEL_JP.get(r.get("team", ""), r.get("team", "?"))
        is_focus = r["player"] == top_player
        if is_focus:
            focus_in_top_n = True
            r_disp = f'<span style="color:#c0392b"><strong>{i}</strong></span>'
            p_disp = f'<span style="color:#c0392b"><strong>{r["player"]} ★</strong></span>'
            v_disp = f'<span style="color:#c0392b"><strong>{r["value"]}</strong></span>'
        else:
            r_disp = str(i)
            p_disp = r["player"]
            v_disp = str(r["value"])
        table_lines.append(f"| {r_disp} | {p_disp} | {team_disp} | {v_disp} |")
    # 圏外 focus_player を末尾別行で表示 (spec §2.5「焦点選手 = 赤太字 + ★」必須)
    if not focus_in_top_n:
        team_disp = _TEAM_LABEL_JP.get(top_giants.get("team", ""), "?")
        r_disp = f'<span style="color:#c0392b"><strong>{giants_rank}</strong></span>'
        p_disp = f'<span style="color:#c0392b"><strong>{top_player} ★</strong></span>'
        v_disp = f'<span style="color:#c0392b"><strong>{top_value}</strong></span>'
        table_lines.append(f"| {r_disp} | {p_disp} | {team_disp} | {v_disp} |")
    table_md = "\n".join(table_lines)

    body_md = f"""# {title}

## ひとこと

巨人 {top_player} の {metric_label_jp} は **{top_value}** ({scope_label} 時点)、
セ・リーグ内 **{giants_rank} 位**。

## リーグ TOP {top_n}

{table_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 選手 | **{top_player}**(巨人) |
| 指標 | {metric_label_jp} = **{top_value}** |
| 順位 | リーグ {giants_rank} 位 |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計式 | SUM({stat_col}) over {table} (期間内全試合) |
| 集計期間 | {scope_label}({period_range}) |
"""
    body_html = markdown_to_html(body_md)
    return {
        "title": title,
        "body_md": body_md,
        "body_html": body_html,
        "stat_col": stat_col,
        "scope": scope,
        "top_player": top_player,
        "top_value": top_value,
        "giants_rank": giants_rank,
        "league_total": len(rows),
        "team_coverage": len({r.get("team") for r in rows if r.get("team")}),
    }


def publish_player_counting_draft(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    stat_col: str,
    table: str,
    metric_label_jp: str,
    scope: str,
    category_name: str = DEFAULT_CATEGORY_NAME,
    dry_run: bool = False,
) -> dict:
    """player counting stat ranking 記事を WP draft / publish (348 step 3 part 2 D-1)."""
    article = render_player_counting_article(
        conn, stat_col=stat_col, table=table,
        metric_label_jp=metric_label_jp, scope=scope, top_n=10,
    )
    if article is None:
        return {"status": "skip", "reason": "no_data_or_no_giants",
                "stat_col": stat_col, "scope": scope}
    title_check = title_guard.ensure_title_period(article["title"], scope=scope)
    if not title_check.ok:
        return {
            "status": "skip_title_period_guard",
            "reason": title_check.reason,
            "stat_col": stat_col,
            "scope": scope,
            "title": article["title"],
        }
    article["title"] = title_check.title
    quality_decision = quality_gate.validate_counting_article(article)
    if not quality_decision.allowed:
        return quality_gate.skip_result(
            quality_decision,
            stat_col=stat_col,
            scope=scope,
            title=article["title"],
        )
    dedup_context = {
        "subject_key": article["top_player"],
        "metric_name": stat_col,
        "scope": scope,
        "value": article.get("top_value"),
        "rank": article.get("giants_rank"),
        "total": article.get("league_total"),
    }
    dedup_decision = dedup_gate.evaluate_metric_cooldown(conn, **dedup_context)
    if not dedup_decision.get("allowed"):
        return {
            "status": "skip_dedup_cooldown",
            "reason": dedup_decision.get("reason"),
            "stat_col": stat_col,
            "scope": scope,
            "focus_player": article["top_player"],
            "dedup": dedup_decision,
        }
    if dry_run:
        return {"status": "dry_run", "title": article["title"]}
    try:
        category_id = wp_client_obj.create_category(category_name)
    except Exception:
        category_id = 0
    if not category_id:
        try:
            category_id = wp_client_obj.resolve_category_id(category_name)
        except Exception:
            category_id = 0
    if not category_id:
        return {"status": "error", "stage": "category"}
    publish_status = _resolve_publish_status(focus_team_code="g")
    _banner = _giants_news_banner_html(
        article["title"], _BANNER_SOURCE_LABEL, category_name
    )
    dedup_history_id = 0
    dedup_record_error = ""
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=_banner + article["body_html"],
            categories=[category_id],
            status=publish_status,
            caller="ranking_article_publisher_counting",
        )
        try:
            dedup_history_id = dedup_gate.record_metric_publish(
                conn,
                **dedup_context,
                title=article["title"],
                post_id=int(post_id or 0),
                wp_status=publish_status,
            )
        except Exception as exc:  # noqa: BLE001
            dedup_record_error = f"{type(exc).__name__}: {exc}"
        return {
            "status": "published" if publish_status == "publish" else "published_draft",
            "title": article["title"],
            "post_id": int(post_id or 0),
            "stat_col": stat_col, "scope": scope,
            "dedup_history_id": dedup_history_id,
            "dedup_record_error": dedup_record_error,
        }
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def publish_default_set(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    dry_run: bool = False,
    max_per_run: Optional[int] = None,
) -> list[dict]:
    """default rank set を順番に投入 (per-run 上限まで)。

    2026-05-16: default auto publish は短期変化を見る ``last_7d`` に寄せていた。
    403 (2026-05-20): 試合のない日に sample 不足で publish 0 件になる問題を
    解決するため、 日付 base (last_7d) を 試合数 base (last_5_games) に
    cutover。 audit で last_5_games は 7 名達成 (last_7d は 1-2 名のみ)。
    season / last_30d は手動判断または別 gate 付きの再導入対象。
    """
    if max_per_run is None:
        max_per_run = DEFAULT_MAX_PER_RUN
    # 2026-05-15 user 指示「サバメトリクスはいらない」適用、wOBA / FIP 除外。
    # 348 step 1 defense-in-depth (2026-05-16): WHIP も × metric なので除外
    # (publish_giants_centric_ranking_draft 内 gate と二重防御)。
    # 残す指標: OPS / AVG / OBP / SLG / ERA / K_per_9。
    # 403 (2026-05-20): last_7d (= 直近7日) → last_5_games (直近5試合) cutover
    # 試合のない日でも sample が確保され、 publish 過疎を回避。 audit 確定値。
    default_jobs = [
        # batter (last_5_games、 audit min_sample 12 AB / 7 名達成)
        {"metric_name": "OPS", "scope": "last_5_games", "top_n": 50},
        {"metric_name": "AVG", "scope": "last_5_games", "top_n": 50},
        {"metric_name": "OBP", "scope": "last_5_games", "top_n": 50},
        {"metric_name": "SLG", "scope": "last_5_games", "top_n": 50},
        # pitcher (last_5_games、 audit OK) — WHIP は × で削除済
        {"metric_name": "ERA", "scope": "last_5_games", "top_n": 30},
        {"metric_name": "K_per_9", "scope": "last_5_games", "top_n": 30},
    ]
    results: list[dict] = []
    published = 0
    seen_metric_periods: set[str] = set()
    for job in default_jobs:
        if published >= max_per_run:
            results.append({
                "status": "skip_max_per_run",
                "metric_name": job["metric_name"],
                "scope": job["scope"],
            })
            continue
        metric_key = str(job["metric_name"])
        if metric_key in seen_metric_periods:
            results.append({
                "status": "skip_duplicate_metric_period",
                "metric_name": job["metric_name"],
                "scope": job["scope"],
            })
            continue
        result = publish_giants_centric_ranking_draft(
            conn, wp_client_obj,
            metric_name=job["metric_name"],
            scope=job["scope"],
            top_n=job["top_n"],
            dry_run=dry_run,
        )
        results.append(result)
        if result.get("status") in ("published", "published_draft", "dry_run"):
            seen_metric_periods.add(metric_key)
        if result.get("status") in ("published", "published_draft", "dry_run"):
            published += 1
    return results
