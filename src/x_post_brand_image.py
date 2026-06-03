"""x_post_brand_image — ブランディング用おしゃれ画像 (style B: 写真 | ブランドパネル)。

2026-06-03 user 確定: X-post ブランディング投稿に「データなし・おしゃれ系」の
ヨシラバー・ブランド画像を1枚添付する。AI 画像生成は使わず (課金回避)、 既存の
選手写真を Pillow で合成 = ¥0。 日本語は IPAGothic / Noto CJK で描画 (cairosvg の
CJK 豆腐事故 437 を回避、 本番 Docker に font 同梱済)。

style B (mock 承認): 左 62% に選手写真 (cover crop)、 右 38% に黒×オレンジ
グラデパネル + 白区切り線 + 「ヨシラバー」 wordmark + tagline。
"""
from __future__ import annotations

import io
import logging
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

LOG = logging.getLogger(__name__)

# 本番 Docker 同梱フォント (Dockerfile.x_post_mail: fonts-ipafont-gothic / fonts-noto-cjk)
_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)

_ORANGE = (255, 111, 0)
_BLACK = (17, 17, 17)
_WHITE = (255, 255, 255)
_DEFAULT_TAGLINE = ("巨人を、", "もっと熱く。")


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # 最終 fallback (CJK 不可だが crash 回避)
    return ImageFont.load_default()


def _cover_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """img を (w,h) に cover (中央 crop してアスペクト維持で埋める)。"""
    img = img.convert("RGB")
    sw, sh = img.size
    if sw <= 0 or sh <= 0:
        return Image.new("RGB", (w, h), (40, 44, 52))
    scale = max(w / sw, h / sh)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 3  # 顔が上寄りになりがちなので少し上を残す
    return img.crop((left, top, left + w, top + h))


def render_brand_card_b(
    photo_bytes: Optional[bytes],
    *,
    tagline_lines: Sequence[str] = _DEFAULT_TAGLINE,
    size: int = 1080,
    brand_text: str = "ヨシラバー",
) -> bytes:
    """style B のブランド画像 PNG bytes を返す。

    photo_bytes が空/不正でも crash せず、 左パネルは暗色 placeholder で描画
    (graceful、 呼び出し側は常に1枚得られる)。
    """
    W = H = int(size)
    photo_w = int(W * 0.62)
    panel_w = W - photo_w

    canvas = Image.new("RGB", (W, H), _BLACK)

    # 左: 選手写真 (cover)。 取得失敗時は暗色グラデの placeholder。
    if photo_bytes:
        try:
            ph = _cover_crop(Image.open(io.BytesIO(photo_bytes)), photo_w, H)
        except Exception as exc:  # noqa: BLE001
            LOG.info("brand_card photo decode failed (placeholder): %r", exc)
            ph = None
    else:
        ph = None
    if ph is None:
        ph = Image.new("RGB", (photo_w, H), (40, 44, 52))
        pd = ImageDraw.Draw(ph)
        for y in range(H):
            t = y / H
            pd.line([(0, y), (photo_w, y)], fill=(int(30 + t * 25), int(33 + t * 28), int(40 + t * 30)))
    canvas.paste(ph, (0, 0))

    d = ImageDraw.Draw(canvas)
    # 右: オレンジ→黒 縦グラデパネル
    for x in range(photo_w, W):
        t = (x - photo_w) / max(1, panel_w)
        c = (
            int(_ORANGE[0] - t * (_ORANGE[0] - _BLACK[0])),
            int(_ORANGE[1] - t * (_ORANGE[1] - _BLACK[1])),
            int(_ORANGE[2] - t * (_ORANGE[2] - _BLACK[2])),
        )
        d.line([(x, 0), (x, H)], fill=c)
    # 白区切り線
    d.rectangle([photo_w, 0, photo_w + 6, H], fill=_WHITE)

    cx = photo_w + panel_w // 2
    # wordmark
    d.text((cx, H // 2 - 70), brand_text, font=_font(56), fill=_WHITE, anchor="mm")
    # tagline
    line_font = _font(40)
    base_y = H // 2 + 10
    for i, line in enumerate(tagline_lines):
        # 全行白 (グラデ暗部での黒文字低コントラストを回避)。 視認性のため細い影を敷く。
        d.text((cx + 2, base_y + i * 56 + 2), str(line), font=line_font, fill=(0, 0, 0), anchor="mm")
        d.text((cx, base_y + i * 56), str(line), font=line_font, fill=_WHITE, anchor="mm")

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


# --- 選手写真の取得 (eyecatch map → 公開WP media → bytes、 auth 不要) ---

import json as _json  # noqa: E402
import os as _os  # noqa: E402
import urllib.request as _urlreq  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_EYECATCH_MAP_PATH = _Path(__file__).resolve().parent.parent / "config" / "player_eyecatch_map.json"
_GIANTS_MARK_MEDIA_ID = 63578  # 巨人マーク (写真が無い選手の fallback)
_WP_BASE = "https://yoshilover.com"
_photo_cache: dict = {}


def _load_eyecatch_map() -> dict:
    try:
        return _json.loads(_EYECATCH_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.info("brand_card eyecatch map load failed: %r", exc)
        return {}


def _media_source_url(media_id: int) -> str:
    """公開 WP REST で media の source_url を取得 (published media は auth 不要)。"""
    try:
        req = _urlreq.Request(
            f"{_WP_BASE}/wp-json/wp/v2/media/{int(media_id)}?_fields=source_url",
            headers={"User-Agent": "yoshilover-brand-img/1.0"},
        )
        with _urlreq.urlopen(req, timeout=12) as r:
            return str((_json.load(r) or {}).get("source_url", "")).strip()
    except Exception as exc:  # noqa: BLE001
        LOG.info("brand_card media source_url fail id=%s: %r", media_id, exc)
        return ""


def _fetch_player_photo_bytes(player_name: str) -> Optional[bytes]:
    """player → eyecatch map → media_id → 公開URL → bytes。 無ければ巨人マーク。"""
    name = str(player_name or "").strip()
    if name in _photo_cache:
        return _photo_cache[name]
    mp = _load_eyecatch_map()
    info = mp.get(name) or mp.get(name.replace(" ", "")) or mp.get(name.replace("　", ""))
    media_id = int(info.get("id")) if info and info.get("id") else _GIANTS_MARK_MEDIA_ID
    url = _media_source_url(media_id)
    if not url and media_id != _GIANTS_MARK_MEDIA_ID:
        url = _media_source_url(_GIANTS_MARK_MEDIA_ID)
    data = None
    if url:
        try:
            with _urlreq.urlopen(_urlreq.Request(url, headers={"User-Agent": "yoshilover-brand-img/1.0"}), timeout=12) as r:
                data = r.read()
        except Exception as exc:  # noqa: BLE001
            LOG.info("brand_card photo fetch fail %s: %r", url, exc)
            data = None
    _photo_cache[name] = data
    return data


def build_brand_image_for_player(
    player_name: str,
    *,
    tagline_lines: Sequence[str] = _DEFAULT_TAGLINE,
) -> Optional[bytes]:
    """focus 選手の写真を取得 → style B ブランド画像 PNG を返す。

    写真取得に失敗しても placeholder で1枚生成して返す (常に画像が付く)。
    例外時のみ None (呼び出し側は画像なしで続行)。
    """
    try:
        photo = _fetch_player_photo_bytes(player_name)
        return render_brand_card_b(photo, tagline_lines=tagline_lines)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_brand_image_for_player failed player=%s: %r", player_name, exc)
        return None
