import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import body_contract_fail_ledger as ledger


JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 5, 3, 12, 34, 56, tzinfo=JST)


class _FailingBlob:
    generation = 0

    def exists(self):
        return False

    def upload_from_string(self, *_args, **_kwargs):
        raise RuntimeError("gcs down")


class _Bucket:
    def blob(self, _name):
        return _FailingBlob()


class _Client:
    def bucket(self, _name):
        return _Bucket()


class BodyContractFailLedgerTests(unittest.TestCase):
    def _validation_result(self, **overrides):
        payload = {
            "ok": False,
            "action": "fail",
            "fail_axes": ["farm_result_numeric_fabrication"],
            "expected_first_block": "【二軍結果・活躍の要旨】",
            "actual_first_block": "【ファームのハイライト】",
            "missing_required_blocks": ["【二軍個別選手成績】"],
            "has_source_block": True,
            "stop_reason": "farm_result_numeric_fabrication",
        }
        payload.update(overrides)
        return payload

    def test_flag_off_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "body_contract_fail_history.jsonl"
            with patch.dict(
                "os.environ",
                {ledger.BODY_CONTRACT_FAIL_LEDGER_PATH_ENV: str(history_path)},
                clear=True,
            ):
                result = ledger.record_body_contract_fail(
                    source_url="https://example.com/body-fail",
                    source_title="二軍戦の記事",
                    generated_title="二軍 浅野翔吾が3安打",
                    category="ドラフト・育成",
                    article_subtype="farm_result",
                    validation_result=self._validation_result(),
                    now=NOW,
                )

        self.assertEqual(result.status, "gate_off")
        self.assertIsNone(result.record)
        self.assertFalse(history_path.exists())

    def test_flag_on_appends_required_schema_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "body_contract_fail_history.jsonl"
            with patch.dict(
                "os.environ",
                {
                    ledger.ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV: "1",
                    ledger.BODY_CONTRACT_FAIL_LEDGER_PATH_ENV: str(history_path),
                },
                clear=True,
            ):
                result = ledger.record_body_contract_fail(
                    source_url="https://example.com/body-fail",
                    source_title="二軍戦の記事",
                    generated_title="二軍 浅野翔吾が3安打",
                    category="ドラフト・育成",
                    article_subtype="farm_result",
                    validation_result=self._validation_result(action="reroll"),
                    body_excerpt="浅野翔吾が3安打を放ったが、スコアの裏取りに失敗した。",
                    now=NOW,
                )

            rows = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.status, "recorded")
        self.assertEqual(result.local_path, history_path)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["record_type"], "body_contract_fail")
        self.assertEqual(row["skip_layer"], "body_contract")
        self.assertEqual(row["terminal_state"], "skip_accounted")
        self.assertEqual(row["validation_action"], "reroll")
        self.assertEqual(row["source_url"], "https://example.com/body-fail")
        self.assertEqual(row["source_url_hash"], result.record["source_url_hash"])
        self.assertEqual(row["source_title"], "二軍戦の記事")
        self.assertEqual(row["generated_title"], "二軍 浅野翔吾が3安打")
        self.assertEqual(row["category"], "ドラフト・育成")
        self.assertEqual(row["article_subtype"], "farm_result")
        self.assertEqual(row["fail_axes"], ["farm_result_numeric_fabrication"])
        self.assertEqual(row["expected_first_block"], "【二軍結果・活躍の要旨】")
        self.assertEqual(row["actual_first_block"], "【ファームのハイライト】")
        self.assertEqual(row["missing_required_blocks"], ["【二軍個別選手成績】"])
        self.assertTrue(row["has_source_block"])
        self.assertEqual(row["stop_reason"], "farm_result_numeric_fabrication")
        self.assertTrue(str(row["body_excerpt_hash"]).startswith("sha256:"))
        self.assertEqual(row["suppressed_mail_count"], 0)

    def test_gcs_append_failure_warns_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "body_contract_fail_history.jsonl"
            logger = logging.getLogger("test_body_contract_fail_ledger")

            with patch.dict(
                "os.environ",
                {
                    ledger.ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV: "1",
                    ledger.BODY_CONTRACT_FAIL_LEDGER_PATH_ENV: str(history_path),
                },
                clear=True,
            ), self.assertLogs("test_body_contract_fail_ledger", level="WARNING") as captured:
                result = ledger.record_body_contract_fail(
                    source_url="https://example.com/body-fail",
                    source_title="二軍戦の記事",
                    generated_title="二軍 浅野翔吾が3安打",
                    category="ドラフト・育成",
                    article_subtype="farm_result",
                    validation_result=self._validation_result(),
                    logger=logger,
                    gcs_client=_Client(),
                    now=NOW,
                )

            rows = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result.status, "recorded")
        self.assertEqual(len(rows), 1)
        self.assertIn("body_contract_fail_history_gcs_append_failed", captured.output[0])


if __name__ == "__main__":
    unittest.main()
