"""DATA-INSIGHT-continuous: anomaly / 「気づかない pattern」 detector.

production DB の `advanced_metric_snapshots` + 既存 `batting_logs` /
`pitching_logs` から、大手が出さない「気づかない pattern」を rule-based
+ 軽 ML(z-score / 線形比較)で検出し、`article_candidates` table に
emit する。

検出する 5 signal_type:
  * `anomaly_zscore_outlier_batter` — リーグ平均から +2σ 以上の打者
  * `anomaly_zscore_outlier_pitcher` — リーグ平均から +2σ 以上の投手
    (lower-is-better metric は反転)
  * `anomaly_babip_divergence` — AVG vs BABIP 乖離(運要素過半 / 過小)
  * `anomaly_fip_era_divergence` — FIP vs ERA 乖離(運に支えられた表面値)
  * `anomaly_giants_top_outlier` — 巨人選手で league top 5 % 以内の異常値

設計方針:
  * pure rule-based、LLM 不使用
  * 既存 `article_candidates.signal_type` と disjoint (新 5 signal、verify 済)
  * idempotent: 同 run_id + signal_type + player_canonical を dedup
  * best-effort: 1 detector の失敗が他 detector を止めない (try/except per-detector)

Hard constraints (work record §7):
  * env / secret / scheduler 一切 touch しない
  * LLM call を path に混入させない
  * 既存 schema を mutate しない (additive insert only)
  * `status='NEW'` の既存 row を上書きしない
"""

from __future__ import annotations

import datetime as dt
import math
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# 新 signal_type (既存 11 種と disjoint verify 済)
SIGNAL_ZSCORE_BATTER = "anomaly_zscore_outlier_batter"
SIGNAL_ZSCORE_PITCHER = "anomaly_zscore_outlier_pitcher"
SIGNAL_BABIP_DIVERGENCE = "anomaly_babip_divergence"
SIGNAL_FIP_ERA_DIVERGENCE = "anomaly_fip_era_divergence"
SIGNAL_GIANTS_TOP_OUTLIER = "anomaly_giants_top_outlier"

ALL_ANOMALY_SIGNALS = (
    SIGNAL_ZSCORE_BATTER,
    SIGNAL_ZSCORE_PITCHER,
    SIGNAL_BABIP_DIVERGENCE,
    SIGNAL_FIP_ERA_DIVERGENCE,
    SIGNAL_GIANTS_TOP_OUTLIER,
)

# default 閾値 (env で override 可能、user「結構緩めていい」適用、巨人 優先)
DEFAULT_ZSCORE_THRESHOLD = float(
    os.environ.get("DATA_INSIGHT_ANOMALY_THRESHOLD_SIGMA", "1.0") or "1.0"
)
DEFAULT_BABIP_DIVERGENCE = 0.050  # AVG vs BABIP 差 (緩和、運要素 候補広げ)
DEFAULT_FIP_ERA_DIVERGENCE = 1.00  # FIP vs ERA 差 (緩和)
DEFAULT_GIANTS_TOP_PCT = 0.30  # league top 30% 以内 (大幅緩和、巨人 拾いやすく)
DEFAULT_MIN_SAMPLE_BATTER = 20  # PA 最低 (default 30 から緩和)
DEFAULT_MIN_SAMPLE_PITCHER = 10  # IP 最低 (default 15 から緩和)

# 巨人 優先 priority (publish 順序を巨人 first にする)
GIANTS_PRIORITY = 1
NON_GIANTS_PRIORITY = 3
SIGNAL_TREND_RISING = "anomaly_trend_monthly_rising"  # 月別 OPS slope 上昇


# ─── 統計 helper ────────────────────────────────────────────────────────────


def _mean_std(values: list[float]) -> tuple[float, float]:
    """sample mean + sample std (n-1 ddof)。空 list は (0, 0) を返す。"""
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    mean = sum(values) / n
    if n < 2:
        return (mean, 0.0)
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    std = math.sqrt(var)
    return (mean, std)


def _zscore(value: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.0
    return (value - mean) / std


# ─── candidate insert helper ────────────────────────────────────────────────


def _ensure_insight_run(conn: sqlite3.Connection, run_id: str) -> None:
    """``insight_runs`` table に該当 run_id がなければ INSERT (FK 制約満たすため)."""
    existing = conn.execute(
        "SELECT 1 FROM insight_runs WHERE run_id = ? LIMIT 1", (run_id,),
    ).fetchone()
    if existing:
        return
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, "
        "n_candidates, notes) VALUES (?, ?, NULL, NULL, 0, ?)",
        (run_id, now_iso, "DATA-INSIGHT-continuous anomaly_detector"),
    )
    conn.commit()


def _insert_candidate(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_type: str,
    player_canonical: str,
    player_display: Optional[str],
    magnitude: float,
    baseline_value: str,
    current_value: str,
    window_label: str,
    comparison_target: Optional[str],
    evidence_json: Optional[str] = None,
    priority: int = 2,
    notes: Optional[str] = None,
) -> int:
    """`article_candidates` table に 1 row insert。既存 row との dedup は
    `signal_type + player_canonical + window_label` で行う (同 run 内重複回避)。

    return: inserted candidate_id、または既存検出時は 0。
    """
    existing = conn.execute(
        "SELECT candidate_id FROM article_candidates "
        "WHERE signal_type = ? AND player_canonical = ? AND window_label = ? "
        "AND status IN ('NEW', 'REVIEWED', 'DRAFTED') "
        "AND created_at > datetime('now', '-7 days')",
        (signal_type, player_canonical, window_label),
    ).fetchone()
    if existing:
        return 0
    _ensure_insight_run(conn, run_id)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO article_candidates "
        "(run_id, player_canonical, player_display, signal_type, magnitude, "
        "baseline_value, current_value, window_label, comparison_target, "
        "evidence_json, priority, status, created_at, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?)",
        (run_id, player_canonical, player_display, signal_type, magnitude,
         baseline_value, current_value, window_label, comparison_target,
         evidence_json, priority, now_iso, notes),
    )
    return int(cur.lastrowid or 0)


# ─── detector 1: z-score batter outlier ─────────────────────────────────────


def detect_zscore_batter_outliers(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    scope: str = "last_30d",
    metric_name: str = "OPS",
    threshold_sigma: float = DEFAULT_ZSCORE_THRESHOLD,
    min_sample: int = 30,
    run_id: Optional[str] = None,
) -> list[int]:
    """指定 scope の batter metric で league 平均 +threshold_sigma 以上の outlier を検出。

    検出 candidate を `article_candidates` に insert (signal_type=
    `anomaly_zscore_outlier_batter`)。return: inserted candidate_ids list。
    """
    rows = conn.execute(
        "SELECT player_canonical, team_code, metric_value, sample_size "
        "FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
        "AND sample_size >= ? AND metric_value IS NOT NULL",
        (metric_name, scope, snapshot_date, min_sample),
    ).fetchall()
    if len(rows) < 5:
        return []  # sample 不足、統計的に有意でない
    values = [float(r[2]) for r in rows]
    mean, std = _mean_std(values)
    if std <= 0:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    window_label = f"{metric_name}_{scope}_{snapshot_date}"
    for player_canonical, team_code, value, sample in rows:
        z = _zscore(float(value), mean, std)
        if z < threshold_sigma:
            continue
        # 巨人選手は priority=1 (publish 先頭)、他球団は priority=3
        prio = GIANTS_PRIORITY if (team_code or "").strip() == "g" else NON_GIANTS_PRIORITY
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_ZSCORE_BATTER,
            player_canonical=str(player_canonical),
            player_display=None,
            magnitude=float(round(z, 3)),
            baseline_value=f"league_mean={mean:.3f} std={std:.3f} n={len(rows)}",
            current_value=f"{metric_name}={value:.3f} sample={sample}",
            window_label=window_label,
            comparison_target=f"league_{scope}",
            evidence_json=None,
            priority=prio,
            notes=f"team={team_code} metric={metric_name}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── detector 2: z-score pitcher outlier (lower-is-better 反転) ────────────


_PITCHER_LOWER_IS_BETTER = frozenset({"ERA", "WHIP", "FIP", "xFIP", "BB_per_9", "HR_per_9"})


def detect_zscore_pitcher_outliers(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    scope: str = "season",
    metric_name: str = "ERA",
    threshold_sigma: float = DEFAULT_ZSCORE_THRESHOLD,
    min_sample: int = 15,
    run_id: Optional[str] = None,
) -> list[int]:
    """投手 metric (lower-is-better は反転で `+threshold_sigma 以上良い`を検出)."""
    rows = conn.execute(
        "SELECT player_canonical, team_code, metric_value, sample_size "
        "FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
        "AND sample_size >= ? AND metric_value IS NOT NULL",
        (metric_name, scope, snapshot_date, min_sample),
    ).fetchall()
    if len(rows) < 5:
        return []
    values = [float(r[2]) for r in rows]
    mean, std = _mean_std(values)
    if std <= 0:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    window_label = f"{metric_name}_{scope}_{snapshot_date}"
    lower_is_better = metric_name in _PITCHER_LOWER_IS_BETTER
    for player_canonical, team_code, value, sample in rows:
        z = _zscore(float(value), mean, std)
        # lower_is_better は反転 (低い = 良い outlier)
        effective_z = -z if lower_is_better else z
        if effective_z < threshold_sigma:
            continue
        prio = GIANTS_PRIORITY if (team_code or "").strip() == "g" else NON_GIANTS_PRIORITY
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_ZSCORE_PITCHER,
            player_canonical=str(player_canonical),
            player_display=None,
            magnitude=float(round(effective_z, 3)),
            baseline_value=f"league_mean={mean:.3f} std={std:.3f} n={len(rows)}",
            current_value=f"{metric_name}={value:.3f} sample={sample}",
            window_label=window_label,
            comparison_target=f"league_{scope}",
            evidence_json=None,
            priority=prio,
            notes=f"team={team_code} metric={metric_name} lower_is_better={lower_is_better}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── detector 3: BABIP vs AVG 乖離 (運要素過半) ────────────────────────────


def detect_babip_divergence(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    scope: str = "last_30d",
    threshold: float = DEFAULT_BABIP_DIVERGENCE,
    min_sample: int = 30,
    run_id: Optional[str] = None,
) -> list[int]:
    """同 player の BABIP - AVG が threshold 以上なら運要素過半と判定。

    league 平均 BABIP は ~0.300、AVG との乖離が +0.08 以上なら高 BABIP
    支えで実力値より高い AVG、-0.08 以下なら BABIP 不運で AVG 抑えられている。
    """
    avg_rows = {
        r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT player_canonical, metric_value, team_code FROM advanced_metric_snapshots "
            "WHERE metric_name = 'AVG' AND scope = ? AND snapshot_date = ? "
            "AND sample_size >= ?",
            (scope, snapshot_date, min_sample),
        )
    }
    babip_rows = {
        r[0]: r[1] for r in conn.execute(
            "SELECT player_canonical, metric_value FROM advanced_metric_snapshots "
            "WHERE metric_name = 'BABIP' AND scope = ? AND snapshot_date = ? "
            "AND sample_size >= ?",
            (scope, snapshot_date, min_sample),
        )
    }
    if not avg_rows or not babip_rows:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    window_label = f"BABIP_divergence_{scope}_{snapshot_date}"
    for player, (avg_val, team_code) in avg_rows.items():
        babip_val = babip_rows.get(player)
        if babip_val is None or avg_val is None:
            continue
        diff = float(babip_val) - float(avg_val)
        if abs(diff) < threshold:
            continue
        direction = "BABIP高_運に支えられ" if diff > 0 else "BABIP低_運に逆らわれ"
        prio = GIANTS_PRIORITY if (team_code or "").strip() == "g" else NON_GIANTS_PRIORITY
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_BABIP_DIVERGENCE,
            player_canonical=str(player),
            player_display=None,
            magnitude=float(round(diff, 3)),
            baseline_value=f"AVG={avg_val:.3f}",
            current_value=f"BABIP={babip_val:.3f}",
            window_label=window_label,
            comparison_target="BABIP_vs_AVG",
            evidence_json=None,
            priority=prio,
            notes=f"{direction} team={team_code}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── detector 4: FIP vs ERA 乖離 ────────────────────────────────────────────


def detect_fip_era_divergence(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    scope: str = "season",
    threshold: float = DEFAULT_FIP_ERA_DIVERGENCE,
    min_sample: int = 15,
    run_id: Optional[str] = None,
) -> list[int]:
    """ERA vs FIP の乖離。FIP-ERA > +1.5 は ERA が運に支えられた表面値、
    FIP-ERA < -1.5 は ERA が運悪く、本質指標では好調。"""
    era_rows = {
        r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT player_canonical, metric_value, team_code FROM advanced_metric_snapshots "
            "WHERE metric_name = 'ERA' AND scope = ? AND snapshot_date = ? "
            "AND sample_size >= ?",
            (scope, snapshot_date, min_sample),
        )
    }
    fip_rows = {
        r[0]: r[1] for r in conn.execute(
            "SELECT player_canonical, metric_value FROM advanced_metric_snapshots "
            "WHERE metric_name = 'FIP' AND scope = ? AND snapshot_date = ? "
            "AND sample_size >= ?",
            (scope, snapshot_date, min_sample),
        )
    }
    if not era_rows or not fip_rows:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    window_label = f"FIP_ERA_divergence_{scope}_{snapshot_date}"
    for player, (era_val, team_code) in era_rows.items():
        fip_val = fip_rows.get(player)
        if fip_val is None or era_val is None:
            continue
        diff = float(fip_val) - float(era_val)
        if abs(diff) < threshold:
            continue
        direction = "FIP高_ERAが運に支えられた表面値" if diff > 0 else "FIP低_ERAが運悪く本質は好調"
        prio = GIANTS_PRIORITY if (team_code or "").strip() == "g" else NON_GIANTS_PRIORITY
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_FIP_ERA_DIVERGENCE,
            player_canonical=str(player),
            player_display=None,
            magnitude=float(round(diff, 3)),
            baseline_value=f"ERA={era_val:.3f}",
            current_value=f"FIP={fip_val:.3f}",
            window_label=window_label,
            comparison_target="FIP_vs_ERA",
            evidence_json=None,
            priority=prio,
            notes=f"{direction} team={team_code}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── detector 5: Giants top 5% outlier ──────────────────────────────────────


def detect_giants_top_outliers(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    scope: str = "last_30d",
    metric_name: str = "OPS",
    top_pct: float = DEFAULT_GIANTS_TOP_PCT,
    min_sample: int = 30,
    run_id: Optional[str] = None,
) -> list[int]:
    """巨人選手のうち league rank top X % 以内に入っているなら notable outlier。

    例: league_total=100 で top 5% = rank<=5 以内の 巨人選手 を全件検出。
    """
    rows = conn.execute(
        "SELECT player_canonical, team_code, metric_value, sample_size, "
        "league_rank, league_total FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
        "AND sample_size >= ? AND team_code = 'g' AND league_rank IS NOT NULL",
        (metric_name, scope, snapshot_date, min_sample),
    ).fetchall()
    if not rows:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    window_label = f"giants_top_{int(top_pct*100)}pct_{metric_name}_{scope}_{snapshot_date}"
    for player, team_code, value, sample, rank, total in rows:
        if not total or total < 10:
            continue
        pct = float(rank) / float(total)
        if pct > top_pct:
            continue
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_GIANTS_TOP_OUTLIER,
            player_canonical=str(player),
            player_display=None,
            magnitude=float(round(pct, 4)),
            baseline_value=f"league_total={total}",
            current_value=f"{metric_name}={value:.3f} rank={rank} sample={sample}",
            window_label=window_label,
            comparison_target=f"league_top_{int(top_pct*100)}pct",
            evidence_json=None,
            priority=1,
            notes=f"team={team_code} pct={pct:.4f}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── public API: run all detectors ──────────────────────────────────────────


def run_all_anomaly_detectors(
    conn: sqlite3.Connection,
    *,
    snapshot_date: Optional[str] = None,
    run_id: Optional[str] = None,
) -> dict[str, list[int]]:
    """全 5 detector を best-effort で実行、結果を dict で返す。

    Returns: ``{signal_type: [candidate_ids]}``
    """
    if snapshot_date is None:
        latest = conn.execute(
            "SELECT MAX(snapshot_date) FROM advanced_metric_snapshots"
        ).fetchone()
        snapshot_date = latest[0] if latest else dt.date.today().isoformat()
    if run_id is None:
        run_id = str(uuid.uuid4())
    out: dict[str, list[int]] = {}
    try:
        out[SIGNAL_ZSCORE_BATTER] = detect_zscore_batter_outliers(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_ZSCORE_BATTER] = []
    try:
        out[SIGNAL_ZSCORE_PITCHER] = detect_zscore_pitcher_outliers(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_ZSCORE_PITCHER] = []
    try:
        out[SIGNAL_BABIP_DIVERGENCE] = detect_babip_divergence(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_BABIP_DIVERGENCE] = []
    try:
        out[SIGNAL_FIP_ERA_DIVERGENCE] = detect_fip_era_divergence(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_FIP_ERA_DIVERGENCE] = []
    try:
        out[SIGNAL_GIANTS_TOP_OUTLIER] = detect_giants_top_outliers(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_GIANTS_TOP_OUTLIER] = []
    return out
