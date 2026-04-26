from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools import run_guarded_publish as cli


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class _FakeWP:
    def get_post(self, post_id: int) -> dict:
        return {
            "id": post_id,
            "content": {"raw": "<p>after publish body</p>", "rendered": "<p>after publish body</p>"},
        }


class RunGuardedPublishLedgerTests(unittest.TestCase):
    def test_live_history_rows_are_mirrored_best_effort(self) -> None:
        completed = cli.repair_provider_ledger.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b"token\n",
            stderr=b"",
        )

        for mode in ("success", "firestore_failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                input_path = tmp / "input.json"
                history_path = tmp / "history.jsonl"
                fallback_path = tmp / "fallback.jsonl"
                backup_path = tmp / "backup.json"
                artifact_uris: list[str] = []

                input_path.write_text("{}\n", encoding="utf-8")
                backup_path.write_text(
                    json.dumps(
                        {
                            "id": 63105,
                            "content": {"raw": "<p>before publish body</p>", "rendered": "<p>before publish body</p>"},
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                def fake_requests(method, url, **kwargs):
                    if method == "POST" and "repair_ledger_locks" in url:
                        return _FakeResponse(200, {"name": "lock-doc"})
                    if method == "GET" and "repair_ledger/" in url:
                        return _FakeResponse(404, {"error": {"message": "missing"}})
                    if method == "POST" and "repair_ledger" in url:
                        if mode == "firestore_failure":
                            raise cli.repair_provider_ledger.requests.RequestException("firestore down")
                        artifact_uris.append(kwargs["json"]["fields"]["artifact_uri"]["stringValue"])
                        return _FakeResponse(200, {"name": "ledger-doc"})
                    if method == "DELETE" and "repair_ledger_locks" in url:
                        return _FakeResponse(200, {})
                    raise AssertionError(f"unexpected request: {method} {url}")

                def fake_run_guarded_publish(**kwargs):
                    row = {
                        "post_id": 63105,
                        "judgment": "green",
                        "status": "sent",
                        "ts": "2026-04-26T23:10:00+09:00",
                        "backup_path": str(backup_path),
                        "error": None,
                        "publishable": True,
                        "cleanup_required": False,
                        "cleanup_success": None,
                        "hold_reason": None,
                    }
                    Path(kwargs["history_path"]).write_text(
                        json.dumps(row, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    return {
                        "scan_meta": {
                            "input_from": str(kwargs["input_from"]),
                            "live": True,
                            "max_burst": 1,
                            "ts": "2026-04-26T23:10:00+09:00",
                        },
                        "proposed": [],
                        "refused": [],
                        "summary": {
                            "proposed_count": 0,
                            "refused_count": 0,
                            "would_publish": 1,
                            "would_skip": 0,
                            "postcheck_batch_count": 0,
                        },
                        "executed": [
                            {
                                "post_id": 63105,
                                "status": "sent",
                                "backup_path": str(backup_path),
                                "publish_link": "https://yoshilover.com/63105",
                            }
                        ],
                        "postcheck_batches": [],
                    }

                stdout = io.StringIO()
                with patch.dict(
                    "os.environ",
                    {
                        cli.runner_ledger_integration.ENV_LEDGER_FIRESTORE_ENABLED: "true",
                        cli.runner_ledger_integration.ENV_LEDGER_GCS_ARTIFACT_ENABLED: "true",
                        "GOOGLE_CLOUD_PROJECT": "project-id",
                    },
                    clear=False,
                ), patch(
                    "src.tools.run_guarded_publish.run_guarded_publish",
                    side_effect=fake_run_guarded_publish,
                ), patch(
                    "src.tools.run_guarded_publish._make_wp_client",
                    return_value=_FakeWP(),
                ), patch(
                    "src.tools.run_guarded_publish.repair_provider_ledger.resolve_jsonl_ledger_path",
                    return_value=fallback_path,
                ), patch(
                    "src.repair_provider_ledger.subprocess.run",
                    return_value=completed,
                ), patch(
                    "src.cloud_run_persistence.subprocess.run",
                    return_value=completed,
                ), patch(
                    "src.repair_provider_ledger.requests.request",
                    side_effect=fake_requests,
                ), patch("sys.stdout", stdout):
                    exit_code = cli.main(
                        [
                            "--input-from",
                            str(input_path),
                            "--live",
                            "--daily-cap-allow",
                            "--history-path",
                            str(history_path),
                        ]
                    )

                self.assertEqual(exit_code, 0)
                if mode == "success":
                    self.assertTrue(artifact_uris)
                    self.assertTrue(artifact_uris[0].startswith("gs://yoshilover-history/repair_artifacts/"))
                else:
                    rows = [
                        json.loads(line)
                        for line in fallback_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    self.assertEqual(len(rows), 1)
                    self.assertTrue(rows[0]["artifact_uri"].startswith("gs://yoshilover-history/repair_artifacts/"))


if __name__ == "__main__":
    unittest.main()
