# 046-A1 - first wave fixture dry-run

Parent ticket: [046-pickup-parity-first-wave-promotion.md](046-pickup-parity-first-wave-promotion.md)

## Purpose

046-A1 fixes the promotion judgment for the first pickup wave before runtime wiring.
It covers only fixture input, a pure function, dry-run stdout evidence, and tests.

## Scope

- Target families: `lineup_notice`, `comment_notice`, `injury_notice`, `postgame_result`.
- Target branches: `fixed_primary`, `deferred_pickup`, `duplicate_absorbed`.
- Fixture source: `tests/fixtures/first_wave/*.json`.
- Dry-run command: `python -m src.tools.run_first_wave_dry_run --assert-expected tests/fixtures/first_wave/*.json`.
- Stdout evidence format: `route=<route> subtype=<subtype> candidate_key=<key> source_kind=<kind> trust_tier=<tier>`.

## Non-goals

- No runtime route switch.
- No WP draft creation.
- No published write.
- No scheduler, env, secret, automation, scraper, fetcher, or API change.
- No changes to `src/source_trust.py`, `src/source_id.py`, `src/game_id.py`, or `src/tools/run_notice_fixed_lane.py`.

## Acceptance

- The 12 fixture patterns cover 4 families x 3 branches.
- Trust-boundary fixtures return `fixed_primary`.
- Trust-outside fixtures return `deferred_pickup`.
- Duplicate `candidate_key` fixtures return `duplicate_absorbed`.
- Existing route and trust schema remain unchanged.
