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


def _has_ext(standings: List[Dict[str, Any]]) -> bool:
    """得点/失点/本塁打/打率/防御率 の拡張列が全行に揃っているか。"""
    keys = ("runs", "runs_allowed", "hr", "avg", "era")
    return bool(standings) and all(all(k in r for k in keys) for r in standings)


def build_giants_lede(standings: List[Dict[str, Any]]) -> str:
    """順位表データから巨人視点のリード文を機械生成(数値は data 由来のみ)。

    拡張列(防御率/本塁打 等)が揃っていればチーム成績ランキングまで触れ、
    無ければ順位・勝敗・貯金だけの簡易リードにする(自動取得=NPB std のみ時)。"""
    g = next((r for r in standings if r["team"] == GIANTS), None)
    if not g:
        return ""
    head = (
        f"{'首位は' if g.get('rank') == 1 else ''}<strong>巨人</strong>"
        + ("" if g.get("rank") == 1 else f"は{g['rank']}位")
        + f"。{g['w']}勝{g['l']}敗{g['t']}分・勝率{g['pct']}・貯金{_toban(g['w'], g['l'])}"
        + ("でリーグをリードする。" if g.get("rank") == 1 else "。")
    )
    if not _has_ext(standings):
        return head
    n = len(standings)
    era_rank = _rank_of(standings, GIANTS, "era", ascending=True)   # 防御率は小さいほど上位
    hr_rank = _rank_of(standings, GIANTS, "hr", ascending=False)
    avg_rank = _rank_of(standings, GIANTS, "avg", ascending=False)
    runs_rank = _rank_of(standings, GIANTS, "runs", ascending=False)
    return (
        head
        + f"<strong>チーム防御率{g['era']}はリーグ{era_rank}位</strong>、"
        f"<strong>本塁打{g['hr']}はリーグ{hr_rank}位</strong>。一方で"
        f"チーム打率{g['avg']}はリーグ{avg_rank}位、得点{g['runs']}はリーグ{runs_rank}位"
        f"({n}球団中)。"
    )


_BASE_STANDINGS_HEADERS = ["順位", "球団", "試", "勝", "敗", "分", "勝率", "貯金"]
_EXT_STANDINGS_HEADERS = ["得点", "失点", "本塁打", "打率", "防御率"]
_BAT_HEADERS = ["順位", "選手", "球団", "打率", "試", "打数", "安打",
               "本塁打", "打点", "出塁率", "長打率"]
_PIT_HEADERS = ["順位", "選手", "球団", "防御率", "試", "勝", "敗", "S", "投球回", "奪三振"]


def render_leaders_table(heading: str, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """NPB公式の列をそのまま描画する汎用ランキング表。

    各行は「選手」セルに ``佐藤 輝明(神)`` 形式で球団を含むため、行内に ``(巨)`` を
    含む行を巨人としてハイライトする。"""
    body = ""
    for r in rows:
        hi = any("(巨)" in str(c) for c in r)
        body += "<tr>" + _td(list(r), hi) + "</tr>"
    return f"<h2>{_html.escape(heading)}</h2>" + _table(list(headers), body)


def render_standings_article(
    standings: List[Dict[str, Any]],
    batting: List[Dict[str, Any]] | None = None,
    pitching: List[Dict[str, Any]] | None = None,
    *,
    date_label: str,
    source: str = "NPB公式成績 / スポーツナビ",
    leader_tables: List[Dict[str, Any]] | None = None,
) -> Tuple[str, str, str]:
    """(title, html, excerpt) を返す。

    standings 各行(必須): rank/team/g/w/l/t/pct  (+任意: runs/runs_allowed/hr/avg/era)
    batting 各行(任意):   rank/name/team/avg/g/ab/h/hr/rbi/obp/slg
    pitching 各行(任意):  rank/name/team/era/g/w/l/sv/ip/so

    拡張列・個人ランキングは渡された時だけ描画する(自動取得=順位表のみ時に対応)。
    """
    batting = batting or []
    pitching = pitching or []
    leader_tables = leader_tables or []
    ext = _has_ext(standings)
    headers = _BASE_STANDINGS_HEADERS + (_EXT_STANDINGS_HEADERS if ext else [])

    s_rows = ""
    for r in standings:
        cells = [r["rank"], r["team"], r["g"], r["w"], r["l"], r["t"], r["pct"],
                 _toban(r["w"], r["l"])]
        if ext:
            cells += [r["runs"], r["runs_allowed"], r["hr"], r["avg"], r["era"]]
        s_rows += "<tr>" + _td(cells, r["team"] == GIANTS) + "</tr>"

    lede = build_giants_lede(standings)
    parts = [
        f"<h2>セ・リーグ順位表({_html.escape(date_label)}時点)</h2>",
        f"<p>{lede}</p>",
        _table(headers, s_rows),
    ]
    if batting:
        b_rows = "".join(
            "<tr>" + _td([r["rank"], r["name"], r["team"], r["avg"], r["g"], r["ab"],
                          r["h"], r["hr"], r["rbi"], r["obp"], r["slg"]],
                         r["team"] == "巨") + "</tr>"
            for r in batting
        )
        parts += ["<h2>セ・リーグ 個人打撃ランキング(打率)</h2>", _table(_BAT_HEADERS, b_rows)]
    if pitching:
        p_rows = "".join(
            "<tr>" + _td([r["rank"], r["name"], r["team"], r["era"], r["g"], r["w"],
                          r["l"], r["sv"], r["ip"], r["so"]],
                         r["team"] == "巨") + "</tr>"
            for r in pitching
        )
        parts += ["<h2>セ・リーグ 個人投手ランキング(防御率)</h2>", _table(_PIT_HEADERS, p_rows)]
    for lt in leader_tables:
        parts.append(render_leaders_table(lt["heading"], lt["headers"], lt["rows"]))
    parts.append(
        f'<p style="font-size:12px;color:#888;">＜出典＞{_html.escape(source)}'
        f"({_html.escape(date_label)}時点)</p>"
    )
    html = "".join(parts)

    top = next((r for r in standings if r.get("rank") == 1), standings[0])
    has_rankings = bool(batting or pitching or leader_tables)
    rank_suffix = "｜打撃・投手 個人成績ランキング" if has_rankings else ""
    title = f"【セ・リーグ順位表】{top['team']}が首位({date_label}時点){rank_suffix}"
    if has_rankings:
        excerpt = f"セ・リーグ順位表({top['team']}首位)と個人打撃・投手ランキングをまとめて掲載。"
    else:
        excerpt = f"セ・リーグ順位表({top['team']}首位)。勝敗・勝率・貯金をまとめて掲載。"
    return title, html, excerpt


# NPB 公式のフルチーム名 → 短縮表示名
_TEAM_SHORT = {
    "読売ジャイアンツ": "巨人",
    "阪神タイガース": "阪神",
    "東京ヤクルトスワローズ": "ヤクルト",
    "横浜DeNAベイスターズ": "DeNA",
    "広島東洋カープ": "広島",
    "中日ドラゴンズ": "中日",
}


def short_team_name(name: str) -> str:
    """フルチーム名を短縮名へ(未知はそのまま)。"""
    return _TEAM_SHORT.get((name or "").strip(), (name or "").strip())
