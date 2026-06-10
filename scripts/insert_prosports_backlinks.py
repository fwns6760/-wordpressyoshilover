#!/usr/bin/env python3
"""prosports.yoshilover.com の巨人選手 人物記事 93 件に、本体データページへの
逆方向リンク (評価還流) を冪等挿入する。

対象と宛先は config/prosports_link_map.json (正本) の by_slug を反転して使う。
挿入物: 記事本文末尾に marker class `ys-yoshilover-crosslink` 付きボックス 1 個。
再実行時は marker 検出で skip (重複しない)。

使い方:
  python3 scripts/insert_prosports_backlinks.py --dry-run
  python3 scripts/insert_prosports_backlinks.py --limit 3      # canary
  python3 scripts/insert_prosports_backlinks.py                # 全件

認証: ~/.prosports_wp_cred (`user:application-password` 1 行、 chmod 600)。
鍵は log にも stdout にも出さない。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
MAP_PATH = os.path.join(ROOT, "config", "prosports_link_map.json")
CRED_PATH = os.path.expanduser("~/.prosports_wp_cred")
API = "https://prosports.yoshilover.com/wp-json/wp/v2/posts"
MARKER = "ys-yoshilover-crosslink"


def _auth_header() -> str:
    user_pass = open(CRED_PATH, encoding="utf-8").read().strip()
    return "Basic " + base64.b64encode(user_pass.encode()).decode()


def _req(url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
        },
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _box_html(player: str, data_slug: str) -> str:
    url = f"https://yoshilover.com/data/{data_slug}/"
    return (
        f'\n<div class="{MARKER}" style="margin:24px 0;padding:14px 16px;'
        'background:#fff8f3;border:2px solid #ffd9bf;border-radius:10px;">'
        '<p style="margin:0;font-size:14px;font-weight:700;">'
        f'▶ <a href="{url}">{player}の最新成績・年度別データはこちら（ヨシラバー）</a></p>'
        '<p style="margin:4px 0 0;font-size:12px;color:#777;">'
        '打率・本塁打・直近試合・年度別成績を毎日更新中</p></div>'
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="先頭 N 記事のみ (canary)")
    args = ap.parse_args()

    by_slug = json.load(open(MAP_PATH, encoding="utf-8"))["by_slug"]
    # 記事単位に反転 (1 記事 = 1 選手 1 box)
    jobs = []
    for data_slug, entries in by_slug.items():
        for e in entries:
            jobs.append({"post_id": e["post_id"], "player": e["player"],
                         "data_slug": data_slug, "title": e["title"]})
    jobs.sort(key=lambda j: j["post_id"])
    if args.limit:
        jobs = jobs[: args.limit]

    done = skipped = failed = 0
    for j in jobs:
        try:
            post = _req(f'{API}/{j["post_id"]}?context=edit&_fields=id,content,status')
            raw = (post.get("content") or {}).get("raw") or ""
            if MARKER in raw:
                skipped += 1
                print(f'SKIP (既挿入) {j["post_id"]} {j["player"]}')
                continue
            new_content = raw.rstrip() + _box_html(j["player"], j["data_slug"])
            if args.dry_run:
                print(f'DRY {j["post_id"]} {j["player"]} -> /data/{j["data_slug"]}/ (status={post.get("status")})')
                done += 1
                continue
            _req(f'{API}/{j["post_id"]}', {"content": new_content})
            done += 1
            print(f'OK {j["post_id"]} {j["player"]} -> /data/{j["data_slug"]}/')
            time.sleep(0.5)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f'FAIL {j["post_id"]} {j["player"]}: {exc!r}', file=sys.stderr)
    print(f"done={done} skipped={skipped} failed={failed} total={len(jobs)}")


if __name__ == "__main__":
    main()
