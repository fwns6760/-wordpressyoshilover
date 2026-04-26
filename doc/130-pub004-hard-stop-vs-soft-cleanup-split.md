# 130 pub004-hard-stop-vs-soft-cleanup-split

## meta

- number: 130
- alias: -
- owner: Claude Code(設計)/ Codex A or B(実装、disjoint scope で並走可)
- type: ops / publish gate logic refactor
- status: READY
- priority: **P0**(105 ramp viability の前提、即 fire)
- lane: A or B(両方 OK、`src/guarded_publish_evaluator.py` 改修中心)
- created: 2026-04-26
- parent: 105(PUB-004-D)/ PUB-004-A / PUB-002-A
- policy lock: 2026-04-26(Hard Stop only hold + Soft Cleanup publish OK)

## 目的

105 dry-run で全 97 件が Red 落ちした原因 = filter strict 過ぎ。
WordPress publish は **noindex / X なし / SNS なし** なので、致命的でない品質問題は **公開後に後追い修正**で良い。

Red 条件を **Hard Stop / Soft Cleanup** の 2 分類に再設計。
`publishable = NOT hard_stop`(soft_cleanup は publishable + cleanup_log/yellow_log 記録)。

## Hard Stop(必ず hold、絶対 publish しない)

| flag | 既存対応 | 内容 |
|---|---|---|
| `unsupported_named_fact` | 新規 | source にない具体事実(数値 / 日付 / 選手名 etc.) |
| `obvious_misinformation` | 新規 | 明らかな誤情報(scores / dates / player status) |
| `injury_death_severe` | 既 `injury_death` | 故障 / 離脱 / 登録抹消 / 診断 / 症状 |
| `title_body_mismatch_strict` | 既 `title_body_mismatch` strict 部分 | 完全不一致(別記事レベル) |
| `cross_article_contamination` | 新規 | 別記事 lineup / 数字混入 |
| `x_sns_auto_post_risk` | 新規 | WP plugin / hook で auto-tweet 配線がある post(WP REST publish では本来発火しないが念のため) |
| `lineup_duplicate_excessive` | 既 `lineup_duplicate_absorbed_by_hochi` 部分 | 同 game / 同スタメン の **過剰**重複(同 player 同状況 既 publish 多数) |

## Soft Cleanup(publish OK + cleanup_log / yellow_log)

| flag | 既存対応 | 内容 |
|---|---|---|
| `heading_sentence_as_h3` | 既設 | 本文文の H3 化 → cleanup で p 化 |
| `weird_heading_label` | 既設 | ラベルと内容不一致 |
| `dev_log_contamination` | 既設 | dev block 混入 |
| `site_component_mixed_into_body_middle` | 既 Red、本 ticket で Soft へ降格 | site 部品中盤混入 |
| `site_component_mixed_into_body_tail` | 既 Yellow | site 部品末尾(変更なし)|
| `speculative_title` | 既 Red、本 ticket で Soft へ降格 | title speculative phrase |
| `title_body_mismatch_partial` | 既 `title_body_mismatch` partial 部分 | 071 SUBJECT_ABSENT / EVENT_DIVERGE(完全別物 ではなく部分的)|
| `missing_primary_source` | 既設、109 で改善対象 | source 弱い |
| `subtype_unresolved` | 既設、110 で改善対象 | other 落ち |
| `long_body` | 既設、111 で改善対象 | prose >3500 |
| `numerical_anomaly_low_severity` | 新規 | 打率 .400 超 等(致命的でなく確認推奨レベル) |

## 新運用(2026-04-26 cap 変更後)

1. **Hard Stop ある post → 個別 hold**(publishable: false、**全体停止しない**、他 post は publish 進行)
2. **Soft Cleanup のみ → publishable: true**、publish 後 cleanup_log + yellow_log 記録
3. PUB-004-B runner で cleanup 実行(`heading_sentence_as_h3` / `dev_log_contamination` 既設 detector で apply)
4. 公開後に 108(audit)/ 109/110/111/112 で後追い修正
5. **X / SNS POST は 0 件のまま**(PUB-005 gate まで禁止、本 ticket は WP publish のみ対象)
6. **user 確認なし**、daily cap **1 回 20 本 / 1 日 100 本**(新 cap)
7. **10 本ごとに軽い postcheck**(public URL HTTP 200 確認 + 記事内容 read-only 確認)
8. **mail 通知大量送信防止** = publish-notice 側で batch / suppress 別管理(131 で実装、本 ticket と並走)
9. Red-hard 出たら **その記事だけ hold**、全体停止なし

## PUB-004-B cap 改修(本 ticket scope に含める)

- `--max-burst` default 3 → **20**(host code で enforce、env / flag で緩めない range は 1-30)
- daily cap 10 → **100**(JST 0:00 reset)
- 10 件ごとに postcheck round trip(WP REST GET で status=publish 確認)
- Hard Stop 個別 hold logic(全体 abort ではなく per-post skip + log)

## 実装範囲(narrow 改修)

- 改修: `src/guarded_publish_evaluator.py`
  - Red flag を `hard_stop` / `soft_cleanup` に分類する dict / set 追加
  - `publishable` 判定 = `NOT (any flag in hard_stop)`(soft_cleanup ある場合も publishable: true)
  - 出力 JSON に `hard_stop_count` / `soft_cleanup_count` 内訳追加
  - 既存 `red_flags` 配列は維持(後方互換)、`category: hard_stop|soft_cleanup` 追加
- 改修: `src/guarded_publish_runner.py`(必要時)
  - Soft Cleanup で publish 進行(既 `heading_sentence_as_h3` / `dev_log_contamination` cleanup 既設利用)
  - yellow_log / cleanup_log 既設 + Soft Cleanup record 追加
- tests: `tests/test_guarded_publish_evaluator.py` / `tests/test_guarded_publish_runner.py`(既存 + Soft Cleanup case 追加)

## 実装制約

- 既存 17+9 件 evaluator tests baseline 維持
- 既存 17 件 runner tests baseline 維持
- WP write 一切なし(本 ticket = filter logic 改修のみ)
- API call なし
- backend Python のみ、front / .env / secret / Cloud Run env 触らない
- requirements*.txt 改変なし
- `git add -A` 禁止 / `git push` 禁止(Claude が後で push)

## acceptance

1. PUB-004-A evaluator が hard_stop / soft_cleanup を分類
2. publishable = NOT hard_stop(soft_cleanup あっても publishable)
3. 出力 JSON に hard_stop_count / soft_cleanup_count 内訳
4. 既存 tests pass(suite baseline 維持)
5. 新 tests +N で hard_stop / soft_cleanup 各 case verify
6. 105 再 dry-run autonomous で publishable 件数 > 0 想定(現 97 Red のうち、injury_death 35 件以外は soft 寄り)

## 後続(本 ticket land 後の autonomous 連鎖)

1. **105 再 dry-run autonomous**(Claude 直、PUB-004-A 改修反映の publishable 件数確認)
2. **live ramp 試行**(PUB-004-B `--live --max-burst 3 --daily-cap-allow`、burst 3 件 autonomous publish)
3. publish-notice mail 自動配信(既存 095 cron tick で 4 件配信、user は Gmail 着信で確認)
4. cleanup_log / yellow_log を 108/109/110/111/112 後追いで改善

## 関連 file

- `doc/PUB-004-guarded-auto-publish-runner.md`(parent contract)
- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(R 判定 contract)
- `doc/105 / PUB-004-D`(backlog ramp)
- `doc/118-pub004-red-reason-decision-pack.md`(Red 内訳 baseline)
- `doc/123-pub004-auto-publish-readiness-and-regression-guard.md`(readiness 確認)
- `src/guarded_publish_evaluator.py`(改修対象)
- `src/guarded_publish_runner.py`(改修対象 / 必要時)
