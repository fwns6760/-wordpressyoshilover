# 385-INGEST YouTube caption short quote summary

## meta

- ticket: 385-INGEST-youtube-caption-short-quote-summary
- status: LIVE_DEPLOYED_OBSERVE
- owner: Codex A
- lane: A
- priority: P0.5
- created: 2026-05-19
- github_issue: #60
- parent_ticket: 383-INGEST-youtube-source-articleize-fix

## user request

YouTube 記事の字幕引用が長くなりすぎるため、長い字幕全文風の 1 block ではなく、短い引用 + 要点表示に寄せる。

User lock:

- LLM でなくてもできる範囲を優先する。
- 推測で補わない。
- 記憶から再構成しない。
- silent skip しない。
- 自己評価で OK にしない。
- 証拠だけで判断する。

## current implementation evidence

- `src/youtube_caption_fetcher.py` uses `youtube-transcript-api`.
- `src/youtube_caption_fetcher.py` comment says LLM is not used.
- `src/youtube_caption_fetcher.py` joins caption segments and normalizes whitespace.
- `src/rss_fetcher.py` calls `fetch_youtube_caption(video_id, max_chars=_YOUTUBE_CAPTION_FETCH_MAX_CHARS, logger=logger)`.
- `_YOUTUBE_CAPTION_FETCH_MAX_CHARS = 1500`; this widens the caption material window before deterministic extraction.
- `src/rss_fetcher.py` appends one `<aside class="nomotoke-youtube-caption">` section with heading `📺 字幕抜粋`, source attribution, and YouTube embed.
- `src/rss_fetcher.py` then extracts max 2 short quotes and max 3 "要点" bullets from caption text only.

## scope

Implement YouTube caption presentation v2 only.

- Keep LLM off.
- Keep caption fetch source unchanged.
- Split caption text deterministically into sentences.
- Select up to 1-2 short quote excerpts from caption text only.
- Add short "要点" bullets from caption text only.
- Cap per-quote and per-bullet character length.
- Escape HTML.
- Keep source attribution and YouTube embed.
- Log explicit reasons when caption is unavailable, too short, or extraction falls back.

## write scope

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_youtube_caption_section.py`
- `doc/active/385-INGEST-youtube-caption-short-quote-summary.md`
- `doc/README.md`
- `doc/active/assignments.md`

## do not touch

- `src/youtube_caption_fetcher.py` unless tests prove the fetch boundary must change.
- `config/rss_sources.json`
- `config/youtube_ob_sources.json`
- Cloud Scheduler
- Cloud Run env / Secret Manager
- `RUN_DRAFT_ONLY`
- WP existing posts
- X live post
- frontend files

## acceptance

- YouTube caption section no longer renders a single long 600-char paragraph when sentence extraction succeeds.
- Caption section renders:
  - heading `📺 字幕抜粋`
  - quote block with max 1-2 short quote excerpts
  - "要点" list made only from caption sentences
  - source attribution
  - YouTube embed
- No LLM call is added.
- No inferred facts are generated outside selected caption text.
- Long captions are capped and do not appear verbatim in full.
- Existing skip behavior remains safe:
  - non-YouTube URL unchanged
  - existing marker unchanged
  - no video ID unchanged with log
  - no caption unchanged with log
  - caption fetch exception unchanged with log
- Tests pass:
  - `python3 -m unittest tests.test_rss_fetcher_youtube_caption_section tests.test_youtube_caption_fetcher tests.test_rss_fetcher_youtube_title_prefix tests.test_youtube_title_filter`
  - `python3 -m compileall src/rss_fetcher.py`
  - AST parse over touched Python files
  - `git diff --check`

## implementation summary

- Added deterministic caption sentence splitting in `src/rss_fetcher.py`.
- Added quote / summary selection from caption text only.
- Added max 2 quote excerpts and max 3 summary bullets.
- Widened the caption fetch material window from 600 to 1500 chars while keeping visible quote / bullet caps unchanged.
- Kept source attribution and YouTube embed.
- Kept LLM off.
- Added explicit fallback / skip logs for no extracted quote and no summary cases.
- Note: due concurrent 384 commit activity, the `src/rss_fetcher.py` implementation hunk is present in commit `620121c`; this ticket commit records the 385 ticket and regression tests.

## validation evidence

2026-05-19 local:

- `python3 -m unittest tests.test_rss_fetcher_youtube_caption_section tests.test_youtube_caption_fetcher tests.test_rss_fetcher_youtube_title_prefix tests.test_youtube_title_filter` passed: 47 tests.
- `python3 -m unittest tests.test_rss_fetcher_youtube_integration` passed: 15 tests.
- `python3 -m compileall src/rss_fetcher.py` passed.
- `python3 -m py_compile tests/test_rss_fetcher_youtube_caption_section.py` passed.
- AST parse passed for `src/rss_fetcher.py` and `tests/test_rss_fetcher_youtube_caption_section.py`.
- `git diff --check` passed for touched 385 files.

2026-05-19 follow-up local:

- `python3 -m unittest tests.test_rss_fetcher_youtube_caption_section tests.test_youtube_caption_fetcher tests.test_rss_fetcher_youtube_title_prefix tests.test_youtube_title_filter tests.test_rss_fetcher_youtube_integration` passed: 63 tests.
- `python3 -m compileall src/rss_fetcher.py` passed.
- `python3 -m py_compile tests/test_rss_fetcher_youtube_caption_section.py` passed.
- AST parse passed for `src/rss_fetcher.py` and `tests/test_rss_fetcher_youtube_caption_section.py`.
- `git diff --check` passed.
- Added regression test proving `fetch_youtube_caption(... max_chars=1500 ...)` is used.

## live evidence

2026-05-19 live deploy:

- Cloud Build `0752f06d-a07d-4fbc-ba62-4c49c99c8b41` SUCCESS.
- Image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:385-youtube-caption-24c1707` pushed.
- Cloud Run service `yoshilover-fetcher` deployed revision `yoshilover-fetcher-00438-k8l`.
- Traffic: `yoshilover-fetcher-00438-k8l` 100%.
- Service health: `GET /health` returned `OK`.
- New revision ERROR log check returned `[]`.
- Env / Secret / Scheduler / `RUN_DRAFT_ONLY` / WP existing posts / X / frontend were not changed.

2026-05-19 follow-up live deploy:

- Cloud Build `82719b1a-b443-4960-b0f2-bb1139df9845` SUCCESS.
- Image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:385-youtube-caption-1500-6904c98` pushed.
- Image digest `sha256:2d696966d794565f2ace305e61f2a91cdff40c41dca8c0124334b146cc0578be`.
- Cloud Run service `yoshilover-fetcher` deployed revision `yoshilover-fetcher-00441-xj8`.
- Traffic: `yoshilover-fetcher-00441-xj8` 100%.
- Service health: `GET /health` returned `OK`.
- New revision ERROR log check returned `[]`.
- Env / Secret / Scheduler / `RUN_DRAFT_ONLY` / WP existing posts / X / frontend were not changed.

## next action

Observe the next natural fire for `youtube_caption_section_appended` with `quote_count` / `summary_count`, then close GitHub Issue #60 if live article output matches acceptance.
