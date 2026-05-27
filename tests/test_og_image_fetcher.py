"""Tests for og_image_fetcher (ticket 438 Phase 1)."""

from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock, patch

from src import og_image_fetcher as ogf


class _FakeResponse:
    """Stand-in for requests.Response that supports .raw.read() / .close()."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict | None = None,
        encoding: str = "utf-8",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = encoding
        self.content = content
        self.raw = io.BytesIO(content)

    def close(self) -> None:
        pass


class ExtractOgImageUrlTests(unittest.TestCase):
    def test_property_first(self) -> None:
        html = '<meta property="og:image" content="https://example.com/a.jpg">'
        self.assertEqual(ogf._extract_og_image_url(html), "https://example.com/a.jpg")

    def test_content_first(self) -> None:
        html = '<meta content="https://example.com/b.png" property="og:image">'
        self.assertEqual(ogf._extract_og_image_url(html), "https://example.com/b.png")

    def test_twitter_image(self) -> None:
        html = '<meta name="twitter:image" content="https://example.com/c.jpg">'
        self.assertEqual(ogf._extract_og_image_url(html), "https://example.com/c.jpg")

    def test_twitter_image_src(self) -> None:
        html = '<meta name="twitter:image:src" content="https://example.com/d.jpg">'
        self.assertEqual(ogf._extract_og_image_url(html), "https://example.com/d.jpg")

    def test_missing(self) -> None:
        self.assertEqual(ogf._extract_og_image_url("<html>no meta</html>"), "")

    def test_empty(self) -> None:
        self.assertEqual(ogf._extract_og_image_url(""), "")

    def test_html_entity_in_url(self) -> None:
        """fetch_og_image side で _html.unescape を通すが、 抽出 regex は literal で取る。"""
        html = '<meta property="og:image" content="https://example.com/a.jpg?x=1&amp;y=2">'
        self.assertEqual(
            ogf._extract_og_image_url(html),
            "https://example.com/a.jpg?x=1&amp;y=2",
        )


class FetchOgImageTests(unittest.TestCase):
    def test_empty_url(self) -> None:
        self.assertIsNone(ogf.fetch_og_image(""))

    def test_happy_path(self) -> None:
        html = b'<meta property="og:image" content="https://example.com/img.jpg">'
        img_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        html_resp = _FakeResponse(content=html, encoding="utf-8")
        img_resp = _FakeResponse(content=img_bytes, headers={"Content-Type": "image/png"})
        fake_get = MagicMock(side_effect=[html_resp, img_resp])
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            result = ogf.fetch_og_image("https://example.com/article")
        self.assertIsNotNone(result)
        self.assertEqual(result.image_bytes, img_bytes)
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual(result.image_url, "https://example.com/img.jpg")
        # 2 回 GET (HTML + image) されている
        self.assertEqual(fake_get.call_count, 2)

    def test_no_og_image_meta(self) -> None:
        html = b"<html><head><title>no og</title></head></html>"
        fake_get = MagicMock(return_value=_FakeResponse(content=html))
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            self.assertIsNone(ogf.fetch_og_image("https://example.com/a"))
        # image GET は呼ばれない
        self.assertEqual(fake_get.call_count, 1)

    def test_html_4xx(self) -> None:
        fake_get = MagicMock(return_value=_FakeResponse(status_code=404))
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            self.assertIsNone(ogf.fetch_og_image("https://example.com/missing"))

    def test_image_4xx(self) -> None:
        html = b'<meta property="og:image" content="https://example.com/x.jpg">'
        html_resp = _FakeResponse(content=html)
        img_resp = _FakeResponse(status_code=404)
        fake_get = MagicMock(side_effect=[html_resp, img_resp])
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            self.assertIsNone(ogf.fetch_og_image("https://example.com/a"))

    def test_image_size_over_limit(self) -> None:
        html = b'<meta property="og:image" content="https://example.com/big.jpg">'
        # 6 MiB の dummy bytes (上限 5 MiB を超える)
        img_bytes = b"x" * (6 * 1024 * 1024)
        html_resp = _FakeResponse(content=html)
        img_resp = _FakeResponse(content=img_bytes)
        fake_get = MagicMock(side_effect=[html_resp, img_resp])
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            self.assertIsNone(ogf.fetch_og_image("https://example.com/a"))

    def test_relative_image_url_absolutized(self) -> None:
        html = b'<meta property="og:image" content="/static/img.jpg">'
        img_bytes = b"PNGDATA"
        html_resp = _FakeResponse(content=html)
        img_resp = _FakeResponse(content=img_bytes, headers={"Content-Type": "image/jpeg"})
        fake_get = MagicMock(side_effect=[html_resp, img_resp])
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            result = ogf.fetch_og_image("https://example.com/article/123")
        self.assertIsNotNone(result)
        # 相対 → absolute に変換されている
        self.assertEqual(result.image_url, "https://example.com/static/img.jpg")

    def test_html_entity_decoded_in_image_url(self) -> None:
        html = b'<meta property="og:image" content="https://example.com/a.jpg?x=1&amp;y=2">'
        img_bytes = b"PNG"
        html_resp = _FakeResponse(content=html)
        img_resp = _FakeResponse(content=img_bytes)
        fake_get = MagicMock(side_effect=[html_resp, img_resp])
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            result = ogf.fetch_og_image("https://example.com/a")
        self.assertIsNotNone(result)
        # &amp; が & にデコードされる
        self.assertEqual(result.image_url, "https://example.com/a.jpg?x=1&y=2")

    def test_network_exception_silent(self) -> None:
        fake_get = MagicMock(side_effect=ConnectionError("no network"))
        with patch.object(ogf, "requests", MagicMock(get=fake_get)):
            self.assertIsNone(ogf.fetch_og_image("https://example.com/a"))


class TryFetchOgImageForCandidateTests(unittest.TestCase):
    """`x_post_branding_gen._try_fetch_og_image_for_candidate` の挙動 (438)。"""

    def setUp(self) -> None:
        import logging
        self.log = logging.getLogger("test_try_fetch")

    def _fake_result(self) -> ogf.OgImageResult:
        return ogf.OgImageResult(
            image_bytes=b"PNGDATA",
            content_type="image/png",
            image_url="https://example.com/img.jpg",
        )

    def test_success(self) -> None:
        from src import x_post_branding_gen as xbg
        with patch("src.og_image_fetcher.fetch_og_image", return_value=self._fake_result()):
            b, alt, url = xbg._try_fetch_og_image_for_candidate(
                source_url="https://hochi.news/articles/test",
                source_name="スポーツ報知",
                log=self.log,
            )
        self.assertEqual(b, b"PNGDATA")
        self.assertEqual(alt, "引用元: スポーツ報知")
        self.assertEqual(url, "https://example.com/img.jpg")

    def test_twitter_url_silently_skipped(self) -> None:
        from src import x_post_branding_gen as xbg
        b, alt, url = xbg._try_fetch_og_image_for_candidate(
            source_url="https://twitter.com/hochi_giants/status/123",
            source_name="hochi_giants",
            log=self.log,
        )
        self.assertEqual((b, alt, url), (b"", "", ""))

    def test_x_com_url_silently_skipped(self) -> None:
        from src import x_post_branding_gen as xbg
        b, alt, url = xbg._try_fetch_og_image_for_candidate(
            source_url="https://x.com/sanspo_giants/status/456",
            source_name="sanspo",
            log=self.log,
        )
        self.assertEqual((b, alt, url), (b"", "", ""))

    def test_fetch_returns_none(self) -> None:
        from src import x_post_branding_gen as xbg
        with patch("src.og_image_fetcher.fetch_og_image", return_value=None):
            b, alt, url = xbg._try_fetch_og_image_for_candidate(
                source_url="https://hochi.news/articles/missing",
                source_name="報知",
                log=self.log,
            )
        self.assertEqual((b, alt, url), (b"", "", ""))

    def test_empty_source_url(self) -> None:
        from src import x_post_branding_gen as xbg
        b, alt, url = xbg._try_fetch_og_image_for_candidate(
            source_url="",
            source_name="",
            log=self.log,
        )
        self.assertEqual((b, alt, url), (b"", "", ""))

    def test_empty_source_name_fallback(self) -> None:
        from src import x_post_branding_gen as xbg
        with patch("src.og_image_fetcher.fetch_og_image", return_value=self._fake_result()):
            b, alt, url = xbg._try_fetch_og_image_for_candidate(
                source_url="https://hochi.news/articles/x",
                source_name="",
                log=self.log,
            )
        self.assertEqual(alt, "引用元: 媒体")

    def test_unexpected_exception_silent(self) -> None:
        from src import x_post_branding_gen as xbg
        with patch("src.og_image_fetcher.fetch_og_image", side_effect=RuntimeError("boom")):
            b, alt, url = xbg._try_fetch_og_image_for_candidate(
                source_url="https://hochi.news/articles/y",
                source_name="報知",
                log=self.log,
            )
        self.assertEqual((b, alt, url), (b"", "", ""))


if __name__ == "__main__":
    unittest.main()
