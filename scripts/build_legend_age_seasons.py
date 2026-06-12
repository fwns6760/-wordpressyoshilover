"""巨人レジェンドの年度別打撃成績を NPB 公式から取得して bake-in JSON を作る。

角度① 新旧比較 (同年齢レジェンド対比、 2026-06-12 user 合意) のデータ仕込み。
ob_legends_full.json は通算のみで年度別が無いため、 X 候補の「同年齢時点比較」に
必要な年度別行をこの script で取得し ``config/legend_age_seasons.json`` へ焼く。

- 取得元: NPB 公式 個人年度別成績 page (npb_career_scraper.fetch_player_career)
- npb_id は NPB 公式 検索 (https://npb.jp/bis/players/search/result) で 2026-06-12
  に 1 件ずつ verify した literal (推測で埋めない rule)
- 引退選手の過去成績は不変なので、 取得は一度きりで repo に commit する
  (現役 2 名 = 坂本勇人 / 岡本和真 の行は年 1 回シーズン後に再実行して追記)

実行: python3 scripts/build_legend_age_seasons.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.npb_career_scraper import fetch_player_career  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent.parent / "config" / "legend_age_seasons.json"

# NPB 公式検索で verify 済み (2026-06-12)。 打者レジェンドのみ (投手は次バッチ)。
LEGEND_IDS: dict[str, str] = {
    "王貞治": "81383808",
    "長嶋茂雄": "81983806",
    "松井秀喜": "51253887",
    "原辰徳": "71073863",
    "阿部慎之助": "21125113",
    "高橋由伸": "51953886",
    "坂本勇人": "51955114",
    "岡本和真": "11515130",
}

# 比較に使う打撃列 (BATTING_COLUMNS のうち X 候補で使うもの)
_KEEP_COLS = ("年度", "所属球団", "試合", "打数", "安打", "本塁打", "打点", "盗塁", "打率")


def main() -> int:
    stats: dict[str, dict] = {}
    for name, npb_id in LEGEND_IDS.items():
        career = fetch_player_career(npb_id)
        if not career:
            print(f"FETCH FAIL: {name} ({npb_id}) — 除外 (推測で埋めない)")
            continue
        profile = career.get("profile") or {}
        batting = career.get("batting") or {}
        years = batting.get("years") or []
        birthdate = (profile.get("birthdate") or "").strip()
        if not years or not birthdate:
            print(f"DATA MISSING: {name} years={len(years)} birth={birthdate!r} — 除外")
            continue
        rows = [{c: y.get(c, "") for c in _KEEP_COLS} for y in years]
        stats[name] = {"npb_id": npb_id, "birthdate": birthdate, "seasons": rows}
        print(f"OK: {name} seasons={len(rows)} birth={birthdate}")
        time.sleep(1.5)  # NPB 公式への礼儀 (連続 fetch しない)

    out = {
        "_source": "NPB公式 個人年度別成績 (https://npb.jp/bis/players/{id}.html)",
        "_note": (
            "角度① 新旧比較用。 npb_id は NPB 公式検索で verify 済み literal。 "
            "引退選手は不変、 現役 (坂本勇人/岡本和真) はシーズン後に再実行して更新。"
        ),
        "_built_with": "scripts/build_legend_age_seasons.py",
        "stats": stats,
    }
    OUT_PATH.write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"WROTE {OUT_PATH} players={len(stats)}")
    return 0 if len(stats) == len(LEGEND_IDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
