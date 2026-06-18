"""sync_player_class_from_roster の plan / dump ロジック検証。"""

import json

from src.tools import sync_player_class_from_roster as sync


def _empty_class():
    return {
        "_source": "test",
        "_updated": "2026-01-01",
        "_note": "test",
        "shihai": {"投手": ["既存投手"], "捕手": [], "内野手": [], "外野手": []},
        "ikusei": {"投手": [], "捕手": [], "内野手": [], "外野手": []},
    }


def test_clean_position_is_added():
    roster = [
        {"name": "小笠原慎之介", "aliases": ["小笠原慎之介", "小笠原 慎之介"],
         "role": "player", "position": "投手", "active": True},
    ]
    additions, unresolved = sync.plan(roster, _empty_class())
    assert ("小笠原慎之介", "shihai", "投手") in additions
    assert unresolved == []


def test_position_field_maps_to_bucket():
    roster = [
        {"name": "岡本和真", "role": "player", "position": "内野手", "active": True},
        {"name": "長野久義", "role": "player", "position": "外野手", "active": True},
    ]
    additions, _ = sync.plan(roster, _empty_class())
    assert ("岡本和真", "shihai", "内野手") in additions
    assert ("長野久義", "shihai", "外野手") in additions


def test_ambiguous_dasha_is_unresolved_not_guessed():
    roster = [{"name": "梶原昂希", "role": "player", "position": "打者", "active": True}]
    additions, unresolved = sync.plan(roster, _empty_class())
    assert additions == []
    assert unresolved and unresolved[0][0] == "梶原昂希"


def test_ikusei_without_position_is_unresolved():
    roster = [{"name": "育成太郎", "role": "ikusei", "position": "", "active": True}]
    additions, unresolved = sync.plan(roster, _empty_class())
    assert additions == []
    assert unresolved and unresolved[0][0] == "育成太郎"


def test_alias_match_prevents_duplicate():
    # alias "既存投手" が既に分類済みなので、別表記 canonical でも追加しない
    roster = [
        {"name": "Ｆ．既存投手", "aliases": ["Ｆ．既存投手", "既存投手"],
         "role": "player", "position": "投手", "active": True},
    ]
    additions, unresolved = sync.plan(roster, _empty_class())
    assert additions == []
    assert unresolved == []


def test_manager_coach_skipped():
    roster = [
        {"name": "監督さん", "role": "manager", "position": "監督", "active": True},
        {"name": "コーチさん", "role": "coach", "position": "", "active": True},
    ]
    additions, unresolved = sync.plan(roster, _empty_class())
    assert additions == []
    assert unresolved == []


def test_inactive_skipped():
    roster = [{"name": "引退太郎", "role": "player", "position": "投手", "active": False}]
    additions, unresolved = sync.plan(roster, _empty_class())
    assert additions == []
    assert unresolved == []


def test_idempotent():
    roster = [{"name": "新投手", "role": "player", "position": "投手", "active": True}]
    pc = _empty_class()
    additions, _ = sync.plan(roster, pc)
    sync.apply_additions(pc, additions)
    # 2 回目は追加ゼロ
    additions2, _ = sync.plan(roster, pc)
    assert additions2 == []


def test_dump_roundtrip_fidelity():
    """実 config を読み、無変更で dump したら byte 一致 (最小差分保証)。"""
    raw = sync.CLASS_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert sync._dump(data) == raw


def test_apply_updates_timestamp():
    pc = _empty_class()
    sync.apply_additions(pc, [("X", "shihai", "投手")], updated="2026-06-18")
    assert pc["_updated"] == "2026-06-18"
    assert "X" in pc["shihai"]["投手"]
