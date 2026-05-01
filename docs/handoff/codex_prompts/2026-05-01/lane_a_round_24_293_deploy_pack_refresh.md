# Lane A round 24 — 293-COST deploy-phase Pack refresh

## 目的

293-COST を impl 完了 state(`6932b25` / `afdf140` / `7c2b0cc` / `10022c0`、pytest 2018/0)に同期した **deploy-phase Pack** へ refresh。POLICY §3.5 7-point verify、§16.4 3-dimension rollback、OK/HOLD/REJECT 正規化、10b production-safe regression scope を反映。

doc-only、code 変更なし、deploy なし、production 不変。

## 不可触リスト

- src / tests / scripts / config / .codex / quality-* / draft-body-editor 触らない
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- `git add -A` 禁止
- `docs/ops/*` 触らない(Pack refresh は handoff 側のみ、ops 整合は別 round)
- 既存 `2026-05-01_293_COST_*` file は touching 可能だが、既 ready pack と final review は **保存**(rename or 新 file 作成、削除しない)

## scope (新規 file 1 + 既 file 0 編集、合計 1 path stage)

added (A):
- `docs/handoff/codex_responses/2026-05-01_293_COST_deploy_pack_v3.md`(新規、impl 完了 state 反映)

注: 既 `2026-05-01_293_COST_ready_pack.md` は削除しない、後方互換用に保存。`v3` を最新版として位置づける(本 file 内で「supersedes 2026-05-01_293_COST_ready_pack.md」明記)。

prompt 永続化:
- `docs/handoff/codex_prompts/2026-05-01/lane_a_round_24_293_deploy_pack_refresh.md`(self-include)

## Pack 内容(13 fields + 10a/10b、ACCEPTANCE_PACK_TEMPLATE 整合)

### Decision Header

```yaml
ticket: 293-COST
recommendation: GO | HOLD | REJECT  # Claude 推奨を最後に書く
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: medium
classification: USER_DECISION_REQUIRED  # image rebuild + flag ON
user_go_reason: FLAG_ENV+IMAGE_REBUILD
expires_at: 5/2 09:00 JST Phase 6 verify pass + 24h 安定後
```

### 13 fields

1. **Conclusion**: 推奨 GO / HOLD / REJECT(Claude 判断、1 sentence reason)
2. **Scope**: image rebuild(`yoshilover-fetcher:<new SHA>`、preflight skip 含む)+ env apply `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1` + `PREFLIGHT_SKIP_LEDGER_PATH` + `PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS`
3. **Non-Scope**: Cloud Run service traffic split / Scheduler 変更 / SEO / source 追加 / Gemini call 増加 / mail routing
4. **Current Evidence**:
   - commits: `6932b25` / `afdf140` / `7c2b0cc` / `10022c0` 全部 origin/master 反映済
   - tests: pytest baseline 2008/0 → after 2018/0 (+10 = 7 new + 3 既存、299-QA transient なし fresh 環境で pass)
   - prod state: 298-v4 deploy 完了 OBSERVED_OK、Lane A/B idle
5. **User-Visible Impact**: preflight skip 時に email 通知(現状 silent skip と区別)、normal review mail / 289 / Team Shiny From 維持
6. **Mail Volume Impact**: expected mails/h ~5 (preflight skip 観測 from 過去 6h)、MAIL_BUDGET 30/h 内、初日 burst 想定 ~10 上限
7. **Gemini / Cost Impact**: skip 通知に Gemini call なし(scanner / ledger touch のみ)、source/candidate 数不変
8. **Silent Skip Impact**: preflight skip → publish-notice 経由で visible mail、silent skip 0 維持(POLICY §8 整合)
9. **Preconditions**: 298-v4 Phase 6 verify pass + 24h 安定 + image build success + rollback target SHA 確認
10. **Tests**: unit / smoke / regression / mail / rollback 全 pytest 2018/0
10a. **Post-Deploy Verify Plan(POLICY §3.5 7-point)**:
   - image / revision matches `<new SHA>`
   - env / flag matches `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1`
   - service / job startup
   - runtime rollback target: prev image SHA 記録
   - GitHub/source rollback path: revert candidates `6932b25..10022c0`
   - error trend: 0
   - mail volume: rolling 1h<30, 24h<100
   - Gemini delta: ±5%
   - silent skip: 0
   - Team Shiny From: y.sebata@shiny-lab.org 維持
   - publish/review/hold/skip 導線維持
   - stop condition not hit
10b. **Production-Safe Regression Scope**:
   - allowed: read-only / log / health / mail count / env check / revision check / Scheduler obs / sample candidate / dry-run / existing notification route
   - forbidden: bulk mail / source addition / Gemini increase / publish criteria change / cleanup mutation / SEO / rollback-impossible / flag ON without GO / mail UNKNOWN experiment
11. **Rollback(POLICY §3.6 / §16.4 3 dimensions)**:
   - Tier 1 runtime:
     - env rollback: `gcloud run jobs update <job> --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION,PREFLIGHT_SKIP_LEDGER_PATH,PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS`(30 sec)
     - image rollback: `gcloud run jobs update <job> --image=<prev_SHA>`(2-3 min)
   - Tier 2 source: `git revert 6932b25 afdf140 7c2b0cc 10022c0` + push origin master
   - last known good: prev image SHA + commit `dab9b8e`(298-v4 robustness supplement)
12. **Stop Conditions**: rolling 1h sent>30 / silent skip>0 / errors>0 / 289減 / Team Shiny From変 / publish/review/hold/skip導線破損 / Gemini call >+5% / cache_hit ratio >±15%pt
13. **User Reply**: 一言 `OK` / `HOLD` / `REJECT`

## 実施

1. 既 file 確認: `cat docs/handoff/codex_responses/2026-05-01_293_COST_ready_pack.md`(supersedes link 用)
2. 新 file 作成: `docs/handoff/codex_responses/2026-05-01_293_COST_deploy_pack_v3.md`、上記 13 fields + Decision Header を埋める
3. 冒頭に「supersedes `2026-05-01_293_COST_ready_pack.md`(impl-start phase artifact)」明記
4. Claude 推奨 = 暫定 `HOLD`(298-v4 24h 安定確認まで)、user GO 受領で GO 化、5/2 朝 Phase 6 verify pass 後に再評価
5. `git add docs/handoff/codex_responses/2026-05-01_293_COST_deploy_pack_v3.md docs/handoff/codex_prompts/2026-05-01/lane_a_round_24_293_deploy_pack_refresh.md`
6. `git diff --cached --name-status` で A 2 確認
7. commit message: `docs(handoff): 293-COST deploy-phase Pack v3 (impl complete sync + 7-point verify + 3-dim rollback + OK/HOLD/REJECT)`
8. plumbing 3 段 fallback 装備
9. `git log -1 --stat` で 2 file changed 確認

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "docs/handoff/codex_responses/2026-05-01_293_COST_deploy_pack_v3.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_a_round_24_293_deploy_pack_refresh.md"
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
- 内容 13 fields + 10a/10b + Decision Header のみ、impl 不変
- pytest +0(doc-only)
- scope 内
- rollback 不要(可逆 doc commit)
