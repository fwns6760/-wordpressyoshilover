"""画像 scrape & WP /media upload (Yahoo / Omyutech / Wikimedia 混合 source)。

2026-05-27 user override: 「Yahoo / 一球速報 portrait も使う」。
既存 fetch_player_eyecatch_wikipedia.py の Out of scope (NPB公式 etc) を
データ-insight 若手 quota の visual variety 目的で個別 override。
source URL は WP /media caption / description に必ず記録、後追い差し替え可。

Usage:
    python scripts/scrape_player_eyecatches_yahoo.py --dry-run
    python scripts/scrape_player_eyecatches_yahoo.py --commit
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from src.wp_client import WPClient  # noqa: E402

MAP_PATH = REPO_ROOT / "config" / "player_eyecatch_map.json"

PLAYERS = [
    ("石塚裕惺", "https://sports-baseball.west.edge.storage-yahoo.jp/npb/images/player/portrait/1/2116069.jpg", "Yahoo スポーツナビ"),
    ("田和廉", "https://sports-baseball.west.edge.storage-yahoo.jp/npb/images/player/portrait/1/2118291.jpg", "Yahoo スポーツナビ"),
    ("平山功太", "https://sports-baseball.west.edge.storage-yahoo.jp/npb/images/player/portrait/1/2112330.jpg", "Yahoo スポーツナビ"),
    ("三塚琉生", "https://sports-baseball.west.edge.storage-yahoo.jp/npb/images/player/portrait/1/2104612.jpg", "Yahoo スポーツナビ"),
    ("岡田悠希", "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/Yuki_Okada_20220812_%28cropped%29.jpg/330px-Yuki_Okada_20220812_%28cropped%29.jpg", "Wikimedia Commons (CC-BY-SA)"),
    ("小濱佑斗", "https://baseball.omyutech.com/webdata/team26374/P_1835318_20250731.JPG", "一球速報 (Omyutech)"),
    ("竹丸和幸", "https://sports-baseball.west.edge.storage-yahoo.jp/npb/images/player/portrait/1/2118993.jpg", "Yahoo スポーツナビ"),
]


def _patch_media_metadata(wp: WPClient, media_id: int, *, caption: str, description: str, alt_text: str, title: str) -> bool:
    try:
        resp = requests.post(
            f"{wp.api}/media/{media_id}",
            auth=wp.auth,
            json={"caption": caption, "description": description, "alt_text": alt_text, "title": title},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"  [patch-fail] media_id={media_id} err={exc}")
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    p.add_argument("--player", help="特定選手のみ実行 (name 完全一致)")
    args = p.parse_args(argv)

    targets = PLAYERS if not args.player else [r for r in PLAYERS if r[0] == args.player]
    if not targets:
        print(f"[error] player not found: {args.player}")
        return 1

    existing = json.loads(MAP_PATH.read_text(encoding="utf-8")) if MAP_PATH.exists() else {}

    if args.dry_run:
        print(f"=== dry-run: {len(targets)} targets ===")
        ok = 0
        for name, url, source_label in targets:
            try:
                r = requests.head(url, timeout=10, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
                ct = r.headers.get("Content-Type", "?")
                marker = "OK " if r.status_code == 200 and "image" in ct else "NG "
                ok += 1 if marker == "OK " else 0
                print(f"  {marker} {name} HTTP={r.status_code} CT={ct} source={source_label}")
            except Exception as exc:
                print(f"  NG  {name} err={exc}")
        print(f"=== dry-run summary: {ok}/{len(targets)} OK ===")
        return 0 if ok == len(targets) else 1

    wp = WPClient()
    print(f"=== commit: WP={wp.base_url} targets={len(targets)} ===")

    if MAP_PATH.exists():
        backup = MAP_PATH.with_suffix(".json.bak-2026-05-27")
        backup.write_text(MAP_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[backup] {backup.name}")

    results = []
    for name, url, source_label in targets:
        entry = existing.get(name)
        if isinstance(entry, dict) and entry.get("id"):
            print(f"  [skip-existing] {name} id={entry['id']}")
            results.append((name, entry["id"], "skip-existing"))
            continue

        mid = wp.upload_image_from_url(url, source_url=url)
        if not mid:
            print(f"  [fail] {name}")
            results.append((name, 0, "upload-failed"))
            continue

        caption = f"出典: {source_label} / URL: {url}"
        desc = f"巨人選手 {name} の portrait。 source={source_label}\nURL: {url}\n2026-05-27 scrape (user override OK)"
        _patch_media_metadata(wp, mid, caption=caption, description=desc, alt_text=f"{name} 顔写真", title=f"{name} portrait")

        existing[name] = {"id": mid, "title": f"{name} (scraped {source_label} 2026-05-27)"}
        results.append((name, mid, "uploaded"))
        print(f"  [ok] {name} media_id={mid}")

    MAP_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {MAP_PATH.name}")

    print()
    print("=== summary ===")
    for name, mid, status in results:
        print(f"  {name}: media_id={mid} status={status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
