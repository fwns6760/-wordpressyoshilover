"""377-OPS Phase 1C: mail body_excerpt + admin_edit_url builder.

PublishNoticeRequest.body_excerpt / .admin_edit_url を populate するための純関数。
scanner / email_sender の各 PublishNoticeRequest 構築箇所から呼ばれる。

Why: mail card に本文 600-1000 字 + WP admin 編集 link を出すことで、 user が mail 本文を
読んで draft → publish 判断できるようにする (CLAUDE.md 377-OPS / GH #51)。
"""

from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
# 段落境界 (block-level closing tag) を改行 marker に置換するため。
_BLOCK_CLOSE_RE = re.compile(
    r"(?is)</\s*(?:p|h[1-6]|div|li|blockquote|tr|td|article|section)\s*>"
)
# 単独 <br> も改行 marker に。
_BR_RE = re.compile(r"(?is)<br\s*/?>")
# 行内の空白圧縮 (改行は残す)。
_INLINE_WS_RE = re.compile(r"[ \t]+")
# 改行周りの余白 / 3 連以上の改行を 2 改行 (= 1 空行) に圧縮。
_NEWLINE_TRIM_RE = re.compile(r"[ \t]*\n[ \t]*")
_NEWLINE_COLLAPSE_RE = re.compile(r"\n{3,}")

_SCRIPT_STYLE_BLOCK_RE = re.compile(
    r"(?is)<(?P<tag>script|style)\b[^>]*>.*?</(?P=tag)>"
)

_TWITTER_TWEET_BLOCK_RE = re.compile(
    r'(?is)<blockquote\b[^>]*class=["\'][^"\']*twitter-tweet[^"\']*["\'][^>]*>.*?</blockquote>'
)

_RELATED_POSTS_BLOCK_RE = re.compile(
    r'(?is)<div\b[^>]*class=["\'][^"\']*yoshilover-related-posts[^"\']*["\'][^>]*>.*?</div>'
)

# Why: section header の literal を bounded で列挙し、 `\S*` greedy 化による
#      `</(?P=htag)>` backtrack 越境を防ぐ (Python re engine の挙動)。
_SECTION_LABEL_ALTERNATIVES = (
    r"ファンの声|ファン反応|X反応|SNSの声|ポストまとめ|反響|関連記事|【関連記事】"
)

# Why: <h2>💬 ファンの声</h2> 以降を 次の <h2-6> まで section ごと削除して mail の visual ノイズを減らす。
#      `\Z` alternation を入れると lazy `.*?` が end まで膨らむ Python re engine の挙動を踏まえ、
#      「次 heading まで削除」と「末尾まで削除」の 2 pass に分ける。
_FAN_VOICE_SECTION_TO_NEXT_HEADING_RE = re.compile(
    r"(?is)<(?P<htag>h[1-6])\b[^>]*>"
    rf"\s*(?:💬\s*)?(?:{_SECTION_LABEL_ALTERNATIVES})\s*"
    r"</(?P=htag)>"
    r".*?(?=<h[1-6]\b)"
)
_FAN_VOICE_SECTION_TO_END_RE = re.compile(
    r"(?is)<(?P<htag>h[1-6])\b[^>]*>"
    rf"\s*(?:💬\s*)?(?:{_SECTION_LABEL_ALTERNATIVES})\s*"
    r"</(?P=htag)>"
    r".*\Z"
)

# Why: HTML strip 後に残る先頭 label を 1 度だけ落として「本文」から始める。
_LEADING_LABEL_RE = re.compile(
    rf"(?is)^\s*(?:💬\s*)?(?:{_SECTION_LABEL_ALTERNATIVES})\s*"
)

_DEFAULT_MAX_CHARS = 1000
_MIN_USEFUL_CHARS = 1


def build_admin_edit_url(
    post_id: int | str | None,
    wp_base_url: str | None,
) -> str | None:
    """WP admin の post edit screen URL を組み立てる。

    Format: ``{wp_base_url}/wp-admin/post.php?post={post_id}&action=edit``
    Why: mail card に「編集 / 公開」link として出す。 user の WP login cookie で即 publish に進む。

    Returns ``None`` for invalid input (missing base url / 不正 post_id) — caller は None なら
    link を出さず minimal mode のまま続行する fail-open 設計。
    """
    if post_id is None or wp_base_url is None:
        return None
    try:
        pid = int(str(post_id).strip())
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    base = str(wp_base_url).strip().rstrip("/")
    if not base:
        return None
    return f"{base}/wp-admin/post.php?post={pid}&action=edit"


def build_body_excerpt(
    body_html: str | None,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str | None:
    """記事本文 (HTML or plain text) から mail 用 plain text excerpt を作る。

    手順:
      1. ``<script>`` / ``<style>`` block を削除
      2. ``<blockquote class="twitter-tweet">`` 埋め込み (X embed) を削除
      3. ``yoshilover-related-posts`` div を削除
      4. ``💬 ファンの声`` / ``関連記事`` heading 以降を次 heading まで section ごと削除
      5. HTML tag を strip、 entity を unescape、 whitespace を collapse
      6. 先頭に残る label (``💬 ファンの声`` 等) を 1 度落とす
      7. ``max_chars`` 超過時は末尾 ``…`` で truncate

    Returns ``None`` if input is None / empty / 全 strip 後 0 字。
    """
    if body_html is None:
        return None
    text = str(body_html)
    if not text.strip():
        return None
    text = _SCRIPT_STYLE_BLOCK_RE.sub("", text)
    text = _TWITTER_TWEET_BLOCK_RE.sub("", text)
    text = _RELATED_POSTS_BLOCK_RE.sub("", text)
    text = _FAN_VOICE_SECTION_TO_NEXT_HEADING_RE.sub("", text)
    text = _FAN_VOICE_SECTION_TO_END_RE.sub("", text)
    # 段落構造を保持: block-level 終了タグ → 2 改行 (= 1 空行)、 <br> → 1 改行。
    text = _BLOCK_CLOSE_RE.sub("\n\n", text)
    text = _BR_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", html.unescape(text))
    # 行内空白圧縮 → 改行周り trim → 3 連改行を 2 連に圧縮。
    text = _INLINE_WS_RE.sub(" ", text)
    text = _NEWLINE_TRIM_RE.sub("\n", text)
    text = _NEWLINE_COLLAPSE_RE.sub("\n\n", text).strip()
    text = _LEADING_LABEL_RE.sub("", text).strip()
    if len(text) < _MIN_USEFUL_CHARS:
        return None
    if max_chars and len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


__all__ = ["build_admin_edit_url", "build_body_excerpt"]
