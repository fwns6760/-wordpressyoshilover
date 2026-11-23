import base64
import copy
import json
import sqlite3
import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from src import data_site_official_season as official
from src import data_site_query as query
from src import data_site_template_salary as salary
from src import salary_auto_refresh as auto
from src.data_site_template_pillar import _fmt_ip, _build_recent_digest_html, PillarPlayerInfo
from src.data_site_template_draft import render_draft_excerpt
from src.data_site_template_interleague import _live_complete, render_interleague_html

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT/'tests/fixtures/official_season'


def php_summary(html):
    code = """define('ABSPATH', __DIR__);
function add_action(...$a) {} function add_filter(...$a) {} function add_shortcode(...$a) {}
require $argv[1]; echo json_encode(yoshilover_063_reading_summary(base64_decode($argv[2])), JSON_UNESCAPED_UNICODE);"""
    result = subprocess.run(['php','-r',code,str(ROOT/'src/yoshilover-063-frontend.php'),
        base64.b64encode(html.encode()).decode()],capture_output=True,text=True,check=True)
    return json.loads(result.stdout)


def test_summaries_compare_counts_not_small_sample_rates_or_batter_strikeouts():
    html = '<h2>打撃成績</h2><table><tr><th>年度</th><th>打率</th><th>本塁打</th><th>三振</th></tr>'
    html += '<tr><td>2025</td><td>.900</td><td>1</td><td>100</td></tr><tr><td>2026</td><td>.280</td><td>30</td><td>80</td></tr></table>'
    result = php_summary(html)
    assert result['sentences'] == ['単年の最多本塁打は2026年の30本です。']
    assert 'NPB通算' not in json.dumps(result,ensure_ascii=False)
    assert php_summary(html.replace('2025','2026')) == []  # ambiguous team stints
    assert php_summary('<p>記録なし</p>') == []
    assert php_summary('<section id="sl-summary"></section>'+html) == []


def test_ranking_preserves_ties_and_metric():
    html = '<h2>開幕投手 回数ランキング</h2><table><tr><th>順位</th><th>投手</th><th>回数</th></tr>'
    html += '<tr><td>1</td><td>A</td><td>8回</td></tr><tr><td>2</td><td>B</td><td>7回</td></tr><tr><td>2</td><td>C</td><td>7回</td></tr></table>'
    result = php_summary(html)
    assert result['sentences'][1] == '2位はB（回数 7回）です。'
    assert result['sentences'][2].startswith('2位はC')


def test_official_table_requires_year_team_complete_counts_and_normalizes_names():
    raw = (FIX/'2026-p.html').read_text()
    records = official.parse_official_season(raw,2026,'p')
    assert records['田中将大']['ip'] == 68 + 1/3
    assert records['赤星優志']['ip'] == 53
    assert '山崎伊織' in records
    with pytest.raises(ValueError): official.parse_official_season(raw,2027,'p')
    with pytest.raises(ValueError): official.parse_official_season(raw.replace('読売ジャイアンツ','阪神タイガース'),2026,'p')
    with pytest.raises(ValueError): official.parse_official_season(raw.replace('>42<','>不明<',1),2026,'p')


def test_decimal_innings_survive_many_appearances_and_match_all_splits(tmp_path,monkeypatch):
    db=tmp_path/'test.db';c=sqlite3.connect(db)
    c.executescript('CREATE TABLE pitching_logs(game_id TEXT, player_canonical TEXT, team_name TEXT, IP REAL,K INT,BB INT,H_allowed INT,HR_allowed INT,ER INT,pitches INT,result_mark TEXT);CREATE TABLE games(game_id TEXT,game_date TEXT,opponent TEXT);')
    for i in range(30):
        gid=f'2026-05-{i+1:02}:g-t-{i+1:02}'
        c.execute('INSERT INTO games VALUES(?,?,?)',(gid,gid[:10],'阪神'))
        c.execute('INSERT INTO pitching_logs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(gid,'テスト投手','巨人',.333,1,1,1,0,1,10,''))
    c.commit();c.close();monkeypatch.setenv('INSIGHT_DB_PATH',str(db));monkeypatch.setenv('DATA_SITE_ICHIGUN_OFFICIAL','0')
    stats=query.fetch_pitching_stats_season('テスト投手')
    assert stats.ip==10 and stats.era==27 and stats.whip==6
    for fn in [query.fetch_pitcher_opponent_split_stats,query.fetch_pitcher_month_split_stats,query.fetch_pitcher_venue_split_stats]:
        rows=fn('テスト投手');assert rows[0][2]==10 and rows[0][-1]==27
    assert _fmt_ip(.667)=='0.2' and _fmt_ip(.333)=='0.1' and _fmt_ip(68+1/3)=='68.1'
    assert _fmt_ip(0)=='0.0'


def test_official_pitching_wins_over_incomplete_local_database(monkeypatch):
    rec=official.parse_official_season((FIX/'2026-p.html').read_text(),2026,'p')
    monkeypatch.setattr(official,'official_season_map',lambda *args:rec)
    monkeypatch.setenv('DATA_SITE_ICHIGUN_OFFICIAL','1')
    monkeypatch.setattr(query,'_ensure_insight_db_local',lambda: pytest.fail('official total must be preferred'))
    p=query.fetch_pitching_stats_season('田中 将大')
    assert p.games==13 and p.ip==68+1/3 and round(p.era,2)==3.42


def test_salary_summary_delta_pending_scope_and_official_performance():
    p={'name':'田中将大','slug':'tanaka-masahiro','active':True,'position':'投手',
       'salary_target_year':2027,'years':[{'year':2026,'salary_man':10000,'team':'巨人'},
       {'year':2027,'salary_man':8000,'team':'巨人','sources':[{}],'reported_on':'2026-11-20'}]}
    text=salary._salary_summary(p)
    assert '2000万円減（20%減）' in text and 'スポーツナビ' in text
    missing=copy.deepcopy(p);missing['years']=missing['years'][:1]
    assert '2027年年俸は未確認' in salary._salary_summary(missing)
    gap=copy.deepcopy(p);gap['years'][0]['year']=2025
    assert salary._salary_change(gap)==''
    state={'target_year':2027,'entries':{},'season_comparison':{'year':2026,'checked_on':'2026-11-22',
        'pitching':official.parse_official_season((FIX/'2026-p.html').read_text(),2026,'p')}}
    hydrated=auto.hydrate_data({'players':[p]},state)['players'][0]
    text=salary._salary_summary(hydrated)
    assert '68と1/3回' in text and '防御率3.42' in text and '2026年の一軍成績' in text
    state['season_comparison']['year']=2025
    assert 'season_comparison' not in auto.hydrate_data({'players':[p]},state)['players'][0]


def test_interleague_complete_requires_all_teams_and_draft_span_is_data_driven():
    from tests.test_data_site_template_interleague import SAMPLE
    data=copy.deepcopy(SAMPLE)
    data['live']={'year':2026,'giants':dict(data['years'][0],year=2026), 'standings':[{'rank':1,'team':'巨人','league':'セ','g':18,'w':12,'l':6,'t':0,'pct':'.667'}]}
    data['live']['standings']=[dict(data['live']['standings'][0],team=f'T{i}',g=18) for i in range(12)]
    assert _live_complete(data)
    text=render_interleague_html(data)
    assert '全日程終了' in text and '開催中' not in text and '暫定' not in text
    data['live']['standings'][0]['g']=17
    assert not _live_complete(data)
    assert '1965〜2026年' in render_draft_excerpt({'draft_picks':[{'year':1965},{'year':2026}]})
