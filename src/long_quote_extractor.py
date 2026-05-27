"""Long quote extractor for X-post comment candidates (ticket 438 Phase 2).

source article HTML body から「」 で囲まれた長 quote を抽出する。
Pattern B (brand_quote) で画像 overlay text として使う。

設計:
- HTML から <script> / <style> / tag を剥がして plain text 化
- 「...」 segment を全部抽出
- 60-180 字に収まる最長 quote を選ぶ
- 60 字未満は短すぎ → 不採用 (Pattern A フォールバック)
- 180 字超過は 「。」 / 「、」 境界で truncate (末尾「…」 禁止 = literal violation)
- ネスト quote (「外『内』外」) は外側の「」 のみ対象
"""

from __future__ import annotations

import re as _re
from typing import Iterable


_DEFAULT_MIN_CHARS = 60
_DEFAULT_MAX_CHARS = 180

# 「」 のみ抽出 (『』 はネストとみなして対象外)。 ネスト無し前提で内側 chars を取る。
_QUOTE_PATTERN = _re.compile(r"「([^「」]+)」")

# HTML cleaning: <script> / <style> ブロックを丸ごと除去
_SCRIPT_RE = _re.compile(r"<script[^>]*>.*?</script>", _re.IGNORECASE | _re.DOTALL)
_STYLE_RE = _re.compile(r"<style[^>]*>.*?</style>", _re.IGNORECASE | _re.DOTALL)
_TAG_RE = _re.compile(r"<[^>]+>")
_WHITESPACE_RE = _re.compile(r"\s+")


def extract_long_quote(
    text: str,
    *,
    min_chars: int = _DEFAULT_MIN_CHARS,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """plain text or HTML から最長の「」 quote 内容を取り出す.

    入力が HTML なら自動で tag 剥がし → quote 抽出。 plain text でもそのまま動く。
    返り値は **「」 を含まない** 内側の string。 caller 側で「」 を再付与する。

    成立条件:
    - 抽出した最長 quote が ``min_chars`` 以上
    - 180 字超過時は ``max_chars`` 以下に句読点境界で truncate

    成立しない時は "" を返す (caller 側 Pattern A フォールバック)。
    """
    if not isinstance(text, str) or not text:
        return ""
    plain = _strip_html_to_plain(text)
    if not plain:
        return ""
    candidates = _QUOTE_PATTERN.findall(plain)
    if not candidates:
        return ""
    # 「」 内の前後 whitespace を整理
    cleaned: list[str] = []
    for q in candidates:
        normalized = _WHITESPACE_RE.sub(" ", q).strip()
        if normalized:
            cleaned.append(normalized)
    if not cleaned:
        return ""
    # 長さ降順で見て、 最初に min_chars 以上のものを採用
    cleaned.sort(key=len, reverse=True)
    for candidate in cleaned:
        if len(candidate) < min_chars:
            return ""  # 最長 < min → どれも届かない
        if len(candidate) <= max_chars:
            return candidate
        truncated = _truncate_at_sentence_boundary(candidate, max_chars, min_chars)
        if truncated:
            return truncated
    return ""


def _strip_html_to_plain(text: str) -> str:
    """HTML から <script> / <style> / 全 tag を取り除いて plain text 化."""
    if "<" not in text:
        return text
    s = _SCRIPT_RE.sub(" ", text)
    s = _STYLE_RE.sub(" ", s)
    s = _TAG_RE.sub(" ", s)
    # HTML entity を最小限デコード (& 系)。 fully unescape は本 module の責任外。
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return s


def _truncate_at_sentence_boundary(text: str, max_chars: int, min_chars: int) -> str:
    """text を max_chars 以下に切り詰める. 「。」 / 「、」 の最も後ろの位置で cut.

    末尾「…」 は禁止 (literal 引用 violation)。 句読点が見つからない場合は
    max_chars 位置で literal cut (末尾「、」「。」 になる確率高い)。
    min_chars 未満になる cut は採用しない (短すぎる)。
    """
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    last_period = head.rfind("。")
    last_comma = head.rfind("、")
    boundary = max(last_period, last_comma)
    if boundary >= min_chars - 1:
        # 句読点まで含めて cut
        return head[: boundary + 1]
    # 句読点が短すぎる位置にしかない → literal cut (改変は避け、 自然境界)
    return head


__all__ = ["extract_long_quote"]
