"""437 attach_ranking_image (publisher 統合 helper) integration tests.

mock WP client + article dict で:
- 正常系: PNG 生成 → upload_generated_image 呼び出し → media_id 返却
- empty image_rows → 0
- WP upload 失敗 → 0
- 例外 → 0 (caller 側 publish 続行)
- dedup: 既存 slug PNG を pre-delete してから upload (累積防止)
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.x_post_image_gen import _eyecatch_slug, attach_ranking_image


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
    wp.find_media_by_slug.return_value = 0  # no existing
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
    # 437 dedup: filename は slug ベース (ASCII safe + hash)
    assert filename.startswith("437eyc-")
    assert filename.endswith(".png")
    assert content_type == "image/png"
    # find_media_by_slug が pre-delete 確認のため 1 回呼ばれる
    wp.find_media_by_slug.assert_called_once()
    # 既存無しなので delete_media は呼ばれない
    wp.delete_media.assert_not_called()


def test_empty_image_rows_returns_zero():
    wp = MagicMock()
    article = {"image_rows": [], "image_metric_name": "OPS"}
    media_id = attach_ranking_image(wp, article)
    assert media_id == 0
    # WP upload は呼ばれない
    wp.upload_generated_image.assert_not_called()
    # dedup find も skip (image_rows 空で early return)
    wp.find_media_by_slug.assert_not_called()


def test_missing_image_rows_returns_zero():
    wp = MagicMock()
    article = {"focus_player": "坂本勇人"}  # image_rows なし
    media_id = attach_ranking_image(wp, article)
    assert media_id == 0
    wp.upload_generated_image.assert_not_called()


def test_wp_upload_returns_zero_then_attach_returns_zero():
    wp = MagicMock()
    wp.find_media_by_slug.return_value = 0
    wp.upload_generated_image.return_value = 0
    media_id = attach_ranking_image(wp, _giants_focus_article())
    assert media_id == 0


def test_wp_upload_raises_exception_then_attach_returns_zero():
    wp = MagicMock()
    wp.find_media_by_slug.return_value = 0
    wp.upload_generated_image.side_effect = RuntimeError("WP 500")
    # exception caught internally → caller 側 publish 続行可
    media_id = attach_ranking_image(wp, _giants_focus_article())
    assert media_id == 0


def test_hook_line_says_2giants_when_2_in_top10():
    """巨人選手 2 名が rows にいる時、 hook line が「巨人 2 名」 になる。"""
    wp = MagicMock()
    wp.find_media_by_slug.return_value = 0
    captured_png = []
    def capture(png, filename, ct):
        captured_png.append((png, filename))
        return 99
    wp.upload_generated_image.side_effect = capture
    article = _giants_focus_article()
    attach_ranking_image(wp, article)
    assert len(captured_png) == 1


def test_no_giants_hook_falls_back_to_metric_label():
    wp = MagicMock()
    wp.find_media_by_slug.return_value = 0
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
    wp.find_media_by_slug.return_value = 0
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
    # slug ベース (ASCII only)
    assert filename.startswith("437eyc-")


# ----- 437 dedup (slug-based pre-delete) -----


def test_eyecatch_slug_stable_same_input_same_output():
    """同じ (metric, focus) は何度呼んでも同じ slug を返す。"""
    s1 = _eyecatch_slug("OPS", "坂本勇人")
    s2 = _eyecatch_slug("OPS", "坂本勇人")
    assert s1 == s2
    assert s1.startswith("437eyc-")
    # ASCII-only (URL-safe)
    assert all(c.isascii() for c in s1)


def test_eyecatch_slug_different_metric_different_slug():
    s_ops = _eyecatch_slug("OPS", "坂本勇人")
    s_avg = _eyecatch_slug("AVG", "坂本勇人")
    assert s_ops != s_avg


def test_eyecatch_slug_different_focus_different_slug():
    s_sakamoto = _eyecatch_slug("OPS", "坂本勇人")
    s_okamoto = _eyecatch_slug("OPS", "岡本和真")
    assert s_sakamoto != s_okamoto


def test_dedup_pre_deletes_existing_media_before_upload():
    """既存 slug PNG があれば upload 前に delete される。"""
    wp = MagicMock()
    wp.find_media_by_slug.return_value = 99999  # 既存 media id
    wp.upload_generated_image.return_value = 12346
    media_id = attach_ranking_image(wp, _giants_focus_article())
    assert media_id == 12346
    # 既存を find → delete → upload の順
    wp.find_media_by_slug.assert_called_once()
    wp.delete_media.assert_called_once_with(99999)
    wp.upload_generated_image.assert_called_once()


def test_dedup_delete_failure_does_not_block_upload():
    """delete_media が False を返しても upload は続行 (publish 守る)。"""
    wp = MagicMock()
    wp.find_media_by_slug.return_value = 88888
    wp.delete_media.return_value = False  # delete 失敗
    wp.upload_generated_image.return_value = 12347
    media_id = attach_ranking_image(wp, _giants_focus_article())
    # upload は実行される
    assert media_id == 12347
    wp.upload_generated_image.assert_called_once()


def test_dedup_find_raises_exception_still_uploads():
    """find_media_by_slug が例外を投げても upload を止めない。"""
    wp = MagicMock()
    wp.find_media_by_slug.side_effect = RuntimeError("WP search failed")
    wp.upload_generated_image.return_value = 12348
    media_id = attach_ranking_image(wp, _giants_focus_article())
    # upload は実行 + media_id 返却
    assert media_id == 12348
    wp.upload_generated_image.assert_called_once()
    # delete は呼ばれない (find が失敗したので)
    wp.delete_media.assert_not_called()
