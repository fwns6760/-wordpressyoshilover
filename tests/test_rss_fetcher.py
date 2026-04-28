import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def test_compute_duplicate_key_canonical_url_priority():
    first = rss_fetcher.compute_duplicate_key(
        source_url="https://example.com/story-a",
        canonical_url="https://example.com/canonical/123",
        title="【巨人】阿部監督がコメント",
        source_family="hochi",
        game_id="2026042801",
        player="阿部慎之助",
        subtype="manager",
    )
    second = rss_fetcher.compute_duplicate_key(
        source_url="https://another.example.com/story-b",
        canonical_url="https://example.com/canonical/123",
        title="【巨人】別タイトル",
        source_family="sponichi",
        game_id="different",
        player="岡本和真",
        subtype="player",
    )
    assert first == second


def test_compute_duplicate_key_game_id_subtype_fallback():
    first = rss_fetcher.compute_duplicate_key(
        source_url="https://example.com/a",
        canonical_url="",
        title="巨人が阪神に勝利",
        source_family="hochi",
        game_id="2026042801",
        subtype="postgame",
    )
    second = rss_fetcher.compute_duplicate_key(
        source_url="https://example.com/b",
        canonical_url="",
        title="別タイトル",
        source_family="sponichi",
        game_id="2026042801",
        subtype="postgame",
    )
    assert first == second


def test_compute_duplicate_key_player_subtype_fallback():
    first = rss_fetcher.compute_duplicate_key(
        source_url="https://example.com/a",
        canonical_url="",
        title="【巨人】岡本和真が復帰へ",
        source_family="hochi",
        player="岡本和真",
        subtype="player",
    )
    second = rss_fetcher.compute_duplicate_key(
        source_url="https://example.com/b",
        canonical_url="",
        title="【巨人】岡本和真が復帰へ",
        source_family="sponichi",
        player="岡本和真",
        subtype="player",
    )
    assert first == second


def test_compute_duplicate_key_title_family_fallback():
    first = rss_fetcher.compute_duplicate_key(
        source_url="https://news.hochi.news/articles/1",
        canonical_url="",
        title="【巨人】阿部監督がコメント",
        source_family="hochi",
        subtype="manager",
    )
    second = rss_fetcher.compute_duplicate_key(
        source_url="https://www.sponichi.co.jp/baseball/news/1",
        canonical_url="",
        title="【巨人】阿部監督がコメント",
        source_family="sponichi",
        subtype="manager",
    )
    assert first != second


def test_normalize_title_full_to_half_width():
    assert rss_fetcher._normalize_title_for_dedupe("【巨人】ＡＢＣ１２３　大城卓三") == "巨人 abc123 大城卓三"


def test_normalize_title_punctuation_collapse():
    assert rss_fetcher._normalize_title_for_dedupe("【巨人】阿部監督…「行くぞ！！」") == "巨人 阿部監督 行くぞ"


def test_extract_source_family_uses_source_trust():
    assert (
        rss_fetcher._extract_source_family("https://news.hochi.news/articles/2026/04/28/example.html")
        == "hochi"
    )


def test_extract_source_family_falls_back_to_host():
    assert rss_fetcher._extract_source_family("https://example.org/story") == "example.org"


def test_primary_source_selected_by_source_trust_family_priority():
    candidates = [
        {
            "entry_index": 1,
            "source_rank": 2,
            "source_name": "Yahoo",
            "source_type": "news",
            "entry": {},
            "post_url": "https://news.yahoo.co.jp/articles/abc",
            "raw_title": "【巨人】阿部監督がコメント",
            "title": "【巨人】阿部監督がコメント",
            "category": "首脳陣",
            "summary": "阿部監督がコメントした。",
            "entry_has_game": False,
            "published_at": datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc),
        },
        {
            "entry_index": 2,
            "source_rank": 3,
            "source_name": "スポーツ報知",
            "source_type": "news",
            "entry": {},
            "post_url": "https://news.hochi.news/articles/def",
            "raw_title": "【巨人】阿部監督がコメント",
            "title": "【巨人】阿部監督がコメント",
            "category": "首脳陣",
            "summary": "阿部監督がコメントした。詳細もある。",
            "entry_has_game": False,
            "published_at": datetime(2026, 4, 28, 12, 5, tzinfo=timezone.utc),
        },
    ]
    annotated = rss_fetcher._annotate_duplicate_guard_contexts(candidates)
    yahoo_ctx = annotated[0]["duplicate_guard_context"]
    hochi_ctx = annotated[1]["duplicate_guard_context"]
    assert yahoo_ctx["same_run_primary"] is False
    assert hochi_ctx["same_run_primary"] is True


def test_ledger_cooldown_expires_after_n_hours():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "duplicate.jsonl"
        old_ts = datetime(2026, 4, 28, 0, 0, tzinfo=timezone.utc)
        payload = {
            "timestamp": old_ts.isoformat(),
            "duplicate_key": "abc123",
            "group_signature": "title:abc",
            "source_url_hash": "hash1",
            "source_family": "hochi",
            "source_family_priority": 2,
            "title_norm": "abc",
            "subtype": "manager",
            "post_id": 1,
            "primary": True,
            "canonical_present": False,
            "body_length": 120,
            "published_at": old_ts.isoformat(),
            "player": "",
            "game_id": "",
            "topic_key": "",
            "match_basis": "title_family",
        }
        ledger_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        ledger = rss_fetcher._DuplicateNewsLedger(
            ledger_path=ledger_path,
            cooldown_hours=6,
            now=old_ts + timedelta(hours=7),
        )
        assert ledger.find_recent("abc123", "title:abc") is None


def test_ledger_in_process_memory_first():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "duplicate.jsonl"
        ledger = rss_fetcher._DuplicateNewsLedger(ledger_path=ledger_path, cooldown_hours=6)
        ledger.record(
            duplicate_key="abc123",
            group_signature="title:abc",
            source_url_hash="hash1",
            source_family="hochi",
            source_family_priority=2,
            title_norm="abc",
            subtype="manager",
            post_id=10,
            primary=True,
            canonical_present=False,
            body_length=100,
            published_at=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc).isoformat(),
            match_basis="title_family",
        )
        hit = ledger.find_recent("abc123", "title:abc")
        assert hit is not None
        assert hit["post_id"] == 10


def test_lineup_dedupe_path_unchanged():
    candidate = {
        "entry_index": 1,
        "source_rank": 1,
        "source_name": "スポーツ報知",
        "source_type": "news",
        "entry": {},
        "post_url": "https://news.hochi.news/articles/lineup",
        "raw_title": "【巨人】今日のスタメン発表 1番丸 4番岡本",
        "title": "【巨人】今日のスタメン発表 1番丸 4番岡本",
        "category": "試合速報",
        "summary": "巨人がスタメンを発表した。",
        "entry_has_game": True,
        "published_at": datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc),
    }
    assert rss_fetcher._build_duplicate_news_context_from_prepared_entry(candidate) is None


def test_log_payload_no_full_url_no_body_no_secret():
    with CaptureLogs("rss_fetcher") as messages:
        rss_fetcher._emit_duplicate_news_structured(
            logging.getLogger("rss_fetcher"),
            event="duplicate_news_pre_gemini_skip",
            duplicate_key="abc123def4567890",
            skipped_source_url_hash="feedfacefeedface",
            primary_source_url_hash="deadbeefdeadbeef",
            primary_post_id=42,
            title_norm="巨人 阿部監督 コメント",
            subtype="manager",
            source_family="hochi",
        )
    payload = json.loads(messages[0])
    assert "source_url" not in payload
    assert "body" not in payload
    assert "prompt" not in payload
    assert "api_key" not in payload
    assert "https://news.hochi.news/" not in messages[0]


def test_rule_based_subtype_allowlist_filters_non_permitted_values(monkeypatch):
    monkeypatch.setenv("RULE_BASED_SUBTYPES", "default,lineup,postgame,program,notice,farm")

    assert rss_fetcher._rule_based_subtype_allowlist() == frozenset({"lineup", "program", "notice"})
    assert rss_fetcher._should_use_rule_based("default") is False
    assert rss_fetcher._should_use_rule_based("postgame") is False
    assert rss_fetcher._should_use_rule_based("farm") is False


def test_rule_based_skip_log_payload_no_full_url_no_body_no_secret(caplog):
    with caplog.at_level(logging.INFO, logger="rss_fetcher"):
        rss_fetcher._log_rule_based_subtype_skip_gemini(
            logging.getLogger("rss_fetcher"),
            subtype="lineup",
            source_url="https://news.hochi.news/articles/example-lineup",
            input_chars=321,
            output_chars=654,
        )

    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "rule_based_subtype_skip_gemini"
    assert payload["subtype"] == "lineup"
    assert payload["saved_gemini_calls"] == 3
    assert payload["source_url_hash"]
    assert "source_url" not in payload
    assert "body" not in payload
    assert "prompt" not in payload
    assert "api_key" not in payload
