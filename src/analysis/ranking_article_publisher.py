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
from src.analysis.insight_article_generator import (  # noqa: E402
    ArticleContext,
    RankRow,
)


# 新 category 名 (work record §4)
DEFAULT_CATEGORY_NAME = "データで見る巨人"

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
        sample_window_label = {
            "last_7d": "直近 7 日",
            "last_30d": "直近 30 日",
            "season": "シーズン累計",
        }.get(scope, scope)

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
        base_title = f"【巨人データを見る】{base_title}"

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
    scope_label_map = {"last_7d": "直近 7 日", "last_30d": "直近 30 日", "season": "シーズン累計"}
    formula = metric_formula_map.get(metric_name, f"{metric_name} 標準式")
    scope_label_text = scope_label_map.get(scope, scope)

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

    # period date range + 試合数
    today = dt.date.today()
    if scope == "last_7d":
        start_d = today - dt.timedelta(days=6)
    elif scope == "last_30d":
        start_d = today - dt.timedelta(days=29)
    elif scope == "season":
        start_d = dt.date(today.year, 3, 27)
    else:
        start_d = today
    try:
        n_games = conn.execute(
            "SELECT COUNT(*) FROM games WHERE game_date BETWEEN ? AND ?",
            (start_d.isoformat(), today.isoformat()),
        ).fetchone()[0]
    except Exception:
        n_games = 0
    period_full = f"{start_d.isoformat()} 〜 {today.isoformat()}({n_games}試合)"

    body_md = f"""# {base_title}

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
    # 巨人 focus の ranking 記事は ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1 なら
    # 自動 publish。他球団 focus または env flag OFF は 'draft' 維持。
    rows = article.get("meta", {}) or {}
    focus_team_code = "g"  # ranking 記事は focus_player が常に巨人 (find_giants_top)
    publish_status = _resolve_publish_status(focus_team_code=focus_team_code)
    try:
        post_id = wp_client_obj.create_post(
            title=article["title"],
            content=article["body_html"],
            categories=[category_id],
            status=publish_status,
            caller="ranking_article_publisher",
        )
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
    }


# ─── CLI / wire helper ──────────────────────────────────────────────────────


def publish_default_set(
    conn: sqlite3.Connection,
    wp_client_obj: Any,
    *,
    dry_run: bool = False,
    max_per_run: Optional[int] = None,
) -> list[dict]:
    """default rank set を順番に投入 (per-run 上限まで)。

    現状は OPS / wOBA / ERA / FIP の 4 種類を ``last_30d`` で投入。tuning で
    metric 種類追加 / scope 変更可能。
    """
    if max_per_run is None:
        max_per_run = DEFAULT_MAX_PER_RUN
    default_jobs = [
        {"metric_name": "OPS", "scope": "last_30d", "top_n": 30},
        {"metric_name": "wOBA", "scope": "last_30d", "top_n": 30},
        {"metric_name": "ERA", "scope": "season", "top_n": 20},
        {"metric_name": "FIP", "scope": "season", "top_n": 20},
    ]
    results: list[dict] = []
    published = 0
    for job in default_jobs:
        if published >= max_per_run:
            results.append({
                "status": "skip_max_per_run",
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
        if result.get("status") in ("published_draft", "dry_run"):
            published += 1
    return results
