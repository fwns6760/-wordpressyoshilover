---
ticket: 244-followup
title: 244 module subtype-aware severity (試合系 strict / コメント系 lenient)
status: CLOSED
owner: Codex B
priority: P1
lane: B
ready_for: codex_b_fire
created: 2026-04-29
parent: 244 (`f2cc8a3` numeric module + evaluator + X suppress)
related: 234-impl-2/5/6 (subtype-aware mail/body)
---

## 背景

244 (`f2cc8a3`) は subtype 区別なしで uniform 判定。user 明示で記事タイプ別 severity が必要:
- 試合系 (postgame / farm_result / lineup / farm_lineup / pregame / probable_starter): 必須 strict (concrete mismatch = hard_stop)
- コメント/談話/コラム系 (manager_comment / player_comment / sns_topic / rumor_market): 軽め lenient (mismatch でも review 止まり)
- default / 不明: 中程度 (review、AI 補完禁止)

## scope (narrow、2 file 想定)

### 1. src/baseball_numeric_fact_consistency.py (subtype-aware severity tuning)

- 既存 `check_consistency(...)` signature に `subtype: str = ""` 追加 (default 値で後方互換維持)
- 内部 SUBTYPE 分類 frozenset 定義:
  ```python
  STRICT_SUBTYPES = frozenset({"postgame", "farm_result", "lineup", "farm_lineup", "pregame", "probable_starter"})
  LENIENT_SUBTYPES = frozenset({"manager_comment", "player_comment", "sns_topic", "rumor_market"})
  ```
- severity 判定 logic 修正:
  - subtype が STRICT_SUBTYPES → 既存 logic (concrete mismatch = hard_stop)
  - subtype が LENIENT_SUBTYPES → mismatch を review に 緩和 (hard_stop ではなく review)
  - その他 (default / unknown / 空文字) → review 止まり
- 既存呼び出し元 (subtype 引数なし) は default `""` で動く → 既存挙動完全維持

### 2. src/guarded_publish_evaluator.py (caller 側で subtype 渡す narrow 修正)

- 既存 `check_consistency(...)` 呼び出し位置 (242-A/B/D/D2/E と同 pattern で integration されている場所) に `subtype=record.get("article_subtype", "")` を追加
- それ以外の logic は touch しない

### 3. tests (narrow):

- `tests/test_baseball_numeric_fact_consistency.py` に subtype 別 fixture 6 件追加:
  - `test_strict_subtype_postgame_score_mismatch_hard_stops` (既存と同じ挙動、regression)
  - `test_lenient_subtype_manager_comment_score_mismatch_reviews` (新)
  - `test_lenient_subtype_player_comment_pitcher_confusion_reviews` (新)
  - `test_default_subtype_score_mismatch_reviews` (新、不明 subtype は review)
  - `test_legacy_call_without_subtype_default_to_review_safe_side` (新、後方互換)
  - `test_strict_subtype_farm_result_score_fabrication_hard_stops` (regression)
- 既存 fixture 全件 pass 維持(call signature 変更だが default 引数で後方互換)

## 不可触

- src/article_entity_team_mismatch.py (242-B)
- src/publish_notice_email_sender.py (234 系)
- src/body_validator.py / src/fixed_lane_prompt_builder.py (234-impl-5/6)
- src/tools/draft_body_editor.py (244-B / 244-B-followup scope)
- subtype 文字列追加禁止 (既存 subtype を使う、新 string は frozenset 内のみ)
- Gemini call 追加 / prompt 改修
- env / Secret / Scheduler / WP

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 file のみ stage
2. **挙動**: 新規 6 fixture 全 pass、既存 fixture fail 0、後方互換維持
3. **境界**: 評価 logic の subtype-aware branch のみ追加、broad 緩和なし

## commit message

`244-followup: subtype-aware severity (strict/lenient/default branching) + fixtures`
