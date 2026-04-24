"""Title-style contract helpers and validator for ticket 086."""

from __future__ import annotations

from dataclasses import dataclass
import re


DEFAULT_MIN_TITLE_LENGTH = 14
DEFAULT_MAX_TITLE_LENGTH = 60

TITLE_STYLE_SPECULATIVE = "TITLE_STYLE_SPECULATIVE"
TITLE_STYLE_GENERIC = "TITLE_STYLE_GENERIC"
TITLE_STYLE_CLICKBAIT = "TITLE_STYLE_CLICKBAIT"
TITLE_STYLE_OUT_OF_LENGTH = "TITLE_STYLE_OUT_OF_LENGTH"
TITLE_STYLE_FORBIDDEN_PREFIX = "TITLE_STYLE_FORBIDDEN_PREFIX"

FIXED_LANE_TO_EDITORIAL_SUBTYPE = {
    "program": "program",
    "notice": "notice",
    "probable_starter": "pregame",
    "farm_result": "farm",
    "postgame": "postgame",
}

SUBTYPE_ALIASES = {
    "fact_notice": "notice",
    "social_video_notice": "social_video",
    "x_source_notice": "x_source",
}

GENERIC_PHRASES = (
    "どう見る",
    "本音",
    "思い",
    "語る",
    "コメントまとめ",
    "試合後コメント",
    "ドラ1コンビ",
    "Xをどう見る",
    "X をどう見る",
    "Xがコメント",
    "Xについて語る",
    "注目したい",
    "振り返りたい",
    "コメントに注目",
    "コメントから見えるもの",
    "選手コメントを読む",
    "真相",
    "見どころ徹底解説",
)

CLICKBAIT_PHRASES = (
    "驚愕",
    "衝撃",
    "ヤバい",
    "史上最高",
    "圧倒的",
    "間違いなく",
)

COMMON_SPECULATIVE_PHRASES = (
    "どう見たいか",
    "何を見せるか",
    "どこを見たいか",
    "どうなるか",
)

SPECULATIVE_PHRASES_BY_SUBTYPE = {
    "postgame": COMMON_SPECULATIVE_PHRASES + ("どう見せるか",),
    "lineup": COMMON_SPECULATIVE_PHRASES + ("どう並べたか",),
    "manager": COMMON_SPECULATIVE_PHRASES,
    "pregame": COMMON_SPECULATIVE_PHRASES + ("どう挑む", "どう見せるか"),
    "farm": COMMON_SPECULATIVE_PHRASES + ("どう並べたか",),
    "comment": COMMON_SPECULATIVE_PHRASES,
    "social_video": COMMON_SPECULATIVE_PHRASES + ("どう見えるか",),
    "x_source": COMMON_SPECULATIVE_PHRASES,
    "notice": COMMON_SPECULATIVE_PHRASES,
    "program": COMMON_SPECULATIVE_PHRASES + ("どう見るか",),
}

FORBIDDEN_PREFIX_RE = re.compile(r"^\s*【(?:速報|LIVE|巨人)(?:[^】]*)】")
FORBIDDEN_STYLE_PATTERNS = (
    (re.compile(r"。"), "句点"),
    (re.compile(r"[『』]"), "引用記号『』"),
)
QUOTED_SEGMENT_RE = re.compile(r"(?:「[^」]*」|\"[^\"]*\")")
QUESTION_MARK_RE = re.compile(r"[?？]")
WHITESPACE_RE = re.compile(r"\s+")
NOTICE_STATE_SPECULATION_RE = re.compile(r"現在の状態は[.…]*[?？]?$")


@dataclass(frozen=True)
class TitleStyleContract:
    subtype: str
    base_forms: tuple[str, ...]
    allowed_forms: tuple[str, ...]
    banned_forms: tuple[str, ...]
    min_length: int = DEFAULT_MIN_TITLE_LENGTH
    max_length: int = DEFAULT_MAX_TITLE_LENGTH
    allow_notice_state_question: bool = False


@dataclass(frozen=True)
class StyleValidationResult:
    ok: bool
    reason_code: str | None
    detail: str | None


TITLE_STYLE_CONTRACTS = {
    "postgame": TitleStyleContract(
        subtype="postgame",
        base_forms=("巨人・<選手名>、<事象動詞句>！！！",),
        allowed_forms=(
            "巨人、<事象動詞句>！！！",
            "巨人・<選手名>、<数値><事象>！！！",
            "巨人・<選手名>、<前段> → <結果>！！！",
        ),
        banned_forms=(
            "<選手>はどう見せるか",
            "<選手>の真相とは?",
            "【速報】<選手>、<事象>",
            "<選手>、<事象>。",
        ),
        min_length=14,
        max_length=40,
    ),
    "lineup": TitleStyleContract(
        subtype="lineup",
        base_forms=("4月X日(曜) セ・リーグ公式戦「<対戦カード>」 巨人、スタメン発表！！！",),
        allowed_forms=(
            "巨人スタメン <キープレイヤー> <ポジション> <事象>",
            "巨人、ベンチ入り選手一覧",
        ),
        banned_forms=(
            "スタメンを<どう並べたか>",
            "<choice の比較>",
        ),
        min_length=25,
        max_length=60,
    ),
    "manager": TitleStyleContract(
        subtype="manager",
        base_forms=("巨人・<監督名>監督、<対象>の<項目>は…",),
        allowed_forms=(
            "巨人・<監督名>監督「<引用 inline>」",
            "巨人・<コーチ名>コーチ、<対象選手>の<項目>を<事象>",
        ),
        banned_forms=(
            "<監督>のコメントから見えるもの",
            "<監督>の本音とは",
        ),
        min_length=20,
        max_length=50,
    ),
    "pregame": TitleStyleContract(
        subtype="pregame",
        base_forms=("4月X日(曜)の予告先発が発表される！！！",),
        allowed_forms=(
            "<日付> <対戦カード> 予告先発: <投手名>",
            "巨人・<投手名>、<日付>先発予定",
        ),
        banned_forms=(
            "<試合> どう挑む?",
            "<投手>はどう見せるか",
        ),
        min_length=14,
        max_length=40,
    ),
    "farm": TitleStyleContract(
        subtype="farm",
        base_forms=("巨人二軍 <選手名>、<事象>！！！",),
        allowed_forms=(
            "巨人・<選手名>、二軍で<事象>",
            "巨人二軍スタメン 4月X日(曜) <対戦カード>",
        ),
        banned_forms=(
            "<若手>をどう並べたか",
            "<選手>はどこを見たいか",
        ),
        min_length=18,
        max_length=50,
    ),
    "comment": TitleStyleContract(
        subtype="comment",
        base_forms=(
            "巨人・<選手名>、<scene>に「<nucleus>」",
            "巨人・<選手名>、<対象>は「<nucleus>」と明かす",
            "巨人・<選手名>、<team_state>に<emotion verb>「<nucleus>」",
        ),
        allowed_forms=(
            "巨人・<選手名>、降板後にコメント",
            "<媒体>・<記者名>「<引用>」",
        ),
        banned_forms=(
            "どう見る",
            "本音",
            "思い",
            "語る",
            "コメントまとめ",
            "試合後コメント",
            "ドラ1コンビ",
            "Xをどう見る",
            "Xがコメント",
            "Xについて語る",
            "注目したい",
            "振り返りたい",
            "コメントに注目",
            "コメントから見えるもの",
            "選手コメントを読む",
        ),
        min_length=25,
        max_length=60,
    ),
    "social_video": TitleStyleContract(
        subtype="social_video",
        base_forms=("巨人・<選手名>の<事象>【動画】",),
        allowed_forms=("<球団公式 / 媒体>、<選手名>の<事象>を公開【動画】",),
        banned_forms=(
            "<選手>のすごさ【動画】",
            "<選手>はどう見えるか【動画】",
        ),
    ),
    "x_source": TitleStyleContract(
        subtype="x_source",
        base_forms=("<account_name>、<event 断定>",),
        allowed_forms=("<account_name>が報じる: <snippet>",),
        banned_forms=(
            "どう見る",
            "本音",
            "TOPIC_TIER_AS_FACT",
        ),
    ),
    "notice": TitleStyleContract(
        subtype="notice",
        base_forms=(
            "巨人・<選手名>、<状態>",
            "巨人・<選手名>、<診断>で\"<結論>\"！！！",
            "巨人、<選手名>を<対象>に<事象>",
        ),
        allowed_forms=("巨人・<選手名>、現在の状態は…？",),
        banned_forms=(
            "勝敗 / lineup / 統計を speculative 化した title",
            "<選手>の真相",
        ),
        min_length=14,
        max_length=40,
        allow_notice_state_question=True,
    ),
    "program": TitleStyleContract(
        subtype="program",
        base_forms=("<番組名>「<内容>」(<日付> <時刻>放送)",),
        allowed_forms=("<番組名>: <ゲスト名> 出演(<日付>)",),
        banned_forms=(
            "<番組>はどう見るか",
            "<番組>の見どころ徹底解説",
        ),
        min_length=20,
        max_length=50,
    ),
}


def normalize_title_style_subtype(subtype: str) -> str:
    normalized = str(subtype or "").strip().lower()
    if not normalized:
        return ""
    return SUBTYPE_ALIASES.get(normalized, normalized)


def fixed_lane_to_editorial_subtype(subtype: str) -> str:
    normalized = str(subtype or "").strip()
    return FIXED_LANE_TO_EDITORIAL_SUBTYPE.get(normalized, normalize_title_style_subtype(normalized))


def get_title_style_contract(subtype: str) -> TitleStyleContract:
    canonical = normalize_title_style_subtype(subtype)
    try:
        return TITLE_STYLE_CONTRACTS[canonical]
    except KeyError as exc:  # pragma: no cover - defensive path
        raise ValueError(f"unsupported title-style subtype: {subtype!r}") from exc


def _normalize_title(title: str) -> str:
    return WHITESPACE_RE.sub(" ", str(title or "")).strip()


def _strip_quoted_segments(title: str) -> str:
    return QUOTED_SEGMENT_RE.sub("", _normalize_title(title))


def build_title_style_prompt_lines(subtype: str) -> tuple[str, ...]:
    contract = get_title_style_contract(subtype)
    common_lines = (
        "球団名/主体は冒頭に置き、主語と事象は『、』でつなぐ。",
        "接頭辞の【速報】【LIVE】【巨人】は使わず、句点『。』も打たない。",
        "引用は原則「」を使う。『』は使わない。",
        f"文字数は {contract.min_length}-{contract.max_length} 字に収める。",
    )
    subtype_lines = (
        f"基本型: {' / '.join(contract.base_forms)}",
        f"許容形: {' / '.join(contract.allowed_forms)}",
        f"Don't generate titles like: {' / '.join(contract.banned_forms)}",
    )
    return common_lines + subtype_lines


def _match_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        if phrase and phrase in text:
            return phrase
    return None


def _generic_match(title: str) -> str | None:
    title_for_check = _strip_quoted_segments(title)
    match = _match_phrase(title_for_check, GENERIC_PHRASES)
    if match:
        return match
    for pattern, label in FORBIDDEN_STYLE_PATTERNS:
        if pattern.search(title_for_check):
            return label
    return None


def _clickbait_match(title: str) -> str | None:
    return _match_phrase(_normalize_title(title), CLICKBAIT_PHRASES)


def _allows_notice_question(title: str, contract: TitleStyleContract) -> bool:
    if not contract.allow_notice_state_question:
        return False
    return bool(NOTICE_STATE_SPECULATION_RE.search(_normalize_title(title)))


def _speculative_match(title: str, contract: TitleStyleContract) -> str | None:
    title_for_check = _strip_quoted_segments(title)
    match = _match_phrase(title_for_check, SPECULATIVE_PHRASES_BY_SUBTYPE.get(contract.subtype, COMMON_SPECULATIVE_PHRASES))
    if match:
        return match
    if QUESTION_MARK_RE.search(title_for_check) and not _allows_notice_question(title_for_check, contract):
        return "question_mark"
    return None


def validate_title_style(title: str, subtype: str) -> StyleValidationResult:
    contract = get_title_style_contract(subtype)
    normalized = _normalize_title(title)

    if FORBIDDEN_PREFIX_RE.search(normalized):
        return StyleValidationResult(False, TITLE_STYLE_FORBIDDEN_PREFIX, f"forbidden_prefix={normalized[:16]}")

    length = len(normalized)
    if length < contract.min_length or length > contract.max_length:
        return StyleValidationResult(
            False,
            TITLE_STYLE_OUT_OF_LENGTH,
            f"length={length} allowed={contract.min_length}-{contract.max_length}",
        )

    generic_match = _generic_match(normalized)
    if generic_match:
        return StyleValidationResult(False, TITLE_STYLE_GENERIC, f"matched={generic_match}")

    clickbait_match = _clickbait_match(normalized)
    if clickbait_match:
        return StyleValidationResult(False, TITLE_STYLE_CLICKBAIT, f"matched={clickbait_match}")

    speculative_match = _speculative_match(normalized, contract)
    if speculative_match:
        return StyleValidationResult(False, TITLE_STYLE_SPECULATIVE, f"matched={speculative_match}")

    return StyleValidationResult(True, None, None)


__all__ = [
    "CLICKBAIT_PHRASES",
    "FIXED_LANE_TO_EDITORIAL_SUBTYPE",
    "GENERIC_PHRASES",
    "StyleValidationResult",
    "TITLE_STYLE_CLICKBAIT",
    "TITLE_STYLE_CONTRACTS",
    "TITLE_STYLE_FORBIDDEN_PREFIX",
    "TITLE_STYLE_GENERIC",
    "TITLE_STYLE_OUT_OF_LENGTH",
    "TITLE_STYLE_SPECULATIVE",
    "TitleStyleContract",
    "build_title_style_prompt_lines",
    "fixed_lane_to_editorial_subtype",
    "get_title_style_contract",
    "normalize_title_style_subtype",
    "validate_title_style",
]
