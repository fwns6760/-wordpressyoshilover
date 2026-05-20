"""OB (元巨人) name table and literal marker helpers for ticket 408.

Phase 1 (2026-05-20):
- Primary gate = literal marker (`元巨人` / `巨人OB` / `古巣巨人` / `巨人時代` 等) in title
- Name table is defined for Phase 2 use; Phase 1 classifier does NOT consume it
- This avoids false-positives where a current 巨人 staff member is mentioned

Inclusion criteria for OB_NAME_SEED:
- 巨人 在籍歴 あり
- 現在 巨人 組織に属さない (player / coach / manager / staff いずれも)
- 公開記事に登場し得る (解説者 / 引退 / 戦没 含む)

Exclusion (MUST NOT be added in Phase 1, current 巨人 staff):
- 阿部慎之助 (監督)
- 桑田真澄 (二軍監督)
- 杉内俊哉 (一軍投手コーチ)
- 元木大介 / 川相昌弘 / 村田修一 等 (兼任の可能性ある OB は Phase 2 で context 判定追加)
- 全現役 NPB 巨人選手

Phase 2 で context judge を追加し、 「OB だが現在 巨人 兼任」のケースも
誤判定しないように、 name_table 経路は marker 経路より strict にする。

See: docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md §4
"""

from __future__ import annotations


OB_NAME_SEED: frozenset[str] = frozenset({
    # 引退 / 解説者 / メディア露出中
    "高橋由伸",
    "上原浩治",
    "江川卓",
    "槙原寛己",
    "中畑清",
    "駒田徳広",
    "清原和博",
    "鈴木尚広",
    "西本聖",
    "矢野謙次",
    "内海哲也",
    "木佐貫洋",
    "松井秀喜",
    "仁志敏久",
    # 名誉職 / 元監督
    "長嶋茂雄",
    "王貞治",
    # MLB OB (see project_mlb_player_inclusion_policy)
    "菅野智之",
    # legacy
    "沢村栄治",
})


OB_LITERAL_MARKERS: tuple[str, ...] = (
    "元巨人",
    "元読売",
    "巨人OB",
    "巨人O.B.",
    "読売OB",
    "古巣・巨人",
    "古巣巨人",
    "巨人時代",
    "巨人だった",
    "ジャイアンツOB",
)


def has_ob_literal_marker(text: str) -> bool:
    """Phase 1 primary gate: literal marker による OB 確定判定.

    text に OB_LITERAL_MARKERS のいずれかが含まれていれば True。
    title 単体への適用を想定 (summary だけに含まれる場合は OB 主題ではないことが多い)。
    """
    if not text:
        return False
    return any(marker in text for marker in OB_LITERAL_MARKERS)


def is_known_ob_name(name: str) -> bool:
    """name table に登録済みかを返す."""
    if not name:
        return False
    return name.strip() in OB_NAME_SEED


# Phase 2 で current 巨人 staff context を除外するための marker
# (OB 名簿に含まれている人物が記事中で現巨人スタッフ扱いされている場合は OB override を見送る)
_CURRENT_GIANTS_ROLE_GUARDS: tuple[str, ...] = (
    "巨人監督",
    "巨人新監督",
    "巨人ヘッドコーチ",
    "巨人投手コーチ",
    "巨人打撃コーチ",
    "巨人内野守備走塁コーチ",
    "巨人外野守備走塁コーチ",
    "巨人バッテリーコーチ",
    "巨人二軍監督",
    "巨人三軍監督",
    "巨人 監督",
    "ジャイアンツ監督",
    "現巨人",
)


def has_known_ob_name(text: str) -> bool:
    """Phase 2 secondary gate: text 内に OB_NAME_SEED の名前が含まれているか.

    OB literal marker (primary gate) と合わせて使う。 primary が hit しない時の
    補強判定。 false-positive 抑制のため `_CURRENT_GIANTS_ROLE_GUARDS` (巨人監督 /
    巨人◯◯コーチ 等) が同 text に共存している場合は False を返す
    (OB 名簿の人物が現巨人スタッフとして言及されている文脈は OB override 対象外)。
    """
    if not text:
        return False
    if any(guard in text for guard in _CURRENT_GIANTS_ROLE_GUARDS):
        return False
    return any(name in text for name in OB_NAME_SEED)
