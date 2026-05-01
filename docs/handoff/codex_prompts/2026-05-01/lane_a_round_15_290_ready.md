# Lane A round 15 prompt: 290-QA READY 化

You are Codex (Lane A round 15, doc-only / read-only). 290-QA weak title rescue deploy 判断 Pack を READY 化(user 即返答可能 1 page).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
290-QA weak title rescue deploy 判断(消化順 順 3、新 OPS_BOARD FUTURE_USER_GO entry、READY 化)

参照(既存 commit 着地済):
- Pack draft: docs/handoff/codex_responses/2026-05-01_290_QA_pack_draft.md(65c09c1)
- Pack supplement: docs/handoff/codex_responses/2026-05-01_290_QA_pack_supplement.md(d089340、13/13)
- 既存 impl: commit c14e269 既 push、ENABLE_WEAK_TITLE_RESCUE 未設定で live-inert
- Pack consistency review v2: 0ae5505

[goal]
docs/handoff/codex_responses/2026-05-01_290_QA_ready_pack.md(NEW)を作成。

含むもの(user 即返答可能 1 page):
1. **Conclusion**: HOLD(298-Phase3 ROLLED_BACK 後 24h 安定 + 17:00 observe pass 待ち) / GO 推奨は precondition 全 YES 後
2. **Scope**: yoshilover-fetcher service image rebuild(c14e269 included)+ env `ENABLE_WEAK_TITLE_RESCUE=1` apply
3. **Non-Scope**: publish-notice / guarded-publish / Scheduler / SEO / Team Shiny From / 290 以外の ticket
4. **Implementation Order**:
   - step 1: clean build(POLICY §8 / git stash -u or /tmp clean export)
   - step 2: HOLD 混入なし verify(`git log <prev_image>..<new_image>` で他 HOLD ticket 0 確認)
   - step 3: image rebuild + service update(yoshilover-fetcher 旧 :4be818d → 新 SHA)
   - step 4: env apply `ENABLE_WEAK_TITLE_RESCUE=1`
   - step 5: 1-2 trigger 観察(救済 candidate ledger emit / 289 不変 / Team Shiny / Gemini 0)
5. **Test Plan**:
   - precondition: 298-Phase3 24h 安定 / 17:00 observe pass / pytest baseline +0 regression
   - flag ON 後 verify: A/B 群 7 候補(泉口/山崎+西舘/阿部/平山関連 3/竹丸+内海)救済 emit 確認
   - regression: title regression なし(weak title rescue → strict validation 通過率 ↑)
6. **Rollback Plan**(Phase A/B):
   - Phase A: env remove(`gcloud run services update yoshilover-fetcher --remove-env-vars=ENABLE_WEAK_TITLE_RESCUE`)~30 sec
   - Phase B: image rollback(yoshilover-fetcher :4be818d 旧 SHA)~2-3 min
7. **18 fields YES/NO/UNKNOWN**:
   - Gemini call increase: NO(regex/metadata only、Gemini 呼び出し 0)
   - Token increase: NO
   - Candidate disappearance risk: NO(逆方向、disappearance 減少)
   - Cache impact: NO(rescue path = scanner 経由でなく fetcher 経由、cache 無関係)
   - Mail volume impact: YES(微増、救済 candidate ledger emit)
8. **Stop Condition**:
   - silent skip 増加(POLICY §8 違反)
   - Gemini call delta > 0
   - Team Shiny 変化
   - 救済 fail / title regression 検出
   - 289 emit 減少
   - publish 急減
9. **Preconditions**:
   - 298-Phase3 ROLLED_BACK 後 24h 安定確認
   - 17:00 production_health_observe pass(本日確認済)
   - 299-QA flaky/transient 整理 (cache/process-history 由来確定)
   - clean build prep + HOLD 混入なし verify
   - rollback target image SHA 確認(:4be818d)
   - pytest baseline +0 regression
10. **User Reply**:`GO` / `HOLD` / `REJECT`

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止
- 既存 290 Pack draft / supplement 修正禁止(別 file 新規 ready_pack)
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff
- DO NOT install packages

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_290_QA_ready_pack.md]
- commit_hash: <sha>
- ready_status: ready_for_user_go (precondition 全 YES) | hold (precondition 1 件以上 NO)
- next_action_for_claude: "290-QA READY 化、user GO 提示は 298 安定 + 24h 後"
