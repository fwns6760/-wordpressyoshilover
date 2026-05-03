# sample_farm_result_63510

- `post_id`: `63510`
- `backup_path`: `/home/fwns6/code/wordpressyoshilover/logs/cleanup_backup/63510_20260426T012330.json`
- `subtype`: `farm_result`
- `quality_flags`: `missing_featured_media, missing_primary_source, site_component_mixed_into_body_middle, heading_sentence_as_h3`

## 元本文

```text
📰 巨人公式 / 巨人公式X ⚾ GIANTS FARM WATCH
【二軍】巨人 4-0 中日 先発の 投手は9回無失点8奪三振の完封！ 一回と二回
【二軍】巨人 4-0 中日先発の 投手は9回無失点8奪三振の完封。一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
📌 関連ポスト
https://twitter.com/TokyoGiants/status/2047971696335089781
【二軍結果・活躍の要旨】
巨人二軍の試合は4-0という結果でした。
💬 このニュース、どう見る？
【二軍】巨人 4-0 中日先発の 投手は9回無失点8奪三振の完封。
一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
【ファームのハイライト】
一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。
【二軍個別選手成績】
一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
【一軍への示唆】
二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。
💬 先に予想を書く？
💬 みんなの本音は？
📰 参照元: 巨人公式 / 巨人公式X
https://twitter.com/TokyoGiants/status/2047971696335089781
```

## source/meta facts

- `article_subtype`: `farm_result`
- `source_label`: `巨人公式 / 巨人公式X`
- `source_url`: `https://twitter.com/TokyoGiants/status/2047971696335089781`
- `source_urls`: `https://twitter.com/TokyoGiants/status/2047971696335089781`
- `title.rendered`: `巨人二軍 4-0 結果のポイント`
- `source_body_cue`: `先発は9回無失点8奪三振の完封。一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。`
- `speaker_name`: `not present in source/meta`
- `player_name`: `not present in source/meta`
- `key_quote`: `not present in source/meta`
- `score`: `4-0`
- `opponent`: `中日`
- `result`: `勝利`
- `pitching_line`: `9回無失点`
- `venue`: `not present in source/meta`
- `game_date`: `not present in source/meta`
- `starter_pitcher`: `not present in source/meta`
- `opponent_lineup_link`: `not present in source/meta`
- `modified`: `2026-04-25T19:01:56`
- `fetched_at`: `2026-04-26T01:23:30.081474+00:00`
- `lineup_order`: `not present in source/meta`

## 修正文候補

```markdown
### 二軍メモ
- 巨人二軍は中日戦で4-0、勝利。
- 先発は9回無失点。
- 一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
```

## diff

```diff
--- original.normalized
+++ preview.det
@@ -1,21 +1,4 @@
-📰 巨人公式 / 巨人公式X ⚾ GIANTS FARM WATCH
-【二軍】巨人 4-0 中日 先発の 投手は9回無失点8奪三振の完封！ 一回と二回
-【二軍】巨人 4-0 中日先発の 投手は9回無失点8奪三振の完封。一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
-📌 関連ポスト
-https://twitter.com/TokyoGiants/status/2047971696335089781
-【二軍結果・活躍の要旨】
-巨人二軍の試合は4-0という結果でした。
-💬 このニュース、どう見る？
-【二軍】巨人 4-0 中日先発の 投手は9回無失点8奪三振の完封。
-一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
-【ファームのハイライト】
-一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
-ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。
-【二軍個別選手成績】
-一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
-【一軍への示唆】
-二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。
-💬 先に予想を書く？
-💬 みんなの本音は？
-📰 参照元: 巨人公式 / 巨人公式X
-https://twitter.com/TokyoGiants/status/2047971696335089781
+### 二軍メモ
+- 巨人二軍は中日戦で4-0、勝利。
+- 先発は9回無失点。
+- 一回と二回に2得点ずつ、計4得点し勝利👏試合の詳細はこちら。
```

## 適用 rule list

- `remove_placeholders`: `applied` (先発の\s*投手は)
- `remove_empty_headings`: `applied` (💬 先に予想を書く？)
- `remove_optional_sections`: `applied` (📌 関連ポスト, 💬 このニュース、どう見る？, 【一軍への示唆】, 💬 みんなの本音は？)
- `condense_long_speculation`: `not_applied`
- `template_align_farm_result`: `applied` (subtype=farm_result)

## acceptance check

- `recommend_for_apply`: `yes`
- `mandatory_pass_count`: `5/5`
- `desirable_pass_count`: `3/3`

### mandatory
- `no_source_meta_fabrication`: `PASS` (ok)
- `no_placeholder_residual`: `PASS` (ok)
- `rule_list_explicit`: `PASS` (rendered=5, applied=4)
- `unified_diff_format`: `PASS` (ok)
- `wp_gemini_deploy_zero`: `PASS` (preview-only script; WP write 0 / Gemini call 0 / deploy 0)

### desirable
- `fixed_not_longer_than_original`: `PASS` (72 <= 591)
- `section_count_not_expanded`: `PASS` (1 <= 7)
- `facts_coverage_ge_80pct`: `PASS` (100.0%)
