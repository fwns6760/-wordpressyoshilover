# 118 pub004-red-reason-decision-pack

## meta

- number: 118
- alias: -
- owner: Claude Code(read-only data 整理 + user 提示)
- type: ops / decision support / read-only data
- status: REVIEW_NEEDED(artifact 生成済み、user 提示/再集計待ち)
- priority: P0.5(105 user 判断材料、本 ticket は orchestration / Claude 直)
- lane: A / Claude orchestration
- created: 2026-04-26
- parent: 105(PUB-004-D backlog ramp)
- source: `/tmp/pub004d/full_eval.json`(105 dry-run autonomous 結果、total 97 / Green 0 / Yellow 0 / Red 97)
- artifact: `/tmp/pub004d/decision_pack.json`

## 目的

105 dry-run が **total 97 / Green 0 / Yellow 0 / Red 97** だった理由を整理し、user が ramp go / no-go / filter retune を判断できる **材料**を作る。

**filter 緩和実装ではない**。**live publish ではない**。**user 判断 pack の生成のみ**。

## scope

read-only データ整理 + report:
- **Red 理由 top**(理由分布、上位 N flag)
- **代表 post_id**(各 Red 理由ごとに 3-5 件サンプル + title preview)
- **Yellow 化できそうな候補**(filter 緩和 1-2 軸で Red → Yellow 降格可能なもの推定)
- **絶対 Red 候補**(injury_death / 別記事混入 等の致命的 risk、緩和不可)
- **cleanup で救える候補**(`heading_sentence_as_h3` / `dev_log_contamination` 等で cleanup 後 Green 可能なもの)

## 重要制約

- **filter 緩和実装 / publish ramp 一切禁止**(本 ticket = データ整理のみ)
- live publish / mail / X / SNS 一切禁止
- WP write 一切禁止(read-only autonomous)
- `RUN_DRAFT_ONLY` flip 禁止
- `.env` / secret / Cloud Run env 触らない
- new code 不要(Claude 自身が `/tmp/pub004d/full_eval.json` を集計)

## 不可触

- WP write
- PUB-004-A evaluator の filter logic 改変(本 ticket scope 外、user 判断後の別 ticket = `121-...` 等)
- PUB-004-B / cleanup runner 実行
- automation / scheduler / .env / secret
- baseballwordpress repo
- front / plugin / build
- 既存 src/ 配下
- `git add -A` / `git push`(本 ticket = report 出力のみ、commit 不要 / 必要時 Claude push)

## acceptance

1. Red 理由 top 5(本 chat 内既出: site_component_middle 96 / title_body_mismatch 69 / speculative_title 44 / injury_death 35 / lineup_no_hochi_source 2)
2. 各理由の代表 post_id サンプル(3-5 件 / 理由)+ title preview
3. **Yellow 化候補**: site_component middle 判定を tail or Yellow 緩和すると何件が Green/Yellow に動くか推定
4. **絶対 Red 候補**: injury_death 35 件の post_id list(これは緩和不可、user 公開判断境界)
5. **cleanup 救済候補**: PUB-004-B detector で cleanup 適用後 Green になりうる件数推定
6. user 提示用 1 page summary + raw JSON pack(`/tmp/pub004d/decision_pack.json`)

## test_command

なし(本 ticket = read-only autonomous data 整理、test 不要)

## next_action

1. `/tmp/pub004d/full_eval.json` から Red 理由分布再計算
2. 各 Red 理由ごとに 3-5 件代表 post_id 抽出
3. cross-tab(post_id × 複数 Red flags)で「1 軸緩和で救える」「複数軸ヒットで救えない」分類
4. cleanup 救済候補 = `heading_sentence_as_h3` / `dev_log_contamination` を含む post_id 抽出
5. 出力 `/tmp/pub004d/decision_pack.json` + human summary を本 chat 内で user に提示
6. 123 readiness/regression guard と合わせて user 1 ワード判断:
   - `A` = ramp 中止
   - `B` = filter retune narrow便(別 ticket 起票、本 ticket scope 外)
   - `C` = 108 (cleanup audit) land 後再評価

## 不可侵

- 本 ticket は **filter retune 実装ではない**(別 ticket、user judgment 後)
- 本 ticket は **live publish ramp ではない**(105 BLOCKED_USER 維持)
- 本 ticket は **PUB-004-A 改変ではない**(read-only data 整理のみ)

## 関連 file

- `doc/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`(105 alias)
- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(R 判定 contract)
- `doc/PUB-004-guarded-auto-publish-runner.md`(PUB-004 親、Red 条件)
- `doc/108-existing-published-site-component-cleanup-audit.md`(cleanup 救済候補の根拠 detector)
- `/tmp/pub004d/full_eval.json`(105 dry-run autonomous 結果)
