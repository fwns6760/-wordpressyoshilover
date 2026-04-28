# 154 publish-policy-current(2026-04-26 PM 改訂、PUB-002-A 全面更新)

## meta

- 旧 PUB-002-A 全面更新版
- 反映 ticket: 130 / 135 / 137 / 141 / 142 revert / 145 / 146
- updated: 2026-04-26 PM
- supersedes: PUB-002-A(`doc/done/2026-04/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`)

## 判定 3 分類(130 実装)

- `publish_clean`
- `repairable_before_publish`
- `hard_stop`
- `publishable = NOT hard_stop`
- `cleanup_required = repairable_flags が 1 つ以上あり、かつ publishable`

## hard_stop flag(現 constant 12 種、publish 対象に入れない)

`src/guarded_publish_evaluator.py` の `HARD_STOP_FLAGS`:

| flag | 意味 |
|---|---|
| `unsupported_named_fact` | fact-check meta に `unsupported_*` 系 risk があり、source にない具体事実が混じる |
| `obvious_misinformation` | fact-check meta の `contradiction` / `source_mismatch` を誤情報として扱う |
| `title_body_mismatch_strict` | title と冒頭本文の主語/事象が strict 不一致(lineup title なのに body は postgame 等) |
| `cross_article_contamination` | nucleus validator の `MULTIPLE_NUCLEI` 相当で、別記事の核が混入している |
| `x_sns_auto_post_risk` | post meta に `posted_to_x` / `auto_tweet` などの truthy 値があり、SNS 自動投稿配線を疑う |
| `ranking_list_only` | 本文がランキング列挙だけで記事核が弱い |
| `lineup_no_hochi_source` | lineup dedup 判定で「報知代表がないため defer」になった |
| `lineup_prefix_misuse` | lineup source priority 判定で title prefix misuse を検出した |
| `dev_log_contamination_scattered` | dev log 断片が散在し、安全に一括 cleanup できる clear block がない |
| `stale_for_breaking_board` | freshness gate で stale 判定(default 24h、comment 系 48h など) |
| `expired_lineup_or_pregame` | lineup/pregame 系が 6h 超、または試合開始推定時刻を過ぎた |
| `expired_game_context` | postgame/game_result 系が 24h 超で失効した |

## repairable flag(現 constant 15 種、runner action map 対応)

`src/guarded_publish_evaluator.py` の `REPAIRABLE_FLAGS` と `src/guarded_publish_runner.py` の `REPAIRABLE_FLAG_ACTION_MAP`:

| flag | cleanup action | 意味 |
|---|---|---|
| `heading_sentence_as_h3` | `h3_to_p_demotion` | 文章丸ごとの h3 を p へ降格する |
| `weird_heading_label` | `remove_weird_heading_label` | 中身と合わない helper 見出しを除去する |
| `dev_log_contamination` | `remove_dev_log_block` | clear な dev log block を本文から除去する |
| `site_component_mixed_into_body` | `remove_site_component_block` | 関連記事/ファンの声などの site component を本文から除去する |
| `ai_tone_heading_or_lead` | `warning_only_ai_tone` | AI っぽい見出し/lead を warning-only で記録する |
| `light_structure_break` | `normalize_structure_break` | 空 `p` や連続 `br` を正規化する |
| `weak_source_display` | `append_source_anchor` | 抽出済み source URL を `出典:` 行で追記する |
| `subtype_unresolved` | `set_meta_article_subtype` | extractor heuristic から `meta.article_subtype` を補完する |
| `long_body` | `trim_trailing_prose_tail` | 5000 chars 超の trailing prose tail を圧縮する |
| `missing_primary_source` | `warning_only_missing_primary_source` | source URL 自体がなく、warning-only で保持する |
| `missing_featured_media` | `warning_only_missing_featured_media` | featured image 不足を warning-only で保持する |
| `title_body_mismatch_partial` | `warning_only_partial_mismatch` | strict ではない partial mismatch を warning-only で保持する |
| `numerical_anomaly_low_severity` | `warning_only_low_severity_numeric` | 低 severity の数値異常を warning-only で保持する |
| `injury_death` | `user_overide_full_publish_no_op` | user override 意図で no-op action 名を持つ |
| `lineup_duplicate_excessive` | `user_overide_full_publish_no_op` | user override 意図で no-op action 名を持つ |

### 現コードのズレ(重要)

- `REPAIRABLE_FLAG_ACTION_MAP` には `stale_for_breaking_board` / `expired_lineup_or_pregame` / `expired_game_context` も `freshness_audit_only_no_op` として載っている
- ただし現 evaluator は freshness 3 flag を `hard_stop` category で emit するため、通常 publish flow ではこの no-op action は使われない
- `injury_death` / `lineup_duplicate_excessive` も constant と runner map 上は repairable/no-op へ寄っているが、現 evaluator の `_evaluate_record()` / duplicate guard はまだ `hard_stop` category を付ける経路が残っている
- 既存 tests もこの 2 flag を hard-stop として検証しているため、**policy intent と runtime behavior は完全一致していない**

## 公開前 cleanup chain(130 runner)

`src/guarded_publish_runner.py` の live path:

1. backup 作成  
   `logs/cleanup_backup/<post_id>_<ts>.json` へ本文/抜粋/meta/status/link を退避
2. cleanup action 実行  
   `repairable_flags` ごとに action map を適用
3. post-condition verify  
   - 本文が空でない(`body_empty` で拒否)
   - prose が 100 chars 以上(`prose_lt_100` で拒否)
   - title subject の主要 token が本文に残る(`title_subject_missing` で拒否)
   - source anchor が消えていない(`source_anchor_missing` で拒否)
   - source URL host が残る(`source_url_missing` で拒否)
4. verify pass のみ publish
5. cleanup fail / verify fail はその post だけ `hold`  
   batch 全体 abort はしない

## cap(137 sent only count)

- default burst: `20`
- hard cap: `30`
- daily cap: `100`
- `_daily_sent_count()` は `status=sent` だけを budget 計上する
- `refused` / `skipped` は daily budget を消費しない
- ただし `_history_attempted_post_ids()` は `sent` と `refused` を attempt 済みとして扱う

## freshness gate(135 + 142 revert で hard_stop 復活)

`src/guarded_publish_evaluator.py` の `freshness_check()`:

- 6h: `lineup` / `pregame` / `probable_starter` / `farm_lineup`
- 24h: `postgame` / `game_result` / `roster` / `injury` / `registration` / `recovery` / `notice` / `player_notice` / `player_recovery` / default
- 48h: `comment` / `speech` / `manager` / `program` / `off_field` / `farm_feature`
- date 優先順位:
  - source meta fields(`source_published_at` など)
  - `source_block`
  - source URL 中の日付
  - body date
  - `created_at`
  - fallback `now`
- `modified` は freshness 判定に使わない
- lineup/pregame は age だけでなく、本文や title から推定した game start 時刻(明示がなければ 18:00 JST)経過でも `expired_lineup_or_pregame`

## WP publish vs X / SNS post

- current WP publish gate は `publishable = NOT hard_stop` で回る
- したがって **runtime 上は hard-stop に出た flag は publish されない**
- `injury_death` / `lineup_duplicate_excessive` については user override intent が constant/action-map へ部分反映済みだが、現 evaluator hard-stop 経路が残るため、**「hard-stop 以外全公開」に完全移行した状態ではない**
- X / SNS post は別 gate(`src/x_post_eligibility_evaluator.py`)でさらに strict
- 147 ramp は Phase 1 完了、Phase 2-5 は BLOCKED の段階解禁

## 公開後 cleanup

- 153: read-only audit で cleanup proposals を作る
- 124: `published_cleanup_apply_runner` が `--live` で proposal を適用する
- pre-publish gate と post-publish cleanup は別レーンで運用する

## user 解除済 safety gate(2026-04-26 PM lock、要警戒)

- commit `5b0e5ed`
  - `injury_death`: `HARD_STOP_FLAGS` から外し、`REPAIRABLE_FLAGS` へ移動
  - `lineup_duplicate_excessive`: `HARD_STOP_FLAGS` から外し、`REPAIRABLE_FLAGS` へ移動
  - runner action map に `user_overide_full_publish_no_op` を追加
- 解除根拠: user 「全記事公開」指示(2026-04-26 PM)
- ただし現 evaluator の hard-stop 付与コードと tests は残っている
- 実務上は 4/17 同質事故 risk / 同 title 多重公開 risk をまだ警戒する

## 関連 ticket

- 130 `867d90f`
- 135 `506e5ad`
- 136 `d11d84c`
- 137 `b5a8c34`
- 141 `4f7963d`
- 142 revert `e302187`
- 145 `5b01662`
- 146 `c433b89`
- 153 `3bd0f8a`
- 124 `d25d02c`
- PUB-004-C cron `2d42293`(doc sync、5min auto)
