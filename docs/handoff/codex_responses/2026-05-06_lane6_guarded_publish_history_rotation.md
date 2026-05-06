# Lane 6: guarded_publish_history.jsonl rotation 設計 (doc-only)

作成日: 2026-05-06
作成者: Claude Code 直接
スコープ: doc-only (実装 / deploy / GCS mutation 全なし)

## 1. 現状

### 1-1. file size と entry 数
- `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
- **97.32 MiB / 284,313 entries** (2026-05-06 取得)
- daily growth 推定: 1日あたり数千〜1万 entries (Scheduler */5 で guarded-publish 12 cycle/h × 24h × 平均 30 entries/cycle)

### 1-2. entry 構造
```
{"post_id": ..., "ts": "<ISO>", "status": ..., "backup_path": ...,
 "error": ..., "judgment": ..., "publishable": ..., "cleanup_required": ...,
 "cleanup_success": ..., "hold_reason": ...}
```

### 1-3. 利用箇所 (publish_notice_scanner.py, scan_guarded_publish_history)
- 毎 cycle (5min) GCS から `/tmp/pub004d/guarded_publish_history.jsonl` へ download
- cursor (`guarded_publish_history_cursor.txt`) で scan 開始位置を保持
- cursor 以降の line を順次 parse、freshness 判定 / review notification emit
- 終了時 GCS へ upload (cleanup_log.jsonl と yellow_log.jsonl と同様)

### 1-4. cost 影響
- GCS download/upload 帯域 (97 MiB × 12 cycle/h × 24h ≈ 28 GiB/day)
- /tmp 一時 file 書込み I/O
- subprocess `gcloud storage cp` で download/upload 5-10s/file
- scan 自体の CPU は cursor 進めながらの line-by-line で軽量だが、file load が線形

### 1-5. cursor 仕組み
- `guarded_publish_history_cursor.txt` に最終処理 timestamp / line offset を保持
- 起動時 cursor 以降を scan、scan 完了後に cursor 更新
- cursor は GCS の `gs://baseballsite-yoshilover-state/publish_notice/guarded_publish_history_cursor.txt` で persist

## 2. rotation 戦略候補

### 2-A. 案 A: 日次 rotation + N 日 retention (推奨)

**file 構造**:
```
guarded_publish/
├── guarded_publish_history.jsonl                  # current (今日分のみ、自動 rotate)
├── archive/
│   ├── guarded_publish_history-2026-04-29.jsonl
│   ├── guarded_publish_history-2026-04-30.jsonl
│   ├── ...
│   └── guarded_publish_history-2026-05-05.jsonl  (前日まで)
```

**rotation 動作**:
- guarded-publish job が JST 0:00 起動時 (or 専用 rotation job 起動時)、現 file を `archive/<date>.jsonl` へ move
- current `guarded_publish_history.jsonl` は新規 (空) で開始
- archive は読み取り専用、scanner は通常 current のみ scan

**retention**:
- archive の自動削除なし、user 手動 or 別 ticket で月次削除
- もし自動なら: 90日 (3ヶ月) で削除、Lane 7 cost guard alarm と組合せ

**長所**:
- current 軽量 (1日分 = 数 MiB)
- scanner side 変更最小 (archive は scan しない、current だけ)
- cursor 互換性: 日次 rotation 時に cursor を初期化 (rollover marker で Daily reset)
- backup を archive で保証 (user 手動 audit 可)

**短所**:
- 日次 rotation 自体の implementation が必要 (新 cron job or guarded-publish 起動時 trigger)
- cursor 初期化と past-day 重複 emit 防止のため history_cursor の semantics 拡張必要 (日付 + offset)

### 2-B. 案 B: tail-only 7日 retention (シンプル)

**動作**:
- 起動時、history.jsonl から `ts >= now - 7 days` の entry のみ keep、それ以前は drop
- 古い entry は GCS で `archive/yyyy-mm.jsonl` (月次) へ move (任意)

**file 構造**:
```
guarded_publish/
├── guarded_publish_history.jsonl                  # 直近 7 日のみ (~14-20 MiB)
└── archive/                                        # 任意、cost 監視用
    └── ...
```

**長所**:
- 単純 (cron で head/tail 操作)
- scanner / cursor の semantics 不変
- 7 日分で probably ~15-25 MiB、80% size 削減

**短所**:
- cursor が retention 境界を跨ぐ時 (例: 8日前を指す古い cursor) に scan 開始位置不明、scanner 側 fallback 必要
- archive 自動化が別途必要 (user 手動 audit cost)

### 2-C. 案 C: in-place 圧縮 + retention (最小工事)

**動作**:
- gzip 圧縮で file size 1/5 〜 1/10 (jsonl 圧縮率高い)
- `guarded_publish_history.jsonl.gz` を scanner 側で zcat / gzip module で読む
- 14日 retention で in-place trim

**長所**:
- file size 直接削減 (~10 MiB target)
- archive 構造変えない

**短所**:
- scanner / publish-notice 全 file の I/O path 変更必要 (gzip module 追加)
- 圧縮 / 解凍 overhead で CPU 増 (cycle あたり ~1-2s)
- gcloud storage cp は gzip 知らないので transparent decompression 不可

## 3. 推奨案

**A 案 + B 案ハイブリッド**:
1. **Phase 1 (本セッション内、doc-only)**: 設計確定のみ、実装なし
2. **Phase 2 (別 ticket)**: B 案 (7-14 日 tail retention) で即削減
   - guarded-publish 起動時に `ts < now - 14days` を drop、archive へ append
   - cursor 互換: cursor が 14 日前を指してたら head に reset (publish-notice 起動時 fall-back)
   - Phase 2 で 97 MiB → ~15-20 MiB を達成
3. **Phase 3 (将来)**: A 案 (日次 rotation) で current/archive 完全分離
   - JST 0:00 rotation job
   - current は ~5 MiB / day で運用
   - archive は 30-90 日保持

## 4. 実装案 (Phase 2 = 即効 retention)

### 4-1. 変更対象 file
- `src/guarded_publish_runner.py` (起動 / 終了時の history file maintenance に retention logic 追加)
- `src/publish_notice_scanner.py` (cursor が retention 境界を跨ぐ場合の fallback)
- `src/cloud_run_persistence.py` (GCS sync 前後の trim 処理任意)
- 新 env: `ENABLE_GUARDED_PUBLISH_HISTORY_RETENTION` (default OFF)
- 新 env: `GUARDED_PUBLISH_HISTORY_RETENTION_DAYS` (default 14)
- 新 fixture: `tests/test_guarded_publish_history_retention.py`

### 4-2. retention logic 概要
```python
# guarded_publish_runner.py 起動時 (initialize_history)
if _enable_retention():
    cutoff = now - timedelta(days=_retention_days())
    keep, drop = partition_by_ts(history_lines, cutoff)
    if drop:
        archive_append("archive/yyyy-mm.jsonl", drop)  # 月次 archive
        history_lines = keep
        history_save(history_lines)
```

### 4-3. cursor fallback (publish-notice 側)
```python
# publish_notice_scanner.py scan_guarded_publish_history 起動時
cursor_value = read_cursor()
if cursor_value < oldest_ts(history):
    cursor_value = oldest_ts(history)  # head に jump
    log("cursor_reset_to_head: cursor was older than retention window")
```

## 5. cursor 互換性 / rollback

### 5-1. cursor 互換性
- 現 cursor format: timestamp string (or line offset)
- retention 適用後、cursor が retention window より古い場合: head に reset (上記 4-3)
- entry 重複 emit 防止: history_cursor + duplicate guard (既存 ENABLE_REPLAY_WINDOW_DEDUP=1) で 5min window 重複検出
- replay window dedup は既に LIVE_APPLIED 状態 (Lane FF / `4231805` image)

### 5-2. rollback 手順
- env flag `ENABLE_GUARDED_PUBLISH_HISTORY_RETENTION=0` に戻す (1 コマンド)
- archive から history へ append し直し: `gsutil cat archive/*.jsonl > guarded_publish_history.jsonl`
- (ただし retention 適用後は古い entry を削除するため、完全 restore は archive 必須)
- 安全策: archive 削除しない、retention は append-to-archive + drop-from-current

### 5-3. fail-safe
- retention drop 数が 1 cycle で 1000+ なら異常 (warning log + skip drop、要 audit)
- archive write 失敗時は drop 中止 (history 継続使用)

## 6. cost 削減見込み (Phase 2 後)

| 項目 | 現 | Phase 2 後 |
|---|---|---|
| `guarded_publish_history.jsonl` size | 97 MiB | ~15 MiB (84% 削減) |
| GCS download/upload daily | ~28 GiB | ~4 GiB (86% 削減) |
| scan time per cycle | ~10-15s | ~2-3s (80% 削減) |
| Archive cost (月次) | 無し | ~10 MiB/month archive (negligible) |

## 7. 不可触 / 制約

- 本 doc は doc-only、code/config/GCS 一切変更しない
- 実装は別 ticket、本セッションでは触らない
- guarded_publish_history の **既存 entry 削除は一切行わない** (本セッション内)
- archive 設計は将来別 ticket で扱う

## 8. 関連 commit / 文書
- P0 publish-notice two-phase: `bf29bcc` (本日 deploy 予定、scan 重さの一次原因の direct phase 分離)
- Lane 7 cost guard: `2026-05-06_lane7_cloud_run_cost_guard.md` (同日)
- 既存 cleanup ledger 設計: `Lane FF / BUG-004+291 replay-window dedup`

## 9. next_judgment
- doc-only commit + push のみ
- 実装 (Phase 2) は別 ticket、user 明示 GO 後に着手
