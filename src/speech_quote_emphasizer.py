"""Wrap 「」/『』 inline speech segments with a styled span.

Applied to the source-body excerpt block (nomotoke-source-excerpt__body) so
that direct-speech quotes stand out without changing the global stylesheet.
"""
from __future__ import annotations

import re

_SPAN_OPEN = '<span style="color:#c54500;font-weight:700;font-size:1.3em">'
_SPAN_CLOSE = "</span>"
_STYLE_FINGERPRINT = "color:#c54500"

# Inner content can include <br> / <br /> but must not cross paragraph
# boundaries (</p>) and must not contain another opener of the same kind.
_PAT_KAGI = re.compile(r"「((?:(?!</p>)[^「」])+?)」", re.S)
_PAT_NIJUU = re.compile(r"『((?:(?!</p>)[^『』])+?)』", re.S)


def _wrap_factory(open_ch: str, close_ch: str):
    def _wrap(match: re.Match[str]) -> str:
        inner = match.group(1)
        if _STYLE_FINGERPRINT in inner:
            return match.group(0)
        return f"{open_ch}{_SPAN_OPEN}{inner}{_SPAN_CLOSE}{close_ch}"

    return _wrap


def wrap_speech_quotes(html_fragment: str) -> str:
    """Return ``html_fragment`` with 「…」 and 『…』 inner text wrapped in a
    styled span. Idempotent — already-wrapped segments are left untouched.
    """
    if not html_fragment:
        return html_fragment
    out = _PAT_KAGI.sub(_wrap_factory("「", "」"), html_fragment)
    out = _PAT_NIJUU.sub(_wrap_factory("『", "』"), out)
    return out
