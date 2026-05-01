# Lane B round 13 prompt: 300-COST READY pack 化(READY_FOR_IMPL 目指す)

You are Codex (Lane B round 13, doc-only / read-only). 300-COST READY pack 化(290/282/288 と同 pattern、user 即返答可能 1 page).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
300-COST source-side guarded-publish 再評価 cost reduction(消化順 順 6、新 OPS_BOARD ACTIVE entry、READY_FOR_IMPL 目指す)

参照(全 commit 着地済):
- source 解析 v1: docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis.md(7a946a8)
- Pack draft: docs/handoff/codex_responses/2026-05-01_300_COST_pack_draft.md(54c2355)
- Pack supplement: docs/handoff/codex_responses/2026-05-01_300_COST_pack_supplement.md(c959327)
- source 解析 v2: docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis_v2.md(ead78a3)
- 新 ACCEPTANCE_PACK_TEMPLATE.md(13 fields)

[goal]
docs/handoff/codex_responses/2026-05-01_300_COST_ready_pack.md(NEW)を作成。
290/282/288 ready pack と同 pattern、user 即返答可能 1 page、READY_FOR_IMPL 状態 = impl 順序 / blast radius / cost impact / mail impact / rollback 案 全部整理。

含むもの(user 即返答可能 1 page):
1. **Conclusion**: HOLD(298 安定 + 24h 後 impl 起票) / GO 推奨は precondition 全 YES 後
2. **Scope**: src/guarded_publish_runner.py 変更(Option C-narrow:status / judgment / hold_reason 全部前回 record と同じなら ts 再 append しない)+ env 1 個追加
3. **Non-Scope**: 298-Phase3 / 293 / 282 / 290 / 288 / Scheduler / SEO / Team Shiny / WP REST mutation
4. **Implementation Order**(commit 分割 4):
   - commit 1: env scaffold + idempotent helper
   - commit 2: backlog_only unchanged 判定 logic
   - commit 3: tests 5 cases
   - commit 4: docstring + integration verify
5. **Test Plan**(5 cases、source 解析 v2 反映):
   - test 1: backlog_only unchanged → ts 再 append skip
   - test 2: real review unchanged → ts 引き続き append(影響なし)
   - test 3: backlog_only changed(status / judgment / hold_reason 変化)→ ts append
   - test 4: flag OFF 100% 不変
   - test 5: scanner consumer 互換(298 ledger と整合)
6. **Rollback Plan**(Phase A/B/C):
   - Phase A: env 1 コマンド(`gcloud run jobs update guarded-publish --remove-env-vars=ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY`)~30 sec
   - Phase B: image rollback(:6df049c 旧 SHA)~2-3 min
   - Phase C: ledger archive 退避(必要時のみ)
7. **18 fields YES/NO/UNKNOWN**:
   - Gemini call increase: NO
   - Token increase: NO
   - Candidate disappearance risk: NO(unchanged 時のみ skip、新規 publish 機会失わない)
   - Cache impact: NO
   - Mail volume impact: NO(sink-side 不変、source-side cost 削減のみ)
8. **Stop Condition**:
   - 真の review semantics 変化(real review unchanged が ts append 失う)
   - silent skip 増加(POLICY §8 違反)
   - mail 通知 path 影響
   - cap=10 / 24h dedup 違反
   - GCS write 削減効果なし(Option C-narrow logic 失敗)
9. **Preconditions**:
   - 298-Phase3 ROLLED_BACK 後 24h 安定確認
   - 17:00 production_health_observe pass
   - source v2 解析 evidence(28800 → 数百 rows/day 想定)
   - Cloud Run execution count/day=288 / GCS upload count/day=288 は別 ticket(persistence whole-file upload skip)
10. **User Reply**:`GO` / `HOLD` / `REJECT`

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止
- 既存 source 解析 v1/v2 / Pack / supplement 修正禁止(別 file 新規 ready_pack)
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff
- DO NOT install packages

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_300_COST_ready_pack.md]
- commit_hash: <sha>
- ready_status: ready_pending_298 (298 安定 + 24h 後 impl 起票) | hold
- next_action_for_claude: "300-COST READY 化、impl 起票は 298 安定 + 24h 後"
