"""Tests for 377-OPS Phase 1B: draft mode mail に本文 + admin link を含める.

GH #51。 user が mail で本文判断 + 1 click で WP admin edit 画面 → 公開。

PublishNoticeRequest に body_excerpt + admin_edit_url 任意 field 追加、
build_body_text が両方を本文セクションに展開する。 既存 publish mail
(body_excerpt=None) は従来通り、 backward compat。
"""

from __future__ import annotations

from src.publish_notice_email_sender import (
    PublishNoticeRequest,
    build_body_text,
)


def _req(**overrides):
    base = dict(
        post_id=12345,
        title="【巨人】テスト記事",
        canonical_url="https://yoshilover.com/12345",
        subtype="news",
        publish_time_iso="2026-05-17T07:00:00+09:00",
        summary="テスト要約",
    )
    base.update(overrides)
    return PublishNoticeRequest(**base)


def test_body_text_omits_excerpt_when_none():
    """body_excerpt=None (default) では本文セクション無 (backward compat)."""
    text = build_body_text(_req())
    assert "本文(抜粋):" not in text


def test_body_text_includes_excerpt_when_provided():
    """body_excerpt が provided されたら 本文セクション出る."""
    excerpt = "ここに記事の本文抜粋が入る。 巨人投手が好投、 6 回 1 失点でチームを勝利に導いた。"
    text = build_body_text(_req(body_excerpt=excerpt))
    assert "本文(抜粋):" in text
    assert excerpt in text


def test_body_text_includes_admin_edit_url_when_provided():
    """admin_edit_url が provided されたら 編集 / 公開 link 出る."""
    admin_url = "https://yoshilover.com/wp-admin/post.php?post=12345&action=edit"
    text = build_body_text(_req(admin_edit_url=admin_url))
    assert "編集 / 公開:" in text
    assert admin_url in text


def test_body_text_includes_both_excerpt_and_admin_url():
    """両方 provided で 両方 出る."""
    excerpt = "テスト本文 600 字…"
    admin_url = "https://yoshilover.com/wp-admin/post.php?post=12345&action=edit"
    text = build_body_text(_req(body_excerpt=excerpt, admin_edit_url=admin_url))
    assert "本文(抜粋):" in text
    assert excerpt in text
    assert "編集 / 公開:" in text
    assert admin_url in text


def test_body_text_empty_excerpt_treated_as_omitted():
    """body_excerpt='' (空文字) は None 同様に section 出さない."""
    text = build_body_text(_req(body_excerpt=""))
    assert "本文(抜粋):" not in text


def test_body_text_minimal_mode_default_keeps_title_url_only():
    """minimal body mode (既存 default) は title + url のみで unchanged."""
    text = build_body_text(_req(summary="既存サマリ"))
    # minimal mode では title + url のみ返す (summary は表示しない)
    assert "【巨人】テスト記事" in text
    assert "https://yoshilover.com/12345" in text
    # 旧 summary line は minimal mode では出ない
    assert "summary:" not in text or "本文(抜粋):" in text
