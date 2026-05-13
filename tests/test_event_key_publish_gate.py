"""Tests for src.event_key_publish_gate — pure decision library.

The gate decides whether a new draft article should be published as a
parent or held as a child, based on event_key co-occurrence with
recently-published articles. No WP I/O.
"""

from __future__ import annotations

from src import event_key_publish_gate as gate


def _post(post_id: int, title: str, *, date: str = "2026-05-12T20:00:00") -> dict:
    return {
        "id": post_id,
        "date": date,
        "title": {"rendered": title},
        "categories": [],
        "link": f"https://yoshilover.com/{post_id}",
    }


def test_publish_when_no_recent_publishes() -> None:
    cand = _post(66669, "【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ", date="2026-05-12T21:15:51")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[])
    assert d.decision == "publish"
    assert d.reason == "first_record_of_event_key"
    assert d.event_subtype == "walk_off"
    assert d.event_player == "佐々木俊輔"


def test_hold_when_same_event_key_already_published() -> None:
    parent = _post(66669, "【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ", date="2026-05-12T21:15:51")
    cand = _post(66677, "巨人が今季初のサヨナラ勝ち！ 佐々木が中崎から岐阜の夜空にサヨナラ2ラン", date="2026-05-12T21:30:49")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[parent])
    assert d.decision == "hold"
    assert d.reason == "parent_exists_same_event_key"
    assert d.existing_parent_id == 66669


def test_generic_quote_absorbs_into_existing_homerun_parent() -> None:
    parent = _post(66589, "【巨人】戸郷翔征に今季初勝利を！女房・大城卓三が先制４号ソロ「風に乗ってくれた」")
    cand = _post(66635, "大城卓三「風に乗ってくれました」", date="2026-05-12T20:30:00")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[parent])
    assert d.decision == "hold"
    assert "generic_absorbs_into" in d.reason
    assert d.existing_parent_id == 66589


def test_generic_alone_publishes_when_no_primary_parent() -> None:
    cand = _post(66712, "阿部監督「バントはないよって」", date="2026-05-12T22:00:38")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[])
    assert d.decision == "publish"
    assert d.event_subtype == "generic"
    # event_player should be 阿部慎之助 (alias-resolved from 監督)
    assert d.event_player == "阿部慎之助"


def test_lineup_pre_always_publishes() -> None:
    sayonara = _post(66669, "【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ", date="2026-05-12T21:15:51")
    cand = _post(66603, "巨人広島戦 当日カードの試合前情報", date="2026-05-12T19:45:24")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[sayonara])
    assert d.decision == "publish"
    assert "non_gateable_subtype" in d.reason


def test_different_event_key_publishes() -> None:
    sasaki = _post(66669, "【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ", date="2026-05-12T21:15:51")
    cand = _post(66589, "【巨人】戸郷翔征に今季初勝利を！女房・大城卓三が先制４号ソロ「風に乗ってくれた」", date="2026-05-12T20:00:00")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[sasaki])
    assert d.decision == "publish"
    # 大城が subject marker で勝つ
    assert d.event_player == "大城卓三"
    assert d.event_subtype == "homerun"


def test_orphan_two_gun_article_publishes() -> None:
    """二軍 articles fail has_giants_game_context → no event_player → always
    publish (gate doesn't hold them since they have no parent to merge
    into)."""
    cand = _post(66565, "【巨人】二軍ＤｅＮＡ戦で貯金6")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[])
    assert d.decision == "publish"
    assert d.event_subtype == "orphan"


def test_manager_with_player_attributes_to_player() -> None:
    """『阿部監督、佐々木の長打力信じ』は佐々木 walk_off に行く（manager
    override）。既存の佐々木サヨナラ parent があれば hold される。"""
    parent = _post(66669, "【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ", date="2026-05-12T21:15:51")
    cand = _post(66760, "「勝負をかけた」巨人・阿部監督、佐々木の長打力信じ「バントはないよ」采配的中で今季初サヨナラ勝ち", date="2026-05-13T06:01:42")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[parent])
    assert d.event_player == "佐々木俊輔"
    assert d.decision == "hold"
    assert d.existing_parent_id == 66669


def test_decision_to_dict_roundtrip() -> None:
    cand = _post(66669, "【巨人】今季初のサヨナラ勝ち！佐々木俊輔", date="2026-05-12T21:15:51")
    d = gate.decide_publish_or_hold(cand, recent_publishes=[])
    body = d.to_dict()
    assert body["decision"] == "publish"
    assert body["event_player"] == "佐々木俊輔"
    assert body["event_subtype"] == "walk_off"
    assert "candidate_post_id" in body
