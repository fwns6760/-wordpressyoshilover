"""tests for src/publish_notice_body_excerpt.py (377-OPS Phase 1C / GH #51)."""

from __future__ import annotations

import pytest

from publish_notice_body_excerpt import build_admin_edit_url, build_body_excerpt


# --- build_admin_edit_url ---------------------------------------------------


class TestBuildAdminEditUrl:
    def test_returns_url_for_int_post_id(self):
        assert (
            build_admin_edit_url(123, "https://yoshilover.com")
            == "https://yoshilover.com/wp-admin/post.php?post=123&action=edit"
        )

    def test_returns_url_for_str_post_id(self):
        assert (
            build_admin_edit_url("456", "https://yoshilover.com")
            == "https://yoshilover.com/wp-admin/post.php?post=456&action=edit"
        )

    def test_strips_trailing_slash_from_base_url(self):
        assert (
            build_admin_edit_url(789, "https://yoshilover.com/")
            == "https://yoshilover.com/wp-admin/post.php?post=789&action=edit"
        )

    def test_strips_multiple_trailing_slashes(self):
        assert (
            build_admin_edit_url(1, "https://yoshilover.com///")
            == "https://yoshilover.com/wp-admin/post.php?post=1&action=edit"
        )

    def test_returns_none_for_none_post_id(self):
        assert build_admin_edit_url(None, "https://yoshilover.com") is None

    def test_returns_none_for_none_wp_base_url(self):
        assert build_admin_edit_url(123, None) is None

    def test_returns_none_for_empty_wp_base_url(self):
        assert build_admin_edit_url(123, "") is None

    def test_returns_none_for_whitespace_wp_base_url(self):
        assert build_admin_edit_url(123, "   ") is None

    def test_returns_none_for_zero_post_id(self):
        assert build_admin_edit_url(0, "https://yoshilover.com") is None

    def test_returns_none_for_negative_post_id(self):
        assert build_admin_edit_url(-1, "https://yoshilover.com") is None

    def test_returns_none_for_non_numeric_str_post_id(self):
        assert build_admin_edit_url("abc", "https://yoshilover.com") is None

    def test_returns_none_for_empty_str_post_id(self):
        assert build_admin_edit_url("", "https://yoshilover.com") is None

    def test_accepts_post_id_with_whitespace_padding(self):
        assert (
            build_admin_edit_url("  42  ", "https://yoshilover.com")
            == "https://yoshilover.com/wp-admin/post.php?post=42&action=edit"
        )

    def test_accepts_wp_base_url_with_whitespace_padding(self):
        assert (
            build_admin_edit_url(42, "  https://yoshilover.com  ")
            == "https://yoshilover.com/wp-admin/post.php?post=42&action=edit"
        )

    def test_accepts_http_scheme(self):
        assert (
            build_admin_edit_url(42, "http://localhost:8080")
            == "http://localhost:8080/wp-admin/post.php?post=42&action=edit"
        )


# --- build_body_excerpt -----------------------------------------------------


class TestBuildBodyExcerpt:
    def test_returns_none_for_none(self):
        assert build_body_excerpt(None) is None

    def test_returns_none_for_empty_string(self):
        assert build_body_excerpt("") is None

    def test_returns_none_for_whitespace_only(self):
        assert build_body_excerpt("   \n\t  ") is None

    def test_returns_plain_text_unchanged(self):
        text = "巨人は3-1で勝利した。岡本和真が2試合連続HRを記録した。"
        assert build_body_excerpt(text) == text

    def test_strips_simple_html_tags(self):
        html_text = "<p>巨人は3-1で勝利した。</p><p>岡本がHR。</p>"
        result = build_body_excerpt(html_text)
        assert result == "巨人は3-1で勝利した。 岡本がHR。"

    def test_decodes_html_entities(self):
        html_text = "<p>巨人&nbsp;3 &amp; 阪神 1</p>"
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "&" in result
        assert "&amp;" not in result

    def test_collapses_whitespace(self):
        html_text = "<p>巨人は\n\n  勝利した。</p>"
        result = build_body_excerpt(html_text)
        assert result == "巨人は 勝利した。"

    def test_removes_related_posts_div(self):
        html_text = (
            "<p>本文だよ。</p>"
            '<div class="yoshilover-related-posts">'
            "<h3>関連記事</h3><ul><li>記事1</li><li>記事2</li></ul>"
            "</div>"
            "<p>続きの本文。</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "関連記事" not in result
        assert "記事1" not in result
        assert "本文だよ。" in result
        assert "続きの本文。" in result

    def test_removes_fan_voice_section_until_next_heading(self):
        html_text = (
            "<h2>試合経過</h2><p>巨人は3-1で勝利。</p>"
            "<h2>💬 ファンの声</h2>"
            '<blockquote class="twitter-tweet">X embed content</blockquote>'
            '<blockquote class="twitter-tweet">More X content</blockquote>'
            "<h2>次の試合</h2><p>明日は阪神戦。</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "ファンの声" not in result
        assert "X embed content" not in result
        assert "More X content" not in result
        assert "試合経過" in result
        assert "巨人は3-1で勝利。" in result
        assert "次の試合" in result
        assert "明日は阪神戦。" in result

    def test_removes_fan_voice_section_until_end_of_doc(self):
        html_text = (
            "<h2>試合経過</h2><p>巨人は3-1で勝利。</p>"
            "<h2>💬 ファンの声</h2>"
            "<p>fan voice 1</p>"
            "<p>fan voice 2</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "ファンの声" not in result
        assert "fan voice" not in result
        assert "試合経過" in result
        assert "巨人は3-1で勝利。" in result

    def test_removes_kanren_kiji_section(self):
        html_text = (
            "<h2>本文</h2><p>本文の中身。</p>"
            "<h2>【関連記事】</h2>"
            "<p>関連記事 1 link</p>"
            "<h2>続き</h2><p>続きの本文。</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "関連記事" not in result
        assert "本文の中身。" in result
        assert "続きの本文。" in result

    def test_removes_script_blocks(self):
        html_text = (
            "<p>本文。</p>"
            "<script>window.foo = 1;</script>"
            "<p>続き。</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "window.foo" not in result
        assert "本文。" in result
        assert "続き。" in result

    def test_removes_style_blocks(self):
        html_text = "<style>.foo { color: red; }</style><p>本文。</p>"
        result = build_body_excerpt(html_text)
        assert result == "本文。"

    def test_removes_twitter_tweet_blockquote(self):
        html_text = (
            "<p>記事本文。</p>"
            '<blockquote class="twitter-tweet" data-lang="ja">'
            "<p>tweet text</p><a href=\"https://twitter.com/x/123\">link</a>"
            "</blockquote>"
            "<p>後続。</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "tweet text" not in result
        assert "twitter.com" not in result
        assert "記事本文。" in result
        assert "後続。" in result

    def test_truncates_long_text_with_ellipsis(self):
        long_text = "あ" * 1500
        result = build_body_excerpt(long_text, max_chars=1000)
        assert result is not None
        assert len(result) == 1000
        assert result.endswith("…")
        assert result[:999] == "あ" * 999

    def test_does_not_truncate_text_at_exact_max_chars(self):
        text = "あ" * 1000
        result = build_body_excerpt(text, max_chars=1000)
        assert result == text

    def test_custom_max_chars(self):
        text = "あ" * 200
        result = build_body_excerpt(text, max_chars=100)
        assert result is not None
        assert len(result) == 100
        assert result.endswith("…")

    def test_leading_fan_voice_label_stripped(self):
        text = "💬 ファンの声 本文ここから始まる。"
        result = build_body_excerpt(text)
        assert result == "本文ここから始まる。"

    def test_leading_kanren_label_stripped(self):
        text = "【関連記事】 本文ここから。"
        result = build_body_excerpt(text)
        assert result == "本文ここから。"

    def test_multiple_fan_voice_sections_all_removed(self):
        html_text = (
            "<h2>1試合目</h2><p>勝利。</p>"
            "<h2>💬 ファンの声</h2><p>v1</p>"
            "<h2>2試合目</h2><p>勝利。</p>"
            "<h2>💬 ファンの声</h2><p>v2</p>"
            "<h2>まとめ</h2><p>連勝。</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "v1" not in result
        assert "v2" not in result
        assert "ファンの声" not in result
        assert "1試合目" in result
        assert "2試合目" in result
        assert "まとめ" in result
        assert "連勝。" in result

    def test_returns_none_when_everything_stripped(self):
        html_text = (
            "<h2>💬 ファンの声</h2><p>only fan voice content</p>"
        )
        result = build_body_excerpt(html_text)
        assert result is None

    def test_default_max_chars_is_1000(self):
        text = "あ" * 1500
        result = build_body_excerpt(text)
        assert result is not None
        assert len(result) == 1000

    def test_max_chars_zero_disables_truncation(self):
        text = "あ" * 5000
        result = build_body_excerpt(text, max_chars=0)
        assert result == text

    def test_real_world_postgame_body(self):
        """Why: 実際の postgame HTML 構造で本文だけ残ることを verify."""
        html_text = """
        <h2>試合結果</h2>
        <p>巨人 3-1 阪神。 岡本和真の2試合連続HRが決勝点となった。</p>
        <h2>勝敗投手</h2>
        <p>勝利投手: 戸郷翔征 / 敗戦投手: 才木浩人</p>
        <h2>💬 ファンの声</h2>
        <blockquote class="twitter-tweet"><p>岡本最高！</p></blockquote>
        <blockquote class="twitter-tweet"><p>戸郷ナイスピッチング</p></blockquote>
        <div class="yoshilover-related-posts">
          <h3>関連記事</h3>
          <ul><li><a href="/foo">巨人の岡本</a></li></ul>
        </div>
        """
        result = build_body_excerpt(html_text)
        assert result is not None
        assert "試合結果" in result
        assert "岡本和真" in result
        assert "勝敗投手" in result
        assert "戸郷翔征" in result
        assert "ファンの声" not in result
        assert "twitter" not in result.lower()
        assert "関連記事" not in result
        assert "岡本最高" not in result
        assert "戸郷ナイスピッチング" not in result
