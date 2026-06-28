"""Wikimedia Commons から「商用利用可の free ライセンス写真のみ」を取得する。

著作権ハードルール(§18)対応: ネット画像の無断転載は致命的NG。一方 Commons の
**free ライセンス画像(CC0 / Public domain / CC BY / CC BY-SA)** は、ライセンス条件
(= 著作者クレジット表示)を守れば商用利用が合法。本モジュールは画像ごとに license
メタデータを API で確認し、**商用可のものだけ**採用し、**クレジット文字列を必ず返す**。

非free(fair use)/ NC(非営利限定)/ ND(改変禁止 = 動画に使えない)は自動で弾く。
取得できなければ None を返し、呼び出し側は自社 eyecatch / 頭文字カードに fallback する。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
from typing import Any

import requests

LOG = logging.getLogger(__name__)

WIKI_API_JA = "https://ja.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "yoshilover-yt-shorts/1.0 (Giants data shorts; rights-aware Commons fetch; "
    "contact fwns6760@gmail.com)"
)
DEFAULT_CACHE_DIR = Path("/tmp/yt_shorts_commons")

# 商用利用OKと判定する license コード/語(machine code or short name の小文字)。
# "attribution" = CC Attribution(無印 = free), "gfdl" = 商用可(継承条件付き)。
_FREE_HINTS = (
    "cc0", "cc-by", "cc by", "public domain", "publicdomain", "pdm", "pd-",
    "attribution", "gfdl",
)
# これを含むものは弾く: 非営利(NC) / 改変禁止(ND) / 非free / fair use。
# machine code("cc-by-nc-sa-4.0")と short name("...NonCommercial...")両対応。
_BLOCK_HINTS = (
    "noncommercial", "non-commercial", "by-nc", "-nc-", "-nc.", "-nc ",
    "noderiv", "no-deriv", "by-nd", "-nd-", "-nd.", "-nd ",
    "non-free", "nonfree", "fair use", "fairuse", "all rights reserved",
)


@dataclass(frozen=True)
class CommonsPhoto:
    local_path: str
    license: str
    artist: str
    attribution: str        # 動画/概要欄に出すクレジット 1 行
    file_page_url: str


def _session_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()


def is_commercial_free(license_code: str, short_name: str = "") -> bool:
    """license が商用利用可(CC0/PD/CC-BY/CC-BY-SA)なら True。NC/ND/非free は False。"""
    blob = f"{license_code or ''} {short_name or ''}".lower()
    if not blob.strip():
        return False
    # ND / NC / 非free を最優先で弾く(CC BY-NC-SA 等の取りこぼし防止)。
    if any(bad in blob for bad in _BLOCK_HINTS):
        return False
    return any(hint in blob for hint in _FREE_HINTS)


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _lead_image_filename(title: str) -> str | None:
    try:
        data = _session_get(
            WIKI_API_JA,
            {
                "action": "query",
                "prop": "pageimages",
                "piprop": "name",
                "titles": title,
                "redirects": 1,
                "format": "json",
            },
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("commons_lead_image_failed title=%s err=%r", title, exc)
        return None
    pages = (data.get("query") or {}).get("pages") or {}
    for _, page in pages.items():
        name = page.get("pageimage")
        if name:
            return str(name)
    return None


def _image_info(filename: str) -> dict[str, Any] | None:
    try:
        data = _session_get(
            COMMONS_API,
            {
                "action": "query",
                "prop": "imageinfo",
                "iiprop": "extmetadata|url",
                "titles": "File:" + filename,
                "format": "json",
            },
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("commons_imageinfo_failed file=%s err=%r", filename, exc)
        return None
    pages = (data.get("query") or {}).get("pages") or {}
    for _, page in pages.items():
        info = (page.get("imageinfo") or [None])[0]
        if info:
            return info
    return None


def _build_attribution(short_name: str, artist: str) -> str:
    artist = _strip_html(artist)
    lic = short_name or "Wikimedia Commons"
    if artist:
        return f"写真: {artist} / {lic} / Wikimedia Commons"
    return f"写真: {lic} / Wikimedia Commons"


def _download(url: str, cache_dir: Path) -> str | None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        ext = ".jpg"
        m = re.search(r"\.(jpg|jpeg|png)$", url, re.IGNORECASE)
        if m:
            ext = "." + m.group(1).lower()
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ext
        target = cache_dir / name
        if target.exists() and target.stat().st_size > 0:
            return str(target)
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        target.write_bytes(r.content)
        return str(target)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("commons_download_failed url=%s err=%r", url, exc)
        return None


_CACHE: dict[str, CommonsPhoto | None] = {}


def fetch_commons_photo(
    player_name: str,
    *,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> CommonsPhoto | None:
    """選手名 → Commons の free ライセンス写真(商用可)+ クレジット。無ければ None。"""
    key = str(player_name or "").strip()
    if not key:
        return None
    if key in _CACHE:
        return _CACHE[key]

    result: CommonsPhoto | None = None
    filename = _lead_image_filename(key)
    if filename:
        info = _image_info(filename)
        if info:
            em = info.get("extmetadata") or {}
            short = (em.get("LicenseShortName") or {}).get("value") or ""
            code = (em.get("License") or {}).get("value") or ""
            artist = (em.get("Artist") or {}).get("value") or ""
            url = info.get("url") or ""
            if url and is_commercial_free(code, short):
                local = _download(url, Path(cache_dir))
                if local:
                    result = CommonsPhoto(
                        local_path=local,
                        license=short or code,
                        artist=_strip_html(artist),
                        attribution=_build_attribution(short or code, artist),
                        file_page_url=f"https://commons.wikimedia.org/wiki/File:{filename}",
                    )
            else:
                LOG.info("commons_photo_rejected player=%s license=%s", key, short or code)
    _CACHE[key] = result
    return result


__all__ = [
    "CommonsPhoto",
    "fetch_commons_photo",
    "is_commercial_free",
]
