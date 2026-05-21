# 358-INSIGHT-local-production-db-pull

## status

- **status**: CLOSED LIVE_DEPLOYED_VERIFIED (2026-05-21 audit、 `src/tools/pull_insight_db_from_gcs.py --target /tmp/yoshilover-insight-latest.db --ttl-seconds 0` を本日 404 audit で実利用、 `production_state: games: 259, pitching_logs: 2108` の prod DB pull 成功、 download-only / 双方向 sync 無し / GCS source-of-truth 維持 の決定通り稼働)
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **scope**: production `insight.db` をローカル確認用に読み取り専用 pull する operator tool

## user intent

2026-05-16 user 指示:

- mail / 自動公開のデータがどこから来るのか分かりにくい
- DB 同士が同期されているのか確認したい
- ローカル DB が古いことで判断を間違えるのは困る
- ただし本番DBへローカルDBを同期するかどうかは危険なので、やるべきか決めてほしい

## decision

本番DBとローカルDBの双方向同期、またはローカルから本番GCSへの同期は **しない**。

理由:

- production source of truth は GCS `insight.db`
- local `data/insight/insight.db` は生成物で、古くても本番処理の正本ではない
- local -> production sync を許すと古いDBで本番を巻き戻す事故が起きる

代わりに、確認時だけ production GCS からローカルへ **download-only** で pull し、最新試合日 / 巨人最新試合日 / row count を表示する。

## implementation contract

変更する:

- `src/tools/pull_insight_db_from_gcs.py`
- `tests/test_pull_insight_db_from_gcs.py`
- 本 ticket / board docs

変更しない:

- Cloud Run Job
- Cloud Scheduler
- Secret / env
- GCS upload path
- WP publish
- mail send
- X / SNS live post
- `data/insight/insight.db` の commit

## accepted behavior

- default target は `/tmp/yoshilover-insight-latest.db`
- default では repo-local `data/insight/insight.db` を上書きしない
- `--replace-local` を明示した場合だけ `data/insight/insight.db` を上書きする
- GCS は download-only。upload API は呼ばない
- ローカル Python に `google-cloud-storage` が無い場合は `gcloud storage cp` に fallback し、同じく download-only にする
- tool output は JSON で、少なくとも以下を含む:
  - source bucket / object
  - local path / file size
  - latest `games.game_date`
  - latest Giants game date based on `batting_logs.team_name`
  - staleness days
  - key table row counts
- `insight.db` object missing / download failure は silent skip せず、non-zero exit + reason を返す

## verification

実行済み:

- `python3 -m py_compile src/tools/pull_insight_db_from_gcs.py tests/test_pull_insight_db_from_gcs.py`
  - PASS
- `python3 -m pytest tests/test_pull_insight_db_from_gcs.py tests/test_manual_intake_insight_query.py tests/test_insight_gcs_sync.py -q`
  - PASS (`34 passed, 3 warnings`)
- `python3 -m compileall -q src/tools/pull_insight_db_from_gcs.py tests/test_pull_insight_db_from_gcs.py`
  - PASS
- AST parse
  - PASS (`ast_ok`)
- scoped `git diff --check`
  - PASS
- production GCS read-only smoke:
  - command: `python3 -m src.tools.pull_insight_db_from_gcs --target /tmp/yoshilover-insight-latest-smoke.db`
  - non-escalated first run: FAIL (`gcloud` config dir read-only in sandbox)
  - escalated read-only rerun: PASS
  - transport: `gcloud_storage`
  - latest_game_date: `2026-05-16`
  - latest_giants_game_date: `2026-05-16`
  - staleness_days: `0`
  - tables: games `242`, batting_logs `4356`, pitching_logs `1922`, advanced_metric_snapshots `36779`, article_candidates `16202`

未実行:

- `--replace-local` による repo-local DB 上書き smoke は未実行。理由: generated DB を不用意に汚さないため。
- Cloud Run / Scheduler / env / Secret / GCS upload / WP publish / mail / X / SNS は対象外、未実行。
