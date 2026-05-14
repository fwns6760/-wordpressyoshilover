"""344-INGEST Phase 1a: YouTube 字幕 fetch wrapper.

`youtube-transcript-api` を使って公開字幕 (auto-generated 含む) を pull。
LLM 不使用、try/except 個別隔離で main flow を絶対に壊さない設計。

著作権: 引用法 32 条範囲内 (literal 600-1500字 + 出典明示 + oEmbed 併設)
を caller 側で担保。本 module は raw text を返すだけ。
"""

from __future__ import annotations

import logging
import re
from typing import Iterable


_DEFAULT_LANGS: tuple[str, ...] = ("ja", "ja-JP", "en")
_MIN_CAPTION_LEN = 30
_DEFAULT_MAX_CHARS = 600


def fetch_youtube_caption(
    video_id: str,
    *,
    languages: Iterable[str] = _DEFAULT_LANGS,
    max_chars: int = _DEFAULT_MAX_CHARS,
    logger: logging.Logger | None = None,
) -> str:
    """指定動画の字幕 text を返す。失敗時は空文字 (例外で main flow を壊さない)。

    - languages 順に caption を試行 (Japanese 優先、無ければ英語 fallback)
    - 各 segment の text を join + whitespace 正規化
    - max_chars で trim (sentence boundary を尊重)
    - lib import / fetch 例外は warning log + 空文字
    """
    if not video_id:
        return ""
    log = logger or logging.getLogger("youtube_caption_fetcher")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        log.warning("youtube_transcript_api import failed: %s", exc)
        return ""

    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=tuple(languages))
    except Exception as exc:  # noqa: BLE001 — 主に NoTranscriptFound / TranscriptsDisabled / RequestBlocked / network error
        log.info(
            "youtube_caption_unavailable video_id=%s err=%s",
            video_id,
            type(exc).__name__,
        )
        return ""

    try:
        segments = list(fetched)
    except Exception as exc:  # noqa: BLE001
        log.warning("youtube_caption_iter_failed video_id=%s err=%s", video_id, exc)
        return ""

    text = _join_caption_segments(segments)
    if len(text) < _MIN_CAPTION_LEN:
        return ""
    return _trim_to_max_chars(text, max_chars)


def _join_caption_segments(segments) -> str:
    """字幕 segment list を 1 string に join、whitespace 正規化。"""
    parts: list[str] = []
    for seg in segments:
        text = ""
        if hasattr(seg, "text"):
            text = str(seg.text or "")
        elif isinstance(seg, dict):
            text = str(seg.get("text") or "")
        if not text:
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _trim_to_max_chars(text: str, max_chars: int) -> str:
    """max_chars 以下に trim、sentence boundary (。！？) で natural break 試行。"""
    if not text or len(text) <= max_chars:
        return text
    head = text[:max_chars]
    for sep in ("。", "！", "？", ".", "!"):
        idx = head.rfind(sep)
        if idx >= max_chars // 2:
            return head[: idx + 1]
    return head
