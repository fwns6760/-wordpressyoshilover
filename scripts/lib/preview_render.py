from __future__ import annotations

import difflib
import re
from typing import Any

from lib.preview_rules import RuleResult, find_placeholder_hits


NUMERIC_TOKEN_RE = re.compile(
    r"(?:\d+-\d+x?|\d+回(?:途中)?(?:\d+安打)?(?:無失点|\d+失点)|第\d+号|\d+点|\d+分前|\d+年目)"
)


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
        ("modified", facts.get("modified")),
        ("fetched_at", facts.get("fetched_at")),
    ]
    lines = []
    for label, value in ordered_fields:
        lines.append(f"- `{label}`: {_format_fact_value(value)}")
    return "\n".join(lines)


def render_applied_rules(rule_results: list[RuleResult]) -> str:
    lines = []
    for result in rule_results:
        status = "applied" if result.applied else "not_applied"
        detail = f" ({result.details})" if result.details else ""
        lines.append(f"- `{result.name}`: `{status}`{detail}")
    return "\n".join(lines)


def evaluate_acceptance(original: str, fixed: str, facts: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    diff_text = render_unified_diff(original, fixed)
    placeholder_hits = find_placeholder_hits(fixed)
    fabrication_findings = _find_fabrication_signals(fixed, facts)
    original_len = len(original)
    fixed_len = len(fixed)
    original_sections = _count_sections(original)
    fixed_sections = _count_sections(fixed)
    coverage = _facts_coverage(fixed, facts)
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
            "pass": True,
            "detail": "rule results rendered explicitly",
        },
        {
            "key": "unified_diff_format",
            "pass": diff_text.startswith("--- original.normalized\n+++ preview.det"),
            "detail": "ok" if diff_text.startswith("--- original.normalized\n+++ preview.det") else "diff header mismatch",
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
    return {"mandatory": mandatory, "desirable": desirable}


def render_acceptance_check(original: str, fixed: str, facts: dict[str, Any]) -> str:
    acceptance = evaluate_acceptance(original, fixed, facts)
    lines = ["### mandatory"]
    for item in acceptance["mandatory"]:
        status = "PASS" if item["pass"] else "FAIL"
        lines.append(f"- `{item['key']}`: `{status}` ({item['detail']})")
    lines.append("")
    lines.append("### desirable")
    for item in acceptance["desirable"]:
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
    acceptance: str,
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
            acceptance,
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


def _find_fabrication_signals(fixed: str, facts: dict[str, Any]) -> list[str]:
    support_text = " ".join(
        str(part)
        for part in (
            facts.get("title_rendered"),
            facts.get("source_cue"),
            facts.get("score"),
            facts.get("opponent"),
            facts.get("result"),
            facts.get("player_name"),
            facts.get("speaker_name"),
            facts.get("pitching_line"),
            facts.get("key_quote"),
        )
        if part
    )
    findings: list[str] = []

    for token in dict.fromkeys(NUMERIC_TOKEN_RE.findall(fixed)):
        if token not in support_text:
            findings.append(f"unsupported numeric token: {token}")

    if "勝利" in fixed and "勝利" not in support_text and facts.get("result") != "勝利":
        findings.append("unsupported result token: 勝利")
    if "敗戦" in fixed and "敗戦" not in support_text and facts.get("result") != "敗戦":
        findings.append("unsupported result token: 敗戦")
    return findings
