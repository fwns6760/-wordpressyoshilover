"""Player name → URL slug 変換 (data-site Phase 1.0 / ticket 443).

slug rule (Phase 1.0 lock):
- 日本人 player: 姓-名 を kebab-case romaji (例: 吉川尚輝 → yoshikawa-naoki)
- 外国人 player (katakana): そのまま kebab-case romaji (例: マルティネス → martinez)
- 役職 suffix (監督/監督代行/コーチ/外野手/捕手 等) は除去
- 全角空白 / 半角空白 / 中黒 / 「・」 を kebab に統一

Phase 1.0 では hardcoded mapping table を持つ (姓名 → romaji)。
Phase 1 full 拡大時に kakasi / pykakasi 等の自動変換に切替検討。
"""

from __future__ import annotations

# Phase 1.0 で必要な 3 player + 拡張に備えた一軍 active player 主要 30 名を hardcode。
# Phase 1.5 で残り 80 名を追記する。
_PLAYER_SLUG_MAP: dict[str, str] = {
    # Phase 1.0
    "吉川尚輝": "yoshikawa-naoki",
    "坂本勇人": "sakamoto-hayato",
    "丸佳浩": "maru-yoshihiro",
    # Phase 1.5 想定 (一軍 active 主要、 段階追加)
    "岡本和真": "okamoto-kazuma",
    "戸郷翔征": "togo-shosei",
    "山﨑伊織": "yamazaki-iori",
    "田中将大": "tanaka-masahiro",
    "大城卓三": "ohshiro-takuzo",
    "キャベッジ": "cabbage",
    "マルティネス": "martinez",
    "リチャード": "richard",
    "中山礼都": "nakayama-raito",
    "門脇誠": "kadowaki-makoto",
    "西舘勇陽": "nishidate-yuyo",
    "森下暢仁": "morishita-masato",
    "泉口友汰": "izuguchi-yuta",
    # 監督・コーチ
    "阿部慎之助": "abe-shinnosuke",
    "橋上秀樹": "hashigami-hideki",
}


def player_slug(name: str) -> str:
    """canonical player name → URL slug.

    未知 player は roster name の lower + ascii fallback (kebab) を返す。
    呼び出し元が validate するため、 ここで例外は投げない。
    """
    if not name:
        return ""
    normalized = name.strip()
    # roster の姓名間 空白 (半角/全角) を吸収
    for sp in (" ", "　"):
        if sp in normalized:
            normalized = normalized.replace(sp, "")
    if normalized in _PLAYER_SLUG_MAP:
        return _PLAYER_SLUG_MAP[normalized]
    # fallback: ascii only / lower / kebab (未知 player 救済)
    ascii_part = "".join(c if (c.isascii() and (c.isalnum() or c == "-")) else "-" for c in normalized.lower())
    return "-".join(p for p in ascii_part.split("-") if p) or normalized


def known_player_names() -> list[str]:
    """slug map に載っている canonical name list (Phase 1.0+1.5 想定)。"""
    return sorted(_PLAYER_SLUG_MAP.keys())


__all__ = ["player_slug", "known_player_names"]
