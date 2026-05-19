"""392: ヨシラバー branding X 投稿案を Gemma 4 + Tavily HTTP REST で生成。

391 (Phase 1 CLI) で smoke 確認した方法を本番 ``x-post-mail-lane`` に
組み込むための core モジュール。 stdio MCP ではなく **Tavily REST direct**
を採用 (既存 ``Dockerfile.x_post_mail`` に Node を追加せず、 image / cold
start 不変)。

設計方針 (2026-05-19 user lock):

- 検索は ``POST https://api.tavily.com/search`` で HTTP REST 直叩き。
  fastmcp / Node は使わない。
- 生成は Gemini API 経由 Gemma 4 31B (free tier)。 paid 切替禁止。
- spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) を
  system prompt + post-gen regex validator の二段で gate。
- 失敗時は ``None`` 返却 (silent skip)。 caller (``run_x_post_mail.py``) は
  既存 mail を絶対に止めない。
- 任意で ``insight.db`` 由来の DB 照合済み数字を RAG として注入できる。
"""

from __future__ import annotations

import hashlib as _hashlib
import logging as _logging
import re as _re
from typing import Optional

# 既存 ``x_post_mail_lane`` の Candidate / 共通 helper を再利用する。
from src.x_post_mail_lane import (
    Candidate,
    X_CHAR_LIMIT,
    _finalize_post_text,
    _is_safe_post_text,
    _is_verified_full_giants_player_name,
)


# Gemini API 経由 Gemma 4 31B model id (391 smoke で動作確認済)
_GEMMA_BRANDING_METRIC = "GEMMA_BRANDING"
_GEMMA_BRANDING_MODEL = "gemma-4-31b-it"


# spec 382 hard rule の追加 gate (既存 ``_FORBIDDEN_POST_TERMS`` の上に積む)
_GEMMA_BRANDING_FORBIDDEN_PATTERNS = (
    _re.compile(r"https?://"),
    _re.compile(r"#\S+"),
    _re.compile(r"ヨシラバー(で|を|に)?整理しました"),
    _re.compile(r"Xでは|X上では|みんなの声"),
)


_SYSTEM_PROMPT = """あなたはヨシラバーという巨人ファン向けメディアの編集者です。
Tavily で巨人関連トピックを web 検索し、 X 投稿案を 1 件生成してください。

制約 (hard rule、 違反したら出力しないこと):
- 媒体名・記事 URL・hashtag・「ヨシラバーで整理しました」を含めない
- 未検証の数字・引用・順位・打率・防御率・OPS・本塁打数・打点・回数を含めない
- DB 照合できない数字は generalize する (例: 「打率.160」→「打率の数字」)
- ヨシラバー独自の framing で書く。記事タイトルのコピーは禁止
- 280 文字以内
- 巨人ファンが続きを見たくなる hook を入れる
- 巨人以外の球団選手の話題は除外
- 公開済み MLB の元巨人 OB (菅野・岡本等) は OK、 非元巨人 MLB は NG

出力形式: post 本文のみ。 説明や前置きは書かない。
"""


def _tavily_search(
    query: str,
    api_key: str,
    *,
    max_results: int = 3,
    timeout_seconds: int = 30,
) -> list[dict]:
    """Tavily REST API 検索。

    成功時は result dict list を返す。 network / 4xx / 5xx / JSON parse 失敗
    時は空 list 返却 (caller は no context として skip 判断する)。
    """
    if not query or not api_key:
        return []
    try:
        import requests
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
            timeout=timeout_seconds,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    return results


def _gemma_branding_safety_check(text: str) -> bool:
    """spec 382 hard rule gate for Gemma branding output.

    True = safe (pass). False = violation (caller drops the candidate)。
    """
    if not text or not text.strip():
        return False
    if len(text) > X_CHAR_LIMIT:
        return False
    for pattern in _GEMMA_BRANDING_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return False
    if not _is_safe_post_text(text):
        return False
    return True


def _format_tavily_context(results: list[dict], *, snippet_len: int = 300) -> str:
    lines = []
    for r in results:
        title = str(r.get("title") or "").strip()
        content = str(r.get("content") or "").strip()
        if not title and not content:
            continue
        lines.append(f"- {title}: {content[:snippet_len]}")
    return "\n".join(lines)


def build_gemma_branding_candidate(
    player_name: str,
    *,
    gemini_api_key: str,
    tavily_api_key: str,
    db_fact_line: str = "",
    max_tavily_results: int = 3,
    timeout_seconds: int = 30,
    model_id: str = _GEMMA_BRANDING_MODEL,
    temperature: float = 0.6,
    logger: Optional[_logging.Logger] = None,
) -> Optional[Candidate]:
    """Tavily REST 検索 + Gemma 4 31B 生成で 1 件の Candidate を返す。

    silent skip 条件 (``None`` 返却):
    - player_name 不正 / 巨人 roster 不一致
    - API key 不足
    - Tavily 失敗 (factual ground 無し → hallucination 抑制のため生成しない)
    - Gemma 失敗 (rate limit / network 等)
    - 空生成 / spec 382 hard rule 違反 (validator drop)
    """
    log = logger or _logging.getLogger("x_post_branding_gen")
    player = str(player_name or "").strip()
    if not player or not gemini_api_key or not tavily_api_key:
        log.info("gemma_branding_skip reason=missing_input player=%r", player)
        return None
    if not _is_verified_full_giants_player_name(player):
        log.info("gemma_branding_skip reason=not_verified_giants_player player=%r", player)
        return None

    # 1. Tavily 検索 (factual ground)
    query = f"巨人 {player} 最新"
    results = _tavily_search(
        query,
        tavily_api_key,
        max_results=max_tavily_results,
        timeout_seconds=timeout_seconds,
    )
    if not results:
        log.warning(
            "gemma_branding_skip reason=no_tavily_results query=%r player=%s",
            query,
            player,
        )
        return None
    context = _format_tavily_context(results)
    if not context:
        log.warning(
            "gemma_branding_skip reason=empty_tavily_context query=%r player=%s",
            query,
            player,
        )
        return None

    # 2. Gemma 4 生成
    prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"対象選手: {player}\n\n"
        f"DB 照合済み数字 (使ってよい数字): {db_fact_line or 'なし'}\n\n"
        f"Tavily 検索結果 (context、 ここから不検証数字 / 引用 / 媒体名 / URL は使わない):\n"
        f"{context}\n\n"
        "上記情報を踏まえて、 ヨシラバー独自の framing で X 投稿案を 1 件、 本文のみ書いてください。"
    )
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - silent skip is the fault-tolerance contract
        log.warning(
            "gemma_branding_skip reason=gemini_error player=%s err=%r",
            player,
            exc,
        )
        return None

    text = _finalize_post_text(text)

    # 3. spec 382 hard rule validator
    if not _gemma_branding_safety_check(text):
        log.warning(
            "gemma_branding_skip reason=safety_check_failed player=%s text_preview=%r",
            player,
            text[:60],
        )
        return None

    # 4. Candidate dataclass
    signature_hash = _hashlib.sha1(
        f"gemma_branding|{player}|{text[:80]}".encode("utf-8")
    ).hexdigest()[:16]
    draft_lines = [
        "【根拠: Gemma 4 + Tavily HTTP REST + 任意 DB 参照】",
        f"対象選手: {player}",
        f"検索 query: {query}",
        f"Tavily 結果数: {len(results)}",
        f"DB fact 注入: {'あり' if db_fact_line else 'なし'}",
        f"model: {model_id}",
        "",
        "【Tavily 検索結果 snippet】",
        context,
    ]
    if db_fact_line:
        draft_lines.extend(["", "【DB fact line】", db_fact_line])
    log.info(
        "gemma_branding_candidate_built player=%s tavily_results=%d text_len=%d",
        player,
        len(results),
        len(text),
    )
    return Candidate(
        title=f"Gemma 4 branding｜{player}",
        metric=_GEMMA_BRANDING_METRIC,
        period_label="LLM 生成",
        draft_text="\n".join(draft_lines),
        post_text=text,
        char_count=len(text),
        signature=f"gemma_branding|{signature_hash}|False|None",
        focus_player=player,
        source_material_type="gemma_branding",
    )
