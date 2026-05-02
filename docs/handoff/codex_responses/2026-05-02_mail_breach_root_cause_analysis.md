# 2026-05-02 mail breach root cause analysis

## scope

- read-only analysis only
- data source:
  - `gcloud logging read` on Cloud Run Job `publish-notice`
  - stdout `[result]` lines for actual sent mail rows
  - stdout `[summary]` lines for run-level sent distribution
  - stderr `permanent_dedup_ttl_prune` for change #5 effect check
- target window:
  - start: `2026-05-01 19:35 JST`
  - end: `2026-05-02 19:35 JST`

## important date clarification

- The user-facing incident snapshot `110/100` corresponds to the **110th sent mail at `2026-05-02 18:15:56 JST`**.
- The full requested 24h window close at `2026-05-02 19:35 JST` contains **120 sent mails**, because another `10` mails were sent between `18:35 JST` and `19:05 JST`.
- Breach timing by exact log:
  - 100th sent: `2026-05-02 16:41:03 JST`
  - 101st sent: `2026-05-02 16:46:11 JST`
  - 110th sent: `2026-05-02 18:15:56 JST`
  - last sent inside window: `2026-05-02 19:05:59 JST`

## 1. breach cumulative timeline

### 1h buckets (`19:35 JST` anchor)

| bucket (JST) | sent | cumulative | main mix |
|---|---:|---:|---|
| 05/01 19:35-20:34 | 10 | 10 | 289 x6 / old_candidate x3 / real_review x1 |
| 05/01 20:35-21:34 | 6 | 16 | 289 x5 / old_candidate x1 |
| 05/01 21:35-22:34 | 13 | 29 | 289 x9 / old_candidate x2 / real_review x2 |
| 05/01 22:35-23:34 | 9 | 38 | 289 x8 / guarded_review x1 |
| 05/01 23:35-00:34 | 8 | 46 | 289 x6 / guarded_review x2 |
| 05/02 00:35-01:34 | 0 | 46 | - |
| 05/02 01:35-02:34 | 0 | 46 | - |
| 05/02 02:35-03:34 | 0 | 46 | - |
| 05/02 03:35-04:34 | 0 | 46 | - |
| 05/02 04:35-05:34 | 4 | 50 | 289 x2 / real_review x2 |
| 05/02 05:35-06:34 | 2 | 52 | 289 x2 |
| 05/02 06:35-07:34 | 7 | 59 | guarded_review x7 |
| 05/02 07:35-08:34 | 4 | 63 | 289 x3 / guarded_review x1 |
| 05/02 08:35-09:34 | 1 | 64 | 289 x1 |
| 05/02 09:35-10:34 | 6 | 70 | 289 x2 / old_candidate x3 / guarded_review x1 |
| 05/02 10:35-11:34 | 4 | 74 | guarded_review x2 / 289 x1 / old_candidate x1 |
| 05/02 11:35-12:34 | 6 | 80 | 289 x3 / real_review x2 / old_candidate x1 |
| 05/02 12:35-13:34 | 5 | 85 | 289 x2 / old_candidate x3 |
| 05/02 13:35-14:34 | 6 | 91 | 289 x3 / old_candidate x2 / real_review x1 |
| 05/02 14:35-15:34 | 4 | 95 | old_candidate x2 / guarded_review x1 / 289 x1 |
| 05/02 15:35-16:34 | 2 | 97 | 289 x1 / real_review x1 |
| 05/02 16:35-17:34 | 6 | 103 | guarded_review x3 / 289 x3 |
| 05/02 17:35-18:34 | 7 | 110 | old_candidate x5 / 289 x2 |
| 05/02 18:35-19:34 | 10 | 120 | 289 x6 / real_review x4 |

### rolling 60min

- peak: **16 mails / rolling 60min** at `2026-05-01 22:06 JST`
- valley: **0 mails / rolling 60min** at `2026-05-01 19:35 JST` and several overnight points
- non-zero valley: **1 mail / rolling 60min** at `2026-05-02 05:17 JST`
- interpretation:
  - no storm pattern (`>30/h`) exists in this window
  - the breach is a **slow cumulative leak**, not a burst incident

### pre-postgame headroom

- cumulative before `2026-05-02 09:00 JST`: `63`
- cumulative before `2026-05-02 12:00 JST`: `75`
- cumulative before `2026-05-02 14:00 JST` (game start): `89`
- cumulative before `2026-05-02 17:00 JST`: `101`

Conclusion: by first pitch there were only `11` mails of 24h headroom left. The later evening lift increased the overrun, but the budget was already nearly exhausted before the game moved into postgame territory.

## 2. mail class breakdown

### full close (`2026-05-02 19:35 JST`, total `120`)

| class | count | share | note |
|---|---:|---:|---|
| `289_post_gen_validate` | 66 | 55.0% | `【要review｜post_gen_validate】` |
| `real_review` | 13 | 10.8% | `【要確認】` / `【要確認・X見送り】` |
| `preflight_skip` | 0 | 0.0% | `【要review｜preflight_skip】` not observed |
| `error` | 0 | 0.0% | `【警告】` / `【緊急】` / `[ALERT]` not observed |
| `other` | 41 | 34.2% | old_candidate + guarded_review existing path |

### `other` sub-breakdown

| sub-bucket inside `other` | count | note |
|---|---:|---|
| `old_candidate` | 23 | exact subject prefix `【要確認(古い候補)】` |
| `guarded_review` | 18 | exact subject prefix `【要review】`; existing `review_hold` path inferred from subject/classifier |
| `summary` sent mails | 0 | no `kind=summary` sent rows |
| `alert` sent mails | 0 | no `kind=alert` sent rows |
| `publish` / `x_candidate` sent mails | 0 | not part of this breach window |

### incident snapshot (`110/100`, at `2026-05-02 18:15:56 JST`)

| class | count | share of `110` |
|---|---:|---:|
| `289_post_gen_validate` | 60 | 54.5% |
| `real_review` | 9 | 8.2% |
| `preflight_skip` | 0 | 0.0% |
| `error` | 0 | 0.0% |
| `other` | 41 | 37.3% |

### `[summary]` run logs

- run summaries observed: `282`
- aggregate from `[summary]` lines:
  - `sent=120`
  - `suppressed=0`
  - `errors=0`
  - `reasons={}` throughout
- sent-per-run distribution:
  - `0` mails: `210` runs
  - `1` mail: `44` runs
  - `2` mails: `17` runs
  - `3` mails: `7` runs
  - `4` mails: `2` runs
  - `6` mails: `1` run
  - `7` mails: `1` run

This matters for mitigation: the system is not hitting `cap=10/run`; it is mostly emitting `0-3` mails per run, many times.

## 3. primary cause and why the breach happened

### single biggest cause

- **Primary cause class = `289_post_gen_validate`**
- share:
  - snapshot `110`: `60 / 110 = 54.5%`
  - full close `120`: `66 / 120 = 55.0%`

### but not a single-path incident

- The breach was not caused by one runaway class alone.
- At the `110` snapshot:
  - removing all `289` mails would drop cumulative to `50`
  - removing all `old_candidate` mails would drop cumulative to `87`
  - removing all `guarded_review` mails would drop cumulative to `92`
- At the full `120` close:
  - removing all `289` mails would drop cumulative to `54`
  - removing all `old_candidate` mails would drop cumulative to `97`
  - removing all `guarded_review` mails would still leave `102`

Conclusion: `289` is the dominant path, but the actual breach required **stacking** with existing `old_candidate` and `guarded_review` paths.

### postgame surge correlation

- `2026-05-02 14:00-17:00 JST`: `12` mails
- `2026-05-02 17:00-19:35 JST`: `19` mails
- so yes, there is a postgame-shaped lift

However the lift is **not** the root anomaly:

- breach already occurred at `2026-05-02 16:46 JST`
- cumulative was already `89` before `14:00 JST`
- cumulative was already `101` before `17:00 JST`

### same game-day comparison

| window | sent | mix |
|---|---:|---|
| `2026-04-30 17:00-19:35 JST` | 23 | 289 x16 / real_review x4 / old_candidate x3 |
| `2026-05-01 17:00-19:35 JST` | 43 | 289 x32 / old_candidate x9 / guarded_review x2 |
| `2026-05-02 17:00-19:35 JST` | 19 | 289 x9 / old_candidate x5 / real_review x4 / guarded_review x1 |

Interpretation:

- `2026-05-02` evening lift is **lower** than both `2026-04-30` and `2026-05-01`.
- therefore the breach is not "an abnormally large 17-19 JST surge"
- the true mechanism is:
  1. `289` consumed the largest share all day
  2. `old_candidate` kept adding background volume
  3. `guarded_review` added mid-day volume
  4. by late afternoon the remaining 24h headroom was already too small

### improvement path check

- change #5 (`permanent_dedup_ttl_prune`):
  - log events observed on stderr from `2026-05-02 14:30 JST` to `19:10 JST`: `57`
  - every event had `count=0`
  - meaning: prune code ran, but **pruned nothing**, so it did not reduce mail volume
- `visibility_v1`:
  - no `visibility_v1` string appears in the 24h publish-notice log dump used for this analysis
  - net effect in this breach window is therefore **no observable reduction**

## 4. mitigation options (doc only)

### A. do not rely on `cap=10/run -> 5/run` as the main fix

- evidence:
  - only `2` runs exceeded `5` mails (`7` once, `6` once)
  - theoretical reduction in this exact window is only **3 mails** (`120 -> 117`)
- judgment:
  - **insufficient alone**
- trade-off:
  - low implementation effort
  - low value
  - can starve legitimate review mail during dense windows without actually protecting the 24h budget

### B. add `289_post_gen_validate` hourly/daily governor or digest mode

- evidence:
  - biggest single class: `66 / 120`
  - by `14:00 JST`, `289` alone already contributed `52`
- recommended shape:
  - keep first `N` per hour as per-post mail
  - convert overflow to one digest with title list + skip reasons
  - flag-gated, default OFF
- trade-off:
  - best leverage on volume
  - risk: user sees fewer raw weak-title / strict-review mails
  - mitigation: digest must preserve titles, source hash, skip reason label, count

### C. make `old_candidate` more summary-oriented

- evidence:
  - `old_candidate = 23 / 120`
  - full suppression of this bucket alone would have held the 24h close under budget (`120 -> 97`)
- recommended shape:
  - first `0-3` per day as per-post mail
  - the rest summary-only
  - or hard stop `old_candidate` once 24h cumulative crosses a threshold
- trade-off:
  - safest user impact because freshness is lowest
  - risk: backlog visibility drops unless a digest is always emitted

### D. extend class reserve into a real 24h budget governor

- current reality:
  - class reserve protects **selection inside one run**
  - it does **not** protect cumulative 24h budget
- recommended shape:
  - when cumulative 24h crosses a soft threshold (example `80`)
  - demote lower-priority classes in order:
    - `old_candidate`
    - `guarded_review`
    - extra `289`
  - keep:
    - `error`
    - `real_review`
    - `preflight_skip` when 282 later turns on
- trade-off:
  - strongest systemic control
  - highest policy complexity
  - needs explicit observability for budget state and downgraded counts

### E. do not rate-limit `real_review` first

- evidence:
  - `real_review = 13 / 120` full close
  - `real_review = 9 / 110` at incident snapshot
- judgment:
  - poor savings, high user-risk
- trade-off:
  - saves little
  - more likely to hide genuinely important human-review work

## 5. follow-up ticket recommendations

### priority recommendation

- **P0**: `publish-notice 24h budget governor + old_candidate demotion`
  - scope:
    - `publish-notice` scanner/sender path only
    - default OFF
    - flag-gated
    - no fetcher / Scheduler / env broadening
  - minimum behavior:
    - preserve `error` / `real_review`
    - demote `old_candidate` first
    - expose downgraded count in logs
  - estimated effort:
    - `M`

- **P1**: `289 post_gen_validate digest/rate-limit`
  - scope:
    - 289 path only
    - keep first `N`, digest the rest
  - estimated effort:
    - `M`

- **P1**: `old_candidate summary-only or daily cap`
  - scope:
    - old_candidate path only
    - most likely smallest blast radius
  - estimated effort:
    - `S-M`

- **P2**: `cap=10 -> 5`
  - scope:
    - current max-per-run only
  - estimated effort:
    - `S`
  - recommendation:
    - only as a secondary guard, not as the main fix

### recommended next action chain for 5/3+

1. keep `282-COST` blocked
2. fire a narrow impl ticket for `publish-notice` budget control, default OFF
3. prefer `old_candidate` demotion first if the goal is the smallest blast-radius fix
4. if broader safety is required, pair it with `289` digest/rate-limit
5. after deploy, require a fresh 24h observe with:
   - cumulative `<=100`
   - rolling 60min `<=30`
   - `silent skip = 0`
   - `errors = 0`
   - Team Shiny / existing mail From unchanged

## bottom line

- The breach is **existing-path accumulation**, not a new storm.
- The single biggest class is `289_post_gen_validate`, but the full breach came from `289 + old_candidate + guarded_review` stacking.
- `cap=10/run` held; therefore per-run cap is not the real problem.
- The most practical narrow fix is:
  - demote `old_candidate` earlier, and/or
  - add a `289` digest/rate-limit path,
  - under a true 24h budget governor rather than a smaller per-run cap.
