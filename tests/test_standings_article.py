"""standings_article の描画ロジック検証(決定的・LLM不使用)。"""

from src import standings_article as sa


def _standings():
    return [
        {"rank": 1, "team": "巨人", "g": 64, "w": 34, "l": 28, "t": 2, "pct": ".548",
         "runs": 202, "runs_allowed": 205, "hr": 51, "avg": ".228", "era": "2.99"},
        {"rank": 2, "team": "阪神", "g": 64, "w": 34, "l": 29, "t": 1, "pct": ".540",
         "runs": 240, "runs_allowed": 212, "hr": 46, "avg": ".248", "era": "3.06"},
        {"rank": 5, "team": "広島", "g": 62, "w": 23, "l": 36, "t": 3, "pct": ".390",
         "runs": 175, "runs_allowed": 194, "hr": 38, "avg": ".214", "era": "2.87"},
    ]


def _batting():
    return [{"rank": 10, "name": "ダルベック", "team": "巨", "avg": ".249", "g": 61,
             "ab": 217, "h": 54, "hr": 11, "rbi": 33, "obp": ".333", "slg": ".461"}]


def _pitching():
    return [{"rank": 1, "name": "髙橋遥人", "team": "阪神", "era": "1.07", "g": 10,
             "w": 8, "l": 0, "sv": 0, "ip": "75.2", "so": 73}]


def test_toban_sign():
    assert sa._toban(34, 28) == "+6"
    assert sa._toban(26, 36) == "-10"
    assert sa._toban(30, 30) == "+0"


def test_rank_of_era_ascending():
    s = _standings()
    # era: 広島2.87 < 巨人2.99 < 阪神3.06 → 巨人は2位
    assert sa._rank_of(s, "巨人", "era", ascending=True) == 2
    assert sa._rank_of(s, "広島", "era", ascending=True) == 1


def test_giants_lede_first_place_mentions_facts():
    lede = sa.build_giants_lede(_standings())
    assert "首位" in lede and "巨人" in lede
    assert "貯金+6" in lede
    assert "防御率2.99はリーグ2位" in lede  # 機械算出


def test_render_returns_title_html_excerpt():
    title, html, excerpt = sa.render_standings_article(
        _standings(), _batting(), _pitching(), date_label="2026年6月17日",
    )
    assert "巨人が首位" in title
    assert "セ・リーグ順位表" in html
    assert "貯金" in html and "防御率" in html
    assert "background:#fff6e5" in html  # 巨人行ハイライト
    assert "ダルベック" in html and "髙橋遥人" in html
    assert "順位表" in excerpt or "首位" in excerpt


def test_render_is_deterministic():
    a = sa.render_standings_article(_standings(), _batting(), _pitching(), date_label="d")
    b = sa.render_standings_article(_standings(), _batting(), _pitching(), date_label="d")
    assert a == b  # 同入力 → 同出力(LLM 無し)
