# 120 x-post-autopost-queue-and-ledger

## meta

- owner: Codex A or either
- lane: A/either
- priority: P1
- status: PARKED
- alias: PUB-005-A3
- parent: PUB-005
- blocked_by: 119 close
- created: 2026-04-26

## purpose

119 の eligible 記事と 107 の template candidates を、X 投稿候補 queue / ledger にする。
同一記事・同一文案の二重投稿を防ぎ、121 live helper が安全に 1 件だけ取り出せる状態を作る。

## scope

- 119 eligible を入力にする
- 107 / `src/x_post_template_candidates.py` の文案候補を利用する
- `candidate_hash` を生成する
- queue / ledger を dry-run default で扱う
- duplicate を refused / skipped として記録する

## ledger fields

- `post_id`
- `article_url`
- `template_type`
- `candidate_hash`
- `queued_at`
- `posted_at`
- `status`

## non-goals

- X API live post
- WP write
- mail real-send
- LLM / Gemini / Grok / xAI
- X 検索 / X 収集
- cron / scheduler

## acceptance

- 同一記事二重 queue 防止
- 同一 candidate 二重投稿防止
- `queued`, `posted`, `skipped`, `failed` 相当の status が表現できる
- dry-run summary が出る
- queue / ledger の読み書き tests がある
- X API call zero
- secret read/display zero

## suggested files

- `src/x_post_autopost_queue.py`
- `src/tools/run_x_post_autopost_queue.py`
- `tests/test_x_post_autopost_queue.py`

## verification

```bash
python3 -m pytest tests/test_x_post_autopost_queue.py
python3 -m src.tools.run_x_post_autopost_queue --fixture <eligible.json> --dry-run
```
