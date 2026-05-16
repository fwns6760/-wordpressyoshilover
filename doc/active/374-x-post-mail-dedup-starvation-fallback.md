# 374-x-post-mail-dedup-starvation-fallback

## status

- **status**: REVIEW_NEEDED
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-16 JST
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/43
- **scope**: X 投稿候補 mail の 24h dedup starvation fallback

## user intent

2026-05-16 user 指示:

- 353〜355 関連 mail が 1 回しか来なかった理由を確認したい
- 候補がないのではなく、直さないと今後も自然 mail が来ないなら恒久対応したい
- mail は止めなくてよい

## cause

- 07:00 / 12:00 JST の自然 Scheduler fire は service account mismatch で HTTP 403 だった
- 15:00 JST は送信成功したが、手動確認で送った 10 候補が 24h dedup ledger に記録済みだったため候補が 1 件まで減った
- 17:30 JST は dedup skip と sample不足で候補 0 件になり、mail send が skip された
- 現行 dedup は hard skip のため、候補 pool が薄い時間帯に「重複抑制」が「メール停止」へ化ける

## implementation contract

変更する:

- `src/tools/run_x_post_mail.py`
- `tests/test_x_post_mail.py`
- 本 ticket / board docs

変更しない:

- `src/x_post_mail_lane.py` の combo / GCS ledger 仕様
- SMTP credential / Secret / env
- Cloud Scheduler schedule / OAuth service account
- WP publish / WP 既存記事
- X API / SNS live post
- `insight-nightly` / data-insight publish lane

## accepted behavior

- 24h dedup は通常維持する
- dedup 後の候補数が `X_POST_MAIL_DEDUP_MIN_CANDIDATES` 未満なら、dedup-safe 候補を先頭に残し、不足分だけ dedup なし候補で backfill する
- default floor は 3 件
- dedup 後に 3 件以上ある場合は従来通り再選別しない
- dedup / GCS の read-write 失敗は mail send を止めない既存方針を維持する
- 手動 execute は追加 mail 回避のため実行しない

## verification

実行済み:

- GitHub Issue #43 作成: https://github.com/fwns6760/-wordpressyoshilover/issues/43
- `python3 -m py_compile src/tools/run_x_post_mail.py tests/test_x_post_mail.py` — PASS
- `python3 -m pytest -q tests/test_x_post_mail.py` — PASS (`71 passed, 3 warnings`)
- `python3 -m compileall -q src/tools/run_x_post_mail.py tests/test_x_post_mail.py` — PASS
- `python3 -c "... ast.parse ..."` — PASS
- `python3 -m pytest -q tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py` — PASS (`107 passed, 3 warnings, 6 subtests passed`)

## deploy

- pre-deploy: pending
- manual execute: 未実行予定 (追加 mail を避け、次回自然 fire で観察)

## notes

- これは dedup の撤去ではない
- 重複抑制で候補が十分残る時は従来の 24h dedup がそのまま効く
- 候補が枯れる時だけ、mail visibility を優先して dedup を soft preference に下げる
