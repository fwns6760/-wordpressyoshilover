# 122 x-post-controlled-autopost-rollout

## meta

- owner: Codex A after 121 smoke success
- lane: A
- priority: P1.5
- status: PARKED
- alias: PUB-005-C
- parent: PUB-005
- blocked_by: 121 smoke success
- created: 2026-04-26

## purpose

121 の one-shot smoke 成功後、X 投稿を daily cap 付きで controlled autopost に広げる。
投稿ごとの user 確認は不要に寄せるが、Green only / duplicate guard / failure stop を維持する。

## scope

- 初期 daily cap 1 件
- 安定後 daily cap 3 件
- 119 eligibility を必ず通す
- 120 ledger / duplicate guard を必ず使う
- 121 live helper を投稿実行の下層として使う
- failure / duplicate / cap 超過は stop し、理由を記録する

## non-goals

- cron 化の即時実装
- X 検索 / X 収集
- Grok / xAI API
- WP write
- Cloud Run / `RUN_DRAFT_ONLY`
- Yellow / Red 記事の投稿

## acceptance

- daily cap enforced
- duplicate 防止
- refusal / skip / failure 理由が記録される
- X API failure 時に自動連投しない
- Green only gate を bypass できない
- tests cover cap, duplicate, failure stop, no eligible candidates

## rollout default

1. 1日1件で開始
2. 7日間事故なしなら 1日3件へ拡大
3. cron 化はさらに後続 ticket で判断

## suggested files

- `src/x_post_controlled_rollout.py`
- `src/tools/run_x_post_controlled_rollout.py`
- `tests/test_x_post_controlled_rollout.py`

## verification

```bash
python3 -m pytest tests/test_x_post_controlled_rollout.py
python3 -m src.tools.run_x_post_controlled_rollout --dry-run
```
