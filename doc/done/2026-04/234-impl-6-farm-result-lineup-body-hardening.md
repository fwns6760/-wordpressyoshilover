---
ticket: 234-impl-6
title: 234 contract 反映(farm_result / farm_lineup の本文 hardening、source/meta anchor 強化)
status: CLOSED
owner: Codex B (Round 2)
priority: P1
lane: B
ready_for: codex_b_fire (after 234-impl-5)
created: 2026-04-29
related: 234-impl-1 (CLOSED、farm mail UX)、234-impl-5 (postgame/lineup body hardening、同 file 連続 commit)
---

## 背景

234-impl-5 の同 file (body_validator.py + fixed_lane_prompt_builder.py) 連続 narrow 追加。`farm_result` / `farm_lineup` 本文生成で source/meta anchor 強化。

## scope (narrow、2 file)

### 1. src/fixed_lane_prompt_builder.py (farm_result contract anchor 強化)

- `CONTRACTS["farm_result"]` の `fallback_copy` に追加:
  - 「source/meta にない数字(安打数・打点・投球回・失点等)を本文に書かない。numeric weak の場合は『二軍試合速報待ち』『source 記載なし』で止める。」
  - 「source/meta にない選手名を本文に書かない。一軍昇格断定や決勝打・好投の主語を source 外の名前で書かない。」
- `abstract_lead_ban` 既存 lines 不変
- farm_lineup 用に新規 contract は **作らない**(subtype 文字列追加禁止)
- 234-impl-5 で postgame contract に追加した anchor 行は触らない、farm_result branch のみ

### 2. src/body_validator.py (farm_result / farm_lineup post-gen check)

- 既存 `FAIL_AXES` に追加:
  - `farm_result_player_unverified` (source にない選手名が成績の主語)
  - `farm_result_numeric_fabrication` (source にない数字)
  - `farm_lineup_lineup_missing` (二軍記事で `1番` / `先発` / `スタメン` marker が body に無い)
- 一軍判定との重複回避:
  - 234-impl-5 で追加された first_team_postgame check は subtype `postgame` 限定、本 ticket は subtype `farm_result` / `farm_lineup` 限定で disjoint
  - 二軍 marker (`二軍|三軍|ファーム|farm|Farm|FARM`) hit を必須条件にして、誤判定回避

### 3. tests (4 fixture 追加、既存 fixture 不変)

- `test_farm_result_player_unverified_blocks`
- `test_farm_result_numeric_fabrication_blocks` (source にない安打数 → fail)
- `test_farm_lineup_missing_lineup_marker_blocks`
- `test_farm_result_with_full_source_facts_passes` (regression)

## 不可触

- src/publish_notice_email_sender.py touch 禁止 (impl-3/4 scope)
- 234-impl-5 で追加した postgame contract anchor / first_team_postgame fail_axis を 1 行も変更しない、新規 farm 系 branch のみ
- 244 / 244-B / 242-B / 243 / 234-impl-1/2 既存 logic 不変
- subtype 文字列追加 (`first_team_*` / `farm_lineup_*` を src 識別子として使わない、helper 内 marker のみ)
- Gemini call 追加
- env / Secret / Scheduler / WP

## デグレ防止 contract

- 既存 fixture 全件 pass を維持
- regression fixture (good full-source farm_result) で「本 ticket で挙動変わらない」を担保
- 一軍 postgame fixture (impl-5) との衝突なし(subtype 別 disjoint check)
- false positive 1 件でも疑いがあれば実装止めて Claude に report

## acceptance (3 点 contract)

1. **着地**: 1 commit に src/fixed_lane_prompt_builder.py + src/body_validator.py + tests のみ stage
2. **挙動**: 新規 4 fixture 全 pass、既存 fixture fail 0
3. **境界**: publish_notice_email_sender / 評価 logic / Gemini / Cloud Run 不変

## commit message

`234-impl-6: farm_result/farm_lineup body hardening (source anchor + post-gen check) + fixtures`
