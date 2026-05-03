from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import sys
import warnings
from typing import Any

from lib.preview_rules import (
    RuleResult,
    condense_long_speculation,
    remove_empty_headings,
    remove_optional_sections,
    remove_placeholders,
)


warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)


try:
    from src import rss_fetcher, weak_title_rescue
except ImportError:  # pragma: no cover - script execution path
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.append(str(repo_root))
    from src import rss_fetcher, weak_title_rescue


QUOTE_RE = re.compile(r"「([^」]+)」")
DATE_RE = re.compile(r"(\d{1,2}月\d{1,2}日)")
TIME_RE = re.compile(r"(\d{1,2}:\d{2}|\d{1,2}時(?:\d{1,2}分)?)")
EVENT_RE = re.compile(
    r"(\d安打\d本塁打|\d安打|\d打点|\d本塁打|無失点|好投|合流|昇格|登録抹消|復帰)"
)


PHASE5_SAMPLE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "post_id": 63109,
        "category": "player_comment",
        "subtype": "player_comment",
        "generation_category": "選手情報",
        "title_strategy": "subtype_aware_rescue",
        "metadata": {
            "article_subtype": "player_comment",
            "player_name": "則本昂大",
            "role": "投手",
        },
        "fact_axes": ("player_name", "key_quote", "source_url"),
    },
    {
        "post_id": 63429,
        "category": "farm_lineup",
        "subtype": "farm_lineup",
        "generation_category": "ドラフト・育成",
        "title_strategy": "rewrite_display_title",
        "has_game": True,
        "metadata": {
            "article_subtype": "farm_lineup",
            "farm": True,
        },
        "fact_axes": ("source_url", "source_headline"),
    },
    {
        "post_id": 63331,
        "category": "pregame",
        "subtype": "pregame",
        "generation_category": "試合速報",
        "title_strategy": "rewrite_display_title",
        "title_override": "巨人DeNA戦 田中将大先発 試合前情報",
        "has_game": True,
        "metadata": {
            "article_subtype": "pregame",
            "published_at": "2026-04-24T12:25:33+09:00",
            "game_date": "2026-04-24T00:00:00+09:00",
            "game_time": "18:00",
            "opponent": "DeNA",
        },
        "fact_axes": ("game_date", "game_time", "opponent", "source_url"),
    },
    {
        "post_id": 63107,
        "category": "pregame",
        "subtype": "pregame",
        "generation_category": "試合速報",
        "title_strategy": "rewrite_display_title",
        "has_game": True,
        "metadata": {
            "article_subtype": "pregame",
            "published_at": "2026-04-21T12:13:59+09:00",
            "game_date": "2026-04-21T00:00:00+09:00",
            "game_time": "18:00",
            "opponent": "中日",
        },
        "fact_axes": ("game_date", "game_time", "opponent", "source_url"),
    },
    {
        "post_id": 63232,
        "category": "roster_notice",
        "subtype": "roster_notice",
        "generation_category": "選手情報",
        "title_strategy": "subtype_aware_rescue",
        "metadata": {
            "article_subtype": "player",
            "special_story_kind": "player_notice",
            "player_name": "石塚裕惺",
            "notice_type": "緊急昇格",
        },
        "fact_axes": ("player_name", "notice_type", "source_url"),
    },
    {
        "post_id": 63133,
        "category": "player_notice",
        "subtype": "farm_player_result",
        "generation_category": "ドラフト・育成",
        "title_strategy": "subtype_aware_rescue",
        "metadata": {
            "article_subtype": "farm_player_result",
            "player_name": "山瀬慎之助",
            "farm": True,
            "player_event": "本塁打",
        },
        "fact_axes": ("player_name", "player_event", "source_url"),
    },
    {
        "post_id": 63263,
        "category": "player_notice",
        "subtype": "farm_player_result",
        "generation_category": "ドラフト・育成",
        "title_strategy": "subtype_aware_rescue",
        "metadata": {
            "article_subtype": "farm_player_result",
            "player_name": "石川達也",
            "farm": True,
            "player_event": "無失点",
        },
        "fact_axes": ("player_name", "player_event", "source_url"),
    },
)


def canonical_category(category: str | None) -> str:
    normalized = str(category or "").strip().lower().replace("-", "_")
    aliases = {
        "manager_coach": "manager",
        "manager_comment": "manager",
        "若手選手": "player_notice",
        "young_player": "player_notice",
        "probable_starter": "pregame",
    }
    return aliases.get(normalized, normalized)


def select_phase5_samples(category: str, count: int) -> list[dict[str, Any]]:
    normalized = canonical_category(category)
    matches = [dict(item) for item in PHASE5_SAMPLE_CATALOG if item["category"] == normalized]
    if not matches:
        raise SystemExit(f"unknown phase5 category: {category}")
    if count < 1:
        raise SystemExit("--count must be >= 1")
    if count > len(matches):
        raise SystemExit(
            f"category={normalized} has only {len(matches)} phase5 samples; requested count={count}"
        )
    return matches[:count]


def build_phase5_pipeline(
    original_text: str,
    facts: dict[str, Any],
    sample: dict[str, Any],
) -> tuple[str, list[RuleResult], dict[str, Any]]:
    working = original_text
    rule_results: list[RuleResult] = []
    for rule in (remove_placeholders, remove_empty_headings):
        working, result = rule(working)
        rule_results.append(result)

    working, result = remove_optional_sections(
        working,
        allowed_sections=_allowed_sections_for_subtype(sample["subtype"]),
    )
    rule_results.append(result)

    working, result = condense_long_speculation(working)
    rule_results.append(result)

    interface = build_unlock_interface(sample, facts, original_text)
    fixed = build_preview_body(sample["subtype"], interface, facts)
    rule_results.append(
        RuleResult(
            name=f"template_align_{sample['subtype']}",
            applied=fixed.strip() != working.strip(),
            details=f"title_strategy={sample['title_strategy']}",
        )
    )
    return fixed, rule_results, interface


def build_unlock_interface(
    sample: dict[str, Any],
    facts: dict[str, Any],
    original_text: str,
) -> dict[str, Any]:
    metadata = _build_metadata(sample, facts)
    source_title = str(facts.get("source_headline") or facts.get("title_rendered") or "").strip()
    source_summary = str(
        facts.get("source_summary") or facts.get("source_cue") or source_title or original_text
    ).strip()
    source_url = str(facts.get("source_url") or "").strip()
    source_name = str(facts.get("source_label") or "").strip()
    generated_title = str(facts.get("title_rendered") or source_title or "").strip()

    title_strategy = sample["title_strategy"]
    title_result = None
    if title_strategy == "subtype_aware_rescue":
        title_result = weak_title_rescue.rescue_subtype_aware(
            gen_title=generated_title,
            source_title=source_title,
            body=source_summary,
            summary=source_summary,
            metadata=metadata,
        )
        unlock_title = title_result.title if title_result else source_title
        title_strategy_detail = title_result.strategy if title_result else "fallback_source_headline"
    elif title_strategy == "rewrite_display_title":
        unlock_title, template_key = rss_fetcher._rewrite_display_title_with_template(
            source_title,
            source_summary,
            sample["generation_category"],
            bool(sample.get("has_game", False)),
        )
        title_strategy_detail = template_key
    else:
        unlock_title = source_title or generated_title
        title_strategy_detail = "source_headline"
    if sample.get("title_override"):
        unlock_title = str(sample["title_override"]).strip()
        title_strategy_detail = "title_override"

    unlock_subtype = str(sample["subtype"]).strip()
    source_day_label = _source_day_label(facts)
    player_name = str(metadata.get("player_name") or facts.get("player_name") or "").strip()
    notice_type = str(metadata.get("notice_type") or facts.get("notice_type") or "").strip()
    player_event = str(metadata.get("player_event") or facts.get("player_event") or "").strip()
    if unlock_subtype == "farm_lineup" and source_day_label:
        unlock_title = f"巨人二軍スタメン {source_day_label}"
        title_strategy_detail = "farm_lineup_day_title"
    if unlock_subtype == "roster_notice" and player_name and notice_type:
        unlock_title = f"{player_name}が{notice_type}"
        title_strategy_detail = "notice_particle_title"
    if unlock_subtype == "farm_player_result" and player_name and player_event:
        unlock_title = f"{player_name}が{player_event}"
        title_strategy_detail = "farm_player_particle_title"
    previous_flag = os.environ.get(rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG)
    os.environ[rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG] = "1"
    unlock_reason = rss_fetcher._subtype_aware_narrow_unlock_reason(
        title=unlock_title,
        article_subtype=str(metadata.get("article_subtype") or unlock_subtype),
        source_name=source_name,
        source_url=source_url,
        source_title=source_title,
        source_body=source_summary,
        summary=source_summary,
        metadata=metadata,
        weak_reason="blacklist_phrase:結果のポイント",
    )
    if previous_flag is None:
        os.environ.pop(rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG, None)
    else:
        os.environ[rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG] = previous_flag
    expected_reason = f"subtype_aware_{unlock_subtype}"
    if unlock_subtype == "roster_notice":
        expected_reason = "subtype_aware_roster_notice"

    present_fact_axes = [
        axis
        for axis in sample.get("fact_axes", ())
        if _resolve_fact_axis(axis, facts, metadata, source_summary)
    ]
    interface_match = bool(
        unlock_title
        and source_url
        and unlock_subtype
        and unlock_reason == expected_reason
        and len(present_fact_axes) == len(sample.get("fact_axes", ()))
    )
    return {
        "unlock_title": unlock_title,
        "unlock_subtype": unlock_subtype,
        "unlock_reason": unlock_reason or "",
        "expected_reason": expected_reason,
        "source_title": source_title,
        "source_summary": source_summary,
        "source_url": source_url,
        "source_day_label": source_day_label,
        "title_strategy": title_strategy_detail,
        "required_fact_axes": list(sample.get("fact_axes", ())),
        "present_fact_axes": present_fact_axes,
        "interface_match": interface_match,
    }


def build_preview_body(
    subtype: str,
    interface: dict[str, Any],
    facts: dict[str, Any],
) -> str:
    title = str(interface.get("unlock_title") or facts.get("title_rendered") or "").strip()
    summary = str(interface.get("source_summary") or facts.get("source_cue") or title).strip()
    if subtype == "pregame":
        return rss_fetcher._build_pregame_safe_fallback(title, summary)
    if subtype == "farm_lineup":
        return rss_fetcher._build_farm_lineup_safe_fallback(title, summary)
    if subtype == "roster_notice":
        return rss_fetcher._build_notice_safe_fallback(
            title,
            summary,
            source_day_label=_source_day_label(facts),
        )
    if subtype == "player_comment":
        return _build_player_comment_preview(title, summary, facts)
    if subtype == "farm_player_result":
        return _build_farm_player_preview(title, summary, facts)
    return summary


def expected_headings_for_subtype(subtype: str) -> tuple[str, ...]:
    if subtype == "player_comment":
        return tuple(rss_fetcher.MANAGER_REQUIRED_HEADINGS)
    if subtype == "pregame":
        return tuple(rss_fetcher.GAME_REQUIRED_HEADINGS["pregame"])
    if subtype == "farm_lineup":
        return tuple(rss_fetcher.FARM_REQUIRED_HEADINGS["farm_lineup"])
    if subtype == "roster_notice":
        return tuple(rss_fetcher.NOTICE_REQUIRED_HEADINGS)
    if subtype == "farm_player_result":
        return tuple(rss_fetcher.FARM_REQUIRED_HEADINGS["farm"])
    return ()


def extract_title_fragments(title: str, subtype: str) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", str(title or "")).strip()
    quote_match = QUOTE_RE.search(cleaned)
    if quote_match and "「" in cleaned:
        subject = cleaned.split("「", 1)[0].strip(" ・、")
        return subject, quote_match.group(1).strip()
    if subtype in {"roster_notice", "farm_player_result"}:
        if "が" in cleaned:
            subject, event = cleaned.split("が", 1)
            return subject.strip(), event.strip()
        if " " in cleaned:
            subject, event = cleaned.split(" ", 1)
            return subject.strip(), event.strip()
    if subtype == "farm_lineup":
        date_match = DATE_RE.search(cleaned)
        return "二軍スタメン", date_match.group(1) if date_match else cleaned.replace("二軍スタメン", "").strip()
    if subtype == "pregame":
        parts = cleaned.split(" ", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) == 2 else cleaned
    return cleaned, ""


def _allowed_sections_for_subtype(subtype: str) -> set[str]:
    if subtype == "player_comment":
        return {
            "【ニュースの整理】",
            "【次の注目】",
        }
    if subtype == "pregame":
        return set(rss_fetcher.GAME_REQUIRED_HEADINGS["pregame"])
    if subtype == "farm_lineup":
        return set(rss_fetcher.FARM_REQUIRED_HEADINGS["farm_lineup"])
    if subtype == "roster_notice":
        return {
            "【二軍結果・活躍の要旨】",
        }
    if subtype == "farm_player_result":
        return {
            "【二軍結果・活躍の要旨】",
            "【ファームのハイライト】",
            "【二軍個別選手成績】",
            "【一軍への示唆】",
        }
    return set()


def _build_metadata(sample: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(sample.get("metadata", {}))
    defaults = {
        "published_at": facts.get("modified"),
        "game_date": facts.get("game_date"),
        "game_time": facts.get("game_time"),
        "player_name": facts.get("player_name"),
        "speaker": facts.get("speaker_name"),
        "opponent": facts.get("opponent"),
        "score": facts.get("score"),
        "notice_type": facts.get("notice_type"),
    }
    for key, value in defaults.items():
        if key not in metadata and value:
            metadata[key] = value
    if "farm" not in metadata and sample["subtype"].startswith("farm_"):
        metadata["farm"] = True
    return metadata


def _resolve_fact_axis(
    axis: str,
    facts: dict[str, Any],
    metadata: dict[str, Any],
    source_summary: str,
) -> str:
    if axis == "player_name":
        return str(metadata.get("player_name") or facts.get("player_name") or "").strip()
    if axis == "key_quote":
        return str(facts.get("key_quote") or _extract_quote(source_summary) or "").strip()
    if axis == "source_url":
        return str(facts.get("source_url") or "").strip()
    if axis == "source_headline":
        return str(facts.get("source_headline") or "").strip()
    if axis == "game_date":
        return str(metadata.get("game_date") or facts.get("game_date") or "").strip()
    if axis == "game_time":
        return str(metadata.get("game_time") or facts.get("game_time") or "").strip()
    if axis == "opponent":
        return str(metadata.get("opponent") or facts.get("opponent") or "").strip()
    if axis == "notice_type":
        return str(metadata.get("notice_type") or facts.get("notice_type") or "").strip()
    if axis == "player_event":
        return str(metadata.get("player_event") or facts.get("player_event") or "").strip()
    return ""


def _build_player_comment_preview(title: str, summary: str, facts: dict[str, Any]) -> str:
    headings = rss_fetcher.MANAGER_REQUIRED_HEADINGS
    player_name = str(facts.get("player_name") or title.split("「", 1)[0]).strip(" ・、")
    quote = _extract_quote(title) or str(facts.get("key_quote") or "").strip()
    sentences = _summary_sentences(summary)

    lines = [headings[0], f"{player_name}が「{quote}」と話した。"]
    if sentences:
        lines.append(_ensure_period(sentences[0]))

    lines.extend(
        [
            headings[1],
            f"コメントの核は「{quote}」という言葉です。",
            _ensure_period(sentences[1]) if len(sentences) >= 2 else "source/meta にある発言の芯だけを残す。",
            headings[2],
            _ensure_period(sentences[2]) if len(sentences) >= 3 else "発言が出た文脈は source/meta にある範囲だけで確認する。",
            headings[3],
            "次の試合前後の評価は補完せず、発言内容そのものを短く整理する。",
        ]
    )
    return "\n".join(lines)


def _build_farm_player_preview(title: str, summary: str, facts: dict[str, Any]) -> str:
    headings = rss_fetcher.FARM_REQUIRED_HEADINGS["farm"]
    player_name, event = extract_title_fragments(title, "farm_player_result")
    event = event or str(facts.get("player_event") or _extract_event(summary) or "").strip()
    sentences = _summary_sentences(summary)

    lines = [headings[0], f"{player_name}に{event}の動きがあった。"]
    if sentences:
        lines.append(_ensure_period(sentences[0]))

    lines.extend(
        [
            headings[1],
            _ensure_period(sentences[1]) if len(sentences) >= 2 else "ファームで確認できた事実だけを先に残す。",
            headings[2],
            f"{player_name}に関する数字や出来事は source/meta にある範囲だけで整理する。",
            headings[3],
            "若手・二軍メモとして、次の評価につながる事実だけを短く残す。",
        ]
    )
    return "\n".join(lines)


def _summary_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    sentences: list[str] = []
    for raw_sentence in cleaned.split("。"):
        sentence = re.sub(r"^【[^】]+】", "", raw_sentence).strip(" 。")
        if not sentence or sentence.startswith(("💬", "📌", "📰")):
            continue
        sentences.append(sentence)
    return sentences


def _extract_quote(text: str) -> str:
    match = QUOTE_RE.search(str(text or ""))
    return match.group(1).strip() if match else ""


def _extract_event(text: str) -> str:
    match = EVENT_RE.search(str(text or ""))
    return match.group(1).strip() if match else ""


def _ensure_period(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith("。") else f"{cleaned}。"


def _source_day_label(facts: dict[str, Any]) -> str:
    modified = str(facts.get("modified") or "").strip()
    if modified:
        try:
            parsed = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            return f"{parsed.month}月{parsed.day}日"
        except ValueError:
            pass
    game_date = str(facts.get("game_date") or "").strip()
    match = DATE_RE.search(game_date)
    return match.group(1) if match else ""
