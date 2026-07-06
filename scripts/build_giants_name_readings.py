#!/usr/bin/env python3
"""巨人 全選手の読み辞書 generator (2026-07-06 Shorts品質改善①)。

NPB 公式 rst_g.html から選手個別ページ URL を拾い、各ページの
``<li id="pc_v_kana">とごう・しょうせい</li>`` を取得して
``config/giants_name_readings.json`` に bake する。

- key = 漢字フル名 (全角スペース除去、例「戸郷翔征」)
- value = かな読み (「・」除去、例「とごうしょうせい」)
- 監督・コーチ (個別ページリンク無し) と有名OBは対象外
  → ``yt_shorts_script.NAME_READING_OVERRIDES`` に手動登録する
- 外国人登録名 (カタカナのみ) は TTS 誤読リスクが無いので skip

実行: PYTHONPATH=. python3 scripts/build_giants_name_readings.py
支配下/育成の入れ替え時に再実行して commit する (runtime fetch はしない =
Shorts job はネットワーク断でも動く)。
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER_URL = "https://npb.jp/bis/teams/rst_g.html"
OUT_PATH = ROOT / "config" / "giants_name_readings.json"
UA = "Mozilla/5.0 (yoshilover shorts reading dict builder)"

PLAYER_LINK_RE = re.compile(
    r'<a href="(/bis/players/\d+\.html)">([^<]+)</a>'
)
KANA_RE = re.compile(r'<li id="pc_v_kana">([^<]+)</li>')
KATAKANA_ONLY_RE = re.compile(r"^[゠-ヿー・\s　]+$")


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    html = _get(ROSTER_URL)
    pairs = []
    seen = set()
    for path, raw_name in PLAYER_LINK_RE.findall(html):
        name = raw_name.replace("　", "").replace(" ", "").strip()
        if not name or path in seen:
            continue
        seen.add(path)
        if KATAKANA_ONLY_RE.match(raw_name):
            continue  # 外国人登録名は誤読リスクなし
        pairs.append((name, f"https://npb.jp{path}"))
    print(f"roster links: {len(pairs)}")
    readings: dict[str, str] = {}
    failures: list[str] = []
    for i, (name, url) in enumerate(pairs, 1):
        try:
            page = _get(url)
            m = KANA_RE.search(page)
            kana = (m.group(1) if m else "").replace("・", "").replace("　", "").strip()
            # 登録名ページの「たいせい（おうたたいせい）」形式は本名括弧を落とす
            kana = kana.split("（")[0].split("(")[0].strip()
            if kana:
                readings[name] = kana
            else:
                failures.append(name)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} ({exc})")
        if i % 20 == 0:
            print(f"  {i}/{len(pairs)} fetched")
        time.sleep(0.3)  # NPB への礼儀
    OUT_PATH.write_text(
        json.dumps(readings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(readings)} readings -> {OUT_PATH}")
    if failures:
        print(f"NO KANA ({len(failures)}): {', '.join(failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
