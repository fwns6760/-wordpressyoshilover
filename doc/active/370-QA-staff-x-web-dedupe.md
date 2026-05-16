# 370-QA staff X+Web dedupe

## meta

- ticket: 370-QA-staff-x-web-dedupe
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/39
- status: LIVE_DEPLOYED_OBSERVE
- priority: P0.5
- owner: Codex
- lane: B
- created: 2026-05-16 JST

## observed facts

- `68649` was created at `2026-05-16T20:01:30+09:00`, status `publish`.
- `68649` has X embeds for `https://twitter.com/hochi_giants/status/2055602460085936131` and `https://twitter.com/SportsHochi/status/2055601759096086884`.
- `68649` has source excerpt from `https://hochi.news/articles/20260516-OHT1T51338.html`.
- `68653` was created at `2026-05-16T20:01:38+09:00`, same run, same source URL, web-only.
- Cloud log shows `68649` created from X at `11:01:29Z`, then `68653` created from the same Hochi article at `11:01:36Z`.
- Existing `368-QA` X+Web dedupe required `player_name`. `杉内投手コーチ` did not create a dedupe key, so the staff quote case escaped.

## root cause

Same-family X+Web dedupe grouped candidates by `source_family + player_name + event_token`.
This works for player articles, but staff/manager/coach quote articles can have the staff member as the article subject and a player only as the object of the quote.
When the X candidate did not expose the player name in the same way as the Web candidate, the grouping key did not match.

## scope

- Extend same-family X+Web dedupe to derive a deterministic staff subject for `監督` / `コーチ` / `投手コーチ` / `投手チーフコーチ` etc.
- Keep the existing 368 policy: X candidate is parent, Web-only candidate is consumed.
- Patch existing WP posts:
  - keep `68649` published with X embed + source excerpt.
  - move `68653` duplicate to trash.

## non-goals / forbidden

- Do not infer facts from memory.
- Do not use AI / LLM similarity.
- Do not silently skip.
- Do not change Scheduler / env / Secret / X / SNS / mail behavior.
- Do not touch unrelated frontend / build / logs / generated files.

## acceptance

- Fixture test covers `68649` / `68653` staff quote X+Web dedupe.
- Existing player X+Web dedupe tests still pass.
- `68649` remains `publish`, has X embed and source excerpt, and title/headline no longer ends with `…`.
- `68653` is `trash`.
- Focused tests, compileall, and AST parse pass.
- Cloud Run deploy is verified by `/health` and startup log evidence.

## implementation evidence

- WP correction:
  - `68649` status `publish`, title/schema headline:
    `杉内投手コーチがウィットリーの投球に言及「ピッチャーに四球を出すところは本人が一番反省しているでしょう」`
  - `68649` keeps X embed + source excerpt.
  - `68653` status `trash`.
- Code:
  - `src/rss_fetcher.py` now detects deterministic staff subjects such as `杉内投手コーチ` for same-family X+Web dedupe before falling back to roster player names.
  - X candidate remains parent and Web-only candidate is consumed via existing 368 path.
- Tests:
  - `python3 -m py_compile src/rss_fetcher.py tests/test_rss_fetcher_same_family_x_web_dedup.py`
  - `python3 -m compileall -q src/rss_fetcher.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_related_posts.py tests/test_build_news_block.py tests/test_media_xpost_selector.py`
  - AST parse OK for `src/rss_fetcher.py` and `tests/test_rss_fetcher_same_family_x_web_dedup.py`
  - `python3 -m pytest tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_related_posts.py tests/test_build_news_block.py tests/test_media_xpost_selector.py -q` => `104 passed, 4 warnings`
- Commit/deploy:
  - code commit `e98bb8c` (`370: dedupe staff quote x web pairs`)
  - Cloud Build `3df7fcf2-b845-46d4-84f5-a56e9bf307d1` SUCCESS
  - image `370-staff-x-web-e98bb8c`
  - digest `sha256:6189023b74d9eda2ecafd56f02e6919051bfa6a0a8487a400ba3e75d3164566e`
  - revision `yoshilover-fetcher-00407-h9v` 100%
  - `/health` => `OK`
  - startup log: `Default STARTUP TCP probe succeeded after 1 attempt`
  - Scheduler / env / Secret / X / SNS / mail conditions were not changed.

## observe

- Keep GitHub Issue #39 open until a natural same-family staff X+Web fire produces `same_family_web_consumed` evidence in production logs.
