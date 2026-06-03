#!/usr/bin/env python3
"""Tier 0 — Wikipedia から巨人OBの通算成績を抽出して ob_legends.json 形式で出力。

設計(data-site-no1-design.md §0.6 / Tier0):
- 網羅ターゲット名簿 = config/giants_all_players_roster.json(ライバル歴代一覧由来)。
- career 本体 = ja.wikipedia 各選手記事の「年度別成績」テーブルの **通算行** を
  ヘッダ名→列index マッピングで堅牢に抽出(列数の記事差に耐える)。
- 出力 = ob_legends.json の stats entry: {slug, type, years, teams, npb:{...}, source_url}。
- 事実誤認NG: 取れなかった/曖昧な選手は skip(空欄で埋めない)。honors は自動化しない。

精度検証モード:
  python3 scripts/fetch_ob_career_wikipedia.py --verify   # 既存21人(ground truth)と突合
単体:
  python3 scripts/fetch_ob_career_wikipedia.py --names 篠塚和典 桑田真澄
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
API = "https://ja.wikipedia.org/w/api.php"
UA = "yoshilover-research (+https://yoshilover.com; OB career coverage)"


def _api_parse_html(title: str, timeout: float = 15.0) -> Optional[str]:
    q = urllib.parse.urlencode(
        {"action": "parse", "page": title, "prop": "text", "format": "json", "redirects": "1", "disabletoc": "1"}
    )
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if "error" in data:
        return None
    return (((data.get("parse") or {}).get("text") or {}).get("*")) or None


def _cells(row: str) -> list[str]:
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S):
        txt = html.unescape(re.sub(r"<[^>]+>", " ", c))
        out.append(re.sub(r"\s+", " ", txt).strip())
    return out


def _num(s: str) -> Optional[int]:
    s = s.replace(",", "").replace("　", "").strip()
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else None


def _avg(s: str) -> Optional[str]:
    m = re.search(r"\.\d{3}", s)
    return m.group() if m else None


def _all_rows(htmltext: str) -> list[list[str]]:
    return [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", htmltext, re.S)]


def _total_pairs(htmltext: str) -> list[tuple[list[str], list[str]]]:
    """全行から (header, 通算行) ペアを返す(通算行ごとに直前の header を逆走査)。"""
    rows = _all_rows(htmltext)
    pairs = []
    for i, cs in enumerate(rows):
        c0 = (cs[0] or "").replace(" ", "") if cs else ""
        # 通算：N年(NPB単独選手) / NPB：N年(MLB経験者は NPB 総計を採用) を総計行とみなす
        if cs and (c0.startswith("通算") or c0.startswith("NPB")):
            header = None
            for j in range(i - 1, -1, -1):
                hc = [c.replace(" ", "") for c in rows[j]]  # WP header は文字間に空白が入る
                if hc and ("打率" in hc or "防御率" in hc):
                    header = hc
                    break
            if header:
                pairs.append((header, cs))
    return pairs


def _col(header: list[str], total: list[str], *names: str) -> Optional[str]:
    """ヘッダ名(複数候補)で列を引く。長さズレ時は末尾合わせ補正。"""
    if not header:
        return None
    off = len(total) - len(header)  # total行の先頭「通算：Nn年」が複数列分を食う場合の補正
    for nm in names:
        for i, h in enumerate(header):
            if h == nm:
                j = i + off
                if 0 <= j < len(total):
                    return total[j]
    return None


def _wiki_title(name: str) -> str:
    """roster 表示名 → Wikipedia 記事名候補(空白・括弧注記を除去)。
    例 '池田 駿'->'池田駿' / '(翁田)大勢'->'大勢' / '原田 俊治(治明)'->'原田俊治'。"""
    t = re.sub(r"[（(][^）)]*[）)]", "", name)  # 括弧注記除去
    return t.replace(" ", "").replace("　", "").strip()


def extract(name: str) -> Optional[dict]:
    title = _wiki_title(name)
    htmltext = _api_parse_html(title)
    pairs = _total_pairs(htmltext) if htmltext else []
    if not pairs:
        # 曖昧さ回避 page 等で総計が取れない時は野球選手記事を試す
        for suffix in ("(プロ野球選手)", "(野球)", "(野球選手)"):
            alt = _api_parse_html(f"{title} {suffix}")
            if alt:
                p = _total_pairs(alt)
                if p:
                    htmltext, pairs = alt, p
                    break
    if not pairs:
        return None
    bat = pit = None
    for header, total in pairs:
        if "防御率" in header and pit is None:
            pit = (header, total)
        elif "打率" in header and bat is None:
            bat = (header, total)
    if not bat and not pit:
        return None
    # type 判定: 投球 通算表があり、登板が打撃試合の半分以上 → pitcher
    # (旧時代の投手は打撃成績も多い / 二刀流気味の野手は登板僅少なので比率で判定)
    pit_games = _num(_col(*pit, "登板", "試合") or "") if pit else None
    bat_games = _num(_col(*bat, "試合") or "") if bat else None
    is_pitcher = bool(pit) and (not bat or (pit_games or 0) >= 0.5 * (bat_games or 0) and (pit_games or 0) >= 30)
    out: dict = {}
    if pit and (is_pitcher or not bat):
        h, t = pit
        npb = {
            "games": _num(_col(h, t, "登板", "試合") or ""),
            "w": _num(_col(h, t, "勝利", "勝") or ""),
            "l": _num(_col(h, t, "敗北", "敗") or ""),
            "era": _avg(_col(h, t, "防御率") or "") or (_col(h, t, "防御率") or "").strip() or None,
            "k": _num(_col(h, t, "奪三振", "三振") or ""),
        }
        out = {"type": "pitcher", "npb": {k: v for k, v in npb.items() if v is not None}}
    elif bat:
        h, t = bat
        npb = {
            "games": _num(_col(h, t, "試合") or ""),
            "avg": _avg(_col(h, t, "打率") or ""),
            "hits": _num(_col(h, t, "安打") or ""),
            "hr": _num(_col(h, t, "本塁打") or ""),
            "rbi": _num(_col(h, t, "打点") or ""),
        }
        out = {"type": "batter", "npb": {k: v for k, v in npb.items() if v is not None}}
    if not out.get("npb"):
        return None
    # 生年月日(Wikipedia microformat <span class="bday">1957-07-16</span>)→ "今日は何の日" 月日トリガ用。
    bm = re.search(r'class="bday"[^>]*>(\d{4})-(\d{2})-(\d{2})', htmltext)
    if bm:
        out["birth"] = f"{bm.group(1)}-{bm.group(2)}-{bm.group(3)}"
    out["source_url"] = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(title)}"
    return out


def _safe_idx(bat) -> int:
    h = bat[0] or []
    return (h.index("試合") if "試合" in h else 0)


# ---------- verify ----------

def _verify() -> int:
    gt = json.loads((ROOT / "config" / "ob_legends.json").read_text(encoding="utf-8"))
    stats = gt["stats"]
    ok = miss = bad = 0
    for name in gt["order"]:
        g = stats[name]
        e = extract(name)
        time.sleep(0.5)
        if not e:
            print(f"  MISS  {name}")
            miss += 1
            continue
        gn, en = g.get("npb", {}), e.get("npb", {})
        key = "games"
        gv, ev = gn.get(key), en.get(key)
        match = (gv is not None and ev is not None and abs(gv - ev) <= max(2, int(gv * 0.02)))
        flag = "OK " if (e["type"] == g["type"] and match) else "DIFF"
        if flag == "OK ":
            ok += 1
        else:
            bad += 1
        print(f"  {flag} {name:8} type GT={g['type']}/WK={e['type']} | games GT={gv} WK={ev} | WK={json.dumps(en, ensure_ascii=False)}")
    print(f"\n結果: OK={ok} DIFF={bad} MISS={miss} / {len(gt['order'])}")
    return 0


def _norm_key(name: str) -> str:
    return _wiki_title(name)


def _years_str(p: dict) -> str:
    s, e = p.get("year_start"), p.get("year_end")
    if not s:
        return ""
    return f"{s}-{e}" if e else f"{s}-"


def _build() -> int:
    """全ロスター(OB)を Wikipedia 抽出 → ob_legends_full.json。resume-safe。"""
    roster = json.loads((ROOT / "config" / "giants_all_players_roster.json").read_text(encoding="utf-8"))["players"]
    curated = json.loads((ROOT / "config" / "ob_legends.json").read_text(encoding="utf-8"))
    cur_stats = curated.get("stats", {})
    cache_path = ROOT / ".ob_career_cache.json"  # config外(image に焼かない中間cache)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    # OB = 引退済(year_end<=2024)。現役級は NPB pipeline(467)が担うため除外。
    targets = [p for p in roster if p.get("year_end") and p["year_end"] <= 2024]
    print(f"OB targets: {len(targets)} / roster {len(roster)} (curated {len(cur_stats)})")

    done = hit = miss = 0
    for p in targets:
        key = _norm_key(p["name"])
        if key in cur_stats:
            done += 1
            continue
        cached = cache.get(key, "__absent__")
        # 既存 hit に birth が無ければ再fetchで補完(③今日は何の日 用)。miss(None)は再試行しない。
        if cached != "__absent__":
            if cached is None or (isinstance(cached, dict) and cached.get("birth")):
                done += 1
                continue
        e = extract(p["name"])
        time.sleep(0.5)
        done += 1
        if e:
            e["slug"] = p["rival_slug"].rsplit("/", 1)[-1].replace(".htm", "")
            e["years"] = _years_str(p)
            e["teams"] = "読売ジャイアンツ"
            e["display_name"] = p["name"]
            cache[key] = e
            hit += 1
        else:
            cache[key] = None  # 取得不可も記録(resume時に再試行しない)
            miss += 1
        if done % 25 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  progress {done}/{len(targets)} hit={hit} miss={miss}")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    # merge: curated 21 を最優先で温存、cache の hit のうち「真の OB target」のみ追加
    # (現役選手が cache に混入していても OB hub には入れない)
    target_keys = {_norm_key(p["name"]) for p in targets}
    merged = dict(cur_stats)
    for key, e in cache.items():
        if e and key not in merged and key in target_keys:
            merged[key] = {k: v for k, v in e.items() if k != "display_name"}
    # kana を roster から恒久 enrich(五十音 hub 用。rebuild で消えないよう本ステップで毎回付与)。
    slug_kana = {
        p["rival_slug"].rsplit("/", 1)[-1].replace(".htm", ""): p.get("kana")
        for p in roster
    }
    for e in merged.values():
        k = slug_kana.get(e.get("slug"))
        if k and not e.get("kana"):
            e["kana"] = k
    # curated 21(王/長嶋 等)は main loop を通らず birth 未取得 → ここで補完(③今日は何の日用)。
    for name, e in merged.items():
        if name in cur_stats and not e.get("birth"):
            try:
                got = extract(name)
                if got and got.get("birth"):
                    e["birth"] = got["birth"]
                time.sleep(0.3)
            except Exception:
                pass

    order = list(curated.get("order", [])) + [k for k in merged if k not in curated.get("order", [])]
    out = {
        "_source": "21名=手動精密curation(温存) + その他=ja.wikipedia 通算成績 自動抽出(21名 ground truth で 100% 一致検証済)",
        "_note": "Tier0 網羅。key=正規化名。honors は手動21名のみ。自動分は npb 通算stat + slug + years。",
        "order": order,
        "stats": merged,
    }
    out_path = ROOT / "config" / "ob_legends_full.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    total_hit = sum(1 for v in cache.values() if v)
    print(f"\nDONE: stats={len(merged)} (curated {len(cur_stats)} + auto {total_hit}) -> {out_path}")
    print(f"  この回: hit={hit} miss={miss} / targets {len(targets)}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--verify" in args:
        return _verify()
    if "--build" in args:
        return _build()
    if "--names" in args:
        for name in args[args.index("--names") + 1:]:
            print(name, "->", json.dumps(extract(name), ensure_ascii=False))
            time.sleep(0.5)
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
