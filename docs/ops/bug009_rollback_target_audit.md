# BUG-009 rollback target 3-dim audit

Date: 2026-05-03 JST  
Mode: read-only audit, doc-only output, no deploy, no env mutation, no WP REST

## 1. Scope and method

- Read targets:
  - `docs/ops/POLICY.md`
  - `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
  - `doc/waiting/294-PROCESS-release-composition-gate.md`
  - `docs/handoff/runbook/245_wp_plugin_upload.md`
  - `docs/handoff/codex_responses/*deploy*.md` and nearby Pack docs
  - `docs/handoff/session_logs/2026-05-02_morning_verify.md`
- Read-only support evidence:
  - `git log --since='2026-05-01 00:00' --until='2026-05-03 23:59' --oneline`
  - `git show --stat` for deploy-related commits
- No `src/` or `tests/` edits.
- No Cloud Run / Scheduler / env / plugin live mutation.

Legend:

- `COMPLETE`: env / image / GitHub(source) rollback target is fully recorded, or an explicit `none` / plugin-backup equivalent is written with no ambiguity.
- `PARTIAL`: 1-2 dimensions are recorded, or a dimension is stale / generic / implied rather than exact.
- `UNKNOWN`: no usable rollback anchor is found in the searched record.

## 2. Canonical requirement audit

| artifact | observed state | audit result | note |
|---|---|---|---|
| `docs/ops/POLICY.md` | `§3.5`, `§3.6`, `§19.2`, `§19.4` require release composition verify, HOLD on unknown rollback, and exact env/image/source anchors | COMPLETE | Canonical policy is already strong enough for BUG-009 |
| `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` | `11. Rollback` + `Audit-Derived Required Fields A/B` require exact env rollback, exact image rollback, exact source revert, last known good anchor, and HOLD on placeholder/unknown | COMPLETE | Template matches current policy |
| `doc/waiting/294-PROCESS-release-composition-gate.md` | release composition is documented, but 3-dim rollback is not normalized at the same level as current policy/template; `doc_path` still points to `doc/active/...` while file lives in `doc/waiting/...` | PARTIAL | 294 lags behind the current canonical rules |
| `docs/handoff/runbook/245_wp_plugin_upload.md` | plugin upload runbook records no-env/no-image, immediate live backup rollback order, and repo revert `git revert 46241ce` | COMPLETE | Best current example of concrete rollback recording for a non-Cloud-Run target |
| recent deploy history docs | `293` / `282` have Pack-level rollback sections; 2026-05-02 A/B/D chain is recorded mainly in session log, not in a dedicated deploy Pack/report | PARTIAL | Process drift exists between canonical template and actual deploy logging |

## 3. Recent deploy-case audit (2026-05-02 to 2026-05-03)

| case | target and evidence | env rollback record | image rollback record | GitHub/source rollback record | classification |
|---|---|---|---|---|---|
| A. publish-notice 24h budget governor | `docs/handoff/session_logs/2026-05-02_morning_verify.md` lines covering 20:52-21:22 JST only | Apply `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR=1` is recorded, but exact remove command is not written | Pre image capture `publish-notice:d541ebb` and new image `84a7d66` are recorded in the session log | No exact `git revert 84a7d66` path is written in the searched docs | PARTIAL |
| B. publish-notice 289 digest | same session log, 21:27-21:42 JST | Apply `ENABLE_289_POST_GEN_VALIDATE_DIGEST=1` is recorded, but exact remove command is not written | New image `eaba749` is recorded; previous image is inferable from case A, but no exact rollback command is written | No exact `git revert eaba749` path is written in the searched docs | PARTIAL |
| D. fetcher wiring fix for change #3 | same session log, 21:07-21:20 JST | No env change occurred and default-OFF state is observed, but there is no explicit `env rollback: none` line | Pre image capture `fetcher:d541ebb` and new image `84a7d66` are recorded | No exact `git revert 422ba95` path is written in the searched docs | PARTIAL |
| 282-COST flag ON | `docs/handoff/codex_responses/2026-05-01_282_COST_pack_supplement.md`, `..._pack_v3_template_refresh.md`, and session log line at 22:51 JST | Exact remove command exists: `--remove-env-vars=ENABLE_GEMINI_PREFLIGHT` | Drift exists: supplement anchors image rollback to `:4be818d`, but the actual pre-apply live image on 2026-05-02 22:51 JST is `84a7d66`; refresh doc then marks image rollback as not applicable | Exact source revert hash is not fixed for the actual live apply; refresh doc says no source revert is required for the flag flip itself | PARTIAL |
| 291 subtask chain (`f5c0250`, `09d5b93`, `398321d`, `a4a5de8`, later subtasks) | `doc/waiting/291-OBSERVE-candidate-terminal-outcome-contract.md` plus commit history; no deploy Pack or live apply record found in searched runbooks/session logs | Generic flag-off/remove paths are described for `ENABLE_NARROW_UNLOCK_NON_POSTGAME` and `ENABLE_BODY_CONTRACT_FAIL_LEDGER` | No exact live image rollback command or exact pre-deploy image anchor is recorded | File-level or generic revert intent exists, but no exact `git revert <commit-set>` is recorded for the live bundle | PARTIAL |
| 245 WP plugin upload | `docs/handoff/runbook/245_wp_plugin_upload.md` | Explicit `env rollback target: none` | Explicit `Cloud Run image rollback target: none`; live rollback target is the immediate plugin backup, then `v8 -> v7 -> v6` zip order | Exact repo-level revert is recorded: `git revert 46241ce` | COMPLETE |

## 4. What the audit shows

### 4.1 Canonical docs are ahead of execution logs

- As of 2026-05-02 JST, `POLICY.md` and `ACCEPTANCE_PACK_TEMPLATE.md` already require exact 3-dim anchors and HOLD on unknown rollback.
- The gap is not mainly missing policy text.
- The gap is that some real deploys on 2026-05-02 were logged as operational session notes rather than as a Pack/report that repeated the exact env/image/source rollback matrix.

### 4.2 The 2026-05-02 A/B/D deploy chain is the main weak point

- Search results show `84a7d66`, `eaba749`, `422ba95`, `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR`, and `ENABLE_289_POST_GEN_VALIDATE_DIGEST` only in `docs/handoff/session_logs/2026-05-02_morning_verify.md` inside the searched markdown set.
- That means the deploy history exists, but the 3-dim rollback target is not independently normalized into a Pack/runbook/report artifact.
- Manual reconstruction is still possible from git and the session log, so this is not yet `CONTAMINATED`, but it is below the canonical standard.

### 4.3 Env-only/live-inert cases still drift on "image/source not applicable"

- `282-COST` is the clearest example.
- One doc records a concrete fallback image (`:4be818d`), but that anchor is stale after the 2026-05-02 A/B/D image updates.
- A later refresh doc then treats image rollback as not applicable and source revert as not required for the flag flip.
- Under current `POLICY §19.4`, this is not strong enough to call the case fully recorded.

### 4.4 291 has design-time rollback notes, but not deploy-ready 3-dim anchors

- The 291 contract doc is useful for subtask boundaries and generic rollback intent.
- However, it does not pin an exact live image anchor or an exact `git revert` commit set for a future live bundle.
- No searched deploy Pack/runbook/session-log entry proves that 291 live apply was packaged with exact env/image/GitHub rollback anchors.

## 5. Decision

## AT_RISK

Reason:

- Canonical rules are present, but only `245` is fully normalized in the searched 2026-05-02 to 2026-05-03 evidence set.
- `A`, `B`, `D`, `282`, and `291` are all below the current "exact 3-dim anchor" standard.
- No case in this audit is proven rollback-impossible right now because git/session-log reconstruction is still available.
- However, rollback readiness is inconsistent enough that unknown/stale anchors could slow recovery during the next incident.

Counts:

- deploy cases audited: `6`
- `COMPLETE`: `1`
- `PARTIAL`: `5`
- `UNKNOWN`: `0`

## 6. BUG-009 narrow fix proposals (no new ticket number)

### subtask-1: mandatory rollback matrix in every deploy report

Add a fixed block to all deploy reports, including `CLAUDE_AUTO_GO`:

```text
rollback_matrix:
  env:
    apply:
    rollback:
  image:
    current_live_before_apply:
    target_after_apply:
    rollback_command:
  source:
    release_composition_commits:
    revert_command:
    last_known_good_commit:
```

Acceptance:

- session-log-only deploy evidence is no longer sufficient by itself
- every deploy leaves one grep-able rollback block

### subtask-2: explicit `n/a` rule plus stale-anchor prohibition

Clarify one rule in Pack/template/process docs:

- `n/a` is allowed only when that dimension truly does not exist for the target layer
- env-only Cloud Run changes must still record the current live image baseline and source baseline as fallback anchors
- stale pre-change image anchors are invalid once a newer live image is already in production

Acceptance:

- `282`-style env-only Packs cannot pass with a stale image baseline or a generic source placeholder

### subtask-3: backfill 2026-05-02 chain into one normalized artifact

Backfill one doc-only record for:

- A `84a7d66`
- B `eaba749`
- D `422ba95`
- 282 env apply on top of `84a7d66`

Acceptance:

- exact env/image/source rollback anchor for the 2026-05-02 chain is captured in one place
- future incident response does not depend on replaying the whole session log

### subtask-4: refresh 294 so it mirrors current policy

Update `294-PROCESS-release-composition-gate` so it explicitly reflects:

- `POLICY §19.2` release composition verify
- `POLICY §19.4` 3-dim rollback anchor
- current folder/doc_path reality

Acceptance:

- 294 is no longer older/weaker than `POLICY.md`
- deploy process docs stop splitting "release composition" and "rollback matrix" into separate, uneven standards

## 7. Recommended next Claude decision

- Treat BUG-009 as `AT_RISK`, not `CLEAN`.
- Do not escalate to `CONTAMINATED` unless a live target is found with no reconstructable previous image/env/source anchor at all.
- Next best action is BUG-009 subtask-3 first, because it closes the highest-value operational gap with doc-only work and no live mutation.
