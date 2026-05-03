from __future__ import annotations

import difflib
import re
from typing import Any

from lib.preview_phase5 import expected_headings_for_subtype, extract_title_fragments
from lib.preview_rules import RuleResult, find_placeholder_hits


NUMERIC_TOKEN_RE = re.compile(
    r"(?:\d+-\d+x?|\d+回(?:途中)?(?:\d+安打)?(?:無失点|\d+失点)|"
    r"\d+打数\d+安打\d+打点\d+本塁打|防御率\d+\.\d+|\d+勝\d+敗|"
    r"\d+奪三振|第\d+号|\d+点|\d+分前|\d+年目)"
)
PHASE5_NUMERIC_RE = re.compile(
    r"(?:\d{1,2}月\d{1,2}日|\d{1,2}:\d{2}|\d{1,2}時(?:\d{1,2}分)?|"
    r"\d+-\d+x?|\d+安打\d+本塁打|\d+安打|\d+打点|\d+本塁打|"
    r"\d+回(?:途中)?(?:\d+安打)?(?:無失点|\d+失点)|防御率\d+\.\d+|"
    r"\d+勝\d+敗|\d+奪三振|\d+番)"
)
RESULT_TOKENS = ("勝利", "敗戦", "引き分け", "サヨナラ負け")
QUOTE_RE = re.compile(r"「([^」]+)」")


def render_unified_diff(original: str, fixed: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            fixed.splitlines(),
            fromfile="original.normalized",
            tofile="preview.det",
            lineterm="",
        )
    )


def render_facts_section(facts: dict[str, Any]) -> str:
    ordered_fields = [
        ("article_subtype", facts.get("subtype_hint")),
        ("source_label", facts.get("source_label")),
        ("source_url", facts.get("source_url")),
        ("source_urls", facts.get("source_urls")),
        ("source_headline", facts.get("source_headline")),
        ("source_summary", facts.get("source_summary")),
        ("title.rendered", facts.get("title_rendered")),
        ("source_body_cue", facts.get("source_cue")),
        ("speaker_name", facts.get("speaker_name")),
        ("player_name", facts.get("player_name")),
        ("key_quote", facts.get("key_quote")),
        ("score", facts.get("score")),
        ("opponent", facts.get("opponent")),
        ("result", facts.get("result")),
        ("pitching_line", facts.get("pitching_line")),
        ("venue", facts.get("venue")),
        ("game_date", facts.get("game_date")),
        ("game_time", facts.get("game_time")),
        ("notice_type", facts.get("notice_type")),
        ("player_event", facts.get("player_event")),
        ("starter_pitcher", facts.get("starter_pitcher")),
        ("opponent_lineup_link", facts.get("opponent_lineup_link")),
        ("modified", facts.get("modified")),
        ("fetched_at", facts.get("fetched_at")),
    ]
    lines: list[str] = []
    for label, value in ordered_fields:
        lines.append(f"- `{label}`: {_format_fact_value(value)}")

    lineup_order = facts.get("lineup_order") or []
    if lineup_order:
        lines.append("- `lineup_order`:")
        lines.extend(_render_lineup_fact_lines(lineup_order))
    else:
        lines.append("- `lineup_order`: `not present in source/meta`")
    return "\n".join(lines)


def render_applied_rules(rule_results: list[RuleResult]) -> str:
    lines = []
    for result in rule_results:
        status = "applied" if result.applied else "not_applied"
        detail = f" ({result.details})" if result.details else ""
        lines.append(f"- `{result.name}`: `{status}`{detail}")
    return "\n".join(lines)


def evaluate_acceptance(
    original: str,
    fixed: str,
    facts: dict[str, Any],
    applied_rules: list[RuleResult],
    *,
    expected_subtype: str | None = None,
    interface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diff_text = render_unified_diff(original, fixed)
    placeholder_hits = find_placeholder_hits(fixed)
    fabrication_findings = _find_fabrication_signals(original, fixed, facts)
    original_len = len(original)
    fixed_len = len(fixed)
    original_sections = _count_sections(original)
    fixed_sections = _count_sections(fixed)
    coverage = _facts_coverage(fixed, facts)
    applied_count = sum(1 for rule in applied_rules if rule.applied)

    mandatory = [
        {
            "key": "no_source_meta_fabrication",
            "pass": not fabrication_findings,
            "detail": "ok" if not fabrication_findings else "; ".join(fabrication_findings),
        },
        {
            "key": "no_placeholder_residual",
            "pass": not placeholder_hits,
            "detail": "ok" if not placeholder_hits else ", ".join(placeholder_hits),
        },
        {
            "key": "rule_list_explicit",
            "pass": len(applied_rules) >= 1,
            "detail": f"rendered={len(applied_rules)}, applied={applied_count}",
        },
        {
            "key": "unified_diff_format",
            "pass": diff_text.startswith("--- original.normalized\n+++ preview.det"),
            "detail": (
                "ok"
                if diff_text.startswith("--- original.normalized\n+++ preview.det")
                else "diff header mismatch"
            ),
        },
        {
            "key": "wp_gemini_deploy_zero",
            "pass": True,
            "detail": "preview-only script; WP write 0 / Gemini call 0 / deploy 0",
        },
    ]
    desirable = [
        {
            "key": "fixed_not_longer_than_original",
            "pass": fixed_len <= original_len,
            "detail": f"{fixed_len} <= {original_len}",
        },
        {
            "key": "section_count_not_expanded",
            "pass": fixed_sections <= original_sections,
            "detail": f"{fixed_sections} <= {original_sections}",
        },
        {
            "key": "facts_coverage_ge_80pct",
            "pass": coverage >= 0.8,
            "detail": f"{coverage * 100:.1f}%",
        },
    ]
    mandatory_pass_count = sum(1 for item in mandatory if item["pass"])
    desirable_pass_count = sum(1 for item in desirable if item["pass"])
    phase5_axes = _evaluate_phase5_axes(
        original,
        fixed,
        facts,
        expected_subtype=expected_subtype,
        interface=interface,
        placeholder_hits=placeholder_hits,
    )
    phase5_pass_count = sum(1 for item in phase5_axes if item["pass"])
    recommend_for_apply = "yes" if mandatory_pass_count == len(mandatory) else "no"
    if phase5_axes and phase5_pass_count != len(phase5_axes):
        recommend_for_apply = "no"
    return {
        "mandatory": mandatory,
        "desirable": desirable,
        "phase5_axes": phase5_axes,
        "phase5_pass_count": phase5_pass_count,
        "mandatory_pass_count": mandatory_pass_count,
        "desirable_pass_count": desirable_pass_count,
        "recommend_for_apply": recommend_for_apply,
    }


def render_acceptance_check(acceptance: dict[str, Any]) -> str:
    mandatory = acceptance["mandatory"]
    desirable = acceptance["desirable"]
    phase5_axes = acceptance.get("phase5_axes") or []
    lines = [
        f"- `recommend_for_apply`: `{acceptance['recommend_for_apply']}`",
        f"- `mandatory_pass_count`: `{acceptance['mandatory_pass_count']}/{len(mandatory)}`",
        f"- `desirable_pass_count`: `{acceptance['desirable_pass_count']}/{len(desirable)}`",
        *( [f"- `phase5_pass_count`: `{acceptance['phase5_pass_count']}/{len(phase5_axes)}`"] if phase5_axes else [] ),
        "",
        "### mandatory",
    ]
    for item in mandatory:
        status = "PASS" if item["pass"] else "FAIL"
        lines.append(f"- `{item['key']}`: `{status}` ({item['detail']})")
    lines.append("")
    lines.append("### desirable")
    for item in desirable:
        status = "PASS" if item["pass"] else "FAIL"
        lines.append(f"- `{item['key']}`: `{status}` ({item['detail']})")
    if phase5_axes:
        lines.append("")
        lines.append("### phase5")
        for item in phase5_axes:
            status = "PASS" if item["pass"] else "FAIL"
            lines.append(f"- `{item['key']}`: `{status}` ({item['detail']})")
    return "\n".join(lines)


def render_sample(
    sample_id: str,
    subtype: str,
    original: str,
    fixed: str,
    facts: dict[str, Any],
    rules: list[RuleResult],
    acceptance: dict[str, Any],
    quality_flags: list[str] | None = None,
    interface: dict[str, Any] | None = None,
) -> str:
    quality_label = ", ".join(quality_flags or ["none"])
    rendered_interface = render_interface_section(interface) if interface else ""
    return "\n".join(
        [
            f"# {sample_id}",
            "",
            f"- `post_id`: `{facts.get('post_id')}`",
            f"- `backup_path`: `{facts.get('backup_path')}`",
            f"- `subtype`: `{subtype}`",
            f"- `quality_flags`: `{quality_label}`",
            "",
            "## 元本文",
            "",
            "```text",
            original,
            "```",
            "",
            "## source/meta facts",
            "",
            render_facts_section(facts),
            *(["", "## subtype-aware unlock interface", "", rendered_interface] if rendered_interface else []),
            "",
            "## 修正文候補",
            "",
            "```markdown",
            fixed,
            "```",
            "",
            "## diff",
            "",
            "```diff",
            render_unified_diff(original, fixed),
            "```",
            "",
            "## 適用 rule list",
            "",
            render_applied_rules(rules),
            "",
            "## acceptance check",
            "",
            render_acceptance_check(acceptance),
        ]
    ).strip() + "\n"


def render_interface_section(interface: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"- `unlock_title`: {_format_fact_value(interface.get('unlock_title'))}",
            f"- `unlock_subtype`: {_format_fact_value(interface.get('unlock_subtype'))}",
            f"- `unlock_reason`: {_format_fact_value(interface.get('unlock_reason'))}",
            f"- `title_strategy`: {_format_fact_value(interface.get('title_strategy'))}",
            f"- `source_url`: {_format_fact_value(interface.get('source_url'))}",
            f"- `required_fact_axes`: {_format_fact_value(interface.get('required_fact_axes'))}",
            f"- `present_fact_axes`: {_format_fact_value(interface.get('present_fact_axes'))}",
            f"- `interface_match`: {_format_fact_value('yes' if interface.get('interface_match') else 'no')}",
        ]
    )


def _format_fact_value(value: Any) -> str:
    if value is None:
        return "`not present in source/meta`"
    if isinstance(value, list):
        if not value:
            return "`not present in source/meta`"
        joined = ", ".join(f"`{item}`" for item in value)
        return joined
    return f"`{value}`"


def _render_lineup_fact_lines(lineup_order: list[dict[str, str]]) -> list[str]:
    return [f"  - `{entry['rendered']}`" for entry in lineup_order]


def _count_sections(text: str) -> int:
    return sum(
        1
        for line in text.splitlines()
        if line.startswith("【") or line.startswith("### ")
    )


def _facts_coverage(fixed: str, facts: dict[str, Any]) -> float:
    coverable = facts.get("coverable_facts") or []
    if not coverable:
        return 1.0
    hits = 0
    for item in coverable:
        if str(item["value"]) in fixed:
            hits += 1
    return hits / len(coverable)


def _evaluate_phase5_axes(
    original: str,
    fixed: str,
    facts: dict[str, Any],
    *,
    expected_subtype: str | None,
    interface: dict[str, Any] | None,
    placeholder_hits: list[str],
) -> list[dict[str, Any]]:
    if not expected_subtype or not interface:
        return []
    title = str(interface.get("unlock_title") or "").strip()
    title_subject, title_event = extract_title_fragments(title, expected_subtype)
    expected_headings = list(expected_headings_for_subtype(expected_subtype))
    actual_headings = _extract_heading_lines(fixed)
    body_contract_ok = bool(expected_headings) and actual_headings[: len(expected_headings)] == expected_headings
    if body_contract_ok:
        sections = _extract_sections(fixed)
        for heading in expected_headings:
            if not sections.get(heading):
                body_contract_ok = False
                break

    unsupported_numeric = _find_unsupported_phase5_numeric_tokens(
        fixed,
        support_parts=[
            original,
            title,
            facts.get("title_rendered"),
            facts.get("source_headline"),
            facts.get("source_summary"),
            facts.get("source_cue"),
            facts.get("score"),
            facts.get("game_date"),
            facts.get("game_time"),
            facts.get("notice_type"),
            facts.get("player_event"),
            interface.get("source_day_label"),
        ],
    )
    integrity_pass, integrity_detail = _evaluate_title_body_integrity(
        expected_subtype,
        title,
        fixed,
        facts,
        title_subject=title_subject,
        title_event=title_event,
    )
    return [
        {
            "key": "title_body_integrity",
            "pass": integrity_pass,
            "detail": integrity_detail,
        },
        {
            "key": "subtype_match",
            "pass": interface.get("unlock_subtype") == expected_subtype and bool(interface.get("interface_match")),
            "detail": str(interface.get("unlock_reason") or "unlock_reason missing"),
        },
        {
            "key": "numeric_guard",
            "pass": not unsupported_numeric,
            "detail": "ok" if not unsupported_numeric else ", ".join(unsupported_numeric),
        },
        {
            "key": "placeholder_absence",
            "pass": not placeholder_hits,
            "detail": "ok" if not placeholder_hits else ", ".join(placeholder_hits),
        },
        {
            "key": "body_contract_pass",
            "pass": body_contract_ok,
            "detail": (
                "ok"
                if body_contract_ok
                else f"expected={expected_headings}, actual={actual_headings[:len(expected_headings)]}"
            ),
        },
    ]


def _evaluate_title_body_integrity(
    expected_subtype: str,
    title: str,
    fixed: str,
    facts: dict[str, Any],
    *,
    title_subject: str,
    title_event: str,
) -> tuple[bool, str]:
    if expected_subtype == "pregame":
        opponent = str(facts.get("opponent") or "").strip()
        event_options = [str(facts.get("game_time") or "").strip(), "予告先発", "先発", "試合前情報"]
        hits = [fragment for fragment in [opponent] if fragment and fragment in fixed]
        event_hit = next((fragment for fragment in event_options if fragment and fragment in fixed), "")
        if event_hit:
            hits.append(event_hit)
        return (len(hits) >= 2, " / ".join(hits) if hits else "missing pregame opponent/event")
    if expected_subtype == "farm_lineup":
        hits = [fragment for fragment in ("二軍", "スタメン") if fragment in fixed]
        return (len(hits) == 2, " / ".join(hits) if hits else "missing farm_lineup core markers")
    title_parts = [part for part in (title_subject, title_event) if part]
    hits = [part for part in title_parts if part in fixed]
    if title_parts and len(hits) == len(title_parts):
        return True, " / ".join(hits)
    return False, f"missing title fragments: subject={title_subject or '-'} event={title_event or '-'}"


def _extract_heading_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("【") and "】" in line]


def _extract_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("【") and "】" in line:
            current_heading = line
            sections.setdefault(current_heading, [])
            continue
        if current_heading:
            sections[current_heading].append(line)
    return sections


def _find_unsupported_phase5_numeric_tokens(
    fixed: str,
    *,
    support_parts: list[Any],
) -> list[str]:
    support_tokens = {
        _normalize_phase5_numeric_token(token)
        for part in support_parts
        for token in PHASE5_NUMERIC_RE.findall(str(part or ""))
    }
    findings: list[str] = []
    for token in dict.fromkeys(PHASE5_NUMERIC_RE.findall(fixed)):
        normalized = _normalize_phase5_numeric_token(token)
        if normalized not in support_tokens:
            findings.append(token)
    return findings


def _normalize_phase5_numeric_token(token: str) -> str:
    normalized = str(token or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    normalized = normalized.replace("－", "-").replace("–", "-").replace("対", "-")
    normalized = normalized.replace(" ", "")
    match = re.fullmatch(r"(\d{1,2})時(\d{1,2})分", normalized)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
    match = re.fullmatch(r"(\d{1,2})時", normalized)
    if match:
        return f"{int(match.group(1)):02d}:00"
    return normalized


def _find_fabrication_signals(
    original: str,
    fixed: str,
    facts: dict[str, Any],
) -> list[str]:
    support_parts = [
        original,
        facts.get("title_rendered"),
        facts.get("source_headline"),
        facts.get("source_summary"),
        facts.get("source_cue"),
        facts.get("score"),
        facts.get("opponent"),
        facts.get("result"),
        facts.get("player_name"),
        facts.get("speaker_name"),
        facts.get("pitching_line"),
        facts.get("key_quote"),
        facts.get("venue"),
        facts.get("game_date"),
        facts.get("game_time"),
        facts.get("notice_type"),
        facts.get("player_event"),
        facts.get("starter_pitcher"),
        facts.get("opponent_lineup_link"),
    ]
    for entry in facts.get("lineup_order") or []:
        support_parts.extend((entry.get("player"), entry.get("rendered"), entry.get("position")))
    support_text = " ".join(str(part) for part in support_parts if part)
    findings: list[str] = []

    for token in dict.fromkeys(NUMERIC_TOKEN_RE.findall(fixed)):
        if token not in support_text:
            findings.append(f"unsupported numeric token: {token}")

    for result_token in RESULT_TOKENS:
        if result_token in fixed and result_token not in support_text:
            findings.append(f"unsupported result token: {result_token}")

    lineup_lines = {
        str(entry["rendered"]) for entry in (facts.get("lineup_order") or []) if entry.get("rendered")
    }
    for line in fixed.splitlines():
        stripped = line.strip()
        if re.match(r"^[1-9]番\s+", stripped) and stripped not in lineup_lines:
            findings.append(f"unsupported lineup line: {stripped}")

    starter_pitcher = facts.get("starter_pitcher")
    starter_line = f"- 巨人: {starter_pitcher}" if starter_pitcher else None
    if starter_line and starter_line in fixed and starter_pitcher not in original:
        findings.append(f"starter not anchored in source/meta: {starter_pitcher}")

    for field in ("speaker_name", "player_name"):
        value = facts.get(field)
        if value and value in fixed and value not in original:
            findings.append(f"{field} not anchored in source/meta: {value}")

    for quote in QUOTE_RE.findall(fixed):
        if quote not in support_text:
            findings.append(f"unsupported quote token: {quote}")
    return findings
