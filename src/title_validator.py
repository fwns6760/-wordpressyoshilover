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
DATE_JP_TOKEN_RE = re.compile(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日")
DATE_SLASH_TOKEN_RE = re.compile(r"(?:\d{4}/)?\d{1,2}/\d{1,2}")
TIME_TOKEN_RE = re.compile(r"\d{1,2}:\d{2}")

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
_LINEUP_ORDER_SLOT_RE = re.compile(r"(?<![0-9０-９])[1-9１-９]番(?!手)")
_LINEUP_OPPONENT_MARKERS = (
    "阪神",
    "中日",
    "ヤクルト",
    "広島",
    "DeNA",
    "ＤｅＮＡ",
    "横浜",
    "ソフトバンク",
    "日本ハム",
    "日ハム",
    "ロッテ",
    "楽天",
    "オリックス",
    "西武",
    "戦",
    "vs",
    "VS",
    "対",
)
_LINEUP_STARTER_MARKERS = ("先発", "予告先発")
_MANAGER_EVENT_MARKERS = ("説明", "言及", "明か", "継投", "起用", "采配", "評価", "振り返", "狙い")
_PLAYER_COMMENT_MARKERS = ("コメント", "談話", "一問一答", "発言", "振り返", "明か", "語", "手応え", "意欲")
_FARM_PERFORMANCE_MARKERS = ("安打", "打点", "本塁打", "ホームラン", "好投", "無失点", "奪三振", "打", "回")
_NOTICE_EVENT_MARKERS = (
    "一軍昇格",
    "昇格",
    "一軍登録",
    "再登録",
    "登録抹消",
    "抹消",
    "一軍合流",
    "合流",
    "復帰",
    "実戦復帰",
    "二軍落ち",
)
_FARM_PLAYER_EVENT_MARKERS = _FARM_PERFORMANCE_MARKERS + ("実戦復帰", "復帰", "昇格", "昇格候補", "候補")
_QUOTE_CHARS_RE = re.compile(r"[「『].+[」』]")

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

LEADING_PARTICLE_RE = re.compile(r"^[がをにのへとでもや]")
RELATED_INFO_ESCAPE_RE = re.compile(r"関連情報\s*$")
GENERIC_PERSON_NOUNS = (
    "選手",
    "投手",
    "コーチ",
    "監督",
    "捕手",
    "内野手",
    "外野手",
    "チーム",
    "球団",
    "ベンチ",
    "首脳陣",
)
KNOWN_PERSON_NAME_MARKERS = (
    "阿部",
    "川相",
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
    "吉田",
)
NON_NAME_SPEAKER_LABELS = frozenset(
    (
        *GENERIC_PERSON_NOUNS,
        "大敗",
        "快勝",
        "惨敗",
        "打線",
    )
)
NON_NAME_NAME_TOKENS = frozenset(
    {
        *NON_NAME_SPEAKER_LABELS,
        "巨人",
        "ジャイアンツ",
        "今季",
        "一軍",
        "二軍",
        "合流",
        "登録",
        "抹消",
        "復帰",
        "昇格",
        "先発",
        "試合",
        "結果",
        "速報",
        "練習",
        "公示",
        "関連情報",
    }
)
_GENERIC_PERSON_NOUN_PATTERN = "|".join(re.escape(noun) for noun in GENERIC_PERSON_NOUNS)
GENERIC_SUBJECT_START_RE = re.compile(rf"^(?:{_GENERIC_PERSON_NOUN_PATTERN})(?:[、，,\s]|$)")
GENERIC_SUBJECT_END_RE = re.compile(rf"(?:{_GENERIC_PERSON_NOUN_PATTERN})\s*$")
NAME_PATTERN_RE = re.compile(
    r"(?:[一-龯]{2,4}(?:[ァ-ヴー]+|・[一-龯ァ-ヴー]+)?|[A-Z][a-zA-Z]+)"
    r"(?=(?:が|は|も|の|、|，|,|「|『|[0-9０-９]|$))"
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
        try:
            from .weak_title_rescue import is_strong_with_name_and_event
        except ImportError:  # pragma: no cover - rss_fetcher top-level import path
            from weak_title_rescue import is_strong_with_name_and_event

        if is_strong_with_name_and_event(normalized):
            return False, ""
        return True, "no_strong_marker"
    return False, ""


def title_starts_with_particle(title: str) -> bool:
    stripped = _normalize_title_text(title)
    if not stripped:
        return False
    if LEADING_PARTICLE_RE.match(stripped):
        return True
    core = _strip_reserved_prefixes(stripped)
    return bool(core and LEADING_PARTICLE_RE.match(core))


def title_uses_related_info_escape(title: str) -> bool:
    stripped = _normalize_title_text(title)
    if not stripped:
        return False
    return bool(RELATED_INFO_ESCAPE_RE.search(stripped))


def _looks_like_person_name_token(token: str) -> bool:
    stripped = str(token or "").strip(" ・、，,")
    if not stripped:
        return False
    if stripped in NON_NAME_NAME_TOKENS:
        return False
    if stripped.endswith(("情報", "起用", "登録", "抹消", "復帰", "昇格", "先発", "合流", "練習", "速報", "試合", "結果")):
        return False
    return True


def title_has_person_name_candidate(title: str) -> bool:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False
    core = _strip_reserved_prefixes(normalized) or normalized
    if any(marker in core for marker in KNOWN_PERSON_NAME_MARKERS):
        return True
    for match in NAME_PATTERN_RE.finditer(core):
        if _looks_like_person_name_token(match.group(0)):
            return True
    return False


def title_has_only_generic_subject(title: str) -> bool:
    """固有人名がなく、generic noun だけが主語になっている title を narrow に検出する。"""
    normalized = _normalize_title_text(title)
    if not normalized:
        return False
    core = _strip_reserved_prefixes(normalized) or normalized
    if not any(noun in core for noun in GENERIC_PERSON_NOUNS):
        return False
    if title_has_person_name_candidate(core):
        return False
    return bool(GENERIC_SUBJECT_START_RE.match(core) or GENERIC_SUBJECT_END_RE.search(core))


def is_non_name_speaker_label(value: str) -> bool:
    normalized = _normalize_title_text(value)
    if not normalized:
        return False
    if title_has_person_name_candidate(normalized):
        return False
    return normalized in NON_NAME_SPEAKER_LABELS


def is_weak_subject_title(title: str) -> tuple[bool, str]:
    """対象者名が弱い title を検出する。"""
    stripped = _normalize_title_text(title)
    if not stripped:
        return False, ""
    if title_starts_with_particle(stripped):
        return True, "leading_particle_no_subject"
    if title_uses_related_info_escape(stripped):
        return True, "related_info_escape"
    if title_has_only_generic_subject(stripped):
        return True, "generic_noun_only_no_person_name"
    return False, ""


def _title_has_lineup_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    if any(marker in normalized for marker in _LINEUP_OPPONENT_MARKERS):
        return True, "lineup_has_opponent"
    if _LINEUP_ORDER_SLOT_RE.search(normalized):
        return True, "lineup_has_order"
    if any(marker in normalized for marker in _LINEUP_STARTER_MARKERS):
        return True, "lineup_has_starter"
    return False, "lineup_missing_opponent_order_or_starter"


def _title_has_manager_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    core = _strip_reserved_prefixes(normalized) or normalized
    if GENERIC_SUBJECT_START_RE.match(core) or any(core.startswith(noun) for noun in GENERIC_PERSON_NOUNS):
        return False, "manager_missing_speaker"
    if not title_has_person_name_candidate(normalized):
        return False, "manager_missing_speaker"
    if _QUOTE_CHARS_RE.search(normalized):
        return True, "manager_has_quote"
    if any(marker in normalized for marker in _MANAGER_EVENT_MARKERS):
        return True, "manager_has_event"
    return False, "manager_missing_quote_or_event"


def _title_has_farm_result_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    if _SCORE_RE.search(normalized):
        return True, "farm_result_has_score"
    if title_has_person_name_candidate(normalized) and any(marker in normalized for marker in _FARM_PERFORMANCE_MARKERS):
        return True, "farm_result_has_player_performance"
    return False, "farm_result_missing_score_or_player_performance"


def title_has_minimum_article_context(title: str, article_subtype: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"

    subtype = _normalize_minimum_context_subtype(article_subtype)
    if not subtype:
        subtype = str(article_subtype or "").strip().lower()
    if subtype == "lineup":
        return _title_has_lineup_context(normalized)
    if subtype == "postgame":
        return _title_has_postgame_context(normalized)
    if subtype == "manager":
        return _title_has_manager_context(normalized)
    if subtype == "player_comment":
        return _title_has_player_comment_context(normalized)
    if subtype in {"farm_result", "farm"}:
        return _title_has_farm_result_context(normalized)
    if subtype == "farm_lineup":
        return _title_has_farm_lineup_context(normalized)
    if subtype == "pregame":
        return _title_has_pregame_context(normalized)
    if subtype == "roster_notice":
        return _title_has_roster_notice_context(normalized)
    if subtype == "farm_player_result":
        return _title_has_farm_player_result_context(normalized)
    return True, "not_applicable"


def _normalize_minimum_context_subtype(article_subtype: str) -> str:
    subtype = str(article_subtype or "").strip().lower()
    if not subtype:
        return ""
    if subtype in {"manager", "coach", "manager_comment", "coach_comment", "manager_quote", "coach_quote"}:
        return "manager"
    if subtype in {"player", "player_comment", "player_quote"}:
        return "player_comment"
    if subtype in {"notice", "player_notice", "roster_notice", "recovery", "player_recovery", "injury_recovery_notice"}:
        return "roster_notice"
    if subtype in {"farm", "farm_result"}:
        return "farm_result"
    if subtype == "farm_lineup":
        return "farm_lineup"
    if subtype in {"pregame", "probable_starter"}:
        return "pregame"
    if subtype == "farm_player_result":
        return "farm_player_result"
    return subtype


def _title_has_postgame_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    if _SCORE_RE.search(normalized) and any(marker in normalized for marker in _POSTGAME_MARKERS):
        return True, "postgame_has_score_and_result"
    if normalized.startswith("試合結果") and _SCORE_RE.search(normalized):
        return True, "postgame_has_score"
    return False, "postgame_missing_score_or_result"


def _title_has_player_comment_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    if not title_has_person_name_candidate(normalized):
        return False, "player_comment_missing_player"
    if _QUOTE_CHARS_RE.search(normalized):
        return True, "player_comment_has_quote"
    if any(marker in normalized for marker in _PLAYER_COMMENT_MARKERS):
        return True, "player_comment_has_comment_marker"
    return False, "player_comment_missing_quote_or_comment_marker"


def _title_has_farm_lineup_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    if not any(marker in normalized for marker in _FARM_MARKERS):
        return False, "farm_lineup_missing_farm_marker"
    lineup_ok, _reason = _title_has_lineup_context(normalized)
    if lineup_ok:
        return True, "farm_lineup_has_order"
    if DATE_JP_TOKEN_RE.search(normalized) or DATE_SLASH_TOKEN_RE.search(normalized):
        return True, "farm_lineup_has_date"
    return False, "farm_lineup_missing_date_or_order"


def _title_has_pregame_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    lineup_ok, _reason = _title_has_lineup_context(normalized)
    if lineup_ok:
        return True, "pregame_has_lineup_context"
    has_time = bool(TIME_TOKEN_RE.search(normalized))
    has_opponent = any(marker in normalized for marker in _LINEUP_OPPONENT_MARKERS)
    if any(marker in normalized for marker in _PREGAME_MARKERS) and (has_time or has_opponent):
        return True, "pregame_has_time_or_opponent"
    if has_time and has_opponent:
        return True, "pregame_has_schedule"
    return False, "pregame_missing_time_opponent_or_starter"


def _title_has_roster_notice_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    if not title_has_person_name_candidate(normalized):
        return False, "roster_notice_missing_player"
    if any(marker in normalized for marker in _NOTICE_EVENT_MARKERS):
        return True, "roster_notice_has_event"
    return False, "roster_notice_missing_event"


def _title_has_farm_player_result_context(title: str) -> tuple[bool, str]:
    normalized = _normalize_title_text(title)
    if not normalized:
        return False, "title_empty"
    if not title_has_person_name_candidate(normalized):
        return False, "farm_player_result_missing_player"
    if any(marker in normalized for marker in _FARM_MARKERS) and any(
        marker in normalized for marker in _FARM_PLAYER_EVENT_MARKERS
    ):
        return True, "farm_player_result_has_event"
    if any(marker in normalized for marker in _FARM_PLAYER_EVENT_MARKERS):
        return True, "farm_player_result_has_player_event"
    return False, "farm_player_result_missing_event"


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
    "is_non_name_speaker_label",
    "is_weak_generated_title",
    "is_weak_subject_title",
    "is_supported_subtype",
    "starts_with_sokuho_prefix",
    "starts_with_starmen_prefix",
    "title_has_minimum_article_context",
    "title_has_person_name_candidate",
    "validate_title_candidate",
]
