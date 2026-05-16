# 371-QA disable game live source policy

## meta

- ticket: 371-QA-disable-game-live-source-policy
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/40
- status: LIVE_DEPLOYED_OBSERVE
- priority: P0.5
- owner: Codex
- lane: B
- created: 2026-05-16 JST

## observed facts

- User direction: `絞らないでいい解除して。重複だけがいや`.
- `https://x.com/sanspo_giants/status/2055605389954277860?s=20` exists in the `サンスポ巨人X` RSSHub feed.
- The feed item contains the linked Sanspo article:
  `https://www.sanspo.com/article/20260516-IFAIPMDS2BE23MNDJD5JXPUANU/?outputType=theme_giants`
- Read-only unfurl probe returned `x_unfurl_article_found` for that URL and `extract_article_body_excerpt` produced a 303-character excerpt.
- WP REST search found no post for `2055605389954277860` or `IFAIPMDS2BE23MNDJD5JXPUANU` at investigation time.
- Production logs at `2026-05-16T11:01Z` and `2026-05-16T11:30Z` show both `サンスポ巨人X` and `サンスポ 巨人 search` skipped by `game_live_source_policy_skip`.

## root cause

`game_live_source_policy` is active when `has_game` is true and the run starts during `17:00-21:30 JST`.
During that window it only allows sources with `game_live_primary` or `game_live_video_signal`.
This suppresses normal article sources such as Sanspo X / Sanspo Web even after a game has ended.

## scope

- Disable `game_live_source_policy` by default.
- Keep the old allowlist behavior only as an explicit opt-in code path for future emergency use.
- Let normal sources flow during live-window runs.
- Rely on existing duplicate gates:
  - same-fire status ID dedupe
  - same-fire cross-source title duplicate stop
  - cross-family same-event dedupe
  - X+Web same-family dedupe

## non-goals / forbidden

- Do not change Scheduler / env / Secret / X / SNS / mail behavior.
- Do not create live X posts.
- Do not loosen duplicate guards.
- Do not touch unrelated frontend / build / logs / generated files.

## acceptance

- Default behavior: `article_source` is not skipped during `17:00-21:30 JST`.
- Logs show `game_live_source_policy_enabled=false`, `game_live_source_policy_active=false`, `game_live_source_policy_skipped_sources=0` under default tests.
- Legacy allowlist remains testable only when `ENABLE_GAME_LIVE_SOURCE_POLICY=1`.
- Focused observability and dedupe tests pass.
- Cloud Run deploy is verified by `/health` and startup log evidence.

## implementation evidence

- Code:
  - Added `ENABLE_GAME_LIVE_SOURCE_POLICY`; default is OFF.
  - `_source_allowed_by_game_live_policy()` returns `True` when the policy is disabled.
  - `_main()` only activates source-level skipping when both `has_game` and `ENABLE_GAME_LIVE_SOURCE_POLICY=1` and the run is inside the live window.
  - Flow summary now records `game_live_source_policy_enabled`.
- Tests:
  - `python3 -m py_compile src/rss_fetcher.py tests/test_rss_fetcher_observability.py`
  - `python3 -m compileall -q src/rss_fetcher.py tests/test_rss_fetcher_observability.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_rss_fetcher_duplicate_guard.py`
  - AST parse OK for `src/rss_fetcher.py` and `tests/test_rss_fetcher_observability.py`
  - `python3 -m pytest tests/test_rss_fetcher_observability.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_rss_fetcher_duplicate_guard.py -q` => `32 passed, 3 warnings`
  - `python3 -m pytest tests/test_rss_fetcher_observability.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_rss_fetcher_duplicate_guard.py tests/test_duplicate_target_integrity.py tests/test_rss_fetcher_history_duplicate_audit.py -q` => `41 passed, 3 warnings`
- Commit/deploy:
  - commit `639040e` (`371: disable game live source policy by default`)
  - Cloud Build `dec33608-4335-40fe-8b63-9867d3e5f79d` SUCCESS
  - image `371-source-unlock-639040e`
  - digest `sha256:86370ac5b7e696e3be352dd49362f31e0fae880bb4e525418d6e9d652f917c9b`
  - revision `yoshilover-fetcher-00408-l7b` 100%
  - `/health` => `OK`
  - startup log: `Default STARTUP TCP probe succeeded after 1 attempt`
  - Scheduler / env / Secret / X / SNS / mail conditions were not changed.
  - Manual `/run` was not executed to avoid extra publish/mail side effects.

## observe

- Next natural fetcher run should report `game_live_source_policy_enabled=false`, `game_live_source_policy_active=false`, and no `game_live_source_policy_skip` for Sanspo sources unless the opt-in env is explicitly added later.
