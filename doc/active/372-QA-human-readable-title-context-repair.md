# 372-QA human-readable title context repair

## meta

- ticket: 372-QA-human-readable-title-context-repair
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/41
- status: LIVE_DEPLOYED_OBSERVE
- priority: P0.5
- owner: Codex
- lane: B
- created: 2026-05-16 JST

## observed facts

- User reported titles such as `68537` and `68622` are hard for humans to understand.
- WP REST confirmed:
  - `68537` was `publish`, title/headline `内海哲也投手コーチ、先発`.
  - `68622` was `publish`, title/headline `井上温大「ミスドの券」`.
- Cloud Logging confirmed the generation path:
  - `68622`: template `player_quote_short` selected `井上温大「ミスドの券」` from an off-field quote, while source/body had `8回3安打無失点9奪三振`.
  - `68537`: template `manager_generic` selected `内海哲也投手コーチ、先発`, while the X source text was about `先発・ウィットリー投手`.
- Same pattern also appeared in existing titles ending in `関連情報`, `関連発言`, `コメント整理`, or generic `選手「...」`.

## root cause

The final title path accepted syntactically valid but context-thin titles.
The weak-title rescue covered some short player-event titles, but not these broader human readability failures:

- quote-only title where the quote is not the article's baseball fact
- staff/coach title ending with only `先発`
- generic subject such as `選手`
- titles ending in `関連情報` / `関連発言` / `コメント整理`

## scope

- Add deterministic human-context repair inside `_finalize_title`.
- Use only local source title / source summary / source analysis already available in the pipeline.
- Prefer literal baseball context:
  - staff target: `内海哲也投手コーチ、ウィットリーの投球に言及`
  - pitching line: `井上温大、8回3安打無失点9奪三振`
  - concrete source headline when no safer structured event exists
- Emit `human_context_title_repaired` structured logs when repair happens.
- Fix existing affected WP titles and JSON-LD headlines.

## non-goals / forbidden

- Do not use LLM / Gemini for title repair.
- Do not generate titles from memory.
- Do not silently skip repairable titles.
- Do not rely on self-evaluation only; fixture-backed tests are required.
- Do not change Scheduler / env / Secret / X / SNS / mail behavior.
- Do not touch unrelated frontend / build / logs / generated files.

## acceptance

- `68537` fixture repairs to `内海哲也投手コーチ、ウィットリーの投球に言及`.
- `68622` fixture repairs to `井上温大、8回3安打無失点9奪三振`.
- Generic `関連情報` / generic `選手「...」` titles use a concrete source headline when safe.
- Manager/coach quote titles do not incorrectly become pitcher stat-line titles.
- Existing affected WP posts have matching title and JSON-LD headline.
- Focused title and RSS regression tests pass.
- Cloud Run deploy is verified by `/health` and startup log evidence.

## implementation evidence

- Code:
  - Added `_repair_human_context_title()` and helpers in `src/rss_fetcher.py`.
  - Added `_log_human_context_title_repaired()` structured log event.
  - Wired repair into `_finalize_title()` before generic blocklist fallback and after blocklist-derived quote/action rewrites.
  - Added source/context arguments at dry-run and live `_finalize_title()` call sites.
- Tests:
  - Added `tests/test_human_context_title_repair.py`.
  - Covered player quote short, manager generic staff target, source headline fallback, generic related info, generic subject quote, eventful title no-op, and manager quote stat-line false positive prevention.
  - `python3 -m py_compile src/rss_fetcher.py tests/test_human_context_title_repair.py`
  - `python3 -m compileall -q src/rss_fetcher.py tests/test_human_context_title_repair.py tests/test_title_rewrite.py tests/test_rss_fetcher_article_quality_v1.py tests/test_narrow_unlock_subtype_aware.py tests/test_rss_manager_short_subtype_tune.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_duplicate_prevention_golden.py`
  - AST parse OK for `src/rss_fetcher.py` and `tests/test_human_context_title_repair.py`.
  - `python3 -m pytest -q tests/test_human_context_title_repair.py tests/test_title_rewrite.py tests/test_rss_fetcher_article_quality_v1.py tests/test_narrow_unlock_subtype_aware.py tests/test_rss_manager_short_subtype_tune.py` => `79 passed, 3 warnings, 13 subtests passed`
  - `python3 -m pytest -q tests/test_human_context_title_repair.py tests/test_title_rewrite.py tests/test_rss_fetcher_article_quality_v1.py tests/test_narrow_unlock_subtype_aware.py tests/test_rss_manager_short_subtype_tune.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_duplicate_prevention_golden.py tests/test_duplicate_target_integrity.py tests/test_rss_fetcher_history_duplicate_audit.py` => `104 passed, 3 xfailed, 3 warnings, 16 subtests passed`
- WP existing-title repair:
  - Updated 41 posts via WP REST after status check.
  - Updated `title` and JSON-LD `headline`; status was not changed.
  - Verification: 41 checked, `headline_mismatches=0`.
- Commit/deploy:
  - commit `097c4c8` (`372: repair context-thin RSS titles`)
  - Cloud Build `9faa589c-fa6d-40c9-930b-3c80e80fd076` SUCCESS
  - image `372-title-context-097c4c8`
  - digest `sha256:1f557f4c909dc3d0737978ad4ce2bcc6ae921ce9ccbd0dece96b6f0af31e8242`
  - revision `yoshilover-fetcher-00409-jkg` 100%
  - `/health` => `OK`
  - startup log: `Default STARTUP TCP probe succeeded after 1 attempt`
  - Scheduler / env / Secret / X / SNS / mail conditions were not changed.
  - Manual `/run` was not executed to avoid extra publish/mail side effects.

## observe

- Next natural fetcher run should emit `human_context_title_repaired` for any title caught by this contract.
- New titles should not end as `関連情報`, `関連発言`, `コメント整理`, generic `選手「...」`, or `人物、先発` when source text contains concrete context.
