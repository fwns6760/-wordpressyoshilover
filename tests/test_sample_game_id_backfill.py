import json

import pytest

from src.tools import sample_game_id_backfill as backfill


@pytest.fixture
def make_post():
    def _make_post(
        post_id: int,
        *,
        title: str,
        body: str,
        subtype: str | None = None,
        source_urls: list[str] | None = None,
        modified_gmt: str = "2026-04-21T03:00:00",
    ) -> dict:
        meta: dict[str, object] = {}
        if subtype is not None:
            meta["article_subtype"] = subtype
        if source_urls is not None:
            meta["source_urls"] = source_urls
        return {
            "id": post_id,
            "modified_gmt": modified_gmt,
            "title": {"raw": title},
            "content": {"raw": body},
            "meta": meta,
        }

    return _make_post


def test_normalize_team_code():
    assert backfill.normalize_team_code("巨人") == "giants"
    assert backfill.normalize_team_code("ＤｅＮＡ") == "baystars"
    assert backfill.normalize_team_code("オリックス") == "buffaloes"
    assert backfill.normalize_team_code("未知") is None


def test_detect_doubleheader_suffix():
    assert backfill.detect_doubleheader_suffix("巨人2軍 ロッテ2軍 第1試合") == "1"
    assert backfill.detect_doubleheader_suffix("game 2 preview") == "2"
    assert backfill.detect_doubleheader_suffix("通常開催") == ""


def test_derive_game_id_for_synthetic_drafts(make_post):
    cases = [
        (
            make_post(
                101,
                title="【巨人】阪神戦の見どころ",
                body="4月21日 東京ドームで阪神と対戦。予告先発を確認する。",
                subtype="pregame",
                source_urls=["https://www.giants.jp/game/20260421/preview/"],
            ),
            "20260421-giants-tigers",
        ),
        (
            make_post(
                102,
                title="【巨人】阪神に競り勝つ",
                body="2026年4月22日 甲子園で阪神に3-2で勝利。試合終了。",
                subtype="postgame",
                source_urls=["https://baseball.yahoo.co.jp/npb/game/2026042201/top"],
            ),
            "20260422-tigers-giants",
        ),
        (
            make_post(
                103,
                title="【巨人2軍】ロッテ2軍とのダブルヘッダー第2試合",
                body="4月23日 ジャイアンツ球場でロッテと対戦。2軍の先発を確認する。",
                subtype="farm",
                source_urls=["https://www.giants.jp/game/20260423/preview/"],
            ),
            "20260423-giants-marines-2",
        ),
    ]

    for post, expected in cases:
        row = backfill.derive_game_id_for_post(post)
        assert row["derived_game_id"] == expected
        assert row["reason_if_null"] is None


def test_main_writes_report_without_network(monkeypatch, tmp_path, make_post, capsys):
    posts = [
        make_post(
            201,
            title="【巨人】阪神戦の見どころ",
            body="4月21日 東京ドームで阪神と対戦。",
            subtype="pregame",
            source_urls=["https://www.giants.jp/game/20260421/preview/"],
        ),
        make_post(
            202,
            title="球団からのお知らせ",
            body="イベント情報です。",
            subtype="general",
            source_urls=[],
        ),
    ]
    monkeypatch.setattr(backfill, "load_recent_drafts", lambda max_posts: posts[:max_posts])
    output_path = tmp_path / "report.md"

    assert backfill.main(["--max-posts", "2", "--output", str(output_path)]) == 0

    stdout = capsys.readouterr().out
    assert "| 201 | pregame |" in stdout
    assert output_path.read_text(encoding="utf-8") == stdout
    summary = json.loads(stdout.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert summary["derived_count"] == 1
    assert summary["null_count"] == 1
