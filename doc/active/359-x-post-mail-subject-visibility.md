# 359-x-post-mail-subject-visibility

## status

- **status**: REVIEW_NEEDED
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **scope**: X 投稿候補 mail の件名を他の自動通知と見分けやすくする

## user intent

2026-05-16 user 指示:

- 他の自動通知も来るので X 投稿候補 mail だと気づきにくい
- title / 件名を分かりやすくしたい
- ポストの絵文字など、受信箱で目に入る工夫がほしい

## implementation contract

変更する:

- `src/x_post_mail_lane.py`
- `tests/test_x_post_mail.py`
- 本 ticket / board docs

変更しない:

- 候補生成ロジック
- DB read / GCS dedup
- mail 宛先 / SMTP / Secret / env
- Cloud Scheduler 時刻
- WP publish
- X / SNS live post

## accepted behavior

- 件名は `📮【要確認：巨人データX投稿候補 N件】午後 2026-05-16 15:00 JST` のように、他通知と見分けられる
- 件名に `X投稿候補` / `巨人データ` / 件数 / 時間帯 / timestamp が入る
- text / HTML body の先頭にも `巨人データX投稿候補` と明記する
- body には「公開通知ではない」ことを明記する
- メール本文の X intent URL / 280 字制限 / 候補内容は変えない

## verification

実行済み:

- `python3 -m py_compile src/x_post_mail_lane.py tests/test_x_post_mail.py`
  - PASS
- `python3 -m pytest tests/test_x_post_mail.py -q`
  - PASS (`69 passed, 3 warnings`)
- `python3 -m compileall -q src/x_post_mail_lane.py tests/test_x_post_mail.py`
  - PASS
- AST parse
  - PASS (`ast_ok`)
- scoped `git diff --check`
  - PASS
- `python3 -m pytest tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py -q`
  - PASS (`105 passed, 3 warnings, 6 subtests passed`)

## deploy notes

- live 反映には `x-post-mail-lane` image rebuild + Cloud Run Job image update が必要
- Scheduler / env / Secret は変更しない
- 手動 execute は追加 mail を送るため、原則実行しない。次回自然 fire で確認する
