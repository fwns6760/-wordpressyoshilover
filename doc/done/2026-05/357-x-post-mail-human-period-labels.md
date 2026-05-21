# 357-x-post-mail-human-period-labels

## status

- **status**: CLOSED LIVE_DEPLOYED_VERIFIED (2026-05-21 audit、 prod log 5/20 22:00 fire で `dedup skip combo OBP/直近5試合` / `K_per_9/直近10試合` 等 human period label が period-family / dedup signature に組み込み完了、 mail 候補 pool の period 表示も `直近5試合・規定打席5以上` 形式で稼働)
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **scope**: X 投稿候補 mail の period 表示と候補 pool の微修正

## user intent

2026-05-16 user 指示:

- 日付だけの「5/11〜5/16」は日本の野球ファンには分かりにくい
- 「直近5試合」「直近10試合」を前面に出す
- 「7月成績」のような月別記録は分かりやすい
- 大手は全期間を載せるので、ヨシラバー system では全期間 / 今シーズン系はいらない

## implementation contract

変更する:

- `src/x_post_mail_lane.py`
- `src/tools/run_x_post_mail.py`
- `tests/test_x_post_mail.py`
- 本 ticket / board docs

変更しない:

- X / SNS live post
- Cloud Scheduler
- Cloud Run env / Secret
- WP publish
- `insight-nightly` / data-insight publish lane

## accepted behavior

- X 候補本文 2 行目は `（直近5試合・規定打席5以上）` のように表示する
- `直近10試合` も同様に日付だけでなく period label を前面に出す
- `7月成績` のような月別は、月初 3 日だけ前月成績として候補 pool に追加する
- 月別候補は巨人内 ranking 限定
- 全期間 / 今シーズン候補は X 投稿候補 mail pool から出さない
- 守備位置別も全期間ではなく `直近7日` に寄せる
- 24h dedup と period-family skip は維持する
- 直近5/10試合の期間窓は all-NPB `games` 日付ではなく、`batting_logs` に巨人 row がある試合日だけで作る
- X 投稿候補 mail は `insight.db` の最新 `games.game_date` が JST 今日から 2 日超古い場合、候補生成前に停止する

## verification

実行済み:

- GitHub Issue #29 comment: https://github.com/fwns6760/-wordpressyoshilover/issues/29#issuecomment-4465826892
- GitHub Issue #29 deploy comment: https://github.com/fwns6760/-wordpressyoshilover/issues/29#issuecomment-4465848146
- `python3 -m py_compile src/x_post_mail_lane.py tests/test_x_post_mail.py` — PASS
- `python3 -m pytest tests/test_x_post_mail.py -q` — PASS (`65 passed, 3 warnings`)
- `python3 -m py_compile src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py` — PASS
- `python3 -m pytest tests/test_x_post_mail.py -q` — PASS (`69 passed, 3 warnings`)
- production GCS DB copy `/tmp/insight-prod-20260516.db` smoke:
  - `latest_game_date 2026-05-15`
  - `staleness_days_at_2026_05_16_noon 1`
  - `recent5_giants_window ('2026-05-09', '2026-05-15')`
  - `recent10_giants_window ('2026-05-03', '2026-05-15')`
- `python3 -m compileall -q src/x_post_mail_lane.py tests/test_x_post_mail.py` — PASS
- `python3 -c "... ast.parse ..."` — PASS (`ast_ok`)
- `python3 -m pytest tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py -q` — PASS (`101 passed, 3 warnings, 6 subtests passed`)
- `git diff --check` — FAIL on unrelated existing `src/yoshilover-063-frontend.php` conflict markers
- scoped `git diff --check -- <changed files>` — PASS

## deploy

- 2026-05-16 14:35 JST deploy 済み。
- build context: clean `git archive HEAD` export `/tmp/x-post-mail-deploy-15ff032` (dirty worktree / unrelated conflict marker を混入させない)
- Cloud Build: `99349741-1b32-4f75-87a9-8c2d76896acd` SUCCESS
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:357-db-freshness-15ff032`
- digest: `sha256:ef71d320a4125b7060137b5db62947922d2797b2de1246fe906fc037b32888b8`
- Cloud Run Job: `x-post-mail-lane` generation `9`
- changed: Job image only
- unchanged: Scheduler / env / Secret / WP publish / X API / X live post
- manual execute: 未実行 (追加 mail を避け、次回自然 fire で観察)
