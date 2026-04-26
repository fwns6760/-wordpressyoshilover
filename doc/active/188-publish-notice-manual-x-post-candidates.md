# 188 publish-notice manual X post candidates

- priority: P0.5
- status: READY
- owner: Codex B
- lane: B
- parent: 095-D / 131 / PUB-005

## Purpose

公開通知メールに、運営者がコピペして手動投稿できる X 投稿本文案を入れる。
X API の URL 付き投稿コストが高いため、この記事 URL 付きの自動 X 投稿は行わず、メール内の文案提示に寄せる。

## Scope

- `src/publish_notice_email_sender.py`
- `tests/test_publish_notice_email_sender.py`
- this ticket / board docs

## Requirements

- per-post publish notice mail body に手動 X 投稿候補を 3 パターン追加する。
- 候補は 280 字以内に収める。
- 候補 1 は記事紹介型で URL を含める。
- 候補 2 は反応フック型で URL を含める。
- 候補 3 は「なかの人」向け一言型で、URL なしでも使える短文にする。
- subtype / title / summary だけで deterministic に生成する。
- 既存の publish notice subject / recipient / duplicate suppression / burst summary / alert mail の挙動を変えない。

## Explicit Non-Goals

- X API 投稿はしない。
- X queue / ledger / Cloud Run / Scheduler / Secret Manager は触らない。
- WP write / publish runner / mail real-send smoke はしない。
- LLM は使わない。
- URL 付き X 自動投稿の再開判断は扱わない。

## Acceptance

- `build_body_text()` が既存 5 行情報に加えて `manual_x_post_candidates` block を出す。
- 3 候補すべてが 280 字以内。
- blank summary でも `(なし)` summary 行を維持し、候補生成で落ちない。
- `send()` の real path が新しい body を bridge に渡す。
- `python3 -m pytest tests/test_publish_notice_email_sender.py` が通る。

## Notes

- 107 / 119 / 120 などの X gate / queue 実装とは分離する。
- 今回は publish 通知メールの本文補助だけなので、既存公開不具合修正作業を止めない。
