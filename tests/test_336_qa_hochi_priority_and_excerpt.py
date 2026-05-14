"""Tests for 336-QA Phase 1+2+3 (#10/#11/#12): hochi-priority parent +
hochi_raw_html_excerpt field + body renderer block + rss_fetcher 配管."""

from __future__ import annotations

import unittest

from src import player_voice_digest_body_renderer as _renderer
from src.player_voice_digest_clusterer import (
    DigestChild,
    DigestCluster,
    _pick_parent,
    find_digest_clusters,
)


class HochiPriorityParentTests(unittest.TestCase):
    """336-QA Phase 1: cluster 内に hochi family があれば必ず親に固定。"""

    def _candidate(self, family: str, body: str, source_url: str = "") -> dict:
        url_map = {
            "hochi": "https://hochi.news/articles/x.html",
            "sanspo": "https://www.sanspo.com/article/x/",
            "sponichi": "https://www.sponichi.co.jp/baseball/news/x.html",
            "nikkansports": "https://www.nikkansports.com/baseball/news/x.html",
            "daily": "https://www.daily.co.jp/baseball/x.html",
        }
        return {
            "post_url": source_url or url_map.get(family, "https://example.com/x"),
            "summary": body,
            "body": body,
            "source_family": family,
        }

    def test_pick_parent_prefers_hochi_over_longer_sanspo(self):
        sanspo = self._candidate("sanspo", "サンスポ" * 100)
        hochi = self._candidate("hochi", "報知短い")
        result = _pick_parent([sanspo, hochi])
        self.assertEqual(result, hochi)

    def test_pick_parent_falls_through_when_no_hochi(self):
        sanspo = self._candidate("sanspo", "サンスポ本文" * 50)
        sponichi = self._candidate("sponichi", "スポニチ短")
        result = _pick_parent([sanspo, sponichi])
        self.assertEqual(result, sanspo)

    def test_pick_parent_picks_longest_hochi_when_multiple(self):
        hochi_short = self._candidate("hochi", "短", "https://hochi.news/a.html")
        hochi_long = self._candidate("hochi", "長" * 100, "https://hochi.news/b.html")
        result = _pick_parent([hochi_short, hochi_long])
        self.assertEqual(result, hochi_long)


class DigestClusterFieldTests(unittest.TestCase):
    """336-QA Phase 1: DigestCluster に hochi_raw_html_excerpt field 追加。"""

    def test_default_is_empty_string(self):
        cluster = DigestCluster(
            game_id="g",
            player_id="p",
            player_name="坂本勇人",
            parent_candidate={"post_url": "https://hochi.news/x"},
            parent_family="hochi",
            quote="一生忘れない瞬間が今日この場で生まれた",
            event_token="サヨナラ",
            children=(),
        )
        self.assertEqual(cluster.hochi_raw_html_excerpt, "")

    def test_field_can_be_set(self):
        cluster = DigestCluster(
            game_id="g",
            player_id="p",
            player_name="坂本勇人",
            parent_candidate={"post_url": "https://hochi.news/x"},
            parent_family="hochi",
            quote="一生忘れない瞬間が今日この場で生まれた",
            event_token="サヨナラ",
            children=(),
            hochi_raw_html_excerpt="報知本文の literal 600字...",
        )
        self.assertEqual(cluster.hochi_raw_html_excerpt, "報知本文の literal 600字...")


class HochiExcerptBlockRenderTests(unittest.TestCase):
    """336-QA Phase 2: body renderer で nomotoke-source-excerpt aside 描画。"""

    def test_render_block_with_excerpt(self):
        result = _renderer._render_hochi_excerpt_block("巨人・坂本勇人が逆転サヨナラ３ラン。")
        self.assertIn("nomotoke-source-excerpt", result)
        self.assertIn("nomotoke-source-excerpt__label", result)
        self.assertIn("nomotoke-source-excerpt__body", result)
        self.assertIn("nomotoke-source-excerpt__attr", result)
        self.assertIn("📖 本文抜粋", result)
        self.assertIn("— スポーツ報知", result)
        self.assertIn("巨人・坂本勇人が逆転サヨナラ３ラン", result)

    def test_render_block_empty_returns_empty(self):
        self.assertEqual(_renderer._render_hochi_excerpt_block(""), "")

    def test_render_escapes_html(self):
        result = _renderer._render_hochi_excerpt_block("<script>alert(1)</script>")
        self.assertNotIn("<script>alert", result)
        self.assertIn("&lt;script&gt;", result)

    def test_full_body_includes_excerpt_block_when_payload_set(self):
        candidate = {
            "subtype_hint": "player_voice_digest",
            "body": "巨人・坂本勇人が逆転サヨナラ３ラン。「一生忘れない瞬間が今日この場で生まれた」と語った。",
            "summary": "",
            "digest_cluster_payload": {
                "player_name": "坂本勇人",
                "quote": "一生忘れない瞬間が今日この場で生まれた",
                "event_token": "サヨナラ",
                "parent_family": "hochi",
                "children": [],
                "officials": [],
                "hochi_raw_html_excerpt": "報知の long 抜粋テキスト本文。" * 5,
            },
        }
        body = _renderer.render_player_voice_digest_body(candidate)
        self.assertIn("nomotoke-source-excerpt", body)
        self.assertIn("— スポーツ報知", body)
        self.assertIn("報知の long 抜粋テキスト本文", body)

    def test_full_body_omits_excerpt_when_payload_absent(self):
        candidate = {
            "subtype_hint": "player_voice_digest",
            "body": "巨人・坂本勇人が逆転サヨナラ３ラン。「一生忘れない瞬間が今日この場で生まれた」と語った。",
            "summary": "",
            "digest_cluster_payload": {
                "player_name": "坂本勇人",
                "quote": "一生忘れない瞬間が今日この場で生まれた",
                "event_token": "サヨナラ",
                "parent_family": "sanspo",
                "children": [],
                "officials": [],
                "hochi_raw_html_excerpt": "",
            },
        }
        body = _renderer.render_player_voice_digest_body(candidate)
        self.assertNotIn("nomotoke-source-excerpt", body)


class FindDigestClustersHochiPriorityIntegrationTests(unittest.TestCase):
    """336-QA Phase 1: find_digest_clusters 経由で hochi 優先動作確認。"""

    def test_hochi_chosen_as_parent_in_full_pipeline(self):
        long_quote = "一生忘れない瞬間が今日この場で生まれた最高のホームランだ"
        candidates = [
            {
                "post_url": "https://www.sanspo.com/article/x/",
                "title": "巨人・坂本勇人がサヨナラ３ラン！通算300号メモリアル弾",
                "summary": "サンスポ summary",
                "body": f"巨人・坂本がホームラン。「{long_quote}」と語った。" + "サンスポ" * 200,
                "source_family": "sanspo",
                "game_id": "2026-05-14",
                "player_name": "坂本勇人",
            },
            {
                "post_url": "https://hochi.news/articles/x.html",
                "title": "巨人坂本勇人サヨナラ３ラン300号メモリアル",
                "summary": "報知 summary",
                "body": f"報知本文。巨人・坂本がサヨナラホームラン。「{long_quote}」と発言した。",
                "source_family": "hochi",
                "game_id": "2026-05-14",
                "player_name": "坂本勇人",
            },
            {
                "post_url": "https://www.sponichi.co.jp/baseball/news/x.html",
                "title": "巨人・坂本勇人がサヨナラ３ラン！通算300号でチーム逆転勝利",
                "summary": "サヨナラホームランで決着した試合の見出し抜粋テキスト。",
                "body": "スポニチ本文。",
                "source_family": "sponichi",
                "game_id": "2026-05-14",
                "player_name": "坂本勇人",
            },
            {
                "post_url": "https://www.nikkansports.com/baseball/news/x.html",
                "title": "巨人坂本勇人サヨナラ３ラン通算300号メモリアル弾で逆転勝利",
                "summary": "サヨナラホームランで決着した試合の見出し抜粋テキスト。",
                "body": "日刊スポーツ本文。",
                "source_family": "nikkansports",
                "game_id": "2026-05-14",
                "player_name": "坂本勇人",
            },
        ]
        clusters = find_digest_clusters(candidates)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].parent_family, "hochi")
        self.assertEqual(clusters[0].hochi_raw_html_excerpt, "")  # clusterer は populate しない


if __name__ == "__main__":
    unittest.main()
