import json
import unittest
from pathlib import Path

from src import rss_fetcher


RSS_SOURCES_PATH = Path(__file__).resolve().parents[1] / "config" / "rss_sources.json"


def _source_roles_by_name() -> dict[str, set[str]]:
    sources = json.loads(RSS_SOURCES_PATH.read_text(encoding="utf-8"))
    return {
        source["name"]: rss_fetcher._source_roles_from_config(source.get("role"))
        for source in sources
    }


class RssSourceArticlePolicyTests(unittest.TestCase):
    def test_sports_paper_sources_remain_post_sources_but_skip_wp_articles(self):
        roles_by_name = _source_roles_by_name()
        sports_paper_sources = {
            "スポーツ報知巨人班X",
            "日刊スポーツX",
            "日テレスポーツX",
            "スポニチ野球記者X",
            "サンスポ巨人X",
            "日刊巨人班X",
            "デイリー野球X",
            "日刊スポーツ 巨人",
            "スポーツ報知 巨人 tag",
            "デイリー 巨人 index",
            "スポニチ 野球 巨人 filter",
            "サンスポ 巨人 search",
            "中日スポーツ 巨人 search",
        }

        for name in sorted(sports_paper_sources):
            with self.subTest(name=name):
                roles = roles_by_name[name]
                self.assertIn("article_source", roles)
                self.assertIn("wp_article_skip", roles)

    def test_weekly_tabloid_sources_are_wp_article_priority(self):
        roles_by_name = _source_roles_by_name()
        priority_sources = {
            "東スポ巨人担当X",
            "東スポWEB 巨人 label",
            "週刊ベースボールONLINE RSS",
            "FRIDAY ジャイアンツ tag",
            "Smart FLASH 巨人 tag",
            "週刊女性PRIME 巨人 tag",
            "文春オンライン 読売ジャイアンツ",
            "NEWSポストセブン 巨人 search",
            "デイリー新潮 巨人 search",
            "現代ビジネス 巨人 search",
            "アサ芸プラス 巨人 search",
            "日刊SPA! 巨人 search",
        }

        for name in sorted(priority_sources):
            with self.subTest(name=name):
                roles = roles_by_name[name]
                self.assertIn("article_source", roles)
                self.assertIn("wp_article_priority", roles)
                self.assertNotIn("wp_article_skip", roles)

    def test_official_and_straight_news_sources_are_not_accidentally_demoted(self):
        roles_by_name = _source_roles_by_name()
        neutral_sources = {
            # 2026-07-06: 「読売ジャイアンツX」は config 上「巨人公式X」に
            # 改名済のため名称を追従 (存在しない名前は KeyError で subtest error)
            "巨人公式X",
            "読売新聞オンライン プロ野球",
            "日テレNEWS NNN 巨人 tag",
            "産経新聞 巨人 search",
        }

        for name in sorted(neutral_sources):
            with self.subTest(name=name):
                roles = roles_by_name[name]
                self.assertNotIn("wp_article_skip", roles)
                self.assertNotIn("wp_article_priority", roles)

    def test_wp_article_skip_role_only_blocks_wp_article_creation(self):
        source = {
            "type": "social_news",
            "role": ["article_source", "media_quote_pool", "wp_article_skip"],
        }

        self.assertFalse(
            rss_fetcher._should_articleize_source(
                source_type="social_news",
                source=source,
                source_roles=rss_fetcher._source_roles_from_config(source["role"]),
            )
        )

    def test_wp_article_priority_sorts_after_lineup_and_official_video(self):
        general_entry = {
            "source_type": "news",
            "source_roles": ["article_source"],
            "category": "選手情報",
            "title": "【巨人】一般記事",
            "summary": "一般記事の概要。",
            "entry_has_game": False,
        }
        priority_entry = {
            "source_type": "tag_scrape",
            "source_roles": ["article_source", "media_quote_pool", "wp_article_priority"],
            "category": "コラム",
            "title": "巨人の注目選手を週刊誌が報じる",
            "summary": "週刊誌系の記事。",
            "entry_has_game": False,
        }
        official_video_entry = {
            "source_type": "tag_scrape",
            "source_roles": ["media_quote_only", "official_video_source"],
            "category": "試合速報",
            "title": "戸郷翔征投手の今季初勝利に球団カメラが密着",
            "summary": "",
            "entry_has_game": True,
        }
        lineup_entry = {
            "source_type": "news",
            "source_roles": ["article_source"],
            "category": "試合速報",
            "title": "【巨人】今日のスタメン発表 1番丸、4番岡本和",
            "summary": "巨人が阪神戦のスタメンを発表した。",
            "entry_has_game": True,
        }

        prioritized = rss_fetcher._prioritize_prepared_entries_for_creation(
            [general_entry, priority_entry, official_video_entry, lineup_entry]
        )

        self.assertEqual(
            [item["title"] for item in prioritized],
            [
                lineup_entry["title"],
                official_video_entry["title"],
                priority_entry["title"],
                general_entry["title"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
