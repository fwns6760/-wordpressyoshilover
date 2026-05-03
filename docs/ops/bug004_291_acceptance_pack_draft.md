# BUG-004+291 acceptance pack draft

Last updated: 2026-05-03 JST
Status: `partial`
Canonical template: `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
Canonical acceptance criteria source: `doc/waiting/291-OBSERVE-candidate-terminal-outcome-contract.md`

This draft is worker C `SIDE_READONLY` output only. It changes no runtime behavior and exists to normalize the parent ticket's acceptance boundary before worker A/B evidence is appended.

## 1. DECISION

| field | value |
|---|---|
| ticket | `BUG-004+291` |
| recommendation | `HOLD` |
| classification | `HOLD` |
| decision_owner | `Claude` |
| reason | acceptance criteria are now explicit, but worker A/B evidence and the exact pre-`6095468` fetcher image rollback anchor are not yet normalized into one Pack |

## 2. EXECUTION

| field | value |
|---|---|
| owner | `Codex worker C` |
| scope | `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` 13-item normalization, `291` acceptance lock, this partial Pack draft |
| non_scope | src/tests/config changes, deploy, env, Scheduler, SEO, source add, Gemini call, mail emission, WP REST |
| live_mutation | `none` |

## 3. EVIDENCE

### commit

| hash | summary |
|---|---|
| `f5c0250` | `291: subtask-1+2+4 impl (weak_title_rescue rules + title floor helper + body_contract_fail ledger module, default OFF)` |
| `09d5b93` | `291: subtask-3 rss_fetcher narrow unlock wiring (default OFF, live-inert, postgame/stale/duplicate exclusions)` |
| `398321d` | `291: subtask-5 rss_fetcher body_contract skip hook (default OFF, live-inert, ledger writer hook)` |
| `a4a5de8` | `291: subtask-6 publish-only Gmail filter (default OFF, diagnostics to ledger/log/digest)` |
| `b57a50a` | `291: subtask-8 duplicate target integrity strict (default OFF, exact source_url_hash match, no silent drop)` |
| `f005ef5` | `291: record publish recovery rescue boundaries` |
| `6095468` | `291: subtask-9 subtype-aware narrow unlock for 8 categories (default OFF, deterministic, exclusions preserved)` |

### image

| target | current evidence |
|---|---|
| `guarded-publish` | live apply record exists: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc`, previous image `:9e9302f` |
| `yoshilover-fetcher` | session log records deploy to image tag `6095468`, revision `00184-mnz`; exact pre-apply image digest/revision is not yet normalized in repo-visible evidence |

### env

| target | current evidence |
|---|---|
| `guarded-publish` | `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1` |
| `yoshilover-fetcher` | `ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE=1` |

### execution

| target | current evidence |
|---|---|
| `guarded-publish` | `docs/handoff/codex_responses/2026-05-03_291_subtask_8_guarded_publish_deploy.md` records `guarded-publish-pvgdr` success after apply |
| `yoshilover-fetcher` | `docs/handoff/session_logs/2026-05-03_subtask_chain.md` records `291-subtask-9` deploy to revision `00184-mnz` and first verify slice |

### log

| signal | current evidence |
|---|---|
| `duplicate_target_integrity_check` | observed after subtask-8 apply |
| `weak_title_subtype_aware` | verify-1 observed `emit=0 (no weak title)` |
| publish-path heartbeat | verify-1 observed `drafts_created=1 general / error=0` |

### evidence gaps

- worker A output is not yet appended
- worker B output is not yet appended
- exact pre-`6095468` fetcher image rollback anchor is still missing

## 4. USER_GO_REQUIRED

| field | value |
|---|---|
| is | `false` |
| category | `none` |

## 5. USER_GO_REASON

| field | value |
|---|---|
| summary | `none for this draft; current work is doc-only and live-inert` |
| max_risk | `stale acceptance evidence if later 291 mutations land without this draft being refreshed` |
| rollback_ready | `yes for this doc-only draft itself; parent runtime Pack remains partial` |

## 6. NEXT_REVIEW_AT

| field | value |
|---|---|
| trigger | worker A/B evidence lands, or a new 291 runtime mutation / rollback occurs, or the 30-60min verify window evidence is added to repo-visible docs |

## 7. EXPIRY

| field | value |
|---|---|
| invalidates_when | any new `291` code commit, env flip, image update, rollback, or acceptance-criteria change occurs |

## 8. ROLLBACK_TARGETS

### env

| target | apply | rollback | owner |
|---|---|---|---|
| `yoshilover-fetcher` | `gcloud run services update yoshilover-fetcher --project baseballsite --region asia-northeast1 --update-env-vars=ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE=1` | `gcloud run services update yoshilover-fetcher --project baseballsite --region asia-northeast1 --remove-env-vars=ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE` | authenticated executor / Claude |
| `guarded-publish` | `gcloud run jobs update guarded-publish --project baseballsite --region asia-northeast1 --update-env-vars=ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1` | `gcloud run jobs update guarded-publish --project baseballsite --region asia-northeast1 --remove-env-vars=ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT` | authenticated executor / Claude |

### image

| target | current_live_before_apply | target_after_apply | rollback | owner |
|---|---|---|---|---|
| `guarded-publish` | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:9e9302f` | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc` | `gcloud run jobs update guarded-publish --project baseballsite --region asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:9e9302f` | authenticated executor / Claude |
| `yoshilover-fetcher` | `OPEN: exact pre-6095468 image / revision not yet normalized in repo-visible evidence` | `yoshilover-fetcher:6095468` (`rev 00184-mnz`) | `OPEN: exact rollback command must be fixed before final accept` | authenticated executor / Claude |

### github

| field | value |
|---|---|
| release_composition_commits | `6095468`, `b57a50a`, `a4a5de8`, `398321d`, `09d5b93`, `f5c0250` |
| revert | `git revert 6095468 b57a50a a4a5de8 398321d 09d5b93 f5c0250` |
| owner | `Claude / Codex` |

## 9. POST_DEPLOY_VERIFY

| field | value |
|---|---|
| required | `true` |
| observed_status | `PARTIAL` |

### commands

```bash
gcloud run services describe yoshilover-fetcher --project baseballsite --region asia-northeast1
gcloud run jobs describe guarded-publish --project baseballsite --region asia-northeast1
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND textPayload:"weak_title_subtype_aware"' --project baseballsite --freshness=60m --limit=20 --order=desc --format='value(timestamp,textPayload)'
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND textPayload:"rss_fetcher_flow_summary"' --project baseballsite --freshness=60m --limit=20 --order=desc --format='value(timestamp,textPayload)'
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="guarded-publish" AND (jsonPayload.event="duplicate_target_integrity_check" OR textPayload:"duplicate_target_integrity_check")' --project baseballsite --freshness=60m --limit=20 --order=desc --format='value(timestamp,textPayload,jsonPayload)'
```

### success signals

- fetcher revision remains the expected `subtask-9` image / env pair
- guarded-publish remains the expected `subtask-8` image / env pair
- `duplicate_target_integrity_check` is observed after apply
- `weak_title_subtype_aware` either emits for a rescued weak-title candidate or is explicitly absent because no weak-title candidate appeared
- publish/review/hold/skip/`queued_visible` drain is explainable, with no silent disappearance
- `error=0`
- no erroneous publish

## 10. STOP_CONDITION

- `silent skip > 0`
- erroneous publish appears
- `weak_title_subtype_aware` path emits but breaks subtype / Giants / source_url / body_contract guard
- `duplicate_target_integrity_check` disappears after apply when duplicate candidates still exist
- mail volume increases relative to baseline
- Gemini call count increases relative to baseline
- exact fetcher image rollback anchor remains unknown when Claude tries to final-accept the Pack

## 11. REGRESSION

### required_checks

- `postgame strict`, `stale_postgame`, duplicate, `hard_stop`, numeric, placeholder, `body_contract_fail` exclusions remain intact
- no new normal Gmail class is added
- `body_contract_fail` remains ledger-visible, not per-post normal mail
- source add, Scheduler, SEO, WP body, and publish-state mutation stay out of scope
- read-only verify shows no new errors

### forbidden_expansion

- source addition
- Scheduler mutation
- SEO / noindex / canonical / `301` changes
- Gemini fallback expansion
- new mail path or higher mail budget
- WP REST write

## 12. MAIL_GEMINI_DELTA

| field | value |
|---|---|
| mail_delta | `unchanged or lower` is required; current repo-visible evidence shows no new mail path, but full live count is still pending worker A/B + verify append |
| gemini_delta | `unchanged or lower` is required; current evidence shows deterministic rescue / integrity work only |
| invariant | `new mail emission path = 0`, `new prompt path = 0`, `new Gemini fallback = 0` |

## 13. OPEN_QUESTIONS

- What is the exact pre-`6095468` fetcher image digest / revision for image rollback?
- Which worker A evidence and worker B evidence should be added as the final acceptance witnesses for `publish/review/hold/skip/queued_visible` drain?
- Does the final Pack want a dedicated `queued_visible -> terminal outcome` sample row, or is scanner/ledger evidence enough once A/B outputs arrive?
