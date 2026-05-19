# 386-INSIGHT no-game-day normal exit

## meta

- ticket: 386-INSIGHT-no-game-day-normal-exit
- status: CLOSED
- owner: Codex A
- lane: A
- priority: P0.5
- created: 2026-05-19
- github_issue: #61
- parent: insight-nightly data analysis runtime

## user request

2026-05-18 は月曜日で試合なし。試合が無いこと自体は正常なので、データ分析 Job が失敗扱いにならないようにする。

## observed problem

2026-05-19 10:00 JST の `insight-nightly` 最新 execution `insight-nightly-fzc4d` は失敗。

- Cloud Run Job: `insight-nightly`
- latest execution: `insight-nightly-fzc4d`
- result: `exit code 2`
- log reason: `auto_resolve_all_failed: no slugs found for 2026-05-18 (last error: FetchBlocked('http_404'))`

Production DB itself is present and readable:

- `games=248`
- `batting_logs=4464`
- `pitching_logs=2007`
- `advanced_metric_snapshots=64076`
- latest game date: `2026-05-17`
- latest snapshot date: `2026-05-18`

## root cause

`src/analysis/insight_nightly.py` treated "no slug found for target date" as `FetchBlocked` even when an NPB schedule page was readable and parseable.

That collapsed two different states:

- no game day: schedule page readable, target date has no game links
- real failure: schedule page cannot be fetched or parsed

## scope

Change only `insight-nightly` schedule resolution and tests.

- If schedule HTML is readable and parseable, but target date has no NPB games, return a normal no-op result.
- If schedule HTML is readable and parseable, but Giants-only mode has no Giants game, return a normal no-op result.
- Keep real schedule fetch / parser failures as blocked errors.
- Do not change WP, Scheduler, Secret, env, X, or existing posts.

## write scope

- `src/analysis/insight_nightly.py`
- `tests/test_insight_nightly.py`
- `doc/done/2026-05/386-INSIGHT-no-game-day-normal-exit.md`
- `doc/README.md`
- `doc/active/assignments.md`

## implementation summary

- Added `NoScheduledGames` exception carrying `target_date`, `scope`, and `reason`.
- `resolve_all_slugs_auto()` now distinguishes parseable schedule pages from fetch failure.
- `resolve_slug_auto()` now treats "other games exist but no Giants game" as no-op for the Giants lane.
- CLI `main()` now prints `{"status":"no_game_day", ...}` and exits `0` for `NoScheduledGames`.
- `FetchBlocked` remains `status=blocked` / exit `2`.

## validation evidence

2026-05-19 local:

- `python3 -m pytest tests/test_insight_nightly.py tests/test_insight_schedule.py tests/test_insight_nightly_summary_logging.py` passed: 33 tests.
- `python3 -m compileall src/analysis/insight_nightly.py` passed.
- `python3 -m py_compile tests/test_insight_nightly.py` passed.
- AST parse passed for `src/analysis/insight_nightly.py` and `tests/test_insight_nightly.py`.
- `git diff --check` passed.

## deploy

- commit: `a852abf` (`386: treat insight no-game days as normal no-op`)
- Cloud Run Job: `insight-nightly`
- deployed image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:386-no-game-a852abf`
- job generation: `67`
- latest execution: `insight-nightly-mf69g`
- result: completed successfully, exit `0`, succeeded count `1`
- log evidence: `status=no_game_day`, reason `no scheduled NPB games for 2026-05-18`

## 2026-05-19 follow-up: no-game data mail

- cause verified: `insight-nightly` args have no `--date`, so `auto_target_jst_date()` kept the 2026-05-19 morning/noon runs on `2026-05-18`; `no_game_day` returned before the DATA-INSIGHT publish block.
- code: commit `8454a21` adds `ENABLE_DATA_INSIGHT_NO_GAME_DAY_PUBLISH=1` path so no-game days can still run DATA-INSIGHT publish from persisted GCS DB state.
- deploy: image `insight-nightly:386-no-game-publish-8454a21`, Job generation `68`, execution `insight-nightly-j4sbm` completed successfully.
- WP evidence: `insight-nightly-j4sbm` published post IDs `69545`, `69546`, `69547`, all titled with `【巨人データ】`.
- mail cause verified: `publish-notice` had `DRAFT_ONLY_SCAN_MODE=1`, while DATA-INSIGHT Giants articles publish directly via `ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1`; published `【巨人データ】` posts were outside the mail scanner.
- code: commit `0d09c10` adds `ENABLE_DATA_INSIGHT_PUBLISHED_NOTICE=1` so published posts whose title starts `【巨人データ】` are mail-scanned; other published posts remain excluded.
- deploy: image `publish-notice:data-insight-mail-0d09c10`, Job generation `107`, execution `publish-notice-gm5tb` completed successfully.
- mail evidence: `publish-notice-gm5tb` logged `sent=3`; per-post sent for `69545`, `69546`, `69547`; summary mail also sent.

## next action

Closed. Continue normal `insight-nightly` and `publish-notice` observation on the next natural scheduled run.
