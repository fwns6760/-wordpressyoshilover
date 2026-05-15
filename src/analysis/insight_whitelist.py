"""DATA-INSIGHT-continuous: metric whitelist gate (348 ticket step 1).

`config/insight_whitelist.json` を 1 度 load し、 metric_name / team_code 単位の
gate 判定を提供。 detector / publisher 双方で defense-in-depth で利用される。

設計方針:
  * stdlib のみ (json / pathlib)、 新規依存無し
  * config 不在時は backward-compatible (許可寄り、 既存挙動維持)
  * load 結果は module-level cache、 起動時 1 回のみ読み込み
  * spec 正本 = `doc/reference/data-insight-metric-whitelist.md`、
    本 module は実行 layer の正本

Hard constraints (348 ticket §7):
  * env / secret / scheduler 一切 touch しない
  * LLM call を path に混入させない
  * config 形式 = JSON (2026-05-15 user 確定、 YAML 採用しない)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_CONFIG_PATH = ROOT / "config" / "insight_whitelist.json"


_CACHED_CONFIG: Optional[dict[str, Any]] = None
_CACHED_PATH: Optional[Path] = None


# sentinel for "config 引数未指定" — None 自体は "config 明示不在" (backward-compat)
# として区別する必要があるため
_UNSET: Any = object()


def load_whitelist_config(
    path: Optional[Path] = None,
    *,
    force_reload: bool = False,
) -> Optional[dict[str, Any]]:
    """`config/insight_whitelist.json` を load。 file 不在なら None。

    Args:
        path: explicit config file path (test 用、 default = DEFAULT_CONFIG_PATH)
        force_reload: cache を無視して再 load (test 用)
    """
    global _CACHED_CONFIG, _CACHED_PATH
    target = path or DEFAULT_CONFIG_PATH
    if not force_reload and _CACHED_CONFIG is not None and _CACHED_PATH == target:
        return _CACHED_CONFIG
    if not target.exists():
        return None
    with open(target, encoding="utf-8") as f:
        data = json.load(f)
    _CACHED_CONFIG = data
    _CACHED_PATH = target
    return data


def reset_cache() -> None:
    """test 用: cache を強制 clear。"""
    global _CACHED_CONFIG, _CACHED_PATH
    _CACHED_CONFIG = None
    _CACHED_PATH = None


def _resolve_config(config: Any) -> Optional[dict[str, Any]]:
    """config 引数を解決。 _UNSET なら default load、 None なら明示不在。"""
    if config is _UNSET:
        return load_whitelist_config()
    return config


def is_metric_allowed(metric_name: str, *, config: Any = _UNSET) -> bool:
    """`metric_name` が publish 対象 ◯ list か。 × list なら False。

    config 不在 (None) 時は True (backward-compatible)。
    """
    cfg = _resolve_config(config)
    if cfg is None:
        return True
    disallowed = cfg.get("metrics_disallowed", [])
    return metric_name not in disallowed


def is_subject_team(team_code: Optional[str], *, config: Any = _UNSET) -> bool:
    """`team_code` が記事 title 主語対象 (= 巨人) か。

    config 不在 (None) 時は True (backward-compatible、 既存挙動)。
    """
    cfg = _resolve_config(config)
    if cfg is None:
        return True
    subject = cfg.get("team_filter", {}).get("subject_team_code", "g")
    return (team_code or "").strip() == subject


def metric_name_ja(metric_name: str, *, config: Any = _UNSET) -> str:
    """`metric_name` の日本語表記を返す。 mapping 不在なら原文 fallback。

    例外: OPS / UZR / WAR の 3 つは英略号のまま (mapping で同名)。
    """
    cfg = _resolve_config(config)
    if cfg is None:
        return metric_name
    mapping = cfg.get("metric_name_ja", {})
    return mapping.get(metric_name, metric_name)


def scope_ja(scope: str, *, config: Any = _UNSET) -> str:
    """`scope` の日本語表記。 mapping 不在なら原文 fallback。"""
    cfg = _resolve_config(config)
    if cfg is None:
        return scope
    mapping = cfg.get("scope_ja", {})
    return mapping.get(scope, scope)


def zscore_sigma(*, config: Any = _UNSET) -> float:
    """率系の z-score 閾値 (default 1.5σ)。"""
    cfg = _resolve_config(config)
    if cfg is None:
        return 1.5
    return float(cfg.get("thresholds", {}).get("zscore_sigma_rate", 1.5))


def counting_top_n(*, config: Any = _UNSET) -> int:
    """counting stats ranking の TOP N (default 10)。"""
    cfg = _resolve_config(config)
    if cfg is None:
        return 10
    return int(cfg.get("thresholds", {}).get("counting_top_n", 10))
