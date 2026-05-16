"""DATA-INSIGHT publish-time data quality gate.

356-INSIGHT: 348 whitelist / 349 dedup / title period guard の後段で、
WP create_post 直前にデータ記事として最低限の信頼性を確認する。

Design:
  * stdlib only, no schema migration
  * fail closed for known data-quality problems
  * every block returns an explicit skip status/reason
  * no env / scheduler / secret / WP existing article mutation
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import insight_whitelist as _wl  # noqa: E402


CENTRAL_TEAMS = frozenset({"g", "t", "s", "c", "db", "d"})
PITCHER_METRICS = frozenset({"ERA", "WIN_PCT", "K_per_9", "BB_per_9", "HR_per_9"})
FIELDING_METRICS = frozenset({"FIELDING_PCT", "UZR_proxy"})

STATUS_SAMPLE = "skip_data_quality_sample"
STATUS_COVERAGE = "skip_data_quality_coverage"
STATUS_STALE = "skip_data_quality_stale_snapshot"
STATUS_EVIDENCE = "skip_data_quality_missing_evidence"


@dataclass(frozen=True)
class QualityDecision:
    allowed: bool
    status: str = "ok"
    reason: str = "ok"
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "reason": self.reason,
            "details": dict(self.details),
        }


def ok(**details: Any) -> QualityDecision:
    return QualityDecision(True, "ok", "ok", details)


def block(status: str, reason: str, **details: Any) -> QualityDecision:
    return QualityDecision(False, status, reason, details)


def skip_result(decision: QualityDecision, **extra: Any) -> dict[str, Any]:
    """Publisher return payload for a failed quality decision."""
    payload = {
        "status": decision.status,
        "reason": decision.reason,
        "quality_gate": decision.as_dict(),
    }
    payload.update(extra)
    return payload


def _quality_config(config: Any = None) -> dict[str, Any]:
    cfg = _wl.load_whitelist_config() if config is None else config
    if cfg is None:
        return {}
    return cfg.get("data_quality", {}) or {}


def _thresholds(config: Any = None) -> dict[str, Any]:
    cfg = _wl.load_whitelist_config() if config is None else config
    if cfg is None:
        return {}
    return cfg.get("thresholds", {}) or {}


def min_sample_for_metric(metric_name: str, *, config: Any = None) -> Optional[int]:
    """Return minimum sample for rate/snapshot metrics.

    Counting stats do not have a universal sample_size column in rendered
    articles, so unknown metric names return None.
    """
    thresholds = _thresholds(config)
    quality = _quality_config(config)
    if metric_name in PITCHER_METRICS:
        return int(thresholds.get("min_sample_pitcher_ip", 10))
    if metric_name in FIELDING_METRICS:
        return int(quality.get("min_sample_fielding", 10))
    if metric_name in {"AVG", "OBP", "SLG", "OPS", "RISP"}:
        return int(thresholds.get("min_sample_batter_pa", 20))
    return None


def _parse_iso_date(value: str) -> Optional[dt.date]:
    text = str(value or "").strip()
    if len(text) >= 10:
        text = text[:10]
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def latest_snapshot_date(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    scope: str,
) -> Optional[str]:
    row = conn.execute(
        "SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ?",
        (metric_name, scope),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def validate_snapshot_freshness(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    scope: str,
    snapshot_date: Optional[str] = None,
    today: Optional[dt.date] = None,
    config: Any = None,
) -> QualityDecision:
    """Ensure the rendered article uses the latest and recent-enough snapshot."""
    latest = latest_snapshot_date(conn, metric_name=metric_name, scope=scope)
    effective = snapshot_date or latest
    if not effective:
        return block(
            STATUS_COVERAGE,
            "missing_snapshot",
            metric_name=metric_name,
            scope=scope,
        )
    if latest and snapshot_date and snapshot_date < latest:
        return block(
            STATUS_STALE,
            "not_latest_snapshot",
            metric_name=metric_name,
            scope=scope,
            snapshot_date=snapshot_date,
            latest_snapshot_date=latest,
        )

    snap_date = _parse_iso_date(effective)
    if snap_date is None:
        return block(
            STATUS_STALE,
            "invalid_snapshot_date",
            metric_name=metric_name,
            scope=scope,
            snapshot_date=effective,
        )
    quality = _quality_config(config)
    max_age_days = int(quality.get("max_snapshot_age_days", 3))
    current = today or dt.date.today()
    age_days = max(0, (current - snap_date).days)
    if max_age_days >= 0 and age_days > max_age_days:
        return block(
            STATUS_STALE,
            "snapshot_too_old",
            metric_name=metric_name,
            scope=scope,
            snapshot_date=effective,
            age_days=age_days,
            max_snapshot_age_days=max_age_days,
        )
    return ok(
        metric_name=metric_name,
        scope=scope,
        snapshot_date=effective,
        latest_snapshot_date=latest,
        age_days=age_days,
    )


def validate_snapshot_coverage(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    scope: str,
    snapshot_date: Optional[str] = None,
    league: str = "central",
    config: Any = None,
) -> QualityDecision:
    """Check that ranking has enough teams and rows to be meaningful."""
    effective = snapshot_date or latest_snapshot_date(
        conn, metric_name=metric_name, scope=scope,
    )
    if not effective:
        return block(
            STATUS_COVERAGE,
            "missing_snapshot",
            metric_name=metric_name,
            scope=scope,
        )
    quality = _quality_config(config)
    min_teams = int(quality.get("min_central_teams", 6))
    min_total = int(quality.get("min_league_total", 6))

    teams = CENTRAL_TEAMS if league == "central" else CENTRAL_TEAMS
    placeholders = ",".join("?" * len(teams))
    row = conn.execute(
        "SELECT COUNT(DISTINCT team_code), COUNT(*), "
        "MAX(COALESCE(league_total, 0)) "
        "FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
        f"AND team_code IN ({placeholders}) "
        "AND metric_value IS NOT NULL",
        (metric_name, scope, effective, *sorted(teams)),
    ).fetchone()
    team_count = int(row[0] or 0) if row else 0
    row_count = int(row[1] or 0) if row else 0
    max_league_total = int(row[2] or 0) if row else 0
    if team_count < min_teams:
        return block(
            STATUS_COVERAGE,
            "insufficient_team_coverage",
            metric_name=metric_name,
            scope=scope,
            snapshot_date=effective,
            team_count=team_count,
            min_central_teams=min_teams,
        )
    if max(row_count, max_league_total) < min_total:
        return block(
            STATUS_COVERAGE,
            "insufficient_league_total",
            metric_name=metric_name,
            scope=scope,
            snapshot_date=effective,
            row_count=row_count,
            league_total=max_league_total,
            min_league_total=min_total,
        )
    return ok(
        metric_name=metric_name,
        scope=scope,
        snapshot_date=effective,
        team_count=team_count,
        row_count=row_count,
        league_total=max_league_total,
    )


def validate_focus_sample(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    scope: str,
    player_canonical: str,
    snapshot_date: Optional[str] = None,
    config: Any = None,
) -> QualityDecision:
    min_sample = min_sample_for_metric(metric_name, config=config)
    if min_sample is None:
        return ok(metric_name=metric_name, scope=scope, sample_required=False)
    effective = snapshot_date or latest_snapshot_date(
        conn, metric_name=metric_name, scope=scope,
    )
    row = conn.execute(
        "SELECT sample_size, team_code FROM advanced_metric_snapshots "
        "WHERE metric_name = ? AND scope = ? AND snapshot_date = ? "
        "AND player_canonical = ? "
        "ORDER BY CASE WHEN team_code = 'g' THEN 0 ELSE 1 END LIMIT 1",
        (metric_name, scope, effective, player_canonical),
    ).fetchone()
    sample_size = int(row[0] or 0) if row else 0
    team_code = str(row[1] or "") if row else ""
    if sample_size < min_sample:
        return block(
            STATUS_SAMPLE,
            "insufficient_sample",
            metric_name=metric_name,
            scope=scope,
            player_canonical=player_canonical,
            sample_size=sample_size,
            min_sample=min_sample,
            team_code=team_code,
        )
    return ok(
        metric_name=metric_name,
        scope=scope,
        player_canonical=player_canonical,
        sample_size=sample_size,
        min_sample=min_sample,
        team_code=team_code,
    )


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def validate_body_evidence(
    body_text: str,
    *,
    require_sample: bool = False,
    require_comparison: bool = True,
) -> QualityDecision:
    """Check visible evidence fields in rendered body markdown/html."""
    text = str(body_text or "")
    missing: list[str] = []
    if "データ元" not in text:
        missing.append("source")
    if not _has_any(text, ("集計期間", "対象期間", "時点")):
        missing.append("period")
    if not _has_any(text, ("計算式", "集計式", "集計基準", "算出")):
        missing.append("formula")
    if require_sample and "サンプル" not in text:
        missing.append("sample")
    if require_comparison and not _has_any(text, ("比較", "順位", "リーグ", "平均との差", "基準")):
        missing.append("comparison")
    if missing:
        return block(
            STATUS_EVIDENCE,
            "missing_body_evidence",
            missing=missing,
        )
    return ok(require_sample=require_sample, require_comparison=require_comparison)


def validate_player_snapshot_article(
    conn: sqlite3.Connection,
    article: dict[str, Any],
    *,
    metric_name: str,
    scope: str,
    focus_player: Optional[str],
    snapshot_date: Optional[str] = None,
    require_sample_evidence: bool = True,
    today: Optional[dt.date] = None,
) -> QualityDecision:
    """Combined gate for player ranking/anomaly articles backed by snapshots."""
    if not focus_player:
        return block(
            STATUS_COVERAGE,
            "missing_focus_player",
            metric_name=metric_name,
            scope=scope,
        )
    freshness = validate_snapshot_freshness(
        conn,
        metric_name=metric_name,
        scope=scope,
        snapshot_date=snapshot_date,
        today=today,
    )
    if not freshness.allowed:
        return freshness
    effective_snapshot = freshness.details.get("snapshot_date") or snapshot_date
    coverage = validate_snapshot_coverage(
        conn,
        metric_name=metric_name,
        scope=scope,
        snapshot_date=effective_snapshot,
        league="central",
    )
    if not coverage.allowed:
        return coverage
    sample = validate_focus_sample(
        conn,
        metric_name=metric_name,
        scope=scope,
        player_canonical=focus_player,
        snapshot_date=effective_snapshot,
    )
    if not sample.allowed:
        return sample
    evidence = validate_body_evidence(
        article.get("body_md") or article.get("body_html") or "",
        require_sample=require_sample_evidence,
        require_comparison=True,
    )
    if not evidence.allowed:
        return evidence
    return ok(
        freshness=freshness.details,
        coverage=coverage.details,
        sample=sample.details,
        evidence=evidence.details,
    )


def validate_counting_article(article: dict[str, Any]) -> QualityDecision:
    """Gate for counting stat articles built from batting/pitching logs."""
    quality = _quality_config()
    min_teams = int(quality.get("min_central_teams", 6))
    team_coverage = int(article.get("team_coverage") or 0)
    if team_coverage and team_coverage < min_teams:
        return block(
            STATUS_COVERAGE,
            "insufficient_team_coverage",
            team_count=team_coverage,
            min_central_teams=min_teams,
        )
    league_total = int(article.get("league_total") or 0)
    min_total = int(quality.get("min_league_total", 6))
    if league_total < min_total:
        return block(
            STATUS_COVERAGE,
            "insufficient_league_total",
            league_total=league_total,
            min_league_total=min_total,
        )
    evidence = validate_body_evidence(
        article.get("body_md") or article.get("body_html") or "",
        require_sample=False,
        require_comparison=True,
    )
    if not evidence.allowed:
        return evidence
    return ok(team_coverage=team_coverage, league_total=league_total)


def validate_team_metric_article(article: dict[str, Any]) -> QualityDecision:
    quality = _quality_config()
    min_teams = int(quality.get("min_central_teams", 6))
    league_total = int(article.get("league_total") or 0)
    if league_total < min_teams:
        return block(
            STATUS_COVERAGE,
            "insufficient_team_coverage",
            team_count=league_total,
            min_central_teams=min_teams,
        )
    evidence = validate_body_evidence(
        article.get("body_md") or article.get("body_html") or "",
        require_sample=False,
        require_comparison=True,
    )
    if not evidence.allowed:
        return evidence
    return ok(league_total=league_total)


def validate_basic_article(article: dict[str, Any]) -> QualityDecision:
    """Gate for team/current/record articles without snapshot ranking rows."""
    evidence = validate_body_evidence(
        article.get("body_md") or article.get("body_html") or "",
        require_sample=False,
        require_comparison=False,
    )
    if not evidence.allowed:
        return evidence
    return ok()
