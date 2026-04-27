# 190 publish-notice manual X candidates impl

- priority: P0.5
- status: CLOSED
- owner: Claude / User follow-up
- lane: B
- parent: 191 / 095-D / 131 / PUB-005

## Background

`1ac710b` は commit message 上は `188` だが、正式番号は 188(IAM fix)と衝突するため、この実装記録を `190` として再整理する。

元 user 要望は以下だった。

- 公開通知メールに手動 X 投稿用本文案を入れる
- ハッシュタグ付き
- 自動 X 投稿は中止し、手動コピペ用にする
- **実装はまだしない、設計のみ**

## What Landed In `1ac710b`

- `src/publish_notice_email_sender.py`
  - `MAX_MANUAL_X_POST_LENGTH = 280` を追加
  - `build_manual_x_post_candidates()` を追加
  - subtype に応じて 3 本の deterministic 候補を返す実装を追加
  - `build_body_text()` に `manual_x_post_candidates:` block と `article_url:` 行を追加
- `tests/test_publish_notice_email_sender.py`
  - mail body に 3 候補が出ることを確認
  - blank summary でも壊れないことを確認
  - 280 字以内制約を確認

## Impl Summary

- 候補は 3 本固定
  - `x_post_1_article_intro`
  - `x_post_2_reaction_hook`
  - `x_post_3_inside_voice`
- subtype 分岐は `lineup / postgame / farm / notice / program / default`
- URL 付き候補は 2 本、inside voice は URL なし
- X API / queue / Cloud Run / Scheduler / Secret / WP write には触れていない

## Gap Versus Original Request

- user 要望にあった **hashtags** は実装されていない
- user 要望は **design-only** だったが、`1ac710b` は code と tests まで land している
- その後 `189`(`b7a9e1f`) で selector 方式まで拡張されており、spec freeze 前に scope が前進している

## Ratify

- 2026-04-27 user 認容: 「ポストも乗るんだよね。公開記事に。」を、publish-notice mail の manual X candidates 挙動 keep として正式採用する。
- `188` / `189` commit(`1ac710b` / `b7a9e1f`)で landed した backend manual X candidates 実装を正式 scope として freeze する。
- `9vd48` / `9rsjt` / `pwh4r` execution で X candidates 入り mail が user 受信済みであり、実運用上も keep 前提で整合している。
- `195` で同 selector / wording 系 logic を frontend share corner に流用済みであり、mail / frontend 間の整合確認も完了している。
