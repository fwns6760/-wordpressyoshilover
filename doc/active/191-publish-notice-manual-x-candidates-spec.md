# 191 publish-notice manual X candidates spec

- priority: P0.5
- status: REVIEW_NEEDED
- owner: Claude / User follow-up
- lane: B
- parent: 095-D / 131 / PUB-005

## Background

`b6b2b2b` は commit message 上は `188` だが、正式番号 188(IAM fix)と衝突するため、この spec 記録を `191` として再整理する。

## What `b6b2b2b` Recorded

- `doc/active/188-publish-notice-manual-x-post-candidates.md` を新規作成
- `doc/README.md` と `doc/active/assignments.md` に手動 X 候補 ticket を追加
- status は `READY`
- purpose は「公開通知メールに、運営者がコピペして手動投稿できる X 投稿本文案を入れる」
- non-goals は `X API 投稿なし / X queue・ledger・GCP live なし / WP write なし / LLM なし`

## Original User Intent To Preserve

- 公開通知メールに手動 X 投稿用本文案を入れる
- **ハッシュタグ付き**
- 自動 X 投稿は中止し、手動コピペ用にする
- **実装はまだしない、設計のみ**

## Gap Versus Reality

- `190`(`1ac710b`) で code 実装まで land 済み
- `189`(`b7a9e1f`) で selector 方式へさらに拡張済み
- landed behavior には hashtag 要件がまだ入っていない
- spec-only 予定だったため、実装順序が user 要望より先行している

## Review Needed

- 191 を正式 spec として維持するか
- hashtag 要件を後追い実装するか
- 190 / 189 を accept するか、差分是正 ticket を別で立てるか
