#!/usr/bin/env python3
"""config/giants_foreign_players.json (歴代外国人選手 hub /data/foreign-players/ の正本) を生成する。

ソース (全て repo 内の検証済み正本 + 個別 verify、推測で埋めない):
  1. config/ob_legends_full.json
     - kana に欧文 3 連続字を含む entry = 外国人 OB (V.スタルヒン含む)
     - 韓国/台湾出身 (趙成珉/鄭珉哲/鄭珉台/林羿豪) も kana に欧文表記があり自動収録
  2. ハワイ出身の日系米国人 (NPB 外国籍選手) の手動 extras
     - 堀尾文人 (マウイ島出身・日本プロ野球 外国人選手第1号 1934)
     - 与那嶺要 (ホノルル出身 1951-1960)
     - 柏枝文治 (ハワイ出身 1953-1956)
     - 宮本敏雄 (ハワイ出身 1955-1962)
     出典: ja.wikipedia 各選手記事 (2026-06-10 verify 済)
  3. config/data_site_player_class.json (NPB 公式由来) の現役カタカナ名
     - リチャード (砂川リチャード) は沖縄出身の日本人のため対象外
     - 現役の slug は config/data_site_player_slugs.json から prefix match で解決

保留 (pending): 金伏ウーゴ (2016、日系ブラジル人、一軍登板なし) — 外国人選手としての
扱い整備中のため v1 非収録。

実行: python3 scripts/build_foreign_players_config.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGENDS = ROOT / "config" / "ob_legends_full.json"
PLAYER_CLASS = ROOT / "config" / "data_site_player_class.json"
SLUGS = ROOT / "config" / "data_site_player_slugs.json"
OUT = ROOT / "config" / "giants_foreign_players.json"

SEASON = 2026

# ハワイ出身の日系米国人 (外国籍選手)。 name → 注記 (出典 verify 済の事実のみ)
HAWAII_NISEI_EXTRAS = {
    "堀尾文人": "ハワイ・マウイ島出身の日系二世 (米国籍)。日本プロ野球の外国人選手第1号、1934年大日本東京野球倶楽部創立メンバー",
    "与那嶺要": "ハワイ・ホノルル出身の日系二世 (米国籍)。首位打者3回、1994年野球殿堂入り",
    "柏枝文治": "ハワイ出身の日系二世 (米国籍)。1953年入団、同年打率.341",
    "宮本敏雄": "ハワイ出身の日系二世 (米国籍)。「エンディ宮本」",
}

# 現役カタカナ名のうち日本人 (外国人選手ではない) ため除外
ACTIVE_EXCLUDE = {"リチャード"}  # 砂川リチャード = 沖縄出身の日本人


def _clean_display(name: str) -> str:
    """display 名の HTML entity (&thinsp;) を space に正規化。"""
    return name.replace("&thinsp;", " ").strip()


def _roman_of(kana: str) -> str:
    """kana field から現地名 (欧文) 部分を取り出す。「VICTOR STARFFIN／すた ひろし」→ 前半。"""
    part = str(kana or "").split("／")[0].strip()
    return part if re.search(r"[A-Za-z]{3,}", part) else ""


def main() -> None:
    legends = json.loads(LEGENDS.read_text(encoding="utf-8"))
    stats: dict = legends["stats"]

    ob: list[dict] = []
    seen: set[str] = set()

    def add_ob(name: str, v: dict, note: str = "") -> None:
        if name in seen:
            return
        seen.add(name)
        entry = {
            "name": name,
            "display_name": _clean_display(str(v.get("display_name") or name)),
            "slug": v.get("slug") or "",
            "type": v.get("type") or "",
            "years": v.get("years") or "",
            "roman": _roman_of(v.get("kana")),
            "npb": v.get("npb") or {},
        }
        if note:
            entry["note"] = note
        ob.append(entry)

    # 1. kana 欧文 3 連続字 = 外国人 OB
    for name, v in stats.items():
        if re.search(r"[A-Za-z]{3,}", str(v.get("kana", ""))):
            add_ob(name, v)

    # 2. ハワイ出身日系 extras (台帳 entry 必須 — 無ければ収録しない)
    for name, note in HAWAII_NISEI_EXTRAS.items():
        v = stats.get(name)
        if v:
            add_ob(name, v, note=note)
        else:
            print(f"WARN: extras {name} not in ledger — skipped")

    def start_year(e: dict) -> int:
        m = re.match(r"(\d{4})", e.get("years") or "")
        return int(m.group(1)) if m else 9999

    ob.sort(key=lambda e: (start_year(e), e["display_name"]))

    # 3. 現役 (NPB 公式由来 player class)。 slug は prefix match。
    pclass = json.loads(PLAYER_CLASS.read_text(encoding="utf-8"))
    slugs = json.loads(SLUGS.read_text(encoding="utf-8"))

    def slug_for(name: str) -> str:
        for k, v in slugs.items():
            if k.startswith(name):
                return v
        return ""

    kat = re.compile(r"[ァ-ヶー・]+")
    active: list[dict] = []
    for status_key, status_label in (("shihai", "支配下"), ("ikusei", "育成")):
        for group, names in (pclass.get(status_key) or {}).items():
            for name in names:
                if kat.fullmatch(name.replace(" ", "")) and name not in ACTIVE_EXCLUDE:
                    active.append({
                        "name": name,
                        "group": group,
                        "status": status_label,
                        "slug": slug_for(name),
                    })

    out = {
        "_source": ("ob_legends_full.json (kana 欧文判定) + ハワイ日系 extras (ja.wikipedia verify) "
                    "+ data_site_player_class.json (NPB 公式) 由来。generator: scripts/build_foreign_players_config.py"),
        "_updated": "2026-06-10",
        "_policy": ("事実のみ・推測で埋めない。日系選手は出典 verify 済のみ収録。"
                    "リチャード (砂川リチャード) は沖縄出身の日本人のため対象外。"),
        "season": SEASON,
        "pending": [
            "金伏ウーゴ (2016、日系ブラジル人、一軍登板なし) — 外国人選手としての扱い整備中",
            "現役選手の巨人加入年 — 整備後に年度別早見表へ反映",
        ],
        "ob": ob,
        "active": active,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: ob={len(ob)} active={len(active)}")


if __name__ == "__main__":
    main()
