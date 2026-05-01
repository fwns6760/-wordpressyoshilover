# Lane B round 20 — 288-INGEST Phase 1 candidate visibility contract verify(read-only)

## 目的

288-INGEST Pack v3 4-phase split(commit `fedf159`)の Phase 1 = candidate visibility contract を read-only verify。新 source 追加前段で「全 candidate が publish/review/hold/skip 経由で可視化されている」契約が現状 codebase 上で守られているか evidence 収集。

source 追加なし、deploy なし、env 変更なし、Gemini call 増加なし、mail 量増加なし。

## 不可触リスト(Hard constraints)

- src / tests / scripts / config 一切編集しない、**read-only grep / cat / 設計のみ**
- production 不触
- `git add -A` 禁止、明示 stage のみ

## 観測対象

### 1. silent skip 違反候補 path 0 確認(POLICY §19.1 整合)

```
grep -r "no_op_skip\|llm_skip\|content_hash_dedupe\|PREFLIGHT_SKIP_MISSING_\|REVIEW_POST_DETAIL_ERROR\|REVIEW_POST_MISSING" src/
```

期待:既知 path のみ、改修 #1 commit `e7e656c` 後の状態で増加なし。

### 2. candidate visibility 経路 inventory

各 candidate state で publish/review/hold/skip terminal 到達経路を確認:
- `src/rss_fetcher.py`: 全 skip_reason 列挙(skip_filter / skip_duplicate / live_update_disabled 等)、terminal state 経路
- `src/guarded_publish_runner.py`: refused / proposed の visibility(本日 5/1 evidence: backlog_only / hourly_cap 等)
- `src/publish_notice_scanner.py`: review/hold/skip mail 経路(改修 #6 cap reserve 後の状態)
- `src/draft_body_editor*.py`: 生成失敗 / dedupe / cooldown の log/mail 経路

### 3. body_contract_validate fail の visibility(POLICY §289-OBSERVE 整合)

`grep -r "body_contract_validate" src/` で fail 時の経路確認。POLICY 推奨 = 289 経路で可視化。現状 log-only or 289 経由か区別。

### 4. 新 source 追加時に新発生する skip pattern 想定

288 Pack v3 で 3 source 候補(rss_sources.json 拡張想定)を追加した場合、新発生し得る skip pattern 列挙(各 candidate が visibility 経路に乗るか想定)。

## 出力(stdout + Pack 補強 doc)

新 file: `docs/handoff/codex_responses/2026-05-01_288_INGEST_phase1_visibility_evidence.md`

内容:

1. **silent skip violation grep 結果**:0 件 / 既知 path 一覧
2. **candidate visibility 経路 inventory**:src/* の skip path 一覧 + terminal state mapping
3. **body_contract_validate visibility**:現状経路(log-only or 289 経由)+ 改善要否判定
4. **新 source 追加時 risk 想定**:Phase 3 source 追加時に visibility が壊れる pattern 列挙
5. **Phase 1 OBSERVED 判定**:
   - PASS:全 candidate が visible terminal に到達、新 source 追加でも visibility 契約維持可能
   - FAIL:violation path 検出、Phase 2 で修正必要
   - PARTIAL:gap あり、追加 evidence 必要
6. **Phase 2 fallback + trust impl への引継ぎ事項**

## 実施

1. read-only grep / cat で evidence 収集
2. 上記 doc 作成
3. `git add docs/handoff/codex_responses/2026-05-01_288_INGEST_phase1_visibility_evidence.md docs/handoff/codex_prompts/2026-05-01/lane_b_round_20_288_phase1_visibility_verify.md`
4. `git diff --cached --name-status` で 2 file のみ確認
5. commit message: `docs(handoff): 288-INGEST Phase 1 candidate visibility contract verify (read-only evidence)`
6. plumbing 3 段 fallback 装備
7. `git log -1 --stat`

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "docs/handoff/codex_responses/2026-05-01_288_INGEST_phase1_visibility_evidence.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_b_round_20_288_phase1_visibility_verify.md"
  ],
  "phase_1_judgement": "PASS | FAIL | PARTIAL",
  "violation_path_count": <int>,
  "test": "n/a (read-only)",
  "remaining_risk": "none",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master + Phase 2 design 更新"
}
```

## 5 step 一次受け契約

- read-only(commit / git mutation 一切なし、最後の自分の commit のみ)
- src / tests / scripts / config 一切編集しない
- pytest 不要
- scope 内
- rollback 不要(read-only doc commit、可逆)
