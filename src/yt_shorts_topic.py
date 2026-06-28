"""YouTube Shorts topic selection for the yoshilover data-short lane.

Phase 1 consumes the existing ``/data/notable`` payload shape and picks one
rights-safe, data-backed topic for a 60 second vertical video.  It does not
fetch media, call YouTube, or mutate WordPress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping


DEFAULT_SOURCE_URL = "https://yoshilover.com/data/notable?v=yt"


@dataclass(frozen=True)
class ShortsTopic:
    player: str
    slug: str
    label: str
    value: str
    note: str
    category: str
    as_of: str
    title: str
    hook: str
    source_url: str = DEFAULT_SOURCE_URL
    priority: float = 0.0
    raw_item: dict[str, Any] = field(default_factory=dict)

    @property
    def topic_key(self) -> str:
        base = "|".join(
            [
                "yt_shorts",
                self.as_of,
                self.player,
                self.label,
                self.value,
            ]
        )
        return re.sub(r"\s+", "", base)


def _first_number(value: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?|\.\d+", str(value or ""))
    if not match:
        return 0.0
    raw = match.group(0)
    try:
        return float("0" + raw if raw.startswith(".") else raw)
    except ValueError:
        return 0.0


def _priority_for_item(item: Mapping[str, Any]) -> float:
    label = str(item.get("label") or "")
    category = str(item.get("category") or "")
    value = str(item.get("value") or "")
    note = str(item.get("note") or "")
    number = _first_number(value)

    if category == "streak" or "連続" in label:
        base = 500.0
    elif category == "weekly_mvp" or "週間MVP" in label:
        base = 450.0
    elif category in {"salary", "cost"} or "年俸" in label or "コスパ" in label:
        base = 320.0
    elif category == "mlb" or "MLB" in label or "MLB" in note:
        base = 260.0
    else:
        base = 200.0

    # Stronger hooks win inside the same category.  Keep the boost capped so
    # category intent remains dominant.
    return base + min(number, 99.0)


def _label_value_phrase(label: str, value: str) -> str:
    if label and value and value[0] in ".0123456789" and re.search(r"[A-Za-z0-9/]$", label):
        return f"{label} {value}"
    return f"{label}{value}"


def topic_from_notable_item(
    item: Mapping[str, Any],
    *,
    as_of: str = "",
    source_url: str = DEFAULT_SOURCE_URL,
) -> ShortsTopic | None:
    player = str(item.get("player") or "").strip()
    label = str(item.get("label") or "").strip()
    value = str(item.get("value") or "").strip()
    if not player or not label or not value:
        return None

    note = str(item.get("note") or "").strip()
    slug = str(item.get("slug") or "").strip()
    category = str(item.get("category") or "form").strip() or "form"
    phrase = _label_value_phrase(label, value)
    title = f"{player} {phrase}をデータで見る"
    hook = f"{player}、{phrase}"
    return ShortsTopic(
        player=player,
        slug=slug,
        label=label,
        value=value,
        note=note,
        category=category,
        as_of=str(as_of or "").strip(),
        title=title,
        hook=hook,
        source_url=source_url,
        priority=_priority_for_item(item),
        raw_item=dict(item),
    )


def list_topics_from_notable_data(
    notable_data: Mapping[str, Any] | None,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
) -> list[ShortsTopic]:
    """Return all topics from a notable-data payload, best (highest priority) first.

    Payload shape is intentionally loose:
    ``{"as_of": "YYYY-MM-DD", "items": [{player,label,value,note,...}]}``.
    Unknown keys are preserved in ``ShortsTopic.raw_item`` for mail evidence.
    Callers that want diversity (e.g. least-recently-used fallback) rank this
    list themselves instead of always taking the top entry.
    """

    if not notable_data:
        return []
    as_of = str(notable_data.get("as_of") or "")
    topics: list[ShortsTopic] = []
    for item in notable_data.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        topic = topic_from_notable_item(item, as_of=as_of, source_url=source_url)
        if topic is not None:
            topics.append(topic)
    return sorted(topics, key=lambda t: (-t.priority, t.player, t.label))


def select_topic_from_notable_data(
    notable_data: Mapping[str, Any] | None,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
) -> ShortsTopic | None:
    """Return the highest-priority topic from a notable-data payload."""

    topics = list_topics_from_notable_data(notable_data, source_url=source_url)
    return topics[0] if topics else None


__all__ = [
    "DEFAULT_SOURCE_URL",
    "ShortsTopic",
    "list_topics_from_notable_data",
    "select_topic_from_notable_data",
    "topic_from_notable_item",
]
