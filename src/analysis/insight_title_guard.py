"""Runtime title guard for DATA-INSIGHT articles.

This module enforces the user-facing rule that an automatic data-insight
article title must tell the reader the aggregation period.  It is deliberately
small and stdlib-only: callers either get a period-completed title or an
explicit validation failure reason to report upstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.analysis import insight_whitelist as _wl


_SCOPE_FALLBACKS = {
    "season": "今シーズン",
    "last_7d": "直近1週間",
    "last_30d": "直近1ヶ月",
    # 403 (2026-05-20): 試合数 / PA / 登板数 / IP base 新 scope
    "last_3_games": "直近3試合",
    "last_5_games": "直近5試合",
    "last_10_games": "直近10試合",
    "last_30_pa": "直近30打席",
    "last_50_pa": "直近50打席",
    "last_100_pa": "直近100打席",
    "last_3_appearances": "直近3登板",
    "last_5_appearances": "直近5登板",
    "last_10_appearances": "直近10登板",
    "last_5_ip": "直近5投球回",
    "last_10_ip": "直近10投球回",
    "monthly": "月別",
    "weekly": "週別",
    "today": "今日の試合",
    "current": "現在",
}

_PERIOD_KEYWORD_RE = re.compile(
    r"(直近\s*\d+\s*(?:日|試合|週間|ヶ月|か月|月|打席|登板|投球回)|"
    # issue #44 E (2026-05-17): 週別 / 月別 を period marker として認識する。
    # 半角 (週別) を ranking_article_publisher が先に append、 ensure_title_period
    # は全角（週別）を再 append → (週別)（週別) 重複の root cause。
    r"週別|月別|"
    r"今シーズン|シーズン累計|シーズン進行中|"
    r"今日の試合|本日|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}|"
    r"(?:セ・リーグ|リーグ)?\d+\s*連戦|"
    r"(?:vs|VS|対)\s*[^）\)]+戦?)"
)

_INTERNAL_SCOPE_RE = re.compile(
    r"\b(?:season|last_7d|last_30d|"
    r"last_3_games|last_5_games|last_10_games|"
    r"last_30_pa|last_50_pa|last_100_pa|"
    r"last_3_appearances|last_5_appearances|last_10_appearances|"
    r"last_5_ip|last_10_ip|"
    r"monthly|weekly)\b"
)


@dataclass(frozen=True)
class TitleGuardResult:
    ok: bool
    title: str
    reason: str = ""
    appended_label: str = ""


def compact_period_label(label: str) -> str:
    """Normalize spacing in short Japanese period labels for title suffixes."""
    text = (label or "").strip()
    if text in {"直近", "近期", "recent"}:
        return ""
    replacements = (
        # 試合 base (403 で 3 追加)
        ("直近 3 試合", "直近3試合"),
        ("直近 5 試合", "直近5試合"),
        ("直近 10 試合", "直近10試合"),
        ("直近 7 日", "直近7日"),
        ("直近 30 日", "直近30日"),
        ("直近 1 週間", "直近1週間"),
        ("直近 1 ヶ月", "直近1ヶ月"),
        ("直近 1 か月", "直近1か月"),
        ("1 週間", "1週間"),
        ("1 ヶ月", "1ヶ月"),
        # 403 新 unit: 打席 / 登板 / 投球回
        ("直近 30 打席", "直近30打席"),
        ("直近 50 打席", "直近50打席"),
        ("直近 100 打席", "直近100打席"),
        ("直近 3 登板", "直近3登板"),
        ("直近 5 登板", "直近5登板"),
        ("直近 10 登板", "直近10登板"),
        ("直近 5 投球回", "直近5投球回"),
        ("直近 10 投球回", "直近10投球回"),
    )
    for src, dst in replacements:
        text = text.replace(src, dst)
    if re.fullmatch(r"(?:直近)?\s*\d+\s*(?:日|試合|週間|ヶ月|か月|打席|登板|投球回)", text):
        text = re.sub(r"\s+", "", text)
    return text


def period_label_for_scope(scope: Optional[str]) -> str:
    """Return reader-facing period label for a known data-insight scope."""
    code = (scope or "").strip()
    if not code:
        return ""
    label = _wl.scope_ja(code)
    if label == code:
        label = _SCOPE_FALLBACKS.get(code, code)
    return compact_period_label(label)


def title_has_period(title: str) -> bool:
    """Return True when title already carries a reader-facing period marker."""
    text = (title or "").strip()
    if not text:
        return False
    return _PERIOD_KEYWORD_RE.search(text) is not None


def ensure_title_period(
    title: str,
    *,
    scope: Optional[str] = None,
    period_label: Optional[str] = None,
) -> TitleGuardResult:
    """Validate or auto-complete a data-insight title with a period suffix.

    If the title already includes a human-readable period marker, it is returned
    unchanged.  Internal scope codes such as ``last_5_games`` do not satisfy the
    rule; when a known scope/label is supplied, the Japanese label is appended.
    """
    original = (title or "").strip()
    if not original:
        return TitleGuardResult(False, original, "empty_title")

    if title_has_period(original) and not _INTERNAL_SCOPE_RE.search(original):
        return TitleGuardResult(True, original)

    label = compact_period_label(period_label or "") or period_label_for_scope(scope)
    if not label or label == (scope or ""):
        return TitleGuardResult(False, original, "missing_period_in_title")

    suffix = f"（{label}）"
    if original.endswith(suffix):
        return TitleGuardResult(True, original)
    return TitleGuardResult(True, f"{original}{suffix}", appended_label=label)
