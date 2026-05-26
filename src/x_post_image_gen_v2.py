"""437 Phase 2: Pillow-based X-post image generator.

cairosvg + 12 SVG template の Phase 1 path (e90fcfa で WP eyecatch attach 廃止)
の代替として、 Pillow + IPAGothic で 1080x1080 PNG を直接描画する。

廃止理由: cairosvg は container 内 font fallback chain で CJK glyph を解決できず
日本語 tofu (post 72079 / 72076) を引き起こした。 Pillow は TTF を file path で
直接読むため、 OS font config に依存せず CJK 描画が確実。

scope (Phase 2A): ranking_table 1 layout production-quality。 残りの 11 template と
format auto-routing は後続 Phase で追加。
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SIZE = 1080
PNG_MAX_BYTES = 500 * 1024  # 500KB — X / WP 帯域圧迫を回避
DEFAULT_FOOTER_HANDLE = "@yoshilover_giants"
DEFAULT_FOOTER_META = "巨人データ"

# CJK 描画が確実な TTF を優先順に探索する。 production の Cloud Run image は
# `fonts-ipafont-gothic` を apt install してこの path を保証する (Phase 2D)。
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)

# brand palette (2026-05-25 user lock)
COLOR_BG = "#ffffff"
COLOR_BLACK = "#000000"
COLOR_HEADER_TOP = "#FF7A1A"
COLOR_HEADER_BOT = "#D84315"
COLOR_GIANTS_ROW_LEFT = "#FF6F00"
COLOR_GIANTS_ROW_RIGHT = "#F57C00"
COLOR_GOLD = "#FFD700"
COLOR_WHITE = "#ffffff"
COLOR_GRAY_ROW_SEP = "#e0e0e0"
COLOR_GRAY_RANK = "#bbbbbb"
COLOR_GRAY_TEAM = "#888888"


def _find_font(size: int):
    """CJK 描画可能な TrueType font を探して返す。

    Returns:
        (PIL.ImageFont.FreeTypeFont, path str) on success.

    Raises:
        RuntimeError: 候補 path に CJK font が 1 つもない場合。
            (Cloud Run image の Dockerfile で apt install fonts-ipafont-gothic
            が抜けたケースを即検出する。)
    """
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, size=size)
            return font, path
        except (OSError, IOError):
            continue
    raise RuntimeError(
        f"No CJK font available. Searched: {FONT_CANDIDATES}. "
        "Install `fonts-ipafont-gothic` or `fonts-noto-cjk` in the runtime image."
    )


def _make_vertical_gradient(width: int, height: int, top_hex: str, bot_hex: str):
    """top_hex → bot_hex の縦方向 linear gradient PIL Image を返す。"""
    from PIL import Image

    top = _hex_to_rgb(top_hex)
    bot = _hex_to_rgb(bot_hex)
    img = Image.new("RGB", (width, height), top)
    pixels = img.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(width):
            pixels[x, y] = (r, g, b)
    return img


def _make_horizontal_gradient(width: int, height: int, left_hex: str, right_hex: str):
    """left_hex → right_hex の横方向 linear gradient PIL Image を返す。"""
    from PIL import Image

    left = _hex_to_rgb(left_hex)
    right = _hex_to_rgb(right_hex)
    img = Image.new("RGB", (width, height), left)
    pixels = img.load()
    for x in range(width):
        t = x / max(width - 1, 1)
        r = int(left[0] + (right[0] - left[0]) * t)
        g = int(left[1] + (right[1] - left[1]) * t)
        b = int(left[2] + (right[2] - left[2]) * t)
        for y in range(height):
            pixels[x, y] = (r, g, b)
    return img


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _draw_row_drop_shadow(canvas, rect_xy: tuple[int, int, int, int], blur: int = 8):
    """rect 領域の真下に黒系 drop shadow を加える (巨人 row 立体感)。"""
    from PIL import Image, ImageDraw, ImageFilter

    x1, y1, x2, y2 = rect_xy
    pad = blur * 2
    w = (x2 - x1) + pad * 2
    h = (y2 - y1) + pad * 2
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rectangle((pad, pad, pad + (x2 - x1), pad + (y2 - y1)), fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=blur))
    canvas.alpha_composite(shadow, dest=(x1 - pad + 2, y1 - pad + 3))


def _render_ranking_table(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """ranking_table data dict → PIL RGBA Image (1080x1080)。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)

    # 上 黒 stripe (14px) + header gradient (240px) + 下 黒 stripe (8px)
    top_stripe = Image.new("RGB", (size, 14), COLOR_BLACK)
    canvas.paste(top_stripe, (0, 0))

    header_grad = _make_vertical_gradient(size, 240, COLOR_HEADER_TOP, COLOR_HEADER_BOT)
    canvas.paste(header_grad, (0, 14))

    below_header_stripe = Image.new("RGB", (size, 8), COLOR_BLACK)
    canvas.paste(below_header_stripe, (0, 254))

    draw = ImageDraw.Draw(canvas)

    # hook_line (金、 中央、 y=115 baseline 相当 → top y ≈ 95)
    hook_line = str(data.get("hook_line", ""))
    if hook_line:
        font_hook, _ = _find_font(size=42)
        draw.text(
            (size // 2, 115),
            hook_line,
            font=font_hook,
            fill=COLOR_GOLD,
            anchor="ms",
            stroke_width=2,
            stroke_fill=COLOR_GOLD,
        )

    # title (白、 中央、 y=195)
    title = str(data.get("title", ""))
    if title:
        font_title, _ = _find_font(size=74)
        draw.text(
            (size // 2, 195),
            title,
            font=font_title,
            fill=COLOR_WHITE,
            anchor="ms",
            stroke_width=2,
            stroke_fill=COLOR_WHITE,
        )

    # subtitle (白、 中央、 y=235)
    subtitle = str(data.get("subtitle", ""))
    if subtitle:
        font_sub, _ = _find_font(size=30)
        draw.text(
            (size // 2, 235),
            subtitle,
            font=font_sub,
            fill=COLOR_WHITE,
            anchor="ms",
        )

    # rows (8 row 想定、 step 85px、 y_base = 345 + i * 85)
    rows = data.get("rows", []) or []
    for i, row in enumerate(rows):
        y_base = 345 + i * 85
        if row.get("is_giants"):
            # 巨人 row: drop shadow + orange row gradient + 金 star + 白文字
            rect = (40, y_base - 60, 1040, y_base + 20)
            _draw_row_drop_shadow(canvas, rect, blur=8)
            row_grad = _make_horizontal_gradient(
                1000, 80, COLOR_GIANTS_ROW_LEFT, COLOR_GIANTS_ROW_RIGHT
            )
            canvas.paste(row_grad, (40, y_base - 60))
            draw = ImageDraw.Draw(canvas)  # reattach after paste

            # rank (金、 中央 x=100、 y=y_base+5 baseline)
            font_rank = _find_font(size=60)[0]
            draw.text(
                (100, y_base + 5),
                str(row.get("rank", "")),
                font=font_rank,
                fill=COLOR_GOLD,
                anchor="ms",
                stroke_width=2,
                stroke_fill=COLOR_GOLD,
            )

            # name + ★ (白 + 金 ★、 left-anchor x=180、 y=y_base-10)
            font_name = _find_font(size=50)[0]
            name_text = str(row.get("name", ""))
            draw.text(
                (180, y_base - 10),
                name_text,
                font=font_name,
                fill=COLOR_WHITE,
                anchor="ls",
                stroke_width=2,
                stroke_fill=COLOR_WHITE,
            )
            name_bbox = draw.textbbox((180, y_base - 10), name_text, font=font_name, anchor="ls")
            star_x = name_bbox[2] + 12
            draw.text(
                (star_x, y_base - 10),
                "★",
                font=font_name,
                fill=COLOR_GOLD,
                anchor="ls",
                stroke_width=2,
                stroke_fill=COLOR_GOLD,
            )

            # team (金、 x=180、 y=y_base+20)
            font_team = _find_font(size=22)[0]
            draw.text(
                (180, y_base + 20),
                str(row.get("team", "")),
                font=font_team,
                fill=COLOR_GOLD,
                anchor="ls",
                stroke_width=1,
                stroke_fill=COLOR_GOLD,
            )

            # value (白、 right-anchor x=1020、 y=y_base+10)
            font_value = _find_font(size=76)[0]
            draw.text(
                (1020, y_base + 10),
                str(row.get("value", "")),
                font=font_value,
                fill=COLOR_WHITE,
                anchor="rs",
                stroke_width=2,
                stroke_fill=COLOR_WHITE,
            )
        else:
            # 非巨人 row: 細い separator + 灰 rank + 黒 name
            draw.line(
                [(60, y_base - 65), (1020, y_base - 65)],
                fill=COLOR_GRAY_ROW_SEP,
                width=2,
            )
            font_rank = _find_font(size=56)[0]
            draw.text(
                (100, y_base),
                str(row.get("rank", "")),
                font=font_rank,
                fill=COLOR_GRAY_RANK,
                anchor="ms",
                stroke_width=1,
                stroke_fill=COLOR_GRAY_RANK,
            )

            font_name = _find_font(size=40)[0]
            draw.text(
                (180, y_base),
                str(row.get("name", "")),
                font=font_name,
                fill=COLOR_BLACK,
                anchor="ls",
                stroke_width=1,
                stroke_fill=COLOR_BLACK,
            )

            font_team = _find_font(size=22)[0]
            draw.text(
                (180, y_base + 30),
                str(row.get("team", "")),
                font=font_team,
                fill=COLOR_GRAY_TEAM,
                anchor="ls",
            )

            font_value = _find_font(size=68)[0]
            draw.text(
                (1020, y_base + 5),
                str(row.get("value", "")),
                font=font_value,
                fill=COLOR_BLACK,
                anchor="rs",
                stroke_width=2,
                stroke_fill=COLOR_BLACK,
            )

    # footer (handle = orange、 meta = 灰)
    footer_handle = str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE))
    footer_meta = str(data.get("footer_meta", DEFAULT_FOOTER_META))
    font_handle = _find_font(size=26)[0]
    draw.text(
        (size // 2, 1035),
        footer_handle,
        font=font_handle,
        fill=COLOR_GIANTS_ROW_LEFT,
        anchor="ms",
        stroke_width=1,
        stroke_fill=COLOR_GIANTS_ROW_LEFT,
    )
    font_meta = _find_font(size=20)[0]
    draw.text(
        (size // 2, 1065),
        footer_meta,
        font=font_meta,
        fill=COLOR_GRAY_TEAM,
        anchor="ms",
    )

    return canvas


def _pillow_image_to_png_bytes(img, size: int) -> bytes:
    """RGBA → RGB に flatten した PNG bytes を返す (X / WP の alpha 非対応回避)。"""
    from PIL import Image

    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, COLOR_BG)
        background.paste(img, mask=img.split()[3])
        img = background
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_png(
    template_key: str,
    data: dict[str, Any],
    size: int = DEFAULT_SIZE,
) -> bytes | None:
    """Pillow + CJK font で PNG bytes を生成する entry point。

    Phase 2A scope: template_key="ranking_table" のみ実装。 他 key は将来追加。

    Args:
        template_key: "ranking_table" など。
        data: build_ranking_data() の出力。
        size: PNG 出力 size (default 1080x1080)。

    Returns:
        PNG bytes on success, None on any failure (caller fallback)。
    """
    try:
        if template_key != "ranking_table":
            logger.warning(
                "[437v2] generate_png unknown template_key=%s (Phase 2A: ranking_table only)",
                template_key,
            )
            return None
        img = _render_ranking_table(data, size=size)
        png_bytes = _pillow_image_to_png_bytes(img, size=size)
    except Exception as exc:
        logger.warning(
            "[437v2] generate_png failed template=%s error=%s", template_key, exc
        )
        return None
    if not png_bytes:
        logger.warning("[437v2] generate_png empty bytes template=%s", template_key)
        return None
    if len(png_bytes) > PNG_MAX_BYTES:
        logger.warning(
            "[437v2] generate_png size exceeded template=%s bytes=%d max=%d",
            template_key,
            len(png_bytes),
            PNG_MAX_BYTES,
        )
        return None
    return png_bytes


def build_ranking_data(
    *,
    title: str,
    subtitle: str,
    hook_line: str,
    rows: list[dict[str, Any]],
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    """ranking_table 用 data dict を組む helper (v1 と同 shape)。"""
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "rows": rows,
        "footer_handle": footer_handle,
        "footer_meta": footer_meta,
    }
