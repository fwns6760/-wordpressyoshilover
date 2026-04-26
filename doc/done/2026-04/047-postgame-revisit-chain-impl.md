# 047 — 020 postgame 連鎖 impl(1 試合から派生記事で再訪理由を増やす)

**フェーズ：** のもとけ型再訪導線の中核 impl(020 spec の impl 便)
**担当：** Codex A(2026-04-22 owner 整流、046 first wave 延長の route 判定層 hook が実装重心のため。Codex B 領域=prompt / validator / body / subtype 境界 / repair playbook は不可触として維持)
**依存：** 020 spec(accepted、reference)、012(game_id)、013(AIエージェント版 review)、028 T1 trust、037 pickup parity、046 first wave accepted(`8ef8330` + `069daa6`)
**状態：** READY(doc+impl 一体化、46 観測 gate pass 後に fire)

---

## why_now

- 046 first wave で `postgame_result` が fixed_primary に昇格し、1 試合 1 記事の基盤は閉じた。
- ただし 1 試合 1 記事で終わらせると再訪理由が単発で、のもとけ型の複数再訪導線が作れない。
- 020 spec(`doc/020-postgame-revisit-chain.md`、TODO 全 【×】= 決定済み / impl 未)は `postgame` を起点に主役選手 / 監督コメント / transaction / データの 4 派生を 24h window 内に作る contract を固定済み。
- user 固定優先順位(2026-04-22): **047 → 062 → 060 並走 → 061 後ろ**。「先に記事の枝を増やす、次に巡回感、SNS / SEO は土台の上」の意図に合致。
- 047 は 020 spec を src に落として再訪理由を実装層で発生させる本線。046 の次弾として「Draft 本数増」を直接稼ぐ。

## purpose

- 020 spec の 4 派生条件(主役選手 / 監督コメント / transaction / データ)を **候補 emit** 層として src に足す。
- `postgame` accept 後 24h window 内だけ派生候補を emit する(乱発しない)。
- 1 試合 **最大 4 本**の派生上限を守り、超過分は次試合まで繰り延べる。
- primary tier(球団公式 / NPB 公式 / 球団公式発表)確定時だけ fixed_primary に、secondary / rumor は `deferred_pickup` 維持。
- 派生候補の `candidate_key` を 046 first wave の dedupe と整合させ、重複は `duplicate_absorbed`。
- 本便で WP draft 書込までを含む(fixed lane と同じ経路で Draft 作成)。published 書込は禁止。

## scope

### 実装対象(最小 scope)

- `src/postgame_revisit_chain.py`(新規)または `src/tools/run_notice_fixed_lane.py` 内に派生候補 emit module を追加
  - 関数名は Codex 判断。以下は指針:
    - `aggregate_postgame_derivatives(postgame_candidate, window_hours: int = 24) -> list[DerivativeCandidate]`
    - `_check_player_highlight(...)` / `_check_manager_comment(...)` / `_check_transaction(...)` / `_check_data_milestone(...)`
- `src/tools/run_notice_fixed_lane.py` の route 判定層に、`postgame_result` accept 時に `aggregate_postgame_derivatives()` を呼ぶ hook を追加
- 派生 candidate は 046 と同じ `candidate_key` 生成規約 + route evidence 形式で stdout に emit
- 派生 subtype は `fact_notice` / `farm`(020 spec 準拠)で切り出し。新 subtype は足さない

### 派生条件(020 spec §派生条件、そのまま impl)

- **主役選手派生**: 記事内 weight 最上位選手タグが 1 件以上 + 直近 3 試合で同選手派生未発行 + 勝敗直結 or 特筆成績
  - weight 分散 / 凡記録のみ → 派生しない
- **監督コメント派生**: 戦術 / 選手評価 / 次戦方針のいずれか明確 + 引用長 300 字以上目安 + primary tier
  - 「良かった」等の薄いコメントは切り出さない
- **transaction 系派生**: 試合当日 or 直後 24h 以内 + 公示 / 故障 / 登録・抹消 / 契約発表 + primary tier
  - rumor / unknown tier のみ → AI エージェント版へ差し戻し
- **データ系派生**: チーム新記録 / 個人節目 / リーグ上位到達 + primary tier
  - タグ「野球データ」+ 該当選手タグ必須、単なる打率推移では派生しない

### 非機能(020 spec §非機能、そのまま impl)

- 1 試合 1 記事で終わらせない: `postgame` 起点に最大 **4 本**派生可
- `live` 中は `live_anchor` 1 本の update のみ、派生は `post` state 後だけ
- 4 本超過は次試合まで繰り延べ、本便内では emit しない
- mail / automation / gmail / SMTP / sendmail / scheduler / env / secret は一切触らない

### 呼び出し経路

- CLI エントリ: 既存 `src/tools/run_notice_fixed_lane.py` の route 判定層に統合(新 CLI 追加しない)
- `postgame_result` が `route=fixed_primary` で accept された時、同 run 内で派生候補 emit を走らせる
- 派生候補は `route=fixed_primary_derivative` / `route=deferred_pickup_derivative` の 2 outcome を追加
  - trust 条件 pass → `fixed_primary_derivative`(WP draft 作成)
  - trust 条件 fail → `deferred_pickup_derivative`(Draft 作らず、AI エージェント版に回す)

### tests 追加(最低セット)

- 4 派生条件それぞれで primary tier pass → fixed_primary_derivative emit(4 pattern)
- 4 派生条件それぞれで secondary / rumor → deferred_pickup_derivative(4 pattern)
- 1 試合 4 本上限到達 → 5 本目以降は emit されない(1 pattern)
- `live_anchor` 中 state では派生 emit されない(1 pattern)
- 24h window 外の postgame accept → 派生 emit されない(1 pattern)
- 派生 candidate_key の dedupe(046 の dedupe と衝突しない、1 pattern)
- 薄い監督コメント(300 字未満)は派生しない(1 pattern)
- weight 分散(最上位選手不明瞭)は主役選手派生しない(1 pattern)
- 最低 **12 パターン**追加

### 不可触

- route 判定の**母体**(028 T1 assert narrow / 037 pickup boundary / 046 first wave の 4 家族昇格分岐)
- `src/source_trust.py` / `src/source_id.py` / `src/game_id.py`(呼ぶだけ、diff 0)
- `src/eyecatch_fallback.py`(041)
- Codex B 領域: `src/body_validator.py` / `src/title_validator.py` / `src/source_attribution_validator.py` / `src/fixed_lane_prompt_builder.py`(diff 0)
- `src/repair_playbook.py`(040、触らない)
- 038 ledger schema(17 field 不変)
- 045 optional intake path
- WP published 書込(Phase 4 まで禁止)
- automation.toml / scheduler / `.codex/automations/**` / env / secret / quality-gmail / quality-monitor / draft-body-editor
- 060 SNS contract(doc-only、047 と並走だが触らない)
- 020 spec doc(reference 保持、本便は impl 側のみ)

## non_goals

- 020 spec の決定事項の変更(派生条件数値 / 4 本上限 / 24h window の書換)
- 新 subtype の追加(派生は既存 `fact_notice` / `farm` で切り出す)
- AI 画像生成 / 新 external fetcher / 新 API client / 新 scraper
- 新 Python dep(既存 import で足りる)
- 022 multisource merge / 023-026 Batch API の前倒し
- 046 first wave 4 家族の trust 条件 / route 判定層の書換
- `player_stat_update` second wave の同時着地(本便 scope 外、別便)
- 060 SNS 投稿連携(061 以降)

## success_criteria(3 点 contract)

**一次信号(accept 根拠)**

- **着地**: `git log -1 --stat` で派生 module + tests + route hook の追加のみ、`git status --short` clean
- **挙動**: `pytest` 全 pass + CLI 実行で `postgame_result` accept 時に派生候補 route evidence が emit される
  - stdout に `route=fixed_primary_derivative subtype=<fact_notice|farm> family=<player|manager|transaction|data> candidate_key=<key>` 相当が出る
  - 4 本上限 + 24h window + trust 条件が test で confirm される
- **境界**: 不可触リストに diff なし(028 T1 / 037 / 046 route 層 / source_trust / source_id / game_id / Codex B 領域 / repair_playbook / eyecatch_fallback / 060 / 020 spec doc すべて zero diff)

**二次信号(事後記録、accept 根拠にしない)**

- 実運用で 1 試合あたり 1-4 本の派生 Draft が生成される観測(Claude 手動週次)

## acceptance_check(自己追認)

- `grep -r 'postgame_result\|ROUTE_FIXED_PRIMARY' src/` で 046 first wave 判定ロジックに diff が無い
- `grep -r 'source_trust\|source_id\|game_id' src/postgame_revisit_chain.py` で呼ぶだけ(書換無し)
- `grep -r 'subprocess\|requests\|urlopen' src/postgame_revisit_chain.py` で新 external call が無い
- `git diff HEAD~1 -- src/source_trust.py src/source_id.py src/game_id.py src/eyecatch_fallback.py src/repair_playbook.py` で差分 0
- `git diff HEAD~1 -- src/body_validator.py src/title_validator.py src/source_attribution_validator.py src/fixed_lane_prompt_builder.py` で差分 0
- `git diff HEAD~1 -- doc/020-postgame-revisit-chain.md doc/060-sns-dual-account-draft-era-bridge.md` で差分 0
- published 書込経路が呼ばれていない(WP POST/PUT は draft status のみ)
- pytest 全 pass
- 最低 12 パターン tests 追加

## fire 前提 / stop 条件

### fire 前提(046 観測 gate、2026-04-22 user 指示)

**既定 gate = A、gate B は補助扱い(user 明示時のみ)**(2026-04-22 user 指示):

- **gate A(既定 / 時間 gate)**: 046 accept(`069daa6`、2026-04-22 08:13 JST)から **48 時間経過** + **critical regression 0 件** → そのまま fire(blanket go、user 追加確認不要)
- **gate B(補助 / 観測 gate)**: 046 first wave manual review **10 件到達** + **critical regression 0 件** → **user から「10 件 OK」の明示発声があった時のみ** gate A より早くても fire 可。Claude 側から gate B を根拠に前倒し fire しない

**critical regression の定義**(3 項目、1 件でも観測されたら fire 保留):

1. trust 外 source が `fixed` lane に昇格している
   - ledger 検出キー: `source_trust != primary && chosen_lane = fixed`(ledger schema 17 field の `source_trust` + `chosen_lane` の組で判定、`route_outcome` は ledger schema に含まれないため ledger では見ない)
   - stdout route evidence(`route=fixed_primary` が trust 外 source で出る)は一次信号として併用
2. published write が発生している(Draft 以外への書込)
3. duplicate rate > 10%(046 first wave 4 家族の重複率が全 Draft の 10% を超える)

### stop 条件

- 046 first wave 4 家族の route 判定層への diff
- 028 T1 assert narrow / 037 pickup boundary / 045 optional intake への diff
- `src/source_trust.py` / `src/source_id.py` / `src/game_id.py` への書換
- Codex B 領域 / `src/repair_playbook.py` / `src/eyecatch_fallback.py` への diff
- 038 ledger schema の書換(17 field 不変)
- WP published 書込
- automation.toml / scheduler / cron 登録
- 新 external dep 追加
- pytest 失敗

## TODO(起票時点)

【】`src/postgame_revisit_chain.py`(or `run_notice_fixed_lane.py` 内)に派生候補 emit module を追加
【】4 派生条件(主役選手 / 監督コメント / transaction / データ)を 020 spec §派生条件どおり実装
【】`postgame_result` accept 時に派生 emit を呼ぶ route hook を追加
【】4 本上限 / 24h window / primary tier 条件を実装
【】派生 route outcome(`fixed_primary_derivative` / `deferred_pickup_derivative`)を stdout に emit
【】`candidate_key` 生成を 046 dedupe と整合させる
【】tests 最低 12 パターン追加(4 派生 × 2 trust + 4 上限 / window / dedupe / 薄コメ / weight 分散)
【】020 spec doc は触らない(reference 保持)
【】046 first wave 4 家族の route 層 / 028 T1 / 037 pickup / 060 SNS contract に diff を入れない
【】published 書込 / automation 登録しない
【】doc/README.md に 047 行追加を cleanup commit で吸収

## 本便の scope 外(再掲、混線防止)

- 048 repair playbook ledger 連携 formatter(B 補修線 HOLD、047 accept 後に HOLD 解除判定)
- 062 comment-first topic hub contract(047 の次、別起票)
- 060 SNS contract(doc-only 並走、本便で触らない)
- 061 自動投稿実装(060 gate pass まで止める)
- `player_stat_update` second wave(別番号で後続)
- 041 / 045 / 039 / 042 / 043 / 044 の独立 observation(凍結)
- 020 / 021 / 023-026 / 035 / 022 = reserve 据え置き
