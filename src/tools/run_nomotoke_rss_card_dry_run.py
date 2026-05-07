"""NOMOTOKE-RSS-CARD-001A — RSS dry-run observability CLI.

Purpose
=======

Run the RSS-to-nomotoke-card router against:

    1. live RSS 1-pass over ``config/rss_sources.json`` (HTTP serial fetch).
    2. Cloud Logging last 72h sample (``article_skipped_post_gen_validate`` /
       ``article_ai_route_override`` events from yoshilover-fetcher).

Emit a JSON report with per-source / per-template / per-skip-reason cross-tabs,
samples, and the LOCKED ``recommended_next_integration`` decision block for
NOMOTOKE-RSS-CARD-001B.

NEVER calls Gemini. NEVER writes to WP. NEVER touches rss_fetcher.py.

Usage
-----

    python -m src.tools.run_nomotoke_rss_card_dry_run \\
        [--source live,logging|live|logging|json] \\
        [--out PATH] \\
        [--max-per-source 30] \\
        [--max-total 400] \\
        [--hours 72] \\
        [--json-fixtures PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent.parent
_VENDOR = str(ROOT / "vendor")
_SRC = str(ROOT / "src")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import feedparser  # noqa: E402

from src.nomotoke_rss_router import (  # noqa: E402
    QUALITY_CEILING_BY_TEMPLATE,
    REQUIRED_FACTS_BY_TEMPLATE,
    RSS_ONLY_ALLOWED_TEMPLATES,
    RSS_ONLY_BLOCKED_TEMPLATES,
    SKIP_REASON_TAXONOMY,
    derive_next_recommended,
    derive_not_suitable_for_rss,
    route_rss_entry_to_nomotoke_card,
)


HTTP_USER_AGENT = "Mozilla/5.0 (yoshilover-nomotoke-rss-card-dry-run/1)"
HTTP_ACCEPT = (
    "application/rss+xml, application/atom+xml, application/xml, text/xml"
)
HTTP_TIMEOUT_SEC = 10
SAMPLE_LIMIT_PER_TEMPLATE = 5
SAMPLE_LIMIT_PER_SKIP_REASON = 5
TITLE_TRUNCATE = 80


# ---------------------------------------------------------------------------
# Live RSS 1-pass
# ---------------------------------------------------------------------------


def _fetch_feed(url: str) -> Tuple[Any, str]:
    """Return (feed, error). feed is None on failure."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": HTTP_USER_AGENT, "Accept": HTTP_ACCEPT},
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            data = resp.read()
        feed = feedparser.parse(data)
        return feed, ""
    except Exception as exc:
        return None, f"{exc.__class__.__name__}: {exc}"


def _entry_to_router_input(entry: Any) -> Dict[str, Any]:
    return {
        "title": (entry.get("title") or ""),
        "summary": (
            entry.get("summary")
            or entry.get("description")
            or ((entry.get("content", [{}])[0] or {}).get("value", "") if entry.get("content") else "")
            or ""
        ),
        "link": (entry.get("link") or ""),
        "published": (entry.get("published") or entry.get("pubDate") or ""),
    }


def run_live_rss_pass(
    *,
    sources_file: Path,
    max_per_source: int,
    max_total: int,
) -> Dict[str, Any]:
    sources_data: List[Dict[str, Any]] = json.loads(
        sources_file.read_text(encoding="utf-8")
    )
    state = _new_aggregate_state()
    source_errors: Dict[str, str] = {}
    total_seen = 0

    for src in sources_data:
        if total_seen >= max_total:
            break
        source_name = (src.get("name") or "").strip()
        url = (src.get("url") or "").strip()
        if not url:
            continue
        feed, err = _fetch_feed(url)
        if feed is None:
            source_errors[source_name or url] = err
            continue
        entries = list(feed.entries or [])[:max_per_source]
        if total_seen + len(entries) > max_total:
            entries = entries[: max_total - total_seen]
        for raw in entries:
            total_seen += 1
            re_input = _entry_to_router_input(raw)
            try:
                result = route_rss_entry_to_nomotoke_card(
                    re_input,
                    source_name=source_name,
                    source_url=re_input["link"],
                )
            except ValueError as exc:
                # nomotoke phrasing guard fired; record explicit skip
                _record_skip(
                    state,
                    source_name=source_name,
                    skip_reason=f"defensive_value_error:{exc}",
                    sample_title=re_input["title"][:TITLE_TRUNCATE],
                    canonical_url="",
                )
                continue
            _record_route(state, result, sample_title=re_input["title"][:TITLE_TRUNCATE])

    state["source_errors"] = source_errors
    state["total_entries"] = total_seen
    state["source_count"] = len(sources_data)
    return state


# ---------------------------------------------------------------------------
# Cloud Logging 72h sample
# ---------------------------------------------------------------------------


_LOGGING_TEXT_PAYLOAD_RE = re.compile(r"\{.*\}", re.DOTALL)


def run_logging_sample_pass(*, hours: int) -> Dict[str, Any]:
    """Best-effort. Always returns a dict. May set logging_sample_insufficient=true."""
    state = _new_aggregate_state()
    state["logging_sample_insufficient"] = False
    state["logging_fields_acquired"] = []
    state["logging_fields_missing"] = []
    state["logging_fallback_strategy"] = ""
    state["total_entries"] = 0

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    query = (
        'resource.type="cloud_run_revision" AND '
        'resource.labels.service_name="yoshilover-fetcher" AND '
        '(textPayload:"article_skipped_post_gen_validate" OR '
        'textPayload:"article_ai_route_override") AND '
        f'timestamp>="{cutoff}"'
    )
    try:
        proc = subprocess.run(
            [
                "gcloud",
                "logging",
                "read",
                query,
                "--limit=2000",
                "--format=value(textPayload)",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        state["logging_sample_insufficient"] = True
        state["logging_fields_missing"] = ["all"]
        state["logging_fallback_strategy"] = (
            f"gcloud_unavailable:{exc.__class__.__name__}; live_rss_only"
        )
        return state

    if proc.returncode != 0:
        state["logging_sample_insufficient"] = True
        state["logging_fields_missing"] = ["all"]
        state["logging_fallback_strategy"] = (
            f"gcloud_returncode={proc.returncode}; live_rss_only"
        )
        return state

    raw_lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]

    parsed: List[Dict[str, Any]] = []
    fields_seen: set = set()
    for ln in raw_lines:
        m = _LOGGING_TEXT_PAYLOAD_RE.search(ln)
        if not m:
            continue
        try:
            obj = json.loads(m.group(0))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        fields_seen.update(obj.keys())
        ev = obj.get("event") or ""
        if ev == "article_ai_route_override":
            parsed.append(
                {
                    "title": obj.get("title", ""),
                    "summary": "",
                    "link": obj.get("source_url", ""),
                    "published": "",
                    "source_name_hint": _domain_to_source_name(obj.get("source_url", "")),
                }
            )
        elif ev == "article_skipped_post_gen_validate":
            parsed.append(
                {
                    "title": obj.get("title", ""),
                    "summary": "",
                    "link": obj.get("post_url", ""),
                    "published": "",
                    "source_name_hint": _domain_to_source_name(obj.get("post_url", "")),
                }
            )

    state["logging_fields_acquired"] = sorted(fields_seen)
    if len(parsed) < 50:
        state["logging_sample_insufficient"] = True
        state["logging_fallback_strategy"] = "live_rss_dominant"
    else:
        state["logging_sample_insufficient"] = False

    state["total_entries"] = len(parsed)
    state["entries_acquired"] = len(parsed)

    for re_input in parsed:
        source_name = re_input.pop("source_name_hint") or ""
        try:
            result = route_rss_entry_to_nomotoke_card(
                re_input,
                source_name=source_name,
                source_url=re_input["link"],
            )
        except ValueError as exc:
            _record_skip(
                state,
                source_name=source_name,
                skip_reason=f"defensive_value_error:{exc}",
                sample_title=re_input["title"][:TITLE_TRUNCATE],
                canonical_url="",
            )
            continue
        _record_route(state, result, sample_title=re_input["title"][:TITLE_TRUNCATE])

    return state


def _domain_to_source_name(url: str) -> str:
    if not url:
        return ""
    if "twitter.com" in url or "x.com" in url:
        # try to extract handle
        m = re.search(r"twitter\.com/([^/]+)/", url) or re.search(r"x\.com/([^/]+)/", url)
        if m:
            return m.group(1)
        return "twitter.com"
    if "hochi" in url:
        return "スポーツ報知 巨人"
    if "nikkansports" in url:
        return "日刊スポーツ 巨人"
    if "sponichi" in url:
        return "SponichiYakyu"
    if "sanspo" in url:
        return "Sanspo_Giants"
    if "baseballking" in url:
        return "ベースボールキング"
    if "full-count" in url:
        return "Full-Count 巨人"
    return ""


# ---------------------------------------------------------------------------
# JSON fixture pass (optional, for tests)
# ---------------------------------------------------------------------------


def run_json_fixture_pass(fixture_dir: Path) -> Dict[str, Any]:
    state = _new_aggregate_state()
    state["total_entries"] = 0
    if not fixture_dir.exists():
        return state
    files = sorted(fixture_dir.glob("*.json"))
    for f in files:
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        source_name = (obj.get("source_name") or "").strip()
        link = (obj.get("link") or "").strip()
        re_input = {
            "title": (obj.get("title") or "").strip(),
            "summary": (obj.get("summary") or "").strip(),
            "link": link,
            "published": (obj.get("published") or "").strip(),
        }
        state["total_entries"] += 1
        try:
            result = route_rss_entry_to_nomotoke_card(
                re_input,
                source_name=source_name,
                source_url=link,
            )
        except ValueError as exc:
            _record_skip(
                state,
                source_name=source_name,
                skip_reason=f"defensive_value_error:{exc}",
                sample_title=re_input["title"][:TITLE_TRUNCATE],
                canonical_url="",
            )
            continue
        _record_route(state, result, sample_title=re_input["title"][:TITLE_TRUNCATE])
    return state


# ---------------------------------------------------------------------------
# Aggregate state
# ---------------------------------------------------------------------------


def _new_aggregate_state() -> Dict[str, Any]:
    return {
        "total_entries": 0,
        "source_count": 0,
        "hit_total": 0,
        "skip_total": 0,
        "template_counts": {},
        "skip_reason_counts": {},
        "per_source_counts": {},
        "per_source_template_counts": {},
        "per_source_skip_reason_counts": {},
        "samples_by_template": {},
        "samples_by_skip_reason": {},
        "template_confidence_counts": {},
        "source_errors": {},
    }


def _record_route(state: Dict[str, Any], result: Any, *, sample_title: str) -> None:
    src = result.source_name or "(unknown)"
    state["per_source_counts"][src] = state["per_source_counts"].get(src, 0) + 1
    if result.matched and result.template_key:
        state["hit_total"] += 1
        tk = result.template_key
        state["template_counts"][tk] = state["template_counts"].get(tk, 0) + 1
        ps = state["per_source_template_counts"].setdefault(src, {})
        ps[tk] = ps.get(tk, 0) + 1
        cb = state["template_confidence_counts"].setdefault(tk, {})
        cb[result.confidence] = cb.get(result.confidence, 0) + 1
        bucket = state["samples_by_template"].setdefault(tk, [])
        if len(bucket) < SAMPLE_LIMIT_PER_TEMPLATE:
            bucket.append(
                {
                    "source_name": src,
                    "title": sample_title,
                    "url": result.canonical_url,
                    "confidence": result.confidence,
                    "tier": result.tier,
                }
            )
    else:
        _record_skip(
            state,
            source_name=src,
            skip_reason=result.skip_reason or "unknown_skip",
            sample_title=sample_title,
            canonical_url=result.canonical_url,
        )


def _record_skip(
    state: Dict[str, Any],
    *,
    source_name: str,
    skip_reason: str,
    sample_title: str,
    canonical_url: str,
) -> None:
    state["skip_total"] += 1
    state["skip_reason_counts"][skip_reason] = (
        state["skip_reason_counts"].get(skip_reason, 0) + 1
    )
    src = source_name or "(unknown)"
    state["per_source_counts"][src] = state["per_source_counts"].get(src, 0) + 1
    ps = state["per_source_skip_reason_counts"].setdefault(src, {})
    ps[skip_reason] = ps.get(skip_reason, 0) + 1
    bucket = state["samples_by_skip_reason"].setdefault(skip_reason, [])
    if len(bucket) < SAMPLE_LIMIT_PER_SKIP_REASON:
        bucket.append(
            {
                "source_name": src,
                "title": sample_title,
                "url": canonical_url,
            }
        )


# ---------------------------------------------------------------------------
# Recommended next integration block (LOCKED, immovable)
# ---------------------------------------------------------------------------


RECOMMENDED_NEXT_INTEGRATION: Dict[str, Any] = {
    "type": "separate_cli",
    "exact_entrypoint": {
        "file": "src/tools/run_nomotoke_rss_card_draft.py",
        "cmd": "python -m src.tools.run_nomotoke_rss_card_draft",
        "default_mode": "dry-run",
        "flags": {
            "--source": "live | logging | json",
            "--template": "allowlist (subset of RSS_ONLY_ALLOWED_TEMPLATES)",
            "--limit": "int",
            "--mode": "dry-run | draft  (draft 明示指定必須)",
        },
    },
    "exact_flow": [
        "1. load entries from --source",
        "2. result = src.nomotoke_rss_router.route_rss_entry_to_nomotoke_card(entry)",
        "3. if not result.matched: skip with explicit skip_reason",
        "4. category_id = resolve_category_id_from_template(result.template_key)  # config/categories.json fallback コラム",
        "5. if category_id is None: skip with reason='category_id_unresolved'",
        "6. html_payload = src.nomotoke_card_renderer.select_renderer(result.template_key)(result.would_render_call.data_preview)",
        "7. if is_duplicate_nomotoke_card(source_url, template_key, normalized_title): skip with 'duplicate'",
        "8. if --mode draft: WPClient.create_post(status='draft', categories=[category_id], source_url=canonical_url, caller='nomotoke_card_draft_cli', source_lane='nomotoke_card')",
        "9. emit JSON summary entry per processed item",
    ],
    "functions_to_add": [
        "route_entry_to_nomotoke_card(entry) -> RouteResult  (already exists in src/nomotoke_rss_router.py)",
        "extract_required_facts(entry, template_key) -> {facts, missing}  (thin helper over RouteResult)",
        "render_nomotoke_card(template_key, facts) -> html  (uses select_renderer)",
        "build_wp_draft_payload(route_result, html, category_id) -> payload",
        "is_duplicate_nomotoke_card(source_url, template_key, title) -> bool",
        "resolve_category_id_from_template(template_key) -> int | None  (config/categories.json + fallback コラム category_id)",
    ],
    "wp_payload_shape": {
        "title": "str",
        "content": "str (HTML)",
        "categories": "list[int]  -- MUST be category_id list, NEVER category names",
        "categories_rule": "WP に category name は渡さない。config/categories.json を引いて id_list に変換、解決不能なら draft 作らず skip with reason='category_id_unresolved'",
        "categories_fallback": "コラム category_id (resolved from config/categories.json)",
        "status": "draft",
        "source_url": "<canonical_url>",
        "caller": "nomotoke_card_draft_cli",
        "source_lane": "nomotoke_card",
        "extras_via_audit_log_only": [
            "template_key",
            "source_name",
            "required_facts (FULL — jsonl のみ、HTML comment には絶対入れない)",
            "extracted_facts (FULL — jsonl のみ)",
            "tier",
            "confidence",
        ],
        "rule": "WPClient は改造しない。標準 create_post 引数のみ使う",
    },
    "meta_policy": {
        "primary": "logs/nomotoke_card_draft_log.jsonl",
        "primary_contents": [
            "route_id",
            "template_key",
            "source_url",
            "source_url_hash",
            "required_facts (full)",
            "extracted_facts (full)",
            "tier",
            "confidence",
            "wp_post_id",
            "created_at",
        ],
        "secondary": "WP body の HTML comment",
        "secondary_contents_minimal": [
            "template_key",
            "source_url_hash",
            "route_id",
        ],
        "secondary_forbidden": [
            "required_facts full",
            "extracted_facts full",
            "tier",
            "confidence",
        ],
        "rule": "required_facts 全文は jsonl のみ。HTML comment には minimal information だけ。tests で検証",
    },
    "dedupe_keys": {
        "layer_1_required": "source_url 完全一致 (WPClient.find_recent_post_by_title 内蔵 dedupe を使う)",
        "layer_2_optional": "x_status_id 完全一致 (X URL の場合)",
        "layer_3_optional": "template_key + normalized_title 一致",
        "layer_4_required": "same-run dedupe set (CLI process scope, source_url normalized)",
        "decision": "layer_1 と layer_4 は MUST、layer_2/3 は CLI 内追加 check (best-effort)",
    },
    "downstream_behavior": {
        "guarded_publish": "既存 draft polling で自動 pick up (touch なし)",
        "publish_notice": "既存 review/hold/skip 通知に自動乗る (touch なし)",
        "rule": "001B では publish-notice / guarded-publish を直接呼ばない",
    },
    "manual_intake_difference": {
        "manual_intake": "user 指定 URL 1 件、operator on-demand",
        "nomotoke_card_draft_cli": "RSS / logging / json から複数 entry batch 化",
        "decision": "統合しない (責務が違う)",
    },
    "files_to_touch_in_001B": {
        "new": [
            "src/tools/run_nomotoke_rss_card_draft.py",
            "tests/test_nomotoke_rss_card_draft_cli.py",
        ],
        "extend_narrow": [
            "src/nomotoke_rss_router.py (extract_required_facts helper if needed)",
        ],
    },
    "files_not_to_touch_in_001B": [
        "src/rss_fetcher.py (HARD lock until 001C)",
        "src/wp_client.py (HARD lock)",
        "src/nomotoke_card_renderer.py (already complete)",
        "src/tools/manual_intake.py (separate ticket if needed)",
        "config/rss_sources.json",
        "env / Schedulers / Cloud Run / Dockerfile / cloudbuild_*.yaml",
        "publish-notice / guarded-publish / draft-body-editor jobs",
    ],
    "rollback_001B": [
        "delete the 2 new files",
        "or git revert <001B_commit>",
        "default --mode dry-run なので env / Scheduler 不変",
        "--mode draft 明示時のみ WP write、誤実行 risk 限定的",
    ],
    "acceptance_001B": [
        "--mode dry-run で WP write 0 確認 (test で WPClient.create_post mock 0 call assert)",
        "--mode draft で WP draft 作成、source_url meta 残る",
        "category name が WPClient.create_post に渡らないことを test で検証",
        "category_id 解決不能で skip='category_id_unresolved' 動作 test",
        "required_facts 全文が HTML comment に入らないことを test で検証",
        "dedupe layer 1+4 機能確認",
        "publish-notice/guarded-publish 既存 polling で pick up 確認 (24h観測)",
        "tests >= 20 cases (dry-run / draft mock / dedupe / required_facts skip / category_id_unresolved / Gemini 0 / WP write 0)",
    ],
    "promote_to_rss_fetcher_auto_001C": {
        "candidate_position": "rss_fetcher.py の candidate 準備後 / Gemini 前 / WP 前",
        "hold_until": "001B で 24h 実績取得後",
        "out_of_scope": "001A / 001B では rss_fetcher.py 編集禁止",
    },
}


# ---------------------------------------------------------------------------
# Why-not-suitable summary per blocked template
# ---------------------------------------------------------------------------


def _why_not_suitable() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tk in RSS_ONLY_BLOCKED_TEMPLATES:
        meta = QUALITY_CEILING_BY_TEMPLATE.get(tk, {})
        out[tk] = f"{meta.get('rss_only_quality', '?')}: {meta.get('reason', '')}"
    return out


def _if_low_hit_explanation(report: Dict[str, Any]) -> str:
    live = report.get("live_rss") or {}
    log = report.get("logging_72h") or {}
    live_hits = int(live.get("hit_total", 0) or 0)
    log_hits = int(log.get("hit_total", 0) or 0)
    if live_hits + log_hits >= 5:
        return ""
    notes = []
    if live_hits == 0:
        notes.append("live RSS で hit 0 — 13 source の見出し中、Giants 関連 entry が当該時刻には存在しない、または quote_short / pitcher_pair が抽出可能な headline が無い")
    if log.get("logging_sample_insufficient"):
        notes.append(
            f"Cloud Logging sample 不足 (fallback={log.get('logging_fallback_strategy', '')})"
        )
    if log_hits == 0 and not log.get("logging_sample_insufficient"):
        notes.append(
            "Cloud Logging sample に Giants 関連 source URL が含まれていたが quote_short / pregame keyword が title から regex 抽出不能"
        )
    notes.append(
        "RSS の supply 上限: title/summary だけでは構造データを取れない。"
        "manager_comment / player_comment は媒体側が「{選手名}「{quote}」」型タイトルを書くか次第。"
        "pregame_pitcher は NPB公式 / 球団公式の予告先発投稿が当該時刻に出ている時のみ hit。"
    )
    return "; ".join(notes)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.run_nomotoke_rss_card_dry_run",
        description=(
            "NOMOTOKE-RSS-CARD-001A dry-run observability. Live RSS + 72h "
            "Cloud Logging report. NEVER calls Gemini. NEVER writes WP."
        ),
    )
    p.add_argument(
        "--source",
        default="live,logging",
        help="comma-separated subset of {live,logging,json}",
    )
    p.add_argument("--out", default="", help="output JSON path; default = stdout")
    p.add_argument("--max-per-source", type=int, default=30)
    p.add_argument("--max-total", type=int, default=400)
    p.add_argument("--hours", type=int, default=72)
    p.add_argument(
        "--json-fixtures",
        default=str(ROOT / "tests" / "fixtures" / "nomotoke_rss_router"),
        help="dir of JSON fixture files for --source json",
    )
    p.add_argument(
        "--sources-file",
        default=str(ROOT / "config" / "rss_sources.json"),
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    sources = {s.strip() for s in (args.source or "").split(",") if s.strip()}

    report: Dict[str, Any] = {
        "schema_version": "nomotoke_rss_card_dry_run.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rss_only_allowed_templates": list(RSS_ONLY_ALLOWED_TEMPLATES),
        "rss_only_blocked_templates": list(RSS_ONLY_BLOCKED_TEMPLATES),
        "manual_intake_candidate_templates": [
            tk
            for tk, meta in QUALITY_CEILING_BY_TEMPLATE.items()
            if meta.get("allow_manual_intake")
        ],
        "structured_data_required_templates": [
            tk
            for tk, meta in QUALITY_CEILING_BY_TEMPLATE.items()
            if meta.get("allow_structured_data")
            and not meta.get("allow_rss_only")
        ],
        "quality_ceiling_by_template": QUALITY_CEILING_BY_TEMPLATE,
        "required_facts_by_template": REQUIRED_FACTS_BY_TEMPLATE,
        "skip_reason_taxonomy": list(SKIP_REASON_TAXONOMY),
        "live_rss": None,
        "logging_72h": None,
        "json_fixtures": None,
        "next_recommended_templates": [],
        "not_suitable_for_rss_templates": derive_not_suitable_for_rss(),
        "why_not_suitable": _why_not_suitable(),
        "if_low_hit_explanation": "",
        "recommended_next_integration": RECOMMENDED_NEXT_INTEGRATION,
    }

    if "live" in sources:
        report["live_rss"] = run_live_rss_pass(
            sources_file=Path(args.sources_file),
            max_per_source=args.max_per_source,
            max_total=args.max_total,
        )
    if "logging" in sources:
        report["logging_72h"] = run_logging_sample_pass(hours=args.hours)
    if "json" in sources:
        report["json_fixtures"] = run_json_fixture_pass(Path(args.json_fixtures))

    # combined recommendation across live + logging
    combined_template_counts: Dict[str, int] = {}
    combined_conf: Dict[str, Dict[str, int]] = {}
    for key in ("live_rss", "logging_72h", "json_fixtures"):
        block = report.get(key)
        if not block:
            continue
        for tk, n in (block.get("template_counts") or {}).items():
            combined_template_counts[tk] = combined_template_counts.get(tk, 0) + int(n)
        for tk, conf in (block.get("template_confidence_counts") or {}).items():
            target = combined_conf.setdefault(tk, {})
            for k, v in (conf or {}).items():
                target[k] = target.get(k, 0) + int(v)

    report["next_recommended_templates"] = derive_next_recommended(
        combined_template_counts,
        combined_conf,
    )
    report["if_low_hit_explanation"] = _if_low_hit_explanation(report)

    out_text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"wrote: {args.out}")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
