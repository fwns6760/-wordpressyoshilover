# sample_farm_player_result_63133

- `post_id`: `63133`
- `backup_path`: `/home/fwns6/code/wordpressyoshilover/logs/cleanup_backup/63133_20260426T031359.json`
- `subtype`: `farm_player_result`
- `quality_flags`: `site_component_mixed_into_body_middle, title_body_mismatch_partial, heading_sentence_as_h3, stale_for_breaking_board`

## 元本文

```text
📰 報知新聞 / スポーツ報知巨人班X ⚾ GIANTS FARM WATCH
【巨人】通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が
【巨人】通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。
📌 関連ポスト
https://twitter.com/hochi_giants/status/2046395520998916495
【二軍結果・活躍の要旨】
💬 このニュース、どう見る？
【巨人】通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。
【ファームのハイライト】
二軍戦では得点の動きと投手の内容を先に押さえると全体像が見えやすくなります。
ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。
【二軍個別選手成績】
【一軍への示唆】
二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。
💬 先に予想を書く？
💬 みんなの本音は？
📰 参照元: 報知新聞 / スポーツ報知巨人班X
https://twitter.com/hochi_giants/status/2046395520998916495
```

## source/meta facts

- `article_subtype`: `farm_result`
- `source_label`: `報知新聞 / スポーツ報知巨人班X`
- `source_url`: `https://twitter.com/hochi_giants/status/2046395520998916495`
- `source_urls`: `https://twitter.com/hochi_giants/status/2046395520998916495`
- `source_headline`: `【巨人】通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が`
- `source_summary`: `通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。`
- `title.rendered`: `通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍…`
- `source_body_cue`: `通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。`
- `speaker_name`: `not present in source/meta`
- `player_name`: `山瀬慎之助`
- `key_quote`: `not present in source/meta`
- `score`: `not present in source/meta`
- `opponent`: `西武`
- `result`: `not present in source/meta`
- `pitching_line`: `not present in source/meta`
- `venue`: `not present in source/meta`
- `game_date`: `not present in source/meta`
- `game_time`: `not present in source/meta`
- `notice_type`: `合流`
- `player_event`: `０安打`
- `starter_pitcher`: `not present in source/meta`
- `opponent_lineup_link`: `not present in source/meta`
- `modified`: `2026-04-21T11:00:46`
- `fetched_at`: `2026-04-26T03:13:59.464133+00:00`
- `lineup_order`: `not present in source/meta`

## subtype-aware unlock interface

- `unlock_title`: `山瀬慎之助が本塁打`
- `unlock_subtype`: `farm_player_result`
- `unlock_reason`: `subtype_aware_farm_player_result`
- `title_strategy`: `farm_player_particle_title`
- `source_url`: `https://twitter.com/hochi_giants/status/2046395520998916495`
- `required_fact_axes`: `player_name`, `player_event`, `source_url`
- `present_fact_axes`: `player_name`, `player_event`, `source_url`
- `interface_match`: `yes`

## 修正文候補

```markdown
【二軍結果・活躍の要旨】
山瀬慎之助に本塁打の動きがあった。
通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。
【ファームのハイライト】
ファームで確認できた事実だけを先に残す。
【二軍個別選手成績】
山瀬慎之助に関する数字や出来事は source/meta にある範囲だけで整理する。
【一軍への示唆】
若手・二軍メモとして、次の評価につながる事実だけを短く残す。
```

## diff

```diff
--- original.normalized
+++ preview.det
@@ -1,18 +1,9 @@
-📰 報知新聞 / スポーツ報知巨人班X ⚾ GIANTS FARM WATCH
-【巨人】通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が
-【巨人】通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。
-📌 関連ポスト
-https://twitter.com/hochi_giants/status/2046395520998916495
 【二軍結果・活躍の要旨】
-💬 このニュース、どう見る？
-【巨人】通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。
+山瀬慎之助に本塁打の動きがあった。
+通算２０００安打まで残り７０本の丸佳浩、プロ初本塁打マークの山瀬慎之助が２軍合流…２軍・西武戦。
 【ファームのハイライト】
-二軍戦では得点の動きと投手の内容を先に押さえると全体像が見えやすくなります。
-ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。
+ファームで確認できた事実だけを先に残す。
 【二軍個別選手成績】
+山瀬慎之助に関する数字や出来事は source/meta にある範囲だけで整理する。
 【一軍への示唆】
-二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。
-💬 先に予想を書く？
-💬 みんなの本音は？
-📰 参照元: 報知新聞 / スポーツ報知巨人班X
-https://twitter.com/hochi_giants/status/2046395520998916495
+若手・二軍メモとして、次の評価につながる事実だけを短く残す。
```

## 適用 rule list

- `remove_placeholders`: `not_applied`
- `remove_empty_headings`: `applied` (【二軍結果・活躍の要旨】, 【二軍個別選手成績】, 💬 先に予想を書く？)
- `remove_optional_sections`: `applied` (📌 関連ポスト, 💬 このニュース、どう見る？, 💬 みんなの本音は？)
- `condense_long_speculation`: `not_applied`
- `template_align_farm_player_result`: `applied` (title_strategy=subtype_aware_rescue)

## acceptance check

- `recommend_for_apply`: `yes`
- `mandatory_pass_count`: `5/5`
- `desirable_pass_count`: `3/3`
- `phase5_pass_count`: `5/5`

### mandatory
- `no_source_meta_fabrication`: `PASS` (ok)
- `no_placeholder_residual`: `PASS` (ok)
- `rule_list_explicit`: `PASS` (rendered=5, applied=3)
- `unified_diff_format`: `PASS` (ok)
- `wp_gemini_deploy_zero`: `PASS` (preview-only script; WP write 0 / Gemini call 0 / deploy 0)

### desirable
- `fixed_not_longer_than_original`: `PASS` (207 <= 536)
- `section_count_not_expanded`: `PASS` (4 <= 7)
- `facts_coverage_ge_80pct`: `PASS` (100.0%)

### phase5
- `title_body_integrity`: `PASS` (山瀬慎之助 / 本塁打)
- `subtype_match`: `PASS` (subtype_aware_farm_player_result)
- `numeric_guard`: `PASS` (ok)
- `placeholder_absence`: `PASS` (ok)
- `body_contract_pass`: `PASS` (ok)
