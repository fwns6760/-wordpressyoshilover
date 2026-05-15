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
from src.giants_news_banner import (  # noqa: E402
    giants_news_banner_html as _giants_news_banner_html,
)

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


def aggregate_team_run_diff(conn: sqlite3.Connection, *, scope: str) -> list[dict]:
    """セ・リーグ 6 球団の得失点差 = SUM(giants_score - opp_score) 各球団視点で集計

    348 step 3 part 2: 得失点差 ranking。 巨人試合は games.giants_score - opp_score、
    他球団試合は team_name 経由で対戦結果から逆算が必要だが、 現 schema では
    巨人視点しか取れないため、 巨人のみ計算 (他球団は 0 で list 化、 表示時
    に注記)。
    """
    start, end = _scope_window(scope)
    row = conn.execute(
        "SELECT SUM(giants_score), SUM(opp_score) FROM games "
        "WHERE game_date >= ? AND game_date <= ? "
        "AND giants_score IS NOT NULL AND opp_score IS NOT NULL",
        (start, end),
    ).fetchone()
    gscore, oscore = row if row else (0, 0)
    diff = int(gscore or 0) - int(oscore or 0)
    # 巨人のみ実値、 他球団は schema 制約で 0 (display 側で「不明」と扱う)
    return [{"team": tc, "value": diff if tc == "g" else 0} for tc in CENTRAL_TEAMS]


def aggregate_team_winning_streak(conn: sqlite3.Connection) -> dict:
    """巨人の現在の連勝/連敗を games table の result から計算 (348 step 3 part 2)。

    return: {"team": "g", "streak": int, "kind": "win" | "loss" | "none"}
    最近の試合から逆順で同 result が続く回数を count。
    """
    rows = conn.execute(
        "SELECT result FROM games "
        "WHERE result IS NOT NULL AND result != 'unknown' "
        "ORDER BY game_date DESC LIMIT 30",
    ).fetchall()
    if not rows:
        return {"team": "g", "streak": 0, "kind": "none"}
    first = (rows[0][0] or "").lower()
    if first not in ("win", "loss"):
        return {"team": "g", "streak": 0, "kind": "none"}
    streak = 0
    for r in rows:
        if (r[0] or "").lower() == first:
            streak += 1
        else:
            break
    return {"team": "g", "streak": streak, "kind": first}


def aggregate_team_vs_opponent(
    conn: sqlite3.Connection, *, opponent: str, scope: str,
) -> dict:
    """巨人 vs 指定対戦相手 の W-L 集計 (348 step 3 part 2)。

    return: {"opponent": <str>, "W": int, "L": int, "T": int, "scope": <str>}
    """
    start, end = _scope_window(scope)
    rows = conn.execute(
        "SELECT result FROM games "
        "WHERE game_date >= ? AND game_date <= ? "
        "AND opponent = ? AND result IS NOT NULL",
        (start, end, opponent),
    ).fetchall()
    w = l = t = 0
    for (r,) in rows:
        rl = (r or "").lower()
        if rl == "win":
            w += 1
        elif rl == "loss":
            l += 1
        elif rl == "draw":
            t += 1
    return {"opponent": opponent, "W": w, "L": l, "T": t, "scope": scope}


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

    # 2026-05-15 user 指示「期間は末尾に」適用、日時 prefix なし、scope を
    # title 末尾に括弧書き。集計期間は body 内「集計期間」row にも記載。
    title = (
        f"【巨人データ】セ・リーグ球団{metric_label}、巨人 {giants_rank}/6 位 "
        f"{giants_val_str} ({scope_label})"
    )

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
    # NEWS-BANNER-FIX-2026-05-15: team ranking 記事も赤紫グラデ banner を冒頭に
    # prepend し、全 publish 経路で content の先頭に banner が立つ状態を維持。
    _banner = _giants_news_banner_html(
        article["title"], rap._BANNER_SOURCE_LABEL, category_name
    )
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=_banner + article["body_html"],
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


def render_team_streak_article(conn: sqlite3.Connection) -> Optional[dict]:
    """巨人の連勝/連敗 streak 記事を render (348 step 3 part 2 D-2)。

    streak >= 3 で記事化、 それ未満は None で skip。
    """
    s = aggregate_team_winning_streak(conn)
    streak = int(s.get("streak", 0))
    kind = s.get("kind", "none")
    if streak < 3 or kind not in ("win", "loss"):
        return None
    kind_label = "連勝" if kind == "win" else "連敗"
    today = dt.date.today().isoformat()
    title = f"【巨人データ】チーム {streak} {kind_label} ({today} 時点)"
    body_md = f"""# {title}

## ひとこと

巨人は直近 **{streak} 試合連続{kind_label}** ({today} 時点)。

## このデータについて

| 項目 | 内容 |
|---|---|
| 球団 | **巨人** |
| 状況 | {streak} {kind_label} |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計基準 | 最新試合から逆順 scan で同 result が連続している試合数 |
| 計算式 | games.result を最新から逆順 scan、 同 kind が break するまで count |
| 注 | 中止 / 中断試合は含めない |
"""
    body_html = rap.markdown_to_html(body_md)
    return {
        "title": title,
        "body_md": body_md,
        "body_html": body_html,
        "streak": streak,
        "kind": kind,
    }


def publish_team_streak_draft(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    category_name: str = DEFAULT_CATEGORY_NAME,
    dry_run: bool = False,
) -> dict:
    article = render_team_streak_article(conn)
    if article is None:
        return {"status": "skip", "reason": "no_active_streak"}
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
    publish_status = rap._resolve_publish_status(focus_team_code="g")
    _banner = _giants_news_banner_html(
        article["title"], rap._BANNER_SOURCE_LABEL, category_name
    )
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=_banner + article["body_html"],
            categories=[category_id],
            status=publish_status,
            caller="team_ranking_publisher_streak",
        )
        return {
            "status": "published" if publish_status == "publish" else "published_draft",
            "title": article["title"],
            "post_id": int(post_id or 0),
        }
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def publish_team_default_set(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    max_per_run: int = 100,
    dry_run: bool = False,
) -> list[dict]:
    """デフォルト team metric publish set。
    2026-05-15 user 指示「データサイト化、上限なし」適用、3 → 100 (実質 cap 無し)。
    """
    default_jobs = [
        # 開幕から (season)
        {"metric": "HR", "scope": "season"},
        {"metric": "AVG", "scope": "season"},
        {"metric": "ERA", "scope": "season"},
        # 月間 (last_30d)
        {"metric": "HR", "scope": "last_30d"},
        {"metric": "AVG", "scope": "last_30d"},
        {"metric": "ERA", "scope": "last_30d"},
        # 週間 (last_7d)
        {"metric": "HR", "scope": "last_7d"},
        {"metric": "AVG", "scope": "last_7d"},
        {"metric": "ERA", "scope": "last_7d"},
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
    # 348 step 3 part 2 D-2: streak article (active >= 3 連勝/連敗 時のみ)
    if published < max_per_run:
        streak_r = publish_team_streak_draft(conn, wp_client_obj, dry_run=dry_run)
        results.append(streak_r)
    return results
