import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cloud_run_smoke_test.sh"


def _service_json(run_draft_only="1", auto_tweet_enabled="0", publish_require_image="1") -> dict:
    return {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "image": "example/image:tag",
                            "env": [
                                {"name": "RUN_DRAFT_ONLY", "value": run_draft_only},
                                {"name": "AUTO_TWEET_ENABLED", "value": auto_tweet_enabled},
                                {"name": "PUBLISH_REQUIRE_IMAGE", "value": publish_require_image},
                            ],
                        }
                    ]
                }
            }
        },
        "status": {
            "latestReadyRevisionName": "test-revision",
            "traffic": [{"revisionName": "test-revision", "percent": 100}],
        },
    }


class CloudRunSmokeTestScriptTests(unittest.TestCase):
    def _run_script(self, service_payload: dict, log_output: str = "2026-04-17T08:40:53Z run_started") -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            service_json_path = tmp / "service.json"
            service_json_path.write_text(json.dumps(service_payload), encoding="utf-8")

            gcloud_path = tmp / "gcloud"
            gcloud_path.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        'if [[ \"$1\" == \"run\" && \"$2\" == \"services\" && \"$3\" == \"describe\" ]]; then',
                        '  cat \"$SERVICE_JSON_PATH\"',
                        'elif [[ \"$1\" == \"logging\" && \"$2\" == \"read\" ]]; then',
                        '  printf \"%s\\n\" \"${GCLOUD_LOG_OUTPUT}\"',
                        'elif [[ \"$1\" == \"config\" && \"$2\" == \"get-value\" && \"$3\" == \"project\" ]]; then',
                        '  printf \"%s\\n\" \"${PROJECT}\"',
                        "else",
                        '  echo \"unexpected gcloud args: $*\" >&2',
                        "  exit 1",
                        "fi",
                    ]
                ),
                encoding="utf-8",
            )
            gcloud_path.chmod(gcloud_path.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{tmp}{os.pathsep}{env['PATH']}",
                    "PROJECT": "baseballsite",
                    "SERVICE_JSON_PATH": str(service_json_path),
                    "GCLOUD_LOG_OUTPUT": log_output,
                }
            )
            return subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_smoke_test_passes_when_expected_env_values_are_present(self):
        result = self._run_script(_service_json())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RUN_DRAFT_ONLY=1", result.stdout)
        self.assertIn("AUTO_TWEET_ENABLED=0", result.stdout)
        self.assertIn("PUBLISH_REQUIRE_IMAGE=1", result.stdout)

    def test_smoke_test_fails_when_run_draft_only_is_disabled(self):
        result = self._run_script(_service_json(run_draft_only="0"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("🔴 RUN_DRAFT_ONLY=0 detected. Expected 1. Rollback required.", result.stderr)

    def test_smoke_test_fails_when_auto_tweet_enabled_is_true(self):
        result = self._run_script(_service_json(auto_tweet_enabled="1"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("🔴 AUTO_TWEET_ENABLED=1 detected. Expected 0. Rollback required.", result.stderr)

    def test_smoke_test_fails_when_publish_require_image_is_disabled(self):
        result = self._run_script(_service_json(publish_require_image="0"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("🔴 PUBLISH_REQUIRE_IMAGE=0 detected. Expected 1. Rollback required.", result.stderr)


if __name__ == "__main__":
    unittest.main()
