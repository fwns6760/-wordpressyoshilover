# 362-INSIGHT queue cleanup and metric run cap

- **status**: CLOSED LIVE_DEPLOYED_VERIFIED (2026-05-21 audit、 prod insight.db `article_candidates` status 分布で 4 status 全部稼働確認: DROPPED_DISABLED_SIGNAL=25283 / EXPIRED=5752 / DRAFTED=273 / PUBLISHED=76 / DROPPED_METRIC_RUN_CAP=23 / NEW=19。 metric cap = 1/run effective、 disabled signal sweep + stale expire + cleanup 全 path 動作)
- **owner**: Codex
- **priority**: high
- **created_at**: 2026-05-16

## Background

2026-05-16 15:00 JST の `insight-nightly` で UZR 記事が 3 本連続で出た。
ログ確認では、anomaly publish block が先に走り、`status='NEW'` / priority 1 の
UZR candidates が `max_per_run=3` を埋めたことが原因。

production GCS DB copy では `article_candidates` が以下の状態だった。

- `NEW`: 15,938
- `DRAFTED`: 255
- `PUBLISHED`: 9
- current auto anomaly fetchable NEW: 3 件、すべて `anomaly_defense_uzr_outlier`

user 方針:

- 同じ指標が同じ時間帯に連続で出るのは困る。
- 規則を厳しくする。
- キューもたまりっぱなしにしない。

## Scope

- `src/analysis/anomaly_article_publisher.py`
- focused tests
- ticket board docs

## Acceptance

- 1 回の anomaly auto publish で、同じ metric は最大 1 本まで。
- metric cap で落とした candidate は削除せず、`article_candidates.status` を監査可能な skip status に変更する。
- 古い `status='NEW'` candidate は TTL で `EXPIRED` に変更する。
- 現在の anomaly auto publish 対象外 signal は `DROPPED_DISABLED_SIGNAL` に変更し、`NEW` に残し続けない。
- `dry_run=True` は queue cleanup / status mutation をしない。
- 既存公開 WP post / Scheduler / env / Secret / X / SNS は変更しない。

## Verification Plan

- unit tests for queue cleanup
- unit tests for metric run cap
- targeted pytest around anomaly publisher / insight quality gate
- deploy only after tests pass

## Implementation Notes

- `cleanup_anomaly_queue()` added to move old `NEW` rows to `EXPIRED` and auto-publish-disabled signals to `DROPPED_DISABLED_SIGNAL`.
- `publish_anomaly_drafts()` now defaults to one article per metric per run.
- Extra same-metric candidates are moved to `DROPPED_METRIC_RUN_CAP` after the first same-metric publish/dry-run slot is used.
- `dry_run=True` does not mutate queue status.
- Defense team comparison articles now include a `計算式` row so the publish quality gate does not reject them as missing evidence.

## Verification

- `python3 -m py_compile src/analysis/anomaly_article_publisher.py tests/test_insight_anomaly_detector.py tests/test_insight_step3_part2_records.py`
- `python3 -m pytest tests/test_insight_anomaly_detector.py tests/test_insight_step3_part2_records.py tests/test_insight_quality_gate.py tests/test_insight_whitelist_gate.py tests/test_ranking_article_publisher.py -q` -> 118 passed
- `python3 -m pytest tests/test_insight_nightly.py tests/test_insight_dedup_gate.py -q` -> 20 passed
- scoped `git diff --check` -> pass
- production DB copy smoke on `/tmp` only: `NEW 15938 -> 822`, `EXPIRED 3856`, `DROPPED_DISABLED_SIGNAL 11257`, one UZR draft candidate, two UZR `DROPPED_METRIC_RUN_CAP`

## Deploy

- code commit: `80b87ea`
- Cloud Build: `67bcb6db-468d-45ff-887a-74ff6e830a70` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:362-queue-80b87ea`
- digest: `sha256:b05e30ece3a0d90062ecf6d38acb2d2b81d3511389ab98e75993d8634786d136`
- Cloud Run Job: `insight-nightly`, generation `51`
- Scheduler: `data-insight-*` 7 triggers ENABLED
- manual execute: not run, to avoid extra publish/mail outside natural schedule

## Not Done

- Existing public WP posts were not edited.
- Scheduler / env / Secret were not changed.
- X / SNS posting was not executed.
