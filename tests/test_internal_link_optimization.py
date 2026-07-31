from __future__ import annotations

import base64
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.data_site_backlink_injector import _backfill_page_for_date
from src.data_site_farm_source import FarmPlayerStat
from src.data_site_internal_link import linkify
from src.data_site_query import LeaderEntry
from src.data_site_template_farm import render_farm_players_html
from src.data_site_template_salary_value import _player_link as salary_value_player_link
from src.data_site_template_team import render_pitching_ranking_html, render_record_html
from src.sns_realtime_topic import (
    DATA_PAGES_CACHE,
    _fetch_data_page_slugs,
    make_tag_url_resolver,
)
from src.sns_realtime_topic_template import render_trend_chips
from src.tools.build_player_slug_map import _player_name_from_title


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "yoshilover-063-frontend.php"


def _php_eval(expression: str, payload: str = "") -> str:
    bootstrap = """
define('ABSPATH', __DIR__);
function add_action(...$args) {}
function add_filter(...$args) {}
function add_shortcode(...$args) {}
function wp_strip_all_tags($value) { return strip_tags($value); }
require $argv[1];
$payload = base64_decode($argv[2]);
"""
    proc = subprocess.run(
        [
            "php",
            "-r",
            bootstrap + expression,
            str(PLUGIN),
            base64.b64encode(payload.encode()).decode(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def test_current_player_seo_titles_reduce_to_names() -> None:
    assert (
        _player_name_from_title(
            "坂本勇人 2026年成績・打率【巨人 内野手・背番号6】 | 巨人選手データ"
        )
        == "坂本勇人"
    )
    assert (
        _player_name_from_title(
            "竹丸 和幸 2026年成績・防御率【巨人 投手・背番号21】 | 巨人選手データ"
        )
        == "竹丸 和幸"
    )
    assert _player_name_from_title("王貞治 通算成績【巨人OB】") == "王貞治"


def test_regenerated_slug_map_links_current_players() -> None:
    assert 'href="/data/sakamoto-hayato"' in linkify("坂本勇人")
    assert 'href="/data/takemaru-kazuyuki"' in linkify("竹丸和幸")
    assert 'href="/data/urata-shunsuke"' in linkify("浦田俊輔")
    assert 'href="/data/ota-taishi"' in linkify("大田泰示")
    assert 'href="/data/tatsuoka-soichiro"' in linkify("立岡宗一郎")


def test_backfill_page_rotates_but_never_uses_page_one() -> None:
    first = _backfill_page_for_date(date(2026, 7, 31))
    second = _backfill_page_for_date(date(2026, 8, 1))
    assert first >= 2
    assert second >= 2
    assert first != second


def test_board_topic_gate_rejects_non_japanese_and_non_baseball_topics() -> None:
    rejected = _php_eval(
        "$topic=(object)['ID'=>1,'post_content'=>'Toyota service'];"
        "function get_the_title($topic){return $GLOBALS['payload'];}"
        "echo yoshilover_063_board_topic_is_safe($topic) ? '1' : '0';",
        "Автосервис Тойота в Москве",
    )
    assert rejected == "0"

    unrelated = _php_eval(
        "$topic=(object)['ID'=>1,'post_content'=>'今日のおすすめ'];"
        "function get_the_title($topic){return $GLOBALS['payload'];}"
        "echo yoshilover_063_board_topic_is_safe($topic) ? '1' : '0';",
        "東京の自動車整備について",
    )
    assert unrelated == "0"


def test_board_topic_gate_allows_giants_discussion() -> None:
    accepted = _php_eval(
        "$topic=(object)['ID'=>1,'post_content'=>'先発投手について語ろう'];"
        "function get_the_title($topic){return $GLOBALS['payload'];}"
        "echo yoshilover_063_board_topic_is_safe($topic) ? '1' : '0';",
        "今日の巨人戦を振り返る",
    )
    assert accepted == "1"


def test_board_topic_link_is_single_ugc_nofollow_candidate() -> None:
    source = PLUGIN.read_text(encoding="utf-8")
    assert "$variant === 'bottom' ? yoshilover_063_get_board_hot_topic()" in source
    assert 'rel="ugc nofollow"' in source


def test_legacy_about_menu_link_is_repaired() -> None:
    repaired = _php_eval(
        "function home_url($path=''){return 'https://yoshilover.com'.$path;}"
        "$item=(object)['ID'=>55464];"
        "$atts=yoshilover_063_repair_legacy_about_menu_link("
        "['href'=>'https://yoshilover.com/?page_id=1980'],$item);"
        "echo $atts['href'];"
    )
    assert repaired == "https://yoshilover.com/about-yoshilover"


def test_home_hub_links_previously_orphaned_assets() -> None:
    source = PLUGIN.read_text(encoding="utf-8")
    assert "'href' => '/data/opening-pitchers'" in source
    assert "'href' => '/giants-sns-realtime-1gun'" in source
    assert "yoshilover_063_noindex_legacy_home_dashboard" in source


def test_rankings_and_record_link_only_to_existing_player_pages() -> None:
    rankings = {
        "勝利": [
            LeaderEntry("別所毅彦", 221.0, "221勝"),
            LeaderEntry("ページ未作成選手", 1.0, "1勝"),
        ]
    }
    ranking_html = render_pitching_ranking_html({}, {}, rankings)
    assert "/data/bessho-takehiko" in ranking_html
    assert "/data/ページ未作成選手" not in ranking_html

    record_html = render_record_html({"200勝": rankings["勝利"]})
    assert "/data/bessho-takehiko" in record_html
    assert "/data/ページ未作成選手" not in record_html


def test_farm_unknown_player_name_does_not_create_japanese_slug_404() -> None:
    unknown = FarmPlayerStat(
        name="フェリス",
        role="batting",
        games="1",
        hits="1",
        hr="0",
        rbi="0",
        sb="0",
        avg="1.000",
    )
    html = render_farm_players_html([unknown], [])
    assert "フェリス" in html
    assert "/data/フェリス" not in html


def test_salary_value_prefers_current_canonical_slug() -> None:
    html = salary_value_player_link("ウィットリー", "whitley-26")
    assert "/data/salary/whitley/" in html
    assert "whitley-26" not in html


def test_sns_topic_does_not_fallback_to_unverified_tag_archive() -> None:
    resolver = make_tag_url_resolver({"sakamoto-hayato"})
    assert resolver("坂本勇人").endswith("/data/sakamoto-hayato/")
    assert resolver("久保康生") == ""
    html = render_trend_chips(
        {"久保康生": 2},
        tag_url_for=resolver,
    )
    assert "/tag/" not in html
    assert "<span" in html


def test_sns_data_page_lookup_paginates_beyond_first_hundred() -> None:
    parent = MagicMock(status_code=200)
    parent.json.return_value = [{"id": 99}]
    first = MagicMock(status_code=200)
    first.json.return_value = [{"slug": f"player-{i}"} for i in range(100)]
    second = MagicMock(status_code=200)
    second.json.return_value = [{"slug": "player-100"}, {"slug": "player-101"}]
    for response in (parent, first, second):
        response.raise_for_status.return_value = None
    client = SimpleNamespace(api="https://example.test/wp-json/wp/v2", auth=("u", "p"))
    DATA_PAGES_CACHE.clear()
    with patch(
        "src.sns_realtime_topic.requests.get",
        side_effect=[parent, first, second],
    ) as get:
        slugs = _fetch_data_page_slugs(client)
    assert len(slugs) == 102
    assert "player-101" in slugs
    assert get.call_count == 3
