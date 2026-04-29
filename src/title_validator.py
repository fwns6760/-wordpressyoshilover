"""Title-layer subtype guard helpers for ticket 030."""

from __future__ import annotations

import re


TITLE_PREFIX_BY_SUBTYPE = {
    "lineup": "巨人スタメン",
    "postgame": "試合結果",
    "live_update": "",
    "pregame": "先発情報",
    "farm": "二軍",
    "fact_notice": "訂正・告知系",
}

REQUIRED_FIRST_BLOCK_BY_SUBTYPE = {
    "lineup": "【試合概要】",
    "postgame": "【試合結果】",
    "live_update": "【いま起きていること】",
    "pregame": "【変更情報の要旨】",
    "farm": "【二軍結果・活躍の要旨】",
    "fact_notice": "【訂正の対象】",
}

CONTROLLED_SUBTYPES = tuple(TITLE_PREFIX_BY_SUBTYPE.keys())
LIVE_UPDATE_REQUIRED_FIRST_BLOCK = REQUIRED_FIRST_BLOCK_BY_SUBTYPE["live_update"]

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LEADING_BRACKET_RE = re.compile(r"^\s*【[^】]+】\s*")
_STARMEN_PREFIX_RE = re.compile(r"^[\s\u3000【\[\(（「『]*(?:巨人スタメン)")
_SOKUHO_PREFIX_RE = re.compile(r"^[\s\u3000【\[\(（「『]*速報")
_LIVE_UPDATE_INNING_RE = re.compile(r"(?<![0-9０-９])(?:[1-9]|1\d|[１-９])回(?:表|裏|終了|途中|で)?")
_SCORE_RE = re.compile(r"\d{1,2}\s*[－\-–]\s*\d{1,2}")

_LIVE_UPDATE_MARKERS = ("途中経過", "勝ち越し", "逆転", "同点", "継投")
_POSTGAME_MARKERS = (
    "試合結果",
    "勝利",
    "敗戦",
    "引き分け",
    "白星",
    "黒星",
    "試合後コメント",
    "試合の流れ",
    "分岐点",
    "終盤の一打",
    "打線沈黙",
)
_PREGAME_MARKERS = ("先発情報", "予告先発", "先発", "試合前")
_FACT_NOTICE_MARKERS = ("訂正", "告知", "お知らせ", "お詫び", "公示", "誤報", "取り下げ")
_FARM_MARKERS = ("二軍", "２軍", "2軍", "ファーム")

_REROLL_DEFAULT_SUFFIX = {
    "lineup": "発表のポイント",
    "postgame": "試合のポイント",
    "live_update": "途中経過のポイント",
    "pregame": "試合前のポイント",
    "farm": "試合のポイント",
    "fact_notice": "告知内容",
}

WEAK_GENERATED_TITLE_PHRASES = (
    "前日コメント整理",
    "ベンチ関連の発言ポイント",
    "実戦で何を見せるか",
    "何を見せるか",
    "注目ポイント",
    "今後に注目",
    "詳しくはこちら",
    "試合の詳細はこちら",
    "結果のポイント",
    "コメント整理",
    "発言ポイント",
)

WEAK_GENERATED_TITLE_STRONG_MARKERS = (
    "巨人",
    "ジャイアンツ",
    "選手",
    "監督",
    "コーチ",
    "投手",
    "捕手",
    "内野手",
    "外野手",
    "スタメン",
    "先発",
    "試合",
    "予告先発",
    "プレー",
    "登録",
    "抹消",
    "復帰",
    "公示",
    "離脱",
    "番組",
    "配信",
    "放送",
    "GIANTS TV",
    "戸郷",
    "山崎",
    "井上",
    "岡本",
    "坂本",
    "丸",
    "中田",
    "梶谷",
    "浅野",
    "吉川",
    "大城",
    "小林",
    "菅野",
    "高橋",
    "田中",
    "西舘",
    "阪神",
    "中日",
    "ヤクルト",
    "広島",
    "DeNA",
    "ロッテ",
    "オリックス",
    "ソフトバンク",
    "日ハム",
    "西武",
    "楽天",
    "マリナーズ",
    "ドジャース",
)


def is_supported_subtype(article_subtype: str) -> bool:
    return article_subtype in CONTROLLED_SUBTYPES


def _normalize_title_text(text: str) -> str:
    clean = _HTML_RE.sub("", text or "")
    clean = _WS_RE.sub(" ", clean)
    return clean.strip()


def starts_with_starmen_prefix(title: str) -> bool:
    return bool(_STARMEN_PREFIX_RE.search(_normalize_title_text(title)))


def starts_with_sokuho_prefix(title: str) -> bool:
    return bool(_SOKUHO_PREFIX_RE.search(_normalize_title_text(title)))


def _has_live_update_signal(title: str) -> bool:
    normalized = _normalize_title_text(title)
    return bool(
        starts_with_sokuho_prefix(normalized)
        or _LIVE_UPDATE_INNING_RE.search(normalized)
        or any(marker in normalized for marker in _LIVE_UPDATE_MARKERS)
    )


def _has_postgame_signal(title: str) -> bool:
    normalized = _normalize_title_text(title)
    return bool(
        normalized.startswith("試合結果")
        or "巨人試合結果" in normalized
        or (_SCORE_RE.search(normalized) and any(marker in normalized for marker in ("勝利", "敗戦", "引き分け", "白星", "黒星")))
        or any(marker in normalized for marker in _POSTGAME_MARKERS)
    )


def _has_pregame_signal(title: str) -> bool:
    normalized = _normalize_title_text(title)
    return any(marker in normalized for marker in _PREGAME_MARKERS)


def _has_fact_notice_signal(title: str) -> bool:
    normalized = _normalize_title_text(title)
    return any(marker in normalized for marker in _FACT_NOTICE_MARKERS)


def _has_farm_signal(title: str) -> bool:
    normalized = _normalize_title_text(title)
    return any(marker in normalized for marker in _FARM_MARKERS)


def infer_subtype_from_title(title: str) -> str:
    normalized = _normalize_title_text(title)
    if not normalized:
        return ""
    if starts_with_starmen_prefix(normalized):
        return "lineup"
    if _has_fact_notice_signal(normalized):
        return "fact_notice"
    if _has_farm_signal(normalized):
        return "farm"
    if _has_live_update_signal(normalized):
        return "live_update"
    if _has_pregame_signal(normalized):
        return "pregame"
    if _has_postgame_signal(normalized):
        return "postgame"
    return ""


def is_weak_generated_title(title: str) -> tuple[bool, str]:
    """生成 title が weak かどうか判定する。"""
    normalized = str(title or "").strip()
    if not normalized:
        return True, "title_empty"
    if len(normalized) < 12:
        return True, "title_too_short"
    for phrase in WEAK_GENERATED_TITLE_PHRASES:
        if phrase in normalized:
            return True, f"blacklist_phrase:{phrase}"
    if not any(marker in normalized for marker in WEAK_GENERATED_TITLE_STRONG_MARKERS):
        return True, "no_strong_marker"
    return False, ""


def validate_title_candidate(title: str, article_subtype: str) -> dict[str, object]:
    expected_first_block = REQUIRED_FIRST_BLOCK_BY_SUBTYPE.get(article_subtype, "")
    inferred_subtype = infer_subtype_from_title(title)
    fail_axes: list[str] = []

    def _append(axis: str) -> None:
        if axis not in fail_axes:
            fail_axes.append(axis)

    if not is_supported_subtype(article_subtype):
        return {
            "ok": True,
            "fail_axes": fail_axes,
            "inferred_subtype": inferred_subtype,
            "expected_first_block": expected_first_block,
            "supports_guard": False,
        }

    if starts_with_starmen_prefix(title) and article_subtype != "lineup":
        _append("starmen_prefix_forbidden")

    if starts_with_sokuho_prefix(title) and article_subtype != "live_update":
        _append("sokuho_prefix_forbidden")

    if inferred_subtype and inferred_subtype != article_subtype:
        _append("title_subtype_mismatch")

    if _has_live_update_signal(title) and expected_first_block != LIVE_UPDATE_REQUIRED_FIRST_BLOCK:
        _append("strong_live_title_body_conflict")

    stop_reason = fail_axes[0] if fail_axes else ""
    return {
        "ok": not fail_axes,
        "fail_axes": fail_axes,
        "inferred_subtype": inferred_subtype,
        "expected_first_block": expected_first_block,
        "supports_guard": True,
        "stop_reason": stop_reason,
    }


def _strip_reserved_prefixes(title: str) -> str:
    text = _normalize_title_text(title)
    changed = True
    while changed and text:
        changed = False
        updated = _LEADING_BRACKET_RE.sub("", text).strip()
        if updated != text:
            text = updated
            changed = True
        for prefix in (
            "速報",
            "巨人スタメン",
            "試合結果",
            "先発情報",
            "巨人二軍スタメン",
            "巨人二軍",
            "二軍",
            "ファーム",
            "訂正",
            "告知",
            "お知らせ",
            "お詫び",
            "公示",
            "誤報",
            "取り下げ",
        ):
            updated = re.sub(rf"^{re.escape(prefix)}[:：]?\s*", "", text).strip()
            if updated != text:
                text = updated
                changed = True
                break
    return text


def _safe_reroll_core(title: str, article_subtype: str) -> str:
    core = _strip_reserved_prefixes(title)
    if not core:
        return ""
    if article_subtype != "lineup":
        core = _STARMEN_PREFIX_RE.sub("", core).strip()
    if article_subtype != "live_update":
        core = _SOKUHO_PREFIX_RE.sub("", core).strip()
        core = _LIVE_UPDATE_INNING_RE.sub("", core).strip()
        core = core.replace("途中経過", "").strip()
    core = _WS_RE.sub(" ", core).strip(" ・、:：")
    if not core:
        return ""

    if article_subtype != "live_update" and _has_live_update_signal(core):
        return ""
    if article_subtype != "lineup" and starts_with_starmen_prefix(core):
        return ""
    if article_subtype == "pregame" and (_has_postgame_signal(core) or _has_fact_notice_signal(core)):
        return ""
    if article_subtype == "lineup" and (_has_postgame_signal(core) or _has_fact_notice_signal(core)):
        return ""
    if article_subtype == "fact_notice" and not _has_fact_notice_signal(core):
        return ""
    return core


def build_reroll_title(title: str, article_subtype: str) -> str:
    if not is_supported_subtype(article_subtype):
        return _normalize_title_text(title)

    core = _safe_reroll_core(title, article_subtype)
    default_suffix = _REROLL_DEFAULT_SUFFIX[article_subtype]

    if article_subtype == "live_update":
        candidate = core or default_suffix
        if "途中経過" not in candidate:
            candidate = f"途中経過 {candidate}".strip()
        return _normalize_title_text(candidate)

    prefix = TITLE_PREFIX_BY_SUBTYPE[article_subtype]
    if article_subtype == "fact_notice":
        prefix = "訂正"

    candidate = f"{prefix} {core or default_suffix}".strip()
    return _normalize_title_text(candidate)


__all__ = [
    "CONTROLLED_SUBTYPES",
    "LIVE_UPDATE_REQUIRED_FIRST_BLOCK",
    "REQUIRED_FIRST_BLOCK_BY_SUBTYPE",
    "TITLE_PREFIX_BY_SUBTYPE",
    "build_reroll_title",
    "infer_subtype_from_title",
    "is_weak_generated_title",
    "is_supported_subtype",
    "starts_with_sokuho_prefix",
    "starts_with_starmen_prefix",
    "validate_title_candidate",
]
