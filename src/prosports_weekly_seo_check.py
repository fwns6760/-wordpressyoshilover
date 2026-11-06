"""prosports.yoshilover.com 週次 SEO チェック (Cloud Run Job)。

目的: AI で 1 日 10 本以上出しているサブドメインが「量 > 質」に傾いた兆しを、
      user が覚えていなくても毎週メールで受け取れるようにする (read-only、サイトへの書き込みなし)。

見るもの (すべて GSC / 公開 REST から取得、状態ファイル不要):
  1. 直近 7 日に公開した記事の インデックス登録率 (URL 検査 API)
  2. 公開 14〜35 日目の記事の 1 本あたり表示回数 を、
     ひとつ前の世代 (今 42〜63 日目の記事) が同じ年齢だったときの値と比較
  3. サイト全体の 表示 / クリック (直近 28 日 vs 前 28 日)
  4. 一人一記事の崩れ (同じ名前の検索語が、自宅・hub 以外の 2 記事以上に分散)
  5. どの hub (球団別一覧など) からもリンクされていない記事
  6. AI 検索での見え方 (LLMO、2026-11-06): AI クローラーの記事取得数と、AI チャット/AI 検索から
     の訪問数 (直近 7 日 vs 前 7 日)。サイト側 Code Snippet #53 が数え、公開 REST
     /wp-json/prosports/v1/ai-visibility で返す集計値を読むだけ。
  7. タイトル絞り込みの材料 (2026-11-06 user GO): 公開 60 日以上の記事について、タイトルにあるのに
     検索語に一度も出ない語と、検索語にあるのにタイトルに無い語を記事別に出す。月初の週 (1〜7 日) の
     週次か、env TITLE_REPORT=1 のときだけ載せる。判断と編集は user (Claude はタイトルを変えない)。

いずれかが閾値を超えたら件名に【要確認】を付ける。

認証: Secret Manager `gsc-adc-oauth` (gsc_monthly_report と同じ)。
メール: 既存 mail_delivery_bridge (Gmail SMTP)。

env:
  GSC_OAUTH_JSON          — secretRef で注入される OAuth json (必須)
  GSC_SITE_URL            — 既定 https://prosports.yoshilover.com/
  GSC_REPORT_MAIL_ENABLED — "1" で実送信 (既定 dry-run)
  WEEKLY_INSPECT_CAP      — URL 検査の上限件数 (既定 120)
  TITLE_REPORT            — "1" でタイトル絞り込み節を強制的に載せる (既定: 月初の週だけ)
  MAIL_BRIDGE_*           — mail_delivery_bridge と同じ
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html import unescape as html_unescape
from urllib.parse import unquote

import requests

from src.gsc_monthly_report import API_BASE, _headers, _oauth_access_token
from src.mail_delivery_bridge import MailRequest, send as bridge_send

LOG = logging.getLogger("prosports_weekly_seo_check")

SITE_URL = os.environ.get("GSC_SITE_URL", "https://prosports.yoshilover.com/").strip() or "https://prosports.yoshilover.com/"
UA = {"User-Agent": "prosports-weekly-seo-check/1.0"}
# hub = topic cluster の親ページ。slug は 2026-11-05 時点の実在一覧 (astoral-family は牧秀悟の記事なので含めない)。
HUB_SLUGS = ["athlete-family", "athlete-homes", "baseball-family", "soccerkazokutsuma"] + [
    f"{t}-tsuma-kazoku"
    for t in ("baystars", "buffaloes", "carp", "dragons", "eagles", "fighters", "giants-geneki", "hanshin", "hawks", "lions", "marines", "swallows")
]
HOME_RE = re.compile(r"jitaku|tsuma-kazoku|-family/|homes/|soccerkazokutsuma")
# 2026-11-05 に user と確認済みで問題ない分散 (同姓の別人 / 自宅・年俸など別テーマ / 統合済み旧 URL の名残)。
# 新しい名前だけをメールに載せるための除外。家族記事どうしの分散が新たに出れば、ここに無いので載る。
CANNIBAL_KNOWN_OK = {"相川亮二", "桑田真澄", "立浪和義", "立浪", "高橋", "宮本", "川崎宗則", "平田由佳", "西岡", "阿部", "阿部慎之助", "中村", "カープ", "巨人", "阪神"}

# 閾値 (user 合意 2026-11-05: 登録率 / 1 本あたり表示 / サイト表示 の 3 つが落ちたら知らせる)
INDEX_RATE_MIN = 0.85
INDEX_RATE_MIN_POSTS = 5
COHORT_RATIO_MIN = 0.6
SITE_IMPR_RATIO_MIN = 0.7
NOT_INDEXED_MAX = 3

# タイトル絞り込み: タイトルに入りがちな家族系キーワード (長い語を先に置き、部分一致の二重数えを避ける)
TITLE_VOCAB = [
    "誹謗中傷", "馴れ初め", "再婚相手", "元嫁", "元妻", "奥さん", "嫁", "妻", "結婚", "再婚", "離婚", "彼女", "子供", "息子", "娘", "孫",
    "実家", "両親", "父親", "母親", "父", "母", "兄弟", "兄", "弟", "姉", "妹", "祖父", "祖母", "家族", "画像", "写真", "住所", "自宅", "豪邸",
    "年齢", "出身", "大学", "高校", "職業", "会社", "国籍", "宗教", "噂", "現在", "インスタ", "名前", "年収", "年俸", "死因", "病気", "トラブル", "愛車",
]
TITLE_MIN_AGE_DAYS = 60
TITLE_REPORT_CAP = 40


@dataclass
class Post:
    id: int
    date: _dt.date
    link: str
    slug: str
    title: str = ""


@dataclass
class Report:
    today: _dt.date
    window_cur: tuple[str, str]
    window_prev: tuple[str, str]
    posts_total: int = 0
    new_posts: list[Post] = field(default_factory=list)
    new_states: dict[str, str] = field(default_factory=dict)
    cohort_cur: tuple[int, float] = (0, 0.0)  # (posts, impr per post)
    cohort_prev: tuple[int, float] = (0, 0.0)
    site_cur: tuple[int, int] = (0, 0)  # (impr, clicks)
    site_prev: tuple[int, int] = (0, 0)
    cannibal: dict[str, dict[str, float]] = field(default_factory=dict)
    not_in_hub: list[str] = field(default_factory=list)
    near_page1: list[tuple[str, int, int, float]] = field(default_factory=list)
    ai_bots: dict[str, tuple[int, int]] = field(default_factory=dict)  # name -> (last 7d, prior 7d)
    ai_refs: dict[str, tuple[int, int]] = field(default_factory=dict)  # referrer domain -> (last 7d, prior 7d)
    ai_available: bool = False
    title_rows: list[tuple[str, int, list[str], list[tuple[str, int]]]] = field(default_factory=list)  # (url, impr, never-queried title words, queried words missing from title)
    title_report_on: bool = False
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- fetchers

def _posts() -> list[Post]:
    out: list[Post] = []
    page = 1
    while True:
        r = requests.get(
            f"{SITE_URL}wp-json/wp/v2/posts",
            params={"per_page": 100, "page": page, "_fields": "id,date,link,slug,title"},
            headers=UA, timeout=60,
        )
        if r.status_code == 400:  # past last page
            break
        r.raise_for_status()
        batch = r.json()
        for p in batch:
            out.append(Post(int(p["id"]), _dt.date.fromisoformat(p["date"][:10]), p["link"], p["slug"], html_unescape((p.get("title") or {}).get("rendered") or "")))
        if len(batch) < 100:
            break
        page += 1
    return out


def _gsc_rows(token: str, start: str, end: str, dimensions: list[str]) -> list[dict]:
    site = requests.utils.quote(SITE_URL, safe="")
    rows: list[dict] = []
    start_row = 0
    while True:
        body = {"startDate": start, "endDate": end, "dimensions": dimensions, "rowLimit": 25000, "startRow": start_row}
        r = requests.post(f"{API_BASE}/webmasters/v3/sites/{site}/searchAnalytics/query", headers=_headers(token), json=body, timeout=120)
        r.raise_for_status()
        got = r.json().get("rows") or []
        rows += got
        if len(got) < 25000:
            return rows
        start_row += 25000


def _inspect(token: str, url: str, attempts: int = 3) -> str:
    """URL 検査。429 / 5xx / 通信エラーは 2, 4 秒待って最大 attempts 回。最後まで駄目なら API_ERROR_<code> か INSPECT_ERROR。"""
    last = "INSPECT_ERROR"
    for i in range(attempts):
        try:
            r = requests.post(
                f"{API_BASE}/v1/urlInspection/index:inspect",
                headers=_headers(token), json={"inspectionUrl": url, "siteUrl": SITE_URL}, timeout=30,
            )
            if r.ok:
                res = (r.json().get("inspectionResult") or {}).get("indexStatusResult") or {}
                return res.get("coverageState") or res.get("verdict") or "UNKNOWN"
            last = f"API_ERROR_{r.status_code}"
            LOG.warning("inspect %s -> HTTP %s (%s) attempt %d", url, r.status_code, r.text[:160].replace("\n", " "), i + 1)
            if r.status_code < 500 and r.status_code != 429:
                return last
        except Exception as exc:  # noqa: BLE001
            last = "INSPECT_ERROR"
            LOG.warning("inspect %s failed: %r attempt %d", url, exc, i + 1)
        if i + 1 < attempts:
            time.sleep(2 * (i + 1))
    return last


def _hub_linked_urls() -> set[str]:
    linked: set[str] = set()
    for slug in HUB_SLUGS:
        try:
            html = requests.get(f"{SITE_URL}{slug}/", headers=UA, timeout=60).text
        except Exception as exc:  # noqa: BLE001
            LOG.warning("hub fetch failed %s: %r", slug, exc)
            continue
        linked |= {unquote(u) for u in re.findall(r'href="(https://prosports\.yoshilover\.com/[^"#?]+)"', html)}
        time.sleep(0.3)
    return linked


def _ai_visibility() -> dict | None:
    """Snippet #53 の日別カウンタ {YYYY-MM-DD: {"bot": {name: n}, "ref": {domain: n}}}。取れなければ None。"""
    try:
        r = requests.get(f"{SITE_URL}wp-json/prosports/v1/ai-visibility", headers=UA, timeout=60)
        r.raise_for_status()
        days = r.json().get("days")
        return days if isinstance(days, dict) else {}
    except Exception as exc:  # noqa: BLE001
        LOG.warning("ai-visibility fetch failed: %r", exc)
        return None


def ai_visibility_windows(days: dict, today: _dt.date, span: int = 7) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
    """直近 span 日 (today-span 〜 today-1) と、その前 span 日の合計を、bot 名 / 参照元ドメインごとに返す。"""
    cur_lo, cur_hi = today - _dt.timedelta(days=span), today - _dt.timedelta(days=1)
    prev_lo, prev_hi = cur_lo - _dt.timedelta(days=span), cur_lo - _dt.timedelta(days=1)
    out: dict[str, dict[str, list[int]]] = {"bot": defaultdict(lambda: [0, 0]), "ref": defaultdict(lambda: [0, 0])}
    for day, kinds in (days or {}).items():
        try:
            d = _dt.date.fromisoformat(str(day))
        except ValueError:
            continue
        slot = 0 if cur_lo <= d <= cur_hi else 1 if prev_lo <= d <= prev_hi else None
        if slot is None or not isinstance(kinds, dict):
            continue
        for kind in ("bot", "ref"):
            for key, n in (kinds.get(kind) or {}).items():
                out[kind][str(key)][slot] += int(n)
    rank = lambda m: dict(sorted(((k, (v[0], v[1])) for k, v in m.items()), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0])))  # noqa: E731
    return rank(out["bot"]), rank(out["ref"])


def title_pruning_rows(posts: list[Post], pq_rows: list[dict], today: _dt.date, min_age: int = TITLE_MIN_AGE_DAYS, cap: int = TITLE_REPORT_CAP) -> list[tuple[str, int, list[str], list[tuple[str, int]]]]:
    """公開 min_age 日以上の記事ごとに (url, 表示合計, 検索に一度も出ないタイトル語, タイトルに無い検索語 top3 [(語, 表示)]) を返す。
    検索語は GSC の query を空白で分けた語 (人名はタイトルに含まれるので自然に除外される)。"""
    by_page: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in pq_rows:
        if "#" in r["keys"][0]:
            continue
        by_page[page_key(r["keys"][0])].append((str(r["keys"][1]), float(r["impressions"])))
    out: list[tuple[str, int, list[str], list[tuple[str, int]]]] = []
    for p in posts:
        if (today - p.date).days < min_age or not p.title:
            continue
        qs = by_page.get(page_key(p.link))
        if not qs:
            continue
        total = sum(i for _, i in qs)
        seen = ""
        present: list[str] = []
        for t in TITLE_VOCAB:  # longest-first vocabulary: skip 嫁 when 元嫁 already matched that spot
            if t in p.title and t not in seen:
                present.append(t)
                seen += t
        never = [t for t in present if not any(t in q for q, _ in qs)]
        missing: dict[str, float] = defaultdict(float)
        for q, i in qs:
            for w in q.split():
                if len(w) >= 2 and w not in p.title and not re.fullmatch(r"[\W\d_]+", w):
                    missing[w] += i
        floor = max(50.0, total * 0.03)
        top = [(w, round(i)) for w, i in sorted(missing.items(), key=lambda kv: -kv[1])[:3] if i >= floor]
        if never or top:
            out.append((p.link, round(total), never, top))
    out.sort(key=lambda x: -x[1])
    return out[:cap]


def _final_url(url: str) -> str:
    try:
        return requests.head(url, headers=UA, timeout=30, allow_redirects=True).url
    except Exception:  # noqa: BLE001
        return url


# ---------------------------------------------------------------- pure logic (unit-tested)

def page_key(url: str) -> str:
    return unquote(url).split("#")[0]


def cohort_impr_per_post(posts: list[Post], impr_by_page: dict[str, float], today: _dt.date, lo: int, hi: int) -> tuple[int, float]:
    members = [p for p in posts if lo <= (today - p.date).days <= hi]
    if not members:
        return 0, 0.0
    total = sum(impr_by_page.get(page_key(p.link), 0.0) for p in members)
    return len(members), round(total / len(members), 1)


def cannibal_candidates(pq_rows: list[dict], min_impr: float = 150.0) -> dict[str, dict[str, float]]:
    """同じ名前 (検索語の先頭トークン) が、自宅記事と hub を除く 2 記事以上に分散しているもの。"""
    spl: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in pq_rows:
        page, query = r["keys"]
        u = page_key(page)
        if HOME_RE.search(u):
            continue
        name = query.split()[0] if query.split() else ""
        if len(name) < 2:
            continue
        spl[name][u] += float(r.get("impressions", 0))
    return {n: dict(d) for n, d in spl.items() if n not in CANNIBAL_KNOWN_OK and len([i for i in d.values() if i >= min_impr]) >= 2}


def compute_flags(rep: Report) -> list[str]:
    flags: list[str] = []
    n = len(rep.new_posts)
    indexed = sum(1 for s in rep.new_states.values() if s == "Submitted and indexed")
    if n >= INDEX_RATE_MIN_POSTS and indexed / n < INDEX_RATE_MIN:
        flags.append(f"新記事の登録率が {indexed}/{n} ({indexed * 100 // n}%) で {int(INDEX_RATE_MIN * 100)}% を下回った")
    not_idx = sum(1 for s in rep.new_states.values() if s == "Crawled - currently not indexed")
    if not_idx >= NOT_INDEXED_MAX:
        flags.append(f"「クロール済み・未登録」の新記事が {not_idx} 本 (Google が中身を見て登録を見送った数)")
    cp, cv = rep.cohort_cur
    pp, pv = rep.cohort_prev
    if cp >= 10 and pp >= 10 and pv > 0 and cv / pv < COHORT_RATIO_MIN:
        flags.append(f"公開 2〜5 週目の記事の 1 本あたり表示が {cv:.0f} で、前の世代 ({pv:.0f}) の {cv / pv * 100:.0f}% に低下")
    si, _ = rep.site_cur
    pi, _ = rep.site_prev
    if pi >= 10000 and si / pi < SITE_IMPR_RATIO_MIN:
        flags.append(f"サイト全体の表示回数が前 28 日の {si / pi * 100:.0f}% に低下 ({pi:,} → {si:,})")
    return flags


# ---------------------------------------------------------------- report

def build_report(inspect_cap: int = 120) -> Report:
    token = _oauth_access_token()
    today = _dt.date.today()
    end1 = today - _dt.timedelta(days=2)
    start1 = end1 - _dt.timedelta(days=27)
    end0 = start1 - _dt.timedelta(days=1)
    start0 = end0 - _dt.timedelta(days=27)
    f = lambda d: d.strftime("%Y-%m-%d")  # noqa: E731
    rep = Report(today=today, window_cur=(f(start1), f(end1)), window_prev=(f(start0), f(end0)))

    posts = _posts()
    rep.posts_total = len(posts)
    LOG.info("posts=%d", len(posts))

    cur = _gsc_rows(token, f(start1), f(end1), ["page"])
    prev = _gsc_rows(token, f(start0), f(end0), ["page"])
    impr_cur = {page_key(r["keys"][0]): float(r["impressions"]) for r in cur if "#" not in r["keys"][0]}
    impr_prev = {page_key(r["keys"][0]): float(r["impressions"]) for r in prev if "#" not in r["keys"][0]}
    rep.site_cur = (round(sum(r["impressions"] for r in cur)), round(sum(r["clicks"] for r in cur)))
    rep.site_prev = (round(sum(r["impressions"] for r in prev)), round(sum(r["clicks"] for r in prev)))

    # 1. new posts index state (URL 検査は 1 件 2〜5 秒かかるので 4 並列。quota 600/min には十分余裕)
    rep.new_posts = [p for p in posts if (today - p.date).days <= 7][:inspect_cap]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for p, state in zip(rep.new_posts, ex.map(lambda p: _inspect(token, p.link), rep.new_posts)):
            rep.new_states[p.link] = state
    LOG.info("inspected=%d", len(rep.new_states))

    # 2. cohorts at equal age: current 14-35d (current window) vs previous generation 42-63d (previous window)
    rep.cohort_cur = cohort_impr_per_post(posts, impr_cur, today, 14, 35)
    rep.cohort_prev = cohort_impr_per_post(posts, impr_prev, today, 42, 63)

    # 4. cannibalization
    pq = _gsc_rows(token, f(start1), f(end1), ["page", "query"])
    rep.cannibal = cannibal_candidates(pq)

    # 5. hub coverage (skip hubs themselves, posts younger than 1 day, and posts that 301 elsewhere)
    linked = _hub_linked_urls()
    hub_links = {f"{SITE_URL}{s}/" for s in HUB_SLUGS}
    missing = [p.link for p in posts if page_key(p.link) not in linked and p.link not in hub_links and (today - p.date).days >= 1]
    rep.not_in_hub = [u for u in missing if _final_url(u) == u]

    # bonus: near page 1 (pos 4-10, impr>=1500) — 内部リンク強化の候補
    pos_rows = {page_key(r["keys"][0]): r for r in cur if "#" not in r["keys"][0]}
    rep.near_page1 = sorted(
        [(u, round(r["impressions"]), round(r["clicks"]), r["position"]) for u, r in pos_rows.items() if r["impressions"] >= 1500 and 4.0 <= r["position"] <= 10.0 and not HOME_RE.search(u)],
        key=lambda x: -x[1],
    )[:8]

    # 7. タイトル絞り込みの材料 (月初の週 or TITLE_REPORT=1)
    rep.title_report_on = today.day <= 7 or os.environ.get("TITLE_REPORT", "").strip() == "1"
    if rep.title_report_on:
        rep.title_rows = title_pruning_rows(posts, pq, today)

    # 6. AI 検索での見え方 (snippet #53 のカウンタ)
    days = _ai_visibility()
    rep.ai_available = days is not None
    rep.ai_bots, rep.ai_refs = ai_visibility_windows(days or {}, today)

    rep.flags = compute_flags(rep)
    return rep


def render(rep: Report) -> tuple[str, str]:
    short = lambda u: u.replace(SITE_URL, "/")  # noqa: E731
    n = len(rep.new_posts)
    indexed = sum(1 for s in rep.new_states.values() if s == "Submitted and indexed")
    cp, cv = rep.cohort_cur
    pp, pv = rep.cohort_prev
    si, sc = rep.site_cur
    pi, pc = rep.site_prev
    lines = [f"prosports 週次 SEO チェック ({rep.today.isoformat()})", ""]
    if rep.flags:
        lines += ["■ 要確認"] + [f"  ・{x}" for x in rep.flags] + [""]
    else:
        lines += ["■ 異常なし (登録率・1 本あたり表示・サイト全体とも閾値内)", ""]
    lines += [
        f"■ 直近 7 日の新記事: {n} 本 / 登録済み {indexed} 本" + (f" ({indexed * 100 // n}%)" if n else ""),
    ]
    others = [(short(u), s) for u, s in rep.new_states.items() if s != "Submitted and indexed"]
    for u, s in others[:10]:
        lines.append(f"    未登録: {u}  {s}")
    lines += [
        "",
        f"■ 公開 2〜5 週目の記事 ({cp} 本): 1 本あたり表示 {cv:,.0f} 回",
        f"   前の世代が同じ年齢だったとき ({pp} 本): {pv:,.0f} 回",
        "",
        f"■ サイト全体 (直近 28 日 {rep.window_cur[0]}〜{rep.window_cur[1]} / 前 28 日)",
        f"   表示 {si:,} (前 {pi:,})  クリック {sc:,} (前 {pc:,})",
        "",
        f"■ 一人一記事の崩れ候補: {len(rep.cannibal)} 件" + ("" if rep.cannibal else " (なし)"),
    ]
    for name, d in sorted(rep.cannibal.items(), key=lambda kv: -sum(kv[1].values()))[:8]:
        pages = " / ".join(f"{short(u)} {i:.0f}" for u, i in sorted(d.items(), key=lambda x: -x[1])[:3])
        lines.append(f"    {name}: {pages}")
    if rep.cannibal:
        lines.append("    (同姓の別人・自宅記事・年俸など別テーマは問題なし。家族記事どうしなら統合を検討)")
    lines += ["", f"■ どの一覧ページ (hub) からもリンクされていない記事: {len(rep.not_in_hub)} 本" + ("" if rep.not_in_hub else " (なし)")]
    for u in rep.not_in_hub[:15]:
        lines.append(f"    {short(u)}")
    if rep.near_page1:
        lines += ["", "■ もう少しで 1 ページ目上位 (4〜10 位・表示 1,500 以上) = 内部リンク強化の候補:"]
        for u, imp, clk, pos in rep.near_page1:
            lines.append(f"    {short(u)}: 表示 {imp:,} / クリック {clk:,} / 平均 {pos:.1f} 位")
    lines += ["", "■ AI 検索での見え方 (直近 7 日 / 前 7 日)"]
    if not rep.ai_available:
        lines.append("    カウンタ (snippet #53) を取得できませんでした")
    else:
        fmt = lambda m: " / ".join(f"{k} {c} (前 {p})" for k, (c, p) in list(m.items())[:8]) or "なし"  # noqa: E731
        lines.append(f"    AI クローラーの記事取得 (キャッシュ命中分は含まず): {fmt(rep.ai_bots)}")
        lines.append(f"    AI チャット・AI 検索からの訪問: {fmt(rep.ai_refs)}")
    if rep.title_report_on:
        lines += ["", f"■ タイトル絞り込みの材料 (公開 {TITLE_MIN_AGE_DAYS} 日以上・直近 28 日の検索語・表示が多い順 {len(rep.title_rows)} 本)",
                  "   「出ない語」= タイトルにあるのに検索語に一度も現れない語 / 「無い語」= 検索語にあるのにタイトルに無い語 (表示)"]
        for u, imp, never, top in rep.title_rows:
            parts = [f"{short(u)} 表示 {imp:,}"]
            if never:
                parts.append("出ない語: " + "・".join(never))
            if top:
                parts.append("無い語: " + "・".join(f"{w} {i:,}" for w, i in top))
            lines.append("    " + " | ".join(parts))
        if not rep.title_rows:
            lines.append("    (該当なし)")
    lines += ["", f"記事総数 {rep.posts_total} 本 / 毎週月曜 10:00 JST 自動送信 (prosports-weekly-seo-check job)。サイトへの書き込みはしません。"]
    mark = "【要確認】" if rep.flags else ""
    subject = f"{mark}【prosports】週次SEOチェック {rep.today.isoformat()} — 新記事登録 {indexed}/{n}・2〜5週目 {cv:,.0f}表示/本"
    return subject, "\n".join(lines)


# ---------------------------------------------------------------- daily mode: 「URL 検査を押す必要がある記事」だけ知らせる

STRAGGLER_MIN_AGE = 2   # 公開 2 日未満はまだ自然に見つかる途中なので対象外
STRAGGLER_MAX_AGE = 14


def stragglers(posts: list[Post], states: dict[str, str], today: _dt.date) -> list[tuple[Post, str, int]]:
    """公開 2〜14 日で、まだ登録されていない記事 [(post, state, age), ...] (古い順)。"""
    out = []
    for p in posts:
        age = (today - p.date).days
        if STRAGGLER_MIN_AGE <= age <= STRAGGLER_MAX_AGE and states.get(p.link, "UNKNOWN") != "Submitted and indexed":
            out.append((p, states.get(p.link, "UNKNOWN"), age))
    return sorted(out, key=lambda x: -x[2])


JP_STATE = {
    "URL is unknown to Google": "Google がまだ知らない",
    "Discovered - currently not indexed": "検出済み・まだ見に来ていない",
    "Crawled - currently not indexed": "クロール済み・登録見送り (中身を見て登録しなかった)",
}


def render_daily(today: _dt.date, found: list[tuple[Post, str, int]], checked: int) -> tuple[str, str]:
    lines = [f"prosports 未登録記事チェック ({today.isoformat()})", "",
             f"公開 {STRAGGLER_MIN_AGE}〜{STRAGGLER_MAX_AGE} 日の記事 {checked} 本を URL 検査し、未登録は {len(found)} 本でした。", "",
             "■ Search Console で「インデックス登録をリクエスト」を押す記事 (古い順):"]
    for p, state, age in found:
        lines.append(f"  公開 {age} 日目  {p.link}")
        lines.append(f"      状態: {JP_STATE.get(state, state)}")
    lines += ["", "「クロール済み・登録見送り」は、押しても登録されないことがあります。何度も残る場合は記事の中身 (薄さ・重複) を見直す候補です。",
              "", "(毎日 09:30 JST、未登録があるときだけ送信 / prosports-index-stragglers job)"]
    return f"【要URL検査】prosports 未登録 {len(found)} 本 ({today.isoformat()})", "\n".join(lines)


def run_daily(cap: int) -> tuple[str, str] | None:
    token = _oauth_access_token()
    today = _dt.date.today()
    targets = [p for p in _posts() if STRAGGLER_MIN_AGE <= (today - p.date).days <= STRAGGLER_MAX_AGE][:cap]
    states: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for p, state in zip(targets, ex.map(lambda p: _inspect(token, p.link), targets)):
            states[p.link] = state
    found = stragglers(targets, states, today)
    LOG.info("daily: checked=%d stragglers=%d", len(targets), len(found))
    if not found:
        return None
    return render_daily(today, found, len(targets))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cap = int(os.environ.get("WEEKLY_INSPECT_CAP", "120") or 120)
    if os.environ.get("DAILY_MODE", "").strip() == "1":
        daily = run_daily(cap)
        if daily is None:
            LOG.info("daily: nothing to report, no mail")
            return 0
        subject, body = daily
    else:
        subject, body = render(build_report(cap))
    LOG.info("report built:\n%s\n%s", subject, body)
    enabled = str(os.environ.get("GSC_REPORT_MAIL_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
    to = [a.strip() for a in os.environ.get("MAIL_BRIDGE_TO", "").split(",") if a.strip()]
    result = bridge_send(MailRequest(to=to, subject=subject, text_body=body), dry_run=not enabled)
    LOG.info("mail result: status=%s reason=%s", result.status, result.reason)
    return 0 if result.status in {"sent", "dry_run"} else 1


if __name__ == "__main__":
    sys.exit(main())
