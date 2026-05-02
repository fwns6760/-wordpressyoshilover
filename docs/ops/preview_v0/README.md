# preview_v0

`GCP Codex WP本文修正プレビュー v0` の preview-only 出力。

## scope

- 対象 subtype: `postgame`, `farm_result`
- サンプル数: `5`
- 入力 source: `logs/cleanup_backup/*.json` の read-only backup
- 実施しないこと: WP write / publish 状態変更 / Gemini call / deploy / env 変更

## body transcription note

- 各 sample の `## 元本文` は `logs/cleanup_backup/*.json` の `content.rendered` を review 用に正規化した全文転記。
- raw HTML 本体は backup JSON 側に残っている。
- `## diff` は raw HTML ではなく、この正規化本文から deterministic preview 候補への unified diff。

## deterministic rule list

- placeholder 削除
- 空見出し削除
- source/meta にない optional section 削除
- CTA / fan-voice / related-posts のような preview 検証に不要な補助要素削除
- 冗長な一般論 / 推測文の短文化
- subtype ごとの固定テンプレへ寄せ
- source/meta にない数字 / 勝敗 / 選手名 / 投手成績は補完しない

## sample index

- `sample_postgame_1.md`
  - backup: `logs/cleanup_backup/63304_20260426T030324.json`
  - post_id: `63304`
  - low-quality pattern: `score/opponent placeholder`, `broken snippet`, `unsupported optional sections`, `long generic inference`
- `sample_postgame_2.md`
  - backup: `logs/cleanup_backup/63274_20260426T030552.json`
  - post_id: `63274`
  - low-quality pattern: `game-result template drift`, `score missing`, `fan voice not source-backed`, `long generic inference`
- `sample_postgame_3.md`
  - backup: `logs/cleanup_backup/63505_20260426T012330.json`
  - post_id: `63505`
  - low-quality pattern: `hero-name placeholder`, `result placeholder`, `fan voice overgrowth`, `long generic inference`
- `sample_farm_result_1.md`
  - backup: `logs/cleanup_backup/63232_20260426T032533.json`
  - post_id: `63232`
  - low-quality pattern: `empty sections`, `generic filler`, `source-unbacked optional sections`
- `sample_farm_result_2.md`
  - backup: `logs/cleanup_backup/63249_20260426T030552.json`
  - post_id: `63249`
  - low-quality pattern: `title restatement only`, `empty sections`, `generic filler`
