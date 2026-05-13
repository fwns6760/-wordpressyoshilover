"""のもとけ-style SEO title template assembler.

Reshapes the already-backfilled title into one of the 5 patterns observed
on dnomotoke.com:

  A. ``<name>「<quote>」``                 — quote-style
  B. ``<modifier>の巨人・<name>、<result>``  — situation+result
  C. ``<verb>+<name>、<info>``             — action-first
  D. ``<OB さん>「<comment>」``             — OB / commentator
  E. ``<date> <game>「巨人vs.<opp>」<...>``  — date-based notice/broadcast

Subtype → pattern mapping (covers ~80% of yoshilover publishes):

  player_comment / player_quote / player  → A
  manager / manager_comment               → A (suffix 監督)
  coach_comment                           → A (suffix コーチ / 投手コーチ 等)
  postgame                                → B
  broadcast / program                     → E (broadcast)
  lineup                                  → E (lineup)
  notice                                  → E (notice)

ENABLE_NOMOTOKE_TITLE_TEMPLATE env (default ON) controls activation.
Returns ``None`` when facts are insufficient — caller keeps original title.
"""

from __future__ import annotations

import os
import re
from typing import Mapping, Optional


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def nomotoke_title_template_enabled() -> bool:
    val = (os.getenv("ENABLE_NOMOTOKE_TITLE_TEMPLATE") or "1").strip().lower()
    return val in _TRUE_VALUES


_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_QUOTE_RE = re.compile(r"[「『]([^」』]{2,60})[」』]")


def _clean(text: str) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", _HTML_RE.sub(" ", text)).strip()


def _first_quote(*texts: str, max_len: int = 28) -> str:
    """Return the first 2-60 char quote found in any of the inputs, trimmed
    to ``max_len`` chars. Empty when no quote present."""
    for t in texts:
        t = _clean(t)
        if not t:
            continue
        m = _QUOTE_RE.search(t)
        if m:
            inner = m.group(1).strip()
            if inner:
                if len(inner) > max_len:
                    inner = inner[:max_len].rstrip() + "…"
                return inner
    return ""


def _display_role_suffix(role: str) -> str:
    role = (role or "").strip()
    if role == "監督":
        return "監督"
    if role == "コーチ":
        return "コーチ"
    if role in {"投手"}:
        return "投手"
    if role in {"捕手", "内野手", "外野手", "選手"}:
        return ""
    return ""


_POSTGAME_RESULT_MARKERS = (
    ("サヨナラ", "サヨナラ勝ち"),
    ("逆転", "逆転勝ち"),
    ("完封", "完封勝ち"),
    ("延長", "延長戦"),
    ("連勝", "連勝"),
    ("敗戦", "敗戦"),
    ("惜敗", "惜敗"),
    ("勝利", "勝利"),
)


def _postgame_modifier(source_title: str, source_body: str, summary: str) -> str:
    """Extract a short B-pattern modifier like 「サヨナラ打の」「無失点投球の」.
    Returns empty when nothing matches."""
    text = " ".join(_clean(t) for t in (source_title, summary, source_body) if t)[:600]
    if not text:
        return ""
    if "サヨナラ" in text:
        return "サヨナラ"
    if "逆転" in text:
        return "逆転"
    if "無失点" in text:
        return "無失点投球"
    if "完封" in text:
        return "完封"
    if "ホームラン" in text or "本塁打" in text:
        return "本塁打"
    if "好救援" in text or "セーブ" in text:
        return "好救援"
    if "猛打賞" in text:
        return "猛打賞"
    return ""


def _postgame_result_phrase(source_title: str, source_body: str, summary: str) -> str:
    text = " ".join(_clean(t) for t in (source_title, summary, source_body) if t)[:600]
    if not text:
        return ""
    for needle, phrase in _POSTGAME_RESULT_MARKERS:
        if needle in text:
            return phrase
    return ""


def _opponent_from_facts(metadata: Mapping[str, object]) -> str:
    for key in ("opponent", "opponent_team", "opponent_team_name"):
        v = str(metadata.get(key) or "").strip()
        if v:
            return v
    return ""


def _date_label_from_facts(metadata: Mapping[str, object]) -> str:
    for key in ("event_date_label", "date_label", "game_date_label"):
        v = str(metadata.get(key) or "").strip()
        if v:
            return v
    return ""


def _is_quote_subtype(subtype: str) -> bool:
    return subtype in {
        "player_comment",
        "player_quote",
        "manager_comment",
        "coach_comment",
    }


def _assemble_pattern_A(
    *,
    name: str,
    role: str,
    quote: str,
    is_manager: bool,
    is_coach: bool,
) -> Optional[str]:
    if not name or not quote:
        return None
    role_suffix = ""
    if is_manager:
        role_suffix = "監督"
    elif is_coach:
        role_suffix = _display_role_suffix(role) or "コーチ"
    if role_suffix and not name.endswith(role_suffix):
        head = f"{name}{role_suffix}"
    else:
        head = name
    return f"{head}「{quote}」"


def _assemble_pattern_B(
    *,
    name: str,
    role: str,
    source_title: str,
    source_body: str,
    summary: str,
) -> Optional[str]:
    if not name:
        return None
    modifier = _postgame_modifier(source_title, source_body, summary)
    result_phrase = _postgame_result_phrase(source_title, source_body, summary)
    if not modifier and not result_phrase:
        return None
    role_suffix = _display_role_suffix(role)
    name_with_role = f"{name}{role_suffix}" if role_suffix and not name.endswith(role_suffix) else name
    prefix = f"{modifier}の" if modifier else ""
    tail = f"、{result_phrase}" if result_phrase else ""
    return f"{prefix}巨人・{name_with_role}{tail}"


def _assemble_pattern_E_broadcast(
    *,
    metadata: Mapping[str, object],
    source_title: str,
) -> Optional[str]:
    """Returns broadcast-style title only when date+opponent are available."""
    date_label = _date_label_from_facts(metadata)
    opponent = _opponent_from_facts(metadata)
    if not date_label or not opponent:
        return None
    suffix = "【テレビ・ネット中継】"
    return f"{date_label}「巨人vs.{opponent}」{suffix}"


def assemble_nomotoke_title(
    *,
    article_subtype: str,
    existing_title: str,
    source_title: str = "",
    source_body: str = "",
    summary: str = "",
    player_name: str = "",
    role: str = "",
    metadata: Optional[Mapping[str, object]] = None,
) -> Optional[str]:
    """Reshape the title to a のもとけ-style pattern based on subtype.

    Returns the reshaped title, or ``None`` when:
      - the assembler is disabled via env
      - subtype has no mapped pattern
      - required facts (name / quote / modifier) are missing
      - the assembled title would equal the input (idempotent)

    Caller keeps ``existing_title`` when ``None`` is returned.
    """
    if not nomotoke_title_template_enabled():
        return None
    metadata = dict(metadata or {})
    subtype = (article_subtype or "").strip()
    name = (player_name or "").strip()

    assembled: Optional[str] = None
    if _is_quote_subtype(subtype):
        quote = _first_quote(existing_title, source_title, source_body, summary)
        assembled = _assemble_pattern_A(
            name=name,
            role=role,
            quote=quote,
            is_manager=subtype == "manager_comment" or role == "監督",
            is_coach=subtype == "coach_comment" or role == "コーチ",
        )
    elif subtype == "manager":
        quote = _first_quote(existing_title, source_title, source_body, summary)
        assembled = _assemble_pattern_A(
            name=name,
            role=role or "監督",
            quote=quote,
            is_manager=True,
            is_coach=False,
        )
    elif subtype == "postgame":
        assembled = _assemble_pattern_B(
            name=name,
            role=role,
            source_title=source_title,
            source_body=source_body,
            summary=summary,
        )
    elif subtype in {"broadcast", "program"}:
        assembled = _assemble_pattern_E_broadcast(
            metadata=metadata,
            source_title=source_title,
        )
    # lineup / notice / pregame は別 pattern、次便で追加

    if assembled and assembled.strip() and assembled.strip() != _clean(existing_title):
        return assembled.strip()
    return None


__all__ = [
    "assemble_nomotoke_title",
    "nomotoke_title_template_enabled",
]
