"""Tests for src.morning_event_key_enricher.

Covers:
  * compose_enrichment_html renders sections by enrichment_role
  * Excludes ``duplicate_or_paraphrase`` and ``other`` roles
  * upsert_enrichment_block appends when no sentinel block present
  * upsert_enrichment_block replaces existing sentinel block (idempotent)
  * process_group: dry-run does not call WP
  * process_group: apply path patches the parent body
  * process_group: skips when parent is not in publish status
"""

from __future__ import annotations

import datetime as dt
import re
from unittest.mock import MagicMock

import pytest

from src import morning_event_key_enricher as enricher


JST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime(2026, 5, 13, 7, 0, 0, tzinfo=JST)


def _group(children: list[dict] | None = None, standalone: list[dict] | None = None) -> dict:
    return {
        "event_key": "2026-05-12|giants_vs_hiroshima|佐々木俊輔|game_result",
        "kind": "game_result",
        "game_date": "2026-05-12",
        "opponent": "hiroshima",
        "hero_player": "佐々木俊輔",
        "parent_id": 66669,
        "parent": {
            "post_id": 66669,
            "title": "【巨人】今季初のサヨナラ勝ち",
            "link": "https://yoshilover.com/66669",
        },
        "children": children or [],
        "standalone": standalone or [],
        "window": {"status": "closed", "close_at": "2026-05-13T07:00:00+09:00"},
        "axes_covered": 6,
        "axes_total": 8,
    }


def _child(post_id: int, title: str, role: str) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "link": f"https://yoshilover.com/{post_id}",
        "enrichment_role": role,
    }


# ─── compose_enrichment_html ────────────────────────────────────────────────


def test_compose_includes_sentinel_markers() -> None:
    g = _group(children=[_child(1, "阿部監督「コメント」", "manager_quote")])
    html = enricher.compose_enrichment_html(g, generated_at=NOW)
    assert enricher.ENRICHMENT_START_MARKER in html
    assert html.rstrip().endswith(enricher.ENRICHMENT_END_MARKER)


def test_compose_renders_role_sections_in_display_order() -> None:
    g = _group(children=[
        _child(1, "ファン反応", "fan_voice_x_post"),
        _child(2, "監督コメント「がんばった」", "manager_quote"),
        _child(3, "本人コメント「最高です」", "player_quote"),
        _child(4, "【動画】サヨナラ", "youtube_video"),
    ])
    html = enricher.compose_enrichment_html(g, generated_at=NOW)
    # Order check: manager → player → youtube → fan_voice
    idx_manager = html.find("監督コメント")
    idx_player = html.find("本人")
    idx_youtube = html.find("動画")
    idx_fan = html.find("ファンの声")
    assert idx_manager < idx_player < idx_youtube < idx_fan


def test_compose_excludes_duplicate_role() -> None:
    g = _group(children=[
        _child(1, "結果言い換え", "duplicate_or_paraphrase"),
        _child(2, "監督コメント", "manager_quote"),
    ])
    html = enricher.compose_enrichment_html(g, generated_at=NOW)
    assert "結果言い換え" not in html
    assert "監督コメント" in html


def test_compose_excludes_other_role() -> None:
    g = _group(children=[_child(1, "未分類", "other")])
    html = enricher.compose_enrichment_html(g, generated_at=NOW)
    assert "未分類" not in html
    # All children filtered → empty notice
    assert "追加情報なし" in html


def test_compose_includes_standalone_section() -> None:
    g = _group(standalone=[{
        "post_id": 9,
        "title": "巨人記録室",
        "link": "https://yoshilover.com/9",
        "reason": "record_compare",
    }])
    html = enricher.compose_enrichment_html(g, generated_at=NOW)
    assert "独立記事" in html
    assert "巨人記録室" in html


def test_compose_escapes_html_in_titles() -> None:
    g = _group(children=[_child(1, "<script>alert(1)</script>", "manager_quote")])
    html = enricher.compose_enrichment_html(g, generated_at=NOW)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_compose_requires_game_result_kind() -> None:
    g = _group()
    g["kind"] = "standalone"
    with pytest.raises(ValueError):
        enricher.compose_enrichment_html(g, generated_at=NOW)


# ─── upsert_enrichment_block ────────────────────────────────────────────────


def test_upsert_appends_when_no_existing_block() -> None:
    original = "<p>original body</p>"
    block = (
        f"{enricher.ENRICHMENT_START_MARKER} event_key=k -->"
        "<h2>new</h2>"
        f"{enricher.ENRICHMENT_END_MARKER}"
    )
    out = enricher.upsert_enrichment_block(original, block)
    assert "<p>original body</p>" in out
    assert "<h2>new</h2>" in out
    assert out.count(enricher.ENRICHMENT_START_MARKER) == 1


def test_upsert_replaces_existing_block_idempotently() -> None:
    block_v1 = (
        f"{enricher.ENRICHMENT_START_MARKER} v=1 -->"
        "<h2>old block</h2>"
        f"{enricher.ENRICHMENT_END_MARKER}"
    )
    block_v2 = (
        f"{enricher.ENRICHMENT_START_MARKER} v=2 -->"
        "<h2>new block</h2>"
        f"{enricher.ENRICHMENT_END_MARKER}"
    )
    original = f"<p>body</p>\n\n{block_v1}\n"
    out = enricher.upsert_enrichment_block(original, block_v2)
    assert "old block" not in out
    assert "new block" in out
    assert out.count(enricher.ENRICHMENT_START_MARKER) == 1
    assert out.count(enricher.ENRICHMENT_END_MARKER) == 1
    # Running again with the same block must be a no-op
    out2 = enricher.upsert_enrichment_block(out, block_v2)
    assert out2 == out


# ─── process_group dry-run / apply ──────────────────────────────────────────


def test_process_group_dry_run_does_not_call_wp() -> None:
    wp = MagicMock()
    g = _group(children=[_child(1, "監督コメント", "manager_quote")])
    result = enricher.process_group(g, wp=wp, apply=False, now=NOW)
    assert result["applied"] is False
    assert result.get("dry_run") is True
    wp.update_post_fields.assert_not_called()


def test_process_group_apply_patches_when_publish(monkeypatch) -> None:
    g = _group(children=[_child(1, "監督コメント「がんばった」", "manager_quote")])
    wp = MagicMock()
    wp.api = "https://yoshilover.com/wp-json/wp/v2"
    wp.auth = ("user", "pw")

    fetched_body = {
        "id": 66669,
        "status": "publish",
        "content": {"raw": "<p>original parent body</p>"},
    }
    monkeypatch.setattr(enricher, "fetch_parent_raw_body", lambda wp_, pid: fetched_body)

    captured: dict = {}

    def fake_patch(wp_, post_id, new_body):
        captured["post_id"] = post_id
        captured["new_body"] = new_body

    monkeypatch.setattr(enricher, "patch_parent_content", fake_patch)
    result = enricher.process_group(g, wp=wp, apply=True, now=NOW)
    assert result["applied"] is True
    assert result["skipped_reason"] is None
    assert captured["post_id"] == 66669
    assert "<p>original parent body</p>" in captured["new_body"]
    assert enricher.ENRICHMENT_START_MARKER in captured["new_body"]
    assert "監督コメント「がんばった」" in captured["new_body"]


def test_process_group_skips_when_parent_not_publish(monkeypatch) -> None:
    g = _group(children=[_child(1, "監督コメント", "manager_quote")])
    wp = MagicMock()
    monkeypatch.setattr(
        enricher,
        "fetch_parent_raw_body",
        lambda wp_, pid: {"id": pid, "status": "draft", "content": {"raw": ""}},
    )
    patch_called = MagicMock()
    monkeypatch.setattr(enricher, "patch_parent_content", patch_called)
    result = enricher.process_group(g, wp=wp, apply=True, now=NOW)
    assert result["applied"] is False
    assert "parent_status_not_publish:draft" in (result["skipped_reason"] or "")
    patch_called.assert_not_called()


def test_process_group_noop_when_body_unchanged(monkeypatch) -> None:
    g = _group(children=[_child(1, "監督コメント", "manager_quote")])
    wp = MagicMock()
    # Pre-populate the body with the exact block we would generate
    block = enricher.compose_enrichment_html(g, generated_at=NOW)
    monkeypatch.setattr(
        enricher,
        "fetch_parent_raw_body",
        lambda wp_, pid: {
            "id": pid,
            "status": "publish",
            "content": {"raw": f"<p>body</p>\n\n{block}\n"},
        },
    )
    patched = MagicMock()
    monkeypatch.setattr(enricher, "patch_parent_content", patched)
    result = enricher.process_group(g, wp=wp, apply=True, now=NOW)
    assert result["applied"] is False
    assert result["skipped_reason"] == "noop_no_change"
    patched.assert_not_called()


# ─── CLI safety ─────────────────────────────────────────────────────────────


def test_cli_rejects_dry_run_and_apply_together(capsys) -> None:
    rc = enricher.main(["--date", "2026-05-12", "--dry-run", "--apply"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "mutually exclusive" in captured.err


# ─── mode-aware collect_eligible_groups ─────────────────────────────────────


def _fake_fetcher(posts):
    def _fetch(*, since, until, **_kwargs):
        out = []
        for p in posts:
            try:
                dat = dt.datetime.fromisoformat(str(p.get("date") or "").replace("Z", "")).date()
            except Exception:
                continue
            if since <= dat < until:
                out.append(p)
        return out
    return _fetch


def _wp_post(pid: int, date: str, title: str) -> dict:
    return {
        "id": pid,
        "date": date,
        "title": {"rendered": title},
        "categories": [],
        "link": f"https://yoshilover.com/{pid}",
    }


_5_12_POSTS = [
    _wp_post(66603, "2026-05-12T19:45:24", "【一軍】巨人 vs 広島 ぎふしん長良川球場 18時試合開始"),
    _wp_post(66669, "2026-05-12T21:15:51", "【巨人】今季初のサヨナラ勝ち！佐々木俊輔に強攻サインで劇的初サヨナラアーチ"),
    _wp_post(66677, "2026-05-12T21:30:49", "巨人が今季初のサヨナラ勝ち！ 佐々木が中崎から岐阜の夜空にサヨナラ2ラン"),
]


def test_morning_mode_skips_open_window() -> None:
    """Before 07:00 JST cutoff = window open → morning mode returns []"""
    fetch = _fake_fetcher(_5_12_POSTS)
    groups = enricher.collect_eligible_groups(
        game_date=dt.date(2026, 5, 12),
        now=dt.datetime(2026, 5, 13, 6, 0, tzinfo=JST),
        mode="morning",
        fetcher=fetch,
    )
    assert groups == []


def test_morning_mode_picks_up_closed_window() -> None:
    """At/after 07:00 JST cutoff = closed → morning mode finds the group"""
    fetch = _fake_fetcher(_5_12_POSTS)
    groups = enricher.collect_eligible_groups(
        game_date=dt.date(2026, 5, 12),
        now=dt.datetime(2026, 5, 13, 7, 0, 1, tzinfo=JST),
        mode="morning",
        fetcher=fetch,
    )
    assert len(groups) == 1
    assert groups[0]["event_subtype"] == "walk_off"
    assert groups[0]["parent_id"] == 66669


def test_rolling_mode_picks_up_open_window() -> None:
    """Rolling mode includes open windows so the 15-min cron can edit
    parents in near-real-time while the night is still active."""
    fetch = _fake_fetcher(_5_12_POSTS)
    groups = enricher.collect_eligible_groups(
        game_date=dt.date(2026, 5, 12),
        now=dt.datetime(2026, 5, 13, 3, 0, tzinfo=JST),  # 03:00 JST = open
        mode="rolling",
        fetcher=fetch,
    )
    assert len(groups) == 1
    assert groups[0]["event_subtype"] == "walk_off"
    assert groups[0]["window"]["status"] == "open"


def test_compose_accepts_player_topic_kind() -> None:
    """v2 added player_topic kind (home_visit / debut_milestone /
    record_milestone / lineup_role). compose must not error on those."""
    g = _group(children=[_child(1, "練習風景", "scene_detail")])
    g["kind"] = "player_topic"
    html = enricher.compose_enrichment_html(g, generated_at=NOW)
    assert enricher.ENRICHMENT_START_MARKER in html


def test_compose_rejects_player_quote_kind() -> None:
    """player_quote (generic-only events) shouldn't get an enrichment
    section — they're just stand-alone quote articles."""
    g = _group(children=[_child(1, "コメント", "manager_quote")])
    g["kind"] = "player_quote"
    import pytest
    with pytest.raises(ValueError):
        enricher.compose_enrichment_html(g, generated_at=NOW)
