# 191 publish-notice manual X candidates spec

- priority: P0.5
- status: CLOSED
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

## Ratify

- `188`(impl) + `189`(contextual selector) + `195`(frontend share corner) で、本件の manual X candidate spec は実装整合込みで完結したものとして扱う。
- subtype × pattern mapping は `lineup / postgame / farm / notice / program / default` を lock し、publish-notice mail / frontend ともこの軸を正式 spec とする。
- hashtag は user 任意の追記領域として扱い、現実装は base 文のみを返す仕様で freeze する。コピペ後の hashtag 追加は user 運用で吸収可能とする。
- 元要望の design-only 先行原則からは逸脱したが、2026-04-27 の user 認容と既配信メール実績をもって keep ratify を確定する。
