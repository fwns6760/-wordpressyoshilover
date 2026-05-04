from __future__ import annotations

import os
import re
from difflib import SequenceMatcher


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
ENABLE_FORBIDDEN_PHRASE_FILTER_ENV_FLAG = "ENABLE_FORBIDDEN_PHRASE_FILTER"
ENABLE_TITLE_GENERIC_COMPOUND_GUARD_ENV_FLAG = "ENABLE_TITLE_GENERIC_COMPOUND_GUARD"
ENABLE_QUOTE_INTEGRITY_GUARD_ENV_FLAG = "ENABLE_QUOTE_INTEGRITY_GUARD"
ENABLE_DUPLICATE_SENTENCE_GUARD_ENV_FLAG = "ENABLE_DUPLICATE_SENTENCE_GUARD"
ENABLE_ACTIVE_TEAM_MISMATCH_GUARD_ENV_FLAG = "ENABLE_ACTIVE_TEAM_MISMATCH_GUARD"
ENABLE_SOURCE_GROUNDING_STRICT_ENV_FLAG = "ENABLE_SOURCE_GROUNDING_STRICT"

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_GENERIC_COMPOUND_SUBJECTS = frozenset(
    {
        "実施選手",
        "起用選手",
        "登板投手",
        "指名選手",
        "復帰選手",
        "昇格選手",
        "登録選手",
        "抹消選手",
        "合流選手",
        "対象選手",
        "出場選手",
        "育成選手",
        "候補選手",
        "参加選手",
    }
)
_FORBIDDEN_HEADING_REPLACEMENTS = {
    "【発信内容の要約】": "【投稿で出ていた内容】",
    "【文脈と背景】": "【この話が出た流れ】",
}
_FORBIDDEN_LINE_REPLACEMENTS = (
    ("発信内容の要約", "投稿で出ていた内容"),
    ("文脈と背景", "この話が出た流れ"),
    ("source にある範囲だけで", "元記事で確認できる範囲で"),
    ("sourceにある範囲だけで", "元記事で確認できる範囲で"),
    ("目を引きます", "という表現が出ていました"),
    ("注目が集まります", "目が向きます"),
    ("ファン必見です", "押さえておきたい内容です"),
    ("今後の動向から目が離せません", "次にどう動くかを追っていきたいです"),
    ("本日は、", "今回の話題は、"),
    ("詳しく見ていきましょう", "整理します"),
    ("今後の活躍に注目です", "次の実戦でどう出るかを見ていきたいです"),
    ("気になる動向です", "動きが気になる話題です"),
)
_FORBIDDEN_PATTERNS = (
    ("ai_intro", re.compile(r"本日は、")),
    ("ai_explainer", re.compile(r"詳しく見ていきましょう")),
    ("ai_close_future", re.compile(r"今後の活躍に注目です")),
    ("ai_close_motion", re.compile(r"気になる動向です")),
    ("phrase_eye_catching", re.compile(r"目を引きます")),
    ("phrase_attention_gathers", re.compile(r"注目が集まります")),
    ("phrase_fan_must_see", re.compile(r"ファン必見です")),
    ("phrase_future_watch", re.compile(r"今後の動向から目が離せません")),
    ("phrase_iie_deshou", re.compile(r"と言えるでしょう")),
    ("phrase_dewa_deshouka", re.compile(r"ではないでしょうか")),
    ("heading_social_summary", re.compile(r"発信内容の要約")),
    ("heading_context_background", re.compile(r"文脈と背景")),
    ("internal_source_instruction", re.compile(r"source\s*にある範囲だけで", re.IGNORECASE)),
    ("internal_prompt_output", re.compile(r"(?:HTMLタグなし|本文のみ出力|見出しは「)")),
)
_QUOTE_RE = re.compile(r"[「『][^」』]{1,120}[」』]")
_TEAM_GROUPS = {
    "巨人": ("読売ジャイアンツ", "ジャイアンツ", "巨人", "読売"),
    "阪神": ("阪神",),
    "中日": ("中日",),
    "広島": ("広島",),
    "ヤクルト": ("ヤクルト",),
    "楽天": ("楽天",),
    "DeNA": ("ＤｅＮＡ", "DeNA", "横浜", "ベイスターズ"),
    "ロッテ": ("ロッテ",),
    "オリックス": ("オリックス",),
    "ソフトバンク": ("ソフトバンク",),
    "日本ハム": ("日本ハム", "日ハム"),
    "西武": ("西武",),
    "ドジャース": ("ドジャース", "Dodgers"),
    "ブルージェイズ": ("ブルージェイズ", "Blue Jays", "BLUE JAYS"),
    "ヤンキース": ("ヤンキース", "Yankees"),
    "メッツ": ("メッツ", "Mets"),
    "カブス": ("カブス", "Cubs"),
    "パドレス": ("パドレス", "Padres"),
    "エンゼルス": ("エンゼルス", "Angels"),
    "レッドソックス": ("レッドソックス", "Red Sox"),
    "フィリーズ": ("フィリーズ", "Phillies"),
    "マリナーズ": ("マリナーズ", "Mariners"),
}
_NON_GIANTS_PREFIXES = tuple(team for team in _TEAM_GROUPS.keys() if team != "巨人")
_TEAM_ALIAS_TO_CANONICAL = {
    alias.lower(): canonical
    for canonical, aliases in _TEAM_GROUPS.items()
    for alias in aliases
}
_TEAM_PATTERN = "|".join(
    sorted((re.escape(alias) for alias in _TEAM_ALIAS_TO_CANONICAL.keys()), key=len, reverse=True)
)
_TEAM_PREFIX_RE = re.compile(
    rf"(?P<team>{'|'.join(sorted((re.escape(team) for team in _NON_GIANTS_PREFIXES), key=len, reverse=True))})"
    r"(?:・|･|／|/)\s*(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー]{2,16})"
)
_STATUS_MARKERS = ("復帰", "実戦復帰", "昇格", "登録", "再登録", "抹消", "合流", "一軍", "1軍", "戦列")
_ALUMNI_MARKERS = ("元巨人", "OB", "巨人OB")
_NON_BASEBALL_MARKERS = (
    "ボクシング",
    "ラウンド",
    "リング",
    "計量",
    "KO",
    "判定",
    "王座",
    "世界戦",
    "スーパーバンタム級",
    "バンタム級",
    "フェザー級",
)
_BASEBALL_MARKERS = (
    "投手",
    "捕手",
    "内野手",
    "外野手",
    "監督",
    "コーチ",
    "先発",
    "登板",
    "打率",
    "防御率",
    "本塁打",
    "打点",
    "安打",
    "スタメン",
    "打順",
    "試合",
    "球団",
    "一軍",
    "二軍",
    "ファーム",
    "抹消",
    "登録",
    "昇格",
    "合流",
    "復帰",
)


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _clean_text(value: str) -> str:
    return _WS_RE.sub(" ", _HTML_RE.sub("", str(value or ""))).strip()


def is_generic_compound_subject(value: str) -> bool:
    normalized = _clean_text(value).strip(" ・、，,")
    if not normalized:
        return False
    normalized = re.sub(r"\s+", "", normalized)
    return normalized in _GENERIC_COMPOUND_SUBJECTS


def sanitize_forbidden_visible_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in str(text or "").split("\n"):
        line = raw_line
        stripped = line.strip()
        if stripped in _FORBIDDEN_HEADING_REPLACEMENTS:
            line = line.replace(stripped, _FORBIDDEN_HEADING_REPLACEMENTS[stripped], 1)
        elif "「" not in line and "『" not in line:
            for old, new in _FORBIDDEN_LINE_REPLACEMENTS:
                line = line.replace(old, new)
        lines.append(line)
    return "\n".join(lines)


def find_forbidden_phrase(text: str) -> dict[str, str] | None:
    normalized = _clean_text(text)
    if not normalized:
        return None
    dequoted = _QUOTE_RE.sub("", normalized)
    for label, pattern in _FORBIDDEN_PATTERNS:
        target = normalized if label.startswith(("heading_", "internal_")) else dequoted
        match = pattern.search(target)
        if match:
            return {"label": label, "phrase": match.group(0)}
    return None


def find_quote_integrity_issue(text: str) -> dict[str, str] | None:
    normalized = _clean_text(text)
    if not normalized:
        return None
    if normalized.count("「") != normalized.count("」"):
        return {"reason": "unbalanced_corner_quote", "marker": "「」"}
    if normalized.count("『") != normalized.count("』"):
        return {"reason": "unbalanced_double_quote", "marker": "『』"}
    dangling = re.search(r"[「『][^」』\n]{6,120}$", normalized)
    if dangling:
        return {"reason": "dangling_quote_tail", "marker": dangling.group(0)}
    return None


def _sentence_units(text: str) -> list[str]:
    normalized = _clean_text(text)
    if not normalized:
        return []
    normalized = re.sub(r"【[^】]+】", "\n", normalized)
    normalized = re.sub(r"(?<=[。！？!?])", "\n", normalized)
    parts = re.split(r"\n+", normalized)
    sentences: list[str] = []
    for part in parts:
        sentence = re.sub(r"\s+", "", part.strip())
        if len(sentence) < 12:
            continue
        if "みなさんの意見はコメントで" in sentence:
            continue
        sentences.append(sentence)
    return sentences


def find_duplicate_sentence(text: str, similarity_threshold: float = 0.9) -> dict[str, str] | None:
    sentences = _sentence_units(text)
    for index, left in enumerate(sentences):
        for right in sentences[index + 1 :]:
            ratio = SequenceMatcher(None, left, right).ratio()
            if ratio >= similarity_threshold:
                return {"reason": "near_duplicate_sentence", "left": left, "right": right, "ratio": f"{ratio:.3f}"}
    return None


def _canonical_team_names(text: str) -> set[str]:
    normalized = _clean_text(text)
    if not normalized:
        return set()
    hits: set[str] = set()
    for alias, canonical in _TEAM_ALIAS_TO_CANONICAL.items():
        if alias and alias in normalized.lower():
            hits.add(canonical)
    return hits


def detect_source_entity_conflict(source_title: str, source_summary: str) -> dict[str, str] | None:
    title_text = _clean_text(source_title)
    summary_text = _clean_text(source_summary)
    full_text = "\n".join(part for part in (title_text, summary_text) if part)
    if not full_text:
        return None

    team_prefix_match = _TEAM_PREFIX_RE.search(title_text or full_text)
    if team_prefix_match and any(marker in full_text for marker in _STATUS_MARKERS):
        return {
            "reason": "non_giants_team_prefix",
            "team": team_prefix_match.group("team"),
            "name": team_prefix_match.group("name"),
        }

    if any(marker in full_text for marker in _ALUMNI_MARKERS) and any(marker in full_text for marker in _NON_BASEBALL_MARKERS):
        if not any(marker in full_text for marker in _BASEBALL_MARKERS):
            return {"reason": "alumni_non_baseball_context"}
    return None


def extract_grounded_team_names(text: str) -> set[str]:
    return _canonical_team_names(text)
