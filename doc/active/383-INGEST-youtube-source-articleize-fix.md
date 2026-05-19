# 383-INGEST YouTube source articleize fix

## meta

- ticket: 383-INGEST-youtube-source-articleize-fix
- status: REVIEW_NEEDED
- owner: Codex A
- lane: A
- priority: P0.5
- created: 2026-05-19
- github_issue: #58
- related_ticket: 344-INGEST-youtube-caption-draft-expansion

## user report

チケット 344 の YouTube 記事が出ない。

## root cause

YouTube channel source は取得自体は成功していたが、`config/rss_sources.json`
上の role が `media_quote_only` だったため、`src/rss_fetcher.py` の source loop
で `media_quote_pool` に入ったあと記事化処理へ進まず `continue` されていた。

そのため 344 で追加した以下の処理に到達していなかった。

- YouTube title filter
- YouTube caption section append
- `【YouTube】` title prefix
- WP draft / publish gate path

Cloud Logging evidence:

- `tag_scraper_per_source.youtube_channel=27`
- YouTube URL の `[SOURCE]` log は出ている
- `youtube_caption_section_appended` は 2026-05-18 以降 0 件
- `youtube_title_filter_skip` は 2026-05-18 以降 0 件

## scope

Fix the 344 connection bug only.

- Keep non-YouTube `media_quote_only` sources pool-only.
- Allow `tag_scrape` + `scraper=youtube_channel` sources to enter the articleize path.
- Expand reviewable `config/youtube_ob_sources.json` sources into fetcher sources at runtime so Phase 1b channel additions are actually used.
- Preserve title filter, caption fetch, history dedupe, publish gates, and `RUN_DRAFT_ONLY=True` behavior.

## write scope

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_youtube_integration.py`
- `doc/active/383-INGEST-youtube-source-articleize-fix.md`
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

- Added `_should_articleize_source(...)`.
  - YouTube channel scraper sources can articleize even with `media_quote_only`.
  - Other `media_quote_only` sources remain pool-only.
- Added `_expand_sources_with_youtube_registry(...)`.
  - Runtime-expands confirmed / candidate sources from `youtube_ob_sources.json`.
  - Skips excluded sources and avoids duplicate channel IDs.
  - Uses conservative default `max_age_days=2`, `article_limit=5` for registry-added channels.
- Wired source expansion immediately after `rss_sources.json` load.

## acceptance

- YouTube channel entries no longer stop at `media_quote_pool` only.
- Existing non-YouTube `media_quote_only` behavior is unchanged.
- `youtube_ob_sources.json` Phase 1b channels become visible to `rss_fetcher` without duplicating them in `rss_sources.json`.
- Tests pass:
  - `python3 -m unittest tests.test_rss_fetcher_youtube_integration tests.test_rss_fetcher_youtube_caption_section tests.test_rss_fetcher_youtube_title_prefix tests.test_youtube_caption_fetcher tests.test_youtube_title_filter tests.test_youtube_ob_source_registry`
  - `python3 -m unittest tests.test_rss_fetcher tests.test_tag_page_scraper tests.test_rss_fetcher_youtube_integration`
  - `python3 -m compileall src/rss_fetcher.py`
  - AST parse over touched Python files
- After deploy / next natural fire, logs show at least one of:
  - `youtube_title_filter_skip`
  - `youtube_caption_section_appended`
  - `【YouTube】` post title creation
  - `youtube_registry_sources_added`

## validation evidence

2026-05-19 local:

- 68 tests passed for 344 / YouTube integration suite.
- 57 tests passed for `rss_fetcher` + `tag_page_scraper` + YouTube integration suite.
- `python3 -m compileall src/rss_fetcher.py` passed.
- AST parse passed for `src/rss_fetcher.py` and `tests/test_rss_fetcher_youtube_integration.py`.
- `git diff --check` passed.

## live evidence

Pending deploy / natural fire observation.

## next action

Commit the repo fix, create / link GitHub Issue, deploy `yoshilover-fetcher`, then observe the next natural fire.
