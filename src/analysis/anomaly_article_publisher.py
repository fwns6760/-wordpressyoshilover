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

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import insight_anomaly_detector as detector  # noqa: E402
from src.analysis import ranking_article_publisher as rap  # noqa: E402

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
    return {
        "OPS": "OPS", "AVG": "打率", "OBP": "出塁率", "SLG": "長打率",
        "wOBA": "wOBA", "ISO": "ISO(長打力)", "BABIP": "BABIP",
        "ERA": "防御率", "FIP": "FIP", "WHIP": "WHIP",
        "K_per_9": "K/9", "BB_per_9": "BB/9", "HR_per_9": "HR/9",
        "K_BB": "K/BB",
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
    scope_label = {
        "last_7d": "1 週間",
        "last_30d": "1 ヶ月",
        "season": "今シーズン",
        "last_5_games": "直近 5 試合",
    }.get(scope, scope)
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

    title = title_template.format(
        player=player, team=team, metric=metric_label,
        value=value_str, rank=rank_str, scope=scope_label,
        league=league_label,
    )

    ranking_table = _render_ranking_table_md(
        top_rows, focus_player=player, metric_label=metric_label,
        extra_focus_row=extra_focus,
    )

    sample_str = str(player_rank_info['sample']) if player_rank_info else '-'
    simple_line = simple_explanation or why_notable_text or ""
    # 1 文目だけに truncate (素人向け 1-2 line max)
    simple_line = simple_line.split("。")[0] + ("。" if simple_line else "")

    body_md = f"""# {title}

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
| 期間 | 2026 シーズン(3/27〜)約 220 試合 |
| 計算式 | {_metric_formula(metric_name)} |
| 比較 | {scope_label} の {league_label} 内 全選手 |
| 更新 | 毎日 5 回(02/07/12/17/21 JST) |
| 生成 | rule-based(LLM 不使用) |
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
    title_template = f"【巨人データを見る】{{player}}、{{scope}}の{metric_label} {{value}} で{{league}} {{rank}} 位"
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
    title_template = f"【巨人データを見る】{{player}}、{{scope}}の{metric_label} {{value}} で{{league}} {{rank}} 位"
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
) -> dict[str, str]:
    """打率 vs BABIP 乖離 = 運要素 / 実力の差を可視化."""
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

    if diff > 0:
        why_text = (
            f"打率(AVG)と BABIP(打球が安打になる確率)を比べると、BABIP が "
            f"**+{diff:.3f}** 高い。これは『運に支えられた打率』の signal — 本来の実力以上に "
            f"安打が出ている可能性があり、シーズン後半に打率が落ち着く(下がる)可能性。"
        )
        notable_phrase = f"打率 {avg_str} は運込み(BABIP {babip_str})"
        simple = f"打率は高いですが、運要素が大きく作用している数字です。シーズン後半に下がる可能性あり。"
    else:
        why_text = (
            f"打率(AVG)と BABIP の差が **{diff:.3f}** で BABIP が低い。"
            f"運に逆らわれている状態で、本来の実力ならもっと打率が高いはず — 不調脱出の signal の可能性。"
        )
        notable_phrase = f"打率 {avg_str} は運悪の数字(BABIP {babip_str})"
        simple = f"打率が低めですが運悪の要素が大きく、本来の実力はもっと上の可能性があります。"

    title_template = f"【巨人データを見る】{{player}}、{{scope}}の{notable_phrase}"
    return _render_unified_article(
        conn, player=player, team_code=team_code, metric_name="AVG",
        scope="last_30d", title_template=title_template,
        why_notable_text=why_text, simple_explanation=simple,
    )


def render_fip_era_divergence_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """防御率 vs FIP 乖離 = 運に支えられた数字 / 本質指標."""
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

    if diff > 0:
        # FIP > ERA: ERA は本来より良く見えてる (運に支えられた)
        why_text = (
            f"防御率(ERA、低いほど良い指標)が **{era_str}** に対し、"
            f"FIP(投手本人の実力指標、低いほど良い)は **{fip_str}** と高い。"
            f"ERA は守備や運に支えられた『表面値』で、本質はもっと悪い投球内容。"
            f"シーズン後半に ERA が悪化するリスクがあります。"
        )
        notable_phrase = f"防御率 {era_str} は運の数字(FIP {fip_str})"
        simple = f"防御率は良い数字ですが、本質指標 FIP では平均より悪い。シーズン後半に防御率が悪化する可能性あり。"
    else:
        # FIP < ERA: ERA は本来より悪く見えてる (運に逆らわれた)
        why_text = (
            f"防御率(ERA、低いほど良い指標)が **{era_str}** に対し、"
            f"FIP(投手本人の実力指標)は **{fip_str}** と低い(良い)。"
            f"ERA は守備や運に逆らわれた数字で、本人の実力からすればもっと低い(良い)はず。"
            f"今後 ERA が改善する可能性があります。"
        )
        notable_phrase = f"防御率 {era_str} は運悪、本来 FIP {fip_str}"
        simple = f"防御率は悪く見えますが、本質指標 FIP では ERA より良い数字。シーズン後半に防御率改善の可能性あり。"

    title_template = f"【巨人データを見る】{{player}}、{{scope}}の{notable_phrase}"
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

    title_template = f"【巨人データを見る】{{player}}、{{scope}}の{metric_label} {{value}} で{{league}} {{rank}} 位"
    why_text = f"巨人選手がリーグ上位に入っている好調を示すデータです。"
    simple = f"巨人選手として、リーグ全体の上位に入っている好調な状態です。"
    scope = "last_30d" if metric_name in ("OPS", "AVG", "wOBA", "BABIP") else "season"
    return _render_unified_article(
        conn, player=player, team_code=team_code, metric_name=metric_name,
        scope=scope, title_template=title_template,
        why_notable_text=why_text, simple_explanation=simple,
    )


# signal_type → render function map
_RENDERERS = {
    detector.SIGNAL_ZSCORE_BATTER: render_zscore_batter_article,
    detector.SIGNAL_ZSCORE_PITCHER: render_zscore_pitcher_article,
    detector.SIGNAL_BABIP_DIVERGENCE: render_babip_divergence_article,
    detector.SIGNAL_FIP_ERA_DIVERGENCE: render_fip_era_divergence_article,
    detector.SIGNAL_GIANTS_TOP_OUTLIER: render_giants_top_article,
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
    result = renderer(conn, candidate_row)
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
                "status": "skip_unknown_signal",
                "candidate_id": cand["candidate_id"],
                "signal_type": cand["signal_type"],
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
        try:
            post_id = wp_client_obj.create_post(
                title=article["title"],
                content=article["body_html"],
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
            })
            published += 1
        except Exception as e:  # noqa: BLE001
            results.append({
                "status": "error_create_post",
                "candidate_id": cand["candidate_id"],
                "error": f"{type(e).__name__}: {e}",
            })
    return results
