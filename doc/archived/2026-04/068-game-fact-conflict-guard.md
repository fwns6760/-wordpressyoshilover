# 068 game fact conflict guard

- owner: Codex B
- deps: 036(prompt hardening) / 040(repair playbook) / 067(comment lane で 3 tag を既に hard fail 実装)
- status: READY
- fire 前提: runtime 非依存(fixture / 既存 Draft / validator で閉じる)
- §31-C 一体化: doc + impl + tests を 1 commit

## §1 目的

067 で comment lane 限定で実装した 3 hard fail tag を、**該当する fixed subtype** へ水平展開する。

## §2 対象 fail_tag と適用範囲

| fail_tag | 分類 | 適用 subtype |
|---|---|---|
| `NO_GAME_BUT_RESULT` | hard fail | **game / result 文脈を持つ subtype のみ**(postgame / lineup / probable_starter / farm_result / 試合結果系 notice) |
| `GAME_RESULT_CONFLICT` | hard fail | **game / result 文脈を持つ subtype のみ**(同上) |
| `TITLE_BODY_ENTITY_MISMATCH` | hard fail | **全 fixed subtype**(game 文脈の有無に依らず適用) |

game / result 文脈を持たない fixed subtype(番組情報 / 公示 / transaction 系 notice 等)には `NO_GAME_BUT_RESULT` / `GAME_RESULT_CONFLICT` を適用しない(false positive 回避)。

## §3 hard fail の性質

- repair 禁止(soft fail 化しない)
- fixed lane で止める(agent lane へ routing しない)
- ledger outcome は既存(`repair_closed` / `escalated` / `accept_draft`)の範囲で `escalated` に相当

## §4 実装方針(最小 diff)

### 新規

- `src/fact_conflict_guard.py`
  - 純粋 helper を切り出す
  - `detect_no_game_but_result(draft, source_refs) -> bool`
  - `detect_game_result_conflict(draft, source_refs) -> bool`
  - `detect_title_body_entity_mismatch(title, body_slots) -> bool`
  - subtype 適用範囲の判定は helper 内部で持たず、呼び出し側の responsibility

- `src/fact_conflict_guard_subtype_policy.py`(または同 module の const)
  - subtype → 適用 fail_tag のマップを定義
  - game/result 文脈を持つ subtype 一覧を定数化

- `tests/test_fact_conflict_guard.py`
  - 3 helper × fixture 入力で hard fail detection
  - 各 subtype policy に対する適用 / 非適用 tests
  - 既存 067 comment lane tests を呼んで非破壊確認(代表 1-2 ケース)

### 既存修正(最小 diff 原則)

- `src/comment_lane_validator.py`
  - 該当 3 tag の判定ロジックを新 helper 呼び出しへ寄せる
  - 067 の validator の **挙動は非破壊**(入出力変化なし)
  - 共通化は helper 抽出のみ、validator class / API 署名は維持
- fixed lane 側の既存 validator(036 系)
  - 新 helper を呼ぶ薄い adapter を追加(最小 diff)

### 既存 067 tests

- 非破壊維持(test file は触らない、pass 継続)

## §5 不可触(§31-B Hard constraints)

- route / trust: `src/source_trust.py` / `src/source_id.py` / `src/tools/run_notice_fixed_lane.py` — diff 0
- automation: `automation.toml` / scheduler / env / secret / mail 経路 — diff 0
- ledger schema: `docs/handoff/ledger/` schema — diff 0
- 036 本体: `src/fixed_lane_prompt_builder.py` — diff 0(068 は validator 層、prompt は触らない)
- 040 本体: `src/repair_playbook.py` — diff 0(068 は hard fail、repair しない)
- 047 本体: `src/postgame_revisit_chain.py` — diff 0
- 046 本体: route 判定 diff 0
- 041: `src/eyecatch_fallback.py` — diff 0
- `published` 書き込み経路 — Phase 4 まで禁止
- Codex A 領域(046 / 047 / 028 T1 / 037 pickup boundary) — diff 0

## §6 accept 条件

1. 3 hard fail helper が独立 module として切り出されている(`src/fact_conflict_guard.py`)
2. subtype policy が定数化され、game/result 文脈の有無で適用が分岐する(fixture tests で検証)
3. `TITLE_BODY_ENTITY_MISMATCH` が全 fixed subtype で発火する(fixture tests で検証)
4. `NO_GAME_BUT_RESULT` / `GAME_RESULT_CONFLICT` が game/result 文脈を持たない subtype で発火しない(fixture tests で検証)
5. 067 comment lane validator の既存 tests が全 pass(32 passed + 14 subtests 非破壊)
6. 3 hard fail すべてで repair 経路に入らない(tests で検証)
7. 既存 ledger tag 衝突は既存正本優先で正規化(067 の正規化テーブルと整合)

## §7 runtime 依存

- 無(fixture + 既存 Draft + validator で閉じる)
- pipeline / automation / WSL / observability と分離

## §8 TODO

- 【×】 `src/fact_conflict_guard.py` 新規実装
- 【×】 subtype policy 定数化
- 【×】 `tests/test_fact_conflict_guard.py` 新規
- 【×】 067 comment_lane_validator.py を helper 呼び出しへ寄せる(最小 diff、挙動非破壊)
- 【×】 fixed lane validator(036 系)へ薄い adapter 追加
- 【×】 067 既存 tests 非破壊確認
- 【×】 §6 accept 条件 7 項目自己追認
