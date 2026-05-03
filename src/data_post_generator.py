"""
data_post_generator.py — 巨人向けデータ記事ジェネレーター

使用例:
    python3 src/data_post_generator.py caught-stealing --dry-run
    python3 src/data_post_generator.py caught-stealing
    python3 src/data_post_generator.py caught-stealing --publish
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vendor")
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)

from dotenv import load_dotenv

from wp_client import WPClient

load_dotenv(ROOT / ".env")

LOG_FILE = ROOT / "logs" / "data_post_generator.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
CENTRAL_LEAGUE = "c"
PACIFIC_LEAGUE = "p"
LEAGUE_LABELS = {
    CENTRAL_LEAGUE: "セ・リーグ",
    PACIFIC_LEAGUE: "パ・リーグ",
}
NPB_CAUGHT_STEALING_SOURCE_LABEL = "NPB リーダーズ（盗塁阻止率・捕手）"
NPB_BATTING_SOURCE_LABEL = "NPB 個人打撃成績（読売ジャイアンツ）"
ON_BASE_MIN_PA = 10


@dataclass
class CaughtStealingEntry:
    rank: int
    player: str
    team: str
    rate: str
    year: int
    league: str


@dataclass
class BatterStatEntry:
    name: str
    games: int
    plate_appearances: int
    avg: str
    slg: str
    obp: str
    ops: str


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as res:
        return res.read().decode("utf-8", errors="ignore")


def build_npbleaders_url(year: int, league: str) -> str:
    return f"https://npb.jp/bis/{year}/stats/lf_csp2_{league}.html"


def build_npb_batting_url(year: int) -> str:
    return f"https://npb.jp/bis/{year}/stats/idb1_g.html"


def parse_caught_stealing_leaders(html: str, year: int, league: str) -> list[CaughtStealingEntry]:
    rows = re.findall(
        r'<tr class="ststats">\s*<td>(\d+)</td>\s*<td>([^<]+)\((.)\)</td>\s*<td>(\.\d+)</td>\s*</tr>',
        html,
        re.DOTALL,
    )
    entries: list[CaughtStealingEntry] = []
    for rank, player, team, rate in rows:
        entries.append(
            CaughtStealingEntry(
                rank=int(rank),
                player=player.strip(),
                team=team.strip(),
                rate=rate.strip(),
                year=year,
                league=league,
            )
        )
    return entries


def fetch_caught_stealing_leaders(year: int, league: str) -> list[CaughtStealingEntry]:
    return parse_caught_stealing_leaders(fetch_html(build_npbleaders_url(year, league)), year, league)


def find_player_entry(entries: list[CaughtStealingEntry], player: str, team: str | None = None) -> CaughtStealingEntry | None:
    for entry in entries:
        if entry.player == player and (team is None or entry.team == team):
            return entry
    return None


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").replace("\u3000", " ").replace("*", "").replace("+", "").strip()


def _parse_rate_to_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _format_ops(obp: str, slg: str) -> str:
    ops = _parse_rate_to_float(obp) + _parse_rate_to_float(slg)
    return f"{ops:.3f}".lstrip("0") if ops < 1 else f"{ops:.3f}"


def parse_team_batting_stats(html: str) -> tuple[str, list[BatterStatEntry]]:
    updated_match = re.search(r'<p class="right">([^<]+)</p>', html)
    updated_label = _strip_tags(updated_match.group(1)) if updated_match else ""
    tbody_match = re.search(r"<tbody>(.*?)</tbody>", html, re.DOTALL)
    if not tbody_match:
        return updated_label, []

    entries: list[BatterStatEntry] = []
    for row_html in re.findall(r"<tr>(.*?)</tr>", tbody_match.group(1), re.DOTALL):
        cols = [_strip_tags(col) for col in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)]
        if len(cols) < 23:
            continue
        name = cols[0]
        games = int(cols[1] or 0)
        plate_appearances = int(cols[2] or 0)
        avg = cols[20]
        slg = cols[21]
        obp = cols[22]
        entries.append(
            BatterStatEntry(
                name=name,
                games=games,
                plate_appearances=plate_appearances,
                avg=avg,
                slg=slg,
                obp=obp,
                ops=_format_ops(obp, slg),
            )
        )
    return updated_label, entries


def fetch_team_batting_stats(year: int) -> tuple[str, list[BatterStatEntry]]:
    return parse_team_batting_stats(fetch_html(build_npb_batting_url(year)))


def _comment_button(label: str, outline: bool = False) -> str:
    if outline:
        return (
            '<!-- wp:buttons {"layout":{"type":"flex","justifyContent":"center"}} -->\n'
            '<div class="wp-block-buttons" style="margin:12px 0 14px;">\n'
            '<!-- wp:button {"className":"is-style-outline"} -->\n'
            f'<div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button" href="#respond" style="font-size:0.96em;padding:12px 18px;line-height:1.35;font-weight:700;color:#F5811F;border-color:#F5811F;border-width:2px;border-style:solid;border-radius:999px;">💬 {label}</a></div>\n'
            '<!-- /wp:button -->\n'
            '</div>\n'
            '<!-- /wp:buttons -->\n\n'
        )
    return (
        '<!-- wp:buttons {"layout":{"type":"flex","justifyContent":"center"}} -->\n'
        '<div class="wp-block-buttons" style="margin:16px 0 4px;">\n'
        '<!-- wp:button -->\n'
        f'<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="#respond" style="background-color:#F5811F;color:#fff;font-size:1.06em;padding:15px 26px;line-height:1.35;font-weight:700;border-radius:999px;">💬 {label}</a></div>\n'
        '<!-- /wp:button -->\n'
        '</div>\n'
        '<!-- /wp:buttons -->\n\n'
    )


def _source_notice(updated_at: str, label: str, url: str) -> str:
    return (
        '<p style="font-size:13px;color:#666;margin-bottom:8px;">'
        f'{updated_at} 更新 / 引用元: <a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
        "</p>\n"
    )


def _source_section(items: list[tuple[str, str]]) -> str:
    rows = []
    for label, url in items:
        rows.append(
            "<li>"
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
            "</li>"
        )
    return (
        "<h3>📚 引用元</h3>\n"
        "<ul>"
        f"{''.join(rows)}"
        "</ul>\n"
    )


def _leaders_table(entries: list[CaughtStealingEntry], highlight_team: str = "巨", limit: int = 5) -> str:
    rows = []
    for entry in entries[:limit]:
        highlight = ' style="background:#fff7ef;"' if entry.team == highlight_team else ""
        rows.append(
            f'<tr{highlight}>'
            f'<td style="padding:10px 8px;text-align:center;width:44px;">{entry.rank}</td>'
            f'<td style="padding:10px 8px;font-weight:700;">{entry.player}</td>'
            f'<td style="padding:10px 8px;text-align:center;width:56px;color:#666;">{entry.team}</td>'
            f'<td style="padding:10px 8px;text-align:right;font-weight:700;color:#F5811F;width:72px;">{entry.rate}</td>'
            '</tr>'
        )
    return (
        '<div style="overflow-x:auto;margin:12px 0 18px;">'
        '<table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;background:#fff;">'
        '<thead><tr style="background:#111;color:#fff;">'
        '<th style="padding:10px 8px;width:44px;">順位</th>'
        '<th style="padding:10px 8px;">捕手</th>'
        '<th style="padding:10px 8px;width:56px;">球団</th>'
        '<th style="padding:10px 8px;width:72px;">阻止率</th>'
        '</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody>"
        '</table></div>'
    )


def _batting_table(entries: list[BatterStatEntry]) -> str:
    rows = []
    for index, entry in enumerate(entries, start=1):
        obp_value = _parse_rate_to_float(entry.obp)
        highlight = ' style="background:#fff7ef;"' if index <= 5 and entry.plate_appearances > 0 else ""
        rows.append(
            f'<tr{highlight}>'
            f'<td style="padding:10px 8px;text-align:center;width:44px;">{index}</td>'
            f'<td style="padding:10px 8px;font-weight:700;">{entry.name}</td>'
            f'<td style="padding:10px 8px;text-align:right;width:56px;">{entry.games}</td>'
            f'<td style="padding:10px 8px;text-align:right;width:64px;">{entry.plate_appearances}</td>'
            f'<td style="padding:10px 8px;text-align:right;width:72px;">{entry.avg}</td>'
            f'<td style="padding:10px 8px;text-align:right;width:72px;font-weight:700;color:#F5811F;">{entry.obp}</td>'
            f'<td style="padding:10px 8px;text-align:right;width:72px;">{entry.ops}</td>'
            "</tr>"
        )
    return (
        '<div style="overflow-x:auto;margin:12px 0 18px;">'
        '<table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;background:#fff;">'
        '<thead><tr style="background:#111;color:#fff;">'
        '<th style="padding:10px 8px;width:44px;">順</th>'
        '<th style="padding:10px 8px;">選手</th>'
        '<th style="padding:10px 8px;width:56px;">試合</th>'
        '<th style="padding:10px 8px;width:64px;">打席</th>'
        '<th style="padding:10px 8px;width:72px;">打率</th>'
        '<th style="padding:10px 8px;width:72px;">出塁率</th>'
        '<th style="padding:10px 8px;width:72px;">OPS</th>'
        '</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def _format_player_line(entry: BatterStatEntry) -> str:
    return f"{entry.name}は打率{entry.avg}、出塁率{entry.obp}、OPS{entry.ops}です。"


def _history_table(entries: list[CaughtStealingEntry]) -> str:
    if not entries:
        return '<p>過去データは取得できませんでした。</p>'
    rows = []
    for entry in entries:
        rows.append(
            '<tr>'
            f'<td style="padding:10px 8px;text-align:center;width:68px;">{entry.year}</td>'
            f'<td style="padding:10px 8px;">{LEAGUE_LABELS.get(entry.league, entry.league)}</td>'
            f'<td style="padding:10px 8px;font-weight:700;">{entry.player}</td>'
            f'<td style="padding:10px 8px;text-align:center;width:56px;color:#666;">{entry.team}</td>'
            f'<td style="padding:10px 8px;text-align:right;font-weight:700;color:#F5811F;width:72px;">{entry.rate}</td>'
            '</tr>'
        )
    return (
        '<div style="overflow-x:auto;margin:12px 0 18px;">'
        '<table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;background:#fff;">'
        '<thead><tr style="background:#f3f4f6;">'
        '<th style="padding:10px 8px;width:68px;">年</th>'
        '<th style="padding:10px 8px;">リーグ</th>'
        '<th style="padding:10px 8px;">捕手</th>'
        '<th style="padding:10px 8px;width:56px;">球団</th>'
        '<th style="padding:10px 8px;width:72px;">阻止率</th>'
        '</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody>"
        '</table></div>'
    )


def build_caught_stealing_report(year: int) -> dict:
    current_entries = fetch_caught_stealing_leaders(year, CENTRAL_LEAGUE)
    if not current_entries:
        raise RuntimeError("今季の盗塁阻止率データを取得できませんでした")

    giants_entries = [entry for entry in current_entries if entry.team == "巨"]
    giants_primary = giants_entries[0] if giants_entries else None

    history_targets = [
        (year - 2, PACIFIC_LEAGUE, "甲斐　拓也", "ソ"),
        (year - 1, PACIFIC_LEAGUE, "甲斐　拓也", "ソ"),
        (year, CENTRAL_LEAGUE, "岸田　行倫", "巨"),
        (year - 1, CENTRAL_LEAGUE, "岸田　行倫", "巨"),
        (year - 2, CENTRAL_LEAGUE, "岸田　行倫", "巨"),
    ]
    history_entries: list[CaughtStealingEntry] = []
    for target_year, league, player, team in history_targets:
        if target_year < 2020:
            continue
        try:
            rows = fetch_caught_stealing_leaders(target_year, league)
            hit = find_player_entry(rows, player, team)
            if hit:
                history_entries.append(hit)
        except Exception as exc:
            logger.warning("過去年の盗塁阻止率取得に失敗 %s %s: %s", target_year, league, exc)

    history_entries.sort(key=lambda row: (row.year, row.league), reverse=True)
    return {
        "year": year,
        "current_entries": current_entries,
        "giants_entries": giants_entries,
        "giants_primary": giants_primary,
        "history_entries": history_entries,
    }


def build_caught_stealing_title(report: dict) -> str:
    primary: CaughtStealingEntry | None = report["giants_primary"]
    if primary:
        return f"巨人捕手の盗塁阻止率をデータで見る {primary.player}はセ{primary.rank}位スタート"
    return "巨人捕手の盗塁阻止率をデータで見る セ・リーグ上位とどう違うか"


def build_caught_stealing_content(report: dict) -> str:
    year = report["year"]
    current_entries: list[CaughtStealingEntry] = report["current_entries"]
    primary: CaughtStealingEntry | None = report["giants_primary"]
    history_entries: list[CaughtStealingEntry] = report["history_entries"]
    updated_at = datetime.now().strftime("%Y年%-m月%-d日 %H:%M")

    leader = current_entries[0]
    comparison_rows = [entry for entry in current_entries[:5] if entry.team != "巨"]
    comparison_text = ""
    if primary and comparison_rows:
        ahead = [entry for entry in comparison_rows if entry.rank < primary.rank]
        behind = [entry for entry in comparison_rows if entry.rank > primary.rank]
        ahead_text = f"上には{ahead[0].player}しかいません。" if ahead else "現時点では巨人がリーグ先頭です。"
        behind_text = ""
        if behind:
            behind_names = "、".join(entry.player for entry in behind[:2])
            behind_text = f" 少なくとも{behind_names}より上にいる状態です。"
        comparison_text = (
            f"他球団と並べると、巨人は捕手守備で見劣りしていません。"
            f" {ahead_text}{behind_text}"
        )
    if primary:
        lead_text = (
            f"{year}年4月14日時点のセ・リーグ盗塁阻止率では、巨人の{primary.player}が{primary.rate}で{primary.rank}位に入っています。"
            f" 現在の首位は{leader.player}の{leader.rate}です。"
        )
        angle_text = (
            f"巨人目線では、まず{primary.player}がリーグ上位を維持できるかが焦点です。"
            " 盗塁阻止率は試行数で上下しやすいので、数字そのものより『上位帯に残れているか』を追う方が実戦向きです。"
        )
    else:
        lead_text = (
            f"{year}年4月14日時点のセ・リーグ盗塁阻止率では、巨人捕手はまだリーダーズ入りしていません。"
            f" 首位は{leader.player}の{leader.rate}です。"
        )
        angle_text = "巨人側は捕手起用が固まるほど数字が見えやすくなるので、まずは守備機会が誰に集まるかがポイントです。"

    history_text = ""
    if history_entries:
        latest_history = history_entries[0]
        history_text = (
            f"過去の推移まで見ると、巨人では{latest_history.player}の数字が基準線になります。"
            " そこに甲斐拓也の過去実績をどう重ねるかで、捕手起用の見え方がかなり変わります。"
        )

    source_url = build_npbleaders_url(year, CENTRAL_LEAGUE)
    return (
        _source_notice(updated_at, NPB_CAUGHT_STEALING_SOURCE_LABEL, source_url)
        +
        '<h2>【ニュースの整理】</h2>\n'
        f'<p>{lead_text}</p>\n'
        f'<p>{angle_text}</p>\n'
        f'<p>{history_text or "今は単発の好送球より、シーズンを通してどこまで維持できるかを見る段階です。"}</p>\n'
        '<h3>📊 セ・リーグ盗塁阻止率ランキング</h3>\n'
        f'{_leaders_table(current_entries)}\n'
        f'{_comment_button("この数字、どう見る？", outline=True)}'
        '<h3>🧭 他球団と比べた巨人の位置</h3>\n'
        f'<p>{comparison_text or "リーグ全体で見た時に、巨人捕手陣がどの帯にいるかを追うのが一番わかりやすい見方です。"}</p>\n'
        '<p>ヤクルト、阪神、DeNAの捕手と並べた時に、巨人は最低限の送球力を確保していると言えます。'
        'このテーマは打撃よりもファンの評価が割れやすいので、数字を土台に見ていくのが有効です。</p>\n'
        f'{_comment_button("他球団と比べてどう見る？", outline=True)}'
        '<h3>📈 巨人捕手の最近の推移</h3>\n'
        f'{_history_table(history_entries)}\n'
        '<h3>👀 ここに注目</h3>\n'
        '<ul>'
        '<li>岸田 行倫がこのままリーグ上位を維持できるか</li>'
        '<li>甲斐拓也の過去実績を巨人でどう活かすか</li>'
        '<li>盗塁阻止率は企図数で動くので、数試合単位で追いすぎないこと</li>'
        '</ul>\n'
        f'{_comment_button("誰を多く使いたい？", outline=True)}'
        '<h3>💬 ファンの見どころ</h3>\n'
        '<p>捕手論は打撃より守備の評価が割れやすいテーマです。'
        '数字で見ると冷静になれる一方で、試合の流れや投手との相性は数字だけでは割り切れません。'
        '巨人ファンとしては、今季どの捕手を軸に見たいかがそのまま議論になります。</p>\n'
        f'{_source_section([(NPB_CAUGHT_STEALING_SOURCE_LABEL, source_url)])}'
        f'{_comment_button("率直にどう思う？")}'
    )


def build_on_base_report(year: int) -> dict:
    updated_label, entries = fetch_team_batting_stats(year)
    if not entries:
        raise RuntimeError("巨人の打撃データを取得できませんでした")

    sorted_entries = sorted(
        entries,
        key=lambda entry: (
            entry.plate_appearances >= 20,
            _parse_rate_to_float(entry.obp),
            entry.plate_appearances,
            entry.games,
        ),
        reverse=True,
    )
    qualifying_entries = [entry for entry in sorted_entries if entry.plate_appearances >= ON_BASE_MIN_PA]
    top_entries = qualifying_entries[:3] if qualifying_entries else [entry for entry in sorted_entries if entry.plate_appearances > 0][:3]
    gap_entries = sorted(
        [entry for entry in sorted_entries if entry.plate_appearances >= 20],
        key=lambda entry: (_parse_rate_to_float(entry.obp) - _parse_rate_to_float(entry.avg), entry.plate_appearances),
        reverse=True,
    )
    return {
        "year": year,
        "updated_label": updated_label,
        "entries": sorted_entries,
        "qualifying_entries": qualifying_entries,
        "top_entries": top_entries,
        "gap_entries": gap_entries[:3],
        "source_url": build_npb_batting_url(year),
        "min_pa": ON_BASE_MIN_PA,
    }


def build_on_base_title(report: dict) -> str:
    top_entries: list[BatterStatEntry] = report["top_entries"]
    if top_entries:
        leader = top_entries[0]
        return f"巨人打線は打率だけで見ていいのか 出塁率で見ると{leader.name}が先頭に立つ"
    return "巨人打線は打率だけで見ていいのか 出塁率で全選手を並べると見え方が変わる"


def build_on_base_content(report: dict) -> str:
    updated_label = report["updated_label"] or datetime.now().strftime("%Y年%-m月%-d日現在")
    entries: list[BatterStatEntry] = report["entries"]
    qualifying_entries: list[BatterStatEntry] = report["qualifying_entries"]
    top_entries: list[BatterStatEntry] = report["top_entries"]
    gap_entries: list[BatterStatEntry] = report["gap_entries"]
    source_url = report["source_url"]
    min_pa: int = report.get("min_pa", ON_BASE_MIN_PA)
    display_entries = qualifying_entries or [entry for entry in entries if entry.plate_appearances > 0]

    lead_lines = []
    if top_entries:
        lead_lines.append(
            f"巨人の出塁率を全選手で並べると、打席数20以上では{top_entries[0].name}の{top_entries[0].obp}が先頭です。"
        )
    if len(top_entries) >= 2:
        lead_lines.append(
            f"続くのは{top_entries[1].name}の{top_entries[1].obp}で、上位打線候補の顔ぶれがかなりはっきりします。"
        )
    if gap_entries:
        gap = gap_entries[0]
        lead_lines.append(
            f"特に{gap.name}は打率{gap.avg}でも出塁率{gap.obp}まで持ってきていて、打率の印象だけでは見えないタイプです。"
        )
    else:
        lead_lines.append("打率だけでは見えにくい出塁力を、打席数と合わせて整理するのがこのページの狙いです。")

    qualifying_text = " / ".join(
        f"{entry.name} {entry.obp}" for entry in top_entries[:3]
    ) or "打席数がまだ少なく、上位は固まり切っていません。"

    note_lines = []
    if len(gap_entries) >= 2:
        note_lines.append(
            f"{gap_entries[0].name}と{gap_entries[1].name}は、打率より出塁率の方が印象を押し上げている組です。"
        )
    note_lines.append(
        "逆に単打は出ていても四球が少ない選手は、出塁率で並べると一段下がって見えます。"
    )
    note_lines.append(
        "打順を考える時は打率より、まず先に塁へ出られるかを見た方が巨人打線の並びは読みやすくなります。"
    )
    focus_gap = gap_entries[0] if gap_entries else None
    if focus_gap and any(entry.name == focus_gap.name for entry in top_entries[:2]) and len(gap_entries) >= 2:
        focus_gap = gap_entries[1]

    return (
        _source_notice(updated_label, NPB_BATTING_SOURCE_LABEL, source_url)
        +
        '<h2>【ニュースの整理】</h2>\n'
        f'<p>{" ".join(lead_lines)}</p>\n'
        f'<p>今回は打席数{min_pa}以上に絞って見ています。'
        f' 打率の数字だけで打線を評価すると、今の巨人はかなり厳しく見えます。'
        f' ただ、出塁率で並べると {qualifying_text} の順で、誰が打線を回しているかが少し違って見えてきます。</p>\n'
        f'<p>{" ".join(note_lines)}</p>\n'
        f'<h3>📊 巨人打線の出塁率一覧（{min_pa}打席以上）</h3>\n'
        f'{_batting_table(display_entries)}\n'
        f'<p style="font-size:13px;color:#666;">※ {min_pa}打席未満の選手は参考値になりやすいため、この表では除外しています。</p>\n'
        f'{_comment_button("上位打線は誰がいい？", outline=True)}'
        '<h3>🧭 打率より先に見たいポイント</h3>\n'
        f'<p>{_format_player_line(top_entries[0]) if top_entries else "主力の出塁率を追うと、打順の見え方がかなり変わります。"}</p>\n'
        f'<p>{_format_player_line(top_entries[1]) if len(top_entries) >= 2 else "上位打線候補がまだ固まり切っていません。"}</p>\n'
        f'<p>{_format_player_line(focus_gap) if focus_gap else "四球で出られる選手を上に置けるかがポイントです。"}</p>\n'
        f'{_comment_button("打率より出塁率を重視する？", outline=True)}'
        '<h3>👀 ここに注目</h3>\n'
        '<ul>'
        '<li>1番と2番に置きたいのは誰か</li>'
        '<li>打率より出塁率で見ると評価が上がる選手は誰か</li>'
        '<li>四球で塁に出られる打者をどこまで上位に並べるか</li>'
        '</ul>\n'
        '<h3>💬 ファンの見どころ</h3>\n'
        '<p>打率だけを見ると、今の巨人打線はどうしても重く見えます。'
        ' ただ、出塁率で並べると「塁に出ている選手」と「そう見えにくい選手」が分かれます。'
        ' 打順をどう組むか、誰を上位に置くかという話も、この数字からかなり議論しやすくなります。</p>\n'
        f'{_source_section([(NPB_BATTING_SOURCE_LABEL, source_url)])}'
        f'{_comment_button("この数字、どう見る？")}'
    )


def cmd_caught_stealing(args: argparse.Namespace) -> None:
    report = build_caught_stealing_report(args.year)
    title = build_caught_stealing_title(report)
    content = build_caught_stealing_content(report)

    if args.dry_run:
        print(title)
        print()
        print(content)
        return

    wp = WPClient()
    category_id = wp.resolve_category_id("コラム")
    status = "publish" if args.publish else "draft"
    post_id = wp.create_post(
        title,
        content,
        categories=[category_id] if category_id else None,
        status=status,
        allow_status_upgrade=(status == "publish"),
        caller="data_post_generator.cmd_caught_stealing",
        source_lane="data_post_generator",
    )
    logger.info("盗塁阻止率データ記事を%s post_id=%s", "公開" if args.publish else "下書き作成", post_id)
    print(post_id)


def cmd_on_base(args: argparse.Namespace) -> None:
    report = build_on_base_report(args.year)
    title = build_on_base_title(report)
    content = build_on_base_content(report)

    if args.dry_run:
        print(title)
        print()
        print(content)
        return

    wp = WPClient()
    category_id = wp.resolve_category_id("コラム")
    status = "publish" if args.publish else "draft"
    post_id = wp.create_post(
        title,
        content,
        categories=[category_id] if category_id else None,
        status=status,
        allow_status_upgrade=(status == "publish"),
        caller="data_post_generator.cmd_on_base",
        source_lane="data_post_generator",
    )
    logger.info("出塁率データ記事を%s post_id=%s", "公開" if args.publish else "下書き作成", post_id)
    print(post_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="巨人向けデータ記事ジェネレーター")
    sub = parser.add_subparsers(dest="command", required=True)

    caught = sub.add_parser("caught-stealing", help="盗塁阻止率データ記事を作成")
    caught.add_argument("--year", type=int, default=datetime.now().year, help="対象年")
    caught.add_argument("--dry-run", action="store_true", help="WordPressに投稿しない")
    caught.add_argument("--publish", action="store_true", help="公開状態で投稿する")
    caught.set_defaults(func=cmd_caught_stealing)

    on_base = sub.add_parser("on-base", help="巨人全選手の出塁率データ記事を作成")
    on_base.add_argument("--year", type=int, default=datetime.now().year, help="対象年")
    on_base.add_argument("--dry-run", action="store_true", help="WordPressに投稿しない")
    on_base.add_argument("--publish", action="store_true", help="公開状態で投稿する")
    on_base.set_defaults(func=cmd_on_base)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
