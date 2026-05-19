# 393: 価格据え置きの本文付き公開判断メール即時化 / 大量時 Part 分割

status: LIVE_DEPLOYED_OBSERVE
owner: Codex
lane: A
priority: P0
created: 2026-05-19 JST
github_issue: #68

---

## 1. 背景

2026-05-19 夜、21:45 fetch 後に draft は作成されたが、`publish-notice`
側で 67 件を `BURST_SUMMARY_ONLY` として抑止し、さらに summary mail が
無効だったため mail が 0 通になった。後続再実行では一部が
`DUPLICATE_WITHIN_24H` になり、「届いていない通知が再送しにくい」状態も
発生した。

user 要件:

- Cloud Run / Scheduler の実行回数を増やさず、価格は据え置きにする
- 記事ができたら原則 5 分以内に mail で公開判断できるようにする
- mail は公開判断に使うため、本文抜粋が必要。タイトルだけのまとめは禁止
- 大量時は 1 記事 1 通で爆発させず、本文付きの Part 分割メールにする

## 2. Scope

### ADD

- `publish_notice_email_sender` に本文付き公開判断 batch summary を追加する
  - 各 entry に `body_excerpt` / `admin_edit_url` / `publish_button_url` /
    `canonical_url` / `subtype` を持たせる
  - `summary_mode="judgment_batch"` の件名と本文を追加
  - 20 件ごとに `Part 1/N` 形式で分割
- `rss_fetcher` に fetcher 内 draft 判断 mail helper を追加する
  - fetcher が draft 作成後、同じ実行内で判断 mail を送る
  - 少数時は個別 mail、多数時は本文付き Part 分割 mail
  - 成功した Part 内の post は queue に `sent` として記録し、後続
    `publish-notice` の 24h duplicate で再通知を止める
- dry-run / gate:
  - `ENABLE_FETCHER_INLINE_DRAFT_NOTICE=1` の時だけ live send
  - env 未設定時は既存挙動不変

### KEEP

- Cloud Scheduler 新規追加なし
- Cloud Run Job / Service の起動回数増加なし
- WP 既存記事の status 変更なし
- X live post なし
- `RUN_DRAFT_ONLY` 変更なし

## 3. 完了条件

- 6 件以上の draft ができた時、本文抜粋付き Part 分割 mail を生成できる
- Part mail 内で各記事の `title / subtype / 本文抜粋 / 編集リンク / 公開ボタン`
  を確認できる
- 送信成功した Part 内 post は後続通知で重複しない
- `suppressed` / `error` / `dry_run` は通知済み扱いにしない
- 既存 `publish-notice` 個別通知・summary・dedup テストが通る

## 4. 不可触

- Scheduler 追加 / 5 分間隔化
- Cloud Run paid tier / 新規 service / 新規 Job 作成
- Secret 値の表示・変更
- `RUN_DRAFT_ONLY`
- X / SNS live post
- WP 既存記事の publish / trash / status 変更
- unrelated dirty files / logs / generated artifacts

## 5. 実装予定ファイル

- `src/publish_notice_email_sender.py`
- `src/rss_fetcher.py`
- `src/tools/run_publish_notice_email_dry_run.py`
- `tests/test_publish_notice_burst_summary.py`
- 必要なら narrow unit test 追加

## 6. テスト予定

- `python3 -m py_compile src/publish_notice_email_sender.py src/tools/run_publish_notice_email_dry_run.py src/rss_fetcher.py`
- `python3 -m unittest tests.test_publish_notice_burst_summary`
- `python3 -m unittest tests.test_publish_notice_email_sender`
- 必要に応じて関連 narrow tests

## 7. 作業ログ

- 2026-05-19: user GO。GitHub Issue #68 作成。
- 2026-05-19: repo 実装 commit `a626bda`。
  `publish_notice_email_sender` に `judgment_batch` summary mode を追加し、
  `run_publish_notice_email_dry_run` に batch summary + per-post sent marker を接続。
  `rss_fetcher` には draft 作成同一実行内の inline notice helper を追加。
- 2026-05-19: follow-up commit `bd0bb07` で fetcher inline notice queue を
  既存 `publish_notice/queue.jsonl` GCS state と共有。inline mail 送信済み post を
  後続 `publish-notice` で再送しないための merge/upload path を追加。
- 2026-05-19: follow-up commit `b495f6a` で fetcher 側の既存
  `FACT_CHECK_EMAIL_TO` を publish notice 宛先 fallback として利用。Secret 追加なし。
- 2026-05-19: tests:
  `python3 -m unittest tests.test_publish_notice_burst_summary tests.test_publish_notice_email_sender tests.test_run_publish_notice_email_dry_run`
  → 196 OK。
  `python3 -m pytest tests/test_rss_fetcher.py -q` → 30 passed。
  `python3 -m unittest tests.test_publish_notice_email_sender` → 176 OK。
- 2026-05-19: deploy:
  publish-notice image `publish-notice:393-judgment-bd0bb07`
  (Cloud Build `f22f5f1e-0bcf-41b8-9ae1-e146c7e2fe83`, digest
  `sha256:22991dbf0dda236636e86f2f973d07519e8abaaf685d18dc016262094f349bbe`)
  を Cloud Run Job generation `111` へ反映。
- 2026-05-19: deploy:
  fetcher image `yoshilover-fetcher:393-inline-mail-b495f6a`
  (Cloud Build `be7cbe88-0e60-4754-8def-3d8f3207bd74`, digest
  `sha256:b9797071571a08302bb92d7d818523741f4c877285889a35827afc5198dc5c77`)
  を revision `yoshilover-fetcher-00445-zm7` / traffic 100% へ反映。
  `/health` → `OK`。
- 2026-05-19: live env:
  `ENABLE_PUBLISH_NOTICE_JUDGMENT_BATCH=1`,
  `PUBLISH_NOTICE_JUDGMENT_BATCH_THRESHOLD=6`,
  `PUBLISH_NOTICE_JUDGMENT_BATCH_PART_SIZE=20`,
  `PUBLISH_NOTICE_BURST_THRESHOLD=-1`,
  `DISABLE_BURST_SUMMARY_MAIL=0`,
  `ENABLE_FETCHER_INLINE_DRAFT_NOTICE=1`,
  `FETCHER_INLINE_DRAFT_NOTICE_INDIVIDUAL_LIMIT=5`,
  `FETCHER_INLINE_DRAFT_NOTICE_PART_SIZE=20`,
  `ENABLE_FETCHER_INLINE_DRAFT_NOTICE_REMOTE_QUEUE=1`。
- 2026-05-19: price-neutral cleanup:
  追加していた `publish-notice-peak-followup` は `PAUSED`
  (`25,55 20-21 * * *` / Asia/Tokyo)。以後は既存 fetch 実行内 inline mail で
  追加 Cloud Run 実行なし。
- 2026-05-19: 残 acceptance:
  次回自然 fetch で draft が作成された時に
  `fetcher_inline_draft_notice_result` log と実 mail 本文を確認する。
