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
DEFAULT_FOOTER_HANDLE = "@yoshilover6760"
DEFAULT_FOOTER_META = "yoshilover.com/data"

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

# brand palette (2026-05-25 user lock / 2026-06-10 refinement: 同系統の
# orange / gold / black は維持しつつ、 下地・カード・文字色に neutral 系を
# 追加して「白地にベタ塗り」の安っぽさを解消する)
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

# 2026-06-10 design refresh palette
COLOR_CANVAS = "#F6F5F2"        # 画面下地 (warm off-white)
COLOR_CARD = "#FFFFFF"          # row / cell card
COLOR_CARD_BORDER = "#E8E5E0"   # card の hairline border
COLOR_CARD_SOFT = "#F1EFEB"     # 控えめな cell 下地 (stat grid 等)
COLOR_TEXT = "#1B1B1B"          # 本文 (純黒より柔らかい)
COLOR_TEXT_SUB = "#8E8983"      # 補足 (チーム名等)
COLOR_BADGE_FILL = "#EFEDE9"    # 4位以下 rank badge
COLOR_BADGE_TEXT = "#6E6962"
COLOR_MEDAL_GOLD = "#F4B400"
COLOR_MEDAL_SILVER = "#ADB5BD"
COLOR_MEDAL_BRONZE = "#C9804E"
COLOR_FOOTER_BAND = "#141414"
COLOR_BAR_NEUTRAL = "#D9D5CF"   # 非巨人 bar

# 2026-06-11 variation palette (night 系 template 用)。 brand lock の
# orange / gold / 黒 の範囲内で、 下地を warm dark に振った別 mood を作る。
COLOR_NIGHT_BG = "#171411"      # night 下地 (warm dark)
COLOR_NIGHT_CARD = "#221E1A"    # night card
COLOR_NIGHT_BORDER = "#332D27"  # night card border
COLOR_NIGHT_TEXT = "#F4F0EA"    # night 本文
COLOR_NIGHT_SUB = "#A89F94"     # night 補足


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


def _draw_crisp_text(draw, xy, text, *, size: int, fill, anchor="ls", fake_stroke: int = 1):
    """bold font があれば stroke なしで crisp に、 IPA fallback 時だけ fake-bold。

    旧実装は常に stroke_width>=1 で増し打ちしており、 Noto Bold 環境でも
    文字が太く滲んで見えた (2026-06-10 user「ださい」指摘の一因)。
    """
    font, path = _find_font(size=size)
    sw = 0 if _is_bold_font_path(path) else fake_stroke
    draw.text(xy, text, font=font, fill=fill, anchor=anchor,
              stroke_width=sw, stroke_fill=fill)
    return font


def _rounded_card(canvas, rect, *, fill=COLOR_CARD, radius: int = 18,
                  border=COLOR_CARD_BORDER, border_w: int = 2, shadow: bool = False):
    """角丸カードを RGBA overlay で描く。 shadow=True で soft drop shadow。"""
    from PIL import Image, ImageDraw, ImageFilter

    x1, y1, x2, y2 = rect
    if shadow:
        blur = 10
        pad = blur * 2
        sh = Image.new("RGBA", (x2 - x1 + pad * 2, y2 - y1 + pad * 2), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rounded_rectangle((pad, pad, pad + (x2 - x1), pad + (y2 - y1)),
                             radius=radius, fill=(20, 12, 0, 60))
        sh = sh.filter(ImageFilter.GaussianBlur(radius=blur))
        canvas.alpha_composite(sh, dest=(x1 - pad, y1 - pad + 5))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle(rect, radius=radius, fill=fill,
                         outline=border, width=border_w if border else 0)
    canvas.alpha_composite(layer)


def _rounded_gradient_card(canvas, rect, *, left_hex=COLOR_GIANTS_ROW_LEFT,
                           right_hex=COLOR_GIANTS_ROW_RIGHT, radius: int = 18,
                           shadow: bool = True):
    """横 gradient の角丸カード (巨人 highlight 用)。"""
    from PIL import Image, ImageDraw, ImageFilter

    x1, y1, x2, y2 = rect
    w, h = x2 - x1, y2 - y1
    if shadow:
        blur = 10
        pad = blur * 2
        sh = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rounded_rectangle((pad, pad, pad + w, pad + h), radius=radius,
                             fill=(120, 50, 0, 80))
        sh = sh.filter(ImageFilter.GaussianBlur(radius=blur))
        canvas.alpha_composite(sh, dest=(x1 - pad, y1 - pad + 6))
    grad = _make_horizontal_gradient(w, h, left_hex, right_hex).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(grad, (x1, y1), mask)
    canvas.alpha_composite(layer)


def _rank_badge(canvas, center, rank, *, r: int = 26, on_giants: bool = False):
    """rank 数字の円 badge。 top3 はメダル色、 4 位以下は neutral。"""
    from PIL import Image, ImageDraw

    medal = {1: COLOR_MEDAL_GOLD, 2: COLOR_MEDAL_SILVER, 3: COLOR_MEDAL_BRONZE}
    try:
        rank_n = int(rank)
    except (TypeError, ValueError):
        rank_n = 0
    if on_giants:
        fill = COLOR_WHITE
        text_c = COLOR_GIANTS_ROW_LEFT if rank_n not in medal else medal[rank_n]
    elif rank_n in medal:
        fill = medal[rank_n]
        text_c = COLOR_WHITE
    else:
        fill = COLOR_BADGE_FILL
        text_c = COLOR_BADGE_TEXT
    cx, cy = center
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    canvas.alpha_composite(layer)
    draw = ImageDraw.Draw(canvas)
    _draw_crisp_text(draw, (cx, cy + 1), str(rank), size=int(r * 1.15),
                     fill=text_c, anchor="mm")
    return draw


def _pill_chip(canvas, center, text, *, size: int = 26, pad_x: int = 22,
               pad_y: int = 10, bg=(0, 0, 0, 110), fg=COLOR_GOLD,
               canvas_draw=None):
    """中央寄せの pill chip (hook 行・ラベル用)。 戻り値は chip の bbox。"""
    from PIL import Image, ImageDraw

    font, path = _find_font(size=size)
    probe = ImageDraw.Draw(canvas)
    bbox = probe.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    cx, cy = center
    rect = (cx - tw // 2 - pad_x, cy - th // 2 - pad_y,
            cx + tw // 2 + pad_x, cy + th // 2 + pad_y)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle(rect, radius=(rect[3] - rect[1]) // 2, fill=bg)
    canvas.alpha_composite(layer)
    draw = ImageDraw.Draw(canvas)
    sw = 0 if _is_bold_font_path(path) else 1
    _draw_text_with_emoji(
        draw, canvas, (cx - tw // 2, cy + th // 2),
        text, main_font=font, main_font_path=path,
        fill=fg, anchor="ls", stroke_width=sw, stroke_fill=fg,
    )
    return rect


def _render_ranking_table(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """ranking_table data dict → PIL RGBA Image (1080x1080)。

    2026-06-10 refresh: 行を角丸カード化 (巨人 = orange gradient card、
    他 = 白 card + hairline border)、 rank は円 badge (top3 メダル色)、
    チーム名は名前と同じ行に inline 配置して行間衝突を解消。
    """
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=230,
    )

    rows = (data.get("rows", []) or [])[:8]
    row_h = 80
    row_gap = 8
    start_y = 280
    x1, x2 = 44, size - 44
    for i, row in enumerate(rows):
        top = start_y + i * (row_h + row_gap)
        rect = (x1, top, x2, top + row_h)
        cy = top + row_h // 2
        is_giants = bool(row.get("is_giants"))
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=16, shadow=True)
            name_c = COLOR_WHITE
            team_c = (255, 235, 220, 255)
            val_c = COLOR_WHITE
        else:
            _rounded_card(canvas, rect, radius=16, shadow=False)
            name_c = COLOR_TEXT
            team_c = COLOR_TEXT_SUB
            val_c = COLOR_TEXT
        draw = _rank_badge(canvas, (x1 + 50, cy), row.get("rank", i + 1),
                           r=26, on_giants=is_giants)

        # name (左) + team (名前の右に inline、 行間衝突なし)
        name_text = str(row.get("name", ""))
        name_size = 46 if is_giants else 42
        font_name, name_path = _find_font(size=name_size)
        sw = 0 if _is_bold_font_path(name_path) else 1
        draw.text((x1 + 102, cy), name_text, font=font_name, fill=name_c,
                  anchor="lm", stroke_width=sw, stroke_fill=name_c)
        name_w = draw.textlength(name_text, font=font_name)
        tx = x1 + 102 + name_w + 16
        if is_giants:
            _draw_crisp_text(draw, (tx, cy + 14), "★", size=30,
                             fill=COLOR_GOLD, anchor="ls")
            tx += 42
        team_text = str(row.get("team", ""))
        if team_text:
            font_team, _ = _find_font(size=24)
            draw.text((tx, cy + 13), team_text, font=font_team,
                      fill=team_c, anchor="ls")

        # value (右寄せ、 全行同 baseline)
        val_size = 58 if is_giants else 52
        _draw_crisp_text(draw, (x2 - 28, cy), str(row.get("value", "")),
                         size=val_size, fill=val_c, anchor="rm")

    _draw_footer_block(
        canvas, draw,
        str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
        str(data.get("footer_meta", DEFAULT_FOOTER_META)),
        size=size,
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
    from PIL import Image, ImageDraw

    canvas.paste(Image.new("RGB", (size, 14), COLOR_BLACK), (0, 0))
    canvas.paste(
        _make_vertical_gradient(size, header_h, COLOR_HEADER_TOP, COLOR_HEADER_BOT),
        (0, 14),
    )
    canvas.paste(Image.new("RGB", (size, 8), COLOR_BLACK), (0, 14 + header_h))

    # header_h に応じて font サイズと baseline 位置を線形補間
    hook_size = max(26, min(34, int(header_h * 0.14)))
    title_size = max(48, min(72, int(header_h * 0.29)))
    sub_size = max(22, min(28, int(header_h * 0.11)))

    hook_y = 14 + int(header_h * 0.24)
    title_y = 14 + int(header_h * 0.62)
    sub_y = 14 + int(header_h * 0.90)

    if hook_line:
        # 旧: 金文字を orange 地に直書き (低 contrast)。 新: 半透明黒 pill に
        # 金文字で hook を「チップ」化して視認性と引き締めを両立。
        _pill_chip(canvas, (size // 2, hook_y), hook_line,
                   size=hook_size, bg=(0, 0, 0, 115), fg=COLOR_GOLD)
        draw = ImageDraw.Draw(canvas)
    if title:
        _draw_crisp_text(draw, (size // 2, title_y), title,
                         size=title_size, fill=COLOR_WHITE, anchor="ms")
    if subtitle:
        font_sub, _ = _find_font(size=sub_size)
        draw.text(
            (size // 2, sub_y),
            subtitle, font=font_sub, fill=(255, 240, 228, 255), anchor="ms",
        )


def _draw_footer_block(canvas, draw, handle: str, meta: str, *, size: int = DEFAULT_SIZE):
    """共通: 下端の黒帯 footer (上端に orange accent line)。

    上端の黒 stripe と対になる「額縁」を作り、 handle を白 / meta を
    warm gray で 1 行にまとめる。
    """
    from PIL import Image, ImageDraw

    band_h = 56
    band_top = size - band_h
    canvas.paste(Image.new("RGB", (size, band_h), COLOR_FOOTER_BAND), (0, band_top))
    canvas.paste(
        _make_horizontal_gradient(size, 4, COLOR_GIANTS_ROW_LEFT, COLOR_HEADER_BOT),
        (0, band_top),
    )
    draw = ImageDraw.Draw(canvas)
    font_handle, _ = _find_font(size=25)
    font_meta, _ = _find_font(size=21)
    sep = "   |   "
    hw = draw.textlength(handle, font=font_handle)
    sw_ = draw.textlength(sep, font=font_meta)
    mw = draw.textlength(meta, font=font_meta)
    start_x = (size - (hw + sw_ + mw)) // 2
    base_y = band_top + band_h // 2 + 9
    draw.text((start_x, base_y), handle, font=font_handle, fill=COLOR_WHITE, anchor="ls")
    draw.text((start_x + hw, base_y), sep, font=font_meta, fill="#5A5650", anchor="ls")
    draw.text((start_x + hw + sw_, base_y), meta, font=font_meta, fill="#B9B3AB", anchor="ls")


def _draw_hero_number(draw, center, text: str, *, size: int, fill, baseline_y: int):
    """hero 数字を字間詰めで描く。 '.' の前後 advance を約 45% 詰めて間延びを消す。"""
    font, _ = _find_font(size=size)
    widths = [draw.textlength(ch, font=font) for ch in text]
    advances = []
    for i, ch in enumerate(text):
        w = widths[i]
        if ch in ".,":
            w *= 0.55
        elif i + 1 < len(text) and text[i + 1] in ".,":
            w *= 0.92
        advances.append(w)
    total = sum(advances)
    x = center - total / 2
    for ch, adv, w in zip(text, advances, widths):
        # 文字自体は左詰めで描き、 advance だけ詰める
        draw.text((x, baseline_y), ch, font=font, fill=fill, anchor="ls")
        x += adv


def _draw_compare_bars(canvas, draw, bars: list[dict], *, size: int, top: int):
    """横棒の比較 chart (最大3本)。 bars[i] = {label, value(float), display, highlight?}。"""
    bars = bars[:3]
    vmax = max((float(b.get("value") or 0) for b in bars), default=0.0)
    if vmax <= 0:
        return
    # 3本時は行高を詰めて hero card (下端 960) からはみ出さないようにする
    bar_x = 320
    bar_h, row_h = (28, 48) if len(bars) >= 3 else (34, 64)
    bar_w_max = size - bar_x - 230
    font_lb, _ = _find_font(size=26)
    for i, b in enumerate(bars):
        y = top + i * row_h
        v = float(b.get("value") or 0)
        w = max(10, int(bar_w_max * v / vmax))
        hl = bool(b.get("highlight"))
        draw.text((bar_x - 18, y + bar_h // 2), str(b.get("label", ""))[:9],
                  font=font_lb, fill=COLOR_TEXT if hl else COLOR_TEXT_SUB, anchor="rm")
        fill = _hex_to_rgb(COLOR_GIANTS_ROW_LEFT) + (255,) if hl else (210, 206, 200, 255)
        draw.rounded_rectangle((bar_x, y, bar_x + w, y + bar_h), radius=bar_h // 2,
                               fill=fill)
        _draw_crisp_text(draw, (bar_x + w + 16, y + bar_h // 2 + 12),
                         str(b.get("display", "")), size=30,
                         fill=COLOR_TEXT if hl else COLOR_TEXT_SUB, anchor="ls")


def _render_player_spotlight(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """1 選手の hero stat を巨大表示 (白 hero card に集約)。

    2026-06-12 洗練版: hero 数字の字間詰め / 「◯/◯時点」日付チップ /
    compare_bars (明示指定時のみ横棒比較 chart、 旧 sub_stats と排他) / 巨人 pill は
    全カード共通情報のため非表示既定 (player_team='巨人' の時 skip)。
    """
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=190,
    )

    # hero card (余白が間延びしないよう内容を 1 枚のカードへ)
    _rounded_card(canvas, (70, 280, size - 70, 960), radius=26, shadow=True)
    draw = ImageDraw.Draw(canvas)

    # 日付チップ (データ鮮度の明示)
    as_of = str(data.get("as_of", ""))
    if as_of:
        font_dt, _ = _find_font(size=24)
        draw.text((size - 100, 330), f"{as_of}時点", font=font_dt,
                  fill=COLOR_TEXT_SUB, anchor="rs")

    player_name = str(data.get("player_name", ""))
    player_team = str(data.get("player_team", ""))
    if player_name:
        font_pn, pn_path = _find_font(size=76)
        sw = 0 if _is_bold_font_path(pn_path) else 1
        name_w = draw.textlength(player_name, font=font_pn)
        nx = (size - name_w) // 2
        draw.text((nx, 405), player_name, font=font_pn, fill=COLOR_TEXT,
                  anchor="ls", stroke_width=sw, stroke_fill=COLOR_TEXT)
        _draw_crisp_text(draw, (nx + name_w + 18, 400), "★", size=40,
                         fill=COLOR_MEDAL_GOLD, anchor="ls")
    # 「巨人」は全カード共通で情報量ゼロのため pill を出さない (それ以外は従来通り)
    if player_team and player_team != "巨人":
        _pill_chip(canvas, (size // 2, 465), player_team, size=26,
                   bg=_hex_to_rgb(COLOR_GIANTS_ROW_LEFT) + (255,), fg=COLOR_WHITE)
        draw = ImageDraw.Draw(canvas)

    metric_label = str(data.get("metric_label", ""))
    if metric_label:
        _pill_chip(canvas, (size // 2, 535), metric_label, size=30,
                   bg=_hex_to_rgb("#262422") + (255,), fg=COLOR_GOLD)
        draw = ImageDraw.Draw(canvas)

    compare_bars = data.get("compare_bars") or []
    hero_value = str(data.get("hero_value", ""))
    if hero_value:
        hero_y = 770 if compare_bars else 805
        _draw_hero_number(draw, size // 2, hero_value, size=230,
                          fill=COLOR_GIANTS_ROW_LEFT, baseline_y=hero_y)

    if compare_bars:
        _draw_compare_bars(canvas, draw, compare_bars, size=size, top=812)
    else:
        sub_stats = (data.get("sub_stats", []) or [])[:2]
        if sub_stats:
            draw.line(((220, 838), (size - 220, 838)), fill=COLOR_CARD_BORDER, width=2)
            col_w = (size - 140) // len(sub_stats)
            for i, s in enumerate(sub_stats):
                x_center = 70 + col_w * i + col_w // 2
                font_sl, _ = _find_font(size=26)
                draw.text((x_center, 882), str(s.get("label", "")), font=font_sl,
                          fill=COLOR_TEXT_SUB, anchor="ms")
                _draw_crisp_text(draw, (x_center, 938), str(s.get("value", "")),
                                 size=48, fill=COLOR_TEXT, anchor="ms")

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

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=190,
    )

    player_name = str(data.get("player_name", ""))
    player_team = str(data.get("player_team", ""))
    if player_name:
        font_pn, pn_path = _find_font(size=64)
        sw = 0 if _is_bold_font_path(pn_path) else 1
        name_w = draw.textlength(player_name, font=font_pn)
        nx = (size - name_w) // 2
        draw.text((nx, 310), player_name, font=font_pn, fill=COLOR_TEXT,
                  anchor="ls", stroke_width=sw, stroke_fill=COLOR_TEXT)
        _draw_crisp_text(draw, (nx + name_w + 16, 306), "★", size=34,
                         fill=COLOR_MEDAL_GOLD, anchor="ls")
    if player_team:
        _pill_chip(canvas, (size // 2, 368), f"{player_team} / 投手", size=24,
                   bg=_hex_to_rgb(COLOR_GIANTS_ROW_LEFT) + (255,), fg=COLOR_WHITE)
        draw = ImageDraw.Draw(canvas)

    # stat grid 3x2 max 6 (角丸 cell、 highlight = orange gradient)
    stats = (data.get("stats", []) or [])[:6]
    cell_w, cell_h, gap = 300, 210, 16
    grid_x = (size - cell_w * 3 - gap * 2) // 2
    grid_y = 440
    for i, st in enumerate(stats):
        col = i % 3
        row = i // 3
        cx = grid_x + col * (cell_w + gap)
        cy = grid_y + row * (cell_h + gap)
        rect = (cx, cy, cx + cell_w, cy + cell_h)
        if st.get("highlight"):
            _rounded_gradient_card(canvas, rect, radius=20, shadow=True)
            label_fill = (255, 235, 220, 255)
            value_fill = COLOR_WHITE
        else:
            _rounded_card(canvas, rect, fill=COLOR_CARD, radius=20)
            label_fill = COLOR_TEXT_SUB
            value_fill = COLOR_TEXT
        draw = ImageDraw.Draw(canvas)
        font_label, _ = _find_font(size=27)
        draw.text((cx + cell_w // 2, cy + 56), str(st.get("label", "")),
                  font=font_label, fill=label_fill, anchor="ms")
        _draw_crisp_text(draw, (cx + cell_w // 2, cy + cell_h - 48),
                         str(st.get("value", "")), size=78,
                         fill=value_fill, anchor="ms")

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

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=190,
    )

    rows = data.get("rows", []) or []
    # 列ラベル行
    font_col, _ = _find_font(size=22)
    for label, x, anchor in (
        ("チーム", 160, "ls"), ("勝敗", 565, "ms"),
        ("勝率", 770, "ms"), ("ゲーム差", size - 72, "rs"),
    ):
        draw.text((x, 302), label, font=font_col, fill=COLOR_TEXT_SUB, anchor=anchor)

    row_h, gap = 92, 10
    start_y = 322
    for i, row in enumerate(rows[:6]):
        top = start_y + i * (row_h + gap)
        rect = (44, top, size - 44, top + row_h)
        cy = top + row_h // 2
        is_giants = bool(row.get("is_giants"))
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=16, shadow=True)
            color_main = COLOR_WHITE
            color_sub = (255, 235, 220, 255)
        else:
            _rounded_card(canvas, rect, radius=16)
            color_main = COLOR_TEXT
            color_sub = COLOR_TEXT_SUB
        draw = _rank_badge(canvas, (96, cy), row.get("rank", i + 1),
                           r=26, on_giants=is_giants)
        font_team, team_path = _find_font(size=40)
        sw = 0 if _is_bold_font_path(team_path) else 1
        draw.text((160, cy), str(row.get("team", "")), font=font_team,
                  fill=color_main, anchor="lm", stroke_width=sw, stroke_fill=color_main)
        font_record, _ = _find_font(size=30)
        draw.text((565, cy), str(row.get("record", "")), font=font_record,
                  fill=color_sub if not is_giants else color_main, anchor="mm")
        _draw_crisp_text(draw, (770, cy), str(row.get("win_pct", "")),
                         size=40, fill=color_main, anchor="mm")
        _draw_crisp_text(draw, (size - 72, cy), str(row.get("games_back", "")),
                         size=40, fill=color_main, anchor="rm")

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

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(
        canvas, draw, str(data.get("title", "")), str(data.get("subtitle", "")),
        str(data.get("hook_line", "")), size=size, header_h=160,
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
    row_h = 58
    start_y = 252
    bar_x = 240
    bar_max_w = 620
    bar_h = 34
    for i, t in enumerate(teams[:12]):
        y = start_y + i * row_h
        bar_w = max(bar_h, int(float(t.get("value", 0) or 0) / max_v * bar_max_w))
        is_giants = bool(t.get("is_giants"))
        font_rank, _ = _find_font(size=22)
        draw.text((34, y), str(i + 1), font=font_rank,
                  fill=COLOR_TEXT_SUB, anchor="lm")
        name_c = COLOR_GIANTS_ROW_LEFT if is_giants else COLOR_TEXT
        name_text = str(t.get("name", ""))
        # 長い球団名 (ソフトバンク 等) は縮小して rank と重ねない
        name_size = 29 if len(name_text) <= 5 else 24
        font_team, team_path = _find_font(size=name_size)
        sw = 0 if _is_bold_font_path(team_path) else 1
        draw.text((bar_x - 18, y), name_text, font=font_team,
                  fill=name_c, anchor="rm",
                  stroke_width=sw if is_giants else 0, stroke_fill=name_c)
        rect = (bar_x, y - bar_h // 2, bar_x + bar_w, y + bar_h // 2)
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=bar_h // 2, shadow=True)
        else:
            _rounded_card(canvas, rect, fill=COLOR_BAR_NEUTRAL,
                          radius=bar_h // 2, border=None, border_w=0)
        draw = ImageDraw.Draw(canvas)
        _draw_crisp_text(draw, (bar_x + bar_w + 16, y),
                         str(t.get("value_label", t.get("value", ""))),
                         size=30, fill=name_c if is_giants else COLOR_TEXT,
                         anchor="lm")

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

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
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
    row_h = 64
    start_y = 268
    bar_x = 265
    bar_max_w = 600
    bar_h = 36
    for i, r in enumerate(rows[:10]):
        y = start_y + i * row_h
        bar_w = max(bar_h, int(_val(r) / max_v * bar_max_w))
        is_giants = bool(r.get("is_giants"))
        font_rank, _ = _find_font(size=22)
        draw.text((52, y), str(r.get("rank", i + 1)), font=font_rank,
                  fill=COLOR_TEXT_SUB, anchor="lm")
        name_c = COLOR_GIANTS_ROW_LEFT if is_giants else COLOR_TEXT
        font_name, name_path = _find_font(size=28)
        sw = 0 if _is_bold_font_path(name_path) else 1
        draw.text((bar_x - 18, y), str(r.get("name", "")), font=font_name,
                  fill=name_c, anchor="rm",
                  stroke_width=sw if is_giants else 0, stroke_fill=name_c)
        rect = (bar_x, y - bar_h // 2, bar_x + bar_w, y + bar_h // 2)
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=bar_h // 2, shadow=True)
        else:
            _rounded_card(canvas, rect, fill=COLOR_BAR_NEUTRAL,
                          radius=bar_h // 2, border=None, border_w=0)
        draw = ImageDraw.Draw(canvas)
        _draw_crisp_text(draw, (bar_x + bar_w + 16, y), str(r.get("value", "")),
                         size=30, fill=name_c if is_giants else COLOR_TEXT,
                         anchor="lm")
    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_monthly_summary(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """上位 3 人 + 数値を大きく hero 表示 (週/月ハイライト風)。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=200)
    rows = (data.get("rows", []) or [])[:3]
    if not rows:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    # 3 段の hero card (角丸 + rank badge)
    card_y_start = 290
    card_h = 200
    card_gap = 20
    for i, r in enumerate(rows):
        cy_top = card_y_start + i * (card_h + card_gap)
        rect = (60, cy_top, size - 60, cy_top + card_h)
        cy = cy_top + card_h // 2
        is_giants = bool(r.get("is_giants"))
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=22, shadow=True)
            name_color = COLOR_WHITE
            val_color = COLOR_WHITE
            team_color = (255, 235, 220, 255)
        else:
            _rounded_card(canvas, rect, radius=22, shadow=False)
            name_color = COLOR_TEXT
            val_color = COLOR_TEXT
            team_color = COLOR_TEXT_SUB
        draw = _rank_badge(canvas, (150, cy), r.get("rank", i + 1),
                           r=44, on_giants=is_giants)
        font_name, name_path = _find_font(size=56)
        sw = 0 if _is_bold_font_path(name_path) else 1
        draw.text((250, cy - 24), str(r.get("name", "")), font=font_name,
                  fill=name_color, anchor="lm", stroke_width=sw, stroke_fill=name_color)
        if is_giants:
            name_w = draw.textlength(str(r.get("name", "")), font=font_name)
            _draw_crisp_text(draw, (250 + name_w + 14, cy - 8), "★", size=32,
                             fill=COLOR_GOLD, anchor="ls")
        font_team, _ = _find_font(size=26)
        draw.text((250, cy + 42), str(r.get("team", "")), font=font_team,
                  fill=team_color, anchor="lm")
        _draw_crisp_text(draw, (size - 92, cy), str(r.get("value", "")),
                         size=80, fill=val_color, anchor="rm")
    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_data_sheet(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """TOP10 を高密度表で。 ranking_table より行数多めで小さい font。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=200)
    rows = data.get("rows", []) or []
    if not rows:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    # 表全体を 1 枚の白カードに載せ、 ヘッダ帯 + zebra で密度を整える
    table_y = 268
    table_h = 50 + 62 * min(len(rows), 10) + 14
    _rounded_card(canvas, (40, table_y, size - 40, table_y + table_h),
                  radius=20, shadow=True)
    from PIL import Image as _Image
    header_band = _Image.new("RGB", (size - 96, 44), "#23211E")
    canvas.paste(header_band, (48, table_y + 8))
    draw = ImageDraw.Draw(canvas)
    font_h, _ = _find_font(size=22)
    headers = [("順位", 100), ("選手", 380), ("球団", 660), ("数値", 960)]
    for label, x in headers:
        draw.text((x, table_y + 30), label, font=font_h,
                  fill="#CFC9C2", anchor="mm")

    row_h = 62
    for i, r in enumerate(rows[:10]):
        y = table_y + 52 + i * row_h
        is_giants = bool(r.get("is_giants"))
        if is_giants:
            _rounded_gradient_card(canvas, (48, y + 2, size - 48, y + row_h - 2),
                                   radius=10, shadow=False)
            name_c = COLOR_WHITE
            team_c = (255, 235, 220, 255)
            val_c = COLOR_WHITE
        else:
            if i % 2 == 1:
                _rounded_card(canvas, (48, y + 2, size - 48, y + row_h - 2),
                              fill="#F7F5F2", radius=10, border=None, border_w=0)
            name_c = COLOR_TEXT
            team_c = COLOR_TEXT_SUB
            val_c = COLOR_TEXT
        draw = _rank_badge(canvas, (100, y + row_h // 2), r.get("rank", i + 1),
                           r=19, on_giants=is_giants)
        font_name, name_path = _find_font(size=30)
        sw = 0 if _is_bold_font_path(name_path) else 1
        draw.text((380, y + row_h // 2), str(r.get("name", "")), font=font_name,
                  fill=name_c, anchor="mm",
                  stroke_width=sw if is_giants else 0, stroke_fill=name_c)
        font_team, _ = _find_font(size=22)
        draw.text((660, y + row_h // 2), str(r.get("team", "")), font=font_team,
                  fill=team_c, anchor="mm")
        _draw_crisp_text(draw, (960, y + row_h // 2), str(r.get("value", "")),
                         size=36, fill=val_c, anchor="mm")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_12team_crown(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """rows から球団別 TOP1 (冠) を集計して 12 球団 grid で表示。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
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

    # grid 3 cols × 4 rows (角丸 cell)
    cols = 3
    gap = 14
    cell_w = (size - 100 - gap * (cols - 1)) // cols
    cell_h = 152
    start_y = 274
    for i, (team, r) in enumerate(teams):
        col = i % cols
        row_i = i // cols
        cx = 50 + col * (cell_w + gap)
        cy = start_y + row_i * (cell_h + gap)
        rect = (cx, cy, cx + cell_w, cy + cell_h)
        is_giants = bool(r.get("is_giants")) or team == "巨人"
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=18, shadow=True)
            rank_c = COLOR_WHITE
            team_c = COLOR_WHITE
            pl_c = (255, 235, 220, 255)
        else:
            _rounded_card(canvas, rect, radius=18)
            rank_c = COLOR_GIANTS_ROW_LEFT
            team_c = COLOR_TEXT
            pl_c = COLOR_TEXT_SUB
        draw = ImageDraw.Draw(canvas)
        _draw_crisp_text(draw, (cx + cell_w // 2, cy + 58), f"#{r.get('rank', '?')}",
                         size=58, fill=rank_c, anchor="mm")
        _draw_crisp_text(draw, (cx + cell_w // 2, cy + 106), team,
                         size=28, fill=team_c, anchor="mm")
        font_pl, _ = _find_font(size=21)
        draw.text((cx + cell_w // 2, cy + 134), str(r.get("name", "")),
                  font=font_pl, fill=pl_c, anchor="mm")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_starting_lineup(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """TOP9 を打順表風 3×3 grid で。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=200)

    rows = (data.get("rows", []) or [])[:9]
    cols = 3
    gap = 14
    cell_w = (size - 100 - gap * (cols - 1)) // cols
    cell_h = 200
    start_y = 272
    for i, r in enumerate(rows):
        col = i % cols
        row_i = i // cols
        cx = 50 + col * (cell_w + gap)
        cy = start_y + row_i * (cell_h + gap)
        rect = (cx, cy, cx + cell_w, cy + cell_h)
        is_giants = bool(r.get("is_giants"))
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=18, shadow=True)
            name_c = COLOR_WHITE
            val_c = COLOR_WHITE
            team_c = (255, 235, 220, 255)
        else:
            _rounded_card(canvas, rect, radius=18)
            name_c = COLOR_TEXT
            val_c = COLOR_TEXT
            team_c = COLOR_TEXT_SUB
        draw = _rank_badge(canvas, (cx + cell_w // 2, cy + 52),
                           r.get("rank", i + 1), r=28, on_giants=is_giants)
        font_name, name_path = _find_font(size=30)
        sw = 0 if _is_bold_font_path(name_path) else 1
        draw.text((cx + cell_w // 2, cy + 112), str(r.get("name", "")),
                  font=font_name, fill=name_c, anchor="mm",
                  stroke_width=sw if is_giants else 0, stroke_fill=name_c)
        _draw_crisp_text(draw, (cx + cell_w // 2, cy + 150), str(r.get("value", "")),
                         size=38, fill=val_c, anchor="mm")
        font_team, _ = _find_font(size=19)
        draw.text((cx + cell_w // 2, cy + 182), str(r.get("team", "")),
                  font=font_team, fill=team_c, anchor="mm")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_scoreboard(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """TOP1 player と「残り合計」 をスコア風に対比表示。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
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

    # スコアボード 2 cells (leader vs rest avg、 角丸カード + 中央 VS badge)
    sb_y = 330
    sb_h = 400
    half_w = (size - 100 - 24) // 2
    lx = 50
    leader_cx = lx + half_w // 2
    if leader.get("is_giants"):
        _rounded_gradient_card(canvas, (lx, sb_y, lx + half_w, sb_y + sb_h),
                               radius=24, shadow=True)
        leader_label_c = (255, 235, 220, 255)
        leader_val_c = COLOR_WHITE
        leader_name_c = COLOR_WHITE
    else:
        _rounded_card(canvas, (lx, sb_y, lx + half_w, sb_y + sb_h),
                      radius=24, shadow=True)
        leader_label_c = COLOR_TEXT_SUB
        leader_val_c = COLOR_TEXT
        leader_name_c = COLOR_TEXT
    draw = ImageDraw.Draw(canvas)

    font_label, _ = _find_font(size=28)
    draw.text((leader_cx, sb_y + 56), "TOP", font=font_label,
              fill=leader_label_c, anchor="mm")
    _draw_crisp_text(draw, (leader_cx, sb_y + 124), str(leader.get("name", "")),
                     size=44, fill=leader_name_c, anchor="mm")
    _draw_crisp_text(draw, (leader_cx, sb_y + 248), str(leader.get("value", "")),
                     size=120, fill=leader_val_c, anchor="mm")
    draw.text((leader_cx, sb_y + sb_h - 44), str(leader.get("team", "")),
              font=font_label, fill=leader_label_c, anchor="mm")

    # rest cell
    rx = lx + half_w + 24
    rest_cx = rx + half_w // 2
    _rounded_card(canvas, (rx, sb_y, rx + half_w, sb_y + sb_h), radius=24, shadow=True)
    draw = ImageDraw.Draw(canvas)
    draw.text((rest_cx, sb_y + 56), "他 平均", font=font_label,
              fill=COLOR_TEXT_SUB, anchor="mm")
    font_name, _ = _find_font(size=40)
    draw.text((rest_cx, sb_y + 124), f"{len(rest)} 人",
              font=font_name, fill=COLOR_TEXT, anchor="mm")
    avg_text = f"{rest_avg:.3f}" if rest_avg < 10 else f"{rest_avg:.1f}"
    _draw_crisp_text(draw, (rest_cx, sb_y + 248), avg_text,
                     size=120, fill=COLOR_TEXT, anchor="mm")
    draw.text((rest_cx, sb_y + sb_h - 44), "2-10位", font=font_label,
              fill=COLOR_TEXT_SUB, anchor="mm")

    # VS badge (2 カードの境界中央に円 overlay)
    from PIL import Image as _Image
    vs_layer = _Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    vd = ImageDraw.Draw(vs_layer)
    vs_cy = sb_y + sb_h // 2
    vd.ellipse((size // 2 - 44, vs_cy - 44, size // 2 + 44, vs_cy + 44),
               fill=_hex_to_rgb("#23211E") + (255,))
    canvas.alpha_composite(vs_layer)
    draw = ImageDraw.Draw(canvas)
    _draw_crisp_text(draw, (size // 2, vs_cy + 2), "VS", size=34,
                     fill=COLOR_GOLD, anchor="mm")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _parse_stat_value(raw: object) -> float | None:
    """".867" / "2.45" / "12" 等の表示文字列を float に。 解釈不能は None。"""
    s = str(raw or "").replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _format_stat_diff(diff: float, *, leading_dot: bool) -> str:
    """対決カードの差分表示。 counting 系は整数、 率系は .3f を trim。"""
    text = f"{abs(diff):.3f}".rstrip("0").rstrip(".")
    if not text:
        text = "0"
    if leading_dot and text.startswith("0."):
        text = text[1:]
    return text


def _render_podium_top3(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """TOP3 を表彰台 (2位-1位-3位) で。 4-6位は下部に小さく添える。

    2026-06-11 variation 追加: list / grid 系と違う「式典」mood。
    """
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=190)

    rows = data.get("rows", []) or []
    top3 = rows[:3]
    if not top3:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    # 表彰台 slot: (row, x1, 台の高さ)。 中央 = 1位 が最も高い。
    col_w, gap = 296, 28
    x_left = (size - col_w * 3 - gap * 2) // 2
    base_y = 830
    slots = [(top3[0], x_left + col_w + gap, 380)]
    if len(top3) >= 2:
        slots.append((top3[1], x_left, 290))
    if len(top3) >= 3:
        slots.append((top3[2], x_left + (col_w + gap) * 2, 230))

    for row, px, plat_h in slots:
        plat_top = base_y - plat_h
        rect = (px, plat_top, px + col_w, base_y)
        is_giants = bool(row.get("is_giants"))
        rank_n = row.get("rank", "?")
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=20, shadow=True)
            val_c = COLOR_WHITE
        else:
            _rounded_card(canvas, rect, radius=20, shadow=True)
            val_c = COLOR_TEXT
        cx = px + col_w // 2
        # 台の上 (overhang): 1位だけ王冠代わりの金star → 名前 → 球団
        draw = ImageDraw.Draw(canvas)
        try:
            is_first = int(rank_n) == 1
        except (TypeError, ValueError):
            is_first = False
        if is_first:
            _draw_crisp_text(draw, (cx, plat_top - 124), "★", size=46,
                             fill=COLOR_MEDAL_GOLD, anchor="ms")
        name_c = COLOR_GIANTS_ROW_LEFT if is_giants else COLOR_TEXT
        _draw_crisp_text(draw, (cx, plat_top - 68), str(row.get("name", "")),
                         size=40, fill=name_c, anchor="ms")
        font_team, _ = _find_font(size=24)
        draw.text((cx, plat_top - 30), str(row.get("team", "")),
                  font=font_team, fill=COLOR_TEXT_SUB, anchor="ms")
        # 台の中: rank badge (メダル色) + 値
        draw = _rank_badge(canvas, (cx, plat_top + 52), rank_n, r=32,
                           on_giants=is_giants)
        _draw_crisp_text(draw, (cx, base_y - max(38, plat_h // 2 - 28)),
                         str(row.get("value", "")), size=64,
                         fill=val_c, anchor="mm")

    # 4-6位 strip (1 行 3 列の小カード)
    extras = rows[3:6]
    if extras:
        strip = (x_left, 866, size - x_left, 982)
        _rounded_card(canvas, strip, radius=18, shadow=False)
        draw = ImageDraw.Draw(canvas)
        col = (strip[2] - strip[0]) // len(extras)
        for i, r in enumerate(extras):
            ex = strip[0] + col * i + col // 2
            is_giants = bool(r.get("is_giants"))
            name_c = COLOR_GIANTS_ROW_LEFT if is_giants else COLOR_TEXT
            font_rk, _ = _find_font(size=22)
            draw.text((ex, 902), f"{r.get('rank', i + 4)}位", font=font_rk,
                      fill=COLOR_TEXT_SUB, anchor="ms")
            _draw_crisp_text(draw, (ex, 938), str(r.get("name", "")),
                             size=27, fill=name_c, anchor="ms")
            font_v, _ = _find_font(size=24)
            draw.text((ex, 970), str(r.get("value", "")), font=font_v,
                      fill=COLOR_TEXT_SUB, anchor="ms")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_focus_duel(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """巨人 focus 選手 vs 隣接 rival の 1on1 対決 (左=orange / 右=dark の対比)。

    2026-06-11 variation 追加。 scoreboard (TOP1 vs 残り平均) と違い、
    巨人選手と直接のライバル 1 人を選んで個 vs 個 で見せる。
    """
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=160)

    rows = data.get("rows", []) or []
    if len(rows) < 2:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    # focus = 最上位の巨人 row (居なければ 1位)。 rival = 1 つ上の順位
    # (focus が先頭なら 1 つ下)。
    focus_i = next((i for i, r in enumerate(rows) if r.get("is_giants")), 0)
    rival_i = focus_i - 1 if focus_i > 0 else focus_i + 1
    focus, rival = rows[focus_i], rows[rival_i]

    card_y, card_b = 220, 930
    half_w = (size - 80 - 24) // 2
    lx, rx = 40, 40 + half_w + 24
    _rounded_gradient_card(canvas, (lx, card_y, lx + half_w, card_b),
                           radius=26, shadow=True)
    _rounded_card(canvas, (rx, card_y, rx + half_w, card_b),
                  fill=COLOR_NIGHT_CARD, radius=26,
                  border=COLOR_NIGHT_BORDER, shadow=True)
    draw = ImageDraw.Draw(canvas)

    for r, cx, name_c, sub_c, val_c in (
        (focus, lx + half_w // 2, COLOR_WHITE, (255, 235, 220, 255), COLOR_WHITE),
        (rival, rx + half_w // 2, COLOR_NIGHT_TEXT, COLOR_NIGHT_SUB, COLOR_GOLD),
    ):
        font_rank, _ = _find_font(size=30)
        draw.text((cx, 300), f"{r.get('rank', '?')}位", font=font_rank,
                  fill=sub_c, anchor="ms")
        name = str(r.get("name", ""))
        name_size = 52 if len(name) <= 5 else 42
        _draw_crisp_text(draw, (cx, 392), name, size=name_size,
                         fill=name_c, anchor="ms")
        font_team, _ = _find_font(size=26)
        draw.text((cx, 442), str(r.get("team", "")), font=font_team,
                  fill=sub_c, anchor="ms")
        _draw_crisp_text(draw, (cx, 660), str(r.get("value", "")),
                         size=110, fill=val_c, anchor="mm")

    # 中央 VS 円
    vs_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    vd = ImageDraw.Draw(vs_layer)
    vs_cy = (card_y + card_b) // 2
    vd.ellipse((size // 2 - 46, vs_cy - 46, size // 2 + 46, vs_cy + 46),
               fill=_hex_to_rgb("#23211E") + (255,))
    canvas.alpha_composite(vs_layer)
    draw = ImageDraw.Draw(canvas)
    _draw_crisp_text(draw, (size // 2, vs_cy + 2), "VS", size=36,
                     fill=COLOR_GOLD, anchor="mm")

    # 差分 chip (両値が数値解釈できる時だけ)
    fv = _parse_stat_value(focus.get("value"))
    rv = _parse_stat_value(rival.get("value"))
    if fv is not None and rv is not None and fv != rv:
        leading_dot = str(focus.get("value", "")).startswith(".") and \
            str(rival.get("value", "")).startswith(".")
        diff_text = _format_stat_diff(fv - rv, leading_dot=leading_dot)
        label = "リード" if fv > rv else "差"
        _pill_chip(canvas, (size // 2, 848), f"{label} {diff_text}",
                   size=28, bg=(0, 0, 0, 200), fg=COLOR_GOLD)
        draw = ImageDraw.Draw(canvas)

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_dark_hero(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """night 仕様: warm dark 下地に hero 数字を orange glow で大きく。

    2026-06-11 variation 追加。 hero = 最上位の巨人 row (居なければ 1位)。
    下部に TOP3 mini list を添える。
    """
    from PIL import Image, ImageDraw, ImageFilter

    canvas = Image.new("RGBA", (size, size), COLOR_NIGHT_BG)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=160)

    rows = data.get("rows", []) or []
    if not rows:
        _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                           str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
        return canvas

    hero = next((r for r in rows if r.get("is_giants")), rows[0])
    hero_name = str(hero.get("name", ""))
    if hero_name:
        _draw_crisp_text(draw, (size // 2, 330), hero_name, size=64,
                         fill=COLOR_NIGHT_TEXT, anchor="ms")
    rank_label = f"セ・リーグ {hero.get('rank', '?')}位 ・ {hero.get('team', '')}"
    _pill_chip(canvas, (size // 2, 396), rank_label, size=25,
               bg=(0, 0, 0, 170), fg=COLOR_GOLD)

    # hero value: orange glow 層 → 本体 (白寄り) の 2 段重ね
    hero_value = str(hero.get("value", ""))
    if hero_value:
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        font_glow, _ = _find_font(size=228)
        gd.text((size // 2, 700), hero_value, font=font_glow,
                fill=_hex_to_rgb(COLOR_HEADER_TOP) + (200,), anchor="ms")
        glow = glow.filter(ImageFilter.GaussianBlur(radius=18))
        canvas.alpha_composite(glow)
        draw = ImageDraw.Draw(canvas)
        _draw_crisp_text(draw, (size // 2, 700), hero_value, size=228,
                         fill="#FFE8D6", anchor="ms")

    # TOP3 mini list
    for i, r in enumerate(rows[:3]):
        top = 766 + i * 70
        rect = (140, top, size - 140, top + 58)
        cy = top + 29
        is_giants = bool(r.get("is_giants"))
        if is_giants:
            _rounded_gradient_card(canvas, rect, radius=14, shadow=False)
            name_c = val_c = COLOR_WHITE
        else:
            _rounded_card(canvas, rect, fill=COLOR_NIGHT_CARD, radius=14,
                          border=COLOR_NIGHT_BORDER)
            name_c = COLOR_NIGHT_TEXT
            val_c = COLOR_NIGHT_SUB
        draw = _rank_badge(canvas, (186, cy), r.get("rank", i + 1), r=20,
                           on_giants=is_giants)
        font_name, name_path = _find_font(size=30)
        sw = 0 if _is_bold_font_path(name_path) else 1
        draw.text((232, cy), str(r.get("name", "")), font=font_name,
                  fill=name_c, anchor="lm",
                  stroke_width=sw if is_giants else 0, stroke_fill=name_c)
        _draw_crisp_text(draw, (size - 168, cy), str(r.get("value", "")),
                         size=32, fill=val_c, anchor="rm")

    _draw_footer_block(canvas, draw, str(data.get("footer_handle", DEFAULT_FOOTER_HANDLE)),
                       str(data.get("footer_meta", DEFAULT_FOOTER_META)), size=size)
    return canvas


def _render_win_split(data: dict[str, Any], size: int = DEFAULT_SIZE):
    """勝利相関カード: 条件あり (orange) vs なし (dark) の勝率対比。

    2026-06-11 角度 v2。 「選手が活躍した試合、 巨人は強い」を 1 枚で。
    data: player_name / cond_label / a_label / a_record / a_rate /
          b_label / b_record / b_rate / diff_label。
    """
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), COLOR_CANVAS)
    draw = ImageDraw.Draw(canvas)
    _draw_header_block(canvas, draw, str(data.get("title", "")),
                       str(data.get("subtitle", "")),
                       str(data.get("hook_line", "")), size=size, header_h=160)

    player_name = str(data.get("player_name", ""))
    if player_name:
        _draw_crisp_text(draw, (size // 2, 300), player_name, size=60,
                         fill=COLOR_TEXT, anchor="ms")
    cond_label = str(data.get("cond_label", ""))
    if cond_label:
        _pill_chip(canvas, (size // 2, 366), cond_label, size=27,
                   bg=_hex_to_rgb("#262422") + (255,), fg=COLOR_GOLD)

    card_y, card_b = 430, 880
    half_w = (size - 80 - 24) // 2
    lx, rx = 40, 40 + half_w + 24
    _rounded_gradient_card(canvas, (lx, card_y, lx + half_w, card_b),
                           radius=26, shadow=True)
    _rounded_card(canvas, (rx, card_y, rx + half_w, card_b),
                  fill=COLOR_NIGHT_CARD, radius=26,
                  border=COLOR_NIGHT_BORDER, shadow=True)
    draw = ImageDraw.Draw(canvas)
    sides = (
        (data.get("a_label", "あり"), data.get("a_record", ""),
         data.get("a_rate", ""), lx + half_w // 2,
         COLOR_WHITE, (255, 235, 220, 255), COLOR_WHITE),
        (data.get("b_label", "なし"), data.get("b_record", ""),
         data.get("b_rate", ""), rx + half_w // 2,
         COLOR_NIGHT_TEXT, COLOR_NIGHT_SUB, COLOR_GOLD),
    )
    for label, record, rate, cx, main_c, sub_c, rate_c in sides:
        font_l, _ = _find_font(size=32)
        draw.text((cx, 510), str(label), font=font_l, fill=sub_c, anchor="ms")
        _draw_crisp_text(draw, (cx, 600), str(record), size=52,
                         fill=main_c, anchor="ms")
        _draw_crisp_text(draw, (cx, 770), str(rate), size=104,
                         fill=rate_c, anchor="ms")
        font_cap, _ = _find_font(size=24)
        draw.text((cx, 830), "勝率", font=font_cap, fill=sub_c, anchor="ms")

    # 中央 VS 円 + 下部 差分 chip
    vs_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    vd = ImageDraw.Draw(vs_layer)
    vs_cy = (card_y + card_b) // 2
    vd.ellipse((size // 2 - 42, vs_cy - 42, size // 2 + 42, vs_cy + 42),
               fill=_hex_to_rgb("#23211E") + (255,))
    canvas.alpha_composite(vs_layer)
    draw = ImageDraw.Draw(canvas)
    _draw_crisp_text(draw, (size // 2, vs_cy + 2), "VS", size=32,
                     fill=COLOR_GOLD, anchor="mm")
    diff_label = str(data.get("diff_label", ""))
    if diff_label:
        _pill_chip(canvas, (size // 2, 940), diff_label, size=30,
                   bg=(0, 0, 0, 200), fg=COLOR_GOLD)
        draw = ImageDraw.Draw(canvas)

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
    "podium_top3": _render_podium_top3,
    "focus_duel": _render_focus_duel,
    "dark_hero": _render_dark_hero,
    "win_split": _render_win_split,
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
    compare_bars: list[dict[str, Any]] | None = None,
    as_of: str = "",
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    """compare_bars[i] = {label, value(float), display, highlight?} 最大3本。
    指定時は sub_stats の代わりに横棒比較 chart を描く。 as_of 例 '6/12'。"""
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "player_name": player_name,
        "player_team": player_team,
        "metric_label": metric_label,
        "hero_value": hero_value,
        "sub_stats": sub_stats or [],
        "compare_bars": compare_bars or [],
        "as_of": as_of,
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


def build_win_split_data(
    *,
    title: str,
    subtitle: str,
    hook_line: str,
    player_name: str,
    cond_label: str,
    a_label: str = "あり",
    a_record: str = "",
    a_rate: str = "",
    b_label: str = "なし",
    b_record: str = "",
    b_rate: str = "",
    diff_label: str = "",
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    """勝利相関 (win_split) data。 a 側=条件成立 (orange)、 b 側=不成立 (dark)。"""
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "player_name": player_name,
        "cond_label": cond_label,
        "a_label": a_label,
        "a_record": a_record,
        "a_rate": a_rate,
        "b_label": b_label,
        "b_record": b_record,
        "b_rate": b_rate,
        "diff_label": diff_label,
        "footer_handle": footer_handle,
        "footer_meta": footer_meta,
    }
