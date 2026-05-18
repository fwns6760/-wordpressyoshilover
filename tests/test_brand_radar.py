from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from src import brand_radar
from src.tools import run_brand_radar_mail


JST = brand_radar.JST


def _topic(
    title: str,
    *,
    source_name: str = "日刊巨人",
    source_type: str = "news",
    hours_old: float = 1.0,
    source_priority: int = 10,
    topic_type: str = "fresh_news",
    base_score: float | None = None,
) -> brand_radar.FreshArticleTopic:
    now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
    score = base_score
    if score is None:
        score = brand_radar._base_score(
            freshness_hours=hours_old,
            source_pri=source_priority,
            topic_type=topic_type,
            magazine_context=brand_radar._is_magazine_source(source_name),
        )
    return brand_radar.FreshArticleTopic(
        title=title,
        url=f"https://example.test/{abs(hash(title))}",
        source_name=source_name,
        source_type=source_type,
        summary="巨人のニュース",
        published_at=now - timedelta(hours=hours_old),
        observed_at=now,
        topic_type=topic_type,
        freshness_hours=hours_old,
        source_priority=source_priority,
        base_score=score,
    )


@dataclass
class FakeXSearchClient:
    signals: list[brand_radar.XSearchSignal]
    calls: int = 0

    def search(
        self,
        topic: brand_radar.FreshArticleTopic,
        *,
        now: datetime,
    ) -> brand_radar.XSearchSignal:
        self.calls += 1
        if self.signals:
            return self.signals.pop(0)
        return brand_radar.XSearchSignal(
            query=brand_radar.build_x_search_query(topic),
            from_date="2026-05-17",
            to_date="2026-05-18",
            status="x_search_empty",
            attempted=True,
        )


class BrandRadarTopicTests(unittest.TestCase):
    def test_fresh_article_candidates_outrank_data_only_candidates(self) -> None:
        fresh = _topic("巨人・若手が一軍合流", hours_old=1, source_priority=10)
        data_only = _topic(
            "巨人データ候補 OPS",
            source_name="insight.db",
            source_type="data",
            hours_old=1,
            source_priority=90,
            base_score=25,
        )

        ordered = brand_radar.sort_topics_for_branding([data_only, fresh])

        self.assertEqual(ordered[0], fresh)

    def test_official_x_is_lower_priority_than_article_sources(self) -> None:
        official = _topic(
            "巨人公式Xの新着",
            source_name="巨人公式X",
            source_type="social_news",
            source_priority=80,
            base_score=40,
        )
        newspaper = _topic(
            "巨人・阿部監督が起用を説明",
            source_name="読売新聞オンライン プロ野球",
            source_type="tag_scrape",
            source_priority=15,
        )

        ordered = brand_radar.sort_topics_for_branding([official, newspaper])

        self.assertEqual(ordered[0], newspaper)

    def test_collect_topics_records_visible_skip_reasons(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        sources = [{"name": "一般RSS", "type": "news", "url": "https://example.test/feed"}]
        stats = brand_radar.BrandRadarStats()

        topics = brand_radar.collect_fresh_article_topics(
            sources=sources,
            now=now,
            fetch_entries=lambda _source: [
                {"title": "阪神の新ニュース", "link": "https://example.test/a"},
                {"title": "巨人キャンペーン開始", "link": "https://example.test/b"},
            ],
            stats=stats,
        )

        self.assertEqual(topics, [])
        self.assertEqual(stats.skipped_by_reason["non_giants_topic"], 1)
        self.assertEqual(stats.skipped_by_reason["low_value_campaign_or_promo"], 1)

    def test_general_rss_summary_only_giants_hit_is_rejected(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        source = {"name": "ベースボールキング", "type": "news", "url": "https://example.test/feed"}

        topic, reason = brand_radar.topic_from_entry(
            {
                "title": "正捕手放出。DeNAに見るチーム作りの難しさ",
                "link": "https://example.test/dena",
                "summary": "巨人の動きにも通じる話題",
            },
            source,
            now=now,
        )

        self.assertIsNone(topic)
        self.assertEqual(reason, "non_giants_topic")

    def test_giants_specific_source_accepts_title_without_keyword(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        source = {"name": "Full-Count 巨人", "type": "news", "url": "https://example.test/feed"}

        topic, reason = brand_radar.topic_from_entry(
            {
                "title": "坂本勇人が必要なワケ",
                "link": "https://example.test/sakamoto",
                "summary": "守備の存在感",
            },
            source,
            now=now,
        )

        self.assertIsNotNone(topic)
        self.assertEqual(reason, "")


class BrandRadarPlanTests(unittest.TestCase):
    def test_x_search_cited_result_is_visible_in_mail_fixture(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        signal = brand_radar.XSearchSignal(
            query="巨人 阿部監督 起用",
            from_date="2026-05-17",
            to_date="2026-05-18",
            status="x_search_cited",
            summary="起用への期待と不安が並んでいる",
            evidence_urls=("https://x.com/fan/status/1",),
            usage={"server_side_tool_usage": {"x_search": 1}},
            attempted=True,
        )
        fake = FakeXSearchClient([signal])

        result = brand_radar.build_brand_post_plans(
            [_topic("巨人・阿部監督が起用を説明", topic_type="manager")],
            x_search_client=fake,
            now=now,
            max_plans=1,
            x_search_call_cap=3,
        )
        mail = brand_radar.compose_brand_radar_mail(result.plans, now=now, stats=result.stats)

        self.assertIn("ヨシラバー投稿企画案｜巨人ニュース鮮度レーダー", mail.subject)
        self.assertIn("投稿案", mail.text_body)
        self.assertIn("狙い:", mail.text_body)
        self.assertIn("証拠:", mail.text_body)
        self.assertIn("X Search query: 巨人 阿部監督 起用", mail.text_body)
        self.assertIn("https://x.com/fan/status/1", mail.text_body)
        self.assertIn("provider usage", mail.text_body)
        self.assertIn("twitter.com/intent/tweet", mail.text_body)

    def test_x_search_empty_is_not_silently_skipped(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        empty = brand_radar.XSearchSignal(
            query="巨人 若手",
            from_date="2026-05-17",
            to_date="2026-05-18",
            status="x_search_empty",
            attempted=True,
        )
        result = brand_radar.build_brand_post_plans(
            [_topic("巨人・若手が一軍合流")],
            x_search_client=FakeXSearchClient([empty]),
            now=now,
            max_plans=1,
            x_search_call_cap=3,
        )
        mail = brand_radar.compose_brand_radar_mail(result.plans, now=now, stats=result.stats)

        self.assertIn("X Search status: x_search_empty", mail.text_body)
        self.assertIn("X signal unavailable: x_search_empty", mail.text_body)
        self.assertNotIn("ファンが盛り上がっている", mail.text_body)

    def test_cost_guard_enforces_x_search_cap(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        fake = FakeXSearchClient(
            [
                brand_radar.XSearchSignal("q1", "2026-05-17", "2026-05-18", "x_search_empty", attempted=True),
                brand_radar.XSearchSignal("q2", "2026-05-17", "2026-05-18", "x_search_empty", attempted=True),
            ]
        )

        result = brand_radar.build_brand_post_plans(
            [
                _topic("巨人・ニュース1", base_score=100),
                _topic("巨人・ニュース2", base_score=90),
                _topic("巨人・ニュース3", base_score=80),
            ],
            x_search_client=fake,
            now=now,
            max_plans=3,
            x_search_call_cap=2,
        )

        self.assertEqual(fake.calls, 2)
        self.assertEqual(result.stats.x_search_calls_used, 2)
        self.assertEqual(result.plans[2].signal.error_type, "x_search_cap_exceeded")
        self.assertEqual(result.stats.skipped_by_reason["x_search_cap_exceeded"], 1)

    def test_no_x_live_post_or_wp_mutation_strings_in_mail(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        result = brand_radar.build_brand_post_plans(
            [_topic("巨人・若手が一軍合流")],
            x_search_client=FakeXSearchClient([]),
            now=now,
            max_plans=1,
            x_search_call_cap=1,
        )
        mail = brand_radar.compose_brand_radar_mail(result.plans, now=now, stats=result.stats)

        self.assertIn("X自動投稿もWP更新もしません", mail.text_body)
        self.assertIn("twitter.com/intent/tweet", mail.text_body)
        self.assertNotIn("api.twitter.com", mail.text_body + mail.html_body)
        self.assertNotIn("/wp-json/wp/v2/posts", mail.text_body + mail.html_body)


class BrandRadarXAIClientTests(unittest.TestCase):
    def test_http_401_403_are_auth_required_for_premium_or_license_followup(self) -> None:
        self.assertEqual(brand_radar._http_error_type(401), "x_search_auth_required")
        self.assertEqual(brand_radar._http_error_type(403), "x_search_auth_required")

    def test_missing_grok_key_is_visible_error(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        with patch.dict("os.environ", {}, clear=True):
            signal = brand_radar.XAIResponsesXSearchClient().search(
                _topic("巨人・若手が一軍合流"),
                now=now,
            )

        self.assertEqual(signal.status, "x_search_error")
        self.assertEqual(signal.error_type, "missing_api_key")
        self.assertFalse(signal.attempted)

    def test_http_403_from_provider_is_visible_auth_required(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)

        def opener(_request, timeout):
            raise HTTPError("https://api.x.ai/v1/responses", 403, "Forbidden", hdrs=None, fp=None)

        client = brand_radar.XAIResponsesXSearchClient(api_key="dummy", opener=opener)
        signal = client.search(_topic("巨人・若手が一軍合流"), now=now)

        self.assertEqual(signal.status, "x_search_error")
        self.assertEqual(signal.error_type, "x_search_auth_required")
        self.assertTrue(signal.attempted)


class BrandRadarCliTests(unittest.TestCase):
    def test_cli_dry_run_does_not_require_recipient_env(self) -> None:
        now = datetime(2026, 5, 18, 18, 0, tzinfo=JST)
        stats = brand_radar.BrandRadarStats(candidates_sent=0)
        result = brand_radar.BrandRadarRunResult(plans=[], stats=stats)
        with patch.dict("os.environ", {}, clear=True), patch.object(
            run_brand_radar_mail.brand_radar,
            "now_jst",
            return_value=now,
        ), patch.object(
            run_brand_radar_mail.brand_radar,
            "load_brand_sources",
            return_value=[],
        ), patch.object(
            run_brand_radar_mail.brand_radar,
            "build_brand_radar",
            return_value=result,
        ), patch.object(
            run_brand_radar_mail.mdb,
            "send",
            return_value=run_brand_radar_mail.mdb.MailResult(
                status="dry_run",
                refused_recipients={},
                smtp_response=[],
            ),
        ) as send:
            code = run_brand_radar_mail.main([])

        self.assertEqual(code, 0)
        request = send.call_args.args[0]
        self.assertEqual(request.to, ["dry-run@example.test"])
        self.assertFalse(send.call_args.kwargs["dry_run"] is False)


if __name__ == "__main__":
    unittest.main()
