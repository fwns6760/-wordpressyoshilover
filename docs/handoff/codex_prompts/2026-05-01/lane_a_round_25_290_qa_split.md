# Lane A round 25 — 290-QA live-inert / enablement split

supersedes `2026-05-01_290_QA_ready_pack.md` (monolithic phase artifact)

## 目的

audit (Lane A round 23) 指摘:現行 290 ready pack は image rebuild + flag ON を一体化、`live-inert deploy` と `ENABLE_WEAK_TITLE_RESCUE=1 enablement` を分離してない → CLAUDE_AUTO_GO 候補範囲と USER_DECISION_REQUIRED 範囲が ticket-level で曖昧。

本 round で 2 pack に split:

- **Pack A (live-inert deploy)**: image rebuild、flag OFF default、挙動 100% 不変、CLAUDE_AUTO_GO 候補
- **Pack B (enablement)**: `ENABLE_WEAK_TITLE_RESCUE=1` flag ON、挙動変化、USER_DECISION_REQUIRED

doc-only。code / deploy / production 不変。

## 不可触リスト

- src / tests / scripts / config / .codex / quality-* / draft-body-editor 触らない
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- `git add -A` 禁止
- `docs/ops/*` 触らない
- 既 `2026-05-01_290_QA_*` file 削除しない、保存

## scope (新規 file 2 + prompt 永続化、合計 3 path stage)

added (A):
- `docs/handoff/codex_responses/2026-05-01_290_QA_pack_A_live_inert_deploy.md`(image rebuild、CLAUDE_AUTO_GO 候補)
- `docs/handoff/codex_responses/2026-05-01_290_QA_pack_B_enablement.md`(flag ON、USER_DECISION_REQUIRED)
- `docs/handoff/codex_prompts/2026-05-01/lane_a_round_25_290_qa_split.md`(self-include)

冒頭に「supersedes `2026-05-01_290_QA_ready_pack.md`(monolithic phase artifact)」明記。

## Pack A (live-inert deploy) 内容

### Decision Header

```yaml
ticket: 290-QA
recommendation: GO  # 298-v4 24h 安定後、CLAUDE_AUTO_GO で進行可
decision_owner: Claude  # CLAUDE_AUTO_GO 該当時
execution_owner: Codex (build) + Claude (push, deploy verify)
risk_class: low
classification: CLAUDE_AUTO_GO  # POLICY §3.1 全条件確認
user_go_reason: n/a (live-inert deploy)
expires_at: 5/2 09:00 JST Phase 6 verify pass + 24h 安定後
```

### 13 fields(Pack A、live-inert deploy)

1. **Conclusion**: 推奨 GO(live-inert deploy、挙動不変、Pack B enablement と切離)
2. **Scope**: image rebuild `<weak-title-rescue 含む新 SHA>`、env 変更なし(`ENABLE_WEAK_TITLE_RESCUE` 未設定 = default OFF)
3. **Non-Scope**: env 変更 / flag ON / Scheduler / SEO / source / Gemini / mail routing
4. **Current Evidence**:
   - existing impl commits: `c14e269` 既 push 済(audit 報告参照)
   - tests: pytest baseline 維持予定
   - prod state: 298-v4 OBSERVED_OK
5. **User-Visible Impact**: なし(flag OFF default、code path 不到達)
6. **Mail Volume Impact**: なし(挙動不変)
7. **Gemini / Cost Impact**: なし(コード unreachable)
8. **Silent Skip Impact**: 不変(silent skip 0 維持、POLICY §8)
9. **Preconditions**: 298-v4 Phase 6 verify pass + 24h 安定 + image build success + rollback target SHA 確認
10. **Tests**: pytest +0(挙動不変)+ 290 関連 unit test pass
10a. **Post-Deploy Verify Plan(POLICY §3.5 7-point)**:
   - image / revision matches `<new SHA>`
   - env / flag: 変更なし確認
   - mail volume: 不変
   - Gemini delta: 0
   - silent skip: 0 維持
   - MAIL_BRIDGE_FROM 維持
   - rollback target: prev image SHA 記録
10b. **Production-Safe Regression Scope**:
   - allowed: read-only / log / health / mail count / env / revision / Scheduler obs / sample candidate / dry-run / existing notification route
   - forbidden: bulk mail / source addition / Gemini / publish criteria / cleanup mutation / SEO / rollback-impossible / flag ON without GO / mail UNKNOWN
11. **Rollback(POLICY §3.6 / §16.4 3 dimensions)**:
   - Tier 1 runtime: image rollback `gcloud run jobs update <job> --image=<prev_SHA>`(2-3 min)
   - Tier 2 source: `git revert c14e269` + push(必要時)
   - last known good: prev image SHA + 直近安定 commit
12. **Stop Conditions**: rolling 1h sent>30 / silent skip>0 / errors>0 / 289減 / Team Shiny変 / publish/review/hold/skip導線破損
13. **User Reply**: 一言 `OK`(CLAUDE_AUTO_GO 該当時、user 通知のみ)

## Pack B (enablement) 内容

### Decision Header

```yaml
ticket: 290-QA-enablement
recommendation: HOLD  # Pack A live-inert deploy 完了 + 1 週間 OBSERVED_OK 後に GO 化検討
decision_owner: user
execution_owner: Codex + Claude
risk_class: medium
classification: USER_DECISION_REQUIRED  # flag ON で挙動変化
user_go_reason: FLAG_ENV+WEAK_TITLE_RESCUE_ENABLEMENT
expires_at: Pack A live-inert OBSERVED_OK + 1 週間後
```

### 13 fields(Pack B、enablement)

1. **Conclusion**: 推奨 HOLD(Pack A 安定後 user GO で GO 化)
2. **Scope**: env apply `ENABLE_WEAK_TITLE_RESCUE=1`、weak title rescue path 有効化
3. **Non-Scope**: image 変更 / Scheduler / SEO / source 追加 / Gemini call 増加(rescue 経路は内部 fallback、新規 Gemini call なし想定だが要確認)
4. **Current Evidence**: Pack A live-inert deploy 完了 evidence(commit + image SHA + post-deploy verify pass)が precondition
5. **User-Visible Impact**: weak title 検出 → review mail / post_gen_validate notification 経路、normal review wall 維持
6. **Mail Volume Impact**: expected +1〜3 mail/h (weak title rescue 検出時)、MAIL_BUDGET 30/h 内
7. **Gemini / Cost Impact**: 確認必須(rescue path で Gemini call 増えるか)、UNKNOWN 解消必須
8. **Silent Skip Impact**: weak title rescue → review 経由 visible mail、silent skip 0 維持
9. **Preconditions**:
   - Pack A live-inert deploy OBSERVED_OK + 1 週間安定
   - Gemini call delta 数値確定
   - mail volume burst 数値確定
   - rollback path 確認(env remove)
10. **Tests**: weak title rescue unit test + integration + mail flow + rollback test
10a. **Post-Deploy Verify Plan(POLICY §3.5 7-point)**:
   - image / revision: Pack A と同一
   - env / flag: `ENABLE_WEAK_TITLE_RESCUE=1` 反映確認
   - mail volume: rolling 1h<30、24h<100
   - Gemini delta: ±5%(UNKNOWN 解消後の数値で判定)
   - silent skip: 0
   - MAIL_BRIDGE_FROM 維持
   - rollback target: env remove 30 sec
10b. **Production-Safe Regression Scope**: Pack A と同等
11. **Rollback(POLICY §3.6 / §16.4 3 dimensions)**:
   - Tier 1 runtime env: `gcloud run jobs update <job> --remove-env-vars=ENABLE_WEAK_TITLE_RESCUE`(30 sec)
   - Tier 1 runtime image: 該当なし(env-only change)
   - Tier 2 source: 該当なし(env-only)、ただし将来 weak title rescue narrow code change を含むなら `git revert <commit>`
12. **Stop Conditions**: rolling 1h sent>30 / Gemini call >+5% / silent skip>0 / errors>0 / publish/review/hold/skip導線破損
13. **User Reply**: 一言 `OK` / `HOLD` / `REJECT`

## 実施

1. 既 `docs/handoff/codex_responses/2026-05-01_290_QA_ready_pack.md` 確認、参照のため supersedes 明記
2. Pack A 新 file 作成: 上記 13 fields + Decision Header + 「Pack A: live-inert deploy」明記
3. Pack B 新 file 作成: 上記 13 fields + Decision Header + 「Pack B: enablement」明記、Pack A 完了が precondition 明記
4. `git add docs/handoff/codex_responses/2026-05-01_290_QA_pack_A_live_inert_deploy.md docs/handoff/codex_responses/2026-05-01_290_QA_pack_B_enablement.md docs/handoff/codex_prompts/2026-05-01/lane_a_round_25_290_qa_split.md`
5. `git diff --cached --name-status` で A 3 確認
6. commit message: `docs(handoff): 290-QA split into Pack A (live-inert deploy CLAUDE_AUTO_GO) + Pack B (enablement USER_DECISION_REQUIRED)`
7. plumbing 3 段 fallback 装備
8. `git log -1 --stat` で 3 file changed 確認

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "docs/handoff/codex_responses/2026-05-01_290_QA_pack_A_live_inert_deploy.md",
    "docs/handoff/codex_responses/2026-05-01_290_QA_pack_B_enablement.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_a_round_25_290_qa_split.md"
  ],
  "diff_stat": "3 files changed (added)",
  "commit_hash": "<hash>",
  "test": "n/a (doc-only)",
  "remaining_risk": "none",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff 3 file (handoff 側のみ、ops 不変)
- 内容 Pack A + Pack B split + supersedes 明記のみ
- pytest +0(doc-only)
- scope 内
- rollback 不要(可逆 doc commit)
