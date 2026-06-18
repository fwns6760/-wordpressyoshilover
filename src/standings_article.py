"""セ・リーグ順位表 + 個人成績ランキングの「濃い」データ記事を描画する。

baseballdata.jp 並みの密度(順位表の主要列 + 打撃/投手 個人ランキング)を、
公式由来データから決定的に組み立てる。LLM 不使用 = 数字は渡されたものをそのまま
描画し、捏造しない。巨人視点のリード文も数値ランキングから機械的に生成する。

データは呼び出し側(公式 NPB extractor / 手入力)が渡す。本モジュールは描画のみ。
"""

from __future__ import annotations

import html as _html
from typing import Any, Dict, List, Sequence, Tuple

GIANTS = "巨人"


def _td(cells: Sequence[Any], highlight: bool = False) -> str:
    style = ' style="background:#fff6e5;font-weight:bold;"' if highlight else ""
    return "".join(f"<td{style}>{_html.escape(str(c))}</td>" for c in cells)


def _th(cells: Sequence[str]) -> str:
    return "".join(f"<th>{_html.escape(str(c))}</th>" for c in cells)


def _table(headers: Sequence[str], body_rows: str) -> str:
    return (
        '<table border="1" cellpadding="6" cellspacing="0" '
        'style="border-collapse:collapse;font-size:13px;text-align:center;">'
        f"<thead><tr>{_th(headers)}</tr></thead><tbody>{body_rows}</tbody></table>"
    )


def _toban(w: int, l: int) -> str:
    """貯金(勝-敗)を符号付きで。"""
    diff = int(w) - int(l)
    return f"+{diff}" if diff >= 0 else str(diff)


def _rank_of(rows: List[Dict[str, Any]], team: str, key: str, *, ascending: bool) -> int:
    """team の key 値がリーグ何位かを返す(1始まり)。同値は同順扱いの単純順位。"""
    vals = sorted((float(r[key]) for r in rows), reverse=not ascending)
    target = float(next(r[key] for r in rows if r["team"] == team))
    return vals.index(target) + 1


def build_giants_lede(standings: List[Dict[str, Any]]) -> str:
    """順位表データから巨人視点のリード文を機械生成(数値は data 由来のみ)。"""
    g = next((r for r in standings if r["team"] == GIANTS), None)
    if not g:
        return ""
    n = len(standings)
    era_rank = _rank_of(standings, GIANTS, "era", ascending=True)   # 防御率は小さいほど上位
    hr_rank = _rank_of(standings, GIANTS, "hr", ascending=False)
    avg_rank = _rank_of(standings, GIANTS, "avg", ascending=False)
    runs_rank = _rank_of(standings, GIANTS, "runs", ascending=False)
    return (
        f"首位は<strong>巨人</strong>。{g['w']}勝{g['l']}敗{g['t']}分・勝率{g['pct']}・"
        f"貯金{_toban(g['w'], g['l'])}でリーグをリードする。"
        f"<strong>チーム防御率{g['era']}はリーグ{era_rank}位</strong>、"
        f"<strong>本塁打{g['hr']}はリーグ{hr_rank}位</strong>。一方で"
        f"チーム打率{g['avg']}はリーグ{avg_rank}位、得点{g['runs']}はリーグ{runs_rank}位"
        f"({n}球団中)と、打線の援護が今後の鍵になる。"
        if g.get("rank") == 1
        else
        f"<strong>巨人</strong>は{g['rank']}位({g['w']}勝{g['l']}敗{g['t']}分・勝率{g['pct']}・"
        f"貯金{_toban(g['w'], g['l'])})。チーム防御率{g['era']}はリーグ{era_rank}位、"
        f"本塁打{g['hr']}はリーグ{hr_rank}位。"
    )


_STANDINGS_HEADERS = ["順位", "球団", "試", "勝", "敗", "分", "勝率",
                      "貯金", "得点", "失点", "本塁打", "打率", "防御率"]
_BAT_HEADERS = ["順位", "選手", "球団", "打率", "試", "打数", "安打",
               "本塁打", "打点", "出塁率", "長打率"]
_PIT_HEADERS = ["順位", "選手", "球団", "防御率", "試", "勝", "敗", "S", "投球回", "奪三振"]


def render_standings_article(
    standings: List[Dict[str, Any]],
    batting: List[Dict[str, Any]],
    pitching: List[Dict[str, Any]],
    *,
    date_label: str,
    source: str = "NPB公式成績 / スポーツナビ",
) -> Tuple[str, str, str]:
    """(title, html, excerpt) を返す。

    standings 各行: rank/team/g/w/l/t/pct/runs/runs_allowed/hr/avg/era
    batting 各行:   rank/name/team/avg/g/ab/h/hr/rbi/obp/slg
    pitching 各行:  rank/name/team/era/g/w/l/sv/ip/so
    """
    s_rows = ""
    for r in standings:
        hi = r["team"] == GIANTS
        s_rows += "<tr>" + _td(
            [r["rank"], r["team"], r["g"], r["w"], r["l"], r["t"], r["pct"],
             _toban(r["w"], r["l"]), r["runs"], r["runs_allowed"], r["hr"], r["avg"], r["era"]],
            hi,
        ) + "</tr>"

    b_rows = "".join(
        "<tr>" + _td([r["rank"], r["name"], r["team"], r["avg"], r["g"], r["ab"],
                      r["h"], r["hr"], r["rbi"], r["obp"], r["slg"]],
                     r["team"] == "巨") + "</tr>"
        for r in batting
    )
    p_rows = "".join(
        "<tr>" + _td([r["rank"], r["name"], r["team"], r["era"], r["g"], r["w"],
                      r["l"], r["sv"], r["ip"], r["so"]],
                     r["team"] == "巨") + "</tr>"
        for r in pitching
    )

    lede = build_giants_lede(standings)
    html = (
        f"<h2>セ・リーグ順位表({_html.escape(date_label)}時点)</h2>"
        f"<p>{lede}</p>"
        f"{_table(_STANDINGS_HEADERS, s_rows)}"
        f"<h2>セ・リーグ 個人打撃ランキング(打率)</h2>"
        f"{_table(_BAT_HEADERS, b_rows)}"
        f"<h2>セ・リーグ 個人投手ランキング(防御率)</h2>"
        f"{_table(_PIT_HEADERS, p_rows)}"
        f'<p style="font-size:12px;color:#888;">＜出典＞{_html.escape(source)}'
        f"({_html.escape(date_label)}時点)</p>"
    )

    top = next((r for r in standings if r.get("rank") == 1), standings[0])
    title = f"【セ・リーグ順位表】{top['team']}が首位({date_label}時点)｜打撃・投手 個人成績ランキング"
    excerpt = f"セ・リーグ順位表({top['team']}首位)と個人打撃・投手ランキングをまとめて掲載。"
    return title, html, excerpt
