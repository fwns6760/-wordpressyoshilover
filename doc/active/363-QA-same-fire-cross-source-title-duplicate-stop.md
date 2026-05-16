# 363-QA same-fire cross-source title duplicate stop

## meta

- status: REVIEW_NEEDED
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16
- updated: 2026-05-16
- trigger: user report that WP drafts `68478` and `68480` appeared as duplicate consecutive articles

## problem

WP REST and Cloud Logging confirmed that `68478` and `68480` were separate TokyoGiants X source URLs, but the title rewrite collapsed both to:

`巨人スタメン 巨人 vs DeNA 東京ドーム🏟 14時試合開始`

The fetcher emitted `title_collision_detected` and `same_fire_distinct_source_detected`, but that path only logged the collision. It did not block the second draft because same-fire dedup only skipped exact same `source_url`.

This also explains the broader user complaint: when 報知 / スポニチ / デイリー cover the same Giants topic, different URLs can still create multiple drafts if they normalize to the same generated title.

## scope

Implement a narrow, same-run duplicate stop for high-confidence families:

- lineup / farm lineup
- pregame
- postgame
- rainout slide
- player status
- player quote
- manager quote

Do not enable global title-only reuse for every article. A global same-title merge can incorrectly hide unrelated generic news.

## implementation

- `src/rss_fetcher.py`
  - Add `_should_skip_same_fire_cross_source_title_duplicate`.
  - When a different `source_url` in the same fire has the same normalized generated title, return `0` before `wp.create_post` for the high-confidence families above.
  - Emit JSON log event `same_fire_cross_source_title_duplicate_skip`.
  - Preserve old observe-only behavior for generic title collisions.
- `tests/test_duplicate_prevention_golden.py`
  - Reproduce `68478` / `68480` style lineup title collision.
  - Add player-quote cross-media duplicate case.
  - Add generic-title case proving unrelated collisions are still only observed.

## acceptance

- Same fire, same generated title, different source URL, `game_lineup` -> second draft is skipped (`post_id=0`).
- Same fire, same generated title, different source URL, `player_quote` -> second draft is skipped (`post_id=0`).
- Generic same-title collision remains observe-only and still creates both drafts.
- Existing exact source URL same-fire dedup still returns `0`.
- No Scheduler / env / Secret / WP existing post / X / SNS changes in this code change.

## verification

- `python3 -m py_compile src/rss_fetcher.py tests/test_duplicate_prevention_golden.py` PASS
- First targeted pytest run failed once because the new generic collision test expected exactly one `logger.info` call, while existing `auto_rss_excerpt_skip` also logs through `logger.info`; assertion was narrowed to check the expected call is present.
- `python3 -m pytest tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_reliability_2026_05_08.py -q` PASS: 36 passed, 3 xfailed, 3 warnings, 3 subtests passed
- `python3 -m pytest tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_reliability_2026_05_08.py tests/test_rss_fetcher.py tests/test_lineup_source_priority.py tests/test_title_prefix_lineup_misuse_fixtures.py -q` PASS: 79 passed, 3 xfailed, 3 warnings, 3 subtests passed

## deploy status

- Not deployed yet in this ticket record.
