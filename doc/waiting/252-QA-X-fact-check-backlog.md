---
ticket: 252-QA
title: X 投稿候補 path 単独 fact check 追加(現状 publish_notice_email_sender 経由のみ、x_post_generator 単独経路の薄い穴を埋める narrow)
status: BACKLOG
owner: Codex B(後段)
priority: P2
lane: B
ready_for: 254-QA 完了 + 247-QA 観察結果後判断
created: 2026-04-29
related: 244 numeric guard / 244-followup / 234-impl-1〜4 / 247-QA
---

## 状態: BACKLOG

## なぜ今やらないか

1. **publish_notice_email_sender 経由の check_consistency 既存**(244 module、line 1096)
   - X 候補 suppress 経路は既に動作中
   - 漏れる経路は限定的(publish_notice 通らない X 候補生成 path がある場合)
2. **緊急度 中**(publish_notice 経由が effective 防衛)
3. **254-QA(投手回数正規化)が事実防衛により直結**
   - 254-QA で 244 検出力強化 → X 候補にも自動波及

## 解除条件(GO trigger)

以下 1 つ以上 検出された場合:
- X 候補で **publish_notice 経由しない path 経由で X 候補生成** が確認された
- X 候補に **数字 / 選手名 ミスの実例**(post_id + 候補 text 明示)
- 247-QA flag ON 観察で「strict success postgame の X 候補に source にない数字 / 選手名」検出

## owner

- 起票: Claude(本日 2026-04-29)
- 実装: Codex B(後段)
- accept: Claude
- live judgment: user GO

## 次確認タイミング

- 254-QA 完了後(本日中 or 翌日)
- 247-QA flag 試合日 ON 観察後
- 編集者から X 候補誤情報報告あった時(即)

## 関連 file

- src/x_post_generator.py(target file、現状 baseball_numeric_fact_consistency import なし)
- src/publish_notice_email_sender.py(line 1096 既存 check_consistency 経路、参考)
- src/baseball_numeric_fact_consistency.py(reuse、変更なし)
- tests/test_x_post_generator.py(or 該当 test file、fixture 追加先)

## コスト影響

- Gemini call: 0(既存 generate 後 post-check のみ)
- X API: 不要
- Cloud Run / Scheduler: 不変
- 運用コスト: 低(suppress 増えるが X 自動投稿しない方針 = 直接外部影響なし)
- 実装工数: 中

## 背景

現状の X 候補 fact check:
- ✅ `src/publish_notice_email_sender.py:1096` で `check_consistency` 呼び出し(244 module)→ X candidate suppress 経路あり
- ❌ `src/x_post_generator.py` 内には `baseball_numeric_fact_consistency` import なし → 単独 generation path で独立 check 薄い
- 実害 risk: 中(244 module hit 時は publish blocked = X 候補も生成されない、ただし publish_notice 経由しない X 候補生成 path がある場合 漏れる)

## 現方針(2026-04-29 user 判断)

- 緊急度 中(publish_notice 経由 check_consistency が既存)
- 254-QA(投手回数正規化)後に判断
- article publish は維持し、失敗した X 候補だけ suppress

## scope (narrow、後段実装時)

### 1. src/x_post_generator.py に narrow check 追加

各 X 候補 generation 関数の出力直後に:
```python
from src.baseball_numeric_fact_consistency import check_consistency

result = check_consistency(
    source_text=source_block,
    generated_body=candidate_text,
    x_candidates=[candidate_text],
    metadata={"subtype": subtype},
    publish_time_iso=publish_time,
    subtype=subtype,
)
if result.severity in ("hard_stop", "x_candidate_suppress"):
    # 該当 X 候補のみ suppress、他候補と article publish は維持
    log_warning(...)
    continue  # この候補だけ skip
```

### 2. tests narrow

- `test_x_candidate_score_mismatch_suppresses_only_that_candidate`
- `test_x_candidate_player_mismatch_suppresses_only_that_candidate`
- `test_x_candidate_pass_allows_all_candidates`
- `test_x_candidate_check_does_not_block_article_publish`

### 3. write_scope (narrow)

- src/x_post_generator.py(narrow check 追加)
- tests/test_x_post_generator.py(or 該当 test file、4 fixture)

## 不可触

- article publish 経路(本 ticket は X 候補のみ suppress)
- Gemini call 数増加(既存 generate 後の post-check のみ)
- X API 連携(候補生成は内部 logic のみ、X 投稿はしない)
- 244 module 内部 logic 変更
- 247-QA / 234-impl-* / Cloud Run / Scheduler / WP REST

## デグレ防止 contract

- article publish 経路不変
- 既存 X 候補 generation logic 不変
- check_consistency 失敗時のみ 該当候補 skip、他候補は通す
- false positive(良 X 候補を suppress)1 件でも疑いがあれば実装止めて Claude に report

## acceptance (将来本実装時)

- 1 commit narrow + tests pass
- article publish 経路 0 影響
- Gemini call 数 0 増加

## non-goals

- X API 連携 / X 自動投稿(user 明示 NG、GPTs 経由)
- publish_notice_email_sender 既存 check_consistency 変更(独立 path 追加のみ)
- 247-QA strict 系統合(別 ticket 250-QA scope)

## HOLD 解除条件

1. 254-QA 完了(投手回数正規化で 244 検出力強化済)
2. 247-QA flag ON 観察(strict 動作中の X 候補挙動 data 取得)
3. 実 X 候補で漏れ事例検出(publish_notice 経由しない X 候補生成 path があれば最優先)

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
