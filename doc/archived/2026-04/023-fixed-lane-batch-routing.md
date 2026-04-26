# 023 — Gemini 2.5 Flash Batch API に流す固定版記事の境界

**フェーズ：** 固定版レーンのコスト最適化  
**担当：** Codex A  
**依存：** 011, 014, 019

---

## 概要

Gemini 2.5 Flash の固定版レーンだけを Batch API に流し、同期呼び出しコストを下げる。
AIエージェント版レーンはそのまま維持し、Batch は補助レーンとして導入する。
正本要件は `/home/fwns6/code/baseballwordpress/docs/handoff/giants_agile_requirements.md` §4 / §9。親チケットは `doc/011` (4dc0b2b) / `doc/014` (2d92405) / `doc/019` (07e5279)。

---

## 決定事項

### Batch 対象

- 対象 subtype:
  `CORE_SUBTYPES` のうち `fact_notice` / `pregame` / `farm` だけを Batch 対象に固定する。`doc/011` の固定版レーン 6 型と `doc/019` の番組 / 公示 / 予告先発カード仕様に合わせる。
- 対象記事:
  番組情報 / 公示 / 予告先発 / 野球データ / 二軍成績 / 二軍結果 / 定型試合前まとめを Batch 対象とする。いずれも固定版レーンでテンプレ再現できる記事に限る。
- Batch 条件:
  `source_trust` が `primary` 相当の `primary tier` で揃い、速報性が低く、AIエージェント版 review が不要な場合だけ流す。`secondary tier` 混在や `rumor` / `unknown` 主体は対象外とする。
- 締切ルール:
  試合開始 1 時間以内の `pregame` / 予告先発は同期固定版レーンへ戻す。公示は発表から 2 時間以内なら同期とし、締切切迫時は Batch から同期へ即時 fallback する。

### Batch 対象外

- AIエージェント版:
  `postgame` / `live_anchor` / 複数 source 統合記事は AIエージェント版レーンを維持する。review / repair ループ前提のため Batch に流さない。
- 速報系:
  試合中の更新、`live_anchor`、当日速報の `postgame` は同期レーンのみとする。試合中・直後の文脈更新は Batch 遅延が致命的とみなす。
- 境界不明記事:
  `CORE_SUBTYPES` 判定に迷う記事、`source_trust` が `rumor` / `unknown` 主体の記事、`secondary tier` 依存が強い記事は安全側で AIエージェント版へ回す。

### fallback

- Batch 失敗:
  Batch job 作成失敗や API エラー時は既存同期固定版レーンへ戻す。再送はせず 1 回試行のみとし、コスト増を避ける。
- deadline 超過:
  Batch 結果が締切を超えた場合は同期固定版レーンで再生成する。超過分の Batch 結果は破棄し、二重 draft を作らない。
- 品質崩れ:
  Batch 結果が `doc/019` の固定版カード仕様を満たさない場合は AIエージェント版へ差し戻す。タグ欠落や事実矛盾など致命的崩れは同期固定版レーンで即再生成する。

### 非機能制約

- Batch 導入対象は固定版レーンのみ。
- 不可触範囲:
  `quality-gmail` / `quality-monitor` / `draft-body-editor`、Gmail / SMTP / sendmail / scheduler / automation / env / secret はこのチケットで変更しない。Batch API key 管理は既存 secret 方針に従い、本便では触れない。
- 同期パイプライン維持:
  Batch は補助レーンであり、既存同期パイプラインと固定版レーンは削除も置換もしない。fallback 依存のため並存を前提にする。

---

## TODO

### Batch 対象

【×】固定版レーンのうち Batch 対象記事を固定する  
【×】Batch 対象にする条件を明記する  
【×】締切が近い記事を除外するルールを明記する  

### Batch 対象外

【×】AIエージェント版を Batch 対象外に固定する  
【×】速報系を Batch 対象外に固定する  
【×】subtype 境界が怪しい記事を Batch 対象外に固定する  

### fallback

【×】Batch 失敗時の同期 fallback を明記する  
【×】deadline 超過時の fallback を明記する  
【×】品質崩れ時の差し戻し先を明記する  

### 非機能制約

【×】mail / automation / env / secret を触らないことを明記する  
【×】既存同期パイプラインを削除しないことを明記する  

---

## 成功条件

- Batch に流す記事と流さない記事が説明できる  
- fallback 経路が明記されている  
- 既存運用を壊さず補助レーンとして導入できる  
