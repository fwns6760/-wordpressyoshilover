# 349-INSIGHT-dedup-cooldown-cascade

## 1. ticket header

- **status**: READY (user 数値 確定 + GO 待ち)
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

## 2.5 設計確定事項 (user lock 済 + pending)

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

### 数値 (user 確定 pending)

| 設定 | 候補 | 私の judgment (確定ではない) |
|---|---|---|
| ①クールダウン日数 N | 7 / 14 / 30 日 | 7 日 |
| ②変化量閾値 | 値の 3% / 5% / 10% 変動 | 5% |
| ③順位 band 区切り | top 1% / 5% / 10% | top 5% / 10% の境界 |

実装着手前に数値 3 つを user 確定必要。

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
```

## 10. Regression Memo 欄

(実装中追記、 検知した regression / 回避策)

```
YYYY-MM-DD HH:MM JST | <test> | <regression> | <fix> | <test added>
```

---

# 作業後追記 (user GO 後、 完了時に埋める)

## 1. 実際に変更したファイル
(未記入)

## 2. diff 概要
(未記入)

## 3. 実行したテスト
(未記入)

## 4. テスト結果
(未記入)

## 5. 残った懸念
(未記入)

## 6. 新しく見つかったデグレ
(未記入)

## 7. 追加した回帰テスト
(未記入)

## 8. 次回触ってはいけない範囲
(未記入)
