# MKT-001 publish-notice marketing mail classification

## Meta

- number: MKT-001
- alias: 219
- status: IN_FLIGHT
- priority: P0.5
- note: parallel implementation is active in `bh1vb526h`; the original 219 spec body below is preserved and this doc is now the marketing-source path

## Alias Note

This doc inherits the original `219 publish-notice marketing mail classification` content with a historical alias retained for the repo-wide board and implementation references.

## Fixed Subject Prefixes

- `【投稿候補】`
- `【公開済】`
- `【要確認】`
- `【警告】`
- `【まとめ】`
- `【緊急】`

## Fixed Body Metadata Fields

- `mail_type`
- `mail_class`
- `action`
- `priority`
- `post_id`
- `subtype`
- `x_post_ready`
- `reason`

## Summary

公開通知メールを「届いたかどうか」から、マーケ作業にそのまま使える通知へ引き上げる。

現状は Gmail 上で送信元が自分に見えやすく、件名や本文から次アクションを判断しにくい。公開数が増えるほど見落としや混乱が起きるため、**メール件名の先頭だけで行動が分かる** prefix / 本文先頭の分類 metadata / Gmail label 前提の仕分け contract を固定する。

## Priority

- priority: P0.5
- status: READY
- owner: Codex B / Claude
- lane: mail本文・マーケ運用
- ready_for: implementation
- blocked_by: none

## Background

- `publish-notice` は GCP で5分毎に動作し、公開記事メールは届くようになった。
- ただし、Gmail一覧では送信元が自分に見え、メール種別が分かりにくい。
- X API のURL付き投稿コスト上昇により、当面はメール内の手動X投稿候補を人間が使う。
- そのため、メールは単なる通知ではなく「公開確認 / X投稿候補 / 要確認 / 警告 / まとめ」を仕分けられる必要がある。

## Goal

Gmail filter / label / label color で運用できるよう、メール件名と本文先頭を安定した分類形式にする。

最優先は本文ではなく件名:

- Gmail一覧で件名の先頭だけ見れば判断できる
- `YOSHILOVER` より先に action label を置く
- 記事タイトルは後ろに置く
- 件名が長くても先頭15文字で作業種別が分かる

Subject format:

```text
【投稿候補】記事タイトル | YOSHILOVER
【公開済】記事タイトル | YOSHILOVER
【要確認】記事タイトル | YOSHILOVER
【警告】post_id=... | YOSHILOVER
【まとめ】直近N件 | YOSHILOVER
【緊急】X/SNS確認 | YOSHILOVER
```

## Mail Classes

### publish

通常公開確認。

- subject prefix: `【公開済】`
- action: `check_article`
- x_post_ready: `false`

### x_candidate

コピペ可能なX投稿候補あり。

- subject prefix: `【投稿候補】`
- action: `copy_x_post`
- x_post_ready: `true`

### review

記事・X候補・source表示などに確認が必要。

- subject prefix: `【要確認】`
- action: `review_article`
- x_post_ready: `false`

### warning

送信・公開・重複・suppressionなどの異常。

- subject prefix: `【警告】`
- action: `inspect_system`

### summary

複数記事のまとめ通知。

- subject prefix: `【まとめ】`
- action: `scan_summary`

### emergency

X/SNS誤投稿など即時確認が必要なもの。

- subject prefix: `【緊急】`
- action: `urgent_check`

## Body Header Contract

per-post mail body の先頭に、Gmail検索や人間の目視で判定しやすい metadata block を置く。

```text
mail_type: publish_notice
mail_class: x_candidate
action: copy_x_post
priority: normal
post_id: 63797
subtype: default
x_post_ready: true
reason: x_candidates_ready
```

## X Candidate Classification

`【投稿候補】` にしてよい条件:

- manual X候補が存在する
- URL付き候補が280字以内
- summary生貼りに見えない
- `📰` / `⚾` / `[…]` / source block が候補本文へ混入していない
- notice / injury / recovery / roster movement など慎重系でない
- fan hook が不適切でない

それ以外は `【公開済】` または `【要確認】` へ倒す。

## Gmail Operation

Gmail側の推奨 label:

- `YOSHILOVER/公開`
- `YOSHILOVER/X投稿候補`
- `YOSHILOVER/要確認`
- `YOSHILOVER/警告`
- `YOSHILOVER/まとめ`

Gmailの色分けは Gmail label color で行う。送信側コードから受信一覧の色を直接指定しない。

## Implementation Scope

Likely files:

- `src/publish_notice_email_sender.py`
- `tests/test_publish_notice_email_sender.py`

Allowed:

- subject prefix logic
- body header metadata block
- mail class selector
- tests for subject/body classification

Out of scope:

- Gmail filter creation
- Gmail label creation
- Gmail star operation
- SMTP account / alias change
- Secret change
- GCP deploy
- live mail send
- WP write
- X API post

## Acceptance

- per-post 件名が mail class に応じて分類される
- 件名の先頭15文字以内で `投稿候補 / 公開済 / 要確認 / 警告 / まとめ / 緊急` が分かる
- 件名末尾に `| YOSHILOVER` を入れ、Gmail filter 用の安定文字列を残す
- summary / alert / emergency の件名 prefix が分類される
- 本文先頭に `mail_type / mail_class / action / priority / post_id / subtype / x_post_ready / reason` が入る
- Gmail filter が subject prefix で分類できる
- X投稿候補が安全にコピペ可能な時だけ `【投稿候補】`
- summary生貼り・source block混入・慎重系は `投稿候補` にしない
- 既存の `manual_x_post_candidates` block を壊さない
- tests pass

## Test Plan

- `python3 -m unittest tests.test_publish_notice_email_sender`
- `python3 -m unittest discover -s tests`

Test cases:

- normal publish -> `【公開済】... | YOSHILOVER`
- clean X candidates -> `【投稿候補】... | YOSHILOVER`
- raw summary/source block mixed candidate -> `【要確認】... | YOSHILOVER`
- roster/injury/recovery sensitive item -> not `【投稿候補】`
- summary -> `【まとめ】... | YOSHILOVER`
- alert -> `【警告】... | YOSHILOVER`
- emergency -> `【緊急】... | YOSHILOVER`
- body header metadata exists before article fields

## Codex Prompt

```text
目的:
publish-notice メールをマーケ作業用に仕分けできる形へ改善してください。
メールは届くようになったが、Gmail上で送信元が自分に見えやすく、何をすべきか判断しにくいです。

対象:
- src/publish_notice_email_sender.py
- tests/test_publish_notice_email_sender.py

やること:
1. per_post メールを mail class に分類する
   件名の先頭で行動が分かるように、YOSHILOVERよりaction labelを先に置く。
   - publish: 【公開済】記事タイトル | YOSHILOVER
   - x_candidate: 【投稿候補】記事タイトル | YOSHILOVER
   - review: 【要確認】記事タイトル | YOSHILOVER
   - warning: 【警告】post_id=... | YOSHILOVER
   - summary: 【まとめ】直近N件 | YOSHILOVER
   - emergency: 【緊急】X/SNS確認 | YOSHILOVER

2. per_post 本文先頭に metadata block を追加する
   - mail_type
   - mail_class
   - action
   - priority
   - post_id
   - subtype
   - x_post_ready
   - reason

3. `【投稿候補】` は安全な候補だけにする
   - manual X候補あり
   - URL付き候補280字以内
   - summary生貼りに見えない
   - `📰` / `⚾` / `[…]` / source block が候補本文へ混入していない
   - notice / injury / recovery / roster movement など慎重系ではない

4. 不安なものは `【要確認】` へ倒す

やらないこと:
- Gmail filter / label作成
- SMTP account / alias変更
- Secret変更
- GCP deploy
- live mail send
- WP write
- X API投稿
- git add -A

受け入れ条件:
- 件名の先頭だけで作業種別が分かる
- `YOSHILOVER` は件名末尾に残し、Gmail filter用の安定語として使う
- Gmail filterで分類できる
- 本文先頭だけ見れば次アクションが分かる
- 既存のmanual_x_post_candidatesを壊さない
- tests/test_publish_notice_email_sender.py が通る
- 可能なら python3 -m unittest discover -s tests も通る

完了報告:
- 変更ファイル
- mail class判定ルール
- subject prefix一覧
- body header例
- test結果
- commit hash
```

## Notes

This is a marketing-ops ticket. It should not be mixed with GCP deploy, Gmail settings, or X API live posting.
