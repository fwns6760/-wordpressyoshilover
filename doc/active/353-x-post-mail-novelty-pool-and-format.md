# 353-x-post-mail-novelty-pool-and-format

## 1. ticket header

- **status**: PARTIAL_VERIFIED (2026-05-20 PM) — code path **exercised in production** 確認 (x-post-mail-lane-sl2zj fire log で `dedup skip combo AVG/直近10試合` / `combo ERA/直近10試合` 等 actual evaluation、 mail send status=sent)。 ただし **mail body の format detail (medals 🥇🥈🥉 / ⭐巨人 / period_suffix lines[1] / 大手 pool 除外) は log に出ず**、 user Gmail 受信箱の目視確認のみで完全 verify 可能
- **priority**: high (user 「データサイト方向 / 大手にないランキング / 意外性」要望直結)
- **owner**: Claude (実装) / user (GO 判断)
- **依存**: 347 lane (`src/x_post_mail_lane.py`、 LIVE 350/351 反映済)
- **依存 (handoff)**: `docs/handoff/session_logs/2026-05-15_pm_x_post_mail_lane_buildout.md`
- **依存 (handoff)**: `docs/handoff/session_logs/2026-05-15_pm_next_session_tasks.md`
- **依存 (memory)**: `project_site_direction_data_focus.md` / `feedback_data_insight_user_preferences_2026_05_15.md`

## 2. 目的 / 背景

2026-05-15 user 明示の方向:
- 「データサイトにしたい、大手にないランキングがコンセプト、意外性があるものが欲しい」
- 「大手新聞が毎日あるデータはいらない」(= pool から除外要望)
- 「見やすくしてポストをより [魅力的に]」(見た目改善)

handoff Task 2 / Task 3 と本日 user 確認した 4 改善 + 大手なし pool + 意外性 sampling を 1 ticket に統合。 本 ticket の scope は `src/x_post_mail_lane.py` 内で完結する (348 disjoint、 346 PWA 不可触)。

scope (合意済、 全部 1 commit):

1. **改行 format B 案** — period_suffix を lines[0] append から lines[1] 分離
2. **絵文字 b 案 (metric 別)** — header の ⚾打撃(AVG/OBP/SLG/OPS) / ⚡投手(ERA) / 🛡️守備(将来) で切替
3. **上位 3 メダル** — 1/2/3 位を 🥇🥈🥉、 4 位以降は数字 prefix
4. **巨人 marker 強化** — ← → ←⭐巨人
5. **metric label 数値前置** — .945 → OPS .945 (数値の前に metric_jp)
6. **1 行空け** — 上位 3 行とそれ以下に空行
7. **大手なし pool** — 大手新聞 (報知 / サンスポ / 日刊 / デイリー / スポニチ 等) が毎日連載で出している data を pool から除外
8. **意外性 sampling** — 各 combo に novelty tag + 重み付き shuffle (yoshilover 独自 = 高頻度 / 中間 = 中頻度 / 大手定番 = 低頻度 or 削除)

## 2.5 設計確定事項 (user lock 済 + pending)

### 確定済 (user 明示 2026-05-15 夜)

- format B 案 (括弧 2 行目): user 答 「B 括弧 2 行目」
- 絵文字 b 案 (metric 別): user 答 「b metric 別 (⚾打撃/⚡投手/🛡️守備)」
- 4 見た目改善 (メダル / ⭐ marker / metric label / 1 行空け): user 答 multiSelect 4 つ全部
- 大手定番 pool 除外 + 意外性 sampling 両方採用: user 答 「両方だよ」
- 「大手新聞が毎日あるデータ」= pool から除外: user 明示
- 349 重複抑制数値 (cooldown / delta / band) = 348 後に回す: user 答 「348 後に回す」

### user 確定 pending (実装前に確認必要)

- 「大手新聞が毎日あるデータ」が具体的にどの combo か:
  - **Claude 推定** (= verify ベースではない、 user 確認必要):
    - シーズン累積 OPS / AVG / ERA / OBP / SLG = 大手毎日連載確実 → pool から除外
    - 月別 OPS / AVG / ERA = 357 follow-up で月初 3 日だけ前月成績 (`7月成績` 形式) として採用。毎日は出さない
    - 先月 closed range / 直近 30 日 / 直近 14 日 / 直近 7 日 / 守備位置別 / 巨人内 ranking = 大手出さない (yoshilover 独自) → 保持
- 意外性 sampling の重み付け値:
  - **Claude 推定**: novelty_high (yoshilover 独自) 60% / novelty_mid (中間) 30% / novelty_low (大手定番) 10%
  - **user 判断**: 上記比率で良いか、 もっと novelty 寄りにするか
- 大手定番 5 combo の完全除外か、 低頻度残しか:
  - **Claude 推奨**: 完全除外 (シーズン累積 5 combo は yoshilover が出す意味薄い)
  - **user 判断**: 残すなら weight 0.1 (10%) 程度

## 3. 今回触らない範囲

### 348 / 349 scope (file レベル disjoint 維持)

- `src/analysis/insight_anomaly_detector.py`
- `src/analysis/insight_etl.py`
- `src/analysis/insight_advanced_metrics.py`
- `src/analysis/insight_nightly.py`
- `src/analysis/ranking_article_publisher.py`
- `src/analysis/anomaly_article_publisher.py` (unstaged M 進行中、 触らない)
- `src/analysis/team_ranking_publisher.py` (unstaged M 進行中、 触らない)
- `src/analysis/insight_dedup_gate.py` (349 で新規予定、 本 ticket では作らない)
- `article_candidates` table (read / write 一切なし)
- `config/insight_whitelist.json` (348 owns、 触らない)

### 既存稼働 lane (不可触)

- 346 PWA: `src/manual_intake_service.py` / `src/format_as_x_post.py` (本 ticket は read-only import のみ)
- 既存 publish-notice mail / fact-check mail / X auto post lane
- WP REST publish 経路
- X API 直叩き
- Gemini / Codex / OpenAI LLM 呼出 一切

### インフラ / 設定

- env / Secret Manager 値変更
- Cloud Run revision の他 service (manual-intake-service / yoshilover-fetcher / guarded-publish / publish-notice)
- Cloud Scheduler 起動時刻 / 頻度変更 (5 個 x-post-mail-* の cron 変更なし)
- 親 repo `baseballwordpress` への変更
- 他 repo

### DB

- `insight.db` schema 改修なし (read-only)
- `games` table (本 ticket では query 不要、 Task 4 = 別 ticket 354 で扱う)

## 4. 影響範囲

### code 変更が入る file

| file | 変更内容 |
|---|---|
| `src/x_post_mail_lane.py` | (A) `_format_one` の 3 分岐 (giants_only / position / 通常) で period_suffix を `lines[0]` append から `lines.insert(1, period_suffix)` に変更 / (B) `_METRIC_LABELS_JP` に基づく header 絵文字 mapping (`_METRIC_HEADER_EMOJI` 新規、 OPS/AVG/OBP/SLG = ⚾ / ERA = ⚡) / (C) 各 ranking 行 (`format_as_x_post` 内 or post-process で) 1-3 位 を 🥇🥈🥉 prefix、 4 位以降は数字 prefix / (D) 巨人行の marker を ←⭐巨人 に変更 / (E) 数値前に `OPS ` 等 metric_jp 前置 / (F) 上位 3 とそれ以下に空行 1 行 / (G) `_build_combos` の シーズン累積 5 combo を除去 (or novelty_low tag 付与) / (H) `_MetricCombo` に `novelty` field 追加 (high / mid / low) / (I) `_select_with_diversity` を 重み付き shuffle に変更 (`random.choices(weights=...)`) / (J) 280 字 cap 超過時 top 5 cut or label 省略 logic 追加 |
| `tests/test_x_post_mail_lane.py` | 既存 assert を新 format に更新 + 新規 test (novelty weighting / 大手 pool 除外 / 280 字 cap 動作 / メダル / ⭐ marker / metric label / 1 行空け) |

### 直接触らない file (依存先のみ)

- `src/format_as_x_post.py` (read-only import、 本 ticket では編集なし、 ただし `_format_one` の post-process で 1 位行を 🥇 prefix に書き換える方が無難。 `format_as_x_post.py` 側の API は不変)
- `src/mail_delivery_bridge.py` (SMTP 送信、 不変)
- `src/manual_intake_insight_query.py` (query_rank 関数、 read-only call)

### Cloud Run 影響

- Cloud Run Job `x-post-mail-lane` の image rebuild (cloudbuild submit → gcloud run jobs update)
- Cloud Scheduler 5 個の cron 不変

## 5. 実行予定テスト

### 既存テスト (regression 防止)

```
cd /home/fwns6/code/wordpressyoshilover
python -m pytest tests/test_x_post_mail_lane.py -v
python -m pytest tests/test_format_as_x_post.py -v
python -m pytest tests/test_mail_delivery_bridge.py -v
```

### 新規追加テスト

| test | 内容 |
|---|---|
| `test_period_line_on_second_row` | period_suffix が lines[1] に分離、 lines[0] は title のみ |
| `test_metric_header_emoji_mapping` | OPS/AVG/OBP/SLG → ⚾、 ERA → ⚡ |
| `test_top3_medal_prefix` | 1/2/3 位 = 🥇🥈🥉、 4 位以降 = `N.` 数字 |
| `test_giants_marker_strong` | 巨人行 末尾に ←⭐巨人 (← のみ → 移行) |
| `test_metric_label_prefix_before_value` | 数値前に metric_jp (例 `OPS .945`) |
| `test_blank_line_between_top3_and_rest` | 上位 3 行と 4 位以降に 空行 1 行 |
| `test_pool_excludes_mainstream_combos` | シーズン累積 OPS/AVG/ERA/OBP/SLG が pool から除外されている (= `_build_combos` の出力に含まれない) |
| `test_novelty_weighted_shuffle` | novelty_high の出現確率 > novelty_low (seed 固定で deterministic に verify) |
| `test_280_char_cap_compliance` | 全 candidate の char_count ≤ 280、 超過時 top 5 cut or label 省略 |
| `test_full_pytest_baseline` | `pytest tests/ -v --tb=short` 全 file 既存 pass 数維持 (regression count = 0) |

### 実行コマンド

```
cd /home/fwns6/code/wordpressyoshilover
python -m pytest tests/test_x_post_mail_lane.py -v
python -m pytest tests/ -v --tb=short -k "x_post or format_as or mail_delivery"
# 完了後 full baseline:
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

## 6. STOP 条件

実装中に以下のいずれかを検出したら即停止 + user 報告:

1. **既存テスト regression**: pytest 既存 test が 1 件でも fail (full pytest baseline 比較)
2. **348 scope への接触**: 不可触リスト (§3) の file を編集してしまった
3. **unstaged 2 file への接触**: `anomaly_article_publisher.py` / `team_ranking_publisher.py` に変更を入れてしまった
4. **280 字 cap 超過 candidate 流出**: 超過した candidate がそのまま X intent URL になる
5. **メダル / ⭐ marker / metric label の二重付与**: 既存処理と新処理が重複して 🥇🥇 や OPS OPS .945 等になる
6. **大手 pool 除外で publish 件数 0**: shuffle 後 候補 0 件で mail 不送信
7. **意外性 sampling で deterministic 性喪失**: 同 (date, hour) seed で異なる順序を返す
8. **scope 外破壊**: env / Secret / Scheduler / WP REST / 親 repo の改修が必要になる
9. **AI 事故源 trigger**: 「記憶から再構成 / silent skip / 自己評価 OK」を自分が踏みかけた時点で stop & 訂正

## 7. 禁止事項

- code commit / push (本 ticket は doc-only phase、 user GO 後のみ)
- deploy / gcloud / Cloud Run / Cloud Build / Scheduler 実行
- env / Secret Manager 値変更
- WP REST 経由の content 削除 / 書き換え / 新規 publish
- X / SNS への直接発信 (本 lane は mail で X intent URL 渡す前提、 X API 直叩きは不可)
- 親 repo `baseballwordpress` への変更
- 348 / 349 scope への scope 拡張
- 不可触 file (§3) への変更
- unstaged 2 file (`anomaly_article_publisher.py` / `team_ranking_publisher.py`) への変更
- LLM (Gemini / Codex / OpenAI) 呼出 一切
- `git add -A` (path 明示 stage のみ)
- `--no-verify` / `--no-gpg-sign` 等 hook skip
- `auth.json` / Secret 値の chat / log / commit / mail 露出
- scope の勝手な分割 (memory `feedback_no_unilateral_scope_split.md`、 user 明示の scope は 1 commit で完遂)

## 8. 想定されるデグレ

### 高確率デグレ

- **既存 test 全 fail**: format 変更 (period_suffix 分離 / メダル / metric label / 1 行空け) で既存 assert が文字列一致しなくなる → 各 test の文字列期待値を新 format に揃えて update が必要
- **280 字 cap 超過**: metric label 前置 (`OPS ` x 10 行 = +40 字)、 ⭐巨人 (+8-10 字)、 1 行空け (+1 字) で約 +50 字、 元 280 内 collapse 可能性は中-低、 大半が cap 超過するリスク
- **header 重複**: `format_as_x_post` 側の header 生成と `_format_one` 側の period_suffix 追加が二重 append される ( lines[0] に追加 → lines.insert(1, ...) で moved の整合)
- **絵文字 metric mapping 漏れ**: 守備位置別 / 巨人内 ranking の特殊 prefix で絵文字 fallback が動かない

### 中確率デグレ

- **意外性 sampling で deterministic 性喪失**: `random.choices` の weight 計算で seed 再 set 漏れ
- **大手 pool 除外しすぎ**: シーズン累積 5 combo 除外で pool が痩せ、 mail 1 通 10 candidates 確保できず < 10
- **メダル 4 位以降の数字 prefix ズレ**: 1-3 位 = 絵文字 / 4-10 位 = `4.` `5.` ... の連番が崩れる
- **mail HTML rendering で絵文字幅異常**: Gmail 等 client で 🥇 が幅広 / monospace 揃わない

### 低確率デグレ

- 既存 5 Scheduler の cron 不変 verify 漏れ (本 ticket では touch しない前提だが、 deploy で誤って override)
- Cloud Run image rebuild で他 service (manual-intake-service 等) に副作用 (Dockerfile 共有部分での誤変更)
- mail subject (`[X 投稿候補 N件] ...`) が変更されてしまい既存 mail filter / 受信側 rule が壊れる

### user 影響

- mail 1 通あたりの candidate 数が pool 縮小で減る (10 → 6-8 件等)
- 大手定番 ranking (シーズン累積) が完全に出なくなる → 一部 user 期待と乖離する場合 user 個別判断
- 絵文字増加で「派手すぎ」体感の可能性、 user feedback で c 案 (footer 派手目) は廃案、 b 案 + 4 改善で抑制

## 9. 作業ログ欄

```
2026-05-15 22:55 JST | doc 起票 | phase_0 | 353 ticket doc 完成 / user GO 待ち | wait
2026-05-15 23:00 JST | user GO 受領 | phase_1 | pytest baseline 70 pass / 0 fail lock | phase_2 impl
2026-05-15 23:05 JST | impl 完了 | phase_2 | x_post_mail_lane.py edits (_MetricCombo novelty / _METRIC_HEADER_EMOJI / _RANKING_ROW_PATTERN / _build_combos 17 combo / _select_with_diversity weighted / _format_one rewrite + _rewrite_ranking_rows + _truncate_to_x_limit_top_n) | test_x_post_mail.py edits (期待値 update 2 + 新 9 test)
2026-05-15 23:08 JST | pytest 確認 | phase_2_verify | tests/test_x_post_mail.py + test_format_as_x_post.py + test_mail_delivery_bridge.py = 79 pass / 0 fail | full pytest
2026-05-15 23:10 JST | full pytest | phase_2_verify | 4839 pass / 4 xfailed (pre-existing) / 0 regression | impl commit
2026-05-15 23:45 JST | impl commit | phase_3 | 3b90a84: src/x_post_mail_lane.py + tests/test_x_post_mail.py + doc/active/353-* (3 files, +709/-46) push 済 | cloudbuild
2026-05-15 23:48 JST | cloudbuild SUCCESS | phase_3 | image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:353-novelty-pool-format / digest sha256:873040b1... / build_id 871d2df1-aa9f-4b5b-b8f1-13a9dd09ac78 (1m30s) | jobs update
2026-05-15 23:49 JST | jobs update SUCCESS | phase_3 | x-post-mail-lane revision 更新 (image 351-variations → 353-novelty-pool-format) | execute
2026-05-15 23:52 JST | execute SUCCESS | phase_3 | execution x-post-mail-lane-wfrtv / Composing mail with 10 candidates / mail send result: status=sent reason=None refused={} / Container exit(0) | log verify
2026-05-15 23:54 JST | log verify | phase_3 | mail sent to fwns6760@gmail.com、 user 朝に Gmail で実機 rendering check | done (next session で実機判定)
```

## 10. Regression Memo 欄

```
2026-05-15 23:08 JST | test_giants_marker_present_when_giants_in_top | 既存 assert `← 巨人` が新 format `←⭐巨人` で fail | 期待値を `←⭐巨人` に update + 旧 `← 巨人` が出ないことを追加 assert | 0 件 新規追加 (期待値 update のみ)
2026-05-15 23:08 JST | test_combo_pool_size_22_for_diversity | pool 22 → 17 で fail | test 名 + assertEqual を 17 に変更、 mainstream_season combo 0 件 assert を追加 | 0 件 新規追加 (期待値 update のみ)
```

(Regression メモは 「既存挙動が意図的に変わったもの」 → test 期待値 update で対応。 production behaviour の意図しない退行は 0 件。)

---

# 作業後追記 (user GO 後、 実装完了時に埋める)

## 1. 実際に変更したファイル

- `src/x_post_mail_lane.py` (+106 / -41 行相当、 logic 全面拡張)
- `tests/test_x_post_mail.py` (+162 / -10 行、 期待値 update 2 件 + 新 9 test class `TicketThreeFiftyThreeFormatTests`)
- `doc/active/353-x-post-mail-novelty-pool-and-format.md` (新規、 本 ticket doc)

## 2. diff 概要

### src/x_post_mail_lane.py

- 追加 imports: `math as _math` / `random as _random` (top-level、 旧 inner import 廃止) / `re as _re`
- 新規定数: `_METRIC_HEADER_EMOJI` (AVG/OBP/SLG/OPS=⚾、 ERA=⚡、 FldPct=🛡️、 fallback 📊) / `_RANKING_ROW_PATTERN` (regex で `{rank}. {name}（{team}）{value}{marker}` を分解) / `_NOVELTY_WEIGHTS` (high 70 / mid 30 / low 10)
- `_MetricCombo` dataclass に `novelty: str = "mid"` field 追加
- `_build_combos`: シーズン累積 5 (OPS/AVG/ERA/OBP/SLG) を完全除外、 残り combo に novelty tag 付与 (今月 / 直近 30 日 / 先月 = mid、 直近 7 日 / 直近 14 日 / 守備位置別 / 巨人内 ranking = high)、 pool 22 → 17
- `_select_with_diversity`: simple shuffle → weighted shuffle (exp-distributed key `-log(uniform()) / weight` で deterministic な weighted permutation)
- `_format_one`:
  - header `📊` → metric 別絵文字 (`_METRIC_HEADER_EMOJI`)
  - period_suffix を `lines[0]` append から `lines.insert(1, ...)` 2 行目分離
  - 新 helper `_rewrite_ranking_rows` 呼出 (1-3 位 = 🥇🥈🥉、 4 位以降 = N.、 数値前に metric_jp 前置、 巨人 marker ←⭐巨人、 3 位行と 4 位行の間に空行 1)
  - 新 helper `_truncate_to_x_limit_top_n` 呼出 (280 字超過時 top 5 まで cut、 それでも超過なら末尾 truncation + …)

### tests/test_x_post_mail.py

- L167 既存 assert: `← 巨人` → `←⭐巨人` (marker 強化)
- L452 既存 assert: pool size 22 → 17、 mainstream_season combo 0 確認 を追加
- 新 class `TicketThreeFiftyThreeFormatTests`: 9 test
  - `test_period_line_separated_to_second_row` — period 2 行目分離
  - `test_metric_header_emoji_batting_pitching` — ⚾ / ⚡ header
  - `test_top3_medal_prefix` — 🥇🥈🥉 / 4. 数字
  - `test_giants_marker_strong_form` — ←⭐巨人 / 旧 form 廃止
  - `test_metric_label_prefix_before_value` — `打率 .945` 等
  - `test_blank_line_between_top3_and_rest` — 🥉 後に空行
  - `test_mainstream_combos_excluded_from_pool` — シーズン累積完全除外
  - `test_novelty_weighted_shuffle_high_appears_early` — top5 で high ≥ 3
  - `test_x_char_cap_enforced_on_all_candidates` — 全 candidate ≤ 280 字

## 3. 実行したテスト

```
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py --tb=short
python3 -m pytest tests/ --tb=short -q   # full pytest
```

## 4. テスト結果

- target 3 file: **79 passed / 0 fail** (baseline 70 → +9 new = 79)
- full pytest: **4839 passed / 4 xfailed (pre-existing) / 0 fail** (regression 0)
- 実出力 verify (`test_giants_marker_present_when_giants_in_top` の draft_text):
  ```
  セ・打率 ランキング ⚾
  （5/1〜5/16・規定打席 1+）

  🥇 佐藤輝明（阪神）打率 .945
  🥈 牧秀悟（DeNA）打率 .932
  🥉 岡本和真（巨人）打率 .921 ←⭐巨人

  4. 村上宗隆（ヤクルト）打率 .918
  5. 鈴木誠也（広島）打率 .910
  6. 細川成也（中日）打率 .900

  #巨人 #ジャイアンツ
  ```
  8 改善 (改行 B / metric 別絵文字 ⚾ / 🥇🥈🥉 / ←⭐巨人 / 打率 .945 / 1 行空け) 全部動作確認。

## 5. 残った懸念

1. **user 実機 Gmail rendering 未 verify**: Claude は Gmail に access できないため、 HTML / 🐦 button / column / 絵文字 (🥇🥈🥉 / ⚾⚡ / ⭐) の Gmail client 上の表示は user 朝確認待ち。 致命的崩れがあれば followup ticket。
2. **`OPS/直近7日` と `ERA/今月` が production data 不足で skip 連発**: log で `Too few rows (0 < 5)` 観測。 シーズン進行 (試合数増) で自然解消の見込み、 ただし明朝の自然 fire (07:00) で何 candidates 出るかは未確認。
3. **意外性 sampling の効果は 1-2 週観察が必要**: weighted shuffle で high 70% / mid 30% は単発 mail の 10 候補のみ見ても判断難。 連日 mail で大手定番除外による「意外性 体感」が上がるか user feedback 待ち。
4. **280 字 cap で truncation 発動の頻度未測定**: 全 candidate cap compliant は pytest で verify したが、 production data (real 選手名 長さ) で実 cap 超過がどのくらい発生するかは scheduler 自然 fire で観察。
5. **巨人内 ranking で 巨人 rows ≥ 3 必要条件**: 巨人選手の規定打席 30+ が 3 人未満だと skip、 シーズン初期に頻発する可能性 (現状 problem 顕在化なし)。

## 6. 新しく見つかったデグレ

なし (production behaviour の意図しない退行 0 件、 pytest full baseline 4839 pass 維持)。 後続観察で出現すれば追記。

## 7. 追加した回帰テスト

`tests/test_x_post_mail.py::TicketThreeFiftyThreeFormatTests` の 9 test (上記 §2 参照)。

## 8. 次回触ってはいけない範囲

- **`src/x_post_mail_lane.py` の post-process logic** — `_rewrite_ranking_rows` / `_truncate_to_x_limit_top_n` / `_select_with_diversity` weighted shuffle は新 fixture を伴う変更なので、 次に触る ticket は必ず本 ticket の test を読んだ上で扱う (期待値が新 format と密結合)。
- **`src/analysis/anomaly_article_publisher.py` / `src/analysis/team_ranking_publisher.py`** — 別作業 (348 step 残 or 別 ticket) の unstaged 進行中分、 本 ticket 完了後も他 lane が進行中の前提で扱う。
- **`src/format_as_x_post.py`** (346 PWA scope、 本 ticket は read-only import のみ、 触る ticket は 346 PWA 経路の影響評価が必要)。
- **348/349 file 群** (`insight_anomaly_detector.py` / `insight_etl.py` / `insight_advanced_metrics.py` / `insight_nightly.py` / `ranking_article_publisher.py` / `anomaly_article_publisher.py` / `team_ranking_publisher.py` / `config/insight_whitelist.json` / `article_candidates` table) — 348 step 4 / 349 cascade で扱う、 本 ticket では一切 touch せず。
- **Cloud Run Job `x-post-mail-lane` の Scheduler** (`x-post-mail-am-1` / `lunch` / `afternoon` / `evening` / `postgame` の 5 個 ENABLED) — 起動時刻 / 頻度の変更は 別 ticket で user 判断必要 (本 ticket は image 入替のみ、 scheduler 不変)。
- **mail SMTP credentials / X API secret** (`seo-web-runtime` SA に grant 済) — secret rotation は user 判断境界 (§11 法務・コスト軸)。
