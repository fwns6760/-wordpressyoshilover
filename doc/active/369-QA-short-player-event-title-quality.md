# 369-QA short player event title quality

## meta

- ticket: 369-QA-short-player-event-title-quality
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/38
- status: CODE_DONE_DEPLOY_PENDING
- priority: P0.5
- owner: Codex
- lane: B
- created: 2026-05-16 JST

## observed facts

- `68539` is `draft`, title `浦田俊輔、発言`, schema headline `浦田俊輔、発言`.
- `68539` body contains literal source text: `東京ドーム 2回適時打の浦田俊輔選手のコメント` and quote `打ったのは真っすぐです`.
- `68608` is `publish`, title `浦田俊輔、安打`, schema headline `浦田俊輔、安打`.
- `68608` body contains literal source text: `【一軍】巨人 4-3 DeNA 3安打1打点猛打賞の活躍` and `浦田俊輔 選手`.
- Existing `335-QA` covers too-short quote-only titles. Existing `290-QA` is the weak title rescue parent. This ticket covers the uncovered `player_name + thin event word` pattern.

## root cause

X-centered player event articles can lose their concrete source facts during title rewrite. When the result is still syntactically valid but too thin, such as `選手名、発言` or `選手名、安打`, the current weak-title rescue did not have a fixture that pulls literal context from the same X source text.

## scope

- Add a deterministic weak-title rescue for `player_name + thin event word`.
- Use only literal source text already present in `source_title`, `summary`, or generated body.
- Patch `68539` and `68608` after checking WP status.
- Deploy `yoshilover-fetcher` after tests.

## non-goals / forbidden

- Do not infer facts from memory.
- Do not invent game outcome wording not present in source.
- Do not silently skip rescue attempts.
- Do not use LLM / Gemini for this title repair.
- Do not change Scheduler / env / Secret / X / SNS / mail behavior.
- Do not touch unrelated frontend, logs, or dirty worktree files.

## implementation contract

- `浦田俊輔、発言` + literal `東京ドーム 2回適時打` + quote becomes a concrete title such as `浦田俊輔、東京ドーム2回適時打「打ったのは真っすぐです」`.
- `浦田俊輔、安打` + literal `巨人 4-3 DeNA` + `3安打1打点猛打賞` becomes `浦田俊輔、巨人4-3DeNA 3安打1打点猛打賞`.
- The rescue must require the player name to be present in the source text.
- The rescued title must still pass weak-title validation.

## acceptance

- Fixture-backed tests cover `68539` and `68608` patterns.
- A negative test proves missing source name is not rescued.
- Existing weak title rescue tests still pass.
- WP `68539` and `68608` title + schema headline are corrected from actual source text.
- Cloud Run deploy is verified by `/health` and startup log evidence.

## implementation evidence

- Added `rescue_short_player_event_title` in `src/weak_title_rescue.py`.
- Hooked the rescue into `_maybe_apply_weak_title_rescue` in `src/rss_fetcher.py`.
- Added regression tests in `tests/test_weak_title_rescue.py`.
- WP patch:
  - `68539` title/headline: `浦田俊輔、発言` -> `浦田俊輔、東京ドーム2回適時打「打ったのは真っすぐです」`
  - `68608` title/headline: `浦田俊輔、安打` -> `浦田俊輔、巨人4-3DeNA 3安打1打点猛打賞`
- Tests:
  - `python3 -m py_compile src/weak_title_rescue.py src/rss_fetcher.py tests/test_weak_title_rescue.py`
  - `python3 -m pytest tests/test_weak_title_rescue.py -q` = 23 passed
  - `python3 -m pytest tests/test_weak_title_rescue.py tests/test_narrow_unlock_subtype_aware.py tests/test_rss_fetcher_fan_important_narrow_exempt.py tests/test_cost_modes.py -q` = 107 passed, 9 subtests passed
  - `python3 -m compileall -q src/weak_title_rescue.py src/rss_fetcher.py tests/test_weak_title_rescue.py tests/test_narrow_unlock_subtype_aware.py`
  - AST parse OK
