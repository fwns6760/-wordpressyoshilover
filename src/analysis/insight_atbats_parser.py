"""INSIGHT-007 step 7c — at-bat text parser.

NPB box-score per-batter rows include a string list of at-bat outcomes,
each ~4-6 characters of compressed Japanese baseball notation:

    "中前安"  → 中堅手 (center) の前 (in front) で 安打 (single)
    "右越本①" → 右翼 (right) を越え (over) で 本塁打 (HR), 打点 1
    "三 振"   → 三振 (strikeout)
    "四 球"   → 四球 (walk)
    "二ゴロ"  → 二塁手 (2B) ゴロ (grounder) — out
    "遊飛"    → 遊撃手 (SS) 飛 (fly) — out
    "二併打"  → double play started at 2B
    "中犠"    → center, sacrifice fly
    "-"       → no plate appearance this slot

This module classifies each token into structured fields:

    {
      "raw": "中前安",
      "result_class": "hit",          # hit | out | strikeout | walk | hbp | sf | sac | error | other
      "bases": 1,                     # 0 (out/K/BB) | 1 (single/walk) | 2 | 3 | 4
      "fielding_position": "中",       # 投 / 捕 / 一 / 二 / 三 / 遊 / 左 / 中 / 右 / None
      "is_hr": False,
      "is_strikeout": False,
      "is_walk": False,
      "is_error": False,
      "is_double_play": False,
      "is_sacrifice": False,
    }

Field-direction extraction is the foundation for the UZR proxy
(``defense_opportunities``): when an at-bat ends at a fielding position
we record an "opportunity" for that position, and a "converted out" if
the result was an out (and not a hit / error).

This parser is **pure text → dict**; no DB, no I/O.
"""

from __future__ import annotations

import re
from typing import Optional

# 守備位置 marker (single Kanji)
_POSITION_KANJI = ("投", "捕", "一", "二", "三", "遊", "左", "中", "右")

# 結果 marker keywords (matched after optional position)
_HIT_MARKERS = ("安",)             # 中前安 / 右前安 / 左前安 等
_HR_MARKERS = ("本",)              # 左越本 / 右中本 / etc.
_K_MARKERS = ("三 振", "三振", "見三振", "空三振")
_WALK_MARKERS = ("四 球", "四球")
_HBP_MARKERS = ("死 球", "死球")
_FLYOUT_MARKERS = ("飛", "犠飛")    # 右飛 / 左飛
_GROUNDOUT_MARKERS = ("ゴロ",)     # 二ゴロ / 遊ゴロ
_DOUBLE_PLAY_MARKERS = ("併打", "併殺")
_SAC_HIT_MARKERS = ("犠打", "犠")  # 犠 covers 犠打 + 犠飛 (we further split below)
_ERROR_MARKERS = ("失",)
_FOUL_FLY_MARKERS = ("邪飛",)
_TRIPLE_MARKERS = ("三塁打", "３")  # NPB box often uses "右中３" for triple
_DOUBLE_MARKERS = ("二塁打", "２")  # "右中２" for double
_RUNNER_OUT_OUTSIDE_PA = ("-",)


def _detect_position(text: str) -> Optional[str]:
    """Return the first single-kanji fielding position marker found, or
    None. We require it appear in the *first 2 chars* so trailing
    Japanese punctuation in the score box doesn't false-positive."""
    head = text[:3]  # tolerate leading 2-byte char prefix on rare records
    for kanji in _POSITION_KANJI:
        if kanji in head:
            return kanji
    return None


def parse_atbat(text: str) -> dict:
    """Classify a single at-bat token. Always returns a dict; unknown
    tokens fall through to ``result_class='other'``."""
    raw = (text or "").strip()
    result: dict = {
        "raw": raw,
        "result_class": "other",
        "bases": 0,
        "fielding_position": None,
        "is_hr": False,
        "is_strikeout": False,
        "is_walk": False,
        "is_hbp": False,
        "is_error": False,
        "is_double_play": False,
        "is_sacrifice": False,
        "is_fly": False,
        "is_grounder": False,
    }
    if not raw or raw in _RUNNER_OUT_OUTSIDE_PA:
        return result

    # Strikeouts (highest signal — text often contains spaces from box format)
    if any(k in raw for k in _K_MARKERS):
        result["result_class"] = "strikeout"
        result["is_strikeout"] = True
        return result
    if any(k in raw for k in _WALK_MARKERS):
        result["result_class"] = "walk"
        result["is_walk"] = True
        result["bases"] = 1
        return result
    if any(k in raw for k in _HBP_MARKERS):
        result["result_class"] = "hbp"
        result["is_hbp"] = True
        result["bases"] = 1
        return result

    position = _detect_position(raw)
    if position:
        result["fielding_position"] = position

    if any(k in raw for k in _HR_MARKERS):
        result["result_class"] = "hit"
        result["is_hr"] = True
        result["bases"] = 4
        return result

    if any(k in raw for k in _DOUBLE_PLAY_MARKERS):
        result["result_class"] = "out"
        result["is_double_play"] = True
        result["is_grounder"] = True
        return result

    if any(k in raw for k in _ERROR_MARKERS):
        result["result_class"] = "error"
        result["is_error"] = True
        result["bases"] = 1
        return result

    # 三塁打 / 二塁打 — detect before plain "安" since the markers overlap
    if any(k in raw for k in _TRIPLE_MARKERS) and "本" not in raw:
        result["result_class"] = "hit"
        result["bases"] = 3
        return result
    if any(k in raw for k in _DOUBLE_MARKERS) and "本" not in raw:
        result["result_class"] = "hit"
        result["bases"] = 2
        return result

    # 安 (single hit)
    if any(k in raw for k in _HIT_MARKERS):
        result["result_class"] = "hit"
        result["bases"] = 1
        return result

    # 飛 (fly out) / ゴロ (grounder out) — must have position
    if any(k in raw for k in _FLYOUT_MARKERS):
        if "犠" in raw:
            result["result_class"] = "sac_fly"
            result["is_sacrifice"] = True
        else:
            result["result_class"] = "out"
        result["is_fly"] = True
        return result
    if any(k in raw for k in _GROUNDOUT_MARKERS):
        result["result_class"] = "out"
        result["is_grounder"] = True
        return result
    if any(k in raw for k in _FOUL_FLY_MARKERS):
        result["result_class"] = "out"
        result["is_fly"] = True
        return result
    if any(k in raw for k in _SAC_HIT_MARKERS):
        result["result_class"] = "sac"
        result["is_sacrifice"] = True
        return result

    return result


def aggregate_for_defense(atbats: list[str]) -> dict[str, dict[str, int]]:
    """Aggregate a batter's at-bat list into *opposing-side defense*
    opportunities by fielding position.

    Returns ``{position: {opportunities, converted_outs, hits_allowed, errors}}``.

    Caller multiplies this by team_role: when this batter is on the
    visiting team, the receiving fielders are the home team's defense
    and vice-versa.
    """
    out: dict[str, dict[str, int]] = {}
    for token in atbats:
        ab = parse_atbat(token)
        pos = ab["fielding_position"]
        if not pos:
            continue
        slot = out.setdefault(
            pos,
            {"opportunities": 0, "converted_outs": 0, "hits_allowed": 0, "errors": 0},
        )
        slot["opportunities"] += 1
        if ab["result_class"] == "out":
            slot["converted_outs"] += 1
        elif ab["result_class"] == "hit":
            slot["hits_allowed"] += 1
        elif ab["result_class"] == "error":
            slot["errors"] += 1
            slot["hits_allowed"] += 1  # 失策で出塁 = converted_outs 失敗扱い
    return out
