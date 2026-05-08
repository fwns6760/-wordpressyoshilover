"""Daily morning digest article generator.

DIGEST-DAILY-MORNING-2026-05-08 ticket Phase 1。

Produces 1 article/day around 06:00 JST aggregating multiple existing blocks:
- 直近試合(recent_games)
- 現順位(standings)
- 翌日試合予定(next_game)
- ファン声(X embed)

ファンが朝起きて 1 記事だけ読めば前日 + 当日が追える状態を作る。
のもとけ式の「朝刊」概念を直接体現。

Idempotent
==========

WP REST で slug ``morning-digest-YYYY-MM-DD`` 既存 check、当日 2 回呼んでも
1 記事のみ publish。

Cost
====

¥0:
- 既存 block helper(_build_recent_games_block / _build_next_game_block /
  _build_standings_block / _build_x_embeds_block)を reuse、新規 fetch なし
- Gemini call なし(本 module は純集約のみ)
- Cloud Run 内で完結、外部 API 増加なし

Usage
=====

>>> from src.tools.digest_daily_morning import build_digest_body, build_digest_title
>>> body = build_digest_body()
>>> title = build_digest_title()
>>> # Or via CLI:
>>> #   python3 -m src.tools.digest_daily_morning --dry-run
>>> #   python3 -m src.tools.digest_daily_morning  # actually publish

Integration
===========

Scheduler integration は別途。最小: ``giants-morning-catchup`` scheduler
(04:30 JST)が yoshilover-fetcher /run に投げる payload で
``--mode=digest_daily`` または env ``ENABLE_DIGEST_DAILY=1`` を読んで本 module
を呼出する path を追加(別 ticket、user judgment境界 = scheduler / env 変更)。
"""

from __future__ import annotations

import argparse
import datetime
from typing import Optional

JST = datetime.timezone(datetime.timedelta(hours=9))


def _today_jp_short() -> str:
    """Return today's date in JP short form '5月9日'."""
    now = datetime.datetime.now(JST)
    return f"{now.month}月{now.day}日"


def _today_iso() -> str:
    """Return today's date as ISO 'YYYY-MM-DD' for slug/dedup."""
    return datetime.datetime.now(JST).strftime("%Y-%m-%d")


def build_digest_title(today_jp: Optional[str] = None) -> str:
    """Compose the daily morning digest article title."""
    label = today_jp or _today_jp_short()
    return f"📰 朝まとめ {label} — 巨人 順位 / 前日試合 / 翌日予定"


def build_digest_slug() -> str:
    """Idempotency key as WP slug: ``morning-digest-YYYY-MM-DD``."""
    return f"morning-digest-{_today_iso()}"


def build_digest_body(
    *,
    today_jp: Optional[str] = None,
    include_recent_games: bool = True,
    include_standings: bool = True,
    include_next_game: bool = True,
    include_x_embeds: bool = True,
) -> str:
    """Compose the daily morning digest body HTML.

    nomotoke-card- marker (nomotoke-card-divider / nomotoke-card-footer) を
    含むので apply_rss_pipeline_enrichment が走り、追加 block (関連記事 等)
    も自動付与される。
    """
    label = today_jp or _today_jp_short()
    parts: list[str] = []

    parts.append(
        f'<p class="nomotoke-lead">{label} 朝まとめ。'
        '前日の試合結果、現在の順位、翌日の予定を 1 記事に集約。</p>'
    )

    parts.append("<h3>📋 事実カード</h3>")
    parts.append(
        f'<p>{label} 時点の巨人情報まとめ。各 block は実データから自動生成。</p>'
    )

    # Lazy import to avoid circular dependency at module load
    try:
        from src.tools.manual_intake import (
            _build_recent_games_block,
            _build_next_game_block,
            _build_standings_block,
            _build_x_embeds_block,
        )
    except Exception:
        return "\n".join(parts)

    if include_recent_games:
        block = _build_recent_games_block()
        if block:
            parts.append(block)

    if include_standings:
        block = _build_standings_block()
        if block:
            parts.append(block)

    if include_next_game:
        block = _build_next_game_block()
        if block:
            parts.append(block)

    if include_x_embeds:
        block = _build_x_embeds_block(f"巨人 {label}", "朝まとめ")
        if block:
            parts.append(block)

    parts.append("<h3>🔗 出典記事</h3>")
    parts.append(
        '<p>各 block の data 元: '
        '<a href="https://baseball.yahoo.co.jp/npb/" target="_blank" rel="noopener">'
        "Yahoo Sportsnavi</a> / "
        '<a href="https://npb.jp/" target="_blank" rel="noopener">NPB公式</a></p>'
    )

    parts.append('<hr class="nomotoke-card-divider">')
    parts.append(
        '<div class="nomotoke-card-footer">'
        '<p class="nomotoke-cta-row">'
        '<a class="nomotoke-cta-button" href="#respond" '
        'style="display:inline-block;padding:12px 28px;background:#f57f17;'
        "color:#fff;text-decoration:none;border-radius:8px;"
        'font-weight:700;font-size:16px;">💬 コメントする</a>'
        "</p>"
        '<p class="nomotoke-comment-hint">'
        "今日の試合の感想・予想はコメント欄からお気軽にどうぞ。"
        "</p>"
        "</div>"
    )

    return "\n".join(parts)


def is_digest_already_published_today(wp_client) -> bool:
    """WP REST slug query で当日分の digest が既存か check。

    True を返すと caller は publish skip すべき。
    """
    slug = build_digest_slug()
    try:
        # WPClient に slug 検索 helper があれば使う、なければ find_recent_post
        existing = wp_client.find_recent_post_by_title(
            slug, reusable_statuses={"publish", "draft", "future"}
        )
        return bool(existing)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily morning digest publisher")
    parser.add_argument("--dry-run", action="store_true", help="print body without publish")
    parser.add_argument(
        "--category-id", type=int, default=670,
        help="WP category ID (default 670 = コラム)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="ignore today-already-published guard",
    )
    args = parser.parse_args()

    title = build_digest_title()
    body = build_digest_body()

    if args.dry_run:
        print(f"=== DRY RUN ===")
        print(f"Title: {title}")
        print(f"Slug: {build_digest_slug()}")
        print(f"Body length: {len(body)} chars")
        print(f"--- body preview (first 800) ---")
        print(body[:800])
        return 0

    try:
        from src.wp_client import WPClient
    except Exception as exc:
        print(f"ERROR: failed to import WPClient: {exc}")
        return 2

    wp = WPClient()
    if not args.force and is_digest_already_published_today(wp):
        print(f"Digest for today already exists, skipping (slug={build_digest_slug()})")
        return 0

    try:
        post_id = wp.create_post(
            title=title,
            content=body,
            status="publish",
            categories=[args.category_id],
            caller="digest_daily_morning",
        )
        print(f"Published: post_id={post_id}")
        return 0
    except Exception as exc:
        print(f"ERROR: create_post failed: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
