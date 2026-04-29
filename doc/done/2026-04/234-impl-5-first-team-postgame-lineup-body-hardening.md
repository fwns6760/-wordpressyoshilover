---
ticket: 234-impl-5
title: 234 contract 反映(一軍 postgame / lineup の本文 hardening、source/meta anchor 強化)
status: CLOSED
owner: Codex B
priority: P1
lane: B
ready_for: codex_b_fire
created: 2026-04-29
related: 234-impl-2 (CLOSED、mail UX 一軍判定 helper)、244-B (CLOSED、repair anchor)、244 (CLOSED、numeric module)
---

## 背景

234-impl-2 で mail UX 側の一軍判定 helper を導入済(`_is_first_team_article` in publish_notice_email_sender)。234-impl-5 は **本文生成段階** で source/meta anchor を強化し、Gemini が数字・選手名・日付を勝手に作るのを抑える narrow 修正。

## 目的

Gemini に数字・日時・選手名を補完させない。
本文生成時に source/meta にある facts だけを使い、optional facts がない section は出さない。
required facts 不足は body_validator で fail_axis 立ててreview 倒し。

## scope (narrow、2 file)

### 1. src/fixed_lane_prompt_builder.py (postgame contract の anchor 強化)

- `CONTRACTS["postgame"]` の `fallback_copy` に追加:
  - 「source/meta にない数字(スコア・打数・投球回・本塁打数等)を本文に書かない。score がない場合は『公式発表待ち』『source 記載なし』で止める。」
  - 「source/meta にない選手名を本文に書かない。一軍 postgame 記事で対戦相手選手を巨人選手として扱わない。」
- `CONTRACTS["postgame"]` の `abstract_lead_ban` 既存 lines は不変
- 一軍 lineup 用に新規 contract は **作らない**(subtype 文字列追加禁止、user 明示)
  - 既存の `pregame` / `probable_starter` contract も触らない
  - lineup の anchor は body_validator 側で対応

### 2. src/body_validator.py (一軍 postgame / lineup の post-gen check)

- 既存 `_validate_postgame_fact_kernel` に追加:
  - `postgame_first_team_player_unverified` (= 一軍 postgame で source にない選手名が決勝打 / 投手成績の主語の場合)
  - `postgame_first_team_score_fabrication` (= 一軍 postgame で source にない score を本文に書いている場合)
  - 一軍判定: title / body に二軍 marker (`二軍|三軍|ファーム|farm|Farm|FARM`) が無いこと
  - source 内の score / player_names を抽出する helper は本 ticket 内で **inline minimal** でよい(244 module 完全 reuse は scope 拡大、本 ticket は body_validator scope 内で narrow)
- 新規 fail_axis 名は `body_validator.py` 内 `FAIL_AXES` (line 71-) に追加
- lineup 系: 既存 `expected_block_order("pregame")` を使い、`pregame_first_team_lineup_missing` 等を必要時のみ narrow 追加

### 3. tests (narrow):

- `tests/test_fixed_lane_prompt_builder.py` (or 該当) に postgame contract fallback_copy verify fixture 1 件
- `tests/test_body_validator.py` (or 該当) に新規 fail_axis fixture 4 件:
  - `test_postgame_first_team_player_unverified_blocks` (source にない選手名 → fail)
  - `test_postgame_first_team_score_fabrication_blocks` (source 1-11 → body 19-1 → fail、244 と同じ digit boundary invariant)
  - `test_postgame_with_full_source_facts_passes` (regression: good 記事を止めない)
  - `test_postgame_with_farm_marker_skips_first_team_check` (二軍記事は本 ticket scope 外、不変)

## 不可触

- src/publish_notice_email_sender.py touch 禁止 (impl-3/4 scope)
- src/baseball_numeric_fact_consistency.py touch 禁止 (244 専任)
- src/guarded_publish_evaluator.py touch 禁止
- src/rss_fetcher.py prompt 全体改修禁止 (本 ticket は narrow anchor のみ)
- src/tools/draft_body_editor.py touch 禁止 (244-B scope)
- subtype 文字列追加 (`first_team_postgame` / `first_team_lineup` を src に書かない)
- Gemini call 追加 / 新規 LLM 呼び出し
- Web / 外部 API / roster DB
- env / Secret / Scheduler / Cloud Run / WP REST
- H3 required 化 / template structure 強制
- 既存 fixture 1 件も変更しない

## デグレ防止 contract

- 既存 fixture 全件 pass を維持
- regression fixture (good full-source postgame、二軍 postgame) で「本 ticket で挙動変わらない」を担保
- digit boundary invariant: source `1-11` を `19-1` などに正規化しない
- false positive(良 一軍 postgame を fail 扱い)1 件でも疑いがあれば実装止めて Claude に report

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 4 file のみ stage、git add -A 禁止
2. **挙動**: 新規 fixture 全 pass、既存 fixture fail 0、pytest baseline 維持
3. **境界**: publish_notice_email_sender / 評価 logic / Gemini / Cloud Run 不変

## commit message

`234-impl-5: first-team postgame/lineup body hardening (source anchor + post-gen check) + fixtures`
