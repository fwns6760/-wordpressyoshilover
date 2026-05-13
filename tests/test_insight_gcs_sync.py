"""Tests for src.analysis.insight_gcs_sync.

Uses fake GCS client / bucket / blob classes so no real GCS access
happens. ``INSIGHT_GCS_BUCKET`` env var is set / unset via monkeypatch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.analysis import insight_gcs_sync as sync


class _FakeBlob:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name

    def exists(self) -> bool:
        return self._name in self._store

    def download_to_filename(self, dst: str) -> None:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(self._store[self._name])

    def upload_from_filename(self, src: str) -> None:
        self._store[self._name] = Path(src).read_bytes()


class _FakeBucket:
    def __init__(self, store: dict, name: str):
        self._store = store
        self.name = name

    def blob(self, object_name: str) -> _FakeBlob:
        return _FakeBlob(self._store, object_name)


class _FakeClient:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(self.store, name)


@pytest.fixture
def fake_client():
    return _FakeClient()


# ─── env helpers ──────────────────────────────────────────────────────────


def test_gcs_bucket_name_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    assert sync.gcs_bucket_name() is None


def test_gcs_bucket_name_returns_env(monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "my-bucket")
    assert sync.gcs_bucket_name() == "my-bucket"


def test_gcs_prefix_strips(monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_PREFIX", "/foo/bar/")
    assert sync.gcs_prefix() == "foo/bar"


# ─── no-op when bucket unset ───────────────────────────────────────────────


def test_download_noop_when_bucket_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    result = sync.download_state(base_dir=tmp_path)
    assert result["skipped"] is True
    assert result["reason"] == "no_bucket"


def test_upload_noop_when_bucket_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    (tmp_path / "insight.db").write_bytes(b"x")
    result = sync.upload_state(base_dir=tmp_path)
    assert result["skipped"] is True


# ─── roundtrip ─────────────────────────────────────────────────────────────


def test_upload_then_download_roundtrip(tmp_path, fake_client, monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    monkeypatch.delenv("INSIGHT_GCS_PREFIX", raising=False)

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "insight.db").write_bytes(b"hello db")
    (src_dir / "article_candidates.csv").write_text("header\nrow", encoding="utf-8")

    up = sync.upload_state(base_dir=src_dir, client=fake_client)
    assert up["skipped"] is False
    assert {o["object"] for o in up["uploaded"]} == {"insight.db", "article_candidates.csv"}

    dst_dir = tmp_path / "dst"
    down = sync.download_state(base_dir=dst_dir, client=fake_client)
    assert down["skipped"] is False
    assert {o["object"] for o in down["downloaded"]} == {"insight.db", "article_candidates.csv"}
    assert (dst_dir / "insight.db").read_bytes() == b"hello db"


def test_upload_with_prefix(tmp_path, fake_client, monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    monkeypatch.setenv("INSIGHT_GCS_PREFIX", "envA")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "insight.db").write_bytes(b"db")

    up = sync.upload_state(base_dir=src_dir, client=fake_client)
    assert up["uploaded"][0]["object"] == "envA/insight.db"


def test_upload_includes_digest_directory(tmp_path, fake_client, monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    monkeypatch.delenv("INSIGHT_GCS_PREFIX", raising=False)

    base = tmp_path / "data"
    base.mkdir()
    (base / "insight.db").write_bytes(b"db")
    digest_dir = base / "digest"
    digest_dir.mkdir()
    (digest_dir / "2026-05-12.md").write_text("# digest", encoding="utf-8")
    (digest_dir / "2026-05-13.md").write_text("# digest 2", encoding="utf-8")

    up = sync.upload_state(
        base_dir=base, digest_dir=digest_dir, client=fake_client,
    )
    objs = {o["object"] for o in up["uploaded"]}
    assert "insight.db" in objs
    assert "digest/2026-05-12.md" in objs
    assert "digest/2026-05-13.md" in objs


def test_upload_skips_missing_files(tmp_path, fake_client, monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    base = tmp_path / "data"
    base.mkdir()
    # only db exists
    (base / "insight.db").write_bytes(b"db")
    up = sync.upload_state(base_dir=base, client=fake_client)
    assert any(o["object"] == "insight.db" for o in up["uploaded"])
    assert "article_candidates.csv" in up["missing"]


def test_download_missing_objects_listed(tmp_path, fake_client, monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    # bucket is empty (first run scenario)
    down = sync.download_state(base_dir=tmp_path, client=fake_client)
    assert down["downloaded"] == []
    assert "insight.db" in down["missing"]
    assert "article_candidates.csv" in down["missing"]


def test_download_partial_existing(tmp_path, fake_client, monkeypatch):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    fake_client.store["insight.db"] = b"existing"
    down = sync.download_state(base_dir=tmp_path, client=fake_client)
    assert any(d["object"] == "insight.db" for d in down["downloaded"])
    assert "article_candidates.csv" in down["missing"]
    assert (tmp_path / "insight.db").read_bytes() == b"existing"
