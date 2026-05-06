"""MANUAL-INTAKE-001 pass-1 CLI.

Manually inject a URL / X URL / news URL into the YOSHILOVER pipeline as a WP
draft. The CLI never auto-publishes. Downstream jobs (guarded-publish,
publish-notice, draft-body-editor) pick up the draft via their existing WP
polling and source_url meta.

memo (--memo) is an operator-only note. It is NEVER:
  - written to entry["summary"]
  - injected into source_fact_block
  - included in any Gemini prompt
  - used as a fact source in body content

memo only appears in CLI stdout/stderr JSON output for audit.
Body grounding integrity is preserved.

Usage:
    python -m src.tools.manual_intake <url> [--memo "..."] [--mode draft|dry-run]
        [--title "..."] [--summary "..."]

Default --mode is "draft".
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
_VENDOR = str(ROOT / "vendor")
_SRC = str(ROOT / "src")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


EXIT_OK = 0
EXIT_INVALID_URL = 10
EXIT_FETCH_FAILED = 11
EXIT_MISSING_TITLE_OR_SUMMARY = 12
EXIT_DUPLICATE = 13
EXIT_VALIDATION_FAILED = 14
EXIT_WP_DRAFT_FAILED = 20
EXIT_DOWNSTREAM_HANDOFF_FAILED = 21
EXIT_RATE_LIMITED = 30
EXIT_UNEXPECTED = 2


RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX = 5
DEFAULT_LOCKFILE = ROOT / "logs" / "manual_intake_throttle.json"

_X_HOSTS = {
    "twitter.com",
    "x.com",
    "www.twitter.com",
    "www.x.com",
    "mobile.twitter.com",
    "mobile.x.com",
}

_MIN_TITLE_CHARS = 8

_META_PATTERNS: tuple[tuple[str, str], ...] = (
    (r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', "title"),
    (r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']', "title"),
    (r'<meta\s+name=["\']twitter:title["\']\s+content=["\']([^"\']+)["\']', "title"),
    (r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', "summary"),
    (r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:description["\']', "summary"),
    (r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', "summary"),
    (r'<meta\s+name=["\']twitter:description["\']\s+content=["\']([^"\']+)["\']', "summary"),
)


def _is_valid_url(url: object) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_x_url(url: str) -> bool:
    if not _is_valid_url(url):
        return False
    return (urlparse(url).netloc or "").lower() in _X_HOSTS


def _normalize_x_url_to_twitter(url: str) -> str:
    return re.sub(r"://(www\.|mobile\.)?x\.com/", "://twitter.com/", url)


def _extract_x_status_id(url: str) -> str:
    match = re.search(r"/status(?:es)?/(\d+)", url or "")
    return match.group(1) if match else ""


def _domain_of(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


def _infer_source_name(url: str) -> str:
    domain = _domain_of(url)
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or "manual_intake"


def _check_rate_limit(lockfile: Path = DEFAULT_LOCKFILE) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds)."""
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    history: list[float] = []
    if lockfile.exists():
        try:
            data = json.loads(lockfile.read_text(encoding="utf-8"))
            if isinstance(data, list):
                history = [float(t) for t in data if isinstance(t, (int, float))]
        except Exception:
            history = []
    history = [t for t in history if (now - t) < RATE_LIMIT_WINDOW_SEC]
    if len(history) >= RATE_LIMIT_MAX:
        oldest = min(history)
        retry = int(RATE_LIMIT_WINDOW_SEC - (now - oldest)) + 1
        return False, max(retry, 1)
    history.append(now)
    lockfile.write_text(json.dumps(history), encoding="utf-8")
    return True, 0


def _parse_og_meta(html_text: str) -> dict[str, str]:
    title = ""
    summary = ""
    for pattern, key in _META_PATTERNS:
        if key == "title" and title:
            continue
        if key == "summary" and summary:
            continue
        match = re.search(pattern, html_text, re.IGNORECASE)
        if match:
            value = html.unescape(match.group(1).strip())
            if key == "title":
                title = value
            elif key == "summary":
                summary = value
    if not title:
        match = re.search(r"<title>([^<]+)</title>", html_text, re.IGNORECASE)
        if match:
            title = html.unescape(match.group(1).strip())
    return {"title": title, "summary": summary}


def _fetch_news_meta(url: str, *, timeout: float = 10.0) -> dict[str, str]:
    try:
        import urllib.request
    except Exception as exc:
        return {"_error": f"urllib_unavailable:{exc}"}
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; yoshilover-manual-intake/1)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read(800_000)
    except Exception as exc:
        return {"_error": f"fetch_failed:{exc.__class__.__name__}"}
    text = content.decode("utf-8", errors="replace")
    return _parse_og_meta(text)


def _build_body_for_x(canonical_url: str) -> str:
    safe = html.escape(canonical_url)
    return (
        f'<blockquote class="twitter-tweet" data-lang="ja">'
        f'<a href="{safe}"></a></blockquote>\n'
        '<script async src="https://platform.twitter.com/widgets.js" '
        'charset="utf-8"></script>\n'
    )


def _build_body_for_news(source_url: str, title: str, summary: str) -> str:
    parts: list[str] = []
    if summary:
        parts.append(f"<p>{html.escape(summary)}</p>")
    label = title or source_url
    parts.append(
        f'<p>出典: <a href="{html.escape(source_url)}" target="_blank" '
        f'rel="noopener">{html.escape(label)}</a></p>'
    )
    return "\n".join(parts)


def _title_quality_failure_reason(title: str) -> str:
    if not title:
        return "title_empty"
    if len(title.strip()) < _MIN_TITLE_CHARS:
        return "title_too_short"
    return ""


def _normalize_title_for_dedupe(title: str) -> str:
    return re.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", (title or "")).lower()


def _is_history_duplicate_local(
    history: dict, *, source_url: str, entry_title_norm: str
) -> bool:
    if source_url and source_url in history:
        return True
    if entry_title_norm and len(entry_title_norm) > 5:
        if f"title:{entry_title_norm[:60]}" in history:
            return True
    return False


def _resolve_routing_lightweight(
    *,
    title: str,
    summary: str,
    source_url: str,
    source_kind: str,
    logger: logging.Logger,
) -> tuple[str, str]:
    """Best-effort category + subtype. Falls back to safe defaults."""
    text = f"{title} {summary}"
    try:
        from rss_fetcher import classify_category as _classify
        from rss_fetcher import _detect_article_subtype as _detect_subtype
    except Exception:
        return "選手情報", source_kind

    keywords: dict[str, Any] = {}
    keywords_path = ROOT / "config" / "keywords.json"
    try:
        if keywords_path.exists():
            keywords = json.loads(keywords_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("keywords_load_failed: %s", exc)

    try:
        category = _classify(text, keywords, source_url, logger) or "選手情報"
    except Exception as exc:
        logger.warning("classify_category_failed: %s", exc)
        category = "選手情報"
    try:
        subtype = _detect_subtype(title, summary, category, False) or source_kind
    except Exception as exc:
        logger.warning("detect_subtype_failed: %s", exc)
        subtype = source_kind
    return category, subtype


def _safe_load_history(logger: logging.Logger) -> dict:
    try:
        from rss_fetcher import load_history
        return load_history() or {}
    except Exception as exc:
        logger.warning("load_history_failed: %s", exc)
        return {}


def _wp_create_draft(
    wp,
    *,
    title: str,
    content: str,
    category: str,
    source_url: str,
    logger: logging.Logger,
) -> tuple[int | None, str | None]:
    """Create a draft via WPClient. WPClient has its own dedupe via
    find_recent_post_by_title + source_url. Returns (post_id, draft_url).
    Caller name 'manual_intake' is recorded for audit."""
    categories = [category] if category else None
    result = wp.create_post(
        title=title,
        content=content,
        categories=categories,
        status="draft",
        source_url=source_url,
        caller="manual_intake",
        source_lane="manual_intake",
    )
    post_id: int | None
    draft_url: str | None = None
    if isinstance(result, dict):
        post_id = result.get("id")
        draft_url = result.get("link")
    elif isinstance(result, int):
        post_id = result
    else:
        post_id = None
    if not post_id:
        raise RuntimeError("wp_create_post_returned_no_id")
    return post_id, draft_url


def run_manual_intake(
    *,
    url: str,
    memo: str = "",
    mode: str = "draft",
    title_override: str = "",
    summary_override: str = "",
    wp_client_factory: Callable[[], Any] | None = None,
    rate_limit_lockfile: Path | None = None,
    fetch_meta: Callable[..., dict[str, str]] = _fetch_news_meta,
    logger: logging.Logger | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run the manual intake pipeline.

    Returns (exit_code, output_dict). memo NEVER reaches body / source_text /
    Gemini prompt — it lives only in the output dict for operator audit.
    """
    logger = logger or logging.getLogger("manual_intake")
    output: dict[str, Any] = {
        "ok": False,
        "mode": mode,
        "url": url,
        "source_url": "",
        "source_kind": "",
        "title": "",
        "category": "",
        "subtype": "",
        "template_key": "manual_intake",
        "status_id": "",
        "duplicate": False,
        "validation_ok": False,
        "reason": "",
        "skip_reason": "",
        "post_id": None,
        "draft_url": None,
    }

    if not _is_valid_url(url):
        output["reason"] = "invalid_url"
        return EXIT_INVALID_URL, output

    lockfile = rate_limit_lockfile or DEFAULT_LOCKFILE
    allowed, retry_after = _check_rate_limit(lockfile)
    if not allowed:
        output["reason"] = "rate_limited"
        output["retry_after_sec"] = retry_after
        return EXIT_RATE_LIMITED, output

    is_x = _is_x_url(url)
    source_kind = "x" if is_x else "news"
    output["source_kind"] = source_kind
    canonical_source_url = _normalize_x_url_to_twitter(url) if is_x else url
    output["source_url"] = canonical_source_url

    if is_x:
        status_id = _extract_x_status_id(url)
        output["status_id"] = status_id
        if not status_id:
            output["reason"] = "x_url_status_id_not_found"
            return EXIT_INVALID_URL, output

    title = (title_override or "").strip()
    summary = (summary_override or "").strip()

    if is_x:
        if not title and not summary:
            output["reason"] = "missing_title_or_summary"
            return EXIT_MISSING_TITLE_OR_SUMMARY, output
        if not title and summary:
            title = summary[:60]
    else:
        if not (title and summary):
            meta = fetch_meta(url)
            if "_error" in meta and not (title or summary):
                output["reason"] = f"fetch_failed:{meta.get('_error')}"
                return EXIT_FETCH_FAILED, output
            if not title:
                title = (meta.get("title", "") or "").strip()
            if not summary:
                summary = (meta.get("summary", "") or "").strip()
        if not title or not summary:
            output["reason"] = "missing_title_or_summary"
            return EXIT_MISSING_TITLE_OR_SUMMARY, output

    output["title"] = title

    title_fail = _title_quality_failure_reason(title)
    if title_fail:
        output["skip_reason"] = title_fail
        output["reason"] = "validation_failed"
        return EXIT_VALIDATION_FAILED, output

    category, subtype = _resolve_routing_lightweight(
        title=title,
        summary=summary,
        source_url=canonical_source_url,
        source_kind=source_kind,
        logger=logger,
    )
    output["category"] = category
    output["subtype"] = subtype

    entry_title_norm = _normalize_title_for_dedupe(title)
    history = _safe_load_history(logger)
    if _is_history_duplicate_local(
        history,
        source_url=canonical_source_url,
        entry_title_norm=entry_title_norm,
    ):
        output["duplicate"] = True
        output["reason"] = "history_duplicate"
        return EXIT_DUPLICATE, output

    output["validation_ok"] = True
    output["source_name"] = _infer_source_name(url)

    if mode == "dry-run":
        output["ok"] = True
        return EXIT_OK, output

    if wp_client_factory is None:
        output["reason"] = "wp_client_factory_not_provided"
        return EXIT_WP_DRAFT_FAILED, output

    if is_x:
        body = _build_body_for_x(canonical_source_url)
    else:
        body = _build_body_for_news(canonical_source_url, title, summary)

    if memo:
        if memo in body:
            raise AssertionError("memo must not appear in WP draft body")
        if memo in title:
            raise AssertionError("memo must not appear in WP draft title")

    try:
        wp = wp_client_factory()
        post_id, draft_url = _wp_create_draft(
            wp,
            title=title,
            content=body,
            category=category,
            source_url=canonical_source_url,
            logger=logger,
        )
    except AssertionError:
        raise
    except Exception as exc:
        output["reason"] = f"wp_draft_failed:{exc.__class__.__name__}"
        logger.error("wp_draft_create_failed: %s", exc)
        return EXIT_WP_DRAFT_FAILED, output

    output["post_id"] = post_id
    output["draft_url"] = draft_url
    output["ok"] = True
    output["downstream_handoff"] = "guarded_publish_polling"
    if memo:
        output["memo"] = memo
    return EXIT_OK, output


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.manual_intake",
        description=(
            "Manually intake a URL/X URL/news URL into the YOSHILOVER WP draft "
            "pipeline. Default --mode 'draft'. Memo is operator-only; it never "
            "reaches body / source_text / Gemini prompt."
        ),
    )
    p.add_argument("url", help="target URL (news article or X status URL)")
    p.add_argument(
        "--memo",
        default="",
        help="operator memo (NOT injected into body / source_text / Gemini prompt)",
    )
    p.add_argument(
        "--mode",
        choices=("draft", "dry-run"),
        default="draft",
        help="default 'draft'; 'dry-run' skips WP write",
    )
    p.add_argument("--title", default="", help="override fetched title")
    p.add_argument("--summary", default="", help="override fetched summary")
    return p


def _default_wp_client_factory():
    from wp_client import WPClient
    return WPClient()


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("manual_intake")

    try:
        exit_code, output = run_manual_intake(
            url=args.url,
            memo=args.memo,
            mode=args.mode,
            title_override=args.title,
            summary_override=args.summary,
            wp_client_factory=_default_wp_client_factory,
            logger=logger,
        )
    except SystemExit:
        raise
    except Exception as exc:
        logger.exception("manual_intake_unexpected_error")
        print(
            json.dumps(
                {"ok": False, "reason": f"unexpected:{exc.__class__.__name__}"},
                ensure_ascii=False,
            )
        )
        return EXIT_UNEXPECTED

    print(json.dumps(output, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
