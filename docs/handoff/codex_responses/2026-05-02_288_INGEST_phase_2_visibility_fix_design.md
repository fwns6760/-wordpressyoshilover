# 288-INGEST Phase 2 visibility fix narrow design

Date: 2026-05-02 JST  
Mode: Codex Lane B / doc-only / read-only design  
Target: 288-INGEST Phase 2 precondition for Phase 3 source-add

## 0. Decision summary

- current decision: `HOLD`
- reason: this turn closes the narrow design only; no implementation, no tests, no deploy evidence
- selected design: **Candidate 1**
  - reuse the proven `289`/`293` pattern
  - promote silent skip paths into `publish_notice`-visible skip records
  - keep `publish/review/hold` judgment semantics unchanged
  - keep Pack A split available as `default OFF` / live-inert

Phase alignment with `2026-05-01_288_INGEST_pack_v3_scope_phase_split.md`:

- Phase 1: visibility evidence -> complete but still `FAIL` until these 4 paths are designed and later fixed
- Phase 2: **this doc**
  - narrow visibility fix design
  - no source add
  - no deploy
- Phase 3: source add remains blocked until Phase 1 can be upgraded to `PASS`

## 1. Violation 4 path read-only analysis

### 1.1 Summary table

| path | trigger input | current output | why silent | POLICY §19.1 sub-clause | upstream impact | downstream impact |
|---|---|---|---|---|---|---|
| `src/publish_notice_scanner.py` | malformed guarded-review row or malformed preflight row | `skipped[]` only, no request queued | no `PublishNoticeRequest`, no mail, cursor can still advance | `PREFLIGHT_SKIP_MISSING_*`, `REVIEW_POST_DETAIL_ERROR`, `REVIEW_POST_MISSING`, plus `deploy verify malformed/drop code = 0` | consumes `guarded_publish_history` / `preflight_skip_history` rows | visible review mail never emitted; malformed candidate can disappear permanently |
| `src/tools/draft_body_editor.py` | `content_hash_dedupe` hit, especially cached-failure/no-body branch | `llm_skip` event, ledger entry, stderr/JSON stdout | internal tool telemetry only; no review/hold/skip mail path | `llm_skip`, `content_hash_dedupe` | reads existing draft candidate + dedupe ledger | caller sees exit code / JSON only; user inbox sees nothing |
| `src/tools/run_draft_body_editor_lane.py` | `no_repair_candidates`, `refused_cooldown`, all candidates deduped/cooldown, editor no-op family | `no_op_skip`, session log, run summary only | structured logs exist but no publish-notice/guarded-review bridge | `no_op_skip`, `llm_skip`, `content_hash_dedupe` | consumes existing draft posts or queued draft candidates | draft remains untouched, lane summary says skip, user-visible route absent |
| `src/repair_fallback_controller.py` | fallback controller dedupe hit, especially cached-failure branch returning `body_text=None` | in-memory `RepairResult` + ledger entry | controller owns no terminal visibility; caller maps to internal summary only | `content_hash_dedupe` | called from repair lane for existing drafts | cached failure becomes lane `api_fail`/skip without mail |

### 1.2 `src/publish_notice_scanner.py`

Current code references:

- guarded review fetch failure:
  - `src/publish_notice_scanner.py:1238-1245`
- preflight malformed payload:
  - `src/publish_notice_scanner.py:1679-1693`
- positive visible path for comparison:
  - `scan_post_gen_validate_history(...)` at `src/publish_notice_scanner.py:1409-1545`
  - `scan()` integration at `src/publish_notice_scanner.py:1926-1965`

Current behavior:

1. guarded-review branch
   - scanner reads a `guarded_publish_history` row
   - if `fetch_post_detail_fn(...)` raises, scanner appends `("post_id", "REVIEW_POST_DETAIL_ERROR")` and continues
   - if the fetched post payload is not a mapping, scanner appends `("post_id", "REVIEW_POST_MISSING")` and continues
2. preflight branch
   - scanner reads a `preflight_skip_history` row
   - if dedupe key cannot be built, scanner appends `("", "PREFLIGHT_SKIP_MISSING_DEDUPE_KEY")`
   - if `source_url` is empty, scanner appends `("dedupe_key", "PREFLIGHT_SKIP_MISSING_SOURCE_URL")`
3. only the good path builds `PublishNoticeRequest(...)` and calls `_append_queue_log(...)`

Why this is silent:

- malformed rows enter `skipped[]` only
- they do **not** enter `emitted[]`
- they do **not** call `_append_queue_log(...)`
- they do **not** become publish-notice email work items
- because cursor advancement happens at scan level, a malformed row can be consumed without any visible terminal outcome

Violation type:

- `docs/ops/POLICY.md:768-777`
  - `PREFLIGHT_SKIP_MISSING_*`
  - `REVIEW_POST_DETAIL_ERROR`
  - `REVIEW_POST_MISSING`
  - deploy verify requires malformed/drop code count `= 0`

Upstream impact:

- guarded-review path depends on `guarded_publish_history.jsonl` rows created by `guarded_publish_runner`
- preflight path depends on `preflight_skip_history.jsonl` rows created by `rss_fetcher`
- scanner is already the mail-visibility hub; any malformed record here is the final choke point

Downstream impact:

- no queued mail
- no review visibility
- possible permanent loss if cursor passes the malformed row
- Phase 3 source-add would multiply this risk because more candidate families would terminate through the same scanner hub

### 1.3 `src/tools/draft_body_editor.py`

Current code references:

- dedupe hit:
  - `src/tools/draft_body_editor.py:863-934`
- direct CLI terminal JSON:
  - `src/tools/draft_body_editor.py:1232-1245`

Current behavior:

1. tool computes `content_hash`
2. if a recent dedupe record exists:
   - sets `llm_skip_reason = "content_hash_dedupe"`
   - emits `_emit_llm_event("llm_skip", ...)`
   - writes dedupe/cost ledger data
3. if cached body is empty:
   - emits repair-provider ledger row with `status="failed"`
   - writes stderr `Gemini API skipped: content_hash_dedupe previous_error=...`
   - exits `20`
4. if cached body exists:
   - continues and later prints JSON result including `"llm_skip_reason": "content_hash_dedupe"`

Why this is silent:

- visibility is local to stdout/stderr/ledger
- no guarded history row
- no publish-notice queue row
- no review/hold/skip mail

Important nuance:

- `content_hash_dedupe` with a reusable cached body is not necessarily candidate disappearance, because a caller may still PUT the edited body
- the true visibility violation is the **terminal no-body / exit-20 branch** and the fact that the tool exposes only internal telemetry when used in automation

Violation type:

- `docs/ops/POLICY.md:770-772`
  - `llm_skip`
  - `content_hash_dedupe`

Upstream impact:

- existing draft body
- `llm_call_dedupe` ledger state
- direct repair invocation context

Downstream impact:

- standalone caller only gets exit code or stdout JSON
- automated callers must add their own visibility
- without that bridge, repeated cached failures remain invisible to the mailbox

### 1.4 `src/tools/run_draft_body_editor_lane.py`

Current code references:

- per-post skip aggregator:
  - `src/tools/run_draft_body_editor_lane.py:1068-1080`
- structured no-op log:
  - `src/tools/run_draft_body_editor_lane.py:1083-1107`
- empty candidate early return:
  - `src/tools/run_draft_body_editor_lane.py:1477-1500`
- cooldown skip:
  - `src/tools/run_draft_body_editor_lane.py:1543-1585`
- cached-no-op accounting:
  - `src/tools/run_draft_body_editor_lane.py:1705-1723`
  - `src/tools/run_draft_body_editor_lane.py:1910-1929`
- summary emission:
  - `src/tools/run_draft_body_editor_lane.py:1145-1179`
  - `src/tools/run_draft_body_editor_lane.py:1194-1233`

Current behavior:

1. lane filters existing draft posts into repair candidates
2. if no candidates remain:
   - emits `event=no_op_skip reason=no_repair_candidates`
   - writes `lane_run` summary
   - exits `0`
3. if a candidate recently hit guarded-publish refusal history:
   - records `refused_cooldown`
   - appends session log `event=llm_skip`
   - continues
4. if the editor/fallback returns a cached dedupe result:
   - lane counts it as `llm_noop_candidate_count`
   - session log includes `llm_skip_reason`
5. if all processed candidates were dedupe/cooldown no-ops:
   - emits `event=no_op_skip reason=all_skipped_by_dedupe_or_cooldown`

Why this is silent:

- visibility stops at stdout JSON/session log
- no `guarded_publish_history` append
- no `PublishNoticeRequest`
- no alert mail
- no digest mail

Violation type:

- `docs/ops/POLICY.md:770-772`
  - `no_op_skip`
  - `llm_skip`
  - `content_hash_dedupe`

Upstream impact:

- existing WordPress draft list or queue file
- edit-window filters
- recent guarded refusal history
- direct editor / fallback-controller return values

Downstream impact:

- the draft simply stays untouched
- the lane summary says "skip", but only inside machine-readable logs
- the mailbox never learns that a repair candidate was intentionally skipped, cooled down, or fully no-oped

### 1.5 `src/repair_fallback_controller.py`

Current code references:

- dedupe branch:
  - `src/repair_fallback_controller.py:202-257`
- lane caller bridge:
  - `_run_fallback_controller(...)` return handling at `src/tools/run_draft_body_editor_lane.py:1587-1668`

Current behavior:

1. controller computes `content_hash`
2. if a recent dedupe record exists:
   - records `skip_reason="content_hash_dedupe"` to the ledger again
   - returns `RepairResult(...)`
3. two branches exist:
   - cached success: `body_text` present, caller can continue to guards/PUT
   - cached failure: `body_text=None`, caller turns this into lane `api_fail` / skipped

Why this is silent:

- controller itself never creates a visible terminal record
- it only returns an object to the caller
- the caller currently translates the cached-failure branch into session-log-only lane outcomes

Violation type:

- `docs/ops/POLICY.md:772`
  - `content_hash_dedupe`

Upstream impact:

- repair lane prompt + current draft body
- dedupe ledger state

Downstream impact:

- successful cached reuse is not a disappearance risk
- cached failure is a disappearance risk because it stops repair without any mailbox-visible reason

## 2. Visibility fix narrow design

### 2.1 Design goal

Promote the 4 known silent paths into a user-visible terminal outcome without:

- changing publish criteria
- changing source coverage
- adding Gemini calls
- changing SMTP / Team Shiny From
- changing Scheduler / Cloud Run env in this turn

### 2.2 Candidate 1: reuse `289`-style visible skip path

Design:

- keep `publish_notice_scanner` as the single mailbox visibility hub
- add new visible-skip records per family
- reuse `notice_kind="post_gen_validate"` so the requests stay in the existing `post_gen_validate` reserve bucket
- differentiate by `record_type`, `skip_layer`, and `subject_override`

Proposed family mapping:

| family | producer point | record_type | skip_layer | subject prefix | dedupe basis |
|---|---|---|---|---|---|
| `body_contract_validate` | `rss_fetcher` fail/reroll branch | `body_contract_skip` | `body_contract` | `【要review｜body_contract】` | `source_url_hash + skip_reason` |
| repair-lane terminal skip | `run_draft_body_editor_lane.py` terminal no-op/cooldown/failure branch | `repair_skip` | `repair_lane` | `【要review｜repair_skip】` | `post_id + skip_reason + content_hash` |
| scanner malformed guarded-review | `publish_notice_scanner.py` direct synthetic request | `scanner_internal_skip` | `guarded_review_malformed` | `【要review｜internal_skip_visible】` | `post_id + reason` |
| scanner malformed preflight | `publish_notice_scanner.py` direct synthetic request | `scanner_internal_skip` | `preflight_malformed` | `【要review｜internal_skip_visible】` | `raw_row_hash + reason` |

Why this is narrow:

- mailbox transport stays where it already exists
- class reserve can stay on the existing `post_gen_validate` bucket because `src/publish_notice_scanner.py:1014-1022` classifies any `notice_kind="post_gen_validate"` request into `_NOTICE_CLASS_POST_GEN_VALIDATE`
- no new SMTP/body renderer family is required
- `cleanup_required` / guarded review semantics stay untouched

Path-by-path application:

1. `body_contract_validate`
   - add a producer helper parallel to `_record_post_gen_validate_skip_history(...)`
   - only emit on terminal `continue` branches
2. scanner malformed rows
   - do **not** append to `skipped[]` only
   - synthesize a minimal visible request immediately
   - blank `canonical_url` is acceptable; `PublishNoticeRequest` already normalizes empty URLs
3. repair lane
   - emit visibility at the **lane terminal boundary**, not inside low-level helper code
   - notify only for true terminal no-op/skip outcomes
   - do **not** mail on cached-success branches that still lead to `put_ok`

Trade-offs:

- implementation cost: **medium**
- mail volume impact: **low to medium**
  - uses existing visible-skip bucket
  - no new class-reserve category required
- publish/review criteria impact: **low**
  - judgment is unchanged
  - only terminal visibility changes
- fit for default-OFF Pack A: **good**

### 2.3 Candidate 2: add a new visible review category `internal_skip_visible`

Design:

- introduce a distinct internal-visible review family
- give it its own subject prefix and class-reserve slot
- optionally allow digest mode later

Benefits:

- semantically clean separation from `289 post_gen_validate`
- easier inbox filtering if repair-lane/internal-skip traffic becomes noisy

Costs:

- implementation cost: **medium-high**
- mail volume impact: **higher planning burden**
  - likely requires **`+1` new review class** in reserve/cap planning
  - exact `mails/hour` and `mails/day` estimate becomes mandatory before GO
- publish/review criteria impact: **low**, but queue-selection logic becomes more complex
- more test surface in scanner class reserve and email sender classification

When this is useful:

- only if Claude wants a clearly separate inbox lane for internal operational skips
- not recommended as the Phase 2 default

### 2.4 Candidate 3: merge into existing `cleanup_required` / guarded review path

Design:

- reuse guarded-review mail by writing synthetic review/hold rows that look like cleanup-required items

Benefits:

- implementation cost: **low-medium** for `post_id`-bearing repair cases
- scanner / sender already understand the route

Costs:

- **not applicable** to pre-WP candidate paths like `body_contract_validate`
- scanner malformed preflight rows often lack the fields that guarded review assumes
- semantic drift:
  - `content_hash_dedupe`
  - `refused_cooldown`
  - `no_repair_candidates`
  are not actually `cleanup_required`
- publish/review criteria impact: **medium-high**
  - this would blur true article-quality review with internal repair-lane no-op state

Conclusion on candidate 3:

- acceptable only as a later, lane-specific shortcut for existing drafts
- not acceptable as the default Phase 2 design

### 2.5 Selected design

Selected: **Candidate 1**

Reason:

1. it covers all 4 violation surfaces, including non-post-id pre-WP skips and existing-draft repair skips
2. it reuses proven `289`/`293` scanner machinery instead of creating a new mailbox subsystem
3. it can stay inside the existing `post_gen_validate` reserve bucket, so class-reserve churn is minimized
4. it preserves `cleanup_required` meaning and keeps publish/review semantics stable
5. it supports a clean split:
   - Pack A: code landed, flags absent/OFF, live-inert
   - Pack B: later enablement with measured mail-volume proof

### 2.6 Default-OFF env flag design

Recommended flags:

| flag | default | purpose |
|---|---|---|
| `ENABLE_BODY_CONTRACT_FAIL_NOTIFICATION` | OFF/absent | enables visible body-contract skip producer |
| `ENABLE_REPAIR_SKIP_NOTIFICATION` | OFF/absent | enables repair-lane visible skip producer |
| `ENABLE_SCANNER_INTERNAL_SKIP_VISIBLE` | OFF/absent | enables scanner-side synthetic requests for malformed guarded/preflight rows |

Pack split:

- Pack A:
  - code landed
  - flags absent/OFF
  - live behavior unchanged
- Pack B:
  - one or more flags ON
  - mailbox-visible behavior changes
  - `USER_DECISION_REQUIRED`

## 3. Test plan for future impl turn

### 3.1 Per-path visible verification

1. `publish_notice_scanner.py`
   - guarded-review fetch error -> visible internal-skip request emitted
   - guarded-review missing post -> visible internal-skip request emitted
   - malformed preflight missing dedupe key -> visible internal-skip request emitted
   - malformed preflight missing source URL -> visible internal-skip request emitted
2. `body_contract_validate`
   - fail branch -> visible skip record + mail request
   - reroll branch that still terminally skips -> visible skip record + mail request
3. `run_draft_body_editor_lane.py`
   - `no_repair_candidates` -> visible internal-skip notification or summary record
   - `refused_cooldown` -> visible repair-skip record
   - `all_skipped_by_dedupe_or_cooldown` -> visible repair-skip record
4. `repair_fallback_controller.py` family
   - cached failure/no-body -> caller emits visible repair-skip record
   - cached success with PUT -> **no** visible skip notification, because no disappearance occurred

### 3.2 Flag-OFF baseline

- all 3 new flags absent/OFF
- scanner, fetcher, repair lane keep current runtime behavior
- no new queue rows
- no new mail subjects
- existing `289`, `293`, real review, hold, error routes unchanged

### 3.3 Mail-volume and reserve checks

- Candidate 1 selected path:
  - no new notice class required
  - existing `post_gen_validate` reserve bucket still works
- verify mixed-batch selection does not reduce:
  - real review minimum
  - error-notification minimum
  - existing `289 post_gen_validate` visibility
- Candidate 2 alternative only:
  - if a new class is introduced later, estimate `+1` reserve category and re-run cap planning

### 3.4 Silent skip invariant

- invariant: visible terminal outcome exists for all 4 families
- invariant: malformed/drop reason count may be non-zero in logs, but **mail visibility count must also be non-zero for the same samples**
- invariant: `silent skip = 0`

### 3.5 Regression set

- `289` notification path unchanged
- `293` preflight visible path unchanged
- guarded review / `cleanup_required` unchanged
- Team Shiny From unchanged
- Gemini call delta `= 0`
- source count unchanged

## 4. Acceptance Pack draft (13 items) for the future Phase 2 impl turn

This pack is for the **future implementation turn**. Current recommendation remains `HOLD`.

### 1. Decision

- `HOLD`
- reason: this turn produced design only; future impl still needs code, tests, rollback anchors, and mail-volume proof

### 2. Scope

- promote the 4 known silent paths into user-visible terminal outcomes
- use Candidate 1 as the default narrow implementation
- keep all new visibility families `default OFF`

### 3. Non-Scope

- no source add
- no `config/rss_sources.json` changes
- no Cloud Run / Scheduler / Secret / live env change in this turn
- no Gemini prompt/provider change
- no Team Shiny From / mail routing change
- no `cleanup_required` semantic rewrite
- no `publish/review/hold` criteria loosening

### 4. Why now

- `288` Phase 3 source-add is blocked until Phase 1 can become `PASS`
- `docs/ops/POLICY.md:766-777` makes these marker families deploy-stop conditions
- current code already has a proven visibility pattern in `289` and `293`; this is the narrowest time to reuse it before source volume expands

### 5. Preconditions

All must be true before future GO:

- Phase 1 evidence doc accepted
- this Phase 2 design accepted
- targeted impl commit exists
- targeted tests green
- full repo unittest green
- rollback anchors written
- Pack A and Pack B explicitly split

### 6. Evidence

- `docs/ops/POLICY.md:766-777`
- `docs/handoff/codex_responses/2026-05-01_288_INGEST_phase1_visibility_evidence.md`
- `doc/active/289-OBSERVE-post-gen-validate-mail-notification.md`
- `doc/active/292-OBSERVE-body-contract-fail-notification.md`
- `doc/active/293-COST-preflight-skip-visible-notification.md`
- code refs:
  - `src/publish_notice_scanner.py`
  - `src/rss_fetcher.py`
  - `src/tools/draft_body_editor.py`
  - `src/tools/run_draft_body_editor_lane.py`
  - `src/repair_fallback_controller.py`

### 7. User-visible impact

- this turn: none
- future Pack A default OFF deploy: none
- future Pack B flag ON:
  - body-contract skip becomes visible
  - repair-lane terminal no-op/skip becomes visible
  - malformed scanner drops become visible
  - existing publish/review/hold and `289` remain

### 8. Mail volume impact

- this turn: `NO`
- Pack A default OFF deploy: `NO`
- Pack B flag ON:
  - Candidate 1 selected path: **mail increase = YES**, but class reserve can stay unchanged because requests can reuse the existing `post_gen_validate` bucket
  - Candidate 2 alternative: **requires `+1` new review category** and exact reserve estimate before GO
- exact Pack B expected rate is still `UNKNOWN` today
  - therefore current decision remains `HOLD`

### 9. Gemini / cost impact

- Gemini call increase: `NO`
- candidate volume impact: none until flags are ON
- future Pack B mail-processing cost increase is possible but bounded at the notification layer only

### 10. Rollback

Future impl / enablement rollback should be:

- Tier 1 runtime:
  - remove `ENABLE_BODY_CONTRACT_FAIL_NOTIFICATION`
  - remove `ENABLE_REPAIR_SKIP_NOTIFICATION`
  - remove `ENABLE_SCANNER_INTERNAL_SKIP_VISIBLE`
- Tier 2 source:
  - `git revert <impl_commit>`

This turn itself needs no rollback because production is untouched.

### 11. Stop conditions

Future enablement should stop if any of these appear:

- unexpected mail increase
- class-reserve starvation of real review / error / existing `289`
- silent skip remains non-zero
- malformed rows still disappear after cursor advance
- `cleanup_required` subjects or criteria drift
- Team Shiny From changes
- rollback anchor is still not concrete

### 12. Expiry

- this design expires on `2026-05-09 23:59 JST` or when superseded by an impl-ready Phase 2 pack

### 13. Recommended decision

- accept this design doc
- then fire a narrow Phase 2 impl ticket
- keep current state `HOLD` until code + tests + rollback anchors exist

## 5. `CLAUDE_AUTO_GO` 14-condition pre-evaluation

This follows the practical 14-condition table already used in `2026-05-02_change_5_old_candidate_ledger_ttl_design.md`.

Interpretation:

- **Pack A** = code landed, flags absent/OFF -> possible `CLAUDE_AUTO_GO`
- **Pack B** = later flag ON enablement -> **not** `CLAUDE_AUTO_GO`; `USER_DECISION_REQUIRED`

| # | condition | Pack A pre-judgment | Pack B pre-judgment | note |
|---|---|---|---|---|
| 1 | flag OFF deploy | YES | NO | Pack B is flag ON by definition |
| 2 | live-inert deploy | YES | NO | enablement changes visible behavior |
| 3 | behavior-preserving image replacement | YES | NO | only true for Pack A |
| 4 | tests are green | PENDING | PENDING | impl not written yet |
| 5 | rollback target confirmed | PENDING | PENDING | exact image/commit anchors not written yet |
| 6 | Gemini call increase none | YES | YES | visibility only, no new LLM calls |
| 7 | mail volume increase none | YES | NO | Pack B intentionally adds visible mail |
| 8 | source addition none | YES | YES | Phase 2 does not touch sources |
| 9 | Scheduler change none | YES | YES | none proposed |
| 10 | SEO/noindex/canonical/301 change none | YES | YES | none proposed |
| 11 | publish/review/hold/skip criteria unchanged | YES for Candidate 1 | YES for Candidate 1 / NO for Candidate 3 | selected design preserves judgment; cleanup-path merge would not |
| 12 | cleanup mutation none | YES | YES | no WP cleanup mutation proposed |
| 13 | candidate disappearance risk none/proven unchanged | YES for Pack A | PENDING | Pack B needs production-safe proof |
| 14 | stop condition written | PARTIAL | PARTIAL | this doc drafts them, impl pack must finalize |

`+1` from POLICY post-deploy discipline:

- post-deploy verify plan written -> `PARTIAL`
  - this doc gives the outline
  - the impl-ready pack must convert it into an exact verify table

### 5.1 Pre-evaluation summary

- selected Candidate 1 keeps Pack A inside plausible `CLAUDE_AUTO_GO` territory **after** implementation, tests, and rollback anchors exist
- Pack B remains `USER_DECISION_REQUIRED` because:
  - mail volume increases
  - visible terminal surface changes
  - candidate disappearance proof must be shown in production-safe evidence
- the expected unmet items today are:
  - tests green
  - rollback target concrete
  - exact Pack B mail estimate
  - post-deploy verify table

## 6. Recommended next step

1. accept this design doc
2. mark Phase 1 as still `FAIL but fully diagnosed`
3. fire a narrow Phase 2 impl ticket using Candidate 1
4. split future work into:
   - Pack A: code + tests + default OFF deploy candidate
   - Pack B: flag ON visibility enablement with mail-volume proof
