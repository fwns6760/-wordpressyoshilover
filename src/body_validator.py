from __future__ import annotations

import re

try:
    from source_attribution_validator import validate_source_attribution
except ImportError:  # pragma: no cover - package import for tests
    from src.source_attribution_validator import validate_source_attribution

try:
    from fact_conflict_guard import (
        GAME_RESULT_CONTEXT_SUBTYPES,
        TITLE_BODY_MISMATCH_SUBTYPES,
        detect_game_result_conflict,
        detect_no_game_but_result,
        detect_title_body_entity_mismatch,
    )
except ImportError:  # pragma: no cover - package import for tests
    from src.fact_conflict_guard import (
        GAME_RESULT_CONTEXT_SUBTYPES,
        TITLE_BODY_MISMATCH_SUBTYPES,
        detect_game_result_conflict,
        detect_no_game_but_result,
        detect_title_body_entity_mismatch,
    )


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
    "GAME_RESULT_CONFLICT",
    "NO_GAME_BUT_RESULT",
    "TITLE_BODY_ENTITY_MISMATCH",
    "source_block_missing",
    "source_attribution_ambiguous",
    "farm_result_player_unverified",
    "farm_result_numeric_fabrication",
    "farm_lineup_lineup_missing",
    "postgame_score_missing",
    "postgame_win_loss_missing",
    "postgame_decisive_event_missing",
    "postgame_first_team_player_unverified",
    "postgame_first_team_score_fabrication",
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
_FARM_MARKER_RE = re.compile(r"(二軍|三軍|ファーム|farm|Farm|FARM)")
_FARM_POSITIVE_MARKER_RE = re.compile(r"(二軍|三軍|ファーム|farm|Farm|FARM)")
_LINEUP_MARKER_RE = re.compile(r"(1番|2番|3番|4番|5番|先発|スタメン)")
_SCORE_TOKEN_RE = re.compile(r"\d+\s*(?:[－\-–]|対)\s*\d+")
_NAME_TOKEN_RE = re.compile(r"[一-龥々ァ-ヴーA-Za-z]{2,10}")
_FIRST_TEAM_POSTGAME_NAME_KEYWORDS = ("決勝打", "先発", "好投", "本塁打")
_GENERIC_NAME_EXCLUSIONS = frozenset(
    {
        "試合結果",
        "ハイライト",
        "選手成績",
        "試合展開",
        "巨人",
        "一軍",
        "二軍",
        "三軍",
        "ファーム",
        "相手",
        "先発",
        "好投",
        "本塁打",
        "決勝打",
        "勝利",
        "敗戦",
        "引分け",
        "引き分け",
        "終盤",
        "流れ",
        "継投",
        "投手",
        "打線",
    }
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
RESULT_NOTICE_CONTEXT_MARKERS = (
    "試合結果",
    "結果のポイント",
    "試合終了",
    "勝敗",
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


def _source_ref_texts(source_context: dict[str, object] | None) -> tuple[str, ...]:
    if not source_context:
        return ()
    values: list[str] = []
    for key in ("source_title", "summary", "source_summary", "description", "title"):
        value = str(source_context.get(key) or "").strip()
        if value:
            values.append(value)
    return tuple(values)


def _normalize_score_token(token: str) -> str:
    return re.sub(r"\s+", "", token or "").replace("－", "-").replace("–", "-")


def _is_probable_name_token(token: str) -> bool:
    candidate = str(token or "").strip()
    if not candidate or not _NAME_TOKEN_RE.fullmatch(candidate):
        return False
    return candidate not in _GENERIC_NAME_EXCLUSIONS


def _is_first_team_postgame(title: str, body_text: str) -> bool:
    blob = f"{title}\n{body_text}"
    return not bool(_FARM_MARKER_RE.search(blob))


def _validate_first_team_postgame_anchor(
    title: str,
    body_text: str,
    source_context: dict[str, object] | None,
) -> list[str]:
    fail_axes: list[str] = []
    if not _is_first_team_postgame(title, body_text):
        return fail_axes

    source_context = source_context or {}
    source_parts = list(_source_ref_texts(source_context))
    for key in ("scoreline", "opponent"):
        value = str(source_context.get(key) or "").strip()
        if value:
            source_parts.append(value)
    raw_entity_tokens = source_context.get("entity_tokens")
    if isinstance(raw_entity_tokens, str):
        token = raw_entity_tokens.strip()
        if token:
            source_parts.append(token)
    elif isinstance(raw_entity_tokens, (list, tuple, set, frozenset)):
        for item in raw_entity_tokens:
            token = str(item or "").strip()
            if token:
                source_parts.append(token)

    source_blob = " ".join(part for part in source_parts if part)
    if not source_blob.strip():
        return fail_axes

    source_scores = {_normalize_score_token(match.group(0)) for match in _SCORE_TOKEN_RE.finditer(source_blob)}
    body_scores = {_normalize_score_token(match.group(0)) for match in _SCORE_TOKEN_RE.finditer(body_text)}
    if body_scores and not body_scores.issubset(source_scores):
        fail_axes.append("postgame_first_team_score_fabrication")

    source_names = {
        token
        for token in _NAME_TOKEN_RE.findall(source_blob)
        if _is_probable_name_token(token)
    }
    body_names = {
        token
        for token in _NAME_TOKEN_RE.findall(body_text)
        if _is_probable_name_token(token)
    }

    suspect_names = {
        name
        for name in body_names
        if not any(name in source_name or source_name in name for source_name in source_names)
    }
    for name in sorted(suspect_names, key=len, reverse=True):
        for match in re.finditer(re.escape(name), body_text):
            window = body_text[max(0, match.start() - 20):match.end() + 20]
            if any(keyword in window for keyword in _FIRST_TEAM_POSTGAME_NAME_KEYWORDS):
                fail_axes.append("postgame_first_team_player_unverified")
                return fail_axes
    return fail_axes


def _is_farm_result_article(title: str, body_text: str, subtype: str) -> bool:
    if str(subtype or "").strip().lower() != "farm_result":
        return False
    blob = f"{title}\n{body_text}"
    return bool(_FARM_POSITIVE_MARKER_RE.search(blob))


def _is_farm_lineup_article(title: str, body_text: str, subtype: str) -> bool:
    if str(subtype or "").strip().lower() != "farm_lineup":
        return False
    blob = f"{title}\n{body_text}"
    return bool(_FARM_POSITIVE_MARKER_RE.search(blob))


def _validate_farm_result_anchor(
    title: str,
    body_text: str,
    source_context: dict[str, object] | None,
) -> list[str]:
    fail_axes: list[str] = []
    if not _is_farm_result_article(title, body_text, "farm_result"):
        return fail_axes

    source_context = source_context or {}
    source_parts = list(_source_ref_texts(source_context))
    for key in ("scoreline", "opponent"):
        value = str(source_context.get(key) or "").strip()
        if value:
            source_parts.append(value)
    raw_entity_tokens = source_context.get("entity_tokens")
    if isinstance(raw_entity_tokens, str):
        token = raw_entity_tokens.strip()
        if token:
            source_parts.append(token)
    elif isinstance(raw_entity_tokens, (list, tuple, set, frozenset)):
        for item in raw_entity_tokens:
            token = str(item or "").strip()
            if token:
                source_parts.append(token)

    source_blob = " ".join(part for part in source_parts if part)
    body_fact_text = "\n".join(
        line
        for _, lines in _extract_blocks(body_text)
        for line in lines
    ) or body_text
    body_numbers = set(re.findall(r"\d+", body_fact_text))
    source_numbers = set(re.findall(r"\d+", source_blob))
    if body_numbers and not body_numbers.issubset(source_numbers):
        fail_axes.append("farm_result_numeric_fabrication")

    def _is_probable_farm_name(token: str) -> bool:
        candidate = str(token or "").strip()
        if not _is_probable_name_token(candidate):
            return False
        if "昇格" in candidate:
            return False
        return candidate not in {"候補", "注目", "示唆"}

    source_names = {
        token
        for token in _NAME_TOKEN_RE.findall(source_blob)
        if _is_probable_farm_name(token)
    }
    body_names = {
        token
        for token in _NAME_TOKEN_RE.findall(body_fact_text)
        if _is_probable_farm_name(token)
    }

    suspect_names = {
        name
        for name in body_names
        if not any(name in source_name or source_name in name for source_name in source_names)
    }
    for name in sorted(suspect_names, key=len, reverse=True):
        for match in re.finditer(re.escape(name), body_fact_text):
            window = body_fact_text[max(0, match.start() - 20):match.end() + 20]
            if any(keyword in window for keyword in ("好投", "本塁打", "決勝", "昇格")):
                fail_axes.append("farm_result_player_unverified")
                return fail_axes
    return fail_axes


def _validate_farm_lineup_anchor(
    title: str,
    body_text: str,
    source_context: dict[str, object] | None,
) -> list[str]:
    del source_context
    fail_axes: list[str] = []
    if not _is_farm_lineup_article(title, body_text, "farm_lineup"):
        return fail_axes
    if not _LINEUP_MARKER_RE.search(body_text):
        fail_axes.append("farm_lineup_lineup_missing")
    return fail_axes


def _guard_entity_tokens(title: str, source_context: dict[str, object] | None) -> tuple[str, ...]:
    if not source_context:
        return ()

    tokens: list[str] = []
    for key in ("opponent", "scoreline"):
        value = str(source_context.get(key) or "").strip()
        if value:
            tokens.append(value)

    raw_entity_tokens = source_context.get("entity_tokens")
    if isinstance(raw_entity_tokens, str):
        token = raw_entity_tokens.strip()
        if token:
            tokens.append(token)
    elif isinstance(raw_entity_tokens, (list, tuple, set, frozenset)):
        for item in raw_entity_tokens:
            token = str(item or "").strip()
            if token:
                tokens.append(token)

    derived_text = "\n".join(part for part in (title, *_source_ref_texts(source_context)) if part)
    score_match = POSTGAME_SCORE_RE.search(derived_text)
    if score_match:
        tokens.append(score_match.group(0))
    opponent_match = POSTGAME_OPPONENT_RE.search(derived_text)
    if opponent_match:
        tokens.append(opponent_match.group(1))

    deduped: list[str] = []
    for token in tokens:
        if token in deduped:
            continue
        deduped.append(token)
    return tuple(deduped)


def _is_result_notice_context(title: str, body_text: str, source_context: dict[str, object] | None) -> bool:
    combined = "\n".join(part for part in (title, body_text, *_source_ref_texts(source_context)) if part)
    if not combined:
        return False
    if POSTGAME_SCORE_RE.search(combined):
        return True
    return any(marker in combined for marker in RESULT_NOTICE_CONTEXT_MARKERS)


def _fact_conflict_payload(
    *,
    title: str,
    body_text: str,
    source_context: dict[str, object] | None,
    entity_tokens: tuple[str, ...],
) -> dict[str, object]:
    source_context = source_context or {}
    return {
        "title": title,
        "body_text": body_text,
        "game_id": str(source_context.get("game_id") or "").strip(),
        "scoreline": str(source_context.get("scoreline") or "").strip(),
        "team_result": str(source_context.get("team_result") or "").strip(),
        "opponent": str(source_context.get("opponent") or "").strip(),
        "required_tokens": entity_tokens,
    }


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
    title = str((source_context or {}).get("title") or "").strip()
    expected = list(expected_block_order(article_subtype))
    if not expected:
        fail_axes: list[str] = []
        if article_subtype == "farm_result":
            fail_axes.extend(_validate_farm_result_anchor(title, body_text, source_context))
        elif article_subtype == "farm_lineup":
            fail_axes.extend(_validate_farm_lineup_anchor(title, body_text, source_context))
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
            "stop_reason": stop_reason,
        }

    actual_headings = _extract_headings(body_text)
    actual_first_block = actual_headings[0] if actual_headings else ""
    missing_required_blocks = [heading for heading in expected if heading not in actual_headings]
    fail_axes: list[str] = []
    entity_tokens = _guard_entity_tokens(title, source_context)
    has_fact_conflict_context = bool(
        title
        or entity_tokens
        or any(
            str((source_context or {}).get(key) or "").strip()
            for key in ("source_title", "summary", "source_summary", "game_id", "scoreline", "team_result", "opponent")
        )
    )
    fact_conflict_payload = _fact_conflict_payload(
        title=title,
        body_text=body_text,
        source_context=source_context,
        entity_tokens=entity_tokens,
    )

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

    if has_fact_conflict_context:
        apply_game_result_conflict_guard = article_subtype in GAME_RESULT_CONTEXT_SUBTYPES or (
            article_subtype == "fact_notice" and _is_result_notice_context(title, body_text, source_context)
        )
        if apply_game_result_conflict_guard and detect_no_game_but_result(fact_conflict_payload, source_context):
            fail_axes.append("NO_GAME_BUT_RESULT")
        if apply_game_result_conflict_guard and detect_game_result_conflict(fact_conflict_payload, source_context):
            fail_axes.append("GAME_RESULT_CONFLICT")
        if article_subtype in TITLE_BODY_MISMATCH_SUBTYPES and detect_title_body_entity_mismatch(title, fact_conflict_payload):
            fail_axes.append("TITLE_BODY_ENTITY_MISMATCH")

    if article_subtype == "postgame":
        fail_axes.extend(_validate_postgame_fact_kernel(body_text))
        fail_axes.extend(_validate_first_team_postgame_anchor(title, body_text, source_context))
    elif article_subtype == "farm_result":
        fail_axes.extend(_validate_farm_result_anchor(title, body_text, source_context))
    elif article_subtype == "farm_lineup":
        fail_axes.extend(_validate_farm_lineup_anchor(title, body_text, source_context))

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
