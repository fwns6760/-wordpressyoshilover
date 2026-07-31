"""Yoshilover の sitemap 全体を対象に内部リンク構造を監査する。

WP や GCP へ書き込まない read-only tool。sitemap URL を再帰的に収集して、
孤立ページ、到達不能ページ、リンク切れ、redirect、query 付き内部リンク、
弱い anchor text を JSON へ出力する。

usage:
    python3 -m src.tools.internal_link_audit \
      --output out/internal-link-audit.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LOG = logging.getLogger("internal_link_audit")
DEFAULT_BASE_URL = "https://yoshilover.com"
DEFAULT_SITEMAPS = (
    f"{DEFAULT_BASE_URL}/sitemap.xml",
    f"{DEFAULT_BASE_URL}/data-sitemap.xml",
)
USER_AGENT = "YoshiloverInternalLinkAudit/1.0 (+https://yoshilover.com/)"
GENERIC_ANCHORS = {
    "",
    "こちら",
    "ここ",
    "詳しくはこちら",
    "続きを読む",
    "もっと見る",
    "記事を読む",
    "詳細",
    "link",
    "read more",
}
_SPACE_RE = re.compile(r"\s+")
_PERCENT_ESCAPE_RE = re.compile(r"%[0-9a-fA-F]{2}")


def normalize_url(url: str, *, base_url: str = DEFAULT_BASE_URL) -> str:
    """内部リンク graph で比較できる canonical URL 形式へ正規化する。"""
    absolute = urljoin(base_url.rstrip("/") + "/", (url or "").strip())
    parts = urlsplit(absolute)
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    if scheme not in {"http", "https"} or not host:
        return ""
    if host in {"www.yoshilover.com", "yoshilover.com"}:
        scheme = "https"
        host = "yoshilover.com"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    path = _PERCENT_ESCAPE_RE.sub(lambda match: match.group(0).upper(), path)
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, parts.query, ""))


def is_internal_url(url: str, *, base_url: str = DEFAULT_BASE_URL) -> bool:
    normalized = normalize_url(url, base_url=base_url)
    return bool(normalized) and urlsplit(normalized).netloc == urlsplit(
        normalize_url(base_url, base_url=base_url)
    ).netloc


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical = ""
        self.robots: list[str] = []
        self.anchors: list[dict[str, str]] = []
        self._anchor_href = ""
        self._anchor_rel = ""
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonical = values.get("href", "")
        elif tag == "meta" and values.get("name", "").lower() == "robots":
            self.robots.append(values.get("content", "").lower())
        elif tag == "a":
            self._anchor_href = values.get("href", "")
            self._anchor_rel = values.get("rel", "").lower()
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._anchor_href:
            return
        self.anchors.append(
            {
                "href": self._anchor_href,
                "text": _SPACE_RE.sub(" ", "".join(self._anchor_text)).strip(),
                "rel": self._anchor_rel,
            }
        )
        self._anchor_href = ""
        self._anchor_rel = ""
        self._anchor_text = []


@dataclass
class PageResult:
    requested_url: str
    final_url: str = ""
    status_code: int = 0
    canonical: str = ""
    noindex: bool = False
    internal_links: list[str] = field(default_factory=list)
    anchors: list[dict[str, str]] = field(default_factory=list)
    error: str = ""


def parse_html_page(
    html: str,
    *,
    requested_url: str,
    final_url: str,
    status_code: int,
    base_url: str = DEFAULT_BASE_URL,
) -> PageResult:
    parser = _PageParser()
    parser.feed(html or "")
    anchors: list[dict[str, str]] = []
    links: list[str] = []
    for anchor in parser.anchors:
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        normalized = normalize_url(href, base_url=final_url or requested_url)
        if not is_internal_url(normalized, base_url=base_url):
            continue
        anchors.append({**anchor, "url": normalized})
        links.append(normalized)
    robots = ",".join(parser.robots)
    return PageResult(
        requested_url=normalize_url(requested_url, base_url=base_url),
        final_url=normalize_url(final_url, base_url=base_url),
        status_code=status_code,
        canonical=normalize_url(parser.canonical, base_url=final_url or requested_url)
        if parser.canonical
        else "",
        noindex="noindex" in robots,
        internal_links=sorted(set(links)),
        anchors=anchors,
    )


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            # brotli 非対応環境で br body を誤 decode しないよう限定する。
            "Accept-Encoding": "gzip, deflate",
        }
    )
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def collect_sitemap_urls(
    sitemap_urls: Iterable[str],
    *,
    timeout: float = 20,
    max_pages: int = 0,
) -> tuple[list[str], list[str]]:
    """sitemap index を再帰処理し、page URL と取得エラーを返す。"""
    pending = deque(normalize_url(url) for url in sitemap_urls)
    seen_sitemaps: set[str] = set()
    pages: list[str] = []
    page_seen: set[str] = set()
    errors: list[str] = []
    session = _session()

    while pending:
        sitemap_url = pending.popleft()
        if not sitemap_url or sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = session.get(sitemap_url, timeout=timeout)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sitemap_url}: {type(exc).__name__}: {exc}")
            continue

        local_name = root.tag.rsplit("}", 1)[-1].lower()
        locations = [
            (element.text or "").strip()
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].lower() == "loc"
        ]
        if local_name == "sitemapindex":
            for location in locations:
                normalized = normalize_url(location)
                if normalized and normalized not in seen_sitemaps:
                    pending.append(normalized)
            continue

        for location in locations:
            normalized = normalize_url(location)
            if not normalized or normalized in page_seen:
                continue
            page_seen.add(normalized)
            pages.append(normalized)
            if max_pages and len(pages) >= max_pages:
                return pages, errors
    return pages, errors


def _fetch_page(url: str, *, timeout: float, base_url: str) -> PageResult:
    try:
        response = _session().get(url, timeout=timeout, allow_redirects=True)
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type:
            return PageResult(
                requested_url=normalize_url(url, base_url=base_url),
                final_url=normalize_url(response.url, base_url=base_url),
                status_code=response.status_code,
            )
        return parse_html_page(
            response.text,
            requested_url=url,
            final_url=response.url,
            status_code=response.status_code,
            base_url=base_url,
        )
    except Exception as exc:  # noqa: BLE001
        return PageResult(
            requested_url=normalize_url(url, base_url=base_url),
            error=f"{type(exc).__name__}: {exc}",
        )


def crawl_pages(
    urls: Iterable[str],
    *,
    base_url: str = DEFAULT_BASE_URL,
    workers: int = 4,
    timeout: float = 20,
) -> list[PageResult]:
    page_urls = list(dict.fromkeys(urls))
    results: list[PageResult] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(_fetch_page, url, timeout=timeout, base_url=base_url): url
            for url in page_urls
        }
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 100 == 0:
                LOG.info("crawled %d/%d pages", index, len(page_urls))
    return sorted(results, key=lambda result: result.requested_url)


def collect_linked_targets(
    pages: Iterable[PageResult],
    *,
    sitemap_urls: Iterable[str],
    limit: int = 500,
) -> list[str]:
    """sitemap 外だが内部リンクされる URL を、出現回数順で検査対象にする。"""
    sitemap_set = {normalize_url(url) for url in sitemap_urls}
    targets: Counter[str] = Counter(
        target
        for page in pages
        for target in page.internal_links
        if target not in sitemap_set
    )
    if limit <= 0:
        return []
    return [url for url, _count in targets.most_common(limit)]


def build_audit_report(
    pages: Iterable[PageResult],
    *,
    sitemap_urls: Iterable[str],
    root_url: str = DEFAULT_BASE_URL,
) -> dict:
    page_list = list(pages)
    sitemap_set = {
        normalize_url(url, base_url=root_url).split("?", 1)[0] for url in sitemap_urls
    }
    results_by_url = {
        normalize_url(page.requested_url, base_url=root_url): page for page in page_list
    }
    sitemap_page_list = [
        page
        for page in page_list
        if normalize_url(page.requested_url, base_url=root_url) in sitemap_set
    ]
    inbound: Counter[str] = Counter()
    sources: dict[str, set[str]] = defaultdict(set)
    query_links: Counter[str] = Counter()
    generic_anchors: Counter[str] = Counter()
    linked_targets: Counter[str] = Counter()

    for page in page_list:
        requested = normalize_url(page.requested_url, base_url=root_url)
        source = requested.split("?", 1)[0]
        if requested not in sitemap_set:
            continue
        for target in page.internal_links:
            target_without_query = target.split("?", 1)[0]
            linked_targets[target_without_query] += 1
            if "?" in target:
                query_links[target] += 1
            if target_without_query in sitemap_set and target_without_query != source:
                inbound[target_without_query] += 1
                sources[target_without_query].add(source)
        for anchor in page.anchors:
            text = _SPACE_RE.sub(" ", anchor.get("text", "")).strip().lower()
            if text in GENERIC_ANCHORS:
                generic_anchors[anchor.get("url", "")] += 1

    eligible = sorted(
        url
        for url in sitemap_set
        if url in results_by_url
        and not results_by_url[url].noindex
        and 200 <= results_by_url[url].status_code < 300
    )
    root = normalize_url(root_url, base_url=root_url).split("?", 1)[0]
    orphans = [url for url in eligible if url != root and inbound[url] == 0]
    near_orphans = [url for url in eligible if url != root and inbound[url] <= 1]

    adjacency: dict[str, set[str]] = defaultdict(set)
    for page in page_list:
        source = normalize_url(page.requested_url, base_url=root_url).split("?", 1)[0]
        if source not in sitemap_set:
            continue
        for target in page.internal_links:
            target = target.split("?", 1)[0]
            if target in sitemap_set and target != source:
                adjacency[source].add(target)
    depth: dict[str, int] = {}
    if root in sitemap_set:
        depth[root] = 0
        queue = deque([root])
        while queue:
            source = queue.popleft()
            for target in adjacency[source]:
                if target not in depth:
                    depth[target] = depth[source] + 1
                    queue.append(target)
    unreachable = sorted(url for url in eligible if url not in depth)

    broken = [
        asdict(page)
        for page in page_list
        if page.error or page.status_code == 0 or page.status_code >= 400
    ]
    broken_sitemap = [
        page
        for page in broken
        if normalize_url(page["requested_url"], base_url=root_url) in sitemap_set
    ]
    broken_linked_targets = [
        page
        for page in broken
        if normalize_url(page["requested_url"], base_url=root_url) not in sitemap_set
    ]
    redirects = [
        {
            "requested_url": page.requested_url,
            "final_url": page.final_url,
            "status_code": page.status_code,
        }
        for page in page_list
        if page.final_url
        and page.requested_url.split("?", 1)[0] != page.final_url.split("?", 1)[0]
    ]
    canonical_mismatches = [
        {
            "url": page.requested_url,
            "canonical": page.canonical,
        }
        for page in page_list
        if page.canonical
        and page.requested_url.split("?", 1)[0] != page.canonical.split("?", 1)[0]
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_url": root,
        "summary": {
            "sitemap_urls": len(sitemap_set),
            "pages_fetched": sum(
                normalize_url(page.requested_url, base_url=root_url) in sitemap_set
                for page in page_list
            ),
            "linked_targets_checked": sum(
                normalize_url(page.requested_url, base_url=root_url) not in sitemap_set
                for page in page_list
            ),
            "fetch_errors_or_4xx_5xx": len(broken),
            "broken_sitemap_pages": len(broken_sitemap),
            "broken_linked_targets": len(broken_linked_targets),
            "redirects": len(redirects),
            "canonical_mismatches": len(canonical_mismatches),
            "noindex_pages": sum(page.noindex for page in sitemap_page_list),
            "orphan_pages": len(orphans),
            "near_orphan_pages": len(near_orphans),
            "unreachable_from_home": len(unreachable),
            "internal_targets_seen": len(linked_targets),
            "query_link_targets": len(query_links),
            "generic_anchor_targets": len(generic_anchors),
            "max_click_depth": max(depth.values(), default=0),
        },
        "orphan_pages": orphans,
        "near_orphan_pages": [
            {
                "url": url,
                "inbound_count": inbound[url],
                "sources": sorted(sources[url]),
            }
            for url in near_orphans
        ],
        "unreachable_from_home": unreachable,
        "broken_pages": broken,
        "broken_sitemap_pages": broken_sitemap,
        "broken_linked_targets": broken_linked_targets,
        "redirects": redirects,
        "canonical_mismatches": canonical_mismatches,
        "query_links": [
            {"url": url, "count": count} for url, count in query_links.most_common()
        ],
        "generic_anchors": [
            {"url": url, "count": count} for url, count in generic_anchors.most_common()
        ],
        "top_linked_targets": [
            {"url": url, "count": count} for url, count in linked_targets.most_common(100)
        ],
        "click_depth": depth,
        "pages": [asdict(page) for page in page_list],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--sitemap", action="append", dest="sitemaps")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument(
        "--linked-target-limit",
        type=int,
        default=500,
        help="sitemap 外の内部リンク先を出現回数順に追加検査する上限",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sitemaps = args.sitemaps or list(DEFAULT_SITEMAPS)
    urls, sitemap_errors = collect_sitemap_urls(
        sitemaps,
        timeout=args.timeout,
        max_pages=max(0, args.max_pages),
    )
    root_url = normalize_url(args.base_url)
    if root_url and root_url not in urls:
        urls.insert(0, root_url)
    LOG.info("collected %d unique page URLs", len(urls))
    pages = crawl_pages(
        urls,
        base_url=args.base_url,
        workers=args.workers,
        timeout=args.timeout,
    )
    linked_targets = collect_linked_targets(
        pages,
        sitemap_urls=urls,
        limit=max(0, args.linked_target_limit),
    )
    if linked_targets:
        LOG.info("checking %d internal targets outside sitemap", len(linked_targets))
        pages.extend(
            crawl_pages(
                linked_targets,
                base_url=args.base_url,
                workers=args.workers,
                timeout=args.timeout,
            )
        )
    report = build_audit_report(pages, sitemap_urls=urls, root_url=args.base_url)
    report["sitemap_errors"] = sitemap_errors
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report: {output.resolve()}")
    return 1 if sitemap_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
