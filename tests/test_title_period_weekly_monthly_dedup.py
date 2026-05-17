"""Tests for issue #44 E: title 末尾 (週別)（週別) 二重付与 fix.

Bug: 実 post で「(週別)（週別)」「(月別)（月別)」が発生していた (5/16-17 で 5 件 publish 済、
post 68505 / 68571 / 68644 / 68946 等)。

Root cause: ``insight_title_guard._PERIOD_KEYWORD_RE`` が「週別 / 月別」を
period marker として認識しなかった。 ``ranking_article_publisher`` が
半角 ``(週別)`` を先に append、 ``ensure_title_period`` は title_has_period が
False と判定して全角 ``（週別）`` を再 append → 結果 ``(週別)（週別)`` 重複。

Fix: ``_PERIOD_KEYWORD_RE`` に「週別 / 月別」を追加。 既に半角 ``(週別)`` が
ある title は no-op で通す。
"""

from __future__ import annotations

from src.analysis.insight_title_guard import (
    title_has_period,
    ensure_title_period,
)


def test_title_has_period_recognizes_weekly_half_width():
    """半角 (週別) を含む title は period 有りと判定."""
    t = "【巨人データ】浦田俊輔 安打数 6 でセ・リーグ 4 位 (週別)"
    assert title_has_period(t) is True


def test_title_has_period_recognizes_weekly_full_width():
    """全角 （週別） を含む title も period 有りと判定."""
    t = "【巨人データ】浦田俊輔 安打数 6 でセ・リーグ 4 位（週別）"
    assert title_has_period(t) is True


def test_title_has_period_recognizes_monthly():
    """月別 (半角 / 全角) も period marker."""
    assert title_has_period("【巨人データ】岡本和真 本塁打 8 で 1 位 (月別)") is True
    assert title_has_period("【巨人データ】岡本和真 本塁打 8 で 1 位（月別）") is True


def test_ensure_title_period_no_double_weekly_append():
    """post 68946 等の bug 再現 → fix 後は二重 append しない."""
    t = "【巨人データ】浦田俊輔 安打数 6 でセ・リーグ 4 位 (週別)"
    r = ensure_title_period(t, scope="weekly")
    assert r.ok is True
    assert r.title == t, f"title 変更されてはいけない: got {r.title!r}"
    assert r.appended_label == "", f"appended_label 空であるべき: got {r.appended_label!r}"
    # 二重 (週別)（週別) になっていない
    assert "(週別)（週別)" not in r.title
    assert "（週別）（週別）" not in r.title


def test_ensure_title_period_no_double_monthly_append():
    t = "【巨人データ】岡本和真 本塁打 8 でセ・リーグ 1 位 (月別)"
    r = ensure_title_period(t, scope="monthly")
    assert r.ok is True
    assert r.title == t
    assert "(月別)（月別)" not in r.title


def test_ensure_title_period_still_works_for_missing_period():
    """period 無し title には従来通り全角 （週別） を append."""
    t = "【巨人データ】浦田俊輔 安打数 6 でセ・リーグ 4 位"
    r = ensure_title_period(t, scope="weekly")
    assert r.ok is True
    assert r.title == "【巨人データ】浦田俊輔 安打数 6 でセ・リーグ 4 位（週別）"
    assert r.appended_label == "週別"


def test_ensure_title_period_recognizes_existing_today_no_change():
    """1軍 試合速報 等の「今日の試合 / 本日」 marker は従来通り (regression check)."""
    t = "【スタメン】巨人 vs DeNA 本日の試合"
    r = ensure_title_period(t, scope="today")
    assert r.title == t
    assert r.appended_label == ""
