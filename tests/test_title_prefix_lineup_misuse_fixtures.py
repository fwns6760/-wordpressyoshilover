import unittest
from datetime import datetime

from src.guarded_publish_evaluator import evaluate_raw_posts
from src.lineup_source_priority import compute_lineup_dedup


FIXED_NOW = datetime.fromisoformat("2026-04-26T21:00:00+09:00")


def _post(
    post_id,
    title,
    body_html,
    *,
    featured_media=10,
    modified="2026-04-26T18:00:00",
    date="2026-04-26T17:00:00",
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


class TitlePrefixLineupMisuseFixtureTests(unittest.TestCase):
    def _evaluate(self, posts):
        return evaluate_raw_posts(posts, window_hours=96, max_pool=100, now=FIXED_NOW)

    def _run_fixture(self, posts):
        return self._evaluate(posts), compute_lineup_dedup(posts)

    def _publishable_entry(self, report, post_id):
        for entry in report["green"] + report["yellow"]:
            if entry["post_id"] == post_id:
                return entry
        self.fail(f"publishable entry not found for post_id={post_id}")

    def _red_entry(self, report, post_id):
        for entry in report["red"]:
            if entry["post_id"] == post_id:
                return entry
        self.fail(f"red entry not found for post_id={post_id}")

    def test_lineup_prefix_with_lineup_notice_body_stays_publishable(self):
        lineup_post = _post(
            1201,
            "巨人スタメン 1番丸 4番岡本 先発は戸郷",
            (
                "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本、先発は戸郷となった。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51010.html</p>"
            ),
            meta={
                "article_subtype": "lineup_notice",
                "candidate_key": "lineup_notice:20260426-g-t:starting",
                "game_id": "20260426-g-t",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51010.html",
            },
        )

        report, dedup = self._run_fixture([lineup_post])

        self.assertEqual(report["summary"]["red_count"], 0)
        self.assertEqual(report["summary"]["publishable_count"], 1)
        self.assertEqual(report["summary"]["lineup_representative_count"], 1)
        entry = self._publishable_entry(report, 1201)
        self.assertEqual(entry["lineup_priority_status"], "representative")
        self.assertEqual(entry["lineup_priority_reason"], "lineup_primary_hochi")
        self.assertEqual(dedup["summary"]["prefix_violation_count"], 0)
        self.assertEqual(dedup["representatives"][0]["post_id"], 1201)

    def test_lineup_prefix_with_postgame_body_is_red(self):
        postgame_post = _post(
            1202,
            "巨人スタメン 主将・岸田行倫が初回に先制の適時二塁打",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、岸田行倫が初回に先制の適時二塁打を放った。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51011.html</p>"
            ),
            meta={
                "article_subtype": "postgame",
                "candidate_key": "postgame_result:20260426-g-t:win",
                "game_id": "20260426-g-t",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51011.html",
            },
        )

        report, dedup = self._run_fixture([postgame_post])

        self.assertEqual(report["summary"]["red_count"], 1)
        self.assertEqual(report["summary"]["lineup_prefix_violation_count"], 1)
        entry = self._red_entry(report, 1202)
        self.assertIn("lineup_prefix_misuse", entry["red_flags"])
        self.assertEqual(entry["subtype"], "postgame")
        self.assertEqual(dedup["prefix_violations"][0]["post_id"], 1202)
        self.assertEqual(dedup["prefix_violations"][0]["reason"], "lineup_prefix_misuse")

    def test_lineup_prefix_with_ranking_body_is_red_and_ranking_list_only(self):
        ranking_post = _post(
            1203,
            "巨人スタメン NPB通算安打 ①（東映）3085 ⑤（広島）2543",
            (
                "<p>NPB通算安打のランキングを整理した。スポーツ報知によると、歴代上位の数字を並べた。</p>"
                "<p>①（東映）3085 ②（阪神）2731 ⑤（広島）2543</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51012.html</p>"
            ),
            meta={
                "article_subtype": "other",
                "candidate_key": "ranking_note:20260426-history",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51012.html",
            },
        )

        report, dedup = self._run_fixture([ranking_post])

        self.assertEqual(report["summary"]["red_count"], 1)
        entry = self._red_entry(report, 1203)
        self.assertIn("lineup_prefix_misuse", entry["red_flags"])
        self.assertIn("ranking_list_only", entry["red_flags"])
        self.assertEqual(report["summary"]["lineup_prefix_violation_count"], 1)
        self.assertEqual(dedup["summary"]["prefix_violation_count"], 1)

    def test_lineup_prefix_with_injury_body_is_red_and_injury_death(self):
        injury_post = _post(
            1204,
            "巨人スタメン 主力が故障で登録抹消 診断結果を待つ状況",
            (
                "<p>主力選手が故障で登録抹消となった。スポーツ報知によると、診断結果を待っている状況だという。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51013.html</p>"
            ),
            meta={
                "article_subtype": "injury",
                "candidate_key": "injury_notice:20260426-main",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51013.html",
            },
        )

        report, dedup = self._run_fixture([injury_post])

        self.assertEqual(report["summary"]["red_count"], 1)
        entry = self._red_entry(report, 1204)
        self.assertIn("lineup_prefix_misuse", entry["red_flags"])
        self.assertIn("injury_death", entry["red_flags"])
        self.assertEqual(entry["subtype"], "injury")
        self.assertEqual(dedup["summary"]["prefix_violation_count"], 1)

    def test_short_starmen_h3_label_is_allowed_for_lineup_notice(self):
        lineup_with_label = _post(
            1205,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本で先発する。</p>"
                "<h3>スタメン</h3>"
                "<p>1番丸 2番門脇 3番吉川 4番岡本 先発戸郷</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51014.html</p>"
            ),
            meta={
                "article_subtype": "lineup_notice",
                "candidate_key": "lineup_notice:20260426-g-c:starting",
                "game_id": "20260426-g-c",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51014.html",
            },
        )

        report, dedup = self._run_fixture([lineup_with_label])

        self.assertEqual(report["summary"]["red_count"], 0)
        self.assertEqual(report["summary"]["publishable_count"], 1)
        entry = self._publishable_entry(report, 1205)
        self.assertNotIn("weird_heading_label", entry.get("yellow_reasons", []))
        self.assertEqual(entry["lineup_priority_status"], "representative")
        self.assertEqual(dedup["summary"]["prefix_violation_count"], 0)

    def test_speculative_lineup_prefix_title_is_red(self):
        speculative_post = _post(
            1206,
            "巨人スタメン どう見るか 阿部監督の起用意図",
            (
                "<p>阿部監督が試合前に起用の狙いを説明した。スポーツ報知によると、守備位置と打順の兼ね合いを確認した。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51015.html</p>"
            ),
            meta={
                "article_subtype": "pregame",
                "candidate_key": "pregame_note:20260426-g-d:manager",
                "game_id": "20260426-g-d",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51015.html",
            },
        )

        report, dedup = self._run_fixture([speculative_post])

        self.assertEqual(report["summary"]["red_count"], 1)
        entry = self._red_entry(report, 1206)
        self.assertIn("speculative_title", entry["red_flags"])
        self.assertIn("lineup_prefix_misuse", entry["red_flags"])
        self.assertEqual(entry["subtype"], "pregame")
        self.assertEqual(dedup["summary"]["prefix_violation_count"], 1)

    def test_same_game_lineup_notice_prefers_hochi_and_absorbs_other_source(self):
        hochi_lineup = _post(
            1207,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本で先発する。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51016.html</p>"
            ),
            meta={
                "article_subtype": "lineup_notice",
                "candidate_key": "lineup_notice:20260426-g-db:starting",
                "game_id": "20260426-g-db",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51016.html",
            },
        )
        yahoo_lineup = _post(
            1208,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。Yahoo!スポーツナビによると、1番丸、4番岡本で先発する。</p>"
                "<p>参照元: Yahoo!スポーツナビ https://baseball.yahoo.co.jp/npb/game/2026042601/top</p>"
            ),
            meta={
                "article_subtype": "lineup_notice",
                "candidate_key": "lineup_notice:20260426-g-db:starting",
                "game_id": "20260426-g-db",
                "_yoshilover_source_url": "https://baseball.yahoo.co.jp/npb/game/2026042601/top",
            },
        )

        report, dedup = self._run_fixture([hochi_lineup, yahoo_lineup])

        self.assertEqual(report["summary"]["lineup_representative_count"], 1)
        self.assertEqual(report["summary"]["lineup_duplicate_absorbed_count"], 1)
        representative = self._publishable_entry(report, 1207)
        absorbed = self._red_entry(report, 1208)
        self.assertEqual(representative["lineup_priority_status"], "representative")
        self.assertIn("lineup_duplicate_absorbed_by_hochi", absorbed["red_flags"])
        self.assertEqual(absorbed["representative_post_id"], 1207)
        self.assertEqual(dedup["representatives"][0]["post_id"], 1207)
        self.assertEqual(dedup["duplicate_absorbed"][0]["post_id"], 1208)

    def test_lineup_notice_without_hochi_is_deferred(self):
        yahoo_only_lineup = _post(
            1209,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。Yahoo!スポーツナビによると、1番丸、4番岡本で先発する。</p>"
                "<p>参照元: Yahoo!スポーツナビ https://baseball.yahoo.co.jp/npb/game/2026042701/top</p>"
            ),
            meta={
                "article_subtype": "lineup_notice",
                "candidate_key": "lineup_notice:20260427-g-c:starting",
                "game_id": "20260427-g-c",
                "_yoshilover_source_url": "https://baseball.yahoo.co.jp/npb/game/2026042701/top",
            },
        )

        report, dedup = self._run_fixture([yahoo_only_lineup])

        self.assertEqual(report["summary"]["red_count"], 1)
        self.assertEqual(report["summary"]["lineup_deferred_count"], 1)
        entry = self._red_entry(report, 1209)
        self.assertEqual(entry["lineup_priority_status"], "deferred")
        self.assertIn("lineup_no_hochi_source", entry["red_flags"])
        self.assertEqual(dedup["deferred"][0]["post_id"], 1209)
        self.assertEqual(dedup["deferred"][0]["reason"], "lineup_no_hochi_source")

    def test_mid_title_starmen_phrase_does_not_trigger_prefix_violation(self):
        comment_post = _post(
            1210,
            "阿部監督が巨人スタメン起用の意図を説明",
            (
                "<p>阿部監督が試合前練習後に巨人スタメン起用の意図を説明した。スポーツ報知によると、守備配置も含めて確認したという。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51017.html</p>"
            ),
            meta={
                "article_subtype": "comment",
                "candidate_key": "comment_notice:20260426-g-d:abe",
                "_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T51017.html",
            },
        )

        report, dedup = self._run_fixture([comment_post])

        self.assertEqual(report["summary"]["publishable_count"], 1)
        self.assertEqual(report["summary"]["lineup_prefix_violation_count"], 0)
        self.assertEqual(dedup["summary"]["prefix_violation_count"], 0)
        entry = self._publishable_entry(report, 1210)
        self.assertNotIn("lineup_priority_status", entry)


if __name__ == "__main__":
    unittest.main()
