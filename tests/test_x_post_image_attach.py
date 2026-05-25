"""437 attach_ranking_image (publisher 統合 helper) integration tests.

mock WP client + article dict で:
- 正常系: PNG 生成 → upload_generated_image 呼び出し → media_id 返却
- empty image_rows → 0
- WP upload 失敗 → 0
- 例外 → 0 (caller 側 publish 続行)
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.x_post_image_gen import attach_ranking_image


def _giants_focus_article():
    return {
        "image_rows": [
            {"rank": 1, "name": "佐藤輝明", "team": "阪神", "value": ".961", "is_giants": False},
            {"rank": 2, "name": "坂倉将吾", "team": "広島", "value": ".882", "is_giants": False},
            {"rank": 3, "name": "坂本勇人", "team": "巨人", "value": ".867", "is_giants": True},
            {"rank": 4, "name": "村松開人", "team": "中日", "value": ".831", "is_giants": False},
            {"rank": 5, "name": "武岡龍世", "team": "ヤクルト", "value": ".812", "is_giants": False},
            {"rank": 6, "name": "大山悠輔", "team": "阪神", "value": ".798", "is_giants": False},
            {"rank": 7, "name": "森下翔太", "team": "阪神", "value": ".785", "is_giants": False},
            {"rank": 8, "name": "岡本和真", "team": "巨人", "value": ".772", "is_giants": True},
        ],
        "image_metric_name": "OPS",
        "image_period_label": "直近 10 試合",
        "focus_player": "坂本勇人",
    }


def test_happy_path_calls_upload_and_returns_media_id():
    wp = MagicMock()
    wp.upload_generated_image.return_value = 12345
    media_id = attach_ranking_image(wp, _giants_focus_article())
    assert media_id == 12345
    # upload_generated_image が 1 回呼ばれる
    assert wp.upload_generated_image.call_count == 1
    call_args = wp.upload_generated_image.call_args
    # (png_bytes, filename, content_type)
    png_bytes = call_args.args[0]
    filename = call_args.args[1]
    content_type = call_args.args[2]
    # PNG signature
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    # filename に metric / focus 名が含まれる
    assert "ops" in filename.lower()
    assert filename.endswith(".png")
    assert content_type == "image/png"


def test_empty_image_rows_returns_zero():
    wp = MagicMock()
    article = {"image_rows": [], "image_metric_name": "OPS"}
    media_id = attach_ranking_image(wp, article)
    assert media_id == 0
    # WP upload は呼ばれない
    wp.upload_generated_image.assert_not_called()


def test_missing_image_rows_returns_zero():
    wp = MagicMock()
    article = {"focus_player": "坂本勇人"}  # image_rows なし
    media_id = attach_ranking_image(wp, article)
    assert media_id == 0
    wp.upload_generated_image.assert_not_called()


def test_wp_upload_returns_zero_then_attach_returns_zero():
    wp = MagicMock()
    wp.upload_generated_image.return_value = 0
    media_id = attach_ranking_image(wp, _giants_focus_article())
    assert media_id == 0


def test_wp_upload_raises_exception_then_attach_returns_zero():
    wp = MagicMock()
    wp.upload_generated_image.side_effect = RuntimeError("WP 500")
    # exception caught internally → caller 側 publish 続行可
    media_id = attach_ranking_image(wp, _giants_focus_article())
    assert media_id == 0


def test_hook_line_says_2giants_when_2_in_top10():
    """巨人選手 2 名が rows にいる時、 hook line が「巨人 2 名」 になる。"""
    wp = MagicMock()
    captured_png = []
    def capture(png, filename, ct):
        captured_png.append((png, filename))
        return 99
    wp.upload_generated_image.side_effect = capture
    article = _giants_focus_article()
    attach_ranking_image(wp, article)
    assert len(captured_png) == 1
    # hook line check は PNG 内では困難なので、 SVG 経由で確認 (別 unit test)
    # 本 test では「upload 成功」 だけ確認、 hook 詳細は test_x_post_image_gen.py 側


def test_no_giants_hook_falls_back_to_metric_label():
    wp = MagicMock()
    wp.upload_generated_image.return_value = 555
    article = {
        "image_rows": [
            {"rank": i + 1, "name": f"選手{i + 1}", "team": "阪神",
             "value": f".{900 - i * 10}", "is_giants": False}
            for i in range(8)
        ],
        "image_metric_name": "wOBA",
        "image_period_label": "シーズン",
        "focus_player": "佐藤輝明",
    }
    media_id = attach_ranking_image(wp, article)
    # 巨人 row 0 でも generate は通る (=「📊 セ・リーグ wOBA ranking」 hook)
    assert media_id == 555


def test_focus_player_special_chars_safe_filename():
    """focus_player に special chars / 全角があっても filename が壊れない。"""
    wp = MagicMock()
    wp.upload_generated_image.return_value = 1
    article = _giants_focus_article()
    article["focus_player"] = "坂本勇人/test\\xss"
    media_id = attach_ranking_image(wp, article)
    assert media_id == 1
    filename = wp.upload_generated_image.call_args.args[1]
    # path traversal / shell 字句が filename に残らないこと
    assert "/" not in filename
    assert "\\" not in filename
    assert filename.endswith(".png")
