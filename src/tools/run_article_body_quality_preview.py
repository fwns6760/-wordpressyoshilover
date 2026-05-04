from __future__ import annotations

import argparse
import contextlib
import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src import rss_fetcher, title_validator
from src.article_quality_guards import (
    sanitize_forbidden_visible_text,
    find_generic_title_pattern,
    extract_grounded_team_names,
)
from src.article_quality_repair import ENTITY_MISMATCH_REPAIR_ENV_FLAG
from src.baseball_numeric_fact_consistency import extract_player_names
from src.wp_client import WPClient


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "docs" / "handoff" / "codex_responses" / "2026-05-04_lane_PP_body_quality_preview.tmp.md"

_HTML_BLOCK_RE = re.compile(r"<(h2|h3|p)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"[0-9０-９]+(?:[.\-/][0-9０-９]+)?(?:号|戦|試合|打点|本|球|回|失点|安打|連発|連続)?")
_NON_FACT_NAME_TOKENS = {
    "意見",
    "現状",
    "記録",
    "反応",
    "実施",
    "緊急登板",
}


@dataclass(frozen=True)
class CandidateManifest:
    post_id: int
    source_title: str
    source_url: str
    source_summary: str
    current_title_fallback: str
    current_body_fallback: str
    current_note: str
    proposed_body_seed: str
    article_subtype: str
    allow_derived_team_labels: tuple[str, ...] = ()


CANDIDATES: tuple[CandidateManifest, ...] = (
    CandidateManifest(
        post_id=64445,
        source_title="【巨人】松浦慶斗が初回から緊急リリーフ 大慌てで準備した舞台裏は… 先発・山崎伊織が２球で交代",
        source_url="https://twitter.com/hochi_giants/status/2050885171277099230",
        source_summary="先発の山崎伊織が2球で交代し、松浦慶斗が初回から緊急リリーフで入った。",
        current_title_fallback="【巨人】松浦慶斗が初回から緊急リリーフ 大慌てで準備した舞台裏は… 先発・山…",
        current_body_fallback="\n".join(
            [
                "【試合概要】",
                "松浦慶斗が初回から緊急リリーフした。",
                "【注目ポイント】",
                "山崎伊織が2球で交代した直後の継投に注目です。",
            ]
        ),
        current_note="WP REST GET unavailable in sandbox; current fields fall back to last-known incident ledger title and source-grounded seed excerpt.",
        proposed_body_seed="\n".join(
            [
                "【ニュースの整理】",
                "松浦慶斗が初回から緊急リリーフした。",
                "先発の山崎伊織が2球で交代した。",
                "【次の注目】",
                "この緊急登板が次の起用につながるかを見たいところです。",
            ]
        ),
        article_subtype="pregame",
    ),
    CandidateManifest(
        post_id=64443,
        source_title="【巨人】ドラ２・田和廉が球団新を更新する１２試合連続無失点 ７回２死満塁→中断→降雨コールドで記録継続",
        source_url="https://twitter.com/hochi_giants/status/2050891541141483536",
        source_summary="田和廉が12試合連続無失点を球団新に伸ばし、7回2死満塁で中断後も降雨コールドで記録を継続した。",
        current_title_fallback="ドラ２・田和廉が球団新を更新する１２試合連続無失点 ７回２死満塁→中断→降雨…",
        current_body_fallback="\n".join(
            [
                "【ニュースの整理】",
                "田和廉が12試合連続無失点を球団新に伸ばした。",
                "【次の注目】",
                "この記録が次戦でも続くか見たいところです。",
            ]
        ),
        current_note="WP REST GET unavailable in sandbox; current fields fall back to last-known incident ledger title and source-grounded seed excerpt.",
        proposed_body_seed="\n".join(
            [
                "【ニュースの整理】",
                "田和廉が球団新となる12試合連続無失点を続けた。",
                "7回2死満塁で中断し、そのまま降雨コールドで記録が継続した。",
                "【次の注目】",
                "この記録が次戦でも伸びるか見たいところです。",
            ]
        ),
        article_subtype="player",
    ),
    CandidateManifest(
        post_id=64461,
        source_title="ブルージェイズ・岡本和真が3戦連発の9号2ラン　9回に反撃の一発放つも及ばず、勝率5割復帰お預け",
        source_url="https://baseballking.jp/ns/694662/",
        source_summary="ブルージェイズで3試合連続本塁打となる9号2ランを放ち、9回に反撃したが勝率5割復帰はならなかった。",
        current_title_fallback="岡本和真、昇格・復帰 関連情報",
        current_body_fallback="\n".join(
            [
                "【故障・復帰の要旨】",
                "岡本和真の状態を整理する。",
                "【故障の詳細】",
                "読売ジャイアンツ所属の岡本和真は調整を続けている。",
                "【リハビリ状況・復帰見通し】",
                "巨人復帰後のプランを見る。",
                "【チームへの影響と今後の注目点】",
                "どこで復帰するか気になります。",
            ]
        ),
        current_note="WP REST GET unavailable in sandbox; fallback is the pre-manual-fix contaminated body family from Lane NN evidence. User note says live article was manually narrowed later.",
        proposed_body_seed="\n".join(
            [
                "【故障・復帰の要旨】",
                "岡本和真の状態を整理する。",
                "【故障の詳細】",
                "読売ジャイアンツ所属の岡本和真は調整を続けている。",
                "【リハビリ状況・復帰見通し】",
                "巨人復帰後のプランを見る。",
                "【チームへの影響と今後の注目点】",
                "どこで復帰するか気になります。",
            ]
        ),
        article_subtype="player_recovery",
        allow_derived_team_labels=("読売ジャイアンツ", "巨人"),
    ),
    CandidateManifest(
        post_id=64453,
        source_title="元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘れるくらい」",
        source_url="https://www.nikkansports.com/baseball/news/202605030000454.html",
        source_summary="ボクシング世界戦を見て、ラウンド中に息をするのも忘れるくらいだったと語った。",
        current_title_fallback="元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘…",
        current_body_fallback="\n".join(
            [
                "【ニュースの整理】",
                "上原浩治氏のコメントを整理する。",
                "【ここに注目】",
                "このコメントはファン必見です。",
                "【次の注目】",
                "この反応がどう広がるか気になります。",
            ]
        ),
        current_note="WP REST GET unavailable in sandbox; fallback excerpt uses the Lane OO/Lane NN evidence family.",
        proposed_body_seed="\n".join(
            [
                "【ニュースの整理】",
                "上原浩治氏のコメントを整理する。",
                "【ここに注目】",
                "このコメントはファン必見です。",
                "【次の注目】",
                "この反応がどう広がるか気になります。",
            ]
        ),
        article_subtype="general",
    ),
    CandidateManifest(
        post_id=64432,
        source_title="右アキレス腱炎からの復帰を目指す 投手がブルペン投球を実施",
        source_url="https://twitter.com/sanspo_giants/status/2051101291485733322",
        source_summary="右アキレス腱炎からの復帰を目指す投手がブルペン投球を実施した。",
        current_title_fallback="実施選手、昇格・復帰 関連情報",
        current_body_fallback="\n".join(
            [
                "【発信内容の要約】",
                "",
                "【文脈と背景】",
                "元記事の内容を確認中です。",
            ]
        ),
        current_note="WP REST GET unavailable in sandbox; fallback excerpt uses the Lane OO evidence family.",
        proposed_body_seed="\n".join(
            [
                "【発信内容の要約】",
                "",
                "【文脈と背景】",
                "元記事の内容を確認中です。",
            ]
        ),
        article_subtype="player",
    ),
)


def _strip_html(value: str) -> str:
    return _WS_RE.sub(" ", _HTML_TAG_RE.sub("", html.unescape(str(value or "")))).strip()


def _excerpt(value: str, limit: int = 300) -> str:
    clean = _strip_html(value)
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip(" ・、。") + "…"


def _extract_headers_from_text(text: str) -> list[str]:
    headers = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("【") and "】" in stripped:
            headers.append(stripped)
    return headers


def _extract_headers_from_html(body_html: str) -> list[str]:
    headers: list[str] = []
    for block_type, content in _HTML_BLOCK_RE.findall(str(body_html or "")):
        if block_type.lower() not in {"h2", "h3"}:
            continue
        header = _strip_html(content)
        if header:
            headers.append(header)
    return headers


def _html_from_body_text(body_text: str) -> str:
    lines = [line.strip() for line in str(body_text or "").splitlines()]
    blocks: list[str] = []
    heading_index = 0
    for line in lines:
        if not line:
            continue
        escaped = html.escape(line)
        if line.startswith("【") and "】" in line:
            level = 2 if heading_index == 0 else 3
            blocks.append(f"<h{level}>{escaped}</h{level}>")
            heading_index += 1
        else:
            blocks.append(f"<p>{escaped}</p>")
    return "\n".join(blocks)


def _body_text_from_html(body_html: str) -> str:
    lines: list[str] = []
    for block_type, content in _HTML_BLOCK_RE.findall(str(body_html or "")):
        text = _strip_html(content)
        if not text:
            continue
        if block_type.lower() in {"h2", "h3"}:
            lines.append(text if text.startswith("【") else f"【{text}】")
        else:
            lines.append(text)
    return "\n".join(lines).strip()


def _number_tokens(text: str) -> set[str]:
    return {match.group(0) for match in _NUMBER_RE.finditer(str(text or ""))}


def _filtered_name_tokens(text: str) -> set[str]:
    return {token for token in extract_player_names(text) if token not in _NON_FACT_NAME_TOKENS}


def _load_current_post(manifest: CandidateManifest) -> dict[str, object]:
    try:
        wp = WPClient()
    except Exception as exc:
        return {
            "fetch_status": "wp_client_unavailable",
            "fetch_error": f"{type(exc).__name__}: {exc}",
            "title": manifest.current_title_fallback,
            "body_text": manifest.current_body_fallback,
            "headers": _extract_headers_from_text(manifest.current_body_fallback),
            "excerpt": _excerpt(manifest.current_body_fallback),
            "title_source": "manifest_fallback",
            "body_source": "manifest_fallback",
        }

    try:
        post = wp.get_post(manifest.post_id)
    except Exception as exc:
        return {
            "fetch_status": "wp_fetch_failed",
            "fetch_error": f"{type(exc).__name__}: {exc}",
            "title": manifest.current_title_fallback,
            "body_text": manifest.current_body_fallback,
            "headers": _extract_headers_from_text(manifest.current_body_fallback),
            "excerpt": _excerpt(manifest.current_body_fallback),
            "title_source": "manifest_fallback",
            "body_source": "manifest_fallback",
        }

    title = (
        post.get("title", {}).get("raw")
        or post.get("title", {}).get("rendered")
        or manifest.current_title_fallback
    )
    body_html = (
        post.get("content", {}).get("raw")
        or post.get("content", {}).get("rendered")
        or ""
    )
    body_text = _body_text_from_html(body_html) or manifest.current_body_fallback
    headers = _extract_headers_from_html(body_html) or _extract_headers_from_text(body_text)
    return {
        "fetch_status": "wp_fetch_ok",
        "fetch_error": "",
        "title": _strip_html(title),
        "body_text": body_text,
        "headers": headers,
        "excerpt": _excerpt(body_text),
        "title_source": "wp_rest",
        "body_source": "wp_rest",
    }


@contextlib.contextmanager
def _preview_flags_enabled() -> Iterable[None]:
    flag_values = {
        "ENABLE_FORBIDDEN_PHRASE_FILTER": "1",
        "ENABLE_TITLE_GENERIC_COMPOUND_GUARD": "1",
        "ENABLE_QUOTE_INTEGRITY_GUARD": "1",
        "ENABLE_DUPLICATE_SENTENCE_GUARD": "1",
        "ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "1",
        "ENABLE_SOURCE_GROUNDING_STRICT": "1",
        "ENABLE_H3_COUNT_GUARD": "1",
        ENTITY_MISMATCH_REPAIR_ENV_FLAG: "1",
    }
    original = {key: os.environ.get(key) for key in flag_values}
    try:
        os.environ.update(flag_values)
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _apply_title_preview(current_title: str, source_title: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    proposed_title = sanitize_forbidden_visible_text(current_title).strip() or current_title.strip()
    weak_subject, weak_subject_reason = title_validator.is_weak_subject_title(proposed_title)
    weak_generated, weak_generated_reason = title_validator.is_weak_generated_title(proposed_title)
    generic_hit = find_generic_title_pattern(proposed_title)
    if generic_hit or weak_subject or weak_generated:
        _, preview_title = rss_fetcher._prepare_source_title_context(source_title, {})
        preview_title = preview_title.strip()
        if preview_title and preview_title != proposed_title:
            removed.append(proposed_title)
            proposed_title = preview_title
    if weak_subject and weak_subject_reason:
        removed.append(f"weak_subject:{weak_subject_reason}")
    if weak_generated and weak_generated_reason:
        removed.append(f"weak_generated:{weak_generated_reason}")
    return proposed_title, list(dict.fromkeys(filter(None, removed)))


def _validate_body(title: str, body_text: str, article_subtype: str, source_title: str, source_summary: str) -> dict[str, object]:
    return rss_fetcher._evaluate_post_gen_validate(
        body_text,
        article_subtype=article_subtype,
        title=title,
        source_refs={
            "source_title": source_title,
            "source_summary": source_summary,
        },
        rendered_html=rss_fetcher._render_preview_body_html(body_text),
    )


def _preview_candidate(manifest: CandidateManifest) -> dict[str, object]:
    current = _load_current_post(manifest)
    current_title = str(current["title"] or manifest.current_title_fallback).strip()
    current_body_text = str(current["body_text"] or manifest.current_body_fallback)
    proposed_title, removed_title_items = _apply_title_preview(current_title, manifest.source_title)
    proposed_body_text = sanitize_forbidden_visible_text(manifest.proposed_body_seed or current_body_text)
    removed_strings: list[str] = []
    if proposed_body_text != (manifest.proposed_body_seed or current_body_text):
        source_lines = set(str(manifest.proposed_body_seed or current_body_text).splitlines())
        target_lines = set(proposed_body_text.splitlines())
        removed_strings.extend(sorted(line for line in source_lines - target_lines if line.strip()))

    validation_before_repair = _validate_body(
        proposed_title,
        proposed_body_text,
        manifest.article_subtype,
        manifest.source_title,
        manifest.source_summary,
    )
    repair_result = None
    if any(str(axis).startswith("entity_mismatch:") for axis in validation_before_repair["fail_axes"]):
        repair_result = rss_fetcher._maybe_apply_entity_mismatch_repair(
            title=proposed_title,
            body_text=proposed_body_text,
            body_html=_html_from_body_text(proposed_body_text),
            source_title=manifest.source_title,
            source_summary=manifest.source_summary,
            article_subtype=manifest.article_subtype,
            source_refs={
                "source_title": manifest.source_title,
                "source_summary": manifest.source_summary,
            },
        )
    flag_hits = list(validation_before_repair["fail_axes"])
    if repair_result is not None:
        flag_hits.extend(f"repair:{flag}" for flag in repair_result.get("repair_flags", ()))
        removed_strings.extend(str(item) for item in repair_result.get("removed_strings", ()) if str(item).strip())
        if repair_result.get("applied"):
            proposed_title = str(repair_result.get("title") or proposed_title)
            proposed_body_text = str(repair_result.get("body_text") or proposed_body_text)
            validation_after = dict(repair_result["validation"])
        else:
            validation_after = dict(repair_result["validation"])
    else:
        validation_after = dict(validation_before_repair)

    source_text = "\n".join(part for part in (manifest.source_title, manifest.source_summary) if part)
    source_names = _filtered_name_tokens(source_text)
    proposed_names = _filtered_name_tokens(f"{proposed_title}\n{proposed_body_text}")
    source_teams = extract_grounded_team_names(source_text)
    proposed_teams = extract_grounded_team_names(f"{proposed_title}\n{proposed_body_text}")
    source_numbers = _number_tokens(source_text)
    proposed_numbers = _number_tokens(f"{proposed_title}\n{proposed_body_text}")

    extra_names = sorted(name for name in proposed_names if name not in source_names)
    extra_teams = sorted(
        team
        for team in proposed_teams
        if team not in source_teams and team not in set(manifest.allow_derived_team_labels)
    )
    extra_numbers = sorted(number for number in proposed_numbers if number not in source_numbers)
    no_new_fact_ok = not extra_names and not extra_teams and not extra_numbers

    preserved_fact_tokens = sorted(
        token
        for token in set(
            [manifest.source_title]
            + sorted(source_names)
            + sorted(source_teams)
            + sorted(source_numbers)
        )
        if token and token in f"{proposed_title}\n{proposed_body_text}"
    )

    residual_risks: list[str] = []
    if current["fetch_status"] != "wp_fetch_ok":
        residual_risks.append("current_wp_rest_fetch_unavailable")
    if manifest.post_id == 64432:
        residual_risks.append("subject_still_unconfirmed_from_source_only")
    if manifest.post_id == 64453:
        residual_risks.append("ob_non_baseball_relevance_remains_review_only")
    if manifest.post_id == 64461 and manifest.allow_derived_team_labels:
        residual_risks.append("derived_former_giants_affiliation_label")
    if validation_after["fail_axes"]:
        residual_risks.extend(str(axis) for axis in validation_after["fail_axes"])

    return {
        "post_id": manifest.post_id,
        "source_title": manifest.source_title,
        "source_url": manifest.source_url,
        "current_title": current_title,
        "current_title_source": current["title_source"],
        "current_body_excerpt": current["excerpt"],
        "current_headers": current["headers"],
        "current_note": manifest.current_note,
        "wp_fetch_status": current["fetch_status"],
        "wp_fetch_error": current["fetch_error"],
        "proposed_title": proposed_title,
        "proposed_body_excerpt": _excerpt(proposed_body_text),
        "proposed_headers": _extract_headers_from_text(proposed_body_text),
        "removed_strings": list(dict.fromkeys(filter(None, removed_title_items + removed_strings))),
        "preserved_facts": preserved_fact_tokens,
        "no_new_fact_ok": no_new_fact_ok,
        "no_new_fact_details": {
            "extra_names": extra_names,
            "extra_teams": extra_teams,
            "extra_numbers": extra_numbers,
            "allowed_derived_team_labels": list(manifest.allow_derived_team_labels),
        },
        "residual_risks": residual_risks,
        "flag_hits_before_repair": validation_before_repair["fail_axes"],
        "flag_hits_after_preview": validation_after["fail_axes"],
        "repair_applied": bool(repair_result and repair_result.get("applied")),
    }


def _render_markdown(results: list[dict[str, object]]) -> str:
    lines = [
        "# Lane PP body quality preview (dry run)",
        "",
        "- mode: preview-only / no WP write / no publish mutation",
        "- flags: Lane OO 6 + Lane PP 2 enabled only inside this process",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"## {result['post_id']}",
                "",
                f"- source title: `{result['source_title']}`",
                f"- source URL: `{result['source_url']}`",
                f"- current title ({result['current_title_source']}): `{result['current_title']}`",
                f"- current body excerpt: `{result['current_body_excerpt']}`",
                f"- current section headers: {json.dumps(result['current_headers'], ensure_ascii=False)}",
                f"- current note: {result['current_note']}",
                f"- wp fetch: `{result['wp_fetch_status']}`",
            ]
        )
        if result["wp_fetch_error"]:
            lines.append(f"- wp fetch error: `{result['wp_fetch_error']}`")
        lines.extend(
            [
                f"- proposed title: `{result['proposed_title']}`",
                f"- proposed body excerpt: `{result['proposed_body_excerpt']}`",
                f"- proposed section headers: {json.dumps(result['proposed_headers'], ensure_ascii=False)}",
                f"- removed strings: {json.dumps(result['removed_strings'], ensure_ascii=False)}",
                f"- preserved facts: {json.dumps(result['preserved_facts'], ensure_ascii=False)}",
                f"- no new fact ok: `{result['no_new_fact_ok']}`",
                f"- no new fact details: {json.dumps(result['no_new_fact_details'], ensure_ascii=False)}",
                f"- residual risks: {json.dumps(result['residual_risks'], ensure_ascii=False)}",
                f"- flag hits before repair: {json.dumps(result['flag_hits_before_repair'], ensure_ascii=False)}",
                f"- flag hits after preview: {json.dumps(result['flag_hits_after_preview'], ensure_ascii=False)}",
                f"- repair applied: `{result['repair_applied']}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run article body quality preview for 5 candidate posts.")
    parser.add_argument("--post-id", dest="post_ids", action="append", type=int, help="Preview only the specified post_id.")
    parser.add_argument("--output", type=Path, default=None, help="Optional markdown output path.")
    args = parser.parse_args(argv)

    selected_ids = set(args.post_ids or [])
    manifests = [item for item in CANDIDATES if not selected_ids or item.post_id in selected_ids]
    with _preview_flags_enabled():
        results = [_preview_candidate(item) for item in manifests]
    rendered = _render_markdown(results)
    output_path = args.output
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
