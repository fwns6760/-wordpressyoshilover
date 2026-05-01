# Lane B round 17 — コスト増 path + mail storm 恒久対策安全性 audit(read-only)

## 目的

明日以降の自律運転で「user 張り付かなくても安全」基盤として、コスト増 path + mail storm 恒久対策が real review / hold / 289 通知を壊さないかの read-only 調査。各軸で発見事項 + 推奨 guard を doc 化。

read-only 限定。impl / commit 一切なし、stdout 出力のみ。

## 不可触リスト

- src / tests / scripts / config / .codex 一切編集しない、read-only grep / cat のみ
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- production change 0、deploy 0、commit 0、push 0
- git mutation 一切なし

## 調査軸 8 件

### 1. Gemini call が増える path

- 想定外で Gemini call が増える code path / config / fallback / retry の特定
- 対象 grep:
  - `src/gemini_*.py` の call site
  - `src/draft_body_editor*.py` の generation path
  - retry / fallback / regeneration の trigger
  - 282-COST preflight gate enable 時の挙動(現状 OFF)
  - 290 weak_title rescue enable 時の挙動(現状 OFF)
- Gemini call 増加 path 列挙(条件 + expected delta)

### 2. retry / fallback / regeneration

- 同一 post に対して LLM 呼出が複数回発生しうる path
- 対象:
  - `src/draft_body_editor*.py` の retry loop
  - body_contract_validate fail 時の regeneration
  - hallucinate_cache invalidation 時の retry
  - post_gen_validate fail → regenerate path(あれば)
- 重複 LLM call の root cause 列挙 + 件数推定

### 3. cache_hit 99% の真因

- `logs/llm_call_dedupe_ledger.jsonl` 等で観測される cache_hit ratio の root cause
- 対象:
  - cache key 構成(post_id + content_hash + prompt_version 等)
  - cache TTL / invalidation
  - cache miss 時の cost
  - cache hit が高すぎることの implication(改修で激減リスク)
- cache_hit dependence の structural risk

### 4. cache miss 時に高コスト経路へ流れるか

- cache miss 時に full LLM regeneration / multi-call へ落ちる path
- 対象:
  - hallucinate cache miss
  - llm_call_dedupe miss
  - draft regeneration miss 時の Gemini fallback
  - 大量 cache miss のシナリオ(deploy 後 / cache file 損失 / config 変更)
- 高コスト fallback path 列挙

### 5. publish-notice / review / hold / post_gen_validate 通知で LLM を呼ぶ可能性

- mail 通知系で LLM 呼出が走る path がないか
- 対象:
  - `src/publish_notice_*.py` の subject / body 生成
  - mail bridge の content 生成
  - post_gen_validate notification の reason 文生成
  - hold / skip 通知の reason 文生成
- mail 通知 path 内の LLM call 列挙(本来 0 想定、見つかればリスク)

### 6. Cloud Run / GCS / Logging 肥大化

- 自動運転で蓄積する artifact の肥大化トレンド
- 対象:
  - GCS `gs://baseballsite-yoshilover-state/` の各 ledger
  - Cloud Run logs retention
  - Logging volume per day
  - cron_eval.json / publish_notice_history.json / dedupe ledger size
  - 5/1 storm 由来の 99 + 50 post_id ledger entry
- 肥大化リスク + retention policy 推奨

### 7. old_candidate sent ledger の retention

- 298-Phase3 v4 で導入した GCS pre-seed ledger(`publish_notice_old_candidate_once.json`)の retention 戦略
- 対象:
  - 現状 106 件、増加レート(新規 first emit 後追記、~1 件/2-3h)
  - 1 ヶ月後の想定 size
  - retention 切替条件(cardinality / TTL / archive)
  - retention なしで永続化した時のリスク
- retention strategy 推奨

### 8. mail storm 恒久対策が real review / hold / 289 通知を壊さないか

- POLICY §7 mail storm rules + GCS pre-seed ledger + cap=10 + 24h dedup の組合せが、normal review / 289 / error notification を抑制してないか
- 対象:
  - 本日 5/1 18:00-19:00 の post_gen_validate 6 件 vs baseline 27/day
  - hold / skip 通知の sent 数 baseline
  - error notification の sent 数 baseline
  - 290 Pack B enablement 後の weak_title rescue review mail expected
- normal mail flow 影響 列挙

## 出力形式(stdout のみ、commit なし)

各軸 8 件で以下の form:

```
### <軸番号> <軸名>

- 発見事項:
  - <bullet 1>
  - <bullet 2>
- リスク level: HIGH / MEDIUM / LOW
- expected delta(数値、可能な範囲):
- 推奨 guard:
  - <bullet 1>
  - <bullet 2>
- POLICY 該当 section / 反映先 doc:
- Claude 自律 GO で潰せるか: YES / PARTIAL / NO
```

最後に Summary:

```
### Summary

- HIGH risk 軸: <list>
- MEDIUM risk 軸: <list>
- 先に入れるべき cost guard: <list>
- mail storm 恒久対策安全性: SAFE / UNSAFE / NEEDS_GUARD
- POLICY 追加が必要な軸: <list>
- 残 UNKNOWN: <list>
- normal mail flow 影響:
```

## 完了報告

```json
{
  "status": "audit_completed",
  "axes_audited": 8,
  "high_risk_axes": [],
  "medium_risk_axes": [],
  "cost_guards_recommended": [],
  "test": "n/a (read-only audit)",
  "open_questions_for_claude": [],
  "next_for_claude": "Read audit output, compress into 8-item report"
}
```

## 5 step 一次受け契約

- read-only(commit / git / push 一切なし)
- src / tests / scripts / config 一切編集しない
- pytest 不要
- scope 内
- rollback 不要(read-only)
