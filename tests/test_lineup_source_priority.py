import unittest

from src.lineup_source_priority import (
    compute_lineup_dedup,
    extract_game_id,
    is_hochi_source,
    validate_lineup_prefix,
)


def _raw_post(
    post_id: int,
    title: str,
    *,
    subtype: str = "lineup",
    candidate_key: str = "",
    game_id: str = "",
    source_name: str = "",
    source_url: str = "",
    modified: str = "2026-04-26T17:00:00",
):
    meta = {"article_subtype": subtype}
    if candidate_key:
        meta["candidate_key"] = candidate_key
    if game_id:
        meta["game_id"] = game_id
    if source_url:
        meta["_yoshilover_source_url"] = source_url
    body = f"<p>参照元: {source_name} {source_url}</p>"
    return {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body},
        "modified": modified,
        "meta": meta,
    }


class LineupSourcePriorityTests(unittest.TestCase):
    def test_is_hochi_source_detects_domain_handle_and_name(self):
        self.assertTrue(
            is_hochi_source(
                "https://news.hochi.news/articles/2026/04/26-OHT1T51000.html",
                "",
                "",
            )
        )
        self.assertTrue(
            is_hochi_source(
                "https://x.com/hochi_giants/status/2040000000000000000",
                "",
                "",
            )
        )
        self.assertTrue(is_hochi_source("", "スポーツ報知巨人班X", ""))
        self.assertFalse(is_hochi_source("https://www.sponichi.co.jp/baseball/news/2026/04/26/kiji.html", "スポニチ", ""))

    def test_extract_game_id_prefers_explicit_field_and_candidate_key(self):
        self.assertEqual(
            extract_game_id({"game_id": "20260426-g-t"}),
            "20260426-g-t",
        )
        self.assertEqual(
            extract_game_id({"candidate_key": "lineup_notice:20260426-g-t:starting"}),
            "20260426-g-t",
        )
        self.assertEqual(
            extract_game_id({"source_url": "https://baseball.yahoo.co.jp/npb/game/2026042601/top"}),
            "2026042601",
        )

    def test_validate_lineup_prefix_only_allows_lineup(self):
        self.assertIsNone(validate_lineup_prefix("巨人スタメン 1番丸 4番岡本", "lineup"))
        self.assertEqual(
            validate_lineup_prefix("巨人スタメン 阪神に3-2で勝利", "postgame"),
            "lineup_prefix_misuse",
        )
        self.assertIsNone(validate_lineup_prefix("巨人が阪神に3-2で勝利", "postgame"))

    def test_compute_lineup_dedup_prefers_hochi_and_absorbs_other_sources(self):
        post_pool = [
            _raw_post(
                101,
                "巨人スタメン 1番丸 4番岡本",
                candidate_key="lineup_notice:20260426-g-t:starting",
                game_id="20260426-g-t",
                source_name="スポーツ報知",
                source_url="https://hochi.news/articles/20260426-OHT1T51000.html",
            ),
            _raw_post(
                102,
                "巨人スタメン 1番丸 4番岡本",
                candidate_key="lineup_notice:20260426-g-t:starting",
                game_id="20260426-g-t",
                source_name="スポニチ",
                source_url="https://www.sponichi.co.jp/baseball/news/2026/04/26/kiji.html",
            ),
        ]

        report = compute_lineup_dedup(post_pool)

        self.assertEqual(report["summary"]["representative_count"], 1)
        self.assertEqual(report["summary"]["duplicate_absorbed_count"], 1)
        self.assertEqual(report["representatives"][0]["post_id"], 101)
        self.assertEqual(report["duplicate_absorbed"][0]["post_id"], 102)
        self.assertEqual(report["duplicate_absorbed"][0]["reason"], "lineup_duplicate_absorbed_by_hochi")

    def test_compute_lineup_dedup_defers_game_without_hochi(self):
        post_pool = [
            _raw_post(
                201,
                "巨人スタメン 1番丸 4番岡本",
                candidate_key="lineup_notice:20260427-g-c:starting",
                game_id="20260427-g-c",
                source_name="スポニチ",
                source_url="https://www.sponichi.co.jp/baseball/news/2026/04/27/kiji.html",
            )
        ]

        report = compute_lineup_dedup(post_pool)

        self.assertEqual(report["summary"]["representative_count"], 0)
        self.assertEqual(report["summary"]["deferred_count"], 1)
        self.assertEqual(report["deferred"][0]["post_id"], 201)
        self.assertEqual(report["deferred"][0]["reason"], "lineup_no_hochi_source")

    def test_compute_lineup_dedup_detects_prefix_violation_on_evaluator_entry(self):
        evaluator_entry = {
            "post_id": 301,
            "title": "巨人スタメン 阪神に3-2で勝利",
            "subtype": "postgame",
            "candidate_key": "postgame_result:20260426-g-t:win",
            "game_id": "20260426-g-t",
            "source_url": "https://hochi.news/articles/20260426-OHT1T51001.html",
            "source_name": "スポーツ報知",
            "source_domain": "hochi.news",
        }

        report = compute_lineup_dedup([evaluator_entry])

        self.assertEqual(report["summary"]["prefix_violation_count"], 1)
        self.assertEqual(report["prefix_violations"][0]["post_id"], 301)
        self.assertEqual(report["prefix_violations"][0]["reason"], "lineup_prefix_misuse")


if __name__ == "__main__":
    unittest.main()
