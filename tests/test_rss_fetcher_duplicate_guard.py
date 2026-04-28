import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


class CaptureLogs:
    def __init__(self, logger_name: str):
        self.logger = logging.getLogger(logger_name)
        self.messages: list[str] = []
        self.handler = logging.Handler()
        self.handler.emit = self._emit  # type: ignore[method-assign]

    def _emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())

    def __enter__(self) -> list[str]:
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)
        return self.messages

    def __exit__(self, exc_type, exc, tb) -> None:
        self.logger.removeHandler(self.handler)


def _make_context(
    *,
    source_url: str = "https://news.hochi.news/articles/2026/04/28/example.html",
    title: str = "【巨人】阿部監督がコメント",
    summary: str = "阿部監督が試合後にコメントした。",
    category: str = "首脳陣",
    source_type: str = "news",
    has_game: bool = False,
    source_entry: dict | None = None,
    published_at: datetime | None = None,
) -> dict:
    context = rss_fetcher._build_duplicate_news_context(
        source_url=source_url,
        title=title,
        summary=summary,
        category=category,
        source_type=source_type,
        has_game=has_game,
        source_entry=source_entry or {},
        source_name="スポーツ報知",
        published_at=published_at,
    )
    assert context is not None
    return context


def test_duplicate_news_pre_gemini_skip_emitted_for_exact_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "duplicate.jsonl"
        ledger = rss_fetcher._DuplicateNewsLedger(ledger_path=ledger_path, cooldown_hours=6)
        context = _make_context()
        ledger.record(
            duplicate_key=context["duplicate_key"],
            group_signature=context["group_signature"],
            source_url_hash="primaryhash000001",
            source_family=context["source_family"],
            source_family_priority=context["source_family_priority"],
            title_norm=context["title_norm"],
            subtype=context["subtype"],
            post_id=777,
            primary=True,
            canonical_present=False,
            body_length=context["body_length"],
            published_at=context["published_at"],
            match_basis=context["match_basis"],
        )
        with patch.object(rss_fetcher._DuplicateNewsLedger, "shared", return_value=ledger):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini") as generate_mock:
                    with patch.object(
                        rss_fetcher,
                        "_resolve_article_ai_strategy",
                        return_value=(True, "首脳陣", "category_enabled"),
                    ):
                        with patch.dict(
                            "os.environ",
                            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "首脳陣", "ARTICLE_AI_MODE": "gemini"},
                            clear=False,
                        ):
                            with CaptureLogs("rss_fetcher") as messages:
                                blocks, ai_body = rss_fetcher.build_news_block(
                                    title="【巨人】阿部監督がコメント",
                                    summary="阿部監督が試合後にコメントした。",
                                    url="https://news.hochi.news/articles/2026/04/28/example.html",
                                    source_name="スポーツ報知",
                                    category="首脳陣",
                                    has_game=False,
                                    article_ai_mode_override="gemini",
                                    duplicate_guard_context=context,
                                )
        generate_mock.assert_not_called()
        assert blocks == ""
        assert ai_body == ""
        assert any('"event": "duplicate_news_pre_gemini_skip"' in message for message in messages)


def test_candidate_duplicate_review_emitted_for_ambiguous():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "duplicate.jsonl"
        ledger = rss_fetcher._DuplicateNewsLedger(ledger_path=ledger_path, cooldown_hours=6)
        current = _make_context(
            source_url="https://news.hochi.news/articles/2026/04/28/example.html",
        )
        existing = _make_context(
            source_url="https://www.sponichi.co.jp/baseball/news/2026/04/28/kiji.html",
        )
        ledger.record(
            duplicate_key=existing["duplicate_key"],
            group_signature=existing["group_signature"],
            source_url_hash="existinghash0001",
            source_family=existing["source_family"],
            source_family_priority=existing["source_family_priority"],
            title_norm=existing["title_norm"],
            subtype=existing["subtype"],
            post_id=778,
            primary=True,
            canonical_present=False,
            body_length=existing["body_length"],
            published_at=existing["published_at"],
            match_basis=existing["match_basis"],
        )
        with patch.object(rss_fetcher._DuplicateNewsLedger, "shared", return_value=ledger):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value="本文です") as generate_mock:
                    with patch.object(
                        rss_fetcher,
                        "_resolve_article_ai_strategy",
                        return_value=(True, "首脳陣", "category_enabled"),
                    ):
                        with patch.dict(
                            "os.environ",
                            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "首脳陣", "ARTICLE_AI_MODE": "gemini"},
                            clear=False,
                        ):
                            with CaptureLogs("rss_fetcher") as messages:
                                _blocks, ai_body = rss_fetcher.build_news_block(
                                    title="【巨人】阿部監督がコメント",
                                    summary="阿部監督が試合後にコメントした。",
                                    url="https://news.hochi.news/articles/2026/04/28/example.html",
                                    source_name="スポーツ報知",
                                    category="首脳陣",
                                    has_game=False,
                                    article_ai_mode_override="gemini",
                                    duplicate_guard_context=current,
                                )
        generate_mock.assert_called_once()
        assert ai_body != ""
        assert any('"event": "candidate_duplicate_review"' in message for message in messages)


def test_record_duplicate_guard_success_preserves_primary_flag():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "duplicate.jsonl"
        ledger = rss_fetcher._DuplicateNewsLedger(ledger_path=ledger_path, cooldown_hours=6)
        current = _make_context()
        current["same_run_primary"] = False
        current["guard_outcome"] = "review"
        with patch.object(rss_fetcher._DuplicateNewsLedger, "shared", return_value=ledger):
            rss_fetcher._record_duplicate_guard_success(current, 901)
        rows = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert '"primary": false' in rows[-1].lower()
        assert '"post_id": 901' in rows[-1]


def test_skip_path_returns_empty_and_skips_gemini():
    context = _make_context()
    context["same_run_group_size"] = 2
    context["same_run_primary"] = False
    context["same_run_primary_source_url_hash"] = "primaryhash000001"
    context["same_run_primary_post_id"] = 88
    context["same_run_ambiguous"] = False
    with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
        with patch.object(rss_fetcher, "generate_article_with_gemini") as generate_mock:
            with patch.object(
                rss_fetcher,
                "_resolve_article_ai_strategy",
                return_value=(True, "首脳陣", "category_enabled"),
            ):
                with patch.dict(
                    "os.environ",
                    {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "首脳陣", "ARTICLE_AI_MODE": "gemini"},
                    clear=False,
                ):
                    blocks, ai_body = rss_fetcher.build_news_block(
                        title="【巨人】阿部監督がコメント",
                        summary="阿部監督が試合後にコメントした。",
                        url="https://news.hochi.news/articles/2026/04/28/example.html",
                        source_name="スポーツ報知",
                        category="首脳陣",
                        has_game=False,
                        article_ai_mode_override="gemini",
                        duplicate_guard_context=context,
                    )
    generate_mock.assert_not_called()
    assert blocks == ""
    assert ai_body == ""


def test_duplicate_review_time_gap_for_player_subtype():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "duplicate.jsonl"
        ledger = rss_fetcher._DuplicateNewsLedger(ledger_path=ledger_path, cooldown_hours=6)
        current_published = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
        existing_published = current_published - timedelta(hours=7)
        current = _make_context(
            title="【巨人】岡本和真が一軍合流",
            summary="岡本和真が一軍に合流した。",
            category="選手情報",
            published_at=current_published,
            source_url="https://news.hochi.news/articles/2026/04/28/example.html",
        )
        existing = _make_context(
            title="【巨人】岡本和真が一軍合流",
            summary="岡本和真が一軍に合流した。",
            category="選手情報",
            published_at=existing_published,
            source_url="https://www.sponichi.co.jp/baseball/news/2026/04/28/kiji.html",
        )
        ledger.record(
            duplicate_key=existing["duplicate_key"],
            group_signature=existing["group_signature"],
            source_url_hash="existinghash0002",
            source_family=existing["source_family"],
            source_family_priority=existing["source_family_priority"],
            title_norm=existing["title_norm"],
            subtype=existing["subtype"],
            post_id=779,
            primary=True,
            canonical_present=False,
            body_length=existing["body_length"],
            published_at=existing_published.isoformat(),
            player=existing["player"],
            match_basis=existing["match_basis"],
            now=current_published,
        )
        with patch.object(rss_fetcher._DuplicateNewsLedger, "shared", return_value=ledger):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value="本文です") as generate_mock:
                    with patch.object(
                        rss_fetcher,
                        "_resolve_article_ai_strategy",
                        return_value=(True, "選手情報", "category_enabled"),
                    ):
                        with patch.dict(
                            "os.environ",
                            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "選手情報", "ARTICLE_AI_MODE": "gemini"},
                            clear=False,
                        ):
                            with CaptureLogs("rss_fetcher") as messages:
                                rss_fetcher.build_news_block(
                                    title="【巨人】岡本和真が一軍合流",
                                    summary="岡本和真が一軍に合流した。",
                                    url="https://news.hochi.news/articles/2026/04/28/example.html",
                                    source_name="スポーツ報知",
                                    category="選手情報",
                                    has_game=False,
                                    article_ai_mode_override="gemini",
                                    duplicate_guard_context=current,
                                )
        generate_mock.assert_called_once()
        assert any('"ambiguity_reason": "player_subtype_match_time_gap"' in message for message in messages)
