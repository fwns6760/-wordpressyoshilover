from datetime import datetime, timedelta

from src import rss_fetcher


def _today_label() -> str:
    now = datetime.now(rss_fetcher.JST)
    return f"{now.month}月{now.day}日"


def _yesterday_label() -> str:
    then = datetime.now(rss_fetcher.JST) - timedelta(days=1)
    return f"{then.month}月{then.day}日"


def _enable_rule_based(monkeypatch, value: str = "lineup,program,notice") -> None:
    monkeypatch.setenv("RULE_BASED_SUBTYPES", value)


def _sample_lineup_rows() -> list[dict]:
    return [
        {"order": "1", "name": "丸佳浩", "position": "中"},
        {"order": "2", "name": "吉川尚輝", "position": "二"},
        {"order": "3", "name": "坂本勇人", "position": "遊"},
        {"order": "4", "name": "岡本和真", "position": "一"},
    ]


def _lineup_title() -> str:
    return "【巨人】スタメン発表 1番丸 4番岡本 先発山崎伊織"


def _lineup_summary(with_starter: bool = True) -> str:
    starter = "先発は山崎伊織。" if with_starter else ""
    return f"4月28日 18:00 東京ドーム 阪神戦。{starter}巨人がスタメンを発表した。"


def _program_title() -> str:
    return "GIANTS TV「阿部監督インタビュー」4月28日 20:00放送"


def _program_summary(extra: str = "") -> str:
    return f"4月28日 20:00にGIANTS TVで配信。阿部監督が出演する。{extra}".strip()


def _notice_title() -> str:
    return "【巨人】浅野翔吾が一軍登録"


def _notice_summary(extra: str = "") -> str:
    return f"4月28日、浅野翔吾が一軍登録。今季打率.280、2本塁打。東京ドームに合流した。{extra}".strip()


def _call_rule_based_lineup(monkeypatch, **overrides):
    payload = {
        "title": _lineup_title(),
        "summary": _lineup_summary(),
        "generation_category": "試合速報",
        "article_subtype": "lineup",
        "source_url": "https://example.com/lineup",
        "source_day_label": _today_label(),
        "source_type": "news",
        "lineup_rows": _sample_lineup_rows(),
    }
    payload.update(overrides)
    return rss_fetcher._build_rule_based_subtype_body(**payload)


def _call_rule_based_program(monkeypatch, **overrides):
    payload = {
        "title": _program_title(),
        "summary": _program_summary(),
        "generation_category": "球団情報",
        "article_subtype": "general",
        "source_url": "https://example.com/program",
        "source_day_label": _today_label(),
        "source_type": "news",
    }
    payload.update(overrides)
    return rss_fetcher._build_rule_based_subtype_body(**payload)


def _call_rule_based_notice(monkeypatch, **overrides):
    payload = {
        "title": _notice_title(),
        "summary": _notice_summary(),
        "generation_category": "選手情報",
        "article_subtype": "player",
        "special_story_kind": "player_notice",
        "source_url": "https://example.com/notice",
        "source_name": "スポーツ報知",
        "source_day_label": _today_label(),
        "source_type": "news",
    }
    payload.update(overrides)
    return rss_fetcher._build_rule_based_subtype_body(**payload)


def _valid_gemini_lineup_body() -> str:
    return "\n".join(
        [
            "【試合概要】",
            "4月28日 阪神戦です。",
            "【スタメン一覧】",
            "1番 丸佳浩 中。",
            "【先発投手】",
            "山崎伊織です。",
            "【注目ポイント】",
            "初回の入り方を見ます。",
        ]
    )


def test_lineup_rule_based_when_meta_complete(monkeypatch):
    _enable_rule_based(monkeypatch)
    result = _call_rule_based_lineup(monkeypatch)

    assert result is not None
    subtype, body = result
    assert subtype == "lineup"
    assert "【試合概要】" in body
    assert "【スタメン一覧】" in body
    assert "1番 丸佳浩 中" in body
    assert "4番 岡本和真 一" in body


def test_lineup_rule_based_falls_back_when_meta_incomplete(monkeypatch):
    _enable_rule_based(monkeypatch)
    result = _call_rule_based_lineup(
        monkeypatch,
        title="【巨人】スタメン発表",
        summary="4月28日 18:00 東京ドーム 阪神戦。巨人がスタメンを発表した。",
        lineup_rows=[],
    )

    assert result is None


def test_program_rule_based_when_meta_complete(monkeypatch):
    _enable_rule_based(monkeypatch)
    result = _call_rule_based_program(monkeypatch)

    assert result is not None
    subtype, body = result
    assert subtype == "program"
    assert "【番組概要】" in body
    assert "【放送・配信日時】" in body
    assert "GIANTS TV" in body


def test_program_rule_based_requires_schedule_label(monkeypatch):
    _enable_rule_based(monkeypatch)
    result = _call_rule_based_program(
        monkeypatch,
        title="GIANTS TV「阿部監督インタビュー」",
        summary="GIANTS TVで配信。阿部監督が出演する。",
    )

    assert result is None


def test_notice_rule_based_truncates_to_200_chars(monkeypatch):
    _enable_rule_based(monkeypatch)
    long_fact = "浅野翔吾が一軍登録となり、" + ("あ" * 230)
    result = _call_rule_based_notice(
        monkeypatch,
        summary=f"4月28日、{long_fact}。今季打率.280、2本塁打。東京ドームに合流した。",
    )

    assert result is not None
    _subtype, body = result
    long_lines = [line for line in body.splitlines() if "あ" in line]
    assert long_lines
    assert len(long_lines[0]) <= 202
    assert long_lines[0].endswith("…。")


def test_default_subtype_never_uses_rule_based(monkeypatch):
    _enable_rule_based(monkeypatch, "default,lineup,program,notice")

    assert rss_fetcher._should_use_rule_based("default") is False
    assert (
        rss_fetcher._build_rule_based_subtype_body(
            title="巨人イベント情報を更新",
            summary="球団から案内が出た。",
            generation_category="コラム",
            article_subtype="general",
            source_url="https://example.com/default",
        )
        is None
    )


def test_postgame_subtype_never_uses_rule_based(monkeypatch):
    _enable_rule_based(monkeypatch, "postgame,lineup,program,notice")

    assert rss_fetcher._should_use_rule_based("postgame") is False


def test_farm_subtype_never_uses_rule_based(monkeypatch):
    _enable_rule_based(monkeypatch, "farm,lineup,program,notice")

    assert rss_fetcher._should_use_rule_based("farm") is False


def test_subtype_unresolved_uses_gemini_path(monkeypatch):
    _enable_rule_based(monkeypatch)

    result = rss_fetcher._build_rule_based_subtype_body(
        title="巨人ニュース",
        summary="球団がコメントした。",
        generation_category="コラム",
        article_subtype="",
        source_url="https://example.com/other",
        source_type="news",
    )

    assert result is None


def test_feature_flag_off_uses_gemini_path(monkeypatch):
    monkeypatch.delenv("RULE_BASED_SUBTYPES", raising=False)

    result = rss_fetcher._build_rule_based_subtype_body(
        title=_lineup_title(),
        summary=_lineup_summary(),
        generation_category="試合速報",
        article_subtype="lineup",
        source_url="https://example.com/lineup",
        source_day_label=_today_label(),
        source_type="news",
        lineup_rows=_sample_lineup_rows(),
    )

    assert result is None


def test_feature_flag_only_lineup(monkeypatch):
    _enable_rule_based(monkeypatch, "lineup")

    assert _call_rule_based_lineup(monkeypatch, source_url="https://example.com/lineup-only") is not None
    assert _call_rule_based_program(monkeypatch, source_url="https://example.com/program-only") is None
    assert _call_rule_based_notice(monkeypatch, source_url="https://example.com/notice-only") is None


def test_rule_based_body_does_not_include_speculation_phrases(monkeypatch):
    _enable_rule_based(monkeypatch)
    result = _call_rule_based_program(
        monkeypatch,
        summary=_program_summary("次回の構想が期待される。"),
    )

    assert result is not None
    _subtype, body = result
    assert "期待される" not in body
    assert "予想" not in body
    assert "だろう" not in body


def test_rule_based_body_includes_source_url(monkeypatch):
    _enable_rule_based(monkeypatch)
    result = _call_rule_based_notice(monkeypatch, source_url="https://example.com/source-notice")

    assert result is not None
    _subtype, body = result
    assert "https://example.com/source-notice" in body


def test_rule_based_body_no_long_quote(monkeypatch):
    _enable_rule_based(monkeypatch)
    long_fact = "4月28日 20:00にGIANTS TVで配信。" + ("い" * 240)
    result = _call_rule_based_program(
        monkeypatch,
        summary=f"{long_fact} 阿部監督が出演する。",
    )

    assert result is not None
    _subtype, body = result
    assert ("い" * 210) not in body


def test_lineup_old_source_falls_back_to_notice_handling(monkeypatch):
    _enable_rule_based(monkeypatch)
    result = _call_rule_based_lineup(
        monkeypatch,
        source_day_label=_yesterday_label(),
    )

    assert result is None


def test_postgame_with_score_uses_gemini_path(monkeypatch):
    _enable_rule_based(monkeypatch, "lineup,program,notice,postgame")

    result = rss_fetcher._build_rule_based_subtype_body(
        title="巨人が阪神に3-2で勝利",
        summary="終盤の一打が決め手になった。",
        generation_category="試合速報",
        article_subtype="postgame",
        source_url="https://example.com/postgame",
        source_type="news",
    )

    assert result is None


def test_build_news_block_lineup_rule_based_skips_gemini(monkeypatch):
    _enable_rule_based(monkeypatch)
    called = {"gemini": False}

    monkeypatch.setattr(rss_fetcher, "should_use_ai_for_category", lambda _category: True)
    monkeypatch.setattr(rss_fetcher, "fetch_fan_reactions_from_yahoo", lambda *args, **kwargs: [])
    monkeypatch.setattr(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", lambda: _sample_lineup_rows())
    monkeypatch.setattr(rss_fetcher, "_maybe_render_postgame_article_parts", lambda **kwargs: None)
    monkeypatch.setattr(rss_fetcher, "_find_related_posts_for_article", lambda **kwargs: [])
    monkeypatch.setattr(rss_fetcher, "_build_related_posts_section", lambda _posts: "")

    def _fake_generate(*args, **kwargs):
        called["gemini"] = True
        return _valid_gemini_lineup_body()

    monkeypatch.setattr(rss_fetcher, "generate_article_with_gemini", _fake_generate)

    _content, ai_body = rss_fetcher.build_news_block(
        title=_lineup_title(),
        summary=_lineup_summary(),
        url="https://example.com/lineup-build",
        source_name="スポーツ報知",
        category="試合速報",
        has_game=True,
        article_ai_mode_override="gemini",
        source_day_label=_today_label(),
        source_type="news",
    )

    assert called["gemini"] is False
    assert "【試合概要】" in ai_body


def test_build_news_block_lineup_incomplete_calls_gemini(monkeypatch):
    _enable_rule_based(monkeypatch)
    called = {"gemini": False}

    monkeypatch.setattr(rss_fetcher, "should_use_ai_for_category", lambda _category: True)
    monkeypatch.setattr(rss_fetcher, "fetch_fan_reactions_from_yahoo", lambda *args, **kwargs: [])
    monkeypatch.setattr(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", lambda: [])
    monkeypatch.setattr(rss_fetcher, "_maybe_render_postgame_article_parts", lambda **kwargs: None)
    monkeypatch.setattr(rss_fetcher, "_find_related_posts_for_article", lambda **kwargs: [])
    monkeypatch.setattr(rss_fetcher, "_build_related_posts_section", lambda _posts: "")

    def _fake_generate(*args, **kwargs):
        called["gemini"] = True
        return _valid_gemini_lineup_body()

    monkeypatch.setattr(rss_fetcher, "generate_article_with_gemini", _fake_generate)

    rss_fetcher.build_news_block(
        title="【巨人】スタメン発表",
        summary="4月28日 18:00 東京ドーム 阪神戦。巨人がスタメンを発表した。",
        url="https://example.com/lineup-fallback",
        source_name="スポーツ報知",
        category="試合速報",
        has_game=True,
        article_ai_mode_override="gemini",
        source_day_label=_today_label(),
        source_type="news",
    )

    assert called["gemini"] is True
