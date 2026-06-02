"""NPB 選手 career page の scraper + parser (ticket 467 — 年度別成績 + 通算 + プロフィール網羅).

巨人 pillar (/data/{slug}/) は今季データしか持たないため、年度別履歴 / 通算 / プロフィールで
ライバル (my-favorite-giants 1936- / baseballdata 2011-) に負けていた。
本 module は NPB 公式 career page から取れる **全情報** を網羅取得する。

source (実取得済 2026-06-02):
- career page : ``https://npb.jp/bis/players/{npb_id}.html``
    - プロフィール  : ポジション / 投打 / 身長・体重 / 生年月日 / 経歴 / ドラフト
    - 打者 年度別+通算 (23 列): 試合 打席 打数 得点 安打 二塁打 三塁打 本塁打 塁打 打点
      盗塁 盗塁刺 犠打 犠飛 四球 死球 三振 併殺打 打率 長打率 出塁率
    - 投手 年度別+通算 (24 列): 登板 勝利 敗北 セーブ H HP 完投 完封勝 無四球 勝率 打者
      投球回 安打 本塁打 四球 死球 三振 暴投 ボーク 失点 自責点 防御率
- name -> npb_id マッピング: ``https://npb.jp/bis/teams/rst_g.html`` (巨人ロスター、 104 名のリンク)

★ network 注意 (ticket 467 §設計上の注意):
  pillar publish は 1 run で 100+ 選手を render する。各選手の career を毎回 scrape すると
  NPB に 100+ req/run × 複数 run/日 = 過負荷 + rate-limit risk。
  本 module は **純粋 parse 関数** と **単発 fetch** だけを提供する。
  日次 1 回の ingest → DB cache → pillar は DB 参照、という運用前提 (caller 側で担保)。

LLM call は一切行わない (全て決定的 parse)。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

NPB_PLAYER_URL = "https://npb.jp/bis/players/{npb_id}.html"
NPB_GIANTS_ROSTER_URL = "https://npb.jp/bis/teams/rst_g.html"

# career page header の正規列 (実取得で確定。並び順固定)
BATTING_COLUMNS: List[str] = [
    "年度", "所属球団", "試合", "打席", "打数", "得点", "安打", "二塁打", "三塁打",
    "本塁打", "塁打", "打点", "盗塁", "盗塁刺", "犠打", "犠飛", "四球", "死球",
    "三振", "併殺打", "打率", "長打率", "出塁率",
]
PITCHING_COLUMNS: List[str] = [
    "年度", "所属球団", "登板", "勝利", "敗北", "セーブ", "H", "HP", "完投", "完封勝",
    "無四球", "勝率", "打者", "投球回", "安打", "本塁打", "四球", "死球", "三振",
    "暴投", "ボーク", "失点", "自責点", "防御率",
]

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_TR_RE = re.compile(r"<tr[^>]*>.*?</tr>", re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_INNING_TABLE_RE = re.compile(r'<table class="table_inning">.*?</table>', re.S)
_ROSTER_LINK_RE = re.compile(r'/bis/players/(\d+)\.html"[^>]*>([^<]+)</a>')
_PROFILE_LABELS = ("ポジション", "投打", "身長／体重", "身長／体重".replace("／", "/"),
                   "生年月日", "経歴", "ドラフト")


def _strip_tags(fragment: str) -> str:
    text = _TAG_RE.sub("", fragment or "")
    text = text.replace("\xa0", " ").replace("　", " ")
    return re.sub(r"\s+", " ", text).strip()


def _normalize_name(raw: str) -> str:
    """全角空白・空白を除去した姓名連結キー (例: '吉川　尚輝' -> '吉川尚輝')。"""
    text = unicodedata.normalize("NFKC", raw or "")
    return re.sub(r"\s+", "", text).strip()


def _flatten_inning_tables(html: str) -> str:
    """投球回の nested ``<table class="table_inning"><th>8</th><td>.2</td>`` を ``8.2`` に潰す。

    この nested table が outer <tr> の境界を壊すため、 parse 前に必ず実施する。
    """
    def repl(match: re.Match) -> str:
        block = match.group(0)
        th = re.search(r"<th[^>]*>(.*?)</th>", block, re.S)
        td = re.search(r"<td[^>]*>(.*?)</td>", block, re.S)
        whole = _strip_tags(th.group(1)) if th else ""
        frac = _strip_tags(td.group(1)) if td else ""
        return f"<td>{whole}{frac}</td>"

    return _INNING_TABLE_RE.sub(repl, html or "")


def _cells_of_tr(tr_html: str) -> List[str]:
    return [_strip_tags(c) for c in _CELL_RE.findall(tr_html)]


def parse_giants_roster_ids(html: str) -> Dict[str, str]:
    """巨人ロスター page (rst_g.html) から {正規化名: npb_id} を抽出する純粋関数。

    例: {'田中将大': '11215114', '戸郷翔征': '41045138', ...}
    """
    if not html:
        return {}
    out: Dict[str, str] = {}
    for npb_id, raw_name in _ROSTER_LINK_RE.findall(html):
        key = _normalize_name(raw_name)
        if not key:
            continue
        # 同名衝突時は先勝ち (ロスターは原則ユニーク)
        out.setdefault(key, npb_id)
    return out


def parse_player_profile(html: str) -> Dict[str, str]:
    """career page 冒頭のプロフィール表から基本情報を抽出する純粋関数。

    返り値 key: position / bats_throws / height_weight / birthdate / school / draft
    取れなかった項目は欠落 (空文字は入れない)。
    """
    if not html:
        return {}
    profile: Dict[str, str] = {}
    label_map = {
        "ポジション": "position",
        "投打": "bats_throws",
        "身長／体重": "height_weight",
        "身長/体重": "height_weight",
        "生年月日": "birthdate",
        "経歴": "school",
        "ドラフト": "draft",
    }
    for tr in _TR_RE.findall(_flatten_inning_tables(html)):
        cells = _cells_of_tr(tr)
        if len(cells) < 2:
            continue
        key = label_map.get(cells[0].replace("／", "/"))
        if key and key not in profile and cells[1]:
            profile[key] = cells[1]
        if len(profile) >= len(set(label_map.values())):
            break
    return profile


def _parse_stats_table(html: str, kind: str) -> Optional[Dict[str, Any]]:
    """career page から打者 or 投手の年度別+通算を抽出する純粋関数。

    kind: 'bat' or 'pitch'。
    返り値: {"kind", "columns", "years": [ {col: val}, ... ], "total": {col: val} or None}
    該当表が無ければ None。
    """
    if kind == "pitch":
        columns, signature = PITCHING_COLUMNS, "防御率"
    else:
        columns, signature = BATTING_COLUMNS, "出塁率"
    ncol = len(columns)

    flat = _flatten_inning_tables(html)
    rows = [_cells_of_tr(tr) for tr in _TR_RE.findall(flat)]

    header_idx = None
    for i, cells in enumerate(rows):
        if "年度" in cells and signature in cells:
            header_idx = i
            break
    if header_idx is None:
        return None

    years: List[Dict[str, str]] = []
    total: Optional[Dict[str, str]] = None
    for cells in rows[header_idx + 1:]:
        if not cells:
            continue
        first = cells[0]
        joined = first + (cells[1] if len(cells) > 1 else "")
        if _YEAR_RE.match(first) and len(cells) >= ncol - 1:
            years.append(_zip_row(columns, cells))
        elif "通" in joined:  # 通算 行
            total = _zip_row(columns, cells)
            break
    if not years and total is None:
        return None
    return {"kind": kind, "columns": columns, "years": years, "total": total}


def _zip_row(columns: List[str], cells: List[str]) -> Dict[str, str]:
    row: Dict[str, str] = {}
    for i, col in enumerate(columns):
        val = cells[i].strip() if i < len(cells) else ""
        if i == 1:  # 所属球団: 全角空白で割れている (読 売) -> 詰める
            val = val.replace(" ", "")
        row[col] = val
    return row


def parse_player_career(html: str) -> Dict[str, Any]:
    """career page 全体を網羅 parse する純粋関数。

    返り値: {
        "profile": {...},
        "is_pitcher": bool,
        "batting": {...} or None,
        "pitching": {...} or None,
    }
    """
    profile = parse_player_profile(html)
    is_pitcher = "投手" in (profile.get("position") or "")
    batting = _parse_stats_table(html, "bat")
    pitching = _parse_stats_table(html, "pitch")
    # position が空でも投手表があれば投手扱い
    if pitching and pitching.get("years"):
        is_pitcher = True
    return {
        "profile": profile,
        "is_pitcher": is_pitcher,
        "batting": batting,
        "pitching": pitching,
    }


def _http_get(url: str, timeout: float = 12.0) -> Optional[str]:
    try:
        import vendor.requests as requests  # type: ignore[import-not-found]
    except Exception:
        try:
            import requests  # type: ignore[import-not-found]
        except Exception:
            return None
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "yoshilover-fetcher (+https://yoshilover.com)"},
        )
    except Exception:
        return None
    if getattr(resp, "status_code", 0) != 200:
        return None
    try:
        resp.encoding = "utf-8"
    except Exception:
        pass
    return getattr(resp, "text", "") or None


def fetch_giants_roster_ids(timeout: float = 12.0) -> Dict[str, str]:
    """巨人ロスターを 1 回 fetch して {正規化名: npb_id} を返す。失敗時 {}。"""
    html = _http_get(NPB_GIANTS_ROSTER_URL, timeout=timeout)
    return parse_giants_roster_ids(html or "")


def fetch_player_career(npb_id: str, timeout: float = 12.0) -> Optional[Dict[str, Any]]:
    """npb_id の career page を 1 回 fetch して網羅 parse 結果を返す。失敗時 None。

    ★ 大量ループからの直接呼び出し禁止 (§設計上の注意)。日次 ingest 専用。
    """
    if not npb_id:
        return None
    html = _http_get(NPB_PLAYER_URL.format(npb_id=str(npb_id)), timeout=timeout)
    if not html:
        return None
    result = parse_player_career(html)
    result["npb_id"] = str(npb_id)
    return result
