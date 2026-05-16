# 356-INSIGHT-data-quality-publish-gate

## 1. ticket header

- **status**: REVIEW_NEEDED
- **priority**: high
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **GH Issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/31
- **parent**: `348-INSIGHT-whitelist-implementation-step1-to-3`, `349-INSIGHT-dedup-cooldown-cascade`

## 2. 目的

data-insight の自動公開直前に、データ記事として最低限の信頼性を満たさない候補を止める。

348 / 349 / title 期間 guard で以下は改善済み:

- × 指標流出防止
- 同じ選手 + 同じ指標の短期重複抑制
- title 期間必須化

残る system risk は以下:

- sample 不足が publisher 全体で統一チェックされていない
- ranking coverage 不足時に順位記事が出る余地がある
- 古い snapshot から記事が出る余地がある
- 本文内のデータ根拠が publish 直前で検証されていない

## 3. 実装方針

- 新規 module `src/analysis/insight_quality_gate.py` に publish 直前 gate を集約する
- publisher 側で WP `create_post` の前に最終チェックする
- fail は silent skip にせず、明示 status / reason を返す
- `config/insight_whitelist.json` に data quality 閾値を追加する
- env / Secret / Scheduler / X / SNS / WP 既存記事は触らない
- schema migration はしない

## 4. skip reason

| reason | 意味 |
|---|---|
| `skip_data_quality_sample` | focus player の sample が閾値未満 |
| `skip_data_quality_coverage` | ranking の比較母数 / セ・リーグ coverage が不足 |
| `skip_data_quality_stale_snapshot` | snapshot が古すぎる |
| `skip_data_quality_missing_evidence` | 本文に期間 / データ元 / 計算式 / 比較 / サンプル等の根拠が不足 |

## 5. 受け入れ条件

- sample 不足の player ranking は WP に作成されず、`skip_data_quality_sample` を返す
- セ・リーグ coverage 不足の ranking は WP に作成されず、`skip_data_quality_coverage` を返す
- stale snapshot は WP に作成されず、`skip_data_quality_stale_snapshot` を返す
- 本文根拠不足は WP に作成されず、`skip_data_quality_missing_evidence` を返す
- team ranking はセ・リーグ 6 球団が揃わない場合に止まる
- 348 whitelist / 349 dedup / title period guard の既存テストが green
- 実行 test と未実行事項を本 ticket に記録する

## 6. 非対象

- mail 制限 / mail digest / mail cooldown
- 自動公開 scheduler の時刻変更
- Cloud Run env / Secret Manager / Scheduler 変更
- WP 既存記事の削除・修正
- X / SNS 自動投稿
- DB schema migration

## 7. 作業ログ

```
2026-05-16 JST | GitHub Issue #31 作成 | user 指示「GitHub issue に入れてから」対応
2026-05-16 JST | repo ticket 356 作成 | doc/active + README + assignments 同期
2026-05-16 JST | 実装 | publish 直前 data quality gate を ranking / anomaly / team publisher に追加
2026-05-16 JST | 検証 | targeted pytest 231 passed、full unittest は既存赤 11 failures / 3 errors
```

## 8. 作業後追記

### 変更ファイル

- `config/insight_whitelist.json`
- `src/analysis/insight_quality_gate.py`
- `src/analysis/ranking_article_publisher.py`
- `src/analysis/anomaly_article_publisher.py`
- `src/analysis/team_ranking_publisher.py`
- `tests/test_insight_quality_gate.py`
- `tests/test_ranking_article_publisher.py`
- `tests/test_insight_anomaly_detector.py`
- `doc/README.md`
- `doc/active/assignments.md`
- `doc/active/356-INSIGHT-data-quality-publish-gate.md`

### 実装内容

- `insight_quality_gate.py` を追加し、WP `create_post` 前に以下を検査:
  - focus player sample 閾値
  - セ・リーグ 6 球団 coverage
  - latest / age based snapshot freshness
  - 本文内の `データ元` / `集計期間` / `計算式 or 集計式` / `比較` / `サンプル`
- skip reason を明示化:
  - `skip_data_quality_sample`
  - `skip_data_quality_coverage`
  - `skip_data_quality_stale_snapshot`
  - `skip_data_quality_missing_evidence`
- team streak / anomaly simple body に計算根拠 token を追加。
- counting articles に team coverage metadata を追加。

### 実行テスト

- `python3 -m py_compile src/analysis/insight_quality_gate.py src/analysis/ranking_article_publisher.py src/analysis/anomaly_article_publisher.py src/analysis/team_ranking_publisher.py tests/test_insight_quality_gate.py tests/test_ranking_article_publisher.py tests/test_insight_anomaly_detector.py`
  - PASS
- `python3 -m compileall -q src/analysis tests/test_insight_quality_gate.py tests/test_ranking_article_publisher.py tests/test_insight_anomaly_detector.py tests/test_insight_whitelist_gate.py tests/test_insight_title_guard.py tests/test_insight_dedup_gate.py`
  - PASS
- AST parse:
  - `ast_ok`
- `git diff --check -- <changed paths>`
  - PASS
- targeted pytest:
  - `python3 -m pytest tests/test_insight_quality_gate.py tests/test_ranking_article_publisher.py tests/test_insight_anomaly_detector.py tests/test_insight_whitelist_gate.py tests/test_insight_title_guard.py tests/test_insight_dedup_gate.py -q`
  - `87 passed, 3 warnings`
- wider data-insight / x-mail regression:
  - `python3 -m pytest tests/test_insight_quality_gate.py tests/test_ranking_article_publisher.py tests/test_insight_anomaly_detector.py tests/test_insight_whitelist_gate.py tests/test_insight_title_guard.py tests/test_insight_dedup_gate.py tests/test_insight_step3_part2_records.py tests/test_insight_article_generator.py tests/test_insight_step2_metrics.py tests/test_x_post_mail.py tests/test_format_as_x_post.py -q`
  - `231 passed, 3 warnings`
- repo baseline:
  - `python3 -m unittest discover -s tests`
  - `Ran 4191 tests`
  - `FAILED (failures=11, errors=3)`

### 未実行 / 対象外

- Cloud Run / Cloud Build / Scheduler deploy: 未実行。記事数を減らす可能性がある live gate のため、repo commit 後に user / authenticated executor 判断。
- env / Secret / Scheduler 変更: 対象外、未実行。
- WP 既存記事の削除 / 修正: 対象外、未実行。
- X / SNS 自動投稿: 対象外、未実行。

### full unittest 既存赤

- `test_manual_intake_service.LiveServerSmokeTest`: local socket `PermissionError: [Errno 1] Operation not permitted`
- `tests/test_manual_intake_service_x_post.py`: token/auth gate で expected 400/503/200/502 が 403
- `tests/test_duplicate_prevention_golden.py`: logger.info call-count expectation mismatch
