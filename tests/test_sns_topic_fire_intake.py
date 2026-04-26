import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.sns_topic_fire_intake import (
    ROUTE_REJECT,
    ROUTE_SOURCE_RECHECK,
    dump_sns_topic_fire_report,
    evaluate_sns_topic_fire_batch,
)
from src.tools import run_sns_topic_fire_intake as dry_run


class SNSTopicFireIntakeTests(unittest.TestCase):
    def _signals(self, *texts, **extra):
        rows = []
        for index, text in enumerate(texts, start=1):
            row = {
                "summary": text,
                "link": f"https://x.com/example/status/{index}",
            }
            row.update(extra)
            rows.append(row)
        return rows

    def test_category_classification_covers_all_mvp_buckets(self):
        fixtures = {
            "player": self._signals(
                "坂本勇人のフォーム修正が気になる。状態が上向けば守備も安定しそう。",
                "坂本勇人のフォーム改善で状態が戻るか見たい。",
                "坂本勇人のフォームと守備のバランスが良くなってきた気がする。",
            ),
            "manager_strategy": self._signals(
                "阿部監督の起用方針、若手競争を続ける狙いが見える。",
                "阿部監督の起用方針は競争重視で、我慢の使い方も気になる。",
                "阿部監督の起用方針と競争のさせ方に注目したい。",
            ),
            "bullpen": self._signals(
                "大勢と中川皓太の勝ちパ継投、8回9回の使い分けが気になる。",
                "大勢と中川皓太のブルペン継投、勝ちパの並びをどうするか見たい。",
                "大勢と中川皓太の終盤継投、勝ちパの順番が話題になっている。",
            ),
            "lineup": self._signals(
                "坂本勇人を3番に置く打順とスタメン、岡本和真との並びが見たい。",
                "坂本勇人の打順とスタメン、主力の並び替えが気になる。",
                "坂本勇人を含むスタメンと打順、岡本和真の前後をどう組むか見たい。",
            ),
            "farm": self._signals(
                "浅野翔吾が二軍でマルチヒット。昇格候補として見たい。",
                "浅野翔吾の二軍での内容が良く、若手の昇格候補として気になる。",
                "浅野翔吾がファームで結果を出していて、二軍からの昇格候補に見える。",
            ),
            "injury_return": self._signals(
                "戸郷翔征の復帰プラン、リハビリ後の復帰時期が気になる。",
                "戸郷翔征の復帰時期とリハビリの進み具合が話題になっている。",
                "戸郷翔征の復帰プラン、コンディションが戻ればいつ上がるか見たい。",
            ),
            "transaction": self._signals(
                "浅野翔吾の登録あるか。公示での一軍合流が気になる。",
                "浅野翔吾の公示と登録の動き、昇格候補として見たい。",
                "浅野翔吾の一軍合流と公示、登録があるか注目したい。",
            ),
            "acquisition_trade": self._signals(
                "捕手補強どうする。甲斐拓也FA調査の行方が気になる。",
                "甲斐拓也のFA調査と捕手補強、補強候補として話題になっている。",
                "甲斐拓也の動向と補強方針、捕手補強をどう進めるか見たい。",
            ),
        }

        for expected_category, signals in fixtures.items():
            with self.subTest(category=expected_category):
                candidates = evaluate_sns_topic_fire_batch(signals, [])
                self.assertEqual(len(candidates), 1)
                candidate = candidates[0]
                self.assertEqual(candidate.category, expected_category)
                self.assertEqual(candidate.source_tier, "reaction")
                self.assertTrue(candidate.fact_recheck_required)
                self.assertEqual(candidate.route_hint, ROUTE_SOURCE_RECHECK)
                self.assertGreaterEqual(candidate.signal_count, 3)

    def test_unsafe_clusters_are_rejected(self):
        slur_candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "阿部監督は無能だから消えろと荒れている。",
                "阿部監督は無能だという罵倒ばかりで話にならない。",
                "阿部監督へ無能だの消えろだのという投稿ばかりだ。",
            ),
            [],
        )
        self.assertEqual(slur_candidates[0].route_hint, ROUTE_REJECT)
        self.assertIn("slur_or_harassment", slur_candidates[0].unsafe_flags)

        sensitive_candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "戸郷翔征が復帰確定らしい、すぐ上がると騒がれている。",
                "戸郷翔征が復帰したらしいという未確認の話が出回っている。",
                "戸郷翔征の復帰確定らしいという噂だけが先行している。",
            ),
            [],
        )
        self.assertEqual(sensitive_candidates[0].route_hint, ROUTE_REJECT)
        self.assertIn("sns_only_sensitive_assertion", sensitive_candidates[0].unsafe_flags)

        overlap_candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "坂本勇人のスタメンと打順が気になる。",
                "坂本勇人のスタメン、打順の並びが話題だ。",
                "坂本勇人の打順とスタメンをどう組むか見たい。",
            ),
            [{"title": "坂本勇人 スタメン 打順 主力打順"}],
        )
        self.assertEqual(overlap_candidates[0].route_hint, ROUTE_REJECT)
        self.assertIn("recent_news_overlap", overlap_candidates[0].unsafe_flags)

    def test_private_person_general_citizen_rejected(self):
        candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "一般人の名前を見つけたという話が広がっていて危ない。",
                "一般人まで特定されたという流れは記事化候補にできない。",
                "一般人の話題で特定されたと騒ぐのは避けるべきだ。",
                category="player",
            ),
            [],
        )

        self.assertEqual(candidates[0].route_hint, ROUTE_REJECT)
        self.assertIn("private_family_or_rumor", candidates[0].unsafe_flags)

    def test_private_person_neighbor_rejected(self):
        candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "近所の人まで特定されたという話は扱えない。",
                "近所の方の名前を見つけたという投稿が広がっている。",
                "近所の第三者個人が話題の中心になるのは危ない。",
                category="player",
            ),
            [],
        )

        self.assertEqual(candidates[0].route_hint, ROUTE_REJECT)
        self.assertIn("private_family_or_rumor", candidates[0].unsafe_flags)

    def test_private_person_child_rejected(self):
        candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "お子さんのことまで話題にしているのは危ない。",
                "子供さんの情報を特定されたという流れは扱えない。",
                "お子さんの名前を見つけたという投稿は候補から外すべきだ。",
                category="player",
            ),
            [],
        )

        self.assertEqual(candidates[0].route_hint, ROUTE_REJECT)
        self.assertIn("private_family_or_rumor", candidates[0].unsafe_flags)

    def test_private_person_address_school_combo_rejected(self):
        candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "住所と学校まで広がっている話は記事化できない。",
                "住所と学校が特定されたという流れは危ない。",
                "住所も学校も出てくる話題は避けるべきだ。",
                category="player",
            ),
            [],
        )

        self.assertEqual(candidates[0].route_hint, ROUTE_REJECT)
        self.assertIn("private_family_or_rumor", candidates[0].unsafe_flags)

    def test_known_public_figure_not_falsely_rejected(self):
        candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                "スポーツ報知の記者が阿部監督の学校時代も交えて起用方針を報じた。",
                "日刊スポーツの番記者が阿部監督と田中将大の起用方針を伝えている。",
                "スポニチの報道でも阿部監督と田中将大の起用方針が話題だ。",
                category="manager_strategy",
            ),
            [],
        )

        self.assertEqual(candidates[0].route_hint, ROUTE_SOURCE_RECHECK)
        self.assertNotIn("private_family_or_rumor", candidates[0].unsafe_flags)

    def test_report_never_contains_raw_sns_text_or_urls(self):
        unique_phrase = "独自フレーズ生文"
        candidates = evaluate_sns_topic_fire_batch(
            self._signals(
                f"阿部監督の起用方針が気になる。{unique_phrase}",
                f"阿部監督の起用方針と競争が気になる。{unique_phrase}",
                f"阿部監督の起用方針、若手競争の見方が分かれる。{unique_phrase}",
            ),
            [],
        )

        json_report = dump_sns_topic_fire_report(candidates, fmt="json")
        human_report = dump_sns_topic_fire_report(candidates, fmt="human")

        self.assertNotIn(unique_phrase, json_report)
        self.assertNotIn(unique_phrase, human_report)
        self.assertNotIn("https://x.com", json_report)
        self.assertNotIn("https://x.com", human_report)
        self.assertNotIn("@example", json_report)
        self.assertNotIn("@example", human_report)


class RunSNSTopicFireIntakeTests(unittest.TestCase):
    def test_cli_json_output(self):
        fixture = {
            "signals": [
                {"summary": "阿部監督の起用方針が気になる。固有生文A", "link": "https://x.com/example/status/1"},
                {"summary": "阿部監督の起用方針と競争が気になる。固有生文A", "link": "https://x.com/example/status/2"},
                {"summary": "阿部監督の起用方針、若手競争の見方が分かれる。固有生文A", "link": "https://x.com/example/status/3"},
            ],
            "rss_index": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture_path), "--format", "json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["items"], 1)
        self.assertEqual(payload["results"][0]["route_hint"], ROUTE_SOURCE_RECHECK)
        self.assertNotIn("固有生文A", stdout.getvalue())
        self.assertNotIn("https://x.com", stdout.getvalue())

    def test_cli_human_output(self):
        fixture = {
            "signals": [
                {"summary": "戸郷翔征が復帰確定らしい。固有生文B", "link": "https://x.com/example/status/1"},
                {"summary": "戸郷翔征が復帰したらしいという話だけ先に広がる。固有生文B", "link": "https://x.com/example/status/2"},
                {"summary": "戸郷翔征の復帰確定らしいという噂が先行している。固有生文B", "link": "https://x.com/example/status/3"},
            ],
            "rss_index": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture_path), "--format", "human"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("SNS Topic Fire Intake Dry Run", output)
        self.assertIn("route_hint: reject", output)
        self.assertIn("sns_only_sensitive_assertion", output)
        self.assertNotIn("固有生文B", output)
        self.assertNotIn("https://x.com", output)


if __name__ == "__main__":
    unittest.main()
