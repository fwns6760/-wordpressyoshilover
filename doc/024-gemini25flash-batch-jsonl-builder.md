# 024 — Gemini 2.5 Flash Batch 投入用 JSONL 生成

**フェーズ：** 固定版 Batch 投入前段  
**担当：** Codex A  
**依存：** 023

---

## 概要

正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §9。親チケットは `doc/011` (`4dc0b2b`) / `doc/014` (`2d92405`) / `doc/019` (`07e5279`) / `doc/023`、handoff docs 正本は `/home/fwns6/code/baseballwordpress/docs/handoff/` 配下。
固定版レーンの Batch 対象記事を 1 件 1 行の JSONL にまとめ、Gemini 2.5 Flash Batch API に投げられる形にする。
このチケットは「投げる前の整形」に限定し、送信そのものとは切り分ける。

---

## 決定事項

### JSONL 単位

- 1 行 1 記事候補:
  固定版レーンの 1 候補 = 1 JSON object = JSONL の 1 行とする。複数候補を 1 行にまとめず、記事単位で idempotent に扱う。
- idempotency key:
  `candidate_id` を必須とし、同一 `candidate_id` の重複投入を禁止する。形式は `{source_id}:{article_type}:{YYYYMMDD}` を推奨し、manifest 側で既出を検出してスキップする。
- article_type:
  `program_notice / transaction_notice / probable_pitcher / baseball_data / farm_result / pregame_summary` の 6 種に限定する。`doc/011` 固定版レーン対象 6 型 / `doc/019` 3 カードと整合し、この 6 種以外は AIエージェント版 の別経路へ回す。
- ルーティング前提:
  `CORE_SUBTYPES` は `pregame / postgame / farm / fact_notice / live_anchor` を維持する。JSONL には固定版 6 型へ正規化できる候補だけを載せ、短納期の `postgame` は `doc/023` 同期経路を優先する。

### 必須フィールド

- 必須フィールド一覧:
  `candidate_id / article_type / title_hint / source_bundle / template_context / tags_hint / category_hint / deadline_hint` を必須とする。欠落行は JSONL 生成時点で弾き、Batch へは送らない。
- source_bundle 最小構造:
  `primary` は 1 件以上の source object 配列、`secondary` は 0 件以上の補強用配列とする。各 object は既存 `src/source_id.py` の `source_id` 語彙に沿った `source_id / url / fetched_at / excerpt?` を持ち、`doc/014` の `source_trust` と `primary tier` に従って rumor / unknown を含めない。
- template_context 最小構造:
  `card_type / key_facts / priority_keys` を必須とする。`card_type` は `doc/019` 3 カードまたは `doc/011` 固定版 6 型に合わせ、`key_facts` には選手名・日付・球場・記録値などの確定情報、`priority_keys` には title 超過時の短縮優先順を入れる。
- deadline_hint:
  記事締切を ISO8601 timestamp で持つ。`doc/023` の短納期ルールである試合前 1h / 公示 2h に該当する候補は JSONL 対象外とし、固定版レーン同期処理へ回す。

### 出力場所

- JSONL 出力先:
  `data/batch/fixed_lane/YYYYMMDD/request-<HHMMSS>.jsonl` に出す。日付ディレクトリは JST 基準、1 日複数バッチを許容し、1 ファイル最大行数を超える場合は request file を分割する。
- manifest:
  同ディレクトリに `manifest-<HHMMSS>.json` を出し、`candidate_id` 一覧 / 行数 / sha256 を持たせる。後段の result loader は `doc/025` でこの manifest を突き合わせに使う。
- 再実行時の扱い:
  既存 manifest に載った `candidate_id` は新規 request に含めない。再実行が必要でも既存 file は上書きせず新規採番し、manifest の `candidate_id` 集合を union で追跡する。

### 非機能制約

- WP write 不可:
  JSONL 生成段階では WordPress に書き込まない。draft 作成 / publish / 既存 post 更新はいずれも scope 外とする。
- mail / automation 不可触:
  `quality-monitor` / `quality-gmail` / `draft-body-editor` を含め、Gmail / SMTP / sendmail / scheduler / env / secret / automation は触らない。Batch API 送信 runner も別便で扱う。
- 既存同期経路は維持:
  JSONL 生成は固定版レーンの並走機能として追加し、既存同期経路を止めない。Batch 側が失敗した場合は `doc/023` の fallback で同期経路へ戻す。

---

## TODO

### JSONL 単位

【×】1 行 1 記事候補の原則を明記する  
【×】idempotency key を決める  
【×】article_type の列挙を決める  

### 必須フィールド

【×】必須フィールド一覧を固定する  
【×】source_bundle の最小構造を決める  
【×】template_context の最小構造を決める  
【×】deadline_hint の扱いを決める  

### 出力場所

【×】JSONL 出力先を決める  
【×】manifest の有無を決める  
【×】再実行時の扱いを決める  

### 非機能制約

【×】WP write をしないことを明記する  
【×】mail / automation を触らないことを明記する  
【×】既存同期経路を止めないことを明記する  

---

## 成功条件

- Batch 投入前の JSONL 仕様が説明できる  
- 1 記事候補を重複なく流せる  
- 後段の result loader が受け取れる形になっている  
