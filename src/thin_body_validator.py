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
  3. ``postgame_scorecard_only``: のもとけ系 postgame card で ``試合スコア``
     table 以外の detail section が無く、generic closing だけで終わる
     scorecard-only body。``65801`` 系の thin-body publish を止める。

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
            'oembed_only_no_body' / 'postgame_scorecard_only' / 'ok')。
            is_thin=False の時は 'ok'。
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
_NOMOTOKE_CARD_FOOTER_RE = re.compile(
    r'class\s*=\s*["\']nomotoke-card-footer["\']',
    re.IGNORECASE,
)
_NOMOTOKE_CTA_ROW_RE = re.compile(
    r'class\s*=\s*["\']nomotoke-cta-row["\']',
    re.IGNORECASE,
)
_POSTGAME_SCORE_HEADING_RE = re.compile(
    r"<h3[^>]*>.*?試合スコア.*?</h3>",
    re.IGNORECASE | re.DOTALL,
)
_POSTGAME_DETAIL_HEADING_RE = re.compile(
    r"<h3[^>]*>.*?(?:打席結果|投球結果|勝敗投手|相手スタメン).*?</h3>",
    re.IGNORECASE | re.DOTALL,
)
_POSTGAME_GENERIC_CLOSING_RE = re.compile(
    r"<p>\s*(?:勝ちました。|悔しい敗戦です。|引き分けでした。)\s*</p>",
    re.IGNORECASE,
)
_SCRIPT_RE = re.compile(
    r"<script[^>]*>.*?</script>",
    re.DOTALL | re.IGNORECASE,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# News digest gradient banner emitted at the top of every nomotoke card.
# Banner is chrome (source / kicker / title attribution) — not body content.
# Strip it before measuring text/html chars so it doesn't mask thin bodies.
# The banner block is `<div class="nomotoke-news-banner" ...><div...><span...>
# ...</span><span...>...</span></div><div...>{title}</div></div>` (3-level
# fixed structure under our control).
_NEWS_BANNER_RE = re.compile(
    r'<div\s+class\s*=\s*["\']nomotoke-news-banner["\'][^>]*>'
    r'<div[^>]*>(?:<span[^>]*>[^<]*</span>\s*)+</div>'
    r'<div[^>]*>[^<]*</div>'
    r'</div>',
    re.IGNORECASE | re.DOTALL,
)
# Fan voice fallback block emitted by h3_normalizer._ensure_fan_voice_section
# when an article has no organic fan voice section. The h3 + the
# `関連ポストなし` placeholder paragraph are chrome — they should not
# rescue an otherwise-thin body from the thin-body publish gate.
_FAN_VOICE_FALLBACK_RE = re.compile(
    r"<h3[^>]*>\s*💬\s*ファンの声(?:[^<]*)\s*</h3>\s*"
    r"<p[^>]*>\s*関連ポストなし\s*</p>",
    re.IGNORECASE | re.DOTALL,
)
_POSTGAME_SCORECARD_ONLY_MAX_TEXT_CHARS = 220

# thin_source_padding: 1-tweet / short-source articles that have been padded
# to 1500-2700 chars with AI scaffolding (questions, generic columns, filler
# "どう見る" / "今後の動向" phrases) rather than concrete fact reporting.
#
# Heuristic — fires only when ALL of:
#   1. X embed wrapper present (yoshilover-x-embed div) — signals 1-tweet
#      source path.
#   2. Visible body text (with chrome stripped) is large enough to be padded
#      (>= 800 chars) but not so large that real reporting is plausible
#      (<= 3000 chars).
#   3. Concrete fact density is low: fewer than 2 fact-token matches
#      (scores like ``3-2``, ``5回``, ``X安打/打点/号/勝/敗`` etc.).
#   4. AI-scaffolding signal count is high: >= 3 rhetorical / general-column
#      phrases.
#
# Conservative by design — false positives skew toward routing to review/draft
# rather than refusing legitimate short-source reporting that has real facts.
_THIN_SOURCE_PADDING_MIN_TEXT_CHARS = 600
_THIN_SOURCE_PADDING_MAX_TEXT_CHARS = 3000
_THIN_SOURCE_PADDING_MIN_SCAFFOLDING = 3
_THIN_SOURCE_PADDING_MIN_FACT_TOKENS = 2

# Rhetorical / general-column phrases that pad out short-source articles.
_THIN_SOURCE_SCAFFOLDING_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"どう(?:見|思|捉|感じ)",
        r"(?:今後|次)(?:の|に)?(?:注目|展開|動向|焦点|期待|展望)",
        r"気になる(?:ポイント|ところ|点)",
        r"ご注目(?:ください|を)",
        r"ではないでしょうか",
        r"のではないか",
        r"と(?:言|い)える(?:でしょう|だろう)",
        r"と考えられ(?:ます|る)",
        r"と思われ(?:ます|る)",
        r"皆さん(?:は|も)",
        r"みなさん(?:は|も)",
        r"ファンの(?:皆さん|期待|反応|声)",
        r"楽しみ(?:です|ですね|にしたい)",
        r"これからの(?:活躍|戦い|展開)",
        r"今シーズン(?:の|も)(?:活躍|期待|注目)",
    )
)
# Quote markers count as scaffolding only if they are empty bracket pairs (a
# common 1-tweet-padding tell where AI invents framing without actual quote).
_EMPTY_QUOTE_PATTERN = re.compile(r"「\s*」")

# Concrete fact tokens that indicate real reporting density.
_FACT_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"[0-9０-９]+\s*[-－ー]\s*[0-9０-９]+",   # score
        r"[0-9０-９]+\s*安打",
        r"[0-9０-９]+\s*打点",
        r"[0-9０-９]+\s*打数",
        r"[0-9０-９]+\s*本塁打",
        r"第?[0-9０-９]+\s*号",
        r"[0-9０-９]+\s*勝[0-9０-９]*敗?",
        r"[0-9０-９]+\s*回(?:[1-9０-９/](?:1/3|2/3))?\s*(?:を投げ|を投球|投げ)",
        r"防御率\s*[0-9０-９]+\.[0-9０-９]+",
        r"打率\s*[\.\．]?[0-9０-９]+",
        r"中[0-9０-９]+日",
        r"イニング",
        r"ホームラン",
        r"タイムリー",
        r"先発出場",
        r"完投",
        r"完封",
        r"勝利投手|敗戦投手|セーブ|ホールド",
    )
)
# Non-empty 「...」 quote with substantive content also counts as fact token
# (real player comment quoted from source).
_REAL_QUOTE_PATTERN = re.compile(r"「[^」]{6,}」")


def _count_pattern_hits(text: str, patterns: tuple[re.Pattern[str], ...]) -> int:
    return sum(1 for p in patterns if p.search(text))


def _count_scaffolding_signals(text: str) -> int:
    count = _count_pattern_hits(text, _THIN_SOURCE_SCAFFOLDING_PATTERNS)
    if _EMPTY_QUOTE_PATTERN.search(text):
        count += 1
    return count


def _count_fact_tokens(text: str) -> int:
    count = _count_pattern_hits(text, _FACT_TOKEN_PATTERNS)
    if _REAL_QUOTE_PATTERN.search(text):
        count += 1
    return count


def _is_thin_source_padding(body_html: str, *, text: str, text_chars: int) -> bool:
    if text_chars < _THIN_SOURCE_PADDING_MIN_TEXT_CHARS:
        return False
    if text_chars > _THIN_SOURCE_PADDING_MAX_TEXT_CHARS:
        return False
    if not _OEMBED_DIV_RE.search(body_html):
        return False
    if _count_fact_tokens(text) >= _THIN_SOURCE_PADDING_MIN_FACT_TOKENS:
        return False
    if _count_scaffolding_signals(text) < _THIN_SOURCE_PADDING_MIN_SCAFFOLDING:
        return False
    return True


def _strip_html_to_text(html: str) -> str:
    """HTML タグ / script / comment / news-digest banner / fan-voice
    fallback block を除去して text content だけ返す。

    純粋な可視文字数測定用。形態素解析等はしない。News digest banner と
    ``💬 ファンの声（Xより）`` + ``<p>関連ポストなし</p>`` の fallback は
    chrome (出典 / 統一見出し / placeholder) であり body content では
    ないので、thin-body 判定の visible-char count からは除く。
    """
    if not html:
        return ""
    html = _NEWS_BANNER_RE.sub("", html)
    html = _FAN_VOICE_FALLBACK_RE.sub("", html)
    html = _SCRIPT_RE.sub("", html)
    html = _HTML_COMMENT_RE.sub("", html)
    html = _TAG_RE.sub("", html)
    return _WS_RE.sub(" ", html).strip()


def _is_postgame_scorecard_only(body_html: str, *, text_chars: int) -> bool:
    """Detect thin nomotoke postgame cards that are effectively scorecard-only.

    Narrow scope only:
    - nomotoke card footer present
    - score heading present
    - no detail sections (at-bat / pitching / opponent lineup)
    - closes with generic win/loss/draw sentence
    - overall visible text still short
    """
    return (
        bool(_NOMOTOKE_CARD_FOOTER_RE.search(body_html))
        and bool(_NOMOTOKE_CTA_ROW_RE.search(body_html))
        and bool(_POSTGAME_SCORE_HEADING_RE.search(body_html))
        and not bool(_POSTGAME_DETAIL_HEADING_RE.search(body_html))
        and bool(_POSTGAME_GENERIC_CLOSING_RE.search(body_html))
        and text_chars < _POSTGAME_SCORECARD_ONLY_MAX_TEXT_CHARS
    )


def is_thin_body(body_html: str) -> ThinBodyResult:
    """本文崩壊 (oembed-only incident pattern) を検出する。

    Returns ``ThinBodyResult(is_thin=True, reason=...)`` if body should be
    REJECTED from publish path.

    Detection (narrow):
      1. ``empty_body``: body_html が None / 空文字
      2. ``oembed_only_no_body``: ``yoshilover-x-embed`` div あり、
         ``<h3>`` なし、30+ chars text を含む ``<p>`` なし、HTML < 600 chars
      3. ``postgame_scorecard_only``: nomotoke postgame card で
         score table + generic closing しか無い thin body

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

    # Strip chrome (news banner + fan voice fallback h3) before checking
    # body structure markers — those are publish-time decorations and must
    # not rescue an otherwise-thin body from the thin-body gate.
    body_for_structure = _FAN_VOICE_FALLBACK_RE.sub(
        "", _NEWS_BANNER_RE.sub("", body_html)
    )
    has_oembed = bool(_OEMBED_DIV_RE.search(body_for_structure))
    has_h3 = bool(_HAS_H3_RE.search(body_for_structure))
    has_text_p = bool(_HAS_TEXT_P_RE.search(body_for_structure))

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

    if _is_postgame_scorecard_only(body_html, text_chars=text_chars):
        return ThinBodyResult(
            is_thin=True,
            reason="postgame_scorecard_only",
            text_chars=text_chars,
            html_chars=html_chars,
        )

    if _is_thin_source_padding(body_html, text=text, text_chars=text_chars):
        return ThinBodyResult(
            is_thin=True,
            reason="thin_source_padding",
            text_chars=text_chars,
            html_chars=html_chars,
        )

    return ThinBodyResult(
        is_thin=False,
        reason="ok",
        text_chars=text_chars,
        html_chars=html_chars,
    )
