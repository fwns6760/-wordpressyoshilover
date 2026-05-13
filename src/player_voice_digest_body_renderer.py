"""Body renderer for player_voice_digest subtype (334-QA Phase 3).

`subtype_hint="player_voice_digest"` + `digest_cluster_payload` を持つ candidate
を入力に、HTML body を出力する。

出力 sections:
  1. Opener: 選手名「full quote (80-150 字 literal、parent body から抜粋)」
  2. 地の文: 3-5 lead sentences from parent body (literal、quote 除外)
  3. Section A 【🌐 各社が伝える】: children list (家族別の見出し + リンク)
  4. Section B 【📣 公式が発表】: officials list (任意、無ければ omit)

すべて literal、AI / LLM rewrite 一切なし。
HTML escape (html.escape) で XSS 対策。
section data が無い場合は section ごと omit。
candidate が digest subtype でなければ空文字。
"""

from __future__ import annotations

import html
import re
from typing import Any, Mapping, Sequence


_QUOTE_RE = re.compile(r"[「『]([^」』]+)[」』]")
_SENTENCE_RE = re.compile(r"([^。！？]+[。！？])")


def render_player_voice_digest_body(
    candidate: Mapping[str, Any],
    *,
    body_quote_min: int = 80,
    body_quote_max: int = 150,
    max_lead_sentences: int = 5,
    min_lead_sentence_chars: int = 5,
) -> str:
    """Render HTML body for player_voice_digest candidate.

    candidate が `subtype_hint != "player_voice_digest"` か、`digest_cluster_payload`
    が無いか、`player_name` が空なら、空文字 ("") を返す。caller は normal body
    flow に fallback する想定。
    """
    if str(candidate.get("subtype_hint") or "").strip() != "player_voice_digest":
        return ""
    payload = candidate.get("digest_cluster_payload")
    if not isinstance(payload, Mapping):
        return ""
    player_name = str(payload.get("player_name") or "").strip()
    if not player_name:
        return ""

    body_text = str(
        candidate.get("body") or candidate.get("summary") or ""
    ).strip()
    body_quote = _extract_long_quote(body_text, body_quote_min, body_quote_max)
    lead = _extract_lead_sentences(
        body_text,
        max_sentences=max_lead_sentences,
        exclude_substr=body_quote,
        min_sentence_chars=min_lead_sentence_chars,
    )

    parts: list[str] = []
    if body_quote:
        parts.append(
            f"<p><strong>{html.escape(player_name)}</strong>"
            f"「{html.escape(body_quote)}」</p>"
        )
    else:
        parts.append(f"<p><strong>{html.escape(player_name)}</strong></p>")

    for sentence in lead:
        parts.append(f"<p>{html.escape(sentence)}</p>")

    children = payload.get("children") or ()
    section_a = _render_section_a(children)
    if section_a:
        parts.append(section_a)

    officials = payload.get("officials") or ()
    section_b = _render_section_b(officials)
    if section_b:
        parts.append(section_b)

    return "\n".join(parts)


def _extract_long_quote(text: str, min_len: int, max_len: int) -> str:
    """Return first literal quote that fits [min_len, max_len]。

    全長が範囲内ならそのまま。max_len 超過なら、句読点で natural break して
    [min_len, max_len] に収まる substring を採用。範囲内に納まらなければ空文字。
    """
    if not text:
        return ""
    for m in _QUOTE_RE.finditer(text):
        inner = m.group(1).strip().rstrip("。、")
        if min_len <= len(inner) <= max_len:
            return inner
        if len(inner) > max_len:
            head = inner[:max_len]
            for sep in ("。", "！", "？"):
                idx = head.rfind(sep)
                if idx >= min_len - 1:
                    return head[: idx + 1].rstrip("。、")
    return ""


def _extract_lead_sentences(
    text: str,
    *,
    max_sentences: int,
    exclude_substr: str = "",
    min_sentence_chars: int,
) -> list[str]:
    """body から「」 quote を除去した上で、句点 / 感嘆符 / 疑問符 区切りで
    sentence を取り出し、先頭から最大 max_sentences 件返す。exclude_substr を
    含む sentence と min_sentence_chars 未満の短い sentence は skip。
    """
    if not text:
        return []
    text_no_quotes = _QUOTE_RE.sub("", text)
    sentences: list[str] = []
    for m in _SENTENCE_RE.finditer(text_no_quotes):
        sentence = m.group(1).strip()
        if not sentence or len(sentence) < min_sentence_chars:
            continue
        if exclude_substr and exclude_substr in sentence:
            continue
        sentences.append(sentence)
        if len(sentences) >= max_sentences:
            break
    return sentences


def _render_section_a(children: Sequence[Mapping[str, Any]]) -> str:
    items = _render_source_items(children)
    if not items:
        return ""
    return "<h3>🌐 各社が伝える</h3>\n<ul>\n" + "\n".join(items) + "\n</ul>"


def _render_section_b(officials: Sequence[Mapping[str, Any]]) -> str:
    items = _render_source_items(officials)
    if not items:
        return ""
    return "<h3>📣 公式が発表</h3>\n<ul>\n" + "\n".join(items) + "\n</ul>"


def _render_source_items(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    items: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        label = str(entry.get("label") or "").strip()
        snippet = str(entry.get("snippet") or "").strip()
        url = str(entry.get("url") or "").strip()
        if not label or not snippet or not url:
            continue
        items.append(
            f"<li><strong>{html.escape(label)}</strong>"
            f"「{html.escape(snippet)}」 "
            f'<a href="{html.escape(url)}" target="_blank" rel="noopener">'
            f"元記事</a></li>"
        )
    return items


__all__ = ["render_player_voice_digest_body"]
