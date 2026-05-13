"""morning_event_key_enricher.py — 翌朝 7:00 JST の親記事自動補強。

Phase A of the parent-article system (Plan A, 2026-05-13 user lock).

Runs once per day. For each event_key group whose window has closed
(= 翌日 JST 07:00 を超えた game_result), append an enrichment section
to the parent (already-published) article. The section indexes child
articles by axis (監督コメント / 本人コメント / YouTube 動画 / 順位影響 /
朝刊コラム / X 反応 = ファンの声).

Idempotent via HTML sentinel comments::

    <!-- yoshilover:event_key_enrichment:start ... -->
    ...
    <!-- yoshilover:event_key_enrichment:end -->

Subsequent runs replace the block in place instead of duplicating.

Mutation policy
---------------
* GET parent body with ``context=edit`` (auth required) so raw content
  with shortcodes is preserved on round-trip.
* POST ``/wp/v2/posts/{id}`` with ``{"content": <new_raw>}``.
* Children are NOT touched. They stay published.
* Records the action in ``logs/event_key_morning_enrichment/<date>.jsonl``.
* ``--dry-run`` is the default. ``--apply`` is required to actually PATCH.

Usage::

    python3 -m src.morning_event_key_enricher --date 2026-05-12 --dry-run
    python3 -m src.morning_event_key_enricher --date 2026-05-12 --apply
    python3 -m src.morning_event_key_enricher --apply  # default = yesterday
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import event_key_ledger as ekl  # noqa: E402

logger = logging.getLogger(__name__)

ENRICHMENT_START_MARKER = "<!-- yoshilover:event_key_enrichment:start"
ENRICHMENT_END_MARKER = "<!-- yoshilover:event_key_enrichment:end -->"
ENRICHMENT_BLOCK_RE = re.compile(
    re.escape(ENRICHMENT_START_MARKER)
    + r".*?"
    + re.escape(ENRICHMENT_END_MARKER),
    flags=re.DOTALL,
)


# ─── enrichment HTML composer ───────────────────────────────────────────────


# Roles that should NOT be surfaced in the enrichment section:
# duplicate_or_paraphrase = pure言い換え（親本文と被る）, other = 未分類。
EXCLUDED_ROLES_FROM_SECTION = {"duplicate_or_paraphrase", "other"}

# Display order + heading for each role group.
ROLE_DISPLAY_ORDER: tuple[tuple[str, str], ...] = (
    ("manager_quote", "監督コメント"),
    ("player_quote", "本人 / 関係者コメント"),
    ("youtube_video", "動画（YouTube公式）"),
    ("instagram_post", "Instagram"),
    ("fan_voice_x_post", "ファンの声（X ポスト）"),
    ("standings_impact", "順位への影響"),
    ("morning_column", "朝刊コラム / 番記者"),
    ("scene_detail", "場面詳細"),
)


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def compose_enrichment_html(group: dict, *, generated_at: dt.datetime) -> str:
    """Build the HTML block that gets inserted between the sentinel
    comments. Pure function — no WP / network access."""
    if group.get("kind") != "game_result":
        raise ValueError(f"compose only valid for game_result groups (got {group.get('kind')})")

    by_role: dict[str, list[dict]] = {}
    for ch in group.get("children") or []:
        role = ch.get("enrichment_role") or "other"
        if role in EXCLUDED_ROLES_FROM_SECTION:
            continue
        by_role.setdefault(role, []).append(ch)

    parts: list[str] = []
    meta = (
        f"{ENRICHMENT_START_MARKER} "
        f"event_key={_esc(group.get('event_key',''))} "
        f"generated_at={generated_at.isoformat()} -->"
    )
    parts.append(meta)
    parts.append("<h2>試合の全角度</h2>")

    rendered_any = False
    for role_key, heading in ROLE_DISPLAY_ORDER:
        items = by_role.get(role_key) or []
        if not items:
            continue
        rendered_any = True
        parts.append(f"<h3>{_esc(heading)}</h3>")
        parts.append("<ul>")
        for it in items:
            link = it.get("link") or ""
            title = it.get("title") or ""
            parts.append(f'  <li><a href="{_esc(link)}">{_esc(title)}</a></li>')
        parts.append("</ul>")

    standalone = group.get("standalone") or []
    if standalone:
        rendered_any = True
        parts.append("<h3>独立記事（起用意図 / 過去記録など）</h3>")
        parts.append("<ul>")
        for st in standalone:
            link = st.get("link") or ""
            title = st.get("title") or ""
            parts.append(f'  <li><a href="{_esc(link)}">{_esc(title)}</a></li>')
        parts.append("</ul>")

    if not rendered_any:
        parts.append("<p><em>追加情報なし</em></p>")

    parts.append(ENRICHMENT_END_MARKER)
    return "\n".join(parts)


def upsert_enrichment_block(original_body: str, new_block: str) -> str:
    """Return ``original_body`` with the existing enrichment sentinel
    block replaced by ``new_block``, or with the block appended at the
    end when no existing block is found.

    Idempotent: running multiple times yields the same result for the
    same ``new_block``.
    """
    if ENRICHMENT_BLOCK_RE.search(original_body):
        return ENRICHMENT_BLOCK_RE.sub(new_block, original_body, count=1)
    sep = "\n\n" if original_body and not original_body.endswith("\n") else "\n"
    return original_body + sep + new_block + "\n"


# ─── WP I/O helpers ─────────────────────────────────────────────────────────


def fetch_parent_raw_body(wp, post_id: int):
    """GET ``/wp/v2/posts/{id}?context=edit`` so we get raw content
    (not rendered HTML). ``wp`` is a ``WPClient`` instance.

    Returns the JSON dict on success; raises on HTTP error.
    """
    import requests

    resp = requests.get(
        f"{wp.api}/posts/{post_id}",
        params={"context": "edit"},
        auth=wp.auth,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def patch_parent_content(wp, post_id: int, new_raw_body: str) -> None:
    """POST update to ``/wp/v2/posts/{id}`` with the new raw content."""
    wp.update_post_fields(
        post_id,
        content=new_raw_body,
        caller="morning_event_key_enricher",
        source_lane="event_key_enrichment",
    )


# ─── main pipeline ──────────────────────────────────────────────────────────


def collect_closed_game_result_groups(
    *,
    game_date: dt.date,
    now: dt.datetime,
    fetcher=None,
) -> list[dict]:
    """Return ``game_result`` groups whose window is closed (``now`` >=
    close_at) for the given ``game_date``. ``fetcher`` is injectable for
    tests; defaults to the live WP REST fetch."""
    fetch = fetcher or ekl.fetch_published_posts
    # Fetch the game day + the morning-after window (close_at = next 07:00).
    posts = fetch(
        since=game_date,
        until=game_date + dt.timedelta(days=1, hours=0),
    )
    # The window-end fetch needs to include articles published 00:00–07:00
    # on game_date+1, which the previous call already covers because the
    # caller passes "until" as exclusive next day; the morning-after
    # roundup falls into that range only when our `until` is at least one
    # full day after game_date. ekl.fetch_published_posts treats the
    # before window as ISO00:00, so we widen by an extra day so that
    # game_date+1's 00:00–07:00 articles are included.
    extra = fetch(
        since=game_date + dt.timedelta(days=1),
        until=game_date + dt.timedelta(days=2),
    )
    posts = list(posts) + [p for p in extra if p.get("id") not in {q.get("id") for q in posts}]
    records = [ekl.post_to_record(p) for p in posts]
    groups = ekl.group_records(records, now=now)
    return [
        g for g in groups
        if g.get("kind") == "game_result"
        and g.get("game_date") == game_date.isoformat()
        and (g.get("window") or {}).get("status") == "closed"
        and len(g.get("children") or []) >= 1
    ]


def process_group(
    group: dict,
    *,
    wp,
    apply: bool,
    now: dt.datetime,
) -> dict:
    """Compose enrichment HTML for a single group and (optionally)
    PATCH the parent body. Returns a result dict for the ledger."""
    parent_id = int(group["parent_id"])
    new_block = compose_enrichment_html(group, generated_at=now)

    result: dict[str, Any] = {
        "event_key": group["event_key"],
        "parent_id": parent_id,
        "children_count": len(group.get("children") or []),
        "standalone_count": len(group.get("standalone") or []),
        "axes_covered": group.get("axes_covered"),
        "axes_total": group.get("axes_total"),
        "block_chars": len(new_block),
        "applied": False,
        "skipped_reason": None,
    }

    if not apply:
        result["dry_run"] = True
        return result

    # apply=True path
    try:
        post = fetch_parent_raw_body(wp, parent_id)
    except Exception as exc:
        result["skipped_reason"] = f"fetch_failed:{exc!r}"
        return result

    status = (post.get("status") or "").lower()
    if status != "publish":
        result["skipped_reason"] = f"parent_status_not_publish:{status}"
        return result

    raw_content = (post.get("content") or {}).get("raw") or ""
    new_body = upsert_enrichment_block(raw_content, new_block)
    if new_body == raw_content:
        result["skipped_reason"] = "noop_no_change"
        return result

    try:
        patch_parent_content(wp, parent_id, new_body)
        result["applied"] = True
    except Exception as exc:
        result["skipped_reason"] = f"patch_failed:{exc!r}"
    return result


def append_ledger(out_dir: Path, label: str, entries: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{label}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


# ─── CLI ────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Morning event_key parent-article enricher (7:00 JST).")
    p.add_argument("--date", help="game_date YYYY-MM-DD (default = yesterday in JST)")
    p.add_argument("--apply", action="store_true", help="actually PATCH parent body via WP REST")
    p.add_argument("--dry-run", action="store_true", help="explicit dry-run (default behavior)")
    p.add_argument("--print-html", action="store_true", help="print the composed HTML for each group")
    return p.parse_args(argv)


def _default_game_date(now: dt.datetime) -> dt.date:
    """Yesterday in JST relative to ``now``."""
    return (now.astimezone(ekl.JST).date() - dt.timedelta(days=1))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    now = dt.datetime.now(ekl.JST)

    if args.date:
        game_date = dt.date.fromisoformat(args.date)
    else:
        game_date = _default_game_date(now)

    apply = bool(args.apply)
    if args.dry_run and apply:
        print("error: --dry-run and --apply are mutually exclusive", file=sys.stderr)
        return 2

    groups = collect_closed_game_result_groups(game_date=game_date, now=now)

    summary: dict[str, Any] = {
        "game_date": game_date.isoformat(),
        "now": now.isoformat(),
        "apply": apply,
        "groups_eligible": len(groups),
    }

    if not groups:
        summary["note"] = "no closed game_result group with children — nothing to do"
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    wp = None
    if apply:
        # Defer the import so dry-run doesn't require .env to be present.
        from src.wp_client import WPClient  # noqa: WPS433

        wp = WPClient()

    results: list[dict] = []
    for g in groups:
        r = process_group(g, wp=wp, apply=apply, now=now)
        results.append(r)
        if args.print_html:
            print("---")
            print(f"event_key: {g['event_key']}")
            print(compose_enrichment_html(g, generated_at=now))

    out_dir = ROOT / "logs" / "event_key_morning_enrichment"
    path = append_ledger(out_dir, game_date.isoformat(), results)
    summary["results"] = results
    summary["ledger_path"] = str(path)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
