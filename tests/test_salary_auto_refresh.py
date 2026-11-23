from __future__ import annotations

import copy
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from src import salary_auto_refresh as auto
from src import salary_contract_source as source
from src import data_site_template_salary as template
from src.data_site_template_salary_value import load_salary_value_data

FIXTURES = Path(__file__).parent / "fixtures" / "salary_contracts"


def fixture_fetch(url):
    name = "mfg-2026.html" if "my-favorite" in url else "yahoo-" + url.rsplit("=", 1)[1].replace("-", "") + ".html"
    return (FIXTURES / name).read_text()


def observed():
    return source.collect_contracts(date(2026, 11, 22), fetch=fixture_fetch)


def baked():
    return {"players": [{"name": "田中将大", "slug": "tanaka-masahiro", "active": True,
        "years": [{"year": 2026, "salary_man": 10000, "team": "巨人"}]}]}


def test_real_tables_verify_27_hold_disagreement_and_missing_source():
    data = observed()
    assert len(data["verified"]) == 27
    assert data["verified"]["田中将大"]["salary_man"] == 8000
    assert data["verified"]["泉口友汰"]["salary_man"] == 8900
    assert data["held"]["則本昂大"]["reason"] == "source_disagreement"
    assert data["held"]["李健熙"]["reason"] == "second_source_missing"
    assert "大山悠輔" not in data["verified"]  # Yahoo rowspan belongs to 阪神.
    assert data["source_requests"] == 4


@pytest.mark.parametrize("day,year", [(date(2026,11,22),2027),(date(2027,1,8),2027),
                                      (date(2027,9,30),2027),(date(2027,10,1),2028)])
def test_salary_year_does_not_roll_twice_in_january(day, year):
    assert source.salary_year(day) == year


def test_wrong_source_year_columns_and_week_are_rejected():
    mfg = fixture_fetch(source.MFG_URL.format(year=2026))
    with pytest.raises(ValueError):
        source.parse_mfg(mfg, 2028, date(2027,11,22))
    with pytest.raises(ValueError):
        source.parse_mfg(mfg.replace("2027", "2030"), 2027, date(2026,11,22))
    with pytest.raises(ValueError):
        source.parse_yahoo(fixture_fetch(source.YAHOO_URL.format(week="2026-11-16")), date(2026,11,9), 2027)
    with pytest.raises(ValueError):
        source.parse_yahoo(fixture_fetch(source.YAHOO_URL.format(week="2026-11-16")).replace("2026年", "2025年"), date(2026,11,16), 2027)


def test_future_reports_are_not_accepted():
    parsed = source.parse_mfg(fixture_fetch(source.MFG_URL.format(year=2026)), 2027, date(2026,11,19))
    assert "田中将大" not in parsed["records"]


def test_normalization_handles_variants_without_prefix_collisions():
    assert source.normalize_name("山﨑　伊織") == source.normalize_name("山崎 伊織")
    assert source.normalize_name("(翁田)大勢") == "大勢"
    assert source.normalize_name("田中 将大 （投）") == "田中将大"
    assert source.normalize_name("田中瑛斗") != "田中将大"


def test_merge_preserves_history_is_idempotent_and_records_corrections():
    base = baked()
    state, _ = auto.merge_observations(base, {"schema_version":1,"entries":{}}, observed())
    data = auto.hydrate_data(base, state)
    assert [y["salary_man"] for y in data["players"][0]["years"]] == [10000,8000]
    same, counts = auto.merge_observations(base, state, observed())
    assert same == state and counts["changed"] == 0
    corrected = observed()
    corrected["verified"]["田中将大"]["salary_man"] = 8100
    for evidence in corrected["verified"]["田中将大"]["sources"]:
        evidence["salary_man"] = 8100
    changed, counts = auto.merge_observations(base, state, corrected)
    entry = changed["entries"]["tanaka-masahiro"]["2027"]
    assert entry["revisions"][0]["salary_man"] == 8000 and counts["changed"] == 1
    assert base == baked()


def test_missing_observation_does_not_erase_persisted_year():
    state, _ = auto.merge_observations(baked(), {"schema_version":1,"entries":{}}, observed())
    no_update = observed(); no_update["verified"] = {}
    retained, _ = auto.merge_observations(baked(), state, no_update)
    assert retained["entries"] == state["entries"]


def test_pending_and_verified_do_not_mix_in_ranking_or_titles():
    base = baked()
    base["players"].append({"name":"未更改選手","slug":"pending","active":True,
                           "years":[{"year":2026,"salary_man":50000,"team":"巨人"}]})
    state, _ = auto.merge_observations(base,{"schema_version":1,"entries":{}},observed())
    data = auto.hydrate_data(base, state)
    rendered = template.render_salary_index_html(data)
    ranking, pending = rendered.split('<h2 id="sl-pending">',1)
    assert "未更改選手" not in ranking and "未更改選手" in pending
    assert "2026年 5億円" in pending
    assert "2027年" in template.render_salary_player_title(data["players"][0])
    assert "2027年は未確認" in template.render_salary_player_title(data["players"][1])
    assert "前年と同額と決まった意味ではありません" in template.render_salary_player_html(data["players"][1])


class Blob:
    def __init__(self, state=None):
        self.state = state
        self.generation = 4 if state is not None else 0
        self.size = len(json.dumps(state or {}).encode())
        self.saves = []
    def reload(self, **kwargs):
        if self.state is None:
            raise NotFound("missing")
    def download_as_bytes(self, if_generation_match, **kwargs):
        assert if_generation_match == self.generation
        return json.dumps(self.state).encode()
    def upload_from_string(self, payload, if_generation_match, **kwargs):
        if if_generation_match != self.generation:
            raise PreconditionFailed("changed")
        self.generation += 1
        self.state = json.loads(payload)
        self.size = len(payload.encode())
        self.saves.append(copy.deepcopy(self.state))


def setup_run(monkeypatch, tmp_path, blob):
    from src import data_site_official_season
    monkeypatch.setattr(data_site_official_season, "comparison_snapshot", lambda *args: None)
    path=tmp_path/'salary.json';path.write_text(json.dumps(baked()))
    monkeypatch.setattr(auto,'BASE_DATA',path)
    monkeypatch.setattr(auto,'state_blob',lambda client:blob)
    monkeypatch.setattr(template,'_reconcile_actives_with_roster',lambda data:None)


def test_source_failure_makes_no_storage_or_wp_writes(monkeypatch,tmp_path):
    blob=Blob();setup_run(monkeypatch,tmp_path,blob);publisher=Mock()
    with pytest.raises(ValueError):
        auto.refresh_salary('https://example.com',None,1,collector=Mock(side_effect=ValueError('source')),publisher=publisher)
    assert not blob.saves and not publisher.called


def test_generation_conflict_makes_no_wp_writes(monkeypatch,tmp_path):
    blob=Blob();setup_run(monkeypatch,tmp_path,blob);publisher=Mock()
    def collect(day):
        blob.generation += 1
        return observed()
    with pytest.raises(PreconditionFailed):
        auto.refresh_salary('https://example.com',None,1,collector=collect,publisher=publisher)
    assert not publisher.called


def test_lease_suppresses_overlap_and_is_released_after_partial_failure(monkeypatch,tmp_path):
    now=datetime(2026,11,22,8,tzinfo=auto.JST)
    blob=Blob({'schema_version':1,'entries':{},'lease':{'until':(now+timedelta(minutes=5)).isoformat()}})
    setup_run(monkeypatch,tmp_path,blob);collector=Mock()
    assert auto.refresh_salary('https://example.com',None,1,now=now,collector=collector)
    assert not collector.called and not blob.saves
    blob.state.pop('lease')
    assert not auto.refresh_salary('https://example.com',None,1,now=now,collector=lambda day:observed(),publisher=lambda *args:{'ok':False,'failed':['one']})
    assert len(blob.saves)==2 and 'lease' in blob.saves[0] and 'lease' not in blob.saves[-1]
    assert blob.state['entries']['tanaka-masahiro']['2027']['salary_man']==8000


def test_corrupt_existing_state_is_not_replaced_with_baked_data():
    with pytest.raises(ValueError):
        auto.load_state(Blob({'schema_version':99,'entries':{}}))


def test_salary_only_entrypoint_does_not_refresh_other_pages(monkeypatch):
    from src.tools import data_site_daily_refresh as daily
    monkeypatch.setattr(daily,'_creds',lambda:('https://example.com',None))
    monkeypatch.setattr(daily,'_find_page_id',lambda *args,**kwargs:1)
    monkeypatch.setattr(auto,'refresh_salary',lambda *args:True)
    other=Mock();monkeypatch.setattr(daily,'_refresh_other_data',other)
    monkeypatch.setattr(daily.sys,'argv',['runner','--salary-only'])
    assert daily.main()==0 and not other.called


def test_salary_failure_is_visible_but_other_pages_still_refresh(monkeypatch):
    from src.tools import data_site_daily_refresh as daily
    monkeypatch.setattr(daily,'_creds',lambda:('https://example.com',None))
    monkeypatch.setattr(daily,'_find_page_id',lambda *args,**kwargs:1)
    monkeypatch.setattr(auto,'refresh_salary',Mock(side_effect=ValueError('source')))
    other=Mock(return_value=0);monkeypatch.setattr(daily,'_refresh_other_data',other)
    monkeypatch.setattr(daily.sys,'argv',['runner'])
    assert daily.main()==1 and other.call_count==1


def test_salary_value_uses_game_year_not_calendar_or_latest_contract(tmp_path):
    path=tmp_path/'stats.db'
    conn=sqlite3.connect(path)
    conn.executescript('CREATE TABLE games(game_id TEXT,game_date TEXT); CREATE TABLE batting_logs(game_id TEXT,player_canonical TEXT,team_name TEXT,AB INT,H INT,RBI INT); CREATE TABLE pitching_logs(game_id TEXT,player_canonical TEXT,team_name TEXT,K INT,IP REAL);')
    conn.execute("INSERT INTO games VALUES('old','2025-10-01')")
    conn.execute("INSERT INTO games VALUES('last','2026-10-03')")
    conn.executemany("INSERT INTO batting_logs VALUES(?, '確認選手','巨人',100,30,10)",[('old',),('last',)])
    conn.commit();conn.close()
    sal=tmp_path/'salary.json';sal.write_text(json.dumps({'players':[{'name':'確認選手','slug':'sample','active':True,
        'years':[{'year':2026,'team':'巨人','salary_man':3000},{'year':2027,'team':'巨人','salary_man':6000}]}]}))
    data=load_salary_value_data(str(path),str(sal),now=datetime(2027,1,5,tzinfo=auto.JST))
    assert data['year']==2026 and data['stats_as_of']=='2026-10-03'
    assert data['batters'][0]['h']==30 and data['batters'][0]['unit']==100


class WP:
    def __init__(self, concurrent=False, drop_content=False):
        def page(number, slug, parent):
            return {'id':number,'slug':slug,'parent':parent,'status':'publish',
                    'date':'2026-01-01T00:00:00','date_gmt':'2025-12-31T15:00:00',
                    'link':f'https://example.com/{slug}/',
                    **{key:{'raw':'old'} for key in ('title','content','excerpt')}}
        self.pages = {10:page(10,'salary',1),11:page(11,'tanaka-masahiro',10)}
        self.posts = []
        self.concurrent, self.drop_content = concurrent, drop_content

    def response(self, value):
        return Mock(json=lambda:copy.deepcopy(value), headers={'X-WP-TotalPages':'1'})

    def get(self, url, params=None, **kwargs):
        if url.endswith('/pages'):
            return self.response([self.pages[10 if params['parent']==1 else 11]])
        page=copy.deepcopy(self.pages[int(url.rsplit('/',1)[1])])
        if self.concurrent:
            page['content']['raw']='concurrent change'
        return self.response(page)

    def post(self, url, json, **kwargs):
        number=int(url.rsplit('/',1)[1]);self.posts.append((number,json))
        for key,value in json.items():
            if key!='content' or not self.drop_content:
                self.pages[number][key]={'raw':value}
        return self.response(self.pages[number])


def test_wp_publisher_updates_then_skips_identical_rerun(monkeypatch):
    wp=WP();monkeypatch.setattr(auto,'_session',lambda auth:wp)
    state,_=auto.merge_observations(baked(),{'entries':{}},observed())
    data=auto.hydrate_data(baked(),state)
    result=auto.publish_salary_pages('https://example.com',None,1,data)
    assert result['ok'] and result['updated_pages']==1 and result['index']=='updated'
    assert len(wp.posts)==2
    again=auto.publish_salary_pages('https://example.com',None,1,data)
    assert again['unchanged_pages']==1 and again['index']=='unchanged' and len(wp.posts)==2
    assert all(set(payload)=={'title','content','excerpt'} for _,payload in wp.posts)


@pytest.mark.parametrize('concurrent,drop_content',[(True,False),(False,True)])
def test_wp_conflict_or_bad_readback_defers_index(monkeypatch,concurrent,drop_content):
    wp=WP(concurrent,drop_content);monkeypatch.setattr(auto,'_session',lambda auth:wp)
    result=auto.publish_salary_pages('https://example.com',None,1,baked())
    assert not result['ok'] and result['index']=='deferred'
    assert len(result['failed'])==1 and all(number==11 for number,_ in wp.posts)
    if concurrent:
        assert not wp.posts


def test_publisher_omits_unpublished_players_without_creating_pages_or_dead_links(monkeypatch):
    wp=WP();monkeypatch.setattr(auto,'_session',lambda auth:wp)
    data=baked();data['players'].append({'name':'未公開選手','slug':'not-published','active':True,
        'years':[{'year':2026,'team':'巨人','salary_man':3000}]})
    result=auto.publish_salary_pages('https://example.com',None,1,data)
    assert result['ok'] and result['skipped_no_page']==['not-published']
    assert 'not-published' not in wp.pages[10]['content']['raw']
    assert len(wp.posts)==2


def test_alias_collapse_requires_canonical_slug_and_identical_history():
    a={'name':'Ｆ．ウィットリー','slug':'whitley','active':True,
       'years':[{'year':2026,'team':'巨人','salary_man':20000}]}
    b={**copy.deepcopy(a),'name':'ウィットリー','slug':'whitley-26'}
    data={'players':[a,b]}
    assert auto.canonical_salary_data(data)['players']==[a]
    assert len(data['players'])==2
    b['years'][0]['salary_man']=21000
    assert len(auto.canonical_salary_data(data)['players'])==2
