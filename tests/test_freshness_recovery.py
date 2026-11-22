from pathlib import Path
from unittest.mock import Mock

import pytest

from src import npb_draft_source as draft
from src.tools import data_site_daily_refresh as daily

FIXTURE = Path(__file__).parent / "fixtures/npb_draft_2026.html"


def test_official_draft_and_invalid_year_partial_table():
    html = FIXTURE.read_text()
    parsed = draft.parse_draft(html, 2026)
    assert len(parsed["draft_picks"]) == 6
    assert len(parsed["ikusei_picks"]) == 5
    assert parsed["draft_picks"][0]["name"] == "織田翔希"
    assert parsed["ikusei_picks"][0]["round"] == "育成1位"
    for invalid in (html.replace("6位", "7位"), html.replace("捕手", "")):
        with pytest.raises(ValueError):
            draft.parse_draft(invalid, 2026)
    with pytest.raises(ValueError):
        draft.parse_draft(html, 2027)


def test_history_preserved_and_missing_year_fails_closed(monkeypatch):
    baked = {"draft_picks": [{"year": 2025, "round": "1位", "name": "既存選手"}],
             "ikusei_picks": [], "lottery": [{"year": 2025, "note": "保持"}]}
    fetch = Mock(return_value=draft.parse_draft(FIXTURE.read_text(), 2026))
    monkeypatch.setattr(draft, "fetch_draft", fetch)
    result = draft.refresh_history(baked, 2026)
    assert result["draft_picks"][-1] == baked["draft_picks"][0]
    assert result["lottery"] == baked["lottery"]
    assert len(baked["draft_picks"]) == 1
    fetch.side_effect = RuntimeError("unavailable")
    monkeypatch.setattr(daily, "_find_page_id", lambda *a, **kw: 10)
    write = Mock()
    monkeypatch.setattr(daily, "_upsert", write)
    with pytest.raises(RuntimeError):
        daily.refresh_draft("base", None, 1, 2026)
    write.assert_not_called()


def test_priority_updates_run_before_failure_and_other_pages_continue(monkeypatch):
    monkeypatch.setattr(daily, "_report_player_class_drift", lambda: None)
    monkeypatch.setattr(daily, "_creds", lambda: ("base", None))
    monkeypatch.setattr(daily, "_find_page_id", lambda *a, **kw: 1)
    order = []
    def run(name):
        def inner(*args):
            order.append(name)
            if name == "refresh_rotation":
                raise RuntimeError("unavailable")
            return True
        return inner
    names = ["refresh_standings", "refresh_draft", "refresh_rotation", "refresh_roster_moves",
             "refresh_injured", "refresh_open_games", "refresh_interleague", "refresh_salary_value"]
    for name in names:
        monkeypatch.setattr(daily, name, run(name))
    assert daily.main() == 0
    assert order == names


def test_compact_salary_db_size_cap(monkeypatch):
    from google.cloud import storage
    blob = Mock(size=129 * 1024 * 1024)
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    monkeypatch.setattr(storage, "Client", lambda: client)
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test")
    assert daily.refresh_salary_value("base", None, 1, 2026) is False
    client.bucket.return_value.blob.assert_called_once_with("data_site.db")
    blob.download_to_filename.assert_not_called()


def test_finished_season_date_is_not_run_date(monkeypatch):
    from src import interleague_scraper as ils, source_npb_standings_extractor as sne
    from src import source_npb_leaders_extractor as nle
    monkeypatch.setattr(ils, "fetch_standings_html", lambda *a: "<p>全日程終了</p>")
    rows = [{"team": t, "games": 143, "wins": 76, "losses": 64, "draws": 3, "win_pct": ".543"}
            for t in ["阪神", "巨人", "DeNA", "広島", "ヤクルト", "中日"]]
    monkeypatch.setattr(sne, "parse_npb_standings_html", lambda h: rows)
    monkeypatch.setattr(nle, "fetch_leaders_html", lambda *a: "")
    monkeypatch.setattr(nle, "parse_leaders_table", lambda h: None)
    write = Mock(return_value=True)
    monkeypatch.setattr(daily, "_upsert", write)
    assert daily.refresh_standings("base", None, 1, 2026)
    assert "2026年 全日程終了" in write.call_args.kwargs["content"]
    rows.pop()
    write.reset_mock()
    assert not daily.refresh_standings("base", None, 1, 2026)
    write.assert_not_called()
