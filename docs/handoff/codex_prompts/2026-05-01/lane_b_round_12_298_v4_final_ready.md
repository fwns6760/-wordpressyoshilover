# Lane B round 12 prompt: 298-Phase3 v4 final READY pack

You are Codex (Lane B round 12, doc-only / read-only). 298-Phase3 v4 final READY pack(明日朝 5/2 06:00 JST user 提示用 1 page、9/9 alignment + UNKNOWN close 統合).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
298-Phase3 v4 第二波対策(消化順 順 1、新 OPS_BOARD HOLD_NEEDS_PACK entry、ROLLED_BACK_AFTER_REGRESSION、明日朝 user GO 提示候補)

参照(既存 commit 着地済):
- v4 Pack: docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_second_wave_pack.md(cdd0c3f、Case A 推奨)
- alignment review: docs/handoff/codex_responses/2026-05-01_298_phase3_v4_alignment_review.md(9d5620e、6/9 → )
- UNKNOWN close: docs/handoff/codex_responses/2026-05-01_298_phase3_v4_unknown_close.md(cf86e88、9/9 alignment)
- INCIDENT_LIBRARY: 4abe1d5(本日 P1 mail storm 経緯)
- 298 stability evidence pre: aa6a8eb
- Pack consistency review v2: 0ae5505
- 新 ACCEPTANCE_PACK_TEMPLATE.md(13 fields + 298 additional 9 項目)
- 新 OPS_BOARD `hold_needs_pack.298-Phase3` re_on_forbidden_until 8 項目

[goal]
docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_final_ready_pack.md(NEW)を作成。

含むもの(明日朝 06:00 JST user 提示用 1 page):
1. **Conclusion**: GO 推奨(9/9 alignment 達成 + UNKNOWN 0 + 第二波 risk OPEN urgency)/ ただし 298_phase3 second-wave boundary close と Codex fire budget reset 状況により HOLD 候補
2. **Scope**:
   - publish-notice Cloud Run job:
     - image rebuild(commit `ffeba45` impl 内容、clean build POLICY §8)
     - job update with new image
     - flag OFF deploy + 1-2 trigger 観察
     - 条件 OK で flag ON apply(`ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`)+ Case A: ledger seed mode
     - 1-2 trigger 観察 + 5/2 09:00 JST 第二波防止確認
3. **Non-Scope**:
   - Team Shiny / 289 / X / Scheduler / live_update / 290 / 293 / 282 / 300 / 288 / WP REST mutation
   - mail 通知条件 大改修(本日 REJECT)
   - 通知体系 全体再設計(本日 REJECT)
4. **Implementation Order(case A)**:
   - step 1: latest HEAD fresh pytest(failures = 3 pre-existing or 0、+0 increase)
   - step 2: 299-QA evidence(N=2 0/0 確認済、本日 transient 再現で N=3 未達)
   - step 3: clean build(`/tmp/yoshi-deploy-head` clean export)
   - step 4: HOLD-carry verify(`git log <prev>..HEAD --oneline`、c14e269 = 290 live-inert 確認)
   - step 5: rollback target image SHA(`:4be818d`)
   - step 6: image rebuild + job update(env 不変、flag OFF default)
   - step 7: 観察 1-2 trigger(挙動 100% 不変)
   - step 8: 条件 OK で flag ON env apply
   - step 9: 観察 1-2 trigger(old_candidate sent=0 / 通常 path 不変)
   - step 10: 5/2 09:00 JST 第二波防止確認
5. **9/9 alignment 達成項目**(ACCEPTANCE_PACK 298 additional fields):
   - old candidate pool cardinality estimate: ~99 件(63003-63311 + 6h 追加分)
   - expected first-send mail count: ~0 通(Case A = ledger seed mode、emit せず登録のみ)or ~99 通(seed なし first emit)
   - max mails/hour: 30 通(MAIL_BUDGET 内、seed mode で 0 想定)
   - max mails/day: 100 通(同上)
   - stop condition: 9 項目 list 明示
   - rollback command: env 1 コマンド + image revert + ledger archive
   - ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE 不在確認: YES
   - persistent ledger 無効確認: YES
   - normal review / 289 / error mail remain active: YES
6. **18 fields YES/NO/UNKNOWN**:
   - Gemini call increase: NO
   - Token increase: NO
   - Candidate disappearance risk: NO
   - Cache impact: NO
   - Mail volume impact: YES(reduction、第二波 99 通 → 0 想定)
7. **Stop Condition**(POLICY §7 / §8 整合):
   - real review (yellow / cleanup_required / hold) emit 減少
   - Team Shiny From 変化
   - 289 emit 減少
   - errors > 0
   - silent skip 増(POLICY §8 違反)
   - cap=10 / 24h dedup 違反
   - MAIL_BUDGET 30/h・100/d 違反
   - publish-notice 全停止
8. **Preconditions(明日朝 06:00 JST 時点で全 YES 必要)**:
   - 298-Phase3 ROLLED_BACK 後 24h 安定(本日 13:55 → 5/2 13:55 が正確 24h、明日朝 06:00 は 16h 経過)→ **partial、boundary judgment**
   - 17:00 production_health_observe pass(本日確認済 + silent skip 0)
   - 299-QA flaky/transient 整理(本日 N=2 0/0 達成、N=3 transient 再現で本日 close 候補なし、明日 deferred)
   - Codex fire budget 確認(本日 22+ 件 P1 例外、明日 reset 期待)
9. **User Reply**:`GO` / `HOLD` / `REJECT`(1 行、明日朝 06:00 JST 1 行提示)

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止
- 既存 v4 Pack / alignment / UNKNOWN close doc 修正禁止(別 file 新規 final_ready_pack)
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_final_ready_pack.md]
- commit_hash: <sha>
- ready_status: ready_for_user_go (precondition 全 YES 想定) | hold (1 件以上 NO)
- next_action_for_claude: "298-Phase3 v4 final READY pack、明日朝 06:00 JST user 1 行提示"
