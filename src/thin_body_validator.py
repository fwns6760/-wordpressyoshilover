"""Thin body validator — STOP gate for 本文崩壊 publish.

Memory rule (feedback_publish_forward_must_check_gate_reason.md):

    STOP gate 6 種:
        本物重複 / placeholder / 事実破綻 / entity mismatch /
        巨人と完全無関係 / **本文崩壊**

This module enforces 「本文崩壊 = STOP」 at WP create_post chokepoint.

Background
==========

2026-05-08 13:04 JST に 10 件の post (65074-65092) が body 420 chars 同一
(``<div class="yoshilover-x-embed">`` の oembed wrapper のみ、本文ゼロ) で
publish された。原因は ``rss_fetcher.py:20966`` の AI 不使用 fallback で
``content = build_oembed_block(post_url)`` が呼ばれ、X URL 想定の
oembed wrapper を hochi.news 等の **非 X URL** で生成 → Twitter widgets.js が
非 X URL を tweet 化できず、live で本文ゼロ表示になった。

memory rule の「本文崩壊」STOP gate が pre-publish で enforce されていなかった。
本 module はその enforcement を WP create_post chokepoint で 1 か所に集約する。

Detection criteria
==================

是 thin (publish refuse):
  1. ``empty_body``: body_html が None / 空文字
  2. ``body_too_small``: total HTML < 50 chars OR text content < 30 chars
  3. ``oembed_only_no_body``: ``yoshilover-x-embed`` div あり / ``<h3>`` なし /
     30+ chars text を含む ``<p>`` なし / total HTML < 600 chars

非 thin (publish OK):
  - 短い記事 (300-500 chars) でも ``<p>`` の text content があれば通す
  - X embed + 本文 (``<h3>`` or ``<p>`` text あり) あれば通す
  - Conservative: false-positive を避け、明確な「本文崩壊」のみ捕える

False-positive policy
=====================

Conservative on purpose. 検出基準を緩く設定して false-positive を避ける。
本 validator が refuse する case は **明らかに本文がない** ものに限定する。
微妙な品質問題 (短い / H3 不足 / 装飾不足) は他の品質 gate / review draft
path で扱う。

NOTE: Cloud Run / WP / Gemini / 外部 API への呼び出しは一切しない。pure-Python
内の HTML 構造判定のみ。¥0、stateless、idempotent。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


__all__ = ["ThinBodyResult", "is_thin_body"]


@dataclass
class ThinBodyResult:
    """thin-body 判定結果。

    Attributes:
        is_thin: True なら publish refuse、False なら通す。
        reason: 検出理由 ('empty_body' / 'body_too_small' /
            'oembed_only_no_body' / 'ok')。is_thin=False の時は 'ok'。
        text_chars: HTML タグを除去した text の文字数。
        html_chars: 入力 HTML の総文字数。
    """

    is_thin: bool
    reason: str
    text_chars: int
    html_chars: int


# 検出 pattern. precompiled for efficiency.
_OEMBED_DIV_RE = re.compile(
    r'<div\s+class\s*=\s*["\']yoshilover-x-embed[^"\']*["\']',
    re.IGNORECASE,
)
_HAS_H3_RE = re.compile(r"<h3[\s>]", re.IGNORECASE)
# 30+ chars text を含む <p>。空 / 短すぎる <p></p> や <p>&nbsp;</p> は除外。
_HAS_TEXT_P_RE = re.compile(
    r"<p[^>]*>[^<]{30,}",
    re.IGNORECASE,
)
_SCRIPT_RE = re.compile(
    r"<script[^>]*>.*?</script>",
    re.DOTALL | re.IGNORECASE,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html_to_text(html: str) -> str:
    """HTML タグ / script / comment を除去して text content だけ返す。

    純粋な可視文字数測定用。形態素解析等はしない。
    """
    if not html:
        return ""
    html = _SCRIPT_RE.sub("", html)
    html = _HTML_COMMENT_RE.sub("", html)
    html = _TAG_RE.sub("", html)
    return _WS_RE.sub(" ", html).strip()


def is_thin_body(body_html: str) -> ThinBodyResult:
    """本文崩壊 (thin / empty body) を検出する。

    Returns ``ThinBodyResult(is_thin=True, reason=...)`` if body should be
    REJECTED from publish path.

    Detection:
      1. ``empty_body``: body_html が None / 空文字
      2. ``body_too_small``: total HTML < 50 chars OR text content < 30 chars
      3. ``oembed_only_no_body``: ``yoshilover-x-embed`` div あり、
         ``<h3>`` なし、30+ chars text を含む ``<p>`` なし、HTML < 600 chars

    Conservative on purpose: 明確な「本文崩壊」のみ捕える。
    """
    if not body_html:
        return ThinBodyResult(
            is_thin=True,
            reason="empty_body",
            text_chars=0,
            html_chars=0,
        )

    html_chars = len(body_html)
    text = _strip_html_to_text(body_html)
    text_chars = len(text)

    if html_chars < 50 or text_chars < 30:
        return ThinBodyResult(
            is_thin=True,
            reason="body_too_small",
            text_chars=text_chars,
            html_chars=html_chars,
        )

    has_oembed = bool(_OEMBED_DIV_RE.search(body_html))
    has_h3 = bool(_HAS_H3_RE.search(body_html))
    has_text_p = bool(_HAS_TEXT_P_RE.search(body_html))

    # 2026-05-08 13:04 JST の 10 件 incident pattern を捕える。
    # X embed wrapper が body 全体で、本文側に H3 も text を含む <p> も無い時。
    if has_oembed and not has_h3 and not has_text_p and html_chars < 600:
        return ThinBodyResult(
            is_thin=True,
            reason="oembed_only_no_body",
            text_chars=text_chars,
            html_chars=html_chars,
        )

    return ThinBodyResult(
        is_thin=False,
        reason="ok",
        text_chars=text_chars,
        html_chars=html_chars,
    )
