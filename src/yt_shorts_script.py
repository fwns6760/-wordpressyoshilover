"""Script and number-guard helpers for YouTube Shorts generation."""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.yt_shorts_topic import ShortsTopic


NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:\d+\.\d+|\.\d+|\d+)")


@dataclass(frozen=True)
class ScriptCaption:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class ShortsScript:
    title: str
    description: str
    narration: str
    captions: tuple[ScriptCaption, ...]
    allowed_numbers: tuple[str, ...]


def _normalize_number(token: str) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    if raw.startswith("."):
        return raw
    if "." in raw:
        left, right = raw.split(".", 1)
        left = str(int(left or "0"))
        return f".{right}" if left == "0" else f"{left}.{right}"
    try:
        return str(int(raw))
    except ValueError:
        return raw


def extract_number_tokens(text: str) -> tuple[str, ...]:
    tokens = []
    for match in NUMBER_RE.finditer(str(text or "")):
        normalized = _normalize_number(match.group(0))
        if normalized:
            tokens.append(normalized)
    return tuple(tokens)


def allowed_numbers_for_topic(topic: ShortsTopic) -> tuple[str, ...]:
    source_text = " ".join(
        [
            topic.label,
            topic.value,
            topic.note,
            topic.as_of,
            str(topic.raw_item.get("label") or ""),
            str(topic.raw_item.get("value") or ""),
            str(topic.raw_item.get("note") or ""),
        ]
    )
    return tuple(dict.fromkeys(extract_number_tokens(source_text)))


def verify_number_guard(text: str, allowed_numbers: tuple[str, ...]) -> tuple[bool, tuple[str, ...]]:
    allowed = set(allowed_numbers)
    leaked = tuple(token for token in extract_number_tokens(text) if token not in allowed)
    return (not leaked, leaked)


def assert_number_guard(text: str, allowed_numbers: tuple[str, ...]) -> None:
    ok, leaked = verify_number_guard(text, allowed_numbers)
    if not ok:
        raise ValueError(f"yt_shorts number guard failed: leaked={list(leaked)}")


def build_script(topic: ShortsTopic) -> ShortsScript:
    """Build a deterministic Japanese narration script.

    Phase 1 intentionally avoids asking an LLM to invent facts.  The only
    numeric strings in the script must come from ``topic.value`` / ``topic.note``
    / ``topic.as_of``; ``assert_number_guard`` enforces that contract.
    """

    allowed = allowed_numbers_for_topic(topic)
    note_line = f"補足すると、{topic.note}。" if topic.note else "今の巨人で見逃せない数字です。"
    narration_parts = [
        f"{topic.hook}。",
        "この数字、ただの好調ではなく、試合の見え方を変える材料です。",
        note_line,
        f"{topic.player}を見る時は、結果だけでなく、この流れまでセットで追いたい。",
        "詳しいデータはヨシラバーの注目データで確認できます。",
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)

    title = topic.title
    description = (
        f"{topic.hook}。\n"
        "巨人の注目データを、ヨシラバーのデータページからショート動画化。\n"
        f"詳しいデータ: {topic.source_url}\n\n"
        "音声: VOICEVOX 青山龍星"
    )
    assert_number_guard(title + "\n" + description, allowed)

    captions = (
        ScriptCaption(0.0, 3.0, topic.hook),
        ScriptCaption(3.0, 17.0, f"{topic.label} {topic.value}"),
        ScriptCaption(17.0, 31.0, topic.note or "今の巨人で見逃せない数字"),
        ScriptCaption(31.0, 45.0, "結果だけでなく、流れまで見る"),
        ScriptCaption(45.0, 55.0, "詳細はヨシラバーで"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    return ShortsScript(
        title=title,
        description=description,
        narration=narration,
        captions=captions,
        allowed_numbers=allowed,
    )


__all__ = [
    "ScriptCaption",
    "ShortsScript",
    "allowed_numbers_for_topic",
    "assert_number_guard",
    "build_script",
    "extract_number_tokens",
    "verify_number_guard",
]
