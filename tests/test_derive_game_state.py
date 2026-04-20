import json
from datetime import datetime, timedelta, timezone

import pytest

from src.tools import derive_game_state as derive


JST = timezone(timedelta(hours=9))


@pytest.fixture
def make_post():
    def _make_post(
        post_id: int,
        *,
        title: str,
        body: str,
        subtype: str | None = None,
        game_id: str | None = None,
        game_start_time: str | None = None,
        source_urls: list[str] | None = None,
        modified_gmt: str = "2026-04-21T09:00:00",
    ) -> dict:
        meta: dict[str, object] = {}
        if subtype is not None:
            meta["article_subtype"] = subtype
        if game_id is not None:
            meta["game_id"] = game_id
        if game_start_time is not None:
            meta["game_start_time"] = game_start_time
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


def test_pre_to_live_trigger_requires_time_and_signal():
    start = datetime(2026, 4, 21, 18, 0, tzinfo=JST)
    assert derive.should_transition_pre_to_live(start, start + timedelta(minutes=1), "プレイボールで1回表が始まった")
    assert not derive.should_transition_pre_to_live(start, start + timedelta(minutes=1), "見どころを更新")
    assert not derive.should_transition_pre_to_live(start, start - timedelta(minutes=1), "試合開始")


def test_live_to_post_transition_by_close_marker():
    start = datetime(2026, 4, 21, 18, 0, tzinfo=JST)
    now = start + timedelta(hours=2)
    assert derive.should_transition_live_to_post(start, now, now, "9回裏終了でゲームセット")


def test_live_to_post_transition_by_timeout_without_late_update():
    start = datetime(2026, 4, 21, 18, 0, tzinfo=JST)
    now = start + timedelta(hours=6)
    assert derive.should_transition_live_to_post(start, start + timedelta(hours=4, minutes=50), now, "8回裏 巨人が勝ち越し")
    assert not derive.should_transition_live_to_post(start, start + timedelta(hours=5, minutes=10), now, "延長10回表も続行")


def test_close_marker_detection_supports_exact_and_ninth_inning_markers():
    assert derive.detect_close_markers("試合終了、巨人が勝利") == ["試合終了"]
    assert "ゲームセット" in derive.detect_close_markers("9回裏終了でゲームセット")
    assert "9plus_inning_close" in derive.detect_close_markers("延長10回終了で決着")
    assert derive.detect_close_markers("8回裏終了") == []


def test_fact_notice_returns_null(make_post):
    post = make_post(101, title="【公示】登録抹消", body="4月21日の出場選手登録公示", subtype="fact_notice")
    row = derive.derive_game_state_for_post(post, now=datetime(2026, 4, 21, 12, 0, tzinfo=JST))
    assert row["derived_game_state"] is None
    assert row["reason_if_null"] == "subtype_no_game_state"


@pytest.mark.parametrize(
    ("subtype", "cases"),
    [
        (
            "pregame",
            [
                ("【巨人】阪神戦の見どころ", "試合前のポイントを整理する。", "pre"),
                ("【巨人】18時プレイボール予定", "東京ドームでの予告先発。", "pre"),
                ("【巨人】先発発表", "試合前の展望記事。", "pre"),
            ],
        ),
        (
            "lineup",
            [
                ("【巨人】スタメン発表", "1番丸、2番吉川。", "pre"),
                ("【巨人】先発オーダー", "18時開始予定のスタメン。", "pre"),
                ("【巨人】今日のスタメン", "捕手は大城。", "pre"),
            ],
        ),
        (
            "live_update",
            [
                ("【巨人】3回表 先制", "3回表に岡本が先制打。", "live"),
                ("【巨人】試合速報", "1回裏に先頭打者が出塁。", "live"),
                ("【巨人】試合速報", "9回裏終了でゲームセット。", "post"),
            ],
        ),
        (
            "live_anchor",
            [
                ("【巨人】ライブ速報", "1回表 プレイボール。", "live"),
                ("【巨人】ライブ速報", "6回裏 同点に追いつく。", "live"),
                ("【巨人】ライブ速報", "試合終了で巨人が勝利。", "post"),
            ],
        ),
        (
            "postgame",
            [
                ("【巨人】阪神に勝利", "試合終了。巨人が3-2で勝利。", "post"),
                ("【巨人】延長戦を制す", "ゲームセット。延長10回終了。", "post"),
                ("【巨人】惜敗", "9回裏終了で敗戦。", "post"),
            ],
        ),
        (
            "farm",
            [
                ("【巨人2軍】ロッテ2軍に勝利", "試合終了。3-1で勝利。", "post"),
                ("【巨人2軍】イースタン速報", "ゲームセットで引き分け。", "post"),
                ("【巨人2軍】ファーム結果", "9回裏終了で4-2。", "post"),
            ],
        ),
        (
            "fact_notice",
            [
                ("【公示】出場選手登録", "本日の公示。", None),
                ("【公示】登録抹消", "巨人の公示を整理。", None),
                ("【公示】支配下登録", "球団発表ベースの公示。", None),
            ],
        ),
    ],
)
def test_subtype_mapping_has_expected_outcomes(make_post, subtype, cases):
    now = datetime(2026, 4, 21, 22, 0, tzinfo=JST)
    for index, (title, body, expected) in enumerate(cases, start=1):
        post = make_post(
            2000 + index,
            title=title,
            body=body,
            subtype=subtype,
            game_id="20260421-giants-tigers",
            game_start_time="2026-04-21T18:00:00+09:00",
            modified_gmt="2026-04-21T11:00:00",
        )
        row = derive.derive_game_state_for_post(post, now=now)
        assert row["derived_game_state"] == expected
        if expected is None:
            assert row["reason_if_null"] == "subtype_no_game_state"
        else:
            assert row["reason_if_null"] is None


def test_main_writes_markdown_report(monkeypatch, tmp_path, make_post, capsys):
    posts = [
        make_post(
            301,
            title="【巨人】スタメン発表",
            body="18時開始予定のスタメン。",
            subtype="lineup",
            game_id="20260421-giants-tigers",
            source_urls=["https://www.giants.jp/game/20260421/preview/"],
        ),
        make_post(
            302,
            title="【公示】登録抹消",
            body="本日の公示です。",
            subtype="fact_notice",
        ),
    ]
    monkeypatch.setattr(derive, "load_recent_drafts", lambda max_posts: posts[:max_posts])
    output_path = tmp_path / "report.md"

    assert derive.main(["--max-posts", "2", "--output", str(output_path)]) == 0

    stdout = capsys.readouterr().out
    assert "| 301 | lineup | 20260421-giants-tigers | pre | - | - |" in stdout
    assert output_path.read_text(encoding="utf-8") == stdout
    summary = json.loads(stdout.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert summary["derived_count"] == 1
    assert summary["null_count"] == 1
