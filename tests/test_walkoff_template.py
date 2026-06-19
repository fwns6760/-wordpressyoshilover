"""data_site_template_walkoff の描画検証。"""

from src import data_site_template_walkoff as w


_DATA = {
    "total": 162,
    "records": [{"category": "チーム通算最多", "player": "王 貞治", "value": "8本", "note": "セ・リーグ記録"}],
    "homeruns": [
        {"no": "1", "player": "中島 治康", "count": "1", "date": "1941年04月07日",
         "opponent": "南海", "game_no": "1回戦", "stadium": "後楽園", "type": "2ラン",
         "score_before": "5-5", "score_after": "7-5", "extra_inning": "", "pitcher": "川崎 徳次", "note": ""},
        {"no": "162", "player": "丸 佳浩", "count": "3", "date": "2026年06月03日",
         "opponent": "オリックス", "game_no": "2回戦", "stadium": "東京ドーム", "type": "満塁",
         "score_before": "1-4", "score_after": "5-4", "extra_inning": "8回", "pitcher": "椋木 蓮", "note": "代打"},
    ],
}


def test_title_and_excerpt():
    assert "サヨナラ本塁打" in w.render_walkoff_title()
    assert "162" in w.render_walkoff_excerpt(_DATA)


def test_html_has_table_records_and_nav():
    h = w.render_walkoff_html(_DATA)
    assert "中島 治康" in h and "丸 佳浩" in h          # 全選手
    assert "サヨナラ本塁打の記録" in h and "8本" in h    # 記録box
    assert "5-5→7-5" in h                              # スコア整形
    assert "/data/legends" in h and 'href="/data"' in h  # cluster nav(トピクラ)


def test_newest_first_order():
    h = w.render_walkoff_html(_DATA)
    # 直近(丸)が古い(中島)より先に出る
    assert h.index("丸 佳浩") < h.index("中島 治康")


def test_empty_data_returns_empty():
    assert w.render_walkoff_html({"homeruns": []}) == ""
