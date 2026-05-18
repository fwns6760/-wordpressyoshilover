"""tests for 377-OPS Phase 1C-2 scanner wiring (GH #51).

Covers:
- ``_resolve_wp_base_url`` (env priority: explicit → WP_URL → WP_API_BASE strip → None)
- ``_request_from_post`` populates ``body_excerpt`` + ``admin_edit_url``
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src import publish_notice_scanner as scanner


class ResolveWpBaseUrlTests(unittest.TestCase):
    def test_explicit_arg_wins(self):
        with patch.dict(os.environ, {"WP_URL": "https://other.example.com"}, clear=False):
            assert (
                scanner._resolve_wp_base_url("https://explicit.example.com")
                == "https://explicit.example.com"
            )

    def test_explicit_arg_strips_trailing_slash(self):
        assert (
            scanner._resolve_wp_base_url("https://example.com/")
            == "https://example.com"
        )

    def test_falls_back_to_wp_url_env(self):
        env = {"WP_URL": "https://yoshilover.com/"}
        with patch.dict(os.environ, env, clear=True):
            assert scanner._resolve_wp_base_url() == "https://yoshilover.com"

    def test_falls_back_to_wp_api_base_strip(self):
        env = {"WP_API_BASE": "https://yoshilover.com/wp-json/wp/v2"}
        with patch.dict(os.environ, env, clear=True):
            assert scanner._resolve_wp_base_url() == "https://yoshilover.com"

    def test_returns_none_when_nothing_available(self):
        with patch.dict(os.environ, {}, clear=True):
            assert scanner._resolve_wp_base_url() is None

    def test_empty_explicit_arg_falls_through_to_env(self):
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            assert scanner._resolve_wp_base_url("") == "https://yoshilover.com"


class RequestFromPostPopulateTests(unittest.TestCase):
    def _post(self, **overrides):
        payload = {
            "id": 123,
            "title": {"rendered": "巨人 3-1 阪神 岡本2試合連続HR"},
            "excerpt": {"rendered": "<p>巨人が3-1で勝利した。</p>"},
            "content": {
                "rendered": (
                    "<h2>試合結果</h2><p>巨人 3-1 阪神。 岡本和真の2試合連続HR。</p>"
                    "<h2>💬 ファンの声</h2>"
                    "<blockquote class=\"twitter-tweet\"><p>岡本最高</p></blockquote>"
                    "<h2>次の試合</h2><p>明日は阪神戦。</p>"
                )
            },
            "link": "https://yoshilover.com/post-123/",
            "date": "2026-05-18T20:30:00+09:00",
            "status": "publish",
            "meta": {"article_subtype": "postgame"},
        }
        payload.update(overrides)
        return payload

    def test_populates_body_excerpt_from_content(self):
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(self._post())
        assert req.body_excerpt is not None
        assert "巨人 3-1 阪神" in req.body_excerpt
        assert "岡本和真" in req.body_excerpt
        assert "次の試合" in req.body_excerpt
        assert "ファンの声" not in req.body_excerpt
        assert "岡本最高" not in req.body_excerpt

    def test_populates_admin_edit_url(self):
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(self._post())
        assert req.admin_edit_url == (
            "https://yoshilover.com/wp-admin/post.php?post=123&action=edit"
        )

    def test_falls_back_to_excerpt_when_content_missing(self):
        post = self._post(content={"rendered": ""})
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(post)
        assert req.body_excerpt == "巨人が3-1で勝利した。"

    def test_body_excerpt_is_none_when_content_and_excerpt_empty(self):
        post = self._post(content={"rendered": ""}, excerpt={"rendered": ""})
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(post)
        assert req.body_excerpt is None

    def test_admin_edit_url_is_none_when_wp_base_url_unavailable(self):
        post = self._post()
        with patch.dict(os.environ, {}, clear=True):
            req = scanner._request_from_post(post)
        assert req.admin_edit_url is None
        # body_excerpt は env に依存しないので populate されているはず
        assert req.body_excerpt is not None

    def test_admin_edit_url_is_none_when_post_id_missing(self):
        post = self._post(id=0)
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(post)
        assert req.admin_edit_url is None

    def test_explicit_wp_base_url_overrides_env(self):
        post = self._post()
        env = {"WP_URL": "https://wrong.example.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(post, wp_base_url="https://right.example.com")
        assert req.admin_edit_url == (
            "https://right.example.com/wp-admin/post.php?post=123&action=edit"
        )

    def test_notice_origin_param_still_works(self):
        post = self._post()
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(post, notice_origin="direct_publish")
        assert req.notice_origin == "direct_publish"
        assert req.body_excerpt is not None
        assert req.admin_edit_url is not None

    def test_existing_fields_unchanged(self):
        """Why: Phase 1C-2 改修で他 field の populate が壊れていないことを verify."""
        post = self._post()
        env = {"WP_URL": "https://yoshilover.com"}
        with patch.dict(os.environ, env, clear=True):
            req = scanner._request_from_post(post)
        assert req.post_id == 123
        assert req.title == "巨人 3-1 阪神 岡本2試合連続HR"
        assert req.canonical_url == "https://yoshilover.com/post-123/"
        assert req.subtype == "postgame"
        assert req.publish_time_iso is not None
        assert req.summary is not None


if __name__ == "__main__":
    unittest.main()
