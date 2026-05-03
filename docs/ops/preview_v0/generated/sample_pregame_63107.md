# sample_pregame_63107

- `post_id`: `63107`
- `backup_path`: `/home/fwns6/code/wordpressyoshilover/logs/cleanup_backup/63107_20260426T031359.json`
- `subtype`: `pregame`
- `quality_flags`: `missing_primary_source, speculative_title, site_component_mixed_into_body_middle, expired_lineup_or_pregame`

## 元本文

```text
📰 サンスポ / サンスポ巨人X ⚾ GIANTS GAME NOTE
【4/21予告先発】 ー （長野、18:00) 巨人:(0勝1敗、防御率1.38
【4/21予告先発】 ー （長野、18:00)巨人:(0勝1敗、防御率1.38)中日:(1勝1敗、防御率3.93)。
📌 関連ポスト
https://twitter.com/sanspo_giants/status/2046124449402179733
【変更情報の要旨】
4月21日の予告先発が発表されました。巨人軍の先発投手は、今季0勝1敗、防御率1.38の投手が長野での試合に登板します。
💬 このニュース、どう見る？
【具体的な変更内容】
4月21日（日）の試合は長野で18:00に開始されます。
巨人軍の先発投手は、今季0勝1敗、防御率1.38の投手が登板します。
対する中日ドラゴンズの先発投手は、今季1勝1敗、防御率3.93の投手が登板します。
【この変更が意味すること】
4月21日の予告先発が発表されました。巨人軍の先発投手は今季0勝1敗、防御率1.38という成績です。この防御率1.38という数字は、安定した投球内容を示していると解釈できます。この投手が長野の地でどのような投球を見せるのか、非常に気になります。
💬 先に予想を書く？
【関連記事】
巨人スタメン 巨人 1-3 ヤクルト 3番手で 投手が登板、走者を一人出すも…
https://yoshilover.com/62965
巨人スタメン 巨人 1-3 ヤクルト 4番手で 投手が登板、三者連続三振を奪…
https://yoshilover.com/62962
💬 みんなの本音は？
📰 参照元: サンスポ / サンスポ巨人X
https://twitter.com/sanspo_giants/status/2046124449402179733
```

## source/meta facts

- `article_subtype`: `postgame`
- `source_label`: `サンスポ / サンスポ巨人X`
- `source_url`: `https://twitter.com/sanspo_giants/status/2046124449402179733`
- `source_urls`: `https://twitter.com/sanspo_giants/status/2046124449402179733`
- `source_headline`: `【4/21予告先発】 ー （長野、18:00) 巨人:(0勝1敗、防御率1.38`
- `source_summary`: `ー （長野、18:00)巨人:(0勝1敗、防御率1.38)中日:(1勝1敗、防御率3.93)。`
- `title.rendered`: `巨人中日戦 予告先発の数字をどう見るか`
- `source_body_cue`: `ー （長野、18:00)巨人:(0勝1敗、防御率1.38)中日:(1勝1敗、防御率3.93)。`
- `speaker_name`: `not present in source/meta`
- `player_name`: `not present in source/meta`
- `key_quote`: `not present in source/meta`
- `score`: `not present in source/meta`
- `opponent`: `中日`
- `result`: `not present in source/meta`
- `pitching_line`: `not present in source/meta`
- `venue`: `not present in source/meta`
- `game_date`: `not present in source/meta`
- `game_time`: `18:00`
- `notice_type`: `not present in source/meta`
- `player_event`: `not present in source/meta`
- `starter_pitcher`: `not present in source/meta`
- `opponent_lineup_link`: `not present in source/meta`
- `modified`: `2026-04-20T18:00:25`
- `fetched_at`: `2026-04-26T03:13:59.464133+00:00`
- `lineup_order`: `not present in source/meta`

## subtype-aware unlock interface

- `unlock_title`: `巨人中日戦 予告先発 関連数字情報`
- `unlock_subtype`: `pregame`
- `unlock_reason`: `subtype_aware_pregame`
- `title_strategy`: `game_pregame_numeric`
- `source_url`: `https://twitter.com/sanspo_giants/status/2046124449402179733`
- `required_fact_axes`: `game_date`, `game_time`, `opponent`, `source_url`
- `present_fact_axes`: `game_date`, `game_time`, `opponent`, `source_url`
- `interface_match`: `yes`

## 修正文候補

```markdown
【変更情報の要旨】
ー （長野、18:00)巨人:(0勝1敗、防御率1.38)中日:(1勝1敗、防御率3.93)。
中日戦 / 18:00の試合前情報として整理します。
【具体的な変更内容】
元記事にある日程や先発情報を、そのまま押さえておきたい変更です。
【この変更が意味すること】
結果予想より先に、この変更で次の試合前をどう迎えるかがポイントです。
変更の意味は実際の入り方にどう出るかで見えてきます。みなさんの意見はコメントで教えてください！
```

## diff

```diff
--- original.normalized
+++ preview.det
@@ -1,23 +1,8 @@
-📰 サンスポ / サンスポ巨人X ⚾ GIANTS GAME NOTE
-【4/21予告先発】 ー （長野、18:00) 巨人:(0勝1敗、防御率1.38
-【4/21予告先発】 ー （長野、18:00)巨人:(0勝1敗、防御率1.38)中日:(1勝1敗、防御率3.93)。
-📌 関連ポスト
-https://twitter.com/sanspo_giants/status/2046124449402179733
 【変更情報の要旨】
-4月21日の予告先発が発表されました。巨人軍の先発投手は、今季0勝1敗、防御率1.38の投手が長野での試合に登板します。
-💬 このニュース、どう見る？
+ー （長野、18:00)巨人:(0勝1敗、防御率1.38)中日:(1勝1敗、防御率3.93)。
+中日戦 / 18:00の試合前情報として整理します。
 【具体的な変更内容】
-4月21日（日）の試合は長野で18:00に開始されます。
-巨人軍の先発投手は、今季0勝1敗、防御率1.38の投手が登板します。
-対する中日ドラゴンズの先発投手は、今季1勝1敗、防御率3.93の投手が登板します。
+元記事にある日程や先発情報を、そのまま押さえておきたい変更です。
 【この変更が意味すること】
-4月21日の予告先発が発表されました。巨人軍の先発投手は今季0勝1敗、防御率1.38という成績です。この防御率1.38という数字は、安定した投球内容を示していると解釈できます。この投手が長野の地でどのような投球を見せるのか、非常に気になります。
-💬 先に予想を書く？
-【関連記事】
-巨人スタメン 巨人 1-3 ヤクルト 3番手で 投手が登板、走者を一人出すも…
-https://yoshilover.com/62965
-巨人スタメン 巨人 1-3 ヤクルト 4番手で 投手が登板、三者連続三振を奪…
-https://yoshilover.com/62962
-💬 みんなの本音は？
-📰 参照元: サンスポ / サンスポ巨人X
-https://twitter.com/sanspo_giants/status/2046124449402179733
+結果予想より先に、この変更で次の試合前をどう迎えるかがポイントです。
+変更の意味は実際の入り方にどう出るかで見えてきます。みなさんの意見はコメントで教えてください！
```

## 適用 rule list

- `remove_placeholders`: `applied` (先発\s*投手は)
- `remove_empty_headings`: `applied` (💬 このニュース、どう見る？, 💬 先に予想を書く？)
- `remove_optional_sections`: `applied` (📌 関連ポスト, 【関連記事】, 💬 みんなの本音は？)
- `condense_long_speculation`: `not_applied`
- `template_align_pregame`: `applied` (title_strategy=rewrite_display_title)

## acceptance check

- `recommend_for_apply`: `yes`
- `mandatory_pass_count`: `5/5`
- `desirable_pass_count`: `3/3`
- `phase5_pass_count`: `5/5`

### mandatory
- `no_source_meta_fabrication`: `PASS` (ok)
- `no_placeholder_residual`: `PASS` (ok)
- `rule_list_explicit`: `PASS` (rendered=5, applied=4)
- `unified_diff_format`: `PASS` (ok)
- `wp_gemini_deploy_zero`: `PASS` (preview-only script; WP write 0 / Gemini call 0 / deploy 0)

### desirable
- `fixed_not_longer_than_original`: `PASS` (225 <= 794)
- `section_count_not_expanded`: `PASS` (3 <= 6)
- `facts_coverage_ge_80pct`: `PASS` (100.0%)

### phase5
- `title_body_integrity`: `PASS` (中日 / 18:00)
- `subtype_match`: `PASS` (subtype_aware_pregame)
- `numeric_guard`: `PASS` (ok)
- `placeholder_absence`: `PASS` (ok)
- `body_contract_pass`: `PASS` (ok)
