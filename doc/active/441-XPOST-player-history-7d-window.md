# 441 XPOST player history window 24h → 168h (7d) + relaxed fallback 削除

## 1. ticket header

- **ticket id**: 441
- **status**: REPO_IMPL_TESTED
- **owner**: Claude
- **lane**: Claude (CLAUDE.md §3 2026-05-12 全権 lock)
- **created**: 2026-05-28
- **priority**: P1
- **github_issue**: pending
- **parent**: 380 (player diversity cap) / 436 (top10 diversity)

## 2. purpose

X-post mail で大城 / マルティネスなど規定打席を満たすレギュラーが「ほぼ毎 mail」 露出する症状を構造的に止める。

24h rolling window では「昨日同時刻に出た player は今日同時刻に復活」できる構造的バグ。 加えて `_load_recent_dedup_records` が today + yesterday の 2 日分しか blob 読まないので、 実効 lookback は最大 ~48h で頭打ち。

## 3. user requirements captured

- 2026-05-28 user 「大城、 マルティネスなどかなりデル」 + 推奨案 (window 24h → 7d + relaxed fallback 削除) に対して 「それにする」
- 既存方針 (memory `feedback_data_insight_user_preferences_2026_05_15` + 436 follow-up): 「少なくてもよいが、 同じ選手連発は避ける」

## 4. scope

### 4.1 lookback window 拡張

- `src/x_post_mail_lane.py`:
  - `_load_recent_dedup_records` default 24 → 168
  - `_load_recent_dedup_signatures` default 24 → 168
  - `_load_recent_player_counts` default 24 → 168
  - blob 読込 loop を `today + yesterday` 2 日固定から、 `ceil(lookback_hours/24) + 1` 日分に拡張
- `src/tools/run_x_post_mail.py`:
  - `X_POST_MAIL_PLAYER_HISTORY_HOURS` env var を新規追加 (default 168, min 1)
  - `_load_recent_dedup_records` 呼出に `lookback_hours=history_hours` を渡す
  - log message に hours を可変表示

### 4.2 relaxed history fallback 削除

- `src/tools/run_x_post_mail.py:1665-1690` の `if not candidates and recent_player_counts:` block を削除し、 0 件のままなら mail skip に変更
- 削除根拠: user 方針「少なくてよいから連発回避優先」(memory + 436 follow-up 21:20 と同方針)

### 4.3 維持する fallback

- `dedup_set` (combo signature) が候補数を割る場合の relaxed retry は **維持** (`run_x_post_mail.py:1455-1479`)
  - 理由: この path は `recent_player_counts` を引き続き渡すので player history は失われない、 combo signature だけを relax する path
- `fan_voice_pool_entries` の 24h lookback は **触らない** (別 concern)

## 5. do not touch

- env / Secret / Scheduler / WP / X live post
- 436 surprise score 設計 (別 ticket で実装)
- 434 anomaly flag-only (別 ticket)
- player_cap (= 1 / mail) は維持

## 6. acceptance criteria

- targeted test `python3 -m pytest tests/test_x_post_mail.py -q -k "dedup or history or fallback or recent_player or skip"` green
- broader test `python3 -m pytest tests/test_x_post_mail.py -q` green
- env var `X_POST_MAIL_PLAYER_HISTORY_HOURS` で window 上書き可能、 default 168
- 0 candidate 時に mail skip (旧 relaxed retry path 廃止)
- `_load_recent_dedup_records` が 7d 分の blob を読む

## 7. test coverage

修正済 test:
- `test_load_recent_dedup_signatures_filters_old`: 30h → 200h old に変更、 別日 blob で store
- `test_player_history_zero_candidate_relaxes_as_last_resort` → `test_player_history_zero_candidate_skips_mail` rename、 旧 relaxed retry を skip 動作に書換

verification:
- `python3 -m py_compile`: OK
- targeted (35 tests): all green
- full `tests/test_x_post_mail.py` (134 tests): all green

## 8. rollback

env で `X_POST_MAIL_PLAYER_HISTORY_HOURS=24` を Cloud Run Job に設定すれば旧挙動に戻る (default だけが 168 になっている)。 relaxed fallback 削除部分は code revert 必要。

## 9. work log

- 2026-05-28 JST: user 「大城、 マルティネスなどかなりデル」 → grep audit で root cause 特定 (24h window + 2 日 blob 制約 + relaxed fallback 3 重)。 推奨 1 案 GO 取得、 着手。
- 2026-05-28 JST: 実装 + test 修正、 broader run 134 passed。 commit 待ち。
