from __future__ import annotations

import json
import os
import re


POSTGAME_STRICT_FEATURE_FLAG_ENV = "POSTGAME_STRICT_TEMPLATE"

POSTGAME_STRICT_REQUIRED_FIELDS = ("game_date", "opponent", "giants_score", "opponent_score", "result")
KEY_EVENT_TYPES = frozenset({"pitching", "batting", "fielding", "comment", "other"})
RESULT_VALID_VALUES = frozenset({"win", "loss", "draw", "unknown"})
RESULT_JP_MAP = {"win": "勝利", "loss": "敗戦", "draw": "引き分け", "unknown": "結果未確定"}

POSTGAME_STRICT_PROMPT = """\
あなたは事実抽出の助手です。以下の source から postgame の facts を抽出し、JSON のみを返してください。
本文を書いてはいけません。JSON 以外の文字列を 1 文字も含めないでください。

[制約]
- source に明記されていない値は null にする
- 推測・補完・「明日の焦点」「次戦への見方」等の編集解釈表現禁止
- 選手名・スコア・日付・対戦相手は source 内の表記そのまま
- 次戦情報は事実のみ(日付/相手/球場/開始時刻)、解釈・展望・「見方」禁止
- key_events は source からの実引用、各 event は type で分類:
  - pitching: 投球関連(被安打、失点、投球回、奪三振 等)
  - batting: 打撃関連(本塁打、適時打、得点絡み 等)
  - fielding: 守備関連(失策、好守 等)
  - comment: 監督・コーチ・選手コメント
  - other: 上記以外の事実
- evidence は source 内の文(各 fact の根拠)

[SCHEMA]
{
  "game_date": "YYYY-MM-DD or null",
  "opponent": "string or null",
  "giants_score": "number or null",
  "opponent_score": "number or null",
  "result": "win|loss|draw|unknown",
  "starter_name": "string or null",
  "starter_innings": "number|string or null",
  "starter_hits": "number or null",
  "starter_runs": "number or null",
  "key_events": [
    {
      "type": "pitching|batting|fielding|comment|other",
      "text": "source にある事実のみ",
      "evidence": "根拠となる source 断片"
    }
  ],
  "manager_comment": "string or null",
  "next_game_info": {
    "date": "string or null",
    "opponent": "string or null",
    "venue": "string or null",
    "start_time": "string or null"
  },
  "confidence": "high|medium|low",
  "evidence_text": ["string", ...]
}

[SOURCE]
{source_text}

[OUTPUT]
JSON only:
"""


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RESULT_KEYWORD_RE = re.compile(r"(決勝打|勝ち越し|サヨナラ|本塁打|ホームラン|逆転打|適時打|タイムリー|犠飛|押し出し|先制|同点|好守|好投|セーブ)")
_INTERPRETATION_BAN_RE = re.compile(r"(見方|展望|焦点|明日の焦点|次戦への見方)")


def is_strict_enabled() -> bool:
    return os.environ.get(POSTGAME_STRICT_FEATURE_FLAG_ENV, "0").strip() == "1"


def _unwrap_markdown_json(text: str) -> str:
    stripped = text.strip()
    for pattern in (r"```json\s*\r?\n(?P<body>.*)\r?\n```", r"```\s*\r?\n(?P<body>.*)\r?\n```"):
        match = re.fullmatch(pattern, stripped, flags=re.DOTALL)
        if match:
            return match.group("body").strip()
    return stripped


def parse_postgame_strict_json(raw: str) -> tuple[dict | None, str]:
    if not isinstance(raw, str):
        return None, "response_not_string"

    stripped = raw.strip()
    stripped = _unwrap_markdown_json(stripped)
    if not stripped:
        return None, "empty_response"
    if not stripped.startswith("{"):
        return None, "non_json_wrapper"

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}"

    if not isinstance(payload, dict):
        return None, "payload_not_object"
    return payload, ""


def validate_postgame_strict_payload(payload: dict, source_text: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["schema_violation:payload"]

    normalized_source = _normalize_text(source_text)
    next_game_info = payload.get("next_game_info")
    if next_game_info is None:
        next_game_info = {}

    schema_checks = (
        ("game_date", _is_optional_date_string(payload.get("game_date"))),
        ("opponent", _is_optional_string(payload.get("opponent"))),
        ("giants_score", _is_optional_number(payload.get("giants_score"))),
        ("opponent_score", _is_optional_number(payload.get("opponent_score"))),
        ("starter_name", _is_optional_string(payload.get("starter_name"))),
        ("starter_innings", _is_optional_number_or_string(payload.get("starter_innings"))),
        ("starter_hits", _is_optional_number(payload.get("starter_hits"))),
        ("starter_runs", _is_optional_number(payload.get("starter_runs"))),
        ("manager_comment", _is_optional_string(payload.get("manager_comment"))),
        ("confidence", isinstance(payload.get("confidence"), str) and payload.get("confidence") in {"high", "medium", "low"}),
        ("evidence_text", _is_string_list(payload.get("evidence_text"))),
        ("next_game_info", isinstance(next_game_info, dict)),
    )
    for field, ok in schema_checks:
        if not ok:
            errors.append(f"schema_violation:{field}")

    if errors:
        return False, _dedupe(errors)

    result = str(payload.get("result") or "").strip()
    if result not in RESULT_VALID_VALUES:
        errors.append("invalid_result")

    for field in POSTGAME_STRICT_REQUIRED_FIELDS:
        value = payload.get(field)
        if field == "result":
            if not value:
                errors.append(f"required_facts_missing:{field}")
        elif _is_missing_required_value(value):
            errors.append(f"required_facts_missing:{field}")

    key_events = payload.get("key_events")
    if not isinstance(key_events, list):
        errors.append("schema_violation:key_events")
        key_events = []

    for index, event in enumerate(key_events):
        if not isinstance(event, dict):
            errors.append(f"schema_violation:key_events[{index}]")
            continue
        event_type = str(event.get("type") or "").strip()
        text = event.get("text")
        evidence = event.get("evidence")
        if event_type not in KEY_EVENT_TYPES:
            errors.append(f"invalid_event_type:{index}")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"schema_violation:key_events[{index}].text")
        if not isinstance(evidence, str) or not evidence.strip():
            errors.append(f"schema_violation:key_events[{index}].evidence")
            continue
        if normalized_source and _normalize_text(evidence) not in normalized_source:
            errors.append(f"evidence_not_in_source:key_events[{index}]")

    evidence_text = payload.get("evidence_text") or []
    for index, item in enumerate(evidence_text):
        if normalized_source and _normalize_text(item) not in normalized_source:
            errors.append(f"evidence_not_in_source:evidence_text[{index}]")

    if str(payload.get("confidence") or "").strip() == "low":
        errors.append("low_confidence_review")

    next_game_checks = (
        ("date", _is_optional_string(next_game_info.get("date"))),
        ("opponent", _is_optional_string(next_game_info.get("opponent"))),
        ("venue", _is_optional_string(next_game_info.get("venue"))),
        ("start_time", _is_optional_string(next_game_info.get("start_time"))),
    )
    for field, ok in next_game_checks:
        if not ok:
            errors.append(f"schema_violation:next_game_info.{field}")

    return not errors, _dedupe(errors)


def has_sufficient_for_render(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    for field in POSTGAME_STRICT_REQUIRED_FIELDS:
        value = payload.get(field)
        if field == "result":
            if str(value or "").strip() not in RESULT_VALID_VALUES:
                return False
            continue
        if _is_missing_required_value(value):
            return False

    key_events = payload.get("key_events") or []
    if not isinstance(key_events, list):
        return False

    has_pitching = bool(_text_value(payload.get("starter_name")) and payload.get("starter_innings") not in (None, ""))
    has_batting = any(isinstance(event, dict) and str(event.get("type") or "").strip() == "batting" for event in key_events)
    has_comment = bool(_text_value(payload.get("manager_comment"))) or any(
        isinstance(event, dict) and str(event.get("type") or "").strip() == "comment"
        for event in key_events
    )
    next_game_info = payload.get("next_game_info") or {}
    has_next_game = bool(_text_value(next_game_info.get("date")) and _text_value(next_game_info.get("opponent")))
    return has_pitching or has_batting or has_comment or has_next_game


def render_postgame_strict_body(payload: dict) -> str:
    used_event_keys: set[tuple[str, str]] = set()
    sections = [
        _render_game_result_block(payload),
        _render_highlight_block(payload, used_event_keys),
        _render_player_performance_block(payload, used_event_keys),
        _render_game_flow_block(payload, used_event_keys),
    ]
    rendered = "\n\n".join(section for section in sections if section.strip())
    if _INTERPRETATION_BAN_RE.search(rendered):
        raise ValueError("renderer_banned_word")
    return rendered


def _render_game_result_block(payload: dict) -> str:
    game_date = _format_game_date_jp(str(payload.get("game_date") or "").strip())
    opponent = _format_opponent_label(payload.get("opponent"))
    result = RESULT_JP_MAP.get(str(payload.get("result") or "").strip(), RESULT_JP_MAP["unknown"])
    score = f"{_format_number(payload.get('giants_score'))}-{_format_number(payload.get('opponent_score'))}"
    return "\n".join(
        [
            "【試合結果】",
            f"{game_date}の{opponent}は、巨人が{score}で{result}でした。",
        ]
    )


def _render_highlight_block(payload: dict, used_event_keys: set[tuple[str, str]]) -> str:
    key_events = _coerce_events(payload.get("key_events"))
    selected = _select_turning_point_events(key_events, used_event_keys)
    lines = ["【ハイライト】"]
    for event in selected[:3]:
        used_event_keys.add(_event_key(event))
        lines.append(f"・{_text_value(event.get('text'))}")
    if len(lines) == 1:
        lines.append("・source にある試合の分岐点を整理しました。")
    return "\n".join(lines)


def _render_player_performance_block(payload: dict, used_event_keys: set[tuple[str, str]]) -> str:
    key_events = _coerce_events(payload.get("key_events"))
    lines = ["【選手成績】"]

    if _text_value(payload.get("starter_name")) and payload.get("starter_innings") not in (None, ""):
        starter_line = f"先発の{_text_value(payload.get('starter_name'))}は{_format_number(payload.get('starter_innings'))}回"
        if payload.get("starter_runs") is not None:
            starter_line += f"{_format_number(payload.get('starter_runs'))}失点"
        starter_line += "でした。"
        lines.append("投手:")
        lines.append(f"・{starter_line}")
        for event in _take_unused_events(key_events, used_event_keys, event_type="pitching", limit=3):
            used_event_keys.add(_event_key(event))
            lines.append(f"・{_text_value(event.get('text'))}")

    batting_events = _take_unused_events(key_events, used_event_keys, event_type="batting", limit=5)
    if batting_events:
        lines.append("打線:")
        for event in batting_events:
            used_event_keys.add(_event_key(event))
            lines.append(f"・{_text_value(event.get('text'))}")

    if len(lines) == 1:
        lines.extend(
            [
                "打線:",
                "・source にある選手成績だけを整理しました。",
            ]
        )
    return "\n".join(lines)


def _render_game_flow_block(payload: dict, used_event_keys: set[tuple[str, str]]) -> str:
    key_events = _coerce_events(payload.get("key_events"))
    lines = ["【試合展開】"]

    manager_comment = _text_value(payload.get("manager_comment"))
    comment_events = _take_unused_events(key_events, used_event_keys, event_type="comment", limit=2)
    if manager_comment or comment_events:
        lines.append("コメント:")
        if manager_comment:
            lines.append(f"・{manager_comment}")
        for event in comment_events:
            used_event_keys.add(_event_key(event))
            event_text = _text_value(event.get("text"))
            if event_text and event_text != manager_comment:
                lines.append(f"・{event_text}")

    next_game_info = payload.get("next_game_info") or {}
    next_game_lines = _render_next_game_lines(next_game_info)
    if next_game_lines:
        lines.append("次戦情報:")
        lines.extend(next_game_lines)

    remainder_events = _take_unused_events(key_events, used_event_keys, event_type="fielding", limit=2)
    remainder_events.extend(_take_unused_events(key_events, used_event_keys, event_type="other", limit=max(0, 2 - len(remainder_events))))
    if remainder_events:
        lines.append("試合展開メモ:")
        for event in remainder_events:
            used_event_keys.add(_event_key(event))
            lines.append(f"・{_text_value(event.get('text'))}")

    lines.append("更新があれば見たいところです。")
    return "\n".join(lines)


def _render_next_game_lines(next_game_info: dict) -> list[str]:
    lines: list[str] = []
    field_map = (
        ("date", "日付"),
        ("opponent", "相手"),
        ("venue", "球場"),
        ("start_time", "開始時刻"),
    )
    for key, label in field_map:
        value = _text_value(next_game_info.get(key))
        if value:
            lines.append(f"・{label}: {value}")
    return lines


def _select_turning_point_events(events: list[dict], used_event_keys: set[tuple[str, str]]) -> list[dict]:
    unused = [event for event in events if _event_key(event) not in used_event_keys]
    selected: list[dict] = []

    for event_type in ("other", "fielding"):
        for event in unused:
            if str(event.get("type") or "").strip() != event_type:
                continue
            if _event_key(event) in {_event_key(item) for item in selected}:
                continue
            selected.append(event)
            if len(selected) >= 3:
                return selected

    if selected:
        return selected

    decisive = [
        event
        for event in unused
        if _RESULT_KEYWORD_RE.search(_text_value(event.get("text")))
        and str(event.get("type") or "").strip() in {"batting", "pitching", "fielding", "other"}
    ]
    if decisive:
        return [decisive[0]]

    for event_type in ("batting", "pitching", "fielding"):
        for event in unused:
            if str(event.get("type") or "").strip() == event_type:
                return [event]
    return selected


def _take_unused_events(
    events: list[dict],
    used_event_keys: set[tuple[str, str]],
    *,
    event_type: str,
    limit: int,
) -> list[dict]:
    selected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        key = _event_key(event)
        if key in used_event_keys or key in seen:
            continue
        if str(event.get("type") or "").strip() != event_type:
            continue
        selected.append(event)
        seen.add(key)
        if len(selected) >= limit:
            break
    return selected


def _coerce_events(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [event for event in value if isinstance(event, dict)]


def _event_key(event: dict) -> tuple[str, str]:
    return (_normalize_text(event.get("text")), _normalize_text(event.get("evidence")))


def _format_game_date_jp(value: str) -> str:
    if not _DATE_RE.fullmatch(value or ""):
        return value or "日付未確認"
    year, month, day = value.split("-")
    return f"{int(year)}年{int(month)}月{int(day)}日"


def _format_opponent_label(value: object) -> str:
    opponent = _text_value(value)
    if not opponent:
        return "相手未確認"
    return opponent if opponent.endswith("戦") else f"{opponent}戦"


def _format_number(value: object) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value).strip()


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _text_value(value: object) -> str:
    return str(value or "").strip()


def _is_optional_string(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_optional_date_string(value: object) -> bool:
    return value is None or (isinstance(value, str) and bool(_DATE_RE.fullmatch(value.strip())))


def _is_optional_number(value: object) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))


def _is_optional_number_or_string(value: object) -> bool:
    return value is None or _is_optional_number(value) or isinstance(value, str)


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_missing_required_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
