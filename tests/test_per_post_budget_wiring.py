from __future__ import annotations

from src import rss_fetcher


def _build_candidate_meta(**overrides):
    payload = {
        "title": "【巨人】阿部監督が継投の狙いを説明",
        "summary": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
        "category": "首脳陣",
        "article_subtype": "manager",
        "source_name": "スポーツ報知",
        "source_url": "https://news.hochi.news/articles/example.html",
        "source_type": "news",
        "has_game": True,
    }
    payload.update(overrides)
    return rss_fetcher._build_gemini_preflight_candidate_meta(**payload)


def test_candidate_meta_includes_post_id_when_available():
    meta = _build_candidate_meta(
        post_context={
            "post_id": "123",
            "wp_post_id": 456,
            "id": "789",
            "history_urls": ["https://news.hochi.news/articles/example.html"],
        }
    )

    assert meta["post_id"] == 123
    assert meta["wp_post_id"] == 456
    assert meta["id"] == 789


def test_candidate_meta_graceful_when_post_id_missing():
    meta = _build_candidate_meta(
        source_entry=None,
        post_context=None,
    )

    assert "post_id" not in meta
    assert "wp_post_id" not in meta
    assert "id" not in meta


def test_resolve_cache_metric_post_id_finds_injected_post_id():
    post_context = {
        "history_urls": ["https://baseball.yahoo.co.jp/npb/game/2026050101/top#postgame"],
        "post_url": "https://baseball.yahoo.co.jp/npb/game/2026050101/top",
        "entry_title_norm": "巨人試合結果阪神に30で勝利",
    }
    meta = _build_candidate_meta(
        title="【巨人試合結果】阪神に3-0で勝利",
        summary="巨人が阪神に3-0で勝利した。",
        category="試合速報",
        article_subtype="postgame",
        source_name="Yahoo!プロ野球 試合結果",
        source_url="https://baseball.yahoo.co.jp/npb/game/2026050101/top",
        source_entry={"link": "https://baseball.yahoo.co.jp/npb/game/2026050101/top"},
        post_context=post_context,
    )
    second_meta = _build_candidate_meta(
        title="【巨人試合結果】阪神に3-0で勝利",
        summary="巨人が阪神に3-0で勝利した。",
        category="試合速報",
        article_subtype="postgame",
        source_name="Yahoo!プロ野球 試合結果",
        source_url="https://baseball.yahoo.co.jp/npb/game/2026050101/top",
        source_entry={"link": "https://baseball.yahoo.co.jp/npb/game/2026050101/top"},
        post_context=post_context,
    )

    assert isinstance(meta["post_id"], int)
    assert meta["post_id"] > 0
    assert meta["post_id"] == second_meta["post_id"]
    assert rss_fetcher._resolve_cache_metric_post_id(meta) == meta["post_id"]
