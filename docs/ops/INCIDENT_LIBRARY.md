# YOSHILOVER INCIDENT_LIBRARY

Last updated: 2026-05-01 17:55 JST(298-v4 deploy 完了 OBSERVED_OK 反映)

This file records reusable incident rules. It is not a session diary.

## Incident: P1 Mail Storm From Old Candidates

### Symptoms

- publish-notice sends old candidate mail repeatedly.
- sent count approaches or exceeds MAIL_BUDGET.
- old candidates recur after dedupe expiry.

### Current Standing

- Current storm is contained.
- 298-Phase3 is rolled back after regression.
- Phase3 is not DONE.
- Phase3 re-ON is forbidden without a new Acceptance Pack.

### Production Reflection Rule

- Flag OFF deploy, live-inert deploy, and behavior-preserving image replacement are not automatically user-GO work.
- Claude may execute them as `CLAUDE_AUTO_GO` only when tests are green, rollback target is confirmed, Gemini/mail/source/Scheduler/SEO/publish criteria/candidate risks do not increase, and stop condition is written.
- Phase3 flag ON, old-candidate re-ON, mail volume increase, or UNKNOWN mail impact remains `USER_DECISION_REQUIRED` or `HOLD`.

### Do

- Preserve normal review mail.
- Preserve 289 post_gen_validate notification mail.
- Preserve error mail.
- Estimate old candidate pool cardinality.
- Estimate first-send mail count.
- Define max mails/hour and max mails/day.
- Define stop condition.
- Keep rollback one-command where possible.

### Do Not

- Do not stop all mail.
- Do not pause Scheduler as a normal fallback.
- Do not reapply `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`.
- Do not wait for pool exhaustion.
- Do not GO with UNKNOWN mail volume impact.
- Do not call Phase3 DONE while the flag is OFF after rollback.

### Required Tests

- old candidate pool count test
- first-send estimate test
- max/hour cap test
- max/day cap test
- normal review mail still sent
- 289 mail still sent
- error mail still sent
- rollback command verified

## Incident: Silent Skip

### Definition

A candidate is unacceptable if it disappears into logs, WP draft state, or internal ledgers without user-visible publish/review/hold/skip notification.

### Accepted Terminal States

- publish
- review notification
- hold notification
- skip notification

### Do

- Add durable reason.
- Add user-visible route.
- Test the route.
- Preserve existing publish/review/hold mail.
- Keep Gemini calls unchanged unless user GO approves an increase.

### Do Not

- Do not treat Cloud Logging alone as acceptance.
- Do not create a skip gate without a visible reason path.
- Do not enable 282 preflight before visible skip readiness.

## Incident: Post-Gen Validate Skip

### Standing Rule

289 is the correct lane for post_gen_validate skip visibility.

### Required Evidence

- skip ledger written
- publish-notice scanner reads it
- mail subject clearly says `post_gen_validate`
- duplicate suppression is bounded
- max_per_run behavior is known
- skipped payload counts are visible

### Known Gap To Watch

`body_contract_validate` failures must not remain log-only. If they are outside 289, add them as a subtask rather than creating a new unrelated ticket.

## Incident: Cost Gate Candidate Loss

### Standing Rule

Cost gates must not make candidates disappear.

### Order

1. candidate visibility
2. silent skip 0
3. cost estimate
4. preflight skip visible
5. flag ON decision

### Do Not

- Do not enable `ENABLE_GEMINI_PREFLIGHT` before 293/visibility readiness.
- Do not add sources before candidate visibility and mail impact are understood.

## Incident: Flaky / Transient Tests

### Standing Rule

Do not call a transient test failure P0 without repeatable evidence.

### Required Evidence

- failing command
- passing retry or repeated failure
- environment difference
- affected ticket
- whether production behavior is affected

### State

Use OBSERVE until repeatability is proven.

## Incident: Raw Codex Output Leakage

### Problem

Raw Codex answers can confuse the user and mix speculation with action.

### Rule

Claude must compress Codex output before user-facing reporting.

### User-Facing Output

Use Decision Batch. Include conclusion, evidence, risk, next action, and the one line the user should return if a decision is needed.

## Incident: P1 Mail Storm 2026-05-01 Second-Wave Risk

### Summary

- `2026-05-01` の P1 mail storm は `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` 単独事故ではなく、old-candidate sink-side first emit が `99+` backlog pool に再露出したことで `MAIL_BUDGET` を破った。

### Timeline

- `09:00 JST`: first wave started after the `168h` review-window hotfix.
- `09:55 JST`: first wave stopped naturally; the storm did not require Scheduler stop or global mail stop.
- `13:00 JST`: `298-Phase3` deploy continuation started.
- `13:24 JST`: flag-ON observe looked green, but only the first protected batches had been sampled.
- `13:35 JST`: second storm was detected after re-ON; `cap=10` held per run but not per hour.
- `13:55 JST`: rollback removed `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` and restored pre-ON behavior.
- `14:15 JST`: post-rollback observe showed `errors=0`, `silent skip=0`, old-candidate emit `0`, and normal paths alive.
- `17:00 JST`: production health observe remains required before any new GO framing.

### Root Causes

- `guarded-publish */5` trigger reevaluated `backlog_only` rows every run, so old candidates kept becoming eligible for publish-notice scanning.
- `24h dedup` expiry reopened old-candidate first emits the next day instead of permanently draining the historical pool.
- `cap=10` limited only per-run sends and did not make the overall system budget-safe.
- pool cardinality itself was too large; a `99+ unique post_id` first emit is already a P1 budget breach even if every single run looks capped.

### Judgment Errors

- treating the `env=168` hotfix as the main fix path was counterproductive; it changed the review window but did not remove the sink-side replay behavior.
- turning `Phase3` flag ON without seeding or neutralizing the existing pool reopened the unregistered backlog.
- Codex preflight stop chaining compressed safe observe time and delayed the cleaner `target=HEAD` deploy path.

### Preserved Boundaries

- `Team Shiny From` remained unchanged.
- `289 post_gen_validate` notification remained alive.
- Scheduler cadence remained unchanged.
- X lane remained unchanged.
- `live_update` remained unchanged.
- Gemini call volume remained unchanged.

### Prevention Anchors

- treat scan-window expansion as a replay-risk change, not as a harmless mail-tuning change.
- never call `cap` alone safe; per-run limits do not replace hour/day budget modeling.
- require first-emit cardinality estimate before GO whenever historical pools can reopen.
- prioritize source-side fixes when sink-side caps still leave a budget-breaking first wave.
- use `target=HEAD` dynamic deploy preflight so doc-only commits do not create false deploy stops.

### Related Commit / Ticket

- tickets: `298-Phase3`, `299-QA`, `300-COST`, `289-OBSERVE`
- commits: `d44594a` (`298` once-only suppression), `7d0c9a5` (`298` deploy result), `a3871f2` (`298` incident evidence), `cdd0c3f` (`298` second-wave pack), `cf86e88` (`298` unknown-close evidence)

### 2026-05-01 19:30 JST → 20:00 JST 298-Phase3 v4 deploy 完了(Case F GCS pre-seed)

- `19:30 JST`: user GO「ならやる」受領。POLICY §3.2 USER_DECISION_REQUIRED + Claude 推奨 GO に対する 1 行返答。
- `19:35 JST`: Lane B round 15 (`bbnqyhph3`) fire、Case F GCS pre-seed `gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json` に 104 post_id pre-seed(5/1朝 storm 99 + 13:35 storm 50 + recent 6h additions の disjoint union)+ `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1` env apply。
- `19:35-19:40 JST`(UTC 08:35-08:40): 3 trigger 観測。post-deploy slice sent=9 (1+1+2 for trigger + 5 backlog-only)、errors=0、silent skip 0。
- live-detected post_id 64109(104 pool 外)→ first emit 1 度のみ + ledger 自動追記 → 106 件。
- 5/1朝 storm 99 cohort + 13:35 storm 50 cohort 全部 `OLD_CANDIDATE_PERMANENT_DEDUP` skip 確認。
- post-deploy 7-point verify pass(POLICY §3.5)、judgement: **OBSERVED_OK**。
- §14 P0/P1 自律 rollback monitor 24h 継続。

### 2026-05-02 09:00 JST Second-Wave Risk(MITIGATED pending Phase 6 verify)

- mitigation: Case F GCS pre-seed 106 件 ledger により permanent_dedup skip 想定。
- Phase 6 read-only verify(Claude 自律 EVIDENCE_ONLY)で確定:
  - rolling 1h sent: MAIL_BUDGET 30/h 内
  - cumulative since 5/1 09:00 JST: MAIL_BUDGET 100/d 内
  - silent skip: 0 継続
  - permanent_dedup skip count: 106+ 安定
  - real review / 289 / errors: 維持
  - 5/1朝 storm 99 cohort sent: **0**(第二波防止)
  - 13:35 storm 50 cohort sent: **0**
- 異常検出時 §14 自律 rollback(env remove 30 sec、本日 13:55 実績整合)。

### 2026-05-01 Reflection(永続記録、POLICY §16.3 整合)

5 reflection points → permanent rules:

1. **HOLD 作業停止 誤り**: HOLD は本番反映停止のみ。前段作業(Pack / UNKNOWN 潰し / test plan / rollback plan / READY 化)は CLAUDE_AUTO_GO 自律 → POLICY §16.2 / §3.3 永続化。
2. **user 技術判断 戻し過ぎ**: 技術 / デグレ / コスト / mail / rollback は Claude 判断。user は推奨 GO/HOLD/REJECT + 理由 + 最大リスク + rollback 可否 受領のみ → POLICY §15.1 / §15.2 永続化。
3. **Codex worker pool 管理弱**: 完了後 Claude 一次受け / lane idle 検出は Claude 責務 / idle なら次の低リスク subtask 投入 / 4 NO 規律 → POLICY §13 / §5 / §15.3 永続化。
4. **/tmp persistence 誤り**: prompt / job ID / receipt / lane status / HOLD 理由 は repo 内記録 → POLICY §13.1 / §13.4 永続化。
5. **GitHub revert と本番 rollback 混同**: 3 dimensions(env/flag, image/revision, source/git revert)を独立扱い、必要組み合わせ → POLICY §3.6 / §16.4 永続化。

old expression(削除対象):「本番反映は一律 user GO 必須」/ 「deploy 完了で DONE」/ 「GitHub revert だけで本番 rollback 済み」/ 「HOLD = 作業停止」/ 「close できないなら pause」/ 「user に技術判断を求める」/ 「Codex idle を user が発見する」(POLICY §16.5 整合)。

## Incident: Deploy Marked Done Without Verify

### Standing Rule

Deploy complete is not DONE. Image reflection, revision update, flag OFF deploy, or live-inert deploy is only a production reflection step.

### Required Evidence

- image / revision matches intended target
- env / flag matches intended target
- service / job starts normally
- runtime rollback target is written
- GitHub/source rollback path is written for failed tests/regression
- errors do not increase
- mail volume is within expectation
- Gemini delta is within expectation
- silent skip is 0
- Team Shiny From is preserved
- publish / review / hold / skip routes remain alive
- stop condition is not hit

### Failure State

Use HOLD or ROLLBACK_REQUIRED, not OBSERVED_OK, when post-deploy verify fails or evidence is missing. If the failure is tied to a committed change, restore production with runtime rollback when needed and restore GitHub source of truth with a non-destructive revert path.
