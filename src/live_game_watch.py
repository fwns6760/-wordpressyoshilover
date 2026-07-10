"""巨人戦ライブ観戦 v0 — NPB 公式スコアページからイベントを検出する。

目的 (2026-07-08 user GO「フーガみたいな観戦中のポストが無い」):
  試合帯の x-post-mail 便 (15分毎) のたびに NPB 公式のライブスコアを 1 回見て、
  前回 snapshot からスコアが動いた時だけ「実況候補」の素材 (検証済み事実行) を返す。
  文章生成・Candidate 化は x_post_mail_lane 側 (既存の voice / 捏造ガードを通す)。

事実性:
  イベントの数字 (スコア・回・本塁打の号数) はすべて NPB 公式ページの表記だけを使う。
  取れなかった項目は書かない。推測で埋めない。

state:
  GCS `baseballsite-yoshilover-state/live_game_watch/{YYYYMMDD}.json` に前回 snapshot。
  同日内の便同士の差分だけを見る (日付が変われば新規)。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import requests

LOG = logging.getLogger("live_game_watch")

JST = timezone(timedelta(hours=9))
_SCORES_INDEX = "https://npb.jp/scores/{year}/{md}/"
_STATE_BUCKET_ENV = "X_POST_STATE_BUCKET"
_DEFAULT_STATE_BUCKET = "baseballsite-yoshilover-state"
_STATE_PREFIX = "live_game_watch"

# 巨人のチームコード (npb.jp の game path は "<away>-<home>-<n>")
_GIANTS_CODE = "g"
_TEAM_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_STATUS_RE = re.compile(r"(試合終了|試合中\s*(\d+)回(表|裏)|試合前)")
_HOMER_RE = re.compile(r"([\w぀-ヿ一-鿿・]+)\s*(\d+号（[^）]*）)")


@dataclass
class LiveGameState:
    date_key: str
    game_url: str
    status: str  # "試合中" / "試合終了" / "試合前"
    inning_label: str  # 例 "3回裏" (試合中のみ)
    giants_home: bool
    giants_score: int
    opp_score: int
    opp_name: str
    homer_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip(cell: str) -> str:
    return _TAG_RE.sub("", cell).replace("&nbsp;", "").strip()


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


def _find_giants_game_url(now: datetime) -> str:
    # /scores/YYYY/MMDD/ の index は WAF で 403 になる (2026-07-08 Cloud Run 実測)。
    # game_day_gate と同じ月間日程ページ (取得実績あり) から当日の score link を拾う。
    url = f"https://npb.jp/games/{now.year}/schedule_{now.month:02d}_detail.html"
    r = requests.get(url, timeout=10, headers=_HEADERS)
    r.raise_for_status()
    md = now.strftime("%m%d")
    for m in re.finditer(rf"/scores/{now.year}/{md}/([a-z]+)-([a-z]+)-\d+/", r.text):
        if _GIANTS_CODE in (m.group(1), m.group(2)):
            return "https://npb.jp" + m.group(0)
    return ""


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_live_page(html: str, *, game_url: str, date_key: str) -> Optional[LiveGameState]:
    st = _STATUS_RE.search(_TAG_RE.sub(" ", html))
    if not st:
        return None
    if st.group(1) == "試合終了":
        status, inning = "試合終了", ""
    elif st.group(1) == "試合前":
        status, inning = "試合前", ""
    else:
        status, inning = "試合中", f"{st.group(2)}回{st.group(3)}"

    # linescore: ヘッダ行 (1..9 計 H E) の直後 2 行が away / home
    rows: list[list[str]] = []
    for m in _TEAM_ROW_RE.finditer(html):
        cells = [_strip(c) for c in _CELL_RE.findall(m.group(1))]
        if len(cells) >= 12 and ("計" in cells or "R" in cells):
            continue  # ヘッダ
        if len(cells) >= 12 and cells[0]:
            rows.append(cells)
    if len(rows) < 2:
        return None
    away, home = rows[0], rows[1]

    def team_total(cells: list[str]) -> int:
        # 末尾 3 列 = 計 / H / E
        return _parse_int(cells[-3])

    giants_home = "巨人" in home[0] or "読売" in home[0]
    giants_row, opp_row = (home, away) if giants_home else (away, home)
    if "巨人" not in giants_row[0] and "読売" not in giants_row[0]:
        return None
    opp_name = re.sub(r"(タイガース|カープ|ドラゴンズ|ベイスターズ|スワローズ).*$", r"\1", opp_row[0])
    opp_name = opp_row[0][-2:] if not opp_name else opp_name

    homers = []
    text = _TAG_RE.sub(" ", html)
    for hm in _HOMER_RE.finditer(text):
        homers.append(f"{hm.group(1)} {hm.group(2)}")

    return LiveGameState(
        date_key=date_key,
        game_url=game_url,
        status=status,
        inning_label=inning,
        giants_home=giants_home,
        giants_score=team_total(giants_row),
        opp_score=team_total(opp_row),
        opp_name=opp_name,
        homer_lines=homers[:6],
    )


def fetch_today_live_game(now: Optional[datetime] = None) -> Optional[LiveGameState]:
    current = (now or datetime.now(JST)).astimezone(JST)
    date_key = current.strftime("%Y%m%d")
    try:
        game_url = _find_giants_game_url(current)
        if not game_url:
            return None
        r = requests.get(game_url, timeout=10, headers=_HEADERS)
        r.raise_for_status()
        # npb.jp は Content-Type ヘッダに charset が無く requests の既定 decode が
        # 化けるため、UTF-8 (実ページの meta charset) を明示する。
        html = r.content.decode("utf-8", errors="replace")
        return parse_live_page(html, game_url=game_url, date_key=date_key)
    except Exception as exc:  # noqa: BLE001 - lane は fail-open (候補なし)
        LOG.info("live_game_watch fetch failed: %r", exc)
        return None


def _state_blob(date_key: str):
    from google.cloud import storage

    bucket_name = os.environ.get(_STATE_BUCKET_ENV, _DEFAULT_STATE_BUCKET)
    return storage.Client().bucket(bucket_name).blob(f"{_STATE_PREFIX}/{date_key}.json")


def load_prev_state(date_key: str) -> Optional[dict[str, Any]]:
    try:
        return json.loads(_state_blob(date_key).download_as_text())
    except Exception:  # noqa: BLE001 - 初回 / 読めない時は差分なし扱い
        return None


def save_state(state: LiveGameState) -> None:
    try:
        _state_blob(state.date_key).upload_from_string(
            json.dumps(state.to_dict(), ensure_ascii=False), content_type="application/json"
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("live_game_watch state save failed: %r", exc)


def detect_events(prev: Optional[dict[str, Any]], cur: LiveGameState) -> list[dict[str, str]]:
    """前回 snapshot との差分イベント。優先順: 試合終了 > 逆転 > 巨人得点 > 失点。

    各 event: {"kind": ..., "fact": <NPB 公式表記だけで組んだ検証済み事実行>}
    prev が無い (便の初回) 時はイベントを出さない (途中経過の洪水防止)。
    """
    events: list[dict[str, str]] = []
    if cur.status == "試合前":
        return events
    score_line = f"巨人{cur.giants_score}-{cur.opp_score}{cur.opp_name}"
    new_homers = []
    if prev is not None:
        prev_homers = set(prev.get("homer_lines") or [])
        new_homers = [h for h in cur.homer_lines if h not in prev_homers]
    homer_note = ("。本塁打: " + " / ".join(new_homers)) if new_homers else ""

    if cur.status == "試合終了":
        if prev is None or prev.get("status") != "試合終了":
            outcome = "勝利" if cur.giants_score > cur.opp_score else (
                "敗戦" if cur.giants_score < cur.opp_score else "引き分け"
            )
            events.append({
                "kind": "game_end",
                "fact": f"試合終了。{score_line}で巨人の{outcome}{homer_note}",
            })
        return events[:2]

    if prev is None:
        return events

    pg, po = int(prev.get("giants_score") or 0), int(prev.get("opp_score") or 0)
    dg, do = cur.giants_score - pg, cur.opp_score - po
    where = f"{cur.inning_label}時点、" if cur.inning_label else ""
    prev_diff, cur_diff = pg - po, cur.giants_score - cur.opp_score
    if dg > 0 and prev_diff < 0 and cur_diff > 0:
        events.append({
            "kind": "lead_change",
            "fact": f"{where}巨人が{dg}点を取って逆転。{score_line}{homer_note}",
        })
    elif dg > 0:
        label = "先制" if po == 0 and pg == 0 else "追加点" if cur_diff > 0 else "反撃"
        events.append({
            "kind": "giants_score",
            "fact": f"{where}巨人が{dg}点の{label}。{score_line}{homer_note}",
        })
    if do > 0:
        events.append({
            "kind": "opp_score",
            "fact": f"{where}{cur.opp_name}に{do}点。{score_line}{homer_note}",
        })
    return events[:2]


# ── 一球速報 (playbyplay) ベースのプレー検出 (2026-07-09 user) ──────────────
# 得点イベントだけだと投手戦で沈黙する & 観戦ポストが出てこない。
# NPB 一球速報の 1 打席ごとの literal 結果 (見逃し三振 / レフト前ヒット / 併殺 等) を
# 前便比で拾い、安打・好機・三振・長打・併殺でも候補を出す (トリガーを下げる)。
# 事実行には その瞬間の実名 (打者 + 投手 + 走者を作った打者) を束ねる (検索インプ源)。

_PBP_PITCHER_RE = re.compile(r"（(?:先発投手|投手交代)）\s*([^\s<（）]+)")
_PBP_INNING_RE = re.compile(r"<h5[^>]*>(\d+)回(表|裏)（([^）]*)）</h5>(.*?)(?=<h5|\Z)", re.S)


def _giants_side(attacking: str) -> bool:
    return ("巨人" in attacking) or ("読売" in attacking)


def parse_plays(html: str) -> list[dict[str, Any]]:
    """一球速報 HTML を打席順の play list に。各 play は
    {inning, half, giants_batting, pitcher, outs, runners, batter, count, outcome}。
    投手は （先発投手）/（投手交代）行から引き継ぐ (giants_batting=False の回の
    pitcher = 巨人投手)。取得/parse 失敗は空 list。"""
    plays: list[dict[str, Any]] = []
    # 投手は表/裏で別人 (表=巨人守備 / 裏=相手守備 etc)。 投手交代行が無い回は前回の
    # 同じ半分の投手を引き継ぐ。 half をまたいで漏らさないよう half 別に保持する。
    pitcher_by_half: dict[str, str] = {}
    for m in _PBP_INNING_RE.finditer(html or ""):
        inning = int(m.group(1))
        half = m.group(2)
        giants_batting = _giants_side(m.group(3))
        block = m.group(4)
        for row in re.finditer(r"<tr[^>]*>(.*?)</tr>", block, re.S):
            row_html = row.group(1)
            plain = _TAG_RE.sub(" ", row_html)
            if _PBP_PITCHER_RE.search(plain):
                # 「（投手交代）西舘 → 田和」は登板する側 (→ の後 = 最後のリンク)。
                # 「（先発投手）西舘」は1人なので最後=その投手。前者を拾うと交代後の
                # 打者が前の投手に誤帰属し、最終投手も漏れる。
                pit_links = re.findall(r'/bis/players/\d+\.html">([^<]+)</a>', row_html)
                if pit_links:
                    pitcher_by_half[half] = pit_links[-1].strip()
                continue
            cells = [
                _TAG_RE.sub("", c).replace("&nbsp;", "").strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)
            ]
            # 打者は選手リンクから直接取る (代打/代走行はセル位置がズレて「代打」等を
            # 拾ってしまうため。 リンク名なら常に実名)。
            bat_m = re.search(r'/bis/players/\d+\.html">([^<]+)</a>', row_html)
            batter = bat_m.group(1).strip() if bat_m else ""
            runners = next((c for c in cells if "塁" in c), "")
            if len(cells) >= 5 and "アウト" in cells[0] and batter:
                plays.append({
                    "inning": inning, "half": half, "giants_batting": giants_batting,
                    "pitcher": pitcher_by_half.get(half, ""), "outs": cells[0],
                    "runners": runners, "batter": batter,
                    "count": cells[-2], "outcome": cells[-1],
                })
    return plays


def fetch_today_plays(now: Optional[datetime] = None) -> list[dict[str, Any]]:
    current = (now or datetime.now(JST)).astimezone(JST)
    try:
        game_url = _find_giants_game_url(current)
        if not game_url:
            return []
        r = requests.get(game_url + "playbyplay.html", timeout=10, headers=_HEADERS)
        r.raise_for_status()
        return parse_plays(r.content.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 - fail-open (候補なし)
        LOG.info("live_game_watch pbp fetch failed: %r", exc)
        return []


def load_play_cursor(date_key: str) -> Optional[int]:
    try:
        return int(json.loads(_state_blob(date_key + "_pbp").download_as_text()).get("count"))
    except Exception:  # noqa: BLE001 - 初回 / 読めない時は None
        return None


def save_play_cursor(date_key: str, count: int) -> None:
    try:
        _state_blob(date_key + "_pbp").upload_from_string(
            json.dumps({"count": count}), content_type="application/json"
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("live_game_watch pbp cursor save failed: %r", exc)


_HIT_WORDS = ("ヒット", "ホームラン", "ツーベース", "スリーベース", "タイムリー", "本塁打", "安打")
_XBH_WORDS = ("ホームラン", "ツーベース", "スリーベース", "本塁打", "タイムリー")


def _runner_count(runners: str) -> int:
    r = (runners or "").strip()
    if not r or r in ("なし",):
        return 0
    return r.count("塁")


def detect_play_events(
    prev_count: Optional[int], plays: list[dict[str, Any]], *,
    score_ctx: str = "", max_count: int = 2,
) -> list[dict[str, str]]:
    """前便 cursor 以降の新規 play から観戦候補を作る。トリガーは低め
    (長打 / 得点圏の好機 / 巨人投手の三振 / 併殺 / 出塁)。事実行は実名を束ねる。
    prev_count=None (便の初回) は emit せず baseline だけ置く。"""
    if prev_count is None or not plays:
        return []
    new = plays[prev_count:] if 0 <= prev_count <= len(plays) else []
    if not new:
        return []
    scored: list[tuple[int, dict[str, str]]] = []
    ctx = f"。{score_ctx}" if score_ctx else ""
    for i, p in enumerate(new):
        outcome = p["outcome"]
        batter, pitcher, gb = p["batter"], p.get("pitcher", ""), p["giants_batting"]
        inn = f"{p['inning']}回{p['half']}"
        prio, fact = 0, ""
        if any(w in outcome for w in _XBH_WORDS):
            if gb:  # 巨人の長打/タイムリー
                vs = f"、対する{pitcher}" if pitcher else ""
                prio, fact = 3, f"{inn}、巨人・{batter}が{outcome}{vs}{ctx}"
            else:   # 被弾/失点
                by = f"巨人・{pitcher}が" if pitcher else ""
                prio, fact = 3, f"{inn}、{by}{batter}に{outcome}を許す{ctx}"
        elif "併殺" in outcome:
            prio, fact = 2, (
                f"{inn}、巨人・{pitcher}が{batter}を併殺に打ち取る{ctx}" if not gb and pitcher
                else f"{inn}、{batter}が併殺{ctx}")
        elif gb and any(w in outcome for w in _HIT_WORDS):
            # 好機: この打者の出塁で走者が溜まっている時は次打者含め束ねる
            nxt = new[i + 1]["batter"] if i + 1 < len(new) and new[i + 1]["giants_batting"] else ""
            nxt_s = f"、続く打席は{nxt}" if nxt else ""
            prio, fact = 2, f"{inn}、巨人・{batter}が{outcome}で出塁{nxt_s}{ctx}"
        elif (not gb) and "三振" in outcome and pitcher:
            prio, fact = 1, f"{inn}、巨人・{pitcher}が{batter}を{outcome}に仕留める{ctx}"
        if prio and fact:
            scored.append((prio, {"kind": "play", "fact": fact}))
    scored.sort(key=lambda t: -t[0])
    return [e for _, e in scored[: max(0, max_count)]]


def build_mvp_poll_line(
    plays: list[dict[str, Any]], win: bool
) -> str:
    """試合後 recap 用の Poll 案 1 行 (2026-07-10 user「小手先でインプ」)。

    Poll は投票→表示の好循環でインプが伸びやすい。X API Free では自動投稿
    しないので、mail に選択肢を書いて user が X アプリで 30 秒で Poll 化する。
    選択肢 = 一球速報の巨人側活躍選手 (本塁打 → 安打順 → 登板投手) 最大4人。
    2人未満なら Poll にならないので "" を返す。
    """
    hrs: list[str] = []
    hits: list[str] = []
    pitchers: list[str] = []
    for p in plays:
        oc = p.get("outcome", "")
        b = p.get("batter", "")
        if p.get("giants_batting") and b:
            if ("ホームラン" in oc or "本塁打" in oc) and b not in hrs:
                hrs.append(b)
            elif any(w in oc for w in _HIT_WORDS) and b not in hits:
                hits.append(b)
        pit = p.get("pitcher", "")
        if (not p.get("giants_batting")) and pit and pit not in pitchers:
            pitchers.append(pit)
    names: list[str] = []
    for nm in hrs + hits + pitchers[:1]:
        if nm not in names:
            names.append(nm)
        if len(names) >= 4:
            break
    if len(names) < 2:
        return ""
    q = "今日のMVPは？" if win else "明日、期待したいのは？"
    return f"📊 Poll案「{q}」→ " + " / ".join(names)


def giants_fullname_map() -> dict[str, str]:
    """姓 → フルネーム (敬称なし・スペースなし)。姓が roster 内で一意な選手のみ。

    NPB 一球速報の選手名は姓のみ (泉口 / 西舘)。X の検索インプはフルネーム
    (泉口友汰) で拾われるため (2026-07-10 user)、roster で一意に解決できる
    姓だけ決定論的に置換する。同姓複数・roster 外 (相手チーム)・外国人等の
    一語登録名 (キャベッジ) はそのまま = 捏造ゼロ。roster 取得失敗は空 map。
    """
    try:
        from src.giants_roster_loader import load_active_roster

        entries = load_active_roster()
    except Exception as exc:  # noqa: BLE001 - roster 不達は置換なしで続行
        LOG.info("giants_fullname_map skip: %r", exc)
        return {}
    by_surname: dict[str, list[str]] = {}
    for e in entries or []:
        name = str(e.get("name") or "").strip()
        if not name:
            continue
        surname = name.split(" ", 1)[0]
        full = name.replace(" ", "")
        if full and full not in by_surname.setdefault(surname, []):
            by_surname[surname].append(full)
    return {
        s: fulls[0]
        for s, fulls in by_surname.items()
        if len(fulls) == 1 and s != fulls[0]
    }


def apply_fullname_map(
    plays: list[dict[str, Any]], fmap: dict[str, str]
) -> list[dict[str, Any]]:
    """plays の巨人側の名前だけフルネーム化した copy を返す。

    巨人側 = giants_batting=True の batter / giants_batting=False の pitcher。
    相手選手は roster に無いので触らない (同姓の巨人選手がいても誤置換しない)。
    """
    if not fmap:
        return plays
    out: list[dict[str, Any]] = []
    for p in plays:
        q = dict(p)
        if p.get("giants_batting"):
            q["batter"] = fmap.get(p.get("batter", ""), p.get("batter", ""))
        else:
            q["pitcher"] = fmap.get(p.get("pitcher", ""), p.get("pitcher", ""))
        out.append(q)
    return out


def build_recap_fact(
    plays: list[dict[str, Any]], giants_score: int, opp_score: int, opp_name: str
) -> str:
    """試合後 recap 用の事実行。一球速報から巨人の活躍選手を実名で大量に束ねる
    (本塁打 / 安打 / 登板投手)。数字・名前は速報にあるものだけ (捏造ガード用)。"""
    win = giants_score > opp_score
    result = "勝利" if win else ("敗戦" if giants_score < opp_score else "引き分け")
    hits: list[str] = []
    hrs: list[str] = []
    pitchers: list[str] = []
    seen: set[str] = set()
    for p in plays:
        oc = p.get("outcome", "")
        b = p.get("batter", "")
        if p.get("giants_batting") and b and any(w in oc for w in _HIT_WORDS):
            if b not in seen:
                seen.add(b)
                hits.append(b)
            if ("ホームラン" in oc or "本塁打" in oc) and b not in hrs:
                hrs.append(b)
        pit = p.get("pitcher", "")
        if (not p.get("giants_batting")) and pit and pit not in pitchers:
            pitchers.append(pit)
    parts = [f"試合終了。巨人{giants_score}-{opp_score}{opp_name}で巨人の{result}"]
    if hrs:
        parts.append("本塁打は" + "・".join(hrs))
    if hits:
        parts.append("安打は" + "・".join(hits[:8]))
    if pitchers:
        parts.append("登板は巨人・" + "・".join(pitchers[:4]))
    return "。".join(parts)
