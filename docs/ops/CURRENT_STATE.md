# YOSHILOVER CURRENT_STATE

Last updated: 2026-05-01 17:55 JST(298-v4 deploy 完了 + Phase 1-5 OBSERVED_OK)
Owner: Claude updates this file as the operations source of truth.

This file is the first operational document to read at session start. If this file conflicts with session logs, old handoffs, old POLICY text, or old OPS_BOARD entries, this file and the current docs/ops set win.

## Today Decisions

- The user is not the work owner for every ticket.
- The user is only the final decision owner for high-risk changes.
- Claude is the field lead.
- Codex is the field developer / worker.
- Raw Codex answers must not be sent directly to the user.
- Do not ask the user small fragmented questions.
- Report decisions in a Decision Batch.
- When a Codex lane becomes idle, Claude must detect it and autonomously feed the next low-risk subtask from the existing ticket order.
- The user discovering an idle Codex lane is an operations failure.
- Read-only, doc-only, evidence collection, test plans, rollback plans, Acceptance Packs, and ticket cleanup are Claude autonomous GO.
- Production changes are classified as `CLAUDE_AUTO_GO`, `USER_DECISION_REQUIRED`, or `HOLD`. Safe production reflection is not blocked just because it is production.
- `CLAUDE_AUTO_GO`: flag OFF deploy, live-inert deploy, or behavior-preserving image replacement when tests are green, rollback is confirmed, and Gemini/mail/source/Scheduler/SEO/publish criteria/candidate disappearance risks do not increase.
- `USER_DECISION_REQUIRED`: flag ON, behavior-changing env, Gemini increase, mail volume increase, source addition, Scheduler/SEO change, publish/review/hold/skip criteria change, cleanup mutation, rollback-impossible change, or external-impact-heavy change.
- `HOLD`: tests, rollback, cost, Gemini delta, mail volume, candidate disappearance risk, stop condition, blast radius, source impact, behavior invariance, or post-deploy verify result is UNKNOWN.
- Deploy complete is not DONE. `OBSERVED_OK` / `DONE` require post-deploy verify and production-safe regression evidence.
- `CLAUDE_AUTO_GO` and `USER_DECISION_REQUIRED` both require post-deploy verify after reflection.
- If tests or production-safe regression fail because of a committed change, rollback must include GitHub/source rollback by non-destructive revert, not only runtime image/revision rollback.
- ACTIVE is limited to at most 2 tickets.
- The user decides time boundaries such as "today is done" or "continue."
- Claude should proceed by risk, regression, and cost gates, not by the clock.
- "Too cautious so everything stops" is REJECT.
- "There is time, so do everything" is REJECT.

## Today Reflection (2026-05-01) — POLICY §16.3 反映

5 reflection points(本日の運用デグレ → 永続ルール化):

1. **HOLD ≠ 作業停止**: HOLD は本番反映停止のみ。Pack/UNKNOWN潰し/test plan/rollback plan/READY化は Claude 自律 GO(POLICY §16.2 / §3.3)。
2. **user に技術判断を戻さない**: 技術/デグレ/コスト/mail/rollback は全て Claude 判断、user は推奨 GO/HOLD/REJECT + 理由 + 最大リスク + rollback 可否を受領するのみ(POLICY §15.1 / §15.2)。
3. **Codex worker pool 管理**: 完了後 Claude 一次受け / lane idle 検出は Claude 責務 / idle なら次の低リスク subtask 投入 / 4 NO 規律(POLICY §13 / §5 / §15.3)。
4. **/tmp 禁止**: prompt / job ID / receipt / lane status / HOLD 理由 = repo 内記録(POLICY §13.1 / §13.4)。
5. **3 dimension rollback**: env/flag / image・revision / source/git revert を独立扱い、必要組み合わせ。GitHub revert だけで本番 rollback 済み扱いは禁止(POLICY §3.6 / §16.4)。

## Current Incident State

### 298-Phase3 v4(本日 deploy 完了)

- Status: **OBSERVED_OK**(Phase 1-5 完了、Phase 6 = 5/2 09:00 JST 第二波防止 verify 残)
- Phase label: `DEPLOY_COMPLETE_OBSERVED_OK`
- 本日 19:30 JST user GO 受領「ならやる」、Lane B round 15 (`bbnqyhph3`) で Case F GCS pre-seed + flag ON apply
- image: `publish-notice:1016670` 不変(env だけ apply、§12 整合)
- env apply: `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
- GCS ledger pre-seed: 104 → 106 件(64109 first emit 後自動追記)
- post-deploy 7-point verify(§3.5):
  - image / revision: 一致
  - env / flag: 一致
  - mail volume: post-deploy slice sent=9(3 trigger、30/h・100/d 余裕)
  - Gemini delta: 増加なし(scanner / ledger touch のみ)
  - silent skip: 0 維持
  - MAIL_BRIDGE_FROM: `y.sebata@shiny-lab.org` 維持
  - rollback target: runtime = env remove(30 sec)+ image SHA 維持 / source = revert candidates 既 push
- regression:
  - 5/1朝 storm 99 cohort (63003-63311) → `OLD_CANDIDATE_PERMANENT_DEDUP` skip 確認
  - 13:35 storm 50 cohort (61938-62940) → 同 skip 確認
  - post 64109(104 pool 外)→ first emit 1 度のみ + ledger 自動追記
  - post_gen_validate / 古い候補 review path 全部観測、消失なし
- DONE 候補化条件: 5/2 09:00 JST Phase 6 第二波防止 read-only verify pass + 24h 安定確認(POLICY §3.5 整合、deploy 完了 ≠ DONE)
- §14 P0/P1 自律 rollback monitor 24h 継続: rolling 1h sent>30 / silent skip>0 / errors>0 / 289 減 / Team Shiny 変 検出で env remove 即実行(本日 13:55 実績整合)

### Mail Storm 状態

- contained(本日 13:35 storm → 13:55 §14 自律 env rollback、19:35 v4 GCS pre-seed deploy → storm 再発 0)
- 第二波 risk(5/2 09:00 JST 想定): permanent_dedup ledger 106 件で防止見込み、Phase 6 verify で確定

### Mail Storm Rules

- Do not stop all mail.
- Do not pause the Scheduler as a normal fallback.
- Do not reapply `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`.
- Do not wait for pool exhaustion as a strategy.
- If mail volume impact is UNKNOWN, GO is forbidden.
- MAIL_BUDGET violation is P1.
- Repeated old-candidate mail is P1 recurrence.
- Normal review mail, 289 notifications, and error notifications must remain active.

## Current Ticket Board Summary

| ticket | current state | allowed now | user GO required for |
|---|---|---|---|
| 293-COST | デプロイ直前まで(impl + 4 commit + push 完了、pytest 2018/0) | impl + test + Pack + rollback plan + post-deploy verify plan | 本番 deploy(image rebuild + flag ON) |
| 300-COST | デプロイ直前まで(read-only analysis) | source-side cost analysis, Pack/test/rollback planning, 実装準備 | 実装 + 本番 deploy |
| 299-QA | OBSERVE | flaky/transient evidence and baseline recording | deploy 系作業に昇格時は別判定 |
| 298-Phase3 v4 | OBSERVED_OK(deploy 完了、Phase 1-5 pass、§17 適用外) | Phase 6 verify (5/2 09:00 JST、Claude 自律 EVIDENCE_ONLY)+ 24h 安定 monitor | DONE 化判定(Phase 6 + 24h 安定後) |
| 282-COST | flag ON 直前まで | Pack + UNKNOWN 潰し + rollback plan(293 完了後) | flag ON |
| 290-QA | デプロイ直前まで | classification Pack + 実装 + Pack | 本番 deploy(weak title rescue enablement)|
| 288-INGEST | source 追加直前まで | source-add decision Pack + UNKNOWN 潰し | source 追加 |

POLICY §17 Pre-Deploy Stop Mode 適用(298-Phase3 v4 以外、本日 user 明示)。push は本番反映を伴わない運用のため Claude 自律 GO。

## Decision Batch Format

Use this format when reporting to the user:

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

## Next Session Read Order

1. `docs/ops/CURRENT_STATE.md`
2. `docs/ops/POLICY.md`
3. `docs/ops/OPS_BOARD.yaml`
4. `docs/ops/NEXT_SESSION_RUNBOOK.md`
5. `docs/ops/INCIDENT_LIBRARY.md`
6. `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`

Session logs, handoff logs, and codex responses are history only. They are not current policy.

## Immediate Operating Posture

- 298-Phase3 v4 deploy 完了、5/2 09:00 JST Phase 6 第二波防止 read-only verify を Claude 自律 EVIDENCE_ONLY scope で実行(POLICY §3.5 / §4 整合)。
- §14 P0/P1 自律 rollback monitor 24h 継続、storm 再発検出時 env remove 即実行(本日 13:55 実績整合)。
- 293-COST READY_FOR_DEPLOY、image rebuild + flag ON Pack 提示は 298 安定後 deferred(POLICY §3.2)。
- 300-COST 継続、read-only 分析 + 分類前置。
- 299-QA OBSERVE 継続、P0 でない。
- user に技術判断 / UNKNOWN / Codex idle / READY 化未済 を投げない(POLICY §15.3 / §16.2 整合)。
- 新 ticket 起票は既存 ticket subtask 化を優先(POLICY §10)。
- raw Codex output は user に出さない、Claude が Decision Batch 形式で圧縮(POLICY §11 / §15.2)。
