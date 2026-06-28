"""Tests for the YOSHILOVER Giants news candidate mail lane."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.tools import finance_news_sns_candidates as fnc
from src.tools import yoshilover_news_candidates as ync


JST = ZoneInfo("Asia/Tokyo")


RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>上原浩治氏が巨人の若手投手に言及 - スポーツ紙</title>
      <link>https://news.google.com/rss/articles/CBMiTEST?oc=5</link>
      <description>巨人OBのYouTube発言</description>
      <pubDate>Sun, 28 Jun 2026 00:15:00 GMT</pubDate>
    </item>
    <item>
      <title>巨人 登録抹消を発表</title>
      <link>https://example.test/notice</link>
      <description>公示</description>
      <pubDate>Sun, 28 Jun 2026 01:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class YoshiloverNewsCandidateTests(unittest.TestCase):
    def test_google_news_title_is_not_rewritten_and_url_can_resolve(self) -> None:
        source = fnc.FinanceSource(
            id="gnews_uehara",
            name="Googleニュース: 上原浩治 巨人",
            market="JP",
            kind="rss",
            url="https://news.google.com/rss/search?q=x",
            priority="P1",
            post_lane="ob",
            score_base=74,
        )
        item = ync.fnc._items_from_feed_text(source, RSS_SAMPLE)[0]
        stats = ync.YoshiNewsBuildStats(loaded_sources=1)
        with patch.object(ync, "is_google_news_url", return_value=True), patch.object(
            ync, "resolve_google_news_url", return_value="https://example.test/uehara"
        ):
            cand = ync._candidate_from_item(
                source,
                item,
                timeout_seconds=1,
                resolve_google_news=True,
                stats=stats,
            )

        self.assertEqual(cand.title, "上原浩治氏が巨人の若手投手に言及 - スポーツ紙")
        self.assertEqual(cand.media, "スポーツ紙")
        self.assertEqual(cand.url, "https://example.test/uehara")
        self.assertEqual(cand.category, "OBネタ")
        self.assertEqual(cand.relation_person, "上原浩治")
        self.assertEqual(stats.resolved_google_news, 1)

    def test_notice_routes_to_x_candidate(self) -> None:
        source = fnc.FinanceSource(
            id="notice",
            name="公示ソース",
            market="JP",
            kind="rss",
            url="https://example.test/rss",
            priority="P1",
            post_lane="notice",
            score_base=70,
        )
        item = ync.fnc._items_from_feed_text(source, RSS_SAMPLE)[1]
        cand = ync._candidate_from_item(
            source,
            item,
            timeout_seconds=1,
            resolve_google_news=False,
            stats=ync.YoshiNewsBuildStats(loaded_sources=1),
        )
        self.assertEqual(cand.category, "X候補")
        self.assertIn("速報性", cand.reason)

    def test_generic_ob_query_does_not_force_unrelated_item_to_ob(self) -> None:
        source = fnc.FinanceSource(
            id="gnews_ob",
            name="Googleニュース: 巨人 OB",
            market="JP",
            kind="rss",
            url="https://news.google.com/rss/search?q=x",
            priority="P1",
            post_lane="ob",
            score_base=74,
            tags=("巨人 OB",),
        )
        item = {
            "title": "巨人・小笠原慎之介、移籍後初登板で3回1失点",
            "url": "https://example.test/ogasawara",
            "summary": "",
            "published": "",
        }
        cand = ync._candidate_from_item(
            source,
            item,
            timeout_seconds=1,
            resolve_google_news=False,
            stats=ync.YoshiNewsBuildStats(loaded_sources=1),
        )
        self.assertNotEqual(cand.category, "OBネタ")

    def test_dave_youtube_source_is_ob_candidate_even_when_title_lacks_name(self) -> None:
        source = fnc.FinanceSource(
            id="yt_dave",
            name="デーブ大久保チャンネル",
            market="JP",
            kind="rss",
            url="https://www.youtube.com/feeds/videos.xml?channel_id=UCKa1VlSq1WwdSQWv4JFdgxg",
            priority="P1",
            post_lane="youtube_ob",
            score_base=68,
        )
        item = {
            "title": "打線について語ります",
            "url": "https://www.youtube.com/watch?v=abc123",
            "summary": "",
            "published": "",
        }
        cand = ync._candidate_from_item(
            source,
            item,
            timeout_seconds=1,
            resolve_google_news=False,
            stats=ync.YoshiNewsBuildStats(loaded_sources=1),
        )
        self.assertEqual(cand.category, "OBネタ")
        self.assertEqual(cand.relation_person, "デーブ大久保")

    def test_weekly_prime_dave_article_is_ob_with_caution(self) -> None:
        source = fnc.FinanceSource(
            id="gnews_dave",
            name="Googleニュース: デーブ大久保 巨人",
            market="JP",
            kind="rss",
            url="https://news.google.com/rss/search?q=x",
            priority="P0",
            post_lane="ob",
            score_base=92,
            tags=("デーブ大久保 巨人",),
        )
        item = {
            "title": "巨人OB・デーブ大久保「浦田？ 知らない」勉強不足すぎるYouTube配信に「評論家返上して」名スコアラー・志田宗大も呆れ顔 | 週刊女性PRIME",
            "url": "https://www.jprime.jp/articles/-/42331?display=b",
            "summary": "",
            "published": "Sun, 28 Jun 2026 00:00:00 GMT",
        }
        cand = ync._candidate_from_item(
            source,
            item,
            timeout_seconds=1,
            resolve_google_news=False,
            stats=ync.YoshiNewsBuildStats(loaded_sources=1),
        )
        self.assertEqual(cand.category, "OBネタ")
        self.assertEqual(cand.relation_person, "デーブ大久保")
        self.assertIn("週刊誌", cand.caution)

    def test_okamoto_mlb_news_is_article_candidate_without_giants_word(self) -> None:
        source = fnc.FinanceSource(
            id="gnews_okamoto_mlb",
            name="Googleニュース: 岡本和真 MLB",
            market="JP",
            kind="rss",
            url="https://news.google.com/rss/search?q=x",
            priority="P0",
            post_lane="mlb_alumni",
            score_base=88,
            tags=("岡本和真 MLB",),
        )
        item = {
            "title": "岡本和真がメジャーで決勝本塁打、現地メディアも称賛",
            "url": "https://example.test/okamoto-mlb",
            "summary": "",
            "published": "",
        }
        cand = ync._candidate_from_item(
            source,
            item,
            timeout_seconds=1,
            resolve_google_news=False,
            stats=ync.YoshiNewsBuildStats(loaded_sources=1),
        )
        self.assertEqual(cand.category, "記事化候補")
        self.assertIn("現MLB動向", cand.reason)
        self.assertEqual(cand.relation_person, "岡本和真")

    def test_sugano_english_mlb_news_is_article_candidate(self) -> None:
        source = fnc.FinanceSource(
            id="gnews_sugano_en",
            name="Googleニュース: Tomoyuki Sugano MLB",
            market="JP",
            kind="rss",
            url="https://news.google.com/rss/search?q=x",
            priority="P0",
            post_lane="mlb_alumni",
            score_base=86,
            tags=("Tomoyuki Sugano MLB",),
        )
        item = {
            "title": "Tomoyuki Sugano sharp again as rotation stabilizes",
            "url": "https://example.test/sugano-mlb",
            "summary": "",
            "published": "",
        }
        cand = ync._candidate_from_item(
            source,
            item,
            timeout_seconds=1,
            resolve_google_news=False,
            stats=ync.YoshiNewsBuildStats(loaded_sources=1),
        )
        self.assertEqual(cand.category, "記事化候補")
        self.assertIn("Tomoyuki Sugano", cand.relation_person)

    def test_build_candidates_dedupes_url_and_title_signature(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            config = tmp / "sources.json"
            ledger = tmp / "ledger.jsonl"
            config.write_text(
                json.dumps(
                    {
                        "scoring": {"dedupe_window_hours": 168, "include_excluded": True},
                        "sources": [
                            {
                                "id": "rss",
                                "name": "テストRSS",
                                "url": "https://example.test/rss.xml",
                                "kind": "rss",
                                "lane": "general",
                                "score_base": 70,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            now = datetime(2026, 6, 28, 9, 0, tzinfo=JST)
            with patch.object(fnc, "_http_get", return_value=RSS_SAMPLE):
                first = ync.build_candidates(
                    source_path=config,
                    now=now,
                    ledger_path=ledger,
                    resolve_google_news=False,
                    max_candidates=10,
                )
            self.assertGreaterEqual(len(first.candidates), 1)
            ync.append_ledger(first.candidates, now=now, ledger_path=ledger)

            with patch.object(fnc, "_http_get", return_value=RSS_SAMPLE):
                second = ync.build_candidates(
                    source_path=config,
                    now=now,
                    ledger_path=ledger,
                    resolve_google_news=False,
                    max_candidates=10,
                )
            self.assertEqual(second.candidates, [])
            self.assertGreaterEqual(second.stats.deduped_items, 1)

    def test_compose_mail_has_required_sections_and_top3(self) -> None:
        now = datetime(2026, 6, 28, 12, 0, tzinfo=JST)
        candidates = [
            ync.YoshiNewsCandidate(
                source_id="a",
                source_name="s",
                title="巨人の若手特集",
                media="媒体A",
                url="https://example.test/a",
                published="2026-06-28 11:00",
                category="記事化候補",
                reason="YOSHILOVERで独自コメントや考察を足しやすい素材のため。",
                score=90,
                title_signature="a",
            ),
            ync.YoshiNewsCandidate(
                source_id="b",
                source_name="s",
                title="デーブ大久保氏がYouTubeで巨人を語る",
                media="YouTube",
                url="https://example.test/b",
                published="2026-06-28 11:05",
                category="OBネタ",
                reason="デーブ大久保の発言として話題化しやすいため。",
                relation_person="デーブ大久保",
                score=95,
                title_signature="b",
            ),
        ]
        subject, text, html = ync.compose_mail(
            candidates,
            now=now,
            stats=ync.YoshiNewsBuildStats(loaded_sources=2, raw_items=2, scored_items=2),
        )
        self.assertEqual(subject, "【YOSHILOVER】巨人ニュース候補：2026-06-28 12")
        for heading in ["■ 記事化候補", "■ X候補", "■ OBネタ", "■ 週刊誌・一般紙", "■ 要確認"]:
            self.assertIn(heading, text)
        self.assertIn("【記事化候補】", text)
        self.assertIn("【OBネタ】", text)
        self.assertIn("今日のおすすめ上位3件", text)
        self.assertIn("自動公開・X自動投稿もしません", text)
        self.assertIn("原典を開く", html)


if __name__ == "__main__":
    unittest.main()
