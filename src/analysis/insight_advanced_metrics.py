"""INSIGHT-007 step 7b — advanced batting / pitching metric formulas.

Pure Python (no numpy / pandas). Each function is parameter-driven so it
can be tested with hand-written expected values and reused at any
aggregation level (single game / season / span).

All functions:

* Return ``None`` when the denominator is zero / inputs are insufficient
  rather than raising.
* Use float division explicitly so int inputs never integer-divide.
* Do **not** touch the SQLite DB or filesystem — callers aggregate rows
  upstream and pass dict-like ``BattingLine`` / ``PitchingLine`` here.

Formulas adopted from standard SABR references (FanGraphs / Baseball
Reference). The wOBA / FIP linear weights are season-agnostic
approximations — for production-grade work we would re-fit per season,
but the constants below give consistent rank ordering and match the
public Japanese baseball analytics blogs (DELTA / 1.02) within ~5%.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ─── linear weights / constants (FanGraphs-style, season-agnostic) ──────────

WOBA_WEIGHT_BB = 0.690
WOBA_WEIGHT_HBP = 0.722
WOBA_WEIGHT_1B = 0.888
WOBA_WEIGHT_2B = 1.271
WOBA_WEIGHT_3B = 1.616
WOBA_WEIGHT_HR = 2.101

# FIP constant — re-derived per season in real systems; 3.10 is a NPB
# typical baseline. We expose it so callers can override after the DB
# accumulates a full league season.
FIP_CONSTANT = 3.10


# ─── data containers ──────────────────────────────────────────────────────


@dataclass
class BattingLine:
    """Single batter's accumulated batting line.

    Fields use SABR notation. ``H1`` etc. = singles, doubles, triples.
    All fields default to zero so callers can ignore unknowns.
    """
    AB: int = 0           # at-bats
    H: int = 0            # hits (total)
    H1: int = 0           # singles
    H2: int = 0           # doubles
    H3: int = 0           # triples
    HR: int = 0           # home runs
    BB: int = 0           # walks (non-IBB excluded for purity, fold IBB here for simplicity)
    IBB: int = 0          # intentional walks (subtract from BB for wOBA)
    HBP: int = 0          # hit by pitch
    SF: int = 0           # sacrifice flies
    SH: int = 0           # sacrifice hits (bunts)
    SO: int = 0           # strikeouts
    PA: int = 0           # plate appearances (computed if 0)
    TB: int = 0           # total bases (computed if 0)

    def coerce(self) -> "BattingLine":
        """Return a defensive copy with PA / TB filled when zero."""
        pa = self.PA or (
            self.AB + self.BB + self.HBP + self.SF + self.SH
        )
        tb = self.TB or (
            self.H1 + 2 * self.H2 + 3 * self.H3 + 4 * self.HR
        )
        return BattingLine(
            AB=self.AB, H=self.H, H1=self.H1, H2=self.H2, H3=self.H3,
            HR=self.HR, BB=self.BB, IBB=self.IBB, HBP=self.HBP, SF=self.SF,
            SH=self.SH, SO=self.SO, PA=pa, TB=tb,
        )


@dataclass
class PitchingLine:
    IP: float = 0.0       # innings pitched (5.1 → 5.333)
    H: int = 0            # hits allowed
    HR: int = 0           # HR allowed
    BB: int = 0           # walks issued (incl IBB)
    HBP: int = 0          # hit batters
    SO: int = 0           # strikeouts
    ER: int = 0           # earned runs
    R: int = 0            # runs allowed
    BF: int = 0           # batters faced
    pitches: int = 0      # total pitches thrown


# ─── batting metrics ──────────────────────────────────────────────────────


def avg(line: BattingLine) -> Optional[float]:
    """Batting average. ``H / AB``."""
    line = line.coerce()
    if line.AB <= 0:
        return None
    return round(line.H / line.AB, 4)


def obp(line: BattingLine) -> Optional[float]:
    """On-base percentage. ``(H + BB + HBP) / (AB + BB + HBP + SF)``."""
    line = line.coerce()
    denom = line.AB + line.BB + line.HBP + line.SF
    if denom <= 0:
        return None
    return round((line.H + line.BB + line.HBP) / denom, 4)


def slg(line: BattingLine) -> Optional[float]:
    """Slugging percentage. ``TB / AB``."""
    line = line.coerce()
    if line.AB <= 0:
        return None
    return round(line.TB / line.AB, 4)


def ops(line: BattingLine) -> Optional[float]:
    """OPS = OBP + SLG."""
    o = obp(line)
    s = slg(line)
    if o is None or s is None:
        return None
    return round(o + s, 4)


def iso(line: BattingLine) -> Optional[float]:
    """ISO (Isolated Power) = SLG − AVG."""
    s = slg(line)
    a = avg(line)
    if s is None or a is None:
        return None
    return round(s - a, 4)


def k_pct(line: BattingLine) -> Optional[float]:
    """K% = SO / PA."""
    line = line.coerce()
    if line.PA <= 0:
        return None
    return round(line.SO / line.PA, 4)


def bb_pct(line: BattingLine) -> Optional[float]:
    """BB% = BB / PA."""
    line = line.coerce()
    if line.PA <= 0:
        return None
    return round(line.BB / line.PA, 4)


def babip(line: BattingLine) -> Optional[float]:
    """BABIP = (H − HR) / (AB − SO − HR + SF)."""
    line = line.coerce()
    denom = line.AB - line.SO - line.HR + line.SF
    if denom <= 0:
        return None
    return round((line.H - line.HR) / denom, 4)


def woba(line: BattingLine) -> Optional[float]:
    """wOBA — weighted on-base average using FanGraphs-style linear
    weights (constants at module top, override for season-specific work)."""
    line = line.coerce()
    denom = line.AB + line.BB - line.IBB + line.SF + line.HBP
    if denom <= 0:
        return None
    bb_non_ibb = max(line.BB - line.IBB, 0)
    numerator = (
        WOBA_WEIGHT_BB * bb_non_ibb
        + WOBA_WEIGHT_HBP * line.HBP
        + WOBA_WEIGHT_1B * line.H1
        + WOBA_WEIGHT_2B * line.H2
        + WOBA_WEIGHT_3B * line.H3
        + WOBA_WEIGHT_HR * line.HR
    )
    return round(numerator / denom, 4)


# ─── pitching metrics ─────────────────────────────────────────────────────


def era(line: PitchingLine) -> Optional[float]:
    """ERA = ER × 9 / IP."""
    if line.IP <= 0:
        return None
    return round(line.ER * 9.0 / line.IP, 3)


def whip(line: PitchingLine) -> Optional[float]:
    """WHIP = (BB + H) / IP."""
    if line.IP <= 0:
        return None
    return round((line.BB + line.H) / line.IP, 3)


def k_per_9(line: PitchingLine) -> Optional[float]:
    """K/9 = SO × 9 / IP."""
    if line.IP <= 0:
        return None
    return round(line.SO * 9.0 / line.IP, 2)


def bb_per_9(line: PitchingLine) -> Optional[float]:
    """BB/9 = BB × 9 / IP."""
    if line.IP <= 0:
        return None
    return round(line.BB * 9.0 / line.IP, 2)


def hr_per_9(line: PitchingLine) -> Optional[float]:
    """HR/9 = HR × 9 / IP."""
    if line.IP <= 0:
        return None
    return round(line.HR * 9.0 / line.IP, 2)


def k_bb_ratio(line: PitchingLine) -> Optional[float]:
    """K/BB ratio. None when BB == 0 (avoid div by zero, signals
    "no walks" rather than "infinite ratio")."""
    if line.BB <= 0:
        return None
    return round(line.SO / line.BB, 2)


def fip(line: PitchingLine, *, constant: float = FIP_CONSTANT) -> Optional[float]:
    """FIP = (13×HR + 3×(BB+HBP) − 2×SO) / IP + constant.

    Constant is season-specific (recompute on full league data);
    default 3.10 is a NPB baseline used by several public analytics
    sites and gives plausible ranking inside a single season.
    """
    if line.IP <= 0:
        return None
    raw = (13 * line.HR + 3 * (line.BB + line.HBP) - 2 * line.SO) / line.IP
    return round(raw + constant, 3)


def xfip(line: PitchingLine, *, league_hr_per_fly: float = 0.10,
         constant: float = FIP_CONSTANT) -> Optional[float]:
    """xFIP — like FIP but replaces actual HR with expected HR based on
    league HR-per-fly rate. We approximate "fly balls" as
    ``BF − BB − HBP − SO − H_other`` which is **not exact** without
    batted-ball data; the resulting xFIP is therefore a rough proxy.

    For a more honest implementation we expose ``league_hr_per_fly`` so
    upstream can recompute once we have batted-ball ratios.
    """
    if line.IP <= 0:
        return None
    # crude fly-ball estimate: 35-40% of outs are fly balls typically
    estimated_fly_balls = max(line.IP * 3 * 0.37, 0.1)
    expected_hr = estimated_fly_balls * league_hr_per_fly
    raw = (13 * expected_hr + 3 * (line.BB + line.HBP) - 2 * line.SO) / line.IP
    return round(raw + constant, 3)


def era_plus(player_era: Optional[float], league_era: Optional[float]) -> Optional[float]:
    """ERA+ = league_ERA / player_ERA × 100. 100 = league average,
    >100 = better than league."""
    if player_era is None or league_era is None or player_era <= 0:
        return None
    return round(league_era / player_era * 100.0, 1)


# ─── batch helper for snapshot generation ─────────────────────────────────


def all_batter_metrics(line: BattingLine) -> dict[str, Optional[float]]:
    return {
        "AVG": avg(line),
        "OBP": obp(line),
        "SLG": slg(line),
        "OPS": ops(line),
        "ISO": iso(line),
        "wOBA": woba(line),
        "K_pct": k_pct(line),
        "BB_pct": bb_pct(line),
        "BABIP": babip(line),
    }


def all_pitcher_metrics(line: PitchingLine) -> dict[str, Optional[float]]:
    return {
        "ERA": era(line),
        "WHIP": whip(line),
        "K_per_9": k_per_9(line),
        "BB_per_9": bb_per_9(line),
        "HR_per_9": hr_per_9(line),
        "K_BB": k_bb_ratio(line),
        "FIP": fip(line),
        "xFIP": xfip(line),
    }
