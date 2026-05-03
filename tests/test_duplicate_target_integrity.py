import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from src import guarded_publish_runner as runner
from tests.test_guarded_publish_runner import FIXED_NOW, LONG_EXTRA, FakeWPClient, _green_entry, _post, _report


FIXTURE_CASES = {
    "positive_exact_match": {
        "candidate_source_url": "https://example.com/shared-source-exact",
        "target_source_url": "https://example.com/shared-source-exact",
    },
    "negative_hash_mismatch": {
        "candidate_source_url": "https://example.com/shared-source-candidate",
        "target_source_url": "https://example.com/shared-source-other",
    },
    "negative_target_post_id_invalid": {
        "candidate_source_url": "https://example.com/shared-source-post-id",
        "target_source_url": "https://example.com/shared-source-post-id",
        "target_post_id_raw": "invalid-post-id",
    },
}


def _candidate_post(post_id: int, title: str, source_url: str) -> dict:
    body_html = (
        f"<p>{title}について整理した。</p>"
        f"<p>{LONG_EXTRA}</p>"
        f"<p>参照元: スポーツ報知 {source_url}</p>"
    )
    return _post(
        post_id,
        title,
        body_html,
        subtype="comment",
        meta={"article_subtype": "comment", "speaker_name": "阿部監督"},
    )


def _published_post(post_id: int, title: str, source_url: str) -> dict:
    post = _candidate_post(post_id, title, source_url)
    post["status"] = "publish"
    post["date"] = "2026-04-26T07:10:00+09:00"
    post["modified"] = "2026-04-26T07:20:00+09:00"
    return post


class DuplicateTargetIntegrityTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _run_live_case(
        self,
        candidate: dict,
        posts: dict[int, dict],
        *,
        env: dict[str, str] | None = None,
        publish_index_override: dict | None = None,
    ) -> tuple[dict, dict, list[dict]]:
        wp = FakeWPClient(posts)
        report = _report(green=[_green_entry(int(candidate["id"]), str(candidate["title"]["raw"]))])

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict("os.environ", env or {}, clear=False):
            history_path = Path(tmpdir) / "history.jsonl"
            stderr_path = Path(tmpdir) / "stderr.jsonl"
            with stderr_path.open("w", encoding="utf-8") as stderr_handle, patch("sys.stderr", stderr_handle):
                if publish_index_override is None:
                    result = runner.run_guarded_publish(
                        input_from=self._write_input(tmpdir, report),
                        live=True,
                        daily_cap_allow=True,
                        history_path=history_path,
                        backup_dir=Path(tmpdir) / "cleanup_backup",
                        yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                        cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                        wp_client=wp,
                        now=FIXED_NOW,
                    )
                else:
                    with patch.object(
                        runner,
                        "_build_duplicate_index",
                        side_effect=[publish_index_override, runner._empty_duplicate_index()],
                    ):
                        result = runner.run_guarded_publish(
                            input_from=self._write_input(tmpdir, report),
                            live=True,
                            daily_cap_allow=True,
                            history_path=history_path,
                            backup_dir=Path(tmpdir) / "cleanup_backup",
                            yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                            cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                            wp_client=wp,
                            now=FIXED_NOW,
                        )

            history_rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            stderr_events = [json.loads(line) for line in stderr_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        integrity_event = next(
            (event for event in stderr_events if event.get("event") == "duplicate_target_integrity_check"),
            {},
        )
        history_row = history_rows[0]
        return result, history_row, integrity_event

    def test_flag_off_keeps_same_source_url_duplicate_behavior_unchanged(self):
        case = FIXTURE_CASES["positive_exact_match"]
        candidate = _candidate_post(7101, "阿部監督が継投を説明", case["candidate_source_url"])
        existing = _published_post(9101, "阿部監督が勝負手を説明", case["target_source_url"])

        result, history_row, integrity_event = self._run_live_case(
            candidate,
            {7101: candidate, 9101: existing},
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9101)
        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(history_row["duplicate_reason"], "same_source_url")
        self.assertNotIn("candidate_source_url_hash", history_row)
        self.assertNotIn("duplicate_target_source_url_hash", history_row)
        self.assertNotIn("duplicate_target_source_url", history_row)
        self.assertEqual(integrity_event, {})

    def test_flag_on_exact_match_emits_integrity_event_and_preserves_hold(self):
        case = FIXTURE_CASES["positive_exact_match"]
        candidate = _candidate_post(7102, "阿部監督が継投を説明", case["candidate_source_url"])
        existing = _published_post(9102, "阿部監督が勝負手を説明", case["target_source_url"])
        expected_hash = runner._source_url_hash(case["candidate_source_url"])

        result, history_row, integrity_event = self._run_live_case(
            candidate,
            {7102: candidate, 9102: existing},
            env={runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1"},
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9102)
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")
        self.assertEqual(history_row["duplicate_reason"], "same_source_url")
        self.assertEqual(history_row["candidate_source_url_hash"], expected_hash)
        self.assertEqual(history_row["duplicate_target_post_id"], 9102)
        self.assertEqual(history_row["duplicate_target_source_url_hash"], expected_hash)
        self.assertEqual(history_row["duplicate_target_source_url"], case["target_source_url"])
        self.assertTrue(integrity_event["integrity_ok"])
        self.assertEqual(integrity_event["candidate_source_url_hash"], expected_hash)
        self.assertEqual(integrity_event["duplicate_target_post_id"], 9102)
        self.assertEqual(integrity_event["duplicate_target_source_url_hash"], expected_hash)
        self.assertEqual(integrity_event["duplicate_target_source_url"], case["target_source_url"])

    def test_flag_on_hash_mismatch_becomes_duplicate_integrity_fail(self):
        case = FIXTURE_CASES["negative_hash_mismatch"]
        candidate = _candidate_post(7103, "阿部監督が継投を説明", case["candidate_source_url"])
        existing = _published_post(9103, "阿部監督が勝負手を説明", case["target_source_url"])
        candidate_hash = runner._source_url_hash(case["candidate_source_url"])
        target_hash = runner._source_url_hash(case["target_source_url"])

        publish_index = runner._empty_duplicate_index()
        reference = runner._duplicate_reference_payload(existing)
        publish_index["source_hashes"][candidate_hash] = [reference]

        result, history_row, integrity_event = self._run_live_case(
            candidate,
            {7103: candidate, 9103: existing},
            env={runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1"},
            publish_index_override=publish_index,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_duplicate_integrity_fail")
        self.assertIsNone(result["refused"][0]["duplicate_of_post_id"])
        self.assertEqual(result["refused"][0]["duplicate_reason"], "duplicate_integrity_fail")
        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(history_row["duplicate_reason"], "duplicate_integrity_fail")
        self.assertIsNone(history_row["duplicate_of_post_id"])
        self.assertEqual(history_row["candidate_source_url_hash"], candidate_hash)
        self.assertEqual(history_row["duplicate_target_post_id"], 9103)
        self.assertEqual(history_row["duplicate_target_source_url_hash"], target_hash)
        self.assertEqual(history_row["duplicate_target_source_url"], case["target_source_url"])
        self.assertEqual(history_row["duplicate_integrity_error"], "source_url_hash_mismatch")
        self.assertFalse(integrity_event["integrity_ok"])
        self.assertEqual(integrity_event["candidate_source_url_hash"], candidate_hash)
        self.assertEqual(integrity_event["duplicate_target_post_id"], 9103)
        self.assertEqual(integrity_event["duplicate_target_source_url_hash"], target_hash)
        self.assertEqual(integrity_event["duplicate_target_source_url"], case["target_source_url"])
        self.assertEqual(integrity_event["duplicate_integrity_error"], "source_url_hash_mismatch")

    def test_flag_on_invalid_target_post_id_becomes_duplicate_integrity_fail(self):
        case = FIXTURE_CASES["negative_target_post_id_invalid"]
        candidate = _candidate_post(7104, "阿部監督が継投を説明", case["candidate_source_url"])
        candidate_hash = runner._source_url_hash(case["candidate_source_url"])

        publish_index = runner._empty_duplicate_index()
        publish_index["source_hashes"][candidate_hash] = [
            {
                "post_id": case["target_post_id_raw"],
                "title": "阿部監督が勝負手を説明",
                "subtype": "comment",
                "speaker_token": "阿部監督",
                "status": "publish",
                "published_at": FIXED_NOW - timedelta(hours=1),
                "source_url": case["target_source_url"],
                "source_url_hash": candidate_hash,
                "source_url_pairs": [
                    {
                        "source_url": case["target_source_url"],
                        "source_url_hash": candidate_hash,
                    }
                ],
            }
        ]

        result, history_row, integrity_event = self._run_live_case(
            candidate,
            {7104: candidate},
            env={runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1"},
            publish_index_override=publish_index,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_duplicate_integrity_fail")
        self.assertIsNone(result["refused"][0]["duplicate_of_post_id"])
        self.assertEqual(result["refused"][0]["duplicate_reason"], "duplicate_integrity_fail")
        self.assertEqual(history_row["duplicate_reason"], "duplicate_integrity_fail")
        self.assertEqual(history_row["candidate_source_url_hash"], candidate_hash)
        self.assertEqual(history_row["duplicate_target_source_url_hash"], candidate_hash)
        self.assertEqual(history_row["duplicate_target_source_url"], case["target_source_url"])
        self.assertEqual(history_row["duplicate_integrity_error"], "target_post_id_invalid")
        self.assertNotIn("duplicate_target_post_id", history_row)
        self.assertFalse(integrity_event["integrity_ok"])
        self.assertEqual(integrity_event["candidate_source_url_hash"], candidate_hash)
        self.assertEqual(integrity_event["duplicate_target_post_id_raw"], case["target_post_id_raw"])
        self.assertEqual(integrity_event["duplicate_target_source_url_hash"], candidate_hash)
        self.assertEqual(integrity_event["duplicate_target_source_url"], case["target_source_url"])
        self.assertEqual(integrity_event["duplicate_integrity_error"], "target_post_id_invalid")


if __name__ == "__main__":
    unittest.main()
