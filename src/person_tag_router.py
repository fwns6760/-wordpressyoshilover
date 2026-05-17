"""Rule-based WP person tag routing for Giants articles.

This module is intentionally deterministic. It never asks an LLM to
classify people, never creates WP tags, and returns explicit skip /
missing reasons so callers do not silently drop routing failures.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import html
import re
from typing import Any

from src import giants_ob_roster
from src import giants_roster_loader


CONTEXT_TAGS: tuple[str, ...] = (
    "一軍",
    "二軍",
    "三軍",
    "育成",
    "速報",
    "監督コメント",
    "OB解説",
    "雑誌報道",
)


@dataclass(frozen=True)
class PersonTagRouting:
    person_tags: tuple[str, ...]
    context_tags: tuple[str, ...]
    skip_reasons: tuple[str, ...]

    @property
    def tag_names(self) -> tuple[str, ...]:
        return _dedupe_preserve_order((*self.person_tags, *self.context_tags))


def _dedupe_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


def _clean_text(*parts: str) -> str:
    joined = " ".join(str(part or "") for part in parts)
    joined = re.sub(r"<[^>]+>", " ", joined)
    joined = html.unescape(joined)
    return re.sub(r"\s+", " ", joined).strip()


def _normalize_token(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = text.lstrip("*")
    return re.sub(r"[\s　【】「」『』〔〕（）()・･．\.,，/／\-ーｰ:：]", "", text).strip()


def _entry_aliases(entry: Mapping[str, Any]) -> tuple[str, ...]:
    name = str(entry.get("name") or "").strip().lstrip("*")
    aliases = [name]
    raw_aliases = entry.get("aliases") or []
    if isinstance(raw_aliases, Sequence) and not isinstance(raw_aliases, (str, bytes)):
        aliases.extend(str(alias or "").strip().lstrip("*") for alias in raw_aliases)
    return _dedupe_preserve_order(aliases)


def _canonical_entry_name(entry: Mapping[str, Any]) -> str:
    return (
        str(entry.get("name") or "")
        .strip()
        .lstrip("*")
        .replace(" ", "")
        .replace("　", "")
    )


def build_person_registry(
    active_roster: Sequence[Mapping[str, Any]] | None = None,
    ob_roster: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, tuple[str, ...]], dict[str, set[str]]]:
    """Return (canonical_to_aliases, alias_to_canonicals).

    Alias collisions are kept in ``alias_to_canonicals`` so matching can
    skip ambiguous short names instead of guessing.
    """

    if active_roster is None:
        active_roster = giants_roster_loader.load_active_roster()
    if ob_roster is None:
        ob_roster = giants_ob_roster.load_giants_ob_roster()

    canonical_to_aliases: dict[str, list[str]] = {}
    alias_to_canonicals: dict[str, set[str]] = {}

    for entry in [*active_roster, *ob_roster]:
        canonical = _canonical_entry_name(entry)
        if not canonical:
            continue
        bucket = canonical_to_aliases.setdefault(canonical, [])
        for alias in _entry_aliases(entry):
            normalized = _normalize_token(alias)
            # Single-character aliases like "原" and "王" are too risky.
            if len(normalized) < 2:
                continue
            if alias not in bucket:
                bucket.append(alias)
            alias_to_canonicals.setdefault(normalized, set()).add(canonical)

    return (
        {name: tuple(aliases) for name, aliases in canonical_to_aliases.items()},
        alias_to_canonicals,
    )


def all_person_tag_names(
    active_roster: Sequence[Mapping[str, Any]] | None = None,
    ob_roster: Sequence[Mapping[str, Any]] | None = None,
    *,
    include_context_tags: bool = True,
) -> tuple[str, ...]:
    canonical_to_aliases, _ = build_person_registry(active_roster, ob_roster)
    tags = sorted(canonical_to_aliases.keys())
    if include_context_tags:
        tags.extend(CONTEXT_TAGS)
    return _dedupe_preserve_order(tags)


def matching_person_tags(
    text: str,
    *,
    active_roster: Sequence[Mapping[str, Any]] | None = None,
    ob_roster: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    canonical_to_aliases, alias_to_canonicals = build_person_registry(
        active_roster,
        ob_roster,
    )
    normalized_text = _normalize_token(text)
    if not normalized_text:
        return (), ("empty_text",)

    ambiguous_aliases: set[str] = set()
    hits: list[str] = []
    hit_seen: set[str] = set()

    alias_rows: list[tuple[str, str]] = []
    canonical_norms = {
        canonical: _normalize_token(canonical)
        for canonical in canonical_to_aliases
    }
    for canonical, aliases in canonical_to_aliases.items():
        for alias in aliases:
            normalized_alias = _normalize_token(alias)
            if len(normalized_alias) < 2:
                continue
            alias_rows.append((normalized_alias, canonical))
    alias_rows.sort(key=lambda row: len(row[0]), reverse=True)

    for normalized_alias, canonical in alias_rows:
        if normalized_alias not in normalized_text:
            continue
        candidates = alias_to_canonicals.get(normalized_alias) or set()
        prefix_candidates = {
            canonical
            for canonical, normalized_name in canonical_norms.items()
            if normalized_name.startswith(normalized_alias)
        }
        if len(candidates) > 1:
            ambiguous_aliases.add(normalized_alias)
            continue
        if len(normalized_alias) <= 3 and len(prefix_candidates) > 1:
            ambiguous_aliases.add(normalized_alias)
            continue
        if canonical not in hit_seen:
            hit_seen.add(canonical)
            hits.append(canonical)

    reasons: list[str] = []
    if not hits:
        reasons.append("no_person_hit")
    for alias in sorted(ambiguous_aliases):
        reasons.append(f"ambiguous_alias:{alias}")
    return tuple(hits), tuple(reasons)


def _context_tags_for(
    text: str,
    *,
    category: str = "",
    article_subtype: str = "",
    source_name: str = "",
    source_type: str = "",
    has_ob_hit: bool = False,
) -> tuple[str, ...]:
    blob = _clean_text(text, category, article_subtype, source_name, source_type)
    tags: list[str] = []
    if "三軍" in blob:
        tags.append("三軍")
    if any(token in blob for token in ("二軍", "2軍", "ファーム")):
        tags.append("二軍")
    if "育成" in blob:
        tags.append("育成")
    if category == "試合速報" or any(
        token in article_subtype
        for token in ("lineup", "pregame", "postgame", "live", "game")
    ):
        tags.append("速報")
    if category == "首脳陣" or any(token in blob for token in ("監督", "コーチ")):
        tags.append("監督コメント")
    if category == "OB・解説者" or has_ob_hit:
        tags.append("OB解説")
    if any(token in blob for token in ("週刊", "雑誌", "FRIDAY", "FLASH", "文春")):
        tags.append("雑誌報道")
    if not any(tag in tags for tag in ("二軍", "三軍")) and category in {"試合速報", "選手情報", "首脳陣"}:
        tags.append("一軍")
    return _dedupe_preserve_order(tags)


def route_tag_names(
    *,
    title: str,
    summary: str = "",
    category: str = "",
    article_subtype: str = "",
    source_name: str = "",
    source_type: str = "",
    active_roster: Sequence[Mapping[str, Any]] | None = None,
    ob_roster: Sequence[Mapping[str, Any]] | None = None,
) -> PersonTagRouting:
    text = _clean_text(title, summary)
    person_tags, reasons = matching_person_tags(
        text,
        active_roster=active_roster,
        ob_roster=ob_roster,
    )

    ob_hits = ()
    try:
        ob_hits = tuple(
            name
            for name in giants_ob_roster.matching_ob_names(
                text,
                roster=ob_roster,
            )
            if name in person_tags
        )
    except Exception:
        ob_hits = ()

    context_tags = _context_tags_for(
        text,
        category=category,
        article_subtype=article_subtype,
        source_name=source_name,
        source_type=source_type,
        has_ob_hit=bool(ob_hits),
    )
    return PersonTagRouting(
        person_tags=person_tags,
        context_tags=context_tags,
        skip_reasons=reasons,
    )


def resolve_existing_wp_tag_ids(
    wp: Any,
    tag_names: Iterable[str],
    *,
    logger: Any | None = None,
) -> tuple[list[int], list[str]]:
    """Resolve tag names to existing WP tag ids.

    Missing tags are returned and optionally logged; this function never
    creates terms. The separate sync CLI owns term creation.
    """

    tag_ids: list[int] = []
    missing: list[str] = []
    for name in _dedupe_preserve_order(tag_names):
        try:
            tag_id = int(wp.resolve_tag_id(name) or 0)
        except Exception as exc:  # noqa: BLE001
            tag_id = 0
            if logger is not None:
                logger.warning("wp_tag_resolve_failed name=%s error=%s", name, exc)
        if tag_id > 0:
            tag_ids.append(tag_id)
        else:
            missing.append(name)
    return tag_ids, missing
