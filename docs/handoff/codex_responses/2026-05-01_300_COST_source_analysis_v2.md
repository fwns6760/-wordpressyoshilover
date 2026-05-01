# 300-COST source-side guarded-publish 再評価 cost analysis v2

Date: 2026-05-01 JST  
Lane: Codex B round 11  
Mode: doc-only / read-only / single-file diff  
Scope: `docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis_v2.md` new only

## 0. Scope and Snapshot

- This v2 keeps `src/` / `tests/` / env / Scheduler / GCP mutation untouched.
- It supplements, not rewrites:
  - `docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis.md` (`7a946a8`)
  - `docs/handoff/codex_responses/2026-05-01_300_COST_pack_draft.md` (`54c2355`)
  - `docs/handoff/codex_responses/2026-05-01_300_COST_pack_supplement.md` (`c959327`)
- Repo source paths used for code-trace:
  - `src/guarded_publish_runner.py:1108-1128`
  - `src/guarded_publish_runner.py:2095-2143`
  - `src/guarded_publish_runner.py:2423-2425`
  - `src/publish_notice_scanner.py:32-51`
  - `src/publish_notice_scanner.py:474-495`
  - `src/publish_notice_scanner.py:523-565`
  - `src/publish_notice_scanner.py:592-610`
  - `src/publish_notice_scanner.py:871-930`
- Live read-only snapshot used for the numbers below:
  - `guarded_publish_history.jsonl` GCS snapshot downloaded at `2026-05-01 16:31 JST`
  - `publish_notice/history.json`, `publish_notice/queue.jsonl`, `publish_notice/publish_notice_old_candidate_once.json` downloaded at the same time
  - analysis window fixed to `2026-04-30 16:30:48 JST` through `2026-05-01 16:30:48 JST`

## 1. Old Backlog Pool: 24h Measured Numbers

### 1.1 Guarded history actuals

| metric | measured value | note |
|---|---:|---|
| total guarded history rows in last 24h | `29,756` | actual live sample, not the earlier rough `28,800` formula |
| `hold_reason=backlog_only` rows in last 24h | `29,481` | `99.1%` of all rows |
| unique `post_id` with `hold_reason=backlog_only` in last 24h | `106` | unique old backlog candidates touched by source-side reevaluation |
| average repeated rows per unique backlog post in last 24h | `278.12` | `29,481 / 106` |
| non-`backlog_only` rows in last 24h | `275` | refused + sent + other review branches |
| unique non-`backlog_only` post_ids in last 24h | `273` | almost all unique, low-repeat compared with backlog-only |

### 1.2 Pool increase / decrease / net growth

Definitions used here:

- `increase` = first-ever `backlog_only` observation enters the pool
- `decrease` = a pool member later becomes `sent`
- `net growth` = `increase - decrease`

Measured result in the fixed `24h` window:

| metric | measured value |
|---|---:|
| new `backlog_only` entrants | `6` |
| publish conversions from those entrants within the same 24h | `0` |
| increase rate | `+6 / day` |
| decrease rate(`publish化`) | `0 / 106 = 0%` on the active `backlog_only` cohort |
| net pool growth | `+6 / day` |

New entrant hours:

- `2026-04-30 17:00 JST`: `1`
- `2026-04-30 19:00 JST`: `2`
- `2026-04-30 20:00 JST`: `2`
- `2026-05-01 13:00 JST`: `1`

### 1.3 Current pool cardinality and age

At the `2026-05-01 16:30:48 JST` snapshot:

| metric | measured value |
|---|---:|
| current latest-state `backlog_only` pool | `104` unique post_id |
| pool members first seen `>24h` ago | `98` |
| pool members first seen `>72h` ago | `80` |
| pool members first seen `>168h` ago | `0` |
| oldest first-seen timestamp in current pool | `2026-04-27 21:31 JST` |
| oldest current backlog age at snapshot | about `91h` |

Interpretation:

- This is not a self-draining pool.
- `98 / 104` of the current pool have already stayed in the `backlog_only` lane for more than one day.
- Waiting for natural exhaustion violates `docs/ops/POLICY.md` §7 and is not supported by the actual pool behavior.

### 1.4 Morning-storm cohort outcome check

For the `2026-05-01 09:05-09:50 JST` first-wave old-candidate mail cohort:

| latest outcome at `2026-05-01 16:30 JST` | count |
|---|---:|
| still `skipped/backlog_only` | `97 / 99` |
| moved to `refused/hard_stop_lineup_duplicate_excessive` | `2 / 99` |
| published | `0 / 99` |

This is the strongest source-side evidence that repeated reevaluation is mostly preserving old backlog state, not converting it into publish.

### 1.5 `2026-05-02 09:00 JST` pool estimate

Linear projection using the measured `+6/day` net growth:

- current pool at `2026-05-01 16:30 JST`: `104`
- time until `2026-05-02 09:00 JST`: about `16.49h`
- projected additional entrants at the same pace: about `4.12`
- projected pool cardinality at `2026-05-02 09:00 JST`: about `108`

Important distinction:

- `108` is the projected total source-side `backlog_only` pool.
- It is not the same as the mail-eligible subset at exactly `09:00 JST`.

Using actual `publish_notice/queue.jsonl` old-candidate send timestamps plus the `24h` dedupe window:

| threshold time | current-pool IDs already dedupe-expired by then |
|---|---:|
| `2026-05-02 09:00 JST` | `5` |
| `2026-05-02 09:30 JST` | `7` |
| `2026-05-02 10:00 JST` | `53` |
| `2026-05-02 12:00 JST` | `103` |

Refinement versus the earlier conservative `99` estimate:

- The earlier `99 unique` risk in `INCIDENT_LIBRARY` and `298-Phase3 v4` is still a valid conservative pack number.
- The later `11:35-11:55 JST` second wave moved `48` current-pool IDs to a later dedupe-expiry bucket.
- As of the `16:30 JST` snapshot, the practical recurrence pattern is:
  - smaller tail on `2026-05-01 17:55-20:25 JST`: `5`
  - main morning re-open on `2026-05-02 09:25-09:50 JST`: `48`
  - later re-open on `2026-05-02 11:10-11:55 JST`: `50` including the `11:10` single and the `11:35-11:55` group

## 2. Mail Storm Model

### 2.1 Why recurrence is mathematically built in today

Source-side recurrence:

- `src/guarded_publish_runner.py:2095-2143` creates a fresh `status=skipped` / `hold_reason=backlog_only` row every live run when a backlog entry is not narrow-publish eligible.
- `src/guarded_publish_runner.py:2423-2425` appends every such row to `guarded_publish_history.jsonl`.
- `src/guarded_publish_runner.py:1108-1128` does not treat `status=skipped` as attempted, so the same `post_id` is reevaluated again at the next `*/5` trigger.

Sink-side recurrence:

- `src/publish_notice_scanner.py:32` sets `_HISTORY_WINDOW = 24h`.
- `src/publish_notice_scanner.py:899-901` uses the `24h` history dedupe when `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` is OFF.
- `src/publish_notice_scanner.py:523-565` loads only rows newer than the cursor, so fresh source-side re-appends are the fuel that keeps old candidates visible to the scanner.

Therefore:

`flag OFF + repeating source rows + 24h history expiry = recurrent old-candidate mail`

### 2.2 Cap math

The per-run cap is not the safety proof. The live formula is:

`mail volume over a window = min(eligible_expired_pool_per_trigger, 10) * trigger_count`

Observed and projected examples:

| case | volume math | normalized rate |
|---|---|---:|
| conservative first-wave pack model | `99 mails / ~50 min` | `118.8/h` |
| refined morning bucket from live queue snapshot | `48 mails / 25 min` | `115.2/h` |
| refined cumulative by `10:00 JST` | `53 mails / 35 min` | `90.9/h` |

All three are far above `MAIL_BUDGET 30/h`.

### 2.3 `24h` dedupe expiry timing

The timing is per `post_id`, based on the stored last-send timestamp.

Concrete dates:

- first-wave sends on `2026-05-01 09:05-09:50 JST` reopen on `2026-05-02 09:05-09:50 JST`
- second-wave sends on `2026-05-01 11:35-11:55 JST` reopen on `2026-05-02 11:35-11:55 JST`
- the small tail on `2026-04-30 17:55-20:25 JST` already reopens on `2026-05-01 17:55-20:25 JST`

### 2.4 Flag ON effect

When `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`:

- `src/publish_notice_scanner.py:47-51` enables the permanent old-candidate ledger path
- `src/publish_notice_scanner.py:898-926` checks the permanent ledger and emits `OLD_CANDIDATE_PERMANENT_DEDUP` instead of relying on `24h` history-only dedupe

Effect:

- old candidates over threshold stop being a `24h` replay problem
- but source-side repeated rows still exist and still bloat `guarded_publish_history.jsonl`

## 3. Candidate Disappearance: Deeper Evaluation

### 3.1 What current repeated rows are doing

Current repeated rows do two different things:

- they preserve reevaluation opportunities inside `guarded-publish`
- they preserve repeated visible reminders to `publish-notice` once the `24h` dedupe expires

Measured evidence:

- `97 / 99` first-wave candidates were still `backlog_only` seven hours later
- `0 / 99` first-wave candidates were published
- `0 / 6` new entrants in the last 24h were published

So the present design keeps visibility alive, but it does not actually drain the pool.

### 3.2 What Option C changes and what it does not change

Option C under discussion:

- skip history append only when the latest `backlog_only` row is unchanged
- reevaluation itself still runs
- WP status is not mutated by the skip

Unchanged:

- guarded-publish still reevaluates the same candidate every `*/5`
- a later state change to `sent` or `refused` can still happen
- source-side publish chance is not removed by the skip itself

Changed:

- the scanner cursor sees no new row for that unchanged candidate
- after the first old-candidate notification, there is no fresh source-side event to surface the same candidate again

### 3.3 3-way judgment

Question: does Option C reduce, keep, or increase candidate disappearance?

Answer:

- `reduce`: `NO`
- `unchanged`: only `conditionally`, if a prior sink-side contract already guarantees the one allowed first notice
- `increase`: `YES` for standalone 300-COST

Reason:

- standalone Option C suppresses the only repeated user-visible reminder path for unchanged `backlog_only` candidates
- the candidate still exists in WP / guarded-publish, but it stops resurfacing once the cursor has moved past its last visible row
- this is a reminder-layer disappearance, not a source-side reevaluation disappearance

This is the key nuance missing from v1 and from the pack supplement's simplified `Candidate disappearance risk = NO` field.

### 3.4 Why sequencing after `298-Phase3 v4 Case A` still makes sense

`298-Phase3 v4 Case A` is a sink-side visibility contract:

- known old candidates are seeded into a permanent ledger before the second wave
- future new `backlog_only` candidates still get one deliberate first notice

Under that sink-side contract:

- 300 no longer needs to provide reminder repetition for already-seeded old candidates
- 300 mainly becomes a raw-row / history-growth reduction ticket

So the correct sequence remains:

1. `298-Phase3 v4 Case A`
2. `24h` stable observe
3. `300-COST` only after the first-notice visibility contract is proven stable

### 3.5 `unchanged-only skip` test cases that v2 adds

1. `backlog_only` unchanged latest row, flag ON  
Expected: source reevaluation continues, but no new guarded-history row is appended.

2. `backlog_only` latest row changes to another hold reason  
Expected: append must still happen because scanner-visible state changed.

3. `backlog_only` latest row changes to `sent` or `refused`  
Expected: append must still happen; publish/hard-stop evidence cannot disappear.

4. standalone 300, no `298` seed/once contract  
Expected: first old-candidate notice may be the last visible reminder; this is the visibility risk and must be documented as intentional if GO is ever proposed.

5. flag OFF baseline  
Expected: current repeated append behavior remains byte-for-byte unchanged.

## 4. Quantitative Cost Impact

### 4.1 Actual `rows/day` delta

Measured last `24h` actual:

- total rows/day proxy: `29,756`
- backlog-only rows/day: `29,481`
- non-backlog rows/day: `275`

If Option C suppresses unchanged `backlog_only` rows and the current rates persist:

- expected backlog rows/day that still remain: about `6`
  - this is the measured first-seen backlog entrant count in the last `24h`
- expected total rows/day: about `281`
  - `275` current non-backlog rows/day
  - `+6` first-seen backlog-only rows/day

Result:

- `29,756/day -> ~281/day`
- row-count reduction about `99.1%`

This is the quantified replacement for the earlier rough `28,800/day -> few hundred/day` phrasing.

### 4.2 Raw append bytes/day

Measured mean serialized row sizes from the live sample:

| row class | mean bytes/row |
|---|---:|
| `backlog_only` skipped row | `364.6` |
| non-`backlog_only` row | `413.1` |

Resulting raw append growth:

| mode | raw append/day |
|---|---:|
| current measured behavior | about `10.36 MiB/day` |
| Option C at current rates | about `0.11 MiB/day` |

This is a raw-append reduction of about `98.9%`.

### 4.3 What does not go down with 300 alone

Unchanged:

- Cloud Scheduler cadence: `*/5`
- Cloud Run job executions/day: `288`
- GCS object uploads/day: `288`

Reason:

- `bin/guarded_publish_entrypoint.sh` always downloads the state, runs the job, then uploads the full `guarded_publish_history.jsonl` object again
- 300 suppresses row creation inside the file
- 300 does not suppress the upload operation itself

Current-size proxy:

- downloaded snapshot size at `2026-05-01 16:31 JST`: `33,346,302 bytes` (`~31.8 MiB`, `ls -lh` rounds to `32M`)
- whole-file upload count/day at current size: about `8.94 GiB/day` of transfer if the object size stayed flat for a day

So the correct split is:

- 300 helps `rows/day`, append growth, and scanner input volume
- 300 does not solve whole-file upload count
- `bin/guarded_publish_entrypoint.sh` unchanged-upload skip is a separate ticket

### 4.4 Job duration impact

Operationally this is not a duration-reduction ticket.

- the work removed by Option C is mainly repeated JSON serialization and `_append_jsonl()` calls
- the job is still dominated by evaluator work, history download, whole-file upload, and WP-facing checks
- relative to the tens-of-seconds job profile already documented in `doc/waiting/230-gcp-cost-governor-and-runtime-spend-reduction.md`, the Option C duration delta is second-order and not a decision driver

Conclusion:

- treat job-duration benefit as negligible
- do not justify 300 by Cloud Run wall-clock reduction

## 5. Delta From `c959327` Supplement

What remains correct from the supplement:

- `Mail volume impact = NO` if that field means "300 changes no user-visible routing class by itself"
- `Cloud Run execution count/day` and `GCS upload count/day` are not reduced by 300 alone
- sequencing after `298-Phase3 v4` is still correct

What v2 adds or tightens:

1. actual `24h` row math is now measured, not rough  
`29,756/day -> ~281/day`, current pool `104`, projected `~108` by `2026-05-02 09:00 JST`

2. cardinality is not the same as first-hour mail risk  
current snapshot says `5` already expired by `09:00`, `53` by `10:00`, `103` by `12:00`

3. whole-file upload count is explicitly separated  
`288 uploads/day` remains a separate entrypoint ticket even if source rows collapse

4. disappearance nuance is stricter  
standalone 300 does not lose source-side reevaluation, but it does increase reminder-layer disappearance for unchanged old candidates

5. test surface is more explicit  
the `unchanged-only skip` branch needs its own `5` narrow cases, especially the standalone-300 visibility case

## 6. POLICY §7 Alignment

### 6.1 `Do not wait for old candidate pool exhaustion`

Aligned.

- measured current pool is `104`
- `98` of those have already been in the `backlog_only` lane for more than `24h`
- net growth in the last `24h` was positive, not negative

300's contribution:

- it does not exhaust the pool
- it only stops writing the same evidence row over and over

### 6.2 `MAIL_BUDGET violation is P1`

Aligned.

Even the refined current snapshot still predicts P1-scale recurrence:

- `48 mails / 25 min = 115.2/h`
- `53 mails by 10:00 JST = 90.9/h`

Both remain over the `30/h` budget.

### 6.3 `Phase3 re-ON requires pool cardinality estimate`

Aligned, with an important limitation.

300 does not materially shrink the candidate pool itself.

- source-side pool now: `104`
- projected source-side pool at `2026-05-02 09:00 JST`: about `108`

Therefore:

- 300 can shrink history noise
- 300 cannot substitute for the `298-Phase3` cardinality / mail-budget pack
- pool-cardinality estimation remains mandatory even if 300 is eventually deployed

## 7. Cross-Reference and Recommended Order

Relationship to `298-Phase3 v4`:

- `298-Phase3 v4 Case A` = sink-side first-notice / second-wave prevention
- `300-COST` = source-side repeated-row suppression

They are complementary, not interchangeable.

Recommended deploy order:

1. `298-Phase3 v4 Case A` first
2. `24h` stable observe with `MAIL_BUDGET`, `289`, `normal review`, `error path`, and `silent skip` all green
3. `300-COST` only after that

Reason:

- 298 is the ticket that directly addresses tomorrow's budget breach risk
- 300 mainly addresses history growth, repeated scanner fuel, and future cost noise
- 300 before 298 would reduce rows, but it would also worsen old-candidate reminder disappearance if deployed standalone

## 8. Final Judgment

- `300-COST` is justified as a deferred source-side hygiene/cost ticket.
- It is not a pool-cardinality reduction ticket.
- It is not an execution-count reduction ticket.
- It is not an upload-count reduction ticket.
- Standalone 300 would make unchanged old candidates less visible after their first review mail.
- Because of that, the current order in the supplement remains correct:
  - `298-Phase3 v4` first
  - then `24h` stable
  - then `300-COST` if still desired

The new evidence in v2 is the measured distinction between:

- `pool size` (`104 now`, `~108 projected at 2026-05-02 09:00 JST`)
- `mail-eligible subset by time bucket` (`5 by 09:00`, `53 by 10:00`, `103 by 12:00`)
- `history row noise` (`29,756/day -> ~281/day`)

That distinction is the main thing v1 and the supplement did not yet make explicit.
