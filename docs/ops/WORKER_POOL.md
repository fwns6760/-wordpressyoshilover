# YOSHILOVER WORKER POOL

Codex Lane state(POLICY §13 永続管理、`/tmp` 禁止、4 NO 規律)。
Last updated: 2026-05-01 21:50 JST(両 Codex lane idle、改修 #1/#2/#6 デプロイ直前まで完了、282-COST HOLD 維持、293-COST FULL_EXERCISE 待ち)

## 完了済 deploy(本日 5/1)

| ticket | status | image / revision | env / flag | 完了時刻 |
|---|---|---|---|---|
| 298-Phase3 v4 | OBSERVED_OK Phase 1-5(Phase 6 = 5/2 09:00 JST 待ち) | publish-notice:1016670(env apply only)→ d541ebb で 293 deploy 時 image rebuild | ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1 | 19:35 JST |
| 290-QA Pack A | OBSERVED_OK | yoshilover-fetcher:c14e269 / 00176-vnk | ENABLE_WEAK_TITLE_RESCUE 未設定維持(default OFF) | 20:40 JST |
| 293-COST | **OBSERVED_OK_SHORT**(FULL_EXERCISE_OK 未到達、AI 上限到達中で preflight gate 未 exercise) | yoshilover-fetcher:d541ebb / 00177-qtr + publish-notice:d541ebb | ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1 両 services | 21:00 JST |

## 改修 impl デプロイ直前まで完了(本日 5/1)

| 改修 | commit | pytest | env knob(default OFF)| 状態 |
|---|---|---|---|---|
| #1 cache_hit split metric | `e7e656c`(Claude fallback) | focused 27/0 + full 2020/3(out-of-scope 既存 fail 3) | ENABLE_CACHE_HIT_SPLIT_METRIC | デプロイ直前まで |
| #2 cache miss circuit breaker | `91ddfdf`(Codex 直接、push 済) | focused 33 passed + 29 subtests passed | ENABLE_GEMINI_CACHE_MISS_BREAKER + threshold/window envs | デプロイ直前まで |
| #6 cap=10 class reserve | `f31cf21`(Codex 直接、push 済) | 2029/0 + targeted 65 pass | ENABLE_PUBLISH_NOTICE_CLASS_RESERVE / *_REAL_REVIEW / *_POST_GEN_VALIDATE / *_ERROR | デプロイ直前まで |

## 設計 / 観測準備 完了(本日 5/1、doc-only)

| item | commit | 内容 |
|---|---|---|
| 300-COST read-only test plan | `7b38386`(Codex 直接、push 済) | impl 便 fire 用 contract 補強、276 行 |
| 293-COST FULL_EXERCISE 観測 runbook | `deea95d` | 5/2 朝 read-only verify task 6 件 + 判定 criteria + rollback path |
| Lane A round 29 v2 / Lane B round 18 v2 receipts | `deea95d` | POLICY §13.6 引継ぎ |
| POLICY §18.6 状態遷移必須報告 | `deea95d` | Decision Batch 必須化、無報告禁止 |
| OPS_BOARD 矛盾清書 | `54669ae` | 290 Pack A OBSERVED_OK / 293 OBSERVED_OK_SHORT / 282 HOLD blocker |

## Codex Lane 状態(現在)

### Lane A(idle、HOLD reason explicit)

- status: **idle**
- last_round: round 30 completed(`bg04licmm` wrapper、改修 #2 cache miss circuit breaker impl、commit `91ddfdf` push 済)
- HOLD reason: 282-COST HOLD 維持 + 293 FULL_EXERCISE 待ちで dev 便 並列投入は production verify 期間中の混入リスク回避、5/2 朝 後に sequential 再開
- next_dispatch_候補: 改修 #3 per-post 24h Gemini budget impl(POLICY §19.7 #3、design proposal 段階)/ 改修 #4 prompt-id cost review gate(doc 反映で完結可能)/ 改修 #5 old_candidate ledger TTL impl

### Lane B(idle、HOLD reason explicit)

- status: **idle**
- last_round: round 19 completed(同 wrapper、300-COST read-only test plan、commit `7b38386` push 済)
- HOLD reason: 同上 + scope disjoint な dev 便なし(改修 #2 / 290 Pack B / 288 source 候補 全 user GO 待ち or 完了待ち)
- next_dispatch_候補: 290 Pack B readiness audit(read-only)/ 288-INGEST source 候補調査(read-only)/ 改修 #5 ledger TTL impl

## §14 mail monitor 並走

- 直近(12:25-12:35 UTC = 21:25-21:35 JST)sent 1/2/2、errors 0、suppressed 0、rolling 1h 8 mails(MAIL_BUDGET 30 余裕)
- §14 P0/P1 自律 rollback monitor 24h 継続(298-v4 + 290 Pack A + 293-COST 重ね)、storm pattern 不在

## HOLD 維持(user 明示、本日 21 時台 directive)

- **282-COST ENABLE_GEMINI_PREFLIGHT=1**:293 FULL_EXERCISE_OK 待ち(5/2 朝 AI 上限 reset 後 fetcher run で preflight gate exercise + publish-notice 通知発生 + Gemini delta 測定 完了後)
- **290-QA Pack B ENABLE_WEAK_TITLE_RESCUE=1**:Pack A 1 週間 OBSERVED_OK 後
- **288-INGEST Phase 3 source 追加**:298 + 293/282 完了後、Phase 1-2 順次
- **Gemini call 増加 / mail 量増加 / publish-review-hold-skip 基準変更 deploy** 全禁止

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
| 29 v1 | 改修 #1 cache_hit split metric impl(290 deploy 中 kill + stash) | `b8h77qcj2`(wrapper) | (killed) | killed |
| 29 v2 | 改修 #1 cache_hit split metric impl 再 fire | `bhbektxze`(wrapper) | `e7e656c`(Claude fallback) | done |
| 30 | 改修 #2 cache miss circuit breaker impl | `bg04licmm`(wrapper) | `91ddfdf`(Codex 直接) | done |

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
| 18 v1 | 改修 #6 cap=10 class reserve impl(290 deploy 中 kill + stash) | `b8h77qcj2`(wrapper) | (killed) | killed |
| 18 v2 | 改修 #6 cap=10 class reserve impl 再 fire | `bhbektxze`(wrapper) | `f31cf21`(Codex 直接) | done |
| 19 | 300-COST read-only test plan | `bg04licmm`(wrapper) | `7b38386`(Codex 直接) | done |

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
