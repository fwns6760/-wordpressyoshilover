"""Tests for issue #44 follow-up: title "…" truncation 復元.

post 68870 の bug: title="ジャイアンツ球場⚾️ 石塚裕惺…" が出てしまい、
主語+述語が読み取れない。 summary 側に full text があるので、 第一文を
再構成して title に当て直す。 RT prefix と location/emoji 装飾 prefix を
剥がして「player + 動作」を前に出す。

memory feedback_title_clickable_descriptive.md: title は「誰が・何を・literal 引用」
で自立、 末尾 ``…`` 禁則。
"""

from __future__ import annotations

from src.title_seo_polisher import (
    DEFAULT_MAX_TITLE_LENGTH,
    recover_from_trailing_ellipsis,
)


def test_recover_post_68870_actual_case():
    """post 68870 の実 data で復元できる.

    - 末尾 ``…`` truncation を消す (user 不満の核)
    - player name (石塚裕惺) と event (マシン打撃を再開) が両方残る
    - RT prefix は剥がす
    - 第一文 (。！？ で終わる) を採用
    """
    title = "ジャイアンツ球場⚾️ 石塚裕惺…"
    summary = (
        "RT 水上智恵【スポーツ報知・巨人担当】: "
        "ジャイアンツ球場⚾️ 石塚裕惺 選手がマシン打撃を再開しました！"
    )
    recovered = recover_from_trailing_ellipsis(title, summary)
    assert not recovered.endswith("…"), (
        f"復元後も「…」末尾: {recovered!r}"
    )
    assert "石塚裕惺" in recovered, f"player name missing: {recovered!r}"
    assert "マシン打撃を再開" in recovered, f"event token missing: {recovered!r}"
    # RT prefix は剥がれている
    assert not recovered.startswith("RT"), f"RT prefix 残: {recovered!r}"
    assert "水上智恵" not in recovered, f"RT 元 user 名残: {recovered!r}"
    # location/emoji 装飾 prefix も剥がれている
    assert not recovered.startswith("ジャイアンツ球場"), (
        f"location prefix 残: {recovered!r}"
    )


def test_recover_no_ellipsis_returns_original():
    """title が "…" で終わってなければ no-op."""
    title = "石塚裕惺、マシン打撃を再開"
    summary = "別の text"
    assert recover_from_trailing_ellipsis(title, summary) == title


def test_recover_no_summary_returns_original():
    """summary が空なら復元できないので原 title 返す."""
    assert recover_from_trailing_ellipsis("ジャイアンツ球場⚾️ 石塚裕惺…", "") == (
        "ジャイアンツ球場⚾️ 石塚裕惺…"
    )
    assert recover_from_trailing_ellipsis("石塚裕惺…", None) == "石塚裕惺…"


def test_recover_summary_also_truncated_returns_original():
    """summary 第一文も "…" で終わってたら復元不能、 原 title 返す."""
    title = "石塚裕惺…"
    summary = "石塚裕惺がマシン打撃を再…"
    recovered = recover_from_trailing_ellipsis(title, summary)
    # 第一文区切り無 (。！？ どれも無 + …で終わる) → 復元不能 fallback
    assert recovered == title


def test_recover_strips_rt_prefix_from_summary():
    """summary 冒頭の RT prefix は剥がしてから第一文抽出する."""
    title = "報知: 巨人、岡本和真が…"
    summary = (
        "RT @hochi_giants: 報知: 巨人、岡本和真が逆転3ラン本塁打を放った！"
    )
    recovered = recover_from_trailing_ellipsis(title, summary)
    assert not recovered.startswith("RT"), f"RT prefix 残: {recovered!r}"
    assert "岡本和真" in recovered
    assert not recovered.endswith("…")


def test_recover_long_summary_caps_at_max_length():
    """summary 第一文が DB-safety cap 超なら末尾 "…" で再 cap (ただし復元成功扱い)."""
    title = "巨人選手の話題…"
    long_first_sentence = (
        "巨人選手が" + "ほにゃらら" * (DEFAULT_MAX_TITLE_LENGTH // 2) + "した！"
    )
    recovered = recover_from_trailing_ellipsis(title, long_first_sentence)
    assert len(recovered) <= DEFAULT_MAX_TITLE_LENGTH
    if len(long_first_sentence) > DEFAULT_MAX_TITLE_LENGTH:
        assert recovered.endswith("…")


def test_recover_non_string_returns_input():
    """type guard: title / summary が str でなければ original 返す."""
    assert recover_from_trailing_ellipsis(None, "test") is None
    assert recover_from_trailing_ellipsis(123, "test") == 123
