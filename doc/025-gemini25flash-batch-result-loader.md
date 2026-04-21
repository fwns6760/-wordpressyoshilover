# 025 — Gemini 2.5 Flash Batch 結果の Draft 取り込み

**フェーズ：** 固定版 Batch 出力の materialize  
**担当：** Codex A  
**依存：** 023, 024

---

## 概要

正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §9。親チケットは `doc/011` (`4dc0b2b`) / `doc/014` (`2d92405`) / `doc/019` (`07e5279`) / `doc/023` (`a6685c1`) / `doc/024`、handoff docs 正本は `/home/fwns6/code/baseballwordpress/docs/handoff/` 配下。
Gemini 2.5 Flash Batch API の結果 JSONL を受け取り、固定版レーンの Draft 候補へ戻す。
ここでは publish しない。Draft 生成までを扱う。

---

## 決定事項

### 結果の読み方

- join key:
  request 側の `candidate_id` を一意 join key に固定する。`source_id` は副 key とし、`doc/024` の `manifest` にある `candidate_id` 一覧 / sha256 で請求側と突合する。
- manifest 不一致:
  `manifest` に存在しない response は破棄する。`candidate_id` 破損時だけ `source_id` を補助照合に使い、join 不能なら materialize しない。
- 成功:
  Batch response が完全で、`doc/019` card と `doc/011` 固定版テンプレの必須キーを満たすものだけ Draft materialize 候補へ渡す。`CORE_SUBTYPES` は `pregame / postgame / farm / fact_notice / live_anchor` を維持し、subtype / category / tag は `doc/014` / `doc/019` の規則に従う。
- 失敗 / 欠落:
  timeout / unreadable / malformed / response 欠落 `candidate_id` は `doc/023` fallback 準拠で既存同期固定版レーンへ戻す。失敗 response は破棄し、二重 Draft は作らない。

### Draft 化

- 出力境界:
  出力は Draft のみとし、WordPress 反映は `draft_status=draft` 固定の Draft 作成までに限定する。publish / published write は本便 scope 外とする。
- metadata:
  Draft metadata に `batch_source=batch` / `batch_job_id` / `candidate_id` を残す。人間編集面には出さず、Observation Ticket と `doc/015` / `doc/026` で `[src:batch]` として分別観測できるようにする。
- 差し戻し:
  `source_trust` が `primary tier` 未満、rumor 混入、title と本文の主事実不整合、`doc/019` card / `doc/011` 固定版必須キー欠落は差し戻す。review / repair が要るものは AIエージェント版、テンプレ再生成で足りるものは同期固定版レーン、致命的崩れは破棄して user 手動編集に任せない。

### 非機能制約

- 不可触範囲:
  `quality-gmail` / `quality-monitor` / `draft-body-editor`、Gmail / SMTP / sendmail / scheduler / env / secret は触らない。Batch 結果取り込みは既存 automation の出力参照だけとし、新規 automation は作らない。
- 主系維持:
  Batch 成功でも既存同期固定版レーンは止めない。`doc/023` fallback と `doc/026` の縮退条件に備え、Batch は補助レーン、主系は同期 + AIエージェント版とする。

---

## TODO

### 結果の読み方

【×】result JSONL の join key を固定する  
【×】成功時の扱いを決める  
【×】失敗 / 欠落時の fallback を決める  

### Draft 化

【×】Draft のみを出力にすることを明記する  
【×】batch 経由の識別情報をどう残すか決める  
【×】差し戻し条件を決める  

### 非機能制約

【×】mail / monitor / editor を触らないことを明記する  
【×】既存同期経路を残すことを明記する  

---

## 成功条件

- Batch 結果を Draft に戻す流れが説明できる  
- 失敗時の fallback がある  
- publish 境界を越えない  
