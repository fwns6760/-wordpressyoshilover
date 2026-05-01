# change-30 cap=10 class reserve pack v1

Date: 2026-05-01 JST  
Mode: Lane B round 18 / impl + test / pre-deploy HOLD  
Pack status: field-complete / default-OFF / user-decision-gated

## Decision Header

```yaml
ticket: 改修-30-cap10-class-reserve
recommendation: HOLD
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: low-medium(scanner allocation change inside cap=10 shared path)
classification: USER_DECISION_REQUIRED
user_go_reason: MAIL_STORM_PROTECTION_ENHANCEMENT
expires_at: 298-v4 24h stability close + 293 deploy complete
```

## 1. Conclusion

- **HOLD**
- code/test は ready だが、deploy + flag ON は `298-v4` 24h 安定と `293` deploy 完了後にだけ判断する。

## 2. Scope

- `src/publish_notice_scanner.py`
  - class reserve env knobs 追加
  - notice class classifier 追加
  - shared cap=10 selection を class reserve aware に変更
  - flag ON 時だけ combined preview/select + cursor freeze を適用
- `tests/test_publish_notice_scanner_class_reserve.py`
  - reserve 5 cases + scan integration 1 case
- `docs/handoff/codex_responses/2026-05-01_change_30_cap10_class_reserve_pack_v1.md`
- `docs/handoff/codex_prompts/2026-05-01/lane_b_round_18_cap10_class_reserve.md`

## 3. Non-Scope

- Cloud Run deploy / image rebuild / Scheduler / Secret / env apply
- `src/mail_*` / `publish_notice_email_sender.py`
- dedup 24h window
- permanent old-candidate ledger contract
- `config/rss_sources.json`
- source ingestion / Gemini / SEO / noindex / canonical / 301
- fetcher / guarded-publish runtime behavior outside publish-notice scanner selection

## 4. Current Evidence

- implementation scope stayed inside:
  - `src/publish_notice_scanner.py`
  - `tests/test_publish_notice_scanner_class_reserve.py`
- targeted regressions:
  - `python3 -m pytest tests/test_publish_notice_scanner_class_reserve.py tests/test_post_gen_validate_notification.py tests/test_preflight_skip_notification.py tests/test_publish_notice_scanner.py`
  - result: `65 passed`
- full regression:
  - `python3 -m pytest`
  - result: `2029 passed, 0 failed`
- production/context anchors used:
  - `docs/ops/POLICY.md §19.9`
  - `docs/ops/INCIDENT_LIBRARY.md`
  - `doc/active/205-COST-publish-notice-incremental-scan-retroactive-accept.md`
- current runtime assumption for this Pack:
  - `ENABLE_PUBLISH_NOTICE_CLASS_RESERVE` is absent/off
  - current live cap remains the existing shared `cap=10`
  - this round has **no deploy**

## 5. User-Visible Impact

- current round itself: production impact `0`
- after future image rebuild with flag OFF:
  - user-visible behavior should stay unchanged
  - reserve code path stays unreachable
- after future flag ON:
  - `real_review` keeps minimum `3`
  - `289 post_gen_validate` keeps minimum `2`
  - `error notification` keeps minimum `1` when scanner-side supply exists
  - remaining slots still stay inside existing cap `10`
- publish / hold / skip / X candidate contracts are unchanged by default-OFF deploy

## 6. Mail Volume Impact

- this round now: `0` mails/hour, `0` mails/day, no production mutation
- future deploy with flag OFF:
  - expected mail delta: `0`
  - cap remains `10/run`
  - MAIL_BUDGET expectation remains unchanged
- future flag ON:
  - total cap remains `10/run`
  - class mix changes, not total mail count
- UNKNOWN mail volume is **NO** for this code path because total cap is unchanged

## 7. Gemini / Cost Impact

- Gemini call increase: **NO**
- token increase: **NO**
- source/candidate count increase: **NO**
- cache impact: **NO**
- runtime cost delta: negligible scanner-side selection only

## 8. Silent Skip Impact

- visibility contract stays:
  - publish
  - review
  - hold
  - visible skip(`289` / `293` path when enabled)
- flag ON behavior does not drop candidates silently:
  - unselected preview rows do not advance their cursor
  - selected rows alone enter history / queue
  - skipped reserve overflow rows remain eligible for next trigger
- internal log only path was not added

## 9. Preconditions

All must be `YES` before GO.

| precondition | judgment | note |
|---|---|---|
| `298-v4` 24h stability close | **NO** | prompt contract says wait for close before GO |
| `293` deploy complete | **NO** | prompt contract says class reserve GO is after 293 deploy |
| full pytest regression green | **YES** | `2029 passed, 0 failed` |
| diff remains narrow(`src 1 + tests 1 + pack 1 + prompt 1`) | **YES** | current staged intent matches contract |
| mail path LLM-free invariant | **YES** | no `src/mail_*` or sender touch |

## 10. Tests

- unit selection:
  - real review minimum preserved
  - post_gen_validate minimum preserved
  - error minimum preserved
  - unused reserve slots transfer
  - priority order preserved
- integration:
  - shared cap=10 across guarded/post_gen/preflight
  - unselected classes keep cursor frozen
- regression:
  - `tests/test_post_gen_validate_notification.py`
  - `tests/test_preflight_skip_notification.py`
  - `tests/test_publish_notice_scanner.py`
- full suite:
  - `2029 passed, 0 failed`

## 10a. Post-Deploy Verify Plan

7-point plan for the future deploy/flag decision:

1. confirm publish-notice image changed and job startup succeeds with no new error burst
2. confirm `ENABLE_PUBLISH_NOTICE_CLASS_RESERVE` remains absent/off for inert deploy
3. confirm normal review / `289` / existing error route counts remain alive
4. confirm `sent` stays inside `cap=10/run` and MAIL_BUDGET guard remains green
5. confirm silent skip stays `0` and no candidate disappearance appears in logs/mail counts
6. confirm Team Shiny From and mail subject/from invariants remain unchanged
7. if flag ON is later tested, compare mixed-class batches and verify `real_review>=3`, `post_gen_validate>=2`, `error>=1` under congestion

## 10b. Production-Safe Regression Scope

Allowed checks only:

- Cloud Run Job image/env describe
- execution success/failure trend
- scanner summary logs
- mail count / route presence
- queue/cursor/history observation
- flag OFF inert deploy observation
- sample mixed-class notice counts from existing ledgers/logs

Forbidden checks:

- bulk mail experiments
- source addition
- Gemini increase
- publish criteria change
- cleanup mutation
- Scheduler/env changes without GO
- irreversible live mutation

## 11. Rollback

### Runtime rollback

- env rollback:
  - `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --remove-env-vars=ENABLE_PUBLISH_NOTICE_CLASS_RESERVE,PUBLISH_NOTICE_CLASS_RESERVE_REAL_REVIEW,PUBLISH_NOTICE_CLASS_RESERVE_POST_GEN_VALIDATE,PUBLISH_NOTICE_CLASS_RESERVE_ERROR`
- image rollback:
  - `gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4be818d`
- expected rollback time:
  - env only `~30 sec`
  - image rollback `~2-3 min`
- rollback owner:
  - Claude authenticated executor
- last known good runtime anchor used by this Pack:
  - image `publish-notice:4be818d`
  - code baseline = pre-class-reserve publish-notice scanner

### GitHub / source rollback

- this round is designed as a single implementation commit
- source rollback path:
  - `git revert <this round single implementation commit>`
- owner:
  - Claude after push / deploy judgment

### Pre-Deploy Gate 5-step result

| gate | result | note |
|---|---|---|
| release composition verify | **PASS** | intended commit scope is 4 files only |
| dirty worktree snapshot | **PASS_WITH_EXCLUSIONS** | unrelated pre-existing dirt remains unstaged |
| silent skip grep class | **PASS** | no new missing-payload path introduced; existing targeted regressions green |
| 3-dim rollback anchor | **PASS** | env/image/source paths fixed in this Pack |
| mail path LLM-free invariant | **PASS** | no mail module touch |

## 12. Stop Conditions

- `cap=10/run` changes
- 24h dedup drifts
- `real_review` / `289` visible path shrinks unexpectedly
- cursor advances for unselected overflow rows
- Team Shiny From changes
- new silent skip appears
- scanner deploy requires touching mail sender or Scheduler

## 13. User Reply

`OK` / `HOLD` / `REJECT`
