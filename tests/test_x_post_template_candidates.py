import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.tools.run_x_post_template_candidates_dry_run import main as cli_main
from src.x_published_poster import PublishedArticle
from src.x_post_template_candidates import (
    MAX_X_POST_LENGTH,
    REFUSE_REASON_DUPLICATE_POST_ID_HISTORY,
    REFUSE_REASON_REWRITE_TOO_CLOSE,
    TEMPLATE_TYPE_FAN_REACTION_HOOK,
    TEMPLATE_TYPE_PROGRAM_MEMO,
    TEMPLATE_TYPE_QUOTE_CLIP,
    TEMPLATE_TYPE_SMALL_NOTE,
    generate_template_candidates,
    load_template_candidate_history,
    record_template_candidate_history,
)


NOW = datetime(2026, 4, 26, 9, 0, tzinfo=timezone.utc)


class XPostTemplateCandidatesTests(unittest.TestCase):
    def _postgame_article(self, **overrides) -> PublishedArticle:
        article = PublishedArticle(
            article_id=701,
            title='阿部監督「最後までよく粘った」 巨人が延長12回サヨナラで連敗ストップ',
            excerpt=(
                "巨人が延長12回サヨナラで連敗を止めた。"
                "救援陣が踏ん張り、終盤の粘りが勝利につながった試合だった。"
            ),
            body_first_paragraph=(
                "<p>巨人が延長12回サヨナラで連敗を止めた。"
                "救援陣が踏ん張り、終盤の粘りが勝利につながった試合だった。"
                "東京ドームの空気が最後に一気に動いた。</p>"
            ),
            canonical_url="https://yoshilover.com/archives/701/",
            published_at=(NOW - timedelta(minutes=20)).isoformat(),
            post_status="publish",
        )
        return PublishedArticle(**{**article.__dict__, **overrides})

    def _program_article(self, **overrides) -> PublishedArticle:
        article = PublishedArticle(
            article_id=880,
            title="巨人戦中継はきょう18時30分から G+ と日テレジータスで放送",
            excerpt=(
                "きょうの巨人戦は18時30分開始。"
                "G+ と日テレジータスで中継し、解説と実況の出演情報も整理した。"
            ),
            body_first_paragraph=(
                "<p>きょうの巨人戦は18時30分開始。"
                "G+ と日テレジータスで中継し、解説と実況の出演情報も整理した。</p>"
            ),
            canonical_url="https://yoshilover.com/archives/880/",
            published_at=(NOW - timedelta(hours=1)).isoformat(),
            post_status="publish",
        )
        return PublishedArticle(**{**article.__dict__, **overrides})

    def _thin_article(self, **overrides) -> PublishedArticle:
        article = PublishedArticle(
            article_id=990,
            title="巨人 OB 会の開催概要",
            excerpt="巨人 OB 会の開催概要。",
            body_first_paragraph="<p>巨人 OB 会の開催概要。</p>",
            canonical_url="https://yoshilover.com/archives/990/",
            published_at=(NOW - timedelta(hours=2)).isoformat(),
            post_status="publish",
        )
        return PublishedArticle(**{**article.__dict__, **overrides})

    def test_generate_candidates_returns_multiple_relevant_template_types(self):
        batch = generate_template_candidates(self._postgame_article(), now=NOW)

        accepted_types = [candidate.template_type for candidate in batch.accepted]

        self.assertEqual(
            accepted_types,
            [
                TEMPLATE_TYPE_QUOTE_CLIP,
                TEMPLATE_TYPE_FAN_REACTION_HOOK,
                TEMPLATE_TYPE_SMALL_NOTE,
            ],
        )
        self.assertEqual(batch.refused, ())
        for candidate in batch.accepted:
            self.assertIn(candidate.article_url, candidate.text)
            self.assertLessEqual(len(candidate.text), MAX_X_POST_LENGTH)
            self.assertEqual(candidate.generated_at, NOW.isoformat())

    def test_program_article_only_emits_program_memo_and_small_note(self):
        batch = generate_template_candidates(self._program_article(), now=NOW)

        accepted_types = [candidate.template_type for candidate in batch.accepted]

        self.assertEqual(accepted_types, [TEMPLATE_TYPE_PROGRAM_MEMO, TEMPLATE_TYPE_SMALL_NOTE])
        self.assertNotIn(TEMPLATE_TYPE_FAN_REACTION_HOOK, accepted_types)
        self.assertNotIn(TEMPLATE_TYPE_QUOTE_CLIP, accepted_types)

    def test_rewrite_heavy_candidate_is_refused(self):
        batch = generate_template_candidates(self._thin_article(), now=NOW)

        self.assertEqual(batch.accepted, ())
        self.assertEqual(len(batch.refused), 1)
        self.assertEqual(batch.refused[0].template_type, TEMPLATE_TYPE_SMALL_NOTE)
        self.assertEqual(batch.refused[0].refuse_reason, REFUSE_REASON_REWRITE_TOO_CLOSE)

    def test_duplicate_history_refuses_relevant_candidates(self):
        article = self._postgame_article()
        history = {str(article.article_id): (NOW - timedelta(minutes=5)).isoformat()}

        batch = generate_template_candidates(article, post_history=history, now=NOW)

        self.assertEqual(batch.accepted, ())
        self.assertEqual(
            [candidate.template_type for candidate in batch.refused],
            [
                TEMPLATE_TYPE_QUOTE_CLIP,
                TEMPLATE_TYPE_FAN_REACTION_HOOK,
                TEMPLATE_TYPE_SMALL_NOTE,
            ],
        )
        self.assertTrue(
            all(candidate.refuse_reason == REFUSE_REASON_DUPLICATE_POST_ID_HISTORY for candidate in batch.refused)
        )

    def test_history_helpers_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "x_post_template_history.json"
            history = load_template_candidate_history(str(history_path))

            record_template_candidate_history(str(history_path), history, 1234, posted_at=NOW)
            loaded = load_template_candidate_history(str(history_path))

            self.assertEqual(loaded["1234"], NOW.isoformat())


class XPostTemplateCandidatesCliTests(unittest.TestCase):
    def _fixture_payload(self) -> dict:
        article = PublishedArticle(
            article_id=777,
            title='阿部監督「切り替えていく」 巨人が逆転勝ち',
            excerpt="巨人が逆転勝ちした。終盤に流れを引き寄せ、投打が最後にかみ合った。",
            body_first_paragraph="<p>巨人が逆転勝ちした。終盤に流れを引き寄せ、投打が最後にかみ合った。</p>",
            canonical_url="https://yoshilover.com/archives/777/",
            published_at=(NOW - timedelta(minutes=30)).isoformat(),
            post_status="publish",
        )
        return {"article": article.__dict__}

    def test_cli_fixture_outputs_batch_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "article.json"
            fixture_path.write_text(json.dumps(self._fixture_payload(), ensure_ascii=False), encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["--fixture", str(fixture_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["post_id"], 777)
        self.assertGreaterEqual(len(payload["accepted"]), 2)
        self.assertTrue(all(entry["article_url"] == "https://yoshilover.com/archives/777/" for entry in payload["accepted"]))

    def test_cli_post_id_reads_wp_post_without_x_credentials(self):
        wp_payload = {
            "id": 456,
            "title": {"rendered": "巨人戦中継はきょう18時30分から G+ で放送"},
            "excerpt": {"rendered": "18時30分開始。G+ で中継し、出演情報も整理した。"},
            "content": {"rendered": "<p>18時30分開始。G+ で中継し、出演情報も整理した。</p>"},
            "link": "https://yoshilover.com/archives/456/",
            "date": (NOW - timedelta(hours=1)).isoformat(),
            "status": "publish",
        }

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("src.tools.run_x_post_template_candidates_dry_run.WPClient") as wp_client_mock:
            wp_client_mock.return_value.get_post.return_value = wp_payload
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["--post-id", "456"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["post_id"], 456)
        self.assertEqual(payload["accepted"][0]["template_type"], TEMPLATE_TYPE_PROGRAM_MEMO)


if __name__ == "__main__":
    unittest.main()
