# 349-INSIGHT-dedup-cooldown-cascade

## 1. ticket header

- **status**: LIVE_DEPLOYED_OBSERVE (2026-05-16 Codex follow-up 実装 + push + `insight-nightly:be96f18` deploy 済、自然 fire 観察待ち)
- **priority**: medium-high (348 ticket 後の next 優先)
- **owner**: Claude (実装) / user (数値 + GO 判断)
- **依存**: 348 ticket (#26) 完了後に着手推奨 (× フィルター後の重複問題実態 verify ベースで挙動 tuning できる)
- **依存 (spec)**: memory `project_data_insight_duplicate_prevention_plan_2026_05_15.md`
- **依存 (audit)**: `docs/handoff/session_logs/2026-05-15_data_insight_metric_implementation_audit.md` の重複検知 audit section

## 2. 目的 / 背景

348 ticket (× フィルター + 軽修正 + 中作業) を deploy した後にも、 ◯ metric (打率 / OPS / 本塁打数 等) の **連日重複** が残る構造的 risk あり:

- 例: 「坂本 OPS リーグ 3 位 (今シーズン)」が値ほぼ変わらず毎日 publish される
- 原因: 既存 dedup は title 完全一致のみ、 日付やちょっとした表現違いで素通り

本 ticket は重複抑制の 3 段階 filter cascade を実装する。 348 と分離する理由は **regression リスク isolate** + **段階 deploy で安全** + **348 観察後の挙動 tuning** が可能になるため。

## 2.5 設計確定事項 (user lock 済)

### Framework lock (2026-05-15 user 「OK よし。記録」)

3 段階 filter cascade:

```
新候補
  ↓
①クールダウン: 「同 player + 同 metric + 同 scope」を最近 N 日以内に publish 済? → YES → skip
  ↓ NO
②変化量 (delta): 前回 publish 値からの変化量が小さい? → YES → skip
  ↓ NO
③順位 band: 前回と同じ順位 band? → YES → skip
  ↓ NO
publish OK
```

### 数値 (2026-05-16 user 会話を受けて実装値 lock)

| 設定 | 実装値 | 理由 |
|---|---|---|
| ①クールダウン日数 N | 7 日 | user「一週間に一度、または大きく動いたら」 |
| ②変化量閾値 | 5% | 小変動の連日再掲を止め、大きな変化は通す |
| ③順位 band 区切り | 1 / 5 / 10 / 30 位 | 順位帯が変わった時だけ短期再掲を許可 |
| scope family | metric_all_periods | 同じ選手 + 同じ指標は `last_7d` / `season` など期間違いでも原則 7 日 cooldown |

## 3. 今回触らない範囲

- **348 ticket スコープ全体** (× フィルター / 軽修正 / 中作業) — 348 の機能を変更しない
- **DB schema 改修** (既存 `article_candidates` を活用、 新 history table も既存 schema に合わせる)
- **env / Secret / Scheduler** 変更
- **WP REST / X / SNS / mail 経路** の wholesale 改修
- **既存稼働 detector / publisher** の core logic 変更 (gate 追加のみ)
- 親 repo `baseballwordpress` への変更
- ステップ 4 (球場別 / WAR / 得点圏 schema 改修) は別 phase

## 4. 影響範囲

### code 変更が入る file (推定)

| file | 変更内容 |
|---|---|
| **新規** `src/analysis/insight_dedup_gate.py` (仮称) | 3 段 cascade logic (cooldown / delta / band check) を集約 |
| `src/analysis/insight_anomaly_detector.py` | candidate insert 前に dedup_gate を call、 通った candidate のみ insert |
| `src/analysis/anomaly_article_publisher.py` | publisher 内でも 最終 check (二重防御) |
| `src/analysis/ranking_article_publisher.py` | 同上 |
| `src/analysis/team_ranking_publisher.py` | 同上 |
| **DB**: `article_candidates` table | 既存 `status='PUBLISHED'` row を **publish 履歴** として参照、 schema 改修なし (= migration 不要見込み) |
| **config**: `config/insight_whitelist.json` | dedup 設定 (cooldown_days / delta_threshold / band_boundaries) を追加 (形式 = JSON、 348 で確定済) |
| `tests/test_insight_dedup_*.py` | 新規 |

### 新規追加テスト (見込み)

| file | 内容 |
|---|---|
| `tests/test_insight_dedup_cooldown.py` | cooldown gate logic (N 日以内 skip / N 日経過 publish) |
| `tests/test_insight_dedup_delta.py` | delta gate logic (変化量小 skip / 変化量大 publish) |
| `tests/test_insight_dedup_band.py` | band gate logic (同 band skip / band 変動 publish) |
| `tests/test_insight_dedup_cascade.py` | 3 段 cascade 順序 + 統合動作 |

## 5. 実行予定テスト

- **既存テスト全 pass** (regression 防止): `pytest tests/test_insight_*.py`
- 新規 cascade 各段の unit test
- cascade 統合 test (3 段順序、 短絡評価)
- 348 ticket 機能の不変 verify (× フィルター / 中作業 / 軽修正 が動き続ける)
- 既存 publish 済 article への副作用無し verify

### 実行コマンド

```
cd /home/fwns6/code/wordpressyoshilover
python -m pytest tests/test_insight_*.py -v
python -m pytest tests/test_insight_dedup_cooldown.py -v
python -m pytest tests/test_insight_dedup_delta.py -v
python -m pytest tests/test_insight_dedup_band.py -v
python -m pytest tests/test_insight_dedup_cascade.py -v
```

## 6. STOP 条件

実装中に以下のいずれかを検出したら即停止 + user 報告:

1. 既存テスト regression
2. 348 ticket の動作変更 (= 重複対策が 348 の機能を壊す)
3. env / scheduler / secret 改修が必要になる
4. publish 経路の wholesale 改修が必要
5. DB schema migration が要請 (本 ticket は migration なし前提)
6. 数値 3 つ (cooldown / delta / band) が未確定なら着手しない
7. cooldown gate で publish 件数 0 件になる (= filter 過剰)
8. AI 事故源 trigger (記憶再構成 / silent skip / 自己評価 OK)

## 7. 禁止事項

- code commit / push (本 ticket は plan phase、 user 数値 + GO 後のみ)
- deploy / gcloud / Cloud Run / Cloud Build 実行
- env / Secret Manager / Scheduler 変更
- 348 ticket の機能変更 (cascade 連携の最小変更以外)
- WP REST 経由 content 削除 / 書き換え / 新規 publish
- X / SNS 発信
- 親 repo `baseballwordpress` への変更
- DB schema 改修 (既存 `article_candidates` を活用する前提)
- `git add -A` (path 明示 stage のみ)
- `--no-verify` 等 hook skip

## 8. 想定されるデグレ

### 高確率
- **cooldown gate で publish 件数 急減** (cooldown 日数次第、 5/15 DB verify で base 15-30 件 / 日 → 7 日 cooldown で 1/7 程度に落ちる可能性)
- **delta gate で metric 種類別の感度ズレ** (打率 5% vs 防御率 5% で意味違う)
- **band gate で順位境界の挙動異常** (top 5% / 10% の境界をまたぐ candidate が頻繁に出る場合)
- **mail layer 既存 dedup との干渉**: `publish_notice_email_sender.py` に 30 分 dedup / 10 分 replay / 10 件 burst 抑制 / 100 件 daily cap 既存。 publish layer cooldown と mail layer dedup の二重防御になるが、 publish 段階で gate しても mail layer の独自 dedup logic も同時に動くため、 mail 配信パターンが想定と異なる可能性

### 中確率
- nightly job 処理時間増加 (publish 履歴 query が増える)
- DB read 競合 (production write と同時実行で lock)
- 既存 published article の status を意図せず変える

### 低確率
- cascade 順序の race condition
- `article_candidates.status='PUBLISHED'` の判定基準ズレ

### user 影響
- mail 配信件数の急減 (新候補が少なくなる)
- 記事の鮮度 / 多様性 のトレードオフ (cooldown 日数次第)

## 9. 作業ログ欄

(実装中追記、 user 数値 + GO 後に作業開始)

```
YYYY-MM-DD HH:MM JST | <event> | <gate (cooldown/delta/band)> | <task> | <next>
2026-05-16 JST | Codex follow-up | cooldown=7d / delta=5% / band=1,5,10,30 | publisher 段で同 subject + metric の期間横断 dedup gate を実装 | commit 後、GH #26/#27 に追記。deploy は別判断
2026-05-16 JST | deploy | same image only | clean `git archive HEAD` export から `insight-nightly:be96f18` build/deploy。Scheduler/env/Secret は未変更、手動 execute 未実行 | 次回自然 fire で記事数・mail数・skip理由を観察
```

## 10. Regression Memo 欄

(実装中追記、 検知した regression / 回避策)

```
YYYY-MM-DD HH:MM JST | <test> | <regression> | <fix> | <test added>
```

---

# 作業後追記 (user GO 後、 完了時に埋める)

## 1. 実際に変更したファイル

- `config/insight_whitelist.json`
- `src/analysis/insight_dedup_gate.py`
- `src/analysis/anomaly_article_publisher.py`
- `src/analysis/ranking_article_publisher.py`
- `src/analysis/team_ranking_publisher.py`
- `src/analysis/insight_anomaly_detector.py`
- `tests/test_insight_dedup_gate.py`
- `tests/test_insight_anomaly_detector.py`
- `tests/test_ranking_article_publisher.py`
- 本 ticket doc / board

## 2. diff 概要

- 同じ subject + metric を `metric_all_periods` に束ね、7 日以内は原則 `skip_dedup_cooldown`。
- 例外は「値が 5% 以上動いた」または「順位 band が変わった」場合のみ。
- publisher 側で WP 投稿後に既存 `article_candidates` へ dedup history row を追加。schema migration なし。
- `BABIP` / `FIP` は detector だけでなく direct renderer 経由でも記事化されないように二重防御。
- `published` status の件数カウント漏れを修正し、auto publish cap が publish でも効くようにした。

## 3. 実行したテスト

- `python3 -m pytest tests/test_insight_dedup_gate.py tests/test_insight_anomaly_detector.py tests/test_ranking_article_publisher.py tests/test_insight_whitelist_gate.py -q`
- `python3 -m pytest tests/test_insight_step3_part2_records.py tests/test_insight_article_generator.py tests/test_insight_step2_metrics.py tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_ranking_article_publisher.py tests/test_insight_dedup_gate.py -q`
- `python3 -m py_compile ...` (変更対象 source/test)
- `python3 -m compileall ...` (変更対象 source/test)
- `python3 -c "import ast, ..."` (変更対象 source/test AST parse)
- `git diff --check -- ...`
- `python3 -m unittest discover -s tests`

## 4. テスト結果

- 対象 pytest: 73 passed, 3 warnings。
- 関連広め pytest: 167 passed, 3 warnings。
- py_compile / compileall / AST parse / diff check: pass。
- full unittest: 4191 tests 実行、11 failures / 3 errors。既存の `manual_intake_service` socket PermissionError、`manual_intake_service_x_post` 403 expectation、`duplicate_prevention_golden` logger call-count で失敗。今回変更対象外。

## 5. 残った懸念

- Cloud Run Job `insight-nightly` image は `be96f18` へ deploy 済み。Scheduler / Secret / env は未変更。
- dedup history は deploy 後の新規投稿から蓄積される。既存 WP 投稿を完全に backfill する処理は未実装。
- mail 専用 cap やグローバル 1 run 合計 cap は別判断。今回の修正は publish 候補生成側の重複抑制。

## 6. 新しく見つかったデグレ

- 現時点で対象テスト上の regression は未検出。
- full unittest の赤は上記既存失敗として残存。

## 7. 追加した回帰テスト

- 期間違い (`last_7d` / `season`) でも同一選手 + 同一指標を 7 日以内 block。
- 8 日経過なら allow。
- 5% 以上の値変化なら allow。
- rank band 変化なら allow。
- `BABIP` / `FIP` detector と direct renderer の block。
- 大城 OPS の期間違い再 publish が `skip_dedup_cooldown` になること。

## 8. 次回触ってはいけない範囲

- env / Secret / Scheduler / Cloud Run deploy は user 判断まで触らない。
- mail 制限の設計変更と自動公開上限の追加調整は user と別途会話してから扱う。
- WP 既存記事の削除 / 書き換え / X 投稿はしない。

## 9. deploy 後の様子見リスク / やっていないこと (2026-05-16)

### 様子見リスク

- **記事が減りすぎる risk**: 同じ subject + metric を 7 日 cooldown で束ねたため、短期的に data-insight 記事が 0〜少数に落ちる可能性がある。次回自然 fire で `published` / `skip_dedup_cooldown` / `skip_max_per_run` の比率を見る。
- **記事がまだ多い risk**: cap は publisher path ごとの上限で、nightly 全体の 1 日総量 cap ではない。anomaly / ranking / team / counting / split が別々に動くため、全体本数が想定より多くなる可能性がある。
- **mail がまだ多い risk**: 今回は publish 候補生成側の重複抑制。mail 専用の「同選手 1 日 1 通」「1 日 N 通まで」「まとめ mail」は未実装。
- **初回だけ既存投稿と重複する risk**: dedup ledger は deploy 後の新規 publish/draft から蓄積。過去 WP 投稿の backfill はしていないため、初回 fire は既存記事との完全重複を止めきれない可能性がある。
- **5% delta の指標別感度 risk**: OPS / 防御率 / 本塁打数などで「5%」の意味が違う。実 mail/article を見て、指標別閾値に分ける必要が出る可能性がある。
- **rank band 境界 risk**: 1 / 5 / 10 / 30 位の境界をまたぐだけで再掲される。境界付近で行き来すると短期再掲が増える可能性がある。
- **期間 title guard は未強制**: title 例は config/spec/test に入れたが、「期間が title に無い記事を必ず落とす/補完する」runtime guard は未実装。
- **manual execute 未実行**: 追加記事・mail を発生させないため deploy 後の手動 `gcloud run jobs execute insight-nightly` は実行していない。次回 Scheduler 自然 fire で確認する。
- **full unittest 赤は残存**: `manual_intake_service` socket PermissionError、`manual_intake_service_x_post` 403 expectation、`duplicate_prevention_golden` logger call-count は今回対象外で未修正。

### やっていないこと

- 1 日全体の data-insight publish 総量 cap。
- mail 専用 cap / mail digest / 同選手同指標 mail cooldown。
- 既存 WP 投稿から dedup history を backfill する処理。
- title 期間必須の runtime validation / auto補完。
- 指標別 delta 閾値。
- Scheduler 本数削減や時刻変更。
- env / Secret 変更。
- WP 既存記事の削除・修正。
