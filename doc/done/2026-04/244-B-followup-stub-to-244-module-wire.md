---
ticket: 244-B-followup
title: 244-B stub → 244 module wire (post-check 実装、Gemini 再呼び出しなし)
status: CLOSED
owner: Codex A
priority: P1
lane: A
ready_for: codex_a_fire
created: 2026-04-29
parent: 244-B (`e04eee1` Phase 2-B stub)
prerequisite: 244 module landed (`f2cc8a3` `src/baseball_numeric_fact_consistency.py`)
---

## 背景

244-B (`e04eee1`) で Phase 2-B として `_post_check_repaired_body` adapter stub を追加(常に severity="pass" 返す pass-through)。244 module (`f2cc8a3`) が landed したので、本 followup で stub を **本物の 244 module wire** に置換。

## scope (narrow、1-2 file)

### 1. src/tools/draft_body_editor.py (stub → wire)

#### 1-A. `_post_check_repaired_body` の実装置換:

```python
# Before (e04eee1 stub):
def _post_check_repaired_body(source_text, new_body, metadata, publish_time_iso):
    return _PostCheckReport(severity="pass", flags=(), details={})

# After (244-B-followup wire):
def _post_check_repaired_body(source_text, new_body, metadata, publish_time_iso):
    from src.baseball_numeric_fact_consistency import check_consistency
    subtype = (metadata or {}).get("subtype", "")
    return check_consistency(
        source_text=source_text,
        generated_body=new_body,
        x_candidates=None,
        metadata=metadata,
        publish_time_iso=publish_time_iso,
        subtype=subtype,  # 244-followup landed 時点で subtype-aware
    )
```

- 244 module signature を inspect して、戻り値 type が `_PostCheckReport` と互換でない場合は wrapper 追加(severity / flags / details の 3 属性 mapping)
- 244-followup が先に landed していれば `subtype` 引数を渡す、まだなら省略(後方互換)

#### 1-B. main() 内 post_check 結果を使った WP draft PUT skip 経路:

- 既存 main() で `_post_check_repaired_body` 呼び出し位置で、戻り値 severity に応じた分岐:
  - `severity="pass"` → 既存 PUT 経路維持 (現状の挙動)
  - `severity="hard_stop"` or `"mismatch"` → **WP draft PUT を skip**、`repair_provider_ledger` に `strict_pass=False` + reason に 244 mismatch flag 名を記録
  - `severity="review"` or `"x_candidate_suppress"` → ledger に記録するが PUT 自体は skip (保守側)
- **Gemini 再呼び出しはしない** (user 明示禁止、Gemini 1 回までで止める)

### 2. tests/test_draft_body_editor.py (5 fixture 追加 or 修正)

- `test_post_check_calls_baseball_numeric_fact_consistency_module` (mock で 244 module 呼び出し確認)
- `test_post_check_score_mismatch_blocks_wp_put` (244 module mock で hard_stop → WP put 呼ばれない、ledger strict_pass=false)
- `test_post_check_pass_allows_wp_put` (244 module mock で pass → 既存 WP put 経路が動く)
- `test_repair_failure_records_strict_pass_false_with_244_flag` (244 mismatch flag を ledger reason に記録)
- `test_repair_does_not_retry_gemini_on_post_check_fail` (Gemini 1 回までで止まる)
- 既存 e04eee1 stub test (`test_post_check_adapter_returns_pass_until_244_module_lands`) は **削除 or 244 module mock pass で置換** (既存 fixture を変更扱いだが、stub→wire の置換なので必要)

## 不可触

- src/baseball_numeric_fact_consistency.py touch 禁止 (244-followup scope)
- src/guarded_publish_evaluator.py touch 禁止
- src/publish_notice_email_sender.py / body_validator.py / fixed_lane_prompt_builder.py touch 禁止
- prompt 改修 / Gemini call 追加 / 再 repair
- env / Secret / Scheduler / WP REST 設定変更
- 既存 WP 記事の本文修正 (失敗時は draft 状態維持)

## デグレ防止 contract

- 既存 e04eee1 prompt anchor 強化 ([FACTS] block / no-fabrication 指示) は 1 行も変更しない
- 既存 e04eee1 fixture (prompt anchor 関連 2 fixture) は維持、stub adapter test のみ wire 版に置換
- 244 module の戻り値が既存 _PostCheckReport と完全互換でなければ wrapper 追加
- false positive (good repair を fail 扱い) 1 件でも疑いがあれば実装止めて Claude に report

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 file のみ stage
2. **挙動**: 新規 5 fixture 全 pass、既存 prompt anchor fixture (e04eee1) 全 pass、stub→wire 置換のみ (logic 不変)
3. **境界**: Gemini call 数増加 0、Cloud Run / Scheduler / Secret / WP すべて不変

## commit message

`244-B-followup: stub → baseball_numeric_fact_consistency module wire + tests`
