# 189 publish-notice contextual manual X candidates

- priority: P0.5
- status: CLOSED
- owner: Codex B
- lane: B
- parent: 190 / 191 / 095-D / 131 / PUB-005

## Purpose

公開通知メールの手動 X 投稿候補を、3 本固定から subtype selector 方式へ拡張する。
X API の URL 付き投稿は行わず、運営者がメールからコピペできる候補だけを生成する。

## Scope

- `src/publish_notice_email_sender.py`
- `tests/test_publish_notice_email_sender.py`
- this ticket / board docs

## Requirements

- `build_manual_x_post_candidates()` を selector 方式へ変更する。
- 内部テンプレは 10〜12 種持つ。
- 判定は現状確実に取れる `subtype` に限定する。
- 対象 subtype は `lineup / postgame / farm / notice / program / default` 程度。
- メールに出す候補は通常 3 本、`lineup / postgame / program` は最大 4 本。
- `article_intro` は原則 1 本出す。
- subtype 別に記事タイプ特化テンプレを 1〜2 本出す。
- `inside_voice` は `lineup / postgame / farm / program` のみ出す。
- `notice` は慎重寄りにし、`fan_reaction_hook` を出さない。
- title / summary に怪我・復帰系ワードがある場合は `fan_reaction_hook` を出さない。
- URL付き候補は最大 3 本まで。
- 全候補は 280 字以内。

## Explicit Non-Goals

- 監督コメント・選手コメント・SNS話題など、subtypeで確実に取れない分類は今回やらない。
- X API 投稿はしない。
- X queue / ledger / Cloud Run / Scheduler / Secret Manager は触らない。
- WP write / publish runner / mail real-send smoke はしない。
- LLM は使わない。

## Acceptance

- [x] subtype 別に出力候補が変わる。
- [x] `notice` で `fan_reaction_hook` が出ない。
- [x] 怪我・復帰ワードで `fan_reaction_hook` が出ない。
- [x] `inside_voice` が条件付きで出る。
- [x] 全候補が 280 字以内。
- [x] URL付き候補が最大 3 本。
- [x] `python3 -m pytest tests/test_publish_notice_email_sender.py` が通る。

## Verification

- `python3 -m pytest tests/test_publish_notice_email_sender.py`
- result: 22 passed, 3 warnings
