# 076 Publish Notice Email

## Purpose

- WordPress の publish event を独立 scanner で検出し、ticket 072 の mail bridge を経由して公開通知 mail を 1 通送る。
- 073 朝分析、074 X 下書き、075 ops mail とは分離した専用 sender にする。
- 061-P1.2 の published scanner / queue / history / cursor は再利用しない。

## Interface

- `src/publish_notice_email_sender.py`
  - `PublishNoticeRequest`
  - `PublishNoticeEmailResult`
  - `build_subject()`
  - `resolve_recipients()`
  - `build_body_text()`
  - `send()`
- `src/publish_notice_scanner.py`
  - `ScanResult`
  - `scan()`
- `src/tools/run_publish_notice_email_dry_run.py`
  - `--scan`
  - `--input <path>`
  - `--stdin`
  - `--send`
  - `--send-enabled`
  - `--cursor-path`
  - `--history-path`
  - `--queue-path`

## Suppress Rules

- `EMPTY_TITLE`
- `MISSING_URL`
- `NO_RECIPIENT`
- `GATE_OFF`

`dry_run=True` では bridge を呼ばない。real send は `--send` と `send_enabled` と recipient 解決の 3 条件が揃ったときだけ実行する。

## Dedup

- `logs/publish_notice_history.json` に `post_id -> publish_time_iso` を保持する。
- scan 開始時に 24 時間超の entry を prune する。
- 同一 `post_id` が 24 時間以内に history に存在する場合は `RECENT_DUPLICATE` で skip する。
- 同一 run 内の重複 `post_id` も `RECENT_DUPLICATE` で skip する。
- cursor 不在の初回 run は backfill せず、`now` を cursor に保存して emit 0 で終了する。

## Queue / Logs

- `logs/publish_notice_cursor.txt`
- `logs/publish_notice_history.json`
- `logs/publish_notice_queue.jsonl`

`queue.jsonl` は append-only。scanner が `queued` 行を残し、CLI は `dry_run` / `sent` / `suppressed` の result 行を追加する。

## Non-Goals

- `automation.toml` の本番有効化
- 061-P1.2 scanner の再利用
- WP PHP hook
- LLM による本文生成
- X API 連携
- real send default
- backfill
- 過去 publish の遡及送信

## Acceptance

- 通常 publish で 1 通分の request が emit され、gate 条件を満たしたときだけ 072 bridge が 1 回呼ばれる。
- `status=publish` 以外は scanner fetch 条件で対象外。
- `--send` だけでは送られず、`PUBLISH_NOTICE_EMAIL_ENABLED=1` か `--send-enabled` が必要。
- default は dry-run で bridge 非実行。
- body text は 5 行固定。
- 24 時間以内の再検知では再送しない。
