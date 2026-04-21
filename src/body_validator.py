from __future__ import annotations

import re

try:
    from source_attribution_validator import validate_source_attribution
except ImportError:  # pragma: no cover - package import for tests
    from src.source_attribution_validator import validate_source_attribution


BODY_CONTRACTS: dict[str, tuple[str, ...]] = {
    "live_update": (
        "【いま起きていること】",
        "【流れが動いた場面】",
        "【次にどこを見るか】",
    ),
    "postgame": (
        "【試合結果】",
        "【ハイライト】",
        "【選手成績】",
        "【試合展開】",
    ),
    "pregame": (
        "【変更情報の要旨】",
        "【具体的な変更内容】",
        "【この変更が意味すること】",
    ),
    "farm": (
        "【二軍結果・活躍の要旨】",
        "【ファームのハイライト】",
        "【二軍個別選手成績】",
        "【一軍への示唆】",
    ),
    "fact_notice": (
        "【訂正の対象】",
        "【訂正内容】",
        "【訂正元】",
        "【お詫び / ファン視点】",
    ),
}

SOURCE_BLOCK_MARKERS = (
    'class="yoshilover-article-source"',
    "記事元を読む",
    "📰 ",
)

HARD_FAIL_AXES = {
    "source_block_missing",
    "source_attribution_ambiguous",
    "postgame_score_missing",
    "postgame_win_loss_missing",
    "postgame_decisive_event_missing",
}

POSTGAME_RESULT_HEADING = "【試合結果】"
POSTGAME_HIGHLIGHT_HEADING = "【ハイライト】"
POSTGAME_SCORE_RE = re.compile(r"(?:\d{1,2}\s*[－\-–]\s*\d{1,2})|(?:\d{1,2}\s*対\s*\d{1,2})")
POSTGAME_WIN_LOSS_RE = re.compile(
    r"(勝利|敗戦|引き分け|引分け|勝った|競り勝った|制した|敗れた|敗れ|白星|黒星|ドロー)"
)
POSTGAME_OPPONENT_RE = re.compile(
    r"(阪神|中日|ヤクルト|広島|DeNA|ＤｅＮＡ|横浜|日本ハム|ソフトバンク|楽天|ロッテ|西武|オリックス|相手)"
)
POSTGAME_DATE_RE = re.compile(
    r"((?:\d{4}年)?\d{1,2}月\d{1,2}日)|(\d{4}[/-]\d{1,2}[/-]\d{1,2})|(\d{1,2}/\d{1,2})"
)
POSTGAME_DECISIVE_EVENT_RE = re.compile(
    r"(決勝打|勝ち越し|サヨナラ|本塁打|ホームラン|逆転打|適時打|タイムリー|犠飛|押し出し|先制|同点|好守|好投|セーブ)"
)
POSTGAME_COMMENT_SLOT_RE = re.compile(
    r"(コメントで教えてください|意見はコメントで|コメント欄で教えてください|感想・コメントをお願いします)"
)
POSTGAME_ABSTRACT_LEAD_PREFIXES = (
    "激闘だった",
    "激闘となった",
    "悔しい敗戦だった",
    "悔しい敗戦となった",
    "惜しい敗戦だった",
    "惜しい敗戦となった",
    "白熱した一戦だった",
    "白熱した一戦となった",
    "熱戦だった",
    "熱戦となった",
    "劇的な勝利だった",
    "劇的な勝利となった",
    "劇的な敗戦だった",
    "劇的な敗戦となった",
    "見応えのある試合だった",
    "見応えのある試合となった",
)


def is_supported_subtype(article_subtype: str) -> bool:
    return article_subtype in BODY_CONTRACTS


def expected_block_order(article_subtype: str) -> tuple[str, ...]:
    return BODY_CONTRACTS.get(article_subtype, ())


def _extract_headings(text: str) -> list[str]:
    headings: list[str] = []
    seen: set[str] = set()
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not (line.startswith("【") and "】" in line):
            continue
        if line in seen:
            continue
        seen.add(line)
        headings.append(line)
    return headings


def _has_source_block(rendered_html: str) -> bool:
    return any(marker in (rendered_html or "") for marker in SOURCE_BLOCK_MARKERS)


def _extract_blocks(text: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("【") and "】" in line:
            if current_heading:
                blocks.append((current_heading, current_lines))
            current_heading = line
            current_lines = []
            continue
        if current_heading:
            current_lines.append(line)
    if current_heading:
        blocks.append((current_heading, current_lines))
    return blocks


def _first_sentence(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    if not text:
        return ""
    match = re.search(r".*?[。！？!?](?:\s|$)", text)
    if match:
        return match.group(0).strip()
    return text.strip()


def _looks_like_abstract_postgame_lead(sentence: str) -> bool:
    trimmed = sentence.strip()
    return any(trimmed.startswith(prefix) for prefix in POSTGAME_ABSTRACT_LEAD_PREFIXES)


def _validate_postgame_fact_kernel(body_text: str) -> list[str]:
    block_map: dict[str, list[str]] = {}
    for heading, lines in _extract_blocks(body_text):
        block_map.setdefault(heading, lines)

    result_lines = block_map.get(POSTGAME_RESULT_HEADING, [])
    highlight_lines = block_map.get(POSTGAME_HIGHLIGHT_HEADING, [])
    if not result_lines:
        return []

    fail_axes: list[str] = []
    result_text = "\n".join(result_lines)
    highlight_text = "\n".join(highlight_lines)
    first_sentence = _first_sentence(result_lines)

    if _looks_like_abstract_postgame_lead(first_sentence):
        fail_axes.append("postgame_abstract_lead")
    if POSTGAME_COMMENT_SLOT_RE.search(result_text) or POSTGAME_COMMENT_SLOT_RE.search(highlight_text):
        fail_axes.append("postgame_comment_slot_before_fact_kernel")
    if not POSTGAME_SCORE_RE.search(result_text):
        fail_axes.append("postgame_score_missing")
    if not POSTGAME_WIN_LOSS_RE.search(result_text):
        fail_axes.append("postgame_win_loss_missing")
    if not POSTGAME_OPPONENT_RE.search(result_text):
        fail_axes.append("postgame_opponent_missing")
    if not POSTGAME_DATE_RE.search(result_text):
        fail_axes.append("postgame_date_missing")
    if not POSTGAME_DECISIVE_EVENT_RE.search(highlight_text):
        fail_axes.append("postgame_decisive_event_missing")
    return fail_axes


def validate_body_candidate(
    body_text: str,
    article_subtype: str,
    *,
    rendered_html: str | None = None,
    source_context: dict[str, object] | None = None,
) -> dict[str, object]:
    expected = list(expected_block_order(article_subtype))
    if not expected:
        return {
            "ok": True,
            "action": "accept",
            "fail_axes": [],
            "expected_first_block": "",
            "actual_first_block": "",
            "expected_block_order": [],
            "actual_block_order": [],
            "missing_required_blocks": [],
            "has_source_block": True,
            "source_attribution_required": False,
            "source_attribution_ok": True,
            "source_attribution_fail_axis": "",
            "primary_source_kind": "",
            "has_t1_web_source": False,
            "required_sources": [],
            "missing_required_sources": [],
            "stop_reason": "",
        }

    actual_headings = _extract_headings(body_text)
    actual_first_block = actual_headings[0] if actual_headings else ""
    missing_required_blocks = [heading for heading in expected if heading not in actual_headings]
    fail_axes: list[str] = []

    if actual_first_block != expected[0]:
        fail_axes.append("first_block_mismatch")
    if missing_required_blocks:
        fail_axes.append("required_block_missing")

    present_positions = [actual_headings.index(heading) for heading in expected if heading in actual_headings]
    if len(present_positions) >= 2 and present_positions != sorted(present_positions):
        fail_axes.append("block_order_mismatch")

    has_source_block = True
    attribution_validation = {
        "required": False,
        "ok": True,
        "fail_axis": "",
        "primary_source_kind": "",
        "has_t1_web_source": False,
        "required_sources": [],
        "missing_required_sources": [],
    }
    if rendered_html is not None:
        has_source_block = _has_source_block(rendered_html)
        if not has_source_block:
            fail_axes.append("source_block_missing")
        else:
            attribution_validation = validate_source_attribution(
                article_subtype,
                rendered_html,
                source_context,
            )
            attribution_fail_axis = str(attribution_validation.get("fail_axis") or "")
            if attribution_fail_axis:
                fail_axes.append(attribution_fail_axis)

    if article_subtype == "postgame":
        fail_axes.extend(_validate_postgame_fact_kernel(body_text))

    stop_reason = ""
    action = "accept"
    hard_fail_axes = [axis for axis in fail_axes if axis in HARD_FAIL_AXES]
    if hard_fail_axes:
        action = "fail"
        stop_reason = hard_fail_axes[0]
    elif fail_axes:
        action = "reroll"
        stop_reason = fail_axes[0]

    return {
        "ok": not fail_axes,
        "action": action,
        "fail_axes": fail_axes,
        "expected_first_block": expected[0],
        "actual_first_block": actual_first_block,
        "expected_block_order": expected,
        "actual_block_order": actual_headings,
        "missing_required_blocks": missing_required_blocks,
        "has_source_block": has_source_block,
        "source_attribution_required": bool(attribution_validation.get("required", False)),
        "source_attribution_ok": bool(attribution_validation.get("ok", True)),
        "source_attribution_fail_axis": str(attribution_validation.get("fail_axis") or ""),
        "primary_source_kind": str(attribution_validation.get("primary_source_kind") or ""),
        "has_t1_web_source": bool(attribution_validation.get("has_t1_web_source", False)),
        "required_sources": list(attribution_validation.get("required_sources") or []),
        "missing_required_sources": list(attribution_validation.get("missing_required_sources") or []),
        "stop_reason": stop_reason,
    }
