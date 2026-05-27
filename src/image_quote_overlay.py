"""Pillow text overlay for brand_quote pattern (ticket 438 Phase 2).

source 媒体写真の上に 人物名 + 「literal long quote」 を焼き込む。

設計 (user lock 2026-05-27):
- 枠 / band / brand mark なし
- 写真の native aspect / size を保持
- text は 写真下半分に white + stroke (black outline) で配置
- 人物名は bold 大、「quote」 は bold 中。 改行は文字単位 (日本語前提)
- 句読点禁則は最低限 ( 「 や 」 が行頭・行末に来るのは許容、 強制改行のみ)
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional


LOG = logging.getLogger(__name__)


_DEFAULT_BOTTOM_MARGIN_RATIO = 0.05
_DEFAULT_SIDE_MARGIN_RATIO = 0.045
_SPEAKER_SIZE_RATIO = 0.052  # 画像 width に対する 人物名 font size 比
_QUOTE_SIZE_RATIO = 0.044    # 画像 width に対する 「quote」 font size 比
_MIN_SPEAKER_SIZE = 32
_MAX_SPEAKER_SIZE = 84
_MIN_QUOTE_SIZE = 28
_MAX_QUOTE_SIZE = 64
_SPEAKER_QUOTE_GAP_PX = 24
_LINE_SPACING_PX = 10
_STROKE_WIDTH_SPEAKER = 4
_STROKE_WIDTH_QUOTE = 3


def apply_quote_overlay(
    image_bytes: bytes,
    *,
    speaker: str,
    quote: str,
    logger: Optional[logging.Logger] = None,
) -> bytes:
    """``image_bytes`` の写真の下半分に ``speaker`` + 「``quote``」 を overlay 焼き込み.

    Returns:
        PNG bytes (改変済画像)。 source の aspect / size はそのまま保持。

    Raises:
        ImportError: Pillow / font が利用できない時
        ValueError: 入力 bytes が画像として開けない時
    """
    log = logger or LOG
    if not image_bytes:
        raise ValueError("empty image_bytes")
    if not speaker or not quote:
        raise ValueError("speaker and quote must both be non-empty")

    try:
        from PIL import Image, ImageDraw  # type: ignore[import-untyped]
    except Exception as exc:  # noqa: BLE001
        raise ImportError(f"Pillow not available: {exc!r}") from exc

    try:
        from src.x_post_image_gen_v2 import _find_font  # 既存 437 CJK font lookup を流用
    except Exception as exc:  # noqa: BLE001
        raise ImportError(f"font lookup not available: {exc!r}") from exc

    try:
        img = Image.open(BytesIO(image_bytes))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"image open failed: {exc!r}") from exc

    # RGBA → RGB に正規化 (JPEG / PNG どちらも統一)
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size

    # font sizes scaled to image width, bounded
    speaker_size = max(_MIN_SPEAKER_SIZE, min(int(w * _SPEAKER_SIZE_RATIO), _MAX_SPEAKER_SIZE))
    quote_size = max(_MIN_QUOTE_SIZE, min(int(w * _QUOTE_SIZE_RATIO), _MAX_QUOTE_SIZE))

    speaker_font, _ = _find_font(speaker_size)
    quote_font, _ = _find_font(quote_size)

    # text 折り返し
    side_margin = max(40, int(w * _DEFAULT_SIDE_MARGIN_RATIO))
    bottom_margin = max(40, int(h * _DEFAULT_BOTTOM_MARGIN_RATIO))
    available_width = w - 2 * side_margin

    quote_text = f"「{quote}」"
    quote_lines = _wrap_text_by_pixel_width(quote_text, quote_font, available_width)

    # 縦位置計算 (bottom から積み上げ)
    quote_line_height = quote_size + _LINE_SPACING_PX
    total_quote_height = quote_line_height * len(quote_lines)
    total_block_height = speaker_size + _SPEAKER_QUOTE_GAP_PX + total_quote_height

    # text block top の y 座標
    y_top = h - bottom_margin - total_block_height
    # bottom margin が image 高さに対して大きすぎる場合、 image 上端を超えてしまう
    # → side margin / font size を縮小する選択もあるが、 V1 は 上端 clamp で対処
    if y_top < bottom_margin // 2:
        # image が小さすぎ → 描画断念して raise (caller 側で Pattern A fallback)
        raise ValueError(
            f"image too small for quote overlay: image={w}x{h}, block_h={total_block_height}"
        )

    draw = ImageDraw.Draw(img)

    # speaker (top of block)
    draw.text(
        (side_margin, y_top),
        speaker,
        font=speaker_font,
        fill="white",
        stroke_width=_STROKE_WIDTH_SPEAKER,
        stroke_fill="black",
    )

    y = y_top + speaker_size + _SPEAKER_QUOTE_GAP_PX
    for line in quote_lines:
        draw.text(
            (side_margin, y),
            line,
            font=quote_font,
            fill="white",
            stroke_width=_STROKE_WIDTH_QUOTE,
            stroke_fill="black",
        )
        y += quote_line_height

    out = BytesIO()
    img.save(out, format="PNG", optimize=False)
    result = out.getvalue()
    log.info(
        "image_quote_overlay_applied image=%dx%d speaker=%s quote_len=%d lines=%d out_bytes=%d",
        w, h, speaker, len(quote), len(quote_lines), len(result),
    )
    return result


def _wrap_text_by_pixel_width(text: str, font, max_width: int) -> list[str]:
    """日本語 text を pixel width で折り返し. 文字単位で wrap。

    句読点禁則 (「」 単独行頭・行末) は最低限の調整のみ実施。
    """
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        try:
            bbox = font.getbbox(candidate)
            width = bbox[2] - bbox[0]
        except Exception:  # noqa: BLE001
            width = len(candidate) * 20  # fallback rough estimate
        if width > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


__all__ = ["apply_quote_overlay"]
