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
  2. ``oembed_only_no_body``: ``yoshilover-x-embed`` div あり / ``<h3>`` なし /
     30+ chars text を含む ``<p>`` なし / total HTML < 600 chars
     → 13:04 JST incident pattern と完全一致

非 thin (publish OK):
  - 短い記事 (12 chars HTML / 4 chars text の test infrastructure 含む)
  - 短い記事 (300-500 chars) でも ``<p>`` の text content があれば通す
  - X embed + 本文 (``<h3>`` or ``<p>`` text あり) あれば通す

False-positive policy
=====================

**本 validator は「oembed-only incident pattern」専用 narrow STOP gate**。
微妙な品質問題 (短い body / H3 不足 / 装飾不足) は **本 validator の責務外**:
- post_gen_validate (rss_fetcher 内): 本文品質 gate
- body_contract_validate: 構造 gate
- review_draft path (RELIABILITY-2026-05-08-E): 軽微 fail を draft 化

本 validator は memory rule の 6 STOP gate のうち「本文崩壊 (content collapse)」を
**oembed_only_no_body** と定義して 1 axis 専用 enforce。他 axis (placeholder /
事実破綻 / entity mismatch / 巨人と完全無関係 / 重複) は別 module で。

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
    """本文崩壊 (oembed-only incident pattern) を検出する。

    Returns ``ThinBodyResult(is_thin=True, reason=...)`` if body should be
    REJECTED from publish path.

    Detection (narrow):
      1. ``empty_body``: body_html が None / 空文字
      2. ``oembed_only_no_body``: ``yoshilover-x-embed`` div あり、
         ``<h3>`` なし、30+ chars text を含む ``<p>`` なし、HTML < 600 chars

    NOT detected here (other gates' responsibility):
      - 短い body (~50 chars HTML): post_gen_validate / body_contract で
      - placeholder body / 事実破綻 / entity mismatch: 既存 stop gate で
      - test infrastructure の minimal body (``<p>body</p>`` 等): 通す
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

    has_oembed = bool(_OEMBED_DIV_RE.search(body_html))
    has_h3 = bool(_HAS_H3_RE.search(body_html))
    has_text_p = bool(_HAS_TEXT_P_RE.search(body_html))

    # 2026-05-08 13:04 JST の 10 件 incident pattern を捕える。
    # X embed wrapper が body 全体で、本文側に H3 も text を含む <p> も無い時。
    # HTML < 600 chars に絞ることで、長文 + X embed の正常 postgame full は
    # 通す (oembed が末尾に付く pattern)。
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
