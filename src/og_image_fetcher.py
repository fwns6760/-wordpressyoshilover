"""og:image fetcher for X-post comment candidates (ticket 438).

source article URL から `<meta property="og:image">` または
`<meta name="twitter:image">` を抽出し、 画像 bytes を返す。

設計:
- timeout: HTML / image それぞれ 5 秒
- User-Agent: facebookexternalhit (open graph 標準爬虫の慣用)
- 失敗 (network / parse / 5xx / X.com 等の認証要求) は静かに None
  返却し、 caller 側で image なし候補として扱う
- 画像 size 上限: 5MB (X media spec)
- HTML 取得 size 上限: 1MB (parse 用)

438 Phase 1: x_post_mail_lane の build_gemma_branding_candidate /
build_x_post_from_article_info から呼ばれる。
"""

from __future__ import annotations

import html as _html
import logging
import re as _re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

try:
    import requests  # type: ignore[import-untyped]
except Exception:  # noqa: BLE001
    requests = None  # type: ignore[assignment]


LOG = logging.getLogger(__name__)


_HTML_TIMEOUT_SECONDS = 5.0
_IMAGE_TIMEOUT_SECONDS = 5.0
_HTML_BYTE_LIMIT = 1_048_576  # 1 MiB
_IMAGE_BYTE_LIMIT = 5_242_880  # 5 MiB (X media spec)
_DEFAULT_USER_AGENT = "facebookexternalhit/1.1"

# Open Graph / Twitter Card meta tag patterns. quote 区別を吸収するため
# 単純な regex 2 系統 + content 抽出を 1 つにまとめる。
_META_OG_IMAGE_RE = _re.compile(
    r"""<meta\s+[^>]*?(?:property|name)\s*=\s*['"](?:og:image|twitter:image|twitter:image:src)['"][^>]*?content\s*=\s*['"]([^'"]+)['"]""",
    _re.IGNORECASE | _re.DOTALL,
)
_META_OG_IMAGE_RE_REVERSED = _re.compile(
    r"""<meta\s+[^>]*?content\s*=\s*['"]([^'"]+)['"][^>]*?(?:property|name)\s*=\s*['"](?:og:image|twitter:image|twitter:image:src)['"]""",
    _re.IGNORECASE | _re.DOTALL,
)


@dataclass(frozen=True)
class OgImageResult:
    image_bytes: bytes
    content_type: str
    image_url: str


def fetch_og_image(
    article_url: str,
    *,
    timeout_seconds: float = _HTML_TIMEOUT_SECONDS,
    user_agent: str = _DEFAULT_USER_AGENT,
    logger: Optional[logging.Logger] = None,
) -> Optional[OgImageResult]:
    """``article_url`` から og:image を抽出して bytes を返す.

    失敗時は None を返す (例外は raise しない)。
    """
    log = logger or LOG
    url = (article_url or "").strip()
    if not url:
        return None
    if requests is None:
        log.warning("og_image_fetcher_skip reason=requests_not_available url=%s", url)
        return None
    headers = {"User-Agent": user_agent}

    try:
        # stream=False で content-encoding (gzip/br) を requests に自動 decompress
        # させる。 stream=True + raw.read() は 圧縮 bytes をそのまま返すため
        # og:image meta が見えない事故になる (sanspo / hochi 等は gzip 配信)。
        resp = requests.get(url, headers=headers, timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        log.info("og_image_fetcher_skip reason=html_fetch_failed url=%s err=%r", url, exc)
        return None
    if resp.status_code >= 400:
        log.info(
            "og_image_fetcher_skip reason=html_http_%d url=%s",
            resp.status_code, url,
        )
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            pass
        return None

    try:
        # resp.content は decompress 済 bytes。 上限で truncate。
        content = resp.content[:_HTML_BYTE_LIMIT]
    except Exception as exc:  # noqa: BLE001
        log.info("og_image_fetcher_skip reason=html_read_failed url=%s err=%r", url, exc)
        return None
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            pass

    encoding = resp.encoding or "utf-8"
    try:
        text = content.decode(encoding, errors="ignore")
    except Exception:  # noqa: BLE001
        text = content.decode("utf-8", errors="ignore")

    image_url = _extract_og_image_url(text)
    if not image_url:
        log.info("og_image_fetcher_skip reason=og_image_meta_missing url=%s", url)
        return None

    # relative URL を absolute へ。 X / mainstream media は通常 absolute だが念のため。
    image_url = urljoin(url, _html.unescape(image_url))

    try:
        # 画像は通常 binary でそのまま (Content-Encoding なし) だが、 念のため
        # stream=False で auto decompress に任せる (CDN が変な gzip 付けても安全)。
        img_resp = requests.get(image_url, headers=headers, timeout=_IMAGE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        log.info("og_image_fetcher_skip reason=image_fetch_failed image_url=%s err=%r", image_url, exc)
        return None
    if img_resp.status_code >= 400:
        log.info(
            "og_image_fetcher_skip reason=image_http_%d image_url=%s",
            img_resp.status_code, image_url,
        )
        try:
            img_resp.close()
        except Exception:  # noqa: BLE001
            pass
        return None

    try:
        image_bytes = img_resp.content
    except Exception as exc:  # noqa: BLE001
        log.info("og_image_fetcher_skip reason=image_read_failed url=%s err=%r", image_url, exc)
        return None
    finally:
        try:
            img_resp.close()
        except Exception:  # noqa: BLE001
            pass

    if not image_bytes:
        log.info("og_image_fetcher_skip reason=image_empty url=%s", image_url)
        return None
    if len(image_bytes) > _IMAGE_BYTE_LIMIT:
        log.info(
            "og_image_fetcher_skip reason=image_too_large size=%d url=%s",
            len(image_bytes), image_url,
        )
        return None

    content_type = (img_resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
    return OgImageResult(image_bytes=image_bytes, content_type=content_type, image_url=image_url)


def _extract_og_image_url(html_text: str) -> str:
    """parse meta og:image / twitter:image from HTML."""
    if not html_text:
        return ""
    # property/name → content の順
    m = _META_OG_IMAGE_RE.search(html_text)
    if m:
        return m.group(1).strip()
    # content → property/name の順 (報知などで時々ある)
    m = _META_OG_IMAGE_RE_REVERSED.search(html_text)
    if m:
        return m.group(1).strip()
    return ""


__all__ = ["OgImageResult", "fetch_og_image"]
