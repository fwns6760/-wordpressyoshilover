"""437 SVG → PNG dynamic eyecatch generator.

publishers (ranking_article_publisher / anomaly_article_publisher / postgame /
lineup) から呼ばれ、 data に応じて Jinja2 template を render して cairosvg で
PNG bytes に変換する。 失敗時は None を返し、 caller 側 publish 自体は続行する
(画像なし fallback)。

Phase 1A: ranking_table 1 template + cairosvg + jinja2 setup.
Phase 1B 以降で template 11 種追加 + format auto-routing。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_SIZE = 1080
PNG_MAX_BYTES = 500 * 1024  # 500KB — X / WP 帯域圧迫を回避
DEFAULT_FOOTER_HANDLE = "@yoshilover_giants"
DEFAULT_FOOTER_META = "巨人データ"


def _jinja_env():
    """Jinja2 Environment を返す。 import 失敗時は None。"""
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except Exception as exc:  # pragma: no cover - import error path
        logger.warning("[437] jinja2 import failed: %s", exc)
        return None
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(default_for_string=True, default=True),
        keep_trailing_newline=False,
    )


def render_svg(template_key: str, data: dict[str, Any]) -> str:
    """template_key (e.g. "ranking_table") + data dict を Jinja2 で render。

    file path: templates/x_post_<template_key>.svg
    raise: TemplateNotFound / TemplateSyntaxError on bad input.
    """
    env = _jinja_env()
    if env is None:
        raise RuntimeError("jinja2 not available")
    template = env.get_template(f"x_post_{template_key}.svg")
    return template.render(**data)


def svg_to_png(svg_text: str, size: int = DEFAULT_SIZE) -> bytes:
    """SVG string を cairosvg で 1080x1080 PNG bytes に変換。

    raise: RuntimeError if cairosvg / cairo native lib missing.
    """
    try:
        import cairosvg
    except Exception as exc:  # pragma: no cover - import error path
        raise RuntimeError(f"cairosvg not available: {exc}") from exc
    png_bytes = cairosvg.svg2png(
        bytestring=svg_text.encode("utf-8"),
        output_width=size,
        output_height=size,
    )
    if png_bytes is None:
        raise RuntimeError("cairosvg returned None")
    return bytes(png_bytes)


def generate_png(
    template_key: str,
    data: dict[str, Any],
    size: int = DEFAULT_SIZE,
) -> bytes | None:
    """publishers 向け entry point。

    Args:
        template_key: e.g. "ranking_table" → templates/x_post_ranking_table.svg
        data: Jinja2 context (template-specific keys)
        size: PNG output size (default 1080x1080)

    Returns:
        PNG bytes on success, None on any failure
        (caller fallback: publish 自体は image 無しで続行)。
    """
    try:
        svg_text = render_svg(template_key, data)
    except Exception as exc:
        logger.warning(
            "[437] generate_png render failed template=%s error=%s",
            template_key,
            exc,
        )
        return None
    try:
        png_bytes = svg_to_png(svg_text, size=size)
    except Exception as exc:
        logger.warning(
            "[437] generate_png cairosvg failed template=%s error=%s",
            template_key,
            exc,
        )
        return None
    if not png_bytes:
        logger.warning("[437] generate_png empty bytes template=%s", template_key)
        return None
    if len(png_bytes) > PNG_MAX_BYTES:
        logger.warning(
            "[437] generate_png size exceeded template=%s bytes=%d max=%d",
            template_key,
            len(png_bytes),
            PNG_MAX_BYTES,
        )
        return None
    return png_bytes


def build_ranking_data(
    *,
    title: str,
    subtitle: str,
    hook_line: str,
    rows: list[dict[str, Any]],
    footer_handle: str = DEFAULT_FOOTER_HANDLE,
    footer_meta: str = DEFAULT_FOOTER_META,
) -> dict[str, Any]:
    """ranking_table template 用 data dict を組む helper。

    rows は 8 件想定 (TOP 1-8)。 各 dict は:
        rank: int / str (e.g. 1, 2, "3")
        name: str (選手名、 全角)
        team: str (球団名、 e.g. "巨人")
        value: str (数値、 e.g. ".867")
        is_giants: bool (巨人 row 強調 ON/OFF)
    """
    return {
        "title": title,
        "subtitle": subtitle,
        "hook_line": hook_line,
        "rows": rows,
        "footer_handle": footer_handle,
        "footer_meta": footer_meta,
    }
