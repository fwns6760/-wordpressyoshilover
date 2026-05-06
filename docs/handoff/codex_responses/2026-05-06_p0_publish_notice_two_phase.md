# p0_publish_notice_two_phase

## incident recap

- 2026-05-06 JST の publish-notice job で、22:14 JST 直前から 23:50 JST まで 900s timeout が連続した。
- 応急処置として `PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=0` を入れ、direct publish mail のみ先に復旧した。
- 重い箇所は `guarded_publish_history.jsonl` 読み込みを含む review/diagnostic phase で、ファイルサイズは約 96 MiB。

## implementation

- A 案(single job two-phase split)を repo 実装した。
- 新 env:
  - `ENABLE_PUBLISH_NOTICE_TWO_PHASE`
    - default OFF
    - OFF 時は legacy `scan()` + legacy send loop を維持
  - `PUBLISH_NOTICE_REVIEW_TIMEOUT_BUDGET_SECONDS`
    - default `0`
    - `>0` の時だけ review phase の各 scan 開始前に soft watchdog を効かせる
- `scan_direct_publish_only()` で direct publish request の emit と main cursor/history 更新を先に確定させる。
- `scan_review_only()` は direct phase 済み history を読み、review 専用 cursor のみ進める。
- `run_publish_notice_email_dry_run.py --scan` は flag ON 時に:
  1. direct phase scan
  2. direct per-post send
  3. burst summary send
  4. review phase scan/send
  の順で進む。
- review phase 例外は local try/except で握り、direct send 完了後の job を巻き戻さない。

## deploy notes

- rollout 順:
  1. image rebuild
  2. job update
  3. `ENABLE_PUBLISH_NOTICE_TWO_PHASE=1`
  4. 必要なら `PUBLISH_NOTICE_REVIEW_TIMEOUT_BUDGET_SECONDS=<small positive>` を追加
- rollback は env 1 本で可能:

```bash
ENABLE_PUBLISH_NOTICE_TWO_PHASE=0
```

- `PUBLISH_NOTICE_REVIEW_TIMEOUT_BUDGET_SECONDS` は `0` のままでも legacy-equivalent review execution になる。
