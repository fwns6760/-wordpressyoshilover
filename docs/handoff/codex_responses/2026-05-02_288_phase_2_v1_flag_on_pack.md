# 288-INGEST Phase 2 v1 flag ON Acceptance Pack

Date: 2026-05-02 JST  
Mode: doc-only / read-only analysis  
Target flag: `ENABLE_INGEST_VISIBILITY_FIX_V1`

## Decision Header

```yaml
ticket: 288-INGEST Phase 2 v1 flag ON
recommendation: HOLD
decision_owner: user
execution_owner: Claude
risk_class: low if runtime target is confirmed; unresolved until env/apply target is closed
classification: USER_DECISION_REQUIRED
user_go_reason: flag ON env change + behavior change + runtime/apply target mismatch must be resolved before GO
expires_at: runtime target + exact rollback anchors confirmed, then re-issue same-day compact Pack
```

Header notes:

- `source_addition_classification = NO`
  - this flag does not edit `config/rss_sources.json`
  - this flag does not add RSS domains, trust families, Scheduler jobs, or fetch volume
- current Phase 2 v1 code closes `3/4` known visibility paths only
- residual `1/4` path remains `src/publish_notice_scanner.py` malformed payload handling and is explicitly Round 2 scope

## 1. Conclusion

**HOLD**.

Technically, Phase 2 v1 looks low-risk on Gemini, source, Scheduler, SEO, and direct sent-mail volume. However, repo inspection shows the flag is read only inside `src/tools/draft_body_editor.py`, while the requested apply/rollback target in the brief is `publish-notice`. Until Claude closes that runtime-target mismatch and records the exact live rollback anchor on the actual executing job(s), this cannot be truthfully promoted to `GO`.

## 2. Scope

If the flag is turned ON on the correct runtime target(s), only these three already-deployed paths change:

1. `src/tools/draft_body_editor.py`
   - cached-failure `content_hash_dedupe` branch calls `emit_ingest_visibility_fix_v1(...)`
   - writes a structured `repair_skip` row into `logs/publish_notice_queue.jsonl`
2. `src/tools/run_draft_body_editor_lane.py`
   - `no_repair_candidates`, `refused_cooldown`, and all-skipped no-op families call the same helper
   - writes structured `repair_skip` rows into the same queue log
3. `src/repair_fallback_controller.py`
   - cached-failure dedupe branch calls the same helper
   - writes a structured `repair_skip` row into the same queue log

Current commit evidence:

- deploy bundle source commit: `c796c77`
- files changed in the repo commit:
  - `src/tools/draft_body_editor.py`
  - `src/tools/run_draft_body_editor_lane.py`
  - `src/repair_fallback_controller.py`
  - `tests/test_ingest_visibility_fix_v1.py`

## 3. Non-Scope

- `src/publish_notice_scanner.py` malformed payload drop path
- `config/rss_sources.json`
- RSS source family / trust score additions
- Gemini prompt / fallback / cache-key changes
- Scheduler cadence changes
- Cloud Run secret changes
- SEO / noindex / canonical / 301
- publish / review / hold / skip criteria changes
- cleanup mutation
- Team Shiny From change

## 4. Current Evidence

### 4.1 Repo evidence

- `git show --stat --oneline c796c77`
  - `feat(ingest): 288 Phase 2 visibility fix v1 - 3 of 4 paths (default OFF flag)`
- `src/tools/draft_body_editor.py`
  - `INGEST_VISIBILITY_FIX_V1_ENV = "ENABLE_INGEST_VISIBILITY_FIX_V1"`
  - `_ingest_visibility_fix_v1_enabled()` checks the env
  - `emit_ingest_visibility_fix_v1(...)` appends a `repair_skip` queue row with `notice_kind="post_gen_validate"`
- `src/publish_notice_email_sender.py`
  - `run_publish_notice_email_dry_run --scan` sends only `scan().emitted` requests
  - helper-appended queue rows are used as queue/history entries, not replayed as direct outbound mail input
  - per-post duplicate suppression here is `30min`, not the scanner's `24h`
- `src/publish_notice_scanner.py`
  - existing `cap=10/run` and `24h` history dedup sit on scanner-produced requests, not on the direct helper appends used by this v1

### 4.2 Existing docs already in repo

- `docs/handoff/codex_responses/2026-05-01_288_INGEST_phase1_visibility_evidence.md`
  - Phase 1 was marked `FAIL`
  - violation inventory = `4`
  - residual unfixed path includes scanner malformed guarded/preflight payloads
- `docs/handoff/codex_responses/2026-05-02_288_INGEST_phase_2_visibility_fix_design.md`
  - explicitly notes the 3 repaired paths become queue-visible
  - explicitly notes they do **not** become direct publish-notice email work items yet
- `doc/done/2026-04/157-deployment-notes.md`
  - `draft-body-editor-trigger` schedule = `2,12,22,32,42,52 * * * *`
  - cadence = `144 runs/day`
- `doc/waiting/230-gcp-cost-governor-and-runtime-spend-reduction.md`
  - `publish-notice` cadence = `*/5`
  - cadence = `288 runs/day`

### 4.3 Test surface present in repo

`tests/test_ingest_visibility_fix_v1.py` covers:

- `draft_body_editor` flag ON emit
- `draft_body_editor` flag OFF silence
- `run_draft_body_editor_lane` no-op emit
- `run_draft_body_editor_lane` cooldown emit
- `repair_fallback_controller` cached-failure emit
- publish path unchanged in both modes

This turn did not re-run tests. This Pack is evidence-only.

## 5. 3 path coverage analysis

### 5.1 Coverage summary

| path | flag ON behavior | visibility result | trigger/day estimate | direct sent-mail/day estimate |
|---|---|---|---|---|
| `src/tools/draft_body_editor.py` | cached-failure `content_hash_dedupe` branch appends `repair_skip` queue row | queue-visible | theoretical upper bound `<= 720/day` (`144 lane runs/day x default max_posts=5`), expected actual `0-5/day` because only cached-failure branch emits and local ledger evidence is sparse | `0/day` direct |
| `src/tools/run_draft_body_editor_lane.py` | `no_repair_candidates`, `refused_cooldown`, all-noop branch append `repair_skip` queue row | queue-visible | exact lane cadence `144/day`; row emission band `0-144/day` depending on lane outcomes | `0/day` direct |
| `src/repair_fallback_controller.py` | cached-failure dedupe branch appends `repair_skip` queue row | queue-visible | unknown live cadence; bounded by repair invocations, expected `0-5/day` from current repo-only evidence | `0/day` direct |

Read:

- the repaired surface is **queue visibility**, not scanner-produced `PublishNoticeRequest`
- direct outbound mail creation is still absent on these three paths under the current consumer topology

### 5.2 Residual 1 path not covered in v1

`src/publish_notice_scanner.py` still has the malformed payload drop path:

- guarded review fetch error -> `REVIEW_POST_DETAIL_ERROR`
- guarded review missing payload -> `REVIEW_POST_MISSING`
- preflight malformed dedupe key -> `PREFLIGHT_SKIP_MISSING_DEDUPE_KEY`
- preflight missing `source_url` -> `PREFLIGHT_SKIP_MISSING_SOURCE_URL`

This path still sits on the actual scanner/mail hub and remains Round 2 scope.

## 6. User-Visible Impact

### 6.1 What changes if the flag is ON

- the three repaired paths stop being pure log/ledger-only
- they start writing structured `repair_skip` queue entries with:
  - `record_type=repair_skip`
  - `skip_layer=repair_lane`
  - `notice_kind=post_gen_validate`
  - subject prefix `【要review｜repair_skip】`

### 6.2 What does **not** change yet

- no new scanner-produced `PublishNoticeRequest`
- no publish criteria change
- no guarded review criteria change
- no direct outbound mail send path on these three repaired branches
- no X candidate generation change

Practical reading:

- queue-level visibility: **YES**
- mailbox-level direct visibility: **NO, not from this v1 alone**

## 7. Mail Volume Impact

### 7.1 Direct sent-mail impact

Expected direct outbound mail delta after flag ON:

- `expected mails/hour = 0`
- `expected mails/day = 0`
- `MAIL_BUDGET 30/h, 100/d = compliant`

Reason:

- `run_publish_notice_email_dry_run --scan` sends only `scan().emitted`
- the v1 helper appends queue/history rows directly
- the current publish-notice runner does not replay existing queue rows as outbound mail work

### 7.2 Queue/input volume impact

Queue/history row volume can increase even when sent mail stays flat:

| band | queue rows/day | reading |
|---|---|---|
| low | `1-5/day` | cached-failure dedupe only |
| mid | `6-24/day` | repair lane active with intermittent cooldown/no-op |
| high | `144/day` | worst case: `no_repair_candidates` once per 10-minute lane tick |

### 7.3 Existing publish-notice defenses

Requested review item:

- `cap=10/run`
- `24h dedup`
- `298 OLD_CANDIDATE_ONCE`

Codex read:

- these remain intact for normal scanner-originated review traffic
- they are **not** the primary guard for the three repaired v1 paths
- the three repaired v1 paths bypass scanner selection and append queue/history rows directly
- therefore the immediate protection is not `cap=10/run`; it is the fact that current sender code does not replay those helper-appended queue rows as direct mail

### 7.4 Mail verdict

- direct sent-mail increase: **NO**
- queue/input increase: **MAYBE**
- mailbox storm risk from this flag alone: **LOW**
- if a future queue-replay consumer is introduced, this Pack becomes stale and must be re-issued

## 7a. Prompt-ID Cost Review(POLICY §21)

Prompt-ID review result: **PASS**

Reason:

- this flag does not change any prompt text
- this flag does not add a new prompt path
- this flag does not change fallback prompt choice
- this flag does not change cache-key structure

Per-prompt decomposition:

| prompt-id | activation / touched path | baseline Gemini calls/day | Gemini delta upper/day | prompt-derived mail path | mail delta estimate | external API calls/day | cost upper bound |
|---|---|---:|---:|---|---|---:|---|
| none (no prompt path touched) | `ENABLE_INGEST_VISIBILITY_FIX_V1` gates `emit_ingest_visibility_fix_v1(...)` after prompt execution/no-op, mainly in `src/tools/draft_body_editor.py` | unchanged | `0/day` | none direct; queue-history rows only | `0/h`, `0/day` direct | `0/day` | `tokens/day=0`, `external_api_calls/day=0`, `cloud_run_executions/day=0` incremental |

## 8. Gemini / Cost Impact

- Gemini call delta: **0**
- external API delta: **0**
- source/candidate count delta: **0**
- Scheduler execution delta: **0**
- Cloud Run execution count/day delta: **0**
- storage/logging delta: **small queue/history growth only**

This is not a prompt or source expansion ticket.

## 9. Silent Skip Impact

### 9.1 Improvement achieved by v1 when ON

The three repaired paths stop ending as:

- stdout only
- stderr only
- local ledger only
- session-log only

They become:

- queue/history-visible `repair_skip` events

### 9.2 Remaining limitation

Phase 1 terminal contract is still not fully `PASS` because:

- scanner malformed payload drops remain unfixed
- queue-visible is not the same thing as direct review mail

### 9.3 Candidate disappearance risk

- for the three repaired v1 paths: reduced from pure log-only to queue-visible
- globally: not yet zero, because the scanner malformed path still exists

## 10. Preconditions

All must be true before a real GO:

1. Claude confirms the **actual runtime target(s)** that execute `src/tools/draft_body_editor.py`
   - repo-only evidence indicates at least `draft-body-editor`
   - `codex-shadow` may also need the same env if that lane executes `repair_fallback_controller`
2. Claude records the exact Tier 1 env rollback command on those actual target jobs
3. Claude records the exact Tier 2 previous image per actual target job
4. Claude confirms whether the current deploy bundle truly coupled this flag with any downstream `publish-notice` image change
5. Claude accepts that Round 2 scanner malformed payload remains out of scope for this enablement

Without `1-3`, rollback is not concrete enough for `GO`.

## 10a. Post-Deploy Verify Plan

If Claude later corrects the runtime target and proceeds:

1. image / revision
   - confirm the actual flag-bearing job image is the intended bundle
2. env / flag
   - confirm `ENABLE_INGEST_VISIBILITY_FIX_V1=1` exists only on the intended job(s)
3. service / job startup
   - next natural run exits `0`
4. runtime rollback target
   - exact prior image/job target written before apply
5. GitHub/source rollback
   - `git revert c796c77`
6. error trend
   - no new `Traceback`, `ModuleNotFoundError`, or queue-append warning burst
7. mail volume
   - direct sent-mail delta remains `0`
8. Gemini delta
   - remains `0`
9. silent skip
   - no new log-only regression on the three repaired branches
10. Team Shiny From
   - unchanged
11. publish / review / hold / skip routes
   - normal publish-notice routes remain alive
12. stop condition
   - any unexpected direct mail send or route break = stop

## 10b. Production-Safe Regression Scope

Allowed:

- read-only job/env describe
- log checks
- queue/history row spot checks
- mail count checks
- existing route checks for `289`, normal review, error mail

Forbidden:

- source addition
- Scheduler change
- Gemini prompt/provider change
- cleanup mutation
- manual queue replay experiment
- bulk mail test
- SEO/noindex/canonical/301 change

## 11. Rollback

### Tier 1 env rollback

Operator brief requested:

```bash
gcloud run jobs update publish-notice --remove-env-vars=ENABLE_INGEST_VISIBILITY_FIX_V1
```

Code-path reality check:

- repo inspection does **not** show this flag being read in `publish-notice`
- the flag is read in `src/tools/draft_body_editor.py`
- therefore Tier 1 must target the actual job(s) executing that module

Current judgment:

- requested command is a **candidate anchor from the brief**
- exact Tier 1 target is still **unclosed in repo-only evidence**
- expected time once target is correct: `~30 sec`

### Tier 2 image rollback

Operator brief requested:

```bash
gcloud run jobs update publish-notice --image=publish-notice:9e9302f
```

Code-path reality check:

- same target mismatch caveat applies
- repo-only evidence does not prove that `publish-notice` is the flag-bearing runtime
- local docs also already use `9e9302f` for a different job family earlier on 2026-05-02, so Claude should re-lock the live image tag before use

Expected time once target is correct: `~2-3 min`

### Tier 3 source rollback

```bash
git revert c796c77
```

Repo-only correction:

- `git show c796c77` contains the Phase 2 v1 code + tests only
- repo inspection does **not** show the old-candidate TTL work inside this commit
- if runtime deploy bundled multiple changes together, that coupling is deploy-level, not source-level

### Rollback order

`Tier 1 -> Tier 2 -> Tier 3`

### Rollback dependency verdict

- env-only separation is conceptually possible
- exact runtime target is not yet closed
- therefore rollback completeness is the main reason this Pack stays `HOLD`

## 12. Stop Conditions

Any one of these means immediate stop:

1. direct outbound mail appears from these three repaired paths when the expected delta is `0`
2. `289` / normal review / error route volume drops unexpectedly
3. Team Shiny From changes
4. new runtime errors appear on the flag-bearing job
5. queue/history rows are emitted but the flag was applied to the wrong job
6. rollback target remains ambiguous at the time of apply
7. scanner malformed path is mistakenly treated as fixed when it is still Round 2 scope

## 13. User Reply

`GO / HOLD / REJECT`

## Recommended Decision

**HOLD**

Direct sent-mail risk from this flag looks effectively zero, and the change does not add source, Gemini, Scheduler, SEO, or publish-criteria risk. The blocker is narrower and more concrete: the code reads `ENABLE_INGEST_VISIBILITY_FIX_V1` only in the draft-body-editor path, but the requested apply/rollback anchor is `publish-notice`. Until Claude locks the actual target job(s) and exact previous image(s), the Pack cannot honestly claim a complete rollback path.
