"""tests for x_post_mail_lane share-x-cand integration (437 Phase 8 / 2026-05-26).

env が揃った状態で compose_mail が candidate ごとに GCS upload + /share-x-cand URL を
HTML body の button href に埋め込むことを verify。 env 未設定時は既存の X intent URL に戻る
(backward compatible)。
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.x_post_mail_lane import Candidate, compose_mail


JST = ZoneInfo("Asia/Tokyo")


def _make_cand(idx: int = 1) -> Candidate:
    return Candidate(
        title=f"テスト候補 {idx}",
        metric="OPS",
        period_label="直近5試合",
        draft_text="1位 坂本勇人（巨人）1.234 🟧巨人🟧\n2位 岡本和真（巨人）1.100 🟧巨人🟧",
        post_text="坂本勇人 OPS 1.234 #巨人",
        char_count=20,
        focus_player="坂本勇人",
    )


class ShareXCandIntegrationTests(unittest.TestCase):
    def test_env_disabled_falls_back_to_intent_url(self) -> None:
        ts = datetime(2026, 5, 26, 12, 0, tzinfo=JST)
        env_clear = {
            k: ""
            for k in ("ENABLE_SHARE_X_BUTTON", "INSIGHT_GCS_BUCKET", "FETCHER_PUBLIC_BASE_URL")
        }
        with patch.dict(os.environ, env_clear, clear=False):
            mail = compose_mail([_make_cand(1)], now=ts)
        # share-x-cand button URL は無く、 X intent URL がそのまま使われる
        self.assertNotIn("/share-x-cand?", mail.html_body)
        self.assertIn("x.com/intent/post", mail.html_body)
        self.assertIn("🐦 X で投稿", mail.html_body)

    def test_env_partial_missing_bucket_falls_back(self) -> None:
        ts = datetime(2026, 5, 26, 12, 0, tzinfo=JST)
        env = {
            "ENABLE_SHARE_X_BUTTON": "1",
            "INSIGHT_GCS_BUCKET": "",  # missing
            "FETCHER_PUBLIC_BASE_URL": "https://fetcher.example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            mail = compose_mail([_make_cand(1)], now=ts)
        self.assertNotIn("/share-x-cand?", mail.html_body)

    def test_env_partial_missing_fetcher_falls_back(self) -> None:
        ts = datetime(2026, 5, 26, 12, 0, tzinfo=JST)
        env = {
            "ENABLE_SHARE_X_BUTTON": "1",
            "INSIGHT_GCS_BUCKET": "test-bucket",
            "FETCHER_PUBLIC_BASE_URL": "",  # missing
        }
        with patch.dict(os.environ, env, clear=False):
            mail = compose_mail([_make_cand(1)], now=ts)
        self.assertNotIn("/share-x-cand?", mail.html_body)

    def test_env_enabled_embeds_share_x_cand_url(self) -> None:
        ts = datetime(2026, 5, 26, 12, 0, tzinfo=JST)
        env = {
            "ENABLE_SHARE_X_BUTTON": "1",
            "INSIGHT_GCS_BUCKET": "test-bucket",
            "FETCHER_PUBLIC_BASE_URL": "https://fetcher.example.com",
        }
        # GCS upload を mock (実 GCS には触れない)
        upload_calls: list[tuple[str, str]] = []

        def _fake_upload(png, *, bucket_name, blob_key, content_type="image/png"):
            upload_calls.append((bucket_name, blob_key))
            return True  # 成功

        with patch.dict(os.environ, env, clear=False), patch(
            "src.x_post_mail_lane._upload_candidate_image_to_gcs",
            side_effect=_fake_upload,
        ):
            mail = compose_mail([_make_cand(1), _make_cand(2)], now=ts)

        # GCS upload が候補ごとに呼ばれた
        self.assertEqual(len(upload_calls), 2)
        for bucket_name, blob_key in upload_calls:
            self.assertEqual(bucket_name, "test-bucket")
            self.assertTrue(blob_key.startswith("share_x_cand/20260526-120000/cand-"))

        # button URL が share-x-cand 経路に置換された
        self.assertIn("https://fetcher.example.com/share-x-cand?", mail.html_body)
        # button label が画像つき変種に変わった
        self.assertIn("🐦 画像つきで X に投稿", mail.html_body)
        # blob key と token が URL params に含まれる
        self.assertIn("key=share_x_cand", mail.html_body)
        self.assertIn("token=", mail.html_body)

    def test_upload_failure_falls_back_to_intent(self) -> None:
        ts = datetime(2026, 5, 26, 12, 0, tzinfo=JST)
        env = {
            "ENABLE_SHARE_X_BUTTON": "1",
            "INSIGHT_GCS_BUCKET": "test-bucket",
            "FETCHER_PUBLIC_BASE_URL": "https://fetcher.example.com",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "src.x_post_mail_lane._upload_candidate_image_to_gcs", return_value=False
        ):
            mail = compose_mail([_make_cand(1)], now=ts)
        # share-x-cand URL は埋め込まれない、 X intent URL が button href
        self.assertNotIn("/share-x-cand?", mail.html_body)
        self.assertIn("x.com/intent/post", mail.html_body)
        self.assertIn("🐦 X で投稿", mail.html_body)


if __name__ == "__main__":
    unittest.main()
