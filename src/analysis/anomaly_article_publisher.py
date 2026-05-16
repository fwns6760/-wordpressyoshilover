"""DATA-INSIGHT-continuous: anomaly / 「気づかない pattern」記事を WP draft 投入.

`insight_anomaly_detector` が emit した `article_candidates` row から
本文を構築、`wp_client.create_post(status='draft')` で WP に landed する。

設計方針:
  * pure rule-based、LLM 不使用
  * `status='draft'` 固定 (auto-publish は env flag gate、本 module 範囲外)
  * 既存 `wp_client.find_recent_post_by_title` の dedup を活用 (idempotent)
  * 1 trigger あたり `DATA_INSIGHT_PUBLISH_MAX_PER_RUN` (default 3) で
    暴走防止
  * 投入後 `article_candidates.status` を 'DRAFTED' に更新 (再 publish 防止)

Hard constraints (work record §7):
  * env / secret / scheduler 一切 touch しない
  * X 自動投稿 / 既存 publish post mutation しない
  * LLM call を path に混入させない
  * `status='draft'` 以外を許容しない
  * 「データで見る巨人」category 以外への投入は許容しない
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import insight_anomaly_detector as detector  # noqa: E402
from src.analysis import insight_dedup_gate as dedup_gate  # noqa: E402
from src.analysis import insight_quality_gate as quality_gate  # noqa: E402
from src.analysis import insight_title_guard as title_guard  # noqa: E402
from src.analysis import insight_whitelist as _wl  # noqa: E402
from src.analysis import ranking_article_publisher as rap  # noqa: E402
from src.giants_news_banner import (  # noqa: E402
    giants_news_banner_html as _giants_news_banner_html,
)

DEFAULT_CATEGORY_NAME = rap.DEFAULT_CATEGORY_NAME

DEFAULT_MAX_PER_RUN = int(
    os.environ.get("DATA_INSIGHT_PUBLISH_MAX_PER_RUN", "3") or "3"
)


# ─── ranking context helper (大城式の table を全 anomaly 記事に共通化) ─────

# リーグ別 team_code 分類 (user 指示「セ/パ で別 ranking」)
CENTRAL_TEAMS = frozenset({"g", "t", "s", "c", "db", "d"})
PACIFIC_TEAMS = frozenset({"h", "l", "m", "e", "b", "f"})


def _league_for_team(team_code: Optional[str]) -> str:
    """team_code から 'central' / 'pacific' / 'unknown' を返す."""
    code = (team_code or "").strip()
    if code in CENTRAL_TEAMS:
        return "central"
    if code in PACIFIC_TEAMS:
        return "pacific"
    return "unknown"


def _league_label(league: str) -> str:
    return {"central": "セ・リーグ", "pacific": "パ・リーグ"}.get(league, "リーグ")


def _league_team_filter(league: str) -> list[str]:
    if league == "central":
        return list(CENTRAL_TEAMS)
    if league == "pacific":
        return list(PACIFIC_TEAMS)
    return []


# lower-is-better metric (rank 計算で ASC sort)
_LOWER_IS_BETTER_METRICS = frozenset({
    "ERA", "WHIP", "FIP", "xFIP", "BB_per_9", "HR_per_9",
})


def _is_higher_better(metric_name: str) -> bool:
    return metric_name not in _LOWER_IS_BETTER_METRICS


def _fetch_ranking_context(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    scope: str,
    snapshot_date: Optional[str] = None,
    top_n: int = 10,
    league: Optional[str] = None,
) -> tuple[list[dict[str, Any]], int]:
    """ranking 上位 ``top_n`` + total league size を返す.

    ``league`` 指定時はそのリーグ内のみで rank 再計算 (db 取得後 sort)。
    """
    if snapshot_date is None:
        latest = conn.execute(
            "SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
            "WHERE metric_name = ? AND scope = ?",
            (metric_name, scope),
        ).fetchone()
        snapshot_date = latest[0] if latest else None
    if not snapshot_date:
        return ([], 0)
    teams = _league_team_filter(league or "")
    order = "ASC" if not _is_higher_better(metric_name) else "DESC"
    if teams:
        placeholders = ",".join("?" * len(teams))
        rows = conn.execute(
            f"SELECT player_canonical, team_code, metric_value, sample_size "
            f"FROM advanced_metric_snapshots "
            f"WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
            f"AND team_code IN ({placeholders}) AND metric_value IS NOT NULL "
            f"ORDER BY metric_value {order}",
            (metric_name, scope, snapshot_date, *teams),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT player_canonical, team_code, metric_value, sample_size "
            f"FROM advanced_metric_snapshots "
            f"WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
            f"AND metric_value IS NOT NULL "
            f"ORDER BY metric_value {order}",
            (metric_name, scope, snapshot_date),
        ).fetchall()
    total = len(rows)
    result = []
    for i, (player, team, value, sample) in enumerate(rows[:top_n], start=1):
        result.append({
            "rank": i, "player": player, "team": team or "?",
            "value": float(value) if value is not None else None,
            "sample": int(sample or 0), "total": total,
        })
    return (result, total)


def _find_player_rank(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    scope: str,
    snapshot_date: Optional[str],
    player_canonical: str,
    league: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """指定 player の rank / value / sample を league filtered で取得."""
    if snapshot_date is None:
        latest = conn.execute(
            "SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
            "WHERE metric_name = ? AND scope = ?",
            (metric_name, scope),
        ).fetchone()
        snapshot_date = latest[0] if latest else None
    if not snapshot_date:
        return None
    teams = _league_team_filter(league or "")
    order = "ASC" if not _is_higher_better(metric_name) else "DESC"
    if teams:
        placeholders = ",".join("?" * len(teams))
        rows = conn.execute(
            f"SELECT player_canonical, team_code, metric_value, sample_size "
            f"FROM advanced_metric_snapshots "
            f"WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
            f"AND team_code IN ({placeholders}) AND metric_value IS NOT NULL "
            f"ORDER BY metric_value {order}",
            (metric_name, scope, snapshot_date, *teams),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT player_canonical, team_code, metric_value, sample_size "
            f"FROM advanced_metric_snapshots "
            f"WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
            f"AND metric_value IS NOT NULL "
            f"ORDER BY metric_value {order}",
            (metric_name, scope, snapshot_date),
        ).fetchall()
    total = len(rows)
    for i, (p, t, v, s) in enumerate(rows, start=1):
        if p == player_canonical:
            return {
                "rank": i, "team": t or "?",
                "value": float(v) if v is not None else None,
                "sample": int(s or 0), "total": total,
            }
    return None


def _render_ranking_table_md(
    top_rows: list[dict[str, Any]],
    *,
    focus_player: str,
    metric_label: str,
    extra_focus_row: Optional[dict[str, Any]] = None,
) -> str:
    """ranking table の markdown を構築 (top_n 行 + 圏外時は ``extra_focus_row`` 追加)."""
    lines = [
        f"| 順位 | 選手 | チーム | {metric_label} | サンプル |",
        "|---|---|---|---|---|",
    ]
    # 赤太字 wrapper (user 指示「該当選手は赤太文字」、WP は HTML 直書き OK)
    def _red_bold(text: str) -> str:
        return f'<span style="color:#c0392b"><strong>{text}</strong></span>'

    focus_in_top = any(r["player"] == focus_player for r in top_rows)
    for r in top_rows:
        is_focus = (r["player"] == focus_player)
        marker = " ★" if is_focus else ""
        val = f"{r['value']:.3f}" if r["value"] is not None else "-"
        team_display = _team_label(r["team"])
        if is_focus:
            rank_disp = _red_bold(str(r["rank"]))
            player_disp = _red_bold(f"{r['player']}{marker}")
            team_disp_cell = _red_bold(team_display)
            val_disp = _red_bold(val)
            sample_disp = _red_bold(str(r["sample"]))
        else:
            rank_disp = str(r["rank"])
            player_disp = r["player"]
            team_disp_cell = team_display
            val_disp = val
            sample_disp = str(r["sample"])
        lines.append(f"| {rank_disp} | {player_disp} | {team_disp_cell} | {val_disp} | {sample_disp} |")
    if not focus_in_top and extra_focus_row:
        val = f"{extra_focus_row['value']:.3f}" if extra_focus_row["value"] is not None else "-"
        team_display = _team_label(extra_focus_row["team"])
        lines.append("| ... | ... | ... | ... | ... |")
        lines.append(
            f"| {_red_bold(str(extra_focus_row['rank']))} | {_red_bold(focus_player + ' ★')} | "
            f"{_red_bold(team_display)} | {_red_bold(val)} | {_red_bold(str(extra_focus_row['sample']))} |"
        )
    return "\n".join(lines)


def _human_metric_label(metric_name: str) -> str:
    """348 step 2: config JSON (insight_whitelist) 経由で日本語化。

    K_per_9 → 奪三振率, BB_per_9 → 与四球率, HR_per_9 → 被本塁打率,
    WIN_PCT → 勝率, FIELDING_PCT → 守備率, RISP → 得点圏打率。
    OPS のみ英略号のまま。

    config 不在時 or mapping 不在時は既存 fallback (× metric の internal
    display 用、 publish されない経路でも label 維持)。
    """
    label = _wl.metric_name_ja(metric_name)
    if label != metric_name:
        return label
    return {
        "wOBA": "加重出塁率", "ISO": "純長打率", "BABIP": "インプレー打率",
        "FIP": "守備非依存防御率", "WHIP": "1イニングあたり被出塁数",
        "K_BB": "奪三振/与四球比",
    }.get(metric_name, metric_name)


def _metric_formula(metric_name: str) -> str:
    """各 metric の簡易計算式 (記事末尾の補足セクション用)."""
    return {
        "OPS": "出塁率(OBP) + 長打率(SLG)",
        "AVG": "安打数 ÷ 打数",
        "OBP": "(安打 + 四球 + 死球) ÷ (打数 + 四球 + 死球 + 犠飛)",
        "SLG": "(単打 + 2塁打×2 + 3塁打×3 + 本塁打×4) ÷ 打数",
        "wOBA": "(0.69×BB + 0.72×HBP + 0.89×1B + 1.27×2B + 1.62×3B + 2.10×HR) ÷ 打席",
        "ISO": "SLG - AVG (純粋な長打力)",
        "BABIP": "(安打 - 本塁打) ÷ (打数 - 本塁打 - 三振 + 犠飛)",
        "ERA": "(自責点 × 9) ÷ 投球回",
        "FIP": "((13×HR + 3×(BB+HBP) - 2×K) ÷ IP) + リーグ定数(約3.10)",
        "WHIP": "(被安打 + 四球) ÷ 投球回",
        "K_per_9": "(奪三振 × 9) ÷ 投球回",
        "BB_per_9": "(与四球 × 9) ÷ 投球回",
        "HR_per_9": "(被本塁打 × 9) ÷ 投球回",
        "K_BB": "奪三振 ÷ 与四球",
    }.get(metric_name, f"{metric_name} 標準計算式")


def _human_metric_explain(metric_name: str) -> str:
    return {
        "OPS": "出塁率と長打率を足した、打者の総合打撃指標(0.800 超で好打者)。",
        "AVG": "打率、打席で安打を打つ確率。",
        "wOBA": "得点期待値ベースの打撃指標、OPS より精度高。0.350 超で好打者。",
        "ISO": "純粋な長打力(SLG - AVG)。0.200 超で長距離砲級。",
        "BABIP": "本塁打を除く打球が安打になる確率、長期平均は 0.300 付近。",
        "ERA": "9 イニング換算の自責点。投手の代表的失点指標。",
        "FIP": "本塁打 / 四球 / 三振から算出する投手指標、守備と運を除いた本人の実力に近い。",
        "WHIP": "1 イニングあたりの (被安打+四球) 数。1.20 以下で好投手級。",
        "K_per_9": "9 イニング換算の奪三振数。",
    }.get(metric_name, f"{metric_name} に関する sabermetric 指標。")


# ─── article rendering ──────────────────────────────────────────────────────


def _team_label(team_code: Optional[str]) -> str:
    mapping = {
        "g": "巨人", "t": "阪神", "s": "ヤクルト", "c": "広島",
        "db": "DeNA", "d": "中日", "h": "ソフトバンク", "l": "西武",
        "m": "ロッテ", "e": "楽天", "b": "オリックス", "f": "日本ハム",
    }
    return mapping.get((team_code or "").strip(), team_code or "?")


def _player_team_code(conn: sqlite3.Connection, player_canonical: str) -> Optional[str]:
    row = conn.execute(
        "SELECT team_code FROM players WHERE player_canonical = ? AND active = 1",
        (player_canonical,),
    ).fetchone()
    return row[0] if row else None


def _render_unified_article(
    conn: sqlite3.Connection,
    *,
    player: str,
    team_code: str,
    metric_name: str,
    scope: str,
    title_template: str,
    why_notable_text: str,
    extra_note: Optional[str] = None,
    simple_explanation: Optional[str] = None,
) -> dict[str, str]:
    """全 anomaly 記事の統一形式 (大城式 ranking 表 + 平易な日本語).

    - title: 与えられた template から
    - lead: 1 sentence、何が凄いかを冒頭で
    - データで見ると: 12 球団 top 10 ranking 表 + 該当選手 highlight (圏外時は別行)
    - なぜ凄いか: 平易な日本語の説明 (why_notable_text)
    - 補足: metric の意味 (1 行)
    """
    team = _team_label(team_code)
    league = _league_for_team(team_code)
    league_label = _league_label(league)

    # title 用 short scope label。config の日本語表記に寄せ、raw scope code は
    # title に出さない。
    scope_label = title_guard.period_label_for_scope(scope) or scope

    # footer 用 具体 date range (title には出さず、本文 footer のみ)
    import datetime as _dt
    today = _dt.date.today()
    if scope == "last_7d":
        start_d = today - _dt.timedelta(days=6)
    elif scope == "last_30d":
        start_d = today - _dt.timedelta(days=29)
    elif scope == "season":
        start_d = _dt.date(today.year, 3, 27)
    elif scope == "monthly":
        # 348 step 3: 当月 1 日から
        start_d = today.replace(day=1)
    elif scope == "weekly":
        # 348 step 3: ISO 週月曜から
        start_d = today - _dt.timedelta(days=today.weekday())
    else:
        # last_5_games / last_10_games / unknown は today から (per-player rolling は
        # footer 表示用なので近似で OK、 厳密 date range は本文ranking表から読める)
        start_d = today
    period_full_label = f"{start_d.isoformat()} 〜 {today.isoformat()}"

    metric_label = _human_metric_label(metric_name)
    metric_explain = _human_metric_explain(metric_name)

    # ranking context fetch (league filter: セ vs パ 別 ranking)
    top_rows, league_total = _fetch_ranking_context(
        conn, metric_name=metric_name, scope=scope, top_n=10, league=league,
    )
    player_rank_info = _find_player_rank(
        conn, metric_name=metric_name, scope=scope,
        snapshot_date=None, player_canonical=player, league=league,
    )

    value_str = "-"
    rank_str = "-"
    if player_rank_info:
        v = player_rank_info["value"]
        value_str = f"{v:.3f}" if v is not None else "-"
        rank_str = f"{player_rank_info['rank']}/{player_rank_info['total']}"

    extra_focus = None
    if player_rank_info and not any(r["player"] == player for r in top_rows):
        extra_focus = player_rank_info
        extra_focus["player"] = player

    # 2026-05-15 user 指示「人間にわかりやすいタイトル」適用、title には
    # 日時 prefix を入れない (集計日時は body の 集計期間 row に表記)。
    # 同 title 重複時は wp_client.create_post の reuse 機構に委ねる。
    title = title_template.format(
        player=player, team=team, metric=metric_label,
        value=value_str, rank=rank_str, scope=scope_label,
        league=league_label,
    )
    title_check = title_guard.ensure_title_period(title, scope=scope)
    if title_check.ok:
        title = title_check.title

    ranking_table = _render_ranking_table_md(
        top_rows, focus_player=player, metric_label=metric_label,
        extra_focus_row=extra_focus,
    )

    sample_str = str(player_rank_info['sample']) if player_rank_info else '-'
    simple_line = simple_explanation or why_notable_text or ""
    # 1 文目だけに truncate (素人向け 1-2 line max)
    simple_line = simple_line.split("。")[0] + ("。" if simple_line else "")

    # 348 step 3 spec §2.5: 「大手にない」 banner 廃止 (全種類で省略)。
    # 同じ lock で SVG chart も廃止。本文は表形式だけで構成する。
    intro_banner = ""

    body_md = f"""# {title}

{intro_banner}

## ひとこと

{simple_line}

## {league_label} ranking({scope_label})

{ranking_table}

## このデータについて

| 項目 | 内容 |
|---|---|
| 選手 | **{player}({team})** / サンプル {sample_str} |
| 指標 | {metric_label} = **{value_str}** / {league_label} **{rank_str} 位** |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計期間 | {period_full_label} |
| 計算式 | {_metric_formula(metric_name)} |
| 比較 | この期間の {league_label} 内 全選手 |
"""
    return {"title": title, "body_md": body_md}


def render_zscore_batter_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """`anomaly_zscore_outlier_batter` を記事化 (大城式)."""
    player = candidate_row["player_canonical"]
    current = candidate_row["current_value"]
    team_code = _player_team_code(conn, player) or "?"
    metric_name = "OPS"
    if "=" in current:
        try:
            metric_name = current.split("=", 1)[0].strip()
        except Exception:
            pass
    metric_label = _human_metric_label(metric_name)
    title_template = f"【巨人データ】{{player}}、{metric_label}{{value}}で{{league}}{{rank}}位（{{scope}}）"
    why_text = f"リーグ平均より明確に高い数字で、12 球団中の上位群に入っています。"
    simple = f"リーグ全体で見て上位の {metric_label} を記録、好調と言える数字です。"
    return _render_unified_article(
        conn, player=player, team_code=team_code, metric_name=metric_name,
        scope="last_30d", title_template=title_template,
        why_notable_text=why_text, simple_explanation=simple,
    )


def render_zscore_pitcher_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    player = candidate_row["player_canonical"]
    current = candidate_row["current_value"]
    team_code = _player_team_code(conn, player) or "?"
    metric_name = "ERA"
    if "=" in current:
        try:
            metric_name = current.split("=", 1)[0].strip()
        except Exception:
            pass
    metric_label = _human_metric_label(metric_name)
    title_template = f"【巨人データ】{{player}}、{metric_label}{{value}}で{{league}}{{rank}}位（{{scope}}）"
    why_text = f"投手として league 上位群の数字、平均的なローテ投手より明確に良い投球内容です。"
    simple = f"リーグ全体で見て上位の投手、好投が data で明確です。"
    return _render_unified_article(
        conn, player=player, team_code=team_code, metric_name=metric_name,
        scope="season", title_template=title_template,
        why_notable_text=why_text, simple_explanation=simple,
    )


def render_babip_divergence_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> Optional[dict[str, str]]:
    """打率 vs BABIP 乖離 = 運要素 / 実力の差を可視化."""
    if not _wl.is_metric_allowed("BABIP"):
        return None
    player = candidate_row["player_canonical"]
    diff = candidate_row["magnitude"]
    baseline = candidate_row["baseline_value"]
    current = candidate_row["current_value"]
    team_code = _player_team_code(conn, player) or "?"

    # AVG / BABIP 数値抽出 (baseline_value = "AVG=0.358", current_value = "BABIP=0.420")
    def _extract_value(text: str, key: str) -> str:
        if not text:
            return "-"
        for part in text.split():
            if part.startswith(f"{key}="):
                return part.split("=", 1)[1]
        return "-"
    avg_str = _extract_value(baseline, "AVG")
    babip_str = _extract_value(current, "BABIP")

    notable_phrase = f"打率 {avg_str} / BABIP {babip_str}(差 {diff:+.3f})"
    if diff > 0:
        why_text = (
            f"打率(AVG)と BABIP(打球が安打になる確率)を比べると、BABIP が "
            f"**+{diff:.3f}** 高い数字です。BABIP は long-run でリーグ平均 0.300 付近に "
            f"近づく性質があるため、シーズン後半で打率が下がる可能性があります。"
        )
        simple = f"打率に対し BABIP が大きく、シーズン後半で打率が下がる可能性のあるデータです。"
    else:
        why_text = (
            f"打率(AVG)と BABIP の差が **{diff:.3f}** で BABIP が低い数字です。"
            f"BABIP は long-run でリーグ平均 0.300 付近に近づくため、打率が上昇する可能性があります。"
        )
        simple = f"打率に対し BABIP が小さく、シーズン後半で打率が上がる可能性のあるデータです。"

    title_template = f"【巨人データ】{{player}}、{notable_phrase} ({{scope}})"
    return _render_unified_article(
        conn, player=player, team_code=team_code, metric_name="AVG",
        scope="last_30d", title_template=title_template,
        why_notable_text=why_text, simple_explanation=simple,
    )


def render_fip_era_divergence_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> Optional[dict[str, str]]:
    """防御率 vs FIP 乖離 = 運に支えられた数字 / 本質指標."""
    if not _wl.is_metric_allowed("FIP"):
        return None
    player = candidate_row["player_canonical"]
    diff = candidate_row["magnitude"]
    baseline = candidate_row["baseline_value"]
    current = candidate_row["current_value"]
    team_code = _player_team_code(conn, player) or "?"

    def _extract_value(text: str, key: str) -> str:
        if not text:
            return "-"
        for part in text.split():
            if part.startswith(f"{key}="):
                return part.split("=", 1)[1]
        return "-"
    era_str = _extract_value(baseline, "ERA")
    fip_str = _extract_value(current, "FIP")

    notable_phrase = f"防御率 {era_str} / FIP {fip_str}(差 {diff:+.3f})"
    if diff > 0:
        why_text = (
            f"防御率(ERA、低いほど良い指標)が **{era_str}** に対し、"
            f"FIP(投手本人の実力指標、低いほど良い)は **{fip_str}** と高い数字です。"
            f"FIP は守備や運の影響を排除した本人の指標で、long-run では ERA がこの数字に近づく傾向があります。"
        )
        simple = f"防御率は FIP より良い数字。シーズン後半に防御率が悪化する可能性のあるデータです。"
    else:
        why_text = (
            f"防御率(ERA、低いほど良い指標)が **{era_str}** に対し、"
            f"FIP(投手本人の実力指標)は **{fip_str}** と低い(良い)数字です。"
            f"FIP は守備や運の影響を排除した本人の指標で、long-run では ERA がこの数字に近づく傾向があります。"
        )
        simple = f"防御率は FIP より悪い数字。シーズン後半に防御率が改善する可能性のあるデータです。"

    title_template = f"【巨人データ】{{player}}、{notable_phrase} ({{scope}})"
    return _render_unified_article(
        conn, player=player, team_code=team_code, metric_name="ERA",
        scope="season", title_template=title_template,
        why_notable_text=why_text, simple_explanation=simple,
    )


def render_giants_top_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """巨人選手で league top X% 以内 (大城式の延長、metric 自動推定)."""
    player = candidate_row["player_canonical"]
    pct = candidate_row["magnitude"]
    current = candidate_row["current_value"]
    team_code = _player_team_code(conn, player) or "g"

    # parse metric from current_value (e.g., "OPS=0.93 rank=12 sample=57")
    metric_name = "OPS"
    if "=" in current:
        try:
            metric_name = current.split("=", 1)[0].strip()
        except Exception:
            pass
    metric_label = _human_metric_label(metric_name)

    title_template = f"【巨人データ】{{player}}、{metric_label}{{value}}で{{league}}{{rank}}位（{{scope}}）"
    why_text = f"巨人選手がリーグ上位に入っている好調を示すデータです。"
    simple = f"巨人選手として、リーグ全体の上位に入っている好調な状態です。"
    scope = "last_30d" if metric_name in ("OPS", "AVG", "wOBA", "BABIP") else "season"
    return _render_unified_article(
        conn, player=player, team_code=team_code, metric_name=metric_name,
        scope=scope, title_template=title_template,
        why_notable_text=why_text, simple_explanation=simple,
    )


# ─── 2026-05-15 追加 renderer (取りこぼし 3 種 + 守備 2 種) ─────────────────
# user 指示「上限なし、閾値を超えたものは全部出す」「守備もだよ」適用。
# 既存は 5 種だけ renderer 有り → 残 3 signal type (HR pace / 規定外好調 /
# 連続多安打) と新規 2 種 (守備 UZR / 守備率) を記事化対応。


def _render_box_score_article(
    *,
    title: str,
    headline: str,
    box_table_rows: list[tuple[str, str]],
    period_label: str,
    source_note: str,
) -> dict[str, str]:
    """box score 表形式 layout (348 step 3 完全達成 D-4)。

    `_render_simple_data_article` の bullet list を 表形式 (key/value table)
    に置き換えた variant。 試合後イベント / record event の詳細 stat 表示用。
    """
    title_check = title_guard.ensure_title_period(title, period_label=period_label)
    if title_check.ok:
        title = title_check.title
    # 348 step 3 spec §2.5: 「大手にない」 banner 廃止 (全種類で省略)。
    intro_banner = ""
    table_lines = ["| 項目 | 数値 |", "|---|---|"]
    for label, value in box_table_rows:
        table_lines.append(f"| {label} | {value} |")
    box_md = "\n".join(table_lines)
    body_md = f"""# {title}

{intro_banner}

## ひとこと

{headline}

## box score 抜粋

{box_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 集計期間 | {period_label} |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 計算式 | box score 抜粋行を集計 |
| 注意点 | {source_note} |
"""
    return {"title": title, "body_md": body_md}


def _render_simple_data_article(
    *,
    title: str,
    headline: str,
    detail_lines: list[str],
    period_label: str,
    source_note: str,
) -> dict[str, str]:
    """ranking table を持たないシンプルな data 記事 body を組み立てる helper。

    title / headline / detail_lines / period_label / source_note の組合せで
    短い記事 body (banner + ひとこと + 詳細 list + データ元) を返す。

    `_render_unified_article` の league ranking が無くてもデータの「なぜ
    特筆すべきか」が伝わる構成 (HR pace / 守備系 等)。

    2026-05-15 user 指示「人間にわかりやすいタイトル」適用、title には日時
    prefix を入れない (集計日時は body の 集計期間 row に表記)。
    """
    title_check = title_guard.ensure_title_period(title, period_label=period_label)
    body_title = title_check.title if title_check.ok else title
    # 348 step 3 spec §2.5: 「大手にない」 banner 廃止 (全種類で省略)。
    intro_banner = ""
    detail_md = _detail_lines_to_table_md(detail_lines)
    body_md = f"""# {body_title}

{intro_banner}

## ひとこと

{headline}

## データ

{detail_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 集計期間 | {period_label} |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 計算式 | 詳細行と注意点を参照 |
| 注意点 | {source_note} |
"""
    return {"title": body_title, "body_md": body_md}


def _detail_lines_to_table_md(detail_lines: list[str]) -> str:
    """Convert simple ``label: value`` details into a reader-friendly table.

    User policy (2026-05-16): data articles should be table-first, not
    bullet-first, so readers can compare numbers quickly.
    """
    lines = ["| 項目 | 数値 |", "|---|---|"]
    for raw in detail_lines:
        item = str(raw or "").strip()
        if not item:
            continue
        if ":" in item:
            label, value = item.split(":", 1)
        elif "：" in item:
            label, value = item.split("：", 1)
        else:
            label, value = "要点", item
        lines.append(f"| {label.strip()} | {value.strip()} |")
    return "\n".join(lines)


def _extract_kv_value(text: str, key: str) -> str:
    for token in (text or "").split():
        if token.startswith(f"{key}="):
            return token.split("=", 1)[1]
    return ""


def _format_stat_value(raw_value: str, *, decimals: int = 3) -> str:
    if not raw_value:
        return "-"
    try:
        return f"{float(raw_value):.{decimals}f}"
    except ValueError:
        return raw_value


def _defense_position_label(position: str) -> str:
    mapping = {
        "投": "投手",
        "捕": "捕手",
        "一": "一塁",
        "二": "二塁",
        "三": "三塁",
        "遊": "遊撃",
        "左": "左翼",
        "中": "中堅",
        "右": "右翼",
    }
    base = mapping.get(position, position)
    return f"{base}守備" if base else "守備"


def _average_comparison_phrase(diff: float) -> str:
    return "守備位置平均を上回る" if diff >= 0 else "守備位置平均を下回る"


def _latest_game_date(conn: sqlite3.Connection) -> Optional[dt.date]:
    row = conn.execute(
        "SELECT MAX(game_date) FROM games WHERE game_date IS NOT NULL"
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return dt.date.fromisoformat(str(row[0]))
    except ValueError:
        return None


def _defense_team_comparison_rows(
    conn: Optional[sqlite3.Connection],
    *,
    position: str,
    metric: str,
    days: int = 30,
) -> tuple[list[dict[str, Any]], str, str]:
    """Return セ・リーグ team comparison rows for defense metrics.

    ``UZR_proxy`` is a team-level proxy here:
    team converted-out rate minus セ・リーグ baseline for the same
    position and window. It is still not true UZR; the article note
    explains the limitation.
    """
    if conn is None or not position:
        return [], "", ""
    latest = _latest_game_date(conn)
    if latest is None:
        return [], "", ""
    since = latest - dt.timedelta(days=max(days - 1, 0))
    raw_rows = conn.execute(
        "SELECT d.team_code, SUM(d.opportunities), SUM(d.converted_outs), "
        "SUM(d.errors) "
        "FROM defense_opportunities d "
        "JOIN games g ON g.game_id = d.game_id "
        "WHERE d.position = ? "
        "AND g.game_date >= ? AND g.game_date <= ? "
        "AND d.team_code IN ('g','t','s','c','db','d') "
        "GROUP BY d.team_code",
        (position, since.isoformat(), latest.isoformat()),
    ).fetchall()
    if not raw_rows:
        return [], since.isoformat(), latest.isoformat()

    league_opps = sum(int(r[1] or 0) for r in raw_rows)
    league_outs = sum(int(r[2] or 0) for r in raw_rows)
    baseline = (league_outs / league_opps) if league_opps else 0.0
    out: list[dict[str, Any]] = []
    for team_code, opps, outs, errors in raw_rows:
        opps_i = int(opps or 0)
        outs_i = int(outs or 0)
        errors_i = int(errors or 0)
        if opps_i <= 0:
            continue
        out_rate = outs_i / opps_i
        if metric == "FIELDING_PCT":
            denom = outs_i + errors_i
            value = (outs_i / denom) if denom else 0.0
        else:
            value = out_rate - baseline
        out.append({
            "team": team_code,
            "value": round(value, 4),
            "opportunities": opps_i,
            "converted_outs": outs_i,
            "out_rate": round(out_rate, 4),
        })
    out.sort(key=lambda r: r["value"], reverse=True)
    for idx, row in enumerate(out, start=1):
        row["rank"] = idx
        row["total"] = len(out)
    return out, since.isoformat(), latest.isoformat()


def _format_signed(value: float) -> str:
    return f"{value:+.3f}"


def _render_defense_team_table_md(
    rows: list[dict[str, Any]],
    *,
    metric_label: str,
    signed_value: bool,
) -> str:
    lines = [
        f"| 順位 | 球団 | {metric_label} | 守備機会 | アウト化率 |",
        "|---|---|---|---|---|",
    ]

    def _red_bold(text: str) -> str:
        return f'<span style="color:#c0392b"><strong>{text}</strong></span>'

    for row in rows:
        team = _team_label(row.get("team"))
        rank = str(row.get("rank"))
        val = (
            _format_signed(float(row.get("value") or 0.0))
            if signed_value else f"{float(row.get('value') or 0.0):.3f}"
        )
        opps = str(int(row.get("opportunities") or 0))
        out_rate = f"{float(row.get('out_rate') or 0.0):.3f}"
        if row.get("team") == "g":
            rank = _red_bold(rank)
            team = _red_bold(f"{team} ★")
            val = _red_bold(val)
            opps = _red_bold(opps)
            out_rate = _red_bold(out_rate)
        lines.append(f"| {rank} | {team} | {val} | {opps} | {out_rate} |")
    return "\n".join(lines)


def _render_defense_team_comparison_article(
    conn: Optional[sqlite3.Connection],
    *,
    player: str,
    position: str,
    metric: str,
    metric_label: str,
    source_note: str,
) -> Optional[dict[str, str]]:
    rows, since, until = _defense_team_comparison_rows(
        conn, position=position, metric=metric, days=30,
    )
    if len(rows) < 4:
        return None
    giants = next((r for r in rows if r["team"] == "g"), None)
    if not giants:
        return None
    position_label = _defense_position_label(position)
    signed_value = metric == "UZR_proxy"
    value_str = (
        _format_signed(float(giants["value"]))
        if signed_value else f"{float(giants['value']):.3f}"
    )
    title = (
        f"【巨人データ】{player}の{position_label}、"
        f"{metric_label} {value_str}で巨人{giants['rank']}/{giants['total']}位（直近30日）"
    )
    title_check = title_guard.ensure_title_period(title, period_label="直近30日")
    if title_check.ok:
        title = title_check.title
    table_md = _render_defense_team_table_md(
        rows, metric_label=metric_label, signed_value=signed_value,
    )
    body_md = f"""# {title}

## ひとこと

巨人の{position_label}の{metric_label}は、セ・リーグ{giants['total']}球団中 **{giants['rank']}位**({value_str})。

## セ・リーグ球団別ランキング（{position_label}・直近30日）

{table_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 球団 | **巨人** / セ・リーグ {giants['rank']}/{giants['total']}位 |
| 指標 | {metric_label} = **{value_str}** |
| 関連した巨人選手 | {player} |
| 守備位置 | {position_label} |
| データ元 | NPB 公式 box score(https://npb.jp/) |
| 集計期間 | {since} 〜 {until} |
| 比較 | セ・リーグ同守備位置の球団別比較 |
| 注意点 | {source_note} |
"""
    return {"title": title, "body_md": body_md}


def render_hr_pace_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_PACE_HR_PROJECTION — 直近 30 日 HR ペースを 143 試合換算。"""
    player = candidate_row["player_canonical"]
    magnitude = candidate_row["magnitude"]
    current = candidate_row.get("current_value") or ""
    title = (
        f"【巨人データ】{player}、直近 30 日 HR ペースを 143 試合換算で約 {magnitude:.1f} 本ペース"
    )
    headline = (
        f"{player} の直近 30 日 HR ペースをフルシーズン換算すると、約 **{magnitude:.1f} 本**"
        f" のペースです。"
    )
    detail = [f"換算ベース: {current or '直近 30 日 HR ペース × 143 試合'}"]
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label="直近 30 日",
        source_note="長打ペースはサンプル次第で変動します、後半失速 / 加速の可能性あり。",
    )


def render_hidden_below_qualifier_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_HIDDEN_OPS_LIMIT — 規定打席未満で上位 OPS の選手。"""
    player = candidate_row["player_canonical"]
    magnitude = candidate_row["magnitude"]
    current = candidate_row.get("current_value") or ""
    title = (
        f"【巨人データ】今シーズン {player}、規定打席未満ながら OPS {magnitude:.3f} の好調"
    )
    headline = (
        f"{player} は規定打席にはまだ届いていないものの、OPS が **{magnitude:.3f}**"
        f" と league 上位帯の数字です。"
    )
    detail = [
        f"現状値: {current or '-'}",
        "規定打席 (=試合数 × 3.1) に届けば公式 ranking 入りする pace。",
    ]
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label="シーズン累計",
        source_note="サンプル数が規定未満のため、長期的にこの数値が維持されるとは限りません。",
    )


def render_hit_streak_run_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_HIT_STREAK_RUN — 連続多安打試合 streak。"""
    player = candidate_row["player_canonical"]
    streak = int(candidate_row.get("magnitude") or 0)
    title = (
        f"【巨人データ】{player}、{streak}試合連続で複数安打"
    )
    headline = (
        f"{player} は **{streak} 試合連続**で 1 試合 2 安打以上を記録しています。"
    )
    detail = [
        f"連続記録: {streak} 試合",
        "1 試合 2 安打以上を継続中。",
    ]
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label="直近",
        source_note="streak は単打 / 長打を区別しないため、出塁率の質は別途要確認。",
    )


def render_defense_uzr_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_DEFENSE_UZR_OUTLIER — 守備位置別 UZR_proxy 平均比。"""
    player = candidate_row["player_canonical"]
    diff = candidate_row.get("magnitude") or 0.0
    notes = candidate_row.get("notes") or ""
    current = candidate_row.get("current_value") or ""
    baseline = candidate_row.get("baseline_value") or ""
    position = ""
    for token in notes.split():
        if token.startswith("position="):
            position = token.split("=", 1)[1]
    team_article = _render_defense_team_comparison_article(
        conn,
        player=player,
        position=position,
        metric="UZR_proxy",
        metric_label="簡易UZR",
        source_note=(
            "これは本物の UZR ではなく box-score 由来の近似指標。"
            "チーム別アウト化率からセ・リーグ同守備位置平均との差を見た参考値。"
            "NPB は打球座標を公開しないため、真の UZR は計算不可。"
        ),
    )
    if team_article is not None:
        return team_article
    position_label = _defense_position_label(position)
    direction = _average_comparison_phrase(diff)
    title = (
        f"【巨人データ】{player}、{position_label}の簡易UZRが{direction}（直近30日）"
    )
    uzr_value = _format_stat_value(_extract_kv_value(current, "RF_proxy"))
    if diff >= 0:
        headline = (
            f"{player} の {position_label}での簡易UZRは、"
            f"NPB 全体の {position_label}平均より **+{diff:.3f}** 高い数字です。"
        )
    else:
        headline = (
            f"{player} の {position_label}での簡易UZRは、"
            f"NPB 全体の {position_label}平均より **{diff:.3f}** 低い数字です。"
        )
    detail = [
        f"対象守備位置: {position_label}",
        f"選手の簡易UZR: {uzr_value}",
        f"守備位置平均との差: {diff:+.3f}",
        f"元データ: {current}",
        f"比較基準: {baseline}",
    ]
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label="直近 30 日",
        source_note=(
            "これは本物の UZR ではなく box-score 由来の近似指標 (RF_proxy − ポジション league 平均)。"
            "NPB は打球座標を公開しないため、真の UZR は計算不可。方向性のみを示す参考値。"
        ),
    )


def render_defense_fielding_pct_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_DEFENSE_FIELDING_PCT — 守備位置別 fielding_pct 平均比。"""
    player = candidate_row["player_canonical"]
    diff = candidate_row.get("magnitude") or 0.0
    notes = candidate_row.get("notes") or ""
    current = candidate_row.get("current_value") or ""
    baseline = candidate_row.get("baseline_value") or ""
    position = ""
    for token in notes.split():
        if token.startswith("position="):
            position = token.split("=", 1)[1]
    team_article = _render_defense_team_comparison_article(
        conn,
        player=player,
        position=position,
        metric="FIELDING_PCT",
        metric_label="守備率",
        source_note=(
            "守備率 = converted_outs / (converted_outs + errors)。"
            "box-score の direction marker ベースのため、捕逸 / 暴投 は含めない簡易版。"
        ),
    )
    if team_article is not None:
        return team_article
    position_label = _defense_position_label(position)
    direction = _average_comparison_phrase(diff)
    fielding_pct = _format_stat_value(_extract_kv_value(current, "fielding_pct"))
    title = (
        f"【巨人データ】{player}、{position_label}率{fielding_pct}が{direction}（直近30日）"
    )
    if diff >= 0:
        headline = (
            f"{player} の {position_label}率は、NPB 全体の {position_label}平均より"
            f" **+{diff:.3f}** 高い数字です。"
        )
    else:
        headline = (
            f"{player} の {position_label}率は、NPB 全体の {position_label}平均より"
            f" **{diff:.3f}** 低い数字です。"
        )
    detail = [
        f"対象守備位置: {position_label}",
        f"選手の守備率: {fielding_pct}",
        f"守備位置平均との差: {diff:+.3f}",
        f"元データ: {current}",
        f"比較基準: {baseline}",
    ]
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label="直近 30 日",
        source_note=(
            "守備率 = converted_outs / (converted_outs + errors)。"
            "box-score の direction marker ベースのため、捕逸 / 暴投 は含まれない簡易版。"
        ),
    )


# ─── 2026-05-15 試合後 ファンが気になる指標 renderer (5 種) ────────────────


def _scope_label_jp(scope: str) -> str:
    """scope code を読者向け JP 表記に変換 (2026-05-15 user 指示「期間を入れる」)。

    raw code (last_7d / last_30d / season / last_5_games) が title に出ると
    読者に伝わらない。「直近 1 週間」「直近 1 ヶ月」「今シーズン」「直近 5 試合」
    へ 1 か所で変換。
    """
    return title_guard.period_label_for_scope(scope) or (scope or "")


def _parse_kv_blob(text: str) -> dict[str, str]:
    """``key=value`` を空白区切りで持つ文字列を dict に。"""
    out: dict[str, str] = {}
    for token in (text or "").split():
        if "=" in token:
            k, v = token.split("=", 1)
            out[k] = v
    return out


def _scope_from_candidate(candidate_row: dict[str, Any]) -> str:
    notes = _parse_kv_blob(candidate_row.get("notes") or "")
    if notes.get("scope"):
        return notes["scope"]
    label = str(candidate_row.get("window_label") or "")
    for scope in (
        "last_10_games", "last_5_games", "last_30d",
        "last_7d", "monthly", "weekly", "season",
    ):
        if scope in label:
            return scope
    return "season"


def _dedup_context_for_candidate(candidate_row: dict[str, Any]) -> Optional[dict[str, Any]]:
    notes = _parse_kv_blob(candidate_row.get("notes") or "")
    signal_type = candidate_row.get("signal_type")
    metric = (
        _SIGNAL_PRIMARY_METRIC.get(signal_type)
        or notes.get("metric")
        or ""
    )
    current = str(candidate_row.get("current_value") or "")
    if not metric and "=" in current:
        metric = current.split("=", 1)[0].strip()
    if not metric or not _wl.is_metric_allowed(metric):
        return None
    player = str(candidate_row.get("player_canonical") or "").strip()
    if not player:
        return None
    return {
        "subject_key": player,
        "metric_name": metric,
        "scope": _scope_from_candidate(candidate_row),
        "value": dedup_gate.parse_first_number(current, preferred_key=metric),
        "rank": dedup_gate.parse_rank(current),
        "total": None,
    }


def render_game_hero_batter_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_GAME_HERO_BATTER — 試合で活躍した打者の今日のヒーロー記事。"""
    player = candidate_row["player_canonical"]
    current = _parse_kv_blob(candidate_row.get("current_value") or "")
    baseline = candidate_row.get("baseline_value") or ""
    notes = _parse_kv_blob(candidate_row.get("notes") or "")
    score = notes.get("game_score") or ""
    opponent_match = ""
    result_match = ""
    for token in (baseline or "").split():
        if token.startswith("opponent="):
            opponent_match = token.split("=", 1)[1]
        elif token.startswith("result="):
            result_match = token.split("=", 1)[1]
    h = current.get("H", "0")
    rbi = current.get("RBI", "0")
    hr = current.get("HR", "0")
    ab = current.get("AB", "0")
    # 試合日 抽出 (baseline_value 形式: "game=2026-05-15:db-d-08 ...")
    import re as _re_d
    _m = _re_d.search(r"game=(\d{4})-(\d{2})-(\d{2})", baseline)
    date_part = f"{int(_m.group(2))}/{int(_m.group(3))} " if _m else ""
    title = (
        f"【巨人データ】{player}、"
        + (f"{hr} 本塁打 " if hr != "0" else "")
        + f"{h} 安打 {rbi} 打点"
        + (f" ({date_part}{opponent_match}戦)" if opponent_match else "")
    )
    headline = (
        f"{player} は今日の {opponent_match or '相手'} 戦で **{ab} 打数 {h} 安打 {rbi} 打点**"
        + (f" / {hr} 本塁打" if hr != "0" else "")
        + f"。試合結果は **{result_match or '結果確定'}** ({score or 'スコア未取得'})。"
    )
    # 348 step 3 完全達成 D-4: bullet list → box score 表形式
    box_rows = [
        ("打数", ab),
        ("安打", h),
        ("本塁打", hr),
        ("打点", rbi),
        ("得点", current.get("R", "0")),
        ("盗塁", current.get("SB", "0")),
        ("試合スコア", score or "-"),
        ("試合結果", result_match or "-"),
        ("対戦相手", opponent_match or "-"),
    ]
    return _render_box_score_article(
        title=title,
        headline=headline,
        box_table_rows=box_rows,
        period_label="今日の試合",
        source_note="NPB 公式 box score 由来。打撃成績の単発活躍は次戦継続するかが鍵。",
    )


def render_game_pitcher_performance_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_GAME_PITCHER_PERF — 投手の今日の好投 / 不調。"""
    player = candidate_row["player_canonical"]
    current = _parse_kv_blob(candidate_row.get("current_value") or "")
    baseline = candidate_row.get("baseline_value") or ""
    notes = _parse_kv_blob(candidate_row.get("notes") or "")
    direction = notes.get("direction", "登板")
    opponent_match = ""
    result_match = ""
    for token in (baseline or "").split():
        if token.startswith("opponent="):
            opponent_match = token.split("=", 1)[1]
        elif token.startswith("result="):
            result_match = token.split("=", 1)[1]
    ip = current.get("IP", "0")
    er = current.get("ER", "0")
    k = current.get("K", "0")
    bb = current.get("BB", "0")
    h_allowed = current.get("H", "0")
    # 試合日 抽出 (baseline_value 形式: "game=2026-05-15:db-d-08 ...")
    import re as _re_dp
    _mp = _re_dp.search(r"game=(\d{4})-(\d{2})-(\d{2})", baseline)
    date_part = f"{int(_mp.group(2))}/{int(_mp.group(3))} " if _mp else ""
    title = (
        f"【巨人データ】{player}、{ip} 回 {er} 自責 {k} 奪三振"
        + (f" ({date_part}{opponent_match}戦)" if opponent_match else "")
    )
    headline = (
        f"{player} は今日の {opponent_match or '相手'} 戦で "
        f"**{ip} 回 {er} 自責点 {k} 奪三振** の {direction}。"
        f" 試合結果 **{result_match or '結果確定'}**。"
    )
    # 348 step 3 完全達成 D-4: bullet list → box score 表形式
    box_rows = [
        ("投球回", ip),
        ("自責点", er),
        ("被安打", h_allowed),
        ("被本塁打", current.get("HR", "0")),
        ("与四球", bb),
        ("奪三振", k),
        ("記録", current.get("mark", "") or "-"),
        ("試合結果", result_match or "-"),
        ("対戦相手", opponent_match or "-"),
    ]
    return _render_box_score_article(
        title=title,
        headline=headline,
        box_table_rows=box_rows,
        period_label="今日の試合",
        source_note="NPB 公式 box score 由来。1 試合の数字、シーズン累計とは別。",
    )


def _format_milestone_value(metric_name: str, raw_value: Any) -> str:
    """Render milestone value for user-facing title/body."""
    try:
        value = float(str(raw_value))
    except (TypeError, ValueError):
        return str(raw_value or "")
    if metric_name in {"ERA", "WHIP", "FIP", "xFIP", "K_per_9", "BB_per_9", "HR_per_9", "K_BB"}:
        return f"{value:.2f}"
    if metric_name in {"HR", "H", "RBI", "SB", "SO"}:
        if value.is_integer():
            return str(int(value))
    return f"{value:g}"


def _metric_value_with_unit(metric_name: str, value_text: str) -> str:
    if metric_name == "HR" and value_text:
        return f"{value_text}本"
    return value_text


def _snapshot_date_from_candidate(candidate_row: dict[str, Any]) -> Optional[str]:
    snapshot = str(candidate_row.get("snapshot_date") or "").strip()
    if snapshot:
        return snapshot
    window = str(candidate_row.get("window_label") or "").strip()
    import re as _re_snapshot
    match = _re_snapshot.search(r"(\d{4}-\d{2}-\d{2})", window)
    if match:
        return match.group(1)
    prefix = "milestone_"
    if window.startswith(prefix):
        candidate = window[len(prefix):]
        if len(candidate) >= 10:
            return candidate[:10]
    return None


_SNAPSHOT_QUALITY_SIGNALS = frozenset({
    detector.SIGNAL_ZSCORE_BATTER,
    detector.SIGNAL_ZSCORE_PITCHER,
    detector.SIGNAL_GIANTS_TOP_OUTLIER,
    detector.SIGNAL_STAT_DELTA,
})


def _quality_decision_for_candidate(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
    article: dict[str, str],
    dedup_context: Optional[dict[str, Any]],
) -> quality_gate.QualityDecision:
    """Choose the strictest safe quality gate for an anomaly candidate."""
    if (
        candidate_row.get("signal_type") in _SNAPSHOT_QUALITY_SIGNALS
        and dedup_context
    ):
        return quality_gate.validate_player_snapshot_article(
            conn,
            article,
            metric_name=dedup_context["metric_name"],
            scope=dedup_context["scope"],
            focus_player=dedup_context["subject_key"],
            snapshot_date=_snapshot_date_from_candidate(candidate_row),
        )
    return quality_gate.validate_basic_article(article)


def _milestone_rank_context(
    conn: Optional[sqlite3.Connection],
    *,
    candidate_row: dict[str, Any],
    metric_name: str,
    player: str,
) -> Optional[dict[str, Any]]:
    if conn is None:
        return None
    snapshot_date = _snapshot_date_from_candidate(candidate_row)
    try:
        return _find_player_rank(
            conn,
            metric_name=metric_name,
            scope="season",
            snapshot_date=snapshot_date,
            player_canonical=player,
            league="central",
        )
    except sqlite3.Error:
        return None


def render_milestone_crossed_article(
    conn: Optional[sqlite3.Connection],
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_MILESTONE_CROSSED — シーズン累計節目 + record event(348 step 3 part 2)。

    notes に ``record=cycle|no_hitter|perfect_game`` がある場合は record event
    として専用 title / body を生成。 それ以外は数値 threshold milestone。
    """
    player = candidate_row["player_canonical"]
    notes = _parse_kv_blob(candidate_row.get("notes") or "")
    record = notes.get("record", "")

    # 348 step 3 完全達成: 連続記録 5 種 (consecutive_*) を専用 render (box score 表形式)
    if record.startswith("consecutive_"):
        record_label = {
            "consecutive_hit": "連続安打試合",
            "consecutive_onbase": "連続出塁試合",
            "consecutive_hr": "連続試合本塁打",
            "consecutive_scoreless_ip": "連続イニング無失点",
            "consecutive_strikeouts": "1 試合最多奪三振",
        }.get(record, record)
        streak = notes.get("streak", "")
        unit = "イニング" if record == "consecutive_scoreless_ip" else (
            "個" if record == "consecutive_strikeouts" else "試合"
        )
        title = f"【巨人データ】{player} {record_label} {streak} {unit} 継続中"
        headline = (
            f"{player} は **{record_label} {streak} {unit}** を継続中 (snapshot_date 時点)。"
        )
        box_rows = [
            ("記録名", record_label),
            ("連続値", f"{streak} {unit}"),
            ("選手", player),
        ]
        game = notes.get("game", "")
        if game:
            box_rows.append(("観測 game", game))
        # proxy 透明性 (348 step 3 完全達成 D-4: 表形式 + 注釈分離)
        if record == "consecutive_onbase":
            box_rows.append(("注", "出塁判定 = H>0 OR R>0 proxy (BB/HBP は atbats_json parse 範囲外)"))
        if record == "consecutive_strikeouts":
            box_rows.append(("注", "PA レベル連続 K でなく 1 試合内 K 総数 max を proxy"))
        return _render_box_score_article(
            title=title,
            headline=headline,
            box_table_rows=box_rows,
            period_label="シーズン進行中",
            source_note="史上 N 人目 / 何年ぶり 等の lookup は手動 (NPB 公式 / Wikipedia)。",
        )

    if record in ("cycle", "no_hitter", "perfect_game"):
        # 348 step 3 完全達成 D-3 + D-4: record event の専用 render (box score 表形式)
        opponent_code = notes.get("opponent", "")
        opponent_jp = _team_label(opponent_code) if opponent_code else ""
        game_id = notes.get("game", "")
        game_date = game_id.split(":", 1)[0] if game_id else ""
        record_label = {
            "cycle": "サイクル安打",
            "no_hitter": "ノーヒットノーラン",
            "perfect_game": "完全試合",
        }[record]
        title = (
            f"【巨人データ】{player} {record_label} 達成"
            + (f" ({game_date} vs {opponent_jp})" if game_date else "")
        )
        headline = (
            f"{player} が **{record_label}** を達成。"
            + (f" ({game_date} vs {opponent_jp} 戦)" if opponent_jp else "")
        )
        box_rows = [
            ("達成内容", record_label),
            ("選手", player),
        ]
        if game_date:
            box_rows.append(("達成日", game_date))
        if opponent_jp:
            box_rows.append(("対戦相手", opponent_jp))
        if game_id:
            box_rows.append(("game_id", game_id))
        # 348 step 3 spec §2.5「✅ 史上 N 人目 / 何年ぶり 入れる、 lookup は手動」
        # placeholder structure (record DB 整備しない、 user / Claude 手動 fill)
        box_rows.append(("史上 N 人目", "_ 人目(NPB 公式 / Wikipedia で手動 lookup)"))
        box_rows.append(("何年ぶり", "_ 年ぶり(同上)"))
        box_rows.append(("前回達成者", "_(同上)"))
        return _render_box_score_article(
            title=title,
            headline=headline,
            box_table_rows=box_rows,
            period_label=game_date or "本日",
            source_note="史上 N 人目 / 何年ぶり 等の lookup は手動 (NPB 公式 / Wikipedia)。",
        )

    # 既存 path: 数値 threshold milestone (シーズン HR 30 到達 等)
    metric = notes.get("metric", "")
    threshold = notes.get("threshold", "")
    value = notes.get("value", "")
    metric_label = _human_metric_label(metric)
    if metric == "HR":
        metric_label = "本塁打"
    value_text = _format_milestone_value(metric, value)
    threshold_text = _format_milestone_value(metric, threshold)
    value_with_unit = _metric_value_with_unit(metric, value_text)
    threshold_with_unit = _metric_value_with_unit(metric, threshold_text)
    lower_is_better = metric in _LOWER_IS_BETTER_METRICS
    rank_context = _milestone_rank_context(
        conn, candidate_row=candidate_row, metric_name=metric, player=player
    )
    rank_phrase = ""
    if rank_context:
        rank_phrase = f"でセ・リーグ{rank_context['rank']}/{rank_context['total']}位"
    title = (
        f"【巨人データ】{player}、{metric_label}{value_with_unit}{rank_phrase}"
        "（今シーズン）"
    )
    if lower_is_better:
        headline = f"{player} の今シーズン{metric_label}は **{value_with_unit}**"
        if rank_context:
            headline += f"、セ・リーグ **{rank_context['rank']}/{rank_context['total']}位**。"
        else:
            headline += "。"
        if threshold_with_unit:
            headline += f" {metric_label}{threshold_with_unit}以下の水準です。"
    else:
        headline = f"{player} の今シーズン{metric_label}は **{value_with_unit}**"
        if rank_context:
            headline += f"、セ・リーグ **{rank_context['rank']}/{rank_context['total']}位**。"
        else:
            headline += "。"
        if threshold_with_unit:
            headline += f" {threshold_with_unit}の節目に到達しています。"
    detail = [
        f"対象指標: {metric_label}",
        "集計期間: 今シーズン",
        f"現在値: {value_with_unit}",
    ]
    if rank_context:
        detail.append(f"セ・リーグ順位: {rank_context['rank']}/{rank_context['total']}位")
    if threshold_with_unit:
        threshold_label = "基準ライン" if lower_is_better else "節目"
        detail.append(f"{threshold_label}: {threshold_with_unit}")
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label="シーズン累計",
        source_note=(
            "防御率など低いほど良い指標は「到達」ではなく、現在値・順位・期間で見る。"
            if lower_is_better
            else "節目通過は次の節目を狙えるかの起点。"
        ),
    )


def render_standings_shift_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_STANDINGS_SHIFT — 球団順位変動。"""
    notes = _parse_kv_blob(candidate_row.get("notes") or "")
    direction = notes.get("direction", "変動")
    current = _parse_kv_blob(candidate_row.get("current_value") or "")
    baseline = _parse_kv_blob(candidate_row.get("baseline_value") or "")
    prev_rank = baseline.get("prev_rank", "?")
    new_rank = current.get("current_rank", "?")
    w = current.get("W", "?")
    l = current.get("L", "?")
    gb = current.get("GB", "?")
    title = (
        f"【巨人データ】巨人、順位 {prev_rank} → {new_rank} ({direction})"
    )
    headline = (
        f"巨人 の順位が **{prev_rank} 位 → {new_rank} 位** に {direction} しました。"
        f" 現状 {w} 勝 {l} 敗、ゲーム差 {gb}。"
    )
    detail = [
        f"前回順位: {prev_rank}",
        f"現順位: {new_rank}",
        f"勝敗: {w}-{l} (GB {gb})",
    ]
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label="シーズン進行中",
        source_note="順位変動は単日の勝敗で動きやすい、月単位 trend と合わせて見るのが本筋。",
    )


def render_stat_delta_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """SIGNAL_STAT_DELTA — snapshot 間 数値急変。"""
    player = candidate_row["player_canonical"]
    notes = _parse_kv_blob(candidate_row.get("notes") or "")
    metric = notes.get("metric", "")
    scope = notes.get("scope", "")
    metric_label = _human_metric_label(metric)
    delta = notes.get("delta", "")
    current = candidate_row.get("current_value") or ""
    baseline = candidate_row.get("baseline_value") or ""
    scope_jp = _scope_label_jp(scope)
    # 2026-05-15 user 指示「title に変化率はいらない、実数値が欲しい」適用、
    # title は current 実値のみ。 delta は body に説明として残す。
    # current_value 形式: "current=0.770 (2026-05-15) rank 3→5" 等
    import re as _re
    _cur_match = _re.search(r"current=([\d\.\-]+)", current)
    cur_val = _cur_match.group(1) if _cur_match else "-"
    scope_title = scope_jp.replace(" ", "")
    period_suffix = f"（{scope_title}）" if scope_title else ""
    title = (
        f"【巨人データ】{player}、{metric_label}{cur_val}{period_suffix}"
    )
    headline = (
        f"{player} の {metric_label} が **{delta}** 変動しました ({baseline} → {current})。"
    )
    detail = [
        f"対象指標: {metric_label}",
        f"集計期間: {scope_jp}",
        f"前回値: {baseline}",
        f"現在値: {current}",
        f"変動: {delta}",
    ]
    return _render_simple_data_article(
        title=title,
        headline=headline,
        detail_lines=detail,
        period_label=f"{scope_jp} (前 snapshot vs 直近 snapshot)",
        source_note="数値変動は短期 trend、長期 trend (1 ヶ月以上) と組み合わせて評価が望ましい。",
    )


# signal_type → render function map
_RENDERERS = {
    detector.SIGNAL_ZSCORE_BATTER: render_zscore_batter_article,
    detector.SIGNAL_ZSCORE_PITCHER: render_zscore_pitcher_article,
    detector.SIGNAL_BABIP_DIVERGENCE: render_babip_divergence_article,
    detector.SIGNAL_FIP_ERA_DIVERGENCE: render_fip_era_divergence_article,
    detector.SIGNAL_GIANTS_TOP_OUTLIER: render_giants_top_article,
    # 2026-05-15 追加 (取りこぼし 3 + 守備 2)
    detector.SIGNAL_PACE_HR_PROJECTION: render_hr_pace_article,
    detector.SIGNAL_HIDDEN_OPS_LIMIT: render_hidden_below_qualifier_article,
    detector.SIGNAL_HIT_STREAK_RUN: render_hit_streak_run_article,
    detector.SIGNAL_DEFENSE_UZR_OUTLIER: render_defense_uzr_article,
    detector.SIGNAL_DEFENSE_FIELDING_PCT: render_defense_fielding_pct_article,
    # 2026-05-15 追加 (試合後 ファンが気になる 5 種)
    detector.SIGNAL_GAME_HERO_BATTER: render_game_hero_batter_article,
    detector.SIGNAL_GAME_PITCHER_PERF: render_game_pitcher_performance_article,
    detector.SIGNAL_MILESTONE_CROSSED: render_milestone_crossed_article,
    detector.SIGNAL_STANDINGS_SHIFT: render_standings_shift_article,
    detector.SIGNAL_STAT_DELTA: render_stat_delta_article,
}

_SIGNAL_PRIMARY_METRIC = {
    detector.SIGNAL_BABIP_DIVERGENCE: "BABIP",
    detector.SIGNAL_FIP_ERA_DIVERGENCE: "FIP",
    detector.SIGNAL_DEFENSE_UZR_OUTLIER: "UZR_proxy",
    detector.SIGNAL_DEFENSE_FIELDING_PCT: "FIELDING_PCT",
}


# ─── public API ─────────────────────────────────────────────────────────────


def render_anomaly_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> Optional[dict[str, str]]:
    """candidate row の signal_type に対応する render を呼び出し、article を生成。

    Returns: ``{title, body_md, body_html}`` or None (未知 signal_type)
    """
    signal_type = candidate_row.get("signal_type")
    renderer = _RENDERERS.get(signal_type)
    if renderer is None:
        return None
    signal_metric = _SIGNAL_PRIMARY_METRIC.get(signal_type)
    if signal_metric and not _wl.is_metric_allowed(signal_metric):
        return None
    metric = _parse_kv_blob(candidate_row.get("notes") or "").get("metric", "")
    if metric and not _wl.is_metric_allowed(metric):
        return None
    result = renderer(conn, candidate_row)
    if result is None:
        return None
    title_check = title_guard.ensure_title_period(
        result["title"],
        scope=_scope_from_candidate(candidate_row),
    )
    if not title_check.ok:
        return None
    if title_check.title != result["title"]:
        result["body_md"] = result["body_md"].replace(
            f"# {result['title']}", f"# {title_check.title}", 1
        )
    result["title"] = title_check.title
    return {
        "title": result["title"],
        "body_md": result["body_md"],
        "body_html": rap.markdown_to_html(result["body_md"]),
    }


def fetch_pending_anomalies(
    conn: sqlite3.Connection,
    *,
    limit: int = 10,
    priority_max: int = 2,
    signal_types: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """status='NEW' な anomaly candidate を priority 順で fetch。"""
    if signal_types is None:
        signal_types = list(detector.ALL_ANOMALY_SIGNALS)
    placeholders = ",".join(["?"] * len(signal_types))
    rows = conn.execute(
        f"SELECT candidate_id, signal_type, player_canonical, player_display, "
        f"magnitude, baseline_value, current_value, window_label, "
        f"comparison_target, priority, status, created_at, notes "
        f"FROM article_candidates "
        f"WHERE status = 'NEW' AND signal_type IN ({placeholders}) "
        f"AND priority <= ? "
        f"ORDER BY priority ASC, created_at DESC LIMIT ?",
        (*signal_types, priority_max, limit),
    ).fetchall()
    cols = ["candidate_id", "signal_type", "player_canonical", "player_display",
            "magnitude", "baseline_value", "current_value", "window_label",
            "comparison_target", "priority", "status", "created_at", "notes"]
    return [dict(zip(cols, r)) for r in rows]


def publish_anomaly_drafts(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    max_per_run: Optional[int] = None,
    category_name: str = DEFAULT_CATEGORY_NAME,
    dry_run: bool = False,
    priority_max: int = 2,
) -> list[dict[str, Any]]:
    """pending anomaly candidates を最大 ``max_per_run`` 件 WP draft 投入。

    各 candidate を render → WP draft 作成 → article_candidates.status を
    'DRAFTED' に更新 (再 publish 防止)。

    Returns: per-candidate result dicts (status, candidate_id, post_id, ...)
    """
    if max_per_run is None:
        max_per_run = DEFAULT_MAX_PER_RUN

    candidates = fetch_pending_anomalies(
        conn, limit=max_per_run * 3, priority_max=priority_max,
    )
    if not candidates:
        return []

    # category 確保 (idempotent)
    category_id = 0
    if not dry_run:
        try:
            category_id = wp_client_obj.create_category(category_name)
        except Exception:  # noqa: BLE001
            category_id = 0
        if not category_id:
            try:
                category_id = wp_client_obj.resolve_category_id(category_name)
            except Exception:  # noqa: BLE001
                category_id = 0

    results: list[dict[str, Any]] = []
    published = 0
    for cand in candidates:
        if published >= max_per_run:
            results.append({
                "status": "skip_max_per_run",
                "candidate_id": cand["candidate_id"],
                "signal_type": cand["signal_type"],
            })
            continue
        article = render_anomaly_article(conn, cand)
        if article is None:
            results.append({
                "status": "skip_unknown_signal_or_title_guard",
                "candidate_id": cand["candidate_id"],
                "signal_type": cand["signal_type"],
                "reason": "unknown_signal_or_missing_period_in_title",
            })
            continue
        dedup_context = _dedup_context_for_candidate(cand)
        quality_decision = _quality_decision_for_candidate(
            conn, cand, article, dedup_context
        )
        if not quality_decision.allowed:
            results.append(quality_gate.skip_result(
                quality_decision,
                candidate_id=cand["candidate_id"],
                signal_type=cand["signal_type"],
                player_canonical=cand["player_canonical"],
                title=article["title"],
            ))
            continue
        if dedup_context:
            dedup_decision = dedup_gate.evaluate_metric_cooldown(
                conn, **dedup_context,
            )
            if not dedup_decision.get("allowed"):
                results.append({
                    "status": "skip_dedup_cooldown",
                    "candidate_id": cand["candidate_id"],
                    "signal_type": cand["signal_type"],
                    "player_canonical": cand["player_canonical"],
                    "metric_name": dedup_context["metric_name"],
                    "scope": dedup_context["scope"],
                    "dedup": dedup_decision,
                })
                continue
        if dry_run:
            results.append({
                "status": "dry_run",
                "candidate_id": cand["candidate_id"],
                "signal_type": cand["signal_type"],
                "title": article["title"],
                "body_html": article["body_html"],
                "player_canonical": cand["player_canonical"],
            })
            published += 1
            continue
        if not category_id:
            results.append({
                "status": "error_category_resolve",
                "candidate_id": cand["candidate_id"],
            })
            continue
        # WP 投入 status 決定 (巨人選手は env flag 設定時 publish 化)
        team_code_for_pub = _player_team_code(conn, cand["player_canonical"])
        publish_status = rap._resolve_publish_status(focus_team_code=team_code_for_pub)
        # NEWS-BANNER-FIX-2026-05-15: anomaly 記事も赤紫グラデ banner を冒頭に
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
                caller="anomaly_article_publisher",
            )
            # mark candidate as DRAFTED
            conn.execute(
                "UPDATE article_candidates SET status = 'DRAFTED' WHERE candidate_id = ?",
                (cand["candidate_id"],),
            )
            conn.commit()
            dedup_history_id = 0
            dedup_record_error = ""
            if dedup_context:
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
            results.append({
                "status": "published" if publish_status == "publish" else "published_draft",
                "wp_status": publish_status,
                "candidate_id": cand["candidate_id"],
                "signal_type": cand["signal_type"],
                "title": article["title"],
                "post_id": int(post_id or 0),
                "category_id": int(category_id),
                "player_canonical": cand["player_canonical"],
                "team_code": team_code_for_pub,
                "dedup_history_id": dedup_history_id,
                "dedup_record_error": dedup_record_error,
            })
            published += 1
        except Exception as e:  # noqa: BLE001
            results.append({
                "status": "error_create_post",
                "candidate_id": cand["candidate_id"],
                "error": f"{type(e).__name__}: {e}",
            })
    return results
