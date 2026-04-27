import unittest
from datetime import datetime
from unittest import mock

from src import guarded_publish_evaluator as evaluator_module
from src.guarded_publish_evaluator import evaluate_raw_posts, render_human_report, scan_wp_drafts


FIXED_NOW = datetime.fromisoformat("2026-04-25T21:00:00+09:00")
FIRE_TIME_NOW = datetime.fromisoformat("2026-04-26T14:25:00+09:00")
FOLLOWUP_NOW = datetime.fromisoformat("2026-04-27T12:00:00+09:00")


def _post(
    post_id,
    title,
    body_html,
    *,
    featured_media=10,
    modified="2026-04-25T18:00:00",
    date="2026-04-25T17:00:00",
    meta=None,
):
    payload = {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body_html},
        "featured_media": featured_media,
        "modified": modified,
        "date": date,
        "categories": [],
        "tags": [],
    }
    if meta is not None:
        payload["meta"] = meta
    return payload


class GuardedPublishEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.clean_post = _post(
            101,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.repairable_post = _post(
            102,
            "巨人はどう動く？阿部監督の狙いはどこ",
            (
                "<p>巨人が阪神戦へ向けて調整した。スポーツ報知によると、阿部監督が打線の状態を確認した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.heading_and_devlog_post = _post(
            103,
            "巨人が中日に5-1で勝利",
            (
                "<p>巨人が中日に5-1で勝利した。スポーツ報知によると、戸郷が7回1失点で今季3勝目を挙げた。</p>"
                "<p>岡本が先制打を放ち、序盤から主導権を握った。</p>"
                "<p>継投も安定し、終盤まで流れを渡さなかった。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
                "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish_evaluator\n"
                "commit_hash=abc12345\n"
                "changed_files=2\n"
                "tokens used: 10\n"
                "git diff --stat\n"
                "</pre>"
            ),
        )
        self.hard_stop_post = _post(
            104,
            "巨人の主力が重症で入院 手術へ",
            (
                "<p>巨人の主力が重症のため入院し、手術を受ける予定だと報じられた。スポーツ報知によると、球団も経過を説明した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            meta={"article_subtype": "injury"},
        )
        self.hard_stop_plus_repairable_post = _post(
            105,
            "巨人はどう動く？主力が重症で入院",
            (
                "<p>巨人の主力が重症のため入院した。スポーツ報知によると、手術の予定も検討されている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            meta={"article_subtype": "injury"},
        )
        self.site_component_post = _post(
            106,
            "巨人が広島に2-1で勝利",
            (
                "<p>巨人が広島に2-1で勝利した。スポーツ報知によると、赤星が7回1失点と好投した。</p>"
                "<p>序盤から丁寧に試合を運んだ。</p>"
                "<p>【関連記事】</p>"
                "<p>終盤は継投で逃げ切った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.weak_source_post = _post(
            107,
            "巨人がヤクルトに6-2で勝利",
            (
                "<p>巨人がヤクルトに6-2で勝利した。先発投手が試合を作り、打線も終盤に加点した。</p>"
                "<p>参照元: https://example.com/source</p>"
            ),
            featured_media=0,
        )
        self.ranking_post = _post(
            108,
            "巨人の記録メモ",
            (
                "<p>巨人の記録メモを整理した。スポーツ報知によると、打線の積み上げが続いている。</p>"
                "<p>NPB通算 1234</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.lineup_hochi_post = _post(
            109,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本で先発する。</p>"
                "<p>試合開始 23:59</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T51000.html</p>"
            ),
            meta={
                "article_subtype": "lineup",
                "candidate_key": "lineup_notice:20260425-g-t:starting",
                "game_id": "20260425-g-t",
                "_yoshilover_source_url": "https://hochi.news/articles/20260425-OHT1T51000.html",
            },
        )
        self.lineup_other_post = _post(
            110,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポニチによると、1番丸、4番岡本で先発する。</p>"
                "<p>試合開始 23:59</p>"
                "<p>参照元: スポニチ https://www.sponichi.co.jp/baseball/news/2026/04/25/kiji.html</p>"
            ),
            meta={
                "article_subtype": "lineup",
                "candidate_key": "lineup_notice:20260425-g-t:starting",
                "game_id": "20260425-g-t",
                "_yoshilover_source_url": "https://www.sponichi.co.jp/baseball/news/2026/04/25/kiji.html",
            },
        )

    def _evaluate(self, posts):
        return evaluate_raw_posts(posts, window_hours=96, max_pool=100, now=FIXED_NOW)

    def _evaluate_at(self, posts, now):
        return evaluate_raw_posts(posts, window_hours=96, max_pool=100, now=now)

    def _find_entry(self, report, post_id):
        for bucket in ("green", "yellow", "red"):
            for entry in report[bucket]:
                if entry["post_id"] == post_id:
                    return entry
        raise AssertionError(f"post_id={post_id} not found")

    def _make_clean_posts(self, start_post_id, count):
        return [
            _post(
                start_post_id + index,
                f"巨人が試合{start_post_id + index}に勝利",
                (
                    f"<p>巨人が試合{start_post_id + index}に勝利した。スポーツ報知によると、投打の流れを整理できる内容だった。</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source</p>"
                ),
            )
            for index in range(count)
        ]

    def test_clean_post_returns_publishable_true_and_cleanup_required_false(self):
        report = self._evaluate([self.clean_post])

        self.assertEqual(report["summary"]["clean_count"], 1)
        self.assertEqual(report["summary"]["repairable_count"], 0)
        self.assertEqual(report["summary"]["hard_stop_count"], 0)
        entry = report["green"][0]
        self.assertEqual(entry["category"], "clean")
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertEqual(entry["repairable_flags"], [])

    def test_repairable_only_post_returns_publishable_true_and_cleanup_required_true(self):
        report = self._evaluate([self.repairable_post])

        self.assertEqual(report["summary"]["clean_count"], 0)
        self.assertEqual(report["summary"]["repairable_count"], 1)
        self.assertEqual(report["summary"]["hard_stop_count"], 0)
        entry = report["yellow"][0]
        self.assertEqual(entry["category"], "repairable")
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["cleanup_required"])
        self.assertIn("ai_tone_heading_or_lead", entry["repairable_flags"])
        self.assertIn("speculative_title", entry["yellow_reasons"])

    def test_hard_stop_only_post_returns_publishable_false(self):
        report = self._evaluate([self.hard_stop_post])

        self.assertEqual(report["summary"]["clean_count"], 0)
        self.assertEqual(report["summary"]["repairable_count"], 0)
        self.assertEqual(report["summary"]["hard_stop_count"], 1)
        entry = report["red"][0]
        self.assertEqual(entry["category"], "hard_stop")
        self.assertFalse(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn(
            {"flag": "death_or_grave_incident", "category": "hard_stop", "legacy_flag": "injury_death"},
            entry["reasons"],
        )

    def test_hard_stop_plus_repairable_returns_publishable_false(self):
        report = self._evaluate([self.hard_stop_plus_repairable_post])

        self.assertEqual(report["summary"]["hard_stop_count"], 1)
        entry = report["red"][0]
        self.assertFalse(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn("death_or_grave_incident", entry["hard_stop_flags"])
        self.assertIn("ai_tone_heading_or_lead", entry["repairable_flags"])
        self.assertIn("speculative_title", entry["yellow_reasons"])

    def test_63795_roster_movement_publishable_yellow(self):
        post = _post(
            63795,
            "巨人主力が登録抹消 復帰目処を待つ",
            (
                "<p>巨人主力が登録抹消となった。スポーツ報知によると、復帰目処を見極めながら再調整を進める。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63795</p>"
            ),
            meta={"article_subtype": "injury"},
        )

        report = self._evaluate([post])

        entry = report["yellow"][0]
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn("roster_movement_yellow", entry["repairable_flags"])
        self.assertEqual(entry["hard_stop_flags"], [])

    def test_awkward_role_phrasing_rewriteable_case_stays_clean(self):
        post = _post(
            113,
            "巨人が阪神に3-2で勝利 戸郷翔征が7回2失点",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷翔征投手となって7回2失点と好投した。スポーツ報知によると、テンポ良く試合を作った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-role-clean</p>"
            ),
        )

        report = self._evaluate([post])

        entry = report["green"][0]
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertNotIn("awkward_role_phrasing", entry["repairable_flags"])

    def test_awkward_role_phrasing_skip_warning(self):
        post = _post(
            114,
            "阿部慎之助監督「次戦へ向けて準備を進める」",
            (
                "<p>阿部慎之助監督が試合後に総括した。スポーツ報知によると、次戦へ向けた準備を進める。</p>"
                "<p>阿部慎之助監督となって。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-role-yellow</p>"
            ),
        )

        report = self._evaluate([post])

        entry = report["yellow"][0]
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn("awkward_role_phrasing", entry["repairable_flags"])
        self.assertIn("awkward_role_phrasing", entry["yellow_reasons"])
        self.assertIn(
            {
                "flag": "awkward_role_phrasing",
                "category": "repairable",
                "detail": "rewrite_count=0;skip_count=1;samples=阿部慎之助監督となって[sentence_end]",
            },
            entry["reasons"],
        )

    def test_death_keyword_remains_hard_stop(self):
        post = _post(
            112,
            "巨人OBの訃報 球団が死去を発表",
            (
                "<p>巨人OBが死去したと球団が発表した。スポーツ報知によると、追悼のコメントも出された。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-death</p>"
            ),
        )

        report = self._evaluate([post])

        entry = report["red"][0]
        self.assertIn("death_or_grave_incident", entry["hard_stop_flags"])
        self.assertFalse(entry["publishable"])

    def test_grave_incident_remains_hard_stop(self):
        report = self._evaluate([self.hard_stop_post])

        entry = report["red"][0]
        self.assertIn("death_or_grave_incident", entry["hard_stop_flags"])
        self.assertFalse(entry["publishable"])

    def test_source_missing_diagnosis_hard_stop(self):
        post = _post(
            113,
            "巨人主力が骨折と診断 復帰時期は未定",
            "<p>巨人主力が骨折と診断された。復帰時期は未定とだけ記され、出典リンクはない。</p>",
            meta={"article_subtype": "injury"},
        )

        report = self._evaluate([post])

        entry = report["red"][0]
        self.assertIn("death_or_grave_incident", entry["hard_stop_flags"])
        self.assertFalse(entry["publishable"])

    def test_promotion_publishable_yellow(self):
        post = _post(
            114,
            "巨人若手が一軍昇格 チームに合流",
            (
                "<p>巨人若手が一軍昇格し、チームに合流した。日刊スポーツによると、即戦力として起用が検討されている。</p>"
                "<p>参照元: 日刊スポーツ https://example.com/source-promotion</p>"
            ),
            meta={"article_subtype": "notice"},
        )

        report = self._evaluate([post])

        entry = report["yellow"][0]
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn("roster_movement_yellow", entry["repairable_flags"])

    def test_demotion_publishable_yellow(self):
        post = _post(
            115,
            "巨人主力が二軍降格 再調整へ",
            (
                "<p>巨人主力が二軍降格となった。スポニチによると、再調整後の再昇格を目指す方針だ。</p>"
                "<p>参照元: スポニチ https://example.com/source-demotion</p>"
            ),
            meta={"article_subtype": "notice"},
        )

        report = self._evaluate([post])

        entry = report["yellow"][0]
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn("roster_movement_yellow", entry["repairable_flags"])

    def test_summary_includes_hard_stop_repairable_clean_counts(self):
        report = self._evaluate(
            [
                self.clean_post,
                self.repairable_post,
                self.heading_and_devlog_post,
                self.hard_stop_post,
                self.site_component_post,
                self.weak_source_post,
                self.ranking_post,
            ]
        )

        self.assertEqual(report["summary"]["green_count"], 1)
        self.assertEqual(report["summary"]["yellow_count"], 4)
        self.assertEqual(report["summary"]["red_count"], 2)
        self.assertEqual(report["summary"]["clean_count"], 1)
        self.assertEqual(report["summary"]["repairable_count"], 4)
        self.assertEqual(report["summary"]["hard_stop_count"], 2)
        self.assertEqual(report["summary"]["publishable_count"], 5)
        self.assertEqual(report["summary"]["soft_cleanup_count"], 4)

    def test_cleanup_candidate_detects_heading_sentence_h3_and_dev_log_contamination(self):
        report = self._evaluate([self.heading_and_devlog_post])

        self.assertEqual(report["summary"]["cleanup_count"], 1)
        cleanup_entry = report["cleanup_candidates"][0]
        self.assertEqual(cleanup_entry["post_id"], 103)
        self.assertEqual(cleanup_entry["post_judgment"], "repairable")
        self.assertEqual(
            sorted(cleanup_entry["cleanup_types"]),
            ["dev_log_contamination", "heading_sentence_as_h3"],
        )

    def test_heading_sentence_as_h3_stays_repairable_for_breaking_board(self):
        report = self._evaluate([self.heading_and_devlog_post])

        entry = self._find_entry(report, 103)
        self.assertIn("heading_sentence_as_h3", evaluator_module.RELAXED_FOR_BREAKING_BOARD_FLAGS)
        self.assertTrue(entry["publishable"])
        self.assertIn("heading_sentence_as_h3", entry["repairable_flags"])
        self.assertNotIn("heading_sentence_as_h3", entry["hard_stop_flags"])

    def test_subtype_unresolved_stays_repairable_for_breaking_board(self):
        unresolved_post = _post(
            111,
            "ベンチの狙いを整理",
            (
                "<p>巨人ベンチが終盤の狙いを整理した。スポーツ報知によると、阿部監督が起用の意図を説明した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-z</p>"
            ),
            meta={"article_subtype": "other"},
        )

        report = self._evaluate([unresolved_post])

        entry = self._find_entry(report, 111)
        self.assertIn("subtype_unresolved", evaluator_module.RELAXED_FOR_BREAKING_BOARD_FLAGS)
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn("subtype_unresolved", entry["repairable_flags"])
        self.assertNotIn("subtype_unresolved", entry["hard_stop_flags"])
        self.assertEqual(entry["resolved_subtype"], "default")
        self.assertEqual(entry["subtype_resolution_source"], "default_fallback")

    def test_subtype_unresolved_with_body_notice_fallback_publishable(self):
        post = _post(
            115,
            "編成の動きを整理",
            (
                "<p>巨人は公示で浅野翔吾の一軍登録を発表した。スポーツ報知によると、週末の合流も見込まれている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-notice-fallback</p>"
            ),
            meta={"article_subtype": "other"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 115)
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertNotIn("subtype_unresolved", entry["repairable_flags"])
        self.assertEqual(entry["resolved_subtype"], "notice")
        self.assertEqual(entry["subtype_resolution_source"], "body_fallback")

    def test_subtype_unresolved_with_title_lineup_fallback_publishable(self):
        post = _post(
            116,
            "スタメン発表 1番丸 4番岡本",
            (
                "<p>巨人のオーダーが示され、1番丸佳浩、4番岡本和真の並びになった。スポーツ報知によると、上位打線の組み替えが焦点になっている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-lineup-fallback</p>"
            ),
            meta={"article_subtype": "other"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 116)
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertNotIn("subtype_unresolved", entry["repairable_flags"])
        self.assertEqual(entry["resolved_subtype"], "lineup")
        self.assertEqual(entry["subtype_resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_unsupported_named_fact_still_refused(self):
        post = _post(
            117,
            "ベンチの狙いを整理",
            (
                "<p>巨人ベンチの狙いを整理した。スポーツ報知によると、終盤の継投判断が注目された。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-risk-unresolved</p>"
            ),
            meta={"article_subtype": "other", "risk_type": "unsupported_named_fact"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 117)
        self.assertFalse(entry["publishable"])
        self.assertIn("unsupported_named_fact", entry["hard_stop_flags"])
        self.assertIn("subtype_unresolved", entry["repairable_flags"])

    def test_site_component_reasons_keep_legacy_yellow_reason_but_use_repairable_flag(self):
        report = self._evaluate([self.site_component_post])

        entry = report["yellow"][0]
        self.assertIn("site_component_mixed_into_body", entry["repairable_flags"])
        self.assertIn("site_component_mixed_into_body_middle", entry["yellow_reasons"])

    def test_missing_featured_media_and_weak_source_display_are_repairable(self):
        report = self._evaluate([self.weak_source_post])

        entry = report["yellow"][0]
        self.assertIn("missing_featured_media", entry["repairable_flags"])
        self.assertIn("weak_source_display", entry["repairable_flags"])
        self.assertIn("missing_primary_source", entry["yellow_reasons"])

    def test_lineup_duplicate_absorbed_by_hochi_keeps_strict_metadata_but_all_hold(self):
        report = self._evaluate([self.lineup_hochi_post, self.lineup_other_post])

        self.assertEqual(report["summary"]["green_count"], 0)
        self.assertEqual(report["summary"]["red_count"], 2)
        self.assertEqual(report["summary"]["lineup_representative_count"], 1)
        self.assertEqual(report["summary"]["lineup_duplicate_absorbed_count"], 1)
        representative_entry = self._find_entry(report, 109)
        absorbed_entry = self._find_entry(report, 110)
        self.assertIn("lineup_duplicate_excessive", representative_entry["hard_stop_flags"])
        self.assertIn("exact_title_match", representative_entry["duplicate_title_match_types"])
        self.assertIn("lineup_duplicate_excessive", absorbed_entry["hard_stop_flags"])
        self.assertIn("lineup_duplicate_absorbed_by_hochi", absorbed_entry["red_flags"])
        self.assertEqual(absorbed_entry["representative_post_id"], 109)

    def test_lineup_duplicate_3_same_title_all_hard_stop(self):
        posts = [
            _post(
                1501,
                "巨人二軍スタメン 若手をどう並べたか",
                (
                    "<p>巨人のスタメンが発表された。スポーツ報知によると、若手中心の並びになった。</p>"
                    "<p>試合開始 23:59</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-a</p>"
                ),
                meta={"article_subtype": "lineup", "game_id": "farm-a"},
            ),
            _post(
                1502,
                "巨人二軍スタメン 若手をどう並べたか",
                (
                    "<p>巨人のスタメンが発表された。日刊スポーツによると、若手中心の並びになった。</p>"
                    "<p>試合開始 23:59</p>"
                    "<p>参照元: 日刊スポーツ https://example.com/source-b</p>"
                ),
                meta={"article_subtype": "lineup", "game_id": "farm-b"},
            ),
            _post(
                1503,
                "巨人二軍スタメン 若手をどう並べたか",
                (
                    "<p>巨人のスタメンが発表された。スポニチによると、若手中心の並びになった。</p>"
                    "<p>試合開始 23:59</p>"
                    "<p>参照元: スポニチ https://example.com/source-c</p>"
                ),
                meta={"article_subtype": "lineup"},
            ),
        ]

        report = self._evaluate(posts)

        self.assertEqual(report["summary"]["green_count"], 0)
        self.assertEqual(report["summary"]["yellow_count"], 0)
        self.assertEqual(report["summary"]["red_count"], 3)
        for post_id in (1501, 1502, 1503):
            entry = self._find_entry(report, post_id)
            self.assertFalse(entry["publishable"])
            self.assertIn("lineup_duplicate_excessive", entry["hard_stop_flags"])
            self.assertIn("exact_title_match", entry["duplicate_title_match_types"])

    def test_lineup_duplicate_2_normalized_suffix_hard_stop(self):
        posts = [
            _post(
                1511,
                "巨人DeNA戦 Deは何を見せたか-2",
                (
                    "<p>巨人とDeNAの一戦を整理した。スポーツ報知によると、守備面の対応が焦点になった。</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-d</p>"
                ),
                meta={"article_subtype": "comment"},
            ),
            _post(
                1512,
                "巨人DeNA戦 Deは何を見せたか-3",
                (
                    "<p>巨人とDeNAの一戦を整理した。日刊スポーツによると、守備面の対応が焦点になった。</p>"
                    "<p>参照元: 日刊スポーツ https://example.com/source-e</p>"
                ),
                meta={"article_subtype": "comment"},
            ),
        ]

        report = self._evaluate(posts)

        self.assertEqual(report["summary"]["red_count"], 2)
        for post_id in (1511, 1512):
            entry = self._find_entry(report, post_id)
            self.assertIn("lineup_duplicate_excessive", entry["hard_stop_flags"])
            self.assertIn("normalized_suffix_title_match", entry["duplicate_title_match_types"])
            self.assertNotIn("exact_title_match", entry["duplicate_title_match_types"])

    def test_lineup_duplicate_subtype_lineup_token_match(self):
        posts = [
            _post(
                1521,
                "巨人スタメン 横浜スタジアム 8佐々木 3吉川 4岡本 守備配置確認",
                (
                    "<p>巨人のスタメンが発表された。スポーツ報知によると、8佐々木、3吉川、4岡本、先発戸郷で臨む。</p>"
                    "<p>試合開始 23:59</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-f</p>"
                ),
                meta={"article_subtype": "lineup"},
            ),
            _post(
                1522,
                "巨人スタメン 横浜スタジアム 8佐々木 3吉川 4岡本 守備配置注目",
                (
                    "<p>巨人のスタメンが発表された。日刊スポーツによると、8佐々木、3吉川、4岡本の並びが維持された。</p>"
                    "<p>試合開始 23:59</p>"
                    "<p>参照元: 日刊スポーツ https://example.com/source-g</p>"
                ),
                meta={"article_subtype": "lineup"},
            ),
        ]

        report = self._evaluate(posts)

        self.assertEqual(report["summary"]["red_count"], 2)
        for post_id in (1521, 1522):
            entry = self._find_entry(report, post_id)
            self.assertIn("lineup_duplicate_excessive", entry["hard_stop_flags"])
            self.assertIn("lineup_title_token_match", entry["duplicate_title_match_types"])

    def test_unique_title_no_duplicate_flag(self):
        posts = [
            _post(
                1531,
                "巨人が阪神に3-2で勝利",
                (
                    "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-h</p>"
                ),
            ),
            _post(
                1532,
                "阿部監督が打線の状態を確認",
                (
                    "<p>阿部監督が打線の状態を確認した。スポーツ報知によると、フリー打撃の内容を評価した。</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-i</p>"
                ),
                meta={"article_subtype": "comment"},
            ),
        ]

        report = self._evaluate(posts)

        self.assertEqual(report["summary"]["publishable_count"], 2)
        for post_id in (1531, 1532):
            entry = self._find_entry(report, post_id)
            self.assertNotIn("lineup_duplicate_excessive", entry["hard_stop_flags"])
            self.assertNotIn("duplicate_title_match_types", entry)

    def test_duplicate_detection_post_freshness_check(self):
        posts = [
            _post(
                1541,
                "巨人スタメン 横浜スタジアム 8佐々木",
                (
                    "<p>巨人のスタメンが発表された。スポーツ報知によると、8佐々木で先発する。</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-j</p>"
                ),
                date="2026-04-25T14:00:00",
                modified="2026-04-25T20:30:00",
                meta={"article_subtype": "lineup", "game_id": "g-db-c"},
            ),
            _post(
                1542,
                "巨人スタメン 横浜スタジアム 8佐々木",
                (
                    "<p>巨人のスタメンが発表された。日刊スポーツによると、8佐々木で先発する。</p>"
                    "<p>試合開始 23:59</p>"
                    "<p>参照元: 日刊スポーツ https://example.com/source-k</p>"
                ),
                date="2026-04-25T20:00:00",
                modified="2026-04-25T20:30:00",
                meta={"article_subtype": "lineup", "game_id": "g-db-d"},
            ),
        ]

        report = self._evaluate(posts)

        stale_entry = self._find_entry(report, 1541)
        fresh_entry = self._find_entry(report, 1542)
        self.assertIn("lineup_duplicate_excessive", stale_entry["hard_stop_flags"])
        self.assertIn("expired_lineup_or_pregame", stale_entry["repairable_flags"])
        self.assertNotIn("expired_lineup_or_pregame", stale_entry["hard_stop_flags"])
        self.assertEqual(stale_entry["freshness_class"], "expired")
        self.assertIn("lineup_duplicate_excessive", fresh_entry["hard_stop_flags"])
        self.assertNotIn("expired_lineup_or_pregame", fresh_entry["hard_stop_flags"])
        self.assertEqual(fresh_entry["freshness_class"], "fresh")

    def test_stale_lineup_6h_over_is_hard_stop(self):
        stale_lineup = _post(
            201,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本で先発する。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T51000.html</p>"
            ),
            date="2026-04-25T14:00:00",
            modified="2026-04-25T20:30:00",
            meta={"article_subtype": "lineup"},
        )

        report = self._evaluate([stale_lineup])

        entry = self._find_entry(report, 201)
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["cleanup_required"])
        self.assertEqual(entry["freshness_class"], "expired")
        self.assertEqual(entry["content_date"], "2026-04-25")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("expired_lineup_or_pregame", entry["repairable_flags"])
        self.assertIn("threshold=6h", entry["freshness_reason"])

    def test_stale_postgame_24h_over_is_hard_stop(self):
        stale_postgame = _post(
            202,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-24T20:00:00",
            modified="2026-04-25T20:30:00",
            meta={"article_subtype": "postgame"},
        )

        report = self._evaluate([stale_postgame])

        entry = self._find_entry(report, 202)
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["cleanup_required"])
        self.assertEqual(entry["freshness_class"], "expired")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("expired_game_context", entry["repairable_flags"])

    def test_stale_default_24h_over_is_hard_stop(self):
        stale_default = _post(
            203,
            "巨人トピック整理",
            (
                "<p>巨人の周辺情報を整理した。スポーツ報知によると、練習内容が更新された。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-24T20:00:00",
            modified="2026-04-25T20:30:00",
        )

        report = self._evaluate([stale_default])

        entry = self._find_entry(report, 203)
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["cleanup_required"])
        self.assertEqual(entry["category"], "repairable")
        self.assertEqual(entry["freshness_class"], "stale")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("stale_for_breaking_board", entry["repairable_flags"])

    def test_comment_48h_within_is_publishable(self):
        fresh_comment = _post(
            204,
            "阿部監督「状態は上がってきた」 打線の手応えを語る",
            (
                "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-23T22:30:00",
            modified="2026-04-25T20:30:00",
            meta={"article_subtype": "comment"},
        )

        report = self._evaluate([fresh_comment])

        entry = self._find_entry(report, 204)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["freshness_class"], "fresh")
        self.assertEqual(entry["content_date"], "2026-04-23")
        self.assertEqual(entry["hard_stop_flags"], [])

    def test_comment_48h_over_is_hard_stop(self):
        stale_comment = _post(
            205,
            "阿部監督「状態は上がってきた」 打線の手応えを語る",
            (
                "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-23T19:30:00",
            modified="2026-04-25T20:30:00",
            meta={"article_subtype": "comment"},
        )

        report = self._evaluate([stale_comment])

        entry = self._find_entry(report, 205)
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["cleanup_required"])
        self.assertEqual(entry["freshness_class"], "stale")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("stale_for_breaking_board", entry["repairable_flags"])

    def test_modified_is_not_used_for_freshness(self):
        old_postgame = _post(
            206,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-21T20:30:00",
            modified="2026-04-25T21:00:00",
            meta={"article_subtype": "postgame"},
        )

        report = self._evaluate([old_postgame])

        entry = self._find_entry(report, 206)
        self.assertEqual(entry["content_date"], "2026-04-21")
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("expired_game_context", entry["repairable_flags"])
        self.assertIn("detected_by=created_at", entry["freshness_reason"])

    def test_source_date_takes_priority_over_created_at(self):
        cases = [
            (
                "newer_source_date_keeps_post_publishable",
                _post(
                    207,
                    "巨人が阪神に3-2で勝利",
                    (
                        "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                        "<p>参照元: スポーツ報知 https://www.sponichi.co.jp/baseball/news/2026/04/25/kiji.html</p>"
                    ),
                    date="2026-04-24T10:00:00",
                    modified="2026-04-25T20:30:00",
                    meta={"article_subtype": "postgame"},
                ),
                "2026-04-25",
                True,
                "fresh",
            ),
            (
                "older_source_date_forces_stale_hold",
                _post(
                    208,
                    "阿部監督「状態は上がってきた」 打線の手応えを語る",
                    (
                        "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                        "<p>参照元: スポーツ報知 https://www.sponichi.co.jp/baseball/news/2026/04/23/kiji.html</p>"
                    ),
                    date="2026-04-25T16:00:00",
                    modified="2026-04-25T20:30:00",
                    meta={"article_subtype": "comment"},
                ),
                "2026-04-23",
                True,
                "stale",
            ),
        ]

        for label, post, expected_date, expected_publishable, expected_class in cases:
            with self.subTest(label=label):
                report = self._evaluate([post])
                entry = self._find_entry(report, post["id"])
                self.assertEqual(entry["content_date"], expected_date)
                self.assertEqual(entry["publishable"], expected_publishable)
                self.assertEqual(entry["freshness_class"], expected_class)
                self.assertIn("priority=1", entry["freshness_reason"])
                self.assertRegex(entry["freshness_reason"], r"detected_by=source_(block|url)")

    def test_body_date_used_when_source_date_missing(self):
        body_dated_post = _post(
            209,
            "巨人が阪神に3-2で勝利",
            (
                "<p>4月24日に東京ドームで行われた阪神戦で巨人が3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知</p>"
            ),
            date="2026-04-25T20:30:00",
            modified="2026-04-25T20:40:00",
            meta={"article_subtype": "postgame"},
        )

        report = self._evaluate([body_dated_post])

        entry = self._find_entry(report, 209)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["content_date"], "2026-04-24")
        self.assertEqual(entry["freshness_class"], "expired")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("expired_game_context", entry["repairable_flags"])
        self.assertIn("detected_by=body_date", entry["freshness_reason"])
        self.assertIn("priority=2", entry["freshness_reason"])

    def test_summary_includes_fresh_stale_expired_counts(self):
        report = self._evaluate(
            [
                _post(
                    210,
                    "阿部監督「状態は上がってきた」 打線の手応えを語る",
                    (
                        "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/source</p>"
                    ),
                    date="2026-04-23T22:30:00",
                    modified="2026-04-25T20:30:00",
                    meta={"article_subtype": "comment"},
                ),
                _post(
                    211,
                    "阿部監督「状態は上がってきた」 打線の手応えを語る",
                    (
                        "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/source</p>"
                    ),
                    date="2026-04-23T19:30:00",
                    modified="2026-04-25T20:30:00",
                    meta={"article_subtype": "comment"},
                ),
                _post(
                    212,
                    "巨人スタメン 1番丸 4番岡本",
                    (
                        "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本で先発する。</p>"
                        "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T51000.html</p>"
                    ),
                    date="2026-04-25T14:00:00",
                    modified="2026-04-25T20:30:00",
                    meta={"article_subtype": "lineup"},
                ),
            ]
        )

        self.assertEqual(report["summary"]["fresh_count"], 1)
        self.assertEqual(report["summary"]["stale_hold_count"], 1)
        self.assertEqual(report["summary"]["expired_hold_count"], 1)

    def test_human_summary_includes_stale_top_list(self):
        report = self._evaluate(
            [
                _post(
                    213,
                    "阿部監督「状態は上がってきた」 打線の手応えを語る",
                    (
                        "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/source</p>"
                    ),
                    date="2026-04-23T19:30:00",
                    modified="2026-04-25T20:30:00",
                    meta={"article_subtype": "comment"},
                ),
                _post(
                    214,
                    "巨人が阪神に3-2で勝利",
                    (
                        "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/source</p>"
                    ),
                    date="2026-04-24T19:00:00",
                    modified="2026-04-25T20:30:00",
                    meta={"article_subtype": "postgame"},
                ),
            ]
        )

        rendered = render_human_report(report)

        self.assertEqual(len(report["stale_top_list"]), 2)
        self.assertIn("Freshness Hold Top", rendered)
        self.assertIn("213 | 阿部監督", rendered)
        self.assertIn("214 | 巨人が阪神に3-2で勝利", rendered)
        self.assertIn("2026-04-23", rendered)

    def test_created_424_draft_is_held_on_426_even_if_modified_on_426(self):
        stale_backlog_post = _post(
            215,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-24T19:30:00",
            modified="2026-04-26T09:15:00",
            meta={"article_subtype": "postgame"},
        )

        report = self._evaluate_at([stale_backlog_post], FIRE_TIME_NOW)

        entry = self._find_entry(report, 215)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["content_date"], "2026-04-24")
        self.assertEqual(entry["freshness_class"], "expired")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("expired_game_context", entry["repairable_flags"])
        self.assertIn("detected_by=created_at", entry["freshness_reason"])
        self.assertNotIn("2026-04-26", entry["freshness_reason"])

    def test_pregame_6h_over_is_hard_stop(self):
        stale_pregame = _post(
            216,
            "試合前に確認したい巨人打線のポイント",
            (
                "<p>巨人は今日の試合前練習で打線の並びを確認した。スポーツ報知によると、先発候補の状態も整理された。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-26T06:00:00",
            modified="2026-04-26T12:00:00",
            meta={"article_subtype": "pregame"},
        )

        report = self._evaluate_at([stale_pregame], FIRE_TIME_NOW)

        entry = self._find_entry(report, 216)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["freshness_class"], "expired")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("expired_lineup_or_pregame", entry["repairable_flags"])
        self.assertIn("threshold=6h", entry["freshness_reason"])

    def test_program_and_off_field_within_48h_remain_publishable(self):
        report = self._evaluate_at(
            [
                _post(
                    217,
                    "巨人戦の中継予定を整理 テレビ放送とラジオ出演情報",
                    (
                        "<p>巨人戦の放送予定が更新された。スポーツ報知によると、テレビ中継とラジオ出演情報がまとまった。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/program</p>"
                    ),
                    date="2026-04-24T18:00:00",
                    modified="2026-04-26T08:00:00",
                    meta={"article_subtype": "program"},
                ),
                _post(
                    218,
                    "巨人グッズ新作が販売開始 東京ドームイベント情報も更新",
                    (
                        "<p>巨人グッズの販売開始情報が更新された。スポーツ報知によると、東京ドームのイベント案内も追加された。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/off-field</p>"
                    ),
                    date="2026-04-24T17:30:00",
                    modified="2026-04-26T08:30:00",
                    meta={"article_subtype": "off_field"},
                ),
            ],
            FIRE_TIME_NOW,
        )

        for post_id in (217, 218):
            with self.subTest(post_id=post_id):
                entry = self._find_entry(report, post_id)
                self.assertTrue(entry["publishable"])
                self.assertEqual(entry["freshness_class"], "fresh")
                self.assertEqual(entry["hard_stop_flags"], [])

    def test_stale_for_breaking_board_is_reported_as_repairable(self):
        stale_comment = _post(
            219,
            "阿部監督「状態は上がってきた」 打線の手応えを語る",
            (
                "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-23T19:30:00",
            modified="2026-04-25T20:30:00",
            meta={"article_subtype": "comment"},
        )

        report = self._evaluate([stale_comment])

        entry = self._find_entry(report, 219)
        self.assertTrue(entry["publishable"])
        self.assertIn("stale_for_breaking_board", entry["repairable_flags"])
        self.assertNotIn("stale_for_breaking_board", entry["hard_stop_flags"])
        self.assertEqual(entry["freshness_class"], "stale")

    def test_stale_x_post_5days_old_is_backlog_only(self):
        stale_x_post = _post(
            220,
            "阿部監督「状態は上がってきた」 打線の手応えを語る",
            (
                "<p>阿部監督は『状態は上がってきた』と語った。スポーツ報知によると、打線の反応を前向きに見ている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="2026-04-27T09:00:00",
            modified="2026-04-27T09:30:00",
            meta={
                "article_subtype": "comment",
                "x_post_date": "2026-04-22T08:30:00+09:00",
                "source_date": "2026-04-27",
            },
        )

        report = self._evaluate_at([stale_x_post], FOLLOWUP_NOW)

        entry = self._find_entry(report, 220)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["content_date"], "2026-04-22")
        self.assertEqual(entry["freshness_source"], "x_post_date")
        self.assertEqual(entry["freshness_class"], "stale")
        self.assertTrue(entry["backlog_only"])
        self.assertIn("stale_for_breaking_board", entry["repairable_flags"])
        self.assertIn("freshness_source=x_post_date", entry["freshness_reason"])

    def test_stale_rss_published_2days_old_lineup_is_backlog_only(self):
        stale_lineup = _post(
            221,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本で先発する。</p>"
                "<p>参照元: スポーツ報知 https://example.com/lineup</p>"
            ),
            date="2026-04-27T10:00:00",
            modified="2026-04-27T10:15:00",
            meta={
                "article_subtype": "lineup",
                "rss_published": "2026-04-25T07:00:00+09:00",
            },
        )

        report = self._evaluate_at([stale_lineup], FOLLOWUP_NOW)

        entry = self._find_entry(report, 221)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["content_date"], "2026-04-25")
        self.assertEqual(entry["freshness_source"], "rss_published")
        self.assertEqual(entry["freshness_class"], "expired")
        self.assertTrue(entry["backlog_only"])
        self.assertIn("expired_lineup_or_pregame", entry["repairable_flags"])

    def test_fresh_postgame_within_24h_publishable(self):
        fresh_postgame = _post(
            222,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/postgame</p>"
            ),
            date="2026-04-22T12:00:00",
            modified="2026-04-27T09:00:00",
            meta={
                "article_subtype": "postgame",
                "rss_published": "2026-04-27T06:00:00+09:00",
            },
        )

        report = self._evaluate_at([fresh_postgame], FOLLOWUP_NOW)

        entry = self._find_entry(report, 222)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["content_date"], "2026-04-27")
        self.assertEqual(entry["freshness_source"], "rss_published")
        self.assertEqual(entry["freshness_class"], "fresh")
        self.assertFalse(entry["backlog_only"])
        self.assertEqual(entry["repairable_flags"], [])

    def test_content_date_unknown_warning_only(self):
        unknown_dated_post = _post(
            223,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            date="",
            modified="2026-04-27T10:00:00",
            meta={"article_subtype": "postgame"},
        )

        report = self._evaluate_at([unknown_dated_post], FOLLOWUP_NOW)

        entry = self._find_entry(report, 223)
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertEqual(entry["freshness_source"], "unknown")
        self.assertEqual(entry["content_date"], "")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertFalse(entry["backlog_only"])
        self.assertIn("content_date_unknown", entry["repairable_flags"])
        self.assertIn("warning=content_date_unknown", entry["freshness_reason"])

    def test_future_dated_notice_event_allowed(self):
        future_notice = _post(
            224,
            "巨人が5月3日に東京ドームでイベント開催",
            (
                "<p>巨人は5月3日に東京ドームでイベントを開催する。スポーツ報知によると、当日は限定グッズの販売も予定されている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/event</p>"
            ),
            date="2026-04-27T09:30:00",
            modified="2026-04-27T09:45:00",
            meta={"article_subtype": "notice"},
        )

        report = self._evaluate_at([future_notice], FOLLOWUP_NOW)

        entry = self._find_entry(report, 224)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["content_date"], "2026-05-03")
        self.assertEqual(entry["freshness_source"], "source_date")
        self.assertEqual(entry["freshness_class"], "fresh")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertFalse(entry["backlog_only"])

    def test_scan_wp_drafts_only_reads_wordpress(self):
        wp_client = mock.Mock()
        wp_client.list_posts.return_value = [self.clean_post]
        wp_client.update_post_fields = mock.Mock()
        wp_client.update_post_status = mock.Mock()
        wp_client.get_post = mock.Mock()

        report = scan_wp_drafts(wp_client, window_hours=96, max_pool=10, now=FIXED_NOW)

        self.assertEqual(report["summary"]["green_count"], 1)
        wp_client.list_posts.assert_called_once_with(
            status="draft",
            per_page=10,
            page=1,
            orderby="modified",
            order="desc",
            context="edit",
        )
        wp_client.update_post_fields.assert_not_called()
        wp_client.update_post_status.assert_not_called()
        wp_client.get_post.assert_not_called()

    def test_scan_wp_drafts_honors_max_pool_300_with_pagination(self):
        wp_client = mock.Mock()
        wp_client.list_posts.side_effect = [
            self._make_clean_posts(3000, 100),
            self._make_clean_posts(3100, 100),
            self._make_clean_posts(3200, 100),
        ]

        report = scan_wp_drafts(wp_client, window_hours=96, max_pool=300, now=FIXED_NOW)

        self.assertEqual(report["summary"]["green_count"], 300)
        self.assertEqual(
            wp_client.list_posts.call_args_list,
            [
                mock.call(status="draft", per_page=100, page=1, orderby="modified", order="desc", context="edit"),
                mock.call(status="draft", per_page=100, page=2, orderby="modified", order="desc", context="edit"),
                mock.call(status="draft", per_page=100, page=3, orderby="modified", order="desc", context="edit"),
            ],
        )

    def test_scan_wp_drafts_max_pool_100_keeps_single_page_behavior(self):
        wp_client = mock.Mock()
        wp_client.list_posts.return_value = self._make_clean_posts(3300, 100)

        report = scan_wp_drafts(wp_client, window_hours=96, max_pool=100, now=FIXED_NOW)

        self.assertEqual(report["summary"]["green_count"], 100)
        wp_client.list_posts.assert_called_once_with(
            status="draft",
            per_page=100,
            page=1,
            orderby="modified",
            order="desc",
            context="edit",
        )

    def test_scan_wp_drafts_allows_partial_results_when_later_page_fails(self):
        wp_client = mock.Mock()
        wp_client.list_posts.side_effect = [
            self._make_clean_posts(3400, 100),
            RuntimeError("wp rest page 2 failed"),
        ]

        report = scan_wp_drafts(wp_client, window_hours=96, max_pool=101, now=FIXED_NOW)

        self.assertEqual(report["summary"]["green_count"], 100)
        self.assertEqual(
            wp_client.list_posts.call_args_list,
            [
                mock.call(status="draft", per_page=100, page=1, orderby="modified", order="desc", context="edit"),
                mock.call(status="draft", per_page=1, page=2, orderby="modified", order="desc", context="edit"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
