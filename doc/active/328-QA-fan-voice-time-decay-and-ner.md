# 328-QA fan voice time decay + NER entity matching

## meta

- number: 328-QA
- type: industry-standard ranking improvements (time decay + NER)
- status: IMPL_LANDED, DEPLOY_PENDING
- priority: P1
- owner: Claude
- created: 2026-05-13
- doc_path: `doc/active/328-QA-fan-voice-time-decay-and-ner.md`

## 1. 背景

user 要望「金がかからない一般的な手法でファンの声の精度を上げて」に対し、業界標準の 2 手法を追加実装。

327-QA / 327-QA-fallback の延長として、Yahoo realtime picker の ranking
ロジックを強化する。¥0 / 既存資産活用 / minimum-diff。

## 2. fix(default ON)

### A. time decay (recency bucket)

industry standard: 新しい post 優先。`_reaction_recency_bucket()` で 4 階層
(3=<6h, 2=<24h, 1=<48h, 0=>=48h) を sort key に挿入。

- env flag: `ENABLE_FAN_REACTION_TIME_DECAY` (default ON)
- sort key 位置: focus_score の次、commentary_score の前
- 同 focus_score の古い post を新しい post が押しのける

### B. NER entity matching (player roster overlap)

industry standard: news matching では shared named entity が強シグナル。
既存 `giants_roster.json` + `_matching_giants_roster_names` をそのまま活用。

- env flag: `ENABLE_FAN_REACTION_NER_BONUS` (default ON)
- 計算: 記事 (title+summary) と reaction text の roster overlap 数 (cap 3)
- sort key 位置: focus_score の直後、recency_bucket の前
- 同 focus_score でも、記事の選手と同じ選手に言及する post が優先

## 3. 触らない範囲

- publish / mail / scheduler / env / Cloud Run / Secret / X API
- `_reaction_focus_score` 本体 / `_reaction_can_fill_shortage`
- 327-QA で landed 済 (subject context, handle cap, h3 dedup, Yahoo fallback)
- 309-QA / 310-QA / 311-QA / 324-QA / 325-QA / 326-QA (別 scope)
- giants_roster.json (read-only)

## 4. test

- `tests/test_yahoo_realtime.py::FanReactionTimeDecayTests` 3 件
- `tests/test_yahoo_realtime.py::FanReactionNERBonusTests` 3 件
- full pytest: 3891 passed / 1 pre-existing fail (regression 0)

## 5. deploy

- new image tag (この commit hash)
- env 不要 (default ON)
- verify は次 cron で実機確認

## 6. 業界手法対応表

| 手法 | 状態 | 本 ticket |
|---|---|---|
| time decay (exponential / bucket) | landed | ✓ |
| NER (entity overlap) | landed | ✓ |
| TF-IDF / BM25 | 既存 `_reaction_focus_score` が部分的に実装済 | 後続 |
| engagement signal (like / RT) | Yahoo 無料 scrape 制約調査要 | 後続 |
| embedding similarity | コスト高、scope 外 | - |
| handle whitelist | 324-QA / 325-QA scaffold landed、user handle list 待ち | 別 |
