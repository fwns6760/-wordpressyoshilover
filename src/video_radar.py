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

import os as _os
import re as _re
import threading as _threading
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from datetime import datetime as _datetime, timezone as _timezone
from email.utils import parsedate_to_datetime as _parsedate_to_datetime
from typing import Callable, Optional
from urllib.request import Request as _Request, urlopen as _urlopen

# 445 と同じ自前 RSSHub (X→RSS bridge)。
_RSSHUB_BASE = "https://rsshub-487178857517.asia-northeast1.run.app"
# 動画 source の巨人系 X account (user 2026-06-01 指定 + 既存良source)。 全ハンドル実feed
# 検証済 (実在 / 鮮度 / 動画サムネ): TokyoGiants=読売ジャイアンツ公式, hochi_giants=報知,
# Sanspo_Giants=サンスポ(動画多), tospo_giants=東スポ巨人, SponichiGiants=スポニチ巨人,
# koba_nikkan=小早川宗一郎(日刊・練習動画), ntv_baseball=DRAMATIC BASEBALL 2026(日テレ巨人中継・動画最多),
# DAZNJPNBaseball=DAZNベースボール。 旧 yomiuri_giants は死にハンドル (1月の「@趣味」RTのみ) で除外。
_BUZZ_HANDLES = [
    "TokyoGiants",
    "hochi_giants",
    "Sanspo_Giants",
    "tospo_giants",
    "SponichiGiants",
    "koba_nikkan",
    "ntv_baseball",
    "DAZNJPNBaseball",
    # 2026-07-02 user 決定 (ライバル差別化の動画SNS)。実 feed 検証済。
    # この lane は require_video=True なので動画付き投稿しか候補にならない。
    # TeamUehara=上原浩治チーム (OB トーク/コラボ動画、巨人選手ゲスト回が狙い)
    # samuraijapan_pr=侍ジャパン公式 (巨人選手選出/合宿時に動画が出るイベント駆動)
    "TeamUehara",
    "samuraijapan_pr",
    # 2026-07-02 user 指摘「他の大手スポーツ紙の記者は外れてない?」で判明した漏れ:
    # 日刊スポーツ巨人担当班 (記者3人体制、練習動画/グルメ/写真、動画 4/15 実測)。
    # 個人の koba_nikkan は入っていたが班アカが未登録だった。
    "nikkan_giants",
    # 2026-07-02 user 追加指定: 水上智恵 (スポーツ報知・巨人担当記者、投手&野手担当)。
    # 実 feed 検証: 18件中 動画10 (練習動画/球場動画中心、班アカ hochi_giants より動画率高)。
    "chiehochi6",
]

# 2026-07-03 実事故: DAZNJPNBaseball (12球団アカ) のオリックス選手クリップが
# 「好プレー」語だけで score 2 に届き、巨人と無関係のまま候補入りした。
# 巨人専門でない handle は、巨人選手の検出 or 巨人語の明示がある投稿のみ通す。
_MULTI_TEAM_HANDLES = frozenset({
    "DAZNJPNBaseball",
    "TeamUehara",
    "samuraijapan_pr",
})

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


def _default_fetch(url: str, *, timeout: int = 0) -> str:
    # 2026-07-07 実測: RSSHub twitter route の未キャッシュ応答は約 22s (X 上流)。
    # 旧 default 12s では未キャッシュ handle がほぼ必ず timeout し、リプ/動画
    # 候補の親ポスト取得が全滅していた。30s に拡大 (env で調整可)。
    if timeout <= 0:
        try:
            timeout = int(_os.environ.get("RSSHUB_FETCH_TIMEOUT_SECONDS") or 30)
        except ValueError:
            timeout = 30
    req = _Request(url, headers={"User-Agent": "yoshilover-x-buzz-radar/1.0"})
    with _urlopen(req, timeout=timeout) as resp:  # noqa: S310 (自前 RSSHub のみ)
        return resp.read().decode("utf-8", errors="replace")


# 2026-07-02 コスト削減: 1 便 (= 1 プロセス) 内で同じ feed URL を複数 lane が
# 取り直さないよう、default fetch を process 内 cache する。Job は one-shot
# プロセスなので鮮度問題はない (fetch_fn 注入時 = テストでは使わない)。
_FETCH_CACHE: dict[str, str] = {}
_FETCH_CACHE_LOCK = _threading.Lock()


def _cached_default_fetch(url: str) -> str:
    with _FETCH_CACHE_LOCK:
        if url in _FETCH_CACHE:
            return _FETCH_CACHE[url]
    body = _default_fetch(url)
    with _FETCH_CACHE_LOCK:
        _FETCH_CACHE[url] = body
    return body


def prefetch_feeds(
    urls: list[str],
    fetch: Callable[[str], str],
    *,
    max_workers: int = 6,
) -> dict[str, object]:
    """URL 群を並列 fetch して {url: xml or Exception} を返す。

    2026-07-02 コスト削減: RSSHub への feed fetch が 1 便あたり 20 本超の直列
    待ちで vCPU 秒の最大要因だったため並列化 (待ちは I/O なので wall time 短縮
    = Cloud Run Job の課金秒数短縮に直結)。失敗はここで握らず Exception を
    値として返し、呼び出し側の従来どおりの skip / log 挙動に委ねる。
    """
    uniq = list(dict.fromkeys(urls))
    results: dict[str, object] = {}
    if not uniq:
        return results

    def _fetch_wave(targets: list[str]) -> None:
        with _ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as ex:
            futs = {ex.submit(fetch, u): u for u in targets}
            for f in futs:
                try:
                    results[futs[f]] = f.result()
                except Exception as exc:  # noqa: BLE001
                    results[futs[f]] = exc

    _fetch_wave(uniq)
    # 2026-07-07: RSSHub は min-instances=0 のため、便頭の一斉 fetch が cold start
    # に刺さり handle 単位で timeout する (実測 62 件/19h → MLB/ファンリプ候補が
    # 便ごと全滅)。 初回 wave で instance が温まった後、失敗分だけ 1 回再試行する。
    failed = [u for u in uniq if isinstance(results.get(u), Exception)]
    if failed:
        _fetch_wave(failed)
    return results


def _strip_html(s: str) -> str:
    s = _re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=_re.S)
    s = _re.sub(r"<[^>]+>", " ", s)
    s = _re.sub(r"&[#0-9A-Za-z]+;", " ", s)
    return _re.sub(r"\s+", " ", s).strip()


def _is_retweet_text(text: str) -> bool:
    """RSSHub twitter/user text that starts with RT is not an original post."""
    return str(text or "").lstrip().startswith(("RT ", "RT　", "RT@", "RT:", "RT："))


# X 投稿に動画が付いているかの判定マーカー。 RSSHub の twitter feed は description 内に
# 動画ポスターを <img src="https://pbs.twimg.com/amplify_video_thumb/..."> 等で埋め込む
# (実 feed で確認済 2026-06-01)。 これらを含む投稿だけが「動画をポスト」長押しの対象になる。
_VIDEO_THUMB_MARKERS = (
    "amplify_video_thumb",   # native 動画アップロード
    "ext_tw_video_thumb",    # 外部 / 旧形式動画
    "tweet_video_thumb",     # アニメ GIF (X 上は動画扱い)
    "<video",                # 稀に video 要素そのもの
    "video/mp4",
    "/video/1",
)


def _has_video_markup(desc_html: str) -> bool:
    """description (生 HTML) に動画ポスター/動画要素マーカーがあれば True。"""
    s = (desc_html or "").lower()
    return any(m in s for m in _VIDEO_THUMB_MARKERS)


def _parse_pubdate(item: str):
    """item の <pubDate> を tz-aware datetime に。 取れなければ None。"""
    m = _re.search(r"<pubDate\b[^>]*>(.*?)</pubDate>", item, _re.S | _re.I)
    if not m:
        return None
    try:
        return _parsedate_to_datetime(m.group(1).strip())
    except (TypeError, ValueError, IndexError):
        return None


def _extract_rss_items(xml: str) -> list[dict]:
    """RSSHub の twitter feed (RSS 2.0) から各 item の {text, url, has_video, published_at} を抽出。"""
    out: list[dict] = []
    for item in _re.findall(r"<item\b.*?</item>", xml or "", _re.S | _re.I):
        parts = []
        desc_raw = ""
        for tag in ("title", "description"):
            m = _re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", item, _re.S | _re.I)
            if m:
                parts.append(m.group(1))
                if tag == "description":
                    desc_raw = m.group(1)
        text = _strip_html(" ".join(parts))
        link_m = _re.search(r"<link\b[^>]*>(.*?)</link>", item, _re.S | _re.I)
        url = _strip_html(link_m.group(1)) if link_m else ""
        if text:
            out.append({
                "text": text,
                "url": url,
                "has_video": _has_video_markup(desc_raw),
                # 静止画 (写真) の添付判定。RSSHub は写真を
                # <img src="https://pbs.twimg.com/media/..."> で埋め込む。
                # 動画サムネ (amplify_video_thumb 等) は media/ を含まないので
                # 動画と画像は独立に判定できる (2026-07-02 MLB watch 用)。
                "has_image": "pbs.twimg.com/media/" in (desc_raw or ""),
                "published_at": _parse_pubdate(item),
            })
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
    fetch = fetch_fn or _cached_default_fetch
    handles = handles or _BUZZ_HANDLES
    counts: dict[str, int] = {}
    urls = {h: f"{_RSSHUB_BASE}/twitter/user/{h}?limit={limit}" for h in handles}
    fetched = prefetch_feeds(list(urls.values()), fetch)
    for h in handles:
        xml = fetched.get(urls[h])
        if not isinstance(xml, str):
            continue
        for item in _extract_rss_items(xml):
            text = str(item.get("text") or "")
            if _is_retweet_text(text):
                continue
            try:
                p = detect_player_fn(text) or ""
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
    require_video: bool = True,
    allow_photo_and_article: bool = False,
    now: Optional[_datetime] = None,
    max_age_hours: float = 48.0,
) -> list[dict]:
    """巨人系 X account の投稿を巡回し、 引用RT 候補に値する投稿を score 降順で返す。

    各 dict: ``text / url / handle / player / score / type_tag / has_video / has_image``。
    X 内で完結する引用RT/リプライ用なので、 YouTube 等の外部リンクは扱わない。

    ``require_video=True`` (既定) のとき、 **動画が付いた投稿だけ** を候補にする。
    動画なし投稿では「動画をポスト」長押しが無意味で、 動画こそがインプを稼ぐため
    (user 2026-06-01)。 動画判定は description の動画サムネ/動画要素マーカー (実 feed 検証済)。

    ``allow_photo_and_article=True`` (2026-07-10 user「記事も。報知とか公式とかの
    記事や写真系」) のとき動画 gate を外し、 写真付き・記事見出し投稿も通す
    (handle は全て媒体/公式/記者アカのため、 score gate と鮮度 gate はそのまま効く)。

    ``max_age_hours`` (既定 48h) より古い投稿は除外する (user 2026-06-01「古いデータ出さない」)。
    feed には最大 1 週間前の投稿が混ざるため、 pubDate ベースで鮮度 gate する。 投稿日時不明は
    判定不能なので通す (RSSHub は通常 RFC1123 を返すので稀)。
    """
    fetch = fetch_fn or _cached_default_fetch
    handles = handles or _BUZZ_HANDLES
    now = now or _datetime.now(_timezone.utc)
    out: list[dict] = []
    seen_urls: set[str] = set()
    feed_urls = {h: f"{_RSSHUB_BASE}/twitter/user/{h}?limit={limit}" for h in handles}
    fetched = prefetch_feeds(list(feed_urls.values()), fetch)
    for h in handles:
        xml = fetched.get(feed_urls[h])
        if not isinstance(xml, str):
            continue
        for item in _extract_rss_items(xml):
            text = item.get("text", "")
            url = item.get("url", "")
            if not text or not url or url in seen_urls:
                continue
            if _is_retweet_text(text):
                continue
            has_video = bool(item.get("has_video"))
            if require_video and not has_video and not allow_photo_and_article:
                continue
            published_at = item.get("published_at")
            if published_at is not None:
                age_h = (now - published_at).total_seconds() / 3600.0
                if age_h > max_age_hours:
                    continue
            try:
                player = detect_player_fn(text) or ""
            except Exception:  # noqa: BLE001
                player = ""
            # 多球団 handle は巨人関連の裏付けが無い投稿を通さない (他球団クリップ誤爆防止)。
            if (
                h in _MULTI_TEAM_HANDLES
                and not player
                and "巨人" not in text
                and "ジャイアンツ" not in text
            ):
                continue
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
                "has_video": has_video,
                "has_image": bool(item.get("has_image")),
            })
    out.sort(key=lambda d: d["score"], reverse=True)
    return out
