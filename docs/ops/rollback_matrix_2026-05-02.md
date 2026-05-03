# Rollback Matrix — 2026-05-02 Deploy Chain

Date: 2026-05-03 JST  
Mode: doc-only backfill, read-only evidence only, no deploy, no env mutation

## 1. Purpose

Normalize the 2026-05-02 deploy chain into one rollback artifact so incident response can use one document for:

- exact env rollback commands
- executable image fallback targets
- GitHub/source revert paths
- evidence links for last known good anchors

This backfill covers the six cases requested under BUG-009 subtask-3:

1. A: publish-notice 24h budget governor
2. B: publish-notice 289 digest
3. D: fetcher wiring fix
4. 282-COST flag ON
5. 291 narrow unlock / ledger / duplicate strict / publish-only filter bundle
6. 245 WP plugin upload

## 2. Evidence Used

- [docs/ops/bug009_rollback_target_audit.md](/home/fwns6/code/wordpressyoshilover/docs/ops/bug009_rollback_target_audit.md)
- [docs/handoff/session_logs/2026-05-02_morning_verify.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/session_logs/2026-05-02_morning_verify.md)
- [docs/handoff/codex_responses/2026-05-01_session_end_handoff.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-01_session_end_handoff.md)
- [docs/handoff/runbook/245_wp_plugin_upload.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/runbook/245_wp_plugin_upload.md)
- [doc/waiting/291-OBSERVE-candidate-terminal-outcome-contract.md](/home/fwns6/code/wordpressyoshilover/doc/waiting/291-OBSERVE-candidate-terminal-outcome-contract.md)
- [doc/waiting/277_audit_2026-05-03.md](/home/fwns6/code/wordpressyoshilover/doc/waiting/277_audit_2026-05-03.md)
- read-only `git log`, `git show --stat`, `git rev-parse`
- read-only `gcloud run jobs describe publish-notice`
- read-only `gcloud run services describe yoshilover-fetcher`

## 3. Exactness Legend

- `FULL`: env command, image target tag, digest, and GitHub revert are all exact in the allowed evidence set.
- `EXECUTABLE`: rollback command and tag/commit are exact and executable, but the allowed evidence set only preserves a digest prefix or no digest at all.
- `N/A`: that dimension does not exist for the target layer.

## 4. Summary Matrix

| case | target | env rollback | image rollback target | GitHub/source rollback | exactness |
|---|---|---|---|---|---|
| A | `publish-notice` | remove `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR` | `publish-notice:d541ebb` | `git revert 84a7d669b58033c3dbee53c11971eaa748a581e7` | `EXECUTABLE` |
| B | `publish-notice` | remove `ENABLE_289_POST_GEN_VALIDATE_DIGEST` | `publish-notice:84a7d66` | `git revert eaba749f0f4cf002a9ad7d1214c67fe7cd1291f7` | `EXECUTABLE` |
| D | `yoshilover-fetcher` | `none` | `yoshilover-fetcher:d541ebb` or revision `00177-qtr` | `git revert 422ba9596133b8797c2567769844217bcb2e5b8b` | `EXECUTABLE` |
| 282 | `yoshilover-fetcher` | remove `ENABLE_GEMINI_PREFLIGHT` | baseline stays `yoshilover-fetcher:84a7d66` | `N/A for the 2026-05-02 env-only apply` | `EXECUTABLE` |
| 291 | `yoshilover-fetcher` + `publish-notice` | remove narrow-unlock / ledger / mail-filter envs | fetcher fallback `:84a7d66`, publish-notice fallback `:eaba749` | revert landed 291 subtasks individually; subtask-9 not landed | `EXECUTABLE` |
| 245 | WP plugin | `N/A` | `N/A` | `git revert 46241cecc28e4e20731ca26bb477028b185178ba` | `FULL` |

## 5. Detailed Rollback Blocks

### A. 24h budget governor (`84a7d66`)

| dimension | normalized anchor |
|---|---|
| target | `publish-notice` Cloud Run Job |
| pre-apply live state | image `publish-notice:d541ebb` from [2026-05-02_morning_verify.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/session_logs/2026-05-02_morning_verify.md) (`rollback target capture`) |
| applied state | image `publish-notice:84a7d66`, digest prefix `sha256:76f93370`, env `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR=1` |
| env rollback | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR` |
| image rollback | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:d541ebb` |
| GitHub rollback | `git revert 84a7d669b58033c3dbee53c11971eaa748a581e7` |
| release composition window | `75bc5061fdcfd7728d2ab3d127bdba544ecca4ca..84a7d669b58033c3dbee53c11971eaa748a581e7` |
| owner / expected time | env `~30 sec`, image `~2-3 min`, source `commit + push + rebuild` |

### B. 289 digest (`eaba749`)

| dimension | normalized anchor |
|---|---|
| target | `publish-notice` Cloud Run Job |
| pre-apply live state | image `publish-notice:84a7d66`, digest prefix `sha256:76f93370` |
| applied state | image `publish-notice:eaba749`, digest prefix `sha256:765cf688`, env `ENABLE_289_POST_GEN_VALIDATE_DIGEST=1` |
| env rollback | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_289_POST_GEN_VALIDATE_DIGEST` |
| image rollback | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:84a7d66` |
| GitHub rollback | `git revert eaba749f0f4cf002a9ad7d1214c67fe7cd1291f7` |
| release composition window | `84a7d669b58033c3dbee53c11971eaa748a581e7..eaba749f0f4cf002a9ad7d1214c67fe7cd1291f7` |
| owner / expected time | env `~30 sec`, image `~2-3 min`, source `commit + push + rebuild` |

### D. fetcher wiring fix (`422ba95`)

| dimension | normalized anchor |
|---|---|
| target | `yoshilover-fetcher` Cloud Run Service |
| pre-apply live state | image `yoshilover-fetcher:d541ebb`, revision `yoshilover-fetcher-00177-qtr`, traffic `100%` |
| applied state | image `yoshilover-fetcher:84a7d66`, digest prefix `sha256:152a511a`, revision `yoshilover-fetcher-00180-4pp`, `ENABLE_PER_POST_24H_GEMINI_BUDGET` unset |
| env rollback | `none` |
| image rollback | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:d541ebb` |
| image rollback alternate | `gcloud run services update-traffic yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --to-revisions=yoshilover-fetcher-00177-qtr=100` |
| GitHub rollback | `git revert 422ba9596133b8797c2567769844217bcb2e5b8b` |
| release composition window | `d541ebb0b7b6f53af2d1152b1a95e3f375b227f6..422ba9596133b8797c2567769844217bcb2e5b8b` |
| owner / expected time | image `~2-3 min`, source `commit + push + rebuild` |

### 282-COST flag ON (`ENABLE_GEMINI_PREFLIGHT`)

| dimension | normalized anchor |
|---|---|
| target | `yoshilover-fetcher` Cloud Run Service |
| pre-apply live state | image `yoshilover-fetcher:84a7d66`, revision `yoshilover-fetcher-00180-4pp`, env `ENABLE_GEMINI_PREFLIGHT` absent |
| applied state | same image `yoshilover-fetcher:84a7d66`, revision `yoshilover-fetcher-00181-22g`, env `ENABLE_GEMINI_PREFLIGHT=1` |
| env rollback | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_GEMINI_PREFLIGHT` |
| image fallback baseline | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:84a7d66` |
| GitHub/source rollback | `N/A for the 2026-05-02 live step`. This was an env-only apply on top of already-live source/image. If runtime-only regression occurs, revert the env first. If source rollback is later required, use the owning ticket revert for the bundled image, not the 282 apply step itself. |
| release composition window | `84a7d669b58033c3dbee53c11971eaa748a581e7` live image retained |
| owner / expected time | env `~30 sec`, image fallback `~2-3 min` |

### 291 bundle (`f5c0250` / `09d5b93` / `398321d` / `a4a5de8` / `b57a50a`)

Current live state confirmed by read-only `gcloud describe` on 2026-05-03 JST:

- fetcher image `yoshilover-fetcher:398321d`
- fetcher env ON: `ENABLE_GEMINI_PREFLIGHT=1`, `ENABLE_NARROW_UNLOCK_NON_POSTGAME=1`, `ENABLE_BODY_CONTRACT_FAIL_LEDGER=1`
- fetcher env absent: `ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE`
- publish-notice image `publish-notice:a4a5de8`
- publish-notice env ON: `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`

| dimension | normalized anchor |
|---|---|
| target | `yoshilover-fetcher` Cloud Run Service + `publish-notice` Cloud Run Job |
| pre-291 fetcher baseline | `yoshilover-fetcher:84a7d66` after the 282 env apply |
| current fetcher state | `yoshilover-fetcher:398321d`, revision `yoshilover-fetcher-00183-6lz` |
| current publish-notice state | `publish-notice:a4a5de8` |
| fetcher env rollback | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_NARROW_UNLOCK_NON_POSTGAME,ENABLE_BODY_CONTRACT_FAIL_LEDGER,ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE` |
| publish-notice env rollback | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_PUBLISH_ONLY_MAIL_FILTER` |
| fetcher image rollback | `gcloud run services update yoshilover-fetcher --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:84a7d66` |
| publish-notice image rollback | `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:eaba749` |
| GitHub rollback: fetcher landed subtasks | `git revert b57a50a00eacc2793bac724c9f8383ba71280990 398321d6cda57d4795f5e97bdabb3e26b93811dd 09d5b9364c30b7c440044fd86931ae27eeca5681 f5c02509387f7a39e5bbefe4348afef91b2049c1` |
| GitHub rollback: publish-notice landed subtask | `git revert a4a5de81d1f334e0aaaeae032c53a490d560fab6` |
| GitHub rollback: doc-only audit | `adc17c4e90537ec344be6781705aaaa5be7ef2a4` is doc-only and does not affect runtime rollback. Revert only if the audit doc itself must be withdrawn. |
| subtask-9 state | not landed as of 2026-05-03 JST, `ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE` absent in current describe, so source/image rollback for subtask-9 is `N/A until land`; only the future env removal path is reserved above |
| 5/3 09:36 verify-window first stop | env-only rollback on current image is the first response path. If behavior still regresses, fall back to fetcher `:84a7d66` and publish-notice `:eaba749`. |
| owner / expected time | env `~30 sec`, image `~2-3 min`, source `commit + push + rebuild` |

#### 291 subtask mapping

| subtask | commit | runtime layer | rollback meaning |
|---|---|---|---|
| subtask-1 + 2 + 4 | `f5c02509387f7a39e5bbefe4348afef91b2049c1` | fetcher image | revert code if deterministic rescue / title floor / durable ledger module itself is wrong |
| subtask-3 | `09d5b9364c30b7c440044fd86931ae27eeca5681` | fetcher image + `ENABLE_NARROW_UNLOCK_NON_POSTGAME` | first-line live rollback is env removal; source rollback if branch logic itself is wrong |
| subtask-5 | `398321d6cda57d4795f5e97bdabb3e26b93811dd` | fetcher image + `ENABLE_BODY_CONTRACT_FAIL_LEDGER` | first-line live rollback is env removal; source rollback if hook itself is wrong |
| subtask-6 | `a4a5de81d1f334e0aaaeae032c53a490d560fab6` | publish-notice image + `ENABLE_PUBLISH_ONLY_MAIL_FILTER` | first-line live rollback is env removal; source rollback if sender/scanner filter logic is wrong |
| subtask-7 | `adc17c4e90537ec344be6781705aaaa5be7ef2a4` | docs only | no runtime rollback needed |
| subtask-8 | `b57a50a00eacc2793bac724c9f8383ba71280990` | fetcher image | source/image rollback only if duplicate target strictness itself regresses |
| subtask-9 | `not landed` | future fetcher env/image | leave `N/A` until commit hash, image tag, and env evidence exist |

### 245 WP plugin upload (`46241ce`)

| dimension | normalized anchor |
|---|---|
| target | manual WP plugin upload |
| env rollback | `N/A` |
| image rollback | `N/A` |
| live rollback target | re-upload immediate backup zip from WP admin step 3, then fallback order `v8 -> v7 -> v6` |
| GitHub rollback | `git revert 46241cecc28e4e20731ca26bb477028b185178ba` |
| owner / expected time | WP backup re-upload `~3 min`, repo revert `commit + push` |

## 6. 294 / Pack Alignment

### Required reinforcement

- `294` must explicitly mirror `POLICY §19.2 release composition verify`.
- `294` must explicitly mirror `POLICY §19.4 3-dimension rollback anchor`.
- `294` must treat `env/image/source` unknown or placeholder as an immediate `HOLD`, not a follow-up note.
- env-only changes must still record current live image baseline and current source baseline.

### ACCEPTANCE_PACK_TEMPLATE status

`docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` already contains the required `UNKNOWN => HOLD` rule for 3-dimension rollback anchors. No template text change is required for this subtask; the process doc must point at the current rule and stop lagging behind it.

## 7. Remaining Ambiguity

### Unknown count

- deploy-case unknown count: `0`
- digest-level ambiguity count: `4`

### Exact gaps that remain in the allowed evidence set

1. `publish-notice:d541ebb` full digest is not normalized in the searched markdown evidence set.
2. `yoshilover-fetcher:d541ebb` full digest is not normalized in the searched markdown evidence set.
3. `yoshilover-fetcher:398321d` current full digest is not exposed by the allowed `gcloud run services describe` output.
4. `publish-notice:a4a5de8` current full digest is not exposed by the allowed `gcloud run jobs describe` output.

These gaps do not block executable rollback because the tag/revision commands and GitHub revert paths are fixed. They do mean this artifact is `EXECUTABLE`, not fully `FULL`, for the Cloud Run rows.

## 8. Conclusion

- The six requested deploy cases now have one normalized rollback reference.
- All six cases have executable env/image/GitHub rollback paths or explicit `N/A`.
- The remaining weakness is digest completeness, not rollback-command availability.
