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
    excerpt="",
    extra=None,
):
    payload = {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body_html},
        "excerpt": {"raw": excerpt, "rendered": excerpt},
        "featured_media": featured_media,
        "modified": modified,
        "date": date,
        "categories": [],
        "tags": [],
    }
    if meta is not None:
        payload["meta"] = meta
    if extra:
        payload.update(extra)
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
        for bucket in ("green", "yellow", "review", "red"):
            for entry in report.get(bucket, []):
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

    def _resolve_subtype_with_other_meta(self, title: str, body_html: str = "<p>本文を整理した。</p>") -> dict:
        post = _post(
            9999,
            title,
            body_html,
            meta={"article_subtype": "other"},
        )
        return evaluator_module.resolve_guarded_publish_subtype(
            post,
            {
                "title": title,
                "body_text": evaluator_module._strip_html(body_html),
                "inferred_subtype": None,
            },
        )

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

    def test_family_death_title_63475_type_skips_death_hard_stop(self):
        post = _post(
            63475,
            "巨人スタメン 皆川岳飛、亡くなったおじいちゃんに記念ボール",
            (
                "<p>巨人の皆川岳飛は試合前、おじいちゃんへの思いを胸にグラウンドへ向かった。"
                "スポーツ報知によると、家族の前で記念ボールを届けたいと話した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63475</p>"
            ),
            meta={"article_subtype": "lineup"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63475)
        self.assertTrue(entry["publishable"])
        self.assertNotIn("death_or_grave_incident", entry["hard_stop_flags"])

    def test_family_death_title_63470_type_skips_death_hard_stop(self):
        post = _post(
            63470,
            "皆川岳飛 天国で見てくれているおじいちゃんに",
            (
                "<p>皆川岳飛は天国で見てくれているおじいちゃんに結果を届けたいと語った。"
                "スポーツ報知によると、父も背中を押したという。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63470</p>"
            ),
            meta={"article_subtype": "player_notice"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63470)
        self.assertTrue(entry["publishable"])
        self.assertNotIn("death_or_grave_incident", entry["hard_stop_flags"])

    def test_player_self_death_fixture_remains_hard_stop(self):
        record = {
            "title": "巨人OBの高田氏が逝去",
            "body_text": "巨人OBの高田氏が逝去したと球団が発表した。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-self-death",
            "source_urls": ["https://example.com/source-self-death"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="comment")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_player_self_grave_injury_fixture_remains_hard_stop(self):
        record = {
            "title": "巨人主力が脳梗塞で意識不明",
            "body_text": "巨人主力が脳梗塞で意識不明となり、家族が病院へ駆けつけた。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-grave-self",
            "source_urls": ["https://example.com/source-grave-self"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="injury")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_surgery_recovery_lineup_context_returns_yellow_instead_of_hard_stop(self):
        record = {
            "title": "巨人スタメン 股関節手術後1軍初スタメン",
            "body_text": "股関節手術後の選手が1軍初スタメンで実戦復帰する。スポーツ報知によると、首脳陣は出場機会で状態を見極める。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-surgery-lineup",
            "source_urls": ["https://example.com/source-surgery-lineup"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="lineup")

        self.assertEqual(flag, "roster_movement_yellow")

    def test_surgery_recovery_rehab_context_returns_yellow_instead_of_hard_stop(self):
        record = {
            "title": "巨人主力 肩手術後 リハビリ順調",
            "body_text": "肩手術後の主力は実戦復帰へ向けたリハビリが順調だ。スポーツ報知によると、段階的に出場機会を増やしていく。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-surgery-rehab",
            "source_urls": ["https://example.com/source-surgery-rehab"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="injury")

        self.assertEqual(flag, "roster_movement_yellow")

    def test_surgery_recovery_return_game_context_returns_yellow_instead_of_hard_stop(self):
        record = {
            "title": "巨人右腕 術後の復帰戦へ",
            "body_text": "右腕は術後の復帰戦に向けて最終調整を進める。スポーツ報知によると、ファームでの復帰登板が予定されている。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-return-game",
            "source_urls": ["https://example.com/source-return-game"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="farm")

        self.assertEqual(flag, "roster_movement_yellow")

    def test_death_keyword_fixture_remains_hard_stop(self):
        record = {
            "title": "巨人関係者が事故で死亡",
            "body_text": "巨人関係者が事故で死亡したと伝えられた。スポーツ報知によると、球団が哀悼の意を示した。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-death-keyword",
            "source_urls": ["https://example.com/source-death-keyword"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_serious_injury_keyword_fixture_remains_hard_stop(self):
        record = {
            "title": "巨人選手が重傷で救急搬送",
            "body_text": "巨人選手が重傷で救急搬送された。スポーツ報知によると、病院で精密検査を受けている。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-serious-injury",
            "source_urls": ["https://example.com/source-serious-injury"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="injury")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_unconscious_critical_keyword_fixture_remains_hard_stop(self):
        record = {
            "title": "巨人OBが意識不明の重体",
            "body_text": "巨人OBが意識不明の重体となった。スポーツ報知によると、関係者が病院に集まっている。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-critical",
            "source_urls": ["https://example.com/source-critical"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_soft_medical_term_with_long_recovery_remains_hard_stop(self):
        record = {
            "title": "巨人主力が入院手術 全治6か月",
            "body_text": "巨人主力が入院して手術を受け、全治6か月の見込みとなった。スポーツ報知によると、復帰まで長期調整が必要だ。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-long-recovery",
            "source_urls": ["https://example.com/source-long-recovery"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="injury")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_soft_medical_term_without_recovery_context_remains_hard_stop(self):
        record = {
            "title": "巨人主力は手術が必要",
            "body_text": "巨人主力は検査の結果、手術が必要と判断された。スポーツ報知によると、今後の見通しは未定だ。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-surgery-needed",
            "source_urls": ["https://example.com/source-surgery-needed"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="injury")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_family_death_player_absent_fixture_stays_publishable(self):
        post = _post(
            63471,
            "巨人の若手選手 祖父が亡くなり試合を欠場",
            (
                "<p>巨人の若手選手は祖父が亡くなり、この日の試合を欠場した。"
                "スポーツ報知によると、球団は家族を優先する判断だと説明した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63471</p>"
            ),
            meta={"article_subtype": "player_notice"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63471)
        self.assertTrue(entry["publishable"])
        self.assertNotIn("death_or_grave_incident", entry["hard_stop_flags"])

    def test_family_marker_adjacent_sentence_skips_death_hard_stop(self):
        record = {
            "title": "巨人の若手が祖父への思いを胸に出場",
            "body_text": "巨人の若手は祖父への思いを胸に出場した。天国へ届ける一打を誓った。",
            "source_block": "参照元: スポーツ報知 https://example.com/source-adjacent-family",
            "source_urls": ["https://example.com/source-adjacent-family"],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="player_notice")

        self.assertIsNone(flag)

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

    def test_farm_lineup_source_missing_roster_signal_stays_yellow(self):
        record = {
            "title": "巨人二軍スタメン 楽天戦の先発メンバー",
            "body_text": "森林どりスタジアムで行われる巨人対楽天の二軍戦は、支配下登録後初スタメンの若手を含む先発メンバーが発表された。",
            "source_block": "",
            "source_urls": [],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="farm_lineup")

        self.assertEqual(flag, "roster_movement_yellow")

    def test_farm_result_source_missing_roster_signal_stays_yellow(self):
        record = {
            "title": "巨人二軍 3-6 楽天 結果のポイント",
            "body_text": "森林どりスタジアムで行われた巨人対楽天の二軍戦は3-6で敗れ、支配下登録を目指す若手が9回に追い上げを見せた。",
            "source_block": "",
            "source_urls": [],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="farm")

        self.assertEqual(flag, "roster_movement_yellow")

    def test_true_medical_incidents_remain_hard_stop(self):
        cases = (
            (
                116,
                {
                    "title": "巨人の主力選手が重症で入院",
                    "body_text": "巨人の主力選手が重症で入院した。スポーツ報知によると、球団が経過を説明した。",
                    "source_block": "参照元: スポーツ報知 https://example.com/source-grave",
                    "source_urls": ["https://example.com/source-grave"],
                },
                "injury",
            ),
            (
                117,
                {
                    "title": "巨人OBの訃報 球団が追悼コメント",
                    "body_text": "巨人OBが死去したと伝えられ、球団が追悼コメントを発表した。",
                    "source_block": "参照元: スポーツ報知 https://example.com/source-obit",
                    "source_urls": ["https://example.com/source-obit"],
                },
                "",
            ),
            (
                118,
                {
                    "title": "巨人主力が2か月の離脱へ",
                    "body_text": "巨人主力が全治2か月の離脱となる見込みだ。スポーツ報知によると、復帰までは長期調整が必要になる。",
                    "source_block": "参照元: スポーツ報知 https://example.com/source-recovery",
                    "source_urls": ["https://example.com/source-recovery"],
                },
                "injury",
            ),
        )

        for post_id, record, subtype in cases:
            with self.subTest(post_id=post_id):
                flag = evaluator_module._medical_roster_flag(record, subtype=subtype)
                self.assertEqual(flag, "death_or_grave_incident")

    def test_generic_source_missing_roster_signal_stays_hard_stop(self):
        record = {
            "title": "巨人主力が登録抹消 再調整へ",
            "body_text": "巨人主力が登録抹消となり、再調整へ入るとだけ記され、出典リンクはない。",
            "source_block": "",
            "source_urls": [],
        }

        flag = evaluator_module._medical_roster_flag(record, subtype="notice")

        self.assertEqual(flag, "death_or_grave_incident")

    def test_entity_role_mismatch_fixture_remains_visible_for_242b_followup(self):
        post = _post(
            63844,
            "巨人―広島戦の見どころ どこに注目？",
            (
                "<p>巨人は広島戦へ向かう。巨人:則本昂大 という表記が混ざるが、試合前の論点整理として本文は続いている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63844</p>"
            ),
        )

        report = self._evaluate([post])

        entry = report["yellow"][0]
        self.assertTrue(entry["publishable"])
        self.assertIn("ai_tone_heading_or_lead", entry["repairable_flags"])
        self.assertNotIn("death_or_grave_incident", entry["hard_stop_flags"])

    def test_other_team_player_contamination_63844_type_returns_yellow(self):
        post = _post(
            63851,
            "巨人 vs 楽天 先発情報",
            (
                "<p>巨人:則本昂大が先発し、試合前のポイントを整理する。スポーツ報知によると、打線の対応が焦点になる。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63851</p>"
            ),
            meta={"article_subtype": "pregame"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63851)
        self.assertEqual(entry["category"], "repairable")
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["cleanup_required"])
        self.assertIn("other_team_player_contamination", entry["repairable_flags"])
        self.assertIn("other_team_player_contamination", entry["yellow_reasons"])
        self.assertIn(
            {
                "flag": "other_team_player_contamination",
                "category": "repairable",
                "detail": "則本昂大(楽天)",
            },
            entry["reasons"],
        )

    def test_clean_post_stays_green_without_other_team_player_contamination(self):
        post = _post(
            63852,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63852</p>"
            ),
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63852)
        self.assertEqual(report["summary"]["clean_count"], 1)
        self.assertEqual(entry["category"], "clean")
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["repairable_flags"], [])
        self.assertNotIn("other_team_player_contamination", entry.get("yellow_reasons", []))

    def test_placeholder_body_repeated_missing_actor_farm_result_hard_stop(self):
        post = _post(
            63845,
            "巨人二軍 3-6 楽天 結果のポイント",
            (
                "<p>【二軍】巨人 3-6 楽天 先発の 投手は5回3失点。9回に 選手の適時打などで追い上げるも敗戦した。</p>"
                "<p>【二軍】巨人 3-6 楽天 先発の 投手は5回3失点。試合の詳細はこちら。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63845</p>"
            ),
            meta={"article_subtype": "farm_result"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63845)
        self.assertFalse(entry["publishable"])
        self.assertIn("farm_result_placeholder_body", entry["hard_stop_flags"])
        self.assertNotIn("placeholder_body_repairable", entry["repairable_flags"])

    def test_placeholder_body_named_actor_farm_result_stays_publishable(self):
        post = _post(
            63846,
            "巨人二軍が楽天に4-2で勝利 山崎伊織が5回1失点",
            (
                "<p>巨人二軍が楽天に4-2で勝利した。先発の山崎伊織は5回1失点と試合を作り、岡本和真の適時打で主導権を握った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63846</p>"
            ),
            meta={"article_subtype": "farm_result"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63846)
        self.assertTrue(entry["publishable"])
        self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])
        self.assertNotIn("placeholder_body_repairable", entry["repairable_flags"])

    def test_placeholder_body_double_empty_heading_is_hard_stop(self):
        post = _post(
            63847,
            "巨人二軍 3-6 楽天 試合メモ",
            (
                "<h2></h2>"
                "<p>巨人二軍は楽天に3-6で敗れた。先発の山崎伊織は5回3失点で、秋広優人の適時打が出た。</p>"
                "<h3>   </h3>"
                "<p>参照元: スポーツ報知 https://example.com/source-63847</p>"
            ),
            meta={"article_subtype": "farm"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63847)
        self.assertFalse(entry["publishable"])
        self.assertIn("farm_result_placeholder_body", entry["hard_stop_flags"])

    def test_placeholder_body_skips_notice_and_column_subtypes(self):
        posts = [
            _post(
                63848,
                "巨人編成メモ 定型文の残り方を整理",
                (
                    "<p>編成メモでは「先発の 投手」「選手の適時打」といった placeholder 例を紹介した。</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-63848</p>"
                ),
                meta={"article_subtype": "notice"},
            ),
            _post(
                63849,
                "巨人コラム 定型文の危うさを検証",
                (
                    "<p>コラムでは「先発の 投手」「選手の適時打」が残ると読み味が崩れる例を取り上げた。</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source-63849</p>"
                ),
                meta={"article_subtype": "column"},
            ),
        ]

        report = self._evaluate(posts)

        for post_id in (63848, 63849):
            entry = self._find_entry(report, post_id)
            self.assertTrue(entry["publishable"])
            self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])
            self.assertNotIn("placeholder_body_repairable", entry["repairable_flags"])

    def test_placeholder_body_filler_only_short_article_is_ignored(self):
        post = _post(
            63850,
            "巨人二軍 試合の詳細はこちら",
            (
                "<p>試合の詳細はこちら。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63850</p>"
            ),
            meta={"article_subtype": "farm_result"},
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63850)
        self.assertTrue(entry["publishable"])
        self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])
        self.assertNotIn("placeholder_body_repairable", entry["repairable_flags"])

    def test_placeholder_body_regression_preserves_242a_medical_roster_matrix(self):
        farm_lineup_post = _post(
            63841,
            "巨人二軍スタメン 楽天戦の先発メンバー",
            (
                "<p>森林どりスタジアムで行われる巨人対楽天の二軍戦は、支配下登録後初スタメンの若手を含む先発メンバーが発表された。</p>"
            ),
            meta={"article_subtype": "farm_lineup"},
        )
        farm_result_post = _post(
            63851,
            "巨人二軍 3-6 楽天 二軍戦の結果",
            (
                "<p>森林どりスタジアムで行われた巨人対楽天の二軍戦は3-6で敗れた。先発の京本眞は5回3失点だった。</p>"
                "<p>9回に浅野翔吾の適時打で追い上げたが、支配下登録を目指す若手の奮闘も届かなかった。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63851</p>"
            ),
            meta={"article_subtype": "farm"},
        )

        report = self._evaluate([farm_lineup_post, farm_result_post])

        lineup_entry = self._find_entry(report, 63841)
        result_entry = self._find_entry(report, 63851)
        self.assertIn("roster_movement_yellow", lineup_entry["repairable_flags"])
        self.assertIn("roster_movement_yellow", result_entry["repairable_flags"])
        self.assertNotIn("death_or_grave_incident", lineup_entry["hard_stop_flags"])
        self.assertNotIn("death_or_grave_incident", result_entry["hard_stop_flags"])
        self.assertNotIn("farm_result_placeholder_body", lineup_entry["hard_stop_flags"])
        self.assertNotIn("farm_result_placeholder_body", result_entry["hard_stop_flags"])

        helper_cases = (
            (
                "grave_incident",
                {
                    "title": "巨人の主力選手が重症で入院",
                    "body_text": "巨人の主力選手が重症で入院した。スポーツ報知によると、球団が経過を説明した。",
                    "source_block": "参照元: スポーツ報知 https://example.com/source-grave-regression",
                    "source_urls": ["https://example.com/source-grave-regression"],
                },
                "injury",
                "death_or_grave_incident",
            ),
            (
                "obituary",
                {
                    "title": "巨人OBの訃報 球団が追悼コメント",
                    "body_text": "巨人OBが死去したと伝えられ、球団が追悼コメントを発表した。",
                    "source_block": "参照元: スポーツ報知 https://example.com/source-obit-regression",
                    "source_urls": ["https://example.com/source-obit-regression"],
                },
                "",
                "death_or_grave_incident",
            ),
            (
                "long_recovery",
                {
                    "title": "巨人主力が2か月の離脱へ",
                    "body_text": "巨人主力が全治2か月の離脱となる見込みだ。スポーツ報知によると、復帰までは長期調整が必要になる。",
                    "source_block": "参照元: スポーツ報知 https://example.com/source-recovery-regression",
                    "source_urls": ["https://example.com/source-recovery-regression"],
                },
                "injury",
                "death_or_grave_incident",
            ),
            (
                "generic_missing_source_notice",
                {
                    "title": "巨人主力が登録抹消 再調整へ",
                    "body_text": "巨人主力が登録抹消となり、再調整へ入るとだけ記され、出典リンクはない。",
                    "source_block": "",
                    "source_urls": [],
                },
                "notice",
                "death_or_grave_incident",
            ),
            (
                "farm_lineup_soft_subtype",
                {
                    "title": "巨人二軍スタメン 楽天戦の先発メンバー",
                    "body_text": "森林どりスタジアムで行われる巨人対楽天の二軍戦は、支配下登録後初スタメンの若手を含む先発メンバーが発表された。",
                    "source_block": "",
                    "source_urls": [],
                },
                "farm_lineup",
                "roster_movement_yellow",
            ),
        )

        for label, record, subtype, expected in helper_cases:
            with self.subTest(label=label):
                flag = evaluator_module._medical_roster_flag(record, subtype=subtype)
                self.assertEqual(flag, expected)

    def test_farm_result_placeholder_body_is_hard_stop_for_63845(self):
        post = _post(
            63845,
            "【二軍】巨人 3-6 楽天 試合結果",
            (
                "<p>【二軍】巨人 3-6 楽天 先発の 投手は5回3失点。9回に 選手の適時打などで追い上げるも敗れた。</p>"
                "<p>【二軍】巨人 3-6 楽天 先発の 投手は5回3失点。試合の詳細はこちら。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63845-hard-stop</p>"
            ),
            meta={"article_subtype": "farm_result"},
            excerpt="巨人二軍は楽天に3-6で敗れた。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63845)
        self.assertEqual(entry["category"], "hard_stop")
        self.assertFalse(entry["publishable"])
        self.assertIn("farm_result_placeholder_body", entry["hard_stop_flags"])

    def test_good_farm_result_without_h3_is_publishable(self):
        post = _post(
            63860,
            "巨人二軍が楽天に4-2で勝利",
            (
                "<p>2026年4月25日の二軍戦で、巨人は楽天に4-2で勝利した。先発の山崎伊織は5回1失点だった。</p>"
                "<p>7回に浅野翔吾の適時打で勝ち越し、終盤は継投で逃げ切った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63860</p>"
            ),
            meta={"article_subtype": "farm_result"},
            excerpt="二軍戦で巨人が4-2で勝利。山崎伊織が先発した。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63860)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["review_flags"], [])
        self.assertEqual(entry["hard_stop_flags"], [])

    def test_farm_result_missing_optional_sections_does_not_block_when_required_facts_exist(self):
        post = _post(
            63861,
            "巨人二軍 5-3 楽天 試合結果",
            (
                "<p>4月25日の二軍戦で巨人は楽天に5-3で勝利した。先発の京本眞は6回2失点で試合を作った。</p>"
                "<p>3回に秋広優人の適時二塁打で先制し、終盤も追加点を奪った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63861</p>"
            ),
            meta={"article_subtype": "farm"},
            excerpt="巨人二軍が楽天に5-3で勝利した。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63861)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["review_flags"], [])
        self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])

    def test_farm_lineup_is_not_blocked_by_farm_result_validator(self):
        post = _post(
            63862,
            "巨人二軍スタメン 楽天戦の先発メンバー",
            (
                "<p>巨人二軍のスタメンが発表された。</p>"
                "<p>1番 浅野翔吾</p>"
                "<p>2番 中山礼都</p>"
                "<p>3番 秋広優人</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63862</p>"
            ),
            meta={"article_subtype": "farm_lineup"},
            excerpt="二軍戦のスタメンが発表された。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63862)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["review_flags"], [])
        self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])

    def test_empty_heading_is_hard_stop_for_farm_result(self):
        post = _post(
            63863,
            "巨人二軍 3-2 楽天 試合結果",
            (
                "<p>巨人二軍が楽天に3-2で勝利した。先発の又木鉄平は5回2失点だった。</p>"
                "<h3>   </h3>"
                "<p>8回に浅野翔吾の適時打で勝ち越した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63863</p>"
            ),
            meta={"article_subtype": "farm_result"},
            excerpt="巨人二軍が3-2で勝利した。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63863)
        self.assertFalse(entry["publishable"])
        self.assertIn("farm_result_placeholder_body", entry["hard_stop_flags"])

    def test_generic_detail_paragraph_repetition_is_hard_stop_for_farm_result(self):
        post = _post(
            63864,
            "巨人二軍 3-6 楽天 試合結果",
            (
                "<p>巨人二軍は楽天に3-6で敗れた。先発の京本眞は5回3失点だった。</p>"
                "<p>試合の詳細はこちら。</p>"
                "<p>詳しくはこちら。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63864</p>"
            ),
            meta={"article_subtype": "farm_result"},
            excerpt="巨人二軍は楽天に3-6で敗れた。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63864)
        self.assertFalse(entry["publishable"])
        self.assertIn("farm_result_placeholder_body", entry["hard_stop_flags"])

    def test_farm_result_too_many_h3_is_review_not_hard_stop_unless_empty_or_placeholder(self):
        post = _post(
            63865,
            "巨人二軍 6-2 楽天 試合結果",
            (
                "<p>巨人二軍が楽天に6-2で勝利した。先発の山崎伊織は5回1失点だった。</p>"
                "<h3>先発投手の結果</h3><p>山崎伊織は5回1失点で白星をつかんだ。</p>"
                "<h3>得点に絡んだ選手</h3><p>浅野翔吾の適時打と秋広優人の犠飛で主導権を握った。</p>"
                "<h3>目立った選手成績</h3><p>中山礼都が2安打、増田陸が1打点を記録した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63865</p>"
            ),
            meta={"article_subtype": "farm_result"},
            excerpt="巨人二軍が楽天に6-2で勝利した。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63865)
        self.assertEqual(entry["category"], "review")
        self.assertFalse(entry["publishable"])
        self.assertIn("farm_result_h3_over_limit_review", entry["review_flags"])
        self.assertEqual(entry["hard_stop_flags"], [])

    def test_farm_result_detection_requires_result_marker_and_no_lineup_marker(self):
        cases = (
            (
                63866,
                _post(
                    63866,
                    "巨人二軍 試合メモ",
                    (
                        "<p>二軍戦のメモ。先発の 投手は5回3失点。選手の適時打という文言も残っている。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/source-63866</p>"
                    ),
                    meta={"article_subtype": "farm_result"},
                    excerpt="二軍戦のメモを整理した。",
                ),
            ),
            (
                63867,
                _post(
                    63867,
                    "巨人二軍スタメン 楽天戦の先発メンバー",
                    (
                        "<p>【二軍】巨人 3-6 楽天 先発の 投手は5回3失点。選手の適時打もあった。</p>"
                        "<p>参照元: スポーツ報知 https://example.com/source-63867</p>"
                    ),
                    meta={"article_subtype": "farm"},
                    excerpt="1番 浅野翔吾、2番 中山礼都。",
                ),
            ),
        )

        report = self._evaluate([case[1] for case in cases])

        for post_id, _ in cases:
            with self.subTest(post_id=post_id):
                entry = self._find_entry(report, post_id)
                self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])
                self.assertEqual(entry["review_flags"], [])

    def test_farm_result_required_facts_weak_is_review_not_hard_stop(self):
        post = _post(
            63868,
            "巨人二軍 3-6 楽天 試合結果",
            (
                "<p>巨人二軍は楽天に3-6で敗れた。終盤まで粘ったが及ばなかった。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63868</p>"
            ),
            meta={"article_subtype": "farm_result"},
            excerpt="巨人二軍は楽天に3-6で敗れた。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63868)
        self.assertEqual(entry["category"], "review")
        self.assertFalse(entry["publishable"])
        self.assertIn("farm_result_required_facts_weak_review", entry["review_flags"])
        self.assertEqual(entry["hard_stop_flags"], [])

    def test_farm_result_body_batting_order_words_do_not_trigger_lineup_exclusion(self):
        post = _post(
            63869,
            "巨人二軍 5-3 楽天 試合結果",
            (
                "<p>巨人二軍が楽天に5-3で勝利した。先発の京本眞は5回1失点だった。</p>"
                "<p>8番打者の浅野翔吾が適時打を放ち、9番の中山礼都も追加点につなげた。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63869</p>"
            ),
            meta={"article_subtype": "farm_result"},
            excerpt="巨人二軍が楽天に5-3で勝利した。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63869)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["review_flags"], [])
        self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])

    def test_farm_lineup_title_marker_excludes_from_farm_result_blocker(self):
        post = _post(
            63870,
            "巨人二軍スタメン 楽天戦の先発メンバー",
            (
                "<p>先発の 投手は5回3失点。選手の適時打もあった、という壊れた文が残っている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-63870</p>"
            ),
            meta={"article_subtype": "farm"},
            excerpt="1番 浅野翔吾、2番 中山礼都。",
        )

        report = self._evaluate([post])

        entry = self._find_entry(report, 63870)
        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["review_flags"], [])
        self.assertNotIn("farm_result_placeholder_body", entry["hard_stop_flags"])

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

    def test_subtype_unresolved_with_title_manager_comment_prefers_manager(self):
        resolved = self._resolve_subtype_with_other_meta("阿部監督がコメント")

        self.assertEqual(resolved["resolved_subtype"], "manager")
        self.assertEqual(resolved["resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_title_coach_quote_prefers_manager(self):
        resolved = self._resolve_subtype_with_other_meta("杉内コーチ「明日は様子を見て」")

        self.assertEqual(resolved["resolved_subtype"], "manager")
        self.assertEqual(resolved["resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_title_comment_signal_resolves_comment(self):
        resolved = self._resolve_subtype_with_other_meta("岡本和真の発言整理")

        self.assertEqual(resolved["resolved_subtype"], "comment")
        self.assertEqual(resolved["resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_title_registration_signal_resolves_roster(self):
        resolved = self._resolve_subtype_with_other_meta("則本昂大、登録抹消")

        self.assertEqual(resolved["resolved_subtype"], "roster")
        self.assertEqual(resolved["resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_title_return_signal_resolves_roster(self):
        resolved = self._resolve_subtype_with_other_meta("川相昌弘、昇格・復帰")

        self.assertEqual(resolved["resolved_subtype"], "roster")
        self.assertEqual(resolved["resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_title_score_signal_resolves_game_result(self):
        resolved = self._resolve_subtype_with_other_meta("巨人 4-2 広島")

        self.assertEqual(resolved["resolved_subtype"], "game_result")
        self.assertEqual(resolved["resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_title_lineup_signal_stays_lineup(self):
        resolved = self._resolve_subtype_with_other_meta("巨人スタメン発表 阿部監督コメント")

        self.assertEqual(resolved["resolved_subtype"], "lineup")
        self.assertEqual(resolved["resolution_source"], "title_fallback")

    def test_subtype_unresolved_with_no_signal_stays_default_fallback(self):
        resolved = self._resolve_subtype_with_other_meta("謎のテキスト")

        self.assertEqual(resolved["resolved_subtype"], "default")
        self.assertEqual(resolved["resolution_source"], "default_fallback")

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

    def test_numeric_fact_mismatch_hard_stop_blocks_publish(self):
        post = _post(
            2441,
            "巨人 1-11 楽天",
            (
                "<p>巨人が楽天に19-1で勝利した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-2441</p>"
            ),
        )

        report = self._evaluate([post])
        entry = self._find_entry(report, 2441)

        self.assertEqual(entry["category"], "hard_stop")
        self.assertFalse(entry["publishable"])
        self.assertIn("numeric_fact_mismatch", entry["hard_stop_flags"])

    def test_numeric_fact_ambiguous_source_stays_review_not_hard_stop(self):
        post = _post(
            2442,
            "巨人戦の速報",
            (
                "<p>巨人が楽天戦を振り返った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-2442</p>"
            ),
            meta={"source_summary": "巨人 1-11 楽天。別稿では巨人 11-1 楽天とも記されている。"},
        )

        report = self._evaluate([post])
        entry = self._find_entry(report, 2442)

        self.assertEqual(entry["category"], "review")
        self.assertFalse(entry["publishable"])
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertIn("score_order_mismatch_review", entry["review_flags"])

    def test_numeric_fact_x_candidate_only_suppresses_x_without_blocking_article(self):
        post = _post(
            2443,
            "巨人 1-11 楽天",
            (
                "<p>巨人は楽天に1-11で敗れた。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-2443</p>"
            ),
            extra={"manual_x_post_candidates": ["巨人が楽天に19-1で勝利。https://yoshilover.com/2443"]},
        )

        report = self._evaluate([post])
        entry = self._find_entry(report, 2443)

        self.assertTrue(entry["publishable"])
        self.assertEqual(entry["category"], "repairable")
        self.assertEqual(entry["hard_stop_flags"], [])
        self.assertEqual(entry["review_flags"], [])
        self.assertFalse(entry["x_post_ready"])
        self.assertIn("x_post_numeric_mismatch", entry["x_candidate_suppress_flags"])
        self.assertIn("x_post_numeric_mismatch", entry["repairable_flags"])


if __name__ == "__main__":
    unittest.main()
