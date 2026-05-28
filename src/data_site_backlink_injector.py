"""Phase 2 (ticket 443 §5 / 444 拡張): 既存 publish 記事に Pillar back-link を
idempotent 注入する batch script.

flow:
1. config から Phase 1.5 対象 31 player の name list を取得
2. 各 player について:
   - WP tag id 解決 (person_tag_router 経由)
   - 該当 tag の publish 記事 を全件 fetch (paginate)
   - 各記事 content の末尾 (出典 block 直前 OR </body> 相当位置) に
     `<aside class="ys-data-backlink">関連: <a href="/data/{slug}/">{player} の データを見る</a></aside>`
     を追加 (既存に同 aside あれば skip = idempotent)
   - WP REST POST /posts/{id} で content 上書き
3. DATA_SITE_BACKLINK_DRY_RUN=1 で 書き込み skip (count + sample のみ)

scope guard:
- DATA_SITE_BACKLINK_MAX_PER_PLAYER で 1 player あたり upsert 上限 (default 20、
  小規模 batch 確認後 拡大)
- DATA_SITE_BACKLINK_PLAYER_FILTER で 1 player のみ実行 (例: 'togo-shosei')

冪等性: aside HTML に class `ys-data-backlink` + slug を持たせ、 検出で skip。
"""

from __future__ import annotations

import json as _json
import logging
import os
import re
import sys
from dataclasses import dataclass, field

import requests
from requests.auth import HTTPBasicAuth

from src.data_site_query import (
    find_player_tag_id,
    load_phase1_player_names,
    load_roster_player,
)
from src.data_site_slug import player_slug


LOG = logging.getLogger("data_site_backlink_injector")

# back-link aside class — このマーカーで既存検出 (冪等性)
BACKLINK_ASIDE_CLASS = "ys-data-backlink"

# aside HTML template (slug を data-slug attr に入れて検出強化)
_BACKLINK_ASIDE_TEMPLATE = (
    '<aside class="{cls}" data-slug="{slug}" '
    'style="background:#fff8e1;border-left:3px solid #ff6f00;'
    'padding:14px 16px;margin:24px 0 0;border-radius:6px;font-size:14px;">'
    '<strong style="color:#5d4037;">関連 player データ:</strong> '
    '<a href="https://yoshilover.com/data/{slug}/" '
    'style="color:#1976d2;text-decoration:none;font-weight:600;">'
    '🐰 {name} の data page を見る →</a>'
    '</aside>'
)


@dataclass
class InjectorSummary:
    player: str
    slug: str
    tag_id: int | None
    posts_total: int = 0
    posts_skipped_already_has: int = 0
    posts_updated: int = 0
    posts_failed: int = 0
    sample_post_ids: list[int] = field(default_factory=list)


def _dry_run_enabled() -> bool:
    return str(os.environ.get("DATA_SITE_BACKLINK_DRY_RUN", "")).strip().lower() in {"1", "true", "yes", "on"}


def _max_per_player() -> int:
    raw = str(os.environ.get("DATA_SITE_BACKLINK_MAX_PER_PLAYER", "20")).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 20


def _player_filter() -> str:
    """1 player slug 指定で他 skip (small-batch verify 用)。 空なら全 31 player。"""
    return str(os.environ.get("DATA_SITE_BACKLINK_PLAYER_FILTER", "")).strip()


def _wp_creds() -> tuple[str, HTTPBasicAuth]:
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        raise RuntimeError("WP_URL / WP_USER / WP_APP_PASSWORD env required")
    return base, HTTPBasicAuth(user, pw)


def _build_aside_html(*, slug: str, name: str) -> str:
    return _BACKLINK_ASIDE_TEMPLATE.format(cls=BACKLINK_ASIDE_CLASS, slug=slug, name=name)


def _already_has_backlink(content: str, slug: str) -> bool:
    """既存 content に同 slug の back-link aside が含まれてるか (冪等性 check)."""
    if not content:
        return False
    # class マーカー + data-slug 一致で検出
    pattern = re.compile(
        rf'class="[^"]*{re.escape(BACKLINK_ASIDE_CLASS)}[^"]*"[^>]*data-slug="{re.escape(slug)}"',
        re.IGNORECASE,
    )
    return bool(pattern.search(content))


def _inject_aside(content: str, aside_html: str) -> str:
    """content 末尾に aside を追加 (既存 layout を破壊しない)."""
    if not content:
        return aside_html
    return content.rstrip() + "\n\n" + aside_html


def _fetch_posts_for_tag(
    base: str,
    auth: HTTPBasicAuth,
    tag_id: int,
    limit: int,
) -> list[dict]:
    """tag id を持つ publish post を最大 limit 件、 新しい順で取得."""
    posts: list[dict] = []
    per_page = min(limit, 100)
    page = 1
    while len(posts) < limit:
        try:
            r = requests.get(
                base + "/wp-json/wp/v2/posts",
                params={
                    "tags": tag_id,
                    "status": "publish",
                    "per_page": per_page,
                    "page": page,
                    "orderby": "date",
                    "order": "desc",
                    "_fields": "id,title,content,link",
                },
                auth=auth,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("fetch_posts err tag=%d page=%d: %r", tag_id, page, exc)
            break
        if not r.ok:
            # 400 で page over-flow (WP 仕様)、 break
            break
        rows = r.json() or []
        if not rows:
            break
        posts.extend(rows)
        if len(rows) < per_page:
            break
        page += 1
    return posts[:limit]


def _update_post_content(
    base: str,
    auth: HTTPBasicAuth,
    post_id: int,
    new_content: str,
) -> bool:
    if _dry_run_enabled():
        return True
    try:
        r = requests.post(
            base + f"/wp-json/wp/v2/posts/{post_id}",
            json={"content": new_content},
            auth=auth,
            timeout=30,
        )
        if r.ok:
            return True
        LOG.warning("update post %d failed status=%d body=%s", post_id, r.status_code, r.text[:200])
        return False
    except Exception as exc:  # noqa: BLE001
        LOG.warning("update post %d exception: %r", post_id, exc)
        return False


def _process_player(player_name: str) -> InjectorSummary:
    slug = player_slug(player_name)
    roster = load_roster_player(player_name)
    display_name = roster.name if roster else player_name
    summary = InjectorSummary(player=player_name, slug=slug, tag_id=None)

    tag_id = find_player_tag_id(player_name)
    summary.tag_id = tag_id
    if tag_id is None:
        LOG.info("skip player=%s reason=no_tag", player_name)
        return summary

    base, auth = _wp_creds()
    limit = _max_per_player()
    posts = _fetch_posts_for_tag(base, auth, tag_id, limit)
    summary.posts_total = len(posts)
    aside_html = _build_aside_html(slug=slug, name=display_name)

    for post in posts:
        post_id = int(post.get("id") or 0)
        if post_id <= 0:
            continue
        content = str((post.get("content") or {}).get("rendered", "") or "")
        if _already_has_backlink(content, slug):
            summary.posts_skipped_already_has += 1
            continue
        new_content = _inject_aside(content, aside_html)
        ok = _update_post_content(base, auth, post_id, new_content)
        if ok:
            summary.posts_updated += 1
            if len(summary.sample_post_ids) < 5:
                summary.sample_post_ids.append(post_id)
        else:
            summary.posts_failed += 1
    return summary


def run() -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    target_names = load_phase1_player_names()
    if not target_names:
        return {"status": "abort", "reason": "no_target_players"}
    filter_slug = _player_filter()
    if filter_slug:
        target_names = [n for n in target_names if player_slug(n) == filter_slug]
        LOG.info("filtered to slug=%s players=%s", filter_slug, target_names)

    LOG.info(
        "backlink injector start dry_run=%s max_per_player=%d players=%d",
        _dry_run_enabled(), _max_per_player(), len(target_names),
    )

    summaries: list[InjectorSummary] = []
    for name in target_names:
        s = _process_player(name)
        summaries.append(s)
        LOG.info(
            "player=%s slug=%s tag=%s total=%d skipped=%d updated=%d failed=%d sample=%s",
            s.player, s.slug, s.tag_id, s.posts_total,
            s.posts_skipped_already_has, s.posts_updated, s.posts_failed,
            s.sample_post_ids,
        )

    totals = {
        "players_processed": len(summaries),
        "posts_total": sum(s.posts_total for s in summaries),
        "posts_skipped_already_has": sum(s.posts_skipped_already_has for s in summaries),
        "posts_updated": sum(s.posts_updated for s in summaries),
        "posts_failed": sum(s.posts_failed for s in summaries),
    }
    LOG.info("backlink injector done totals=%s", _json.dumps(totals, ensure_ascii=False))
    return {"status": "ok", "dry_run": _dry_run_enabled(), "totals": totals, "per_player": [
        {"player": s.player, "slug": s.slug, "tag": s.tag_id, "total": s.posts_total,
         "skipped": s.posts_skipped_already_has, "updated": s.posts_updated, "failed": s.posts_failed,
         "samples": s.sample_post_ids}
        for s in summaries
    ]}


if __name__ == "__main__":
    summary = run()
    sys.exit(0 if summary.get("status") == "ok" else 1)
