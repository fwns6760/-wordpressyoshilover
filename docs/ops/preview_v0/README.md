# preview_v0

`GCP Codex WP本文修正プレビュー v0` の preview-only 出力。

## scope

- phase 4 validated subtype: `postgame`, `farm_result`, `manager`, `lineup`
- phase 5 unlock-scope extension: `player_comment`, `farm_lineup`, `pregame`, `roster_notice`, `若手選手(player_notice -> farm_player_result)`
- 入力 source: `logs/cleanup_backup/*.json` の read-only backup
- 実施しないこと: WP write / publish 状態変更 / Gemini call / deploy / env 変更
- coverage status: [phase5_coverage_matrix.md](/home/fwns6/code/wordpressyoshilover/docs/ops/preview_v0/phase5_coverage_matrix.md)

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
- `lineup` は `【試合概要】 / 【スタメン一覧】 / 【先発投手】 / 【注目ポイント】` の order 構造を保持
- source/meta にない数字 / 勝敗 / 選手名 / 投手成績は補完しない
- mandatory 5 / desirable 3 を sample ごとに自動評価し、`recommend_for_apply` を出力する

format contract:

- [FORMAT.md](/home/fwns6/code/wordpressyoshilover/docs/ops/preview_v0/FORMAT.md)

## generator

preview generator は `scripts/preview_v0_generate.py`。

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 scripts/preview_v0_generate.py \
  --post-ids 63466 63464 63509 \
  --output-dir docs/ops/preview_v0/generated
```

optional:

- `--history-path logs/guarded_publish_history.jsonl`
- `--yellow-log-path logs/guarded_publish_yellow_log.jsonl`
- `--subtype lineup`
- `--subtype-map 63466=postgame 63464=farm_result 63509=manager`

phase 5 category mode:

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 scripts/preview_v0_generate.py --category player_comment --count 1 --dry-run
python3 scripts/preview_v0_generate.py --category farm_lineup --count 1 --dry-run
python3 scripts/preview_v0_generate.py --category pregame --count 2 --dry-run
python3 scripts/preview_v0_generate.py --category roster_notice --count 1 --dry-run
python3 scripts/preview_v0_generate.py --category player_notice --count 1 --dry-run
```

## sample index

### existing manual samples (5)

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

### generated samples (phase 4 baseline 10)

- phase 5 generated additions は [phase5_coverage_matrix.md](/home/fwns6/code/wordpressyoshilover/docs/ops/preview_v0/phase5_coverage_matrix.md) を参照

- `generated/sample_lineup_63393.md`
  - backup: `logs/cleanup_backup/63393_20260426T012330.json`
  - post_id: `63393`
  - low-quality pattern: `heading sequence keep`, `title_body_mismatch_partial`, `order/starter preserve`
- `generated/sample_lineup_63272.md`
  - backup: `logs/cleanup_backup/63272_20260426T030552.json`
  - post_id: `63272`
  - low-quality pattern: `heading_sentence_as_h3`, `empty starter heading`, `lineup structure retention`
- `generated/sample_postgame_63466.md`
  - backup: `logs/cleanup_backup/63466_20260426T012330.json`
  - post_id: `63466`
  - low-quality pattern: `subtype_unresolved`, `anonymous player slot`, `loss-side inning narrative overgrowth`
- `generated/sample_postgame_63479.md`
  - backup: `logs/cleanup_backup/63479_20260426T012330.json`
  - post_id: `63479`
  - low-quality pattern: `missing_primary_source`, `draw-side summary drift`, `anonymous slugger slot`
- `generated/sample_postgame_63515.md`
  - backup: `logs/cleanup_backup/63515_20260426T012330.json`
  - post_id: `63515`
  - low-quality pattern: `speculative_title`, `hero-copy contamination`, `anonymous player slot`
- `generated/sample_farm_result_63464.md`
  - backup: `logs/cleanup_backup/63464_20260426T012330.json`
  - post_id: `63464`
  - low-quality pattern: `anonymous player slot`, `loss-side farm summary`, `missing_primary_source`
- `generated/sample_farm_result_63510.md`
  - backup: `logs/cleanup_backup/63510_20260426T012330.json`
  - post_id: `63510`
  - low-quality pattern: `missing_primary_source`, `heading_sentence_as_h3`, `score-only recap drift`
- `generated/sample_farm_result_63230.md`
  - backup: `logs/cleanup_backup/63230_20260426T030552.json`
  - post_id: `63230`
  - low-quality pattern: `RT contamination`, `stale_for_breaking_board`, `farm result over-template`
- `generated/sample_manager_63509.md`
  - backup: `logs/cleanup_backup/63509_20260426T012330.json`
  - post_id: `63509`
  - low-quality pattern: `title_body_mismatch_partial`, `heading_sentence_as_h3`, `fan voice contamination`
- `generated/sample_manager_63222.md`
  - backup: `logs/cleanup_backup/63222_20260426T030552.json`
  - post_id: `63222`
  - low-quality pattern: `quote_misalign`, `speculative_title`, `heading_sentence_as_h3`
