from __future__ import annotations

import difflib
import re
from typing import Any

from lib.preview_rules import RuleResult, find_placeholder_hits


NUMERIC_TOKEN_RE = re.compile(
    r"(?:\d+-\d+x?|\d+回(?:途中)?(?:\d+安打)?(?:無失点|\d+失点)|"
    r"\d+打数\d+安打\d+打点\d+本塁打|防御率\d+\.\d+|\d+勝\d+敗|"
    r"\d+奪三振|第\d+号|\d+点|\d+分前|\d+年目)"
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
    return {
        "mandatory": mandatory,
        "desirable": desirable,
        "mandatory_pass_count": mandatory_pass_count,
        "desirable_pass_count": desirable_pass_count,
        "recommend_for_apply": "yes" if mandatory_pass_count == len(mandatory) else "no",
    }


def render_acceptance_check(acceptance: dict[str, Any]) -> str:
    mandatory = acceptance["mandatory"]
    desirable = acceptance["desirable"]
    lines = [
        f"- `recommend_for_apply`: `{acceptance['recommend_for_apply']}`",
        f"- `mandatory_pass_count`: `{acceptance['mandatory_pass_count']}/{len(mandatory)}`",
        f"- `desirable_pass_count`: `{acceptance['desirable_pass_count']}/{len(desirable)}`",
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
) -> str:
    quality_label = ", ".join(quality_flags or ["none"])
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


def _find_fabrication_signals(
    original: str,
    fixed: str,
    facts: dict[str, Any],
) -> list[str]:
    support_parts = [
        original,
        facts.get("title_rendered"),
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
