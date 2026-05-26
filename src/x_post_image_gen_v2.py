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
# `fonts-noto-cjk` (実 bold 字形) を主、 `fonts-ipafont-gothic` を fallback と
# して apt install する (Phase 2D)。 Noto Sans CJK JP Bold が見つかれば真の
# bold 字形になり、 stroke_width fake-bold (IPAGothic 用) を抑える。
FONT_CANDIDATES_BOLD = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
)
FONT_CANDIDATES_REGULAR = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)
FONT_CANDIDATES = FONT_CANDIDATES_BOLD + FONT_CANDIDATES_REGULAR

# 🔥 / 🏆 / ⚾ など Unicode 1F000+ の color emoji を tofu させないため、
# 別 font (Noto Color Emoji) を fallback として保持する。 emoji codepoint だけ
# こちらで描き、 CJK / 記号 (★ U+2605 等) は main font のまま。
EMOJI_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto-color-emoji/NotoColorEmoji.ttf",
)
EMOJI_CODEPOINT_THRESHOLD = 0x1F000  # ★ (U+2605) は CJK font 側、 🔥 (U+1F525) は emoji font 側

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
            (Cloud Run image の Dockerfile で apt install fonts-noto-cjk
            または fonts-ipafont-gothic が抜けたケースを即検出する。)
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
        "Install `fonts-noto-cjk` (recommended) or `fonts-ipafont-gothic` "
        "in the runtime image."
    )


def _is_bold_font_path(path: str) -> bool:
    """font path が真の bold 字形を持つ Noto Sans CJK Bold か判定。"""
    return path in FONT_CANDIDATES_BOLD


def _find_emoji_font(size: int):
    """Noto Color Emoji を探して返す (見つからなければ None)。

    color emoji font は bitmap 字形を持ち、 描画サイズが制限される (典型は 109)。
    そのため Pillow が要求サイズに resize する。
    """
    from PIL import ImageFont

    for path in EMOJI_FONT_CANDIDATES:
        try:
            # Noto Color Emoji は size 109 でしか load できない (bitmap font 制約)
            font = ImageFont.truetype(path, size=109)
            return font, path
        except (OSError, IOError):
            continue
    return None, None


def _split_text_by_emoji(text: str) -> list[tuple[str, bool]]:
    """text を (segment, is_emoji) の連続 run に分割する。

    is_emoji=True の run は codepoint >= EMOJI_CODEPOINT_THRESHOLD のみ。
    ★ (U+2605) など CJK font が持つ記号は is_emoji=False のまま main font で描く。
    """
    runs: list[tuple[str, bool]] = []
    buf = ""
    cur_is_emoji = False
    for ch in text:
        ch_is_emoji = ord(ch) >= EMOJI_CODEPOINT_THRESHOLD
        if not buf:
            buf = ch
            cur_is_emoji = ch_is_emoji
        elif ch_is_emoji == cur_is_emoji:
            buf += ch
        else:
            runs.append((buf, cur_is_emoji))
            buf = ch
            cur_is_emoji = ch_is_emoji
    if buf:
        runs.append((buf, cur_is_emoji))
    return runs


def _draw_text_with_emoji(
    draw,
    canvas,
    xy: tuple[int, int],
    text: str,
    *,
    main_font,
    main_font_path: str,
    fill,
    anchor: str = "ls",
    stroke_width: int = 0,
    stroke_fill=None,
    target_emoji_size: int | None = None,
):
    """text に color emoji が混ざっていても tofu させずに描画する。

    実装:
      1. text を CJK + emoji の run に分割
      2. emoji が無ければ通常の draw.text に委譲 (高速 path)
      3. emoji があれば run ごとに位置計算しつつ描画。
         emoji は色付き bitmap font (embedded_color=True) で別途 paste、
         サイズは main font の glyph height に揃える。

    anchor は "ls" (left-baseline) / "ms" (middle-baseline) のみサポート。
    他 anchor は安全側で main_font のみで描画 (emoji が tofu する可能性あり)。
    """
    from PIL import Image, ImageDraw

    # 高速 path: emoji 無し
    runs = _split_text_by_emoji(text)
    has_emoji = any(is_e for _, is_e in runs)
    emoji_font, _ = _find_emoji_font(0) if has_emoji else (None, None)
    if not has_emoji or emoji_font is None:
        draw.text(
            xy,
            text,
            font=main_font,
            fill=fill,
            anchor=anchor,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        return

    # サポート anchor 制限
    if anchor not in ("ls", "ms", "rs"):
        draw.text(
            xy,
            text,
            font=main_font,
            fill=fill,
            anchor=anchor,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        return

    # 横幅を測って anchor を解決
    total_width = 0
    for seg, is_e in runs:
        if is_e:
            # emoji は main_font の line height に合わせるので 1 glyph ≈ font.size * 1.0
            total_width += int(main_font.size * 1.0 * len(seg))
        else:
            bbox = main_font.getbbox(seg)
            total_width += bbox[2] - bbox[0]

    x, y = xy
    if anchor == "ms":
        x = x - total_width // 2
    elif anchor == "rs":
        x = x - total_width
    # baseline 揃え (Pillow の anchor "s" = baseline) は run ごとに保持

    # Noto Color Emoji の bitmap native size (size=109 で load 時のキャンバス)
    EMOJI_NATIVE = 136

    cursor = x
    for seg, is_e in runs:
        if is_e:
            # color emoji は native bitmap size (~136) で render してから target size に resize
            try:
                emoji_glyph_size = int(main_font.size * 1.0)
                # 1 char ごとに描画 (paste 位置を確実にコントロール)
                for ch in seg:
                    native_img = Image.new(
                        "RGBA", (EMOJI_NATIVE, EMOJI_NATIVE), (0, 0, 0, 0)
                    )
                    native_draw = ImageDraw.Draw(native_img)
                    native_draw.text(
                        (0, 0), ch, font=emoji_font, embedded_color=True
                    )
                    # crop tight bbox を取って余白除去
                    bbox = native_img.getbbox()
                    if bbox:
                        native_img = native_img.crop(bbox)
                    scaled = native_img.resize(
                        (emoji_glyph_size, emoji_glyph_size), Image.LANCZOS
                    )
                    paste_y = y - emoji_glyph_size + 4  # baseline 補正
                    canvas.alpha_composite(
                        scaled, dest=(cursor, max(paste_y, 0))
                    )
                    cursor += emoji_glyph_size
            except Exception as exc:
                logger.warning(
                    "[437v2] emoji paste failed seg=%r err=%s — fallback to main font",
                    seg,
                    exc,
                )
                draw.text(
                    (cursor, y),
                    seg,
                    font=main_font,
                    fill=fill,
                    anchor="ls",
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill,
                )
                cursor += int(main_font.size * 1.0 * len(seg))
        else:
            draw.text(
                (cursor, y),
                seg,
                font=main_font,
                fill=fill,
                anchor="ls",
                stroke_width=stroke_width,
                stroke_fill=stroke_fill,
            )
            bbox = main_font.getbbox(seg)
            cursor += bbox[2] - bbox[0]


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
    # color emoji (🔥 / 🏆 / ⚾ など U+1F000+) が混ざっても tofu しないよう、
    # Noto Color Emoji fallback 経由で描く。 ★ (U+2605) は CJK font 側で描かれる。
    hook_line = str(data.get("hook_line", ""))
    if hook_line:
        font_hook, hook_path = _find_font(size=42)
        # 真の Bold 字形なら stroke_width で fake-bold 増し打ちを抑える
        hook_stroke = 1 if _is_bold_font_path(hook_path) else 2
        _draw_text_with_emoji(
            draw,
            canvas,
            (size // 2, 115),
            hook_line,
            main_font=font_hook,
            main_font_path=hook_path,
            fill=COLOR_GOLD,
            anchor="ms",
            stroke_width=hook_stroke,
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
