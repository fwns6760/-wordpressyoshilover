# 2026-05-28 — 441 X-post player history window 24h → 168h

## summary

user 「大城、 マルティネスなどかなりデル」 → 推奨案 (window 7d + relaxed fallback 削除) GO → 実装 + test 修正 + 134 tests passed。

## events

- HH:MM JST | dedup_audit_done | 441 | root cause: 24h window + 2-day blob loop + relaxed fallback の 3 重 | 推奨 1 案
- HH:MM JST | user_go | 441 | 「それにする」 + 「他選手の異常値」 についても問あり | dedup 実装着手 / surprise score は別 ticket
- HH:MM JST | impl_done | 441 | x_post_mail_lane.py 4 箇所 + run_x_post_mail.py 2 箇所 + test 2 件修正 | targeted 35 + full 134 passed
- HH:MM JST | doc_done | 441 | ticket doc + README priority 行追加 | commit + push 待ち

## next

- commit + push (feat/377 branch)
- Cloud Build x-post-mail-lane image (tag: `xpost-history-7d-<short_sha>`)
- `gcloud run jobs update x-post-mail-lane --image=... --update-env-vars X_POST_MAIL_PLAYER_HISTORY_HOURS=168`
- env 不変派の場合は default 168 が効くので env 設定なしでも可、 明示記録のため設定推奨
- 手動 execute は user 判断 (追加 real mail 回避)

## open question (for next session)

- 「他選手の異常値」 (surprise score 実装) は別 ticket 起票必要。 436 §10.2 設計は ある (若手 / 復帰 / 起用増 / 前回圏外 Top10 入り / 直近上昇)、 selection score への組込が unimpl。 user GO 後に着手。
