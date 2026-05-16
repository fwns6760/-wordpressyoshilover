# 360-INSIGHT-defense-table-comparison-format

## status

- **status**: REVIEW_NEEDED
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **scope**: UZR / 守備系データ記事を表形式比較に寄せる

## user intent

2026-05-16 user 指示:

- `68499` などの UZR 記事は出したい
- ただし個人の平均差だけではなく、球団ごとの表形式順位が欲しい
- 方針としてデータ記事は表形式にする

## implementation contract

変更する:

- `src/analysis/anomaly_article_publisher.py`
- `tests/test_insight_step3_part2_records.py`
- board docs

変更しない:

- 既存公開 post の本文
- WordPress publish / update 実行
- Cloud Run / Scheduler / env / Secret
- X / SNS live post
- DB schema

## accepted behavior

- UZR 記事は、conn がある本番生成時にセ・リーグ球団別の表形式 ranking を本文主役にする
- UZR title は `セ・リーグ球団別 {守備位置}の簡易UZR、巨人 N/6位` 型にする
- 巨人行を赤太字 + `★` で強調する
- 関連した巨人選手名は本文表に残す
- `UZR_proxy` の内部名は title に出さない
- シンプルなデータ記事の `## データ` も箇条書きではなく `| 項目 | 数値 |` table にする

## verification

実行済み:

- `python3 -m py_compile src/analysis/anomaly_article_publisher.py tests/test_insight_step3_part2_records.py`
  - PASS
- `python3 -m pytest tests/test_insight_step3_part2_records.py -q`
  - PASS (`37 passed, 3 warnings`)
- `python3 -m compileall -q src/analysis/anomaly_article_publisher.py tests/test_insight_step3_part2_records.py`
  - PASS
- AST parse
  - PASS (`ast_ok`)
- `python3 -m pytest tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py tests/test_insight_whitelist_gate.py tests/test_ranking_article_publisher.py -q`
  - PASS (`100 passed, 3 warnings`)
- scoped `git diff --check`
  - PASS
- production DB copy local preview
  - PASS: `泉口友汰 / 遊撃守備` case renders `セ・リーグ球団別 遊撃守備の簡易UZR、巨人 6/6位 -0.088（直近30日）` with 6-team table

## deploy notes

- live 反映には `insight-nightly` image rebuild + Cloud Run Job image update が必要
- Scheduler / env / Secret は変更しない
- 手動 execute は追加 publish/mail を発生させる可能性があるため原則実行しない。次回自然 fire で確認する
