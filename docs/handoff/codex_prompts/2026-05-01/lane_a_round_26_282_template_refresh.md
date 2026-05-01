# Lane A round 26 — 282-COST template refresh

## 目的

audit (Lane A round 23) 指摘:現行 282 ready pack の precondition 表が `293 impl + test + commit + push` 未完前提で止まっている。現行 `293 READY_FOR_DEPLOY`(impl 完了)に同期し、§3.5 7-point verify、§16.4 3-dimension rollback、`OK/HOLD/REJECT` 正規化を反映した template-refreshed Pack v3 を作成。

doc-only。code / deploy / production 不変。

## 不可触リスト

- src / tests / scripts / config / .codex / quality-* / draft-body-editor 触らない
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- `git add -A` 禁止
- `docs/ops/*` 触らない
- 既 `2026-05-01_282_COST_*` file 削除しない、保存

## scope (新規 file 1 + prompt 永続化、合計 2 path stage)

added (A):
- `docs/handoff/codex_responses/2026-05-01_282_COST_pack_v3_template_refresh.md`(template refresh、`OK/HOLD/REJECT` + §3.5 + §16.4 反映)
- `docs/handoff/codex_prompts/2026-05-01/lane_a_round_26_282_template_refresh.md`(self-include)

冒頭に「supersedes `2026-05-01_282_COST_ready_pack.md`(pre-293-impl phase artifact)」明記。

## Pack 内容(13 fields + 10a/10b、ACCEPTANCE_PACK_TEMPLATE 整合)

### Decision Header

```yaml
ticket: 282-COST
recommendation: HOLD  # 293-COST image rebuild + flag ON deploy 完了 + 24h OBSERVED_OK 後に GO 化検討
decision_owner: user
execution_owner: Codex (env apply via Cloud Run job update) + Claude (push, post-deploy verify)
risk_class: medium
classification: USER_DECISION_REQUIRED  # flag ON で挙動変化(preflight gate)
user_go_reason: FLAG_ENV+COST_INCREASE
expires_at: 293 image rebuild + flag ON OBSERVED_OK + 24h 安定後
```

### 13 fields(ACCEPTANCE_PACK_TEMPLATE)

1. **Conclusion**: 推奨 HOLD(293-COST 完了 + 24h OBSERVED_OK が precondition、その後 user GO で GO 化)
2. **Scope**: env apply `ENABLE_GEMINI_PREFLIGHT=1`、preflight gate 有効化
3. **Non-Scope**: image 変更 / Scheduler / SEO / source 追加 / mail routing 変更
4. **Current Evidence**:
   - 293-COST impl 完了:`6932b25` / `afdf140` / `7c2b0cc` / `10022c0`(全部 origin/master)
   - 293 pytest: 2018/0
   - 293 ready: `READY_FOR_DEPLOY`、image rebuild + flag ON 待ち
   - prod state: 298-v4 deploy OBSERVED_OK
5. **User-Visible Impact**: preflight gate 有効化で source-side cost 削減、見かけ上 publish 量変化なし(silent skip 0 維持)
6. **Mail Volume Impact**: なし(env apply、code path 既 push、preflight gate 経由 mail flow 不変)
7. **Gemini / Cost Impact**: **Gemini call 削減** が目的(scope 内 expected reduction、UNKNOWN 残:exact delta は post-deploy で確定)
8. **Silent Skip Impact**: preflight skip → publish-notice 経由 visible mail(293 で実装済み)、silent skip 0 維持
9. **Preconditions**:
   - 293 image rebuild deploy 完了
   - 293 flag ON OBSERVED_OK
   - 293 24h 安定確認
   - rollback path 確認(env remove)
   - Gemini call delta UNKNOWN 解消(rough: 削減方向、exact 数値は post-deploy 確定)
10. **Tests**:
   - 293 既 pytest 2018/0(`test_preflight_skip_notification.py` 含む 7 new test)
   - 282 専用 unit / integration test なし(env apply のみ、code path 既 push)
   - smoke / regression / mail / rollback 試験は post-deploy 済 obs で確認
10a. **Post-Deploy Verify Plan(POLICY §3.5 7-point)**:
   - image / revision: 293 deploy 後 image 維持(`<293 SHA>`)
   - env / flag: `ENABLE_GEMINI_PREFLIGHT=1` 反映確認
   - mail volume: rolling 1h<30、24h<100、storm pattern 不在
   - Gemini delta: ±5% 内(本来 −方向、exact 確定)
   - silent skip: 0 維持
   - MAIL_BRIDGE_FROM 維持
   - rollback target: env remove 30 sec
10b. **Production-Safe Regression Scope**:
   - allowed: read-only / log / health / mail count / env / revision / Scheduler obs / sample candidate / dry-run / existing notification route
   - forbidden: bulk mail / source addition / Gemini increase / publish criteria change / cleanup mutation / SEO / rollback-impossible / flag ON without GO / mail UNKNOWN
11. **Rollback(POLICY §3.6 / §16.4 3 dimensions)**:
   - Tier 1 runtime env: `gcloud run jobs update <job> --remove-env-vars=ENABLE_GEMINI_PREFLIGHT`(30 sec)
   - Tier 1 runtime image: 該当なし(env-only change)
   - Tier 2 source: 該当なし(env-only)、ただし将来 preflight code change を含む場合 `git revert <commit>`
   - last known good: 293 deploy 直後 image SHA + 293 commit family `6932b25..10022c0`
12. **Stop Conditions**: rolling 1h sent>30 / silent skip>0 / errors>0 / 289減 / Team Shiny変 / publish/review/hold/skip導線破損 / Gemini call >+5%(本来 −だが、+方向検出時 abnormal)
13. **User Reply**: 一言 `OK` / `HOLD` / `REJECT`

## 実施

1. 既 `docs/handoff/codex_responses/2026-05-01_282_COST_ready_pack.md` 確認、参照のため supersedes 明記
2. 既 supplement / unknown resolution 整合確認(`925003d` / `ade62fb`)
3. 新 file 作成: 上記 13 fields + Decision Header + 「supersedes pre-293-impl phase artifact」明記、現行 293 READY_FOR_DEPLOY ベースの precondition 表に refresh
4. `git add docs/handoff/codex_responses/2026-05-01_282_COST_pack_v3_template_refresh.md docs/handoff/codex_prompts/2026-05-01/lane_a_round_26_282_template_refresh.md`
5. `git diff --cached --name-status` で A 2 確認
6. commit message: `docs(handoff): 282-COST Pack v3 template refresh (293 impl 完了 sync + 7-point verify + 3-dim rollback + OK/HOLD/REJECT)`
7. plumbing 3 段 fallback 装備
8. `git log -1 --stat` で 2 file changed 確認

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "docs/handoff/codex_responses/2026-05-01_282_COST_pack_v3_template_refresh.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_a_round_26_282_template_refresh.md"
  ],
  "diff_stat": "2 files changed (added)",
  "commit_hash": "<hash>",
  "test": "n/a (doc-only)",
  "remaining_risk": "none",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff 2 file (handoff 側のみ、ops 不変)
- 内容 template refresh のみ、impl 不変
- pytest +0(doc-only)
- scope 内
- rollback 不要(可逆 doc commit)
