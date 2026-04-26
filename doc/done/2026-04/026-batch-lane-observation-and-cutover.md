# 026 — Batch レーンの観測と段階切替

**フェーズ：** 固定版 Batch の観測と拡大条件  
**担当：** Codex B  
**依存：** 023, 025

---

## 概要

Gemini 2.5 Flash Batch API を固定版レーンへ補助導入した後、コスト削減だけでなく品質悪化が無いかを観測し、どこまで対象を広げるかの切替条件を決める。
正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §7 / §9。親チケットは `doc/015` (`6e9e847`) / `doc/019` (`07e5279`) / `doc/023` / `doc/025`。

---

## 決定事項

### 観測項目

- `batch_success_rate` / `fallback_rate` / `result_latency` / `quality_monitor` flag 増減 / template 崩れ件数 / user review 時間を固定観測項目とする。
- 計測基盤は `doc/015` の Observation Ticket 5 軸を流用し、`quality-monitor` / `quality-gmail` / `draft-body-editor` と別系統の監視は作らない。
- Batch 由来 Draft の `quality_monitor` flag 率は非 Batch と比較し、`quality-monitor` の継続生成ライン上で `[src:batch]` として分別する。乖離が 10% 以上なら Observation Ticket を起票する。
- review 時間の増加は許容するが、全体 lead time が同期固定版レーンの 150% を超えたら対象 subtype を縮小する。
- `live_anchor` / `postgame` の速報 lead time は Batch 観測の評価対象に含めず、速報運用の主系は同期固定版レーンのまま維持する。

### 切替段階

- `CORE_SUBTYPES` は `pregame / postgame / farm / fact_notice / live_anchor` を維持し、Batch は `source_trust` が `primary tier` の固定版レーンだけに段階導入する。
- Stage 1:
  `doc/019` の 3 カード仕様に合わせ、番組情報 / 公示 / 予告先発だけを Batch 対象とする。`fact_notice` と `pregame` の範囲に限り、公示済みの固定版レーンで観測する。
- Stage 2:
  直近 2 週間で `batch_success_rate` 95% 以上、`fallback_rate` 10% 未満、quality flag 率乖離 5% 未満、template 崩れ週 3 件以下を維持した場合のみ、二軍成績と定型試合前まとめを追加する。
- Stage 3:
  Stage 2 が安定した場合のみ野球データを追加する。ここでも固定版レーンだけを対象とし、AIエージェント版へは拡張しない。
- `postgame` / `live_anchor` / 複数 source 統合記事 / review / repair 前提の記事は Stage を問わず Batch 対象外とし、AIエージェント版または同期固定版レーンで扱う。

### 失敗時

- `fallback_rate` が 20% を超えた subtype は Batch 対象から外し、既存同期固定版レーンへ戻す。Batch job の全停止はせず、subtype 単位で縮退する。
- Batch 由来 Draft の `quality_monitor` flag 率が非 Batch 比で +10pt を 3 日連続超過した場合は Stage を 1 段戻す。template 崩れが週 5 件を超えたカード型も対象外にし、`doc/015` Observation Ticket 経由で user 最小判断へ上げる。
- `result_latency` が記事締切超過を週 3 回以上起こした subtype は対象外とする。短納期の `pregame` と発表 2 時間以内の公示は Stage を問わず同期固定版レーンへ戻す。
- latency 超過した Batch 結果は `doc/023` の fallback と整合させて破棄し、二重 draft は作らない。

### 非機能制約

- `quality-monitor` / `quality-gmail` / `draft-body-editor` は参照のみとし、Gmail / SMTP / sendmail / scheduler / env / secret / automation は本便で触らない。
- Batch 観測は既存 automation の計測出力を参照するのみとし、新しい mail / 通知チャネル / flag / config / scheduler は追加しない。
- 通知と監視の主系は既存 `quality-gmail` / `quality-monitor` のままとし、Batch 導入で置換しない。Batch 専用通知は作らず、Observation Ticket に集約し、published write もしない。

---

## TODO

### 観測項目

【×】見るべき指標を固定する  
【×】quality_monitor とどう突き合わせるか決める  
【×】review 時間の扱いを決める  

### 切替段階

【×】Stage 1 / 2 / 3 を定義する  
【×】対象拡大の条件を決める  
【×】AIエージェント版へ拡張しないことを明記する  

### 失敗時

【×】fallback 率が高い場合の戻し方を決める  
【×】quality flag 増加時の縮退条件を決める  
【×】latency 超過時の扱いを決める  

### 非機能制約

【×】mail / automation を触らないことを明記する  
【×】通知の主系を変えないことを明記する  

---

## 成功条件

- Batch 導入後に何を見ればよいかが明確  
- どこまで広げてよいかの切替条件がある  
- 失敗時に安全に元へ戻せる  
