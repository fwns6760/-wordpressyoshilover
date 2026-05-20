"""WP front display helpers for OB / farm2 / farm3 subtypes — ticket 410 Phase 1.

Phase 1 scope (additive helpers, NOT yet wired into draft pipeline):
- build_subtype_badge_html(subtype) -> str | None
  記事ページ上部に表示する subtype badge (元巨人 / 2軍速報 / 3軍練習 等) の HTML
- build_source_attribution_block(subtype, source_url, source_name, ob_current_team=None) -> str
  出典帯 HTML。 OB は「元巨人 / 現所属 ◯◯」併記、 farm3 は「(※非公式)」明示

Phase 1 では本 module の関数は外部から呼ばれない (additive)。 Phase 2 で
src/guarded_publish_runner.py / src/nomotoke_card_renderer.py / src/article_parts_renderer.py
の draft 生成 path に inject する (推奨方式 B: draft 生成側 inject、 WP テーマ PHP 不可触)。

WP REST mutation 禁止 — 本 module は HTML 文字列を返すだけで、 既存 published 記事の
書き換えはしない。

See: docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md §4.6
"""

from __future__ import annotations

from html import escape


# subtype → badge 表示テキスト
_BADGE_LABEL_BY_SUBTYPE: dict[str, str] = {
    "ob": "元巨人",
    "farm2_result": "2軍速報",
    "farm2_lineup": "2軍スタメン",
    "farm3_practice": "3軍練習",
    "farm3_player": "3軍選手",
}

# badge color theme (CSS class suffix)
_BADGE_THEME_BY_SUBTYPE: dict[str, str] = {
    "ob": "ob",
    "farm2_result": "farm2",
    "farm2_lineup": "farm2",
    "farm3_practice": "farm3",
    "farm3_player": "farm3",
}

# 出典帯 prefix label
_ATTRIBUTION_PREFIX_BY_SUBTYPE: dict[str, str] = {
    "ob": "元巨人",
    "farm2_result": "2軍 イースタン",
    "farm2_lineup": "2軍 イースタン",
    "farm3_practice": "3軍 (※非公式)",
    "farm3_player": "3軍 (※非公式)",
}


SUPPORTED_SUBTYPES: frozenset[str] = frozenset(_BADGE_LABEL_BY_SUBTYPE)


def build_subtype_badge_html(subtype: str) -> str | None:
    """410 Phase 1: subtype badge HTML を返す.

    対象 subtype (ob / farm2_result / farm2_lineup / farm3_practice / farm3_player)
    以外は None を返す (非対象 subtype の draft には badge を inject しない設計)。
    """
    label = _BADGE_LABEL_BY_SUBTYPE.get(subtype)
    if not label:
        return None
    theme = _BADGE_THEME_BY_SUBTYPE.get(subtype, "default")
    safe_label = escape(label, quote=False)
    safe_theme = escape(theme, quote=True)
    return (
        f'<div class="nomotoke-subtype-badge nomotoke-subtype-badge--{safe_theme}">'
        f"{safe_label}"
        "</div>"
    )


def build_source_attribution_block(
    subtype: str,
    source_url: str,
    source_name: str,
    *,
    ob_current_team: str | None = None,
) -> str:
    """410 Phase 1: 出典帯 HTML を返す.

    対象 subtype 以外は空文字を返す (caller 側で既存 attribution path を使う前提)。
    OB の `ob_current_team` が指定された場合「元巨人 / 現所属 X」併記。
    """
    prefix = _ATTRIBUTION_PREFIX_BY_SUBTYPE.get(subtype)
    if not prefix:
        return ""
    theme = _BADGE_THEME_BY_SUBTYPE.get(subtype, "default")
    safe_theme = escape(theme, quote=True)
    safe_prefix = escape(prefix, quote=False)

    if subtype == "ob" and ob_current_team:
        safe_current = escape(ob_current_team.strip(), quote=False)
        prefix_html = (
            f'<span class="nomotoke-source-attribution__label">'
            f"{safe_prefix} / 現所属 {safe_current}"
            "</span>"
        )
    else:
        prefix_html = (
            f'<span class="nomotoke-source-attribution__label">'
            f"{safe_prefix}"
            "</span>"
        )

    safe_source_name = escape((source_name or "出典不明").strip(), quote=False)
    safe_source_url = escape((source_url or "").strip(), quote=True)
    if safe_source_url:
        source_html = (
            f'<a class="nomotoke-source-attribution__link" '
            f'href="{safe_source_url}" target="_blank" rel="noopener noreferrer">'
            f"出典: {safe_source_name}"
            "</a>"
        )
    else:
        source_html = (
            f'<span class="nomotoke-source-attribution__source">'
            f"出典: {safe_source_name}"
            "</span>"
        )

    return (
        f'<div class="nomotoke-source-attribution nomotoke-source-attribution--{safe_theme}">'
        f"{prefix_html}"
        f"{source_html}"
        "</div>"
    )


def is_supported_subtype(subtype: str) -> bool:
    """badge / 出典帯 対象 subtype かを返す."""
    return subtype in SUPPORTED_SUBTYPES


def maybe_prepend_subtype_display(
    body_html: str,
    subtype: str,
    *,
    source_url: str = "",
    source_name: str = "",
    ob_current_team: str | None = None,
) -> str:
    """410 Phase 2 wire-in helper: badge を本文先頭 / 出典帯 を本文末尾に挿入.

    対象 subtype (ob / farm2_result / farm2_lineup / farm3_practice / farm3_player)
    以外は body_html を不変で返す (additive no-op、 既存 subtype は副作用なし)。
    Idempotent: 既に同 badge / 出典帯 文字列が body_html に含まれている場合は重複追加しない
    (再 run / retry / 並走 enrich 経路で複数回呼ばれても安全)。
    """
    if not is_supported_subtype(subtype):
        return body_html
    safe_body = body_html or ""
    badge = build_subtype_badge_html(subtype)
    attribution = build_source_attribution_block(
        subtype, source_url, source_name, ob_current_team=ob_current_team
    )
    parts: list[str] = []
    if badge and badge not in safe_body:
        parts.append(badge)
        parts.append("\n")
    parts.append(safe_body)
    if attribution and attribution not in safe_body:
        parts.append("\n")
        parts.append(attribution)
    return "".join(parts)
