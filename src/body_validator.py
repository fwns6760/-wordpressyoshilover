from __future__ import annotations


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


def validate_body_candidate(
    body_text: str,
    article_subtype: str,
    *,
    rendered_html: str | None = None,
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
    if rendered_html is not None:
        has_source_block = _has_source_block(rendered_html)
        if not has_source_block:
            fail_axes.append("source_block_missing")

    stop_reason = ""
    action = "accept"
    if "source_block_missing" in fail_axes:
        action = "fail"
        stop_reason = "source_block_missing"
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
        "stop_reason": stop_reason,
    }
