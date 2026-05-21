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

# Length cap is a DB-safety net only (wp_posts.post_title is VARCHAR(255));
# SNS preview truncation lives in x_post_generator / x_api_client / mail
# subject formatter, so the polisher no longer enforces a SERP-style 50-char
# cap that mid-cut multi-subject titles (e.g. multi-player birthday digests).
DEFAULT_MAX_TITLE_LENGTH = 200


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


# issue #44 follow-up (2026-05-17 user lock、 post 68870): title が "…" で
# 終わっていて主語+述語が読み取れない場合、 summary 側に full text があれば
# その第一文を再構成して title に当てる。 location/emoji 装飾 prefix
# (ジャイアンツ球場⚾️ 等) も剥がして player+動作 を前に出す。
# location + emoji 装飾 prefix (例: "ジャイアンツ球場⚾️ ") を player+選手 の
# 直前で剥がす。 emoji (⚾🏟⭐✨🎯💪🔥💯 等) が prefix に含まれる場合のみ
# 適用、 通常の player 列 (例: "巨人の岡本和真 選手") は剥がさない。
_DECORATION_PREFIX_RE = re.compile(
    r"^\S*[⚾🏟⭐✨🎯💪🔥💯]\S*\s+(?=[一-龥ぁ-んァ-ヴー]{2,6}\s*選手)"
)
_FIRST_SENTENCE_RE = re.compile(r"([^。！？…\n]+[。！？])")


def recover_from_trailing_ellipsis(title: str, summary: str) -> str:
    """``…`` 末尾 truncation title を summary 第一文で再構成する.

    Returns: 再構成後の title。 復元不能なら原 title をそのまま返す。

    Examples (post 68870 actual):
        title="ジャイアンツ球場⚾️ 石塚裕惺…"
        summary="RT 水上智恵【スポーツ報知・巨人担当】: ジャイアンツ球場⚾️ "
                "石塚裕惺 選手がマシン打撃を再開しました！"
        → "石塚裕惺 選手がマシン打撃を再開しました！"
    """
    if not isinstance(title, str) or not title.endswith("…"):
        return title
    if not isinstance(summary, str) or not summary:
        return title
    summary_clean = _strip_rt_prefix(_html.unescape(summary)).strip()
    if not summary_clean:
        return title
    sentence_match = _FIRST_SENTENCE_RE.match(summary_clean)
    if not sentence_match:
        return title
    sentence = sentence_match.group(1).strip()
    if not sentence or sentence.endswith("…"):
        return title
    sentence = _DECORATION_PREFIX_RE.sub("", sentence).strip()
    if not sentence:
        return title
    if len(sentence) > DEFAULT_MAX_TITLE_LENGTH:
        sentence = sentence[: DEFAULT_MAX_TITLE_LENGTH - 1].rstrip() + "…"
    return sentence


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
