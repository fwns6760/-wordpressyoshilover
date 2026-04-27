# 190 publish-notice manual X candidates impl

- priority: P0.5
- status: REVIEW_NEEDED
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

## Review Needed

- `1ac710b` の動作をそのまま正式採用するか
- 191 spec を優先して hashtags 追加や wording 調整を別便で行うか
- spec 先行原則とのズレを accept するか
