"""437 Phase 3: post_x_with_image CLI tests.

scope:
  - dry-run path: 画像 file 保存して終了、 create_tweet 呼ばれない
  - 実 post path: media_upload + create_tweet の順で呼ばれ、 media_ids が伝わる
  - image upload 失敗時: create_tweet 呼ばれず abort
  - ranking JSON 経由の data 注入
  - env 不足時の fail-fast (factory 経由で副作用ゼロ)
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _png_size(b: bytes) -> tuple[int, int]:
    return struct.unpack(">II", b[16:24])


def _make_v1_api(media_id_string: str = "9999111122223333"):
    api = MagicMock()
    media = MagicMock()
    media.media_id_string = media_id_string
    media.media_id = int(media_id_string)
    api.media_upload.return_value = media
    return api


def _make_v2_client(tweet_id: str = "7777888899990000"):
    client = MagicMock()
    response = MagicMock()
    response.data = {"id": tweet_id}
    client.create_tweet.return_value = response
    return client


# ---------- dry-run path ----------


def test_dry_run_saves_image_and_does_not_post(tmp_path, capsys):
    from src.tools.post_x_with_image import main

    out = tmp_path / "preview.png"
    v1_called = MagicMock()
    v2_called = MagicMock()

    code = main(
        [
            "--text",
            "テスト投稿",
            "--dry-run",
            "--dry-run-output",
            str(out),
            "--quiet",
        ],
        _api_v1_factory=v1_called,
        _client_factory=v2_called,
    )
    assert code == 0
    assert out.exists()
    png = out.read_bytes()
    assert _png_size(png) == (1080, 1080)
    v1_called.assert_not_called()
    v2_called.assert_not_called()
    captured = capsys.readouterr()
    assert "[DRY-RUN]" in captured.out


# ---------- 実 post path ----------


def test_post_calls_create_tweet_with_media_ids(tmp_path):
    from src.tools.post_x_with_image import main

    api_v1 = _make_v1_api(media_id_string="1234567890")
    client = _make_v2_client(tweet_id="9876543210")

    code = main(
        [
            "--text",
            "★ 巨人 2 名がセ・リーグ OPS TOP10 入り",
            "--quiet",
        ],
        _api_v1_factory=lambda: api_v1,
        _client_factory=lambda: client,
    )
    assert code == 0
    api_v1.media_upload.assert_called_once()
    client.create_tweet.assert_called_once()
    call_kwargs = client.create_tweet.call_args.kwargs
    assert call_kwargs["text"] == "★ 巨人 2 名がセ・リーグ OPS TOP10 入り"
    assert call_kwargs["media_ids"] == ["1234567890"]


def test_post_prints_tweet_url(capsys):
    from src.tools.post_x_with_image import main

    api_v1 = _make_v1_api()
    client = _make_v2_client(tweet_id="1112223334445556")

    code = main(
        ["--text", "test", "--quiet"],
        _api_v1_factory=lambda: api_v1,
        _client_factory=lambda: client,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "https://x.com/i/web/status/1112223334445556" in out


# ---------- ranking JSON ----------


def test_ranking_json_drives_image_data(tmp_path):
    from src.tools.post_x_with_image import main

    ranking_file = tmp_path / "ranking.json"
    ranking_file.write_text(
        json.dumps(
            {
                "title": "custom title",
                "subtitle": "custom subtitle",
                "hook": "★ custom hook ★",
                "rows": [
                    {
                        "rank": 1,
                        "name": "坂本勇人",
                        "team": "巨人",
                        "value": "1.000",
                        "is_giants": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "preview.png"

    code = main(
        [
            "--text",
            "test",
            "--ranking-json",
            str(ranking_file),
            "--dry-run",
            "--dry-run-output",
            str(out),
            "--quiet",
        ],
    )
    assert code == 0
    assert out.exists()


def test_ranking_json_missing_file_returns_nonzero(tmp_path):
    from src.tools.post_x_with_image import main

    code = main(
        [
            "--text",
            "test",
            "--ranking-json",
            str(tmp_path / "no_such_file.json"),
            "--dry-run",
            "--quiet",
        ],
    )
    assert code == 2


# ---------- failure path ----------


def test_post_aborts_when_media_upload_fails():
    from src.tools.post_x_with_image import main

    api_v1 = MagicMock()
    api_v1.media_upload.return_value = MagicMock(spec=[])  # media_id_string なし
    client = _make_v2_client()

    code = main(
        ["--text", "test", "--quiet"],
        _api_v1_factory=lambda: api_v1,
        _client_factory=lambda: client,
    )
    assert code == 4  # media upload failure exit code
    client.create_tweet.assert_not_called()


def test_post_aborts_when_media_upload_raises():
    import tweepy

    from src.tools.post_x_with_image import main

    api_v1 = MagicMock()
    api_v1.media_upload.side_effect = tweepy.TweepyException("upload failed")
    client = _make_v2_client()

    code = main(
        ["--text", "test", "--quiet"],
        _api_v1_factory=lambda: api_v1,
        _client_factory=lambda: client,
    )
    assert code == 4
    client.create_tweet.assert_not_called()


def test_post_aborts_when_create_tweet_raises():
    import tweepy

    from src.tools.post_x_with_image import main

    api_v1 = _make_v1_api()
    client = MagicMock()
    client.create_tweet.side_effect = tweepy.TweepyException("rate limit")

    code = main(
        ["--text", "test", "--quiet"],
        _api_v1_factory=lambda: api_v1,
        _client_factory=lambda: client,
    )
    assert code == 5
    api_v1.media_upload.assert_called_once()


def test_env_missing_fail_fast():
    """X_API_KEY 等の env が無いと _get_v1_api_for_upload が RuntimeError、
    main は exit 3 を返す。"""
    import os

    from src.tools.post_x_with_image import _get_v1_api_for_upload, main

    saved = {}
    for k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]:
        saved[k] = os.environ.pop(k, None)
    try:
        with pytest.raises(RuntimeError, match="X API env missing"):
            _get_v1_api_for_upload()

        code = main(
            ["--text", "test", "--quiet"],
            _api_v1_factory=_get_v1_api_for_upload,
            _client_factory=lambda: MagicMock(),
        )
        assert code == 3
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
