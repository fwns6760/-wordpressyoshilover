"""Googleニュースの暗号化リンク（news.google.com/rss/articles/CBMi...）を
元記事の実URLに解決する。

CARE LAND サテライト記事は Googleニュースのキーワード検索RSSを母数にする。
RSSの<link>は news.google.com のラッパーで、2024年以降は単純リダイレクトせず
JSページを返すため、適法引用に必要な「元記事の実URL／本文」が取れない。
記事ページに埋め込まれた署名 (data-n-a-sg / data-n-a-ts) を使って
Googleの batchexecute エンドポイントに問い合わせ、実URLを得る。

X API/secret 不要。失敗時は None を返し、呼び出し側は元URL（ラッパー）に
degrade する（記事はできるが引用ブロックは付かない）。
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

LOG = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"

# 同一実行内で同じ記事IDが複数キーワードRSSに現れるため、解決結果（成功URL/None=失敗）を
# プロセス内キャッシュして news.google.com への重複リクエストを抑える。429（IPブロック）対策。
_RESOLVE_CACHE: dict[str, str | None] = {}
# news.google.com への連続アクセスがバーストすると 429 になりやすいので、最小間隔を空ける。
_MIN_INTERVAL = float(os.environ.get("GNEWS_RESOLVE_MIN_INTERVAL", "1.2"))
_last_request_at = [0.0]

# Cloud Run など DC の IP は Google News に 429 で実質ブロックされ、リトライしても通らない。
# 連続で 429 ブロックが続いたら、その実行では以降の解決を即あきらめ（None）、retry で時間を
# 浪費せず非 Google ソースの新着に早く到達できるようにする（サーキットブレーカー）。
_BREAKER_THRESHOLD = int(os.environ.get("GNEWS_RESOLVE_BREAKER", "3"))
_consecutive_429 = [0]
_circuit_open = [False]


def reset_circuit() -> None:
    """テスト/実行境界用にブレーカー・キャッシュ・スロットルを初期化する。"""
    _RESOLVE_CACHE.clear()
    _consecutive_429[0] = 0
    _circuit_open[0] = False
    _last_request_at[0] = 0.0


def _throttle() -> None:
    """直前のリクエストから _MIN_INTERVAL 秒空くまで待つ（バースト防止）。"""
    if _MIN_INTERVAL <= 0:
        return
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request_at[0])
    if wait > 0:
        time.sleep(wait)
    _last_request_at[0] = time.monotonic()


def is_google_news_url(url: str) -> bool:
    """Googleニュースのラッパーリンクか。"""
    return bool(url) and "news.google.com" in url and "/articles/" in url


def _get(url: str, *, data: bytes | None = None, timeout: int = 20,
         extra_headers: dict | None = None) -> tuple[str, str]:
    headers = {"User-Agent": _UA}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers, data=data)
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return resp.geturl(), raw.decode("utf-8", "ignore")


def _article_id(url: str) -> str:
    """ラッパーURLから記事ID（CBMi...）を取り出す。"""
    path = urllib.parse.urlparse(url).path
    return path.rsplit("/", 1)[-1].split("?")[0]


def resolve_google_news_url(url: str, *, timeout: int = 20, retries: int = 3) -> str | None:
    """Googleニュースのラッパーリンクを元記事の実URLに解決する。

    解決できなければ None。news.google.com 自身に着地した場合も None 扱い。
    429 (Too Many Requests) は指数バックオフで retries 回まで再試行する。
    """
    if not is_google_news_url(url):
        return None
    art_id = _article_id(url)
    if not art_id:
        return None
    if art_id in _RESOLVE_CACHE:
        return _RESOLVE_CACHE[art_id]
    if _circuit_open[0]:
        # この実行は Google News に 429 ブロックされていると判断済み。即あきらめる。
        return None
    result = _resolve_with_retry(art_id, timeout=timeout, retries=retries)
    _RESOLVE_CACHE[art_id] = result
    return result


def _resolve_with_retry(art_id: str, *, timeout: int, retries: int) -> str | None:
    for attempt in range(retries + 1):
        _throttle()
        try:
            out = _resolve_once(art_id, timeout=timeout)
            _consecutive_429[0] = 0  # 成功（None含む非429）したらブレーカーのカウンタを戻す
            return out
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt >= retries:
                # この記事はリトライ尽き。連続429が閾値を超えたらブレーカーを開く。
                _consecutive_429[0] += 1
                if _consecutive_429[0] >= _BREAKER_THRESHOLD:
                    _circuit_open[0] = True
                    LOG.warning("gnews_resolve_circuit_open after=%s consecutive 429 "
                                "(以降この実行ではGoogle News解決を即スキップ)",
                                _consecutive_429[0])
            if exc.code == 429 and attempt < retries:
                # Retry-After を尊重しつつ、指数バックオフ＋ジッタで間隔を空ける。
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    base = float(retry_after) if retry_after else 0.0
                except ValueError:
                    base = 0.0
                backoff = max(base, 3.0 * (2 ** attempt)) + random.uniform(0, 1.5)
                LOG.info("gnews_resolve_429 id=%s retry_in=%.1fs", art_id[:24], backoff)
                time.sleep(backoff)
                continue
            LOG.info("gnews_resolve_http_error id=%s code=%s", art_id[:24], exc.code)
            return None
        except Exception as exc:  # noqa: BLE001
            LOG.info("gnews_resolve_failed id=%s error=%s", art_id[:24], type(exc).__name__)
            return None
    return None


def _resolve_once(art_id: str, *, timeout: int) -> str | None:
    """1回分の解決。HTTPError は呼び出し側 (resolve_google_news_url) で 429 リトライ処理する。"""
    # 記事ページから署名 (data-n-a-sg) とタイムスタンプ (data-n-a-ts) を取る。
    _, page = _get("https://news.google.com/articles/" + art_id, timeout=timeout)
    sig = re.search(r'data-n-a-sg="([^"]+)"', page)
    ts = re.search(r'data-n-a-ts="([^"]+)"', page)
    if not (sig and ts):
        LOG.info("gnews_resolve_no_signature id=%s", art_id[:24])
        return None
    inner = json.dumps([
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
          None, None, None, None, None, 0, 1],
         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        art_id, ts.group(1), sig.group(1),
    ])
    payload = [[["Fbv4je", inner]]]
    body = "f.req=" + urllib.parse.quote(json.dumps(payload))
    _, res = _get(
        _BATCH_URL, data=body.encode(), timeout=timeout,
        extra_headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
    )
    # レスポンス中の最初の外部URLを拾う（news.google.com 以外）。
    for m in re.finditer(r'https?://[^\\"\s]+', res):
        cand = m.group(0)
        if "news.google.com" not in cand and "gstatic.com" not in cand:
            return cand
    LOG.info("gnews_resolve_no_url id=%s", art_id[:24])
    return None


def split_publisher_from_title(title: str) -> tuple[str, str | None]:
    """GoogleニュースRSSのタイトル『記事見出し - 媒体名』を分割する。

    返り値 (clean_title, publisher_or_None)。区切りが無ければ (title, None)。
    """
    if not title:
        return title, None
    # 全角・半角ハイフンの " - " 区切りの最後を媒体名とみなす。
    m = re.match(r"^(.*\S)\s+[-–]\s+([^-–]+)$", title.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title, None


__all__ = [
    "is_google_news_url",
    "resolve_google_news_url",
    "split_publisher_from_title",
]
