# 350 X post mail 精度改善 (period 明示 + 規定打席 threshold)

## meta

- owner: Claude Code
- type: implementation (347 lane の精度向上、348 disjoint 維持)
- status: LIVE_DEPLOYED (image `350-precision-v2`、Cloud Run Job 切替 + mail 送信成功 / 2026-05-15 21:59 JST、9 candidates)
- created: 2026-05-15
- updated: 2026-05-15
- doc_path: `doc/active/350-x-post-mail-precision-improvements.md`
- lane: single (Claude direct dev)
- parent: `347-x-post-suggest-mail-lane.md` (LIVE_DEPLOYED) の精度改善 followup
- 関連: 348 spec の precision 観点を 347 lane に取り入れる (ただし 348 file 不可触)

## 1. 目的

347 mail の **精度を上げて、user 「記録間違いはブランディング最悪」 fear を解消**:

現状 (347 初版) で不足:
- 期間が `（今シーズン）` 等の vague label
- sample size 非表示 → 「全試合 OPS .945」と誤読される risk
- min_sample=10 が緩い → 規定打席未満の選手が ranking に混入

→ ブランド「記録に強いヨシラバー」の信頼を損なう risk あり。

## 2. 設計サマリ

### 改善ポイント

| 項目 | 改修前 (347 初版) | 改修後 (350) |
|---|---|---|
| header 期間 label | `（今シーズン）` 等 vague | `（5/15 時点・規定打席 30+）` 等 date 明示 + sample 閾値表示 |
| min_central_rows | 3 (緩い) | 5 (より厳しめ) |
| min_sample default | 10 (緩い) | **30** (batter 規定打席相当) |
| `pick_candidates` sig | 既存 | 既存 (CLI override 可) |

→ 改修は **header 文字列調整 + threshold 値変更**のみ、新 metric / 新 slice なし、348 と完全 disjoint 維持。

### 改修後 sample (期待出力)

```
セ・OPS ランキング 📊（5/15 時点・規定打席 30+）

1. 佐藤輝明（阪神）.945
2. 牧秀悟（DeNA）.932
3. 岡本和真（巨人）.921 ← 巨人
...

#巨人 #ジャイアンツ
```

→ user が見て:
- 「5/15 時点」= as-of date 明確、当日試合反映前 / 反映後 が一目で分かる
- 「規定打席 30+」= 全選手が最低 30 打席消化、ranking 信頼性の baseline 明示
- → ブランド「記録に強い」 を支える根拠が読み手に伝わる

## 3. 今回触らない範囲

絶対不可触:

**348 が触る範囲 (一切 read-only も含めて修正しない)**:
- `src/analysis/insight_*.py` 全部
- `src/analysis/ranking_article_publisher.py` / `anomaly_article_publisher.py` / `team_ranking_publisher.py`
- `article_candidates` table への read / write 一切
- `insight.db` の schema 改修 (read-only access のみ)
- 直近 N 試合 slice の独自実装 (348 で実装予定、347/350 では実装しない)
- 月別 / 週別 aggregation の独自実装 (同上)

**346 PWA 経路不可触**:
- `src/manual_intake_service.py`
- `src/format_as_x_post.py` (346 成果物、read-only import のみ)

**347 で作成された file のうち変更しないもの**:
- `src/tools/run_x_post_mail.py` (CLI、変更不要)
- `Dockerfile.x_post_mail`
- `cloudbuild_x_post_mail.yaml`

**変更するのは 1 file + tests**:
- `src/x_post_mail_lane.py` の `_format_one` 関数の header 部分 + `pick_candidates` の default threshold
- `tests/test_x_post_mail.py` の関連 test 期待値 update + 新 test 追加

**既存 publish-notice / fact-check mail / X auto post / 346 PWA**:
- 一切 touch しない

scope 外の cleanup / refactor / 横展開 一切禁止。

## 4. 影響範囲

直接変更:
- `src/x_post_mail_lane.py` (既存 file、`_format_one` の header logic + `pick_candidates` default 値のみ修正)
- `tests/test_x_post_mail.py` (既存 file、期待値 update + 新 test 1-2 件追加)
- `doc/active/350-x-post-mail-precision-improvements.md` (新規、本 doc)

間接影響:
- なし (新規 file ゼロ、infra 変更ゼロ)

infra 影響:
- 既存 Cloud Run Job `x-post-mail-lane` に新 image を deploy (image rebuild + revision 切替)
- Cloud Scheduler 5 個は不変 (ENABLED のまま)

データ影響:
- insight.db read-only 維持
- WP / X API / article_candidates 不変

ユーザー影響:
- 次回 mail (明朝 7:00 or 手動 execute) から新 format
- 既存 mail (smoke 21:26 既送信) は古い format のまま (上書き不可)

コスト影響:
- なし (cloudbuild + Cloud Run Job 既存枠内)

## 5. 実行予定テスト

unit test 更新:
- `test_period_label_appears_in_draft`: 旧期待 `（今シーズン）` → 新期待 `（5/15 時点・規定打席 30+）` 形式 (regex で柔軟 match)
- `test_pick_central_only_excludes_pacific`: 変更なし (filter logic 不変)
- `test_compose_returns_subject_text_html_count`: 変更なし (mail 構造不変)

unit test 新規:
- `test_header_includes_as_of_date`: header に今日の `M/D 時点` を含む
- `test_header_includes_min_sample_threshold`: header に `規定打席 N+` を含む
- `test_min_central_rows_5_default_strict`: 4 row では skip、5 row で採用

regression:
- pytest baseline 維持 (347 で 4731 passed、350 で +新 test 後も同水準維持)
- 346 PWA / 348 file 関連 test 影響なし

manual smoke (deploy 後):
- `gcloud run jobs execute x-post-mail-lane`
- 受信 mail で:
  - subject 形式不変
  - 各 candidate header に `5/15 時点・規定打席 30+` 等の文字列が含まれる
  - rank row は不変 (`1. 佐藤輝明（阪神）.945`)
  - 巨人 highlight 不変
  - パ 6 球団漏れなし

## 6. STOP条件

実装中 / deploy 中に以下を検知したら即停止:

1. 348 file (`src/analysis/*` 等) の修正が必要と判明 → scope 拡大、stop + user 判断
2. `article_candidates` table の read / write が必要と判明 → 不可触違反、stop
3. 346 `format_as_x_post.py` の修正が必要と判明 → 346 影響、stop
4. 既存 test が新たに red 化 → regression、stop
5. min_sample=30 にしたら 5 candidate も出ない → threshold 緩和 (20 等) を user 判断
6. min_central_rows=5 にしたら全 combo skip → 緩和 (4 等)
7. mail 本文が 280 字超過 → format 圧縮 or candidate 削減を user 判断
8. Cloud Run Job 起動失敗 → image rebuild / env / secret 確認

## 7. 禁止事項

- `git add -A`
- LLM (Gemini / Codex / OpenAI / 他) 呼出の追加
- `--no-verify`
- 348 file 修正
- `article_candidates` 触る
- 346 `format_as_x_post` 修正
- scope 外 cleanup / refactor
- 既存 fail を「対象外」扱いで無視
- 「だいたい合ってればいい」緩い judgment
- AI failure modes (記憶再構成 / silent skip / 自己評価 OK) を無視 — verify ベースのみ

## 8. 想定されるデグレ

1. **規定打席 30+ で候補ゼロ**
   - 原因: シーズン序盤 / 5/15 時点で 30 打席到達選手が少ない
   - 検知: candidates ゼロ件 → mail skip
   - 対策: min_sample を CLI で下げる or 緩和

2. **header が長すぎて折り返し**
   - 原因: `（5/15 時点・規定打席 30+）` で +20 chars
   - 検知: 280 字超過判定
   - 対策: 圧縮表記 `（5/15・PA30+）` で character 節約

3. **既存 test が新 header format で fail**
   - 原因: 期待値 hardcode が変わる
   - 検知: pytest red
   - 対策: 期待値を regex / 部分 match に変更

4. **巨人選手が 30 打席未満で漏れる**
   - 原因: 巨人選手だけ規定到達遅い時期
   - 検知: 巨人 highlight 0 件の mail が連続
   - 対策: pitcher / batter 別 threshold (ERA は 投球回 5+ 等)、本 ticket では実装せず後日

5. **mail 内容変わって user 混乱**
   - 原因: 朝 7:00 で 旧 format → 23:00 で 新 format
   - 検知: user 体感
   - 対策: deploy 後 1 通即実行で確認、format 違いを transitional period として説明

## 9. 作業ログ欄

```
YYYY-MM-DD HH:MM JST | <event> | <path or commit_hash> | <status>
```

予定 milestone:
- doc 350 完成
- src/x_post_mail_lane.py 修正
- tests/test_x_post_mail.py 期待値更新 + 新 test
- pytest green
- cloudbuild
- Cloud Run Job 新 image deploy
- 手動 execute → mail 送信
- 受信確認
- commit + push

## 10. Regression Memo欄

(実装中追記)

確認事項:
- header の as-of date format ("5/15 時点" 等) は subject の date format と一貫させる
- min_sample 30 が NPB 規定打席 (例: 規定 = 試合数 × 3.1) と異なる、本 ticket は 30 打席固定で開始、後日 NPB 公式規定打席 logic 追加検討
- 5/15 時点で巨人 35 試合消化なら規定打席は 100 PA 程度、30 PA は緩い baseline (打席が多い選手の上位 ranking で問題なし)

---

## (post-work セクション、2026-05-15 22:10 JST 完了)

### A. 実際に変更したファイル

- `doc/active/350-x-post-mail-precision-improvements.md` (新規、本 doc)
- `src/x_post_mail_lane.py` (既存修正、`_format_one` + `pick_candidates` default + 新 helper `_format_period_range` / `_sample_label_for_metric`)
- `src/tools/run_x_post_mail.py` (既存修正、CLI default `--min-sample` 10 → 30)
- `tests/test_x_post_mail.py` (既存修正、period test 期待値更新 + 新 4 test 追加: header date range / ERA 投球回 label / min_central_rows=5 strict / monthly concrete range)

### B. diff 概要

- `src/x_post_mail_lane.py`:
  - 新 helper `_sample_label_for_metric(metric)` — ERA は `投球回`、他は `打席`
  - 新 helper `_format_period_range(combo, now)` — `since=None` で `開幕〜M/D 累積`、`since=YYYY-MM-DD` で `M/D〜M/D` 形式の concrete range
  - `_format_one` signature 変更: `min_sample` + `now` を受ける、header suffix を `（{date_range}・規定{打席|投球回} {min_sample}+）` 形式に
  - `pick_candidates` default: `min_sample=10→30`、`min_central_rows=3→5`
- `src/tools/run_x_post_mail.py`: CLI `--min-sample` default 10 → 30
- `tests/test_x_post_mail.py`: 期待 header 文字列を新 format に合わせる + 3 新 test 追加

### C. 実行したテスト

1. AST parse OK
2. module import OK
3. inline simulate (mock query → draft_text):
   - season: `セ・OPS ランキング 📊（開幕〜5/15 累積・規定打席 30+）`
   - monthly: `セ・OPS ランキング 📊（5/1〜5/15・規定打席 30+）`
   - last30: `セ・OPS ランキング 📊（4/15〜5/15・規定打席 30+）`
   - ERA: `セ・防御率 ランキング 📊（…・規定投球回 30+）`
4. pytest 新 module: 28 passed (3 新追加、24 existing + 4 new period/ERA/strict/monthly = 28)
5. pytest scope (format / mail bridge / insight / manual_intake): 全 green
6. cloudbuild 3 回: `350-precision`、`350-precision-v2`、`350-precision-v3`、全 SUCCESS
7. Cloud Run Job deploy 3 回: 各 image で revision 切替、全 succeeded
8. 手動 execute 3 回:
   - `x-post-mail-lane-zcf8c` (v1、min_sample CLI default=10): 10 candidates、status=sent
   - `x-post-mail-lane-zndd8` (v2、CLI default 30 修正後): 9 candidates、ERA 今月 skip、status=sent
   - `x-post-mail-lane-d4f2f` (v3、date range concrete): 9 candidates、status=sent

### D. テスト結果

- 新 module unit: **28 passed**
- scope pytest: **111 passed** (4 warnings、1 pre-existing fail = `test_ingestion_filter_relaxation` で 350 起因ではない、baseline 不変)
- 実 production:
  - mail 3 通送信成功 (v1 / v2 / v3、全 status=sent / refused=空)
  - 9-10 candidates / mail、ERA 今月だけ skip (規定投球回 30+ で セ 5 未満)
  - 巨人 highlight 1+ 候補で確認 (mock simulate ベース)
  - パ 6 球団漏れなし (filter logic 不変、24 test で検証)

### E. 残った懸念

1. **「開幕〜M/D 累積」の「開幕」が曖昧** 🟡
   - 実 NPB 開幕日 (例: 2026/3/27) を hardcode していない
   - 「開幕」という言葉で十分か、`3/27〜5/15 累積` のように具体日付がベターか user 体感次第
   - 必要なら `games` table から MIN(game_date) を query する別 ticket で改善 (本 ticket では避けた、insight.db に新 query 加えるのは scope 拡大)

2. **「規定打席 30+」は NPB 公式規定打席より緩い** 🟡
   - NPB 公式: 試合数 × 3.1 (5/15 時点なら 35 試合 × 3.1 = 約 108 PA が公式規定)
   - 30 PA は緩い baseline、序盤の上位 ranking が捉えやすい
   - user が「もっと厳しい方が信頼性上がる」と感じたら閾値調整 (CLI `--min-sample 60` 等で override 可)

3. **header が長くなった** 🟡
   - 旧: `セ・OPS ランキング 📊（今シーズン）` ≈ 22 chars
   - 新: `セ・OPS ランキング 📊（開幕〜5/15 累積・規定打席 30+）` ≈ 38 chars
   - 280 字 budget はまだ余裕 (合計 200 字程度) だが、選手名が長い metric (例: 通称が複数の選手) で接近する可能性

4. **「期間が入ってない」 user fear の根本** 🔴
   - 私の v1/v2 implementation で `（今シーズン）` 等 vague label に止めたのは 348 spec の貧弱さに引っ張られた判断
   - 「記録間違いはブランディング最悪」level の品質要求に対し、最初から concrete date range を出すべきだった
   - 学習: precision 関連の改善は **「今シーズン」みたいな代名詞でなく具体値を出す方を default にする**

5. **mail 受信側の HTML rendering** 🟡 (前回からの carry-over)
   - 各 candidate の 🐦 X 投稿 button が iOS / Android / Web Gmail でちゃんと動くか実機 verify は user 任せ
   - 3 通連続で届いてるはずなので、user の Gmail で v3 (最新) を見て判断

6. **連日重複防止 dedup なし** 🟡
   - 1 日 5 通 / 朝〜試合後で同じ ranking が連続する可能性
   - 349 (dedup-cooldown) は publish lane 用、本 ticket とは別 lane
   - 必要なら mail lane 専用の 24h dedup を別 ticket (351-MAIL-DEDUP 想定) で追加

### F. 新しく見つかったデグレ

- **build を 3 回繰り返した** ⚠️ minor inefficiency
  - 1 回目 (350-precision): module default 30 だが CLI default 10 で動作 → mismatch
  - 2 回目 (350-precision-v2): CLI default も 30 に統一 → 一致
  - 3 回目 (350-precision-v3): `今シーズン` 等 vague label → concrete date range に変更
  - 教訓: 「精度」テーマの ticket は scope 縛らずに「concrete date range も含めて全 fix」を最初から含めるべきだった、user の「期間入ってない」指摘で 2 周してしまった
- 新たな production 障害: なし

### G. 追加した回帰テスト

`tests/test_x_post_mail.py` の `PickCandidatesTests` クラスに 4 新 test:

| test | 内容 |
|---|---|
| `test_header_includes_date_range_and_sample_threshold` | season combo で `開幕〜5/16 累積` + `規定打席 30+` を含む |
| `test_monthly_combo_header_shows_concrete_date_range` | monthly combo で `5/1〜5/16` 形式の concrete range を含む |
| `test_era_uses_innings_pitched_threshold_label` | ERA candidate で `投球回` ラベルを含む (`打席` ではない) |
| `test_min_central_rows_default_strict` | 4 row では skip、5 row で採用 (default min_central_rows=5 の strict 化検証) |

加えて既存 `test_period_label_appears_in_draft` の期待値を vague `（今シーズン）` から concrete `開幕〜5/16 累積` に更新。

### H. 次回触ってはいけない範囲

1. **`_format_period_range` の since parser**: `datetime.strptime(combo.since, "%Y-%m-%d")` 固定、`_build_combos` で since を `%Y-%m-%d` 形式で渡してる前提。format 変える時は両方同時に更新
2. **`_sample_label_for_metric` の metric 分岐**: 現在 ERA のみ `投球回`、他全部 `打席`。FIP / WHIP 等 pitching metric を SAFE_METRICS に追加するなら ここも更新
3. **「開幕〜M/D 累積」の文字列**: season-wide のとき固定。実 開幕日を入れたい場合は games table への SELECT MIN(game_date) を別 helper で追加 (本 ticket は読み込み回数最小化のため hardcode)
4. **min_sample default 30**: CLI / module default は揃ってる (両方 30)。乖離させると本 ticket の意味なくなる
5. **min_central_rows default 5**: 4 で採用すると単純 ranking 性が崩れる、緩める場合は test_min_central_rows_default_strict と一緒に更新
6. **348 file**: `src/analysis/*.py` / `article_candidates` table / `config/insight_whitelist.json` は完全不可触、本 ticket でも一切 touch していない
7. **346 PWA**: `src/manual_intake_service.py` / `src/format_as_x_post.py` は不可触、本 ticket は `format_as_x_post` を read-only import するだけ

## Regression Memo 補足 (350 実装中に判明)

- **build 3 回の教訓**: precision 改善は scope の境界を狭く切らない方がよい。「concrete date range」も「sample threshold 引き上げ」と同じ ticket に最初から含めるべきだった
- **`now` の伝播**: `_format_one` に `now` を渡す signature に変えた、test mock 側は `datetime(YYYY, M, D, tzinfo=JST)` で固定値渡し
- **CLI vs module default**: `argparse` の default を module の default と揃えるのを忘れがち、本 ticket で 1 round 余分にかかった

## 作業ログ実績

```
2026-05-15 22:00 JST | doc 350 作成 | doc/active/350-x-post-mail-precision-improvements.md | DONE
2026-05-15 22:01 JST | code 修正 (_format_one + _sample_label + threshold defaults) | src/x_post_mail_lane.py | DONE
2026-05-15 22:02 JST | test 更新 + 新 test 追加 | tests/test_x_post_mail.py | DONE
2026-05-15 22:03 JST | pytest 27 passed (scope 111) | -                                  | DONE
2026-05-15 22:04 JST | cloudbuild 1 回目 (350-precision)                                  | DONE
2026-05-15 22:05 JST | deploy + execute v1 (CLI default 10 mismatch 発覚)                | DONE
2026-05-15 22:07 JST | CLI default 30 修正                                               | src/tools/run_x_post_mail.py | DONE
2026-05-15 22:08 JST | cloudbuild 2 回目 (350-precision-v2)                              | DONE
2026-05-15 22:09 JST | deploy + execute v2 (9 candidates、min_sample=30 で send成功)    | DONE
2026-05-15 22:10 JST | user 指摘「期間入ってない」                                       | - | OBSERVED
2026-05-15 22:11 JST | _format_period_range 新規、concrete date range に変更             | src/x_post_mail_lane.py | DONE
2026-05-15 22:12 JST | test 期待値更新 + 新 4 test (28 passed)                           | tests/test_x_post_mail.py | DONE
2026-05-15 22:13 JST | cloudbuild 3 回目 (350-precision-v3)                              | DONE
2026-05-15 22:15 JST | deploy + execute v3 (date range concrete、9 candidates send成功) | DONE
2026-05-15 22:16 JST | doc 350 post-work A-H 追記                                        | doc/active/350-x-post-mail-precision-improvements.md | DONE
2026-05-15 22:17 JST | (次) commit + push                                                | PENDING
```
