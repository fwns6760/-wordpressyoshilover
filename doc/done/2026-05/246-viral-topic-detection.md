---
ticket: 246
title: viral topic detection (SNS バズ検出 → 既存 subtype routing、dry-run)
status: READY
owner: Codex B (impl 想定)
priority: P2
lane: B
ready_for: codex_b_fire (user GO 後)
created: 2026-04-29
related: 234 contract sns_topic (follow-up only、本 ticket では実装しない)、244 / 234-impl-5/6/7 既存 guard (本 ticket は通すだけ)
---

## 背景

現状 fetcher は スポーツ媒体 RSS + 公式系 SNS のみを source としている。
SNS で爆発的に話題になっている巨人ネタ(viral topic)も拾って記事化したい。
ただし **SNS 投稿は事実 source にしない**(噂・推測・誹謗中傷を本文に入れない)。SNS は **topic trigger のみ**。

## 目的

SNS で viral になっている巨人 topic を検出 → **公式 / スポーツ媒体 / 既存 RSS で裏取り** → OK なら **既存 subtype** で routing。
裏取りできないものは default_review / review に倒す(publish しない)。
既存の 234 / 244 / 234-impl-* / NO_GAME_BUT_RESULT guard を必ず通す。

## scope (narrow、dry-run first)

### 1. 新規 module `src/viral_topic_detector.py`

#### 1-A. Source 取得 helpers

- `fetch_yahoo_realtime_search_giants() -> list[dict]`:
  - URL: `https://search.yahoo.co.jp/realtime/search?p=巨人` (scraping、rate-limited)
  - timeout 5 秒、retry なし、失敗時は空 list 返す(既存 fetcher 阻害しない)
  - return: list of `{keyword, rank, trend_volume_or_null, detected_at}`
- `fetch_yahoo_news_baseball_ranking() -> list[dict]`:
  - URL: `https://news.yahoo.co.jp/ranking/access/news/baseball`(scraping)
  - timeout 5 秒、retry なし
  - return: list of `{title, url, rank, detected_at}`
- 両 endpoint 失敗時は detector 全体を no-op(detection 結果空 list)、既存 fetcher 動作不変

#### 1-B. Topic candidate 構築

- `build_topic_candidate(raw_signal: dict, source: str) -> dict`:
  - candidate JSON schema(下記)に整形

#### 1-C. Subtype 推定(rule-based、Gemini 不使用)

- `classify_expected_subtype(keyword: str, title: str = "") -> str | None`:
  - 既存 fetcher の classify_category と同 pattern (rule-based marker match)
  - return: 既存 subtype 文字列のうち 1 つ:`"postgame"` / `"farm_result"` / `"lineup"` / `"farm_lineup"` / `"pregame"` / `"notice"` / `"program"` / `"default"` / `None`
  - **新 subtype 文字列(`viral_topic` / `sns_topic` 等)は src 識別子に書かない**(user 制約、234-impl-2/3/4 と同 pattern)
  - 推定不能 → `None`(後段で default_review に倒す)

#### 1-D. Source confirmation(既存 fetcher 経路 reuse)

- `cross_reference_official_sources(keyword: str, fetcher_history: dict) -> dict`:
  - 既存 fetcher が直近取得した RSS / SNS history(GCS 保管 or in-memory)に同 keyword hit があるか確認
  - hit あり → `{confirmed: true, primary_source_url: "...", primary_subtype: "..."}` 
  - hit なし → `{confirmed: false, reason: "no_official_source_within_24h"}`
  - **新規 web fetch / Gemini call なし**(既存 fetcher state を利用するだけ)

### 2. 新規 dry-run entrypoint `src/tools/run_viral_topic_dry_run.py`

- CLI script: `python3 src/tools/run_viral_topic_dry_run.py --max-candidates 10`
- flow:
  1. `fetch_yahoo_realtime_search_giants()` + `fetch_yahoo_news_baseball_ranking()`
  2. 各 raw signal で `build_topic_candidate()`
  3. `classify_expected_subtype()` で subtype 推定
  4. `cross_reference_official_sources()` で裏取り
  5. JSONL output to `logs/viral_topics_dry_run/<YYYY-MM-DD>.jsonl`
- **publish 経路に流さない**(WP draft 作らない、auto publish なし)
- **dry-run only**(本 ticket scope)

### 3. tests `tests/test_viral_topic_detector.py`

- Yahoo HTML mock 解析(real fetch しない、固定 fixture)
- candidate JSON schema 検証
- subtype classify rule 確認(postgame keyword → "postgame" 等)
- source confirmation logic(hit あり / なし両方)
- 誹謗中傷 / 噂 marker (`噂`, `らしい`, `だってさ`, `〜やばい`)で skip 確認
- 既存 fetcher fixture を broken にしない(test 完全独立)

## candidate JSON schema

```json
{
  "schema_version": 1,
  "detected_at": "2026-04-29T10:00:00+09:00",
  "source": "yahoo_realtime_search" | "yahoo_news_ranking",
  "raw_signal": {
    "keyword": "巨人 戸郷",
    "rank": 1,
    "trend_volume": null,
    "title": "戸郷翔征 完投勝利",
    "url": "https://news.yahoo.co.jp/articles/...",
    "context_excerpt": "戸郷翔征が..."
  },
  "expected_subtype": "postgame" | "farm_result" | "lineup" | "farm_lineup" | "pregame" | "notice" | "program" | "default" | null,
  "subtype_confidence": "high" | "medium" | "low" | "unresolved",
  "source_confirmation": {
    "confirmed": false,
    "primary_source_url": null,
    "primary_subtype": null,
    "reason": "no_official_source_within_24h" | "ok" | null
  },
  "skip_reason": null | "spam_marker" | "not_giants_related" | "subtype_unresolved",
  "publish_blocked": true,
  "next_action": "default_review" | "candidate_for_existing_subtype" | "discard"
}
```

## review / draft 落とし条件

| 条件 | next_action |
|---|---|
| `source_confirmation.confirmed = false` | `default_review`(裏取りなし、人間に振る) |
| `expected_subtype = None` または `unresolved` | `default_review` |
| `skip_reason = "spam_marker"`(誹謗中傷・噂 marker hit) | `discard`(候補にしない) |
| `not_giants_related`(既存 fetcher filter と共通) | `discard` |
| 上記すべて clear + `confirmed = true` + `expected_subtype` 既存 subtype | `candidate_for_existing_subtype`(既存 fetcher 経路で再評価) |

## 既存 subtype routing 方針

- viral topic で hit した keyword の関連公式記事が見つかれば、**既存 fetcher で再 fetch して既存 subtype 経路で本文化**(routing は既存資産)
- 本 ticket は detection + JSON 出力のみ、**routing 接続は別 ticket**(247 等で fetcher 統合判断)
- subtype routing 表(参考):
  - 試合結果 → postgame / farm_result
  - スタメン → lineup / farm_lineup / pregame
  - 公示・復帰・怪我 → roster_notice / injury_recovery_notice (234-impl-3/4 既存 helper)
  - 番組 → program_notice (234-impl-3 既存 helper)
  - 裏取り弱 → default_review / review

## 不可触 (絶対に触らない)

- X API / Twitter API / Twitter scraping(本 ticket は X 不使用)
- 5ch / なんJ / 掲示板系 source(誹謗中傷・著作権 risk)
- Gemini / LLM call 追加
- prompt 改修 / Gemini 入力変更
- 既存 fetcher (rss_fetcher.py) の触り(本 ticket は別 module + 別 entrypoint)
- 既存 publish 経路 / WP REST 設定 / draft 作成
- env / Secret / Scheduler / Cloud Run 設定変更
- 234 contract sns_topic subtype の本実装(table-only 維持)
- viral 専用テンプレ / H2 / H3 構造追加
- 新 subtype 文字列(`viral_topic` / `sns_topic` 等)を src 識別子に書く(helper 内 marker のみ可、234-impl-2/3/4 同 pattern)
- WP category 新規作成(WP DB 操作不要、subtype routing は既存)
- 既存 fixture 1 件も変更しない、追加のみ
- ambient dirty 巻き込み

## デグレ防止 contract

- 新 module + 新 entrypoint + 新 tests のみ、既存 src/tests 触らない
- Yahoo scraping は **timeout 5 秒 / retry なし / 失敗時 no-op**(既存 fetcher 阻害しない)
- detector 全体が落ちても既存 fetcher は完全独立で動く(import 経路完全分離)
- dry-run 出力は `logs/viral_topics_dry_run/` に隔離、publish 経路に流れない
- false positive(良 topic を spam_marker で discard)1 件でも疑いがあれば実装止めて Claude に report

## acceptance (3 点 contract)

1. **着地**: 1 commit に新 module + 新 entrypoint + 新 tests のみ stage、git add -A 禁止
2. **挙動**: 新規 fixture 全 pass、既存 fixture fail 0、pytest baseline 維持
3. **境界**: 既存 fetcher / publish 経路 / Gemini / Cloud Run / WP REST すべて不変、dry-run 出力のみ追加

## commit message 想定

`246: viral topic detection module + dry-run entrypoint (Yahoo realtime + news ranking, no Gemini, no X API)`

## 完了後の Claude / user 判断事項

- 1-3 日 dry-run 観察(`logs/viral_topics_dry_run/` の JSONL を read-only で集計)
- candidate 数 / source_confirmation 比率 / 推定 subtype 分布で「viral pickup の効果」評価
- 効果あれば 247 ticket で fetcher 統合(routing 接続)を別判断
- 効果なし or false positive 多い場合は detector tuning or 廃止判断

## non-goals

- viral topic を即 publish する経路の追加(本 ticket は dry-run only)
- sns_topic subtype の本実装(234 contract の table-only 維持)
- viral 専用テンプレ追加(本文は既存 subtype templates で十分)
- WP category 新規作成
- Gemini に viral 判定を投げる
- X API 接続 / X 自動投稿
- 5ch / なんJ ingestion
