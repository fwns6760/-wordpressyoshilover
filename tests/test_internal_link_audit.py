from __future__ import annotations

from src.tools.internal_link_audit import (
    PageResult,
    build_audit_report,
    collect_linked_targets,
    normalize_url,
    parse_html_page,
)


def test_normalize_url_unifies_host_fragment_and_trailing_slash() -> None:
    assert (
        normalize_url("http://www.yoshilover.com/data/sakamoto-hayato/#stats")
        == "https://yoshilover.com/data/sakamoto-hayato"
    )


def test_parse_html_page_keeps_internal_links_and_anchor_context() -> None:
    page = parse_html_page(
        """
        <html><head>
          <link rel="canonical" href="/data/sakamoto-hayato/">
          <meta name="robots" content="index,follow">
        </head><body>
          <a href="/data/draft/?year=2026">ドラフト一覧</a>
          <a href="https://example.com/">外部</a>
        </body></html>
        """,
        requested_url="https://yoshilover.com/data/sakamoto-hayato/",
        final_url="https://yoshilover.com/data/sakamoto-hayato/",
        status_code=200,
    )
    assert page.canonical == "https://yoshilover.com/data/sakamoto-hayato"
    assert page.internal_links == ["https://yoshilover.com/data/draft?year=2026"]
    assert page.anchors[0]["text"] == "ドラフト一覧"


def test_report_finds_orphan_query_link_and_broken_page() -> None:
    pages = [
        PageResult(
            requested_url="https://yoshilover.com",
            final_url="https://yoshilover.com",
            status_code=200,
            internal_links=[
                "https://yoshilover.com/data",
                "https://yoshilover.com/data?year=2026",
            ],
            anchors=[
                {
                    "url": "https://yoshilover.com/data",
                    "href": "/data/",
                    "text": "詳しくはこちら",
                    "rel": "",
                }
            ],
        ),
        PageResult(
            requested_url="https://yoshilover.com/data",
            final_url="https://yoshilover.com/data",
            status_code=200,
        ),
        PageResult(
            requested_url="https://yoshilover.com/data/orphan",
            final_url="https://yoshilover.com/data/orphan",
            status_code=200,
        ),
        PageResult(
            requested_url="https://yoshilover.com/data/broken",
            final_url="https://yoshilover.com/data/broken",
            status_code=404,
        ),
    ]
    urls = [page.requested_url for page in pages]
    report = build_audit_report(pages, sitemap_urls=urls)
    assert report["summary"]["orphan_pages"] == 1
    assert report["orphan_pages"] == ["https://yoshilover.com/data/orphan"]
    assert report["summary"]["query_link_targets"] == 1
    assert report["summary"]["generic_anchor_targets"] == 1
    assert report["summary"]["fetch_errors_or_4xx_5xx"] == 1


def test_collect_linked_targets_prioritizes_repeated_non_sitemap_url() -> None:
    pages = [
        PageResult(
            requested_url="https://yoshilover.com",
            internal_links=[
                "https://yoshilover.com/data",
                "https://yoshilover.com/?page_id=1980",
            ],
        ),
        PageResult(
            requested_url="https://yoshilover.com/data",
            internal_links=["https://yoshilover.com/?page_id=1980"],
        ),
    ]
    assert collect_linked_targets(
        pages,
        sitemap_urls=["https://yoshilover.com", "https://yoshilover.com/data"],
        limit=1,
    ) == ["https://yoshilover.com/?page_id=1980"]
