# 361-INSIGHT-permanent-table-body-and-title-contract

## status

- **status**: LIVE_DEPLOYED_OBSERVE
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **scope**: DATA-INSIGHT 記事本文の表形式恒久ガード + 巨人サイト前提の title 契約

## user intent

2026-05-16 user 指示:

- `これは本文だよね` に対し、本文だけの一時対応ではなく恒久対応にする
- 巨人サイトなので title は巨人選手を入口にする
- title には、巨人の選手名 / 指標 / 何位 / 期間を入れる

## implementation contract

変更する:

- `src/analysis/anomaly_article_publisher.py`
- `src/analysis/insight_quality_gate.py`
- `tests/test_insight_step3_part2_records.py`
- `tests/test_insight_quality_gate.py`
- board docs

変更しない:

- 既存公開 post の本文
- WordPress publish / update 実行
- Scheduler / env / Secret
- X / SNS live post
- DB schema

## accepted behavior

- UZR / 守備率の title は、`{巨人選手名}の{守備位置}、{指標} {値}で巨人N/6位（期間）` 型にする
- title 先頭で `セ・リーグ球団別` を主語にしない。本文の表でセ・リーグ比較を見せる
- data insight の publish-time quality gate で、本文に markdown/html table が無い記事を止める
- `## データ` / `## このデータについて` / ranking / 比較 section は table 必須
- `## データ` section が bullet list に戻ったら publish/draft 投入前に止める
- `ひとこと` の短い文章は許容する

## verification

実行済み:

- `python3 -m py_compile src/analysis/anomaly_article_publisher.py src/analysis/insight_quality_gate.py tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py`
  - PASS
- `python3 -m pytest tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py -q`
  - PASS (`44 passed, 3 warnings`)
- `python3 -m compileall -q src/analysis/anomaly_article_publisher.py src/analysis/insight_quality_gate.py tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py`
  - PASS
- AST parse
  - PASS (`ast_ok`)
- `python3 -m pytest tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py tests/test_insight_whitelist_gate.py tests/test_ranking_article_publisher.py -q`
  - PASS (`102 passed, 3 warnings`)
- scoped `git diff --check`
  - PASS
- production DB copy local preview
  - PASS: `泉口友汰の遊撃守備、簡易UZR -0.088で巨人6/6位（直近30日）`

## deploy notes

- commit: `8447109`
- Cloud Build: `a2ced6da-5d6a-46e7-bcb1-e1ae93092fdf` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:361-table-title-8447109`
- digest: `sha256:bf0000bff08570ed0a93f57115e5a66252ce85682089c3dbdd4c331ea56fe7eb`
- Cloud Run Job: `insight-nightly` generation `49`
- Scheduler: `data-insight-*` 7 triggers ENABLED のまま確認
- Scheduler / env / Secret は変更しない
- 手動 execute は追加 publish/mail を発生させる可能性があるため未実行。次回自然 fire で live output を確認する
