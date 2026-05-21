# 360-INSIGHT-defense-table-comparison-format

## status

- **status**: CLOSED SUPERSEDED_BY_373_361 (2026-05-21 audit、 `src/analysis/anomaly_article_publisher.py` L1134 / L1149 に `セ・リーグ球団別ランキング` table 実装は LIVE (image `415-vs-lr-mvp`)、 だが UZR title は 373 で player-level 「{選手}、{位置}守備の簡易UZR ... セ・リーグ選手別 N/5位」 に進化、 360 strict title contract 「セ・リーグ球団別 {守備位置}の簡易UZR、巨人 N/6位」 は超過。 table-body 部分 (table-first / `★` 強調 / `## データ` table 必須) は 361 permanent contract に吸収済。 post 69815 で player-level format 稼働確認、 post 69816 で team-level 球団別 format も併存稼働確認)
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **scope**: UZR / 守備系データ記事を表形式比較に寄せる

## user intent

2026-05-16 user 指示:

- `68499` などの UZR 記事は出したい
- ただし個人の平均差だけではなく、球団ごとの表形式順位が欲しい
- 方針としてデータ記事は表形式にする

注: 「全てが表形式」は、数値・比較・根拠の表示を table に寄せる意味で扱う。
読者向けの短い `ひとこと` は残すが、判断材料になるデータ部は表で見せる。

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

- commit: `269fd37`
- Cloud Build: `7cf61309-f315-4fb9-9a2f-5ec130c26c23` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:360-defense-table-269fd37`
- digest: `sha256:0e2abc58b2704a03eb8f49481dae1f3a858986b068cd087854b38a1594af72c7`
- Cloud Run Job: `insight-nightly` generation `48`
- Scheduler: `data-insight-*` 7 triggers ENABLED のまま確認
- Scheduler / env / Secret は変更しない
- 手動 execute は追加 publish/mail を発生させる可能性があるため未実行。次回自然 fire で live output を確認する
