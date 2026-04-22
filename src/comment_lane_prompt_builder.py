"""Structured prompt contract for comment-lane drafts (ticket 067)."""

from __future__ import annotations

import json
from typing import Any, Mapping


COMMENT_INPUT_FIELDS = (
    "speaker_name",
    "speaker_role",
    "scene_type",
    "game_id",
    "opponent",
    "scoreline",
    "team_result",
    "quote_core",
    "quote_source",
    "quote_source_type",
    "target_entity",
    "emotion",
    "trust_tier",
)

COMMENT_OUTPUT_SLOTS = (
    "title",
    "fact_header",
    "lede",
    "quote_block",
    "context",
    "related",
)

RESULT_FIELDS = ("game_id", "opponent", "scoreline", "team_result")


def _normalize_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    missing: list[str] = []
    for key in COMMENT_INPUT_FIELDS:
        if key not in payload:
            missing.append(key)
            normalized[key] = None
            continue
        value = payload.get(key)
        normalized[key] = value if value is not None else None
    if missing:
        raise ValueError(f"missing required comment prompt fields: {', '.join(missing)}")
    return normalized


def build_output_slot_template() -> str:
    return json.dumps({slot: "" for slot in COMMENT_OUTPUT_SLOTS}, ensure_ascii=False, indent=2)


def build_comment_lane_prompt(payload: Mapping[str, Any]) -> str:
    normalized = _normalize_input(payload)
    input_json = json.dumps(normalized, ensure_ascii=False, indent=2)
    result_null_list = ", ".join(RESULT_FIELDS)

    prompt = [
        "あなたはヨシラバー comment lane の structured draft 生成担当です。",
        "入力 JSON にある事実だけを使い、slot 6 個をこの順で埋める。",
        "comment lane では自由作文しない。H2/H3 を付けない。slot の外へ段落を増やさない。",
        "入力 JSON に無い選手名・媒体名・試合結果・感想・背景事情を追加しない。",
        "source_ref には quote_source の名前だけを使う。Draft URL や preview URL は書かない。",
        f"{result_null_list} のどれかが null の場合、本文で試合結果・スコア・対戦相手を断定しない。",
        "",
        "input_schema:",
        json.dumps({key: "<required>" for key in COMMENT_INPUT_FIELDS}, ensure_ascii=False, indent=2),
        "",
        "output_slots:",
        build_output_slot_template(),
        "",
        "slot_rules:",
        "- title: speaker / scene / nucleus を必ず入れる。generic title 禁止。",
        "- fact_header: source_ref を先出しし、誰がどこで何を言ったかを短く置く。",
        "- lede: fact-first で 2〜4 行相当。抽象導入や引用羅列で始めない。",
        "- quote_block: quote_core のみ。入力に無い引用を足さない。",
        "- context: scene_type と target_entity の範囲だけを短く整理する。",
        "- related: downstream の再訪理由になる 1 本線だけを書く。",
        "",
        "return_format:",
        "JSON only",
        "",
        "input_json:",
        input_json,
    ]
    return "\n".join(prompt)


__all__ = [
    "COMMENT_INPUT_FIELDS",
    "COMMENT_OUTPUT_SLOTS",
    "build_comment_lane_prompt",
    "build_output_slot_template",
]
