# Lane A round 16 prompt: 288-INGEST READY 化

You are Codex (Lane A round 16, doc-only / read-only). 288-INGEST source 追加判断 Pack を READY 化(user 即返答可能 1 page).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
288-INGEST source 追加判断(消化順 順 5、新 OPS_BOARD FUTURE_USER_GO entry、5 条件 precondition、READY 化)

参照(既存 commit 着地済):
- Pack draft: docs/handoff/codex_responses/2026-05-01_288_INGEST_pack_draft.md(26ede3a)
- Pack supplement: docs/handoff/codex_responses/2026-05-01_288_INGEST_pack_supplement.md(5f8b966、13/13)
- Pack consistency review v2: 0ae5505
- 新 OPS_BOARD `future_user_go.288-INGEST`(blocked_by: candidate visibility contract / mail impact estimate / Gemini cost estimate)

[goal]
docs/handoff/codex_responses/2026-05-01_288_INGEST_ready_pack.md(NEW)を作成。

含むもの(user 即返答可能 1 page):
1. **Conclusion**: HOLD(5 条件 precondition 全達成待ち) / GO 推奨は 5 条件全 YES 後
2. **Scope**: config/rss_sources.json に新 RSS endpoint 追加(候補:NNN / スポニチ web / サンスポ web 等)+ image rebuild + service update
3. **Non-Scope**: scanner / persistence / ledger / publish-notice / guarded-publish / Scheduler / SEO / Team Shiny
4. **Implementation Order**:
   - step 1: 候補 source list 確定(NNN / スポニチ web / サンスポ web)
   - step 2: config/rss_sources.json 編集
   - step 3: image rebuild + fetcher service update
   - step 4: 24h 観察(article 数 / mail emit / Gemini call delta)
5. **Test Plan**:
   - precondition test: 5 条件全 YES 確認
   - 新 source per-article fetch + Gemini call delta 計測
   - dedup mechanism(source_url_hash / title hash)で衝突なし verify
   - 候補消失契約 verify(既存 source の publish 機会減らない)
6. **Rollback Plan**:
   - Phase A: config revert(`git revert <commit>` で source 削除)+ image rebuild + service update
   - Phase B: 完全 image rollback(yoshilover-fetcher 旧 :4be818d)
   - Phase C: 新 source 由来 cache / ledger archive 退避
7. **18 fields YES/NO/UNKNOWN**:
   - Gemini call increase: **YES**(新 source per-article × call site、定量予測必須、UNKNOWN なら HOLD)
   - Token increase: YES(同上)
   - Candidate disappearance risk: NO(候補消失契約で禁止、dedup mechanism で衝突回避)
   - Cache impact: 要評価(新 source の cache_hit ratio 影響、UNKNOWN resolution 必要)
   - Mail volume impact: YES(増加、定量予測必須)
8. **Stop Condition**:
   - Gemini call delta > +30%
   - candidate disappearance 検出
   - silent skip 増加
   - Team Shiny / 289 / errors 通知 path 影響
   - cache_hit ratio 急変
   - MAIL_BUDGET 30/h・100/d 違反
   - publish 急減 / 急増(±50% 以上)
9. **Preconditions(5 条件)**:
   - condition 1: 289 24h 安定(silent skip 0 維持)
   - condition 2: 290-QA deploy + 24h 安定(weak title rescue 効果確認)
   - condition 3: 295-QA impl 完遂(subtype 誤分類 fix)
   - condition 4: 候補消失契約(POLICY §8 silent skip policy 整合、dedup mechanism + WP 側 publish 機会増加方向)
   - condition 5: cost 抑制策(282-COST flag ON 後 24h Gemini delta < +20% 確認)
10. **User Reply**:`GO` / `HOLD` / `REJECT`(1 行、5 条件全 YES 後の Pack 提示)

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止(config/rss_sources.json 不可触)
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止
- 既存 288 Pack draft / supplement 修正禁止(別 file 新規 ready_pack)
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff
- DO NOT install packages

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_288_INGEST_ready_pack.md]
- commit_hash: <sha>
- ready_status: ready_pending_5_conditions (5 条件全達成後 GO 提示可能) | hold (5 条件 1 件以上 NO)
- next_action_for_claude: "288-INGEST READY 化、user GO 提示は 5 条件達成後"
