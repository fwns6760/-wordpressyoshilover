"""source_excerpt_refiner.py — 本文抜粋の読みどころ選択 (2026-07-10 user 依頼)。

背景: 本文抜粋 (nomotoke-source-excerpt) は記事冒頭の機械切り出しのため、
前置き・状況説明が先頭に来て、発言・核心の一節が抜粋に入らないことがある。
user「もっと洗練された引用文を」→ LLM による「読みどころ選択」を導入。

設計 (捏造ゼロ構造):
- LLM の仕事は「原文ママの連続一節を最大2つ選ぶ」だけ。生成文は一切使わない
- 採用条件 = whitespace 正規化した原文に連続部分文字列として実在すること
- 実在しない / 短すぎ / key なし / 例外 → 空を返し、caller は従来の冒頭抜粋を使う
- 合計字数は caller の max_chars (従来上限) を超えない
"""

from __future__ import annotations

import logging
import re

LOG = logging.getLogger("source_excerpt_refiner")

_MIN_PASSAGE_CHARS = 40


def _squash(text: str) -> str:
    """whitespace を除去した比較用文字列 (literal 判定は改行差を無視する)。"""
    return re.sub(r"\s+", "", text or "")


def parse_passages(raw: str) -> list[str]:
    """PASSAGE1/PASSAGE2 ラベル出力を一節 list に。ラベル無しは空 list。"""
    passages: list[str] = []
    for label in ("PASSAGE1", "PASSAGE2"):
        m = re.search(rf"{label}:\s*(.+?)(?=\nPASSAGE\d:|\Z)", raw or "", re.DOTALL)
        if m:
            text = m.group(1).strip()
            if text:
                passages.append(text)
    return passages


def verify_and_join(
    passages: list[str], long_text: str, *, max_chars: int
) -> str:
    """原文に実在する一節だけを採用して結合。全滅は ""。"""
    src_squashed = _squash(long_text)
    verified: list[str] = []
    for p in passages:
        if len(p) < _MIN_PASSAGE_CHARS:
            LOG.info("excerpt_refine_reject reason=too_short len=%d", len(p))
            continue
        if _squash(p) in src_squashed:
            verified.append(p)
        else:
            LOG.info("excerpt_refine_reject reason=not_literal len=%d", len(p))
    joined = "\n".join(verified)
    while verified and len(joined) > max_chars:
        verified.pop()
        joined = "\n".join(verified)
    if len(joined) < _MIN_PASSAGE_CHARS:
        return ""
    return joined


def refine_excerpt(
    long_text: str,
    *,
    title: str,
    max_chars: int,
    gemini_api_key: str,
) -> str:
    """記事本文から読みどころ一節 (原文ママ) を選んで返す。失敗は ""。"""
    if (
        not long_text
        or len(long_text) < _MIN_PASSAGE_CHARS
        or not gemini_api_key
    ):
        return ""
    from google import genai

    from src.x_post_branding_gen import (
        _X_POST_DATA_LLM_MODEL,
        _x_post_generate_content,
    )

    prompt = "\n".join([
        "あなたは読売ジャイアンツ専門メディアの編集者です。",
        "下の記事本文から、読者に一番刺さる「読みどころ」の一節を選んでください。",
        "",
        "【ルール (最重要)】",
        "- 原文から一字一句そのまま連続で抜き出す。書き換え・要約・文の結合・"
        "省略記号の追加は禁止。",
        "- 一節は 1〜2 個。1 個あたり 2〜5 文程度のまとまり。",
        "- 発言 (「」内) を含む一節を最優先。次に具体的な数字・場面描写。",
        "- 前置き・媒体の定型文・記事末の宣伝・関連記事一覧は選ばない。",
        f"- 記事の主題 ({title}) と直接関係する一節だけ選ぶ。",
        "",
        "出力形式 (ラベル必須、これ以外は書かない):",
        "PASSAGE1: <一節>",
        "PASSAGE2: <一節 (無ければ省略)>",
        "",
        "記事本文:",
        long_text,
    ])
    client = genai.Client(api_key=gemini_api_key)
    response = _x_post_generate_content(
        client,
        model=_X_POST_DATA_LLM_MODEL,
        contents=prompt,
        config={"temperature": 0.2},
    )
    raw = (getattr(response, "text", None) or "").strip()
    return verify_and_join(parse_passages(raw), long_text, max_chars=max_chars)
