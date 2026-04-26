# 130 pub004-hard-stop-vs-repairable-before-publish

## meta

- number: 130
- alias: -
- owner: Claude Code(設計)/ Codex A(実装)
- type: ops / publish gate logic refactor + pre-publish cleanup chain
- status: **READY**(P0、105 live ramp の前提、即 fire)
- priority: **P0**
- lane: A
- created: 2026-04-26
- policy_revised: 2026-04-26(Soft Cleanup を **publish 前 cleanup** へ変更、Repairable before publish に rename)
- parent: 105(PUB-004-D)/ PUB-004-A / PUB-004-B / PUB-002-A
- supersedes_filename: `130-pub004-hard-stop-vs-soft-cleanup-split.md`(旧 spec、本 file が正)

## 目的

105 dry-run で全 97 件 Red 落ち。filter strict 過ぎ + 「Hard Stop 以外 = 全 publish」も雑。
WordPress publish は noindex / X なし / SNS なし だが、それでも本文崩れ・h3 誤用・サイトコンポ混入は **公開前に直してから出す** が正しい。

修正方針:
- 記事を 3 分類:
  - **hard_stop**(絶対 hold)
  - **repairable_before_publish**(cleanup → verify → publish)
  - **publish_clean**(そのまま publish)
- `publishable = NOT hard_stop`
- repairable は cleanup 必須 + cleanup 後の post-condition 検証必須
- cleanup 失敗 / 曖昧 / source 消失 / 本文崩壊 → hold

## 3 分類

### hard_stop(必ず hold、絶対 publish しない)

| flag | 内容 |
|---|---|
| `unsupported_named_fact` | source にない具体事実(数値 / 日付 / 選手名 etc.) |
| `obvious_misinformation` | 明らかな誤情報(scores / dates / player status) |
| `injury_death` | 故障 / 離脱 / 登録抹消 / 診断 / 症状(4/17 事故と同質リスク) |
| `title_body_mismatch_strict` | 完全不一致(別記事レベル) |
| `cross_article_contamination` | 別記事 lineup / 数字混入 |
| `lineup_duplicate_excessive` | 同 game / 同スタメンの過剰重複 |
| `x_sns_auto_post_risk` | WP plugin / hook で auto-tweet 配線がある post(発火懸念) |

### repairable_before_publish(cleanup → verify → publish)

| flag | cleanup |
|---|---|
| `heading_sentence_as_h3` | h3 を p に降格 |
| `dev_log_contamination` | dev log / debug print を本文から除去 |
| `site_component_mixed_into_body` | サイトコンポ(menu / nav / sidebar など)を本文から除去 |
| `weird_heading_label` | 不自然な見出しラベル(ヘルパー文字列等)を整える |
| `ai_tone_heading_or_lead` | AI っぽい見出し / 誘導文を整える |
| `light_structure_break` | 軽い構造崩れ(空 p、孤立 br 等) |
| `weak_source_display` | source 表記弱い(URL あり、表示が地味) |
| `subtype_unresolved` | subtype 未解決 → 既存 extractor heuristic で再判定 |
| `long_body` | long body → 圧縮(trailing 余剰 prose 削除) |

### publish_clean

上記いずれにも該当しない記事。

## evaluator(`src/guarded_publish_evaluator.py`)改修

- 定数 set: `HARD_STOP_FLAGS` / `REPAIRABLE_FLAGS`
- 各 reason に `category: hard_stop|repairable|clean` を付与
- `publishable = NOT (any flag in HARD_STOP_FLAGS)`
- `cleanup_required = (any flag in REPAIRABLE_FLAGS) and publishable`
- summary に `hard_stop_count` / `repairable_count` / `clean_count` / `publishable_count` を追加
- 後方互換: `red_flags` / `green_count` / `yellow_count` / `red_count` 維持

## runner(`src/guarded_publish_runner.py` + `src/tools/run_guarded_publish.py`)改修

### cap

- `--max-burst` default **20**(hard cap **30**、host code で 1-30 range enforce)
- `daily-cap` default **100**(JST 0:00 reset 既設)
- CLI help / test fixture に残る "max 3" 文言を全部 20/30/100 に修正

### publish 前 cleanup chain

1. backup 必須(本文 + meta を JSON / file で `logs/cleanup_backup/<post_id>_<ts>.json` に保存)
2. `cleanup_required` の post は publish 前に必ず cleanup を実行(既存 cleanup module 流用)
3. cleanup 後 post-condition verify:
   - 本文が空でない
   - prose >= 100 chars
   - source 表記 / source URL が消えていない(grep で URL hostname / 「出典」「参考」等の anchor)
   - title subject の主要トークンが本文に残存(既存 71 title-body-nucleus-validator の subject 一致 check 流用)
4. 全 verify pass → publish 実行
5. verify fail / cleanup 例外 → **hold**(`cleanup_log` + history に refused 記録、全体 abort しない、次 post へ)

### Hard Stop 個別 hold

- 1 post の Hard Stop で **その post だけ skip**、history に refused 記録
- 全体 abort しない、次 post 進行

### postcheck

- 10 件ごとに WP REST GET status=publish 確認(既存 1 件ごと postcheck の集約版でも可)

### log

- `cleanup_log` JSONL: 各 cleanup の before/after 概要(冒頭 200 char) + applied flags
- `yellow_log` JSONL: cleanup 後に publish した post の post_id + applied flags
- history JSONL: 各 post の publishable / cleanup_required / cleanup_success / hold reason

## tests

### evaluator 新 tests

- `test_hard_stop_only_post_returns_publishable_false`
- `test_repairable_only_post_returns_publishable_true_and_cleanup_required_true`
- `test_hard_stop_plus_repairable_returns_publishable_false`(hard_stop 優先)
- `test_clean_post_returns_publishable_true_and_cleanup_required_false`
- `test_summary_includes_hard_stop_repairable_clean_counts`
- 既存 evaluator tests pass 必須(後方互換)

### runner 新 tests

- `test_cap_20_burst_enforced`(21 件 input → 20 件 publish + 1 件 skip)
- `test_cap_hard_30_rejected_above`(31 件 → 30 件で stop)
- `test_daily_cap_100_enforced`
- `test_hard_stop_post_skipped_no_global_abort`
- `test_repairable_post_cleanup_then_publish`
- `test_repairable_post_cleanup_failed_post_condition_held`(prose < 100 で hold)
- `test_repairable_post_cleanup_source_lost_held`(source URL 消失で hold)
- `test_repairable_post_cleanup_title_subject_lost_held`
- `test_postcheck_every_10_posts_round_trip`
- `test_backup_required_before_cleanup`
- 既存 runner tests pass 必須

## acceptance

1. 3 分類実装(hard_stop / repairable / clean)
2. publishable = NOT hard_stop
3. cleanup_required = repairable + publishable
4. publish 前 cleanup → verify → publish の順
5. cleanup 失敗 / verify 失敗 で hold(全体 abort なし)
6. cap 20 burst / hard 30 / daily 100 統一
7. CLI help から "max 3" 文言消滅
8. 既存 evaluator/runner tests pass(suite baseline 維持)
9. 新 tests +N 全 pass
10. WP live publish この実装便で実行しない(test は mock のみ)

## verify

- `python3 -m pytest tests/test_guarded_publish_evaluator.py tests/test_guarded_publish_runner.py -v`
- `python3 -m unittest discover -s tests 2>&1 | tail -3`(suite baseline 維持)
- `python3 -m src.tools.run_guarded_publish --help`(max 20/30/100 文言確認)

## 不可触

- `src/wp_client.py` / `src/lineup_source_priority.py` / `src/published_site_component_audit.py` 改変(import 流用のみ)
- 既存 cleanup module 改変(import 流用のみ、新 cleanup 機能の追加実装は本 ticket scope 外)
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- automation / scheduler / front / plugin / build
- requirements*.txt 改変
- baseballwordpress repo
- LLM call / mail real-send / X / SNS POST
- WP live publish(test は mock のみ)
- `git add -A`
- **git push**(Claude が後で push)

## 次

- 130 land → 105 再 dry-run → publish_clean / repaired_publishable / hard_stop / hold_due_cleanup_failure 件数確認 → 20 件 burst live ramp(autonomous)
- 131(publish-notice-burst-summary-and-alerts)を 130 land 後に実装
