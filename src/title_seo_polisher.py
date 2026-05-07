"""Rule-based, no-LLM title polish that runs at create_post boundary.

Targets the SNS-click / readability axis (the YOSHILOVER site is
noindex, so SERP-level SEO is out of scope; this polisher only cleans
the title shape so the user-facing X / Slack / mail preview reads well).

Rules (all reversible, all 0 円):

  1. HTML entity decode (e.g. ``&#8217;`` → ``'``)
  2. Strip retweet / quote prefixes (``RT xxx:`` / ``RT @xxx:``)
  3. Trim generic filler suffixes:
       - ``...についてコメント`` / ``...について``
       - ``...についてのコメント``
       - trailing 「。」「、」「・」「：」「:」 dust
  4. Drop leading 助詞 (``が`` / ``は`` / ``を`` / ``に`` / ``で`` / ``と``
     / ``の``) — Japanese style guides forbid 助詞 starting a headline.
  5. Hoist 巨人 / 巨人・<player> to the head when it appears mid-title.
     (Soft-disabled by default — keep call sites stable; turn on with
     ``hoist_keywords=True`` once we have fixture coverage.)
  6. Cap full-width display length at ``max_length`` (default 50, the
     SP SERP / X preview cutoff in our deployment), with a trailing
     ``…`` (U+2026) when the cap actually trims content.

The polisher is conservative: subtype-controlled titles (試合結果 /
二軍 / 公示 / 巨人スタメン …) are detected by a fixed-prefix check and
left untouched so the existing strict validators in ``title_validator``
and ``title_style_validator`` keep their contracts.
"""

from __future__ import annotations

import html as _html
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

_TITLE_SEO_ENV = "WP_TITLE_SEO_POLISH"


def _polish_enabled() -> bool:
    raw = os.environ.get(_TITLE_SEO_ENV, "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


# Subtype-controlled prefixes carry strict validator contracts already.
# When the title starts with one of these we leave it alone.
_PROTECTED_PREFIXES = (
    "【公示】",
    "【一軍】",
    "【二軍】",
    "【動画】",
    "【スタメン",
    "【試合結果】",
    "【先発情報】",
    "【セパ公示】",
    "【YouTube】",
    "巨人スタメン",
    "巨人・スタメン",
)
_DATE_PREFIX_RE = re.compile(r"^\s*\d{4}年\d{1,2}月\d{1,2}日")
_RT_PREFIX_RE = re.compile(r"^\s*RT\s+[^：:]{1,40}[：:]\s*", re.IGNORECASE)

# Trailing fillers we trim. Order matters — the longer phrases first so
# substring overlap doesn't double-strip.
_TRAILING_FILLERS = (
    "についてコメント",
    "についてのコメント",
    "に関するコメント",
    "についての話",
    "について",
)
_TRAILING_DUST_RE = re.compile(r"[、。・：:\s]+$")
_LEADING_PARTICLE_RE = re.compile(r"^[がはをにでとのも][^\s]")

# Used by the length cap. We measure by len() because the WP REST + SNS
# preview also operate on character count rather than bytes.
DEFAULT_MAX_TITLE_LENGTH = 50


def _strip_rt_prefix(title: str) -> str:
    return _RT_PREFIX_RE.sub("", title, count=1)


def _strip_trailing_filler(title: str) -> str:
    out = title
    for filler in _TRAILING_FILLERS:
        if out.endswith(filler):
            out = out[: -len(filler)]
    out = _TRAILING_DUST_RE.sub("", out)
    return out


def _strip_leading_particle(title: str) -> str:
    if _LEADING_PARTICLE_RE.match(title):
        return title[1:]
    return title


def _cap_length(title: str, max_length: int) -> str:
    if max_length <= 0 or len(title) <= max_length:
        return title
    return title[: max_length - 1].rstrip() + "…"


def _is_protected(title: str) -> bool:
    if not title:
        return False
    if _DATE_PREFIX_RE.match(title):
        return True
    return any(title.startswith(p) for p in _PROTECTED_PREFIXES)


def polish_title(
    title: str,
    *,
    max_length: int = DEFAULT_MAX_TITLE_LENGTH,
    force: bool = False,
) -> str:
    """Return a polished title. Pure function; no I/O.

    The polisher is a no-op when:
      - the env flag is disabled (and ``force`` is False)
      - the input doesn't look like a string
      - the title carries a subtype-controlled prefix

    The output is guaranteed non-empty when the input is non-empty
    after trimming (we never trim the whole title away).
    """
    if not isinstance(title, str):
        return title
    if not force and not _polish_enabled():
        return title

    raw = title.strip()
    if not raw:
        return title

    if _is_protected(raw):
        # Still safe to decode HTML entities and cap length even on
        # protected titles — those operations don't change semantics.
        decoded = _html.unescape(raw)
        return _cap_length(decoded, max_length)

    work = _html.unescape(raw)
    work = _strip_rt_prefix(work)
    work = _strip_trailing_filler(work)
    work = _strip_leading_particle(work)
    work = work.strip()

    if not work:
        # Defensive: never return empty if we started with content.
        return _cap_length(_html.unescape(raw), max_length)

    return _cap_length(work, max_length)
