# Lane B round 11 prompt: 300-COST source-side 解析 v2

You are Codex (Lane B round 11, doc-only / read-only). 300-COST source-side guarded-publish 再評価 解析 v2(old backlog pool / mail storm 再発条件 / candidate disappearance / cost 影響 細部 deeper analysis).

Working directory: /home/fwns6/code/wordpressyoshilover

[ticket]
300-COST source-side reevaluation cost(消化順 順 4、新 OPS_BOARD ACTIVE entry、impl HOLD、本 ticket は read-only 解析 v2 + Pack 補強 evidence)

参照(既存 commit 着地済):
- source 解析 v1: docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis.md(7a946a8)
- Pack draft: docs/handoff/codex_responses/2026-05-01_300_COST_pack_draft.md(54c2355)
- Pack supplement: docs/handoff/codex_responses/2026-05-01_300_COST_pack_supplement.md(c959327)
- INCIDENT_LIBRARY: docs/ops/INCIDENT_LIBRARY.md(本日 P1 mail storm 経緯反映 4abe1d5)
- 新 OPS_BOARD `active.300-COST`(allowed: read-only / cost / test plan / rollback、forbidden: impl / deploy / source 動作変更)

[goal]
docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis_v2.md(NEW)を作成。

含むもの(read-only deeper analysis、impl 着手 0):
1. **old backlog pool 数値解析**(直近 24h log + ledger sample):
   - hold_reason=backlog_only entries の unique post_id 数
   - 24h 平均 increase rate(/ day)
   - 24h decrease rate(publish 化される post の比率)
   - net pool growth(明日朝 5/2 09:00 JST 想定 cardinality 補強)
2. **mail storm 再発条件 mathematical model**:
   - cap=10 / trigger × N trigger / 24h × pool size = storm 規模式
   - 24h dedup expire timing(post_id 単位 24h、最初 emit から 24h 後)
   - flag ON 効果(permanent ledger で post_id 永続 dedup)
   - flag OFF + dedup expire = recurrent storm 必然性
3. **candidate disappearance 詳細**:
   - guarded-publish */5 trigger ごとの skip 評価で publish 機会失う pattern
   - WP 上で「review」状態のまま 24h+ 経過 = 実質 publish 機会喪失
   - source-side fix(Option C)が disappearance 減らすか、変わらないか、増やすかの 3 択評価
4. **cost 影響 quantitative**:
   - GCS write delta(28800 rows/day → 想定 N rows/day with Option C)
   - Cloud Run job execution count(scheduler */5 = 288/day、source-side fix では削減不能)
   - Cloud Run job duration(re-evaluation logic 削減で μs 単位 短縮、無視可能)
   - 別 ticket(persistence whole-file upload skip)候補 = `bin/guarded_publish_entrypoint.sh` の whole-file upload 削減
5. **既存 supplement (c959327) との差分明示**:
   - supplement で「mail volume impact = NO」確定
   - 本 v2 で「Cloud Run execution / GCS upload count は別 ticket」明示
   - candidate disappearance「unchanged 時のみ skip」の test 5 cases 細部
6. **POLICY §7 mail storm rules 整合**:
   - 「old candidate pool exhaustion 待たない」遵守
   - 「MAIL_BUDGET 違反は P1」遵守
   - 「Phase3 re-ON pool cardinality estimate 必須」 = 300 が source-side cardinality 削減に貢献するか
7. **明日朝 user 提示時の cross-reference**:
   - 298-Phase3 v4(sink-side cutoff)との関係:300-COST = source-side fix、298 v4 と並列 / 後続 deploy
   - 推奨 deploy 順序:298-Phase3 v4(明日朝)→ 24h 安定 → 300-COST(deferred)

[hard constraints]
- read-only:src/ tests/ scripts/ config/ 編集禁止
- impl 着手禁止
- env / gcloud / WP / scheduler 操作禁止(gcloud logging read / describe / gsutil cat はOK)
- 既存 source 解析 v1 / Pack / supplement doc 修正禁止(別 file 新規 v2)
- commit only the new doc file
- DO NOT push (Claude push)
- single-file diff
- DO NOT install packages

[completion report - 4 fields]
- changed_files: [docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis_v2.md]
- commit_hash: <sha>
- new_findings_count: <N(v1 から増えた findings)>
- next_action_for_claude: "300-COST source 解析 v2 完了、298 安定後の Pack 起草へ反映"
