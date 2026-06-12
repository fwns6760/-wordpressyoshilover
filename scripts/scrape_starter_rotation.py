#!/usr/bin/env python3
"""巨人 先発ローテ一覧 (全年バッチ) を取得し静的 JSON に固定化する scraper CLI。

実ロジックは src/starter_rotation_scraper.py に集約 (auto-update job と共用)。
- config/starter_rotation_2007_2026.json : フル game log (publisher / 深いページ用)
- config/starter_rotation_summary.json   : 軽量サマリー (063 プラグイン同梱用)

出典 (取得元) は JSON / 表示には載せない (user 方針)。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.starter_rotation_scraper import scrape_year  # noqa: E402

FROM_YEAR = 2007
TO_YEAR = 2026


def main() -> int:
    out_path = ROOT / "config" / "starter_rotation_2007_2026.json"
    years_out: list[dict] = []
    failed: list[int] = []
    for year in range(TO_YEAR, FROM_YEAR - 1, -1):
        entry = scrape_year(year)
        if not entry:
            failed.append(year)
            print(f"  {year}: no data", file=sys.stderr)
            continue
        years_out.append(entry)
        top = entry["pitchers"][0]
        print(f"  {year}: {len(entry['games'])} games, "
              f"{len(entry['pitchers'])} pitchers, top={top['name']}({top['starts']})")
        time.sleep(0.7)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"generated_at": None, "years": years_out}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\nwrote {out_path} ({len(years_out)} years, failed={failed})")

    summary = {"generated_at": None,
               "years": [{"year": y["year"], "pitchers": y["pitchers"]} for y in years_out]}
    summary_path = out_path.parent / "starter_rotation_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"wrote {summary_path} ({summary_path.stat().st_size} bytes)")
    return 0 if years_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
