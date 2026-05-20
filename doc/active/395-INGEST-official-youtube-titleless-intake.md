# 395-INGEST official YouTube titleless intake

## meta

- ticket: 395-INGEST-official-youtube-titleless-intake
- status: LIVE_DEPLOYED_OBSERVE
- owner: Codex A
- lane: A
- priority: P0.5
- created: 2026-05-20
- github_issue: #72
- parent_ticket: 383-INGEST-youtube-source-articleize-fix

## user request

YouTube の取り込みもしてほしい。

## root cause

383 で YouTube source の articleize path は復旧したが、公式 YouTube でも
title に `巨人` / `ジャイアンツ` / 明確な roster / OB 名がない動画は
`youtube_title_filter_skip reason=no_match` で落ちていた。

Live evidence:

- 2026-05-20 09:03 JST natural fire
- source: `読売ジャイアンツYouTube公式`
- title: `小林の肩 vs 朝井の声`
- URL: `https://www.youtube.com/watch?v=CwnwPRKfers`
- result: `youtube_title_filter_skip reason=no_match`

## scope

Official Giants YouTube source intake only.

- Let `official_video_source` YouTube sources pass the YouTube relevance gate even when the title has no Giants keyword.
- Keep non-official YouTube sources on the existing title filter:
  - Giants keyword
  - active Giants player
  - Giants OB
- Keep YouTube caption formatting from 385 unchanged.
- Keep articleization path from 383 unchanged.

## write scope

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_youtube_integration.py`
- `doc/active/395-INGEST-official-youtube-titleless-intake.md`
- `doc/README.md`
- `doc/active/assignments.md`

## do not touch

- `config/rss_sources.json`
- `config/youtube_ob_sources.json`
- Cloud Scheduler
- Cloud Run env / Secret Manager
- `RUN_DRAFT_ONLY`
- WP existing posts
- X live post
- frontend files

## implementation summary

- Added `_check_youtube_giants_filter_for_source(...)`.
- If source roles include `official_video_source`, the YouTube title gate returns
  `(True, "official_video_source")`.
- Existing `_check_youtube_giants_filter(...)` remains unchanged for non-official sources.
- Wired the source-aware filter into the rss_fetcher source loop.
- Added regression tests:
  - official Giants YouTube source passes with `小林の肩 vs 朝井の声`
  - non-official YouTube source still skips unrelated `メジャー大谷総決算`

## validation evidence

2026-05-20 local:

- `python3 -m unittest tests.test_rss_fetcher_youtube_integration tests.test_youtube_title_filter tests.test_rss_fetcher_youtube_caption_section tests.test_youtube_caption_fetcher` passed: 59 tests.
- `python3 -m compileall src/rss_fetcher.py tests/test_rss_fetcher_youtube_integration.py` passed.
- `python3 -m py_compile tests/test_rss_fetcher_youtube_integration.py` passed.
- AST parse passed for `src/rss_fetcher.py` and `tests/test_rss_fetcher_youtube_integration.py`.
- `git diff --check -- src/rss_fetcher.py tests/test_rss_fetcher_youtube_integration.py` passed.
- commit `43b101a` (`395: allow official YouTube weak-title intake`).
- Cloud Build `c3ee2df3-1dee-4c04-867e-409b929c9b09` SUCCESS.
- image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:395-official-youtube-43b101a`.
- image digest `sha256:44ecb346e26631233f9d5ff58395275f83cf63d4c63ac08eaf38791de5c457e7`.
- Cloud Run service `yoshilover-fetcher` deployed to revision `yoshilover-fetcher-00448-5zr`, latest revision 100% traffic.
- `/health` returned `OK`.
- Cloud Run log: startup TCP probe succeeded; new revision ERROR log count 0.

## live evidence

Deploy verified. Natural fire observation is still pending.

Expected evidence:

- `読売ジャイアンツYouTube公式` titleless / weak-title videos no longer log
  `youtube_title_filter_skip reason=no_match`.
- If the source is fresh and not duplicate, it proceeds to draft creation and
  fetcher inline draft notice.

## next action

Observe the next natural fire and verify that official Giants YouTube weak-title
videos no longer stop at `youtube_title_filter_skip reason=no_match`.
