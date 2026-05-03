# preview_v0 format spec

`preview_v0` の sample doc は、manual sample / generated sample ともに以下の section contract を基本にする。

## section order

1. `# sample_<subtype>_<id or ordinal>`
2. top metadata bullets
   - `post_id`
   - `backup_path`
   - `subtype`
   - `quality_flags`
3. `## 元本文`
   - `logs/cleanup_backup/*.json` の `content.rendered` を review 用に deterministic 正規化した本文
4. `## source/meta facts`
   - `guarded_publish_history` と backup 本文から抽出した facts
   - `source/meta` にない値は `not present in source/meta`
5. `## 修正文候補`
   - subtype template に寄せた preview-only markdown
   - source-backed facts と静的文言だけで構成する
6. `## diff`
   - `original.normalized -> preview.det` の unified diff
7. `## 適用 rule list`
   - deterministic rule ごとの `applied` / `not_applied`
8. `## acceptance check`
   - mandatory 5
   - desirable 3

## rendering rules

- `WP write = 0`
- `Gemini call = 0`
- `deploy = 0`
- `source/meta` にない `数字 / 選手名 / 勝敗 / 投手成績` は補完しない
- diff は必ず `--- original.normalized` / `+++ preview.det` header を使う
- rule list は deterministic function 名をそのまま載せる

## acceptance items

### mandatory

1. `no_source_meta_fabrication`
2. `no_placeholder_residual`
3. `rule_list_explicit`
4. `unified_diff_format`
5. `wp_gemini_deploy_zero`

### desirable

1. `fixed_not_longer_than_original`
2. `section_count_not_expanded`
3. `facts_coverage_ge_80pct`

## note on existing 5 samples

- `sample_postgame_1..3.md` / `sample_farm_result_1..2.md` は manual preview の初期成果物。
- scriptized generator の出力は core section contract を維持したまま、`## acceptance check` を明示追加する。
