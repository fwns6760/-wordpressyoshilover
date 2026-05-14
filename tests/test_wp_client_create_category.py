"""Tests for src.wp_client.WPClient.create_category (DATA-INSIGHT-continuous).

POST /wp/v2/categories の 201 path + term_exists 400 fallback path を
mock requests.post で verify。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def wp_client():
    """Construct WPClient with dummy env (no live calls)."""
    env_patch = {
        "WP_URL": "https://example.test",
        "WP_USER": "test-user",
        "WP_APP_PASSWORD": "test-pass",
    }
    with patch.dict(os.environ, env_patch, clear=False):
        from src import wp_client as wpmod
        client = wpmod.WPClient()
        return client


def test_create_category_returns_id_on_success(wp_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": 671, "name": "データで見る巨人", "slug": "data-giants"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(wp_client, "_request_with_retry", return_value=mock_resp):
        result = wp_client.create_category("データで見る巨人")
        assert result == 671


def test_create_category_returns_existing_id_on_term_exists(wp_client):
    """既存 name と衝突した場合は get_categories の既存 ID を返す (idempotent)."""
    import requests
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"code": "term_exists", "message": "term exists"}
    http_error = requests.HTTPError(response=mock_response)

    # _request_with_retry が term_exists で HTTPError を raise する想定
    def raise_term_exists(*args, **kwargs):
        raise http_error

    with patch.object(wp_client, "_request_with_retry", side_effect=raise_term_exists):
        with patch.object(
            wp_client, "get_categories",
            return_value=[{"id": 670, "name": "コラム", "slug": "column"},
                          {"id": 999, "name": "データで見る巨人", "slug": "data-giants"}],
        ):
            result = wp_client.create_category("データで見る巨人")
            assert result == 999


def test_create_category_returns_zero_on_other_error(wp_client):
    """term_exists 以外の HTTPError は 0 を返す (fallback)。"""
    import requests
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"code": "internal_error"}
    http_error = requests.HTTPError(response=mock_response)

    with patch.object(wp_client, "_request_with_retry", side_effect=http_error):
        result = wp_client.create_category("any")
        assert result == 0


def test_create_category_payload_includes_optional_fields(wp_client):
    """slug / description / parent を渡した時の payload 構造 verify."""
    captured_kwargs = {}

    def capture(*args, **kwargs):
        captured_kwargs.update(kwargs)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 100}
        return mock_resp

    with patch.object(wp_client, "_request_with_retry", side_effect=capture):
        wp_client.create_category(
            "テスト", slug="test-slug", description="テスト説明", parent=5,
        )
        payload = captured_kwargs.get("json", {})
        assert payload.get("name") == "テスト"
        assert payload.get("slug") == "test-slug"
        assert payload.get("description") == "テスト説明"
        assert payload.get("parent") == 5


def test_create_category_omits_empty_optionals(wp_client):
    """slug / description / parent が空のときは payload に含めない."""
    captured_kwargs = {}

    def capture(*args, **kwargs):
        captured_kwargs.update(kwargs)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 100}
        return mock_resp

    with patch.object(wp_client, "_request_with_retry", side_effect=capture):
        wp_client.create_category("最小限")
        payload = captured_kwargs.get("json", {})
        assert payload == {"name": "最小限"}
