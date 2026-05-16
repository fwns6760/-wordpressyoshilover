# 357-x-post-mail-human-period-labels

## status

- **status**: REVIEW_NEEDED
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

## verification

実行済み:

- `python3 -m py_compile src/x_post_mail_lane.py tests/test_x_post_mail.py` — PASS
- `python3 -m pytest tests/test_x_post_mail.py -q` — PASS (`65 passed, 3 warnings`)
- `python3 -m compileall -q src/x_post_mail_lane.py tests/test_x_post_mail.py` — PASS
- `python3 -c "... ast.parse ..."` — PASS (`ast_ok`)
- `python3 -m pytest tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py -q` — PASS (`101 passed, 3 warnings, 6 subtests passed`)
- `git diff --check` — FAIL on unrelated existing `src/yoshilover-063-frontend.php` conflict markers
- scoped `git diff --check -- <changed files>` — PASS

## deploy

- この ticket 作成時点では未 deploy。
- Cloud Run Job `x-post-mail-lane` の image 更新は user 明示 GO 後に行う。
