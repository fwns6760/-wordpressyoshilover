from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


PLACEHOLDER_PATTERNS = (
    r"結果確認中",
    r"スコア\s*:?\s*-",
    r"相手\s*:?\s*相手",
    r"(?<![一-龯ぁ-んァ-ヶー])選手(?![一-龯ぁ-んァ-ヶー])",
    r"(?<![一-龯ぁ-んァ-ヶー])投手(?![一-龯ぁ-んァ-ヶー])",
)
HEADING_RE = re.compile(r"^(?:【.+】|[📌📊👀💬].+|### .+)$")
OPTIONAL_SECTION_HEADINGS = {
    "📌 関連ポスト",
    "📊 今日の試合結果",
    "👀 勝負の分岐点",
    "💬 この試合、どう見る？",
    "💬 勝負の分岐点は？",
    "💬 ファンの声（Xより）",
    "💬 今日のMVPは？",
    "💬 このニュース、どう見る？",
    "💬 先に予想を書く？",
    "💬 みんなの本音は？",
    "💬 この発言、どう見る？",
    "💬 次はどう動く？",
    "💬 率直にどう思う？",
    "【関連記事】",
    "【一軍への示唆】",
    "【ファンの関心ポイント】",
}
SPECULATION_MARKERS = (
    "可能性",
    "注目です",
    "見たいところ",
    "どうつながる",
    "良い影響",
    "今後",
    "全体像が見えやすくなります",
    "材料になります",
    "温度感",
    "受け止め方が分かれています",
)


@dataclass(frozen=True)
class RuleResult:
    name: str
    applied: bool
    details: str = ""


def find_placeholder_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, text):
            hits.append(pattern)
    return hits


def remove_placeholders(text: str) -> tuple[str, RuleResult]:
    original = text
    lines = text.splitlines()
    cleaned_lines: list[str] = []
    removed_labels: list[str] = []
    skip_next_blank = False

    for index, line in enumerate(lines):
        working = line
        if re.fullmatch(r"(結果|スコア|相手|決め手)", working):
            next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if next_line in {"結果確認中", "-", "相手"}:
                removed_labels.append(working)
                skip_next_blank = True
                continue
        if skip_next_blank and working.strip() in {"結果確認中", "-", "相手"}:
            removed_labels.append(working.strip())
            skip_next_blank = False
            continue
        skip_next_blank = False

        if "結果確認中" in working:
            working = working.replace("結果確認中", "").strip()
            removed_labels.append("結果確認中")
        if re.search(r"スコア\s*:?\s*-", working):
            working = re.sub(r"スコア\s*:?\s*-", "", working).strip()
            removed_labels.append("スコア=-")
        if re.search(r"相手\s*:?\s*相手", working):
            working = re.sub(r"相手\s*:?\s*相手", "", working).strip()
            removed_labels.append("相手=相手")

        replacements = (
            (r"先発の\s*投手は", "先発は"),
            (r"先発\s*投手は", "先発は"),
            (r"に\s*選手の", "に"),
            (r"に\s*選手が", "に"),
            (r"は\s*選手が", "は"),
            (r"放った\s*選手(?:㊗️)?", "放った"),
            (r"\s*選手㊗️", ""),
        )
        for pattern, replacement in replacements:
            updated = re.sub(pattern, replacement, working)
            if updated != working:
                working = updated
                removed_labels.append(pattern)

        working = re.sub(r"\s+", " ", working).strip()
        if working:
            cleaned_lines.append(working)

    cleaned = "\n".join(cleaned_lines).strip()
    result = RuleResult(
        name="remove_placeholders",
        applied=cleaned != original,
        details=", ".join(dict.fromkeys(removed_labels)) if removed_labels else "",
    )
    return cleaned, result


def remove_empty_headings(text: str) -> tuple[str, RuleResult]:
    lines = text.splitlines()
    keep: list[str] = []
    removed: list[str] = []
    line_count = len(lines)
    index = 0
    while index < line_count:
        line = lines[index]
        if HEADING_RE.match(line):
            next_non_empty = None
            lookahead = index + 1
            while lookahead < line_count:
                if lines[lookahead].strip():
                    next_non_empty = lines[lookahead]
                    break
                lookahead += 1
            if next_non_empty is None or HEADING_RE.match(next_non_empty):
                removed.append(line)
                index += 1
                continue
        keep.append(line)
        index += 1
    cleaned = "\n".join(keep).strip()
    return cleaned, RuleResult(
        name="remove_empty_headings",
        applied=bool(removed),
        details=", ".join(removed),
    )


def remove_optional_sections(
    text: str,
    allowed_sections: set[str] | None = None,
) -> tuple[str, RuleResult]:
    allowed = allowed_sections or set()
    lines = text.splitlines()
    kept: list[str] = []
    removed: list[str] = []
    skipping = False

    for line in lines:
        if HEADING_RE.match(line):
            skipping = False
            if line in OPTIONAL_SECTION_HEADINGS and line not in allowed:
                removed.append(line)
                skipping = True
                continue
        if skipping:
            continue
        kept.append(line)

    cleaned = "\n".join(kept).strip()
    return cleaned, RuleResult(
        name="remove_optional_sections",
        applied=bool(removed),
        details=", ".join(removed),
    )


def condense_long_speculation(text: str) -> tuple[str, RuleResult]:
    kept: list[str] = []
    removed: list[str] = []
    for line in text.splitlines():
        if len(line) >= 45 and any(marker in line for marker in SPECULATION_MARKERS):
            removed.append(line)
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    return cleaned, RuleResult(
        name="condense_long_speculation",
        applied=bool(removed),
        details=f"removed={len(removed)}" if removed else "",
    )


def template_align_postgame(text: str, facts: dict[str, Any]) -> tuple[str, RuleResult]:
    lines = ["### 試合メモ"]
    lines.extend(_postgame_bullets(facts))
    fixed = "\n".join(lines)
    return fixed, RuleResult(
        name="template_align_postgame",
        applied=fixed.strip() != text.strip(),
        details=f"subtype={facts.get('subtype_hint') or 'unknown'}",
    )


def template_align_farm_result(text: str, facts: dict[str, Any]) -> tuple[str, RuleResult]:
    lines = ["### 二軍メモ"]
    lines.extend(_farm_result_bullets(facts))
    fixed = "\n".join(lines)
    return fixed, RuleResult(
        name="template_align_farm_result",
        applied=fixed.strip() != text.strip(),
        details=f"subtype={facts.get('subtype_hint') or 'unknown'}",
    )


def template_align_manager(text: str, facts: dict[str, Any]) -> tuple[str, RuleResult]:
    lines = ["### 監督コメントメモ"]
    speaker = facts.get("speaker_name")
    player = facts.get("player_name")
    quote = facts.get("key_quote")
    if speaker and player and quote:
        lines.append(f"- {speaker}が{player}に「{quote}」と語った一問一答。")
        lines.append(f"- 主題は先制V二塁打を放った{player}への言及。")
    else:
        cue = facts.get("source_cue")
        if cue:
            lines.append(f"- {cue}")
        else:
            lines.append("- 参照元の主題だけを短く残し、source/meta にない補足は入れない。")
    fixed = "\n".join(lines)
    return fixed, RuleResult(
        name="template_align_manager",
        applied=fixed.strip() != text.strip(),
        details=f"subtype={facts.get('subtype_hint') or 'manager'}",
    )


def apply_preview_pipeline(
    original_text: str,
    facts: dict[str, Any],
    subtype: str,
) -> tuple[str, list[RuleResult]]:
    working = original_text
    rule_results: list[RuleResult] = []
    for rule in (remove_placeholders, remove_empty_headings):
        working, result = rule(working)
        rule_results.append(result)

    allowed_sections = _allowed_sections_for_subtype(subtype)
    working, result = remove_optional_sections(working, allowed_sections=allowed_sections)
    rule_results.append(result)

    working, result = condense_long_speculation(working)
    rule_results.append(result)

    if subtype == "postgame":
        working, result = template_align_postgame(working, facts)
    elif subtype == "farm_result":
        working, result = template_align_farm_result(working, facts)
    else:
        working, result = template_align_manager(working, facts)
    rule_results.append(result)
    return working, rule_results


def _allowed_sections_for_subtype(subtype: str) -> set[str]:
    if subtype == "postgame":
        return {"【試合結果】", "【ハイライト】", "【選手成績】", "【試合展開】"}
    if subtype == "farm_result":
        return {"【二軍結果・活躍の要旨】", "【二軍個別選手成績】"}
    if subtype == "manager":
        return {"【話題の要旨】", "【発信内容の要約】", "【文脈と背景】"}
    return set()


def _postgame_bullets(facts: dict[str, Any]) -> list[str]:
    bullets: list[str] = []
    summary = _build_score_summary(facts, label="巨人")
    if summary:
        bullets.append(summary)

    pitching_line = facts.get("pitching_line")
    if pitching_line:
        bullets.append(f"- 先発は{pitching_line}。")

    extra_sentences = _sentence_bullets(facts, skip_contains={pitching_line} if pitching_line else set())
    bullets.extend(extra_sentences[:2])

    if not facts.get("player_name") and "選手" in (facts.get("source_cue") or ""):
        bullets.append("- 選手名は source/meta にないため補完しない。")
    if not bullets:
        bullets.append("- source/meta から確認できる要点だけを残す。")
    return _dedupe_bullets(bullets)


def _farm_result_bullets(facts: dict[str, Any]) -> list[str]:
    bullets: list[str] = []
    summary = _build_score_summary(facts, label="巨人二軍")
    if summary:
        bullets.append(summary)

    pitching_line = facts.get("pitching_line")
    if pitching_line:
        bullets.append(f"- 先発は{pitching_line}。")

    extra_sentences = _sentence_bullets(facts, skip_contains={pitching_line} if pitching_line else set())
    bullets.extend(extra_sentences[:2])

    if not facts.get("player_name") and "選手" in (facts.get("source_cue") or ""):
        bullets.append("- 選手名は source/meta にないため補完しない。")
    if not bullets:
        bullets.append("- 試合結果や選手成績は source/meta にある範囲だけを残す。")
    return _dedupe_bullets(bullets)


def _build_score_summary(facts: dict[str, Any], label: str) -> str | None:
    score = facts.get("score")
    opponent = facts.get("opponent")
    result = facts.get("result")
    if score and opponent and result:
        return f"- {label}は{opponent}戦で{score}、{result}。"
    if score and opponent:
        return f"- {label}は{opponent}戦で{score}。"
    if result and opponent:
        return f"- {label}は{opponent}戦で{result}。"
    return None


def _sentence_bullets(
    facts: dict[str, Any],
    skip_contains: set[str],
) -> list[str]:
    bullets: list[str] = []
    seen = set()
    for sentence in facts.get("supporting_sentences") or []:
        if not sentence:
            continue
        if any(fragment and fragment in sentence for fragment in skip_contains):
            continue
        if sentence in seen:
            continue
        seen.add(sentence)
        bullets.append(f"- {sentence}")
    return bullets


def _dedupe_bullets(bullets: list[str]) -> list[str]:
    deduped: list[str] = []
    seen = set()
    for bullet in bullets:
        key = bullet.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(bullet)
    return deduped
