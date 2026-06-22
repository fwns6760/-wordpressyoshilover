"""Google Indexing API submitter — /data/ ページの crawl を能動的に促す batch。

目的:
  新興ドメインで「検出/クロール済み‑未登録」のまま放置される data-site ページに
  Indexing API (urlNotifications:publish, URL_UPDATED) を打って Googlebot の
  再クロールを誘発する。登録保証ではなく crawl 誘発。

認証:
  Secret Manager `gsc-indexer-sa-key` の service account 鍵を使用。
  この SA (gsc-indexer@baseballsite.iam.gserviceaccount.com) は GSC の
  サイト Owner に追加されている必要がある (未追加だと 403 Permission denied)。
  GOOGLE_APPLICATION_CREDENTIALS が指す鍵があればそちらを優先 (local / Cloud Run)。

quota:
  Indexing API は既定 200 requests/day。--limit (default 180) で安全側に抑える。
  429 を受けたら以降を打ち切って残りは翌日。

優先順:
  1. cluster hub + 主要 sub-hub
  2. active 支配下 69 選手の /data/{romaji} ページ
  3. --all 指定時のみ sitemap 全 /data/ URL を後続に追加

使い方:
  python3 -m src.tools.gsc_indexing_submit --dry-run         # 対象確認のみ
  python3 -m src.tools.gsc_indexing_submit --limit 180       # 本番投入
  python3 -m src.tools.gsc_indexing_submit --all --limit 200 # sitemap 全件も対象
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request

import datetime as _dt

import google.auth
from google.oauth2 import service_account
import google.auth.transport.requests

from src.data_site_query import load_shihai_names
from src.data_site_slug import player_slug

LOG = logging.getLogger("gsc_indexing_submit")

SITE = "https://yoshilover.com"
INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]
KEY_SECRET = "gsc-indexer-sa-key"
GCP_PROJECT = "baseballsite"

# cluster hub + 主要 sub-hub (回遊の起点。優先 crawl 対象)
HUB_PATHS = [
    "/data", "/data/notable", "/data/batting-ranking", "/data/pitching-ranking",
    "/data/team", "/data/standings", "/data/farm", "/data/record", "/data/mlb",
    "/data/salary", "/data/draft", "/data/jersey-numbers", "/data/foreign-players",
]


def _load_sa_credentials():
    """SA 認証情報を取得。

    優先順:
      1. GOOGLE_APPLICATION_CREDENTIALS が指す鍵 file (local 明示)
      2. gcloud で Secret Manager から鍵取得 (gcloud がある local)
      3. ambient credentials = google.auth.default (Cloud Run job が
         gsc-indexer SA として動く場合。鍵 file 不要)
    """
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path and os.path.exists(path):
        info = json.load(open(path, encoding="utf-8"))
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    try:
        raw = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             "--secret", KEY_SECRET, "--project", GCP_PROJECT],
            capture_output=True, text=True,
        ).stdout
        if raw.strip():
            info = json.loads(raw)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    except FileNotFoundError:
        pass  # gcloud 不在 (Cloud Run) → ambient へ
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def _access_token(creds: service_account.Credentials) -> str:
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _build_target_urls(include_all: bool) -> tuple[list[str], list[str]]:
    """(priority, tail) を返す。

    priority = hub + active 支配下 69 選手 (毎日必ず submit。鮮度維持 + 主力優先)。
    tail = sitemap の残り全 /data/ URL (priority に無いもの。rotate 対象)。
    """
    seen: set[str] = set()
    priority: list[str] = []

    def norm(path_or_url: str) -> str:
        u = path_or_url if path_or_url.startswith("http") else SITE + path_or_url
        return u.rstrip("/")

    def add(lst: list[str], path_or_url: str) -> None:
        u = norm(path_or_url)
        if u not in seen:
            seen.add(u)
            lst.append(u)

    for p in HUB_PATHS:
        add(priority, p)
    for name in load_shihai_names():
        add(priority, f"/data/{player_slug(name)}")

    tail: list[str] = []
    if include_all:
        for sm in ("page-sitemap.xml", "page-sitemap2.xml"):
            try:
                xml = urllib.request.urlopen(f"{SITE}/{sm}", timeout=20).read().decode("utf-8", "ignore")
            except Exception as exc:  # noqa: BLE001
                LOG.warning("sitemap fetch fail %s: %r", sm, exc)
                continue
            for m in re.findall(r"<loc>(https://yoshilover\.com/data/[^<]+)</loc>", xml):
                add(tail, m)
    return priority, tail


def _rotate_tail(tail: list[str], slots: int) -> list[str]:
    """day-of-year で tail を rotate し、 毎日違う window を slots 件返す (stateless)。"""
    if slots <= 0 or not tail:
        return []
    if len(tail) <= slots:
        return tail
    yday = _dt.datetime.now(_dt.timezone.utc).timetuple().tm_yday
    start = (yday * slots) % len(tail)
    window = tail[start:start + slots]
    if len(window) < slots:  # wrap around
        window += tail[: slots - len(window)]
    return window


def _publish(token: str, url: str) -> tuple[bool, int, str]:
    body = json.dumps({"url": url, "type": "URL_UPDATED"}).encode()
    req = urllib.request.Request(
        INDEXING_ENDPOINT, data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return True, resp.getcode(), ""
    except urllib.error.HTTPError as e:  # noqa
        return False, e.code, e.read()[:200].decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        return False, 0, repr(exc)


def run(argv: list[str] | None = None) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=180, help="1 回の最大 submit 数 (quota 200/day)")
    ap.add_argument("--all", action="store_true", help="sitemap 全 /data/ URL も対象に追加")
    ap.add_argument("--tail-rotate", action="store_true",
                    help="priority(hub+active) は毎回 + 残り枠を tail から day 単位 rotate")
    ap.add_argument("--dry-run", action="store_true", help="submit せず対象だけ表示")
    ap.add_argument("--sleep", type=float, default=0.3, help="submit 間隔秒")
    args = ap.parse_args(argv)

    priority, tail = _build_target_urls(args.all or args.tail_rotate)
    if args.tail_rotate:
        slots = max(0, args.limit - len(priority))
        targets = (priority + _rotate_tail(tail, slots))[: args.limit]
    else:
        targets = (priority + tail)[: args.limit]
    LOG.info("indexing submit: priority=%d tail=%d targets=%d dry_run=%s all=%s rotate=%s",
             len(priority), len(tail), len(targets), args.dry_run, args.all, args.tail_rotate)
    if args.dry_run:
        for u in targets:
            print(u)
        return {"status": "dry_run", "targets": len(targets)}

    creds = _load_sa_credentials()
    token = _access_token(creds)
    ok = fail = 0
    quota_hit = False
    for i, u in enumerate(targets, 1):
        success, code, msg = _publish(token, u)
        if success:
            ok += 1
        else:
            fail += 1
            LOG.warning("FAIL %s code=%d %s", u, code, msg)
            if code == 429:
                quota_hit = True
                LOG.warning("quota 429 — stop; remaining=%d 翌日へ", len(targets) - i)
                break
            if code == 403:
                LOG.error("403 — SA が GSC Owner 未追加の可能性。中断")
                break
        if i % 25 == 0:
            LOG.info("progress %d/%d ok=%d fail=%d", i, len(targets), ok, fail)
        time.sleep(args.sleep)

    totals = {"status": "ok", "submitted": ok, "failed": fail, "quota_hit": quota_hit,
              "targets": len(targets)}
    LOG.info("indexing submit done %s", json.dumps(totals, ensure_ascii=False))
    return totals


if __name__ == "__main__":
    out = run()
    sys.exit(0 if out.get("status") in {"ok", "dry_run"} else 1)
