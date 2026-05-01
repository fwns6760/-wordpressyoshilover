# 298-Phase3 v4 robustness supplement

Date: 2026-05-01 JST  
Mode: Lane B round 14 / doc-only / read-only supplement  
Scope: add robustness-only context before the `2026-05-02 06:00 JST` user prompt  
Non-goal: do not rewrite `cdd0c3f` / `fac5517` / `9d5620e` / `cf86e88`

---

## 0. state lock

- `298-Phase3` remains `HOLD_NEEDS_PACK` / `ROLLED_BACK_AFTER_REGRESSION`.
- This file is a **supplement**, not a replacement, for:
  - `docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_second_wave_pack.md` (`cdd0c3f`)
  - `docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_final_ready_pack.md` (`fac5517`)
  - `docs/handoff/codex_responses/2026-05-01_298_phase3_v4_alignment_review.md` (`9d5620e`)
  - `docs/handoff/codex_responses/2026-05-01_298_phase3_v4_unknown_close.md` (`cf86e88`)
- Live read-only snapshot used here:
  - Cloud Logging reads through `2026-05-01 17:13 JST`
  - `guarded_publish_history.jsonl` last row timestamp: `2026-05-01T17:10:41.076271+09:00`
  - latest current `backlog_only` pool: `104` unique `post_id`

---

## 1. second-wave cardinality re-estimate

### 1.1 strict counts from live read-only evidence

| item | strict measurement | note |
|---|---:|---|
| morning old-candidate sent cohort(`2026-05-01 09:00-10:00 JST` = `00:00-01:00 UTC`) | `99 unique post_id` | Cloud Logging `[result]` old-candidate rows; `min=61938`, `max=64056` |
| literal numeric subset `63003-63311` inside that same `99`-mail cohort | `20 unique post_id` | proves that the old shorthand "`63003-63311 group`" is a **cohort label**, not a literal numeric interval |
| flag-ON first-emit sent cohort in numeric band `61938-62940` | `50 unique post_id` | canonical from `publish_notice/history.json` and Cloud Logging `02:35-02:56 UTC` `[result]` rows |
| wider queued footprint in numeric band `61938-62940` | `53 unique post_id` | `publish_notice/queue.jsonl`; three IDs were queued footprint only, not confirmed sent in the `02:35-02:56 UTC` result rows |
| current latest-state `backlog_only` pool at `17:10 JST` | `104 unique post_id` | GCS `guarded_publish_history.jsonl` live snapshot |
| current pool first seen within the last `6h` | `1 unique post_id` | `post_id=64092` |

### 1.2 interpretation

1. The conservative `99` number is still valid for the user-facing Pack because it is the **confirmed morning sent cohort** and already consumes `99/100` of `MAIL_BUDGET 100/d`.
2. The phrase "`63003-63311 group`" should not be reused as a literal numeric range in tomorrow's summary.
Current evidence says:
   - literal `63003-63311` subset = `20`
   - full morning old-candidate cohort = `99`
   - real cohort span = `61938..64056`
3. The flag-ON first-emit band `61938-62940` is now **strictly locked to `50 sent`**, with `53 queued-footprint` as the wider non-canonical number.
4. Source-side growth is currently slow:
   - earlier `24h` analysis at `16:31 JST` measured `+6/day`
   - latest `6h` live sample at `17:10 JST` measured only `+1`

### 1.3 `2026-05-02 09:00 JST` working estimate

- low-end formula from the latest live sample:
  - `99 confirmed morning cohort + 1 latest-6h entrant = about 100`
- still-safe external planning band:
  - `100-110`
- why keep the band instead of collapsing to `100`:
  - current pool is already `104`
  - source-side `backlog_only` growth is non-zero
  - exact mail-eligible subset depends on per-`post_id` dedupe-expiry timing, not only pool size

### 1.4 budget implication

- `99 mails / ~50 min = 118.8 mails/hour`
- `100 mails / ~50 min = 120 mails/hour`
- `110 mails / ~55 min = 120 mails/hour`
- therefore even the **lowest plausible second-wave case** still:
  - breaks `MAIL_BUDGET 30/h`
  - sits on or over `MAIL_BUDGET 100/d`

Recommended wording for tomorrow morning:

> second-wave cardinality is now best read as **about `100`, planning band `100-110`**; the older `99` remains a valid conservative floor, not an upper bound

---

## 2. rollback Phase D(manual fallback)

Existing rollback layers stay unchanged:

- Phase A: env remove
- Phase B: image revert
- Phase C: ledger archive / restore

### 2.1 Phase D trigger

Use Phase D when:

- Codex cannot cross the authenticated executor boundary
- Codex shell lacks valid `gcloud` / `gsutil` auth
- sandbox or environment policy prevents live mutation
- Cloud Run mutation must be done immediately by Claude shell or the user shell

Phase D is not a new rollback type. It is the **manual execution path for A/B/C** when Codex cannot mutate live state.

### 2.2 manual gcloud / gsutil CLI path

#### D-1. env remove

```bash
gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE
```

#### D-2. image revert

```bash
gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4be818d
```

#### D-3. ledger archive or restore(if seed/object state is wrong)

Archive current object:

```bash
gsutil mv \
  gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json \
  gs://baseballsite-yoshilover-state/publish_notice/archive/<timestamp>.json
```

Restore a known-good archive when needed:

```bash
gsutil cp \
  gs://baseballsite-yoshilover-state/publish_notice/archive/<known_good>.json \
  gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json
```

#### D-4. verify

- `gcloud run jobs describe publish-notice --project=baseballsite --region=asia-northeast1`
- wait for the next scheduled `*/5` trigger, or use Cloud Console execution only if the authenticated executor intentionally chooses an incident-time live check
- confirm:
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` absent when rolled back
  - `errors=0`
  - `【要確認(古い候補)】` not replaying unexpectedly
  - normal review / `289` / error mail still alive

### 2.3 Cloud Console UI path

1. Open `Cloud Run` -> `Jobs` -> `publish-notice`.
2. `Edit & deploy new revision`.
3. For Phase A:
   - open `Variables & Secrets`
   - remove `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE`
   - deploy
4. For Phase B:
   - keep env as-is
   - replace the container image with `publish-notice:4be818d`
   - deploy
5. For Phase C:
   - open `Cloud Storage`
   - bucket `baseballsite-yoshilover-state`
   - folder `publish_notice/`
   - move `publish_notice_old_candidate_once.json` into `archive/`, or copy back a known-good archive object
6. Verify in `Logs Explorer` and on the next scheduled trigger.

### 2.4 escalation path

1. Codex reports the exact live step that failed and stops retrying.
2. Claude retries through an authenticated shell if available.
3. If Claude shell is unavailable or auth is broken, user executes the CLI or Console path.
4. If neither authenticated path is available before a budget-risk window:
   - keep `298-Phase3` OFF
   - do not ask Codex to brute-force retries
   - choose between `HOLD` and an already-approved emergency fallback only

---

## 3. stop-condition automation proposal(design only, no impl today)

### 3.1 policy placement candidate

- no `POLICY.md` edit in this commit
- candidate text only
- because `POLICY §13` is already occupied, the clean insertion should be:
  - `§13.x` only if Claude wants it grouped with operational persistence/monitoring, or
  - next free top-level section otherwise

### 3.2 detector A: `MAIL_BUDGET` auto-detect

Input:

- publish-notice Cloud Logging `[summary] sent=...`
- optional cross-check with `publish_notice/history.json`

Logic:

1. keep a rolling `12-trigger` window(`60m` at `*/5`)
2. sum `sent` across the last `12` summaries
3. also sum `sent` since JST midnight
4. fire hard alert when either condition is true:
   - rolling `60m > 30`
   - JST day total `> 100`
5. fire early warning before the hard breach:
   - rolling `60m >= 20`
   - JST day total `>= 80`

Output proposal:

- structured alert row in Cloud Logging / GCS
- optional alert mail subject:
  - `【P1 alert】MAIL_BUDGET 30/h breach`
  - `【P1 alert】MAIL_BUDGET 100/d breach`

### 3.3 detector B: silent-skip increase auto-detect

Input:

- publish-notice `[scan]` rows
- publish-notice `[result]` rows by class
- `guarded_publish_history.jsonl`
- `289` skip/notification ledgers when applicable

Logic:

1. for each trigger, count new terminal source-side events that should become visible:
   - new `backlog_only`
   - new `post_gen_validate`
   - new `hard_stop` / `refused`
   - any new skip-like terminal state with a user-visible contract
2. count actual visible outcomes in the same trigger window:
   - sent review mail
   - sent hold mail
   - explicit skip notification
   - explicit suppress reason with durable route
3. compute:
   - `invisible_delta = source_terminal_events - visible_terminal_events`
4. fire `SILENT_SKIP_SUSPECT` when either condition is true:
   - `invisible_delta > 0` for `2` consecutive triggers
   - cumulative `invisible_delta > 3/day`

Principle:

- this detector must treat "log-only" or "cursor-only" disappearance as failure
- it must not rely on Cloud Logging presence alone as proof of user visibility

### 3.4 alert-route migration plan

Current:

- Claude manual monitoring only

Proposed staged migration:

1. stage 0(now): manual Claude observe
2. stage 1: detector job writes structured health rows only
3. stage 2: detector job sends one alert mail for hard breaches
4. stage 3: detector job can propose a rollback payload, but does **not** self-mutate production without a separate user-approved policy

Recommended first implementation boundary:

- detection + alert only
- no automatic rollback in v1

---

## 4. Case A vs Case D vs Case F(re-ordered)

| case | role tomorrow morning | benefit | cost / risk | recommended position |
|---|---|---|---|---|
| **Case A: ledger seed mode** | primary user prompt | preserves the once-only contract, keeps future new `backlog_only` visible once, stays aligned with existing code/tests | needs repo impl + tests + deploy path | **1st / recommended** |
| **Case F: GCS pre-seed** | operator fallback outside the morning user prompt | preserves contract while keeping code untouched | CI-less live object surgery, lower reproducibility, object handling risk | **2nd / fallback when repo deploy is not the fastest safe path** |
| **Case D: backlog_only mute** | emergency-only fallback | fastest path to stop old-candidate mail | mutes the whole `backlog_only` review surface; semantics visibly change | **3rd / last resort** |

### 4.1 practical order

1. tomorrow's user-facing main option remains **Case A only**
2. if Case A cannot be deployed in time but authenticated executor access exists and the flag is still OFF:
   - consider **Case F**
3. if budget breach is imminent and neither A nor F is safely executable:
   - consider **Case D** as the emergency stop surface

### 4.2 precision on Case D

Case D should be described carefully:

- it mutes the `backlog_only` old-candidate review surface itself
- it is **not** the same as stopping all review mail
- normal `【要確認】`, `289`, and error mail are still expected to remain

---

## 5. `2026-05-02 06:00 JST` one-line final candidate

### final line

> **GO推奨**: `298-Phase3` は **Case A(ledger seed mode)** を本線として進める判断材料が揃っている。second-wave risk はなお `OPEN` だが、`9/9 alignment`・`UNKNOWN 0`・`rollback A/B/C + manual Phase D` が揃い、明朝 `09:00 JST` 前に止めるべき対象は十分に特定できている。

### short reason block(`1-3` lines)

- second-wave cardinality is now best framed as **about `100`, planning band `100-110`**; even the floor case breaks `30/h` and saturates `100/d`
- Pack core remains closed: `13/13` + `9/9 alignment` + `UNKNOWN 0`
- rollback robustness is no longer only repo-side; **manual executor Phase D** is fixed if Codex cannot mutate live state

### user reply

`GO` / `HOLD` / `REJECT`

---

## 6. pack independence lock

- no item in `cdd0c3f` or `fac5517` is reopened here
- no `9/9 alignment` row is changed here
- no new ticket is proposed here
- this supplement exists only to:
  - tighten the cardinality wording
  - add manual rollback Phase D
  - document stop-condition automation design
  - sharpen the A/D/F fallback order

Net:

- existing v4 Pack remains the main decision artifact
- this file is the final robustness addendum for tomorrow morning's single user prompt
