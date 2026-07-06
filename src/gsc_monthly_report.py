"""GSC 月次インデックスレポート (Cloud Run Job)。

user の「毎月 Coverage export を手渡し」を廃止し、 Search Console API から
毎月 1 日に自動でインデックス状況をメール報告する。

データ:
  1. Search Analytics — 直近 28 日 vs その前 28 日 (クリック / 表示回数、 サイト全体 + /data 配下)
  2. URL 検査 API — page-sitemap の /data ページから固定サンプル N 件の indexed 状況内訳
     (Submitted and indexed / Crawled - currently not indexed / Discovered - not indexed ...)

認証: Secret Manager `gsc-adc-oauth` (user OAuth refresh token、 webmasters.readonly scope)。
メール: 既存 mail_delivery_bridge (Gmail SMTP)。

env:
  GSC_OAUTH_JSON          — secretRef で注入される OAuth client json (必須)
  GSC_SITE_URL            — 既定 https://yoshilover.com/
  GSC_INSPECT_SAMPLE      — URL 検査サンプル数 (既定 150、 API quota 2000/day)
  GSC_REPORT_MAIL_ENABLED — "1" で実送信 (既定 dry-run)
  MAIL_BRIDGE_*           — mail_delivery_bridge と同じ
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import sys
import time

import requests

from src.mail_delivery_bridge import MailRequest, send as bridge_send

LOG = logging.getLogger("gsc_monthly_report")

SITE_URL = os.environ.get("GSC_SITE_URL", "https://yoshilover.com/").strip() or "https://yoshilover.com/"
QUOTA_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "baseballsite").strip() or "baseballsite"
API_BASE = "https://searchconsole.googleapis.com"
PAGE_SITEMAP = "https://yoshilover.com/page-sitemap.xml"
# hub は毎回必ず検査 (経過を固定観測)
HUB_SLUGS = [
    "data", "data/legends", "data/foreign-players", "data/batting-ranking",
    "data/pitching-ranking", "data/team", "data/jersey-numbers", "data/draft",
    "data/rotation", "data/notable",
]


def _oauth_access_token() -> str:
    raw = os.environ.get("GSC_OAUTH_JSON", "").strip()
    if not raw:
        raise RuntimeError("GSC_OAUTH_JSON env missing")
    cred = json.loads(raw)
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": cred["client_id"],
            "client_secret": cred["client_secret"],
            "refresh_token": cred["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": QUOTA_PROJECT,
        "Content-Type": "application/json",
    }


def _search_analytics(token: str, start: str, end: str, data_only: bool) -> dict:
    body: dict = {"startDate": start, "endDate": end}
    if data_only:
        body["dimensionFilterGroups"] = [{
            "filters": [{"dimension": "page", "operator": "contains", "expression": "/data"}]
        }]
    site = requests.utils.quote(SITE_URL, safe="")
    r = requests.post(
        f"{API_BASE}/webmasters/v3/sites/{site}/searchAnalytics/query",
        headers=_headers(token), json=body, timeout=60,
    )
    r.raise_for_status()
    rows = r.json().get("rows") or []
    if not rows:
        return {"clicks": 0, "impressions": 0}
    return {"clicks": round(rows[0].get("clicks", 0)), "impressions": round(rows[0].get("impressions", 0))}


def _top_queries(token: str, start: str, end: str, data_only: bool, limit: int = 10) -> list[tuple[str, int, int, float]]:
    """表示クエリ Top N [(query, impressions, clicks, position), ...]。"""
    body: dict = {"startDate": start, "endDate": end, "dimensions": ["query"], "rowLimit": limit}
    if data_only:
        body["dimensionFilterGroups"] = [{
            "filters": [{"dimension": "page", "operator": "contains", "expression": "/data"}]
        }]
    site = requests.utils.quote(SITE_URL, safe="")
    r = requests.post(
        f"{API_BASE}/webmasters/v3/sites/{site}/searchAnalytics/query",
        headers=_headers(token), json=body, timeout=60,
    )
    if not r.ok:
        return []
    rows = r.json().get("rows") or []
    return [(x["keys"][0], round(x.get("impressions", 0)), round(x.get("clicks", 0)), x.get("position", 0.0)) for x in rows]


def _sample_data_urls(n: int) -> list[str]:
    html = requests.get(PAGE_SITEMAP, timeout=30).text
    urls = re.findall(r"<loc>(https://yoshilover\.com/data/[^<]+)</loc>", html)
    urls = sorted(set(u.rstrip("/") for u in urls))
    hubs = [f"https://yoshilover.com/{s}" for s in HUB_SLUGS]
    rest = [u for u in urls if u not in hubs]
    # 固定 stride サンプル (毎月同じ顔ぶれ → 月次比較可能)
    if len(rest) > n:
        stride = max(1, len(rest) // n)
        rest = rest[::stride][:n]
    return hubs + rest


def _inspect(token: str, url: str) -> str:
    try:
        return _inspect_once(token, url)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("inspect failed url=%s: %r", url, exc)
        return "INSPECT_ERROR"


def _inspect_once(token: str, url: str) -> str:
    r = requests.post(
        f"{API_BASE}/v1/urlInspection/index:inspect",
        headers=_headers(token),
        json={"inspectionUrl": url, "siteUrl": SITE_URL},
        timeout=30,
    )
    if not r.ok:
        return f"API_ERROR_{r.status_code}"
    res = (r.json().get("inspectionResult") or {}).get("indexStatusResult") or {}
    return res.get("coverageState") or res.get("verdict") or "UNKNOWN"


def build_report() -> tuple[str, str]:
    token = _oauth_access_token()
    today = _dt.date.today()
    end1 = today - _dt.timedelta(days=2)  # GSC データは 2 日遅れ
    start1 = end1 - _dt.timedelta(days=27)
    end0 = start1 - _dt.timedelta(days=1)
    start0 = end0 - _dt.timedelta(days=27)
    f = lambda d: d.strftime("%Y-%m-%d")

    sa_all_cur = _search_analytics(token, f(start1), f(end1), data_only=False)
    sa_all_prev = _search_analytics(token, f(start0), f(end0), data_only=False)
    sa_data_cur = _search_analytics(token, f(start1), f(end1), data_only=True)
    sa_data_prev = _search_analytics(token, f(start0), f(end0), data_only=True)

    n = int(os.environ.get("GSC_INSPECT_SAMPLE", "150") or 150)
    urls = _sample_data_urls(n)
    counts: dict[str, int] = {}
    hub_states: list[tuple[str, str]] = []
    for i, u in enumerate(urls):
        state = _inspect(token, u)
        counts[state] = counts.get(state, 0) + 1
        if i < len(HUB_SLUGS):
            hub_states.append((u, state))
        if (i + 1) % 25 == 0:
            LOG.info("inspect progress %d/%d", i + 1, len(urls))
        time.sleep(0.3)  # quota 600/min に余裕

    indexed = sum(v for k, v in counts.items() if "indexed" in k.lower() and "not" not in k.lower())
    total = sum(counts.values())

    month = today.strftime("%Y-%m")
    lines = [
        f"ヨシラバー GSC 月次レポート ({month})",
        "",
        f"■ 検索パフォーマンス (直近28日 vs 前28日 / {f(start1)}〜{f(end1)})",
        f"  サイト全体: 表示 {sa_all_cur['impressions']:,} (前期 {sa_all_prev['impressions']:,}) / クリック {sa_all_cur['clicks']:,} (前期 {sa_all_prev['clicks']:,})",
        f"  /data 配下: 表示 {sa_data_cur['impressions']:,} (前期 {sa_data_prev['impressions']:,}) / クリック {sa_data_cur['clicks']:,} (前期 {sa_data_prev['clicks']:,})",
        "",
        f"■ /data ページのインデックス状況 (サンプル {total} 件の URL 検査)",
        f"  インデックス登録済み: {indexed} / {total} 件 ({indexed * 100 // max(total, 1)}%)",
        "",
        "  内訳:",
    ]
    for state, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {state}: {c}")
    lines += ["", "■ 主要 hub の状態:"]
    for u, s in hub_states:
        lines.append(f"    {u.replace('https://yoshilover.com/', '/')}: {s}")
    queries = _top_queries(token, f(start1), f(end1), data_only=False)
    if queries:
        lines += ["", "■ 表示クエリ Top10 (サイト全体 / 直近28日):"]
        for q, imp, clk, pos in queries:
            lines.append(f"    {q}: 表示{imp} / クリック{clk} / 平均順位{pos:.0f}")
    dqueries = _top_queries(token, f(start1), f(end1), data_only=True)
    if dqueries:
        lines += ["", "■ /data 配下の表示クエリ Top10:"]
        for q, imp, clk, pos in dqueries:
            lines.append(f"    {q}: 表示{imp} / クリック{clk} / 平均順位{pos:.0f}")
    # 2026-07-06 SEO強化: 「惜しいクエリ」= 表示は出ているのにクリックされない
    # (CTR<2% かつ 平均順位 4〜20位)。title/description を直せば取れる改善候補。
    wide = _top_queries(token, f(start1), f(end1), data_only=False, limit=200)
    near_miss = [
        (q, imp, clk, pos) for q, imp, clk, pos in wide
        if imp >= 50 and 4.0 <= pos <= 20.0 and (clk / imp if imp else 0) < 0.02
    ]
    near_miss.sort(key=lambda x: -x[1])
    if near_miss:
        lines += ["", "■ 惜しいクエリ Top10 (表示多いのにクリック少ない = title改善候補):"]
        for q, imp, clk, pos in near_miss[:10]:
            ctr = clk * 100.0 / imp if imp else 0.0
            lines.append(f"    {q}: 表示{imp} / CTR {ctr:.1f}% / 平均順位{pos:.0f}")
    lines += [
        "",
        "(毎月1日 09:00 JST 自動送信 / gsc-monthly-report job)",
    ]
    subject = f"【ヨシラバー】GSC月次レポート {month} — /data indexed {indexed}/{total}"
    return subject, "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    subject, body = build_report()
    LOG.info("report built:\n%s", body)
    enabled = str(os.environ.get("GSC_REPORT_MAIL_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
    to = [a.strip() for a in os.environ.get("MAIL_BRIDGE_TO", "").split(",") if a.strip()]
    result = bridge_send(
        MailRequest(to=to, subject=subject, text_body=body),
        dry_run=not enabled,
    )
    LOG.info("mail result: status=%s reason=%s", result.status, result.reason)
    return 0 if result.status in {"sent", "dry_run"} else 1


if __name__ == "__main__":
    sys.exit(main())
