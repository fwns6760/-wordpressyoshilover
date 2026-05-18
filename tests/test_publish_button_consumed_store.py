"""tests for src/publish_button_consumed_store.py (379-OPS / GH #53)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src import publish_button_consumed_store as store


class HashTokenTests(unittest.TestCase):
    def test_hash_is_stable(self):
        assert store._hash_token("foo") == store._hash_token("foo")

    def test_different_tokens_different_hashes(self):
        assert store._hash_token("foo") != store._hash_token("bar")

    def test_hash_is_truncated_to_32(self):
        assert len(store._hash_token("anything")) == 32

    def test_empty_token_hashes(self):
        # 空も hash 可能 (caller 側で is_consumed が False を返す)
        assert len(store._hash_token("")) == 32


class IsConsumedTests(unittest.TestCase):
    def test_empty_token_returns_false(self):
        assert store.is_consumed("") is False
        assert store.is_consumed(None) is False  # type: ignore[arg-type]

    def test_gcs_init_failure_returns_false_fail_open(self):
        with patch.object(store, "_gcs_blob", return_value=None):
            assert store.is_consumed("some-token") is False

    def test_blob_exists_returns_true(self):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            assert store.is_consumed("token") is True

    def test_blob_not_exists_returns_false(self):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            assert store.is_consumed("token") is False

    def test_blob_exists_raises_returns_false_fail_open(self):
        mock_blob = MagicMock()
        mock_blob.exists.side_effect = RuntimeError("network err")
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            assert store.is_consumed("token") is False


class MarkConsumedTests(unittest.TestCase):
    def test_empty_token_returns_false(self):
        assert store.mark_consumed("") is False
        assert store.mark_consumed(None) is False  # type: ignore[arg-type]

    def test_gcs_init_failure_returns_false(self):
        with patch.object(store, "_gcs_blob", return_value=None):
            assert store.mark_consumed("some-token") is False

    def test_successful_upload_returns_true(self):
        mock_blob = MagicMock()
        # upload_from_string returns None on success
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            assert store.mark_consumed("token", post_id=123) is True
        mock_blob.upload_from_string.assert_called_once()
        call_kwargs = mock_blob.upload_from_string.call_args.kwargs
        assert call_kwargs.get("if_generation_match") == 0
        assert call_kwargs.get("content_type") == "application/json"

    def test_upload_with_precondition_failure_returns_false(self):
        mock_blob = MagicMock()
        mock_blob.upload_from_string.side_effect = RuntimeError(
            "412 Precondition Failed"
        )
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            assert store.mark_consumed("token", post_id=123) is False

    def test_payload_contains_post_id_and_consumed_at(self):
        mock_blob = MagicMock()
        captured_payload = {}

        def capture(payload, **kwargs):
            import json
            captured_payload.update(json.loads(payload))

        mock_blob.upload_from_string.side_effect = capture
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            store.mark_consumed("token", post_id=42, now=1_700_000_000)
        assert captured_payload["post_id"] == 42
        assert captured_payload["consumed_at_unix"] == 1_700_000_000

    def test_payload_handles_none_post_id(self):
        mock_blob = MagicMock()
        captured_payload = {}

        def capture(payload, **kwargs):
            import json
            captured_payload.update(json.loads(payload))

        mock_blob.upload_from_string.side_effect = capture
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            store.mark_consumed("token", post_id=None, now=1)
        assert captured_payload["post_id"] is None


class RaceConditionScenarioTests(unittest.TestCase):
    """並列 click 時のシナリオ: 同時 mark → 1 つ True / 残り False を verify."""

    def test_first_mark_succeeds_second_fails(self):
        mock_blob = MagicMock()
        # 1 回目 OK、 2 回目 precondition fail
        mock_blob.upload_from_string.side_effect = [None, RuntimeError("412")]
        with patch.object(store, "_gcs_blob", return_value=mock_blob):
            assert store.mark_consumed("token", post_id=1) is True
            assert store.mark_consumed("token", post_id=1) is False


if __name__ == "__main__":
    unittest.main()
