# Lane B round 14 prompt: 298-Phase3 v4 Pack robustness 補強

You are Codex (Lane B round 14, doc-only / read-only). 298-Phase3 v4 Pack 最終補強(第二波 cardinality / rollback robustness / stop condition automation 提案).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
298-Phase3 v4 Pack robustness 補強(消化順 順 1 subtask、新 OPS_BOARD HOLD_NEEDS_PACK 配下、明日朝 user 提示前 final robustness 検証、新規 ticket なし)

参照(全 commit 着地済):
- v4 Pack: docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_second_wave_pack.md(cdd0c3f、Case A 推奨)
- alignment review: 9d5620e
- UNKNOWN close: cf86e88
- final READY pack: docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_final_ready_pack.md(fac5517、9/9 alignment)
- INCIDENT_LIBRARY: 4abe1d5(本日 P1 mail storm 経緯)
- 298 stability evidence pre: aa6a8eb
- 直近 publish-notice / fetcher logs(read-only、本日 storm 終息確認)

[goal]
docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_robustness_supplement.md(NEW)を作成。

含むもの(明日朝 user 提示前 final robustness 検証、新規 ticket なし):
1. **第二波 cardinality 再 estimate**(read-only、最新 ledger sample):
   - 5/1 朝 storm group 63003-63311 の unique post_id 確定数(99 ± N)
   - 5/1 12:35 first emit group 61938-62940 の unique post_id 確定数
   - 直近 6h で追加された backlog_only post 数(scanner skip 経路)
   - 5/2 09:00 JST 想定 cardinality:99 + 6h 追加分 = 100-110 件 想定
   - MAIL_BUDGET 100/d ギリギリ違反 risk
2. **rollback Phase D(手動 fallback)** 追加:
   - Phase A(env remove)/ Phase B(image revert):既存
   - Phase C(ledger archive):既存
   - **Phase D 新規**:Codex sandbox auth fail / Cloud Run mutation 不能時の手動 fallback
     - manual gcloud cli 実行手順
     - Cloud Console UI 操作手順
     - emergency contact / escalation path
3. **stop condition automation 提案**(POLICY §13 新規 candidate):
   - MAIL_BUDGET 30/h / 100/d 違反 自動検出 logic 提案
   - silent skip 増加 自動検出 logic
   - alert 経路(現状 Claude 単独監視 → 将来自動 alert への移行 design)
   - ※ 本提案は「設計」、impl は別 ticket、本日 着手 0
4. **Case A vs Case D vs Case F 再比較**:
   - Case A(ledger seed mode):推奨、user 提示時の primary
   - Case D(backlog_only mute):fallback option(real review path も止まる、緊急時)
   - Case F(GCS pre-seed):fallback option(flag OFF 中の seed、明日朝以外で活用)
   - 各 Case の trade-off 明示 + 推奨選択順序
5. **明日朝 06:00 JST 提示時の 1 行 final**:
   - 結論行 final candidate(GO 推奨 with case A)
   - 理由 1-3 行(第二波 risk OPEN / Pack 9/9 alignment / rollback 3-tier+D 確立)
   - user 返答:GO / HOLD / REJECT のみ
6. **Pack 13/13 + 9/9 alignment 維持確認**:
   - 既存 v4 Pack の項目 update 不要、本 robustness doc は独立 supplement

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止(gcloud logging read / describe / gsutil cat はOK)
- 既存 v4 Pack / alignment / UNKNOWN close / final READY pack 修正禁止(別 file 新規 robustness supplement)
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff
- DO NOT install packages
- 新規 ticket 起票なし(stop condition automation 提案は「設計のみ」、impl 起票は明日以降の別 ticket 候補)

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_robustness_supplement.md]
- commit_hash: <sha>
- robustness_items: [cardinality re-estimate / rollback Phase D / stop condition automation / Case 再比較 / 明日朝 1 行 final]
- next_action_for_claude: "298-Phase3 v4 robustness 補強完了、明日朝 06:00 JST user 1 行提示用 final"
