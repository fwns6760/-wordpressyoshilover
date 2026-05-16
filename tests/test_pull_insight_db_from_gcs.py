from __future__ import annotations

import io
import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

from src.tools import pull_insight_db_from_gcs as tool


class _FakeBlob:
    def __init__(self, store: dict[str, bytes], name: str):
        self._store = store
        self._name = name

    def exists(self) -> bool:
        return self._name in self._store

    def download_to_filename(self, dst: str) -> None:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(self._store[self._name])


class _FakeBucket:
    def __init__(self, store: dict[str, bytes]):
        self._store = store

    def blob(self, object_name: str) -> _FakeBlob:
        return _FakeBlob(self._store, object_name)


class _FakeClient:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(self.store)


def _build_db_bytes(path: Path) -> bytes:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE games (
                game_id TEXT PRIMARY KEY,
                game_date TEXT
            );
            CREATE TABLE batting_logs (
                game_id TEXT,
                team_name TEXT
            );
            CREATE TABLE pitching_logs (
                game_id TEXT,
                team_name TEXT
            );
            CREATE TABLE advanced_metric_snapshots (
                snapshot_id INTEGER PRIMARY KEY
            );
            CREATE TABLE article_candidates (
                candidate_id INTEGER PRIMARY KEY
            );
            """
        )
        conn.executemany(
            "INSERT INTO games (game_id, game_date) VALUES (?, ?)",
            [
                ("2026-05-15:g-t-07", "2026-05-15"),
                ("2026-05-16:l-h-08", "2026-05-16"),
            ],
        )
        conn.executemany(
            "INSERT INTO batting_logs (game_id, team_name) VALUES (?, ?)",
            [
                ("2026-05-15:g-t-07", "巨人"),
                ("2026-05-16:l-h-08", "西武"),
            ],
        )
        conn.executemany(
            "INSERT INTO pitching_logs (game_id, team_name) VALUES (?, ?)",
            [
                ("2026-05-15:g-t-07", "巨人"),
                ("2026-05-16:l-h-08", "西武"),
            ],
        )
        conn.execute("INSERT INTO advanced_metric_snapshots DEFAULT VALUES")
        conn.execute("INSERT INTO article_candidates DEFAULT VALUES")
        conn.commit()
    finally:
        conn.close()
    return path.read_bytes()


def test_pull_latest_insight_db_downloads_to_requested_path(monkeypatch, tmp_path):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    fake = _FakeClient()
    fake.store["insight.db"] = _build_db_bytes(tmp_path / "source.db")
    target = tmp_path / "pulled.db"

    result = tool.pull_latest_insight_db(
        target=target,
        bucket_name="prod-bucket",
        client=fake,
    )

    assert result["ok"] is True
    assert result["source"] == {
        "bucket": "prod-bucket",
        "object": "insight.db",
        "mode": "download_only",
    }
    assert target.exists()
    assert result["summary"]["latest_game_date"] == "2026-05-16"
    assert result["summary"]["latest_giants_game_date"] == "2026-05-15"
    assert result["summary"]["tables"]["games"] == 2
    assert result["summary"]["tables"]["advanced_metric_snapshots"] == 1


def test_pull_latest_insight_db_reports_missing_blob(monkeypatch, tmp_path):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    fake = _FakeClient()
    target = tmp_path / "missing.db"

    result = tool.pull_latest_insight_db(
        target=target,
        bucket_name="prod-bucket",
        client=fake,
    )

    assert result["ok"] is False
    assert result["download"]["reason"] == "blob_missing"
    assert not target.exists()


def test_pull_restores_existing_bucket_env(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "original-bucket")
    fake = _FakeClient()
    fake.store["insight.db"] = _build_db_bytes(tmp_path / "source.db")

    result = tool.pull_latest_insight_db(
        target=tmp_path / "pulled.db",
        bucket_name="override-bucket",
        client=fake,
    )

    assert result["ok"] is True
    assert result["source"]["bucket"] == "override-bucket"
    assert tool.os.environ["INSIGHT_GCS_BUCKET"] == "original-bucket"


def test_main_prints_json_and_defaults_to_tmp_not_repo_local(monkeypatch, tmp_path):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    fake = _FakeClient()
    fake.store["insight.db"] = _build_db_bytes(tmp_path / "source.db")
    out = io.StringIO()
    target = tmp_path / "cli.db"

    exit_code = tool.main(
        ["--target", str(target), "--bucket", "prod-bucket"],
        client=fake,
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["download"]["path"] == str(target)
    assert payload["source"]["mode"] == "download_only"


def test_pull_falls_back_to_gcloud_when_python_storage_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    db_bytes = _build_db_bytes(tmp_path / "source.db")
    target = tmp_path / "gcloud.db"

    def fake_ensure_local_db(**kwargs):
        return {
            "ok": False,
            "path": str(kwargs["cache_path"]),
            "refreshed": False,
            "reason": "download_error:ModuleNotFoundError(\"No module named 'google'\")",
        }

    def fake_run(command, capture_output, check):
        assert command[:4] == ["gcloud", "--project", "baseballsite", "storage"]
        assert command[4] == "cp"
        assert command[5] == "gs://prod-bucket/insight.db"
        Path(command[6]).write_bytes(db_bytes)
        assert command[7] == "--quiet"
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(tool.miq, "ensure_local_db", fake_ensure_local_db)
    with patch("src.cloud_run_persistence.subprocess.run", side_effect=fake_run):
        result = tool.pull_latest_insight_db(
            target=target,
            bucket_name="prod-bucket",
        )

    assert result["ok"] is True
    assert result["download"]["transport"] == "gcloud_storage"
    assert result["download"]["reason"] == "downloaded_gcloud"
    assert result["summary"]["latest_game_date"] == "2026-05-16"
