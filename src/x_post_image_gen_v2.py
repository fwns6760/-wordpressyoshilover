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


def _draw_header_block(canvas, draw, title: str, subtitle: str, hook_line: str, *, size: int = DEFAULT_SIZE, header_h: int = 250):
    """共通: 黒 stripe + orange gradient header + hook / title / subtitle。

    上から: 黒 14px → gradient header_h px → 黒 8px。
    header 内は hook (上端) / title (中央) / subtitle (下端) に縦割で配置し、
    font サイズは header_h に応じて clamp する (短い header でも overlap させない)。
    """
    from PIL import Image

    canvas.paste(Image.new("RGB", (size, 14), COLOR_BLACK), (0, 0))
    canvas.paste(
        _make_vertical_gradient(size, header_h, COLOR_HEADER_TOP, COLOR_HEADER_BOT),
        (0, 14),
    )
    canvas.paste(Image.new("RGB", (size, 8), COLOR_BLACK), (0, 14 + header_h))

    # header_h に応じて font サイズと baseline 位置を線形補間
    hook_size = max(28, min(42, int(header_h * 0.18)))
    title_size = max(48, min(74, int(header_h * 0.30)))
    sub_size = max(22, min(30, int(header_h * 0.12)))

    hook_y = 14 + int(header_h * 0.22)
    title_y = 14 + int(header_h * 0.60)
    sub_y = 14 + int(header_h * 0.92)

    if hook_line:
        font_hook, path = _find_font(size=hook_size)
        _draw_text_with_emoji(
            draw, canvas, (size // 2, hook_y),
            hook_line, main_font=font_hook, main_font_path=path,
            fill=COLOR_GOLD, anchor="ms",
            stroke_width=1 if _is_bold_font_path(path) else 2,
            stroke_fill=COLOR_GOLD,
        )
    if title:
        font_title, _ = _find_font(size=title_size)
        draw.text(
            (size // 2, title_y),
            title, font=font_title, fill=COLOR_WHITE, anchor="ms",
            stroke_width=2, stroke_fill=COLOR_WHITE,
        )
    if subtitle:
        font_sub, _ = _find_font(size=sub_size)
        draw.text(
            (size // 2, sub_y),
            subtitle, font=font_sub, fill=COLOR_WHITE, anchor="ms",
        )


def _draw_footer_block(canvas, draw, handle: str, meta: str, *, size: int = DEFAULT_SIZE):
    """共通: 下部の orange handle + 灰 meta。"""
    font_handle = _find_font(size=26)[0]
    draw.text(
        (size // 2, 1035), handle, font=font_handle, fill=COLOR_GIANTS_ROW_LEFT,
        anchor="ms", stroke_width=1, stroke_fill=COLOR_GIANTS_ROW_LEFT,
    )
    font_meta = _find_font(size=20)[0]
    draw.text((size // 2, 1065), meta, font=font_meta, fill=COLOR_GRAY_TEAM, anchor="ms")


def _render_player_spotlight(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """1 選手の hero stat を巨大表示。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=180,
    )

    # player name + team
    player_name = str(data.get("player_name", ""))
    player_team = str(data.get("player_team", ""))
    if player_name:
        font_pn, _ = _find_font(size=82)
        draw.text(
            (size // 2, 305), f"{player_name} ★",
            font=font_pn, fill=COLOR_BLACK, anchor="ms",
            stroke_width=2, stroke_fill=COLOR_BLACK,
        )
    if player_team:
        font_team, _ = _find_font(size=30)
        draw.text(
            (size // 2, 350), player_team,
            font=font_team, fill=COLOR_GIANTS_ROW_LEFT, anchor="ms",
            stroke_width=1, stroke_fill=COLOR_GIANTS_ROW_LEFT,
        )

    # metric label
    metric_label = str(data.get("metric_label", ""))
    if metric_label:
        font_ml, _ = _find_font(size=44)
        draw.text(
            (size // 2, 450), metric_label,
            font=font_ml, fill=COLOR_BLACK, anchor="ms",
            stroke_width=2, stroke_fill=COLOR_BLACK,
        )

    # huge hero value
    hero_value = str(data.get("hero_value", ""))
    if hero_value:
        font_hv, _ = _find_font(size=240)
        draw.text(
            (size // 2, 720), hero_value,
            font=font_hv, fill=COLOR_GIANTS_ROW_LEFT, anchor="ms",
            stroke_width=4, stroke_fill=COLOR_BLACK,
        )

    # optional sub stats (up to 2 small boxes)
    sub_stats = data.get("sub_stats", []) or []
    if sub_stats:
        font_sl, _ = _find_font(size=28)
        font_sv, _ = _find_font(size=56)
        col_w = 960 // len(sub_stats[:2])
        for i, s in enumerate(sub_stats[:2]):
            x_center = 60 + col_w * i + col_w // 2
            draw.text(
                (x_center, 800), str(s.get("label", "")),
                font=font_sl, fill=COLOR_GIANTS_ROW_LEFT, anchor="ms",
                stroke_width=1, stroke_fill=COLOR_GIANTS_ROW_LEFT,
            )
            draw.text(
                (x_center, 880), str(s.get("value", "")),
                font=font_sv, fill=COLOR_BLACK, anchor="ms",
                stroke_width=2, stroke_fill=COLOR_BLACK,
            )

    _draw_footer_block(
        canvas, draw,
        str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
        str(data.get("footer_meta", DEFAULT_FOOTER_META)),
        size=size,
    )
    return canvas


def _render_pitcher_card(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """投手の名前 + stat grid (3 cols × 2 rows max 6 stats)。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=200,
    )

    player_name = str(data.get("player_name", ""))
    player_team = str(data.get("player_team", ""))
    if player_name:
        font_pn, _ = _find_font(size=70)
        draw.text(
            (size // 2, 315), f"{player_name} ★",
            font=font_pn, fill=COLOR_BLACK, anchor="ms",
            stroke_width=2, stroke_fill=COLOR_BLACK,
        )
    if player_team:
        font_team, _ = _find_font(size=28)
        draw.text(
            (size // 2, 360), f"{player_team} / 投手",
            font=font_team, fill=COLOR_GIANTS_ROW_LEFT, anchor="ms",
        )

    # stat grid 3x2 max 6
    stats = (data.get("stats", []) or [])[:6]
    cell_w = 320
    cell_h = 200
    grid_x = (size - cell_w * 3) // 2
    grid_y = 420
    font_label, _ = _find_font(size=28)
    font_value, _ = _find_font(size=90)
    for i, st in enumerate(stats):
        col = i % 3
        row = i // 3
        cx = grid_x + col * cell_w
        cy = grid_y + row * cell_h
        if st.get("highlight"):
            grad = _make_vertical_gradient(cell_w - 10, cell_h - 10, COLOR_HEADER_TOP, COLOR_HEADER_BOT)
            canvas.paste(grad, (cx + 5, cy + 5))
            draw = ImageDraw.Draw(canvas)
            label_fill = COLOR_WHITE
            value_fill = COLOR_GOLD
        else:
            draw.rectangle(
                (cx + 5, cy + 5, cx + cell_w - 5, cy + cell_h - 5),
                outline=COLOR_BLACK, width=3,
            )
            label_fill = COLOR_BLACK
            value_fill = COLOR_BLACK
        draw.text(
            (cx + cell_w // 2, cy + 50), str(st.get("label", "")),
            font=font_label, fill=label_fill, anchor="ms",
            stroke_width=1, stroke_fill=label_fill,
        )
        draw.text(
            (cx + cell_w // 2, cy + cell_h - 35), str(st.get("value", "")),
            font=font_value, fill=value_fill, anchor="ms",
            stroke_width=2, stroke_fill=COLOR_BLACK if st.get("highlight") else COLOR_BLACK,
        )

    _draw_footer_block(
        canvas, draw,
        str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
        str(data.get("footer_meta", DEFAULT_FOOTER_META)),
        size=size,
    )
    return canvas


def _render_standings(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """12 team 順位表 (勝-敗-分 / 勝率 / ゲーム差)。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=200,
    )

    rows = data.get("rows", []) or []
    row_h = 60
    start_y = 290
    font_rank, _ = _find_font(size=36)
    font_team, _ = _find_font(size=32)
    font_record, _ = _find_font(size=28)
    font_pct, _ = _find_font(size=32)
    font_gap, _ = _find_font(size=32)
    for i, row in enumerate(rows[:6]):
        y = start_y + i * row_h
        if row.get("is_giants"):
            grad = _make_horizontal_gradient(960, row_h - 6, COLOR_GIANTS_ROW_LEFT, "#FF9100")
            canvas.paste(grad, (60, y - 3))
            draw = ImageDraw.Draw(canvas)
            color_main = COLOR_WHITE
            color_rank = COLOR_GOLD
        else:
            draw.line(((60, y + row_h - 3), (size - 60, y + row_h - 3)), fill=COLOR_GRAY_ROW_SEP, width=1)
            color_main = COLOR_BLACK
            color_rank = COLOR_GIANTS_ROW_LEFT
        draw.text((100, y + row_h // 2), str(row.get("rank", i + 1)),
                  font=font_rank, fill=color_rank, anchor="mm",
                  stroke_width=1, stroke_fill=color_rank)
        draw.text((280, y + row_h // 2), str(row.get("team", "")),
                  font=font_team, fill=color_main, anchor="mm",
                  stroke_width=1, stroke_fill=color_main)
        draw.text((500, y + row_h // 2), str(row.get("record", "")),
                  font=font_record, fill=color_main, anchor="mm")
        draw.text((690, y + row_h // 2), str(row.get("win_pct", "")),
                  font=font_pct, fill=color_main, anchor="mm",
                  stroke_width=1, stroke_fill=color_main)
        draw.text((900, y + row_h // 2), str(row.get("games_back", "")),
                  font=font_gap, fill=color_main, anchor="mm",
                  stroke_width=1, stroke_fill=color_main)

    _draw_footer_block(
        canvas, draw,
        str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
        str(data.get("footer_meta", DEFAULT_FOOTER_META)),
        size=size,
    )
    return canvas


def _render_12team_bar(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """12 球団の値を水平バーで比較。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=170,
    )

    teams = data.get("teams", []) or []
    if not teams:
        _draw_footer_block(canvas, draw,
            str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
            str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    values = [float(t.get("value", 0) or 0) for t in teams]
    max_v = max(values) if values else 1.0
    max_v = max_v if max_v > 0 else 1.0
    row_h = 60
    start_y = 240
    bar_max_w = 680
    font_rank, _ = _find_font(size=24)
    font_team, _ = _find_font(size=30)
    font_val, _ = _find_font(size=36)
    for i, t in enumerate(teams[:12]):
        y = start_y + i * row_h
        bar_w = max(2, int(float(t.get("value", 0) or 0) / max_v * bar_max_w))
        if t.get("is_giants"):
            color_bar_l = COLOR_GIANTS_ROW_LEFT
            color_bar_r = "#FF9100"
            color_team = COLOR_GIANTS_ROW_LEFT
            color_val = COLOR_GIANTS_ROW_LEFT
            color_rank = COLOR_GOLD
            grad = _make_horizontal_gradient(bar_w, 38, color_bar_l, color_bar_r)
            canvas.paste(grad, (210, y - 14))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((210, y - 14, 210 + bar_w, y + 24), outline=COLOR_BLACK, width=3)
            team_text = f"{t.get('name', '')} ★"
            stroke_w = 1
        else:
            color_team = COLOR_BLACK
            color_val = COLOR_BLACK
            color_rank = COLOR_GIANTS_ROW_LEFT
            draw.rectangle((210, y - 14, 210 + bar_w, y + 24), fill="#666666", outline=COLOR_BLACK, width=2)
            team_text = str(t.get("name", ""))
            stroke_w = 0
        draw.text((155, y + 5), str(i + 1), font=font_rank, fill=color_rank, anchor="rs",
                  stroke_width=1, stroke_fill=color_rank)
        draw.text((200, y + 5), team_text, font=font_team, fill=color_team, anchor="rs",
                  stroke_width=stroke_w, stroke_fill=color_team)
        draw.text((210 + bar_w + 10, y + 5), str(t.get("value_label", t.get("value", ""))),
                  font=font_val, fill=color_val, anchor="ls",
                  stroke_width=1 if t.get("is_giants") else 0,
                  stroke_fill=color_val)

    _draw_footer_block(
        canvas, draw,
        str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
        str(data.get("footer_meta", DEFAULT_FOOTER_META)),
        size=size,
    )
    return canvas


def _render_chart_bars(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """選手 TOP10 を水平 bar で大小比較 (12team_bar の選手版)。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=180)
    rows = data.get("rows", []) or []
    if not rows:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    def _val(r):
        try:
            return float(str(r.get("value", "0")).replace(",", ""))
        except (ValueError, TypeError):
            return 0.0

    max_v = max(_val(r) for r in rows) or 1.0
    row_h = 60
    start_y = 240
    bar_max_w = 660
    font_rank, _ = _find_font(size=24)
    font_name, _ = _find_font(size=28)
    font_val, _ = _find_font(size=32)
    for i, r in enumerate(rows[:10]):
        y = start_y + i * row_h
        bar_w = max(2, int(_val(r) / max_v * bar_max_w))
        if r.get("is_giants"):
            grad = _make_horizontal_gradient(bar_w, 36, COLOR_GIANTS_ROW_LEFT, "#FF9100")
            canvas.paste(grad, (240, y - 14))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((240, y - 14, 240 + bar_w, y + 22), outline=COLOR_BLACK, width=3)
            name_color = COLOR_GIANTS_ROW_LEFT
            val_color = COLOR_GIANTS_ROW_LEFT
            rank_color = COLOR_GOLD
            name_text = f"{r.get('name', '')} ★"
            stroke_w = 1
        else:
            draw.rectangle((240, y - 14, 240 + bar_w, y + 22), fill="#888888", outline=COLOR_BLACK, width=2)
            name_color = COLOR_BLACK
            val_color = COLOR_BLACK
            rank_color = COLOR_GIANTS_ROW_LEFT
            name_text = str(r.get("name", ""))
            stroke_w = 0
        draw.text((50, y + 5), str(r.get("rank", i + 1)), font=font_rank, fill=rank_color, anchor="ls",
                  stroke_width=1, stroke_fill=rank_color)
        draw.text((230, y + 5), name_text, font=font_name, fill=name_color, anchor="rs",
                  stroke_width=stroke_w, stroke_fill=name_color)
        draw.text((240 + bar_w + 10, y + 5), str(r.get("value", "")), font=font_val, fill=val_color, anchor="ls",
                  stroke_width=1 if r.get("is_giants") else 0, stroke_fill=val_color)
    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_monthly_summary(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """上位 3 人 + 数値を大きく hero 表示 (週/月ハイライト風)。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=200)
    rows = (data.get("rows", []) or [])[:3]
    if not rows:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    # 3 段の hero card
    card_y_start = 280
    card_h = 220
    card_gap = 16
    for i, r in enumerate(rows):
        cy = card_y_start + i * (card_h + card_gap)
        if r.get("is_giants"):
            grad = _make_horizontal_gradient(960, card_h, COLOR_GIANTS_ROW_LEFT, "#FF9100")
            canvas.paste(grad, (60, cy))
            draw = ImageDraw.Draw(canvas)
            rank_color = COLOR_GOLD
            name_color = COLOR_WHITE
            val_color = COLOR_GOLD
            team_color = COLOR_GOLD
            star = " ★"
        else:
            draw.rectangle((60, cy, 60 + 960, cy + card_h), outline=COLOR_BLACK, width=3)
            rank_color = COLOR_GIANTS_ROW_LEFT
            name_color = COLOR_BLACK
            val_color = COLOR_BLACK
            team_color = COLOR_GIANTS_ROW_LEFT
            star = ""
        font_rank, _ = _find_font(size=120)
        draw.text((140, cy + card_h // 2), str(r.get("rank", i + 1)),
                  font=font_rank, fill=rank_color, anchor="mm",
                  stroke_width=2, stroke_fill=rank_color)
        font_name, _ = _find_font(size=58)
        draw.text((280, cy + card_h // 2 - 25), f"{r.get('name', '')}{star}",
                  font=font_name, fill=name_color, anchor="lm",
                  stroke_width=2, stroke_fill=name_color)
        font_team, _ = _find_font(size=26)
        draw.text((280, cy + card_h // 2 + 35), str(r.get("team", "")),
                  font=font_team, fill=team_color, anchor="lm",
                  stroke_width=1, stroke_fill=team_color)
        font_val, _ = _find_font(size=82)
        draw.text((990, cy + card_h // 2), str(r.get("value", "")),
                  font=font_val, fill=val_color, anchor="rm",
                  stroke_width=2, stroke_fill=val_color)
    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_data_sheet(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """TOP10 を高密度表で。 ranking_table より行数多めで小さい font。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=200)
    rows = data.get("rows", []) or []
    if not rows:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    # 表ヘッダ
    table_y = 270
    draw.rectangle((40, table_y, size - 40, table_y + 50), fill=COLOR_BLACK)
    font_h, _ = _find_font(size=24)
    headers = [("順位", 100), ("選手", 380), ("球団", 660), ("数値", 980)]
    for label, x in headers:
        draw.text((x, table_y + 25), label, font=font_h, fill=COLOR_GIANTS_ROW_LEFT, anchor="mm",
                  stroke_width=1, stroke_fill=COLOR_GIANTS_ROW_LEFT)

    row_h = 62
    font_rank, _ = _find_font(size=28)
    font_name, _ = _find_font(size=30)
    font_team, _ = _find_font(size=22)
    font_val, _ = _find_font(size=38)
    for i, r in enumerate(rows[:10]):
        y = table_y + 50 + i * row_h
        if r.get("is_giants"):
            grad = _make_horizontal_gradient(size - 80, row_h - 4, COLOR_GIANTS_ROW_LEFT, "#FF9100")
            canvas.paste(grad, (40, y + 2))
            draw = ImageDraw.Draw(canvas)
            rank_c = COLOR_GOLD
            name_c = COLOR_WHITE
            team_c = COLOR_GOLD
            val_c = COLOR_GOLD
            star = " ★"
            stroke_w = 1
        else:
            draw.line(((40, y + row_h), (size - 40, y + row_h)), fill=COLOR_GRAY_ROW_SEP, width=1)
            rank_c = COLOR_GIANTS_ROW_LEFT
            name_c = COLOR_BLACK
            team_c = COLOR_GRAY_TEAM
            val_c = COLOR_BLACK
            star = ""
            stroke_w = 0
        draw.text((100, y + row_h // 2), str(r.get("rank", i + 1)), font=font_rank, fill=rank_c, anchor="mm",
                  stroke_width=1, stroke_fill=rank_c)
        draw.text((380, y + row_h // 2), f"{r.get('name', '')}{star}", font=font_name, fill=name_c, anchor="mm",
                  stroke_width=stroke_w, stroke_fill=name_c)
        draw.text((660, y + row_h // 2), str(r.get("team", "")), font=font_team, fill=team_c, anchor="mm")
        draw.text((980, y + row_h // 2), str(r.get("value", "")), font=font_val, fill=val_c, anchor="mm",
                  stroke_width=1, stroke_fill=val_c)

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_12team_crown(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """rows から球団別 TOP1 (冠) を集計して 12 球団 grid で表示。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=200)

    rows = data.get("rows", []) or []
    # ユニーク 球団 list を順位順で取得 (TOP1, TOP2 ... を踏まえ)
    team_to_best_rank: dict[str, dict] = {}
    for r in rows[:10]:
        team = str(r.get("team", "")).strip()
        if not team:
            continue
        if team not in team_to_best_rank:
            team_to_best_rank[team] = r
    teams = list(team_to_best_rank.items())[:12]

    # grid 3 cols × 4 rows
    cols = 3
    cell_w = (size - 100) // cols
    cell_h = 150
    start_y = 270
    font_rank, _ = _find_font(size=72)
    font_team, _ = _find_font(size=30)
    font_pl, _ = _find_font(size=22)
    for i, (team, r) in enumerate(teams):
        col = i % cols
        row_i = i // cols
        cx = 50 + col * cell_w
        cy = start_y + row_i * cell_h
        is_giants = bool(r.get("is_giants")) or team == "巨人"
        if is_giants:
            grad = _make_horizontal_gradient(cell_w - 10, cell_h - 10, COLOR_GIANTS_ROW_LEFT, "#FF9100")
            canvas.paste(grad, (cx + 5, cy + 5))
            draw = ImageDraw.Draw(canvas)
            rank_c = COLOR_GOLD
            team_c = COLOR_WHITE
            pl_c = COLOR_GOLD
        else:
            draw.rectangle((cx + 5, cy + 5, cx + cell_w - 5, cy + cell_h - 5),
                           outline=COLOR_BLACK, width=2)
            rank_c = COLOR_GIANTS_ROW_LEFT
            team_c = COLOR_BLACK
            pl_c = COLOR_GRAY_TEAM
        rank_text = f"#{r.get('rank', '?')}"
        draw.text((cx + cell_w // 2, cy + 60), rank_text, font=font_rank, fill=rank_c, anchor="mm",
                  stroke_width=2, stroke_fill=rank_c)
        draw.text((cx + cell_w // 2, cy + 110), team, font=font_team, fill=team_c, anchor="mm",
                  stroke_width=1, stroke_fill=team_c)
        draw.text((cx + cell_w // 2, cy + 138), str(r.get("name", "")), font=font_pl, fill=pl_c, anchor="mm")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_starting_lineup(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """TOP9 を打順表風 3×3 grid で。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=200)

    rows = (data.get("rows", []) or [])[:9]
    cols = 3
    cell_w = (size - 100) // cols
    cell_h = 200
    start_y = 270
    font_num, _ = _find_font(size=84)
    font_name, _ = _find_font(size=30)
    font_val, _ = _find_font(size=42)
    font_team, _ = _find_font(size=20)
    for i, r in enumerate(rows):
        col = i % cols
        row_i = i // cols
        cx = 50 + col * cell_w
        cy = start_y + row_i * cell_h
        if r.get("is_giants"):
            grad = _make_horizontal_gradient(cell_w - 10, cell_h - 10, COLOR_GIANTS_ROW_LEFT, "#FF9100")
            canvas.paste(grad, (cx + 5, cy + 5))
            draw = ImageDraw.Draw(canvas)
            num_c = COLOR_GOLD
            name_c = COLOR_WHITE
            val_c = COLOR_GOLD
            team_c = COLOR_GOLD
        else:
            draw.rectangle((cx + 5, cy + 5, cx + cell_w - 5, cy + cell_h - 5),
                           outline=COLOR_BLACK, width=2)
            num_c = COLOR_GIANTS_ROW_LEFT
            name_c = COLOR_BLACK
            val_c = COLOR_BLACK
            team_c = COLOR_GRAY_TEAM
        draw.text((cx + cell_w // 2, cy + 60), str(r.get("rank", i + 1)),
                  font=font_num, fill=num_c, anchor="mm", stroke_width=2, stroke_fill=num_c)
        draw.text((cx + cell_w // 2, cy + 125), str(r.get("name", "")),
                  font=font_name, fill=name_c, anchor="mm",
                  stroke_width=1, stroke_fill=name_c)
        draw.text((cx + cell_w // 2, cy + 160), str(r.get("value", "")),
                  font=font_val, fill=val_c, anchor="mm", stroke_width=1, stroke_fill=val_c)
        draw.text((cx + cell_w // 2, cy + 188), str(r.get("team", "")),
                  font=font_team, fill=team_c, anchor="mm")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_scoreboard(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """TOP1 player と「残り合計」 をスコア風に対比表示。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=220)

    rows = data.get("rows", []) or []
    if not rows:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    def _val(r):
        try:
            return float(str(r.get("value", "0")).replace(",", ""))
        except (ValueError, TypeError):
            return 0.0

    leader = rows[0]
    rest = rows[1:10]
    rest_sum = sum(_val(r) for r in rest)
    rest_avg = rest_sum / len(rest) if rest else 0.0

    # スコアボード 2 cells (leader vs rest avg)
    sb_y = 320
    sb_h = 380
    half_w = (size - 100) // 2
    # leader cell
    if leader.get("is_giants"):
        grad = _make_vertical_gradient(half_w - 10, sb_h, COLOR_HEADER_TOP, COLOR_HEADER_BOT)
        canvas.paste(grad, (50, sb_y))
        draw = ImageDraw.Draw(canvas)
        leader_label_c = COLOR_GOLD
        leader_val_c = COLOR_WHITE
        leader_name_c = COLOR_WHITE
    else:
        draw.rectangle((50, sb_y, 50 + half_w - 10, sb_y + sb_h), outline=COLOR_BLACK, width=3)
        leader_label_c = COLOR_GIANTS_ROW_LEFT
        leader_val_c = COLOR_BLACK
        leader_name_c = COLOR_BLACK

    font_label, _ = _find_font(size=32)
    font_name, _ = _find_font(size=44)
    font_score, _ = _find_font(size=130)
    draw.text((50 + (half_w - 10) // 2, sb_y + 50), "TOP", font=font_label, fill=leader_label_c, anchor="mm",
              stroke_width=1, stroke_fill=leader_label_c)
    draw.text((50 + (half_w - 10) // 2, sb_y + 110), str(leader.get("name", "")),
              font=font_name, fill=leader_name_c, anchor="mm", stroke_width=2, stroke_fill=leader_name_c)
    draw.text((50 + (half_w - 10) // 2, sb_y + 230), str(leader.get("value", "")),
              font=font_score, fill=leader_val_c, anchor="mm", stroke_width=3, stroke_fill=COLOR_BLACK)
    draw.text((50 + (half_w - 10) // 2, sb_y + sb_h - 30), str(leader.get("team", "")),
              font=font_label, fill=leader_label_c, anchor="mm")

    # rest cell
    rx = 50 + half_w + 10
    draw.rectangle((rx, sb_y, rx + half_w - 10, sb_y + sb_h), outline=COLOR_BLACK, width=3)
    draw.text((rx + (half_w - 10) // 2, sb_y + 50), "他 平均", font=font_label,
              fill=COLOR_GIANTS_ROW_LEFT, anchor="mm", stroke_width=1, stroke_fill=COLOR_GIANTS_ROW_LEFT)
    draw.text((rx + (half_w - 10) // 2, sb_y + 110), f"{len(rest)} 人",
              font=font_name, fill=COLOR_BLACK, anchor="mm")
    avg_text = f"{rest_avg:.3f}" if rest_avg < 10 else f"{rest_avg:.1f}"
    draw.text((rx + (half_w - 10) // 2, sb_y + 230), avg_text, font=font_score, fill=COLOR_BLACK, anchor="mm",
              stroke_width=2, stroke_fill=COLOR_BLACK)
    draw.text((rx + (half_w - 10) // 2, sb_y + sb_h - 30), "2-10位", font=font_label,
              fill=COLOR_GRAY_TEAM, anchor="mm")

    # VS 中央 (small overlay)
    font_vs, _ = _find_font(size=42)
    draw.text((size // 2, sb_y + sb_h + 30), "vs", font=font_vs, fill=COLOR_BLACK, anchor="mm",
              stroke_width=1, stroke_fill=COLOR_BLACK)

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


# 各 template_key → render function dispatch table
TEMPLATE_RENDERERS = {
    "ranking_table": _render_ranking_table,
    "player_spotlight": _render_player_spotlight,
    "pitcher_card": _render_pitcher_card,
    "standings": _render_standings,
    "12team_bar": _render_12team_bar,
    "chart_bars": _render_chart_bars,
    "monthly_summary": _render_monthly_summary,
    "data_sheet": _render_data_sheet,
    "12team_crown": _render_12team_crown,
    "starting_lineup": _render_starting_lineup,
    "scoreboard": _render_scoreboard,
}


def generate_png(
    template_key: str,
    data: dict[str, Any],
    size: int = DEFAULT_SIZE,
) -> bytes | None:
    """Pillow + CJK font で PNG bytes を生成する entry point。

    対応 template_key:
      - ranking_table (Phase 2A)
      - player_spotlight / pitcher_card / standings / 12team_bar (Phase 6)
    未対応 key は WARN log + None で caller fallback。

    Args:
        template_key: 上記いずれか。
        data: build_*_data() の出力 dict。
        size: PNG 出力 size (default 1080x1080)。

    Returns:
        PNG bytes on success, None on any failure (caller fallback)。
    """
    try:
        renderer = TEMPLATE_RENDERERS.get(template_key)
        if renderer is None:
            logger.warning(
                "[437v2] generate_png unknown template_key=%s (supported=%s)",
                template_key, list(TEMPLATE_RENDERERS),
            )
            return None
        img = renderer(data, size=size)
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


def build_player_spotlight_data(
    *,
    title: str,
    subtitle: str,
    hook_line: str,
    player_name: str,
    player_team: str,
    metric_label: str,
    hero_value: str,
    sub_stats: list[dict[str, Any]] | None = None,
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "player_name": player_name,
        "player_team": player_team,
        "metric_label": metric_label,
        "hero_value": hero_value,
        "sub_stats": sub_stats or [],
        "footer_handle": footer_handle,
        "footer_meta": footer_meta,
    }


def build_pitcher_card_data(
    *,
    title: str,
    subtitle: str,
    hook_line: str,
    player_name: str,
    player_team: str,
    stats: list[dict[str, Any]],
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    """投手 stat grid 用 data。 stats[i] = {label, value, highlight?}。最大 6 件。"""
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "player_name": player_name,
        "player_team": player_team,
        "stats": stats,
        "footer_handle": footer_handle,
        "footer_meta": footer_meta,
    }


def build_standings_data(
    *,
    title: str,
    subtitle: str,
    hook_line: str,
    rows: list[dict[str, Any]],
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    """順位表 data。 rows[i] = {rank, team, record, win_pct, games_back, is_giants?}。"""
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "rows": rows,
        "footer_handle": footer_handle,
        "footer_meta": footer_meta,
    }


def build_12team_bar_data(
    *,
    title: str,
    subtitle: str,
    hook_line: str,
    teams: list[dict[str, Any]],
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    """12 球団 bar chart data。 teams[i] = {name, value, value_label?, is_giants?}。"""
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "teams": teams,
        "footer_handle": footer_handle,
        "footer_meta": footer_meta,
    }
