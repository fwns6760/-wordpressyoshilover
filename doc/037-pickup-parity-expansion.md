# 037 — pickup parity expansion

**フェーズ：** pickup 条件の parity 拡張  
**担当：** Codex A  
**依存：** 014, 023, 027, 028, 011, 019

---

## why_now

- 028 実装で fixed lane runner の Draft 断定経路は 4 family に固定されたが、のもとけ比では pickup trigger 種がまだ狭い。
- 027 の実運用 success と 036 の prompt hardening を前提に、今は Draft 断定ルールを崩さず pickup 層だけを厚くできる。
- 037 は `collect wide / assert narrow` を runner の pickup 層へ戻し込み、source 種を広げても duplicate flood を `candidate_key` で抑える便である。

## purpose

- `official / npb / major RSS / team X / reporter X / program / farm` を同一 runner の pickup 層で受け、candidate normalize と evidence bundle を一箇所でそろえる。
- Draft 断定は 028 の `T1 のみ` を維持し、037 は pickup 成功と Draft 未生成を `deferred_pickup` で明示する。

## scope

### pickup source 種

- pickup source 種は次で固定する。
  - `official_web`
  - `npb`
  - `major_rss`
  - `team_x`
  - `reporter_x`
  - `program_table`
  - `farm_info`
  - `tv_radio_comment`
  - `comment_quote`
  - `player_stats_feed`
- trust tier は 028 のまま据え置く。
  - `T1`: official web / npb / 公式番組表
  - `T2`: major RSS / team X
  - `T3`: reporter X

### event_family 拡張

- 028 の 4 family はそのまま維持する。
  - `program_notice`
  - `transaction_notice`
  - `probable_pitcher`
  - `farm_result`
- parity expansion 用 family は次を追加する。
  - `lineup_notice`
  - `comment_notice`
  - `injury_notice`
  - `postgame_result`
  - `player_stat_update`
- `roster_change` は別 family を増やさない。028 の `transaction_notice` が同じ duplicate boundary をすでに持つため、本便では別 key を作らず disjoint rule を守る。

### candidate_key

- 028 の 4 family key は変更しない。
- parity expansion family の key は次で固定する。
  - `lineup_notice:{game_id}:{lineup_kind}`
  - `comment_notice:{notice_date}:{speaker}:{context_slug}`
  - `injury_notice:{notice_date}:{subject}:{injury_status}`
  - `postgame_result:{game_id}:{result_token}`
  - `player_stat_update:{stat_date}:{subject}:{metric_slug}`
- 同一 `candidate_key` の別 source は新規 Draft を増やさず、`source_bundle` / `trigger_only_sources` に吸収する。

### trust + subtype route

- fixed lane Draft 作成は 028 の 4 family に限定し、`lane_target=fixed_lane` を維持する。
- parity expansion family は pickup 正規化だけを担当し、`lane_target=ai_lane` で束ねる。
- route outcome は 028 の 5 種を維持し、pickup 成功 + Draft 未生成の補助ラベルとして `deferred_pickup` を追加する。
  - `await_primary + deferred_pickup`: fixed family だが T1 不足
  - `duplicate_absorbed + deferred_pickup`: 同一 key の既存 Draft あり、または同一 key の別 source を bundle 吸収
  - `deferred_pickup`: parity family を pickup したが、この runner では Draft を作らない
- `rumor` / `unknown` は fixed lane に直接入れない。

### pickup boundary

- `comment_notice`: pickup は広く取るが、本文先頭近くに `誰が / どこで / 何を言ったか` を置ける source だけを候補として残す。
- `injury_notice`: fixed lane で断定してよい境界は `球団公式発表 + 監督・コーチコメントまで`。主要紙は pickup して bundle には入れるが、単独で fixed lane 断定しない。
- `player_stat_update`: `記録更新 / 昇格圏 / 再訪理由あり` のときだけ候補化し、日次の数合わせには使わない。

### taxonomy

- 親カテゴリ `読売ジャイアンツ` を維持する。
- 細分類は child category と tag に寄せ、014 / 019 の「カテゴリは粗く・タグは細かく」を崩さない。

### duplicate flood 抑制

- pickup source を増やしても dedupe 軸は `event_family + candidate_key` で一意化する。
- 同一 key の別 source は `source_kind` ごと bundle に保持し、route は 1 candidate あたり 1 本に収束させる。

## non_goals

- 028 の Draft 断定ルール変更 (`T1 のみ` を維持)
- 新 source trust tier 追加
- AI lane 実装
- `published` 書込
- `automation.toml` / scheduler / env / secret / mail / `quality-gmail` / `quality-monitor` / `draft-body-editor` の変更
- Gemini 以外 LLM 追加

## TODO

【×】pickup source 種を fixed lane runner の pickup 層で固定する  
【×】028 の 4 family に加える parity expansion family を固定する  
【×】parity expansion family ごとの `candidate_key` を disjoint で固定する  
【×】trust tier + subtype による `fixed_lane / ai_lane` route を固定する  
【×】`deferred_pickup` route outcome を補助ラベルとして固定する  
【×】親カテゴリ `読売ジャイアンツ` 維持を明記する  
【×】`collect wide / assert narrow` を pickup contract として明記する  
【×】duplicate flood を `candidate_key` と bundle 吸収で抑制する方針を明記する

## success_criteria

- 追加 5 family の `candidate_key` が tests で固定される。
- T1 / T2 / T3 の分岐で `fixed_primary` と `deferred_pickup` が観測される。
- 同一 `candidate_key` の別 source が bundle に吸収され、親カテゴリ `読売ジャイアンツ` が維持される。
- 028 の 4 family create path と既存 validator/prompt builder contract を壊さない。
