# YOSHILOVER WORKER POOL

Codex Lane state(POLICY §13 永続管理、`/tmp` 禁止、4 NO 規律)。
Last updated: 2026-05-01 20:30 JST(両 lane running、改修 #1 / #6 impl 便 並列駆動中、298-v4 24h soak 並走、§14 mail monitor 並走)

## Active Lanes(両 running、改修 impl 便 並列駆動中)

### Lane A round 29(running、改修 #1 cache_hit split metric impl)

- status: **running**
- job_id: `b8h77qcj2`(wrapper bash、内部 codex pid 117934)
- ticket: 改修-29-cache-hit-split-metric(audit 由来、design ready → impl)
- prompt_path: `docs/handoff/codex_prompts/2026-05-01/lane_a_round_29_cache_hit_split_metric.md`
- receipt_path: `docs/handoff/codex_receipts/2026-05-01/lane_a_round_29.md`(完了後 Claude 作成)
- started_at: 2026-05-01 20:23 JST
- expected_output:
  - `src/llm_call_dedupe.py` or equivalent(metric 出力 path、後方互換)
  - `src/gemini_cache.py` or equivalent(cooldown_hit 判定)
  - `tests/test_cache_hit_split_metric.py`(新規)
  - `docs/handoff/codex_responses/2026-05-01_change_29_cache_hit_split_pack_v1.md`(Pack v1)
  - commit + push (Codex sandbox blocker 時 Claude fallback)
- completion_gate:
  - pytest baseline 2018/0 → +N/0 regression なし
  - default OFF env knob(`ENABLE_CACHE_HIT_SPLIT_METRIC` default 0)、挙動 100% 不変
  - Pack v1 13 fields + 10a 7-point + 10b regression scope + 11 3-dim rollback(env / image / **GitHub source revert** 3 dim)+ 12 + 13 全充足
  - commit hash + push verified to origin/master
- HOLD/STOP condition:
  - pytest fail → stop + investigation
  -既存 cache key / dedupe logic に挙動変化検出 → stop
  - publish-notice / mail path に何か触ってる → stop(scope 違反)
- POLICY classification: CLAUDE_AUTO_GO 候補(impl + test + push まで)、image rebuild + flag ON は USER_DECISION_REQUIRED 別 phase
- expected completion: ~30-40 min(20:55 JST 頃)

### Lane B round 18(running、改修 #6 cap=10 class reserve impl)

- status: **running**
- job_id: `b8h77qcj2`(wrapper bash 同一、内部 codex pid 118203)
- ticket: 改修-30-cap10-class-reserve(audit 由来、design ready → impl)
- prompt_path: `docs/handoff/codex_prompts/2026-05-01/lane_b_round_18_cap10_class_reserve.md`
- receipt_path: `docs/handoff/codex_receipts/2026-05-01/lane_b_round_18.md`(完了後 Claude 作成)
- started_at: 2026-05-01 20:23 JST
- expected_output:
  - `src/publish_notice_scanner.py`(cap allocation logic 改修)
  - `tests/test_publish_notice_scanner_class_reserve.py`(新規)
  - `docs/handoff/codex_responses/2026-05-01_change_30_cap10_class_reserve_pack_v1.md`(Pack v1)
  - commit + push (Codex sandbox blocker 時 Claude fallback)
- completion_gate:
  - pytest baseline 2018/0 → +N/0 regression なし
  - default OFF env knob(`ENABLE_PUBLISH_NOTICE_CLASS_RESERVE` default 0)、cap=10 全体上限不変、priority order 維持
  - Pack v1 13 fields + 10a + 10b + 11 3-dim rollback(env / image / **GitHub source revert** 3 dim)+ 12 + 13 全充足
  - commit hash + push verified to origin/master
- HOLD/STOP condition:
  - pytest fail → stop
  - cap=10 全体上限変動検出 → stop(POLICY §7 違反)
  - 298-v4 観察期間中 publish-notice 実 production 挙動への影響 → stop(default OFF だが念のため)
  - existing 24h dedup / permanent_dedup ledger に touching → stop(298-v4 entanglement 防止)
- POLICY classification: CLAUDE_AUTO_GO 候補(impl + test + push まで、default OFF 維持で挙動不変)
- expected completion: ~30-40 min(20:55 JST 頃)
- 注: 298-v4 24h soak 中、publish-notice 系 src 改修だが default OFF flag で観察非干渉、commit landed + push 後 src 静的反映のみ、production runtime は flag enable まで不変

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

## Lane History(本日 round 28 までの記録)

## Lane History(本日 round 1-12 全部、commit hash 着地済)

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
