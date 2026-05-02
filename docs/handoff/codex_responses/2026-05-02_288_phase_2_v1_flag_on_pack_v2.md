# 288 Phase 2 v1 flag ON Acceptance Pack v2

Date: 2026-05-02 JST  
Mode: doc-only / read-only analysis  
Target flag: `ENABLE_INGEST_VISIBILITY_FIX_V1`

Supersedes: [2026-05-02_288_phase_2_v1_flag_on_pack.md](2026-05-02_288_phase_2_v1_flag_on_pack.md) (`1c4cb66`)

## Decision Header

```yaml
ticket: 288 Phase 2 v1 flag ON
recommendation: GO
decision_owner: user
execution_owner: Claude
risk_class: low
classification: USER_DECISION_REQUIRED
supersedes: docs/handoff/codex_responses/2026-05-02_288_phase_2_v1_flag_on_pack.md@1c4cb66
user_go_reason: flag ON env apply on draft-body-editor changes runtime visibility behavior; direct sent-mail delta is expected 0/day, but queue-visible output changes
expires_at: same-day after draft-body-editor:c796c77 build/deploy verify, or immediately if runtime topology changes again
```

## Delta From Pack v1

- Pack v1 `HOLD` の主因は runtime/apply target mismatch だった。
- repo evidence では `ENABLE_INGEST_VISIBILITY_FIX_V1` を読むのは `publish-notice` ではなく `draft-body-editor` 系 path だけだった。
- 本 v2 では runtime target を `draft-body-editor` に lock できたため、v1 の `HOLD` 根拠は解消。
- 残る分類は `USER_DECISION_REQUIRED` のまま。ただし理由は UNKNOWN ではなく、`flag ON` という behavior-changing env apply そのもの。

## Runtime Target Lock

- true runtime target: **`draft-body-editor` Cloud Run Job**
- repo evidence:
  - `Dockerfile.draft_body_editor` ENTRYPOINT = `python3 -m src.tools.run_draft_body_editor_lane`
  - `src/tools/run_draft_body_editor_lane.py` imports:
    - `from src.tools import draft_body_editor`
    - `from src import repair_fallback_controller`
  - `src/tools/draft_body_editor.py` defines and reads `ENABLE_INGEST_VISIBILITY_FIX_V1`
  - `src/repair_fallback_controller.py` calls `draft_body_editor.emit_ingest_visibility_fix_v1(...)`
- therefore the 3 repaired paths all execute inside `draft-body-editor`:
  - `src/tools/draft_body_editor.py`
  - `src/tools/run_draft_body_editor_lane.py`
  - `src/repair_fallback_controller.py`
- `publish-notice` is **not** the flag reader for this ticket. It appends/scans its own ledgers, but does not execute the repaired branches.

### Scheduler Cadence Lock

- repo-anchored expected live cadence:
  - job: `draft-body-editor-trigger`
  - schedule: `2,12,22,32,42,52 * * * *`
  - timezone: `Asia/Tokyo`
  - target: `draft-body-editor:run`
- source of this cadence inside the repo:
  - `doc/waiting/230A1-scheduler-cadence-phase1-runbook.md`
  - `doc/done/2026-04/177-codex-shadow-gcp-deploy.md`
- note:
  - this turn did **not** run live `gcloud scheduler jobs describe/list`
  - treat the cadence above as repo-anchored current expectation, and let Claude refresh it with live read-only `gcloud` before apply if needed

## Revised `CLAUDE_AUTO_GO` 14-Condition Evaluation

### Pack A: flag OFF image deploy

- judgment: **`GO (CLAUDE_AUTO_GO)`**
- reason:
  - default `OFF`
  - live-inert
  - no behavior change
  - runtime target is now concrete
  - rollback Tier 1/2 anchors are concrete

### Pack B: flag ON enablement

- judgment: **`GO`, but classification remains `USER_DECISION_REQUIRED`**
- reason:
  - original `HOLD` cause was runtime-target ambiguity, and that ambiguity is now closed
  - this is still not `CLAUDE_AUTO_GO` because env enablement changes runtime visibility behavior

| # | condition | judgment | note |
|---|---|---|---|
| 1 | impl 完走 | YES | commit `c796c77` |
| 2 | tests green | YES | latest operator-provided evidence = `1913/0`; repo commit message retains earlier incremental baseline `1896/7 -> 1904/7` |
| 3 | default OFF | YES | env absent/unset = current behavior unchanged |
| 4 | live-inert deploy possible | YES for Pack A / NO for Pack B | flag OFF deploy is inert; flag ON is behavior-changing by definition |
| 5 | flag 未設定で挙動不変 | YES | code path unreachable when env absent |
| 6 | rollback target confirmed | YES | Tier 1 env remove + Tier 2 image `cf8ecb9` anchor |
| 7 | image/digest capture | YES with operational tail | pre-deploy anchor = `draft-body-editor:cf8ecb9`; new `draft-body-editor:c796c77` digest must be recorded once the in-flight build completes |
| 8 | Gemini increase none | YES | no prompt, model, or LLM call-count change |
| 9 | mail increase none / bounded | PARTIAL but acceptable | direct sent mail expected `0/day`; queue rows may increase slightly |
| 10 | source addition none | YES | no `config/rss_sources.json` or fetcher source change |
| 11 | Scheduler/SEO invariants unchanged | YES | no cadence / noindex / canonical / 301 change |
| 12 | publish/review/hold/skip criteria unchanged | YES | no judgment threshold change; visibility evidence only |
| 13 | cleanup mutation none / disappearance risk bounded | YES | no WP cleanup mutation; repaired paths move from pure silent to queue-visible |
| 14 | post-deploy verify possible | YES | concrete read-only verify plan exists below |

Summary:

- **Pack A** satisfies `CLAUDE_AUTO_GO`.
- **Pack B** remains `USER_DECISION_REQUIRED`.
- Unlike Pack v1, there is no longer an UNKNOWN runtime-gap blocker forcing `HOLD`.

## Acceptance Pack 13+1

### 1. Conclusion

- **Recommend `GO` for flag ON enablement.**
- v1 `HOLD` was caused by a false apply target (`publish-notice`). Once the real target is locked to `draft-body-editor`, the remaining risk is low and quickly reversible.

### 2. Scope

- Pack A:
  - rebuild / deploy `draft-body-editor:c796c77` with flag still absent/OFF
- Pack B:
  - apply `ENABLE_INGEST_VISIBILITY_FIX_V1=1` to **`draft-body-editor` only**
- runtime behavior when ON:
  - repaired branches append structured `repair_skip` visibility rows
  - no source expansion
  - no publish criteria change

### 3. Non-Scope

- `publish-notice` image/env change for this flag
- `yoshilover-fetcher` service
- `src/publish_notice_scanner.py` malformed payload round-2 fix
- Scheduler cadence changes
- SEO / noindex / canonical / 301
- Gemini prompt/provider/cache changes
- source family additions
- cleanup mutation
- Team Shiny From change
- 289 / 293 route semantics change

### 4. Current Evidence

- source commit: `c796c77`
- commit subject:
  - `feat(ingest): 288 Phase 2 visibility fix v1 - 3 of 4 paths (default OFF flag)`
- runtime proof:
  - `Dockerfile.draft_body_editor` entrypoint points to `src.tools.run_draft_body_editor_lane`
  - lane imports both repaired modules
- current rollback image anchor:
  - `draft-body-editor:cf8ecb9` = pre-deploy production image anchor at 2026-05-02 11:00 JST operator note
- in-flight build note:
  - `draft-body-editor:c796c77` build/deploy is being handled in parallel by Claude
- mail topology proof:
  - `emit_ingest_visibility_fix_v1()` appends `repair_skip` rows to `logs/publish_notice_queue.jsonl`
  - current `run_publish_notice_email_dry_run --scan` sends only `scan().emitted`
  - current `publish_notice_scanner.scan()` does **not** raw-consume `repair_skip` queue rows as a direct mail source

### 5. User-Visible Impact

- publish mail: unchanged
- normal review mail: unchanged
- hold mail: unchanged
- 289 `post_gen_validate` mail: unchanged
- X candidate flow: unchanged
- new effect:
  - repaired silent branches become **queue-visible**
  - they do **not** become a new direct outbound mail class under the current topology

Practical reading:

- mailbox-visible direct delta: none expected
- ops-visible evidence delta: yes

### 6. Mail Volume Impact

#### 6.1 Direct sent mail

- expected direct sent mail: **`0/day`**
- expected rolling `1h sent`: **`0` from this flag alone**
- `MAIL_BUDGET 30/h, 100/d`: compliant

Reason:

- `emit_ingest_visibility_fix_v1()` only appends queue rows
- current sender sends `scan().emitted`
- current scanner does not raw-consume `repair_skip` queue rows into outbound mail

#### 6.2 Queue row growth

Estimated row growth after flag ON:

| band | rows/day | reading |
|---|---:|---|
| low | `1-5/day` | cached-failure or no-op branches are rare |
| mid | `6-24/day` | intermittent repair lane activity |
| high | `144/day` | worst case: one visible row every 10-minute lane tick |

#### 6.3 Existing publish-notice protections

- existing protections stay unchanged:
  - `cap=10/run`
  - `24h` history dedup
  - `298` old-candidate once path
- important nuance:
  - these protections still govern the existing scanner-ledger review flows
  - they are **not** the primary guard for `repair_skip` today, because the current topology does not convert raw `repair_skip` queue rows into direct outbound mail

Mail verdict:

- sent-mail increase: **NO (expected)**
- queue growth: **MAYBE +micro to modest**
- classification stays `USER_DECISION_REQUIRED` because this is still a behavior-changing env enablement, not because mail is UNKNOWN

### 7. Gemini / Cost Impact

- Gemini call delta/day: `0`
- prompt delta/day: `0`
- external API delta/day: `0`
- source/candidate volume delta/day: `0`
- Cloud Run execution count/day: unchanged
- storage/log growth: small positive due to extra queue rows only

### 7a. Prompt-ID Cost Review

| prompt-id | activation path | Gemini delta/day upper bound | mail volume estimate | API calls/day | cost upper bound | judgment |
|---|---|---:|---|---:|---|---|
| none | `ENABLE_INGEST_VISIBILITY_FIX_V1` only gates queue visibility append after an already-decided skip/no-op path | `0` | direct `0/day`; queue rows MAYBE `1-144/day` | `0` | tokens/day `0`, external API/day `0`, Cloud Run/day unchanged | PASS |

### 8. Silent Skip Impact

- improved paths:
  - `draft_body_editor` no-op / llm-skip families
  - `run_draft_body_editor_lane` no-repair / all-skipped families
  - `repair_fallback_controller` cached silent fallback family
- improvement type:
  - from stdout-only / ledger-only silent behavior
  - to durable queue-visible evidence
- remaining out-of-scope limitation:
  - `publish_notice_scanner.py` malformed payload route is still Round 2
- disappearance verdict:
  - for these 3 repaired branches, risk is materially reduced
  - this is still **ops visibility**, not a new scanner-emitted mailbox route

### 9. Preconditions

All should be true before Pack B apply:

1. `draft-body-editor:c796c77` build/deploy completes successfully
2. Claude records the final deployed digest for `draft-body-editor:c796c77`
3. `draft-body-editor:cf8ecb9` remains the last-known-good rollback anchor, or Claude refreshes the anchor if drift occurred
4. `ENABLE_INGEST_VISIBILITY_FIX_V1` is absent before apply
5. existing `real review`, `289 post_gen_validate`, and `293 preflight_skip` routes are alive before apply
6. authenticated executor is available for Tier 1 rollback within minutes

### 10. Tests

- latest operator-provided test status: **`1913/0`**
- repo commit message earlier incremental record:
  - baseline `1896/7 -> 1904/7`
- targeted coverage includes:
  - flag OFF silence
  - lane no-op visible when flag ON
  - lane llm-skip visible when flag ON
  - controller cached-failure visible when flag ON
  - behavior unchanged when flag OFF
- this turn did not re-run tests; this pack is evidence consolidation only

### 10a. Post-Deploy Verify Plan

After Pack A and before/after Pack B:

1. image / digest
   - confirm `draft-body-editor` points to the intended `c796c77` build artifact
2. env / flag
   - confirm `ENABLE_INGEST_VISIBILITY_FIX_V1=1` exists on `draft-body-editor` only
3. job startup
   - next natural run exits `0`
4. repaired-path evidence
   - if a repaired branch triggers, confirm `repair_skip` structured row append
   - if it does not trigger immediately, at minimum confirm no append warnings / no traceback
5. direct mail delta
   - confirm no unexpected sent-mail burst
6. route health
   - `real review`, `289`, `293`, publish, hold all continue
7. Team Shiny From
   - unchanged
8. rollback anchor
   - exact current image digest and previous `cf8ecb9` anchor both recorded
9. error trend
   - no consecutive `draft-body-editor` execution errors
10. stop condition readiness
   - Tier 1 env rollback command is ready to paste and execute

### 10b. Production-Safe Regression Scope

Allowed:

- read-only job describe
- read-only env/digest verification
- log inspection
- queue row spot-check
- existing mail-count checks
- existing route-health checks (`real review`, `289`, `293`, publish/hold)

Forbidden:

- bulk mail experiment
- raw queue replay experiment
- source addition
- Scheduler mutation
- Gemini increase
- publish criteria change
- cleanup mutation
- SEO/noindex/canonical/301 change
- user-GO-less flag ON on any target other than the locked `draft-body-editor`

### 11. Rollback

Rollback order:

- **Tier 1 env**
  - `gcloud run jobs update draft-body-editor --remove-env-vars=ENABLE_INGEST_VISIBILITY_FIX_V1 --region=asia-northeast1`
  - expected time: `~30 sec`
- **Tier 2 image**
  - `gcloud run jobs update draft-body-editor --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:cf8ecb9 --region=asia-northeast1`
  - expected time: `~2-3 min`
- **Tier 3 source**
  - `git revert c796c77`
  - operational note:
    - Tier 3 exists, but it is slower and is not the first containment tool
    - for live containment, Tier 1 env removal is sufficient unless the image itself proves bad

Rollback verdict:

- exact runtime rollback is now concrete
- this was the missing piece in Pack v1

### 12. Stop Conditions

Any one of these means immediate rollback via Tier 1 first:

1. rolling `1h sent > 30`
2. publish / review / hold / skip route drop
3. `289` or real review notification route missing
4. Team Shiny From changes
5. consecutive `draft-body-editor` errors `> 0`
6. unexpected direct outbound mail appears from `repair_skip`
7. runtime target drift is discovered after apply

### 13. User Reply

`OK / HOLD / REJECT`

## Recommended Decision

- **flag OFF image deploy**: **`GO (CLAUDE_AUTO_GO)`**
  - `draft-body-editor:c796c77` rebuild + Job update only
  - default `OFF`
  - live-inert
  - no user reply needed

- **flag ON enablement**: **`GO`**
  - reason:
    - Pack v1 `HOLD` root cause was runtime-target ambiguity
    - that ambiguity is now closed
    - no Gemini/source/Scheduler/SEO change
    - no direct sent-mail increase is expected under the current topology
    - rollback is concrete at Tier 1 and Tier 2

## User Response Format

- flag OFF deploy: no reply needed; Claude may proceed autonomously after build verify
- flag ON enablement: reply with exactly one word
  - `OK`
  - `HOLD`
  - `REJECT`
