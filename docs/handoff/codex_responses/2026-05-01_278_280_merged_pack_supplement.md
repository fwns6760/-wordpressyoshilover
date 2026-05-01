# 278-280 merged quality improvement Pack supplement

Date: 2026-05-01 JST  
Lane: Codex A round 10 (doc-only / read-only)  
Parent draft: `docs/handoff/codex_responses/2026-05-01_278_280_merged_pack_draft.md` (`0521a25`)  
Purpose: fill the remaining 13-field Pack gaps for rollback, stop condition, mail-volume impact, 290 linkage, phase order, and completeness only

This supplement does not replace the parent draft. Read it together with:

- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
- `docs/ops/POLICY.md`
- `docs/ops/CURRENT_STATE.md`
- `docs/ops/OPS_BOARD.yaml`

Current recommendation remains `HOLD`.

## 0. source-of-truth and phase normalization lock

- `docs/ops/POLICY.md` §1 makes `POLICY.md -> CURRENT_STATE.md -> OPS_BOARD.yaml` the canonical current truth.
- As of `2026-05-01 JST`, `278/279/280` no longer have an active or future-user-go row in the current `OPS_BOARD.yaml` / `CURRENT_STATE.md`. The parent draft's older board-row references are therefore **history-only**, not current active state.
- This supplement keeps `0521a25` as a **historical merged-pack draft supplement** only. It does not recreate a new active board entry and does not change the current `HOLD` posture.
- Phase labels below follow the **merged-pack numbering** requested for user-facing consistency, not the raw repo ticket IDs.

| merged phase label | merged meaning | raw repo ticket / code anchor | live component |
|---|---|---|---|
| `278 phase 1` | title backfill | raw `277` (`8e9f5d8`) + `290` residual-only adjacency, but not a new ticket | `yoshilover-fetcher` |
| `279 phase 2` | RT cleanup | raw `278` RT cleanup scope | `yoshilover-fetcher` |
| `280 phase 3` | mail subject cleanup + summary/excerpt cleanup | raw `279` + raw `280` bundled | `publish-notice` |

Release-composition lock:

- Tier 3 rollback must follow `doc/active/294-PROCESS-release-composition-gate.md`.
- In other words, Tier 3 reverts the **actual phase commit set included in the built image**, not just the nearest ticket number in isolation.

## 1. rollback 3-tier fixed

### 1.1 fixed old-image anchors

| component | canonical old image anchor | evidence path |
|---|---|---|
| fetcher | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d` | `docs/handoff/codex_responses/2026-05-01_298_Phase3_stability_evidence_pre.md` `Q8`; `2026-05-01_290_QA_pack_supplement.md` |
| publish-notice | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice@sha256:644a0ff30494bd41c078ea4a08179ba8b41ad507a66af47677c6c430176059e2` (`publish-notice:1016670`) | `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md`; `2026-05-01_298_Phase3_stability_evidence_pre.md` `Q7` |

Important normalization:

- For this Pack, the canonical publish-notice rollback target is **`publish-notice:1016670`**, not historical `:dc02d61`.
- `:dc02d61` remains useful as older ticket history, but current policy-source-of-truth says the present safe live baseline is `1016670` with the old-candidate flag absent.

### 1.2 per-phase rollback table

| phase | Tier 1 env rollback | Tier 2 image rollback | Tier 3 commit revert | expected time | use when |
|---|---|---|---|---|---|
| `278 phase 1` title backfill | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_TITLE_BACKFILL` | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d` | `git revert <phase1_title_backfill_commit_set>` -> rebuild -> redeploy. Current code anchor for the already-landed raw title-backfill path is `8e9f5d8`; the exact future phase-1 revert set must be locked by the 294 release-composition gate before GO. | Tier 1 `~30 sec`, Tier 2 `~2-3 min`, Tier 3 rebuild dependent | first stop condition hit; Tier 3 only if code itself must be removed |
| `279 phase 2` RT cleanup | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_RT_CLEANUP` | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d` | `git revert <phase2_rt_cleanup_commit_set>` -> rebuild -> redeploy. Exact commit set is future and must be locked at GO by the 294 gate. | Tier 1 `~30 sec`, Tier 2 `~2-3 min`, Tier 3 rebuild dependent | front-title regression or unintended RT/off-field routing drift |
| `280 phase 3` mail subject cleanup + summary/excerpt cleanup | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_MAIL_SUBJECT_CLEANUP` | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice@sha256:644a0ff30494bd41c078ea4a08179ba8b41ad507a66af47677c6c430176059e2` | `git revert <phase3_mail_cleanup_commit_set>` -> rebuild -> redeploy. If raw `279` and raw `280` are deployed as one publish-notice bundle, Tier 3 reverts the bundle commit set together. | Tier 1 `~30 sec`, Tier 2 `~2-3 min`, Tier 3 rebuild dependent | subject/body regression, Team Shiny drift, or mail-path regression |

Fixed rollback rule:

- Tier 1 is the canonical first response for all three phases.
- Tier 2 is the canonical second response if the next trigger still shows degraded behavior.
- Tier 3 is repo-level removal only after the exact phase build composition is locked and the problem is proven to be in code, not just in the env-gated live activation.

## 2. stop conditions and immediate action

These stop conditions align with `docs/ops/POLICY.md` §7 and §8.

| stop condition | affected phase(s) | why it matters | immediate action |
|---|---|---|---|
| silent skip increases | all phases | violates `POLICY.md` §8; every candidate must remain visible through publish/review/hold/skip | phase-local Tier 1 rollback immediately |
| Gemini call delta `> 0` | all phases | all three phases are intended as regex / metadata / string-format changes only; any extra Gemini activity is reverse-direction behavior | phase-local Tier 1 rollback immediately |
| Team Shiny From / `289 post_gen_validate` / error-notification path changes | all phases, especially phase 3 | `POLICY.md` §7 requires normal review, `289`, and error notifications to stay alive; Team Shiny identity is no-touch | phase-local Tier 1 rollback; escalate to Tier 2 if the next trigger is still degraded |
| WP front large title drift | phase 2 direct, phase 1 secondary | RT cleanup changes fetcher-side titles that surface on WP front; broad drift means scope escaped the narrow target | phase 2 Tier 1 rollback immediately |
| mail subject prefix drift or prefix ambiguity | phase 3 | if `publish / review / hold / old candidate / X suppress` are no longer distinguishable from the subject line, the whole goal of phase 3 failed | phase 3 Tier 1 rollback immediately |
| `MAIL_BUDGET` breach: rolling `1h > 30` or cumulative `day > 100` | phase 1 minor risk, phase 3 watch item | `POLICY.md` §7 defines this as P1 | phase-local Tier 1 rollback immediately |

Practical interpretation:

- Phase 2 should be stopped on **user-visible title surface drift**, not only on runtime error.
- Phase 3 should be stopped on **classification / subject-surface drift**, even if send volume does not explode yet.
- If any stop condition persists through the next scheduled trigger after Tier 1, move to Tier 2.

## 3. mail volume impact: quantified estimate

### 3.1 baseline carried into this estimate

Use the current stable-band references already locked elsewhere:

- post-rollback rolling band: `2026-05-01 14:15 JST` observe `5-6 mails/hour`, `errors=0`, `silent skip=0`
- stable-slice proxy used in the 290 supplement: `~79 mails/day`

These numbers are the relevant safety band for this Pack. If the baseline itself is no longer stable, this Pack remains `HOLD`.

### 3.2 phase-by-phase forecast

| phase | expected mail delta | hard ceiling | why |
|---|---|---|---|
| `278 phase 1` title backfill | `+1 to +3/day`, usually `0 to +1/h` | `+7/day` and worst-case same-hour clustering still below the `290` upper bound | rescued weak-title residuals become visible publish/review candidates instead of staying weak or deferred |
| `279 phase 2` RT cleanup | `0/day`, `0/h` | `0` | front/title normalization only; no new mail class, no new scanner, no new trigger |
| `280 phase 3` mail subject cleanup + summary/excerpt cleanup | `0/day`, `0/h` | `0` | subject/body text formatting only; emit count should remain unchanged |

### 3.3 integrated reading

- `278 phase 1` is the **only** phase with a planned positive mail delta.
- Because `278 phase 1` is explicitly the **residual path after `290`**, its expected live delta should be smaller than the `290` rescue upper bound already modeled elsewhere.
- Integrated Pack forecast:
  - expected net delta: `+1 to +3/day`
  - hard ceiling: `+7/day`
  - expected hourly impact: usually `0 to +1/h`
- On the current stable-band baseline, that remains within:
  - `MAIL_BUDGET 30/h`
  - `MAIL_BUDGET 100/d`

Classification:

- `Mail volume impact = YES (minor increase)`
- source of increase = `278 phase 1` rescue visibility only
- `279 phase 2` and `280 phase 3` must remain **mail-count neutral**

If phase 2 or phase 3 changes actual emit count, that is not a success metric. It is a stop condition.

## 4. 290 subset / complement relationship fixed

- `290-QA` weak-title rescue is the **deterministic subset** of the broader title-backfill surface.
- `278 phase 1` is therefore **not** a reimplementation of `c14e269`; it is the residual path for cases left unsolved after `290`.
- Safe sequencing is fixed:
  1. `290` deploy
  2. `290` stable for `24h`
  3. then `278 phase 1`
- Why this order is safer:
  - `290` already has a narrower, env-gated rollback model
  - the residual weak-title population becomes measurable only after `290` is live
  - phase 1 can then target the leftover gap without re-opening the narrower `290` predicates

Fixed interpretation:

- `290 deploy + 24h stable` is the gate for **starting** merged phase work.
- `279 phase 2` and `280 phase 3` do **not** start in parallel with `290`.
- They start only after `278 phase 1` proves stable.

## 5. phase deploy order proposal

The phase order remains fixed:

1. `278 phase 1` deploy
2. `24h` observe
3. `279 phase 2` deploy
4. `24h` observe
5. `280 phase 3` deploy

### 5.1 per-phase observation checklist

| phase | must verify before advancing |
|---|---|
| `278 phase 1` | `MAIL_BUDGET` within band, `silent skip=0`, Gemini delta `0`, Team Shiny unchanged, residual weak-title candidates gain a visible route |
| `279 phase 2` | all phase-1 checks plus no large WP front title drift, no unrelated off-field/title contamination, `289` and error path unchanged |
| `280 phase 3` | all phase-2 checks plus subject prefixes remain distinct, summary/excerpt cleanup stays mail-count neutral, Team Shiny / `289` / error path unchanged |

### 5.2 no-overlap rule

- Do not deploy the next phase in the same 24h window.
- Do not combine phase 2 and phase 3 into one live mutation window even though they are both quality work.
- The only allowed bundle inside this Pack is **raw `279` + raw `280` combined inside `280 phase 3`**, because they share `publish-notice` ownership and should still be observed as one last phase.

## 6. 13-field completeness re-evaluation

This evaluates the Pack as **parent draft + this supplement** against `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`.

| # | required field | status | evidence path |
|---|---|---|---|
| 1 | Conclusion | YES | parent draft §4 |
| 2 | Scope | YES | parent draft §4 + this supplement §0 / §5 |
| 3 | Non-Scope | YES | parent draft §4 |
| 4 | Current Evidence | YES | parent draft §1-3 + this supplement §0 / §1 |
| 5 | User-Visible Impact | YES | parent draft §4 + this supplement §2 / §5 |
| 6 | Mail Volume Impact | YES | this supplement §3 |
| 7 | Gemini / Cost Impact | YES | parent draft §4 + this supplement §2 |
| 8 | Silent Skip Impact | YES | parent draft §4 + this supplement §2 |
| 9 | Preconditions | YES | parent draft §4 + this supplement §4 / §5 |
| 10 | Tests | YES | parent draft §2-3 + `doc/active/277-QA-title-player-name-backfill.md`, `278-QA-rt-title-cleanup.md`, `279-QA-mail-subject-clarity.md`, `280-QA-summary-excerpt-cleanup.md`, `290-QA-weak-title-rescue-backfill.md` acceptance sections |
| 11 | Rollback | YES | this supplement §1 |
| 12 | Stop Conditions | YES | this supplement §2 |
| 13 | User Reply | YES | parent draft §4 |

Result:

- Pack completeness with supplement: `13/13`
- UNKNOWN residual fields: `0`

Remaining pending items are operational gates, not Pack-field UNKNOWNs:

- `290 deploy + 24h stable` must happen first
- the exact phase commit set included in each live image must be locked by the `294` release-composition gate before GO
- each phase still needs its own deploy evidence and `24h` observe evidence

## 7. Claude handoff note

When Claude compresses this for the user, the key additions from this supplement are:

- rollback is now explicitly fixed as **Tier 1 env -> Tier 2 old image -> Tier 3 phase-commit revert**
- the canonical old images are **fetcher `:4be818d`** and **publish-notice `:1016670` / digest `sha256:644a0ff30494bd41c078ea4a08179ba8b41ad507a66af47677c6c430176059e2`**
- stop conditions now explicitly include:
  - `silent skip`
  - Gemini delta `> 0`
  - Team Shiny / `289` / error-path drift
  - WP front large title drift
  - mail subject-prefix drift
  - `MAIL_BUDGET 30/h` or `100/d` violation
- mail impact is no longer vague:
  - phase 1 = **minor increase**
  - phase 2 = **no change**
  - phase 3 = **no change**
  - integrated effect = **small increase, still budget-safe on the current stable band**
- the Pack is now `13/13 complete`, while the correct recommendation still remains `HOLD`
