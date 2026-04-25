import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.speech_seed_intake import (
    ROUTE_COMMENT_CANDIDATE,
    ROUTE_DEFERRED_PICKUP,
    ROUTE_DUPLICATE_LIKE,
    ROUTE_REJECT,
    dump_speech_seed_report,
    evaluate_speech_seed,
)
from src.tools import run_speech_seed_intake_dry_run as dry_run


class SpeechSeedIntakeTests(unittest.TestCase):
    def _seed(self, **overrides):
        payload = {
            "source_url": "https://hochi.news/articles/2026/04/26-OHT1T51000.html",
            "source_title": "阿部監督、浅野の姿勢を評価「積極性が良かった」",
            "source_kind": "comment_quote",
            "published_at": "2026-04-26T21:10:00+09:00",
            "speaker": "阿部慎之助監督",
            "speaker_role": "監督",
            "scene": "練習後囲み",
            "quote_text": "「積極性が良かった」",
            "surrounding_text": "阿部監督が浅野翔吾の練習での姿勢を評価し、次戦起用にも言及した。",
        }
        payload.update(overrides)
        return payload

    def _rss_index(self, *titles):
        return [{"title": title} for title in titles]

    def test_green_seed_routes_to_comment_candidate(self):
        decision = evaluate_speech_seed(
            self._seed(
                source_title="阿部監督、浅野の姿勢を評価「積極性が良かった」",
                surrounding_text="阿部監督が浅野翔吾の積極性を評価し、次戦への期待を口にした。",
            ),
            self._rss_index("戸郷翔征がブルペン入り", "坂本勇人が屋外で調整"),
        )

        self.assertEqual(decision.route_hint, ROUTE_COMMENT_CANDIDATE)
        self.assertEqual(decision.source_kind, "comment_quote")
        self.assertFalse(decision.postgame_summary_like)
        self.assertLess(decision.news_overlap_score, 0.48)
        self.assertTrue(decision.candidate_key.startswith("speech:https://hochi.news/articles/2026/04/26-OHT1T51000.html"))

    def test_strong_rss_overlap_routes_to_duplicate_like(self):
        title = "阿部監督、浅野の姿勢を評価「積極性が良かった」"
        decision = evaluate_speech_seed(
            self._seed(source_title=title),
            self._rss_index(title, "巨人が阪神に勝利"),
        )

        self.assertEqual(decision.route_hint, ROUTE_DUPLICATE_LIKE)
        self.assertGreaterEqual(decision.news_overlap_score, 0.72)
        self.assertIn("news_overlap_high", decision.reasons)

    def test_postgame_summary_seed_routes_to_deferred_pickup(self):
        decision = evaluate_speech_seed(
            self._seed(
                source_title="阿部監督、巨人3-2勝利後に試合を総括",
                scene="試合後コメント",
                quote_text="「チームとして勝ててよかった」",
                surrounding_text="巨人が阪神に3-2で勝利した一戦を阿部監督が振り返った。",
            ),
            self._rss_index("巨人が阪神に3-2で勝利 阿部監督が試合を総括"),
        )

        self.assertEqual(decision.route_hint, ROUTE_DEFERRED_PICKUP)
        self.assertTrue(decision.postgame_summary_like)
        self.assertIn("postgame_summary_like", decision.reasons)

    def test_multiple_speaker_seed_is_rejected(self):
        decision = evaluate_speech_seed(
            self._seed(
                speaker="阿部慎之助監督／岡本和真",
                quote_text="「積極性が良かった」",
            ),
            self._rss_index("別記事"),
        )

        self.assertEqual(decision.route_hint, ROUTE_REJECT)
        self.assertIn("multiple_speakers", decision.reasons)

    def test_low_trust_source_kind_never_becomes_comment_candidate(self):
        decision = evaluate_speech_seed(
            self._seed(
                source_url="https://x.com/fan_account/status/1234567890",
                source_kind="fan_reaction",
                source_title="ファンが阿部監督コメントに反応",
            ),
            self._rss_index("別記事"),
        )

        self.assertEqual(decision.route_hint, ROUTE_REJECT)
        self.assertIn("source_kind_low_trust", decision.reasons)
        self.assertTrue(decision.trust_hint.startswith("low_trust:"))

    def test_dump_report_supports_json_and_human(self):
        decision = evaluate_speech_seed(self._seed(), self._rss_index("別記事"))

        json_payload = json.loads(dump_speech_seed_report([decision], fmt="json"))
        human_payload = dump_speech_seed_report([decision], fmt="human")

        self.assertEqual(json_payload["items"], 1)
        self.assertEqual(json_payload["results"][0]["route_hint"], ROUTE_COMMENT_CANDIDATE)
        self.assertIn("Speech Seed Intake Dry Run", human_payload)
        self.assertIn("route_hint: comment_candidate", human_payload)


class RunSpeechSeedIntakeDryRunTests(unittest.TestCase):
    def _write_jsonl(self, path: Path, rows) -> None:
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "speech.jsonl"
            rss_path = Path(tmpdir) / "rss.jsonl"
            self._write_jsonl(
                input_path,
                [
                    {
                        "source_url": "https://hochi.news/articles/2026/04/26-OHT1T51000.html",
                        "source_title": "阿部監督、浅野の姿勢を評価「積極性が良かった」",
                        "source_kind": "comment_quote",
                        "published_at": "2026-04-26T21:10:00+09:00",
                        "speaker": "阿部慎之助監督",
                        "speaker_role": "監督",
                        "scene": "練習後囲み",
                        "quote_text": "「積極性が良かった」",
                        "surrounding_text": "阿部監督が浅野翔吾の練習での姿勢を評価し、次戦起用にも言及した。",
                    }
                ],
            )
            self._write_jsonl(rss_path, [{"title": "戸郷翔征がブルペン入り"}])

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--input", str(input_path), "--rss-index", str(rss_path), "--format", "json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["items"], 1)
        self.assertEqual(payload["results"][0]["route_hint"], ROUTE_COMMENT_CANDIDATE)

    def test_cli_human_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "speech.jsonl"
            rss_path = Path(tmpdir) / "rss.jsonl"
            self._write_jsonl(
                input_path,
                [
                    {
                        "source_url": "https://x.com/fan_account/status/1234567890",
                        "source_title": "ファンが阿部監督コメントに反応",
                        "source_kind": "fan_reaction",
                        "published_at": "2026-04-26T21:10:00+09:00",
                        "speaker": "阿部慎之助監督",
                        "speaker_role": "監督",
                        "scene": "練習後囲み",
                        "quote_text": "「積極性が良かった」",
                        "surrounding_text": "SNSで反応が広がった。",
                    }
                ],
            )
            self._write_jsonl(rss_path, [{"title": "別記事"}])

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--input", str(input_path), "--rss-index", str(rss_path), "--format", "human"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("Speech Seed Intake Dry Run", output)
        self.assertIn("route_hint: reject", output)
        self.assertIn("reasons: source_kind_low_trust", output)


if __name__ == "__main__":
    unittest.main()
