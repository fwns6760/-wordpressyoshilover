"""465 DATA-ARTICLE: discovery-driven (contrast) titles for DATA-INSIGHT articles.

The legacy title is a flat rank f-string
(``【巨人データ】{player}、{metric}{value}で{league}{rank}位（{scope}）``) that
states a fact but does not surface the *discovery* — how far the number sits
from the league. This module builds a contrast title that puts two
source-derived literal numbers (player value vs league mean) and a deterministic
fixed-dictionary label next to each other, so the reader sees the gap at a
glance.

no-AI contract (memory: feedback_title_no_ai / feedback_title_clickable_descriptive):
  * pure f-string assembly of literal numbers; NO LLM / rewrite.
  * the label is chosen by a numeric ratio band only — a fixed dictionary, never
    generated. It never claims more than the ratio supports.
  * 60-char cap, no trailing ellipsis truncation.
  * returns ``None`` when the gap is too small to be worth surfacing — the caller
    then keeps the existing rank-style title (graceful fallback, never blocks).
"""

from __future__ import annotations

from typing import Optional

PREFIX = "【巨人データ】"
MAX_TITLE_LEN = 60

# Minimum ratio (in the "good" direction) before a contrast title is worth it.
# Below this the player is too close to the league mean for a "発見" framing;
# the caller falls back to the plain rank title.
MIN_SURFACE_RATIO = 1.12

# ratio band -> fixed label. Evaluated high-to-low; first match wins.
# higher-is-better rate stats (OPS / AVG / wOBA ...): ratio = value / mean.
_HIGHER_BETTER_BANDS = (
    (1.25, "リーグ屈指"),
    (MIN_SURFACE_RATIO, "好調"),
)
# lower-is-better rate stats (ERA / FIP / WHIP ...): ratio = mean / value.
_LOWER_BETTER_BANDS = (
    (1.25, "リーグ屈指の安定感"),
    (MIN_SURFACE_RATIO, "安定した内容"),
)


def _fmt(value: float) -> str:
    """Match the body's ``{:.3f}`` rate-stat formatting for title/body parity."""
    return f"{value:.3f}"


def _label_for_ratio(ratio: float, *, lower_is_better: bool) -> Optional[str]:
    bands = _LOWER_BETTER_BANDS if lower_is_better else _HIGHER_BETTER_BANDS
    for threshold, label in bands:
        if ratio >= threshold:
            return label
    return None


def build_contrast_title(
    *,
    player: str,
    metric_label: str,
    player_value: Optional[float],
    league_mean: Optional[float],
    scope_label: str,
    lower_is_better: bool = False,
) -> Optional[str]:
    """Build a contrast (value-vs-league-mean) title, or ``None`` to fall back.

    higher-is-better -> ``{metric}{value}はリーグ平均{mean}の{r}倍 {label}（{scope}）``
    lower-is-better  -> ``{metric}{value}はリーグ平均{mean}を{label}（{scope}）``

    Returns ``None`` when inputs are missing/non-positive, when the gap is below
    ``MIN_SURFACE_RATIO``, or when even the label-dropped form exceeds the cap.
    """
    if player_value is None or league_mean is None:
        return None
    if player_value <= 0 or league_mean <= 0:
        return None

    if lower_is_better:
        ratio = league_mean / player_value
    else:
        ratio = player_value / league_mean
    if ratio < MIN_SURFACE_RATIO:
        return None

    label = _label_for_ratio(ratio, lower_is_better=lower_is_better)
    if label is None:
        return None

    value_s = _fmt(player_value)
    mean_s = _fmt(league_mean)

    if lower_is_better:
        # "倍" reads oddly for lower-is-better metrics; use a direct comparison.
        full = (
            f"{PREFIX}{player}、{metric_label}{value_s}は"
            f"リーグ平均{mean_s}を{label}（{scope_label}）"
        )
        # nothing to drop for the lower-is-better form; either it fits or bail.
        return full if len(full) <= MAX_TITLE_LEN else None

    ratio_disp = f"{ratio:.1f}"
    full = (
        f"{PREFIX}{player}、{metric_label}{value_s}は"
        f"リーグ平均{mean_s}の{ratio_disp}倍 {label}（{scope_label}）"
    )
    if len(full) <= MAX_TITLE_LEN:
        return full
    # Over cap: drop the label; the two literal numbers + ratio are the core.
    trimmed = (
        f"{PREFIX}{player}、{metric_label}{value_s}は"
        f"リーグ平均{mean_s}の{ratio_disp}倍（{scope_label}）"
    )
    return trimmed if len(trimmed) <= MAX_TITLE_LEN else None
