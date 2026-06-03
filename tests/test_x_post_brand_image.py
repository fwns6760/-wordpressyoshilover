"""Tests for x_post_brand_image (style B branding card, ¥0 PIL, CJK-safe)."""
from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from PIL import Image

from src import x_post_brand_image as bi


def _png(w, h, color=(20, 90, 160)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


class RenderBrandCardBTests(unittest.TestCase):
    def test_with_photo_returns_square_png(self):
        png = bi.render_brand_card_b(_png(800, 1000))
        im = Image.open(io.BytesIO(png))
        self.assertEqual(im.size, (1080, 1080))
        self.assertEqual(im.format, "PNG")

    def test_none_photo_uses_placeholder(self):
        png = bi.render_brand_card_b(None)
        self.assertGreater(len(png), 1000)
        self.assertEqual(Image.open(io.BytesIO(png)).size, (1080, 1080))

    def test_garbage_bytes_graceful(self):
        # 不正な画像bytesでも crash せず placeholder で1枚返す
        png = bi.render_brand_card_b(b"not-an-image")
        self.assertEqual(Image.open(io.BytesIO(png)).size, (1080, 1080))

    def test_cover_crop_fills_target(self):
        out = bi._cover_crop(Image.new("RGB", (400, 1200)), 670, 1080)
        self.assertEqual(out.size, (670, 1080))


class BuildBrandImageForPlayerTests(unittest.TestCase):
    def test_fetch_failure_still_returns_placeholder_image(self):
        # 写真取得が None でも placeholder 画像を返す (常に1枚)
        with patch.object(bi, "_fetch_player_photo_bytes", return_value=None):
            png = bi.build_brand_image_for_player("岡本和真")
        self.assertIsNotNone(png)
        self.assertEqual(Image.open(io.BytesIO(png)).size, (1080, 1080))

    def test_uses_fetched_photo(self):
        with patch.object(bi, "_fetch_player_photo_bytes", return_value=_png(900, 900)):
            png = bi.build_brand_image_for_player("坂本勇人")
        self.assertEqual(Image.open(io.BytesIO(png)).size, (1080, 1080))
