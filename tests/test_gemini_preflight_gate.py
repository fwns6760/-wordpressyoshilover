from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher
from src.gemini_cache import GeminiCacheManager
from src.gemini_preflight_gate import (
    PREFLIGHT_ENV_FLAG,
    PREFLIGHT_SKIP_LAYER,
    emit_gemini_call_skipped,
    should_skip_gemini,
)


NOW = datetime(2026, 4, 30, 12, 0, tzinfo=timezone(timedelta(hours=9)))


def _build_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger(f"test_gemini_preflight.{id(stream)}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    return logger, stream


def _log_events(stream: io.StringIO) -> list[dict]:
    events: list[dict] = []
    for raw_line in stream.getvalue().splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _candidate(**overrides) -> dict:
    base = {
        "title": "【巨人】阿部監督が継投の狙いを説明",
        "summary": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
        "body_text": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
        "source_body": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
        "category": "首脳陣",
        "article_subtype": "manager",
        "source_name": "スポーツ報知",
        "source_url": "https://news.hochi.news/articles/example.html",
        "source_type": "news",
        "source_links": [],
        "published_at": NOW - timedelta(hours=1),
        "duplicate_guard_context": {},
    }
    base.update(overrides)
    return base


def _seed_cache(
    manager: GeminiCacheManager,
    *,
    source_url: str,
    content_text: str,
    prompt_template_id: str,
    generated_text: str,
    now: datetime,
) -> None:
    cache_key = rss_fetcher._build_gemini_cache_key(
        source_url=source_url,
        content_text=content_text,
        prompt_template_id=prompt_template_id,
    )
    manager.save(cache_key, generated_text, now=now)


class GeminiPreflightGateTests(unittest.TestCase):
    def test_default_off_never_skips_matching_candidates(self):
        cases = [
            _candidate(existing_publish_same_source_url=True),
            _candidate(article_subtype="live_update"),
            _candidate(
                title="巨人OBが意識不明の重体",
                summary="巨人OBが意識不明の重体となった。",
                body_text="巨人OBが意識不明の重体となった。",
                source_body="巨人OBが意識不明の重体となった。",
            ),
            _candidate(
                title="ヤクルトが阪神に勝利",
                summary="ヤクルトが阪神に勝利した。",
                body_text="ヤクルトが阪神に勝利した。",
                source_body="ヤクルトが阪神に勝利した。",
                source_name="スポーツ報知",
                source_url="https://news.hochi.news/articles/opponent.html",
            ),
        ]
        with patch.dict(os.environ, {PREFLIGHT_ENV_FLAG: "0", "ENABLE_LIVE_UPDATE_ARTICLES": "0"}, clear=False):
            for candidate in cases:
                with self.subTest(candidate=candidate["title"]):
                    self.assertEqual(should_skip_gemini(candidate, now=NOW), (False, None))

    def test_skip_reasons_when_flag_on(self):
        cases = [
            ("existing_publish_same_source_url", _candidate(existing_publish_same_source_url=True)),
            (
                "placeholder_body",
                _candidate(
                    article_subtype="postgame",
                    title="【巨人】試合結果を整理",
                    summary="詳細はこちら",
                    body_text="詳細はこちら",
                    source_body="詳細はこちら",
                ),
            ),
            (
                "not_giants_related",
                _candidate(
                    title="ヤクルトが阪神に勝利",
                    summary="ヤクルトが阪神に勝利した。",
                    body_text="ヤクルトが阪神に勝利した。",
                    source_body="ヤクルトが阪神に勝利した。",
                    source_name="スポーツ報知",
                    source_url="https://news.hochi.news/articles/opponent.html",
                ),
            ),
            ("live_update_target_disabled", _candidate(article_subtype="live_update")),
            (
                "farm_lineup_backlog_blocked",
                _candidate(
                    title="巨人二軍スタメン発表",
                    summary="巨人二軍のスタメンが発表された。若手の並びを確認したい。",
                    body_text="巨人二軍のスタメンが発表された。若手の並びを確認したい。",
                    source_body="巨人二軍のスタメンが発表された。若手の並びを確認したい。",
                    category="ドラフト・育成",
                    article_subtype="farm_lineup",
                    published_at=NOW - timedelta(hours=8),
                ),
            ),
            (
                "farm_result_age_exceeded",
                _candidate(
                    title="巨人二軍 4-2 楽天 試合結果",
                    summary="巨人二軍が楽天に4-2で勝利した。投打の流れを確認できる試合だった。",
                    body_text="巨人二軍が楽天に4-2で勝利した。投打の流れを確認できる試合だった。",
                    source_body="巨人二軍が楽天に4-2で勝利した。投打の流れを確認できる試合だった。",
                    category="ドラフト・育成",
                    article_subtype="farm_result",
                    published_at=NOW - timedelta(hours=25),
                ),
            ),
            (
                "unofficial_source_only",
                _candidate(
                    title="【巨人】ファン反応まとめ",
                    summary="巨人ファンが試合後の空気を語っている。",
                    body_text="巨人ファンが試合後の空気を語っている。",
                    source_body="巨人ファンが試合後の空気を語っている。",
                    source_name="random account",
                    source_type="social_news",
                    source_url="https://x.com/random_account/status/1",
                    source_links=[],
                ),
            ),
            (
                "expected_hard_stop_death_or_grave",
                _candidate(
                    title="巨人OBが意識不明の重体",
                    summary="巨人OBが意識不明の重体となった。",
                    body_text="巨人OBが意識不明の重体となった。",
                    source_body="巨人OBが意識不明の重体となった。",
                    article_subtype="injury",
                ),
            ),
        ]
        with patch.dict(os.environ, {PREFLIGHT_ENV_FLAG: "1", "ENABLE_LIVE_UPDATE_ARTICLES": "0"}, clear=False):
            for expected_reason, candidate in cases:
                with self.subTest(expected_reason=expected_reason):
                    self.assertEqual(should_skip_gemini(candidate, now=NOW), (True, expected_reason))

    def test_publishable_fixtures_pass_when_flag_on(self):
        cases = [
            _candidate(
                title="巨人スタメン発表 坂本勇人が3番",
                summary="巨人のスタメンが発表され、坂本勇人が3番に入った。",
                body_text="巨人のスタメンが発表され、坂本勇人が3番に入った。",
                source_body="巨人のスタメンが発表され、坂本勇人が3番に入った。",
                category="試合速報",
                article_subtype="lineup",
            ),
            _candidate(
                title="巨人二軍スタメン発表",
                summary="巨人二軍のスタメンが発表され、若手の並びが確認できた。",
                body_text="巨人二軍のスタメンが発表され、若手の並びが確認できた。",
                source_body="巨人二軍のスタメンが発表され、若手の並びが確認できた。",
                category="ドラフト・育成",
                article_subtype="farm_lineup",
                published_at=NOW - timedelta(hours=1),
            ),
            _candidate(
                title="巨人二軍 4-2 楽天 試合結果",
                summary="巨人二軍が楽天に4-2で勝利した。24時間以内の結果記事として扱える。",
                body_text="巨人二軍が楽天に4-2で勝利した。24時間以内の結果記事として扱える。",
                source_body="巨人二軍が楽天に4-2で勝利した。24時間以内の結果記事として扱える。",
                category="ドラフト・育成",
                article_subtype="farm_result",
                published_at=NOW - timedelta(hours=23, minutes=30),
            ),
            _candidate(
                title="【巨人】ファン反応の整理",
                summary="巨人ファンの反応を整理しつつ、スポーツ報知の元記事も確認した。",
                body_text="巨人ファンの反応を整理しつつ、スポーツ報知の元記事も確認した。",
                source_body="巨人ファンの反応を整理しつつ、スポーツ報知の元記事も確認した。",
                source_name="random account",
                source_type="social_news",
                source_url="https://x.com/random_account/status/2",
                source_links=[{"url": "https://news.hochi.news/articles/authoritative.html"}],
            ),
        ]
        with patch.dict(os.environ, {PREFLIGHT_ENV_FLAG: "1", "ENABLE_LIVE_UPDATE_ARTICLES": "0"}, clear=False):
            for candidate in cases:
                with self.subTest(title=candidate["title"]):
                    self.assertEqual(should_skip_gemini(candidate, now=NOW), (False, None))

    def test_emit_gemini_call_skipped_logs_expected_payload(self):
        logger, stream = _build_logger()
        emit_gemini_call_skipped(
            logger,
            candidate={
                "post_url": "https://example.com/post",
                "source_url_hash": "abc123",
                "content_hash": "def456",
                "article_subtype": "farm_result",
            },
            skip_reason="farm_result_age_exceeded",
        )
        events = _log_events(stream)
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0],
            {
                "event": "gemini_call_skipped",
                "post_url": "https://example.com/post",
                "source_url_hash": "abc123",
                "content_hash": "def456",
                "subtype": "farm_result",
                "skip_reason": "farm_result_age_exceeded",
                "skip_layer": PREFLIGHT_SKIP_LAYER,
            },
        )

    def test_gemini_text_with_cache_skips_before_cache_lookup(self):
        logger, stream = _build_logger()
        candidate_meta = _candidate(
            article_subtype="farm_result",
            existing_publish_same_source_url=True,
            summary="巨人二軍が楽天に4-2で勝利した。投打の流れを確認できる試合だった。",
            body_text="巨人二軍が楽天に4-2で勝利した。投打の流れを確認できる試合だった。",
            source_body="巨人二軍が楽天に4-2で勝利した。投打の流れを確認できる試合だった。",
        )
        with patch.dict(os.environ, {PREFLIGHT_ENV_FLAG: "1"}, clear=False):
            with patch.object(rss_fetcher, "_gemini_cache_lookup", side_effect=AssertionError("cache lookup should not run")) as mock_lookup:
                with patch.object(
                    rss_fetcher,
                    "_request_gemini_strict_text",
                    side_effect=AssertionError("Gemini request should not run"),
                ) as mock_request:
                    text, telemetry = rss_fetcher._gemini_text_with_cache(
                        api_key="api-key",
                        prompt="PROMPT",
                        logger=logger,
                        attempt_limit=3,
                        min_chars=1,
                        source_url="https://example.com/farm-result",
                        content_text="本文A",
                        prompt_template_id="prompt-v1",
                        cache_manager=object(),
                        candidate_meta=candidate_meta,
                        now=NOW,
                        log_label="test",
                    )

        self.assertEqual(text, "")
        self.assertFalse(telemetry["gemini_call_made"])
        self.assertEqual(telemetry["cache_hit_reason"], "preflight_skip")
        self.assertEqual(telemetry["skip_reason"], "existing_publish_same_source_url")
        self.assertEqual(telemetry["skip_layer"], PREFLIGHT_SKIP_LAYER)
        mock_lookup.assert_not_called()
        mock_request.assert_not_called()
        events = _log_events(stream)
        self.assertEqual([event["event"] for event in events], ["gemini_call_skipped"])

    def test_cache_hit_path_remains_unchanged_when_preflight_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = GeminiCacheManager(state_manager=None, local_cache_dir=Path(tmpdir) / "gemini-cache")
            _seed_cache(
                manager,
                source_url="https://example.com/a",
                content_text="本文A",
                prompt_template_id="prompt-v1",
                generated_text="cached text",
                now=NOW - timedelta(hours=1),
            )
            logger, stream = _build_logger()
            with patch.dict(os.environ, {PREFLIGHT_ENV_FLAG: "1"}, clear=False):
                with patch.object(
                    rss_fetcher,
                    "_request_gemini_strict_text",
                    side_effect=AssertionError("Gemini request should not run on cache hit"),
                ) as mock_request:
                    text, telemetry = rss_fetcher._gemini_text_with_cache(
                        api_key="api-key",
                        prompt="PROMPT",
                        logger=logger,
                        attempt_limit=3,
                        min_chars=1,
                        source_url="https://example.com/a",
                        content_text="本文A",
                        prompt_template_id="prompt-v1",
                        cache_manager=manager,
                        candidate_meta=_candidate(
                            title="【巨人】阿部監督が語る",
                            summary="巨人が勝利し、阿部監督が狙いを語った。具体的なポイントも整理できる。",
                            body_text="巨人が勝利し、阿部監督が狙いを語った。具体的なポイントも整理できる。",
                            source_body="巨人が勝利し、阿部監督が狙いを語った。具体的なポイントも整理できる。",
                            source_url="https://example.com/a",
                        ),
                        now=NOW,
                        log_label="test",
                    )

        self.assertEqual(text, "cached text")
        self.assertTrue(telemetry["cache_hit"])
        self.assertEqual(telemetry["cache_hit_reason"], "content_hash_exact")
        self.assertFalse(telemetry["gemini_call_made"])
        mock_request.assert_not_called()
        events = _log_events(stream)
        self.assertEqual(events[-1]["event"], "gemini_cache_lookup")
        self.assertEqual(events[-1]["cache_hit_reason"], "content_hash_exact")

    def test_build_news_block_preflight_skip_still_returns_safe_fallback(self):
        duplicate_guard_context = {"existing_publish_same_source_url": True}
        with patch.dict(
            os.environ,
            {PREFLIGHT_ENV_FLAG: "1", "GEMINI_API_KEY": "api-key", "ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "strict_fact_mode_enabled", return_value=True):
                with patch.object(rss_fetcher, "_postgame_strict_enabled", return_value=True):
                    with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                        with patch.object(
                            rss_fetcher,
                            "_request_gemini_strict_text",
                            side_effect=AssertionError("Gemini request should not run on preflight skip"),
                        ):
                            with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                                blocks, ai_body = rss_fetcher.build_news_block(
                                    title="【巨人】阪神に3-2で勝利 岡本が決勝打",
                                    summary="巨人が阪神に3-2で勝利し、岡本和真が決勝打を放った。",
                                    url="https://example.com/postgame",
                                    source_name="スポーツ報知",
                                    category="試合速報",
                                    has_game=True,
                                    published_at=NOW - timedelta(hours=1),
                                    duplicate_guard_context=duplicate_guard_context,
                                )

        self.assertNotEqual(blocks, "")
        self.assertNotEqual(ai_body, "")
        self.assertIn("【試合結果】", ai_body)
        self.assertIn("<h2>【試合結果】</h2>", blocks)

    def test_scope_tokens_do_not_expand_beyond_ticket_contract(self):
        module_text = Path(rss_fetcher.ROOT / "src" / "gemini_preflight_gate.py").read_text(encoding="utf-8")
        self.assertEqual(PREFLIGHT_ENV_FLAG, "ENABLE_GEMINI_PREFLIGHT")
        for token in ("Team Shiny From", "canonical", "301", "ENABLE_X_POST_FOR_", "scheduler"):
            with self.subTest(token=token):
                self.assertNotIn(token, module_text)


if __name__ == "__main__":
    unittest.main()
