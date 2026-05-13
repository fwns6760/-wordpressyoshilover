"""Tests for src.event_key_ledger — read-only audit ledger.

Covers:
  * classify_event_type for every keyword bucket
  * attribute_game_date morning-after rule
  * opponent inference + game-context filter
  * group_records produces a single game_result group with the expected
    parent/hero/children/standalone shape for the 2026-05-12 サヨナラHR fixture
"""

from __future__ import annotations

import datetime as dt

import pytest

from src import event_key_ledger as m


# ─── classify_event_type ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "title,expected",
    [
        # walk-off HR (parent of game_result)
        ("【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ", "walk_off_hr_result"),
        # walk-off without HR keyword
        ("巨人が今季初のサヨナラ勝ち！ 佐々木が中崎から岐阜の夜空にサヨナラ2ラン", "walk_off_hr_result"),
        # manager quote
        ("阿部監督「バントはないよって」", "manager_quote"),
        # player quote (allowlist player + bracket)
        ("佐々木俊輔「最高です！ もう、気持ちよかったです」", "player_quote"),
        # video link — walk_off keyword wins when present
        ("【動画】佐々木俊輔が劇的初サヨナラ弾！", "walk_off_hr_result"),
        # YouTube without サヨナラ keyword → video_link
        ("【YouTube】強気な阿部采配…バントより強攻！応えた佐々木俊輔がすごかった", "video_link"),
        # lineup
        ("巨人スタメン 試合終", "lineup_post"),
        ("巨人広島戦 当日カードの試合前情報", "lineup_pre"),
        # スタメン prefix even with サヨナラ keyword → lineup
        ("巨人スタメン 今季初の劇的サヨナラ勝ち！１番・平山功太が初猛打賞", "lineup_pre"),
        # standalone-intent overrides スタメン
        ("【番記者Ｇ戦記】左対左のスタメン起用に佐々木俊輔が応える", "standalone_lane"),
        # record compare
        ("【巨人記録室】今季地方3連勝中、佐々木俊輔が2度決勝打 4月22日の前橋以来", "record_compare"),
        # standings impact
        ("【巨人】劇的サヨナラ勝利も4位後退の珍現象", "walk_off_result"),  # サヨナラ wins
        # plain other
        ("中田翔氏が愛車公開", "other"),
    ],
)
def test_classify_event_type(title: str, expected: str) -> None:
    assert m.classify_event_type(title) == expected


# ─── attribute_game_date ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "iso,expected",
    [
        ("2026-05-12T21:15:51", "2026-05-12"),
        ("2026-05-13T04:30:50", "2026-05-12"),  # morning-after → previous day
        ("2026-05-13T09:59:59", "2026-05-12"),
        ("2026-05-13T10:00:00", "2026-05-13"),  # cutoff
        ("2026-05-13T14:00:00", "2026-05-13"),
    ],
)
def test_attribute_game_date(iso: str, expected: str) -> None:
    assert m.attribute_game_date(iso) == expected


def test_window_close_for() -> None:
    close = m.window_close_for("2026-05-12")
    assert close.year == 2026
    assert close.month == 5
    assert close.day == 13
    assert close.hour == 10
    assert close.tzinfo == m.JST


# ─── giants-game-context filter ─────────────────────────────────────────────


def _make_record(post_id: int, title: str, *, published_at: str = "2026-05-12T20:00:00") -> m.PostRecord:
    return m.post_to_record({
        "id": post_id,
        "date": published_at,
        "title": {"rendered": title},
        "categories": [],
        "link": f"https://yoshilover.com/{post_id}",
    })


def test_has_giants_game_context_excludes_two_gun() -> None:
    rec = _make_record(1, "【巨人】二軍ＤｅＮＡ戦で完封勝利 貯金")
    assert not m.has_giants_game_context(rec)


def test_has_giants_game_context_excludes_ob_suffix() -> None:
    rec = _make_record(2, "中田翔氏が愛車公開 反響")
    assert not m.has_giants_game_context(rec)


def test_has_giants_game_context_excludes_tsuitou() -> None:
    rec = _make_record(3, "終身名誉監督「長嶋茂雄追悼展」 関連")
    assert not m.has_giants_game_context(rec)


def test_has_giants_game_context_passes_with_giants_keyword() -> None:
    rec = _make_record(4, "【巨人】今季初のサヨナラ勝ち")
    assert m.has_giants_game_context(rec)


def test_has_giants_game_context_passes_with_allowlist_player() -> None:
    rec = _make_record(5, "佐々木俊輔「最高です」")
    assert m.has_giants_game_context(rec)


# ─── opponent inference ─────────────────────────────────────────────────────


def test_infer_per_day_opponent_picks_first_non_empty() -> None:
    recs = [
        _make_record(1, "巨人広島戦 当日カードの試合前情報", published_at="2026-05-12T10:00:00"),
        _make_record(2, "【巨人】今季初のサヨナラ勝ち", published_at="2026-05-12T21:15:00"),  # no opp
    ]
    opp_map = m.infer_per_day_opponent(recs)
    assert opp_map.get("2026-05-12") == "hiroshima"


def test_fill_inferred_opponents_only_fills_giants_game_context() -> None:
    recs = [
        _make_record(1, "巨人広島戦 当日カードの試合前情報", published_at="2026-05-12T10:00:00"),
        _make_record(2, "【巨人】今季初のサヨナラ勝ち", published_at="2026-05-12T21:15:00"),
        _make_record(3, "中田翔氏が愛車公開 反響", published_at="2026-05-12T22:00:00"),
        _make_record(4, "【巨人】二軍ＤｅＮＡ戦 貯金", published_at="2026-05-12T17:00:00"),
    ]
    out = m.fill_inferred_opponents(recs)
    # rec1: explicit opponent stays
    assert out[0].opponent == "hiroshima"
    # rec2: inferred to hiroshima (game_result)
    assert out[1].opponent == "hiroshima"
    # rec3: OB suffix excludes inference
    assert out[2].opponent == ""
    # rec4: 二軍 excludes inference
    assert out[3].opponent == ""


# ─── group_records full pipeline on the 5/12 fixture subset ──────────────────


def _build_fixture_records() -> list[m.PostRecord]:
    """Minimal subset of 5/12 posts that captures parent + key children
    + standalone for the 佐々木 walk-off HR event_key."""
    raw = [
        # Pre-game lineup with explicit opponent → seeds opponent inference
        (66603, "2026-05-12T19:45:24", "【一軍】巨人 vs 広島 ぎふしん長良川球場 18時試合開始"),
        # Same-time core articles (anchor selection should prefer the one with player)
        (66663, "2026-05-12T21:15:34", "巨人スタメン 今季初の劇的サヨナラ勝ち！１番・平山功太が初猛打賞"),
        (66667, "2026-05-12T21:15:47", "【巨人】ライデル・マルティネスを同点の９回に投入　１回０封でサヨナラ勝ちにつなげた"),
        (66669, "2026-05-12T21:15:51", "【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ「最高でーす"),
        (66677, "2026-05-12T21:30:49", "巨人が今季初のサヨナラ勝ち！ 佐々木が中崎から岐阜の夜空にサヨナラ2ラン"),
        (66704, "2026-05-12T21:45:37", "なぜ？ 巨人が今季初のサヨナラ勝ちも試合前の3位から4位に後退"),
        (66712, "2026-05-12T22:00:38", "阿部監督「バントはないよって」"),
        (66665, "2026-05-12T21:15:43", "【番記者Ｇ戦記】左対左のスタメン起用に佐々木俊輔が応える 課題の左腕対策"),
        # Next-morning roundup
        (66721, "2026-05-13T04:30:50", "📺YouTube公開📺 ジョージが決めた！🐵自身初サヨナラHRで劇的勝利！🎉"),
        (66754, "2026-05-13T06:01:19", "佐々木俊輔「最高です！ もう、気持ちよかったです」"),
        (66766, "2026-05-13T06:01:53", "【巨人記録室】今季地方3連勝中、佐々木俊輔が2度決勝打 4月22日の前橋以来"),
        (66783, "2026-05-13T07:01:42", "【動画】佐々木俊輔が劇的初サヨナラ弾！"),
        # Unrelated noise that must NOT enter the group
        (66700, "2026-05-12T21:33:00", "中田翔氏が愛車公開 反響"),
        (66565, "2026-05-12T18:00:00", "【巨人】二軍ＤｅＮＡ戦で貯金6"),
    ]
    return [_make_record(pid, title, published_at=ts) for pid, ts, title in raw]


def test_group_records_picks_player_anchor_over_empty_player() -> None:
    records = _build_fixture_records()
    # Freeze "now" to before window close so status=open
    groups = m.group_records(
        records,
        now=dt.datetime(2026, 5, 13, 8, 0, tzinfo=m.JST),
    )
    game_results = [g for g in groups if g["kind"] == "game_result"]
    assert len(game_results) == 1
    gr = game_results[0]
    assert gr["hero_player"] == "佐々木俊輔"
    assert gr["parent_id"] == 66669
    assert gr["event_key"].endswith("|佐々木俊輔|game_result")


def test_group_records_excludes_two_gun_and_ob() -> None:
    records = _build_fixture_records()
    groups = m.group_records(records, now=dt.datetime(2026, 5, 13, 8, 0, tzinfo=m.JST))
    gr = next(g for g in groups if g["kind"] == "game_result")
    child_ids = {c["post_id"] for c in gr["children"]}
    standalone_ids = {s["post_id"] for s in gr["standalone"]}
    assert 66700 not in child_ids  # OB news
    assert 66565 not in child_ids  # 二軍 game
    assert 66700 not in standalone_ids
    assert 66565 not in standalone_ids


def test_group_records_axis_coverage() -> None:
    records = _build_fixture_records()
    groups = m.group_records(records, now=dt.datetime(2026, 5, 13, 8, 0, tzinfo=m.JST))
    gr = next(g for g in groups if g["kind"] == "game_result")
    cov = gr["axis_coverage"]
    assert cov["result_summary"] == 1
    assert cov["manager_quote"] >= 1
    assert cov["player_quote"] >= 1
    assert cov["youtube_video"] >= 1
    assert cov["standings_impact"] >= 1
    assert cov["morning_column"] >= 1  # 番記者 in standalone counts
    assert cov["instagram_post"] == 0
    assert cov["fan_voice_x_post"] == 0


def test_group_records_window_status_open_before_cutoff() -> None:
    records = _build_fixture_records()
    groups = m.group_records(records, now=dt.datetime(2026, 5, 13, 9, 0, tzinfo=m.JST))
    gr = next(g for g in groups if g["kind"] == "game_result")
    assert gr["window"]["status"] == "open"


def test_group_records_window_status_closed_after_cutoff() -> None:
    records = _build_fixture_records()
    groups = m.group_records(records, now=dt.datetime(2026, 5, 13, 10, 0, 1, tzinfo=m.JST))
    gr = next(g for g in groups if g["kind"] == "game_result")
    assert gr["window"]["status"] == "closed"


def test_group_records_standalone_record_compare_kept_separate() -> None:
    records = _build_fixture_records()
    groups = m.group_records(records, now=dt.datetime(2026, 5, 13, 8, 0, tzinfo=m.JST))
    gr = next(g for g in groups if g["kind"] == "game_result")
    sa_ids = {s["post_id"] for s in gr["standalone"]}
    assert 66766 in sa_ids  # 巨人記録室 record_compare
    assert 66665 in sa_ids  # 番記者G戦記 standalone_lane


# ─── render_enriched_preview ────────────────────────────────────────────────


def test_render_enriched_preview_contains_axes_section() -> None:
    records = _build_fixture_records()
    groups = m.group_records(records, now=dt.datetime(2026, 5, 13, 8, 0, tzinfo=m.JST))
    gr = next(g for g in groups if g["kind"] == "game_result")
    md = m.render_enriched_preview(gr)
    assert "## 完成チェックリスト" in md
    assert "✅ result_summary" in md
    assert "❌ instagram_post" in md
    assert "佐々木俊輔" in md
    assert "66669" in md
