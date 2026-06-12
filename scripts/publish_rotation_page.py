#!/usr/bin/env python3
"""/data/rotation/ ページ1枚だけを WP REST 経由で直接 upsert する one-off。

publisher 本体 (現在 別作業の WIP だらけ) を丸ごと動かさず、また Cloud Run を
再デプロイせずに、先発ローテ一覧ページだけを安全に公開/更新する。
認証は .env (WP_URL / WP_USER / WP_APP_PASSWORD) を dotenv で読む。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values  # noqa: E402

import requests  # noqa: E402
from requests.auth import HTTPBasicAuth  # noqa: E402

from src.data_site_template_rotation import (  # noqa: E402
    load_rotation_data,
    render_rotation_excerpt,
    render_rotation_html,
    render_rotation_title,
)

SLUG = "rotation"


def _creds() -> tuple[str, HTTPBasicAuth]:
    env = dotenv_values(ROOT / ".env")
    base = (env.get("WP_URL") or "").strip().rstrip("/")
    user = (env.get("WP_USER") or "").strip()
    pw = (env.get("WP_APP_PASSWORD") or "").strip()
    if not (base and user and pw):
        raise SystemExit("WP_URL / WP_USER / WP_APP_PASSWORD missing in .env")
    return base, HTTPBasicAuth(user, pw)


def _find_page_id(base: str, auth: HTTPBasicAuth, slug: str, parent: int = 0) -> int:
    r = requests.get(
        base + "/wp-json/wp/v2/pages",
        params={"slug": slug, "status": "any", "context": "edit",
                "per_page": 10, "_fields": "id,slug,parent,status"},
        auth=auth, timeout=20,
    )
    r.raise_for_status()
    for p in (r.json() or []):
        if str(p.get("slug", "")) == slug:
            if parent and int(p.get("parent") or 0) != parent:
                continue
            return int(p.get("id") or 0)
    return 0


def main(dry: bool) -> int:
    base, auth = _creds()
    data = load_rotation_data()
    years = data.get("years") or []
    if not years:
        raise SystemExit("rotation data empty; run scripts/scrape_starter_rotation.py first")

    cluster_id = _find_page_id(base, auth, "data", parent=0)
    print(f"cluster /data/ page_id={cluster_id}")

    title = render_rotation_title()
    content = render_rotation_html(data)
    excerpt = render_rotation_excerpt(data)
    print(f"render: years={len(years)} title={title!r} content_bytes={len(content)}")

    if dry:
        print("DRY RUN — not writing to WP.")
        return 0

    payload = {
        "slug": SLUG, "title": title, "content": content,
        "status": "publish", "parent": cluster_id, "excerpt": excerpt,
    }
    existing = _find_page_id(base, auth, SLUG, parent=cluster_id)
    if existing:
        url = base + f"/wp-json/wp/v2/pages/{existing}"
        action = "updated"
    else:
        url = base + "/wp-json/wp/v2/pages"
        action = "created"
    r = requests.post(url, json=payload, auth=auth, timeout=60)
    if not r.ok:
        print(f"upsert FAILED status={r.status_code} body={r.text[:400]}")
        return 1
    page = r.json() or {}
    print(f"{action} page_id={page.get('id')} status={page.get('status')} link={page.get('link')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(dry="--dry" in sys.argv))
