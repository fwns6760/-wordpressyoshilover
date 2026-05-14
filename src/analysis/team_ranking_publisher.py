"""DATA-INSIGHT-continuous: 球団 (team) metric ranking article publisher.

球団打率 / 球団 ERA / 球団 HR 等を セ・リーグ 6 球団で集計、巨人位置 highlight
で WP に publish。個人選手の anomaly 系記事と並走、wider angle で「巨人
打線 / 投手陣 全体」評価。

設計方針:
  * pure rule-based、LLM 不使用
  * セ・リーグ 6 球団に限定 (user 指示「セパは別」)
  * 2026 シーズンの data のみ (今年分)
  * 巨人記事として ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1 で auto publish
  * 7 日 dedup (publish_notice_history.json or タイトル check)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import insight_atbats_parser  # noqa: E402
from src.analysis import ranking_article_publisher as rap  # noqa: E402

DEFAULT_CATEGORY_NAME = rap.DEFAULT_CATEGORY_NAME

CENTRAL_TEAMS = ("g", "t", "s", "c", "db", "d")
TEAM_NAME_TO_CODE = {
    "巨人": "g", "読売": "g", "ジャイアンツ": "g",
    "阪神": "t", "タイガース": "t",
    "ヤクルト": "s", "スワローズ": "s",
    "広島": "c", "カープ": "c",
    "DeNA": "db", "横浜": "db", "ベイスターズ": "db",
    "中日": "d", "ドラゴンズ": "d",
}


def _team_code_from_name(name: str) -> str:
    if not name:
        return "?"
    for token, code in TEAM_NAME_TO_CODE.items():
        if token in name:
            return code
    return "?"


def _scope_window(scope: str, today: Optional[dt.date] = None) -> tuple[str, str]:
    if today is None:
        today = dt.date.today()
    if scope == "last_7d":
        start = today - dt.timedelta(days=6)
    elif scope == "last_30d":
        start = today - dt.timedelta(days=29)
    elif scope == "season":
        start = dt.date(today.year, 3, 27)
    else:
        start = today
    return (start.isoformat(), today.isoformat())


# ─── team metric aggregation ────────────────────────────────────────────────


def aggregate_team_hr(conn: sqlite3.Connection, *, scope: str) -> list[dict]:
    """セ・リーグ 6 球団の HR 数集計 (atbats_json parse)."""
    start, end = _scope_window(scope)
    hr_per_team: dict[str, int] = {tc: 0 for tc in CENTRAL_TEAMS}
    rows = conn.execute(
        "SELECT bl.team_name, bl.atbats_json FROM batting_logs bl "
        "JOIN games g ON bl.game_id = g.game_id "
        "WHERE g.game_date >= ? AND g.game_date <= ? "
        "AND bl.team_name IS NOT NULL AND bl.atbats_json IS NOT NULL",
        (start, end),
    ).fetchall()
    for team_name, atbats_json in rows:
        tc = _team_code_from_name(team_name)
        if tc not in CENTRAL_TEAMS:
            continue
        try:
            atbats = json.loads(atbats_json) if isinstance(atbats_json, str) else atbats_json
        except Exception:
            continue
        if not isinstance(atbats, list):
            continue
        for ab in atbats:
            if not isinstance(ab, str):
                continue
            try:
                if insight_atbats_parser.parse_atbat(ab).get("is_hr"):
                    hr_per_team[tc] += 1
            except Exception:
                continue
    return [{"team": tc, "value": hrs} for tc, hrs in hr_per_team.items()]


def aggregate_team_avg(conn: sqlite3.Connection, *, scope: str) -> list[dict]:
    """セ・リーグ 6 球団の team 打率 = SUM(H) / SUM(AB)."""
    start, end = _scope_window(scope)
    rows = conn.execute(
        "SELECT bl.team_name, SUM(bl.AB) AS ab, SUM(bl.H) AS h "
        "FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
        "WHERE g.game_date >= ? AND g.game_date <= ? "
        "AND bl.team_name IS NOT NULL "
        "GROUP BY bl.team_name",
        (start, end),
    ).fetchall()
    result = []
    for team_name, ab, h in rows:
        tc = _team_code_from_name(team_name)
        if tc not in CENTRAL_TEAMS:
            continue
        if not ab or ab == 0:
            continue
        avg = round(float(h or 0) / float(ab), 4)
        result.append({"team": tc, "value": avg, "ab": ab, "h": h})
    return result


def aggregate_team_era(conn: sqlite3.Connection, *, scope: str) -> list[dict]:
    """セ・リーグ 6 球団の team 防御率 = SUM(ER)*9 / SUM(IP)."""
    start, end = _scope_window(scope)
    rows = conn.execute(
        "SELECT pl.team_name, SUM(pl.IP) AS ip, SUM(pl.ER) AS er "
        "FROM pitching_logs pl JOIN games g ON pl.game_id = g.game_id "
        "WHERE g.game_date >= ? AND g.game_date <= ? "
        "AND pl.team_name IS NOT NULL "
        "GROUP BY pl.team_name",
        (start, end),
    ).fetchall()
    result = []
    for team_name, ip, er in rows:
        tc = _team_code_from_name(team_name)
        if tc not in CENTRAL_TEAMS:
            continue
        if not ip or ip <= 0:
            continue
        era = round(float(er or 0) * 9.0 / float(ip), 3)
        result.append({"team": tc, "value": era, "ip": ip, "er": er})
    return result


# ─── article rendering ──────────────────────────────────────────────────────


def _build_team_table_md(rows: list[dict], focus_tc: str = "g", value_label: str = "値",
                        higher_is_better: bool = True) -> str:
    """6 球団 team table の markdown を構築 (巨人を赤太字 highlight)."""
    sorted_rows = sorted(rows, key=lambda r: r["value"], reverse=higher_is_better)
    lines = [f"| 順位 | 球団 | {value_label} |", "|---|---|---|"]
    for i, r in enumerate(sorted_rows, start=1):
        team_disp = rap._TEAM_LABEL_JP.get(r["team"], r["team"])
        is_focus = (r["team"] == focus_tc)
        if isinstance(r["value"], float):
            val = f"{r['value']:.3f}"
        else:
            val = str(r["value"])
        if is_focus:
            rd = f'<span style="color:#c0392b"><strong>{i}</strong></span>'
            td = f'<span style="color:#c0392b"><strong>{team_disp} ★</strong></span>'
            vd = f'<span style="color:#c0392b"><strong>{val}</strong></span>'
        else:
            rd, td, vd = str(i), team_disp, val
        lines.append(f"| {rd} | {td} | {vd} |")
    return "\n".join(lines)


def _scope_label_jp(scope: str) -> str:
    return {"last_7d": "1 週間", "last_30d": "1 ヶ月", "season": "今シーズン"}.get(scope, scope)


def render_team_metric_article(
    conn: sqlite3.Connection,
    *,
    metric: str,  # 'HR' / 'AVG' / 'ERA'
    scope: str,
) -> Optional[dict]:
    """team metric ranking article を render."""
    higher_is_better = (metric != "ERA")
    if metric == "HR":
        rows = aggregate_team_hr(conn, scope=scope)
        metric_label = "本塁打数"
        formula = "atbats_json から本塁打 count を集計"
        explain = "球団全体の本塁打数。長打力 / 打線爆発力の指標。"
    elif metric == "AVG":
        rows = aggregate_team_avg(conn, scope=scope)
        metric_label = "打率"
        formula = "全選手の SUM(H) ÷ SUM(AB)"
        explain = "球団打率。打線全体の打撃力の総合指標。"
    elif metric == "ERA":
        rows = aggregate_team_era(conn, scope=scope)
        metric_label = "防御率"
        formula = "全投手の (SUM(自責点) × 9) ÷ SUM(投球回)"
        explain = "球団防御率(低いほど良い)。投手陣全体の失点抑止力。"
    else:
        return None

    if len(rows) < 4:
        return None  # data 不足

    sorted_rows = sorted(rows, key=lambda r: r["value"], reverse=higher_is_better)
    giants_row = next((r for r in sorted_rows if r["team"] == "g"), None)
    if not giants_row:
        return None
    giants_rank = sorted_rows.index(giants_row) + 1
    giants_value = giants_row["value"]
    if isinstance(giants_value, float):
        giants_val_str = f"{giants_value:.3f}"
    else:
        giants_val_str = str(giants_value)

    scope_label = _scope_label_jp(scope)
    start_str, end_str = _scope_window(scope)

    title = f"【巨人データを見る】{scope_label}のセ・リーグ球団{metric_label}、巨人 {giants_rank}/6 位({giants_val_str})"

    # table md
    table_md = _build_team_table_md(sorted_rows, focus_tc="g", value_label=metric_label,
                                     higher_is_better=higher_is_better)

    # SVG chart
    chart_rows = [
        {"player": rap._TEAM_LABEL_JP.get(r["team"], r["team"]),
         "team": r["team"], "value": float(r["value"]),
         "sample": r.get("ab", r.get("ip", 0)) or 0,
         "rank": i+1}
        for i, r in enumerate(sorted_rows)
    ]
    chart_svg = rap.render_ranking_svg_bar_chart(
        chart_rows, focus_player=rap._TEAM_LABEL_JP.get("g", "巨人"),
        metric_name=metric_label,
        title=f"セ・リーグ 球団{metric_label} {scope_label}",
        subtitle=f"集計期間: {start_str} 〜 {end_str}",
    )

    intro_banner = (
        '<div style="background:#fff8e1;border-left:4px solid #f39c12;padding:10px 15px;margin:1em 0;">'
        '<strong>🔥 大手ニュースで取り上げないデータ角度</strong><br>'
        f'sabermetric 視点でセ・リーグ全体の球団 {metric_label} を比較した、ヨシラバー独自分析です。'
        '</div>'
    )

    body_md = f"""# {title}

{intro_banner}

## ひとこと

セ・リーグ 6 球団中で巨人の {metric_label} は **{giants_rank} 位**({giants_val_str})。

## セ・リーグ 球団 ranking({scope_label})

{table_md}

{chart_svg}

## このデータについて

| 項目 | 内容 |
|---|---|
| 球団 | **巨人** / セ・リーグ {giants_rank}/6 位 |
| 指標 | {metric_label} = **{giants_val_str}** |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計期間 | {start_str} 〜 {end_str} |
| 計算式 | {formula} |
| 説明 | {explain} |
| 比較 | この期間のセ・リーグ 6 球団全体 |
"""
    body_html = rap.markdown_to_html(body_md)
    return {
        "title": title,
        "body_md": body_md,
        "body_html": body_html,
        "metric": metric,
        "scope": scope,
        "giants_rank": giants_rank,
    }


def publish_team_metric_draft(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    metric: str,
    scope: str,
    category_name: str = DEFAULT_CATEGORY_NAME,
    dry_run: bool = False,
) -> dict:
    article = render_team_metric_article(conn, metric=metric, scope=scope)
    if article is None:
        return {"status": "skip", "reason": "no_data", "metric": metric, "scope": scope}
    if dry_run:
        return {"status": "dry_run", "title": article["title"], "metric": metric, "scope": scope}
    category_id = 0
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

    # 巨人 team の場合 publish、他なら draft (team ranking 記事は常に巨人 focus なので publish 想定)
    publish_status = rap._resolve_publish_status(focus_team_code="g")
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=article["body_html"],
            categories=[category_id],
            status=publish_status,
            caller="team_ranking_publisher",
        )
        return {
            "status": "published" if publish_status == "publish" else "published_draft",
            "title": article["title"],
            "post_id": int(post_id or 0),
            "metric": metric, "scope": scope,
        }
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def publish_team_default_set(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    max_per_run: int = 3,
    dry_run: bool = False,
) -> list[dict]:
    """デフォルト team metric publish set (user 指示「開幕から」優先 + 月間も)."""
    default_jobs = [
        {"metric": "HR", "scope": "season"},     # 開幕からの 球団 HR
        {"metric": "AVG", "scope": "season"},    # 開幕からの 球団打率
        {"metric": "ERA", "scope": "season"},    # 開幕からの 球団防御率
        {"metric": "HR", "scope": "last_30d"},   # 月間 HR
        {"metric": "AVG", "scope": "last_30d"},  # 月間打率
        {"metric": "ERA", "scope": "last_30d"},  # 月間防御率
        {"metric": "HR", "scope": "last_7d"},    # 週間 HR
    ]
    results = []
    published = 0
    for job in default_jobs:
        if published >= max_per_run:
            results.append({"status": "skip_max", **job})
            continue
        r = publish_team_metric_draft(conn, wp_client_obj, dry_run=dry_run, **job)
        results.append(r)
        if r.get("status") in ("published", "published_draft", "dry_run"):
            published += 1
    return results
