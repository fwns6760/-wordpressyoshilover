# Lane A round 13 prompt: 293-COST READY 化

You are Codex (Lane A round 13, doc-only / read-only). 293-COST impl 判断 Pack を READY 化(user 即返答可能 1 page final consolidation).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
293-COST preflight skip visible 化(消化順 順 1、新 OPS_BOARD ACTIVE entry、READY 化 = Pack 完成 + user 即返答可能 + new READY 配下移動候補)

参照(既存 commit 着地済):
- design v2: docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md(30c8204 + Claude 補強 7f2f3e9)
- final review: docs/handoff/codex_responses/2026-05-01_293_COST_pack_final_review.md(856dd59、13/13、UNKNOWN 0)
- numbering correction: docs/handoff/codex_responses/2026-05-01_293_COST_pack_v2_numbering_correction.md(6ddff7c、3 mappings)
- Pack consistency review v2: docs/handoff/codex_responses/2026-05-01_pack_consistency_review_v2.md(0ae5505)
- 新 ACCEPTANCE_PACK_TEMPLATE.md(13 fields format)
- 新 POLICY.md §1-12(numbering 整合)

[goal]
docs/handoff/codex_responses/2026-05-01_293_COST_ready_pack.md(NEW)を作成。

含むもの(user 即返答可能 1 page、READY 配下移動候補):
1. **Conclusion**: GO 推奨 if 293 impl + test + commit + push を進めるか / HOLD if precondition 未達
2. **Scope**:
   - src/publish_notice_scanner.py + src/cloud_run_persistence.py + src/rss_fetcher.py + src/gemini_preflight_gate.py
   - new env 3 (default OFF):ENABLE_PREFLIGHT_SKIP_NOTIFICATION / PREFLIGHT_SKIP_LEDGER_PATH / PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS
   - tests/test_preflight_skip_notification.py 新規 + 既存 test 維持
3. **Non-Scope**:
   - 282-COST flag ON
   - Gemini call 増加(本 ticket は scanner / persistence / ledger touch のみ)
   - Scheduler / SEO / Team Shiny / Source 追加 / WP REST mutation / image rebuild + deploy(本 ticket = impl + test + commit + push まで、deploy 別 Pack)
4. **Implementation Order**(commit 分割 4):
   - commit 1: ledger schema + persistence scaffold(src/cloud_run_persistence.py + tests)
   - commit 2: scanner parallel path(src/publish_notice_scanner.py + tests + 新規 test file)
   - commit 3: rss_fetcher + gemini_preflight_gate skip_layer 出力
   - commit 4: tests 7 cases 全部
5. **Test Plan**(7 cases):
   - case 1: fetcher が flag ON 時 preflight ledger row を書く
   - case 2: scanner が flag ON 時 mail request emit
   - case 3: flag OFF 時 silent skip 0
   - case 4: 24h dedupe window
   - case 5: 8 reason label mapping(table-driven)
   - case 6: post_gen_validate path 維持(289 不変)
   - case 7: persistence entrypoint download/upload
6. **Rollback Plan**(Phase A/B/C):
   - Phase A: env remove(`--remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION`)~30 sec
   - Phase B: image rollback(publish-notice 旧 SHA)~2-3 min
   - Phase C: GCS state cleanup(`preflight_skip_history.jsonl` archive)
7. **18 fields YES/NO/UNKNOWN**(POLICY §11 + ACCEPTANCE_PACK 13 fields + 5 必須):
   - Gemini call increase: NO(scanner / persistence / ledger touch のみ)
   - Token increase: NO
   - Candidate disappearance risk: NO(silent skip 防止が目的、disappearance 逆方向)
   - Cache impact: NO(Gemini cache 無関係)
   - Mail volume impact: YES(282 flag ON 後に新 mail 経路出現、本 ticket 自身は flag OFF で 0)
8. **Stop Condition**:
   - 289 emit 減少
   - Team Shiny 変
   - silent skip 増(POLICY §8 違反)
   - Gemini call 増(本 ticket 経由でなく)
   - cap=10 / 24h dedup 違反
   - MAIL_BUDGET 違反
9. **Preconditions**:
   - 298-Phase3 ROLLED_BACK 安定確認(本日 17:00 observe pass)
   - 17:00 production_health_observe 異常 0(本日 silent skip 0 確認済)
   - Codex 上限超過解消(明日朝以降の Codex 余力)
10. **User Reply**:`GO` / `HOLD` / `REJECT`(1 行)

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止
- 既存 design v2 / final review / numbering / consistency v2 doc 修正禁止(別 file 新規 ready_pack)
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff
- DO NOT install packages

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_293_COST_ready_pack.md]
- commit_hash: <sha>
- ready_status: ready_for_user_go (precondition 全 YES) | hold (precondition 1 件以上 NO)
- next_action_for_claude: "293-COST READY 化、user GO 提示は impl + test + commit + push の判断"
