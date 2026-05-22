"""Tavily MCP (stdio 同梱) + Gemini 3.1 Flash Lite (Gemini API free tier) で
巨人関連の X 投稿案を生成する core モジュール。

設計方針 (2026-05-19 user lock、 model 2026-05-22 swap):
- 検索は Tavily MCP server (npx -y tavily-mcp@latest) を stdio 経由で
  embed する。 remote managed MCP は使わない。
- 生成は Gemini 3.1 Flash Lite を Gemini API free tier 経由。 paid 課金は
  発生させない (user 0 ドル制約)。 旧 gemma-4-31b-it から 2026-05-22 swap、
  free tier 1,500 RPD / 250K TPM 内で運用 (volume 試算 25 req/日 = 1.7%)。
- 出力は post 案の文字列を返すのみ。 mail 送信や WP 書き込みは行わ
  ない (Phase 1 spike scope)。
- spec 382 同様、 unverified 数字 / 引用 / 順位 を post 本文に入れ
  ない hard constraint を system prompt で明示する。
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional, Sequence


# 既定 query list. 巨人 specific topic で smoke を回すためのもの。
# 量は max 5 が default で Tavily free tier 1000 credits/月 に十分余裕。
DEFAULT_QUERIES: tuple[str, ...] = (
    "巨人 戸郷翔征 最新",
    "巨人 試合結果 直近",
    "巨人 マルティネス 守護神",
    "巨人 ファーム 注目選手",
    "巨人 怪我 復帰",
)


# Gemini API model id (2026-05-22 swap: gemma-4-31b-it → gemini-3.1-flash-lite、
# 両方 free tier、 paid 切替禁止 lock 維持)。 定数名は履歴互換のため温存。
GEMMA_MODEL_ID = "gemini-3.1-flash-lite"


SYSTEM_PROMPT = """あなたはヨシラバーという巨人ファン向けメディアの編集者です。
Tavily で巨人関連トピックを web 検索し、 X 投稿案を 1 件生成してください。

制約 (hard rule, 違反したら出力しないこと):
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


@dataclass(frozen=True)
class PostDraft:
    """1 query から生成された X 投稿案。"""

    query: str
    draft: str
    model: str = GEMMA_MODEL_ID
    error: Optional[str] = None


async def _generate_one_draft(
    gemini_client,  # google.genai.Client
    mcp_session,    # fastmcp client session
    query: str,
    *,
    model: str,
    temperature: float,
) -> PostDraft:
    """1 query に対する Gemma 4 生成。 例外時は error フィールドに格納。"""

    try:
        # Gemini SDK 経由で Gemma 4 を呼ぶ。 tools に MCP session を渡すと
        # 必要に応じて Tavily 検索を agentic に発火する。
        # (Google AI SDK の MCP integration は experimental、 API 変更可能性あり)
        response = await gemini_client.aio.models.generate_content(
            model=model,
            contents=(
                f"{SYSTEM_PROMPT}\n\n"
                f"調査して欲しいトピック: {query}\n\n"
                "Tavily で関連情報を検索した上で X 投稿案を 1 件生成してください。"
            ),
            config={
                "temperature": temperature,
                "tools": [mcp_session],
            },
        )
        text = (getattr(response, "text", None) or "").strip()
        return PostDraft(query=query, draft=text, model=model)
    except Exception as exc:  # noqa: BLE001 - smoke spike 段階では広く catch
        return PostDraft(query=query, draft="", model=model, error=repr(exc))


async def generate_post_drafts(
    *,
    gemini_api_key: str,
    tavily_api_key: str,
    queries: Optional[Sequence[str]] = None,
    model: str = GEMMA_MODEL_ID,
    temperature: float = 0.6,
    npx_command: str = "npx",
    tavily_mcp_package: str = "tavily-mcp@latest",
) -> list[PostDraft]:
    """Tavily MCP stdio embed + Gemma 4 で post 案を生成する。

    Tavily MCP は ``npx -y tavily-mcp@latest`` で subprocess 起動 (stdio
    transport)。 Node.js + npm が container に必要 (Phase 2 Dockerfile で
    install)。

    パラメータ:
        gemini_api_key: Gemini API key (Gemma 4 経由用)
        tavily_api_key: Tavily API key (Tavily MCP server 経由)
        queries: 検索 query 群。 None で DEFAULT_QUERIES。
        model: Gemini API model id。 既定は gemini-3.1-flash-lite。
        temperature: 生成 temperature。
        npx_command: npx の実行 path。 既定 ``npx``。
        tavily_mcp_package: tavily-mcp npm package 名 + version pin。

    戻り値: PostDraft list (query 数と同じ長さ)。
    """

    # 依存 import はこの関数内で行う。 import 失敗時に caller 側で
    # ImportError を扱えるようにする (CI / 環境で deps 未 install な
    # 場合の clean error)。
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
    from google import genai

    targets = list(queries) if queries is not None else list(DEFAULT_QUERIES)
    if not targets:
        return []

    transport = StdioTransport(
        command=npx_command,
        args=["-y", tavily_mcp_package],
        env={**os.environ, "TAVILY_API_KEY": tavily_api_key},
    )
    mcp_client = Client(transport)
    gemini_client = genai.Client(api_key=gemini_api_key)

    drafts: list[PostDraft] = []
    async with mcp_client:
        for query in targets:
            draft = await _generate_one_draft(
                gemini_client,
                mcp_client.session,
                query,
                model=model,
                temperature=temperature,
            )
            drafts.append(draft)
    return drafts


def generate_post_drafts_sync(**kwargs) -> list[PostDraft]:
    """``generate_post_drafts`` の同期 wrapper (CLI から呼びやすく)。"""
    return asyncio.run(generate_post_drafts(**kwargs))
