# 282-COST-gemini-preflight-article-gate

| field | value |
|---|---|
| ticket_id | 282-COST-gemini-preflight-article-gate |
| priority | P1 (cost 削減) |
| status | REVIEW_NEEDED |
| owner | Claude (audit/draft) → Codex (別 lane、cost 削減専任) |
| lane | COST |
| ready_for | Claude review / push 判断 |
| blocked_by | (なし、impl/test 完了) |
| doc_path | doc/active/282-COST-gemini-preflight-article-gate.md |
| created | 2026-04-30 |

## 1. 目的

Gemini Flash 呼び出し**前**に「そもそも記事化する素材か」を判定する preflight gate を追加する。明らかに publish しない素材で Gemini を消費しない。

229-COST(同 content_hash 再生成回避、content level)と layer が違う、**meta level dedupe**(subtype / duplicate / 巨人関係性 / placeholder 等)。

## 2. 背景 — 現在の Gemini 呼出経路(audit 結果)

主線 path:
```
yoshilover_fetcher /run trigger
  → rss_fetcher._main()
    → 候補ごと
      → _gemini_cache_lookup (229-COST cache layer、source_url_hash + content_hash)
        ├─ cache_hit → gemini_call_made=False、skip
        └─ cache_miss → _request_gemini_strict_text → Gemini API
```

副線(scope 外):
- `src/x_post_generator.py:283`(X post、OFF 中)
- `src/weekly_summary.py`(週間まとめ、別 cron)
- `src/manual_post.py`(CLI 手動)

## 3. preflight gate の入る場所(設計案)

`_gemini_cache_lookup` の **直前** に新 layer を chain:

```
候補
  → _gemini_preflight_should_skip(candidate, metadata)  ← 新規
      ├─ skip=True → log gemini_call_skipped + skip_reason → return without Gemini
      └─ skip=False(継続)
  → _gemini_cache_lookup (229-COST、不変)
  → _request_gemini_strict_text (不変)
```

skip 判定は **明確に publish しない / Gemini 不要** な素材だけ:

| skip_reason | 判定根拠 | 例 |
|---|---|---|
| `existing_publish_same_source_url` | source_url が WP 既 publish に存在 | 263-QA duplicate guard 早期化 |
| `placeholder_body` | source body が短すぎる / template stub | farm_result placeholder 早期検知 |
| `not_giants_related` | title + body に巨人 token 0、相手チーム単独 | 巨人無関係 |
| `live_update_target_disabled` | live_update subtype + ENABLE_LIVE_UPDATE_ARTICLES=0 | 試合中実況 |
| `farm_lineup_backlog_blocked` | farm_lineup + age 古い + backlog | 281-QA BLOCKED 早期化 |
| `farm_result_age_exceeded` | farm_result + age >= 24h | 281-QA hold 早期化 |
| `unofficial_source_only` | X/2ch 由来で公式・スポーツ紙確認なし | 事実 source 不足 |
| `expected_hard_stop_death_or_grave` | title に死亡/重傷/救急/意識不明 token + 巨人選手該当 | 266-QA hard_stop 予測 |

skip しない(=従来通り Gemini 通す):
- 一軍/二軍スタメン fresh
- 二軍試合結果 24h 以内
- 試合結果 / 監督・コーチ・選手コメント
- 登録/抹消 / 怪我/復帰
- 公式 X / 球団公式 / スポーツ紙確認あり
- グッズ / イベント / 番組(巨人関連明確)

## 4. 実装対象 file

write scope:
- `src/gemini_preflight_gate.py`(新規 module、判定 helper 群)
- `src/rss_fetcher.py`(narrow integration、`_gemini_cache_lookup` 直前に呼出 1 行追加)
- `tests/test_gemini_preflight_gate.py`(新規、デグレ試験 fixture)
- `doc/active/282-COST-gemini-preflight-article-gate.md`(status 更新、本 file)

不可触:
- `src/gemini_cache.py`(229-COST 既存 layer、変更禁止)
- `src/llm_call_dedupe.py`(同上)
- 他 fetcher path 既存ロジック
- `.github/workflows/**`
- `src/guarded_publish_runner.py`(281-QA scope、本便で touch しない)
- `src/publish_notice*` / `src/draft_body_editor*` / `src/sns_topic_publish_bridge.py`
- `src/title_player_name_backfiller.py`(277-QA scope)
- automation / scheduler / env / secret / `.codex/automations/**`
- prosports / SEO / X 自動投稿 path / Team Shiny From / WP REST 直接呼出

## 5. 追加する log event

| event | 内容 |
|---|---|
| `gemini_call_skipped` | preflight skip 時に必ず emit、skip_reason 含む |
| `gemini_call_skipped` field schema | `{event, post_url, source_url_hash, content_hash, subtype, skip_reason, skip_layer="preflight"}` |
| 既存 `gemini_cache_lookup` | 不変、preflight skip 時は呼ばれない(skip 早期 return) |

skip vs cache_hit vs miss の 3 状態が log で区別可能:
- `gemini_call_skipped + skip_layer=preflight` → 新 layer
- `gemini_cache_lookup + cache_hit=true + cache_hit_reason=content_hash_exact` → 既存 229-COST
- `gemini_cache_lookup + cache_hit=false + gemini_call_made=true` → Gemini 実呼出

## 6. 必須デグレ試験(`tests/test_gemini_preflight_gate.py`)

### 6-A. 公開導線(silent 禁止)
- [ ] preflight skip された候補も guarded-publish の input になる(draft 経由)→ silent draft にならない
- [ ] preflight skip → 必要なら review/hold mail に流れる(267-QA notification 維持)
- [ ] silent draft / silent backlog / silent hold 0(全 skip に reason emit)
- [ ] publish 対象候補(一軍スタメン等)は preflight 通過 → Gemini → publish 維持

### 6-B. コスト
- [ ] 同 source_url + 同 content_hash で **preflight skip → cache lookup 不要 → Gemini 0 call** 確認
- [ ] 既存 229-COST cache_hit 挙動を壊さない fixture(同 content_hash 二回目 → cache_hit、preflight 通過)
- [ ] cache_hit / dedupe_skip / cooldown_skip / preflight_skip が log で区別 fixture
- [ ] Gemini call 数 baseline 比較で **増えない**(本変更で減るはず、増えるなら bug)
- [ ] 24h running window で source_url_hash 単位の Gemini call 数集計可能

### 6-C. 記事化基準
- [ ] 一軍スタメン fresh fixture → preflight 通過、Gemini call OK
- [ ] 二軍スタメン fresh fixture(`farm_lineup` + is_backlog=False)→ 通過
- [ ] 二軍試合結果 24h 以内 fixture → 通過
- [ ] 二軍試合結果 25h fixture → preflight skip(`farm_result_age_exceeded`)
- [ ] 古い backlog fixture(allowlist 外 + age >> threshold)→ skip
- [ ] 巨人 token 0 + 相手チーム単独 fixture → skip(`not_giants_related`)
- [ ] placeholder body fixture(< N 文字)→ skip(`placeholder_body`)
- [ ] live_update subtype fixture + ENABLE_LIVE_UPDATE_ARTICLES=0 → skip(`live_update_target_disabled`)
- [ ] X/2ch 由来 + 公式 source 0 fixture → skip(`unofficial_source_only`)
- [ ] X/2ch 由来 + 公式 source あり fixture → 通過

### 6-D. 安全系
- [ ] 死亡/重傷/救急搬送/意識不明 token + 巨人選手 fixture → preflight skip(`expected_hard_stop_death_or_grave`)
- [ ] 既存 hard_stop は本便で素通りしない、preflight 通過後の guarded-publish 段階で trip 維持
- [ ] スコア矛盾 fixture → Gemini 後の baseball_numeric_fact_consistency で trip 維持(preflight で予測スキップしない、本便 scope 外)
- [ ] 一軍/二軍混線 fixture → preflight skip OR Gemini 後 review 維持
- [ ] duplicate guard 維持(263-QA) — 本便で同 source_url 既 publish の skip は預金、263-QA logic 不変

### 6-E. 禁止事項 diff assert
- [ ] ENABLE_LIVE_UPDATE_ARTICLES env 値 不変
- [ ] live_update path 触らない
- [ ] SEO/noindex/canonical/301 token 不在
- [ ] X 自動投稿 path 触らない
- [ ] 新 subtype 追加なし
- [ ] Scheduler 頻度変更なし
- [ ] Team Shiny From 変更なし
- [ ] publish/mail 導線(publish_notice / guarded_publish_runner)touch 禁止

### 6-F. log・観察
- [ ] `gemini_call_made=true/false` が引き続き出る
- [ ] `preflight_skip_reason` が新 event で出る
- [ ] `cache_hit_reason` (229-COST 既存) と区別可能
- [ ] 24h で `gemini_call_skipped` 数を集計可能(jsonPayload に skip_reason / skip_layer 含む)
- [ ] 本変更前後で `gemini_call_made=true` の count 比較可能

## 7. deploy 要否

- commit + push のみ(本便で deploy なし)
- 本番反映は **fetcher (yoshilover-fetcher) image rebuild + service update** 必要
- deploy 便は別 fire(本 ticket 完了 + GH Actions green + 24h KPI baseline 取得後、user GO)

## 8. rollback 条件

- 本 ticket commit を revert すれば即時 rollback
- 本番 image rebuild 後、Gemini call が想定外に減って publish が drop した場合、前 image (`yoshilover-fetcher:27166c5` = 277-QA 反映 image) に戻す
- env flag で preflight ON/OFF 切替を入れるか?
  - 案 A: env flag なし(コード単一 path、シンプル)
  - 案 B: `ENABLE_GEMINI_PREFLIGHT=1` env flag(default OFF、deploy 後段階的有効化)
  - **推奨: 案 B**(rollback path シンプル + canary 可能)

## 9. KPI(24h 観察、deploy 後)

| KPI | 取得方法 | 期待 |
|---|---|---|
| Gemini call 数 / hour | `gemini_call_made=true` の count / 1h window | 本変更前比 -10〜-30% |
| source_url_hash ごとの Gemini call 数 | `source_url_hash` group by + count | 同一 url の重複 call 0 |
| cache_hit 率 | 229-COST 既存 metric | 75% 維持 |
| preflight_skip 数 | `gemini_call_skipped` count + skip_reason 分布 | 本変更前は 0、deploy 後 > 0 |
| Gemini 生成後 publish されなかった件数 | gemini_call_made=true ∩ guarded-publish status != sent | 減少傾向 |
| backlog 入り Gemini 生成済 件数 | gemini_call_made=true ∩ is_backlog=True | 減少傾向 |
| publish 数(変化監視) | WP REST GET / 24h | **不変 or 上昇**(skip で publish が減ったら bug) |
| review/hold mail 数 | publish-notice emit / 24h | 維持 or 適度変動 |

## 10. デグレ試験の自律 GO 範囲(進行ルール)

- preflight skip した候補が **review/hold mail に出る or draft で残る**ことを fixture で必ず assert
- silent skip 0(reason 必須 emit)
- env flag で OFF 起動 → ON 切替で挙動差を観察(canary)
- KPI で publish 数が **減ったら即 rollback**(設定意図と逆方向の出力)

## 11. GO/HOLD 判断

- 今: ticket 起票 + 設計 + デグレ試験
- 281-QA accept + push 完了後、Codex 別 lane で fire(本 ticket impl)
- impl は src 1 file + tests 1 file + ticket doc + 新 module 1 file = narrow scope
- pytest baseline 維持必須(local 7 pre-existing fails 不変、新 fail なら narrow 起票して停止)
- deploy は別 fire、env flag で段階導入推奨
