You are Codex (Lane B round 10, doc-only). 293-COST design v2 doc numbering update.

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
293-COST design v2 doc 内 POLICY §6/18/22 reference を新 POLICY 12 sections numbering に整合化(消化順 2 subtask、user reset 後 docs/ops/POLICY.md は 12 sections に simplified、私の補強 §8-§11 で書いた "POLICY §18 Pack 18 項目" / "POLICY §22 MAIL_BUDGET" 等の reference は新 POLICY と numbering ずれ、明日朝 user 提示時の混乱回避)

参照:
- 新 POLICY: docs/ops/POLICY.md(12 sections、user reset 永続化 ff05412)
- 旧 POLICY 参照箇所:docs/handoff/codex_responses/2026-05-01_293_COST_design_v2.md §8-§11(Claude 補強分、私が書いた "POLICY §18" / "POLICY §22" 等)
- 293-COST Pack final review: docs/handoff/codex_responses/2026-05-01_293_COST_pack_final_review.md(commit 856dd59、numbering ずれ指摘済)

[goal]
docs/handoff/codex_responses/2026-05-01_293_COST_pack_v2_numbering_correction.md(NEW)を作成。

含むもの:
1. **新 POLICY 12 sections mapping**:
   - 旧 POLICY §6/§18/§22 → 新 POLICY §1-12 のどれに対応するか mapping 表
   - 例:旧 §18 (Acceptance Pack 18 項目) → 新 §9 (Acceptance Pack Requirement) + ACCEPTANCE_PACK_TEMPLATE.md 13 fields
   - 例:旧 §22 (MAIL_BUDGET) → 新 §7 (Mail Storm Rules)
2. **293-COST design v2 §8-§11 内の修正必要箇所**:
   - "POLICY §18 18 項目" → "ACCEPTANCE_PACK_TEMPLATE 13 fields(+298 additional)"
   - "POLICY §22 MAIL_BUDGET" → "POLICY §7 Mail Storm Rules"
   - "POLICY §7 順序固定" → numbering 整合 verify
3. **修正適用方針**:
   - design v2 自体は historical artifact、修正不要
   - 明日朝 user 提示時に Claude が Decision Batch 圧縮で適切な新 POLICY 参照に置換
   - 本 doc は cross-reference として残置

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止
- 既存 design v2 / final review doc 修正禁止(別 file 新規 numbering correction)
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff
- 新規 ticket 起票禁止(既存 293-COST 配下 subtask)

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_293_COST_pack_v2_numbering_correction.md]
- commit_hash: <sha>
- mapping_count: <X mappings created>
- next_action_for_claude: "明日朝 user 提示時 design v2 §18/§22 参照を新 POLICY mapping で読替"
