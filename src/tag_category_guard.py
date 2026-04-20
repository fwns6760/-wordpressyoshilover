import re
from typing import Iterable


TAG_MIN: int = 1
TAG_MAX: int = 20
TAG_TARGET_LOW: int = 15
ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {"試合結果", "スタメン", "選手情報", "その他"}
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_tag(tag: str) -> str:
    """Return a normalized tag string."""
    normalized = _WHITESPACE_RE.sub(" ", tag.strip())
    if not normalized:
        return ""
    if any(char.isascii() and char.isalpha() for char in normalized):
        return normalized.lower()
    return normalized


def normalize_tags(tags: Iterable[str]) -> list[str]:
    """Normalize tags, drop blanks, and preserve order."""
    normalized_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = normalize_tag(tag)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_tags.append(normalized)
    return normalized_tags


def validate_tags(tags: Iterable[str]) -> tuple[list[str], list[str]]:
    """Return normalized tags and count warnings."""
    kept = normalize_tags(tags)
    count = len(kept)
    warnings: list[str] = []
    if count > TAG_MAX:
        warnings.append(f"too many tags: {count} > {TAG_MAX}")
    elif count < TAG_MIN:
        warnings.append(f"too few tags: {count} < {TAG_MIN}")
    elif count < TAG_TARGET_LOW:
        warnings.append(f"below target tags: {count} < {TAG_TARGET_LOW}")
    return kept, warnings


def validate_category(category: str) -> tuple[str, list[str]]:
    """Return a supported category and warnings."""
    normalized = normalize_tag(category)
    if normalized in ALLOWED_CATEGORIES:
        return normalized, []
    return "その他", [f"unknown category: {normalized or '(empty)'} -> その他"]
