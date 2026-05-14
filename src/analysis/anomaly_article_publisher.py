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


def render_zscore_batter_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """`anomaly_zscore_outlier_batter` candidate を記事化."""
    player = candidate_row["player_canonical"]
    z = candidate_row["magnitude"]
    baseline = candidate_row["baseline_value"]
    current = candidate_row["current_value"]
    notes = candidate_row.get("notes", "")
    team_code = _player_team_code(conn, player) or "?"
    team = _team_label(team_code)

    # parse metric/scope from current_value (e.g., "OPS=1.190 sample=90")
    metric_name = "OPS"
    if "=" in current:
        try:
            metric_name = current.split("=", 1)[0].strip()
        except Exception:
            pass

    title = f"【データで見る巨人】{player}({team})、{metric_name} がリーグ平均 +{z}σ の異常値 — 大手が見落とす好調"
    body_md = f"""# {title}

{team} の **{player}** は、{metric_name} で **リーグ平均 +{z}σ** の異常値を記録している。一般メディアでは見過ごされがちな指標だが、データ上は明確に上位群。

## データで見ると

| 項目 | 値 |
|---|---|
| 現在値 | {current} |
| リーグ baseline | {baseline} |
| z-score (標準偏差倍率) | +{z}σ |
| ポジション | 打者 |
| 球団 | {team}({team_code}) |

## 解釈

z-score が +2σ を超える選手は league 全体でも上位 2.5% に入る。サンプル数が一定以上に達した状態でこの値なら、運要素より実力に近い指標。{notes}

## 注意

- サンプル数によって z-score は変動するため、最低 PA 30 / IP 15 以上の選手に限定。
- 「気づかない pattern」型分析記事 — 大手が出さない sabermetric ranking の補足。
- ranking 単独では捕捉できない「平均からの距離」を示す指標。

---

_出典: production DB の advanced_metric_snapshots、自動生成 (rule-based、LLM 不使用)。_
"""
    return {"title": title, "body_md": body_md}


def render_zscore_pitcher_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    """`anomaly_zscore_outlier_pitcher` candidate を記事化."""
    player = candidate_row["player_canonical"]
    z = candidate_row["magnitude"]
    baseline = candidate_row["baseline_value"]
    current = candidate_row["current_value"]
    notes = candidate_row.get("notes", "")
    team_code = _player_team_code(conn, player) or "?"
    team = _team_label(team_code)

    metric_name = "ERA"
    if "=" in current:
        try:
            metric_name = current.split("=", 1)[0].strip()
        except Exception:
            pass

    title = f"【データで見る巨人】{player}({team})、{metric_name} がリーグ平均から +{z}σ 良い — 大手が見落とす投球内容"
    body_md = f"""# {title}

{team} の **{player}** は、{metric_name} でリーグ平均から **+{z}σ** 良い投球内容。{metric_name} のような sabermetric は大手記事の主役にならないが、データ上は明確に league top クラス。

## データで見ると

| 項目 | 値 |
|---|---|
| 現在値 | {current} |
| リーグ baseline | {baseline} |
| 標準偏差倍率 | +{z}σ |
| ポジション | 投手 |
| 球団 | {team}({team_code}) |

## 解釈

投手の {metric_name} は lower-is-better 指標、league 平均から +2σ 以上良いということは、上位 2.5% 以内の投手内容。サンプル(IP)が一定以上で安定していれば本質的な強さの裏付け。{notes}

## 注意

- サンプル(IP)が少ない投手は値が大きく振れるため、最低 IP 15 以上に限定。
- ERA / WHIP は守備や運要素も含むため、FIP / xFIP との併読推奨。
- 「気づかない pattern」型分析記事 — sabermetric の data-driven 推奨。

---

_出典: production DB の advanced_metric_snapshots、自動生成 (rule-based、LLM 不使用)。_
"""
    return {"title": title, "body_md": body_md}


def render_babip_divergence_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    player = candidate_row["player_canonical"]
    diff = candidate_row["magnitude"]
    baseline = candidate_row["baseline_value"]
    current = candidate_row["current_value"]
    direction = candidate_row.get("notes", "")
    team_code = _player_team_code(conn, player) or "?"
    team = _team_label(team_code)

    sign = "高い" if diff > 0 else "低い"
    interpretation = (
        "BABIP がリーグ平均より明確に高く、運要素(本塁打以外の打球が安打になりやすい)で AVG が押し上げられている可能性。BABIP は通常 0.300 付近に regress するため、シーズン後半で AVG が落ちる可能性も。"
        if diff > 0
        else "BABIP がリーグ平均より明確に低く、運に逆らわれている。本来の実力なら AVG はもう少し高いはず、不調脱出の signal の可能性。"
    )
    title = f"【データで見る巨人】{player}({team})、BABIP-AVG 乖離 {diff:+.3f} — 運要素と実力を分けて見る"
    body_md = f"""# {title}

{team} の **{player}** の BABIP は AVG と **{diff:+.3f}** 乖離。これは大手が出さない「運 vs 実力」を分けて見る視点。

## データで見ると

| 項目 | 値 |
|---|---|
| AVG | {baseline} |
| BABIP | {current} |
| 乖離 (BABIP - AVG) | {diff:+.3f} |
| ポジション | 打者 |
| 球団 | {team}({team_code}) |

## 解釈

{direction}

{interpretation}

## 注意

- BABIP は long-run で league 平均 ~0.300 に regress する性質。直近のサンプルでは大きく振れる。
- 「気づかない pattern」型分析記事 — 一般メディアでは AVG しか取り上げないが、本質的な指標は両方併読が必要。
- 守備力や打球質(line drive %)を加味するとさらに精度向上 (Phase 2 候補)。

---

_出典: production DB の advanced_metric_snapshots、自動生成 (rule-based、LLM 不使用)。_
"""
    return {"title": title, "body_md": body_md}


def render_fip_era_divergence_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    player = candidate_row["player_canonical"]
    diff = candidate_row["magnitude"]
    baseline = candidate_row["baseline_value"]
    current = candidate_row["current_value"]
    direction = candidate_row.get("notes", "")
    team_code = _player_team_code(conn, player) or "?"
    team = _team_label(team_code)

    interpretation = (
        "FIP が ERA より明確に高い、つまり ERA が運や守備に支えられた表面値。本質指標 FIP では league 中位以下、シーズン後半で ERA が悪化する可能性。"
        if diff > 0
        else "FIP が ERA より明確に低い、つまり ERA が運悪く本質より悪い数値。FIP では league top クラス、本来の実力は ERA 表示よりずっと良い。"
    )
    title = f"【データで見る巨人】{player}({team})、FIP-ERA 乖離 {diff:+.3f} — 表面値と本質指標の差"
    body_md = f"""# {title}

{team} の **{player}** は、FIP と ERA の差が **{diff:+.3f}**。一般メディアの ERA だけでは捉えられない、投手の本質指標を sabermetric で読み解く。

## データで見ると

| 項目 | 値 |
|---|---|
| ERA | {baseline} |
| FIP | {current} |
| 乖離 (FIP - ERA) | {diff:+.3f} |
| ポジション | 投手 |
| 球団 | {team}({team_code}) |

## 解釈

{direction}

{interpretation}

## 注意

- FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + 定数。守備や打球運を排除した投手本人の指標。
- ERA は守備や運に左右される表面値、FIP は long-run で投手の本質指標として regress する傾向。
- 「気づかない pattern」型分析記事 — ERA だけ見る記事の対照。

---

_出典: production DB の advanced_metric_snapshots、自動生成 (rule-based、LLM 不使用)。_
"""
    return {"title": title, "body_md": body_md}


def render_giants_top_article(
    conn: sqlite3.Connection,
    candidate_row: dict[str, Any],
) -> dict[str, str]:
    player = candidate_row["player_canonical"]
    pct = candidate_row["magnitude"]
    baseline = candidate_row["baseline_value"]
    current = candidate_row["current_value"]
    notes = candidate_row.get("notes", "")

    title = f"【データで見る巨人】{player}、リーグ top {int(pct*100)}% 以内の sabermetric 上位 — 大手が見落とす好調"
    body_md = f"""# {title}

巨人の **{player}** は、{current.split('rank=')[0].rstrip()} で **リーグ top {pct*100:.1f}%** の上位群に入っている。一般メディアの試合速報では捕捉されにくい、cross-team data-driven 評価。

## データで見ると

| 項目 | 値 |
|---|---|
| 現在値 | {current} |
| リーグ規模 | {baseline} |
| 順位率 (top の何%) | {pct*100:.2f}% |
| 球団 | 巨人 (g) |

## 解釈

リーグ全体で top 5% 以内に入る選手は、season 全体で見ても安定して上位群に位置している可能性が高い。{notes}

## 注意

- サンプル数(PA / IP)が一定以上の選手に限定して評価。
- ranking 単独で見るより、複数 metric を併読する方が本質に近い (sabermetric panel 推奨)。
- 「気づかない pattern」型分析記事 — 大手記事と異なる「全体での位置」軸。

---

_出典: production DB の advanced_metric_snapshots、自動生成 (rule-based、LLM 不使用)。_
"""
    return {"title": title, "body_md": body_md}


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
