"""Wrap 「」/『』 inline speech segments with a styled span.

Applied to the source-body excerpt block (nomotoke-source-excerpt__body) so
that direct-speech quotes stand out without changing the global stylesheet.

Readability rules (2026-07-02 引用洗練):

- 強調は色 + 太字のみ。font-size は上げない(長い引用が巨大文字の壁に
  なって本文より目立ちすぎるため)。
- 表示文字数が ``_EMPHASIS_MAX_CHARS`` を超える長い発言は強調しない。
  長い直接話法は地の文として読ませたほうが読みやすい。
- 既に強調 span の内側にある 「」/『』 は二重に包まない(入れ子 span で
  強調が重なり崩れるため)。
"""
from __future__ import annotations

import re

_SPAN_OPEN = '<span style="color:#c54500;font-weight:700">'
_SPAN_CLOSE = "</span>"
_STYLE_FINGERPRINT = "color:#c54500"

# Longest visible quote (tags stripped) that still gets emphasis.
_EMPHASIS_MAX_CHARS = 48

# Inner content can include <br> / <br /> but must not cross paragraph
# boundaries (</p>) and must not contain another opener of the same kind.
_PAT_KAGI = re.compile(r"「((?:(?!</p>)[^「」])+?)」", re.S)
_PAT_NIJUU = re.compile(r"『((?:(?!</p>)[^『』])+?)』", re.S)

_TAG_RE = re.compile(r"<[^>]+>")


def _visible_len(fragment: str) -> int:
    return len(_TAG_RE.sub("", fragment))


def _inside_open_span(text: str, pos: int) -> bool:
    """True when ``pos`` falls inside an unclosed emphasis span."""
    head = text[:pos]
    return head.count(_SPAN_OPEN) > head.count(_SPAN_CLOSE)


def _wrap_factory(open_ch: str, close_ch: str):
    def _wrap(match: re.Match[str]) -> str:
        inner = match.group(1)
        if _STYLE_FINGERPRINT in inner:
            return match.group(0)
        if _visible_len(inner) > _EMPHASIS_MAX_CHARS:
            return match.group(0)
        if _inside_open_span(match.string, match.start()):
            return match.group(0)
        return f"{open_ch}{_SPAN_OPEN}{inner}{_SPAN_CLOSE}{close_ch}"

    return _wrap


def wrap_speech_quotes(html_fragment: str) -> str:
    """Return ``html_fragment`` with 「…」 and 『…』 inner text wrapped in a
    styled span. Idempotent — already-wrapped segments are left untouched.
    Long quotes (> ``_EMPHASIS_MAX_CHARS`` visible chars) and quotes nested
    inside an existing emphasis span stay unwrapped.
    """
    if not html_fragment:
        return html_fragment
    out = _PAT_KAGI.sub(_wrap_factory("「", "」"), html_fragment)
    out = _PAT_NIJUU.sub(_wrap_factory("『", "』"), out)
    return out
