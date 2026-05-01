# Lane A round 28 — 290-QA Pack A live-inert deploy(POLICY §20 chain step 1)

## ⚠️ 重要: gcloud は必ず CLOUDSDK_CONFIG 経由で(298-v4 round 15 整合)

Codex sandbox の `~/.config/gcloud` は read-only。gcloud 実行前に必ず writable config を準備:

```bash
# 初回のみ:既存設定を /tmp/gcloud-cfg にコピー(round 15 と同じ pattern)
mkdir -p /tmp/gcloud-cfg
cp -r /home/fwns6/.config/gcloud/* /tmp/gcloud-cfg/ 2>/dev/null || true
chmod -R u+w /tmp/gcloud-cfg

# 全 gcloud 呼出に CLOUDSDK_CONFIG prefix:
CLOUDSDK_CONFIG=/tmp/gcloud-cfg gcloud --project=baseballsite ...
```

`CLOUDSDK_CONFIG=/tmp/gcloud-cfg` を全 gcloud 呼出に必ず付ける。付け忘れると read-only fs error で詰まる(298-v4 round 15 で確立した workaround)。

## ⚠️ rollback target(本 round で確定済、Pack 内 placeholder 全埋)

- service: `yoshilover-fetcher`(Cloud Run service、giants-realtime-trigger 等の `/run` endpoint host)
- prev image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d`
- prev revision: `yoshilover-fetcher-00175-c8c`
- env: `ENABLE_WEAK_TITLE_RESCUE` 未設定(deploy 後も未設定維持)
- source revert: `git revert c14e269`(c14e269 = 290 weak_title_rescue impl commit)

異常時 rollback 順序:
- Tier 1 image rollback: `CLOUDSDK_CONFIG=/tmp/gcloud-cfg gcloud --project=baseballsite run services update-traffic yoshilover-fetcher --to-revisions=yoshilover-fetcher-00175-c8c=100 --region=asia-northeast1`(2-3 min)
- Tier 2 source: `git revert c14e269` + push(必要時、本 deploy で問題出れば)

## 目的

POLICY §20.8 chain order の最初:290-QA Pack A live-inert deploy 実行。image rebuild + Cloud Run 反映 + post-deploy verify 6+9 項目 + 10-item report。

「live-inert」 = `ENABLE_WEAK_TITLE_RESCUE` env 未設定 = flag OFF default = code path 不到達 = 挙動 100% 不変。CLAUDE_AUTO_GO 候補(POLICY §3.1 全条件確認)。

reference: `docs/handoff/codex_responses/2026-05-01_290_QA_pack_A_live_inert_deploy.md`(Pack v3、commit `9f638f5`)

## scope

production change:
- image build(`c14e269` を含む新 SHA)
- Cloud Run service / Cloud Run Job update --image=<new_SHA>(該当 service / job 特定要)
- env / flag 変更なし(`ENABLE_WEAK_TITLE_RESCUE` 未設定維持)
- Scheduler 変更なし
- source 追加なし

doc / receipt:
- 新 file: `docs/handoff/codex_responses/2026-05-01_290_QA_pack_A_deploy_evidence.md`(deploy 後 10-item report)
- 受領 file: `docs/handoff/codex_receipts/2026-05-01/lane_a_round_28.md`(Codex 便 receipt)

## 不可触リスト(Hard constraints)

- env / flag 一切 apply しない(`ENABLE_WEAK_TITLE_RESCUE` 未設定維持)
- Scheduler / SEO / source / mail routing 触らない
- 290 Pack A 以外のチケット deploy しない
- 298-v4 既 deploy / env 触らない
- Gemini call 増加なし確認

## 実施

### Step 0: Pre-Deploy Gate(POLICY §16.1 + §19、5 step)

1. release composition verify: `git log --oneline <prev_image_commit>..HEAD` で HOLD ticket 混入確認
   - prev image = 290 関連 service の現在 image SHA (要 lookup: `gcloud run services describe` or `gcloud run jobs describe`)
   - HEAD = `c14e269` 含む現在 origin/master(現状 `45d6503`)
2. dirty worktree snapshot: `git status --short` whitelist 内のみ
3. silent skip grep: `grep -r "PREFLIGHT_SKIP_MISSING_\|no_op_skip\|REVIEW_POST_DETAIL_ERROR" src/` = 0
4. 3-dim rollback anchor 全埋確認(Pack A 内 placeholder `<prev_SHA>` 残存 確認 + actual SHA 取得して埋める)
5. mail path LLM-free: `grep -r "gemini\|openai\|generateContent" src/publish_notice_* src/mail_*` = 0

5 step pass で deploy 開始。1 件 fail で stop。

### Step 1: deploy 前確認(POLICY §16.1 11 項目)

- target commit / HEAD 一致(image build 対象 = `45d6503` or specific SHA)
- worktree clean
- pytest 緑(`pytest -q`)
- regression なし
- rollback target SHA 確認(prev image SHA capture)
- env 変更なし
- Gemini call 増加なし
- mail volume impact なし(挙動不変)
- candidate disappearance なし(挙動不変)
- stop condition 記録済
- Acceptance Pack ready(Pack A 既 push 済 `9f638f5`)

### Step 2: deploy 実行

1. 290 Pack A 該当 service / job 特定(`weak_title_rescue` / `draft_body_editor` 関連、要 lookup):
   - 候補: `draft-body-editor` Cloud Run Job(weak title rescue 系の処理)
   - または `fetcher` Cloud Run Job、`guarded-publish` Cloud Run Job、`publish-notice` Cloud Run Job
   - actual: `gcloud run jobs list --region=asia-northeast1` で全 job + service 確認、Pack A 該当判断
2. image build:
   - Cloud Build or local build → Artifact Registry push
   - 新 SHA 取得(本 round の rollback target)
3. Cloud Run job / service update:
   - `gcloud run jobs update <name> --image=<new_SHA> --region=asia-northeast1` (job の場合)
   - or `gcloud run services update <name> --image=<new_SHA> --region=asia-northeast1` (service の場合)
4. env / flag 変更なし確認(`gcloud run jobs/services describe` 後 env 一覧 diff)

### Step 3: 本番稼働確認(POLICY §20.2、6 項目)

deploy 直後 〜5 min:

1. image / revision: 新 SHA 反映確認(`gcloud run jobs/services describe` で image field)
2. env / flag: `ENABLE_WEAK_TITLE_RESCUE` 未設定維持確認、他 env diff なし
3. Cloud Run service / job 正常起動(`gcloud run jobs executions list` 直近 fail なし)
4. Scheduler / trigger 想定通り(`gcloud scheduler jobs list` 該当 enabled / lastAttemptTime 直近)
5. error log 増加なし(`gcloud logging read` errors keyword、deploy 前後比較)
6. rollback target 明記:prev image SHA + new image SHA 記録

### Step 4: 本番 safe デグレ試験(POLICY §20.3、9 項目、live-inert 軽め)

deploy 後 15-30 min 観察:

1. mail volume:rolling 1h sent ≤ 30、24h ≤ 100(`publish-notice [summary]` log 観測)
2. sent burst なし(直近 4-6 trigger sent 観測)
3. old_candidate storm なし(`OLD_CANDIDATE_PERMANENT_DEDUP` skip 機能継続、ledger 整合)
4. Gemini delta 0(挙動不変、Gemini call rate deploy 前後比較 = 0%)
5. silent skip 0(POLICY §8 維持、`PREFLIGHT_SKIP_MISSING_*` / `REVIEW_POST_DETAIL_ERROR` 件数 0)
6. MAIL_BRIDGE_FROM `y.sebata@shiny-lab.org` 維持
7. publish/review/hold/skip 導線維持(全 path 観測)
8. 既存通知 alive(289 / real review / error notification 全部観測)
9. WP 主要導線維持(post 生成 → guarded-publish → publish-notice の chain 観測)

### Step 5: 判定

全 6+9 = 15 項目 pass で **OBSERVED_OK**。
1 件 fail で **HOLD or ROLLBACK_REQUIRED**(POLICY §20.5 異常 trigger 該当時)。

### Step 6: 10-item report(POLICY §20.7 形式)

新 file `docs/handoff/codex_responses/2026-05-01_290_QA_pack_A_deploy_evidence.md` に書く:

```
1. ticket: 290-QA Pack A live-inert
2. deploy したか: yes
3. image / revision: <new_SHA>
4. env / flag: ENABLE_WEAK_TITLE_RESCUE 未設定維持(変更なし)
5. 本番稼働確認: pass / fail / partial(§20.2 6 項目内訳)
6. デグレ試験: pass / fail / partial(§20.3 9 項目内訳)
7. mail / Gemini / silent skip: rolling 1h sent=<n> / Gemini delta 0% / silent skip 0
8. rollback target: image SHA <prev_SHA>(2-3 min) + git revert <c14e269>
9. 判定: OBSERVED_OK / HOLD / ROLLBACK_REQUIRED
10. 次に進むチケット: 293-COST(USER_DECISION_REQUIRED、Claude が user 5-field 提示)
```

### Step 7: commit + receipt

- evidence file + receipt + prompt 永続化
- commit message: `deploy(290-QA Pack A): live-inert image rebuild + Cloud Run reflection + 15-item post-deploy verify`
- push origin master(Codex sandbox blocker 時 Claude fallback 通知)

## 異常時 rollback(POLICY §20.5 / §20.6)

異常 8 trigger 検出時:

- mail burst → image rollback `gcloud run jobs/services update <name> --image=<prev_SHA>`(2-3 min)
- silent skip > 0 → 同上 + git revert `c14e269`
- error 連続 → 同上
- Gemini call 想定外 → 同上(本来 0%、+5% 超過時)

rollback 後 post-rollback verify(§20.2 + §20.3 同等)実施、production 安定化確認 → Tier 2 git revert + push origin master。

## 完了報告

```json
{
  "status": "completed | hold | rollback_required",
  "ticket": "290-QA Pack A",
  "deployed": true,
  "image_sha_before": "<prev>",
  "image_sha_after": "<new>",
  "post_deploy_verify": "pass | fail | partial",
  "regression_test": "pass | fail | partial",
  "judgement": "OBSERVED_OK | HOLD | ROLLBACK_REQUIRED",
  "next_ticket": "293-COST or none",
  "10_item_report_path": "docs/handoff/codex_responses/2026-05-01_290_QA_pack_A_deploy_evidence.md",
  "commit_hash": "<hash>",
  "test": "pytest <baseline>/0 (no regression)",
  "remaining_risk": "<...>",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master + report user"
}
```

## 5 step 一次受け契約

- production change(image rebuild + Cloud Run update)、live-inert(flag OFF default)
- 15 項目 post-deploy verify pass で OBSERVED_OK、1 件 fail で HOLD / ROLLBACK
- pytest +0 regression
- scope 内
- 3-dim rollback 全 dim 確保
