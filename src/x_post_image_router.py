"""437 image template auto-routing.

publisher 由来 data (subtype + crown_count 等) から SVG template_key を返す。
LLM 呼び出し 0、 純 Python の if/else 判定だけ。

routing 例:
  - subtype="spotlight" + crown_count >= 5 → "12team_crown"   (3x2 grid)
  - subtype="spotlight" + crown_count == 3 → "12team_crown_3" (1x3 + secondary list)
  - subtype="spotlight" + crown_count <= 1 → "player_spotlight" (hero card)
  - subtype="ranking"                       → "ranking_table"
  - subtype="postgame"                      → "scoreboard"

failure fallback: 未知 subtype は "ranking_table" を返す (caller 側で None 画像 fallback)。
"""
from __future__ import annotations

from typing import Any

TEMPLATE_KEYS = frozenset(
    {
        "ranking_table",
        "player_spotlight",
        "scoreboard",
        "starting_lineup",
        "standings",
        "pitcher_card",
        "monthly_summary",
        "12team_crown",
        "12team_crown_3",
        "data_sheet",
        "chart_bars",
        "12team_bar",
        "spray_chart",
    }
)

DEFAULT_TEMPLATE = "ranking_table"

_SUBTYPE_MAP = {
    "ranking": "ranking_table",
    "postgame": "scoreboard",
    "lineup": "starting_lineup",
    "standings": "standings",
    "pitcher": "pitcher_card",
    "monthly": "monthly_summary",
    "trend": "chart_bars",
    "data_sheet": "data_sheet",
    "spray": "spray_chart",
    "12team_bar": "12team_bar",
}


def select_template(data: dict[str, Any]) -> str:
    """data → template_key。 失敗時は DEFAULT_TEMPLATE を返す。"""
    subtype = (data or {}).get("subtype", "") or ""
    if subtype == "spotlight":
        crown_count = int((data or {}).get("crown_count", 0) or 0)
        if crown_count >= 5:
            return "12team_crown"
        if crown_count >= 2:
            return "12team_crown_3"
        return "player_spotlight"
    return _SUBTYPE_MAP.get(subtype, DEFAULT_TEMPLATE)
