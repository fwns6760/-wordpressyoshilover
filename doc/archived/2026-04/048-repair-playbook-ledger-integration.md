# 048 — 040 repair playbook 次弾 ledger 連携(24h/7d fail_tag 昇格 formatter)

**フェーズ：** 038 昇格 loop の自動判定層(Codex B 補修線 READY / HOLD)
**担当：** Codex B
**依存：** 038 active(docs/handoff/ledger 運用中)、040 accepted(9b0b5ae、`src/repair_playbook.py` + tests 着地済)
**状態：** READY / HOLD(Codex B 補修線 READY 1 本維持枠。046 accepted 済、2026-04-22 以降は HOLD 解除トリガ 3 条件(§fire 前提)のいずれか観測で fire)

---

## why_now

- 038 は ledger 17 field / 10 fail_tags / 3 outcome / 昇格基準(036 系 / 037 系 / 035 判定、優先度 036>037>035)を正本化したが、昇格判定そのものは Claude の週次手動集計に依存している。
- 040 は repair playbook の正本(block / sentence / attribution の局所補修、全文再生成禁止、repair 2 回上限)を固めたが、どの fail_tag がいつ 040 に降ってくるかは手動判定。
- このままだと (a) Claude 不在 1 週間で昇格判定が止まる、(b) ledger 行が増えても 036 / 037 の prompt hardening に反映される速度が遅い。
- Codex B 補修線を空にしない(READY 1 本維持)原則(2026-04-22 user 指示)の正本 1 本として本 ticket を待機枠に置く。
- 本便は 040 playbook の「repair をどう直すか」とは切り離し、「どの fail を 036 / 037 / 035 に昇格させるか」の判定層だけを足す。repair action 本体は触らない。

## purpose

- ledger(`docs/handoff/ledger/YYYY-MM-DD.jsonl`)を読み、`fail_tags` × `subtype` × `prompt_version` × `source_family` の 3-4 軸で 24h / 7d 集計する module を `src/repair_playbook.py` に追加する。
- 038 昇格基準(036 系 = same subtype + same fail_tag + same prompt_version 24h 3 件 or 7d 5 件、037 系 = same source_family + same fail_tag が 2 subtype 以上、035 = close_marker 7d 2 件+ or 10%+)を自動判定する。
- 基準を越えた candidate を `{"promotion_target": "036|037|035", "subtype": ..., "fail_tag": ..., "prompt_version": ..., "window": "24h|7d", "count": N, "sample_candidate_keys": [...]}` の形で emit する。
- emit 結果を current_focus.md / decision_log.md に Claude が貼り込むための 1 行 summary formatter を同時に足す。
- **自動で 036 / 037 / 035 に書き込まない**。decision log への反映は Claude 手動のまま。本便は判定 formatter だけ。

## scope

### 集計 module(`src/repair_playbook.py` 追加)

- 追加関数(関数名は Codex 判断、以下は指針):
  - `aggregate_fail_tags(ledger_dir: Path, *, now: datetime) -> list[PromotionCandidate]`
  - `format_promotion_summary(candidates: list[PromotionCandidate]) -> str`(1 候補 1 行)
- ledger 読み取りは既存 jsonl を read-only に読むだけ。**ledger に書き込まない**(Claude 管理の境界を維持)。
- 既存 `src/repair_playbook.py` の repair action / minimum-diff rubric / 1 Draft 1 回制限に diff を入れない。

### 昇格判定ロジック(038 §昇格基準準拠)

- **036 系候補**: same `subtype` + same `fail_tag` + same `prompt_version` が
  - 24h で 3 件以上 → `promotion_target=036`, `window=24h`
  - または 7d で 5 件以上 → `promotion_target=036`, `window=7d`
- **037 系候補**: same `source_family` + same `fail_tag` が **2 subtype 以上**で出る → `promotion_target=037`, `window=7d`
- **035 候補**: `fail_tag=close_marker` が 7d で **2 件以上** または **全 Draft の 10% 以上** → `promotion_target=035`, `window=7d`
- 優先度: **036 > 037 > 035**(038 §昇格基準と一致)。同一 fail_tag が複数基準を満たす時は上位優先度のみ emit。
- 単発 fail(上記基準未満)は emit しない(`repair_closed` として 040 で閉じられる前提)。

### formatter(human-readable 1 行)

- 出力例(emit しない場合は空行):
  - `2026-04-22 24h 036候補 subtype=postgame fail_tag=thin_body prompt_version=v3 count=4 keys=[k1,k2,...]`
  - `2026-04-22 7d  037候補 source_family=official_x fail_tag=attribution_missing subtypes=[postgame,lineup_notice] count=3`
  - `2026-04-22 7d  035候補 fail_tag=close_marker count=3 ratio=12.5%`

### 呼び出し経路

- CLI エントリ: `python3 -m src.tools.run_repair_playbook_aggregator --aggregate --window 24h|7d --ledger-dir <path>`(専用手動 entrypoint。既存 repair playbook API と runtime には接続しない)。
- 自動起動は本便 scope 外。automation.toml / scheduler / cron には **登録しない**。Claude が手動または event-driven で回す。

### 不可触

- 038 ledger schema(17 field)
- 038 §昇格基準の数値閾値(24h 3 / 7d 5、037 2 subtype、035 2 件+ or 10%+)
- 040 repair action / minimum-diff rubric / fail_tag ごとの repair 順 / 1 Draft 1 回制限
- 036 prompt contract / 037 pickup contract / 035 close_marker observation window
- `src/fixed_lane_prompt_builder.py` / `src/body_validator.py` / `src/title_validator.py` / `src/source_attribution_validator.py`
- Codex A 領域: `src/tools/run_notice_fixed_lane.py` / `src/game_id.py` / `src/source_id.py` / `src/source_trust.py` / `src/eyecatch_fallback.py`
- WP published 書込
- automation.toml / scheduler / env / secret / quality-gmail / quality-monitor / draft-body-editor

## non_goals

- 昇格 candidate を 036 / 037 / 035 の doc / src に自動反映すること(Claude 手動維持)
- ledger への書込(Claude 管理、本便は read-only)
- fail_tag の追加 / 変更(10 種固定)
- outcome の追加 / 変更(3 種固定)
- 038 昇格基準の数値閾値変更
- 040 playbook の repair action 追加 / 変更
- quality-gmail に昇格 candidate を流す(029 digest と混ぜない)
- published 記事の改変
- automation.toml への cron 登録(Phase 次便、本便では CLI 手動実行のみ)

## success_criteria(3 点 contract、feedback_accept_3_point_contract.md 準拠)

**一次信号(accept 根拠)**

- **着地**: `git log -1 --stat` で `src/repair_playbook.py` + tests の追加のみ、`git status --short` clean
- **挙動**: `pytest` 全 pass + CLI `python3 -m src.repair_playbook --aggregate --window 24h|7d` が期待 candidate を emit + `format_promotion_summary()` が 1 候補 1 行出力
- **境界**: 不可触リストに `diff なし`(038 ledger schema / 040 action / Codex A 領域 / validator 本体)

**二次信号(事後記録、accept 根拠にしない)**

- 実 ledger での candidate emit 観測は Claude 手動で週次実施

## acceptance_check(自己追認)

- `grep -r 'ledger' src/repair_playbook.py` で read-only 操作のみ(write / append 無し)
- `grep -r 'subprocess\|requests\|urlopen' src/repair_playbook.py` で新 external call が無い
- `git diff HEAD~1 -- src/tools/run_notice_fixed_lane.py src/source_trust.py src/source_id.py src/game_id.py src/eyecatch_fallback.py` で差分 0(Codex A 領域不可触)
- `git diff HEAD~1 -- src/body_validator.py src/title_validator.py src/source_attribution_validator.py src/fixed_lane_prompt_builder.py` で差分 0
- tests 追加:
  - fixture ledger から 036 系候補(24h 3 / 7d 5)が emit
  - fixture ledger から 037 系候補(2 subtype 跨ぎ)が emit
  - fixture ledger から 035 候補(7d 2 件+ / 10%+)が emit
  - 基準未満の fail_tag は emit されない
  - 優先度 036 > 037 > 035 が候補並びに反映
  - formatter が 1 候補 1 行で出力
  - CLI `--aggregate --window 24h|7d` が正常 exit
- 040 既存 tests / 036 / 030 / 032 / 033 / 034 の validator tests が引き続き pass

## fire 前提 / stop 条件

### fire 前提

- 038 active(達成)
- 040 accepted(`9b0b5ae`、達成)
- 046 accepted(`8ef8330` + `069daa6`、達成)
- 047 accepted(`da692fc`、達成)
- **HOLD 解除トリガの 3 条件のいずれかを観測**(2026-04-22 user 指示):
  - ledger: same subtype + prompt_version + fail_tag が 24h 2 回+
  - 046 first wave + 047 派生 記事の prompt/validator 起因手直し 2 件+
  - quality-gmail digest 主因が 2 連続で prompt/validator 側

### fire 時 prompt 追記項目(2026-04-22 user 指示で吸収予定)

- **ledger schema 拡張: `derivative_family` field 追加**(047 派生 Draft と 046 first wave Draft を ledger 上で区別するための field、047 stdout route evidence `fixed_primary_derivative` / `deferred_pickup_derivative` を ledger に 1 field だけ落とす)。本件は独立 ticket を切らず、048 fire 時の prompt に scope として追記して吸収する(2026-04-22 user 判断、新規 ticket 増やさない方針)。048 scope の `aggregate_fail_tags()` 集計軸にも `derivative_family` を追加し、047 派生便の fail_tag 集計を独立できるようにする

### stop 条件

- 038 ledger schema への書換 / 新 field 追加
- 040 repair action / 1 Draft 1 回制限 / minimum-diff rubric の書換
- Codex A 領域 / validator 本体 / eyecatch fallback への diff
- ledger への write / append
- automation.toml / scheduler / cron 登録
- new external dep(requests / urlopen / 新 subprocess)
- pytest 失敗

## 2026-04-23 formatter 先行便 着地範囲

- fixture ledger(JSON / JSONL) の read-only 集計、24h / 7d window、user acceptance 層 trigger(24h 2 件+)と 036 / 037 / 035 昇格候補 formatter を先行実装。
- 実 ledger 現物 read、038 昇格 loop 接続、`derivative_family` schema 追加、automation / scheduler 登録は未実施のまま後続 scope に残す。

## TODO(起票時点)

【×】`src/repair_playbook.py` に `aggregate_fail_tags()` / `format_promotion_summary()` を追加
【×】ledger jsonl を read-only で読み、3-4 軸集計を 24h / 7d window で実装
【×】038 §昇格基準の数値閾値を実装(036=24h 3 / 7d 5、037=2 subtype、035=2 件+ or 10%+)
【×】優先度 036 > 037 > 035 を candidate emit 並びに反映
【×】基準未満 fail は emit しない
【×】専用 CLI `python3 -m src.tools.run_repair_playbook_aggregator --aggregate --window 24h|7d --ledger-dir <path>` を追加
【×】既存 repair action / minimum-diff rubric / 1 Draft 1 回制限に diff を入れない
【×】038 ledger schema / Codex A 領域 / validator 本体に diff を入れない
【×】automation.toml / scheduler / cron に登録しない
【×】ledger に書き込まない(read-only、Claude 管理境界維持)
【×】tests(036/037/035 emit、基準未満非 emit、優先度順、formatter 1 行、CLI 正常 exit)
【×】doc/README.md に 048 formatter 先行便着地の 1 行を追加

## 本便の scope 外(再掲、混線防止)

- 046 pickup parity first wave(Codex A 本線、2026-04-22 FIRING、本便と独立並走)
- 041 / 045 / 039 / 042 / 043 / 044 = 独立 observation 凍結
- 020 / 021 / 023-026 / 035 / 022 / player_stat_update second wave = reserve
- automation.toml への cron 登録(Phase 次便)
- quality-gmail digest 拡張(029 の 4 行意味固定を守る)
