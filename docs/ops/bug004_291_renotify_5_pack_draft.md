# BUG-004+291 renotify 5 Acceptance Pack draft

Last updated: 2026-05-03 JST  
Mode: read-only audit + doc-only draft  
Canonical template: `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`  
Status: `USER_DECISION_REQUIRED`  
USER_DECISION_REQUIRED: `true`  
Reason: `MAIL_VOLUME_INCREASE_ONE_SHOT`

This Pack draft covers only the one-shot re-notify question for the 5 already-published posts confirmed in `docs/handoff/codex_responses/2026-05-03_BUG004_291_notify_track.md`:

- `64194`
- `64196`
- `64198`
- `64343`
- `64352`

No live mail send, queue mutation, cursor mutation, env change, deploy, Scheduler change, or WP write was performed in this task.

## 1. DECISION

| field | value |
|---|---|
| ticket | `BUG-004+291 wp_publish_vs_notify_gap renotify 5` |
| recommendation | `GO` |
| classification | `USER_DECISION_REQUIRED` |
| decision_owner | `user` |
| reason | exact 5-post one-shot re-notify is technically narrower than cursor replay, keeps rollback impact to mail only, and bounds delta to `+5` once; user approval is still required because this is a real outbound mail increase |

## 2. EXECUTION

| field | value |
|---|---|
| owner | `Claude / authenticated executor after user OK` |
| scope | exact 5-post read-only precheck, one-shot re-notify mechanism selection, mail delta / rollback / stop-condition normalization |
| non_scope | `src/**`, `tests/**`, `config/**`, live mail send in this task, cursor/history mutation in this task, Scheduler/env/deploy/WP write, any post outside `64194/64196/64198/64343/64352` |
| live_mutation | `mail` |

### mechanism comparison

| mechanism | what changes | 5-post precision | dedupe / cursor interaction | pros | cons | verdict |
|---|---|---|---|---|---|---|
| cursor rollback | live `publish_notice_cursor.txt` and likely follow-up replay run | weak | `scan()` writes direct-publish `post_id` into `publish_notice_history.json` with a `24h` recent-duplicate window (`src/publish_notice_scanner.py:33,1369-1375,2737-2749,2954-2958`), so cursor rollback alone can still skip these posts; if current filter remains live, resend can still suppress | reuses normal scan path | not 5-only, touches live cursor, may require history mutation or >24h wait, still depends on publish-only filter behavior | `reject` |
| one-shot re-enqueue | one mail send per exact `post_id`; optional queue/ledger append in the execution environment only | strong | no dependency on scanner cursor; sender duplicate guard is `30 minutes` (`src/publish_notice_email_sender.py:25,1629-1652,2084-2090`); for these 5 rows, current evidence shows suppression, not prior `sent`, so one-shot delta remains bounded | exact 5 ids, no cursor/history rewind, can be executed once and stopped cleanly | if executed before Lane A bypass is live, current sender path can still suppress unless the executor uses an explicit override wrapper; existing stdin path can target exact notifications but subject/body behavior must be chosen deliberately | `recommended` |
| Lane A flag ON via natural resend | behavior-changing env / future direct-publish bypass | none as a standalone replay | fixes future direct-publish mail suppression but does not, by itself, replay already-past rows whose scan/history window has moved on | solves the forward path | not a replay mechanism by itself; still needs either cursor/history mutation or exact targeted replay for these 5 historical misses | `not sufficient alone` |

### recommended execution shape

1. Keep this Pack as a decision artifact only.
2. If user says `OK`, use a one-shot re-enqueue for exactly `64194/64196/64198/64343/64352`.
3. Do not use cursor rollback.
4. Prefer executing the one-shot only after Lane A direct-publish bypass is live, or use an explicit one-shot override path that is proven not to re-hit `PUBLISH_ONLY_FILTER`.

## 3. EVIDENCE

### commit

| hash | summary |
|---|---|
| `05c63cf` | baseline local HEAD used for this read-only code trace; no runtime behavior change was made in this task |

### image

| field | value |
|---|---|
| current | `none` |
| target | `none` |

### env

| field | value |
|---|---|
| add_or_change | `none` |
| remove_or_revert | `none` |

### execution

| item | observed result |
|---|---|
| `curl -fsSL https://yoshilover.com/wp-json/wp/v2/posts/<id>?_fields=id,status,date,date_gmt,link,title` for all 5 ids | all 5 attempts failed in this environment with `curl: (6) Could not resolve host: yoshilover.com` at `2026-05-03 16:05:38 JST`; therefore current WP REST fields are `unverified` |
| scanner / sender code trace | confirmed that direct publish rows are added to scanner history before send and that the publish-only filter suppresses per-post mail by final subject prefix, not raw `notice_kind` |
| existing stdin one-shot path | `src/tools/run_publish_notice_email_dry_run.py:308-392` confirms the existing tool can send an explicit `notifications` list without using `scan()` |

### log

| item | observed signal |
|---|---|
| confirmed suppressed published posts | `docs/handoff/codex_responses/2026-05-03_BUG004_291_notify_track.md` Phase 3 confirms all 5 posts were already published and then suppressed in publish-notice |
| publish-only filter behavior | `src/publish_notice_email_sender.py:1664-1690,2139-2169` and the audit doc confirm suppression reason `PUBLISH_ONLY_FILTER` after final subject classification |
| history / cursor behavior | `src/publish_notice_scanner.py:2700-2759,2954-2958` confirms `scan()` writes cursor/history even before sender suppression is known |

### WP REST current-state snapshot (`best effort only`)

Interpretation note:

- current code treats `post.link` as `canonical_url` (`src/publish_notice_scanner.py:1377-1383`)
- this Pack therefore treats `canonical` as `link` unless a future authenticated WP REST read proves otherwise

| post_id | current status | title.rendered | link | link_published_at (`date`) | canonical | note |
|---|---|---|---|---|---|---|
| `64194` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | WP REST host resolution failed in this audit environment |
| `64196` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | WP REST host resolution failed in this audit environment |
| `64198` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | WP REST host resolution failed in this audit environment |
| `64343` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | WP REST host resolution failed in this audit environment |
| `64352` | `unverified` | `unverified` | `unverified` | `unverified` | `unverified` | WP REST host resolution failed in this audit environment |

### classifier / subject evidence for the 5 target posts

| post_id | guarded-publish evidence | publish-notice result | subject prefix | classifier result | outcome |
|---|---|---|---|---|---|
| `64194` | `2026-05-03T05:35:44Z` (`docs/handoff/codex_responses/2026-05-03_BUG004_291_notify_track.md`) | `2026-05-03T05:41:11Z` | `【要確認】` | `yellow -> review_hold -> suppressed` | published post reached notify, then suppressed |
| `64196` | `2026-05-03T05:35:44Z` | `2026-05-03T05:41:11Z` | `【要review】` | `review -> review_hold -> suppressed` | published post reached notify, then suppressed |
| `64198` | `2026-05-03T05:40:44Z` | `2026-05-03T05:41:11Z` | `【要確認(古い候補)】` | `backlog_only old_candidate -> review_hold -> suppressed` | published post reached notify, then suppressed |
| `64343` | `2026-05-03T05:05:42Z` | `2026-05-03T05:10:58Z` | `【要確認】` | `yellow -> review_hold -> suppressed` | published post reached notify, then suppressed |
| `64352` | `2026-05-03T05:15:40Z` | `2026-05-03T05:21:09Z` | `【要review】` | `review -> review_hold -> suppressed` | published post reached notify, then suppressed |

## 4. USER_GO_REQUIRED

| field | value |
|---|---|
| is | `true` |
| category | `mail_increase` |

## 5. USER_GO_REASON

| field | value |
|---|---|
| summary | `MAIL_VOLUME_INCREASE_ONE_SHOT`: this action intentionally adds `+5` one-time per-post mails for already-published posts that were missed on `2026-05-03` |
| max_risk | mailbox receives 5 additional per-post notifications; if the executor chooses a replay method broader than the recommended one-shot path, blast radius expands beyond the intended 5 |
| rollback_ready | `yes` |

## 6. NEXT_REVIEW_AT

| field | value |
|---|---|
| trigger | review immediately before any live resend attempt, after the executor has network access for WP REST GET and after the exact replay path is fixed |

## 7. EXPIRY

| field | value |
|---|---|
| invalidates_when | any of the 5 posts is already re-notified by another path, publish-notice filter behavior changes, cursor/history is mutated, Lane A replay behavior changes, or fresh WP REST evidence supersedes the `unverified` snapshot |

## 8. ROLLBACK_TARGETS

### env

| field | value |
|---|---|
| apply | `none` |
| rollback | `none` |
| owner | `none` |

### image

| field | value |
|---|---|
| current_live_before_apply | `none` |
| target_after_apply | `none` |
| rollback | `none` |
| owner | `none` |

### github

| field | value |
|---|---|
| release_composition_commits | `none` |
| revert | `none` |
| owner | `none` |

Rollback summary for the recommended one-shot mail path:

- before execution: `no-op`
- after execution: technical rollback is `no-op`; recipient mailbox history remains by design

## 9. POST_DEPLOY_VERIFY

| field | value |
|---|---|
| required | `true` |
| observed_status | `NOT_RUN` |

### commands

```bash
# pre-send read-only check from an executor that can resolve yoshilover.com
curl -fsSL 'https://yoshilover.com/wp-json/wp/v2/posts/64194?_fields=id,status,date,link,title'
curl -fsSL 'https://yoshilover.com/wp-json/wp/v2/posts/64196?_fields=id,status,date,link,title'
curl -fsSL 'https://yoshilover.com/wp-json/wp/v2/posts/64198?_fields=id,status,date,link,title'
curl -fsSL 'https://yoshilover.com/wp-json/wp/v2/posts/64343?_fields=id,status,date,link,title'
curl -fsSL 'https://yoshilover.com/wp-json/wp/v2/posts/64352?_fields=id,status,date,link,title'

# one-shot exact replay path; concrete payload remains executor-owned
python3 src/tools/run_publish_notice_email_dry_run.py --stdin --send --send-enabled
```

### success_signals

- all 5 pre-send WP REST rows resolve and still show `status=publish`
- the replay payload contains only `64194`, `64196`, `64198`, `64343`, `64352`
- replay output shows exactly 5 `kind=per_post` results
- no replay result shows `PUBLISH_ONLY_FILTER`
- no replay result shows `BACKLOG_SUMMARY_ONLY`
- no replay result shows `DUPLICATE_WITHIN_30MIN`
- no 6th post id is sent

## 10. STOP_CONDITION

- any pre-send WP REST GET returns a non-`publish` status for one of the 5 ids
- any pre-send WP REST GET cannot be performed by the authenticated executor and the executor is unwilling to send on `unverified` metadata
- the chosen replay method requires cursor rollback or history deletion
- dry-run or live replay includes any post id outside `64194/64196/64198/64343/64352`
- dry-run or live replay still returns `PUBLISH_ONLY_FILTER`
- expected mail count exceeds `5`

## 11. REGRESSION

### required_checks

- exact target set remains `64194/64196/64198/64343/64352` only
- no `src/**`, `tests/**`, `config/**` change is introduced for this resend decision
- no live cursor, history, Scheduler, env, or deploy mutation is used to achieve the resend
- one-shot replay uses no scan-wide fetch path
- mail count stays bounded to `+5 once`

### forbidden_expansion

- cursor rollback
- `publish_notice_history.json` wipe or manual delete
- replaying any additional post ids beyond the 5 confirmed misses
- dedupe-window changes
- cap changes
- env flag changes as a substitute for a 5-only replay

## 12. MAIL_GEMINI_DELTA

| field | value |
|---|---|
| mail_delta | `increase +5 once` for the recommended path; note that current repo has two separate duplicate windows: scanner history `24h` (`src/publish_notice_scanner.py:33`) and sender duplicate mail guard `30 minutes` (`src/publish_notice_email_sender.py:25`) |
| gemini_delta | `unchanged` |
| invariant | no new prompt path, no deploy/env/scheduler/source mutation, no WP write, and no expansion beyond the exact 5 post ids |

## 13. OPEN_QUESTIONS

- Should the executor wait for Lane A direct-publish bypass to be live before replaying the 5 posts, or should the executor use the existing one-shot stdin sender path with an explicit override that avoids `PUBLISH_ONLY_FILTER` for historical misses?
- Can the authenticated executor capture and archive the 5 WP REST responses at execution time so this Pack can be refreshed from `unverified` to verified before any real mail is sent?

結論:
理由:
最大リスク:
rollback:
userが返すべき1行: OK / HOLD / REJECT
