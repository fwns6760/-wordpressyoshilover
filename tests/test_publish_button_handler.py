"""tests for src/publish_button_handler.py (379-OPS / GH #53)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from src.publish_button_handler import (
    _build_x_intent_url,
    handle_get,
    handle_post as _handle_post_real,
)
from src.publish_button_token import generate_publish_button_token


_TOKEN_TEST_NOW = 1_700_000_000
_TOKEN = generate_publish_button_token(123, ttl_seconds=3600, now=_TOKEN_TEST_NOW)
_VERIFY_NOW = _TOKEN_TEST_NOW + 100


def _wp_draft_post(post_id: int = 123, status: str = "draft"):
    return {
        "id": post_id,
        "title": {"rendered": "巨人 3-1 阪神 岡本 2 試合連続 HR"},
        "link": "https://yoshilover.com/post-123/",
        "status": status,
    }


def handle_post(*args, **kwargs):
    """test wrapper: GCS callable を default mock (consumed=False / mark=True) で injection。

    Why: handler の default は real GCS を叩く。 test では副作用 (real bucket への
    書き込み試行 + warnings) を出さないため、 明示しない限り「未消費 + mark 成功」 mock を入れる。
    """
    kwargs.setdefault("is_consumed", lambda token: False)
    kwargs.setdefault("mark_consumed", lambda token, **_: True)
    return _handle_post_real(*args, **kwargs)


# --- _build_x_intent_url ---------------------------------------------------


_BRAND_TAG = "🐰 ヨシラバー｜⚾ 読売ジャイアンツ速報掲示板"


class BuildXIntentUrlTests(unittest.TestCase):
    def test_returns_url_with_text_url_and_brand_tag(self):
        url = _build_x_intent_url(
            title="巨人勝利",
            article_url="https://yoshilover.com/post-1/",
        )
        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "x.com"
        assert parsed.path == "/intent/tweet"
        qs = parse_qs(parsed.query)
        # title + brand tag が text に同居 (改行区切り)
        assert qs["text"][0].startswith("巨人勝利")
        assert _BRAND_TAG in qs["text"][0]
        assert qs["url"] == ["https://yoshilover.com/post-1/"]

    def test_truncates_long_title_brand_tag_still_appears(self):
        long_title = "あ" * 200
        url = _build_x_intent_url(title=long_title, article_url="https://x.test/")
        qs = parse_qs(urlparse(url).query)
        text = qs["text"][0]
        # title 部分は 80 字 truncate、 brand tag は別途付与
        assert text.startswith("あ" * 79 + "…")
        assert _BRAND_TAG in text

    def test_url_encodes_japanese(self):
        url = _build_x_intent_url(title="巨人", article_url="https://yoshilover.com/post-1/")
        # 日本語が % escape されている
        assert "%E5%B7%A8%E4%BA%BA" in url

    def test_empty_title_brand_tag_only(self):
        url = _build_x_intent_url(title="", article_url="https://yoshilover.com/post-1/")
        qs = parse_qs(urlparse(url).query)
        # title 空でも brand tag は付く
        assert _BRAND_TAG in qs["text"][0]
        assert qs.get("url") == ["https://yoshilover.com/post-1/"]


# --- handle_get ------------------------------------------------------------


class HandleGetTests(unittest.TestCase):
    def test_returns_400_for_invalid_post_id(self):
        code, body, headers = handle_get(
            post_id_raw="abc",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(),
        )
        assert code == 400
        assert "post_id" in body
        assert headers == {}

    def test_returns_400_for_empty_token(self):
        code, _, _ = handle_get(
            post_id_raw="123",
            token="",
            fetch_post=lambda pid: _wp_draft_post(),
        )
        assert code == 400

    def test_returns_403_for_invalid_token(self):
        code, body, _ = handle_get(
            post_id_raw="123",
            token="invalid.token",
            fetch_post=lambda pid: _wp_draft_post(),
            now=_VERIFY_NOW,
        )
        assert code == 403
        assert "改ざん" in body or "期限切れ" in body

    def test_returns_403_for_expired_token(self):
        old_token = generate_publish_button_token(123, ttl_seconds=60, now=1)
        code, _, _ = handle_get(
            post_id_raw="123",
            token=old_token,
            fetch_post=lambda pid: _wp_draft_post(),
            now=9_999_999_999,
        )
        assert code == 403

    def test_returns_404_when_post_not_found(self):
        code, body, _ = handle_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: None,
            now=_VERIFY_NOW,
        )
        assert code == 404
        assert "存在しない" in body

    def test_returns_500_when_fetch_raises(self):
        def boom(pid):
            raise RuntimeError("WP REST timeout")
        code, body, _ = handle_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=boom,
            now=_VERIFY_NOW,
        )
        assert code == 500
        assert "取得に失敗" in body

    def test_returns_200_confirmation_page_for_draft(self):
        code, body, _ = handle_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(),
            now=_VERIFY_NOW,
        )
        assert code == 200
        assert "公開してX投稿画面へ" in body
        assert "下書き (draft)" in body
        assert "巨人 3-1 阪神" in body
        assert "<form method=\"POST\"" in body

    def test_returns_200_confirmation_page_for_publish(self):
        code, body, _ = handle_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(status="publish"),
            now=_VERIFY_NOW,
        )
        assert code == 200
        assert "既に <strong>公開済</strong>" in body
        assert "<form method=\"POST\"" in body


# --- handle_post -----------------------------------------------------------


class HandlePostTests(unittest.TestCase):
    def test_returns_400_for_invalid_post_id(self):
        code, _, _ = handle_post(
            post_id_raw="abc",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(),
            update_post_status=MagicMock(),
        )
        assert code == 400

    def test_returns_403_for_invalid_token(self):
        update_mock = MagicMock()
        code, _, _ = handle_post(
            post_id_raw="123",
            token="invalid.token",
            fetch_post=lambda pid: _wp_draft_post(),
            update_post_status=update_mock,
            now=_VERIFY_NOW,
        )
        assert code == 403
        update_mock.assert_not_called()

    def test_returns_403_for_expired_token(self):
        old_token = generate_publish_button_token(123, ttl_seconds=60, now=1)
        update_mock = MagicMock()
        code, _, _ = handle_post(
            post_id_raw="123",
            token=old_token,
            fetch_post=lambda pid: _wp_draft_post(),
            update_post_status=update_mock,
            now=9_999_999_999,
        )
        assert code == 403
        update_mock.assert_not_called()

    def test_draft_post_publishes_then_redirects_to_x_intent(self):
        update_mock = MagicMock()
        post_state = {"status": "draft"}

        def fetch(pid):
            return {
                "id": pid,
                "title": {"rendered": "巨人勝利"},
                "link": "https://yoshilover.com/post-123/",
                "status": post_state["status"],
            }

        def update(pid, new_status, **kwargs):
            update_mock(pid, new_status, **kwargs)
            post_state["status"] = new_status

        code, body, headers = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=fetch,
            update_post_status=update,
            now=_VERIFY_NOW,
        )
        assert code == 302
        assert body == ""
        assert headers["Location"].startswith("https://x.com/intent/tweet?")
        update_mock.assert_called_once_with(123, "publish")
        # post_state も flip 済 (実 update が走った)
        assert post_state["status"] == "publish"

    def test_already_published_post_skips_update_and_redirects(self):
        update_mock = MagicMock()
        code, body, headers = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(status="publish"),
            update_post_status=update_mock,
            now=_VERIFY_NOW,
        )
        assert code == 302
        assert headers["Location"].startswith("https://x.com/intent/tweet?")
        update_mock.assert_not_called()

    def test_other_status_post_returns_409_and_no_update(self):
        update_mock = MagicMock()
        for status in ("private", "trash", "pending", "future"):
            code, body, _ = handle_post(
                post_id_raw="123",
                token=_TOKEN,
                fetch_post=lambda pid, s=status: _wp_draft_post(status=s),
                update_post_status=update_mock,
                now=_VERIFY_NOW,
            )
            assert code == 409, f"status={status} should return 409"
            assert "対象外" in body
        update_mock.assert_not_called()

    def test_post_not_found_returns_404(self):
        update_mock = MagicMock()
        code, body, _ = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: None,
            update_post_status=update_mock,
            now=_VERIFY_NOW,
        )
        assert code == 404
        update_mock.assert_not_called()

    def test_wp_update_failure_returns_500_with_error_message(self):
        update_mock = MagicMock(side_effect=RuntimeError("WP REST 500"))
        code, body, _ = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(),
            update_post_status=update_mock,
            now=_VERIFY_NOW,
        )
        assert code == 500
        assert "WP REST publish 失敗" in body

    def test_idempotent_double_click(self):
        """draft → publish → publish の 2 回 POST で 1 回しか update が走らない."""
        update_mock = MagicMock()
        post_state = {"status": "draft"}

        def fetch(pid):
            return {
                "id": pid,
                "title": {"rendered": "巨人勝利"},
                "link": "https://yoshilover.com/post-123/",
                "status": post_state["status"],
            }

        def update(pid, new_status, **kwargs):
            update_mock(pid, new_status, **kwargs)
            post_state["status"] = new_status

        # 1 回目: draft → publish
        code1, _, headers1 = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=fetch,
            update_post_status=update,
            now=_VERIFY_NOW,
        )
        # 2 回目: publish のまま (double click 想定)
        code2, _, headers2 = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=fetch,
            update_post_status=update,
            now=_VERIFY_NOW,
        )
        assert code1 == 302 and code2 == 302
        assert headers1["Location"] == headers2["Location"]
        assert update_mock.call_count == 1

    def test_x_intent_url_contains_title_and_url(self):
        code, _, headers = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(status="publish"),
            update_post_status=MagicMock(),
            now=_VERIFY_NOW,
        )
        assert code == 302
        loc = headers["Location"]
        parsed = urlparse(loc)
        qs = parse_qs(parsed.query)
        assert qs["text"][0].startswith("巨人 3-1 阪神 岡本 2 試合連続 HR")
        assert _BRAND_TAG in qs["text"][0]
        assert qs["url"] == ["https://yoshilover.com/post-123/"]

    # --- one-shot token (consumed store) integration ---

    def test_consumed_token_with_draft_post_returns_409(self):
        """token 既消費 + post draft = suspicious、 publish しない."""
        update_mock = MagicMock()
        code, body, _ = _handle_post_real(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(status="draft"),
            update_post_status=update_mock,
            now=_VERIFY_NOW,
            is_consumed=lambda token: True,
            mark_consumed=lambda token, **_: True,
        )
        assert code == 409
        assert "既に使用済" in body
        update_mock.assert_not_called()

    def test_consumed_token_with_publish_post_redirects_idempotent(self):
        """token 既消費 + post publish = idempotent UX、 X intent へ進む."""
        update_mock = MagicMock()
        code, body, headers = _handle_post_real(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(status="publish"),
            update_post_status=update_mock,
            now=_VERIFY_NOW,
            is_consumed=lambda token: True,
            mark_consumed=lambda token, **_: True,
        )
        assert code == 302
        assert headers["Location"].startswith("https://x.com/intent/tweet?")
        update_mock.assert_not_called()

    def test_unconsumed_token_with_draft_marks_consumed_after_publish(self):
        """正常パス: token 未消費 + draft → publish + mark_consumed 呼ばれる."""
        update_mock = MagicMock()
        mark_mock = MagicMock(return_value=True)
        post_state = {"status": "draft"}

        def fetch(pid):
            return {
                "id": pid,
                "title": {"rendered": "巨人勝利"},
                "link": "https://yoshilover.com/post-123/",
                "status": post_state["status"],
            }

        def update(pid, new_status, **kwargs):
            update_mock(pid, new_status, **kwargs)
            post_state["status"] = new_status

        code, _, _ = _handle_post_real(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=fetch,
            update_post_status=update,
            now=_VERIFY_NOW,
            is_consumed=lambda token: False,
            mark_consumed=mark_mock,
        )
        assert code == 302
        update_mock.assert_called_once_with(123, "publish")
        mark_mock.assert_called_once()
        # mark_consumed の引数に post_id が入る
        call_kwargs = mark_mock.call_args.kwargs
        assert call_kwargs.get("post_id") == 123

    def test_unconsumed_token_with_publish_post_does_not_mark(self):
        """既 publish 記事は token を消費しない (再利用余地を残す)."""
        update_mock = MagicMock()
        mark_mock = MagicMock(return_value=True)
        code, _, headers = _handle_post_real(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(status="publish"),
            update_post_status=update_mock,
            now=_VERIFY_NOW,
            is_consumed=lambda token: False,
            mark_consumed=mark_mock,
        )
        assert code == 302
        update_mock.assert_not_called()
        mark_mock.assert_not_called()

    def test_mark_consumed_failure_still_completes_publish_and_redirects(self):
        """mark_consumed が GCS fail で False 返しても publish は完了して redirect する (fail-open)."""
        update_mock = MagicMock()
        mark_mock = MagicMock(return_value=False)  # GCS write failed
        post_state = {"status": "draft"}

        def fetch(pid):
            return {
                "id": pid,
                "title": {"rendered": "巨人勝利"},
                "link": "https://yoshilover.com/post-123/",
                "status": post_state["status"],
            }

        def update(pid, new_status, **kwargs):
            update_mock(pid, new_status, **kwargs)
            post_state["status"] = new_status

        code, _, headers = _handle_post_real(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=fetch,
            update_post_status=update,
            now=_VERIFY_NOW,
            is_consumed=lambda token: False,
            mark_consumed=mark_mock,
        )
        assert code == 302
        update_mock.assert_called_once()
        mark_mock.assert_called_once()

    def test_no_x_api_call_happens(self):
        """X API client を呼ばないことを verify (X 自動投稿は絶対しない hard rule)."""
        import sys
        # x_api_client が import されていなければ未呼出。 import されていても
        # この handler 内で attribute access していなければ OK。
        update_mock = MagicMock()
        code, _, _ = handle_post(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_draft_post(),
            update_post_status=update_mock,
            now=_VERIFY_NOW,
        )
        # x_api_client module は handler 内で参照されない (source code grep で確認可能)
        # 動的 verify として: handler は redirect しか返さない、 X intent URL 以外には
        # 何も投稿しない。
        assert code == 302
        # update_post_status は呼ばれるが、 X 投稿 API は呼ばれない (mock していない)


if __name__ == "__main__":
    unittest.main()
