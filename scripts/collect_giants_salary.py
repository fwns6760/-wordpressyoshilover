"""巨人 現役選手の年俸データ収集 → config/giants_salary.json へ merge。

ソースと突合方針:
- 履歴 (入団年〜2025): nenshuu.net 選手ページ (年度別年俸・契約金・ドラフト・かな読み)
- 当年 (2026): baseball-data.com 巨人一覧の「年俸(推定)」列
- 2026 が両方に存在して食い違う場合は discrepancy として報告し bake しない
- 年俸が 1 年も取れない選手は JSON に入れない (推測で埋めない)
- 既に JSON にいる選手 (手動検証済) は上書きしない

usage:
  python scripts/collect_giants_salary.py            # dry-run (report のみ)
  python scripts/collect_giants_salary.py --write    # JSON へ merge
  python scripts/collect_giants_salary.py --limit 3  # 先頭 N 人だけ (検証用)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_site_slug import _PLAYER_SLUG_MAP  # noqa: E402

SALARY_JSON = ROOT / "config" / "giants_salary.json"
ROSTER_JSON = ROOT / "config" / "giants_roster.json"

NENSHUU_SEED = "https://www.nenshuu.net/shoku/baseball/players.php?name=11215114"
NENSHUU_INDEX = "https://www.nenshuu.net/shoku/baseball/index.php"
BD_GIANTS = "https://baseball-data.com/player/g/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SLEEP_SEC = 1.2

TEAM_SHORT = {
    "読売ジャイアンツ": "巨人", "東京読売巨人軍": "巨人",
    "東北楽天ゴールデンイーグルス": "楽天", "阪神タイガース": "阪神",
    "中日ドラゴンズ": "中日", "広島東洋カープ": "広島", "広島カープ": "広島",
    "横浜DeNAベイスターズ": "DeNA", "横浜ベイスターズ": "横浜",
    "東京ヤクルトスワローズ": "ヤクルト", "ヤクルトスワローズ": "ヤクルト",
    "福岡ソフトバンクホークス": "ソフトバンク", "福岡ダイエーホークス": "ダイエー",
    "北海道日本ハムファイターズ": "日本ハム", "日本ハムファイターズ": "日本ハム",
    "埼玉西武ライオンズ": "西武", "西武ライオンズ": "西武",
    "千葉ロッテマリーンズ": "ロッテ", "オリックス・バファローズ": "オリックス",
    "オリックスブルーウェーブ": "オリックス", "大阪近鉄バファローズ": "近鉄",
}

# ───────────────────── かな → ローマ字 (slug 用) ─────────────────────
_KANA = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo", "しゃ": "sha", "しゅ": "shu",
    "しょ": "sho", "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho", "にゃ": "nya",
    "にゅ": "nyu", "にょ": "nyo", "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo", "りゃ": "rya", "りゅ": "ryu",
    "りょ": "ryo", "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo", "じゃ": "ja",
    "じゅ": "ju", "じょ": "jo", "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo", "ふぁ": "fa", "ふぃ": "fi",
    "ふぇ": "fe", "ふぉ": "fo", "うぃ": "wi", "うぇ": "we", "ヴぁ": "va",
    "てぃ": "ti", "でぃ": "di",
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "o", "ん": "n",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ー": "", "ゔ": "vu",
}


def kana_to_romaji(kana: str) -> str:
    out, i = [], 0
    while i < len(kana):
        if kana[i] == "っ":
            nxt = _KANA.get(kana[i + 1:i + 3]) or _KANA.get(kana[i + 1:i + 2]) or ""
            out.append(nxt[:1])
            i += 1
            continue
        two = kana[i:i + 2]
        if two in _KANA:
            out.append(_KANA[two]); i += 2; continue
        one = kana[i]
        out.append(_KANA.get(one, "")); i += 1
    return "".join(out)


def norm_name(name: str) -> str:
    # 「大勢 （翁田　大勢）」のような括弧付き登録名は括弧前を採用
    name = re.split(r"[（(]", name)[0]
    return name.replace(" ", "").replace("　", "").strip()


def strip_initial(name: str) -> str:
    """「Ｒ．マルティネス」→「マルティネス」(外国人のイニシャル表記ゆれ吸収)。"""
    return re.sub(r"^[A-ZＡ-Ｚ][．.・]?", "", name)


def kata_to_hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def _extra_slug_map() -> dict[str, str]:
    """config/data_site_player_slugs.json (pillar 用) を補助 slug 源として読む。
    key の「2026年成績・防御率」等の suffix と「A.」イニシャルを掃除する。"""
    out = {}
    try:
        raw = json.loads((ROOT / "config" / "data_site_player_slugs.json")
                         .read_text(encoding="utf-8"))
    except Exception:
        return out
    for k, v in raw.items():
        k2 = re.sub(r"\d{4}年.*$", "", k)
        for key in (norm_name(k2), norm_name(strip_initial(k2))):
            if key and key not in out:
                out[key] = v
    return out


_EXTRA_SLUGS = _extra_slug_map()


def slug_for(name: str, kana: str) -> str:
    key = norm_name(name)
    for k in (key, norm_name(strip_initial(key))):
        if k in _PLAYER_SLUG_MAP:
            return _PLAYER_SLUG_MAP[k]
        if k in _EXTRA_SLUGS:
            return _EXTRA_SLUGS[k]
    parts = [p for p in re.split(r"[ 　]+", kana.strip()) if p]
    romaji = [kana_to_romaji(kata_to_hira(p)) for p in parts]
    if len(romaji) >= 2 and all(romaji):
        return f"{romaji[0]}-{romaji[1]}"
    if romaji and romaji[0]:
        return romaji[0]
    # カタカナ登録名 (外国人) は名前自体から
    r = kana_to_romaji(kata_to_hira(strip_initial(key)))
    return r


# ───────────────────── 金額・HTML パース ─────────────────────

def parse_money_man(text: str) -> int | None:
    """「1億6000万円」「9500万円」「1億円」→ 万円 int。読めなければ None。"""
    t = text.replace(",", "").replace("，", "").strip()
    m = re.search(r"(?:(\d+)億)?(?:(\d+)万)?円", t)
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    oku = int(m.group(1) or 0)
    man = int(m.group(2) or 0)
    return oku * 10000 + man


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, timeout=30).read()
    for enc in ("utf-8", "euc-jp", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def table_rows(html: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html):
        cells = [strip_tags(c)
                 for c in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr)]
        if cells:
            rows.append(cells)
    return rows


# ───────────────────── ソース別 取得 ─────────────────────

def nenshuu_giants_ids() -> dict[str, str]:
    """{normalized name: nenshuu id}。巨人 seed ページ (現役巨人) +
    NPB 全体 index (約1000人、新加入の旧球団分・外国人を含む) を統合。
    巨人 seed を優先し、イニシャル除去 key も変種として登録する。"""
    out: dict[str, str] = {}
    for url in (NENSHUU_INDEX, NENSHUU_SEED):
        html = fetch(url)
        for m in re.finditer(
                r'href="(?:[^"]*?)players\.php\?name=(\d+)"[^>]*>([^<]+)<', html):
            raw = m.group(2)
            for key in (norm_name(raw), norm_name(strip_initial(raw))):
                if key and not key.isdigit():
                    out[key] = m.group(1)
        time.sleep(SLEEP_SEC)
    return out


def bd_2026_salaries() -> dict[str, int]:
    """baseball-data.com 巨人一覧 → {normalized name: 2026 推定年俸 (万円)}。"""
    html = fetch(BD_GIANTS)
    out = {}
    for row in table_rows(html):
        if len(row) < 3:
            continue
        # bd の年俸列は「16,000万円」表記。名前 cell の誤検出を避けるため
        # 「万円/億円」を含む cell のみ採用
        sal = None
        for c in row:
            if "万円" in c or "億円" in c:
                sal = parse_money_man(c)
                break
        name = norm_name(row[1]) if len(row) > 1 else ""
        if sal and name and not name.isdigit():
            out[name] = sal
    return out


def parse_player_page(html: str) -> dict:
    """nenshuu 選手ページ → kana / draft / keiyakukin / years。"""
    out: dict = {"years": []}
    m = re.search(r"選手名[\s\S]{0,200}?([ぁ-ゖァ-ヶー]+[ 　]+[ぁ-ゖァ-ヶー]+)",
                  strip_tags(html))
    if not m:
        m = re.search(r"\(([ぁ-ゖァ-ヶー 　]+)\)", strip_tags(html))
    out["kana"] = (m.group(1).strip() if m else "")
    flat = strip_tags(html)
    dm = re.search(r"ドラフト\s*(\d{4}年[^ ]*?(?:ドラフト|巡目|位)[^ ]*)", flat)
    if dm:
        out["draft_desc"] = dm.group(1).strip()
    km = re.search(r"契約金\s*([0-9億万,，]+円)", flat)
    if km:
        out["keiyakukin_man"] = parse_money_man(km.group(1))
    for row in table_rows(html):
        # 年度別年俸 row: [2025年, 36歳, 読売ジャイアンツ, 1億6000万円, 11]
        if len(row) >= 4 and re.fullmatch(r"(19|20)\d{2}\s*年", row[0] or ""):
            year = int(row[0][:4])
            team_raw = row[2]
            sal = parse_money_man(row[3])
            if sal is None or not team_raw:
                continue
            out["years"].append({
                "year": year,
                "team": TEAM_SHORT.get(team_raw, team_raw),
                "league": "NPB",
                "salary_man": sal,
            })
    out["years"].sort(key=lambda y: y["year"])
    return out


# ───────────────────── main ─────────────────────

def main() -> int:
    write = "--write" in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    roster = json.loads(ROSTER_JSON.read_text(encoding="utf-8"))
    targets = [p for p in roster if p.get("role") in ("player", "ikusei")]
    data = json.loads(SALARY_JSON.read_text(encoding="utf-8"))
    existing = {norm_name(p["name"]) for p in data.get("players", [])}

    print("fetch nenshuu id map / baseball-data 2026 list ...")
    id_map = nenshuu_giants_ids()
    bd_map = bd_2026_salaries()
    print(f"nenshuu ids: {len(id_map)} / bd 2026 salaries: {len(bd_map)}")

    report = {"added": [], "no_id": [], "no_years": [], "no_2026": [],
              "discrepancy_2026": [], "slug_fallback": [], "not_giants_skip": []}
    used_slugs = {p["slug"] for p in data.get("players", [])}
    seen_keys = set()
    added = []

    for p in targets:
        key = norm_name(p["name"])
        key2 = norm_name(strip_initial(p["name"]))
        if key in existing or key2 in existing or key2 in seen_keys:
            continue
        seen_keys.add(key2)
        if limit and len(added) >= limit:
            break
        pid = id_map.get(key) or id_map.get(key2)
        bd_2026 = bd_map.get(key) or bd_map.get(key2)
        page = {"years": [], "kana": ""}
        if pid:
            time.sleep(SLEEP_SEC)
            try:
                page = parse_player_page(fetch(
                    f"https://www.nenshuu.net/shoku/baseball/players.php?name={pid}"))
            except Exception as exc:  # noqa: BLE001
                print(f"WARN fetch fail {p['name']}: {exc!r}", file=sys.stderr)
        if not pid and not bd_2026:
            report["no_id"].append(p["name"])
            continue
        years = page["years"]
        # 巨人実在 gate: 2026 推定年俸 (bd=現巨人一覧) が無く、nenshuu 履歴の
        # 最終年も巨人でない選手は、roster 鮮度ズレの可能性があるため bake しない
        if not bd_2026 and years and years[-1]["team"] != "巨人":
            report["not_giants_skip"].append(
                f"{p['name']} (last={years[-1]['year']} {years[-1]['team']})")
            continue
        n_2026 = next((y for y in years if y["year"] == 2026), None)
        if n_2026 and bd_2026 and n_2026["salary_man"] != bd_2026:
            report["discrepancy_2026"].append(
                f"{p['name']}: nenshuu={n_2026['salary_man']} bd={bd_2026}")
            years = [y for y in years if y["year"] != 2026]
            n_2026 = None
        if not n_2026 and bd_2026:
            years.append({"year": 2026, "team": "巨人", "league": "NPB",
                          "salary_man": bd_2026})
        elif not n_2026:
            report["no_2026"].append(p["name"])
        if not years:
            report["no_years"].append(p["name"])
            continue
        slug = slug_for(p["name"], page.get("kana") or "")
        if not slug or not re.fullmatch(r"[a-z0-9-]+", slug):
            report["slug_fallback"].append(f"{p['name']} (kana={page.get('kana')!r})")
            continue
        if slug in used_slugs:
            slug = f"{slug}-{(p.get('jersey_number') or '').lstrip('0') or 'x'}"
        used_slugs.add(slug)
        entry = {
            "name": norm_name(p["name"]),
            "slug": slug,
            "kana": page.get("kana") or "",
            "position": p.get("position") or "",
            "jersey": p.get("jersey_number") or "",
            "active": True,
            "nenshuu_id": pid,
            "years": sorted(years, key=lambda y: y["year"]),
        }
        if page.get("draft_desc") or page.get("keiyakukin_man"):
            entry["draft"] = {}
            if page.get("draft_desc"):
                entry["draft"]["desc"] = page["draft_desc"]
            if page.get("keiyakukin_man"):
                entry["draft"]["keiyakukin_man"] = page["keiyakukin_man"]
        added.append(entry)
        report["added"].append(
            f"{p['name']} slug={slug} years={entry['years'][0]['year']}-"
            f"{entry['years'][-1]['year']} ({len(entry['years'])})")
        print(f"OK {p['name']} ({len(entry['years'])} years)")

    print("\n===== report =====")
    for k, v in report.items():
        print(f"{k}: {len(v)}")
        for line in v:
            print("  -", line)

    if write and added:
        data["players"].extend(added)
        data["_meta"]["updated"] = "2026-06-12"
        SALARY_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {len(added)} players -> {SALARY_JSON}")
    elif added:
        print("\n(dry-run: --write で JSON へ反映)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
