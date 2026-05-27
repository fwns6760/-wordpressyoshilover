"""Tests for image_quote_overlay (ticket 438 Phase 2)."""

from __future__ import annotations

import io
import unittest

from src.image_quote_overlay import apply_quote_overlay, _wrap_text_by_pixel_width


def _make_test_image_bytes(width: int = 1200, height: int = 800, color=(120, 60, 20)) -> bytes:
    """Generate a simple solid-color JPEG/PNG for overlay testing."""
    try:
        from PIL import Image
    except Exception:  # pragma: no cover - skip when Pillow unavailable
        raise unittest.SkipTest("Pillow not installed")
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class ApplyQuoteOverlayTests(unittest.TestCase):
    def test_happy_path_returns_png_bytes(self) -> None:
        try:
            image_bytes = _make_test_image_bytes()
        except unittest.SkipTest as exc:
            self.skipTest(str(exc))
        out = apply_quote_overlay(
            image_bytes,
            speaker="戸郷翔征",
            quote=(
                "最後までしっかり集中して投げ切ることができた。"
                "バッテリーともしっかり話してマウンドに上がった。"
                "ストレートも変化球も思った通りに行った"
            ),
        )
        self.assertIsInstance(out, bytes)
        self.assertGreater(len(out), 1000)
        # PNG magic
        self.assertEqual(out[:8], b"\x89PNG\r\n\x1a\n")

    def test_size_preserved(self) -> None:
        try:
            from PIL import Image
            image_bytes = _make_test_image_bytes(1080, 720)
        except unittest.SkipTest as exc:
            self.skipTest(str(exc))
        except Exception:
            self.skipTest("Pillow not installed")
        out = apply_quote_overlay(
            image_bytes,
            speaker="坂本勇人",
            quote="今日はチームとして勝ち切れて良かった。" * 4,
        )
        img = Image.open(io.BytesIO(out))
        self.assertEqual(img.size, (1080, 720))

    def test_empty_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            apply_quote_overlay(b"", speaker="戸郷", quote="長 quote")
        try:
            image_bytes = _make_test_image_bytes()
        except unittest.SkipTest as exc:
            self.skipTest(str(exc))
        with self.assertRaises(ValueError):
            apply_quote_overlay(image_bytes, speaker="", quote="長 quote")
        with self.assertRaises(ValueError):
            apply_quote_overlay(image_bytes, speaker="戸郷", quote="")

    def test_too_small_image_raises(self) -> None:
        """image が overlay block より小さい時は ValueError → caller 側 Pattern A fallback."""
        try:
            small = _make_test_image_bytes(200, 100)
        except unittest.SkipTest as exc:
            self.skipTest(str(exc))
        with self.assertRaises(ValueError):
            apply_quote_overlay(
                small,
                speaker="戸郷翔征",
                quote="長い quote " * 30,
            )


class WrapTextTests(unittest.TestCase):
    def test_empty_returns_empty_list(self) -> None:
        try:
            from PIL import ImageFont
            from src.x_post_image_gen_v2 import _find_font
            font, _ = _find_font(20)
        except Exception:  # pragma: no cover
            self.skipTest("font not available")
        self.assertEqual(_wrap_text_by_pixel_width("", font, 100), [])

    def test_single_line_short_text(self) -> None:
        try:
            from src.x_post_image_gen_v2 import _find_font
            font, _ = _find_font(30)
        except Exception:
            self.skipTest("font not available")
        out = _wrap_text_by_pixel_width("短い", font, 1000)
        self.assertEqual(out, ["短い"])

    def test_multi_line_wrap(self) -> None:
        try:
            from src.x_post_image_gen_v2 import _find_font
            font, _ = _find_font(40)
        except Exception:
            self.skipTest("font not available")
        text = "あ" * 50  # 50 chars × 40px ≈ 2000px → multi line at 500px max
        out = _wrap_text_by_pixel_width(text, font, 500)
        self.assertGreater(len(out), 1)
        # 連結すると元 text に戻る
        self.assertEqual("".join(out), text)


if __name__ == "__main__":
    unittest.main()
