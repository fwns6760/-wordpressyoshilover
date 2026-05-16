"""Tests for src.analysis.ranking_article_publisher (DATA-INSIGHT-continuous).

`fetch_ranking_rows` / `find_giants_top` / `markdown_to_html` /
`render_giants_centric_ranking` / `publish_giants_centric_ranking_draft`
の fixture-based test。WP 投入は mock、dry_run path も verify。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis import ranking_article_publisher as rap  # noqa: E402


def _seed_snapshots(conn, *, snapshot_date, scope, metric, ranking):
    """sample snapshots を insert。``ranking`` は (player, team, value, sample, rank, total) tuple."""
    for player, team, value, sample, rank, total in ranking:
        conn.execute(
            "INSERT INTO advanced_metric_snapshots "
            "(snapshot_date, scope, player_canonical, team_code, "
            "metric_name, metric_value, sample_size, league_rank, league_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_date, scope, player, team, metric, value, sample, rank, total),
        )
    conn.commit()


def test_fetch_ranking_rows_returns_top_n(tmp_path):
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="OPS",
                        ranking=[
                            ("ダルベック", "g", 0.93, 91, 1, 30),
                            ("佐藤輝明", "t", 0.91, 90, 2, 30),
                            ("坂倉将吾", "c", 0.85, 78, 3, 30),
                        ])
        rows = rap.fetch_ranking_rows(
            conn, metric_name="OPS", scope="last_30d",
            snapshot_date="2026-05-14", top_n=10,
        )
        assert len(rows) == 3
        assert rows[0].player_canonical == "ダルベック"
        assert rows[0].team_code == "g"
        assert rows[0].rank == 1
    finally:
        conn.close()


def test_fetch_ranking_rows_returns_empty_when_no_data(tmp_path):
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        rows = rap.fetch_ranking_rows(
            conn, metric_name="OPS", scope="last_30d", snapshot_date="2026-05-14",
        )
        assert rows == []
    finally:
        conn.close()


def test_fetch_ranking_rows_uses_latest_snapshot_when_date_omitted(tmp_path):
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-10", scope="last_30d", metric="OPS",
                        ranking=[("旧", "g", 0.5, 50, 1, 1)])
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="OPS",
                        ranking=[("新", "g", 0.9, 90, 1, 1)])
        rows = rap.fetch_ranking_rows(conn, metric_name="OPS", scope="last_30d")
        assert len(rows) == 1
        assert rows[0].player_canonical == "新"
    finally:
        conn.close()


def test_find_giants_top_picks_first_giants_player():
    from src.analysis.insight_article_generator import RankRow
    rows = [
        RankRow(player_canonical="阪神選手", team_code="t", metric_value=1.0, sample_size=50, rank=1, total=10),
        RankRow(player_canonical="巨人A", team_code="g", metric_value=0.9, sample_size=50, rank=2, total=10),
        RankRow(player_canonical="巨人B", team_code="g", metric_value=0.85, sample_size=50, rank=3, total=10),
    ]
    assert rap.find_giants_top(rows) == "巨人A"


def test_find_giants_top_returns_none_when_no_giants():
    from src.analysis.insight_article_generator import RankRow
    rows = [
        RankRow(player_canonical="阪神選手", team_code="t", metric_value=1.0, sample_size=50, rank=1, total=10),
    ]
    assert rap.find_giants_top(rows) is None


def test_markdown_to_html_simple_header_and_paragraph():
    md = "# タイトル\n\nこれは段落です。\n"
    html = rap.markdown_to_html(md)
    assert "<h2>タイトル</h2>" in html
    assert "<p>これは段落です。</p>" in html


def test_markdown_to_html_h2_becomes_h3():
    """WP title が h1 を占有するため、render_article の h1 を h2 に、h2 を h3 に降格."""
    md = "## section\n"
    html = rap.markdown_to_html(md)
    assert "<h3>section</h3>" in html


def test_markdown_to_html_table_conversion():
    md = "| 順位 | 選手 |\n|---|---|\n| 1 | A |\n| 2 | B |\n"
    html = rap.markdown_to_html(md)
    assert "<table>" in html
    assert "<th>順位</th>" in html
    assert "<td>A</td>" in html
    assert "<td>B</td>" in html
    assert "</table>" in html


def test_markdown_to_html_bold_italic():
    md = "**bold text** and _italic_\n"
    html = rap.markdown_to_html(md)
    assert "<strong>bold text</strong>" in html
    assert "<em>italic</em>" in html


def test_render_giants_centric_ranking_full(tmp_path):
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="OPS",
                        ranking=[
                            ("ダルベック", "g", 0.93, 91, 1, 30),
                            ("佐藤輝明", "t", 0.91, 90, 2, 30),
                            ("坂倉将吾", "c", 0.85, 78, 3, 30),
                        ])
        result = rap.render_giants_centric_ranking(
            conn, metric_name="OPS", scope="last_30d",
            snapshot_date="2026-05-14", top_n=10,
        )
        assert result is not None
        assert "ダルベック" in result["title"]
        assert "<h2>" in result["body_html"]
        assert "<table>" in result["body_html"]
        assert "<svg" not in result["body_html"]
        assert result["focus_player"] == "ダルベック"
        assert result["metric_name"] == "OPS"
        assert result["scope"] == "last_30d"
    finally:
        conn.close()


def test_render_returns_none_when_no_giants_in_top_n(tmp_path):
    """巨人選手が ranking 圏外なら focus 取れず None で skip."""
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="OPS",
                        ranking=[
                            ("阪神A", "t", 1.0, 100, 1, 30),
                            ("阪神B", "t", 0.95, 100, 2, 30),
                        ])
        result = rap.render_giants_centric_ranking(
            conn, metric_name="OPS", scope="last_30d", snapshot_date="2026-05-14",
        )
        assert result is None
    finally:
        conn.close()


def test_publish_dry_run_returns_article_dict(tmp_path):
    """dry_run=True で WP 投入せず article 内容を返す."""
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="OPS",
                        ranking=[("巨人A", "g", 0.93, 91, 1, 30)])
        wp_mock = MagicMock()
        result = rap.publish_giants_centric_ranking_draft(
            conn, wp_mock,
            metric_name="OPS", scope="last_30d", snapshot_date="2026-05-14",
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert "巨人A" in result["title"]
        # WP 側 method は呼ばれない
        wp_mock.create_category.assert_not_called()
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()


def test_publish_skip_when_no_data(tmp_path):
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        wp_mock = MagicMock()
        result = rap.publish_giants_centric_ranking_draft(
            conn, wp_mock,
            metric_name="OPS", scope="last_30d", snapshot_date="2026-05-14",
        )
        assert result["status"] == "skip"
        assert "no_data" in result["reason"]
    finally:
        conn.close()


def test_publish_full_flow_creates_draft(tmp_path):
    """create_category + create_post 経由で draft が landed することを mock で verify."""
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="OPS",
                        ranking=[("巨人A", "g", 0.93, 91, 1, 30)])
        wp_mock = MagicMock()
        wp_mock.create_category.return_value = 671
        wp_mock.create_post.return_value = 67500
        result = rap.publish_giants_centric_ranking_draft(
            conn, wp_mock,
            metric_name="OPS", scope="last_30d", snapshot_date="2026-05-14",
        )
        assert result["status"] == "published_draft"
        assert result["post_id"] == 67500
        assert result["category_id"] == 671
        # status='draft' 固定 verify (work record §禁止事項)
        call_kwargs = wp_mock.create_post.call_args.kwargs
        assert call_kwargs.get("status") == "draft"
    finally:
        conn.close()


def test_publish_error_on_category_failure(tmp_path):
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="OPS",
                        ranking=[("巨人A", "g", 0.93, 91, 1, 30)])
        wp_mock = MagicMock()
        wp_mock.create_category.return_value = 0
        wp_mock.resolve_category_id.return_value = 0
        result = rap.publish_giants_centric_ranking_draft(
            conn, wp_mock,
            metric_name="OPS", scope="last_30d", snapshot_date="2026-05-14",
        )
        assert result["status"] == "error"
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()


def test_publish_default_set_respects_max_per_run(tmp_path):
    db = tmp_path / "test.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        # default_jobs に含まれる全 metric × scope を seed して
        # max_per_run cap が published_count を制限することを verify。
        # 2026-05-15: default_jobs は 11 件に拡張済 (打者 6 + 投手 5)。
        for metric, scope in [
            ("OPS", "last_30d"), ("wOBA", "last_30d"),
            ("AVG", "last_30d"), ("OBP", "last_30d"),
            ("OPS", "season"), ("wOBA", "season"),
            ("ERA", "season"), ("FIP", "season"), ("WHIP", "season"),
            ("ERA", "last_30d"), ("FIP", "last_30d"),
        ]:
            _seed_snapshots(conn, snapshot_date="2026-05-14", scope=scope, metric=metric,
                            ranking=[("巨人A", "g", 0.5, 90, 1, 30)])
        wp_mock = MagicMock()
        wp_mock.create_category.return_value = 671
        wp_mock.create_post.return_value = 12345
        results = rap.publish_default_set(conn, wp_mock, max_per_run=2)
        published_count = sum(1 for r in results if r.get("status") == "published_draft")
        skip_max_count = sum(1 for r in results if r.get("status") == "skip_max_per_run")
        # max_per_run=2 で 2 件のみ publish、残り (全 jobs - 2) は skip_max_per_run。
        assert published_count == 2
        assert skip_max_count == len(results) - 2
        assert skip_max_count >= 1  # 11 jobs → skip 9 期待だが、最低 1 件は skip される
    finally:
        conn.close()
