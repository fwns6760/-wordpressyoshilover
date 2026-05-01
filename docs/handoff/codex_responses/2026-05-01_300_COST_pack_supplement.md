# 300-COST source-side guarded-publish 再評価 cost Pack supplement

Date: 2026-05-01 JST  
Lane: Codex B round 7 (doc-only / read-only)  
Parent draft: `docs/handoff/codex_responses/2026-05-01_300_COST_pack_draft.md` (`54c2355`)  
Source analysis: `docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis.md` (`7a946a8`)  
Purpose: fill the remaining 13-field Pack gaps for rollback, stop condition, mail-volume impact, execution/upload invariants, and the `298-Phase3` dependency order only

This supplement does not replace the parent draft. Read it together with:

- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
- `docs/ops/POLICY.md`
- `docs/ops/OPS_BOARD.yaml`
- `docs/ops/CURRENT_STATE.md`

Current recommendation remains `HOLD`. This supplement only makes the `300-COST` Pack explicit and complete.

## 1. rollback 3-tier fixed

| tier | action | exact command / action | expected time | owner | use when |
|---|---|---|---|---|---|
| 1 | env rollback | `gcloud run jobs update guarded-publish --region=asia-northeast1 --project=baseballsite --remove-env-vars=ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY` | `~30 sec` | Claude autonomous hotfix boundary if the authenticated executor is available; otherwise user-confirmed executor | First stop condition hit and the fastest way to make `300` live-inert |
| 2 | image rollback | `gcloud run jobs update guarded-publish --region=asia-northeast1 --project=baseballsite --image=<pre-300 guarded-publish image digest/SHA>` | `~2-3 min` | user-confirmed authenticated executor recommended | Tier 1 is insufficient, or runtime behavior still degrades after flag removal |
| 3 | state cleanup | Archive the current state objects first, then restore only the affected artifact if a ledger/cursor anomaly is proven: `guarded_publish_history.jsonl`, `publish_notice_cursor.txt`, `publish_notice_history.json`, `publish_notice_queue.jsonl` | anomaly-only | Claude directs; authenticated executor performs any live cleanup | Use only when Tier 1/2 are not enough because state itself is corrupted or drifted |

Notes:

- Tier 1 is the canonical first rollback because `300-COST` is designed as a default-OFF env-gated change.
- Tier 2 target must be the exact pre-300 guarded-publish image captured immediately before GO. Example form: `:6df049c`, but the real digest/SHA must be confirmed at deploy time.
- Tier 3 is not a normal rollback step. `300-COST` changes no schema and should not require cleanup unless a real anomaly is detected.
- If `300` and `298` are both live, rollback order is `300 -> 298`. Keep the downstream `298` sink-side guard ON unless the incident is proven to be inside `298`.

## 2. stop conditions and immediate action

### 2.1 fixed stop condition list

The following are the fixed stop conditions for `300-COST`. They align with `docs/ops/POLICY.md` §7 and §8.

| stop condition | why it matters | immediate action |
|---|---|---|
| real review emit decreases | `300` must not suppress legitimate review reminders while removing only unchanged `backlog_only` rows | Tier 1 rollback immediately |
| Team Shiny From changes | mail sender invariants are permanent no-touch policy | Tier 1 rollback immediately |
| `289` `post_gen_validate` emit decreases | `300` must not indirectly starve the separate visible skip path | Tier 1 rollback immediately |
| `errors > 0` | runtime regression is a hard stop even if row growth improves | Tier 1 rollback; move to Tier 2 if the next trigger is still unhealthy |
| silent skip increases | every candidate must remain visible through publish/review/hold/skip; internal-log-only outcomes are forbidden | Tier 1 rollback immediately |
| `cap=10/run` or `24h dedup` contract drifts | `300` must not disturb the downstream 4-layer defense; repeated old-candidate mail reappearance is P1 recurrence | Tier 1 rollback immediately |
| `MAIL_BUDGET` breach: rolling `1h > 30` or cumulative `day > 100` | budget violation is permanent P1 policy | Tier 1 rollback immediately |

### 2.2 baseline and monitor contract

Use the same stable baseline family that protects `298-Phase3`:

- `docs/handoff/codex_responses/2026-05-01_298_Phase3_stability_evidence_pre.md`
- `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md`
- `docs/ops/CURRENT_STATE.md`

What must remain true after `300` deploy:

- normal review path remains visible
- `289` `post_gen_validate` path remains visible
- `errors=0`
- `silent skip=0`
- Team Shiny From remains `y.sebata@shiny-lab.org`
- downstream `cap=10` and `24h dedup` behavior stays unchanged

## 3. mail volume impact: quantified estimate

### 3.1 classification

`300-COST` changes only the source-side guarded history append behavior. It does **not** add a new mail class, does **not** change `publish-notice` routing, and does **not** alter subject/cap/recipient/From rules.

Therefore:

- expected mails/hour delta: `0`
- expected mails/day delta: `0`
- `MAIL_BUDGET 30/h` and `100/d` compliance: unchanged from the post-`298` stable baseline
- classification: `Mail volume impact = NO`

### 3.2 what actually decreases

| surface | current | after Option C-narrow | direction |
|---|---|---|---|
| `guarded_publish_history.jsonl` raw row growth | `~28,800 rows/day` | `数百 rows/day` | about `-90%` |
| history raw growth | `~7-10 MB/day` | `~0.1-0.3 MB/day` | major reduction |
| `publish-notice` scanner new-row input | current repeated old backlog row volume | same-order reduction as source rows | reduction |
| scanner processing time | current repeated row scan cost | shorter | reduction |

Important interpretation:

- The reduction is **source-row volume**, not mail emit count.
- If real review mail, `289`, or visible skip volume drops, that is not a success metric. It is a stop condition.

## 4. execution count and GCS upload count: unchanged

`300-COST` reduces repeated row creation, but it does not change trigger cadence or the entrypoint upload pattern.

| metric | current | after `300-COST` only | change |
|---|---|---|---|
| Cloud Run job executions/day | `288` | `288` | `0%` |
| GCS object uploads/day | `288` | `288` | `0%` |
| history rows/day | `~28,800` | `数百` | about `-90%` |
| history payload growth/day | `~7-10 MB` | `~0.1-0.3 MB` | major reduction |

Why this stays flat:

- `guarded-publish-trigger` cadence remains `*/5`
- `bin/guarded_publish_entrypoint.sh` still performs whole-file upload after each run

Conclusion:

- `300-COST` is a **raw row / payload growth** reduction ticket
- it is **not** an execution-count reduction ticket
- it is **not** a GCS upload-count reduction ticket
- unchanged-upload skip belongs to a separate future ticket

## 5. linkage to `298-Phase3`

### 5.1 root-cause relationship

- `298-Phase3` is the sink-side protective layer for old-candidate mail behavior.
- `300-COST` is the source-side fix for the same repeated old-backlog surface.
- `298` stops the downstream storm path.
- `300` removes the upstream repeated unchanged `backlog_only` row generation that keeps feeding that surface.

### 5.2 deploy order and observation order

The order remains fixed:

1. `298-Phase3 v4` deploy
2. `24h` stable observe
3. `300-COST` deploy decision

Reason:

- `298-Phase3` is still `HOLD_NEEDS_PACK` / `ROLLED_BACK_AFTER_REGRESSION` in current ops state.
- `300` should not be the first live mutation while the sink-side protective layer is unresolved.
- If both `300` and `298` were changed in one window, rollback attribution and mail-causality would become ambiguous.

### 5.3 rollback order when both are live

This is fixed by the cross-pack consistency review:

- rollback `300` first
- keep `298` ON unless the incident is proven to be inside `298`

That preserves the downstream protective layer while removing the newer source-side experiment first.

## 6. 13-field completeness re-evaluation

This evaluates the Pack as **parent draft + this supplement** against `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`.

| # | required field | status | evidence path |
|---|---|---|---|
| 1 | Conclusion | YES | parent draft §4 |
| 2 | Scope | YES | parent draft §4 |
| 3 | Non-Scope | YES | parent draft §4 |
| 4 | Current Evidence | YES | parent draft §1-3 + this supplement §4-5 |
| 5 | User-Visible Impact | YES | parent draft §4 + this supplement §2-3 |
| 6 | Mail Volume Impact | YES | this supplement §3 |
| 7 | Gemini / Cost Impact | YES | parent draft §4 + this supplement §4 |
| 8 | Silent Skip Impact | YES | parent draft §4 + this supplement §2 |
| 9 | Preconditions | YES | parent draft §4 + this supplement §5 |
| 10 | Tests | YES | parent draft §3 + source analysis §6 |
| 11 | Rollback | YES | this supplement §1 |
| 12 | Stop Conditions | YES | this supplement §2 |
| 13 | User Reply | YES | parent draft §4 |

Result:

- Pack completeness with supplement: `13/13`
- UNKNOWN residual fields: `0`

Remaining pending items are operational gates, not Pack-field unknowns:

- `298-Phase3 v4` must deploy and pass `24h` stable observe first
- the exact pre-300 guarded-publish image digest/SHA must be captured before GO for Tier 2 rollback
- post-deploy observe must prove that real review / `289` / Team Shiny / `MAIL_BUDGET` remain stable

## 7. Claude handoff note

When Claude compresses this for the user, the key additions from this supplement are:

- rollback is explicitly **Tier 1 env / Tier 2 image / Tier 3 anomaly-only state cleanup**
- mail impact is **NO** in the emit sense; the reduction is in source-row growth and scanner input, not in visible routing
- execution count/day and upload count/day stay flat at `288`
- `300-COST` remains sequenced **after** `298-Phase3 v4 deploy + 24h stable`
- the Pack is now **13/13 complete**, while the correct recommendation still remains `HOLD`
