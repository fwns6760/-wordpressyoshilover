"""player_voice_digest cluster detection (334-QA Phase 2a).

候補記事 list を入力に、以下の cluster 条件を全て満たす digest cluster を返す:

  1. 同一試合 (game_id)
  2. 同一選手 (player_id)
  3. 3 サイト以上の異なる media family を含む
     (報知 / サンスポ / スポニチ / 日刊スポーツ / デイリー / 東スポ)
  4. 親候補 (本文最長 + tiebreaker) に本人発言 literal が 20-40 字で存在
  5. 親候補にイベント token (literal 数値 / 試合状態 fact) が存在
  6. 子候補が 2 件以上、それぞれ別 family・短い見出し or 抜粋 (30-50 字 literal)

parent + child モデル (2026-05-14 user lock): hub 型構造。
  - parent: 本文最長 (tiebreaker: source_trust → published 早)
  - children: 親と別 family、各 family 最長 title 1 件、計 2-5 件

AI / LLM 一切経由しない pure 構造化選択 + literal substring 抽出。
3-token のいずれかが揃わない cluster は返さない (caller は digest 化せず通常 path)。

本 module は rss_fetcher と疎結合: 標準化済み candidate dict を入力にする
pure 関数。rss_fetcher への接続は Phase 2b で行う。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse

from src.source_trust import TRUSTED_SOURCE_PROFILES


_DIGEST_SOURCE_FAMILIES: frozenset[str] = frozenset({
    "hochi",
    "sanspo",
    "sponichi",
    "nikkansports",
    "daily",
    "tokyo_sports",
})


_OFFICIAL_FAMILIES: frozenset[str] = frozenset({
    "giants_official",
    "npb_official",
})


_FAMILY_LABEL: Mapping[str, str] = {
    "hochi": "スポーツ報知",
    "sanspo": "サンスポ",
    "sponichi": "スポニチ",
    "nikkansports": "日刊スポーツ",
    "daily": "デイリー",
    "tokyo_sports": "東スポ",
}


_OFFICIAL_WEB_HOSTS: frozenset[str] = frozenset({
    "giants.jp",
    "www.giants.jp",
    "npb.jp",
    "www.npb.jp",
    "npb.or.jp",
    "www.npb.or.jp",
})


_OFFICIAL_X_HANDLE_HINTS: Mapping[str, str] = {
    "tokyogiants": "巨人公式X",
    "yomiuri_giants": "巨人公式X",
    "/twitter/user/npb": "NPB公式X",
}


_TRUST_RANK: Mapping[str, int] = {
    "primary": 3,
    "high": 2,
    "mid-high": 2,
    "secondary": 1,
    "mid": 1,
}


_QUOTE_RE = re.compile(r"[「『]([^」』]+)[」』]")


_EVENT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"(\d+号(?:サヨナラ|逆転)?ホームラン)"),
    re.compile(r"(サヨナラ(?:ホームラン|安打|打|勝ち)?)"),
    re.compile(r"(逆転(?:3ラン|2ラン|ホームラン|勝ち)?)"),
    re.compile(r"(完封(?:勝ち|勝利)?)"),
    re.compile(r"(完投(?:勝利)?)"),
    re.compile(r"(\d+回\d+失点)"),
    re.compile(r"(\d+奪三振)"),
    re.compile(r"(\d+安打\d+打点)"),
    re.compile(r"(猛打賞)"),
    re.compile(r"(\d+連勝)"),
)


@dataclass(frozen=True)
class DigestChild:
    """digest cluster の子 (親以外の媒体ポスト)。"""

    family: str
    label: str
    snippet: str
    url: str


@dataclass(frozen=True)
class DigestOfficial:
    """digest cluster の公式 source (巨人公式 / NPB 公式)。

    334-QA Phase 2a-ext: ヨシラバーらしさ Section B (公式情報パネル) 用。
    media digest (parent + children) とは別 list、cluster の付加情報として
    body renderer で「【📣 公式が発表】」 section に展開する。
    """

    family: str  # giants_official / npb_official
    label: str   # 巨人公式サイト / 巨人公式X / NPB公式 等
    snippet: str  # literal 30-50 chars
    url: str


@dataclass(frozen=True)
class DigestCluster:
    """digest cluster (親 1 + 子 N、3 family 以上 + 公式 0-N)。"""

    game_id: str
    player_id: str
    player_name: str
    parent_candidate: Mapping[str, Any]
    parent_family: str
    quote: str
    event_token: str
    children: Sequence[DigestChild]
    officials: Sequence[DigestOfficial] = ()

    @property
    def source_families(self) -> frozenset[str]:
        fams = {self.parent_family}
        fams.update(c.family for c in self.children)
        return frozenset(fams)

    @property
    def official_families(self) -> frozenset[str]:
        return frozenset(o.family for o in self.officials)


def find_digest_clusters(
    candidates: Iterable[Mapping[str, Any]],
    *,
    min_quote_len: int = 20,
    max_quote_len: int = 40,
    min_snippet_len: int = 30,
    max_snippet_len: int = 50,
    min_distinct_families: int = 3,
    max_children: int = 5,
) -> list[DigestCluster]:
    """Return digest-eligible clusters from candidate list.

    Caller adapts rss_fetcher / speech_seed_intake candidate dicts to the
    expected shape (see module docstring). Returns empty list when no cluster
    satisfies all conditions — never None.
    """
    grouped = _group_by_game_player(candidates)
    clusters: list[DigestCluster] = []
    for (game_id, player_id), members in grouped.items():
        cluster = _evaluate_group(
            game_id=game_id,
            player_id=player_id,
            members=members,
            min_quote_len=min_quote_len,
            max_quote_len=max_quote_len,
            min_snippet_len=min_snippet_len,
            max_snippet_len=max_snippet_len,
            min_distinct_families=min_distinct_families,
            max_children=max_children,
        )
        if cluster is not None:
            clusters.append(cluster)
    return clusters


def _evaluate_group(
    *,
    game_id: str,
    player_id: str,
    members: list[Mapping[str, Any]],
    min_quote_len: int,
    max_quote_len: int,
    min_snippet_len: int,
    max_snippet_len: int,
    min_distinct_families: int,
    max_children: int,
) -> Optional[DigestCluster]:
    family_set: set[str] = set()
    for m in members:
        fam = _family_for_candidate(m)
        if fam:
            family_set.add(fam)
    digest_families = family_set & _DIGEST_SOURCE_FAMILIES
    if len(digest_families) < min_distinct_families:
        return None

    parent = _pick_parent(members)
    if parent is None:
        return None
    parent_family = _family_for_candidate(parent)
    if parent_family not in _DIGEST_SOURCE_FAMILIES:
        return None

    quote = _extract_literal_quote(parent, min_quote_len, max_quote_len)
    if not quote:
        return None

    event_token = _extract_event_token(parent)
    if not event_token:
        return None

    player_name = _get_player_name(parent)
    if not player_name:
        return None

    children = _pick_children(
        members=members,
        parent=parent,
        parent_family=parent_family,
        min_snippet_len=min_snippet_len,
        max_snippet_len=max_snippet_len,
        max_children=max_children,
    )
    if len(children) < (min_distinct_families - 1):
        return None

    parent_url = str(parent.get("post_url") or parent.get("source_url") or "").strip()
    officials = _pick_officials(
        members=members,
        parent_url=parent_url,
        min_snippet_len=min_snippet_len,
        max_snippet_len=max_snippet_len,
    )

    return DigestCluster(
        game_id=str(game_id),
        player_id=str(player_id),
        player_name=player_name,
        parent_candidate=dict(parent),
        parent_family=parent_family,
        quote=quote,
        event_token=event_token,
        children=tuple(children),
        officials=tuple(officials),
    )


def _group_by_game_player(
    candidates: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for c in candidates:
        game_id = str(c.get("game_id") or "").strip()
        player_key = _player_group_key(c)
        if not game_id or not player_key:
            continue
        key = (game_id, player_key)
        groups.setdefault(key, []).append(c)
    return groups


def _player_group_key(c: Mapping[str, Any]) -> str:
    """player_id を優先、無ければ player_name fallback。

    rss_fetcher の candidate dict には player_id が常に populate されないので、
    player_name (root or metadata) を normalize して group key にする。
    """
    pid = str(c.get("player_id") or "").strip()
    if pid:
        return pid
    return _get_player_name(c)


def _get_player_name(c: Mapping[str, Any]) -> str:
    """player_name を root または metadata から取得。"""
    direct = str(c.get("player_name") or "").strip()
    if direct:
        return direct
    meta = c.get("metadata")
    if isinstance(meta, Mapping):
        return str(meta.get("player_name") or "").strip()
    return ""


def _family_for_candidate(c: Mapping[str, Any]) -> str:
    fam = str(c.get("source_family") or "").strip()
    if fam:
        return fam
    url = str(c.get("post_url") or c.get("source_url") or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url.lower())
    except ValueError:
        return ""
    host = parsed.netloc
    if not host:
        return ""
    # 1. domain 完全一致 / subdomain 一致 (web 記事 URL)
    for profile in TRUSTED_SOURCE_PROFILES:
        for domain in profile.domains:
            if host == domain or host.endswith("." + domain):
                return profile.family
    # 2. X handle path 一致 (rsshub / twitter / x.com URL)
    #    例: rsshub.../twitter/user/TokyoGiants/... → giants_official
    path_parts = [p for p in parsed.path.split("/") if p]
    for profile in TRUSTED_SOURCE_PROFILES:
        for handle in profile.handles:
            if not handle:
                continue
            if handle.lower() in path_parts:
                return profile.family
    return ""


def _pick_parent(members: list[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    if not members:
        return None
    digest_members = [
        m for m in members
        if _family_for_candidate(m) in _DIGEST_SOURCE_FAMILIES
    ]
    if not digest_members:
        return None

    def sort_key(m: Mapping[str, Any]) -> tuple[int, int, str]:
        body_len = len(str(m.get("body") or m.get("summary") or "").strip())
        family = _family_for_candidate(m)
        trust = -_family_trust_rank(family)
        published_at = str(m.get("published_at") or m.get("published") or "")
        return (-body_len, trust, published_at)

    return sorted(digest_members, key=sort_key)[0]


def _family_trust_rank(family: str) -> int:
    for profile in TRUSTED_SOURCE_PROFILES:
        if profile.family == family:
            return _TRUST_RANK.get(profile.family_trust, 0)
    return 0


def _extract_literal_quote(
    candidate: Mapping[str, Any],
    min_len: int,
    max_len: int,
) -> str:
    body = str(candidate.get("body") or candidate.get("summary") or "")
    title = str(
        candidate.get("source_title") or candidate.get("title") or ""
    )
    for text in (body, title):
        if not text:
            continue
        for m in _QUOTE_RE.finditer(text):
            inner = m.group(1).strip().rstrip("。、")
            if min_len <= len(inner) <= max_len:
                return inner
    return ""


def _extract_event_token(candidate: Mapping[str, Any]) -> str:
    """Return longest literal event token match across title + body.

    longest-match policy: `300号サヨナラホームラン` (long、具体) を
    `サヨナラ` (short、generic) より優先する。1 text 内・複数 text 横断で
    finditer + max を取る。AI / LLM rewrite 一切なし。
    """
    title = str(
        candidate.get("source_title") or candidate.get("title") or ""
    )
    body = str(candidate.get("body") or candidate.get("summary") or "")
    best = ""
    for text in (title, body):
        if not text:
            continue
        for pat in _EVENT_PATTERNS:
            for m in pat.finditer(text):
                token = m.group(1)
                if len(token) > len(best):
                    best = token
    return best


def _pick_children(
    *,
    members: list[Mapping[str, Any]],
    parent: Mapping[str, Any],
    parent_family: str,
    min_snippet_len: int,
    max_snippet_len: int,
    max_children: int,
) -> list[DigestChild]:
    parent_url = str(parent.get("post_url") or parent.get("source_url") or "").strip()
    by_family: dict[str, list[Mapping[str, Any]]] = {}
    for m in members:
        if m is parent:
            continue
        url = str(m.get("post_url") or m.get("source_url") or "").strip()
        if url and url == parent_url:
            continue
        fam = _family_for_candidate(m)
        if not fam or fam == parent_family:
            continue
        if fam not in _DIGEST_SOURCE_FAMILIES:
            continue
        by_family.setdefault(fam, []).append(m)

    children: list[DigestChild] = []
    for fam in sorted(by_family.keys()):
        fam_members = by_family[fam]
        ordered = sorted(
            fam_members,
            key=lambda x: -len(str(x.get("title") or x.get("source_title") or "")),
        )
        for cand in ordered:
            snippet = _extract_short_snippet(
                cand, min_snippet_len, max_snippet_len
            )
            if not snippet:
                continue
            url = str(cand.get("post_url") or cand.get("source_url") or "").strip()
            if not url:
                continue
            label = _FAMILY_LABEL.get(fam, fam)
            children.append(
                DigestChild(family=fam, label=label, snippet=snippet, url=url)
            )
            break
        if len(children) >= max_children:
            break
    return children


def _pick_officials(
    *,
    members: list[Mapping[str, Any]],
    parent_url: str,
    min_snippet_len: int,
    max_snippet_len: int,
    max_officials: int = 4,
) -> list[DigestOfficial]:
    """ヨシラバーらしさ Section B 用、公式 source の post / release を抽出。

    media digest (parent + children) とは別 list。giants_official /
    npb_official の各 family から最大 1 件(同 family 複数あれば最長 title 1 件)、
    計 max_officials 件まで。snippet は media digest と同じ [min, max] literal 制約。
    """
    officials: list[DigestOfficial] = []
    by_family: dict[str, list[Mapping[str, Any]]] = {}
    for m in members:
        url = str(m.get("post_url") or m.get("source_url") or "").strip()
        if url and parent_url and url == parent_url:
            continue
        fam = _family_for_candidate(m)
        if not fam or fam not in _OFFICIAL_FAMILIES:
            continue
        by_family.setdefault(fam, []).append(m)

    for fam in sorted(by_family.keys()):
        fam_members = by_family[fam]
        ordered = sorted(
            fam_members,
            key=lambda x: -len(str(x.get("title") or x.get("source_title") or "")),
        )
        for cand in ordered:
            snippet = _extract_short_snippet(
                cand, min_snippet_len, max_snippet_len
            )
            if not snippet:
                continue
            url = str(cand.get("post_url") or cand.get("source_url") or "").strip()
            if not url:
                continue
            officials.append(
                DigestOfficial(
                    family=fam,
                    label=_official_label(fam, url),
                    snippet=snippet,
                    url=url,
                )
            )
            break
        if len(officials) >= max_officials:
            break
    return officials


def _official_label(family: str, url: str) -> str:
    """公式 source の表示 label を URL host / handle hint から導出。

    優先順:
      1. host が _OFFICIAL_WEB_HOSTS にあれば「巨人公式サイト」「NPB公式」
      2. URL に _OFFICIAL_X_HANDLE_HINTS の key が含まれれば X 系 label
      3. それ以外は family default (「巨人公式」「NPB公式」)
    """
    url_lower = url.lower()
    try:
        host = urlparse(url_lower).netloc
    except ValueError:
        host = ""

    if family == "giants_official":
        if host in {"giants.jp", "www.giants.jp"}:
            return "巨人公式サイト"
        for hint, label in _OFFICIAL_X_HANDLE_HINTS.items():
            if hint in url_lower and "巨人" in label:
                return label
        return "巨人公式"

    if family == "npb_official":
        if host in {"npb.jp", "www.npb.jp", "npb.or.jp", "www.npb.or.jp"}:
            return "NPB公式"
        for hint, label in _OFFICIAL_X_HANDLE_HINTS.items():
            if hint in url_lower and "NPB" in label:
                return label
        return "NPB公式"

    return family


def _extract_short_snippet(
    candidate: Mapping[str, Any],
    min_len: int,
    max_len: int,
) -> str:
    """Literal short snippet [min_len, max_len] chars from title (preferred)
    or body lead. Natural break at 。！？、 when over max_len. No AI rewrite,
    no ellipsis. Returns empty when no literal substring in range exists.
    """
    title = str(
        candidate.get("title") or candidate.get("source_title") or ""
    ).strip()
    snippet = _trim_to_range(title, min_len, max_len)
    if snippet:
        return snippet
    body = str(candidate.get("body") or candidate.get("summary") or "").strip()
    return _trim_to_range(body, min_len, max_len)


def _trim_to_range(text: str, min_len: int, max_len: int) -> str:
    if not text:
        return ""
    if min_len <= len(text) <= max_len:
        return text.rstrip("。、")
    if len(text) <= max_len:
        return ""
    head = text[:max_len]
    for sep in ("。", "！", "？", "、"):
        idx = head.rfind(sep)
        if idx >= min_len - 1:
            return head[: idx + 1].rstrip("。、")
    return ""


__all__ = [
    "DigestChild",
    "DigestCluster",
    "DigestOfficial",
    "find_digest_clusters",
]
