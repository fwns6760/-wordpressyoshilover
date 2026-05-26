"""437 Phase 2C: x_post_image_gen_v2 + x_post_image_attach_x の orchestrator
integration test (X live post には触れず、 mock のみ)。

scope:
  - PNG 生成 → attach_x_post_image (mock) で media_id_string が返るチェーン
  - 生成失敗時 (None) → attach 呼ばれず None 連鎖
  - upload 失敗時 → media_id_string None で text-only fallback 可能な状態

CLI sample generator (src/tools/generate_x_post_image_sample.py) も unit 化する。
"""
from __future__ import annotations

import io
import struct
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _png_size(png_bytes: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png_bytes[16:24])


# ---------- orchestrator chain (gen → attach mock) ----------


def test_gen_to_attach_chain_returns_media_id():
    from src.x_post_image_attach_x import attach_x_post_image
    from src.x_post_image_gen_v2 import build_ranking_data, generate_png

    rows = [
        {"rank": 1, "name": "坂本勇人", "team": "巨人", "value": ".867", "is_giants": True},
        {"rank": 2, "name": "岡本和真", "team": "巨人", "value": ".772", "is_giants": True},
    ]
    data = build_ranking_data(
        title="t", subtitle="s", hook_line="★ ★", rows=rows
    )
    png = generate_png("ranking_table", data)
    assert png is not None
    assert _png_size(png) == (1080, 1080)

    fake_api = MagicMock()
    media = MagicMock()
    media.media_id_string = "1111222233334444"
    fake_api.media_upload.return_value = media

    media_id = attach_x_post_image(fake_api, png)
    assert media_id == "1111222233334444"
    fake_api.media_upload.assert_called_once()


def test_gen_failure_propagates_to_attach_skip():
    """generate_png が None を返したら attach 側で early-return すべき。"""
    from src.x_post_image_attach_x import attach_x_post_image

    fake_api = MagicMock()
    media_id = attach_x_post_image(fake_api, b"")
    assert media_id is None
    fake_api.media_upload.assert_not_called()


def test_attach_failure_does_not_corrupt_png():
    """attach 失敗時に caller は同じ PNG bytes を text-only fallback で
    再利用できる (純粋 wrapper、 副作用なし)。"""
    import tweepy

    from src.x_post_image_attach_x import attach_x_post_image
    from src.x_post_image_gen_v2 import build_ranking_data, generate_png

    rows = [{"rank": 1, "name": "A", "team": "巨人", "value": "1.0", "is_giants": True}]
    data = build_ranking_data(title="t", subtitle="s", hook_line="h", rows=rows)
    png = generate_png("ranking_table", data)
    assert png is not None
    original = bytes(png)

    fake_api = MagicMock()
    fake_api.media_upload.side_effect = tweepy.TweepyException("fail")
    media_id = attach_x_post_image(fake_api, png)
    assert media_id is None
    # PNG bytes 自体は変更されていない (caller が text-only fallback で使える)
    assert png == original


# ---------- CLI sample generator ----------


def test_sample_cli_writes_png_file(tmp_path):
    """src/tools/generate_x_post_image_sample.py を subprocess で叩いて PNG
    file を出力できる。 stdout に保存先 path が出る。"""
    output = tmp_path / "sample.png"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "src/tools/generate_x_post_image_sample.py"),
            "--output",
            str(output),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert output.exists()
    png_bytes = output.read_bytes()
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert _png_size(png_bytes) == (1080, 1080)
    assert str(output) in result.stdout


def test_sample_cli_emoji_override(tmp_path):
    """--emoji-start / --emoji-end / --hook flag が伝わる。"""
    output = tmp_path / "sample_no_emoji.png"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "src/tools/generate_x_post_image_sample.py"),
            "--output",
            str(output),
            "--emoji-start",
            "",
            "--emoji-end",
            "",
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert output.exists()


def test_sample_cli_hook_override(tmp_path):
    output = tmp_path / "sample_custom_hook.png"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "src/tools/generate_x_post_image_sample.py"),
            "--output",
            str(output),
            "--hook",
            "★ カスタム hook ★",
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert output.exists()
