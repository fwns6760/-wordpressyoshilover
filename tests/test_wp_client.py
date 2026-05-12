import os
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, call, patch

import requests

from src.nomotoke_card_renderer import render_postgame_card
from src.wp_client import WPClient, WP_PUBLISH_STATUS_GUARD_ENV
from src.wp_revert_audit_ledger import AUDIT_LEDGER_ENV, BLOCK_ENV, LEDGER_PATH_ENV


def _mock_response(
    status_code: int,
    *,
    json_data=None,
    text: str = "",
    headers: dict | None = None,
):
    resp = Mock(status_code=status_code, text=text, headers=headers or {})
    resp.json = Mock(return_value=json_data)
    resp.raise_for_status = Mock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    return resp


class TestWPClientDedup(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_reused_draft_backfills_featured_media(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 456,
                    "title": {"raw": "田中将大「打線を線にしない」 関連発言"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )

        post_id = self.wp.create_draft(
            "田中将大「打線を線にしない」 関連発言",
            "<p>body</p>",
            categories=[663],
            featured_media=62100,
        )

        self.assertEqual(post_id, 456)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(456, featured_media=62100)

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_draft_request_does_not_reuse_published_post(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 321,
                    "categories": [673],
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 789})

        post_id = self.wp.create_draft(
            "巨人戦 試合の流れを分けたポイント",
            "<p>body</p>",
            categories=[673],
            featured_media=654,
        )

        self.assertEqual(post_id, 789)
        mock_update.assert_not_called()
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["featured_media"], 654)

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_publish_request_promotes_reused_draft(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 654,
                    "title": {"raw": "阿部監督「粘り勝った」 ベンチ関連発言"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )

        post_id = self.wp.create_post(
            "阿部監督「粘り勝った」 ベンチ関連発言",
            "<p>body</p>",
            categories=[673, 663],
            status="publish",
            featured_media=777,
        )

        self.assertEqual(post_id, 654)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(
            654,
            featured_media=777,
            categories=[673, 663],
            status="publish",
        )

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_wp_api_403_search_falls_back_to_relaxed_query(self, mock_get, mock_post):
        forbidden = Mock(status_code=403, text='{"code":"rest_forbidden_context"}')
        ok = Mock(status_code=200, json=lambda: [])
        mock_get.side_effect = [forbidden, ok]
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 987})

        post_id = self.wp.create_post(
            "松本剛「甘いところを絞って打ちに行こう」 関連発言",
            "<p>body</p>",
            status="draft",
        )

        self.assertEqual(post_id, 987)
        self.assertEqual(mock_get.call_count, 2)
        first_params = mock_get.call_args_list[0].kwargs["params"]
        second_params = mock_get.call_args_list[1].kwargs["params"]
        self.assertEqual(first_params["context"], "edit")
        self.assertNotIn("context", second_params)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_reuses_recent_same_title(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか",
            "<p>body</p>",
            status="publish",
        )

        self.assertEqual(post_id, 123)
        mock_post.assert_not_called()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_reuses_existing_draft_when_source_url_matches(self, mock_get, mock_post, mock_update):
        source_url = "https://example.com/source/a"
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 333,
                    "title": {"raw": "巨人戦 試合前にどこを見たいか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [673],
                    "meta": {WPClient.SOURCE_URL_META_KEY: source_url},
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人戦 試合前にどこを見たいか",
            "<p>body</p>",
            status="draft",
            source_url=source_url,
        )

        self.assertEqual(post_id, 333)
        mock_post.assert_not_called()
        mock_update.assert_not_called()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_creates_new_when_source_url_differs(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 334,
                    "title": {"raw": "巨人戦 試合前にどこを見たいか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "meta": {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/a"},
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 335})

        post_id = self.wp.create_post(
            "巨人戦 試合前にどこを見たいか",
            "<p>body</p>",
            status="draft",
            source_url="https://example.com/source/b",
        )

        self.assertEqual(post_id, 335)
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["meta"],
            {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/b"},
        )

    @patch("src.wp_client.requests.get")
    def test_find_recent_post_by_title_allows_title_only_reuse_when_enabled(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 336,
                    "title": {"raw": "巨人戦 試合前にどこを見たいか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "meta": {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/a"},
                }
            ],
        )

        post = self.wp.find_recent_post_by_title(
            "巨人戦 試合前にどこを見たいか",
            reusable_statuses={"draft"},
            source_url="https://example.com/source/b",
            allow_title_only_reuse=True,
        )

        self.assertIsNotNone(post)
        self.assertEqual(post["id"], 336)
        self.assertEqual(post["_yoshilover_reuse_reason"], "title_fallback")

    @patch("src.wp_client.requests.get")
    def test_find_recent_post_by_title_uses_24_hour_window_by_default(self, mock_get):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                base = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
                if tz:
                    return base.astimezone(tz)
                return base.replace(tzinfo=None)

        mock_get.return_value = Mock(status_code=200, json=lambda: [])

        with patch("src.wp_client.datetime", FixedDateTime):
            self.wp.find_recent_post_by_title("巨人戦 試合の流れを分けたポイント")

        first_params = mock_get.call_args_list[0].kwargs["params"]
        self.assertEqual(first_params["after"], "2026-04-15T12:00:00+00:00")

    @patch("src.wp_client.requests.get")
    def test_find_recent_post_by_title_matches_polished_stored_against_unpolished_input(self, mock_get):
        """DUP-FIX-2026-05-08-FIND-RECENT-POLISH-AWARE regression.

        Real production scenario (2026-05-08 yoshilover-fetcher / WP post 65339
        など C01 cluster): rss_fetcher generates a long un-polished title each
        fire (>50 chars). create_post applies title_seo_polisher.polish_title
        which truncates to 50 chars + ``…`` before persisting. The next fire
        passes the same long un-polished title to find_recent_post_by_title.
        Without polish-aware compare, _normalize_title(input_full) !=
        _normalize_title(stored_truncated) → no match → new draft created
        every fire (same source URL, identical body marker, ignored).
        """
        long_input_title = (
            "【要review｜post_gen_validate】村田善則バッテリーチーフコーチ"
            "「ものすごく大きなことが起こっているわけではない」"
        )
        polished_stored_title = (
            "【要review｜post_gen_validate】村田善則バッテリーチーフコーチ「ものすごく大…"
        )
        # Sanity: polish_title actually truncates this long input to the
        # exact stored form. Guards against a future polish_title change
        # silently invalidating this regression.
        from src.title_seo_polisher import polish_title

        self.assertEqual(polish_title(long_input_title), polished_stored_title)

        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 65339,
                    "title": {"raw": polished_stored_title},
                    "status": "draft",
                    "date": "2099-05-08T10:32:15",
                    "meta": {},
                }
            ],
        )

        post = self.wp.find_recent_post_by_title(
            long_input_title,
            reusable_statuses={"draft"},
            source_url=None,
            allow_title_only_reuse=True,
        )

        self.assertIsNotNone(post)
        self.assertEqual(post["id"], 65339)
        self.assertEqual(post["_yoshilover_reuse_reason"], "title_fallback")

    @patch("src.wp_client.requests.get")
    def test_find_recent_post_by_title_still_matches_unpolished_stored_against_unpolished_input(self, mock_get):
        """84e48cd intent preservation.

        The polish-aware compare is additive: the original raw normalize
        variant must remain in the candidate set so historical posts
        created BEFORE the polish hook (= un-polished, possibly long)
        still match when the same un-polished input is replayed.
        """
        long_unpolished_title = (
            "巨人戦 試合の流れを分けたポイント 阿部監督が語る今日の中盤での采配と"
            "次戦の見どころとして大事なところを整理"
        )
        # Sanity: confirm this title would be truncated by polish — that's
        # the only way we know the raw-variant path is exercised separately.
        from src.title_seo_polisher import polish_title

        self.assertNotEqual(polish_title(long_unpolished_title), long_unpolished_title)

        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 222,
                    "title": {"raw": long_unpolished_title},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "meta": {},
                }
            ],
        )

        post = self.wp.find_recent_post_by_title(
            long_unpolished_title,
            reusable_statuses={"draft"},
            source_url=None,
            allow_title_only_reuse=True,
        )

        self.assertIsNotNone(post)
        self.assertEqual(post["id"], 222)
        self.assertEqual(post["_yoshilover_reuse_reason"], "title_fallback")

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_reuse_skips_meta_update_when_body_marker_certifies_source_url(self, mock_get, mock_post, mock_update):
        """DUP-FIX-2026-05-08-REUSE-DATE-STABLE regression.

        production C01 (post 65365 など) で起きていた事象: WP REST が
        ``_yoshilover_source_url`` post-meta を露出しないため
        ``existing_source_url`` が空に見え、毎 fire ``meta`` PUT が走り、
        WP の date / modified が動いて user 視点で「同じ draft が毎回
        更新されたように見える」事象を起こしていた。body marker が
        既に source_url を埋めている時は meta の冗長 PUT を skip し、
        update_post_fields が呼ばれないこと (= WP 側で date/modified が
        動かないこと) を verify する。
        """
        source_url = "https://www.nikkansports.com/baseball/news/202605070000508.html"
        marker = WPClient._build_source_url_body_marker(source_url)

        # 第一段階の search では meta を見せない (REST が露出しない、
        # 本番と同条件)。body は marker 入り、reuse は body_marker_match
        # 経路に乗る。
        search_response = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 65365,
                    "title": {"raw": "【要review｜post_gen_validate】村田善則バッテリーチーフコーチ「ものすごく大…"},
                    "status": "draft",
                    "date": "2099-05-08T20:01:00",
                    "featured_media": 0,
                    "categories": [663],
                    "meta": {},
                }
            ],
        )
        # detail fetch (meta probe fallback) は body+marker を返す
        detail_response = Mock(
            status_code=200,
            json=lambda: {
                "id": 65365,
                "title": {"raw": "【要review｜post_gen_validate】村田善則バッテリーチーフコーチ「ものすごく大…"},
                "status": "draft",
                "date": "2099-05-08T20:01:00",
                "featured_media": 0,
                "categories": [663],
                "meta": {},
                "content": {"raw": f"<p>本文</p>{marker}"},
            },
        )
        mock_get.side_effect = [search_response, detail_response]

        post_id = self.wp.create_post(
            "【要review｜post_gen_validate】村田善則バッテリーチーフコーチ「ものすごく大きなことが起こっているわけではない」",
            f"<p>新 fire body</p>{marker}",
            status="draft",
            source_url=source_url,
        )

        self.assertEqual(post_id, 65365)
        mock_post.assert_not_called()
        # 重要: body marker が既に source_url を certify しているため
        # meta 再書込は不要 → update_post_fields が呼ばれない。
        mock_update.assert_not_called()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_reuse_still_writes_meta_when_no_body_marker(self, mock_get, mock_post, mock_update):
        """DUP-FIX-2026-05-08-REUSE-DATE-STABLE backward-compat verify.

        body marker が body 内に存在しない (旧 post / 別経路で作られた
        draft) 場合、WP REST 上 meta が見えなければ従来通り meta PUT を
        走らせ、source_url を post-meta に紐づける挙動を維持する。
        """
        source_url = "https://example.com/source/legacy"

        search_response = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 999,
                    "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                    "status": "draft",
                    "date": "2099-05-08T19:00:00",
                    "featured_media": 0,
                    "categories": [673],
                    "meta": {},
                }
            ],
        )
        detail_response = Mock(
            status_code=200,
            json=lambda: {
                "id": 999,
                "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                "status": "draft",
                "date": "2099-05-08T19:00:00",
                "featured_media": 0,
                "categories": [673],
                "meta": {},
                "content": {"raw": "<p>marker なしの古い body</p>"},
            },
        )
        mock_get.side_effect = [search_response, detail_response]

        post_id = self.wp.create_post(
            "巨人戦 試合の流れを分けたポイント",
            "<p>新 body</p>",
            status="draft",
            source_url=source_url,
            allow_title_only_reuse=True,
        )

        self.assertEqual(post_id, 999)
        mock_post.assert_not_called()
        # 旧 post に marker なし → 従来通り meta を埋め直す
        mock_update.assert_called_once()
        kwargs = mock_update.call_args.kwargs
        self.assertIn("meta", kwargs)
        self.assertEqual(
            kwargs["meta"].get(WPClient.SOURCE_URL_META_KEY), source_url
        )

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_does_not_reuse_old_same_title(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか"},
                    "status": "publish",
                    "date": "2026-04-14T10:00:00",
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 999})

        post_id = self.wp.create_post(
            "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか",
            "<p>body</p>",
            status="publish",
        )

        self.assertEqual(post_id, 999)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_draft_creates_when_no_recent_same_title(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 456})

        post_id = self.wp.create_draft("新しい記事", "<p>body</p>")

        self.assertEqual(post_id, 456)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_draft_saves_source_url_meta_on_new_post(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 457})

        post_id = self.wp.create_draft(
            "新しい記事",
            "<p>body</p>",
            source_url="https://example.com/source/new",
        )

        self.assertEqual(post_id, 457)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["meta"],
            {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/new"},
        )

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_draft_does_not_reuse_published_post(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 789})

        post_id = self.wp.create_draft("巨人戦 試合の流れを分けたポイント", "<p>body</p>")

        self.assertEqual(post_id, 789)
        mock_post.assert_called_once()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_in_draft_mode_does_not_reuse_published_post(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 790})

        post_id = self.wp.create_post(
            "巨人戦 試合の流れを分けたポイント",
            "<p>body</p>",
            status="draft",
            featured_media=88,
        )

        self.assertEqual(post_id, 790)
        mock_update.assert_not_called()
        mock_post.assert_called_once()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_backfills_featured_media_on_reused_draft(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 456,
                    "title": {"raw": "巨人が阪神に3-2で勝利　岡田が決勝打"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [673, 663],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人が阪神に3-2で勝利　岡田が決勝打",
            "<p>body</p>",
            categories=[673, 663],
            status="draft",
            featured_media=321,
        )

        self.assertEqual(post_id, 456)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(456, featured_media=321)

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_promotes_reused_draft_when_publish_requested(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 654,
                    "title": {"raw": "巨人の新外国人右腕をどう見るか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [676],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の新外国人右腕をどう見るか",
            "<p>body</p>",
            categories=[676],
            status="publish",
            featured_media=99,
        )

        self.assertEqual(post_id, 654)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(654, featured_media=99, status="publish")

    @patch.dict(os.environ, {WP_PUBLISH_STATUS_GUARD_ENV: "1"}, clear=False)
    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_blocks_reused_draft_promotion_without_explicit_opt_in(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 655,
                    "title": {"raw": "巨人の新外国人右腕をどう見るか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [676],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の新外国人右腕をどう見るか",
            "<p>body</p>",
            categories=[676],
            status="publish",
            featured_media=99,
        )

        self.assertEqual(post_id, 655)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(655, featured_media=99)

    @patch.dict(os.environ, {WP_PUBLISH_STATUS_GUARD_ENV: "1"}, clear=False)
    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_allows_reused_draft_promotion_with_explicit_opt_in_when_guard_enabled(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 656,
                    "title": {"raw": "巨人の新外国人右腕をどう見るか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [676],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の新外国人右腕をどう見るか",
            "<p>body</p>",
            categories=[676],
            status="publish",
            featured_media=99,
            allow_status_upgrade=True,
            caller="test.explicit_opt_in",
            source_lane="tests",
        )

        self.assertEqual(post_id, 656)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(656, featured_media=99, status="publish")

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_falls_back_when_privileged_search_is_forbidden(self, mock_get, mock_post):
        forbidden = Mock(status_code=400, text='{"code":"rest_forbidden_status"}')
        ok = Mock(
            status_code=200,
            json=lambda: [],
        )
        mock_get.side_effect = [forbidden, ok]
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 789})

        post_id = self.wp.create_post("巨人戦 試合前にどこを見たいか", "<p>body</p>")

        self.assertEqual(post_id, 789)
        self.assertEqual(mock_get.call_count, 2)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_upload_image_from_url_falls_back_to_curl_when_requests_get_fails(self, mock_get, mock_post):
        mock_get.side_effect = OSError("dns failure")
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 321})
        header_result = Mock(stdout=b"HTTP/2 200\r\ncontent-type: image/webp\r\n\r\n")
        body_result = Mock(stdout=b"fake-image-bytes")

        with patch("src.wp_client.subprocess.run", side_effect=[header_result, body_result]) as mock_run:
            media_id = self.wp.upload_image_from_url("https://example.com/image.webp")

        self.assertEqual(media_id, 321)
        self.assertEqual(mock_run.call_count, 2)
        post_headers = mock_post.call_args.kwargs["headers"]
        self.assertEqual(post_headers["Content-Type"], "image/webp")

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_upload_image_from_url_skips_unsupported_content_types(self, mock_get, mock_post):
        for content_type in ("text/html; charset=utf-8", "application/octet-stream"):
            with self.subTest(content_type=content_type):
                mock_get.return_value = Mock(
                    status_code=200,
                    headers={"Content-Type": content_type},
                    content=b"not-an-allowed-image",
                )
                mock_get.return_value.raise_for_status = Mock()

                media_id = self.wp.upload_image_from_url("https://example.com/not-image")

                self.assertEqual(media_id, 0)
                mock_post.assert_not_called()
                mock_get.reset_mock()

    @patch("src.wp_client.requests.get")
    def test_list_posts_uses_edit_context_when_available(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: [{"id": 1}])

        rows = self.wp.list_posts(status="draft", per_page=5, fields=["id", "title"])

        self.assertEqual(rows, [{"id": 1}])
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["status"], "draft")
        self.assertEqual(params["per_page"], 5)
        self.assertEqual(params["context"], "edit")
        self.assertEqual(params["_fields"], "id,title")

    @patch("src.wp_client.requests.get")
    def test_list_posts_retries_without_context(self, mock_get):
        forbidden = Mock(status_code=400, text='{"code":"rest_forbidden_context"}')
        forbidden.raise_for_status.side_effect = requests.HTTPError("bad request")
        ok = Mock(status_code=200, json=lambda: [{"id": 2}])
        mock_get.side_effect = [forbidden, ok]

        rows = self.wp.list_posts(status="draft")

        self.assertEqual(rows, [{"id": 2}])
        self.assertEqual(mock_get.call_count, 2)
        first_params = mock_get.call_args_list[0].kwargs["params"]
        second_params = mock_get.call_args_list[1].kwargs["params"]
        self.assertIn("context", first_params)
        self.assertNotIn("context", second_params)

    def test_get_image_candidate_exclusion_reason_rejects_twimg_emoji_hosts(self):
        for image_url in (
            "https://abs-0.twimg.com/emoji/v2/svg/26a0.svg",
            "https://abs.twimg.com/emoji/v2/svg/26a0.svg",
        ):
            with self.subTest(image_url=image_url):
                self.assertEqual(
                    self.wp._get_image_candidate_exclusion_reason(image_url),
                    "emoji_svg_url",
                )

    def test_get_image_candidate_exclusion_reason_allows_regular_images(self):
        self.assertEqual(
            self.wp._get_image_candidate_exclusion_reason("https://example.com/foo.jpg"),
            "",
        )


class TestWPClientRetryHandling(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch("src.wp_client.requests.get")
    def test_get_post_retries_429_retry_after_then_succeeds(self, mock_get):
        mock_get.side_effect = [
            _mock_response(
                429,
                headers={"Retry-After": "Fri, 01 Jan 2021 00:00:07 GMT"},
                text="too many requests",
            ),
            _mock_response(200, json_data={"id": 42}),
        ]

        with patch("src.wp_client.time.time", return_value=1609459200.0), \
             patch("src.wp_client.time.sleep") as mock_sleep:
            post = self.wp.get_post(42)

        self.assertEqual(post, {"id": 42})
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(7.0)

    @patch("src.wp_client.requests.get")
    def test_get_post_retries_5xx_with_backoff_then_fails(self, mock_get):
        mock_get.return_value = _mock_response(503, text="service unavailable")

        with patch("src.wp_client.random.uniform", return_value=0.25), \
             patch("src.wp_client.time.sleep") as mock_sleep:
            with self.assertRaises(RuntimeError) as ctx:
                self.wp.get_post(99)

        self.assertIn("HTTPエラー", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 4)
        self.assertEqual(mock_sleep.call_args_list, [call(1.25), call(2.25), call(4.25)])

    @patch("src.wp_client.requests.get")
    def test_get_post_4xx_non_429_fails_without_retry(self, mock_get):
        mock_get.return_value = _mock_response(404, text="missing")

        with patch("src.wp_client.time.sleep") as mock_sleep:
            with self.assertRaises(RuntimeError) as ctx:
                self.wp.get_post(100)

        self.assertIn("HTTPエラー", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("src.wp_client.requests.get")
    def test_get_post_retries_urlerror_then_succeeds(self, mock_get):
        mock_get.side_effect = [
            urllib.error.URLError("temporary outage"),
            _mock_response(200, json_data={"id": 55}),
        ]

        with patch("src.wp_client.random.uniform", return_value=0.5), \
             patch("src.wp_client.time.sleep") as mock_sleep:
            post = self.wp.get_post(55)

        self.assertEqual(post, {"id": 55})
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(1.5)


class TestWPPublishedRevertGuard(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch("src.wp_client.requests.post")
    @patch.object(WPClient, "get_post")
    def test_update_post_status_audits_publish_to_draft_attempt(self, mock_get_post, mock_post):
        mock_get_post.return_value = {"id": 900, "status": "publish"}
        mock_post.return_value = _mock_response(200, json_data={"id": 900})

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                AUDIT_LEDGER_ENV: "1",
                LEDGER_PATH_ENV: os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl"),
            },
            clear=False,
        ):
            self.wp.update_post_status(900, "draft", caller="tests.audit", source_lane="tests")
            ledger_rows = [
                json.loads(line)
                for line in Path(os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl")).read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

        self.assertEqual(mock_post.call_args.kwargs["json"], {"status": "draft"})
        self.assertEqual(len(ledger_rows), 1)
        self.assertEqual(ledger_rows[0]["post_id"], 900)
        self.assertEqual(ledger_rows[0]["status_before"], "publish")
        self.assertEqual(ledger_rows[0]["status_after"], "draft")
        self.assertFalse(ledger_rows[0]["blocked"])
        self.assertEqual(ledger_rows[0]["channel"], "update_post_status")

    @patch("src.wp_client.requests.post")
    @patch.object(WPClient, "get_post")
    def test_update_post_status_blocks_publish_to_draft_when_guard_enabled(self, mock_get_post, mock_post):
        mock_get_post.return_value = {"id": 901, "status": "publish"}
        mock_post.return_value = _mock_response(200, json_data={"id": 901})

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                AUDIT_LEDGER_ENV: "1",
                BLOCK_ENV: "1",
                LEDGER_PATH_ENV: os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl"),
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.wp.update_post_status(901, "draft", caller="tests.block", source_lane="tests")
            ledger_rows = [
                json.loads(line)
                for line in Path(os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl")).read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

        self.assertIn("published post status revert blocked", str(ctx.exception))
        mock_post.assert_not_called()
        self.assertEqual(len(ledger_rows), 1)
        self.assertTrue(ledger_rows[0]["blocked"])
        self.assertEqual(ledger_rows[0]["status_after"], "draft")

    @patch("src.wp_client.requests.post")
    @patch.object(WPClient, "get_post")
    def test_update_post_fields_allows_publish_to_trash_with_audit_only(self, mock_get_post, mock_post):
        mock_get_post.return_value = {"id": 902, "status": "publish"}
        mock_post.return_value = _mock_response(200, json_data={"id": 902})

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                AUDIT_LEDGER_ENV: "1",
                BLOCK_ENV: "1",
                LEDGER_PATH_ENV: os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl"),
            },
            clear=False,
        ):
            self.wp.update_post_fields(
                902,
                status="trash",
                caller="tests.trash",
                source_lane="tests",
            )
            ledger_rows = [
                json.loads(line)
                for line in Path(os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl")).read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs["json"], {"status": "trash"})
        self.assertEqual(len(ledger_rows), 1)
        self.assertFalse(ledger_rows[0]["blocked"])
        self.assertEqual(ledger_rows[0]["status_after"], "trash")
        self.assertEqual(ledger_rows[0]["channel"], "update_post_fields")

    @patch("src.wp_client.requests.post")
    @patch.object(WPClient, "get_post")
    def test_update_post_status_skips_probe_when_revert_guard_flags_are_off(self, mock_get_post, mock_post):
        mock_post.return_value = _mock_response(200, json_data={"id": 903})

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                AUDIT_LEDGER_ENV: "",
                BLOCK_ENV: "",
                LEDGER_PATH_ENV: os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl"),
            },
            clear=False,
        ):
            self.wp.update_post_status(903, "draft")

        mock_get_post.assert_not_called()
        mock_post.assert_called_once()
        self.assertFalse(os.path.exists(os.path.join(tmpdir, "wp_revert_audit_ledger.jsonl")))


class TestWPClientSourcePublishedAtMeta(unittest.TestCase):
    """MANUAL-INTAKE-002B: source_published_at_iso → WP meta payload."""

    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_writes_source_published_at_meta(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 901})

        post_id = self.wp.create_post(
            "巨人 試合終了 0-5 ヤクルト",
            "<p>body</p>",
            status="draft",
            source_url="https://hochi.news/articles/x.html",
            source_published_at_iso="2026-05-07T18:30:00+09:00",
        )

        self.assertEqual(post_id, 901)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["meta"],
            {
                WPClient.SOURCE_URL_META_KEY: "https://hochi.news/articles/x.html",
                WPClient.SOURCE_PUBLISHED_AT_META_KEY: "2026-05-07T18:30:00+09:00",
            },
        )

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_omits_meta_when_source_published_at_blank(
        self, mock_get, mock_post
    ):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 902})

        post_id = self.wp.create_post(
            "巨人 試合終了 0-5 ヤクルト",
            "<p>body</p>",
            status="draft",
            source_url="https://hochi.news/articles/y.html",
        )

        self.assertEqual(post_id, 902)
        payload = mock_post.call_args.kwargs["json"]
        self.assertNotIn(
            WPClient.SOURCE_PUBLISHED_AT_META_KEY, payload.get("meta", {})
        )

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_writes_source_published_at_only_when_no_url(
        self, mock_get, mock_post
    ):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 903})

        # Title-only path — passing source_url=None must still let the
        # source_published_at meta land on the post.
        post_id = self.wp.create_post(
            "巨人 試合終了 0-5 ヤクルト",
            "<p>body</p>",
            status="draft",
            source_published_at_iso="2026-05-07T18:30:00+09:00",
        )

        self.assertEqual(post_id, 903)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["meta"],
            {WPClient.SOURCE_PUBLISHED_AT_META_KEY: "2026-05-07T18:30:00+09:00"},
        )

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_reuse_existing_post_backfills_source_published_at_meta(
        self, mock_get, mock_post, mock_update
    ):
        # Existing draft has source_url meta but no source_published_at meta.
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 904,
                    "title": {"raw": "巨人 試合終了 0-5 ヤクルト"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [664],
                    "meta": {
                        WPClient.SOURCE_URL_META_KEY: "https://hochi.news/x.html"
                    },
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人 試合終了 0-5 ヤクルト",
            "<p>body</p>",
            status="draft",
            source_url="https://hochi.news/x.html",
            source_published_at_iso="2026-05-07T18:30:00+09:00",
        )

        self.assertEqual(post_id, 904)
        mock_post.assert_not_called()
        mock_update.assert_called_once()
        update_kwargs = mock_update.call_args.kwargs
        self.assertEqual(
            update_kwargs.get("meta"),
            {
                WPClient.SOURCE_PUBLISHED_AT_META_KEY: "2026-05-07T18:30:00+09:00"
            },
        )

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_reuse_existing_post_does_not_overwrite_existing_source_published_at(
        self, mock_get, mock_post, mock_update
    ):
        existing_iso = "2026-04-30T12:00:00+09:00"
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 905,
                    "title": {"raw": "巨人 試合終了 0-5 ヤクルト"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [664],
                    "meta": {
                        WPClient.SOURCE_URL_META_KEY: "https://hochi.news/x.html",
                        WPClient.SOURCE_PUBLISHED_AT_META_KEY: existing_iso,
                    },
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人 試合終了 0-5 ヤクルト",
            "<p>body</p>",
            status="draft",
            source_url="https://hochi.news/x.html",
            source_published_at_iso="2026-05-07T18:30:00+09:00",
        )

        self.assertEqual(post_id, 905)
        mock_post.assert_not_called()
        mock_update.assert_not_called()


class SourceUrlBodyMarkerTests(unittest.TestCase):
    """Body-marker dedup fallback for sites without registered meta."""

    def test_marker_format(self):
        url = "https://x.com/hochi_giants/status/2052271896071200809"
        marker = WPClient._build_source_url_body_marker(url)
        self.assertTrue(marker.startswith("<!--yl-src:"))
        self.assertTrue(marker.endswith("-->"))
        # 16-hex hash → marker length is 11(prefix) + 16 + 3 = 30
        self.assertEqual(len(marker), 30)

    def test_marker_matches_same_url(self):
        url = "https://example.com/article-1"
        marker = WPClient._build_source_url_body_marker(url)
        post = {"content": {"raw": f"<p>本文</p>{marker}"}}
        self.assertTrue(
            WPClient._post_body_carries_source_url_hash(post, url)
        )

    def test_marker_misses_different_url(self):
        marker = WPClient._build_source_url_body_marker("https://a.com/x")
        post = {"content": {"raw": f"<p>本文</p>{marker}"}}
        self.assertFalse(
            WPClient._post_body_carries_source_url_hash(post, "https://b.com/x")
        )

    def test_marker_empty_url_returns_empty(self):
        self.assertEqual(WPClient._build_source_url_body_marker(""), "")
        self.assertEqual(WPClient._build_source_url_body_marker(None), "")

    def test_post_with_no_content_returns_false(self):
        self.assertFalse(
            WPClient._post_body_carries_source_url_hash({}, "https://x.com/a")
        )
        self.assertFalse(
            WPClient._post_body_carries_source_url_hash(
                {"content": ""}, "https://x.com/a"
            )
        )


class TestThinBodyStopGate(unittest.TestCase):
    """RELIABILITY-2026-05-08-G: 本文崩壊 STOP gate at create_post chokepoint.

    Memory rule (feedback_publish_forward_must_check_gate_reason.md) の限定 6
    STOP gate のうち「本文崩壊」を pre-publish で enforce する。13:04 JST
    incident (10 件 oembed-only thin body publish) の再発防止。
    """

    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_oembed_only_body_raises_thin_body_stop(self, mock_get, mock_post):
        # 既存 post なし (find_recent_post_by_title returns []).
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        # 13:04 incident と同じ body shape (oembed-only, 420 chars 程度).
        thin_body = (
            '<div class="yoshilover-x-embed" '
            'style="margin:24px auto !important;max-width:550px;">'
            '<blockquote class="twitter-tweet" data-dnt="true" data-lang="ja">'
            '<a href="https://hochi.news/articles/abc.html">'
            "https://hochi.news/articles/abc.html</a>"
            "</blockquote></div>"
            '<script async src="https://platform.twitter.com/widgets.js" '
            'charset="utf-8"></script>'
        )
        with self.assertRaises(RuntimeError) as ctx:
            self.wp.create_post(
                title="incident reproduction title",
                content=thin_body,
                categories=[663],
                status="publish",
            )
        self.assertIn("thin_body_stop", str(ctx.exception))
        self.assertIn("oembed_only_no_body", str(ctx.exception))
        # No HTTP POST should have happened (STOP gate fires before send).
        mock_post.assert_not_called()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_empty_body_raises_thin_body_stop(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        with self.assertRaises(RuntimeError) as ctx:
            self.wp.create_post(
                title="empty body test",
                content="",
                categories=[663],
                status="publish",
            )
        self.assertIn("thin_body_stop", str(ctx.exception))
        mock_post.assert_not_called()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_normal_body_does_not_raise(self, mock_get, mock_post):
        # 既存 post なし、create POST は 201 で成功.
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = _mock_response(
            201,
            json_data={"id": 12345, "status": "publish"},
        )
        # H3 + p 本文 のある正常な body.
        normal_body = (
            "<h3>📋 事実カード</h3>"
            "<p>巨人 3-2 阪神に勝利。9 回サヨナラ本塁打、先発投手は山崎伊織で 7 回 2 失点。</p>"
            "<h3>🔗 出典記事</h3>"
            '<p><a href="https://hochi.news/articles/abc.html">出典</a></p>'
        )
        post_id = self.wp.create_post(
            title="正常 body test",
            content=normal_body,
            categories=[663],
            status="publish",
        )
        self.assertEqual(post_id, 12345)
        # HTTP POST が呼ばれているはず.
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_scoreboard_only_postgame_card_raises_thin_body_stop(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = _mock_response(
            201,
            json_data={"id": 54321, "status": "publish"},
        )
        thin_body = render_postgame_card(
            {
                "date_label": "2026年5月6日",
                "league_label": "セ・リーグ",
                "home": "巨人",
                "away": "阪神",
                "team_name": "巨人",
                "score": "5-3",
                "result": "loss",
                "one_line_summary": "",
                "source_url": "https://example.com/postgame-source",
                "inning_score": [
                    {
                        "name": "巨人",
                        "innings": [0, 1, 0, 0, 0, 2, 0, 2, "x"],
                        "total": 5,
                    },
                    {
                        "name": "阪神",
                        "innings": [1, 0, 0, 1, 0, 0, 1, 0, 0],
                        "total": 3,
                    },
                ],
                "atbat_results": [],
                "pitching_results": [],
                "opponent_lineup": [],
                "opposing_pitcher": "",
            }
        )["content_html"]
        with self.assertRaises(RuntimeError) as ctx:
            self.wp.create_post(
                title="scoreboard only postgame",
                content=thin_body,
                categories=[663],
                status="publish",
            )
        self.assertIn("thin_body_stop", str(ctx.exception))
        self.assertIn("postgame_scorecard_only", str(ctx.exception))
        mock_post.assert_not_called()


class HighConfidencePlayerEyecatchFallbackTests(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        os.environ.pop("PLAYER_EYECATCH_HIGH_CONFIDENCE_FALLBACK_DISABLED", None)
        self.wp = WPClient()

    @patch("src.player_eyecatch_resolver.resolve_eyecatch_from_title")
    @patch("src.player_eyecatch_resolver.detect_person")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_single_player_title_opens_person_media_lookup(
        self, mock_get, mock_post, mock_detect, mock_resolve
    ):
        mock_get.return_value = _mock_response(200, json_data=[])
        mock_post.return_value = _mock_response(
            201,
            json_data={"id": 9001},
        )
        mock_detect.return_value = "丸佳浩"
        mock_resolve.return_value = 70123

        self.wp.create_post(
            "丸佳浩、若林楽人らがアメリカンノックで右へ左へ",
            "<p>body</p>",
            categories=[663],
            status="draft",
        )

        self.assertEqual(mock_resolve.call_count, 1)
        kwargs = mock_resolve.call_args.kwargs
        self.assertTrue(kwargs["allow_existing_person_media"])
        self.assertFalse(kwargs["allow_diversified_pool"])
        self.assertTrue(kwargs["use_team_fallback"])

        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["featured_media"], 70123)

    @patch("src.player_eyecatch_resolver.resolve_eyecatch_from_title")
    @patch("src.player_eyecatch_resolver.detect_person")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_generic_team_level_title_falls_back_to_team_only(
        self, mock_get, mock_post, mock_detect, mock_resolve
    ):
        mock_get.return_value = _mock_response(200, json_data=[])
        mock_post.return_value = _mock_response(
            201,
            json_data={"id": 9002},
        )
        mock_detect.return_value = None
        mock_resolve.return_value = 65953

        self.wp.create_post(
            "巨人 試合終了 0-5 ヤクルト",
            "<p>body</p>",
            categories=[663],
            status="draft",
        )

        kwargs = mock_resolve.call_args.kwargs
        self.assertFalse(kwargs["allow_existing_person_media"])
        self.assertFalse(kwargs["allow_diversified_pool"])

        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["featured_media"], 65953)

    @patch.dict(
        os.environ,
        {"PLAYER_EYECATCH_HIGH_CONFIDENCE_FALLBACK_DISABLED": "1"},
        clear=False,
    )
    @patch("src.player_eyecatch_resolver.resolve_eyecatch_from_title")
    @patch("src.player_eyecatch_resolver.detect_person")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_kill_switch_disables_person_media_lookup(
        self, mock_get, mock_post, mock_detect, mock_resolve
    ):
        mock_get.return_value = _mock_response(200, json_data=[])
        mock_post.return_value = _mock_response(
            201,
            json_data={"id": 9003},
        )
        mock_detect.return_value = "丸佳浩"
        mock_resolve.return_value = 65953

        self.wp.create_post(
            "丸佳浩、若林楽人らがアメリカンノックで右へ左へ",
            "<p>body</p>",
            categories=[663],
            status="draft",
        )

        kwargs = mock_resolve.call_args.kwargs
        self.assertFalse(kwargs["allow_existing_person_media"])
        self.assertFalse(kwargs["allow_diversified_pool"])

    @patch("src.player_eyecatch_resolver.resolve_eyecatch_from_title")
    @patch("src.player_eyecatch_resolver.detect_person")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_manual_caller_skips_person_media_and_team_fallback(
        self, mock_get, mock_post, mock_detect, mock_resolve
    ):
        mock_get.return_value = _mock_response(200, json_data=[])
        mock_post.return_value = _mock_response(
            201,
            json_data={"id": 9004},
        )
        mock_detect.return_value = "丸佳浩"
        mock_resolve.return_value = None

        self.wp.create_post(
            "丸佳浩、若林楽人らがアメリカンノックで右へ左へ",
            "<p>body</p>",
            categories=[663],
            status="draft",
            caller="manual_intake.cli",
        )

        kwargs = mock_resolve.call_args.kwargs
        self.assertFalse(kwargs["allow_existing_person_media"])
        self.assertFalse(kwargs["allow_diversified_pool"])
        self.assertFalse(kwargs["use_team_fallback"])

    @patch("src.player_eyecatch_resolver.resolve_eyecatch_from_title")
    @patch("src.player_eyecatch_resolver.detect_person")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_caller_provided_featured_media_skips_resolver(
        self, mock_get, mock_post, mock_detect, mock_resolve
    ):
        mock_get.return_value = _mock_response(200, json_data=[])
        mock_post.return_value = _mock_response(
            201,
            json_data={"id": 9005},
        )

        self.wp.create_post(
            "丸佳浩、若林楽人らがアメリカンノックで右へ左へ",
            "<p>body</p>",
            categories=[663],
            status="draft",
            featured_media=12345,
        )

        mock_detect.assert_not_called()
        mock_resolve.assert_not_called()
        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["featured_media"], 12345)


if __name__ == "__main__":
    unittest.main()
