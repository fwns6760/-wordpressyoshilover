"""data/legends ページ template (OB・レジェンド hub、老ファン向け、Phase B 452)。

既存 OB 21 名を束ね、各レジェンドのカード(通算成績 + 永久欠番/称号)→ 個別ページへ。
SEO: 「巨人 OB ランキング」「長嶋茂雄 王貞治 通算成績」等。老ファンの回遊・再訪導線。
"""

from __future__ import annotations

import html as _html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


def render_legends_title() -> str:
    return "巨人 OB・レジェンド 通算成績【長嶋・王ほか】 | 巨人データ"


def render_legends_excerpt(entries: list) -> str:
    n = len(entries)
    return (f"読売ジャイアンツの歴代OB・レジェンド{n}名の通算成績とプロフィール。"
            "長嶋茂雄・王貞治・原辰徳・松井秀喜ほか、永久欠番や球団記録を巨人専用にまとめた。")


_GYO = [
    ("あ", "あいうえおぁぃぅぇぉ"),
    ("か", "かきくけこがぎぐげご"),
    ("さ", "さしすせそざじずぜぞ"),
    ("た", "たちつてとだぢづでど"),
    ("な", "なにぬねの"),
    ("は", "はひふへほばびぶべぼぱぴぷぺぽ"),
    ("ま", "まみむめも"),
    ("や", "やゆよ"),
    ("ら", "らりるれろ"),
    ("わ", "わをん"),
]


def _gyo_of(kana: str) -> str:
    """かな先頭 → 五十音行ラベル。不明は『他』。"""
    if not kana:
        return "他"
    head = kana[0]
    for label, chars in _GYO:
        if head in chars:
            return label
    return "他"


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


def render_legends_html(entries: list) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>OB・レジェンド</span></nav>'
    )
    entries = [e for e in entries if e]
    # 名球会級(honors 付き = 手動 curated)を上部に featured、残りは五十音グループ。
    featured = [e for e in entries if e.get("honors")]
    rest = [e for e in entries if not e.get("honors")]
    groups: dict[str, list] = {}
    for e in rest:
        groups.setdefault(_gyo_of(e.get("kana", "")), []).append(e)
    order = [g for g, _ in _GYO] + ["他"]

    sections = []
    if featured:
        sections.append(
            '<h2 style="font-size:16px;margin:18px 0 8px;border-left:4px solid #c0392b;padding-left:8px;">名球会・レジェンド</h2>'
            + "".join(_legend_card(e) for e in featured)
        )
    # クイックジャンプ(モバイル回遊)
    jump = " ".join(
        f'<a href="#gyo-{g}" style="display:inline-block;padding:3px 8px;margin:2px;border:1px solid #ddd;border-radius:4px;color:#5d4037;text-decoration:none;font-size:13px;">{g}</a>'
        for g in order if groups.get(g)
    )
    if jump:
        sections.append(f'<div style="margin:10px 0 4px;">{jump}</div>')
    for g in order:
        gl = groups.get(g)
        if not gl:
            continue
        gl.sort(key=lambda e: e.get("kana", "") or "")
        sections.append(
            f'<h2 id="gyo-{g}" style="font-size:16px;margin:18px 0 8px;border-left:4px solid #5d4037;padding-left:8px;">{g}行 <span style="font-size:12px;color:#888;font-weight:normal;">{len(gl)}名</span></h2>'
            + "".join(_legend_card(e) for e in gl)
        )

    body = "".join(sections) or "<p>準備中</p>"
    return (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 OB・レジェンド 通算成績</h1>'
        f'<p style="font-size:13px;color:#666;margin:0 0 14px;">歴代の名選手{len(entries)}名の通算成績とプロフィール。名前をタップで個別ページへ。</p>'
        f'{body}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )
