# 028 — fixed lane intake / trust / route を 027 注入用の短メモとして固定

**フェーズ：** fixed lane Draft 本線の前提固定  
**担当：** Codex A  
**依存：** 011, 014, 019

---

## 概要

- `027` を旧来の「source を狭くする」前提で実装させないため、fixed lane MVP 向けの `collect wide / assert narrow` を短く固定する。
- この ticket は大設計 doc を増やすためのものではなく、`027` に注入するための短い実装メモである。
- fixed lane では `wide intake -> candidate normalize -> trust / route 判定 -> status=draft POST` の最短経路を支える最小契約だけを定義する。

## 決定事項

### collect wide / assert narrow

- 収集は広く行う。対象は `公式Web / npb.jp / 主要媒体RSS / 球団X / 記者X / 番組表 / 二軍情報` を含んでよい。
- 断定は狭く行う。fixed lane の本文断定に使ってよいのは `T1` source だけとする。
- `T2` と `T3` は trigger と evidence bundle には使ってよいが、単独では fixed lane Draft を作らない。

### trust tier

- `T1 = 断定可`
  - 公式Web
  - `npb.jp`
  - 放送局公式 / 公式番組表
- `T2 = trigger + bundle 可`
  - 主要媒体RSS
  - 球団X
- `T3 = trigger のみ`
  - 記者X
  - 選手X

### MVP event family

- fixed lane MVP の family は次の 4 つに固定する。
  - `program_notice`
  - `transaction_notice`
  - `probable_pitcher`
  - `farm_result`

### candidate_key

- family ごとの duplicate guard は次で固定する。
  - `program_notice:{air_date}:{program_slug}`
  - `transaction_notice:{notice_date}:{subject}:{notice_kind}`
  - `probable_pitcher:{game_id}`
  - `farm_result:{game_id}`
- 同一 `candidate_key` の別 source は新規 Draft を増やさず、evidence bundle に吸収する。

### route outcome

- route outcome は次で固定する。
  - `fixed_primary`
  - `await_primary`
  - `duplicate_absorbed`
  - `ambiguous_subject`
  - `out_of_mvp_family`

### taxonomy

- `読売ジャイアンツ` は親カテゴリとして残す。
- MVP 実装では既存 child bucket を使い、詳細分類は `011` / `019` の tag ルールで通す。

---

## TODO

【×】`collect wide / assert narrow` を 027 向けに短く固定する  
【×】`T1 / T2 / T3` を fixed lane 向けに明記する  
【×】MVP の 4 event family を固定する  
【×】4 family それぞれの `candidate_key` を固定する  
【×】route outcome を固定する  
【×】`読売ジャイアンツ` 親カテゴリ維持を明記する  
【×】`027` に注入するための短メモであり、大設計 doc を増やさないことを明記する  

---

## 成功条件

- `027` の implementer が user に聞かず fixed lane 候補判定を決められる  
- `T1 / T2 / T3`、4 family、`candidate_key`、`route outcome`、親カテゴリ rule がすべて入っている  
- 本文が `027` に注入できる短さに収まっている  
- docs を増やすための docs になっていない  
