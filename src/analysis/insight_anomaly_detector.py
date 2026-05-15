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

from src.analysis import insight_whitelist as _wl  # noqa: E402


# 新 signal_type (既存 11 種と disjoint verify 済)
SIGNAL_ZSCORE_BATTER = "anomaly_zscore_outlier_batter"
SIGNAL_ZSCORE_PITCHER = "anomaly_zscore_outlier_pitcher"
SIGNAL_BABIP_DIVERGENCE = "anomaly_babip_divergence"
SIGNAL_FIP_ERA_DIVERGENCE = "anomaly_fip_era_divergence"
SIGNAL_GIANTS_TOP_OUTLIER = "anomaly_giants_top_outlier"
SIGNAL_PACE_HR_PROJECTION = "anomaly_pace_hr_projection"
SIGNAL_HIDDEN_OPS_LIMIT = "anomaly_hidden_below_qualifier"  # 規定外好調
SIGNAL_HIT_STREAK_RUN = "anomaly_consecutive_multi_hit"   # 連続多安打 game
# 2026-05-15 user 指示「守備もだよ」適用、守備系 signal を追加。
SIGNAL_DEFENSE_UZR_OUTLIER = "anomaly_defense_uzr_outlier"  # UZR_proxy 平均比
SIGNAL_DEFENSE_FIELDING_PCT = "anomaly_defense_fielding_pct"  # 守備率
# 2026-05-15 user 指示「試合後にファンが気になる指標」適用、試合後 signal を追加。
SIGNAL_GAME_HERO_BATTER = "anomaly_game_hero_batter"  # 今日のヒーロー (打者)
SIGNAL_GAME_PITCHER_PERF = "anomaly_game_pitcher_perf"  # 今日の好投 / 不調 (投手)
SIGNAL_MILESTONE_CROSSED = "anomaly_milestone_crossed"  # シーズン累計節目越え
SIGNAL_STANDINGS_SHIFT = "anomaly_standings_shift"  # 球団順位変動
SIGNAL_STAT_DELTA = "anomaly_stat_delta"  # snapshot 急変

# 2026-05-15 user 指示「C(マニアック)D(サバメトリクス)はいらない、変化率も
# title から消す」適用、publish 対象 signal_type を縮小。 backlog candidate
# (status='NEW' で残った旧 signal) もこの list に無いものは publisher が
# fetch せず、未配信のまま skip される。
#
# disabled 一覧 (DB に NEW 残ってても publish されない):
#   - SIGNAL_BABIP_DIVERGENCE / SIGNAL_FIP_ERA_DIVERGENCE (D サバメトリクス)
#   - SIGNAL_STAT_DELTA (変化率 title が user 不可)
#   - SIGNAL_GIANTS_TOP_OUTLIER / SIGNAL_PACE_HR_PROJECTION /
#     SIGNAL_HIDDEN_OPS_LIMIT / SIGNAL_HIT_STREAK_RUN (C マニアック)
#   - SIGNAL_DEFENSE_UZR_OUTLIER (UZR_proxy はサバメトリクス、守備率は残)
ALL_ANOMALY_SIGNALS = (
    SIGNAL_ZSCORE_BATTER,
    SIGNAL_ZSCORE_PITCHER,
    SIGNAL_DEFENSE_FIELDING_PCT,
    SIGNAL_GAME_HERO_BATTER,
    SIGNAL_GAME_PITCHER_PERF,
    SIGNAL_MILESTONE_CROSSED,
    SIGNAL_STANDINGS_SHIFT,
)

# default 閾値 (env で override 可能、user「もっと緩めていい、metric 多様化」適用、
# 2026-05-15 user 指示で全閾値を約 2x 緩和、記事数 2-3 倍狙い)
DEFAULT_ZSCORE_THRESHOLD = float(
    os.environ.get("DATA_INSIGHT_ANOMALY_THRESHOLD_SIGMA", "0.5") or "0.5"
)
DEFAULT_BABIP_DIVERGENCE = float(
    os.environ.get("DATA_INSIGHT_BABIP_DIVERGENCE", "0.025") or "0.025"
)  # AVG vs BABIP 差 (緩和 0.05 → 0.025)
DEFAULT_FIP_ERA_DIVERGENCE = float(
    os.environ.get("DATA_INSIGHT_FIP_ERA_DIVERGENCE", "0.50") or "0.50"
)  # FIP vs ERA 差 (緩和 1.0 → 0.5)
DEFAULT_GIANTS_TOP_PCT = float(
    os.environ.get("DATA_INSIGHT_GIANTS_TOP_PCT", "0.50") or "0.50"
)  # league top 50% 以内 (緩和 30% → 50%、巨人 さらに拾いやすく)
DEFAULT_MIN_SAMPLE_BATTER = 20  # PA 最低
DEFAULT_MIN_SAMPLE_PITCHER = 10  # IP 最低

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

    348 step 1 gate: × metric (BABIP / wOBA / 等) は冒頭で skip、 baseline 計算
    は 12 球団全選手だが candidate insert は巨人 (team_code='g') のみ。
    """
    if not _wl.is_metric_allowed(metric_name):
        return []
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
        if not _wl.is_subject_team(team_code):
            continue  # baseline には使うが title 主語にはならない
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
            priority=GIANTS_PRIORITY,
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
    """投手 metric (lower-is-better は反転で `+threshold_sigma 以上良い`を検出).

    348 step 1 gate: × metric (FIP / xFIP / WHIP / K_BB) は冒頭で skip、 candidate
    insert は巨人 (team_code='g') のみ。 baseline 計算は 12 球団全選手。
    """
    if not _wl.is_metric_allowed(metric_name):
        return []
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
        if not _wl.is_subject_team(team_code):
            continue  # baseline には使うが title 主語にはならない
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
            priority=GIANTS_PRIORITY,
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


# ─── detector 6: pace HR projection (シーズン換算 HR ペース) ──────────────


def detect_hr_pace_outliers(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    min_games: int = 15,
    run_id: Optional[str] = None,
) -> list[int]:
    """直近 30 日の HR pace から season 換算 (143 試合) で外れ値となる打者を検出。

    各打者の per-game HR 率 × 143 を計算、上位を outlier として emit。
    """
    rows = conn.execute(
        "SELECT bl.player_canonical, bl.team_name, "
        "COUNT(DISTINCT bl.game_id) AS games, SUM(bl.atbats_json IS NOT NULL) AS pa "
        "FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
        "WHERE g.game_date >= date(?, '-30 days') AND bl.player_canonical IS NOT NULL "
        "GROUP BY bl.player_canonical, bl.team_name "
        "HAVING games >= ?",
        (snapshot_date, min_games),
    ).fetchall()
    if not rows:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())

    # per player HR count
    inserted: list[int] = []
    window_label = f"hr_pace_30d_{snapshot_date}"
    for player, team_name, games, pa in rows:
        # parse atbats_json から HR を count
        hrs = 0
        for r in conn.execute(
            "SELECT atbats_json FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
            "WHERE bl.player_canonical = ? AND g.game_date >= date(?, '-30 days')",
            (player, snapshot_date),
        ):
            atbats = r[0]
            if not atbats:
                continue
            try:
                import json as _j
                parsed = _j.loads(atbats) if isinstance(atbats, str) else atbats
            except Exception:
                continue
            if not isinstance(parsed, list):
                continue
            for ab in parsed:
                if isinstance(ab, str) and ("本" in ab):
                    hrs += 1
        if hrs < 3:  # 30 日で 3 本以上 = season 換算 14 本以上 ペース
            continue
        proj = round(hrs / max(games, 1) * 143, 1)  # 143 試合 season
        if proj < 15:  # 換算 15 本未満は skip
            continue
        team_code = _resolve_team_code_from_name(team_name or "")
        if team_code == "unknown":
            continue
        prio = GIANTS_PRIORITY if team_code == "g" else NON_GIANTS_PRIORITY
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_PACE_HR_PROJECTION,
            player_canonical=str(player),
            player_display=None,
            magnitude=float(proj),
            baseline_value=f"30日HR={hrs} 試合={games}",
            current_value=f"season換算HR={proj:.1f}本",
            window_label=window_label,
            comparison_target="143game_pace",
            evidence_json=None,
            priority=prio,
            notes=f"team={team_code}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── detector 7: 規定外好調 (hidden below qualifier) ──────────────────────


def detect_hidden_below_qualifier_outliers(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    metric_name: str = "OPS",
    scope: str = "last_30d",
    ops_threshold: float = 0.900,
    min_sample: int = 10,
    max_sample: int = 50,
    run_id: Optional[str] = None,
) -> list[int]:
    """規定打席外(サンプル <= max_sample)で metric 値が threshold 以上の隠れ好調を検出。

    大手は規定外なので記事化しない、ヨシラバー独自の data 角度。
    """
    rows = conn.execute(
        "SELECT player_canonical, team_code, metric_value, sample_size "
        "FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
        "AND metric_value >= ? AND sample_size >= ? AND sample_size <= ?",
        (metric_name, scope, snapshot_date, ops_threshold, min_sample, max_sample),
    ).fetchall()
    if not rows:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    window_label = f"hidden_below_qualifier_{metric_name}_{scope}_{snapshot_date}"
    for player, team_code, value, sample in rows:
        prio = GIANTS_PRIORITY if (team_code or "").strip() == "g" else NON_GIANTS_PRIORITY
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_HIDDEN_OPS_LIMIT,
            player_canonical=str(player),
            player_display=None,
            magnitude=float(round(value, 3)),
            baseline_value=f"{metric_name}_threshold={ops_threshold}",
            current_value=f"{metric_name}={value:.3f} sample={sample}",
            window_label=window_label,
            comparison_target="below_qualifier",
            evidence_json=None,
            priority=prio,
            notes=f"team={team_code} 規定外好調",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── detector 8: 連続多安打 game streak ───────────────────────────────────


def detect_consecutive_multi_hit_streak(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    min_streak: int = 3,
    run_id: Optional[str] = None,
) -> list[int]:
    """連続 N 試合以上で multi-hit (2安打+) を記録した打者を検出。"""
    # player 別 game_date 順に H>=2 を判定
    rows = conn.execute(
        "SELECT bl.player_canonical, bl.team_name, g.game_date, bl.H "
        "FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
        "WHERE bl.player_canonical IS NOT NULL AND bl.H IS NOT NULL "
        "AND g.game_date >= date(?, '-30 days') "
        "ORDER BY bl.player_canonical, g.game_date ASC",
        (snapshot_date,),
    ).fetchall()
    if not rows:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())

    # streak 計算 per player
    from collections import defaultdict
    player_seqs: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for player, team_name, gdate, h in rows:
        player_seqs[str(player)].append((str(team_name or ""), gdate, int(h or 0)))

    inserted: list[int] = []
    window_label = f"multi_hit_streak_30d_{snapshot_date}"
    for player, seq in player_seqs.items():
        # 直近の連続 streak を後ろから計算
        streak = 0
        last_team_name = ""
        for team_name, _, h in reversed(seq):
            if h >= 2:
                streak += 1
                last_team_name = team_name
            else:
                break
        if streak < min_streak:
            continue
        team_code = _resolve_team_code_from_name(last_team_name)
        if team_code == "unknown":
            continue
        prio = GIANTS_PRIORITY if team_code == "g" else NON_GIANTS_PRIORITY
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_HIT_STREAK_RUN,
            player_canonical=player,
            player_display=None,
            magnitude=float(streak),
            baseline_value=f"min_streak={min_streak}",
            current_value=f"連続{streak}試合multi-hit",
            window_label=window_label,
            comparison_target="consecutive_multi_hit",
            evidence_json=None,
            priority=prio,
            notes=f"team={team_code}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── detector 9 / 10: 守備 (UZR_proxy / fielding_pct) ───────────────────────
# 2026-05-15 user 指示「守備もだよ」適用。defense_opportunities table から
# RF_proxy / UZR_proxy / fielding_pct を集計し、巨人選手をポジション別に
# league baseline と比較する。真の UZR ではなく box-score 由来の proxy だが、
# 「守備が平均より良い / 悪い」傾向は数値で示せる。
#
# 注: defense_opportunities は ``hits_allowed`` を持つが、これは「打球方向が
# その position に飛び、安打となった」を示すので、(converted_outs + errors)
# とは別の母数。 fielding_pct は伝統的に PO+A vs E の比なので、
# converted_outs / (converted_outs + errors) を採用 (PB / WP は box から
# 取得困難なため次世代対応)。


DEFAULT_DEFENSE_UZR_THRESHOLD = float(
    os.environ.get("DATA_INSIGHT_DEFENSE_UZR_THRESHOLD", "0.05") or "0.05"
)  # |RF_proxy - league_baseline| >= 5% 以上
DEFAULT_DEFENSE_FIELDING_PCT_THRESHOLD = float(
    os.environ.get("DATA_INSIGHT_DEFENSE_FIELDING_PCT_THRESHOLD", "0.03") or "0.03"
)  # |fielding_pct - league_baseline| >= 3% 以上
DEFAULT_DEFENSE_MIN_OPPORTUNITIES = int(
    os.environ.get("DATA_INSIGHT_DEFENSE_MIN_OPPORTUNITIES", "10") or "10"
)


def _giants_defense_rows(
    conn: sqlite3.Connection, *, since_date: str
) -> list[dict]:
    """直近の Giants 守備 opportunities を player × position で aggregate。"""
    rows = conn.execute(
        "SELECT d.player_canonical, d.position, "
        "SUM(d.opportunities) AS opps, "
        "SUM(d.converted_outs) AS outs, "
        "SUM(d.errors) AS errs "
        "FROM defense_opportunities d "
        "JOIN games g ON d.game_id = g.game_id "
        "WHERE d.team_code = 'g' "
        "AND d.player_canonical IS NOT NULL "
        "AND g.game_date >= ? "
        "GROUP BY d.player_canonical, d.position",
        (since_date,),
    ).fetchall()
    return [
        {
            "player": str(r[0]),
            "position": str(r[1]),
            "opportunities": int(r[2] or 0),
            "converted_outs": int(r[3] or 0),
            "errors": int(r[4] or 0),
        }
        for r in rows
    ]


def _league_position_baseline(
    conn: sqlite3.Connection, *, position: str, since_date: str
) -> tuple[Optional[float], Optional[float]]:
    """指定 position の league 平均 (RF_proxy, fielding_pct) を返す。"""
    row = conn.execute(
        "SELECT SUM(opportunities), SUM(converted_outs), SUM(errors) "
        "FROM defense_opportunities d "
        "JOIN games g ON d.game_id = g.game_id "
        "WHERE d.position = ? AND g.game_date >= ?",
        (position, since_date),
    ).fetchone()
    if not row or not row[0]:
        return None, None
    opps = int(row[0] or 0)
    outs = int(row[1] or 0)
    errs = int(row[2] or 0)
    if opps <= 0:
        return None, None
    rf_baseline = outs / opps
    denom = outs + errs
    fpct_baseline = (outs / denom) if denom > 0 else None
    return rf_baseline, fpct_baseline


def detect_giants_defense_outliers(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    window_days: int = 30,
    min_opportunities: int = DEFAULT_DEFENSE_MIN_OPPORTUNITIES,
    uzr_threshold: float = DEFAULT_DEFENSE_UZR_THRESHOLD,
    fielding_pct_threshold: float = DEFAULT_DEFENSE_FIELDING_PCT_THRESHOLD,
    run_id: Optional[str] = None,
) -> tuple[list[int], list[int]]:
    """Giants 選手の守備 outlier を検出 (UZR_proxy + fielding_pct 二系列)。

    `window_days` 期間 (default 30 日) の defense_opportunities を集計し、
    player × position で league baseline と比較。閾値超えで candidate insert。

    Returns: ``(uzr_candidate_ids, fielding_pct_candidate_ids)``
    """
    since_date = (
        dt.date.fromisoformat(snapshot_date) - dt.timedelta(days=window_days)
    ).isoformat()
    rows = _giants_defense_rows(conn, since_date=since_date)
    if not rows:
        return [], []
    if run_id is None:
        run_id = str(uuid.uuid4())

    uzr_ids: list[int] = []
    fpct_ids: list[int] = []
    uzr_window = f"defense_uzr_30d_{snapshot_date}"
    fpct_window = f"defense_fpct_30d_{snapshot_date}"

    # baseline は position ごとに 1 回だけ計算 (call 回数削減)
    baseline_cache: dict[str, tuple[Optional[float], Optional[float]]] = {}
    for r in rows:
        if r["opportunities"] < min_opportunities:
            continue
        pos = r["position"]
        if pos not in baseline_cache:
            baseline_cache[pos] = _league_position_baseline(
                conn, position=pos, since_date=since_date
            )
        rf_baseline, fpct_baseline = baseline_cache[pos]
        rf_player = r["converted_outs"] / r["opportunities"]
        denom = r["converted_outs"] + r["errors"]
        fpct_player = (r["converted_outs"] / denom) if denom > 0 else None

        # ── UZR_proxy outlier ────────────────────────────────────────────
        if rf_baseline is not None:
            uzr_value = rf_player - rf_baseline
            if abs(uzr_value) >= uzr_threshold:
                direction = "守備平均超え" if uzr_value > 0 else "守備平均未満"
                cid = _insert_candidate(
                    conn,
                    run_id=run_id,
                    signal_type=SIGNAL_DEFENSE_UZR_OUTLIER,
                    player_canonical=r["player"],
                    player_display=None,
                    magnitude=float(round(uzr_value, 4)),
                    baseline_value=(
                        f"position={pos} league_RF_baseline={rf_baseline:.3f}"
                    ),
                    current_value=(
                        f"RF_proxy={rf_player:.3f} opportunities={r['opportunities']} "
                        f"converted_outs={r['converted_outs']} errors={r['errors']}"
                    ),
                    window_label=uzr_window,
                    comparison_target=f"defense_uzr_{pos}",
                    evidence_json=None,
                    priority=GIANTS_PRIORITY,
                    notes=f"position={pos} {direction}",
                )
                if cid:
                    uzr_ids.append(cid)

        # ── fielding_pct outlier ─────────────────────────────────────────
        if fpct_baseline is not None and fpct_player is not None:
            fpct_diff = fpct_player - fpct_baseline
            if abs(fpct_diff) >= fielding_pct_threshold:
                direction = "守備率高" if fpct_diff > 0 else "守備率低"
                cid = _insert_candidate(
                    conn,
                    run_id=run_id,
                    signal_type=SIGNAL_DEFENSE_FIELDING_PCT,
                    player_canonical=r["player"],
                    player_display=None,
                    magnitude=float(round(fpct_diff, 4)),
                    baseline_value=(
                        f"position={pos} league_fpct_baseline={fpct_baseline:.3f}"
                    ),
                    current_value=(
                        f"fielding_pct={fpct_player:.3f} converted_outs={r['converted_outs']} "
                        f"errors={r['errors']}"
                    ),
                    window_label=fpct_window,
                    comparison_target=f"defense_fpct_{pos}",
                    evidence_json=None,
                    priority=GIANTS_PRIORITY,
                    notes=f"position={pos} {direction}",
                )
                if cid:
                    fpct_ids.append(cid)
    conn.commit()
    return uzr_ids, fpct_ids


# ─── detector 11-15: 試合後 ファンが気になる指標 (2026-05-15 user 指示) ────
# 試合後、選手と球団の「ファンが気になる」を data から自動抽出して記事化。
#   - A: 今日のヒーロー (打者活躍)        SIGNAL_GAME_HERO_BATTER
#   - B: 投手の好投 / 不調              SIGNAL_GAME_PITCHER_PERF
#   - C: シーズン節目越え / 順位変動    SIGNAL_MILESTONE_CROSSED / SIGNAL_STANDINGS_SHIFT
#   - D: 数字の急変 (snapshot delta)    SIGNAL_STAT_DELTA


def _latest_giants_game(
    conn: sqlite3.Connection, *, snapshot_date: str
) -> Optional[dict]:
    """``snapshot_date`` 以前で最新の Giants 試合 (result 確定済) を返す。"""
    row = conn.execute(
        "SELECT game_id, game_date, opponent, result, giants_score, opp_score, "
        "winning_pitcher, losing_pitcher, save_pitcher "
        "FROM games WHERE result IS NOT NULL AND result != 'unknown' "
        "AND game_date <= ? ORDER BY game_date DESC, game_id DESC LIMIT 1",
        (snapshot_date,),
    ).fetchone()
    if not row:
        return None
    return {
        "game_id": str(row[0]),
        "game_date": str(row[1]),
        "opponent": str(row[2] or ""),
        "result": str(row[3] or ""),
        "giants_score": row[4],
        "opp_score": row[5],
        "winning_pitcher": str(row[6] or ""),
        "losing_pitcher": str(row[7] or ""),
        "save_pitcher": str(row[8] or ""),
    }


def detect_game_hero_batter(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """A: 直近 Giants 試合で活躍した打者を「今日のヒーロー」候補化。

    対象基準 (いずれか満たせば候補化):
      - H >= 3 (multi-hit 以上)
      - H >= 2 AND RBI >= 1
      - RBI >= 2
      - HR を 1 本以上 (atbats_json に 'HR' 含む)
    """
    import json as _json
    game = _latest_giants_game(conn, snapshot_date=snapshot_date)
    if not game:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    rows = conn.execute(
        "SELECT player_canonical, player_display, AB, R, H, RBI, SB, atbats_json "
        "FROM batting_logs WHERE game_id = ? AND team_role = 'giants' "
        "AND player_canonical IS NOT NULL",
        (game["game_id"],),
    ).fetchall()
    inserted: list[int] = []
    window_label = f"game_hero_{game['game_date']}_{game['game_id']}"
    for player, display, ab, r, h, rbi, sb, atbats_json in rows:
        ab = int(ab or 0); r = int(r or 0); h = int(h or 0)
        rbi = int(rbi or 0); sb = int(sb or 0)
        hr_count = 0
        if atbats_json:
            try:
                ab_list = _json.loads(atbats_json) or []
                hr_count = sum(1 for x in ab_list if "HR" in str(x))
            except Exception:  # noqa: BLE001
                hr_count = 0
        qualifies = (
            h >= 3
            or (h >= 2 and rbi >= 1)
            or rbi >= 2
            or hr_count >= 1
        )
        if not qualifies:
            continue
        magnitude = float(h + rbi + (hr_count * 2))  # 簡易 hero score
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_GAME_HERO_BATTER,
            player_canonical=str(player),
            player_display=str(display) if display else None,
            magnitude=magnitude,
            baseline_value=f"game={game['game_id']} opponent={game['opponent']} result={game['result']}",
            current_value=f"AB={ab} R={r} H={h} RBI={rbi} HR={hr_count} SB={sb}",
            window_label=window_label,
            comparison_target=f"giants_game_{game['game_date']}",
            evidence_json=None,
            priority=GIANTS_PRIORITY,
            notes=f"hero_score={magnitude} game_score={game['giants_score']}-{game['opp_score']}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


def detect_game_pitcher_performance(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """B: 直近 Giants 試合で登板した投手の好投 / 不調を検出。

    対象基準 (いずれか満たせば候補化):
      - 好投: IP >= 5 AND ER <= 2 (先発の quality start 近似)
      - 救援好投: IP >= 1 AND ER == 0 AND result_mark in ('S','H')
      - 不調: IP < 5 AND ER >= 4 (KO 級)
    """
    game = _latest_giants_game(conn, snapshot_date=snapshot_date)
    if not game:
        return []
    if run_id is None:
        run_id = str(uuid.uuid4())
    rows = conn.execute(
        "SELECT player_canonical, player_display, appearance_order, result_mark, "
        "IP, H_allowed, BB, K, ER, HR_allowed "
        "FROM pitching_logs WHERE game_id = ? AND team_role = 'giants' "
        "AND player_canonical IS NOT NULL",
        (game["game_id"],),
    ).fetchall()
    inserted: list[int] = []
    window_label = f"game_pitcher_{game['game_date']}_{game['game_id']}"
    for player, display, order, result_mark, ip, h_allowed, bb, k, er, hr_allowed in rows:
        ip = float(ip or 0); er = int(er or 0); k = int(k or 0)
        h_allowed = int(h_allowed or 0); bb = int(bb or 0)
        hr_allowed = int(hr_allowed or 0)
        result_mark = str(result_mark or "")
        qualifies_good = (ip >= 5 and er <= 2) or (
            ip >= 1 and er == 0 and result_mark in ("S", "H", "勝")
        )
        qualifies_bad = ip < 5 and er >= 4
        if not (qualifies_good or qualifies_bad):
            continue
        direction = "好投" if qualifies_good else "不調"
        magnitude = float(round(k - er * 2, 2))  # 簡易 quality score
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_GAME_PITCHER_PERF,
            player_canonical=str(player),
            player_display=str(display) if display else None,
            magnitude=magnitude,
            baseline_value=f"game={game['game_id']} opponent={game['opponent']} result={game['result']}",
            current_value=f"IP={ip} H={h_allowed} BB={bb} K={k} ER={er} HR={hr_allowed} mark={result_mark}",
            window_label=window_label,
            comparison_target=f"giants_game_{game['game_date']}",
            evidence_json=None,
            priority=GIANTS_PRIORITY,
            notes=f"direction={direction} order={order}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# C-1: シーズン累計の節目越え (HR / 防御率 / WHIP)
# 2026-05-15 サバメトリクス drop で FIP は除外。
_MILESTONE_THRESHOLDS_BATTER = {
    "HR": (5, 10, 15, 20, 25, 30),       # 本塁打 5/10/15/20/25/30
}
_MILESTONE_THRESHOLDS_PITCHER_LOWER = {
    "ERA": (2.00, 2.50, 3.00),           # 防御率 (低い方が良い)、threshold を下回ったら milestone
    "WHIP": (1.00, 1.10, 1.20),
}


def detect_milestone_crossed(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """C-1: Giants 選手のシーズン累計が境界 (milestone) を越えたか check。

    現状 snapshot_date のみ見て「閾値超えてる」を全件出す簡易版。重複防止
    は ``_insert_candidate`` の (player + window_label) dedup に任せる。
    """
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    window_label = f"milestone_{snapshot_date}"

    for metric, thresholds in _MILESTONE_THRESHOLDS_BATTER.items():
        rows = conn.execute(
            "SELECT player_canonical, metric_value, sample_size "
            "FROM advanced_metric_snapshots "
            "WHERE metric_name = ? AND scope = 'season' AND snapshot_date = ? "
            "AND team_code = 'g' AND metric_value IS NOT NULL",
            (metric, snapshot_date),
        ).fetchall()
        for player, value, sample in rows:
            value = float(value or 0)
            # 直近に超えた threshold を 1 つだけ採用 (最も大きいもの)
            crossed = max((t for t in thresholds if value >= t), default=None)
            if crossed is None:
                continue
            cid = _insert_candidate(
                conn,
                run_id=run_id,
                signal_type=SIGNAL_MILESTONE_CROSSED,
                player_canonical=str(player),
                player_display=None,
                magnitude=float(crossed),
                baseline_value=f"threshold={crossed}",
                current_value=f"{metric}={value:.0f} sample={sample}",
                window_label=window_label,
                comparison_target=f"milestone_{metric}_{int(crossed)}",
                evidence_json=None,
                priority=GIANTS_PRIORITY,
                notes=f"metric={metric} threshold={crossed} value={value:.0f}",
            )
            if cid:
                inserted.append(cid)

    for metric, thresholds in _MILESTONE_THRESHOLDS_PITCHER_LOWER.items():
        rows = conn.execute(
            "SELECT player_canonical, metric_value, sample_size "
            "FROM advanced_metric_snapshots "
            "WHERE metric_name = ? AND scope = 'season' AND snapshot_date = ? "
            "AND team_code = 'g' AND metric_value IS NOT NULL",
            (metric, snapshot_date),
        ).fetchall()
        for player, value, sample in rows:
            value = float(value or 0)
            if value <= 0:
                continue
            # threshold を下回ってるか、低い方から
            crossed = min((t for t in thresholds if value <= t), default=None)
            if crossed is None:
                continue
            cid = _insert_candidate(
                conn,
                run_id=run_id,
                signal_type=SIGNAL_MILESTONE_CROSSED,
                player_canonical=str(player),
                player_display=None,
                magnitude=float(crossed),
                baseline_value=f"threshold={crossed}",
                current_value=f"{metric}={value:.3f} sample={sample}",
                window_label=window_label,
                comparison_target=f"milestone_{metric}_{crossed}",
                evidence_json=None,
                priority=GIANTS_PRIORITY,
                notes=f"metric={metric} threshold={crossed} value={value:.3f} (lower_is_better)",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


# ─── 348 step 3 part 2: record / milestone event detectors ──────────────


def detect_cycle_hits(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """サイクルヒット検出 (348 step 3 part 2)。

    snapshot_date の Giants 試合の batting_logs.atbats_json を parse、
    同一打者で 1B + 2B + 3B + HR を 1 試合で達成した player を検出。
    """
    import json as _json
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []

    rows = conn.execute(
        "SELECT bl.game_id, bl.player_canonical, bl.atbats_json, g.opponent "
        "FROM batting_logs bl JOIN games g ON bl.game_id = g.game_id "
        "WHERE g.game_date = ? AND bl.team_name LIKE '%巨人%' "
        "AND bl.player_canonical IS NOT NULL AND bl.atbats_json IS NOT NULL",
        (snapshot_date,),
    ).fetchall()

    for game_id, player, atbats_json, opponent in rows:
        try:
            atbats = _json.loads(atbats_json) if isinstance(atbats_json, str) else atbats_json
        except (ValueError, TypeError):
            continue
        if not isinstance(atbats, list):
            continue
        hit_types: set[int] = set()
        for ab_text in atbats:
            if not isinstance(ab_text, str):
                continue
            try:
                from src.analysis import insight_atbats_parser as _parser
                parsed = _parser.parse_atbat(ab_text)
            except Exception:  # noqa: BLE001
                continue
            if parsed.get("is_hr"):
                hit_types.add(4)
            elif parsed.get("result_class") == "hit":
                bases = int(parsed.get("bases") or 0)
                if bases in (1, 2, 3):
                    hit_types.add(bases)
        if hit_types == {1, 2, 3, 4}:
            window_label = f"cycle_{snapshot_date}_{game_id}"
            cid = _insert_candidate(
                conn,
                run_id=run_id,
                signal_type=SIGNAL_MILESTONE_CROSSED,
                player_canonical=str(player),
                player_display=None,
                magnitude=4.0,
                baseline_value="cycle (1B+2B+3B+HR same game)",
                current_value=f"game={game_id} vs={opponent}",
                window_label=window_label,
                comparison_target="record_cycle",
                evidence_json=None,
                priority=GIANTS_PRIORITY,
                notes=f"record=cycle game={game_id} opponent={opponent}",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


def detect_no_hitter(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """ノーヒットノーラン検出 (348 step 3 part 2)。

    snapshot_date の Giants 投手で H_allowed=0 AND IP>=9.0 を検出。
    完投 + 0 安打を条件にする (ノーノー)。 完全試合は別 detector。
    """
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    rows = conn.execute(
        "SELECT pl.game_id, pl.player_canonical, pl.IP, pl.H_allowed, "
        "pl.BB, pl.HBP, pl.BF, g.opponent "
        "FROM pitching_logs pl JOIN games g ON pl.game_id = g.game_id "
        "WHERE g.game_date = ? AND pl.team_name LIKE '%巨人%' "
        "AND pl.player_canonical IS NOT NULL "
        "AND pl.H_allowed = 0 AND pl.IP >= 9.0",
        (snapshot_date,),
    ).fetchall()
    for game_id, player, ip, h_allowed, bb, hbp, bf, opponent in rows:
        # 完全試合は別 detector で扱うため、 ここではノーノーのみ
        # (BB > 0 or HBP > 0 でも H=0 なら ノーノー成立)
        is_perfect = (int(bb or 0) == 0 and int(hbp or 0) == 0 and int(bf or 0) <= 28)
        if is_perfect:
            continue  # 完全試合は detect_perfect_game で別 emit
        window_label = f"no_hitter_{snapshot_date}_{game_id}"
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_MILESTONE_CROSSED,
            player_canonical=str(player),
            player_display=None,
            magnitude=float(ip),
            baseline_value="no-hitter (H=0, IP>=9.0)",
            current_value=f"game={game_id} IP={ip} BB={bb} HBP={hbp}",
            window_label=window_label,
            comparison_target="record_no_hitter",
            evidence_json=None,
            priority=GIANTS_PRIORITY,
            notes=f"record=no_hitter game={game_id} opponent={opponent}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


def detect_perfect_game(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """完全試合検出 (348 step 3 part 2)。

    H_allowed=0 AND BB=0 AND HBP=0 AND IP>=9.0 AND BF<=28 (27 打者で完投、
    エラー等で 28 まで OK の運用)。
    """
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    rows = conn.execute(
        "SELECT pl.game_id, pl.player_canonical, pl.IP, pl.BF, g.opponent "
        "FROM pitching_logs pl JOIN games g ON pl.game_id = g.game_id "
        "WHERE g.game_date = ? AND pl.team_name LIKE '%巨人%' "
        "AND pl.player_canonical IS NOT NULL "
        "AND pl.H_allowed = 0 AND pl.BB = 0 AND pl.HBP = 0 "
        "AND pl.IP >= 9.0 AND pl.BF <= 28",
        (snapshot_date,),
    ).fetchall()
    for game_id, player, ip, bf, opponent in rows:
        window_label = f"perfect_game_{snapshot_date}_{game_id}"
        cid = _insert_candidate(
            conn,
            run_id=run_id,
            signal_type=SIGNAL_MILESTONE_CROSSED,
            player_canonical=str(player),
            player_display=None,
            magnitude=27.0,
            baseline_value="perfect game (H=0, BB=0, HBP=0, BF<=28)",
            current_value=f"game={game_id} IP={ip} BF={bf}",
            window_label=window_label,
            comparison_target="record_perfect_game",
            evidence_json=None,
            priority=GIANTS_PRIORITY,
            notes=f"record=perfect_game game={game_id} opponent={opponent}",
        )
        if cid:
            inserted.append(cid)
    conn.commit()
    return inserted


# ─── 348 step 3 完全達成: 連続記録 5 detector ──────────────────────────


def _giants_batters(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT bl.player_canonical FROM batting_logs bl "
        "WHERE bl.team_name LIKE '%巨人%' AND bl.player_canonical IS NOT NULL "
        "AND bl.player_canonical != ''"
    ).fetchall()
    return [str(r[0]) for r in rows]


def _giants_pitchers(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT pl.player_canonical FROM pitching_logs pl "
        "WHERE pl.team_name LIKE '%巨人%' AND pl.player_canonical IS NOT NULL "
        "AND pl.player_canonical != ''"
    ).fetchall()
    return [str(r[0]) for r in rows]


def _emit_streak_candidate(
    conn, *, run_id, player, streak_value, record_key, title_kind, notes_extra,
) -> int:
    return _insert_candidate(
        conn,
        run_id=run_id,
        signal_type=SIGNAL_MILESTONE_CROSSED,
        player_canonical=str(player),
        player_display=None,
        magnitude=float(streak_value),
        baseline_value=f"streak={streak_value}",
        current_value=f"{streak_value} {title_kind}",
        window_label=f"{record_key}_{player}",
        comparison_target=f"record_{record_key}",
        evidence_json=None,
        priority=GIANTS_PRIORITY,
        notes=f"record={record_key} streak={streak_value} {notes_extra}",
    ) or 0


def detect_consecutive_hit_streak(
    conn: sqlite3.Connection, *,
    snapshot_date: str, run_id: Optional[str] = None, min_games: int = 7,
) -> list[int]:
    """連続安打試合 streak (H>0 連続 game)、 min_games 以上で emit (348 step 3)."""
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    for player in _giants_batters(conn):
        rows = conn.execute(
            "SELECT g.game_date, bl.H FROM batting_logs bl "
            "JOIN games g ON bl.game_id = g.game_id "
            "WHERE bl.player_canonical = ? AND g.game_date <= ? "
            "ORDER BY g.game_date DESC", (player, snapshot_date),
        ).fetchall()
        streak = 0
        for _, h in rows:
            if int(h or 0) > 0:
                streak += 1
            else:
                break
        if streak >= min_games:
            cid = _emit_streak_candidate(
                conn, run_id=run_id, player=player, streak_value=streak,
                record_key="consecutive_hit", title_kind="連続安打試合",
                notes_extra=f"as_of={snapshot_date}",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


def detect_consecutive_onbase_streak(
    conn: sqlite3.Connection, *,
    snapshot_date: str, run_id: Optional[str] = None, min_games: int = 10,
) -> list[int]:
    """連続出塁試合 (H>0 OR R>0 proxy、 walk/hbp は atbats_json parse 必要だが
    cost 抑制で R>0 proxy 使用、 注釈は body 側で記載) (348 step 3)."""
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    for player in _giants_batters(conn):
        rows = conn.execute(
            "SELECT g.game_date, bl.H, bl.R FROM batting_logs bl "
            "JOIN games g ON bl.game_id = g.game_id "
            "WHERE bl.player_canonical = ? AND g.game_date <= ? "
            "ORDER BY g.game_date DESC", (player, snapshot_date),
        ).fetchall()
        streak = 0
        for _, h, r in rows:
            if int(h or 0) > 0 or int(r or 0) > 0:
                streak += 1
            else:
                break
        if streak >= min_games:
            cid = _emit_streak_candidate(
                conn, run_id=run_id, player=player, streak_value=streak,
                record_key="consecutive_onbase", title_kind="連続出塁試合",
                notes_extra=f"proxy=H_or_R as_of={snapshot_date}",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


def detect_consecutive_hr_streak(
    conn: sqlite3.Connection, *,
    snapshot_date: str, run_id: Optional[str] = None, min_games: int = 3,
) -> list[int]:
    """連続試合本塁打 (atbats_json parse で is_hr 検出)、 min_games 以上で emit."""
    import json as _json
    if run_id is None:
        run_id = str(uuid.uuid4())
    try:
        from src.analysis import insight_atbats_parser as _parser
    except Exception:  # noqa: BLE001
        return []
    inserted: list[int] = []
    for player in _giants_batters(conn):
        rows = conn.execute(
            "SELECT g.game_date, bl.atbats_json FROM batting_logs bl "
            "JOIN games g ON bl.game_id = g.game_id "
            "WHERE bl.player_canonical = ? AND g.game_date <= ? "
            "ORDER BY g.game_date DESC", (player, snapshot_date),
        ).fetchall()
        streak = 0
        for _, atb_json in rows:
            try:
                atbs = _json.loads(atb_json) if isinstance(atb_json, str) else atb_json
            except (ValueError, TypeError):
                atbs = []
            if not isinstance(atbs, list):
                atbs = []
            had_hr = False
            for ab in atbs:
                if isinstance(ab, str):
                    try:
                        if _parser.parse_atbat(ab).get("is_hr"):
                            had_hr = True
                            break
                    except Exception:  # noqa: BLE001
                        continue
            if had_hr:
                streak += 1
            else:
                break
        if streak >= min_games:
            cid = _emit_streak_candidate(
                conn, run_id=run_id, player=player, streak_value=streak,
                record_key="consecutive_hr", title_kind="連続試合本塁打",
                notes_extra=f"as_of={snapshot_date}",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


def detect_consecutive_scoreless_innings(
    conn: sqlite3.Connection, *,
    snapshot_date: str, run_id: Optional[str] = None, min_ip: float = 15.0,
) -> list[int]:
    """連続イニング無失点 (pitcher 連続 game で ER==0 の IP 合計、
    min_ip 以上で emit) (348 step 3)."""
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    for player in _giants_pitchers(conn):
        rows = conn.execute(
            "SELECT g.game_date, pl.IP, pl.ER FROM pitching_logs pl "
            "JOIN games g ON pl.game_id = g.game_id "
            "WHERE pl.player_canonical = ? AND g.game_date <= ? "
            "ORDER BY g.game_date DESC", (player, snapshot_date),
        ).fetchall()
        ip_streak = 0.0
        for _, ip, er in rows:
            if int(er or 0) == 0 and float(ip or 0) > 0:
                ip_streak += float(ip)
            else:
                break
        if ip_streak >= min_ip:
            cid = _emit_streak_candidate(
                conn, run_id=run_id, player=player, streak_value=ip_streak,
                record_key="consecutive_scoreless_ip",
                title_kind="連続イニング無失点",
                notes_extra=f"ip={ip_streak:.1f} as_of={snapshot_date}",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


def detect_consecutive_strikeouts(
    conn: sqlite3.Connection, *,
    snapshot_date: str, run_id: Optional[str] = None, min_k: int = 10,
) -> list[int]:
    """連続奪三振 = 1 試合内最多 K (proxy)、 シーズン高 K (>=min_k) game で emit
    (PA-level 連続 K は atbats_json の PA 順序 parse 必要、 実装簡略化のため
    試合内 K 総数 を proxy、 注釈は body 側で記載) (348 step 3)."""
    if run_id is None:
        run_id = str(uuid.uuid4())
    inserted: list[int] = []
    for player in _giants_pitchers(conn):
        rows = conn.execute(
            "SELECT g.game_date, MAX(pl.K) FROM pitching_logs pl "
            "JOIN games g ON pl.game_id = g.game_id "
            "WHERE pl.player_canonical = ? AND g.game_date <= ? "
            "GROUP BY g.game_id ORDER BY pl.K DESC LIMIT 1",
            (player, snapshot_date),
        ).fetchall()
        if not rows:
            continue
        game_date, max_k = rows[0]
        max_k = int(max_k or 0)
        if max_k >= min_k:
            cid = _emit_streak_candidate(
                conn, run_id=run_id, player=player, streak_value=max_k,
                record_key="consecutive_strikeouts",
                title_kind="1 試合最多奪三振 (連続奪三振 proxy)",
                notes_extra=f"game={game_date} k={max_k} proxy=game_max",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


def detect_standings_shift(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """C-2: standings_snapshots の直近 2 件を比較、Giants 順位 が動いたら emit。"""
    if run_id is None:
        run_id = str(uuid.uuid4())
    rows = conn.execute(
        "SELECT DISTINCT snap_date FROM standings_snapshots "
        "WHERE snap_date <= ? ORDER BY snap_date DESC LIMIT 2",
        (snapshot_date,),
    ).fetchall()
    if len(rows) < 2:
        return []
    latest_date = str(rows[0][0])
    prev_date = str(rows[1][0])
    latest = conn.execute(
        "SELECT rank, W, L, T, games_behind FROM standings_snapshots "
        "WHERE snap_date = ? AND team = 'g'",
        (latest_date,),
    ).fetchone()
    prev = conn.execute(
        "SELECT rank, W, L, T, games_behind FROM standings_snapshots "
        "WHERE snap_date = ? AND team = 'g'",
        (prev_date,),
    ).fetchone()
    if not latest or not prev:
        return []
    if latest[0] == prev[0]:
        return []  # 順位変化なし
    direction = "上昇" if (latest[0] or 0) < (prev[0] or 0) else "下降"
    window_label = f"standings_shift_{latest_date}"
    cid = _insert_candidate(
        conn,
        run_id=run_id,
        signal_type=SIGNAL_STANDINGS_SHIFT,
        player_canonical="巨人",
        player_display="読売ジャイアンツ",
        magnitude=float((prev[0] or 0) - (latest[0] or 0)),
        baseline_value=f"prev_rank={prev[0]} prev_W={prev[1]} prev_L={prev[2]}",
        current_value=f"current_rank={latest[0]} W={latest[1]} L={latest[2]} T={latest[3]} GB={latest[4]}",
        window_label=window_label,
        comparison_target=f"standings_shift_{prev_date}_to_{latest_date}",
        evidence_json=None,
        priority=GIANTS_PRIORITY,
        notes=f"direction={direction} prev_date={prev_date} latest_date={latest_date}",
    )
    return [cid] if cid else []


_STAT_DELTA_THRESHOLDS = {
    # 2026-05-15 サバメトリクス drop: wOBA / FIP 除外。
    "OPS": 0.020, "AVG": 0.015, "OBP": 0.015, "SLG": 0.020,
    "ERA": 0.30, "WHIP": 0.08,
}


def detect_stat_delta(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    run_id: Optional[str] = None,
) -> list[int]:
    """D: advanced_metric_snapshots の最新 vs 直前 snapshot を比較、 Giants 選手で
    顕著な変化があれば候補化。snapshot 同日 2 件はないため (snapshot_date 単位)、
    直前 snapshot_date を 1 つ前の DISTINCT date とする。"""
    if run_id is None:
        run_id = str(uuid.uuid4())
    rows = conn.execute(
        "SELECT DISTINCT snapshot_date FROM advanced_metric_snapshots "
        "WHERE snapshot_date <= ? ORDER BY snapshot_date DESC LIMIT 2",
        (snapshot_date,),
    ).fetchall()
    if len(rows) < 2:
        return []
    latest_date = str(rows[0][0])
    prev_date = str(rows[1][0])
    inserted: list[int] = []
    window_label = f"stat_delta_{latest_date}_vs_{prev_date}"

    for metric, threshold in _STAT_DELTA_THRESHOLDS.items():
        # 同 player x metric x scope で 2 日分 join、Giants のみ
        delta_rows = conn.execute(
            "SELECT a.player_canonical, a.scope, a.metric_value AS new_val, "
            "b.metric_value AS old_val, a.league_rank AS new_rank, "
            "b.league_rank AS old_rank "
            "FROM advanced_metric_snapshots a "
            "JOIN advanced_metric_snapshots b "
            "  ON a.player_canonical = b.player_canonical "
            "  AND a.metric_name = b.metric_name "
            "  AND a.scope = b.scope "
            "WHERE a.metric_name = ? AND a.snapshot_date = ? "
            "AND b.snapshot_date = ? AND a.team_code = 'g' "
            "AND a.metric_value IS NOT NULL AND b.metric_value IS NOT NULL",
            (metric, latest_date, prev_date),
        ).fetchall()
        for player, scope, new_val, old_val, new_rank, old_rank in delta_rows:
            delta = float(new_val) - float(old_val)
            if abs(delta) < threshold:
                continue
            rank_change = ""
            if new_rank is not None and old_rank is not None:
                diff_rank = int(new_rank) - int(old_rank)
                if diff_rank != 0:
                    rank_change = f" rank {old_rank}→{new_rank}"
            cid = _insert_candidate(
                conn,
                run_id=run_id,
                signal_type=SIGNAL_STAT_DELTA,
                player_canonical=str(player),
                player_display=None,
                magnitude=float(round(delta, 4)),
                baseline_value=f"prev={old_val:.3f} ({prev_date})",
                current_value=f"current={new_val:.3f} ({latest_date}){rank_change}",
                window_label=window_label,
                comparison_target=f"stat_delta_{metric}_{scope}",
                evidence_json=None,
                priority=GIANTS_PRIORITY,
                notes=f"metric={metric} scope={scope} delta={delta:+.3f}{rank_change}",
            )
            if cid:
                inserted.append(cid)
    conn.commit()
    return inserted


# ─── public API: run all detectors ──────────────────────────────────────────


# 2026-05-15 user 指示「サバメトリクスはいらない」適用、一般 + 中上級の指標
# のみ scan する。FIP / xFIP / wOBA / BABIP / ISO / K_pct / BB_pct は削除。
# 残す: AVG (打率) / OBP (出塁率) / SLG (長打率) / OPS / ERA / WHIP / K_per_9
# (奪三振率) / 守備率 (fielding_pct)。
# 2026-05-15 user 指示「C(マニアック)D(サバメトリクス)はいらない」適用。
# 投手は ERA のみ(WHIP/K_per_9 は drop)。 batter は OPS/AVG/OBP/SLG。
_ZSCORE_BATTER_METRICS = ("OPS", "AVG", "OBP", "SLG")
_ZSCORE_PITCHER_METRICS = ("ERA",)
_GIANTS_TOP_METRICS = ()  # 巨人 top% 検出器 drop (マニアック判定)
_ZSCORE_BATTER_SCOPES = ("last_30d", "season", "last_7d")
_ZSCORE_PITCHER_SCOPES = ("season", "last_30d", "last_7d")
_GIANTS_TOP_SCOPES = ("last_30d", "season", "last_7d")


def run_all_anomaly_detectors(
    conn: sqlite3.Connection,
    *,
    snapshot_date: Optional[str] = None,
    run_id: Optional[str] = None,
) -> dict[str, list[int]]:
    """全 detector を best-effort で実行、結果を dict で返す。

    2026-05-15 拡張: z-score 打者 / 投手 / Giants top% は 複数 metric を
    全 scan する (記事多様性向上)。同 player が異 metric で複数 candidate
    化されるが、window_label が metric を含むため dedupe で吸収される。

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
    out[SIGNAL_ZSCORE_BATTER] = []
    for metric in _ZSCORE_BATTER_METRICS:
        for scope in _ZSCORE_BATTER_SCOPES:
            try:
                out[SIGNAL_ZSCORE_BATTER].extend(
                    detect_zscore_batter_outliers(
                        conn, snapshot_date=snapshot_date, run_id=run_id,
                        metric_name=metric, scope=scope,
                    )
                )
            except Exception:  # noqa: BLE001
                pass
    out[SIGNAL_ZSCORE_PITCHER] = []
    for metric in _ZSCORE_PITCHER_METRICS:
        for scope in _ZSCORE_PITCHER_SCOPES:
            try:
                out[SIGNAL_ZSCORE_PITCHER].extend(
                    detect_zscore_pitcher_outliers(
                        conn, snapshot_date=snapshot_date, run_id=run_id,
                        metric_name=metric, scope=scope,
                    )
                )
            except Exception:  # noqa: BLE001
                pass
    # 2026-05-15 user 指示「サバメトリクスはいらない」適用、BABIP / FIP-ERA
    # 乖離 detector は call せず空に固定 (signal_type 自体は backward-compat
    # のため残し、再開する場合は env で復活させる前提)。
    out[SIGNAL_BABIP_DIVERGENCE] = []
    out[SIGNAL_FIP_ERA_DIVERGENCE] = []
    out[SIGNAL_GIANTS_TOP_OUTLIER] = []
    for metric in _GIANTS_TOP_METRICS:
        for scope in _GIANTS_TOP_SCOPES:
            try:
                out[SIGNAL_GIANTS_TOP_OUTLIER].extend(
                    detect_giants_top_outliers(
                        conn, snapshot_date=snapshot_date, run_id=run_id,
                        metric_name=metric, scope=scope,
                    )
                )
            except Exception:  # noqa: BLE001
                pass
    # 2026-05-15 user 指示「マニアック drop」適用、HR pace / 規定外好調 / 連続
    # 多安打 / 巨人 top% は detector call せず空 (signal_type 自体は backward-
    # compat で残し、env / code 復活余地)。
    out[SIGNAL_PACE_HR_PROJECTION] = []
    out[SIGNAL_HIDDEN_OPS_LIMIT] = []
    # 連続多安打 も「マニアック」分類で drop (user 指示)
    out[SIGNAL_HIT_STREAK_RUN] = []
    # 2026-05-15 user 指示「サバメトリクスはいらない」適用、UZR_proxy は
    # 計算式自体がサバメトリクスのため drop、fielding_pct (一般的な守備率)
    # のみ残す。
    try:
        _uzr_ids, fpct_ids = detect_giants_defense_outliers(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
        out[SIGNAL_DEFENSE_UZR_OUTLIER] = []  # drop UZR
        out[SIGNAL_DEFENSE_FIELDING_PCT] = fpct_ids
    except Exception:  # noqa: BLE001
        out[SIGNAL_DEFENSE_UZR_OUTLIER] = []
        out[SIGNAL_DEFENSE_FIELDING_PCT] = []
    # 2026-05-15 試合後 ファンが気になる指標 5 detector
    try:
        out[SIGNAL_GAME_HERO_BATTER] = detect_game_hero_batter(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_GAME_HERO_BATTER] = []
    try:
        out[SIGNAL_GAME_PITCHER_PERF] = detect_game_pitcher_performance(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_GAME_PITCHER_PERF] = []
    try:
        milestone_ids = detect_milestone_crossed(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
        # 348 step 3 part 2: record events (cycle / no-hitter / perfect game) も
        # SIGNAL_MILESTONE_CROSSED で emit、 同一 signal type にまとめる
        try:
            milestone_ids += detect_cycle_hits(
                conn, snapshot_date=snapshot_date, run_id=run_id,
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            milestone_ids += detect_no_hitter(
                conn, snapshot_date=snapshot_date, run_id=run_id,
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            milestone_ids += detect_perfect_game(
                conn, snapshot_date=snapshot_date, run_id=run_id,
            )
        except Exception:  # noqa: BLE001
            pass
        # 348 step 3 完全達成: 連続記録 5 種 detector
        for _fn in (
            detect_consecutive_hit_streak,
            detect_consecutive_onbase_streak,
            detect_consecutive_hr_streak,
            detect_consecutive_scoreless_innings,
            detect_consecutive_strikeouts,
        ):
            try:
                milestone_ids += _fn(
                    conn, snapshot_date=snapshot_date, run_id=run_id,
                )
            except Exception:  # noqa: BLE001
                continue
        out[SIGNAL_MILESTONE_CROSSED] = milestone_ids
    except Exception:  # noqa: BLE001
        out[SIGNAL_MILESTONE_CROSSED] = []
    try:
        out[SIGNAL_STANDINGS_SHIFT] = detect_standings_shift(
            conn, snapshot_date=snapshot_date, run_id=run_id,
        )
    except Exception:  # noqa: BLE001
        out[SIGNAL_STANDINGS_SHIFT] = []
    # 2026-05-15 user 指示「変化率はタイトルじゃわかりにくい、サバメトリ
    # クス分類で drop」適用、stat_delta detector も BABIP/FIP-ERA と同様
    # に call せず空。signal_type 自体は backward-compat で残す。
    out[SIGNAL_STAT_DELTA] = []
    return out
