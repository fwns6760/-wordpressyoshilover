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


def _standings_base_only():
    # 自動取得(NPB std)= 拡張列なし、rank/team/g/w/l/t/pct のみ
    return [
        {"rank": 1, "team": "巨人", "g": 64, "w": 34, "l": 28, "t": 2, "pct": ".548"},
        {"rank": 2, "team": "阪神", "g": 64, "w": 34, "l": 29, "t": 1, "pct": ".540"},
    ]


def test_render_adapts_when_only_base_columns():
    # 拡張列・ランキング無しでも順位表は出る。拡張ヘッダ/ランキング見出しは出さない。
    title, html, excerpt = sa.render_standings_article(
        _standings_base_only(), date_label="2026年6月17日",
    )
    assert "セ・リーグ順位表" in html
    assert "貯金" in html
    assert "防御率" not in html        # 拡張列は出さない
    assert "個人打撃ランキング" not in html  # ランキングは渡されてない
    assert "巨人が首位" in title


def test_lede_basic_when_no_ext():
    lede = sa.build_giants_lede(_standings_base_only())
    assert "首位" in lede and "貯金+6" in lede
    assert "防御率" not in lede  # 拡張データ無し → 簡易リード


def test_short_team_name():
    assert sa.short_team_name("読売ジャイアンツ") == "巨人"
    assert sa.short_team_name("横浜DeNAベイスターズ") == "DeNA"
    assert sa.short_team_name("巨人") == "巨人"      # 既に短縮
    assert sa.short_team_name("未知球団") == "未知球団"  # 未知はそのまま


def test_render_leaders_table_highlights_giants():
    html = sa.render_leaders_table(
        "打撃", ["順位", "選手", "打率"],
        [["1", "佐藤 輝明(神)", ".359"], ["2", "ダルベック(巨)", ".249"]],
    )
    assert "打撃" in html and "ダルベック(巨)" in html
    assert "background:#fff6e5" in html  # 巨人行ハイライト


def test_render_with_leader_tables_in_title_and_body():
    lt = [{"heading": "個人打撃", "headers": ["順位", "選手", "打率"],
           "rows": [["1", "佐藤 輝明(神)", ".359"]]}]
    title, html, _ = sa.render_standings_article(
        _standings_base_only(), date_label="d", leader_tables=lt,
    )
    assert "個人成績ランキング" in title  # ランキング有り → タイトルに反映
    assert "個人打撃" in html and "佐藤 輝明(神)" in html
