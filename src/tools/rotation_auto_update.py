"""先発ローテ一覧ページの毎朝自動更新 (Cloud Run Job entrypoint)。

流れ (LLM/Gemini 不使用・軽量):
1. image に焼かれた config/starter_rotation_2007_2026.json (履歴) を読む
2. 当年 (datetime.now().year) だけ my-favorite-giants から再取得
3. 当年エントリを差し替え (履歴は不変なので触らない)
4. /data/rotation/ ページを再 render → WP REST で publish 更新

認証: 環境変数 WP_URL / WP_USER / WP_APP_PASSWORD (Cloud Run は Secret Manager 注入)。
ローカル実行時は .env を fallback で読む。

publisher 本体 (別作業の WIP) には一切依存しない。他のデータページにも触らない。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.starter_rotation_scraper import scrape_year, upsert_year  # noqa: E402
from src.data_site_template_rotation import (  # noqa: E402
    render_rotation_excerpt,
    render_rotation_html,
    render_rotation_title,
)

DATA_PATH = ROOT / "config" / "starter_rotation_2007_2026.json"
SLUG = "rotation"


def _creds() -> tuple[str, HTTPBasicAuth]:
    base = (os.environ.get("WP_URL") or "").strip().rstrip("/")
    user = (os.environ.get("WP_USER") or "").strip()
    pw = (os.environ.get("WP_APP_PASSWORD") or "").strip()
    if not (base and user and pw):
        # local fallback
        try:
            from dotenv import dotenv_values
            env = dotenv_values(ROOT / ".env")
            base = base or (env.get("WP_URL") or "").strip().rstrip("/")
            user = user or (env.get("WP_USER") or "").strip()
            pw = pw or (env.get("WP_APP_PASSWORD") or "").strip()
        except Exception:
            pass
    if not (base and user and pw):
        raise SystemExit("WP_URL / WP_USER / WP_APP_PASSWORD required (env or .env)")
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


def main() -> int:
    data = {"years": []}
    if DATA_PATH.is_file():
        try:
            data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"WARN: baked data read failed: {exc!r}", file=sys.stderr)
    years = data.get("years") or []

    cur = datetime.now(timezone.utc).year
    fresh = scrape_year(cur)
    if fresh:
        before = next((len(y.get("games") or []) for y in years
                       if int(y.get("year") or 0) == cur), 0)
        years = upsert_year(years, fresh)
        print(f"refreshed {cur}: {before} -> {len(fresh['games'])} games")
    else:
        print(f"WARN: {cur} fetch returned no data; publishing with baked data only",
              file=sys.stderr)
    data["years"] = years

    if not years:
        raise SystemExit("no rotation data to publish")

    base, auth = _creds()
    cluster_id = _find_page_id(base, auth, "data", parent=0)
    content = render_rotation_html(data)
    payload = {
        "slug": SLUG,
        "title": render_rotation_title(),
        "content": content,
        "status": "publish",
        "parent": cluster_id,
        "excerpt": render_rotation_excerpt(data),
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
        print(f"upsert FAILED status={r.status_code} body={r.text[:400]}", file=sys.stderr)
        return 1
    page = r.json() or {}
    print(f"{action} page_id={page.get('id')} status={page.get('status')} "
          f"link={page.get('link')} bytes={len(content)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
