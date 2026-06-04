"""data/legends ページ template (OB・レジェンド hub、老ファン向け、Phase B 452)。

既存 OB 21 名を束ね、各レジェンドのカード(通算成績 + 永久欠番/称号)→ 個別ページへ。
SEO: 「巨人 OB ランキング」「長嶋茂雄 王貞治 通算成績」等。老ファンの回遊・再訪導線。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


_RICH_TOTALS: dict | None = None


def _rich_total(slug: str) -> dict | None:
    """ob_career_yearly_full.json (ベンチ由来 rich) の通算行を slug 引き。

    名鑑テーブルにモデルケースより深い通算成績 (打点/盗塁/出塁率/OPS、 投手は S/投球回/WHIP)
    を載せるための source。 無ければ None で basic にフォールバック。
    """
    global _RICH_TOTALS
    if _RICH_TOTALS is None:
        path = _os.path.join(_os.path.dirname(__file__), "..", "config", "ob_career_yearly_full.json")
        try:
            with open(path, encoding="utf-8") as fh:
                _RICH_TOTALS = _json.load(fh)
        except Exception:
            _RICH_TOTALS = {}
    v = _RICH_TOTALS.get(slug)
    if not v:
        return None
    blk = (v.get("pitching") if v.get("is_pitcher") else v.get("batting")) or {}
    total = blk.get("total")
    if not total:
        return None
    return {"is_pitcher": bool(v.get("is_pitcher")), "total": total}


# 名鑑テーブルの表示列 (deep)。 (見出し, total キー) の順。
_BAT_COLS = [("試合", "試合"), ("安打", "安打"), ("本", "本塁打"), ("打点", "打点"),
            ("盗塁", "盗塁"), ("打率", "打率"), ("出塁", "出塁率"), ("OPS", "OPS")]
_PIT_COLS = [("登板", "登板"), ("勝", "勝利"), ("敗", "敗北"), ("S", "セーブ"),
            ("投球回", "投球回"), ("奪三", "奪三振"), ("防御率", "防御率"), ("WHIP", "WHIP")]


def render_legends_title() -> str:
    return "巨人 OB・レジェンド 通算成績【長嶋・王ほか】 | 巨人データ"


def render_legends_excerpt(entries: list) -> str:
    n = len(entries)
    return (f"読売ジャイアンツの歴代OB・レジェンド{n}名の通算成績とプロフィール。"
            "長嶋茂雄・王貞治・原辰徳・松井秀喜ほか、永久欠番や球団記録を巨人専用にまとめた。")


# 五十音表 (行ごとの個別音)。 索引は個別音単位 (駒田=「こ」、 クロマティ=「く」、 篠塚=「し」で着地)。
_GOJUON = [
    ["あ", "い", "う", "え", "お"],
    ["か", "き", "く", "け", "こ"],
    ["さ", "し", "す", "せ", "そ"],
    ["た", "ち", "つ", "て", "と"],
    ["な", "に", "ぬ", "ね", "の"],
    ["は", "ひ", "ふ", "へ", "ほ"],
    ["ま", "み", "む", "め", "も"],
    ["や", "ゆ", "よ"],
    ["ら", "り", "る", "れ", "ろ"],
    ["わ", "を", "ん"],
]
_KANA_ORDER = [k for row in _GOJUON for k in row]

# 濁点・半濁点・小書き → 清音 (索引列を統合: が→か、 ぱ→は、 ぁ→あ)。
_KANA_BASE = {
    "が": "か", "ぎ": "き", "ぐ": "く", "げ": "け", "ご": "こ",
    "ざ": "さ", "じ": "し", "ず": "す", "ぜ": "せ", "ぞ": "そ",
    "だ": "た", "ぢ": "ち", "づ": "つ", "で": "て", "ど": "と",
    "ば": "は", "び": "ひ", "ぶ": "ふ", "べ": "へ", "ぼ": "ほ",
    "ぱ": "は", "ぴ": "ひ", "ぷ": "ふ", "ぺ": "へ", "ぽ": "ほ",
    "ぁ": "あ", "ぃ": "い", "ぅ": "う", "ぇ": "え", "ぉ": "お",
    "っ": "つ", "ゃ": "や", "ゅ": "ゆ", "ょ": "よ", "ゎ": "わ", "ゐ": "い", "ゑ": "え",
}


# 50音索引の確実性のため、 source に kana 欠落がある選手を補完 (索引の穴を作らない)。
_KANA_FALLBACK = {
    "斎藤雅樹": "さいとう まさき",
    "アレックス・ラミレス": "らみれす",
}


def _kata_to_hira(ch: str) -> str:
    """カタカナ → ひらがな (助っ人外国人名 クロマティ→く 等)。 それ以外は素通し。"""
    o = ord(ch)
    if 0x30A1 <= o <= 0x30F6:  # ァ..ヶ
        return chr(o - 0x60)
    return ch


def _gyo_of(kana: str) -> str:
    """かな/カナ先頭 → 個別音ラベル (清音に正規化)。 該当しなければ『他』。"""
    if not kana:
        return "他"
    head = _kata_to_hira(kana[0])
    head = _KANA_BASE.get(head, head)
    return head if head in _KANA_ORDER else "他"


def _legend_card(e: dict) -> str:
    name = e.get("display_name", "")
    slug = e.get("slug", "")
    npb = e.get("npb") or {}
    typ = e.get("type", "batter")
    if typ == "pitcher":
        key = f'{npb.get("w", "-")}勝 / 防御率{_esc(str(npb.get("era", "-")))}'
    else:
        key = f'打率{_esc(str(npb.get("avg", "-")))}・{npb.get("hr", "-")}本'
    honor = (e.get("honors") or [""])[0]
    href = f'{CLUSTER_URL}{_esc(slug)}/' if slug else "#"
    return (
        f'<a href="{href}" style="display:block;text-decoration:none;color:inherit;'
        'border:1px solid #eee;border-radius:8px;padding:10px 12px;margin:0 0 8px;background:#fff;">'
        f'<div style="font-weight:700;color:#5d4037;">{_esc(name)} '
        f'<span style="font-size:11px;color:#888;font-weight:normal;">{_esc(e.get("years", ""))}</span></div>'
        f'<div style="font-size:13px;color:#c0392b;">{key}</div>'
        f'<div style="font-size:11px;color:#888;">{_esc(honor)}</div>'
        '</a>'
    )


def _is_pitcher_entry(e: dict) -> bool:
    rich = _rich_total(e.get("slug", ""))
    if rich is not None:
        return rich["is_pitcher"]
    return e.get("type") == "pitcher"


def _stat_cell(e: dict, key: str) -> str:
    """rich 通算 → basic npb の順で 1 セル値。 無ければ '-'。"""
    rich = _rich_total(e.get("slug", ""))
    if rich and rich["total"].get(key):
        return _esc(str(rich["total"][key]))
    npb = e.get("npb") or {}
    fb = {"試合": "games", "安打": "hits", "本塁打": "hr", "打点": "rbi", "打率": "avg",
          "登板": "games", "勝利": "w", "防御率": "era", "奪三振": "k"}
    v = npb.get(fb.get(key, "")) if key in fb else ""
    return _esc(str(v)) if v not in (None, "") else "-"


def _legend_table(entries: list, is_pitcher: bool) -> str:
    """deep 通算成績テーブル (1 行 = 1 選手、 名前→個別ページ)。 横スクロール対応。"""
    if not entries:
        return ""
    cols = _PIT_COLS if is_pitcher else _BAT_COLS
    label = "投手" if is_pitcher else "打者"
    head = ('<th style="text-align:left;padding:4px 8px;position:sticky;left:0;background:#5d4037;">選手</th>'
            '<th style="padding:4px 6px;">在籍</th>'
            + "".join(f'<th style="padding:4px 6px;">{h}</th>' for h, _ in cols))
    rows = []
    for e in entries:
        slug = e.get("slug", "")
        href = f'{CLUSTER_URL}{_esc(slug)}/' if slug else "#"
        tds = "".join(f'<td style="padding:4px 6px;text-align:right;">{_stat_cell(e, k)}</td>' for _, k in cols)
        rows.append(
            f'<tr><td style="padding:4px 8px;text-align:left;position:sticky;left:0;background:#fff;">'
            f'<a href="{href}" style="color:#e65100;text-decoration:none;font-weight:600;">{_esc(e.get("display_name", ""))}</a></td>'
            f'<td style="padding:4px 6px;text-align:center;color:#888;font-size:11px;white-space:nowrap;">{_esc(e.get("years", ""))}</td>'
            f'{tds}</tr>'
        )
    return (
        f'<div style="font-size:12px;color:#5d4037;font-weight:700;margin:8px 0 2px;">{label} ({len(entries)}名)</div>'
        '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 0 10px;">'
        '<table style="border-collapse:collapse;font-size:13px;white-space:nowrap;min-width:100%;">'
        f'<thead><tr style="background:#5d4037;color:#fff;">{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def render_legends_html(entries: list) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>歴代在籍選手</span></nav>'
    )
    entries = [e for e in entries if e]

    def _index_key(e: dict) -> str:
        # kana → 補完 → display_name (カタカナ助っ人も _gyo_of がカナ→かな変換)。
        return e.get("kana") or _KANA_FALLBACK.get(e.get("display_name", ""), "") or e.get("display_name", "")

    # 全選手を個別音で索引化 (駒田=こ / クロマティ=く / 篠塚=し で正確に着地。 行単位でなく音単位)。
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(_gyo_of(_index_key(e)), []).append(e)
    order = _KANA_ORDER + ["他"]

    sections = []
    # 五十音表クイックジャンプ (sticky 常時操作。 行レイアウトで該当音へ即移動。
    # 在籍者のいる音はオレンジリンク、 いない音は淡色)。
    rows_html = []
    for row in _GOJUON:
        btns = []
        for k in row:
            if groups.get(k):
                btns.append(f'<a href="#gyo-{k}" style="display:inline-block;width:30px;text-align:center;'
                            f'padding:5px 0;margin:1px;border:1px solid #ffcc80;border-radius:4px;'
                            f'color:#e65100;text-decoration:none;font-size:14px;font-weight:700;">{k}</a>')
            else:
                btns.append(f'<span style="display:inline-block;width:30px;text-align:center;padding:5px 0;'
                            f'margin:1px;color:#ccc;font-size:14px;">{k}</span>')
        rows_html.append('<div style="white-space:nowrap;">' + "".join(btns) + '</div>')
    sections.append(
        '<div style="position:sticky;top:0;background:#fff;z-index:5;padding:8px 0;border-bottom:1px solid #eee;margin:0 0 8px;overflow-x:auto;">'
        '<div style="font-size:12px;color:#888;margin:0 0 4px;">50音で探す:</div>'
        + "".join(rows_html) + '</div>'
    )
    for g in order:
        gl = groups.get(g)
        if not gl:
            continue
        gl.sort(key=lambda e: _index_key(e) or "んん")
        batters = [e for e in gl if not _is_pitcher_entry(e)]
        pitchers = [e for e in gl if _is_pitcher_entry(e)]
        label = g if g != "他" else "その他"
        sections.append(
            f'<h2 id="gyo-{g}" style="font-size:16px;margin:20px 0 6px;border-left:4px solid #5d4037;padding-left:8px;">'
            f'{label} <span style="font-size:12px;color:#888;font-weight:normal;">{len(gl)}名</span></h2>'
            + _legend_table(batters, is_pitcher=False)
            + _legend_table(pitchers, is_pitcher=True)
        )

    body = "".join(sections) or "<p>準備中</p>"
    return (
        '<div style="font-family:sans-serif;max-width:760px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 歴代在籍選手 通算成績名鑑</h1>'
        f'<p style="font-size:13px;color:#666;margin:0 0 14px;">読売ジャイアンツ歴代の名選手{len(entries)}名を50音で一覧。'
        '打者は打率・出塁率・OPS、投手は防御率・WHIPまで通算成績を掲載。選手名から年度別フル成績ページへ。</p>'
        f'{body}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )
