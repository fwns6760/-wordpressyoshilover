"""451/SNS: X投稿用データカードの HTML 生成 (ヨシラバー ブランド、 巨人オレンジ)。

Phase 1 (本モジュール): insight.db 由来のデータ → 自己完結 HTML (inline CSS) を生成。
Phase 2 (別): HTML→PNG 描画 (headless Chromium 等) は環境に描画器が無いため別途インフラ判断。
本モジュールは描画器に依存せず、 HTML 文字列を返すところまで (テスト容易・¥0)。

カード型:
- render_player_card_html: 選手データカード (打率 hero + NPB順位 + 安打/打点/試合/終盤)
- render_late_inning_card_html: 「終盤に強い男」 (序盤/中盤/終盤 を横棒バー、 終盤を強調)

全カード共通の ブランド header/footer + オレンジ palette で 視覚的 identity を統一。
"""
from __future__ import annotations

import html as _html
from typing import Optional

CARD_SIZE = 1080
_HANDLE = "@yoshilover6760"
_BRAND = "ヨシラバー 巨人データ"
_SITE = "yoshilover.com/data"


def _esc(s: object) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def _fmt_avg(avg: Optional[float]) -> str:
    if avg is None:
        return "-"
    return f"{avg:.3f}".lstrip("0") if avg < 1 else f"{avg:.3f}"


# 共通 CSS (全カード)。 1080x1080、 オレンジ基調、 CJK font fallback。
_BASE_CSS = """
:root{--o:#ff6a00;--od:#e25400;--ol:#fff3ea;--gray:#dcd3cc;--ink:#161616;--mut:#7a7a7a;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Noto Sans CJK JP','Yu Gothic',sans-serif;}
.card{width:1080px;height:1080px;background:#fff;display:flex;flex-direction:column;overflow:hidden;}
.hd{background:linear-gradient(100deg,var(--o),var(--od));color:#fff;padding:36px 52px;display:flex;align-items:center;justify-content:space-between;}
.hd .brand{display:flex;align-items:center;gap:16px;}
.hd .g{width:68px;height:68px;border-radius:50%;background:#fff;color:var(--o);font-size:46px;font-weight:900;display:flex;align-items:center;justify-content:center;}
.hd .t1{font-size:30px;font-weight:900;}.hd .t2{font-size:18px;font-weight:700;opacity:.92;}
.hd .yr{font-size:26px;font-weight:900;background:rgba(0,0,0,.18);padding:7px 18px;border-radius:10px;}
.bd{flex:1;padding:50px 64px 0;display:flex;flex-direction:column;}
.ft{margin-top:auto;background:var(--ink);color:#fff;padding:24px 64px;display:flex;align-items:center;justify-content:space-between;font-size:21px;}
.ft .r{color:#ffb27a;font-weight:800;}
.name{font-size:60px;font-weight:900;color:var(--ink);line-height:1.05;}
.name .pos{font-size:26px;color:var(--od);background:var(--ol);padding:4px 14px;border-radius:8px;margin-left:14px;vertical-align:middle;}
.pt{margin:34px 0 0;font-size:34px;font-weight:800;color:var(--ink);border-left:8px solid var(--o);padding-left:22px;line-height:1.4;}
/* player card */
.hero{display:flex;align-items:flex-end;gap:44px;margin:44px 0 0;}
.hero .v{font-size:140px;font-weight:900;color:var(--o);line-height:.9;font-variant-numeric:tabular-nums;}
.hero .l{font-size:30px;font-weight:800;color:var(--mut);margin-top:6px;}
.rankpill{background:var(--o);color:#fff;font-size:34px;font-weight:900;padding:14px 30px;border-radius:999px;margin-bottom:26px;box-shadow:0 6px 18px rgba(226,84,0,.35);}
.rankpill .npb{font-size:22px;opacity:.9;margin-right:8px;}
.subs{display:flex;gap:20px;margin:48px 0 0;}
.subs .s{flex:1;background:var(--ol);border-radius:18px;padding:24px 0;text-align:center;}
.subs .s .v{font-size:56px;font-weight:900;color:var(--od);line-height:1;font-variant-numeric:tabular-nums;}
.subs .s .l{font-size:23px;font-weight:700;color:var(--mut);margin-top:10px;}
/* late-inning card */
.hook{font-size:60px;font-weight:900;color:var(--o);line-height:1;}
.hook .em{background:var(--o);color:#fff;padding:4px 18px;border-radius:14px;}
.bars{margin:42px 0 0;}
.bar{display:flex;align-items:center;gap:24px;margin:0 0 24px;}
.bar .nm{width:130px;font-size:34px;font-weight:800;color:var(--ink);flex:none;}
.bar .tr{flex:1;background:#f1e7df;border-radius:14px;height:62px;overflow:hidden;}
.bar .fl{height:100%;border-radius:14px;background:var(--gray);}
.bar.top .fl{background:linear-gradient(90deg,var(--o),var(--od));}
.bar .vl{width:160px;font-size:44px;font-weight:900;color:var(--mut);text-align:right;flex:none;font-variant-numeric:tabular-nums;}
.bar.top .vl{color:var(--o);}
"""


def _doc(body: str, css_extra: str = "") -> str:
    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        f"<style>{_BASE_CSS}{css_extra}</style></head><body>{body}</body></html>"
    )


def _header_html(year: str = "2026") -> str:
    return (
        '<div class="hd"><div class="brand"><div class="g">G</div>'
        f'<div><div class="t1">{_BRAND}</div><div class="t2">{_HANDLE}</div></div></div>'
        f'<div class="yr">{_esc(year)}</div></div>'
    )


def _footer_html(note: str) -> str:
    return f'<div class="ft"><div>{_esc(note)}</div><div class="r">{_SITE}</div></div>'


def render_player_card_html(
    *,
    name: str,
    position: str = "",
    jersey: str = "",
    season_avg: Optional[float] = None,
    hits: int = 0,
    rbi: int = 0,
    games: int = 0,
    late_avg: Optional[float] = None,
    rank_label: str = "",
    rank: Optional[int] = None,
    rank_total: Optional[int] = None,
    point_line: str = "",
    year: str = "2026",
) -> str:
    """選手データカード HTML。 打率 hero + NPB順位 pill + 安打/打点/試合/終盤打率。"""
    pos = f'<span class="pos">{_esc(position)}</span>' if position else ""
    num = f"背番号 {_esc(jersey)}" if jersey else ""
    pill = ""
    if rank and rank_total:
        pill = (
            f'<div class="rankpill"><span class="npb">NPB</span>{rank}位 '
            f'<span style="font-size:22px;opacity:.85">/{rank_total}人中</span></div>'
        )
    rank_caption = f"{_esc(rank_label)} " if rank_label else ""
    subs = [
        (str(hits), "安打"), (str(rbi), "打点"), (str(games), "試合"),
        (_fmt_avg(late_avg), "終盤打率"),
    ]
    subs_html = "".join(
        f'<div class="s"><div class="v">{_esc(v)}</div><div class="l">{_esc(l)}</div></div>'
        for v, l in subs
    )
    pt = f'<div class="pt">{_esc(point_line)}</div>' if point_line else ""
    body = (
        '<div class="card">' + _header_html(year) +
        '<div class="bd">'
        f'<div class="name">{_esc(name)}{pos}</div>'
        f'<div style="font-size:26px;font-weight:700;color:var(--od);margin-top:10px;">{num}</div>'
        '<div class="hero"><div>'
        f'<div class="v">{_fmt_avg(season_avg)}</div><div class="l">{rank_caption}打率</div>'
        f'</div>{pill}</div>'
        f'<div class="subs">{subs_html}</div>'
        f'{pt}'
        '</div>' +
        _footer_html(f"{year}シーズン ・ NPB公式box集計") +
        '</div>'
    )
    return _doc(body)


def render_pitcher_card_html(
    *,
    name: str,
    headline: str = "",
    era: Optional[float] = None,
    wins: int = 0,
    losses: int = 0,
    k: int = 0,
    ip: Optional[float] = None,
    games: int = 0,
    point_line: str = "",
    year: str = "2026",
) -> str:
    """投手データカード HTML。 防御率 hero + 勝敗/奪三振/投球回/登板。 headline=出来事見出し。"""
    def _era(v: Optional[float]) -> str:
        return f"{v:.2f}" if v is not None else "-"
    hook = (
        f'<div class="hook"><span class="em">{_esc(headline)}</span></div>'
        if headline else ""
    )
    subs = [
        (f"{wins}勝{losses}敗", "勝敗"), (str(k), "奪三振"),
        (f"{ip:.1f}" if ip is not None else "-", "投球回"), (str(games), "登板"),
    ]
    subs_html = "".join(
        f'<div class="s"><div class="v">{_esc(v)}</div><div class="l">{_esc(l)}</div></div>'
        for v, l in subs
    )
    pt = f'<div class="pt">{_esc(point_line)}</div>' if point_line else ""
    body = (
        '<div class="card">' + _header_html(year) +
        '<div class="bd">'
        f'{hook}'
        f'<div class="name" style="margin-top:18px;">{_esc(name)}<span class="pos">投手</span></div>'
        '<div class="hero"><div>'
        f'<div class="v">{_era(era)}</div><div class="l">防御率</div></div></div>'
        f'<div class="subs">{subs_html}</div>'
        f'{pt}'
        '</div>' +
        _footer_html(f"{year}シーズン ・ NPB公式box集計") +
        '</div>'
    )
    return _doc(body)


def render_late_inning_card_html(
    *,
    name: str,
    position: str = "",
    soban: Optional[float] = None,
    chuban: Optional[float] = None,
    shuban: Optional[float] = None,
    shuban_h: int = 0,
    shuban_ab: int = 0,
    year: str = "2026",
) -> str:
    """「終盤に強い男」カード HTML。 序盤/中盤/終盤を横棒バーで、 終盤(最高)を強調。"""
    pos = f'<span class="pos">{_esc(position)}</span>' if position else ""
    phases = [("序盤", soban), ("中盤", chuban), ("終盤", shuban)]
    top_val = max((v for _, v in phases if v is not None), default=0.0)

    def _bar(label: str, avg: Optional[float]) -> str:
        a = avg or 0.0
        w = max(2.0, min(100.0, a / 0.450 * 100.0))
        is_top = avg is not None and avg >= top_val and avg > 0
        cls = "bar top" if is_top else "bar"
        return (
            f'<div class="{cls}"><div class="nm">{_esc(label)}</div>'
            f'<div class="tr"><div class="fl" style="width:{w:.0f}%"></div></div>'
            f'<div class="vl">{_fmt_avg(avg)}</div></div>'
        )

    bars = "".join(_bar(l, v) for l, v in phases)
    detail = f"(終盤 {shuban_h}安打/{shuban_ab}打数)" if shuban_ab else ""
    body = (
        '<div class="card">' + _header_html(year) +
        '<div class="bd">'
        '<div class="hook"><span class="em">終盤</span>に強い男</div>'
        f'<div class="name" style="font-size:54px;margin:24px 0 0;">{_esc(name)}{pos}</div>'
        f'<div class="bars">{bars}</div>'
        f'<div class="pt">7回以降、勝負どころで打つ。{_esc(detail)}</div>'
        '</div>' +
        _footer_html(f"{year}シーズン ・ 終盤=7〜9回 ・ NPB公式box集計") +
        '</div>'
    )
    return _doc(body)
