from __future__ import annotations

from dataclasses import dataclass
import html
import re

from src.article_quality_guards import detect_source_entity_conflict


ENTITY_MISMATCH_REPAIR_ENV_FLAG = "ENABLE_ENTITY_MISMATCH_REPAIR"

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SENTENCE_BREAK_RE = re.compile(r"(?<=[。！？!?])")
_BODY_HEADING_RE = re.compile(r"<h[23][^>]*>【[^】]+】</h[23]>", re.IGNORECASE)
_BODY_END_MARKERS = (
    re.compile(r"<h3[^>]*>💬\s*ファンの声（Xより）</h3>", re.IGNORECASE),
    re.compile(r'<div class="yoshilover-related-posts"', re.IGNORECASE),
    re.compile(r"📰\s*参照元:", re.IGNORECASE),
)
_CTA_BLOCK_RE = re.compile(
    r'<!-- wp:buttons .*?href="#respond".*?<!-- /wp:buttons -->\s*',
    re.IGNORECASE | re.DOTALL,
)
_NOTICE_RECOVERY_MARKERS = (
    "【公示の要旨】",
    "【対象選手の基本情報】",
    "【公示の背景】",
    "【故障・復帰の要旨】",
    "【故障の詳細】",
    "【リハビリ状況・復帰見通し】",
    "【チームへの影響と今後の注目点】",
    "読売ジャイアンツ所属",
    "ジャイアンツ所属",
    "一軍登録",
    "登録抹消",
)
_ROLE_RE = re.compile(r"(投手|捕手|内野手|外野手|選手)")


@dataclass(frozen=True)
class EntityMismatchRepairResult:
    applied: bool
    repairable: bool
    title: str
    body_text: str
    body_html: str
    source_team: str
    player_name: str
    reason: str
    stop_reason: str
    removed_strings: tuple[str, ...]
    repair_flags: tuple[str, ...]


def _clean_text(value: str) -> str:
    text = html.unescape(_HTML_RE.sub("", str(value or "")))
    return _WS_RE.sub(" ", text).strip()


def _trim_title(value: str, max_chars: int = 42) -> str:
    clean = _clean_text(value).strip("。 ")
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip(" ・、。") + "…"


def _sentence_units(*parts: str) -> list[str]:
    text = "\n".join(_clean_text(part) for part in parts if _clean_text(part))
    if not text:
        return []
    normalized = text.replace("　", " ")
    segments = []
    for chunk in _SENTENCE_BREAK_RE.split(normalized):
        sentence = chunk.strip(" ・、。\n")
        if sentence and sentence not in segments:
            segments.append(sentence)
    return segments


def _role_from_source(*parts: str) -> str:
    text = "\n".join(_clean_text(part) for part in parts if part)
    match = _ROLE_RE.search(text)
    return match.group(1) if match else "選手"


def _dynamic_replacements(team: str, name: str, role: str) -> tuple[tuple[str, str], ...]:
    current_label = f"元読売ジャイアンツ・現{team}の{name}"
    current_sentence = f"{name}は元読売ジャイアンツ・現{team}の{role}です。"
    return (
        (f"読売ジャイアンツ所属の{name}", current_label),
        (f"ジャイアンツ所属の{name}", current_label),
        (f"巨人所属の{name}", current_label),
        (f"読売ジャイアンツの{name}", current_label),
        (f"ジャイアンツの{name}", current_label),
        (f"巨人の{name}", current_label),
        (f"{name}は読売ジャイアンツ所属である。", current_sentence),
        (f"{name}は読売ジャイアンツ所属です。", current_sentence),
        (f"{name}は読売ジャイアンツの{role}です。", current_sentence),
        (f"{name}は巨人所属である。", current_sentence),
        (f"{name}は巨人所属です。", current_sentence),
        (f"{name}は巨人の{role}です。", current_sentence),
        ("【昇格・復帰 関連情報】", f"【{name} 近況】"),
        ("昇格・復帰 関連情報", f"{name} 近況"),
        ("巨人復帰後", f"現{team}でのプレー"),
        ("巨人復帰", f"{team}でのプレー"),
    )


def _apply_replacements(value: str, replacements: tuple[tuple[str, str], ...]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    text = str(value or "")
    removed_strings: list[str] = []
    repair_flags: list[str] = []
    for before, after in replacements:
        if before in text:
            text = text.replace(before, after)
            removed_strings.append(before)
            repair_flags.append(f"replace:{before}->{after}")
    return text, tuple(dict.fromkeys(removed_strings)), tuple(dict.fromkeys(repair_flags))


def _needs_source_rebuild(body_text: str, source_title: str, source_summary: str) -> bool:
    source_text = "\n".join(_sentence_units(source_title, source_summary))
    if any(marker in body_text for marker in _NOTICE_RECOVERY_MARKERS):
        if not any(marker in source_text for marker in _NOTICE_RECOVERY_MARKERS):
            return True
    if "読売ジャイアンツ" in body_text and "読売ジャイアンツ" not in source_text:
        return True
    return False


def _build_source_grounded_body(*, source_title: str, source_summary: str, team: str, name: str, role: str) -> str:
    facts = _sentence_units(source_title, source_summary)
    if not facts:
        return ""
    primary = facts[0]
    secondary = facts[1] if len(facts) >= 2 else primary
    tertiary = ""
    for fact in facts[2:]:
        if fact not in {primary, secondary}:
            tertiary = fact
            break

    lines = [
        "【ニュースの整理】",
        f"{primary}。",
    ]
    if secondary and secondary != primary:
        lines.append(f"{secondary}。")
    lines.extend(
        [
            f"【{name} 近況】",
            f"元読売ジャイアンツ・現{team}の{name}に関する話題です。",
        ]
    )
    if tertiary:
        lines.append(f"{tertiary}。")
    else:
        lines.append(f"{name}の現状は、元記事で確認できる範囲をそのまま追いたい内容です。")
    lines.extend(
        [
            "【次の注目】",
            f"現{team}で次にどんな内容を見せるかを見たいところです。",
            "みなさんの意見はコメントで教えてください！",
        ]
    )
    return "\n".join(lines)


def _render_body_html(body_text: str) -> str:
    lines = [line.strip() for line in str(body_text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    blocks: list[str] = []
    heading_index = 0
    for line in lines:
        escaped = html.escape(line)
        if line.startswith("【") and "】" in line:
            level = 2 if heading_index == 0 else 3
            blocks.append(
                f'<!-- wp:heading {{"level":{level}}} -->\n'
                f"<h{level}>{escaped}</h{level}>\n"
                f"<!-- /wp:heading -->\n\n"
            )
            heading_index += 1
            continue
        blocks.append(
            "<!-- wp:paragraph -->\n"
            f"<p>{escaped}</p>\n"
            "<!-- /wp:paragraph -->\n\n"
            '<!-- wp:spacer {"height":"8px"} -->\n'
            '<div style="height:8px" aria-hidden="true" class="wp-block-spacer"></div>\n'
            "<!-- /wp:spacer -->\n\n"
        )
    return "".join(blocks)


def _replace_body_region(content_html: str, body_html: str) -> str:
    original = str(content_html or "")
    if not original or not body_html:
        return original
    start_match = _BODY_HEADING_RE.search(original)
    if not start_match:
        return original
    end_positions = [len(original)]
    for marker in _BODY_END_MARKERS:
        match = marker.search(original, start_match.end())
        if match:
            end_positions.append(match.start())
    end_index = min(end_positions)
    preserved_cta = "".join(_CTA_BLOCK_RE.findall(original[start_match.start() : end_index]))
    return "".join(
        [
            original[: start_match.start()],
            body_html,
            preserved_cta,
            original[end_index:],
        ]
    )


def repair_entity_mismatch(
    *,
    current_title: str,
    body_text: str,
    body_html: str,
    source_title: str,
    source_summary: str,
    max_title_chars: int = 42,
) -> EntityMismatchRepairResult:
    conflict = detect_source_entity_conflict(source_title, source_summary)
    if not conflict:
        return EntityMismatchRepairResult(
            applied=False,
            repairable=False,
            title=current_title,
            body_text=body_text,
            body_html=body_html,
            source_team="",
            player_name="",
            reason="no_conflict",
            stop_reason="entity_mismatch_not_detected",
            removed_strings=(),
            repair_flags=(),
        )
    if conflict.get("reason") != "non_giants_team_prefix":
        return EntityMismatchRepairResult(
            applied=False,
            repairable=False,
            title=current_title,
            body_text=body_text,
            body_html=body_html,
            source_team=str(conflict.get("team") or ""),
            player_name=str(conflict.get("name") or ""),
            reason=str(conflict.get("reason") or ""),
            stop_reason=f"entity_mismatch_unrepairable:{conflict.get('reason') or 'unknown'}",
            removed_strings=(),
            repair_flags=(),
        )

    team = str(conflict.get("team") or "").strip()
    name = str(conflict.get("name") or "").strip()
    if not team or not name:
        return EntityMismatchRepairResult(
            applied=False,
            repairable=False,
            title=current_title,
            body_text=body_text,
            body_html=body_html,
            source_team=team,
            player_name=name,
            reason="non_giants_team_prefix",
            stop_reason="entity_mismatch_missing_team_or_name",
            removed_strings=(),
            repair_flags=(),
        )

    role = _role_from_source(source_title, source_summary)
    repaired_title = _trim_title(source_title or current_title, max_chars=max_title_chars)
    replacements = _dynamic_replacements(team, name, role)
    repaired_body_text, removed_text, repair_flags = _apply_replacements(body_text, replacements)
    repaired_body_html, removed_html, html_flags = _apply_replacements(body_html, replacements)
    removed_strings = tuple(dict.fromkeys((*removed_text, *removed_html)))
    merged_flags = tuple(dict.fromkeys((*repair_flags, *html_flags)))

    if _needs_source_rebuild(repaired_body_text, source_title, source_summary):
        rebuilt_body = _build_source_grounded_body(
            source_title=source_title,
            source_summary=source_summary,
            team=team,
            name=name,
            role=role,
        )
        if not rebuilt_body:
            return EntityMismatchRepairResult(
                applied=False,
                repairable=False,
                title=current_title,
                body_text=body_text,
                body_html=body_html,
                source_team=team,
                player_name=name,
                reason="non_giants_team_prefix",
                stop_reason="entity_mismatch_rebuild_failed",
                removed_strings=removed_strings,
                repair_flags=merged_flags,
            )
        repaired_body_text = rebuilt_body
        repaired_body_html = _replace_body_region(body_html, _render_body_html(rebuilt_body))
        if not repaired_body_html:
            repaired_body_html = body_html
        merged_flags = tuple(dict.fromkeys((*merged_flags, "entity_mismatch_body_rebuilt")))

    applied = (
        repaired_title != str(current_title or "").strip()
        or repaired_body_text != str(body_text or "")
        or repaired_body_html != str(body_html or "")
    )
    return EntityMismatchRepairResult(
        applied=applied,
        repairable=True,
        title=repaired_title,
        body_text=repaired_body_text,
        body_html=repaired_body_html,
        source_team=team,
        player_name=name,
        reason="non_giants_team_prefix",
        stop_reason="",
        removed_strings=removed_strings,
        repair_flags=merged_flags,
    )
