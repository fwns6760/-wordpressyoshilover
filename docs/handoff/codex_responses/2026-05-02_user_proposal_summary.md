# 2026-05-02 user proposal summary

作成: 2026-05-01 JST  
用途: 2026-05-02 06:00 JST user 提示用 1 page / Decision Batch 1 画面圧縮  
新規 ticket: なし

## 1. 本日 close 状態

- **P1 mail storm contained / 全 Pack 完成 / 17:00 observe pass。明日朝 user に上げるのは `298-Phase3 v4 Case A` 1 件のみ。**

Reference map:

- `298`: [2026-05-01_298_Phase3_v4_second_wave_pack.md](2026-05-01_298_Phase3_v4_second_wave_pack.md) `cdd0c3f`, [2026-05-01_298_phase3_v4_alignment_review.md](2026-05-01_298_phase3_v4_alignment_review.md) `9d5620e`, [2026-05-01_298_phase3_v4_unknown_close.md](2026-05-01_298_phase3_v4_unknown_close.md) `cf86e88`, [2026-05-01_298_Phase3_stability_evidence_pre.md](2026-05-01_298_Phase3_stability_evidence_pre.md) `aa6a8eb`
- `299`: [2026-05-01_299_QA_flaky_analysis.md](2026-05-01_299_QA_flaky_analysis.md) `b2e1a48`, [2026-05-01_299_QA_n2_evidence.md](2026-05-01_299_QA_n2_evidence.md) `60242be`
- `consistency / unknown`: [2026-05-01_pack_consistency_review.md](2026-05-01_pack_consistency_review.md) `908b081`, [2026-05-01_unknown_flags_resolution.md](2026-05-01_unknown_flags_resolution.md) `ade62fb`

## 2. 明日朝の提示候補(Decision Batch 1)

### 298-Phase3 v4 Case A 第二波対策 Pack

- **結論**: **GO 推奨 if all preconditions met / HOLD if any precondition unmet**
- **理由 1**: `2026-05-02 09:00 JST` 前後の 24h dedup expiry で、既知 `99` 件の old-candidate second wave が再送される risk が残っている。
- **理由 2**: Case A は `99 -> 0` を狙う最小 blast-radius 案で、`real review` / `289 post_gen_validate` / `Team Shiny` / `cap=10` / Gemini path を維持したまま second wave だけを潰せる。
- **理由 3**: `alignment 9/9`、rollback 3-tier、remain-active evidence は bundle 済みで、明朝 user 判断に必要な Pack 面は揃っている。
- **GO 前提条件**: `298` current observe が green 維持、Case A suppress/test/build evidence が揃う、`MAIL_BUDGET` breach なし、`real review` / `289` / error path 不変。
- **rollback**: `env remove -> image revert -> ledger archive restore` の 3-tier で即停止可能。
- **stop condition**: `real review` 減 / `289` 減 / error path 低下 / silent skip 増 / repeated old-candidate 再出現 / `MAIL_BUDGET 30/h or 100/d` breach で即 stop。
- **mail volume**: 対策前 risk は `99 mails / ~50 min = 118.8/h`, `99/100 per day`。Case A target は second wave `99 -> 0`。
- **Gemini delta**: `0` 想定。Case A は publish-notice / ledger 側で、fetcher/Gemini call path は触らない。
- **user 返答**: `GO` / `HOLD` / `REJECT`
- **refs**: `298` bundle 4 docs + `908b081` consistency review

## 3. Deferred(明日朝は提示しない)

- `290-QA`: `298` 安定 + `24h` 後。fetcher rebuild + `ENABLE_WEAK_TITLE_RESCUE=1` は次便候補。[pack](2026-05-01_290_QA_pack_draft.md) `65c09c1`, [supplement](2026-05-01_290_QA_pack_supplement.md) `d089340`
- `293-COST impl`: `298` 安定後、`299-QA`/observe/budget reset を満たしてから独立 deploy 候補。[design v2](2026-05-01_293_COST_design_v2.md) `30c8204`, `7f2f3e9`, [final review](2026-05-01_293_COST_pack_final_review.md) `856dd59`
- `282-COST`: `293` 完遂 + `24h` 安定後。flag ON judgment は Pack 完成済みだが順序未達。[pack](2026-05-01_282_COST_pack_draft.md) `1fd2755`, [supplement](2026-05-01_282_COST_pack_supplement.md) `925003d`
- `300-COST`: `298` 安定 + `24h` 後。`290` と graph 並列だが same-day multi-pack 提示は避ける。[source analysis](2026-05-01_300_COST_source_analysis.md) `7a946a8`, [pack](2026-05-01_300_COST_pack_draft.md) `54c2355`, [supplement](2026-05-01_300_COST_pack_supplement.md) `c959327`
- `288-INGEST`: 5 条件全 YES 後。`289 / 290 / 295 / 291 / 282-293` chain 未達のため HOLD 維持。[pack](2026-05-01_288_INGEST_pack_draft.md) `26ede3a`, [supplement](2026-05-01_288_INGEST_pack_supplement.md) `5f8b966`
- `278-280-MERGED`: `290 deploy + 24h` 後。phase 1-3 統合 pack は完成済みだが timing 早すぎ。 [pack](2026-05-01_278_280_merged_pack_draft.md) `0521a25`, [supplement](2026-05-01_278_280_merged_pack_supplement.md) `a9ab8b6`
- `295-QA`: impl 未。まず設計 doc から起草、明日朝の user prompt には出さない。`doc/active/295-QA-subtype-evaluator-misclassify-fix.md`
- `postgame_strict` 緩和: separate ticket 候補のまま据え置き。明日朝は新規 ticket を増やさない

## 4. 明日以降の deploy 順序提案

1. `298-Phase3 v4` second-wave Case A を `2026-05-02` 朝の first decision とする
2. `293-COST impl` は `298` 安定後の独立 deploy 候補
3. `290-QA` は `298` 安定 `24h` 後
4. `282-COST` は `293` 完遂後
5. `300-COST` は `298` 安定 `24h` 後、graph 上は `290` と並列
6. `278-280-MERGED` は `290 deploy + 24h` 後
7. `288-INGEST` は 5 条件達成後の最終 leaf

運用原則:

- `1 day / 1 user decision / 1 main pack`
- `publish-notice` 変更と別 mail-routing change を同日に束ねない
- `yoshilover-fetcher` 側も one moving part per observe window を維持する
