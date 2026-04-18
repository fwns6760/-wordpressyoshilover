"""
draft_inventory_from_logs.py -- Cloud Logging 由来の post_id 候補から現在の draft 在庫を棚卸しする

使用例:
    python3 -m src.draft_inventory_from_logs --days 7
    python3 -m src.draft_inventory_from_logs --days 7 --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).parent.parent
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from draft_audit import audit_post, load_source_catalog
from wp_client import WPClient

POST_ID_RE = re.compile(r"post_id=(\d+)")
DEFAULT_SERVICE = "yoshilover-fetcher"
DEFAULT_PROJECT = "baseballsite"


def _build_logging_query(service_name: str, days: int) -> str:
    return (
        'resource.type="cloud_run_revision" '
        f'AND resource.labels.service_name="{service_name}" '
        'AND ('
        'textPayload:"[WP] 記事draft post_id=" OR '
        'textPayload:"[WP] 下書き作成 post_id=" OR '
        'textPayload:"[WP] 既存記事を再利用 post_id="'
        ')'
    )


def _run_logging_read(*, query: str, project_id: str, limit: int, days: int) -> list[dict[str, Any]]:
    cmd = [
        "gcloud",
        "logging",
        "read",
        query,
        f"--project={project_id}",
        f"--limit={max(limit, 1)}",
        f"--freshness={max(days, 1)}d",
        "--format=json",
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(completed.stdout or "[]")


def extract_candidate_post_ids(entries: Iterable[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    seen = set()
    for entry in entries:
        payload = entry.get("textPayload") or entry.get("jsonPayload", {})
        if isinstance(payload, dict):
            payload = json.dumps(payload, ensure_ascii=False)
        for raw in POST_ID_RE.findall(str(payload)):
            post_id = int(raw)
            if post_id in seen:
                continue
            seen.add(post_id)
            ids.append(post_id)
    return ids


def collect_candidate_post_ids(
    *,
    project_id: str = DEFAULT_PROJECT,
    service_name: str = DEFAULT_SERVICE,
    days: int = 7,
    limit: int = 500,
    reader=None,
) -> list[int]:
    query = _build_logging_query(service_name, days)
    entries = (reader or _run_logging_read)(query=query, project_id=project_id, limit=limit, days=days)
    return extract_candidate_post_ids(entries)


def audit_current_drafts(post_ids: Iterable[int], wp: WPClient | None = None) -> list[dict[str, Any]]:
    wp_client = wp or WPClient()
    categories = wp_client.get_categories()
    category_map = {int(row["id"]): row["name"] for row in categories}
    source_catalog = load_source_catalog()
    audited: list[dict[str, Any]] = []

    for post_id in post_ids:
        try:
            post = wp_client.get_post(int(post_id))
        except Exception:
            continue
        if (post.get("status") or "").lower() != "draft":
            continue
        audited.append(audit_post(post, category_map, source_catalog, wp_client.base_url))

    audited.sort(key=lambda row: (row.get("modified") or "", row.get("id") or 0), reverse=True)
    return audited


def summarize_inventory(audited_posts: list[dict[str, Any]]) -> dict[str, Any]:
    subtype_counts = Counter(post["article_subtype"] for post in audited_posts)
    category_subtype_counts = Counter(f"{post['primary_category']}/{post['article_subtype']}" for post in audited_posts)
    return {
        "total_drafts": len(audited_posts),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "category_subtype_counts": dict(sorted(category_subtype_counts.items())),
        "post_ids": [post["id"] for post in audited_posts],
    }


def _render_text(summary: dict[str, Any], audited_posts: list[dict[str, Any]]) -> str:
    lines = [
        f"total_drafts: {summary['total_drafts']}",
        "",
        "[subtype_counts]",
    ]
    for subtype, count in summary["subtype_counts"].items():
        lines.append(f"{subtype}: {count}")
    lines.extend(["", "[posts]"])
    for post in audited_posts:
        lines.append(
            f"{post['id']} | {post['modified']} | {post['primary_category']}/{post['article_subtype']} | {post['title']}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cloud Logging 由来の post_id 候補から現在の draft 在庫を棚卸しする")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="GCP project id")
    parser.add_argument("--service", default=DEFAULT_SERVICE, help="Cloud Run service name")
    parser.add_argument("--days", type=int, default=7, help="候補 post_id を拾う日数")
    parser.add_argument("--limit", type=int, default=500, help="logging read の取得件数上限")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    args = parser.parse_args()

    candidate_ids = collect_candidate_post_ids(
        project_id=args.project,
        service_name=args.service,
        days=args.days,
        limit=args.limit,
    )
    audited_posts = audit_current_drafts(candidate_ids)
    summary = summarize_inventory(audited_posts)

    if args.json:
        print(json.dumps({"summary": summary, "posts": audited_posts}, ensure_ascii=False, indent=2))
        return

    print(_render_text(summary, audited_posts))


if __name__ == "__main__":
    main()
