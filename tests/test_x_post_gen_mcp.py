"""Mock-based tests for ``src.x_post_gen_mcp`` (ticket 391 Phase 1).

このテストは ``google-genai`` / ``fastmcp`` が CI 環境に install されて
いなくても通るよう、 sys.modules に fake module を差し込んだ後で
``src.x_post_gen_mcp`` を import する設計にしている。 これは 391 ticket
の \"$0 制約 + 軽量 smoke spike\" 方針に合わせるためで、 実 API 動作の
verify は user 側の WSL smoke で行う。
"""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock


def _ensure_fake_module(name: str) -> types.ModuleType:
    """sys.modules に fake module を差し込む helper。

    既に install されていればそのまま使う (尊重) し、 未 install なら
    `unittest.mock.MagicMock` を type として注入して `import name` が
    通るようにする。
    """
    if name in sys.modules and sys.modules[name] is not None:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ----- fake fastmcp ---------------------------------------------------------

_fastmcp = _ensure_fake_module("fastmcp")
if not hasattr(_fastmcp, "Client"):
    class _FakeFastMcpClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
            self.session = MagicMock(name="fastmcp.Client.session")

        async def __aenter__(self):  # noqa: ANN001
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

    _fastmcp.Client = _FakeFastMcpClient  # type: ignore[attr-defined]

_fastmcp_transports = _ensure_fake_module("fastmcp.client.transports")
if not hasattr(_fastmcp_transports, "StdioTransport"):
    class _FakeStdioTransport:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs

    _fastmcp_transports.StdioTransport = _FakeStdioTransport  # type: ignore[attr-defined]
    _ensure_fake_module("fastmcp.client").transports = _fastmcp_transports  # type: ignore[attr-defined]


# ----- fake google.genai ----------------------------------------------------

_google = _ensure_fake_module("google")
_google_genai = _ensure_fake_module("google.genai")
setattr(_google, "genai", _google_genai)
if not hasattr(_google_genai, "Client"):
    class _FakeGenaiClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self.aio = MagicMock(name="genai.Client.aio")

    _google_genai.Client = _FakeGenaiClient  # type: ignore[attr-defined]


# Now safe to import the module under test (after fake injection above).
import src.x_post_gen_mcp as xpg  # noqa: E402


class DefaultsTests(unittest.TestCase):
    def test_default_queries_are_giants_specific(self) -> None:
        # spec 382 hard rule: 巨人以外を扱わない。 default は全部「巨人」始まり。
        self.assertGreater(len(xpg.DEFAULT_QUERIES), 0)
        for q in xpg.DEFAULT_QUERIES:
            self.assertIn("巨人", q, f"query must mention 巨人: {q!r}")

    def test_gemma_model_id_is_31b(self) -> None:
        # 0 ドル制約 + user 指定: 2026-05-22 swap で gemma-4-31b-it →
        # gemini-3.1-flash-lite (両方 free tier、 paid 切替禁止 lock 維持)。
        self.assertEqual(xpg.GEMMA_MODEL_ID, "gemini-3.1-flash-lite")

    def test_system_prompt_forbids_url_hashtag(self) -> None:
        # spec 382 hard rule (URL / hashtag / 媒体名 禁止) が prompt に記述されている
        self.assertIn("URL", xpg.SYSTEM_PROMPT)
        self.assertIn("hashtag", xpg.SYSTEM_PROMPT)
        self.assertIn("未検証", xpg.SYSTEM_PROMPT)


class PostDraftDataclassTests(unittest.TestCase):
    def test_default_error_is_none(self) -> None:
        d = xpg.PostDraft(query="巨人 戸郷翔征", draft="サンプル")
        self.assertIsNone(d.error)
        self.assertEqual(d.model, xpg.GEMMA_MODEL_ID)

    def test_error_field_is_settable(self) -> None:
        d = xpg.PostDraft(query="q", draft="", error="boom")
        self.assertEqual(d.error, "boom")


class GenerateOneDraftTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_draft_text_on_success(self) -> None:
        response = MagicMock()
        response.text = "サンプル投稿案"
        gemini_client = MagicMock()
        gemini_client.aio.models.generate_content = AsyncMock(return_value=response)
        mcp_session = MagicMock()

        result = await xpg._generate_one_draft(
            gemini_client,
            mcp_session,
            "巨人 戸郷翔征",
            model="gemini-3.1-flash-lite",
            temperature=0.5,
        )

        self.assertEqual(result.query, "巨人 戸郷翔征")
        self.assertEqual(result.draft, "サンプル投稿案")
        self.assertIsNone(result.error)
        self.assertEqual(result.model, "gemini-3.1-flash-lite")
        gemini_client.aio.models.generate_content.assert_awaited_once()

    async def test_passes_mcp_session_as_tool(self) -> None:
        response = MagicMock()
        response.text = "x"
        gemini_client = MagicMock()
        gemini_client.aio.models.generate_content = AsyncMock(return_value=response)
        mcp_session = MagicMock()

        await xpg._generate_one_draft(
            gemini_client,
            mcp_session,
            "巨人 試合結果",
            model="gemini-3.1-flash-lite",
            temperature=0.6,
        )

        call = gemini_client.aio.models.generate_content.await_args
        self.assertIsNotNone(call)
        assert call is not None
        # tools に MCP session が渡っていること (Tavily 経由検索の hook)
        config = call.kwargs.get("config")
        self.assertIsNotNone(config)
        self.assertEqual(config["tools"], [mcp_session])
        self.assertAlmostEqual(config["temperature"], 0.6)
        self.assertEqual(call.kwargs["model"], "gemini-3.1-flash-lite")

    async def test_captures_exception_in_error_field(self) -> None:
        gemini_client = MagicMock()
        gemini_client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("rate limit"),
        )
        mcp_session = MagicMock()

        result = await xpg._generate_one_draft(
            gemini_client,
            mcp_session,
            "巨人 戸郷翔征",
            model="gemini-3.1-flash-lite",
            temperature=0.5,
        )

        self.assertEqual(result.query, "巨人 戸郷翔征")
        self.assertEqual(result.draft, "")
        self.assertIsNotNone(result.error)
        assert result.error is not None
        self.assertIn("rate limit", result.error)


class GeneratePostDraftsTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_query_list_returns_empty(self) -> None:
        # query が空なら API 呼ばずに空を返す (cost 0)
        drafts = await xpg.generate_post_drafts(
            gemini_api_key="fake",
            tavily_api_key="fake",
            queries=[],
        )
        self.assertEqual(drafts, [])

    async def test_query_count_equals_draft_count(self) -> None:
        # query 数 = 出力 PostDraft 数 の不変条件
        async def fake_generate(_gc, _mcp, query, *, model, temperature):
            return xpg.PostDraft(query=query, draft=f"draft-for-{query}", model=model)

        saved = xpg._generate_one_draft
        xpg._generate_one_draft = fake_generate  # type: ignore[assignment]
        try:
            drafts = await xpg.generate_post_drafts(
                gemini_api_key="fake-gemini",
                tavily_api_key="fake-tavily",
                queries=["q1", "q2", "q3"],
            )
        finally:
            xpg._generate_one_draft = saved  # type: ignore[assignment]

        self.assertEqual(len(drafts), 3)
        self.assertEqual([d.query for d in drafts], ["q1", "q2", "q3"])
        for d in drafts:
            self.assertTrue(d.draft.startswith("draft-for-"))
            self.assertIsNone(d.error)


if __name__ == "__main__":
    unittest.main()
