# 2026-05-01 Session End Handoff(user 追加判断不要、5/2 朝 自律再開用)

session 終了 22:45 JST。本 doc を 5/2 朝 startup 時に最初に読み、self-checklist で再開可能。

## 全 ticket 状態(本日 5/1 終了時点)

### deploy 完了済(production 反映済)

| ticket | status | image / revision | env / flag | 完了時刻 |
|---|---|---|---|---|
| 298-Phase3 v4 | OBSERVED_OK Phase 1-5 | publish-notice:1016670 → :d541ebb(293 deploy 時 image rebuild) | ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1 | 19:35 JST |
| 290-QA Pack A | OBSERVED_OK | yoshilover-fetcher:c14e269 / 00176-vnk(293 deploy で 00177-qtr へ traffic 移行) | ENABLE_WEAK_TITLE_RESCUE 未設定維持(default OFF) | 20:40 JST |
| 293-COST | **OBSERVED_OK_SHORT**(FULL_EXERCISE_OK 未到達) | yoshilover-fetcher:d541ebb / 00177-qtr + publish-notice:d541ebb | ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1 両 services | 21:00 JST |

### 改修 impl デプロイ直前まで完了(production 不触、image rebuild + flag ON は user GO 後別 phase)

| 改修 | commit | pytest | env knob(default OFF) | 状態 |
|---|---|---|---|---|
| #1 cache_hit split metric | `e7e656c` | focused 27/0 + full 2020/3 | ENABLE_CACHE_HIT_SPLIT_METRIC | デプロイ直前まで |
| #2 cache miss circuit breaker | `91ddfdf` | focused 33 + 29 subtests | ENABLE_GEMINI_CACHE_MISS_BREAKER + threshold/window | デプロイ直前まで |
| #3 per-post 24h Gemini budget | `76f748b` | 17/0 → 24/0 +7 new | ENABLE_PER_POST_24H_GEMINI_BUDGET + LIMIT | デプロイ直前まで |
| #6 cap=10 class reserve | `f31cf21` | 2029/0 + targeted 65 | ENABLE_PUBLISH_NOTICE_CLASS_RESERVE + class | デプロイ直前まで |

### 設計 / 観測準備 完了(doc-only)

- 300-COST read-only test plan v1(`7b38386`):impl 便 fire 用 contract 補強、276 行
- 293-COST FULL_EXERCISE 観測 runbook(5/2 朝 用):`docs/handoff/codex_responses/2026-05-02_293_full_exercise_observe_runbook.md`
- 288-INGEST Phase 1 visibility evidence(round 20):**FAIL**、violation 4(既知 POLICY §19.1 marker)、Phase 2 visibility fix 必須化

### HOLD 維持(user 明示、本日終了時点)

| ticket | HOLD 内容 | 解除条件 |
|---|---|---|
| 282-COST | env apply ENABLE_GEMINI_PREFLIGHT=1 | 293 FULL_EXERCISE_OK + 24h 安定(5/2 朝以降) |
| 290-QA Pack B | env apply ENABLE_WEAK_TITLE_RESCUE=1 | Pack A 1 週間 OBSERVED_OK(5/8 JST)+ Gemini delta UNKNOWN 解消 |
| 300-COST impl 便 fire | impl + image rebuild + deploy | 298 + 293 完了 + user GO |
| 288-INGEST Phase 3 source 追加 | `config/rss_sources.json` 編集 | Phase 1 PASS 化(Phase 2 visibility fix 完走) |
| Gemini call 増加 / mail 量増加 / publish-review-hold-skip 基準変更 deploy | 全 production change | per-ticket Pack で 内 + user GO |

## 5/2 朝 startup task list(優先順、Claude 自律 read-only)

### Task A: 298-Phase3 v4 Phase 6 verify(09:00 JST)

**runbook:** `docs/ops/NEXT_SESSION_RUNBOOK.md` §15

確認:
- rolling 1h sent: MAIL_BUDGET 30/h 内
- cumulative since 5/1 09:00 JST: MAIL_BUDGET 100/d 内
- silent skip: 0 継続
- permanent_dedup skip count: 106+ 安定
- real review / 289 / errors: 維持
- 5/1朝 storm 99 cohort sent: **0**(第二波防止)
- 13:35 storm 50 cohort sent: **0**

判定:全 pass → 298-Phase3 v4 OBSERVED_OK 確定。Phase 6 verify 結果 1 行報告。

### Task B: 293-COST FULL_EXERCISE observe(AI 上限 reset 後)

**runbook:** `docs/handoff/codex_responses/2026-05-02_293_full_exercise_observe_runbook.md`(本日作成済)

read-only verify 6 task:
1. AI 上限 reset 確認
2. preflight skip event 発生確認(fetcher + publish-notice)
3. publish-notice 「要review｜preflight_skip」mail 発生確認
4. Gemini delta -10〜-30% 測定
5. silent skip 0 維持
6. mail volume / Team Shiny / 既存通知 確認

FULL_EXERCISE_OK 確定条件:6 全 pass。

### Task C: 282-COST GO 検討(293 FULL_EXERCISE_OK + 24h 安定後)

5/2 朝 Task B pass 後、282-COST env apply Pack 提示。POLICY §15.2 5-field format で user GO 受領後 fire。

### Task D(自律 GO 候補、低リスク subtask):

両 Codex lane idle、HOLD reason 4 条件全 YES。startup で以下から優先順 fire:

1. **改修 #4 prompt-id cost review gate**(POLICY § + Pack template doc 反映、impl 不要 path、Lane A 適性)
2. **改修 #5 old_candidate ledger TTL impl**(narrow prune script、Lane A or B)
3. **288 Phase 2 visibility fix narrow design**(Phase 1 FAIL violation 4 path 修正、Lane A)
4. **290 Pack B Gemini call path read-only 解析**(weak title rescue が Gemini 含むか、Lane B)

各 fire 前に POLICY §19.3 dirty worktree pre-fire snapshot + scope disjoint check。

## 今回作業由来 dirty / 未 push / unexpected modified = 0 確認

Session 終了時点で以下を verify:

```bash
cd /home/fwns6/code/wordpressyoshilover

# 1. 未 push commit 0
git log --oneline origin/master..HEAD
# 期待:空

# 2. 今回作業由来の untracked / modified 0
git status --short
# 期待:whitelist 内のみ
```

### Whitelist(既存 ambient untracked、5/2 朝 startup で触らない)

- `docs/handoff/codex_requests/2026-04-24_*` / `2026-04-25_*`(歴史的、本日触ってない)
- `docs/handoff/run_logs/`
- `build/` / `data/` / `logs/` / `backups/` / `.codex/`
- `HEAD/`(壊れた断片名 untracked、長期残存)
- 上記以外の `?? ` で出る path で本日 turn 由来でないもの

5/2 朝の `git status --short` 期待出力:**whitelist 内のみ、本日作業 (5/1) 由来のものは 0**。

## §14 P0/P1 自律 rollback monitor(24h 継続、5/2 朝も)

trigger 検出時 Claude 自律実行(user GO 不要):

| trigger | 対応 |
|---|---|
| rolling 1h sent > 30 | env remove `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE`(30 sec) |
| silent skip > 0 | env remove + image rollback(2-3 min)+ git revert candidates 既 push |
| errors > 0 連続 | 同上 |
| 289 mail 減 | stop + 即報告(P0) |
| Team Shiny From 変動 | 即 rollback |
| publish/review/hold/skip 導線破損 | 同上 |
| Gemini call >+5%(本来 -方向) | abnormal 即 rollback |
| MAIL_BUDGET 超過 | 同上 |

## 異常時 3-dim rollback(POLICY §3.6 / §16.4)

最も新しい deploy = 293-COST(d541ebb)に対する rollback:

- **Tier 1 runtime image / revision:**
  - `gcloud run services update-traffic yoshilover-fetcher --to-revisions=yoshilover-fetcher-00176-vnk=100 --region=asia-northeast1`(2-3 min、290 Pack A の OBSERVED_OK 状態へ戻す)
  - `gcloud run jobs update publish-notice --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:1016670 --region=asia-northeast1`(2-3 min、298-v4 image へ戻す)
- **Tier 1 runtime env:**
  - `gcloud run services update yoshilover-fetcher --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION --region=asia-northeast1`(30 sec)
  - `gcloud run jobs update publish-notice --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION --region=asia-northeast1`(30 sec)
- **Tier 2 source:** `git revert 10022c0 7c2b0cc afdf140 6932b25` + push origin master(commit 由来事故時)

## Codex Lane 状態(両 idle、5/2 朝 startup 時 dispatch 候補)

両 Lane idle、HOLD reason 4 条件全 YES:
- last commit 完走 + push verified
- worktree clean(今回作業 scope)
- ambient untracked のみ残存
- 5/2 09:00 JST 以降 Phase 6 + FULL_EXERCISE 確認後に dispatch 再開

dispatch 候補は Task D(改修 #4 / #5 / 288 Phase 2 / 290 Pack B 解析)。

## 重要 file 索引(5/2 朝 startup 時)

- POLICY:`docs/ops/POLICY.md`(§17 Pre-Deploy Stop Mode / §18 Worker Dispatch / §19 Audit Permanent Guards / §20 Sequential Single-Ticket)
- CURRENT_STATE:`docs/ops/CURRENT_STATE.md`
- OPS_BOARD:`docs/ops/OPS_BOARD.yaml`
- NEXT_SESSION_RUNBOOK:`docs/ops/NEXT_SESSION_RUNBOOK.md`
- WORKER_POOL:`docs/ops/WORKER_POOL.md`
- INCIDENT_LIBRARY:`docs/ops/INCIDENT_LIBRARY.md`
- ACCEPTANCE_PACK_TEMPLATE:`docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`
- 5/2 Phase 6 + FULL_EXERCISE runbook:`docs/handoff/codex_responses/2026-05-02_293_full_exercise_observe_runbook.md`
- 288 Phase 1 evidence:`docs/handoff/codex_responses/2026-05-01_288_INGEST_phase1_visibility_evidence.md`
- 改修 #1〜#6 Pack v1:`docs/handoff/codex_responses/2026-05-01_change_*_pack_v1.md`

## 結論(user 追加判断 0、5/2 朝 自律再開可能)

- 本日 deploy chain step 1-2(290 Pack A + 293-COST)完走、298-v4 24h soak 並走中
- 改修 #1 / #2 / #3 / #6 デプロイ直前まで(default OFF、production 不触)
- 改修 #4 / #5 = 設計段階、5/2 朝 fire 候補
- 288 Phase 1 FAIL → Phase 2 visibility fix が source 追加 precondition、5/2 朝 narrow design 起票候補
- 282 / 290 Pack B / 300 / 288 Phase 3 = HOLD 維持、解除条件は本 doc table 通り
- §14 monitor 継続、storm pattern 不在

5/2 朝 09:00 JST に Phase 6 verify から自動再開、user 通知のみで判断不要。
