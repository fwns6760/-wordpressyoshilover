# 121 x-post-live-helper-one-shot-smoke

## meta

- owner: Codex A after user unlock
- lane: A
- priority: P1
- status: BLOCKED_USER
- alias: PUB-005-B1
- parent: PUB-005
- blocked_by: X live unlock / credential boundary / 120 close
- created: 2026-04-26

## purpose

120 の queue から 1 件だけ取り出し、X API で one-shot live smoke する。
これは X live 解禁の境界なので、実装・実行ともに credential / live post の user unlock が必要。

## scope

- dry-run default
- `--live` 必須で実 POST
- queue 内の 1 件のみ対象
- success 時は ledger を `posted` に更新
- duplicate 再投稿は拒否
- secret 実値は表示しない
- Grok / xAI API は使わない
- `src/x_post_generator.py` の古い Grok/Gemini 経路は使わない

## non-goals

- daily cap rollout(122)
- cron / scheduler
- X 検索 / X 収集
- WP write
- mail real-send
- Cloud Run / `RUN_DRAFT_ONLY`

## acceptance

- `--live` なしでは X API 投稿不可
- dry-run で投稿文を確認できる
- live success 時に ledger が更新される
- duplicate 再投稿を拒否する
- X API failure 時に ledger が failed / retryable に残る
- secret values are never printed
- tests cover dry-run, missing live flag, duplicate, success/failure ledger update

## suggested files

- `src/x_post_live_helper.py`
- `src/tools/run_x_post_live_helper.py`
- `tests/test_x_post_live_helper.py`

## verification

```bash
python3 -m pytest tests/test_x_post_live_helper.py
python3 -m src.tools.run_x_post_live_helper --queue <queue.jsonl> --candidate-hash <hash>
```

Live verification is a separate user-unlocked smoke and must not be run automatically.
