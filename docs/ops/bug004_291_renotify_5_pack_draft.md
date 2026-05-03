# BUG-004+291 renotify 5 Acceptance Pack draft

Last updated: 2026-05-03 JST  
Mode: reduced-scope execution prep + blocked local executor record  
Canonical template: `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`  
Status: `HOLD`  
USER_DECISION_REQUIRED: `false`  
Reason: `VERIFY_BLOCKED_EXECUTOR_NETWORK`

This Pack draft covers only the one-shot re-notify question for the 5 already-published posts confirmed in `docs/handoff/codex_responses/2026-05-03_BUG004_291_notify_track.md`:

- `64194`
- `64196`
- `64198`
- `64343`
- `64352`

User `OK` for the original 5-post mail increase had already been received before this update. This update records the narrower 2-post subset decision and the local executor stop.

No live mail send, queue/history rollback, deploy, Scheduler change, or WP write was performed in this task.

## 1. DECISION

| field | value |
|---|---|
| ticket | `BUG-004+291 wp_publish_vs_notify_gap renotify 5` |
| recommendation | `HOLD local Codex executor / hand off to Claude or another network-capable executor` |
| classification | `HOLD` |
| decision_owner | `Claude / authenticated executor` |
| reason | the user `OK` for `mail+5` already covers the narrower `mail+2` subset, but the Codex sandbox cannot resolve or log in to Gmail SMTP, so live send must move to a network-capable executor |

## 2. EXECUTION

| field | value |
|---|---|
| owner | `Codex local preflight + Claude / authenticated executor for actual live send` |
| scope | exact reduced subset `64194` + `64343`, one-shot replay path, mail delta / rollback / stop-condition normalization, local SMTP preflight |
| non_scope | `src/**`, `tests/**`, `config/**`, cursor/history rollback, Scheduler/env/deploy/WP write, and any post outside `64194/64343` for the live subset (`64196/64198/64352` are explicitly excluded) |
| live_mutation | `mail` |

### mechanism comparison

| mechanism | what changes | 5-post precision | dedupe / cursor interaction | pros | cons | verdict |
|---|---|---|---|---|---|---|
| cursor rollback | live `publish_notice_cursor.txt` and likely follow-up replay run | weak | `scan()` writes direct-publish `post_id` into `publish_notice_history.json` with a `24h` recent-duplicate window (`src/publish_notice_scanner.py:33,1369-1375,2737-2749,2954-2958`), so cursor rollback alone can still skip these posts; if current filter remains live, resend can still suppress | reuses normal scan path | not 5-only, touches live cursor, may require history mutation or >24h wait, still depends on publish-only filter behavior | `reject` |
| one-shot re-enqueue | one mail send per exact `post_id`; optional queue/ledger append in the execution environment only | strong | no dependency on scanner cursor; sender duplicate guard is `30 minutes` (`src/publish_notice_email_sender.py:25,1629-1652,2084-2090`); for these 5 rows, current evidence shows suppression, not prior `sent`, so one-shot delta remains bounded | exact 5 ids, no cursor/history rewind, can be executed once and stopped cleanly | if executed before Lane A bypass is live, current sender path can still suppress unless the executor uses an explicit override wrapper; existing stdin path can target exact notifications but subject/body behavior must be chosen deliberately | `recommended` |
| Lane A flag ON via natural resend | behavior-changing env / future direct-publish bypass | none as a standalone replay | fixes future direct-publish mail suppression but does not, by itself, replay already-past rows whose scan/history window has moved on | solves the forward path | not a replay mechanism by itself; still needs either cursor/history mutation or exact targeted replay for these 5 historical misses | `not sufficient alone` |

### recommended execution shape

1. Use the reduced live subset only: `64194` and `64343`.
2. Stop and exclude `64196`, `64198`, and `64352` because the latest Claude-side WP REST verify reported them as `401` / non-publish for this resend scope.
3. Do not use cursor rollback.
4. Use a one-shot stdin replay with `subject_override` `【公開済】... | YOSHILOVER`.
5. Run the actual live send only from an executor that can resolve and log in to Gmail SMTP.

## Execution record (2026-05-03 PM)

- executed_at_jst: `2026-05-03 16:26:53 JST`
- WSL WP REST verify input from Claude:
  - `64194` = `publish` (`date=2026-05-03T14:35:43`, title `「『こどもの日』グッズを発売🧒👧 読売巨人軍は…」`)
  - `64343` = `publish` (`date=2026-05-03T14:05:41`, title `「立岡『立岡コーチとともに…』 関連発言」`)
  - `64196` / `64198` / `64352` = `401` / excluded from resend scope
- reduced execution decision:
  - live target set = `64194`, `64343`
  - stopped by scope-reduce = `64196`, `64198`, `64352`
- local SMTP preflight from Codex sandbox:
  - `MAIL_BRIDGE_SMTP_USERNAME=fwns6760@gmail.com` was recoverable from repo docs/runbooks as the historical sender override
  - SMTP login preflight returned `SMTP_LOGIN_ERROR gaierror [Errno -3] Temporary failure in name resolution`
  - result: STOP before dry-run/live replay because the local executor cannot reach the mail bridge
- dry-run summary:
  - `not run`
  - reason: SMTP/DNS stop was detected before replay execution; this Pack does not fabricate live payload fields beyond the verified reduced subset
- live send summary:
  - `not run`
  - result: `0 sent`, `0 partial`, `0 rollback`
- mail delta actual:
  - `+0` in this task
  - approved target remains `+2 once` when replay is executed by a network-capable executor
- rollback executed:
  - `no`

## 3. EVIDENCE

### commit

| hash | summary |
|---|---|
| `62c9b6a` | baseline local HEAD used for reduced-scope preflight; no runtime behavior change was made before the SMTP stop |

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
| SMTP login preflight with repo-local app password + documented sender override | `SMTP_LOGIN_ERROR gaierror [Errno -3] Temporary failure in name resolution` at `2026-05-03 16:26:53 JST`; Codex sandbox cannot reach Gmail SMTP, so live send was not attempted |

### log

| item | observed signal |
|---|---|
| confirmed suppressed published posts | `docs/handoff/codex_responses/2026-05-03_BUG004_291_notify_track.md` Phase 3 confirms all 5 posts were already published and then suppressed in publish-notice |
| publish-only filter behavior | `src/publish_notice_email_sender.py:1664-1690,2139-2169` and the audit doc confirm suppression reason `PUBLISH_ONLY_FILTER` after final subject classification |
| history / cursor behavior | `src/publish_notice_scanner.py:2700-2759,2954-2958` confirms `scan()` writes cursor/history even before sender suppression is known |

### WP REST current-state snapshot (`Claude WSL verify + local best effort`)

Interpretation note:

- current code treats `post.link` as `canonical_url` (`src/publish_notice_scanner.py:1377-1383`)
- this Pack therefore treats `canonical` as `link` unless a future authenticated WP REST read proves otherwise

| post_id | current status | title.rendered | link | link_published_at (`date`) | canonical | note |
|---|---|---|---|---|---|---|
| `64194` | `publish` | `『こどもの日』グッズを発売🧒👧 読売巨人軍は…` | `unknown in local sandbox` | `2026-05-03T14:35:43` | `unknown in local sandbox` | Claude WSL verify says resend target |
| `64196` | `401 / excluded` | `unknown in local sandbox` | `unknown in local sandbox` | `unknown in local sandbox` | `unknown in local sandbox` | excluded from reduced subset; separate audit |
| `64198` | `401 / excluded` | `unknown in local sandbox` | `unknown in local sandbox` | `unknown in local sandbox` | `unknown in local sandbox` | excluded from reduced subset; separate audit |
| `64343` | `publish` | `立岡『立岡コーチとともに…』 関連発言` | `unknown in local sandbox` | `2026-05-03T14:05:41` | `unknown in local sandbox` | Claude WSL verify says resend target |
| `64352` | `401 / excluded` | `unknown in local sandbox` | `unknown in local sandbox` | `unknown in local sandbox` | `unknown in local sandbox` | excluded from reduced subset; separate audit |

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
| is | `false` |
| category | `already satisfied by wider 5-post user OK; current pack is executor-handoff only` |

## 5. USER_GO_REASON

| field | value |
|---|---|
| summary | `MAIL_VOLUME_INCREASE_ONE_SHOT` user approval was already received for `+5 once`; the current reduced scope is `+2 once` (`64194` + `64343`) |
| max_risk | if the next executor does not preserve the reduced subset, a broader resend than `+2` can occur; in this Codex session no mail was sent because SMTP was unreachable |
| rollback_ready | `yes` |

## 6. NEXT_REVIEW_AT

| field | value |
|---|---|
| trigger | rerun immediately from Claude WSL or another network-capable executor that can resolve `smtp.gmail.com` and optionally capture the exact WP REST `link` fields for `64194` / `64343` before send |

## 7. EXPIRY

| field | value |
|---|---|
| invalidates_when | either `64194` or `64343` is already re-notified by another path, their publish status changes, cursor/history is mutated, publish-notice filter behavior changes, or a later verify changes the reduced subset |

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
| observed_status | `BLOCKED_LOCAL_EXECUTOR_SMTP_DNS` |

### commands

```bash
# pre-send read-only check from an executor that can resolve yoshilover.com
curl -fsSL 'https://yoshilover.com/wp-json/wp/v2/posts/64194?_fields=id,status,date,link,title'
curl -fsSL 'https://yoshilover.com/wp-json/wp/v2/posts/64343?_fields=id,status,date,link,title'

# optional SMTP preflight from the next executor shell
python3 - <<'PY'
import smtplib
from dotenv import load_dotenv
load_dotenv('.env')
from src.mail_delivery_bridge import load_credentials_from_env
creds = load_credentials_from_env()
with smtplib.SMTP_SSL(creds.smtp_host, creds.smtp_port, timeout=10) as smtp:
    smtp.login('fwns6760@gmail.com', creds.app_password)
    print(smtp.noop())
PY

# reduced one-shot dry-run
MAIL_BRIDGE_SMTP_USERNAME=fwns6760@gmail.com ENABLE_PUBLISH_ONLY_MAIL_FILTER=0 python3 src/tools/run_publish_notice_email_dry_run.py --stdin

# reduced one-shot live send
MAIL_BRIDGE_SMTP_USERNAME=fwns6760@gmail.com ENABLE_PUBLISH_ONLY_MAIL_FILTER=0 python3 src/tools/run_publish_notice_email_dry_run.py --stdin --send --send-enabled
```

### success_signals

- both pre-send WP REST rows (`64194`, `64343`) resolve and still show `status=publish`
- the replay payload contains only `64194` and `64343`
- replay output shows exactly 2 `kind=per_post` results
- no replay result shows `PUBLISH_ONLY_FILTER`
- no replay result shows `BACKLOG_SUMMARY_ONLY`
- no replay result shows `DUPLICATE_WITHIN_30MIN`
- no excluded post id (`64196`, `64198`, `64352`) is sent

## 10. STOP_CONDITION

- any pre-send WP REST GET returns a non-`publish` status for either reduced live target (`64194` or `64343`)
- any pre-send WP REST GET cannot be performed by the authenticated executor and the executor is unwilling to send on `unverified` metadata
- SMTP preflight or live bridge access returns DNS / socket / auth failure
- the chosen replay method requires cursor rollback or history deletion
- dry-run or live replay includes any post id outside `64194/64196/64198/64343/64352`
- dry-run or live replay still returns `PUBLISH_ONLY_FILTER`
- expected mail count exceeds `2` for the reduced subset

## 11. REGRESSION

### required_checks

- exact reduced live target set remains `64194` and `64343` only
- no `src/**`, `tests/**`, `config/**` change is introduced for this resend decision
- no live cursor, history, Scheduler, env, or deploy mutation is used to achieve the resend
- one-shot replay uses no scan-wide fetch path
- mail count stays bounded to `+2 once`

### forbidden_expansion

- cursor rollback
- `publish_notice_history.json` wipe or manual delete
- replaying `64196`, `64198`, `64352`, or any post id outside the reduced subset
- dedupe-window changes
- cap changes
- env flag changes as a substitute for a 5-only replay

## 12. MAIL_GEMINI_DELTA

| field | value |
|---|---|
| mail_delta | `+0` in this Codex task because send never started; approved target remains `increase +2 once` for the reduced subset when the next executor reruns it. The repo still has two duplicate windows: scanner history `24h` (`src/publish_notice_scanner.py:33`) and sender duplicate mail guard `30 minutes` (`src/publish_notice_email_sender.py:25`) |
| gemini_delta | `unchanged` |
| invariant | no new prompt path, no deploy/env/scheduler/source mutation, no WP write, and no expansion beyond the reduced live subset `64194` + `64343` |

## 13. OPEN_QUESTIONS

- Can Claude WSL execute the reduced 2-post replay directly, using the same documented SMTP username override that passed in historical runbooks but failed here only because the Codex sandbox had no DNS?
- Can the next executor capture the exact WP REST `link` values for `64194` and `64343` so the stdin payload avoids any URL inference before the real send?

結論: HOLD(local Codex executor) / rerun from Claude or another network-capable executor
理由: user OK is already satisfied for the wider 5-post approval, but this sandbox cannot reach Gmail SMTP and therefore cannot complete the approved `+2` reduced resend safely.
最大リスク: next executor broadens the payload beyond `64194` and `64343`, or sends without first confirming the exact `link` fields.
rollback: no-op in this task because no mail was sent
userが返すべき1行: なし(次は Claude 実行判断)
