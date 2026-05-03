import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import publish_notice_email_sender as sender
from src import publish_notice_scanner as scanner


NOW = datetime(2026, 5, 3, 9, 0, tzinfo=scanner.JST)


class _BridgeResult:
    def __init__(self, *, status: str = "sent", reason: str | None = None) -> None:
        self.status = status
        self.reason = reason


class PublishOnlyMailFilterTests(unittest.TestCase):
    def _request(self, notice_class: str, index: int = 1) -> sender.PublishNoticeRequest:
        kwargs = {
            "post_id": f"{notice_class}:{index}",
            "title": f"{notice_class} title {index}",
            "canonical_url": f"https://example.com/{notice_class}/{index}",
            "subtype": "postgame",
            "publish_time_iso": NOW.isoformat(),
            "summary": "巨人が阪神に3-2で勝利。決勝打と継投が焦点になった。",
            "is_backlog": False,
        }
        if notice_class == "publish":
            kwargs.update(
                notice_kind="publish",
                subject_override=f"【公開済】publish {index} | YOSHILOVER",
            )
        elif notice_class == "real_review":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要確認】real review {index} | YOSHILOVER",
            )
        elif notice_class == "guarded_review":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要review】guarded review {index} | YOSHILOVER",
            )
        elif notice_class == "old_candidate":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要確認(古い候補)】old candidate {index} | YOSHILOVER",
            )
        elif notice_class == "post_gen_validate":
            kwargs.update(
                notice_kind="post_gen_validate",
                subject_override=f"【要review｜post_gen_validate】post gen {index} | YOSHILOVER",
                source_title=f"元記事タイトル {index}",
                generated_title=f"生成タイトル {index}",
                skip_reason="weak_subject_title:related_info_escape",
                skip_reason_label="タイトルが『関連情報』だけで弱いため",
                source_url_hash=f"hash{index:04d}",
                category="試合速報",
                record_type="post_gen_validate",
                skip_layer="post_gen_validate",
                fail_axes=("weak_subject_title:related_info_escape",),
            )
        elif notice_class == "preflight_skip":
            kwargs.update(
                notice_kind="post_gen_validate",
                subject_override=f"【要review｜preflight_skip】preflight {index} | YOSHILOVER",
                source_title=f"元記事タイトル {index}",
                generated_title=f"生成タイトル {index}",
                skip_reason="placeholder_body",
                skip_reason_label="placeholder body のため",
                source_url_hash=f"preflight{index:04d}",
                category="試合速報",
                record_type="preflight_skip",
                skip_layer="preflight",
            )
        elif notice_class == "digest":
            kwargs.update(
                notice_kind="post_gen_validate",
                subject_override=f"【要review｜post_gen_validate digest｜2件】digest {index} | YOSHILOVER",
                source_title="representative_subject: digest representative",
                generated_title="[digest-1] item 1\n[digest-2] item 2",
                skip_reason="post_gen_validate_digest",
                skip_reason_label="直近60分の overflow 2件を digest 化",
                category="試合速報",
                record_type="post_gen_validate_digest",
                skip_layer="post_gen_validate",
                fail_axes=("digest-1", "digest-2"),
            )
        else:
            raise AssertionError(f"unsupported notice_class: {notice_class}")
        return sender.PublishNoticeRequest(**kwargs)

    def _send(
        self,
        request: sender.PublishNoticeRequest,
        *,
        flag_on: bool,
    ) -> tuple[sender.PublishNoticeEmailResult, MagicMock]:
        bridge_send = MagicMock(return_value=_BridgeResult())
        env = {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}
        if flag_on:
            env["ENABLE_PUBLISH_ONLY_MAIL_FILTER"] = "1"
        with patch.dict("os.environ", env, clear=True):
            result = sender.send(
                request,
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
            )
        return result, bridge_send

    def test_scanner_publish_only_helper_matches_subject_prefixes(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1"}, clear=True):
            self.assertTrue(scanner._publish_only_mail_filter_enabled())
            self.assertTrue(scanner._is_publish_only_mail_class(self._request("publish")))
            self.assertFalse(scanner._is_publish_only_mail_class(self._request("post_gen_validate")))
            self.assertFalse(scanner._is_publish_only_mail_class(self._request("preflight_skip")))
            self.assertFalse(scanner._is_publish_only_mail_class(self._request("real_review")))
            self.assertFalse(scanner._is_publish_only_mail_class(self._request("old_candidate")))
            self.assertFalse(scanner._is_publish_only_mail_class(self._request("guarded_review")))
            self.assertFalse(scanner._is_publish_only_mail_class(self._request("digest")))

    def test_flag_off_keeps_all_notice_classes_emittable(self):
        for notice_class in (
            "publish",
            "post_gen_validate",
            "preflight_skip",
            "real_review",
            "old_candidate",
            "guarded_review",
            "digest",
        ):
            with self.subTest(notice_class=notice_class):
                result, bridge_send = self._send(self._request(notice_class), flag_on=False)

                self.assertEqual(result.status, "sent")
                self.assertIsNone(result.reason)
                self.assertEqual(bridge_send.call_count, 1)

    def test_flag_on_publish_notice_is_sent(self):
        result, bridge_send = self._send(self._request("publish"), flag_on=True)

        self.assertEqual(result.status, "sent")
        self.assertIsNone(result.reason)
        self.assertEqual(bridge_send.call_count, 1)

    def test_flag_on_post_gen_validate_is_suppressed(self):
        result, bridge_send = self._send(self._request("post_gen_validate"), flag_on=True)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
        self.assertEqual(bridge_send.call_count, 0)

    def test_flag_on_preflight_skip_is_suppressed(self):
        result, bridge_send = self._send(self._request("preflight_skip"), flag_on=True)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
        self.assertEqual(bridge_send.call_count, 0)

    def test_flag_on_real_review_is_suppressed(self):
        result, bridge_send = self._send(self._request("real_review"), flag_on=True)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
        self.assertEqual(bridge_send.call_count, 0)

    def test_flag_on_old_candidate_is_suppressed(self):
        result, bridge_send = self._send(self._request("old_candidate"), flag_on=True)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
        self.assertEqual(bridge_send.call_count, 0)

    def test_flag_on_guarded_review_is_suppressed(self):
        result, bridge_send = self._send(self._request("guarded_review"), flag_on=True)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
        self.assertEqual(bridge_send.call_count, 0)

    def test_flag_on_digest_is_suppressed(self):
        result, bridge_send = self._send(self._request("digest"), flag_on=True)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
        self.assertEqual(bridge_send.call_count, 0)

    def test_flag_on_keeps_post_gen_validate_ledger_and_queue_rows(self):
        entry = {
            "ts": NOW.isoformat(),
            "source_url": "https://example.com/post-gen-1",
            "source_url_hash": "hash0001",
            "source_title": "元記事タイトル 1",
            "generated_title": "生成タイトル 1",
            "category": "試合速報",
            "article_subtype": "postgame",
            "skip_reason": "weak_subject_title:related_info_escape",
            "fail_axis": ["weak_subject_title:related_info_escape"],
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
            },
            clear=True,
        ):
            root = Path(tmpdir)
            ledger_path = root / "post_gen_validate_history.jsonl"
            cursor_path = root / "post_gen_validate_cursor.txt"
            history_path = root / "publish_notice_history.json"
            queue_path = root / "publish_notice_queue.jsonl"
            ledger_path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            result = scanner.scan_post_gen_validate_history(
                post_gen_validate_history_path=ledger_path,
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                max_per_run=5,
                now=NOW,
            )
            self.assertEqual(len(result.emitted), 1)

            bridge_send = MagicMock(return_value=_BridgeResult())
            mail_result = sender.send(
                result.emitted[0],
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
            )
            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=result.emitted[0].post_id,
                result=mail_result,
                publish_time_iso=result.emitted[0].publish_time_iso,
                recorded_at=NOW,
            )

            ledger_rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            queue_rows = [
                json.loads(line)
                for line in queue_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(ledger_rows), 1)
        self.assertEqual(ledger_rows[0]["skip_reason"], "weak_subject_title:related_info_escape")
        self.assertEqual(queue_rows[0]["status"], "queued")
        self.assertEqual(queue_rows[1]["status"], "suppressed")
        self.assertEqual(queue_rows[1]["reason"], "PUBLISH_ONLY_FILTER")
        self.assertEqual(bridge_send.call_count, 0)


if __name__ == "__main__":
    unittest.main()
