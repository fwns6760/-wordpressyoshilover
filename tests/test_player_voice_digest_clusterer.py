"""Tests for src/player_voice_digest_clusterer.py — 334-QA Phase 2a."""

from __future__ import annotations

import unittest

from src.player_voice_digest_clusterer import (
    DigestChild,
    DigestCluster,
    find_digest_clusters,
)


_HOST_URL = {
    "hochi": "https://hochi.news/articles/{}.html",
    "sanspo": "https://www.sanspo.com/article/{}/",
    "sponichi": "https://www.sponichi.co.jp/baseball/{}.html",
    "nikkansports": "https://www.nikkansports.com/baseball/news/{}.html",
    "daily": "https://www.daily.co.jp/baseball/2026/05/14/{}.shtml",
    "tokyo_sports": "https://www.tokyo-sports.co.jp/articles/-/{}",
}


def _cand(
    *,
    family: str = "hochi",
    game_id: str = "g1",
    player_id: str = "p1",
    player_name: str = "坂本勇人",
    title: str = "",
    body: str = "",
    article_id: str = "1",
    published_at: str = "2026-05-14T20:00",
    post_url: str = "",
) -> dict:
    if not post_url:
        post_url = _HOST_URL[family].format(article_id)
    return {
        "game_id": game_id,
        "player_id": player_id,
        "player_name": player_name,
        "title": title,
        "body": body,
        "post_url": post_url,
        "published_at": published_at,
    }


# parent body: quote 「24字」 + event token 「300号サヨナラホームラン」、body 67 字
_PARENT_BODY = (
    "坂本勇人は試合後の取材で"
    "「最後まで集中して振り切れたんじゃないかと思います」"
    "と振り返り、300号サヨナラホームランで勝利を引き寄せた。"
)

# child title 31 字
_SANSPO_TITLE = (
    "坂本勇人のサヨナラ本塁打が決勝点、巨人が劇的勝利で連勝を伸ばす"
)

# child title 33 字
_NIKKAN_TITLE = (
    "坂本勇人が満員の東京ドームで劇的なサヨナラ本塁打を放ち勝利を呼んだ"
)

# child title 32 字 (daily)
_DAILY_TITLE = (
    "坂本勇人サヨナラ本塁打が試合を決めた、巨人ファン総立ちの劇的勝利"
)

# child title 30 字 (tokyo_sports)
_TOSPO_TITLE = (
    "坂本勇人のサヨナラ本塁打で巨人勝利、本人も「最高でした」と歓喜"
)


class BasicClusterDetectionTests(unittest.TestCase):
    def test_basic_3_family_cluster_detected(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY, title="坂本サヨナラ"),
            _cand(family="sanspo", title=_SANSPO_TITLE),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.game_id, "g1")
        self.assertEqual(cluster.player_id, "p1")
        self.assertEqual(cluster.player_name, "坂本勇人")
        self.assertEqual(cluster.parent_family, "hochi")
        self.assertEqual(
            cluster.quote, "最後まで集中して振り切れたんじゃないかと思います"
        )
        self.assertEqual(cluster.event_token, "300号サヨナラホームラン")
        self.assertEqual(len(cluster.children), 2)
        child_families = {c.family for c in cluster.children}
        self.assertEqual(child_families, {"sanspo", "nikkansports"})
        self.assertEqual(cluster.source_families, {"hochi", "sanspo", "nikkansports"})


class BelowMinFamiliesTests(unittest.TestCase):
    def test_two_families_returns_empty(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", title=_SANSPO_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(clusters, [])


class ParentSelectionTests(unittest.TestCase):
    def test_parent_picked_by_longest_body(self):
        # hochi has shorter body, sanspo has longest body (both have quote+event)
        short_body = "坂本勇人「最後まで集中して振り切れたんじゃないかと思います」300号サヨナラホームラン"
        long_body = (
            "5月14日、東京ドームに集まった満員のファンの前で、"
            "坂本勇人は試合後の取材で"
            "「最後まで集中して振り切れたんじゃないかと思います」"
            "と振り返った。300号サヨナラホームランで巨人を勝利に導いた。"
        )
        candidates = [
            _cand(family="hochi", body=short_body),
            _cand(family="sanspo", body=long_body, title=_SANSPO_TITLE),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        # sanspo wins as parent (longest body)
        self.assertEqual(clusters[0].parent_family, "sanspo")
        child_families = {c.family for c in clusters[0].children}
        # hochi body は 43 字、[30, 50] snippet 範囲に入るので child snippet が
        # 生成され、hochi も children に含まれる (正しい挙動)。
        self.assertEqual(child_families, {"hochi", "nikkansports"})

    def test_parent_tiebreak_by_published_time(self):
        # Same body length, earlier published_at wins
        body = (
            "坂本勇人が試合後に"
            "「最後まで集中して振り切れたんじゃないかと思います」"
            "と語った。300号サヨナラホームランで勝利。"
        )
        candidates = [
            _cand(
                family="sanspo",
                body=body,
                title=_SANSPO_TITLE,
                published_at="2026-05-14T21:00",
            ),
            _cand(
                family="hochi",
                body=body,
                title="hochi",
                published_at="2026-05-14T20:30",
            ),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        # hochi (earlier) wins tiebreak
        self.assertEqual(clusters[0].parent_family, "hochi")


class ChildrenSelectionTests(unittest.TestCase):
    def test_children_one_per_family(self):
        # 2 sanspo candidates — only 1 should appear in children
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", article_id="1", title=_SANSPO_TITLE),
            _cand(family="sanspo", article_id="2", title=_SANSPO_TITLE + "別"),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        sanspo_count = sum(1 for c in clusters[0].children if c.family == "sanspo")
        self.assertEqual(sanspo_count, 1)

    def test_children_exclude_parent_family(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(
                family="hochi",
                article_id="2",
                title="hochi second article " + _SANSPO_TITLE,
            ),
            _cand(family="sanspo", title=_SANSPO_TITLE),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        child_families = {c.family for c in clusters[0].children}
        self.assertNotIn("hochi", child_families)

    def test_max_children_capped_at_5(self):
        # 6 families total: 1 parent + 5 children at most
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", title=_SANSPO_TITLE),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
            _cand(family="daily", title=_DAILY_TITLE),
            _cand(family="tokyo_sports", title=_TOSPO_TITLE),
            _cand(
                family="sponichi",
                title="坂本勇人のサヨナラで勝利、巨人ファンが大歓喜の劇的フィナーレ",
            ),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        self.assertLessEqual(len(clusters[0].children), 5)
        self.assertEqual(len(clusters[0].children), 5)


class MissingFactsTests(unittest.TestCase):
    def test_no_quote_in_parent_no_cluster(self):
        body_no_quote = "坂本勇人が300号サヨナラホームランで勝利を引き寄せた。"
        candidates = [
            _cand(family="hochi", body=body_no_quote),
            _cand(family="sanspo", title=_SANSPO_TITLE),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(clusters, [])

    def test_no_event_token_in_parent_no_cluster(self):
        body_no_event = (
            "坂本勇人は取材で"
            "「最後まで集中して振り切れたんじゃないかと思います」"
            "と振り返った。今日の試合は印象深いものだった。"
        )
        candidates = [
            _cand(family="hochi", body=body_no_event),
            _cand(family="sanspo", title=_SANSPO_TITLE),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(clusters, [])

    def test_no_player_name_no_cluster(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY, player_name=""),
            _cand(family="sanspo", title=_SANSPO_TITLE, player_name=""),
            _cand(family="nikkansports", title=_NIKKAN_TITLE, player_name=""),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(clusters, [])


class GroupingTests(unittest.TestCase):
    def test_missing_game_id_skipped(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY, game_id=""),
            _cand(family="sanspo", title=_SANSPO_TITLE, game_id=""),
            _cand(family="nikkansports", title=_NIKKAN_TITLE, game_id=""),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(clusters, [])

    def test_different_games_not_clustered(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY, game_id="g1"),
            _cand(family="sanspo", title=_SANSPO_TITLE, game_id="g2"),
            _cand(family="nikkansports", title=_NIKKAN_TITLE, game_id="g3"),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(clusters, [])


class SnippetExtractionTests(unittest.TestCase):
    def test_short_title_falls_back_to_body_for_snippet(self):
        short_title = "サヨナラ"  # 4 chars, too short for snippet
        long_body_for_snippet = (
            "坂本勇人のサヨナラ本塁打が試合を決め、巨人が劇的勝利で連勝を伸ばす。"
            "東京ドームのファンも総立ち。"
        )
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", title=short_title, body=long_body_for_snippet),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        sanspo_child = next(
            (c for c in clusters[0].children if c.family == "sanspo"),
            None,
        )
        self.assertIsNotNone(sanspo_child)
        self.assertGreaterEqual(len(sanspo_child.snippet), 30)
        self.assertLessEqual(len(sanspo_child.snippet), 50)

    def test_neither_title_nor_body_in_range_no_child(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", title="短い", body="短い"),
            _cand(family="nikkansports", title=_NIKKAN_TITLE),
            _cand(family="daily", title=_DAILY_TITLE),
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        child_families = {c.family for c in clusters[0].children}
        self.assertNotIn("sanspo", child_families)
        self.assertIn("nikkansports", child_families)
        self.assertIn("daily", child_families)


def _cand_family(c: dict) -> str:
    """Test helper: replicate clusterer's family derivation."""
    from src.player_voice_digest_clusterer import _family_for_candidate

    return _family_for_candidate(c)


if __name__ == "__main__":
    unittest.main()
