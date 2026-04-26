# 046 — 037 follow-up: pickup parity first wave(4 family)を fixed lane Draft 候補へ昇格

**フェーズ：** 037 follow-up(のもとけ比 Draft 本数増の挙動化)
**担当：** Codex A
**依存：** 037 accepted(aac632c)、045 accepted(6246f8a)、028 impl accepted(c407415)、041 accepted(854b616)、014 / 019

---

## why_now

- 037 で parity 5 family の pickup contract / `deferred_pickup` route outcome は入ったが、fixed lane で Draft 化されるのは 028 の 4 family(program_notice / transaction_notice / probable_pitcher / farm_result)+ NPB 公示 1 件止まりで、parity family は deferred のまま Draft 本数が増えていない。
- 045 で non-NPB intake 経路が通った今、`deferred_pickup` に滞留している pickup を **trust 条件合致時だけ** `fixed_primary` に昇格させれば、028 T1 / 037 pickup contract を崩さずに Draft 量を増やせる状態になっている。
- 25 Draft/day 目標(037 で固定)に対し、現状は Draft 63175 級(1 件/day)で決定的に不足。のもとけ型に近づけるためには「Draft 本数を直接増やす」挙動化が次の 1 本として唯一の優先。
- 037 の「collect wide / assert narrow」境界を維持したまま、first wave 4 家族だけを fixed_primary 昇格対象にする。

## purpose

- parity 5 family のうち first wave 4 家族を、trust 条件合致時だけ `deferred_pickup` から `fixed_primary` へ昇格させる。
- 対象は `lineup_notice` / `comment_notice` / `injury_notice` / `postgame_result` の 4 家族。`player_stat_update` は second wave として 037 scope のまま deferred 維持。
- trust tier 条件は 037 の pickup boundary に完全準拠し、**trust 外の intake item は引き続き `deferred_pickup`** に残す。
- 028 T1 assert narrow / 037 pickup contract / candidate_key dedupe / source_bundle 吸収ロジックは書き換えない。挙動の切替点だけを足す。

## scope

### route 判定層の昇格

- `src/tools/run_notice_fixed_lane.py` の route 判定層(028 の 5 route outcome 判定経路)で、4 家族に対して trust 条件合致時に `fixed_primary` を返す分岐を追加する。
- 対象 4 家族と trust 条件(037 pickup boundary 準拠):
  - `lineup_notice`: **公式 X(球団公式アカウント)** + **球団公式 announcement** まで T1 として `fixed_primary`
  - `comment_notice`: **球団公式** + **公式 X** + **主要媒体引用** + **TV・ラジオ発言** まで T1 として `fixed_primary`
  - `injury_notice`: **球団公式発表** + **監督・コーチコメント** まで T1 として `fixed_primary`(主要紙の怪我情報は対象外 = deferred 継続)
  - `postgame_result`: **球団公式** + **公式 X** + **NPB 公式データ** まで T1 として `fixed_primary`
- trust 条件外(secondary / rumor / unknown、または 037 pickup boundary の範囲外)は引き続き `deferred_pickup` を返す。
- trust 判定は `src/source_trust.py` の既存 tier + 037 で導入した source_kind を **呼ぶだけ**(tier 追加 / 書換なし)。

### Draft 生成経路

- 昇格した intake item は既存の fixed lane Draft 作成経路(027 / 028 で確立、045 で optional intake 接続済み)を通って **WP draft のみ** 生成する。
- 親カテゴリは `読売ジャイアンツ` 固定(014 / 019 準拠)。
- published 書込は Phase 4 まで禁止(028 / 027 と同じ)。
- 041 structured eyecatch fallback は既存 hook 経路で自動発動(本便で eyecatch 経路は触らない)。

### duplicate / candidate_key 契約

- 4 家族の candidate_key 生成は 037 で既に定義済み(game_id + 区別子)。本便は呼ぶだけ。
- 028 の 5 route outcome(`fixed_primary` / `await_primary` / `duplicate_absorbed` / `ambiguous_subject` / `out_of_mvp_family`)の判定ロジックは書き換えない。4 家族の trust 合致時だけ `fixed_primary` を返す分岐を足す。
- 同一 candidate_key の 2 件目以降は現状通り `duplicate_absorbed` で吸収される(挙動不変)。

### 不可触

- 028 T1 assert narrow / tier 判定(`src/source_trust.py`)
- 037 pickup contract / `deferred_pickup` route outcome / candidate_key dedupe / source_bundle 吸収
- 045 optional intake path(`_load_optional_intake_items()` / `_resolve_optional_intake()`)
- 041 structured eyecatch fallback(`src/eyecatch_fallback.py`)
- `src/game_id.py` / `src/source_id.py` / `src/source_trust.py` の採番・判定ロジック(呼ぶだけ)
- candidate_key 生成(037 で固定済)
- WP published 書込(Phase 4 まで禁止)
- automation.toml / scheduler / env / secret / quality-gmail / quality-monitor / draft-body-editor
- prompt / template / body validator / title validator / attribution validator(Codex B 領域、本便で触らない)
- 022 multisource merge / 023-026 Batch API / 020 postgame revisit / 021 farm roster loops

## non_goals

- `player_stat_update` の昇格(data feed 整備後の second wave、本便 scope 外)
- 新 trust tier 追加 / secondary・rumor を T1 に上げる
- 037 pickup boundary の緩和 / 拡張
- 主要紙 injury 情報の fixed lane 断定(agent lane 領域)
- 022 multisource merge / 023-026 Batch API の前倒し
- prompt hardening / template hardening(Codex B follow-up は実運用で明確に不足が観測された時だけ別便で起票、本便では着手しない)
- published 書込 / SNS 自動投稿 / X 文面拡張
- 新 external fetcher / 新 API client / 新 scraper / 新 RSS subscribe
- AI 画像生成
- automation.toml / scheduler / env / secret / quality-gmail / quality-monitor / draft-body-editor の変更
- doc/README.md の在庫表更新以外の書換(本便 cleanup commit として 1 行足すのみ)

## success_criteria

**一次信号(本便の accept 根拠)**

- `src/tools/run_notice_fixed_lane.py` の stdout に、4 家族それぞれで `fixed_primary` route evidence(例: `route=fixed_primary subtype=lineup_notice candidate_key=... source_kind=... trust_tier=primary`)が出ること。
- 同じ run で **WP draft が新規作成**される(`[WP] Draft 作成 post_id=<N> subtype=...` 系の既存 log 行で確認)。
- trust 条件外 intake item は stdout に `route=deferred_pickup` が出ており、WP draft を作らないこと。
- default NPB path(no-arg 実行)の既存挙動が壊れていないこと(028 / 037 / 045 / 041 の tests pass)。

**二次信号(事後記録、本便の accept 根拠にしない)**

- 038 ledger に 4 家族(NPB 公示以外)の entry が 1 件以上事後記録される(Claude 手動追記、本便の acceptance には使わない)。

## acceptance_check

- tests 追加(4 家族 × 3 分岐 = 12 パターン):
  - `lineup_notice` / `comment_notice` / `injury_notice` / `postgame_result` それぞれで、
    - trust 条件合致(T1)→ `fixed_primary` を返し Draft 生成経路に進む
    - trust 条件不足(secondary / rumor / unknown / boundary 外)→ `deferred_pickup` を返す
    - candidate_key 重複 → `duplicate_absorbed` を返す(028 挙動不変)
- default NPB path / 028 5 route outcome / 037 pickup contract / 045 optional intake path / 041 eyecatch の既存 tests が全 pass。
- `grep -r 'T1\|TIER_PRIMARY\|assert_narrow' src/` で 028 T1 assert narrow の判定ロジックに diff が無いこと。
- `grep -r 'candidate_key\|source_bundle' src/` で 037 pickup contract に diff が無いこと。
- `grep -r 'subprocess\|requests\|urlopen' src/tools/run_notice_fixed_lane.py` で新 external call が追加されていないこと。
- `git diff HEAD~1 -- src/source_trust.py src/source_id.py src/game_id.py` で差分 0。
- `git diff HEAD~1 -- src/body_validator.py src/title_validator.py src/source_attribution_validator.py src/fixed_lane_prompt_builder.py` で差分 0(Codex B 領域不可触)。
- published 書込経路が呼ばれていないこと(WP POST/PUT は draft status のみ)。
- pytest 全 pass。

## fire 前提 / stop 条件

### fire 前提(すべて達成)

- 037 accepted(`aac632c`)
- 045 accepted(`6246f8a`)
- 028 impl accepted(`c407415`)
- 041 accepted(`854b616`)
- 038 ledger 運用中(Claude 管理)

### stop 条件(いずれかを観測した時は即停止、accept しない)

- trust 外(rumor / unknown / secondary / 037 pickup boundary 範囲外)が `fixed_primary` で Draft 化
- 日次 duplicate rate が **10% を越える**
- 028 T1 assert narrow / 037 pickup contract / candidate_key dedupe / source_bundle 吸収が書換わる
- `src/source_trust.py` / `src/source_id.py` / `src/game_id.py` に diff が入る
- Codex B 領域(validator / prompt builder / template)に diff が入る
- published 書込が発生
- 新 external fetcher / 新 API client / 新 scraper が追加される
- pytest 失敗

## TODO(起票時点)

【】`src/tools/run_notice_fixed_lane.py` の route 判定層に 4 家族の `fixed_primary` 昇格分岐を追加する(trust 条件合致時のみ)
【】trust 条件は 037 pickup boundary に完全準拠(lineup=公式 X + 球団公式 / comment=球団公式 + 公式 X + 主要媒体 + TV・ラジオ発言 / injury=球団公式 + 監督・コーチコメント / postgame_result=球団公式 + NPB 公式)
【】trust 外は引き続き `deferred_pickup` に残す
【】`src/source_trust.py` / `src/source_id.py` / `src/game_id.py` の判定ロジックに diff を入れない(呼ぶだけ)
【】`player_stat_update` は本便で触らない(second wave、037 scope のまま deferred 維持)
【】028 T1 assert narrow / 037 pickup contract / candidate_key dedupe / source_bundle 吸収 / 045 optional intake path / 041 eyecatch に diff を入れない
【】Codex B 領域(validator / prompt builder / template)に diff を入れない
【】親カテゴリ `読売ジャイアンツ` 維持、WP draft のみ書込、published 書込なし
【】新 external fetcher / 新 API client / 新 scraper / 新 RSS subscribe / AI 画像生成を追加しない
【】stdout に `route=fixed_primary subtype=... candidate_key=... source_kind=... trust_tier=...` が出るようにする(一次信号)
【】tests を 4 家族 × 3 分岐(fixed_primary / deferred_pickup / duplicate_absorbed)= 12 パターン追加する
【】default NPB path + 028 + 037 + 045 + 041 の既存 tests 全 pass を確認する
【】doc/README.md に 046 行を追加し cleanup commit として吸収する(Claude 側で commit 不可)

## 成功条件

- 本便で 4 家族(lineup_notice / comment_notice / injury_notice / postgame_result)が trust 条件合致時に fixed lane Draft として生成される。
- trust 外は deferred 維持で、assert narrow が壊れていない。
- 028 T1 / 037 pickup contract / 045 optional intake / 041 eyecatch の既存挙動が不変。
- 25 Draft/day に向けて increment の土台が入る(実運用観測は本便 scope 外、事後記録)。
- Codex B 領域に入らず、Codex A 1 本で完結(prompt hardening 要件が実運用で明確化された時だけ後続 Codex B follow-up を別便で切る)。

---

## 本便の scope 外(再掲、混線防止)

- 旧 doc/046(E1 game_id/source_id consumer promotion)/ 旧 doc/048(playbook ledger formatter)の未発火 draft は本便で 046 番号を再定義、048 番号はリリース(再定義待ち)
- 020 / 021 / 023-026 / 035 = reserve 据え置き
- 041 / 045 / 039 / 042 / 043 / 044 = 独立 observation として凍結(本便と独立並走)
- 022 multisource merge / player_stat_update second wave(047 以降で別途検討)
- push 14 commits(DNS blocker、user 判断事項、隔離維持)
- Codex B lane(048 以降)= prompt hardening の不足が実運用で明確化した時だけ別便で起票
