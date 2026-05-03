import json
import logging
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src import body_contract_fail_ledger as ledger
from src import rss_fetcher


SOURCE_URL = "https://example.com/lineup"
SOURCE_TITLE = "【巨人】スタメン発表 1番丸 先発戸郷"
GENERATED_TITLE = "巨人スタメン発表 1番丸 先発戸郷"
SOURCE_SUMMARY = "5月3日 18:00 東京ドーム 阪神戦。巨人がスタメンを発表した。"
BODY_EXCERPT = "【試合概要】\n5月3日 阪神戦のスタメンです。"


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


class RssFetcherBodyContractFailLedgerTests(unittest.TestCase):
    def _validation_result(self, *, action: str, **overrides):
        payload = {
            "ok": False,
            "action": action,
            "fail_axes": ["first_block_mismatch"],
            "expected_first_block": "【試合概要】",
            "actual_first_block": "【注目ポイント】",
            "missing_required_blocks": [],
            "actual_block_order": ["【注目ポイント】"],
            "has_source_block": True,
            "stop_reason": "first_block_mismatch",
        }
        payload.update(overrides)
        return payload

    def _run_main_once(
        self,
        *,
        validation_result: dict[str, object],
        env: dict[str, str],
        patch_record: bool = False,
        record_side_effect=None,
    ) -> tuple[list[dict[str, object]], object | None]:
        entry = {"title": SOURCE_TITLE, "summary": SOURCE_SUMMARY, "link": SOURCE_URL}
        args = Namespace(dry_run=False, draft_only=False, limit=10, article_ai_mode=None)

        with tempfile.TemporaryDirectory() as tmpdir, ExitStack() as stack:
            tmpdir_path = Path(tmpdir)
            sources_file = tmpdir_path / "rss_sources.json"
            keywords_file = tmpdir_path / "keywords.json"
            history_path = tmpdir_path / "body_contract_fail_history.jsonl"

            sources_file.write_text(
                json.dumps(
                    [
                        {
                            "name": "テストソース",
                            "url": "https://feed.example.com/rss.xml",
                            "type": "news",
                            "role": ["article_source"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            keywords_file.write_text(
                json.dumps({"試合速報": ["巨人"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            active_env = {
                ledger.BODY_CONTRACT_FAIL_LEDGER_PATH_ENV: str(history_path),
            }
            active_env.update(env)

            stack.enter_context(patch.dict("os.environ", active_env, clear=True))
            stack.enter_context(patch.object(rss_fetcher, "RSS_SOURCES_FILE", sources_file))
            stack.enter_context(patch.object(rss_fetcher, "KEYWORDS_FILE", keywords_file))
            stack.enter_context(patch.object(rss_fetcher, "WPClient", return_value=SimpleNamespace()))
            stack.enter_context(patch.object(rss_fetcher, "check_giants_game_today", return_value=(False, "", "")))
            stack.enter_context(patch.object(rss_fetcher, "load_history", return_value={}))
            stack.enter_context(patch.object(rss_fetcher.feedparser, "parse", return_value=SimpleNamespace(entries=[entry])))
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_entry_published_datetime",
                    return_value=datetime(2026, 5, 3, 12, 0, 0),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_entry_day_key", return_value="2026-05-03"))
            stack.enter_context(
                patch.object(rss_fetcher, "_aggregate_lineup_candidates", side_effect=lambda items: items)
            )
            stack.enter_context(
                patch.object(rss_fetcher, "_prioritize_prepared_entries_for_creation", side_effect=lambda items: items)
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_annotate_duplicate_guard_contexts",
                    side_effect=lambda items: [dict(item, duplicate_guard_context={}) for item in items],
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_should_skip_stale_postgame_entry", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_should_skip_stale_player_status_entry", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_is_promotional_video_entry", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_detect_article_subtype", return_value="lineup"))
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_source_fact_block_metrics",
                    return_value=("x" * 200, 200),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_is_thin_source_fact_block", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_resolve_article_generation_category", return_value="試合速報"))
            stack.enter_context(patch.object(rss_fetcher, "evaluate_media_quote_selection", return_value={"quotes": []}))
            stack.enter_context(patch.object(rss_fetcher, "fetch_article_images", return_value=[]))
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_filter_image_candidates",
                    side_effect=lambda images, *_args, **_kwargs: images,
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_refetch_article_images_if_empty",
                    side_effect=lambda images, *_args, **_kwargs: images,
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_ensure_story_featured_images",
                    side_effect=lambda images, *_args, **_kwargs: images,
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_rewrite_display_title_with_guard",
                    return_value=(GENERATED_TITLE, "body_contract_test"),
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_apply_title_player_name_backfill",
                    return_value=(GENERATED_TITLE, SOURCE_TITLE),
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_maybe_apply_weak_title_rescue",
                    return_value=(GENERATED_TITLE, None),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_maybe_route_weak_generated_title_review", return_value=None))
            stack.enter_context(patch.object(rss_fetcher, "_maybe_route_weak_subject_title_review", return_value=None))
            stack.enter_context(patch.object(rss_fetcher, "_log_title_template_selected"))
            stack.enter_context(patch.object(rss_fetcher, "build_news_block", return_value=("<p>body</p>", BODY_EXCERPT)))
            stack.enter_context(patch.object(rss_fetcher, "_validate_body_candidate", return_value=validation_result))
            stack.enter_context(patch.object(rss_fetcher, "_evaluate_post_gen_validate", return_value={"ok": True}))
            stack.enter_context(patch.object(ledger, "_default_gcs_client", return_value=None))

            record_mock = None
            if patch_record:
                record_mock = stack.enter_context(
                    patch.object(rss_fetcher, "record_body_contract_fail", side_effect=record_side_effect)
                )

            rss_fetcher._main(args, logging.getLogger("rss_fetcher"))

            if history_path.exists():
                rows = [
                    json.loads(line)
                    for line in history_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            else:
                rows = []

        return rows, record_mock

    def test_flag_off_keeps_hook_silent(self):
        rows, record_mock = self._run_main_once(
            validation_result=self._validation_result(action="fail"),
            env={},
            patch_record=True,
        )

        self.assertEqual(rows, [])
        self.assertIsNotNone(record_mock)
        record_mock.assert_not_called()

    def test_flag_on_appends_fail_row(self):
        rows, _record_mock = self._run_main_once(
            validation_result=self._validation_result(action="fail"),
            env={ledger.ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV: "1"},
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["record_type"], "body_contract_fail")
        self.assertEqual(row["skip_layer"], "body_contract")
        self.assertEqual(row["terminal_state"], "skip_accounted")
        self.assertEqual(row["validation_action"], "fail")
        self.assertEqual(row["source_url"], SOURCE_URL)
        self.assertEqual(row["source_title"], SOURCE_TITLE)
        self.assertEqual(row["generated_title"], GENERATED_TITLE)
        self.assertEqual(row["category"], "試合速報")
        self.assertEqual(row["article_subtype"], "lineup")
        self.assertEqual(row["fail_axes"], ["first_block_mismatch"])
        self.assertEqual(row["suppressed_mail_count"], 0)
        self.assertEqual(len(str(row["source_url_hash"])), 16)
        self.assertTrue(str(row["body_excerpt_hash"]).startswith("sha256:"))
        self.assertIn("ts", row)

    def test_flag_on_appends_reroll_row(self):
        rows, _record_mock = self._run_main_once(
            validation_result=self._validation_result(
                action="reroll",
                fail_axes=["missing_required_block"],
                missing_required_blocks=["【スタメン一覧】"],
                actual_block_order=["【試合のポイント】"],
                stop_reason="",
            ),
            env={ledger.ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV: "1"},
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["validation_action"], "reroll")
        self.assertEqual(row["fail_axes"], ["missing_required_block"])
        self.assertEqual(row["missing_required_blocks"], ["【スタメン一覧】"])
        self.assertEqual(row["suppressed_mail_count"], 0)

    def test_gcs_append_failure_warns_only(self):
        def _record_with_failing_gcs(**kwargs):
            return ledger.record_body_contract_fail(gcs_client=_Client(), **kwargs)

        with self.assertLogs("rss_fetcher", level="WARNING") as captured:
            rows, _record_mock = self._run_main_once(
                validation_result=self._validation_result(action="fail"),
                env={ledger.ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV: "1"},
                patch_record=True,
                record_side_effect=_record_with_failing_gcs,
            )

        self.assertEqual(len(rows), 1)
        self.assertTrue(
            any("body_contract_fail_history_gcs_append_failed" in line for line in captured.output)
        )


if __name__ == "__main__":
    unittest.main()
