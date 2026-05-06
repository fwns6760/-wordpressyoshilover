# Theme 2 stale freshness audit + gap fill

Date: 2026-05-06
Alias: `theme2_stale_freshness_audit_and_gap_fill`
Incident: `INCIDENT_TICKET_stale_rss_freshness_2026-05-05`
Base commit audited: `5528fc9`

## Result

- Default-OFF contract is preserved for all 3 flags:
  - `ENABLE_SOURCE_TIME_PRIORITY_FRESHNESS`
  - `ENABLE_STRICT_BREAKING_NEWS_THRESHOLDS`
  - `ENABLE_FETCHER_STALE_SOURCE_GUARD`
- Existing numeric defaults are unchanged:
  - manager/comment/speech default threshold `48h`
  - strict manager/comment/speech threshold `24h`
  - lineup/pregame/probable starter/farm lineup `6h`
  - postgame/game result/notice/roster/injury/recovery family `24h`
  - backlog narrow buffer default `12h`, strict `0h`
  - unresolved fallback `24h`
  - `farm_result` backlog narrow cap `24h`
- Concrete gap was found and fixed:
  - strict freshness ON still allowed `created_at` fallback to count as fresh when no source time was extractable
  - fix is narrow and rejection-only:
    - `guarded_publish_evaluator`: strict mode now upgrades `created_at_fallback` / non-source basis to `source_time_missing_review`
    - `guarded_publish_runner`: source-priority + strict mode now refuses backlog candidates with non-source freshness basis as `source_time_missing_review`
- `source_too_old` is not wired anywhere in runtime code. It exists only in the incident ticket text. Actual runtime reasons are the 5 below plus the newly enforced strict fallback review path.

## 5528fc9 file / function map

### `src/guarded_publish_evaluator.py`

- `_freshness_threshold_hours(subtype)`
  - strict ON: `comment` / `speech` / `manager` drop from `48h` to `24h`
  - strict OFF: original thresholds stay in force
- `_resolve_content_datetime(raw_post, record, now=...)`
  - source-time extraction order:
    1. primary meta fields: `rss_published`, `x_post_date`
    2. source date/time meta fields: `source_published_at`, `published_at`, `source_datetime`, `source_date`, `article_date`, `source_created_at`
    3. `source_block`
    4. source URLs from body/meta
    5. body text date extraction
    6. `created_at` fallback
    7. unknown
- `freshness_check(...)`
  - emits `stale_source_age`, `backlog_only_source_age`, `source_time_missing_review` structured logs when strict is ON
  - returns `freshness_age_hours`, `freshness_source`, `freshness_basis`, `source_published_at`, `backlog_only`
- `_evaluate_record(...)`
  - converts freshness results into green/yellow/review/red entries
  - after this change, strict non-source fallback is promoted to review via `source_time_missing_review`

### `src/guarded_publish_runner.py`

- `_entry_freshness_context(entry, now=...)`
  - source-time priority order:
    1. `source_published_at`
    2. `source_datetime`
    3. `source_date`
    4. `article_date`
    5. `published_at`
    6. `freshness_age_hours` precomputed fallback
    7. `created_at` / `date` / `modified` fallback
- `_backlog_narrow_age_buffer_hours()`
  - strict OFF: `12h`
  - strict ON: `0h`
- `_backlog_narrow_publish_decision(entry, now=...)`
  - strict ON emits/refuses with:
    - `stale_source_age`
    - `backlog_only_source_age`
    - `source_time_missing_review`
  - after this change, source-priority + strict mode refuses non-source basis fallback instead of treating it as publishable

### `src/rss_fetcher.py`

- `_decode_x_status_datetime(post_url)`
  - extracts source time from X/Twitter snowflake
- `_entry_exact_published_datetime(entry)`
  - reads feed `published_parsed` / `published` / `pubDate`
- `_entry_exact_updated_datetime(entry)`
  - fallback to feed `updated_parsed` / `updated`
- `_url_date_reference_datetime(post_url, now=...)`
  - last-resort `/YYYY/MM/DD/` or compact `YYYYMMDD...` URL date extraction
- `_resolve_stale_source_guard_source(...)`
  - extraction order:
    1. X snowflake
    2. RSS published
    3. RSS updated
    4. URL date pattern
- `_evaluate_fetcher_stale_source_guard(...)`
  - flag OFF: unconditional allow
  - flag ON: returns
    - `stale_x_post`
    - `stale_rss_entry`
    - `stale_source_age`
    - `source_time_missing_review`

## Runtime reason map

| reason | layer | fire condition | coverage after this work |
| --- | --- | --- | --- |
| `stale_source_age` | evaluator / runner / fetcher | non-lineup stale source age over active threshold | covered |
| `backlog_only_source_age` | evaluator / runner | lineup/pregame family stale in strict mode | covered |
| `stale_x_post` | fetcher | X snowflake decoded and over threshold | covered |
| `stale_rss_entry` | fetcher | RSS `published` or `updated` decoded and over threshold | covered |
| `source_time_missing_review` | evaluator / runner / fetcher | no source time extractable, or strict fallback degraded to non-source basis | covered |
| `source_too_old` | none | not implemented in runtime | gap noted, no runtime dependency found |

## Gap found

Before this change:

- strict ON could still pass a manager/comment article if freshness resolved only from `created_at`
- this happened because evaluator treated `created_at_fallback` as a valid fresh basis, and runner backlog narrowing also allowed it when age was within threshold

After this change:

- evaluator strict mode returns review flag `source_time_missing_review` for non-source freshness basis
- runner source-priority + strict mode returns refusal reason `source_time_missing_review` for non-source freshness basis
- fetcher behavior is unchanged; it already refused missing source time when its flag is ON

## 64384 fixture evidence

New file: `tests/test_stale_freshness_incident_64384.py`

- F1 `64384` shape:
  - 2026-05-03 manager comment checked at 2026-05-05 22:00 UTC
  - runner strict/source-priority ON => `stale_source_age`
  - fetcher guard ON => `stale_rss_entry`
  - all flags OFF => preserved pass
- F2 fresh same-day manager comment:
  - 1 hour old source remains green / eligible / creatable
- F3 24h + 1m boundary:
  - strict ON rejects in runner/fetcher
  - strict OFF remains green/eligible
- F4 48h + 1m boundary:
  - relaxed 48h threshold still trips evaluator/fetcher
  - backlog buffer policy remains unchanged
- F5 missing source time:
  - fetcher => `source_time_missing_review`
  - evaluator strict => review flag `source_time_missing_review`
  - runner source-priority + strict => `source_time_missing_review`
- F6 backlog interaction:
  - backlog flag + source within 24h stays eligible
  - no false `backlog_only_source_age`
- F7-F9 same-day non-regression:
  - postgame 30m old => green
  - lineup 2h before game => green
  - farm_result 1h old => green

## Test evidence

- Targeted:
  - `python3 -m pytest tests/test_stale_*.py tests/test_*freshness*.py tests/test_guarded_publish_runner.py tests/test_rss_fetcher.py`
  - result: `146 passed`
- Full:
  - `python3 -m pytest tests/`
  - result: `2414 passed`

## Recommended GO order for 2026-05-07

### Phase 1

- enable `ENABLE_FETCHER_STALE_SOURCE_GUARD=1`
- narrowest surface: stale sources are stopped before draft creation
- watch:
  - count of `stale_x_post`, `stale_rss_entry`, `source_time_missing_review`
  - same-day manager / roster / postgame draft creation volume

### Phase 2

- enable `ENABLE_SOURCE_TIME_PRIORITY_FRESHNESS=1`
- this makes guarded publish prefer `source_published_at` and related fields over draft creation time
- watch:
  - `freshness_source_resolved` logs
  - any spike in `source_time_missing_review`
  - whether same-day articles still resolve to `freshness_basis=source_time`

### Phase 3

- enable `ENABLE_STRICT_BREAKING_NEWS_THRESHOLDS=1`
- widest behavioral change: manager/comment/speech 48h => 24h, backlog buffer `12h => 0h`
- watch:
  - manager/comment/speech hold rate near 24h boundary
  - lineup/pregame `backlog_only_source_age`
  - review volume caused by missing source time fallback

## Risk notes

- Phase 1 risk is lowest. It only affects ingest-time stale candidates and already has explicit reasons.
- Phase 2 is safe if source metadata is consistently present. If not, review volume will rise but the new fix prevents silent fresh leakage.
- Phase 3 is the broadest and should be last because it combines threshold tightening with the strict fallback review rule.
