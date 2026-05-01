# YOSHILOVER NEXT_SESSION_RUNBOOK

Last updated: 2026-05-01 17:55 JST(298-v4 deploy 完了 + Phase 6 verify queued for 5/2 09:00 JST)

Use this when Claude/Codex resumes after restart.

## 1. First Read Order

1. `docs/ops/CURRENT_STATE.md`
2. `docs/ops/POLICY.md`
3. `docs/ops/OPS_BOARD.yaml`
4. `docs/ops/INCIDENT_LIBRARY.md`
5. `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`

Do not treat session logs, old handoffs, or raw Codex responses as current policy.

## 2. Startup Checks

Run read-only checks only:

- `git status --short`
- `git log --oneline -10`
- confirm dirty worktree paths before touching docs
- inspect `docs/ops/OPS_BOARD.yaml`
- confirm whether any Codex lane is currently running

Do not make unclassified production changes during startup. Apply `POLICY.md` section 3 before any production reflection: `CLAUDE_AUTO_GO` may proceed after evidence; `USER_DECISION_REQUIRED` needs a completed Pack; `HOLD` means Claude closes UNKNOWN first. Any production reflection then requires post-deploy verify before `OBSERVED_OK` or `DONE`.

## 3. Restore Current Board

Current major state:

- **298-Phase3 v4**: `OBSERVED_OK`、deploy 完了 (Lane B round 15 `bbnqyhph3`、本日 19:30 JST user GO「ならやる」受領)。Case F GCS pre-seed 106 件 + `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1` apply。post-deploy 7-point verify pass、storm 再発 0。**5/2 09:00 JST Phase 6 第二波防止 read-only verify 待ち**(Claude 自律 EVIDENCE_ONLY scope)。24h 安定 + Phase 6 pass で DONE 候補化。§14 P0/P1 自律 rollback monitor 24h 継続。
- **293-COST**: `READY_FOR_DEPLOY`、impl + test + push 完了(commits `6932b25`/`afdf140`/`7c2b0cc`/`10022c0`、pytest 2018/0、env knobs default OFF)。298-v4 24h 安定後、image rebuild + flag ON Pack 提示(USER_DECISION_REQUIRED)。
- **300-COST**: active for read-only source-side cost analysis; source-side behavior change must be classified before implementation/deploy.
- **299-QA**: observe flaky/transient, not P0 by default.
- **282-COST**: future user GO for flag ON after 293.
- **290-QA**: live-inert deploy may be `CLAUDE_AUTO_GO` after classification and post-deploy verify plan; weak title rescue enablement is user decision.
- **288-INGEST**: future user GO for source addition Pack.

Codex Lane state:

- Lane A: idle、last round 19 (`bvbjy9mog`、POLICY §3.5/§3.6/§15 commit `3d67d2a` + push 完了)。HOLD reason 4 条件全 YES。
- Lane B: idle、last round 15 (`bbnqyhph3`、298-v4 deploy 完了 OBSERVED_OK)。24h monitor 継続。
- 詳細は `docs/ops/WORKER_POOL.md` 参照(POLICY §13.6 引継ぎ)。

## 4. Codex Lane Handling

- Claude owns lane monitoring.
- Codex is a worker, not a manager.
- If a lane is idle, Claude must apply the four-condition gate from `POLICY.md` section 5.
- If a low-risk existing-ticket subtask remains, Claude dispatches it autonomously.
- Eligible low-risk subtasks are read-only, doc-only, evidence, test plan, rollback plan, Acceptance Pack, or ticket cleanup.
- Do not dispatch code/deploy/env/Scheduler/source/Gemini/mail-routing work until it is classified under `POLICY.md` section 3. `CLAUDE_AUTO_GO` work may proceed; `USER_DECISION_REQUIRED` needs a Pack; `HOLD` stays internal until UNKNOWN is closed.
- Do not ask the user whether to dispatch a READY-incomplete low-risk subtask.
- Do not keep a lane idle unless the HOLD reason is explicit.
- Do not fire meaningless work just to make Codex look busy.
- Do not create new tickets when the work can be absorbed as a subtask of an existing ticket.

Approved example: Lane B was initially idle, but Claude found remaining low-risk work in 298-Phase3 v4 Pack consistency, ACCEPTANCE_PACK extra-field alignment, and UNKNOWN-residual detection. Dispatching that Lane B task was correct because it stayed inside existing-ticket Pack/evidence work and did not touch deploy, env, Scheduler, source, Gemini, code, or mail conditions.

## 5. Decision Batch Only

When reporting to the user, use:

```text
結論: GO / HOLD / REJECT
P1 mail storm状態: contained / active / unknown
完了したチケット:
今進めているチケット:
次に流すチケット:
user判断が必要なもの: 0件 or Decision Batch
デグレ確認: test / mail / Gemini / silent skip / rollback
userが返すべき1行:
```

Do not paste raw Codex output.

## 6. 298-Phase3 v4 Post-Deploy Guard

本日 19:30 JST user GO「ならやる」受領、Case F GCS pre-seed + flag ON deploy 完了 OBSERVED_OK。

5/2 09:00 JST Phase 6 第二波防止 verify(Claude 自律 EVIDENCE_ONLY、read-only):

- rolling 1h sent: MAIL_BUDGET 30/h 内
- cumulative since 5/1 09:00 JST: MAIL_BUDGET 100/d 内
- silent skip: 0 継続
- permanent_dedup skip count: 106+ 安定(新規追加で +N)
- real review / 289 / errors: 維持
- 5/1朝 storm 99 cohort sent: **0**(第二波防止)
- 13:35 storm 50 cohort sent: **0**
- 直近 6h 追加 post: ledger 登録済 → sent=0 想定

検出時 §14 自律 rollback(env remove 30 sec、本日 13:55 実績整合):

- rolling 1h sent>30
- silent skip>0
- errors>0
- 289 mail 減
- Team Shiny From 変

24h 安定 + Phase 6 pass で 298-Phase3 v4 → DONE 候補化(POLICY §3.5、deploy 完了 ≠ DONE)。

## 7. Mail Storm Safety

Never use these as normal fixes:

- all-mail stop
- Scheduler pause
- `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`
- waiting for pool exhaustion

Keep normal review mail, 289 notification mail, and error mail active.

## 7a. Pre-Deploy Stop Mode(POLICY §17、298-Phase3 v4 以外 全 ticket 適用)

298-Phase3 v4 を除く全 ticket は **デプロイ直前まで** 進める。本番反映は user GO まで実行しない。

進めてよい:impl / test / pytest / regression 確認 / commit / push(auto-deploy なし運用)/ Acceptance Pack / rollback plan / post-deploy verify plan / cost / mail / Gemini / candidate disappearance 確認 / UNKNOWN 潰し。

進めてはいけない:Cloud Run deploy / env / flag / Scheduler / SEO / source 追加 / Gemini call 増加 / mail 通知条件 / 本番挙動変化操作。

ticket 別:

- 293-COST: デプロイ直前まで進める
- 282-COST: flag ON 直前まで進める
- 290-QA: デプロイ直前まで進める
- 300-COST: 実装直前または実装準備まで進める
- 288-INGEST: source 追加直前まで進める

user 向け報告では「READY_FOR_DEPLOY」より「デプロイ直前まで」を使う(POLICY §17.5)。

## 8. Low-Risk Work Queue

Proceed only inside current ticket scope:

1. 5/2 09:00 JST 298-v4 Phase 6 第二波防止 read-only verify(Claude 自律 EVIDENCE_ONLY、最優先)。
2. 24h 安定確認後、298-Phase3 v4 DONE 化判定。
3. 293-COST image rebuild + flag ON Pack 提示(USER_DECISION_REQUIRED)。298-v4 安定後 deferred。
4. 300-COST read-only cost analysis.
5. 299-QA baseline and recurrence observation.
6. Board/doc cleanup if ambiguity blocks the above.

Do not create new tickets unless an issue cannot fit into the above.

## 8a. Ticket Progress Loop(POLICY §16.2 整合、closeできないからpause = 禁止)

Codex lane が idle で次便 fire 判断する時、以下の順で:

1. DONE できるなら evidence 付き DONE
2. DONE できないなら READY 化
3. READY 化できないなら UNKNOWN 潰し
4. UNKNOWN があるなら read-only 調査
5. Pack 未完成なら Acceptance Pack 作成
6. rollback 不明なら rollback plan 作成
7. test 不明なら test plan 作成
8. Codex lane idle なら既存 ticket の低リスク subtask 投入

新 ticket 起票より既存 ticket subtask 化を優先(POLICY §10)。

## 9. Stop / Classify Conditions

Stop and classify the change under `POLICY.md` section 3 if any production effect is proposed.

Proceed autonomously only when it is `CLAUDE_AUTO_GO`:

- flag OFF deploy, live-inert deploy, or behavior-preserving image replacement
- tests green
- rollback target confirmed, including GitHub/source rollback path when tests or regression fail
- no Gemini/mail/source/Scheduler/SEO/publish criteria/candidate risk increase
- stop condition written
- post-deploy verify plan written

Prepare an Acceptance Pack when it is `USER_DECISION_REQUIRED`:

- flag ON
- behavior-changing env
- Gemini call increase
- mail volume increase
- source addition
- Scheduler/SEO change
- publish/review/hold/skip criteria change
- cleanup mutation
- rollback-impossible or external-impact-heavy change

Hold internally when any safety field is UNKNOWN. Do not ask the user to resolve UNKNOWN technical risk.

## 10. Post-Deploy Verify

Deploy complete is not DONE. After any production reflection, run only production-safe regression checks and record:

- image / revision
- env / flag
- service / job startup
- runtime rollback target
- GitHub/source rollback path for failed tests/regression
- error trend
- mail count
- Gemini delta
- silent skip count
- Team Shiny From
- publish / review / hold / skip route health
- stop condition result

Allowed production-safe checks: read-only, logs, health, mail count, env/revision checks, Scheduler/job observation, sample article/candidate state, flag OFF/no-send/dry-run-equivalent checks, and existing notification route checks.

Forbidden production tests: bulk mail, source addition, Gemini increase, publish criteria change, cleanup mutation, SEO/noindex/canonical/301, rollback-impossible operation, user-GO-less flag ON, or experiments while mail impact is UNKNOWN.

If verify fails, classify as `HOLD` or `ROLLBACK_REQUIRED`; do not mark `OBSERVED_OK`. If the failure is tied to a committed change, include GitHub/source rollback by non-destructive `git revert` in addition to any runtime rollback.

## 11. Successful Session Close

Before closing a session:

- update `CURRENT_STATE.md`
- update `OPS_BOARD.yaml`
- update `WORKER_POOL.md`(Lane A/B state、POLICY §13.6 引継ぎ)
- ensure ACTIVE count is at most 2
- record unresolved user decisions as Decision Batch items only
- 298-Phase3 v4 は Phase 6 verify pass + 24h 安定後にのみ DONE 化、deploy 完了だけでは DONE にしない(POLICY §3.5 整合)

## 12. 3 dimension Rollback(POLICY §16.4 整合)

production 事故時、3 dimensions のうち該当を必要分組み合わせる:

- **env / flag rollback**: 30 sec、`gcloud run jobs/services update --remove-env-vars=<flag>`(flag ON 起因 / env 起因 異常)
- **image / revision rollback**: 2-3 min、Cloud Run service `update-traffic --to-revisions=<prev>=100` / job `update --image=<prev_sha>`(image 内 commit 起因異常)
- **source / git revert**: `git revert <bad_commit>` + push origin master(repo 反映を残さず、再 build で bad change が再混入を防ぐ)

production 安定優先(env / image)→ source 整合(git revert)。GitHub 戻すだけで本番 rollback 済み扱いは禁止。

## 13. Pre-Deploy Gate(POLICY §16.1 整合)

production 反映前に 11 項目確認:

target commit/HEAD一致 / worktree clean / tests green / regression なし / rollback target / env変更有無 / Gemini 増加有無 / mail volume / candidate disappearance / stop condition / Acceptance Pack(USER_DECISION_REQUIRED 時)

UNKNOWN は user に投げず HOLD。

## 14. 2026-05-01 Audit Guards(POLICY §19 整合、deploy 便 step 0)

明日以降 deploy 便 fire 時、step 0 で以下を全部実行:

1. **§19.2 release composition verify**: `git log --oneline <prev_image_commit>..<new_image_commit>` で HOLD ticket 混入 0 確認、混入時 build 前停止
2. **§19.3 dirty worktree snapshot**: `git status --short` で whitelist (codex_requests 0424/0425、run_logs、build/data/logs/backups/.codex)以外の untracked / modified が 1 件でもあれば停止
3. **§19.1 silent skip grep**: `grep -r "no_op_skip\|llm_skip\|content_hash_dedupe\|PREFLIGHT_SKIP_MISSING_\|REVIEW_POST_DETAIL_ERROR" src/` で出力 0 確認
4. **§19.4 3-dim rollback anchor**: Pack 内 placeholder `<prev_SHA>` 残存 0、env / image / source 全 dim 埋まり確認
5. **§19.5 mail path LLM-free**: `grep -r "gemini\|openai\|generateContent" src/publish_notice_* src/mail_*` = 0 行確認

5 step 全 pass で build 開始 GO。1 つでも fail で HOLD。

## 14a. Sequential Single-Ticket Chain(POLICY §20、本日 user 明示)

各 ticket は **1 件ずつ順次** で 6 step 完走必須(同時並列 deploy 禁止):

1. deploy 前確認(§16.1 11 項目 + §19 5 step gate)
2. deploy 実行
3. 本番稼働確認(§20.2 6 項目: image / env / Cloud Run 正常 / Scheduler / error / rollback target)
4. 本番 safe デグレ試験(§20.3 9 項目: mail volume / sent burst / old_candidate storm / Gemini delta / silent skip / Team Shiny From / publish-review-hold-skip 導線 / 既存通知 / WP 主要導線)
5. 判定: OBSERVED_OK / HOLD / ROLLBACK_REQUIRED
6. 次 ticket へ進む(step 5 OBSERVED_OK 確定後のみ)

live-inert / flag OFF deploy でも post-deploy verify 軽め必須(15 項目を read-only)。flag ON / env / source / mail / Gemini 増加は強い verify。

異常 trigger 8 件 → 次へ進まず HOLD or ROLLBACK_REQUIRED → 3-dim rollback(code = git revert / image = Cloud Run rollback / flag = env rollback)→ post-rollback verify。

10-item report 形式(各 ticket 完了時): ticket / deployed / image / env / 稼働確認 / デグレ試験 / mail+Gemini+silent skip / rollback target / 判定 / 次 ticket。

chain 順序(POLICY §20.8): 298-v4 OBSERVED_OK → 290 Pack A live-inert → 293-COST → 282-COST → 290 Pack B → 300-COST → 288-INGEST Phase 1-4。

## 15. 5/2 09:00 JST Phase 6 verify(298-Phase3 v4)

Claude 自律 EVIDENCE_ONLY、read-only:

- rolling 1h sent: MAIL_BUDGET 30/h 内
- cumulative since 5/1 09:00 JST: MAIL_BUDGET 100/d 内
- silent skip: 0 継続
- permanent_dedup skip count: 106+ 安定
- real review / 289 / errors: 維持
- 5/1朝 storm 99 cohort sent: **0**(第二波防止)
- 13:35 storm 50 cohort sent: **0**

検出時 §14 自律 rollback。

24h 安定 + Phase 6 pass で 298-Phase3 v4 → DONE 化(POLICY §3.5、deploy 完了 ≠ DONE)。
