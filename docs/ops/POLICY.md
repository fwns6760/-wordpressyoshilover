# YOSHILOVER OPS POLICY

Last updated: 2026-05-01 JST

This is the permanent operations policy. If this file conflicts with old POLICY files, session logs, handoffs, memory, or Codex answers, this file wins.

## 1. Source Of Truth

Current operational truth is, in order:

1. `docs/ops/POLICY.md`
2. `docs/ops/CURRENT_STATE.md`
3. `docs/ops/OPS_BOARD.yaml`
4. `docs/ops/NEXT_SESSION_RUNBOOK.md`
5. `docs/ops/INCIDENT_LIBRARY.md`
6. `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`

`docs/handoff/session_logs`, `docs/handoff/codex_responses`, old handoffs, old OPS_BOARD text, and old POLICY text are history. They are not current instructions.

## 2. Roles

- User: decision owner for high-risk choices only.
- Claude: field lead, dispatcher, accept/reject reviewer, deployment coordinator, and user-facing reporter.
- Codex: field developer / worker.

Rules:

- User is not an execution owner.
- Claude must not forward raw Codex output to the user.
- Claude must compress Codex output into evidence, risk, next action, and Decision Batch.
- User should not be asked fragmented questions.
- User should not discover idle Codex lanes.
- Claude owns Codex lane monitoring and next-subtask dispatch.

## 3. Production Change Classification

Production change is not automatically blocked just because it touches production. Only risky production change is escalated to the user.

### 3.1 CLAUDE_AUTO_GO

Claude may execute production reflection without user GO when all conditions are true:

- flag OFF deploy
- live-inert deploy
- behavior-preserving image replacement
- tests are green
- rollback target is confirmed, including GitHub/source rollback path when tests or regression fail
- Gemini call increase: none
- mail volume increase: none
- source addition: none
- Scheduler change: none
- SEO/noindex/canonical/301 change: none
- publish/review/hold/skip criteria change: none
- cleanup mutation: none
- candidate disappearance risk: none, or proven unchanged from existing behavior
- stop condition is written
- post-deploy verify plan is written

Claude reports the result afterward in a Decision Batch only after post-deploy verify and production-safe regression evidence are collected.

### 3.2 USER_DECISION_REQUIRED

User decision is required for:

- flag ON
- env change that changes behavior
- Scheduler enable/disable/pause/resume/frequency change
- SEO/noindex/canonical/301/sitemap/robots change
- source addition
- Gemini call increase
- major mail routing or notification-condition change
- cleanup mutation
- rollback-impossible or hard-to-rollback change
- publication policy relaxation
- mail volume increase
- candidate disappearance risk
- external-impact-heavy change

Claude must not ask the user to make technical judgment. Claude completes the Acceptance Pack first and gives a recommendation:

- recommendation: GO / HOLD / REJECT
- reason: 1-3 lines
- maximum risk
- rollback availability
- post-deploy verify plan
- production-safe regression plan
- user reply: `OK` / `HOLD` / `REJECT`

### 3.3 HOLD

If any of the following is UNKNOWN, the state is HOLD. Do not ask the user to decide; Claude must close the UNKNOWN first:

- tests
- rollback
- cost impact
- Gemini call delta
- mail volume impact
- candidate disappearance risk
- stop condition
- blast radius
- source impact
- whether existing behavior is unchanged
- post-deploy verify result

### 3.4 Post-Deploy Verify / Production-Safe Regression

Deploy complete is not DONE. Image or revision reflection is not DONE. Flag OFF is not a verify exemption.

After any production reflection, including both `CLAUDE_AUTO_GO` and `USER_DECISION_REQUIRED`, Claude must collect post-deploy verify and production-safe regression evidence before the ticket can become `OBSERVED_OK` or `DONE` candidate.

Required post-deploy verify:

- image / revision matches the intended target
- env / flag state matches the intended target
- service / job starts normally
- runtime rollback target is written
- GitHub/source rollback path is written for test or regression failure
- error increase: none
- mail volume: within expectation
- Gemini call delta: within expectation
- silent skip: 0
- Team Shiny From preserved
- publish / review / hold / skip routes remain alive
- stop condition is not hit

Production-safe regression checks may include only:

- read-only checks
- log checks
- health checks
- mail count checks
- env checks
- revision checks
- Scheduler / job execution observation
- sample article / candidate state checks
- flag OFF / no-send / dry-run-equivalent checks
- existing notification route preservation checks

Forbidden production tests:

- unintended bulk mail send
- source addition
- Gemini call increase
- publish criteria change
- cleanup mutation
- SEO/noindex/canonical/301 change
- rollback-impossible operation
- flag ON without user GO
- experiment while mail volume impact is UNKNOWN

If verify fails, do not mark `OBSERVED_OK`. Use `HOLD` or `ROLLBACK_REQUIRED` when any of these occur:

- `sent=10` burst
- MAIL_BUDGET exceeded
- silent skip occurs
- unexpected Gemini call increase
- Team Shiny From changes
- publish / review / hold / skip route breaks
- old_candidate storm recurs
- consecutive errors
- rollback target is unknown
- GitHub/source rollback path is unknown after tests or regression fail

### 3.5 Post-Deploy Verify Checklist(本番反映後 必須項目)

毎回の本番反映後、Claude は以下 7 項目を必ず確認 + 証跡記録(順不同、全て read-only):

1. **image / revision**: 反映 image SHA / revision が intended target と一致
2. **env / flag**: 反映 env / flag が intended target と一致(余計な diff なし)
3. **mail volume**: rolling 1h / 24h で MAIL_BUDGET 30/h・100/d 内、storm pattern 不在
4. **Gemini delta**: 反映前 1h vs 反映後 1h の Gemini call rate delta 範囲内(目安 ±5%)
5. **silent skip**: 0 維持(POLICY §8、existing publish/review/hold mail 不在化が起きていない)
6. **Team Shiny From**: `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` 維持
7. **rollback target**: runtime rollback(image SHA / revision)+ source rollback(`git revert` target commit)両方記録済

7 項目のいずれか不一致 / 異常時は `HOLD` or `ROLLBACK_REQUIRED`、§3.6 に従って rollback 実行。

### 3.6 Rollback Mechanism(2-tier、runtime + source 両方)

本番反映後に異常検出した場合、rollback は GitHub revert 単独では不足。runtime + source の 2-tier で実行:

**Tier 1: runtime rollback(production を即時 known-good 状態へ戻す)**

- env 単独問題: `gcloud run jobs/services update <name> --remove-env-vars=<flag>` で flag OFF(30 sec、§14 自律 hotfix 該当時)
- image / revision 問題: Cloud Run service は `gcloud run services update-traffic --to-revisions=<prev_rev>=100`、Cloud Run job は `gcloud run jobs update <name> --image=<prev_image_sha>` で前 revision / 前 image へ戻す(2-3 min)
- 必ず前 revision / 前 image SHA を反映前に記録しておく(§3.5 #7)

**Tier 2: source rollback(repo に bad change を残さない)**

- runtime rollback で production が安定したら、`git revert <bad_commit>` で revert commit を作成、origin master に push
- 強制 history rewrite(`git reset --hard` + `push -f`)は使わない
- revert commit は通常通り Codex が作成、Claude は push、§31-D commit便直列維持

**Tier 1 と Tier 2 は両方必須**。runtime rollback だけでは次回 image rebuild で bad change が再混入する。GitHub revert だけでは production の bad image / bad env が残る。

判断順序: 異常検出 → Tier 1 即実行(production 安定化最優先)→ 安定確認後 Tier 2(repo source of truth 整合)。

## 4. Claude Autonomous GO

Claude may proceed without user GO for:

- read-only investigation
- doc-only changes
- evidence collection
- test plan creation
- rollback plan creation
- Acceptance Pack drafting
- ticket state cleanup
- board compression
- incident analysis
- low-risk existing-ticket subtasks that do not touch code, deploy, env, Scheduler, SEO, source config, Gemini call count, or mail-routing behavior
- `CLAUDE_AUTO_GO` production changes defined in section 3.1

Claude must stop and prepare an Acceptance Pack if a task enters `USER_DECISION_REQUIRED`. Claude must HOLD, not ask the user, if any safety-critical field remains UNKNOWN.

## 5. Codex Lane Policy

- ACTIVE tickets are limited to 2.
- Codex is a worker, not a manager.
- Claude owns Codex lane A/B state management.
- Codex idle detection is Claude's responsibility.
- User discovering an idle Codex lane is an operations failure.
- When a lane finishes, Claude reviews output, verifies scope, updates the board, and then dispatches the next eligible low-risk subtask.
- Do not dispatch work just to keep Codex busy.
- Do not dispatch outside the current ticket order to avoid boredom or time pressure.
- New ticket sprawl is forbidden; absorb work into existing-ticket subtasks when possible.
- "慎重すぎて全停止" is REJECT.
- "時間があるから全部やる" is REJECT.
- Time boundaries are set by the user. Claude gates by risk, regression, and cost.

### Lane Idle Four-Condition Gate

Claude may keep a lane idle only when all four conditions are true:

1. There is genuinely no low-risk subtask remaining inside the current consumption order.
2. Existing Packs, read-only checks, test plans, rollback plans, and evidence tasks are already complete.
3. Remaining work would only duplicate Lane A or the active observe task.
4. Remaining work is either `USER_DECISION_REQUIRED` or `HOLD`, such as flag ON, behavior-changing env, Scheduler/SEO/source change, Gemini or mail increase, cleanup mutation, rollback-impossible change, or unresolved UNKNOWN risk.

If any low-risk existing-ticket subtask remains, Claude fires it autonomously. If the lane stays idle, Claude records the HOLD reason in the board or current-state note.

### Approved GO Example

Lane B was initially idle, but the four-condition gate found remaining low-risk subtasks: 298-Phase3 v4 Pack consistency review, ACCEPTANCE_PACK additional-field alignment, and UNKNOWN-residual detection. Claude therefore fired Lane B under manager control. This is the correct pattern: existing-ticket, doc/evidence/Pack work may be dispatched autonomously; it is not busywork.

## 6. Status Vocabulary

Allowed current states:

- `ACTIVE`
- `OBSERVE`
- `READY`
- `HOLD_NEEDS_PACK`
- `FUTURE_USER_GO`
- `OBSERVED_OK`
- `DONE`
- `FROZEN`
- `DEEP_FROZEN`
- `DEPRECATED`

Do not use:

- `DONE_PARTIAL`
- `NOT_DONE`
- ambiguous "maybe done" labels

`DONE` requires evidence. A code commit alone is not DONE. Deploy complete is not DONE. For production behavior, `OBSERVED_OK` and `DONE` require deploy evidence, post-deploy verify, and production-safe regression evidence.

## 7. Mail Storm Rules

These rules are incident-derived and permanent unless explicitly replaced by a new policy:

- Do not stop all mail.
- Do not pause Scheduler as the normal fallback.
- Do not reapply `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`.
- Do not wait for old candidate pool exhaustion.
- Do not GO if mail volume impact is UNKNOWN.
- MAIL_BUDGET violation is P1.
- Repeated old-candidate mail is P1 recurrence.
- Keep normal review, 289 post_gen_validate notification, and error notifications alive.
- 298-Phase3 is not DONE while it is rolled back after regression.
- Phase3 re-ON requires pool cardinality, expected mail count, max mails/hour, max mails/day, stop condition, and rollback plan.

## 8. Silent Skip Policy

User acceptance condition:

Every candidate must become visible through one of:

- publish
- review notification
- hold notification
- skip notification

Internal logs only, WP draft only, or silent skip are not accepted.

If a stop/skip gate is added, the regression test must prove:

- the skipped candidate has a reason
- the reason is durable
- the reason is user-visible or intentionally summarized
- existing publish/review/hold mail remains active
- Gemini calls do not increase unless user GO approved it

## 9. Acceptance Pack Requirement

Use `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` for any User GO decision.

The Pack must include:

- recommendation: GO / HOLD / REJECT
- scope
- non-scope
- risk
- mail impact
- Gemini/cost impact
- rollback
- stop condition
- tests
- evidence
- UNKNOWN fields

UNKNOWN in a safety-critical field means HOLD.

## 10. Ticket Creation Policy

- Do not create new tickets when an existing ticket can absorb the work as a subtask.
- New tickets are allowed for true new incident classes, disjoint scope, or explicit user request.
- Alias maps are preferred over destructive renumbering.
- Existing ticket numbers used in docs or commits must remain traceable.

## 11. Reporting Policy

Use Decision Batch for user-facing updates:

```text
結論: GO / HOLD / REJECT
P1 mail storm状態: contained / active / unknown
完了したチケット:
今進めているチケット:
次に流すチケット:
user判断が必要なもの: 0件 or Decision Batch
デグレ確認: test / mail / Gemini / silent skip / rollback
deploy対象:
image / revision:
env / flag:
post-deploy verify:
regression:
mail件数:
Gemini delta:
silent skip:
rollback target:
GitHub/source rollback:
判定: OBSERVED_OK / HOLD / ROLLBACK_REQUIRED
userが返すべき1行:
```

Do not send raw Codex logs or raw Codex self-reports to the user.

## 12. Permanent No-Touch Defaults

Unless a specific Acceptance Pack with user GO says otherwise:

- X automatic posting remains OFF.
- Team Shiny From remains unchanged.
- Scheduler cadence remains unchanged.
- SEO/noindex/canonical/301 remains unchanged.
- Source additions remain HOLD.
- Gemini call increases remain HOLD.
- Phase3 remains OFF after rollback.

## 13. Codex Worker Pool Persistence(/tmp 禁止、永続化 必須)

`/tmp` は Ubuntu 再起動 / cleanup で消える前提。**永続性が必要な ops state を /tmp に置かない**。

### 13.1 必須永続化 path(repo 内)

| 種類 | path |
|---|---|
| Codex prompt | `docs/handoff/codex_prompts/YYYY-MM-DD/lane_X_round_N.md` |
| Codex receipt(job ID / lane ID / start / expected output)| `docs/handoff/codex_receipts/YYYY-MM-DD/lane_X_round_N.md` |
| Lane state(running / completed / blocked / failed / idle + HOLD reason)| `docs/ops/WORKER_POOL.md` |

### 13.2 fire 完了の定義(4 step 全部達成)

prompt staging file 作成だけ ≠ fire:

1. prompt を repo 永続化(`docs/handoff/codex_prompts/`)
2. `codex exec` 実行(Bash bg)
3. job ID / lane ID 記録(`docs/handoff/codex_receipts/`)
4. WORKER_POOL.md の lane status を `running` に update + commit

### 13.3 lane idle 化 = HOLD reason 必須

`docs/ops/WORKER_POOL.md` の lane entry に **HOLD reason 必須記載**(消化順内 candidate 評価結果 / 4 条件 evaluate / next dispatch timing)。HOLD reason なしの idle 禁止。

### 13.4 /tmp 許容範囲

- その場限りの一時 staging(< 5 min、即 fire 用、再現不要)
- log tail / Bash output 一時保存
- 永続性不要な calculation buffer

### 13.5 4 NO 規律(永続)

```
No job ID, no fire.
No receipt, no fire.
No HOLD reason, no idle.
No /tmp for persistent ops state.
```

### 13.6 session 切断時の引継ぎ

Claude rate limit / context 圧縮 / WSL 再起動 / 別端末で起動 で監視不能になった場合:

1. `docs/ops/WORKER_POOL.md` で lane state 読取
2. `docs/handoff/codex_receipts/<latest>/` で running job ID 確認
3. `docs/handoff/codex_prompts/<latest>/` で prompt 内容把握
4. Bash background task list で running 確認(なければ failed 判定)
5. completed lane → 一次受け → push → 次 dispatch
6. idle lane → HOLD reason check → HOLD 妥当 or 次 dispatch 判定

## 14. Production Change 3 分類(永続、user 細切れ確認禁止)

「本番反映だから止める」ではなく「**危険な本番反映だけ止める**」。user を現場監督に戻さない。

### 14.1 CLAUDE_AUTO_GO(Claude 自律で本番反映、user 確認不要)

以下 **全 9 条件 AND 満たす場合**、Claude が image rebuild / Cloud Run job/service update / env 操作 まで自律実行:

1. flag OFF deploy(env 既存値変更なし、新 env 追加で default OFF)
2. live-inert deploy(env 未設定で挙動 100% 不変)
3. 挙動不変 image 差し替え(image 内 commit 内容が live-inert)
4. pytest green(baseline +0 regression、新 test 全 pass)
5. rollback target image SHA 確認済み
6. Gemini call 増加なし(scanner / persistence / ledger touch のみ等、Gemini 呼び出しなし)
7. mail volume 増加なし(sink-side cutoff / source-side 不変 / dedup 機能維持)
8. source 追加なし(`config/rss_sources.json` 不変)
9. Scheduler 頻度変更なし / SEO 不変 / publish 基準変更なし(POLICY §12 不変方針整合)

### 14.2 USER_DECISION_REQUIRED(Claude 推奨判断 + user 1 行返答)

以下のいずれか含む場合、Claude が **Acceptance Pack 完成 + 推奨判断 GO / HOLD / REJECT** まで出す。user は推奨に対して `OK / HOLD / REJECT` を 1 行で返すのみ:

- flag ON(挙動変化を伴う env apply)
- env 変更で挙動が変わる
- Gemini call 増加
- mail 量増加(MAIL_BUDGET 30/h・100/d 内設計でも増加方向)
- source 追加(`config/rss_sources.json` 拡張)
- Scheduler enable/disable/pause/resume/頻度変更
- SEO/noindex/canonical/301/sitemap/robots 変更
- publish/review/hold/skip 基準変更
- cleanup mutation(WP delete / draft 戻し / private 化)
- rollback 不能(履歴削除 / secret rotation 不能化 等)
- mail storm 再発リスクあり(過去事例で similar pattern 検出)

**user に技術判断を投げない**。Claude が技術 / デグレ / コスト / mail impact / rollback を確認 + 推奨まで完結。

### 14.3 HOLD(UNKNOWN 潰し優先、user に投げない)

以下のいずれか UNKNOWN なら **user に投げず Claude が UNKNOWN 潰しを進める**:

- test 結果 UNKNOWN
- rollback 手段 UNKNOWN
- cost impact(Gemini / Cloud Build / GCS)UNKNOWN
- mail volume impact UNKNOWN
- candidate disappearance risk UNKNOWN
- stop condition UNKNOWN

UNKNOWN 解消で USER_DECISION_REQUIRED に格上げ、または CLAUDE_AUTO_GO 条件達成で自律進行。

### 14.4 user 接点 minimization

- CLAUDE_AUTO_GO:user 通知不要(完了報告のみ POLICY §11 Decision Batch、resolved 1 行)
- USER_DECISION_REQUIRED:Acceptance Pack 提示 + 推奨判断、user 返答は `OK / HOLD / REJECT` 1 行のみ
- HOLD:user に投げず Claude が UNKNOWN 解消、解消後に再分類

### 14.5 適用例(本日 7 ticket)

| ticket | 分類 | 根拠 |
|---|---|---|
| 298-Phase3 v4 | USER_DECISION_REQUIRED → 本日 user GO 受領済 deploy 完了 | flag ON + mail storm 再発リスクあり、本日 19:30 JST「ならやる」受領 |
| 293-COST | impl/test/push = CLAUDE_AUTO_GO / image rebuild + flag ON = USER_DECISION_REQUIRED | 2 phase 化、本日 impl + push まで自律、deploy + flag ON は user 推奨 |
| 282-COST | USER_DECISION_REQUIRED | flag ON で挙動変化(preflight gate)|
| 290-QA | image rebuild = CLAUDE_AUTO_GO 候補(live-inert)/ flag ON = USER_DECISION_REQUIRED | 2 phase 化、image rebuild は HOLD 混入なし verify 後 自律 |
| 300-COST | USER_DECISION_REQUIRED | source 動作変化(idempotent ts append)|
| 288-INGEST | USER_DECISION_REQUIRED | source 追加 + Gemini call 増加 |
| 299-QA | OBSERVE のみ、production change なし | N=3 close gate で OBSERVE 維持 |

## 15. Field-Lead Discipline & User Interface Format(永続、user 依存度を下げる)

本日(2026-05-01)user 明示の strengthening。POLICY §2 / §3 / §11 と整合する強化版。

### 15.1 Claude responsibilities(全部 Claude が握る)

- 技術判断
- デグレ判断
- コスト判断
- mail impact 判断
- rollback 判断(runtime + source 両方、§3.6 整合)
- Codex worker pool 管理(idle 検出 + 次便 dispatch、§5 / §13 整合)
- 次チケット投入
- Acceptance Pack 作成(§9 整合)
- 推奨 GO / HOLD / REJECT 提示(§3.2 整合)

「user に判断を仰ぐ」ではなく「Claude が判断 + 推奨提示、user は判定だけ返す」。

### 15.2 user-facing 5-field format(USER_DECISION_REQUIRED 時の確定フォーマット)

```
1. 推奨: GO / HOLD / REJECT
2. 理由: 1〜3 行(技術 / デグレ / コスト / mail / rollback の要点)
3. 最大リスク: 1 行(発生時の被害想定)
4. rollback 可能か: yes / no(yes 時は Tier 1 + Tier 2 path 1 行で記述)
5. user が返す一言: OK / HOLD / REJECT
```

`OK` 返答 = 即実行。Claude が deploy + post-deploy verify(§3.5)+ Decision Batch 報告まで完結。

### 15.3 禁止行為(運用デグレ)

- user に「どうしますか？」と聞く
- user に複数候補(2-3 案)を並べて選ばせる
- 技術判断を user に渡す(image / env / flag / Gemini / mail / rollback すべて Claude 判断)
- Codex idle を user に発見させる(発見側になった時点で Claude の責務違反)
- close できないからと作業を pause する(close gate と作業継続は別問題、§3.3 HOLD は本番反映のみ)
- UNKNOWN を user 判断へ投げる
- user を中継役(relay)として使う(Claude → user → ChatGPT → user → Claude の loop)

### 15.4 UNKNOWN 処理(user に投げない)

UNKNOWN 検出時、Claude が以下を順に実行:

1. read-only 調査で潰す(log / config / GCS / WP REST GET)
2. ChatGPT 会議室に圧縮判断補助を依頼(user 経由で OK、ただし user は中継役のみ)
3. Codex 調査便で潰す(test / fixture / dry-run、§14 自律 hotfix 該当時は即 fire)
4. それでも潰せない場合のみ、推奨 HOLD(質問ではなく判定として)で 5-field format 提示

UNKNOWN 解消で再分類(CLAUDE_AUTO_GO / USER_DECISION_REQUIRED)。

### 15.5 user の役割(明示)

- 現場監督ではない
- Claude の推奨判断に対して `OK / HOLD / REJECT` を返すだけ
- 高 risk choice の最終責任(POLICY §2 整合)
- 細かい技術 / 運用判断は委任済(本 §15)

### 15.6 適用境界

| 状態 | Claude の動き | user 接点 |
|---|---|---|
| CLAUDE_AUTO_GO(§3.1)| 自律 deploy + 自律 post-deploy verify + Decision Batch 報告 | 完了報告のみ、判断不要 |
| USER_DECISION_REQUIRED(§3.2)| Acceptance Pack + 推奨 + 5-field format | 一言 `OK / HOLD / REJECT` |
| HOLD(§3.3)| UNKNOWN 潰し進行(調査・Pack化・推奨 HOLD 化)| user 不在 / 進捗 1 行報告のみ |
| §14 P0/P1 自律 hotfix(8 条件)| 即実行 + 事後報告 | 事後報告のみ、事前判断不要 |

## 16. Pre-Deploy Gate & Ticket Progress Loop(永続、現場自律ループ)

本日(2026-05-01)user 明示の追加。「方針が現場の自律実行ループに落ちていなかった」反省を解消。

### 16.1 Pre-Deploy Gate(本番反映前 必須確認 11 項目)

production 反映前(`CLAUDE_AUTO_GO` でも `USER_DECISION_REQUIRED` でも)、Claude は以下 11 項目を必ず確認:

1. target commit / HEAD 一致(deploy する image が intended commit を含む)
2. worktree clean(`git status --short` = 空、untracked が混入してない)
3. tests green(pytest baseline +0 regression)
4. regression なし(prev → new commit 一覧で HOLD ticket 該当 0、§release composition verify 整合)
5. rollback target 確認済み(runtime image SHA + source `git revert` 候補 commit、§3.6 整合)
6. env / flag 変更有無(変更ある場合は §3.2 USER_DECISION_REQUIRED か §3.1 CLAUDE_AUTO_GO 判定済)
7. Gemini call 増加有無(増加ある場合は §3.2)
8. mail volume impact(MAIL_BUDGET 30/h・100/d 内設計、storm 再発リスク評価)
9. candidate disappearance risk(silent skip 0 維持、§8 整合)
10. stop condition(§14 P0/P1 自律 rollback 8 条件のうち該当を明示)
11. Acceptance Pack 完成(`USER_DECISION_REQUIRED` 時、§9 整合)

UNKNOWN がある場合は user に投げず HOLD(§15.4 整合)。

### 16.2 Ticket Progress Loop(closeできないからpause = 禁止)

Claude は以下の順で自律的に進める。「close できないから pause」は禁止:

1. **DONE できるなら evidence 付き DONE**(§3.5 post-deploy verify pass + production-safe regression OK)
2. **DONE できないなら READY 化**(impl + test + push 完了、deploy 待ちの状態へ)
3. **READY 化できないなら UNKNOWN 潰し**(§15.4 順序: read-only 調査 → ChatGPT 圧縮 → Codex 調査便)
4. **UNKNOWN があるなら read-only 調査**(log / config / GCS / WP REST GET、production 不変)
5. **Pack 未完成なら Acceptance Pack 作成**(§9 整合、13 fields + 必要時 298-Phase3 additional)
6. **rollback 不明なら rollback plan 作成**(§3.6 2-tier、runtime + source)
7. **test 不明なら test plan 作成**(unit / smoke / regression / mail / rollback)
8. **Codex lane が idle なら既存ticket の低リスク subtask を投入**(§5 / §13 整合、新 ticket 起票より優先)

`HOLD` は本番反映停止の意味で使う。前段作業(Pack / UNKNOWN 潰し / test plan / rollback plan / READY 化)は CLAUDE_AUTO_GO で進む(§4 整合)。

### 16.3 5 Reflection Points(2026-05-01 永続記録)

本日の運用デグレ → 永続ルール反映:

1. **HOLD = 作業停止 と扱った誤り**: HOLD は本番反映停止であって前段作業停止ではない。Pack 作成 / UNKNOWN 潰し / test plan / rollback plan / READY 化は Claude 自律 GO(§16.2 整合)。
2. **user に技術判断を戻しすぎた誤り**: user は技術判断しない。Claude が技術 / デグレ / コスト / mail / rollback を判断、user には推奨 GO/HOLD/REJECT + 理由 + 最大リスク + rollback 可否のみ提示(§15.1 / §15.2 整合)。
3. **Codex worker pool 管理の弱さ**: Codex 完了後 Claude 一次受け / lane idle 検出は Claude 責務 / idle なら次の低リスク subtask 投入 / HOLD なら明確な理由 / 4 NO 規律(No job ID, no fire / No receipt, no fire / No HOLD reason, no idle / No /tmp、§13 整合)。
4. **/tmp に prompt や receipt を置く誤り**: /tmp は再起動 / cleanup で消える。prompt / job ID / receipt / lane status / HOLD 理由は repo 内記録(§13.1 / §13.4 整合)。
5. **GitHub revert と本番 rollback の混同**: 3 dimensions が独立(env/flag / image・revision / source/git revert)、必要に応じて組み合わせる。GitHub だけ戻して本番 rollback 済み扱いは禁止(§3.6 整合)。

### 16.4 Rollback 3 dimensions(§3.6 補足、永続)

| dimension | 戻し先 | 速度 | 用途 |
|---|---|---|---|
| env / flag rollback | 反映前 env 状態 | 30 sec(`gcloud run jobs/services update --remove-env-vars`)| flag ON 起因 / env 起因 異常時、Tier 1 |
| image / revision rollback | 反映前 image SHA / revision | 2-3 min(Cloud Run service `--to-revisions=`/job `--image=`)| image 内 commit 起因異常時、Tier 1 |
| source / git revert | repo の bad commit 反転 | commit + push 通常 flow | repo 反映を残さず、再 build で bad change が再混入を防ぐ、Tier 2 |

production 事故時、3 dimensions のうち該当するものを必要分組み合わせる。3 dimensions 同時実行 / 1 dimension のみで完了 / 順序入替 全て可、ただし production 安定優先(Tier 1 first)→ source 整合(Tier 2)。

### 16.5 古い表現の削除 / 修正

以下の表現は POLICY 全体で扱わない(本日 user 明示の修正対象):

- 「本番反映は一律 user GO 必須」→ 修正後: §3 で 3 分類、CLAUDE_AUTO_GO は user GO 不要
- 「deploy 完了で DONE」→ 修正後: §3.5 post-deploy verify pass + regression OK で OBSERVED_OK / DONE
- 「GitHub revert だけで本番 rollback 済み」→ 修正後: §3.6 / §16.4 で 3 dimensions 明示
- 「HOLD = 作業停止」→ 修正後: §3.3 / §16.2 で HOLD は本番反映停止のみ
- 「close できないなら pause」→ 修正後: §16.2 progress loop で禁止
- 「user に技術判断を求める」→ 修正後: §15.1 / §15.2 で Claude が判断 + 推奨提示
- 「Codex idle を user が発見する」→ 修正後: §5 / §13 / §15.3 で Claude 責務違反
