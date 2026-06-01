"""451: X-buzz-post radar — 自前 RSSHub (X→RSS、 X API 不使用) で巨人系 X account を
read-only 巡回し、「懐かしい・ファンが面白い・いま話題」の **X 投稿** を拾って、
ユーザーが **引用RT / リプライ** で native に乗れる候補にする。

方針 (user 2026-06-01):
- **YouTube は使わない**。 外部リンク (YouTube 等) は X でリーチが落ちるため、
  X 内で完結する「引用RT/リプライ」候補にする (外部リンクを本文に貼らない)。
- 動画ファイルの転載はしない (そもそも投稿の引用 = native 参照のみ)。
- Gemini / X API は使わない。 RSSHub の twitter/user route は 445 で稼働実証済み。
"""
from __future__ import annotations

import re as _re
from typing import Callable, Optional
from urllib.request import Request as _Request, urlopen as _urlopen

# 445 と同じ自前 RSSHub (X→RSS bridge)。
_RSSHUB_BASE = "https://rsshub-487178857517.asia-northeast1.run.app"
_BUZZ_HANDLES = ["yomiuri_giants", "TokyoGiants", "hochi_giants", "Sanspo_Giants"]

# 「懐かしい / 名場面」系シグナル
_NOSTALGIA_MARKERS = (
    "名場面", "名シーン", "名勝負", "名プレー", "名守備", "名言", "伝説", "レジェンド",
    "懐かし", "振り返り", "回顧", "あの日", "あの試合", "思い出", "秘話", "秘蔵", "お宝",
    "蔵出し", "アーカイブ", "球史", "当時", "現役時代", "全盛期",
)
# 「ファンが面白い / 反応する」系シグナル
_FUN_MARKERS = (
    "神", "規格外", "衝撃", "必見", "鳥肌", "劇的", "圧巻", "伝説の", "ヤバ", "エグ",
    "サヨナラ", "満塁", "逆転", "完全試合", "ノーヒットノーラン", "好プレー", "ファインプレー",
    "デビュー", "初", "号", "引退", "復活", "復帰",
)


def classify_post(
    text: str,
    *,
    player: str = "",
    buzz_players: Optional[set[str]] = None,
) -> tuple[int, str]:
    """X 投稿テキストからスコアと型タグを返す。 pure / 決定的 (LLM 不使用)。

    ``buzz_players`` = いま X でバズってる選手集合 (RSSHub 言及数由来)。 該当を最優先で加点。
    Returns ``(score, type_tag)``。 score>=2 を候補閾値の目安にする。
    """
    t = text or ""
    score = 0
    nostalgia = any(m in t for m in _NOSTALGIA_MARKERS)
    fun = any(m in t for m in _FUN_MARKERS)
    has_year = bool(_re.search(r"(19|20)\d{2}", t))
    is_buzz = bool(player and buzz_players and player in buzz_players)

    if nostalgia:
        score += 2
    if fun:
        score += 1
    if has_year:
        score += 1
    if player:
        score += 2
    if is_buzz:
        score += 3  # X バズ選手 = 最優先

    if is_buzz:
        tag = "Xで話題"
    elif nostalgia:
        tag = "懐かし・名場面"
    elif fun:
        tag = "好プレー・反応"
    elif player:
        tag = "選手の話題"
    else:
        tag = "巨人の話題"
    return score, tag


def _default_fetch(url: str, *, timeout: int = 12) -> str:
    req = _Request(url, headers={"User-Agent": "yoshilover-x-buzz-radar/1.0"})
    with _urlopen(req, timeout=timeout) as resp:  # noqa: S310 (自前 RSSHub のみ)
        return resp.read().decode("utf-8", errors="replace")


def _strip_html(s: str) -> str:
    s = _re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=_re.S)
    s = _re.sub(r"<[^>]+>", " ", s)
    s = _re.sub(r"&[#0-9A-Za-z]+;", " ", s)
    return _re.sub(r"\s+", " ", s).strip()


def _extract_rss_items(xml: str) -> list[dict]:
    """RSSHub の twitter feed (RSS 2.0) から各 item の {text, url} を抽出。"""
    out: list[dict] = []
    for item in _re.findall(r"<item\b.*?</item>", xml or "", _re.S | _re.I):
        parts = []
        for tag in ("title", "description"):
            m = _re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", item, _re.S | _re.I)
            if m:
                parts.append(m.group(1))
        text = _strip_html(" ".join(parts))
        link_m = _re.search(r"<link\b[^>]*>(.*?)</link>", item, _re.S | _re.I)
        url = _strip_html(link_m.group(1)) if link_m else ""
        if text:
            out.append({"text": text, "url": url})
    return out


def fetch_buzzing_players(
    *,
    detect_player_fn: Callable[[str], str],
    fetch_fn: Optional[Callable[[str], str]] = None,
    handles: Optional[list[str]] = None,
    limit: int = 30,
    top_n: int = 8,
    min_mentions: int = 2,
) -> dict[str, int]:
    """RSSHub 経由で巨人系 X account を読み、 言及の多い選手を {name: count} で返す。

    X API は使わない (445 と同じ self-host RSSHub の twitter/user route)。 取得失敗は
    silent skip。 ``min_mentions`` 未満は落とし、 上位 ``top_n`` を返す。
    """
    fetch = fetch_fn or _default_fetch
    handles = handles or _BUZZ_HANDLES
    counts: dict[str, int] = {}
    for h in handles:
        try:
            xml = fetch(f"{_RSSHUB_BASE}/twitter/user/{h}?limit={limit}")
        except Exception:  # noqa: BLE001
            continue
        for item in _extract_rss_items(xml):
            try:
                p = detect_player_fn(item["text"]) or ""
            except Exception:  # noqa: BLE001
                p = ""
            if p:
                counts[p] = counts.get(p, 0) + 1
    filtered = {k: v for k, v in counts.items() if v >= min_mentions}
    return dict(sorted(filtered.items(), key=lambda kv: kv[1], reverse=True)[:top_n])


def gather_buzz_posts(
    *,
    detect_player_fn: Callable[[str], str],
    fetch_fn: Optional[Callable[[str], str]] = None,
    handles: Optional[list[str]] = None,
    buzz_players: Optional[set[str]] = None,
    limit: int = 30,
    min_score: int = 2,
) -> list[dict]:
    """巨人系 X account の投稿を巡回し、 引用RT 候補に値する投稿を score 降順で返す。

    各 dict: ``text / url / handle / player / score / type_tag``。 X 内で完結する
    引用RT/リプライ用なので、 YouTube 等の外部リンクは扱わない。
    """
    fetch = fetch_fn or _default_fetch
    handles = handles or _BUZZ_HANDLES
    out: list[dict] = []
    seen_urls: set[str] = set()
    for h in handles:
        try:
            xml = fetch(f"{_RSSHUB_BASE}/twitter/user/{h}?limit={limit}")
        except Exception:  # noqa: BLE001
            continue
        for item in _extract_rss_items(xml):
            text = item.get("text", "")
            url = item.get("url", "")
            if not text or not url or url in seen_urls:
                continue
            try:
                player = detect_player_fn(text) or ""
            except Exception:  # noqa: BLE001
                player = ""
            score, tag = classify_post(text, player=player, buzz_players=buzz_players)
            if score < min_score:
                continue
            seen_urls.add(url)
            out.append({
                "text": text,
                "url": url,
                "handle": h,
                "player": player,
                "score": score,
                "type_tag": tag,
            })
    out.sort(key=lambda d: d["score"], reverse=True)
    return out
