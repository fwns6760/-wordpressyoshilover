"""INSIGHT-008 — rank/metric data → markdown article draft (template-based).

The goal is to turn accumulated-only signals (split / streak / FIP rank /
RF_proxy etc.) into a publishable article skeleton **without** calling
Gemini / GPT — pure Python templates that the operator can edit and
ship via the existing manual-intake path.

Three layers:

1. ``ArticleContext`` collects the inputs (focus player, metric, rank
   table rows, sample window, scope description) into a structured
   payload.
2. ``select_template`` picks the appropriate template by metric_kind
   (batting / pitching / defense) — each has slightly different lead
   phrasing and disclaimers.
3. ``render_article`` produces markdown:
     - title (suggested)
     - lead paragraph (data summary)
     - data table (top N + focus player highlighted)
     - 解釈 paragraph (rule-based on data shape)
     - disclaimer (especially for RF_proxy / UZR_proxy)
     - meta footer (generated_at, source, sample_size)

The output is meant for **human review + manual paste into WordPress**
or for ingestion via the existing manual-intake form (no auto-publish).

No Gemini / X API / WP REST writes from this module.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional


# ─── metric metadata ────────────────────────────────────────────────────────

_METRIC_KIND: dict[str, str] = {
    # batting
    "AVG": "batting", "OBP": "batting", "SLG": "batting", "OPS": "batting",
    "ISO": "batting", "wOBA": "batting", "K_pct": "batting",
    "BB_pct": "batting", "BABIP": "batting",
    # pitching
    "ERA": "pitching", "WHIP": "pitching", "K_per_9": "pitching",
    "BB_per_9": "pitching", "HR_per_9": "pitching", "K_BB": "pitching",
    "FIP": "pitching", "xFIP": "pitching",
    # defense (approximation)
    "RF_proxy": "defense", "UZR_proxy": "defense",
}

_METRIC_LABEL_JA: dict[str, str] = {
    "AVG": "打率",
    "OBP": "出塁率",
    "SLG": "長打率",
    "OPS": "OPS",
    "ISO": "純長打 (ISO)",
    "wOBA": "wOBA",
    "K_pct": "三振率",
    "BB_pct": "四球率",
    "BABIP": "BABIP",
    "ERA": "防御率",
    "WHIP": "WHIP",
    "K_per_9": "K/9",
    "BB_per_9": "BB/9",
    "HR_per_9": "HR/9",
    "K_BB": "K/BB",
    "FIP": "FIP",
    "xFIP": "xFIP",
    "RF_proxy": "Range Factor 代理 (守備機会の out 変換率)",
    "UZR_proxy": "UZR 代理 (RF_proxy − リーグ位置平均)",
}

# 値が高い = 良い metric
_HIGHER_IS_BETTER: dict[str, bool] = {
    "AVG": True, "OBP": True, "SLG": True, "OPS": True, "ISO": True,
    "wOBA": True, "BB_pct": True, "K_pct": False, "BABIP": True,
    "ERA": False, "WHIP": False, "K_per_9": True, "BB_per_9": False,
    "HR_per_9": False, "K_BB": True, "FIP": False, "xFIP": False,
    "RF_proxy": True, "UZR_proxy": True,
}


# ─── data containers ────────────────────────────────────────────────────────


@dataclass
class RankRow:
    player_canonical: str
    team_code: Optional[str]
    metric_value: Optional[float]
    sample_size: int
    rank: int
    total: int


@dataclass
class ArticleContext:
    metric_name: str
    rows: list[RankRow]
    focus_player: Optional[str] = None
    position_filter: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    sample_window_label: str = "通算"


# ─── public API ─────────────────────────────────────────────────────────────


def render_article(ctx: ArticleContext, *, top_n: int = 10) -> dict:
    """Return ``{title, body_md, suggested_tags, meta}``."""
    kind = _METRIC_KIND.get(ctx.metric_name, "other")
    label = _METRIC_LABEL_JA.get(ctx.metric_name, ctx.metric_name)
    higher = _HIGHER_IS_BETTER.get(ctx.metric_name, True)
    focus_row = _find_focus_row(ctx.rows, ctx.focus_player)
    title = _make_title(ctx, label, focus_row, kind)
    lead = _make_lead(ctx, label, focus_row, kind)
    table = _render_rank_table(ctx.rows[:top_n], focus_row, label)
    interpretation = _make_interpretation(ctx, label, focus_row, higher, kind)
    disclaimer = _make_disclaimer(kind)
    meta_footer = _make_meta_footer(ctx)

    parts = [
        f"# {title}",
        "",
        lead,
        "",
        "## データで見ると",
        "",
        table,
        "",
        "## 解釈",
        "",
        interpretation,
        "",
        disclaimer,
        "",
        meta_footer,
    ]
    return {
        "title": title,
        "body_md": "\n".join(parts).rstrip() + "\n",
        "suggested_tags": _suggest_tags(ctx, focus_row, kind),
        "meta": {
            "metric_name": ctx.metric_name,
            "metric_label": label,
            "position_filter": ctx.position_filter,
            "focus_player": ctx.focus_player,
            "total_players": ctx.rows and ctx.rows[0].total,
            "sample_window": ctx.sample_window_label,
        },
    }


# ─── helpers ────────────────────────────────────────────────────────────────


def _find_focus_row(rows: list[RankRow], focus_player: Optional[str]) -> Optional[RankRow]:
    if not focus_player:
        return None
    for r in rows:
        if r.player_canonical == focus_player:
            return r
    return None


def _make_title(ctx: ArticleContext, label: str, focus: Optional[RankRow], kind: str) -> str:
    # 2026-05-15 user 指示「日時 prefix なし、人間にわかりやすく」適用。
    # 期間は title 末尾の sample_window_label に含まれる (例: 4/15〜5/14)。
    if focus and ctx.position_filter:
        return (
            f"巨人・{focus.player_canonical}、12 球団{ctx.position_filter}手の{label}で"
            f"{focus.rank}位 / {focus.total}人 (期間: {ctx.sample_window_label})"
        )
    if focus:
        return (
            f"{focus.player_canonical}、{label} は 12 球団中 {focus.rank} 位 — "
            f"{ctx.sample_window_label}データから見る位置"
        )
    if ctx.position_filter:
        return f"12 球団{ctx.position_filter}手の{label}ランキング {ctx.sample_window_label}"
    return f"12 球団 {label} ランキング {ctx.sample_window_label}"


def _make_lead(ctx: ArticleContext, label: str, focus: Optional[RankRow], kind: str) -> str:
    n_total = ctx.rows[0].total if ctx.rows else 0
    if focus:
        val = focus.metric_value
        rank = focus.rank
        team = focus.team_code or "?"
        share = (
            f"全 {focus.total} 人中で {rank} 位 (値 {val}、サンプル {focus.sample_size})。"
        )
        intro = {
            "batting": (
                f"巨人の {focus.player_canonical} は、{ctx.sample_window_label}の"
                f"{label}で {share}"
            ),
            "pitching": (
                f"{focus.player_canonical} ({team}) の {label} は "
                f"{ctx.sample_window_label} で見ると {share}"
            ),
            "defense": (
                f"{focus.player_canonical} の {ctx.position_filter or ''}"
                f" 守備機会の out 変換率 ({label}) は"
                f"{ctx.sample_window_label} で {share} "
                f"これは真の UZR ではなく近似指標である点に注意。"
            ),
        }.get(kind, share)
        return intro
    return (
        f"NPB 12 球団から{ctx.sample_window_label}の{label}を集計し、"
        f"{n_total} 人を順位化したデータをまとめた。"
    )


def _render_rank_table(rows: list[RankRow], focus: Optional[RankRow], label: str) -> str:
    if not rows:
        return "_該当データなし_"
    lines = [
        f"| 順位 | 選手 | チーム | {label} | サンプル |",
        "|---|---|---|---|---|",
    ]
    focus_name = focus.player_canonical if focus else None
    for r in rows:
        marker = " ★" if focus_name and r.player_canonical == focus_name else ""
        team = r.team_code or "-"
        val = r.metric_value if r.metric_value is not None else "-"
        lines.append(
            f"| {r.rank}/{r.total} | {r.player_canonical}{marker} | {team} | {val} | {r.sample_size} |"
        )
    return "\n".join(lines)


def _make_interpretation(
    ctx: ArticleContext,
    label: str,
    focus: Optional[RankRow],
    higher_is_better: bool,
    kind: str,
) -> str:
    if not focus:
        return f"全 12 球団の{label}を集計したランキング表は上記のとおり。"
    rank, total = focus.rank, focus.total
    val = focus.metric_value
    quartile = "上位 1/4" if rank * 4 <= total else (
        "上位 1/3" if rank * 3 <= total else (
            "中位" if rank * 2 <= total else "下位"
        )
    )
    direction = "高い" if higher_is_better else "低い"
    if higher_is_better:
        good = rank * 3 <= total  # 上位 1/3 を「良い」とする
    else:
        good = rank * 3 <= total  # 同条件 (rank 数字が小さい = 良い)
    if good:
        verdict = f"これは {label} としては {direction}方向に振れており、12 球団平均より明確に上"
    elif rank * 2 <= total:
        verdict = f"{label} は 12 球団中位、平均近辺"
    else:
        verdict = f"{label} は 12 球団下位、改善余地がある領域"

    return (
        f"{focus.player_canonical} の{label}は {val} で、12 球団中 {rank} 位 ({quartile})。"
        f"{verdict}。サンプル {focus.sample_size} ({ctx.sample_window_label}) に基づくため、"
        "サンプルが小さい場合は今後の試合で値が動く可能性がある。"
    )


def _make_disclaimer(kind: str) -> str:
    if kind == "defense":
        return (
            "**注: 守備指標について** — 公開された UZR ではなく、box "
            "score の打球方向 marker から計算した RF (Range Factor) 代理である。"
            "真の UZR は打球座標 (NPB 非公開) を要するため、本指標は方向性のみを示す。"
        )
    return (
        "**注: 集計について** — 期間内の累積値から計算。"
        "サンプル数が少ない場合は値が大きく動くため、最低 30 PA / 10 IP 以上で見るのが推奨。"
    )


def _make_meta_footer(ctx: ArticleContext) -> str:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"---",
        f"_metric: {ctx.metric_name}_ ・ _scope: {ctx.sample_window_label}_",
        f"_generated_at: {now}_ ・ _source: NPB official box scores_",
    ]
    if ctx.since or ctx.until:
        lines.append(f"_window: {ctx.since or '(no-start)'} 〜 {ctx.until or '(no-end)'}_")
    if ctx.position_filter:
        lines.append(f"_position: {ctx.position_filter}_")
    return "\n".join(lines)


def _suggest_tags(ctx: ArticleContext, focus: Optional[RankRow], kind: str) -> list[str]:
    tags: list[str] = ["巨人", "データ分析", "12球団ランキング"]
    tags.append(_METRIC_LABEL_JA.get(ctx.metric_name, ctx.metric_name))
    if focus and focus.player_canonical:
        tags.append(focus.player_canonical)
    if ctx.position_filter:
        tags.append(f"{ctx.position_filter}手")
    if kind == "defense":
        tags.append("守備")
    elif kind == "pitching":
        tags.append("投手")
    elif kind == "batting":
        tags.append("打撃")
    return tags
