# YOSHILOVER WORKER POOL

Codex Lane state(POLICY §13 永続管理、`/tmp` 禁止、4 NO 規律)。
Last updated: 2026-05-01 21:35 JST(改修 #1/#6 デプロイ直前まで完了 + Lane A round 30 / Lane B round 19 並走、282 HOLD 維持)

## 現在進行 phase: 改修 sequential + 282 HOLD + 293 FULL_EXERCISE 観測準備

**完了済 deploy(本日 5/1):**

| ticket | status | image / revision | env / flag | 完了時刻 |
|---|---|---|---|---|
| 298-Phase3 v4 | OBSERVED_OK Phase 1-5(Phase 6 = 5/2 09:00 JST 待ち) | publish-notice:1016670(env apply only) | ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1 | 19:35 JST |
| 290-QA Pack A | OBSERVED_OK | yoshilover-fetcher:c14e269 / 00176-vnk | ENABLE_WEAK_TITLE_RESCUE 未設定維持(default OFF) | 20:40 JST |
| 293-COST | **OBSERVED_OK_SHORT**(FULL_EXERCISE_OK 未到達) | yoshilover-fetcher:d541ebb / 00177-qtr + publish-notice:d541ebb | ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1 両 services | 21:00 JST |

**改修 impl デプロイ直前まで完了(本日 5/1):**

| 改修 | commit | pytest | env knob | 状態 |
|---|---|---|---|---|
| #1 cache_hit split metric | `e7e656c`(Claude fallback) | focused 27/0 + full 2020/3(out-of-scope 既存 fail 3) | ENABLE_CACHE_HIT_SPLIT_METRIC default OFF | デプロイ直前まで |
| #6 cap=10 class reserve | `f31cf21`(Codex 直接) | 2029/0 + targeted 65 pass | ENABLE_PUBLISH_NOTICE_CLASS_RESERVE / *_REAL_REVIEW / *_POST_GEN_VALIDATE / *_ERROR default OFF | デプロイ直前まで |

**現在進行 Codex 並走(production 不触、impl/設計 便):**

- Lane A round 30: **running**(改修 #2 cache miss circuit breaker impl、`bg04licmm`、21:30 JST fire)
- Lane B round 19: **running**(300-COST read-only test plan、同上)

**§14 mail monitor 並走:**

- 直近(12:00-12:25 UTC = 21:00-21:25 JST)sent 1/0/2/0/0、errors 0、suppressed 0、storm pattern 不在
- §14 P0/P1 自律 rollback monitor 24h 継続(298-v4 + 290 Pack A + 293-COST 重ね)

**HOLD 維持(user 明示):**

- 282-COST ENABLE_GEMINI_PREFLIGHT=1 → 293 FULL_EXERCISE_OK 確定後
- 290-QA Pack B ENABLE_WEAK_TITLE_RESCUE=1 → Pack A 1 週間 OBSERVED_OK 後
- 288-INGEST Phase 3 source 追加 → 298 + 293/282 完了後
- Gemini call 増加 / mail 量増加 / publish/review/hold/skip 基準変更 deploy 全禁止

### 現フェーズ実態(逃げない、Codex は動いていない):

| 項目 | 値 |
|---|---|
| 進行作業種別 | Claude deploy / build 実行中 |
| 対象 ticket | 293-COST(image rebuild + flag ON `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1`)|
| 対象 commit | `d541ebb`(origin/master HEAD、293 impl 全 4 commits 含む `6932b25` / `afdf140` / `7c2b0cc` / `10022c0`)|
| 対象 image tag | `d541ebb` |
| build 対象 service / job | `yoshilover-fetcher`(service)+ `publish-notice`(job)、両方 src/rss_fetcher.py + src/publish_notice_scanner.py で env 参照 |

### build status

| service / job | status | build_id | log |
|---|---|---|---|
| publish-notice | **running**(Cloud Build queued/in_progress、20:50:56 JST submit) | `1065ed53-93fc-4e3d-846d-d286841d6b56` | `/tmp/build_publish_notice_293.log` |
| yoshilover-fetcher | **running**(archive creation / submit、20:51 JST retry) | TBD(submission 中) | `/tmp/build_fetcher_293.log` |

両 build 完了見込:~5-10 min(20:55-21:00 JST)。

### deploy status

| step | status |
|---|---|
| 1. build success | **pending**(両 build 完了待ち) |
| 2. image push to Artifact Registry | pending |
| 3. Cloud Run service `yoshilover-fetcher` update --image + env apply | pending |
| 4. Cloud Run job `publish-notice` update --image + env apply | pending |
| 5. traffic 100% to new revision | pending |
| 6. post-deploy verify 15 項目 | pending |
| 7. 判定 OBSERVED_OK / HOLD / ROLLBACK_REQUIRED | pending |

### traffic status(現時点、deploy 前)

- `yoshilover-fetcher`:revision `yoshilover-fetcher-00176-vnk`(image `:c14e269`)= 100%(本日 20:40 JST 290 Pack A deploy 後の active revision)
- `publish-notice`:image `:1016670`(本日 19:35 JST 298-v4 deploy で env apply のみ、image 不変維持)

deploy 後想定:
- `yoshilover-fetcher`:revision `yoshilover-fetcher-00177-XXX`(image `:d541ebb`)= 100%、prev 00176-vnk = rollback target
- `publish-notice`:execution 次回から image `:d541ebb`、prev image `:1016670` = rollback target

### env / flag 差分(293 で適用、両 services に同一)

新規追加:
- `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1`(default 0 → 1、preflight skip notification 有効化)
- `PREFLIGHT_SKIP_LEDGER_PATH=<path>`(ledger 書込 path、digit ledger jsonl)
- `PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS=<comma-separated fields>`(dedupe key 構成 fields)

不変維持:
- 他 全 env(`MAIL_BRIDGE_FROM`、`ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` 等)
- `ENABLE_WEAK_TITLE_RESCUE` 未設定維持(290 Pack A live-inert 状態保持)

### rollback target(3 dimensions、§3.6 / §16.4)

- **runtime image / revision rollback**:
  - `yoshilover-fetcher`:`gcloud run services update-traffic yoshilover-fetcher --to-revisions=yoshilover-fetcher-00176-vnk=100 --region=asia-northeast1`(2-3 min、290 Pack A の OBSERVED_OK 状態へ戻す)
  - `publish-notice`:`gcloud run jobs update publish-notice --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:1016670 --region=asia-northeast1`(2-3 min、298-v4 image へ戻す)
- **runtime env / flag rollback**:
  - 両 service / job:`gcloud run services/jobs update <name> --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION,PREFLIGHT_SKIP_LEDGER_PATH,PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS --region=asia-northeast1`(30 sec、preflight gate OFF へ戻す)
- **GitHub / source revert path**:
  - `git revert 10022c0 7c2b0cc afdf140 6932b25` + push origin master(commit 由来事故時、4 commits chain 全 revert)

### post-deploy verify 項目(§20.2 6 + §20.3 9 = 15、本 deploy は flag ON で **強い** verify)

§20.2 本番稼働確認:
1. image / revision intended target 一致(both services)
2. env / flag intended target 一致(`ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1` 等反映確認)
3. service / job 正常起動(`gcloud run services/jobs describe` + executions list)
4. Scheduler / trigger 想定通り(giants-* + publish-notice-trigger + guarded-publish-trigger ENABLED 維持)
5. error log 増加なし
6. rollback target 明記済(本 record)

§20.3 本番 safe デグレ試験(flag ON のため強め、~30-60 min observe):
7. mail volume MAIL_BUDGET 内(rolling 1h ≤ 30、24h ≤ 100、preflight skip 由来 +N 想定 ~5 mails/h、上限 storm pattern 不在)
8. sent burst なし
9. old_candidate storm なし(`OLD_CANDIDATE_PERMANENT_DEDUP` skip 機能継続)
10. Gemini delta -10〜-30%(preflight gate により減少方向、+5% 超過時 abnormal)
11. silent skip 0(POLICY §8、preflight skip → publish-notice 経由 visible mail で 0 維持)
12. MAIL_BRIDGE_FROM `y.sebata@shiny-lab.org` 維持
13. publish/review/hold/skip 導線維持
14. 既存通知 alive(289 / real review / error)
15. WP 主要導線維持

### STOP 条件(検出 → §20.6 rollback、§20.5 異常 8 trigger)

- build fail(任意 service)
- image push fail
- Cloud Run update fail
- 任意 post-deploy verify 項目 fail
- 異常 8 trigger 検出:
  - mail burst(rolling 1h sent>30)
  - MAIL_BUDGET 超過(rolling 1h>30 or 24h>100)
  - silent skip>0
  - Gemini call >+5%(本来 -方向、+方向検出 abnormal)
  - Team Shiny From 変動
  - publish/review/hold/skip 導線破損
  - rollback target 不明
  - error 連続

任意 trigger 検出時、3-dim rollback 即実行 + post-rollback verify(§20.2 + §20.3 同等)+ commit 由来なら git revert 4 commits + push。

## Codex 実装 lane 状態(現在 idle、stash 待避中)

### Lane A(idle、Claude deploy 中の context、stashed work あり)

- status: **idle**
- stash 0(top of stack):`改修-impl-WIP-restore-after-290-deploy`(改修 #1 cache_hit split metric impl WIP / 改修 #6 cap=10 class reserve impl WIP の混合 working tree)
- next_dispatch:Claude deploy 完走(290 OBSERVED_OK + 293 OBSERVED_OK 後)→ stash 復帰 → 改修 #1 + #6 impl 便再 fire(POLICY §17.1 自律 GO scope)
- HOLD reason:Claude が deploy 実行中、Codex impl lane 並列で worktree dirty 化すると build / push / verify 干渉、deploy 完走まで待機

### Lane B(idle、scope disjoint な dev 便なし)

- status: **idle**
- stash 0:同上(改修 #6 部分含む)
- next_dispatch:Lane A stash 復帰後、改修 #2 / #3 等 sequential

## Active Lanes(両 running、改修 impl 並列駆動中、production 不触)

### Lane A round 29 v2(running、改修 #1 cache_hit split metric impl)

- status: **running**
- job_id: `bhbektxze`(wrapper bash)
- ticket: 改修-29-cache-hit-split-metric(audit 由来)
- prompt_path: `docs/handoff/codex_prompts/2026-05-01/lane_a_round_29_cache_hit_split_metric.md`
- receipt_path: `docs/handoff/codex_receipts/2026-05-01/lane_a_round_29.md`(完了後 Claude 作成)
- started_at: 2026-05-01 21:01 JST(stash pop 復帰後 fresh fire)
- worktree state: stash 復帰時点で `src/gemini_cache.py` / `src/llm_call_dedupe.py` / `src/rss_fetcher.py` modified、`src/publish_notice_scanner.py` modified(改修 #6 と一部干渉)
- expected_output: src 改修 + tests + Pack v1 + commit + push
- HOLD/STOP condition: pytest fail / scope 違反 / 既存 cache logic 挙動変化検出

### Lane B round 18 v2(running、改修 #6 cap=10 class reserve impl)

- status: **running**
- job_id: `bhbektxze`(同 wrapper bash)
- ticket: 改修-30-cap10-class-reserve(audit 由来)
- prompt_path: `docs/handoff/codex_prompts/2026-05-01/lane_b_round_18_cap10_class_reserve.md`
- receipt_path: `docs/handoff/codex_receipts/2026-05-01/lane_b_round_18.md`(完了後 Claude 作成)
- started_at: 2026-05-01 21:01 JST
- worktree state: `src/publish_notice_scanner.py` modified(Lane A と一部 file 重複、scope disjoint だが merge 注意)
- expected_output: scanner cap reserve 実装 + tests + Pack v1 + commit + push
- HOLD/STOP condition: cap=10 全体上限変動 / pytest fail / 298-v4 / 293 観察 entanglement

### 並走 monitor

- 293-COST observation 継続(~30 min trend confirm まで Claude が mail / Gemini delta 監視)
- §14 P0/P1 monitor 継続

## 並走 monitor(Claude 一次受け、§14 P0/P1)

- mail [summary] log read 〜10-15 min ごと
- 直近 5 trigger(20:01-20:20 JST)sent 0/0/3/1/0、errors 0、silent skip 0、storm pattern 不在
- §14 自律 rollback trigger 検出時 即実行(rolling 1h sent>30 / silent skip>0 / errors>0 / 289 減 / Team Shiny From 変)

## 改修 6 件 実状況分類(claim 引っ込めて再評価、証拠ベース)

- ❌ 「6 件全 デプロイ直前まで到達」は claim 不可(impl 便完走 + commit + push verify 後にのみ)

| # | 改修 | 段階 | 証拠 |
|---|---|---|---|
| #1 cache_hit split metric | **impl 便 running**(Lane A round 29) | prompt + Pack proposal のみ、impl/test/Pack v1 未生成、commit 0 |
| #2 cache miss circuit breaker | **design proposal 段階**(Pack proposal text のみ) | prompt 未起票、impl/test/Pack v1 未生成 |
| #3 per-post 24h Gemini budget | **design proposal 段階** | 同上 |
| #4 prompt-id cost review gate | **design proposal 段階** | 同上(POLICY 追加 + Pack template 拡張で済む可能性、impl 不要 path) |
| #5 old_candidate ledger TTL | **design proposal 段階** | 同上 |
| #6 cap=10 class reserve | **impl 便 running**(Lane B round 18) | prompt + Pack proposal のみ、impl/test/Pack v1 未生成、commit 0 |

「デプロイ直前まで」 = impl + test + commit + push + Pack v1 完成 + UNKNOWN 解消(deploy 直前 capture 項目除く)+ 13 fields + 10a + 10b + 11 3-dim(env / image / **GitHub source revert** 全 dim 明記)+ 12 + 13 全充足 → これらが揃って初めて到達。

## Lane History(本日 round 1-29 + 改修 impl WIP stash、commit hash 着地済)

### Lane A history

| round | ticket | job_id | commit | status |
|---|---|---|---|---|
| 1 | 282-COST Pack draft | `bu63il63k` | `1fd2755` | done |
| 2 | 300-COST Pack draft | `b93y1byc4` | `54c2355` | done |
| 3 | 278-280-MERGED Pack draft | `bbjtahzxz` | `0521a25` | done |
| 4 | 298-Phase3 v4 Pack | `b2ktx5kd0` | `cdd0c3f` | done |
| 5 | UNKNOWN resolution | `bsl484r1l` | `ade62fb` | done |
| 6 | 299-QA N=2 evidence | `bxv7c4jgp` | `60242be` | done |
| 7 | 293-COST Pack final review | `bbimo1p1x` | `856dd59` | done |
| 8 | 290-QA Pack supplement | `b95tm2a2e` | `d089340` | done |
| 9 | 282-COST Pack supplement | `bimwnrpgq` | `925003d` | done |
| 10 | 278-280-MERGED supplement | `bbj14iavs` | `a9ab8b6` | done |
| 11 | user proposal summary | `bd93ylgqy` | `9c5225d` | done |
| 12 | Pack consistency review v2 | `b1fiot2e4` | (closed prior) | done |
| 18 | 293-COST impl + test + commit + push | `bbzzdjawe` | `6932b25` / `afdf140` / `7c2b0cc` / `10022c0` | done |
| 19 | POLICY §3.5+§3.6+§15+§14.5 row commit | `bvbjy9mog` (retry) | `3d67d2a` | done |
| 20 | ops reflection 9-file doc commit(POLICY §16 + CURRENT_STATE + OPS_BOARD + NEXT_SESSION_RUNBOOK + INCIDENT_LIBRARY + WORKER_POOL + 3 handoff)| `bfafdyqns` | `7b606ee` | done |
| 21 | round 20 close + receipt 永続化 | `bgaivvmwm` | `a524a04` | done |
| 22 | POLICY §17 Pre-Deploy Stop Mode 永続化 | `buklecukq` (retry `bm1pgt1qh`) sandbox blocked | `40c4d15` (Claude fallback) | done |
| 23 | Pack readiness audit(5 ticket) | `b3n2mzmaj` | (read-only audit、no commit) | done |
| 24 | 293-COST deploy pack v3 | (parallel batch) sandbox blocked | `df96eeb` (Claude fallback batch) | done |
| 25 | 290-QA Pack A/B split | `b3s97m7o5` | `9f638f5` | done |
| 26 | 282-COST pack v3 template refresh | `boq306tyo` | `d2ee8e3` | done |
| 27 | 288-INGEST Pack v3 4-phase split | `btby69pqe` sandbox blocked | `fedf159` (Claude fallback) | done |
| 28 | 290-QA Pack A live-inert deploy | `bgub9cruu` (gcloud read-only fail) `bm0oxofqb` (re-fire CLOUDSDK_CONFIG fix) | killed (precondition not met、5/2 19:35 JST 以降に再 fire) | killed |
| 28b | POLICY §19 audit guards 永続化 + multi-phase split + ACCEPTANCE_PACK_TEMPLATE 拡張 | (Claude direct edit + sandbox blocked) | `a1aac8f` (Claude fallback) | done |
| 28c | POLICY §20 Sequential Single-Ticket Production Reflection 永続化 | (Claude direct edit) | `45d6503` (Claude fallback) | done |
| 29 | 改修 #1 cache_hit split metric impl | `b8h77qcj2`(wrapper、pid 117934) | (running) | **running** |

### Lane B history

| round | ticket | job_id | commit | status |
|---|---|---|---|---|
| 1 | 290-QA Pack draft | `bf6m2c0nm` | `65c09c1` | done |
| 2 | 288-INGEST Pack draft | `by59srg7l` | `26ede3a` | done |
| 3 | Pack consistency review v1 | `bvnlwrvjz` | `908b081` | done |
| 4 | 298 stability evidence pre | `b4fg71arl` | `aa6a8eb` | done |
| 5 | 298-Phase3 v4 alignment review | `b8ur8zfwh` | `9d5620e` | done |
| 6 | 298-Phase3 v4 UNKNOWN close | `bwudujkv2` | `cf86e88` | done |
| 7 | 300-COST Pack supplement | `bxb9ltfcw` | `c959327` | done |
| 8 | 288-INGEST Pack supplement | `bn532umyf` | `5f8b966` | done |
| 9 | INCIDENT_LIBRARY append | `b0grmdtgy` | `4abe1d5` | done |
| 10 | 293-COST numbering correction | `b6mrhbha7` | (closed prior) | done |
| 14 | 298-Phase3 v4 robustness supplement | `bum1usgj7` | `dab9b8e` | done |
| 15 | 298-Phase3 v4 deploy(Case F GCS pre-seed + flag ON) | `bbnqyhph3` | env apply only(image 不変) | done — Phase 1-5 OBSERVED_OK、Phase 6 verify 5/2 09:00 JST 待ち、24h soak ends 5/2 19:35 JST |
| 16 | 300-COST impl-prep narrow spec | (parallel batch) | `e14c944` | done |
| 17 | コスト + storm 安全性 audit(8 軸) | `b3jkl9sd6`(re-fire) | (read-only audit、no commit) | done |
| 18 | 改修 #6 cap=10 class reserve impl | `b8h77qcj2`(wrapper、pid 118203) | (running) | **running** |

## 4 NO 規律(POLICY §13.5 整合)

```
No job ID, no fire.
No receipt, no fire.
No HOLD reason, no idle.
No /tmp for persistent ops state.
```

## Session 切断時 引継ぎ

1. 本 file で lane state 把握
2. running の場合、job_id を Bash background task list で確認
3. completed の場合、receipt_path + expected_output で結果 verify + push
4. idle の場合、HOLD reason check + 4 条件評価 → 妥当 or 次 dispatch
