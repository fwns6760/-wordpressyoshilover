"""INSIGHT-003 — markdown digest生成。

``article_candidates`` を human-readable な markdown に変換し、朝の
review 用ファイルとして書き出す。Cloud Scheduler 設定後は cron で
``data/insight/digest/<date>.md`` が user の手元に毎朝届く形を想定。

設計方針:

* category ごとに section をまとめる (打撃 / 投球 / 起用 / 単試合 / その他)。
* priority 昇順 (1 が最高) → magnitude の大きい順で並べ替え。
* run_id を絞らない (デフォルト): 直近 24 時間内 (run_ts 基準) に挿入された
  candidates が対象。
* evidence_json は markdown 内で短く show、`evidence_excerpt` で 100 chars 切り。
* 出力は read-only な markdown ファイル、WP には一切渡さない。
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# signal_type ごとのカテゴリラベル
CATEGORY_LABELS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("batting", "## 打撃シグナル", (
        "batter_homerun", "batter_multi_hit",
        "batter_recent_hot", "batter_recent_cold",
        "batter_hit_streak",
    )),
    ("pitching", "## 投球シグナル", (
        "starter_quality_start", "pitcher_high_pitch_count",
        "pitcher_workload_warning",
        "pitcher_rest_days_back_to_back", "pitcher_rest_days_extended_layoff",
    )),
    ("lineup", "## 起用シグナル", (
        "lineup_slot_jump_up", "lineup_slot_jump_down",
        "lineup_first_slot_appearance",
    )),
)


def _categorize(signal_type: str) -> str:
    for code, _label, types in CATEGORY_LABELS:
        if signal_type in types:
            return code
    return "other"


def _excerpt(text: Optional[str], limit: int = 100) -> str:
    if not text:
        return ""
    s = str(text)
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


def _format_evidence(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except Exception:
        return _excerpt(raw, 100)
    if isinstance(parsed, dict):
        items = list(parsed.items())
        flat = ", ".join(f"{k}={parsed[k]}" for k, _ in items[:4])
        return _excerpt(flat, 120)
    return _excerpt(json.dumps(parsed, ensure_ascii=False), 120)


def fetch_candidates_for_digest(
    conn: sqlite3.Connection,
    *,
    game_date: Optional[str] = None,
    since_run_ts: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Return article_candidate rows joined with insight_runs.run_ts.

    Filtering precedence:
      * ``since_run_ts`` (e.g. last 24h ISO timestamp) — takes precedence
        when provided.
      * ``game_date`` — restricts to candidates with this date in any
        related game (single-game) or run_ts day prefix (multi-game).
      * Neither: return all candidates.
    """
    base = (
        "SELECT ac.*, ir.run_ts AS run_ts "
        "FROM article_candidates ac LEFT JOIN insight_runs ir ON ir.run_id=ac.run_id"
    )
    where: list[str] = []
    params: list = []
    if since_run_ts:
        where.append("ir.run_ts >= ?")
        params.append(since_run_ts)
    elif game_date:
        # match game-tied single-game signals OR multi-game signals from the same run_ts date
        where.append(
            "(ac.game_id LIKE ? OR substr(ir.run_ts, 1, 10) = ?)"
        )
        params.extend([f"{game_date}%", game_date])
    sql = base + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY ac.priority ASC, ac.magnitude DESC, ac.candidate_id DESC"
    sql += f" LIMIT {int(limit)}"
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur]


def render_digest_markdown(
    rows: list[dict],
    *,
    game_date: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> str:
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    lines: list[str] = []
    title = f"# 巨人 — データ分析 article candidates"
    if game_date:
        title += f"  ({game_date})"
    lines.append(title)
    lines.append("")
    lines.append(f"_generated_at: {generated_at} / total candidates: {len(rows)}_")
    lines.append("")

    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(_categorize(r.get("signal_type") or ""), []).append(r)

    for code, label, _types in CATEGORY_LABELS:
        items = by_cat.get(code) or []
        if not items:
            continue
        lines.append(label)
        lines.append("")
        lines.append(
            "| 優先度 | signal | 選手 | current | baseline | window | 比較対象 | notes | evidence |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|"
        )
        for r in items:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"P{r.get('priority') or '-'}",
                        str(r.get("signal_type") or ""),
                        (r.get("player_canonical") or r.get("player_display") or "-"),
                        _excerpt(r.get("current_value"), 40),
                        _excerpt(r.get("baseline_value"), 40),
                        _excerpt(r.get("window_label"), 30),
                        _excerpt(r.get("comparison_target"), 30),
                        _excerpt(r.get("notes"), 50),
                        _format_evidence(r.get("evidence_json")),
                    ]
                )
                + " |"
            )
        lines.append("")

    misc = by_cat.get("other") or []
    if misc:
        lines.append("## その他")
        lines.append("")
        for r in misc:
            lines.append(
                f"- [P{r.get('priority') or '-'}] {r.get('signal_type')} — "
                f"{r.get('player_canonical') or r.get('player_display') or '?'}: "
                f"{_excerpt(r.get('current_value'), 80)} ({_excerpt(r.get('notes'), 80)})"
            )
        lines.append("")

    if not rows:
        lines.append("候補なし。")

    return "\n".join(lines).rstrip() + "\n"


def write_digest(
    *,
    db_path: Path,
    out_path: Path,
    game_date: Optional[str] = None,
    since_run_ts: Optional[str] = None,
    limit: int = 200,
) -> int:
    """Compose markdown for the given filters, write to ``out_path``.
    Returns the number of candidate rows rendered."""
    if not db_path.exists():
        # nothing to digest — still emit an empty file so callers can
        # confirm the path.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            render_digest_markdown([], game_date=game_date), encoding="utf-8"
        )
        return 0
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = fetch_candidates_for_digest(
            conn, game_date=game_date, since_run_ts=since_run_ts, limit=limit,
        )
    finally:
        conn.close()
    md = render_digest_markdown(rows, game_date=game_date)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    return len(rows)
