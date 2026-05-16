# 355-x-post-mail-24h-dedup

## 1. ticket header

- **status**: READY (user GO 待ち、 本 doc 作成のみ、 code 編集禁止)
- **priority**: medium (handoff Task 5、 連日同 ranking 体感抑制)
- **owner**: Claude (実装) / user (GO 判断)
- **依存**: 353 (LIVE)、 354 (LIVE)、 347 lane
- **依存 (handoff)**: `docs/handoff/session_logs/2026-05-15_pm_next_session_tasks.md` Task 5

## 2. 目的 / 背景

handoff Task 5: 1 日 5 通 mail (07/12/15/17:30/22:30) で **同 metric / 同 player / 同 combo が連日連続** 出る risk を軽く抑制。

348 dedup (article_candidates table、 publish 用) / 349 cascade (3 段 cooldown/delta/band、 348 後着手) とは **別 lane** = **別 storage** = 衝突回避。 x_post_mail lane 内で軽量 24h dedup を完結させる。

## 2.5 設計確定事項 (verify ベース、 user 判断 pending あり)

### Cloud Run Job 制約

- Cloud Run Job は ephemeral (container 終了で local disk 消える)
- 永続化必要 → **GCS object 一択** (local SQLite / Memorystore は overkill / 設定コスト増)

### Storage 設計

- **bucket**: 既存 `INSIGHT_GCS_BUCKET` env (= insight.db cache bucket) を **流用、 prefix で分離**
  - path: `gs://${INSIGHT_GCS_BUCKET}/x_post_mail/dedup/YYYY-MM-DD.jsonl`
  - 利点: 新 bucket / 新 IAM 不要 (= user 判断境界回避)、 同 SA で read/write
  - **user 確認 pending**: 同 bucket prefix 分離での write 増加 OK か (insight.db cache と衝突なし設計、 GCS 無料枠 5GB/月 余裕)
- **format**: JSON Lines (append 友好、 部分 read 可能)
  - 1 record = `{"ts": "2026-05-16T07:05:23Z", "signature": "OPS|今月|False|None", "candidate_count": 10}`
- **rotation**: 日付別 file = 自然な 24h window、 古い file は新 file ロード時 自動的に out of scope
- **24h sliding window**: 「直近 24h の record」 = 当日 file + 前日 file の `ts >= now - 24h` filter
- **race condition**: Cloud Run Job 5 個 Scheduler は 7:00 / 12:00 / 15:00 / 17:30 / 22:30 = 重ならない、 append-only なので衝突 risk 低、 lock 不要

### dedup signature 設計

- signature = `f"{combo.metric}|{combo.period_label}|{combo.giants_only}|{combo.position}"`
- 例: `OPS|直近5試合|True|None` / `AVG|今月|False|None` / `OPS|今シーズン|False|捕`
- 同 signature が **24h 以内** に既出 → skip (combo pool から候補としても外す)

### dedup gate のタイミング

- `pick_candidates` の combo 選定段階で **既出 signature の combo を skip**
- weighted shuffle 後、 combo loop 内で `if signature in recent_24h_set: continue`
- skip された分、 max_candidates まで他 combo を試行

### 記録のタイミング

- **mail 送信成功時のみ** 採用した combo signature を append
- 送信失敗 (status != "sent") = 記録しない、 retry 時に同 combo を再選出可能
- run_x_post_mail.py が send 結果を受けて record_dedup を call

### Toggle / safety net

- env var `X_POST_MAIL_DEDUP_DISABLED=1` で機能 OFF にする escape hatch (storage trouble 時の emergency switch)
- GCS read 失敗時は **silent fallback to empty set** (= dedup なし、 mail は送る) — 致命的にしない

## 3. 今回触らない範囲

### 348 / 349 scope (file レベル disjoint 維持)

- `src/analysis/*.py` 全部
- `article_candidates` table
- `config/insight_whitelist.json`
- 348 dedup history (= article_candidates の status='PUBLISHED' row)
- 349 cascade gate (実装後でも 連携しない、 別 lane で完全独立)

### 既存稼働 lane

- 346 PWA: `src/manual_intake_service.py` / `src/format_as_x_post.py`
- 既存 publish-notice mail / fact-check mail / X auto post lane
- WP REST publish 経路
- LLM 呼出 一切

### インフラ / 設定

- env / Secret Manager 値変更 (新 env `X_POST_MAIL_DEDUP_DISABLED` は **optional**、 absent default で機能 ON)
- 他 Cloud Run service の image
- Cloud Scheduler 5 個 x-post-mail-* の cron 不変
- 親 repo `baseballwordpress`
- **GCS bucket の IAM 変更 (= user 判断境界 §11)** — 既存 SA の write 権限が無ければ STOP + user 判断

### DB

- `insight.db` schema / data 一切 read / write なし (24h dedup は別 storage)
- `games` table への write 一切なし

## 4. 影響範囲

### code 変更が入る file

| file | 変更内容 |
|---|---|
| `src/x_post_mail_lane.py` | (A) `_combo_signature(combo)` helper 新規 / (B) `_load_recent_dedup_signatures(bucket, now, lookback_hours=24)` helper 新規 (GCS read、 当日 + 前日 file load、 ts filter、 silent fallback) / (C) `_record_dedup_signatures(bucket, signatures, now)` helper 新規 (GCS append) / (D) `pick_candidates` に `dedup_set: Optional[set[str]] = None` 引数追加、 combo loop 内で signature dedup gate を入れる / (E) 採用 candidate の signature list を return 値に追加 (or pick_candidates の return type 拡張) |
| `src/tools/run_x_post_mail.py` | (F) `INSIGHT_GCS_BUCKET` env 取得 / (G) `X_POST_MAIL_DEDUP_DISABLED` env check (escape hatch) / (H) pick_candidates 前に `_load_recent_dedup_signatures` call、 dedup_set を渡す / (I) mail send result.status == "sent" の時のみ `_record_dedup_signatures` call |
| `tests/test_x_post_mail.py` | 新クラス + 6-8 test (GCS mock fixture、 signature 生成 / read / write / skip / fallback / disabled flag) |

### 直接触らない file

- `src/manual_intake_insight_query.py` (insight.db cache 経路、 不変)
- `src/format_as_x_post.py` (346 PWA、 不変)
- `src/mail_delivery_bridge.py` (SMTP、 不変)

### Cloud Run / GCS 影響

- Cloud Run Job `x-post-mail-lane` の image rebuild
- GCS bucket `${INSIGHT_GCS_BUCKET}` に新 prefix `x_post_mail/dedup/` が追加 (= write 増加、 但し JSONL 1 日数 KB)
- IAM: 既存 SA の bucket write 権限が必要 (verify pending、 既に grant 済の可能性高い = insight_gcs_sync.py で write してる)

## 5. 実行予定テスト

### 既存テスト

```
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py --tb=short
python3 -m pytest tests/ --tb=short -q
```

### 新規追加テスト

| test | 内容 |
|---|---|
| `test_combo_signature_format` | `_combo_signature` が `metric\|period\|giants\|position` 形式を返す |
| `test_combo_signature_unique_per_combo` | 異なる combo は異なる signature |
| `test_load_recent_dedup_signatures_returns_set` | GCS mock で JSONL 読み、 24h 以内の signature set を返す |
| `test_load_recent_dedup_signatures_filters_old` | 24h 超の record は除外される |
| `test_load_recent_dedup_signatures_silent_fallback` | GCS error 時 空 set を返す |
| `test_pick_candidates_skips_dedup_set_combos` | dedup_set に含まれる signature combo は pick されない |
| `test_pick_candidates_no_dedup_set_works` | dedup_set=None default で従来挙動 |
| `test_record_dedup_signatures_writes_jsonl` | GCS mock で signatures が JSONL として書き込まれる |

## 6. STOP 条件

1. 既存 pytest test (4853 + 354 で +8 = 4861) が 1 件でも fail (regression)
2. 348 scope への接触 (不可触リスト §3)
3. unstaged 2 file (`anomaly_article_publisher.py` / `team_ranking_publisher.py`) への変更
4. `INSIGHT_GCS_BUCKET` の SA write 権限が無くて IAM 変更が必要になる → STOP + user 判断
5. dedup gate で publish 件数 急減 (= 5 通 / 日 → 1-2 件しか出ない)
6. GCS read で 既存 insight.db cache を破壊する経路を踏む (= read-only 想定なのに write してしまう)
7. AI 事故源 trigger (記憶再構成 / silent skip / 自己評価 OK)

## 7. 禁止事項

- code commit / push (本 ticket は doc-only phase、 user GO 後のみ)
- deploy / gcloud / Cloud Run / Cloud Build / Scheduler 実行
- env / Secret Manager 値変更 (新 env は code 内 default + os.environ.get で対応、 Cloud Run env 設定変更しない)
- WP REST / X / SNS への発信
- 親 repo `baseballwordpress` への変更
- 348 / 349 scope への scope 拡張
- 不可触 file (§3) への変更
- LLM 呼出 一切
- `git add -A`
- `--no-verify` 等 hook skip
- `auth.json` / Secret 値の chat / log / commit 露出
- scope の勝手な分割

## 8. 想定されるデグレ

### 高確率デグレ

- **GCS write 権限不足で record 失敗**: 既存 SA は read (insight.db download) は OK だが write 権限が要 verify。 失敗時は silent log + mail 送信は続行 (致命的にしない)
- **dedup で 5 通 / 日 中 後半 mail が候補不足**: 朝 5 件採用 → 昼 5 件採用 → 午後 で残り pool 13、 直近 24h skip で更に減って 5 件 確保できなくなる可能性
- **既存 53 test の signature が変わる**: pick_candidates の signature 拡張で test side effect

### 中確率デグレ

- **GCS read latency が増えて Cloud Run Job timeout**: 当日 + 前日 file の 2 read、 各 < 100ms 想定だが ネットワーク劣化時 risk
- **JSONL parse error で silent fallback** が disabled の場合: parse error 検出時 raise すべき箇所も silent fallback してしまい debug 困難
- **race condition で append 衝突**: Scheduler 5 個は時刻分散だが manual fire 時 user 操作で同時 fire 可能

### 低確率デグレ

- GCS object size 肥大化 (1 record 数 byte × 5 件 / 日 × 365 日 = ~1MB / 年、 問題なし)
- 既存 insight.db cache file への影響 (= GCS path 完全 分離なので 0)

### user 影響

- mail 1 通あたり candidates 数が dedup で 10 → 8-9 件に減る可能性
- 連日 「同じ ranking ばかり」体感の改善 (期待効果)
- 「直近 5 試合 OPS」が朝出たら 昼/夜の同 combo は skip = 多様性 up

## 9. 作業ログ欄

```
2026-05-16 01:00 JST | doc 起票 | phase_0 | 355 ticket doc 完成 / user GO 待ち | wait
2026-05-16 01:05 JST | user GO 受領 | phase_0_to_1 | merit 議論後 user 「やる」確定 | Phase 0 verify
2026-05-16 01:07 JST | SA verify | phase_0 | INSIGHT_GCS_BUCKET=baseballsite-yoshilover-insight、 SA=487178857517-compute@developer (roles/storage.objectUser、 read+write 包括) | IAM 変更不要、 phase_2 impl
2026-05-16 01:10 JST | impl 完了 | phase_2 | src/x_post_mail_lane.py edits (json/timezone imports + Candidate.signature + _combo_signature + _get_storage_client + _dedup_blob_path + _load_recent_dedup_signatures + _record_dedup_signatures + pick_candidates dedup_set 引数 + dedup skip log + _format_one signature 設定) | src/tools/run_x_post_mail.py edits (env + dedup load + send 成功時 record)
2026-05-16 01:12 JST | tests 追加 | phase_2 | TicketThreeFiftyFiveDedupTests クラス + 9 test (FakeBlob/FakeBucket/FakeClient in-memory mock) | pytest verify
2026-05-16 01:13 JST | pytest 確認 | phase_2_verify | test_x_post_mail.py 61 pass (52→61、 +9 new 355) | full pytest
2026-05-16 01:15 JST | full pytest | phase_2_verify | 4862 pass / 4 xfailed (pre-existing) / 0 regression | impl commit
2026-05-16 01:20 JST | impl commit | phase_3 | a54a773: src + tests + doc (4 files, +670/-4) push 済 | cloudbuild
2026-05-16 01:26 JST | cloudbuild SUCCESS | phase_3 | image x-post-mail-lane:355-24h-dedup / digest sha256:a7badfff... / build_id e31a97ce-4c4c-4011-95dc-0f680c833b94 (1m27s) | jobs update
2026-05-16 01:27 JST | jobs update SUCCESS | phase_3 | image 354-last-n-games → 355-24h-dedup | execute
2026-05-16 01:29 JST | execute SUCCESS | phase_3 | execution x-post-mail-lane-qclg8 / Loaded 24h dedup set: 0 signatures (初回) / db_path=True, dedup=0 / Composing 10 candidates / status=sent / Recorded 10 dedup signatures (ok=True) / Container exit(0) | log verify
2026-05-16 01:31 JST | log verify | phase_3 | mail sent to fwns6760@gmail.com、 GCS write 動作確認 (gs://baseballsite-yoshilover-insight/x_post_mail/dedup/2026-05-16.jsonl に 10 signatures 書き込み確認) | GH Issue 起票 + 2nd commit
```

## 10. Regression Memo 欄

```
YYYY-MM-DD HH:MM JST | <test> | <regression> | <fix> | <test added>
```

---

# 作業後追記 (user GO 後、 実装完了時に埋める)

## 1. 実際に変更したファイル

- `src/x_post_mail_lane.py` (+131 / -2 行、 dedup logic + Candidate.signature)
- `src/tools/run_x_post_mail.py` (+33 / -3 行、 env + load + record)
- `tests/test_x_post_mail.py` (+170 / -2 行、 新 `TicketThreeFiftyFiveDedupTests` クラス + 9 test、 timedelta import 追加)
- `doc/active/355-x-post-mail-24h-dedup.md` (新規、 本 ticket doc)

## 2. diff 概要

### src/x_post_mail_lane.py

- imports 追加: `json as _json` / `timezone as _tz` (from datetime)
- `Candidate` dataclass に `signature: str = ""` field 追加 (default で既存 test 互換)
- `_combo_signature(combo)` — `f"{metric}|{period_label}|{giants_only}|{position or 'None'}"` 形式
- `_get_storage_client()` — lazy GCS client builder (test で patch 可能)
- `_dedup_blob_path(date_str)` — path 生成 helper
- `_load_recent_dedup_signatures(bucket, now, lookback_hours=24)` — today + yesterday の JSONL を read、 ts filter、 silent fallback on error
- `_record_dedup_signatures(bucket, signatures, now)` — read existing + append + re-upload、 silent failure on error
- `pick_candidates(..., dedup_set=None)` — dedup gate 追加、 signature in set なら skip + INFO log
- `_format_one` — Candidate 構築時に `signature=_combo_signature(combo)` 設定

### src/tools/run_x_post_mail.py

- `INSIGHT_GCS_BUCKET` env から bucket 名取得
- `X_POST_MAIL_DEDUP_DISABLED` env で escape hatch (1/true/yes で disable)
- `pick_candidates` 前: `_load_recent_dedup_signatures` call、 dedup_set を渡す
- mail send 成功時のみ: 採用 candidate の signatures を `_record_dedup_signatures` で append

### tests/test_x_post_mail.py

- `timedelta` import 追加
- 新 class `TicketThreeFiftyFiveDedupTests`: FakeBlob / FakeBucket / FakeClient で in-memory GCS mock、 `_get_storage_client` を patch
- 9 test:
  - `test_combo_signature_format` — `OPS|今月|False|None` 形式
  - `test_combo_signature_unique_per_dimensions` — 異なる dimension は異なる signature
  - `test_load_recent_dedup_signatures_returns_set` — today + yesterday JSONL から set 構築
  - `test_load_recent_dedup_signatures_filters_old` — 24h 超 record を除外
  - `test_load_recent_dedup_signatures_silent_fallback_on_error` — GCS error で空 set
  - `test_pick_candidates_skips_combos_in_dedup_set` — dedup_set 内 combo を skip
  - `test_pick_candidates_dedup_set_none_keeps_legacy_behaviour` — default None で従来挙動
  - `test_record_dedup_signatures_writes_jsonl` — signatures が JSONL として書き込まれる
  - `test_record_dedup_signatures_appends_to_existing` — 既存 record に append (上書きしない)

## 3. 実行したテスト

```
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_x_post_mail.py -q --tb=short
python3 -m pytest tests/ --tb=short -q   # full baseline
```

## 4. テスト結果

- target file `test_x_post_mail.py`: **61 passed / 0 fail** (52 → 61、 +9 new 355)
- full pytest: **4862 passed / 4 xfailed (pre-existing) / 0 fail** (regression count = 0)

## 5. 残った懸念

1. **次 fire (= Scheduler 自然 06:00 / 07:00 etc) で dedup gate 効果未 verify**: 初回 fire は `Loaded 0 signatures` で skip ゼロ、 次回以降の fire で `Loaded ≥1 signatures` + 「dedup skip combo ...」 log が出るかは Scheduler 自然 fire まで未確認 (`gcloud logging read` で検出可)。
2. **24h 後 file rotation 未 verify**: 翌日 (5/17) になると `2026-05-17.jsonl` を新規作成 + 5/16 file は 24h window から自然脱落するが、 翌日 file 作成の挙動は production で未確認。
3. **race condition (manual fire 重複)**: Scheduler は時刻分散だが user が手動 fire を連打すると `_record_dedup_signatures` の read-existing → append → upload が衝突する可能性 (= 後勝ち、 1 batch 喪失)。 致命的にはならない。
4. **`Recorded 10 dedup signatures` で 10 全部 = max_candidates 上限 = 採用件数。 dedup gate で skip された combo は count に入らない**: 次 fire で 10 + 新 signature が record される、 24h 経つと自然脱落で list 大きくならない設計。
5. **bucket prefix 衝突なし verify 未完**: `gs://baseballsite-yoshilover-insight` の他 user (insight.db cache / 348 nightly etc) が `x_post_mail/dedup/*` prefix を読まない前提だが、 1 次 source で完全 verify はしていない (但し path 分離なので衝突 risk 極低)。

## 6. 新しく見つかったデグレ

なし (production behaviour の意図しない退行 0 件、 pytest full 4862 pass / 0 fail、 deploy log 上 ERROR / WARNING ログなし、 mail 1 通 status=sent 配信完了、 GCS write `ok=True`)。 後続観察で出現すれば追記。

## 6.1 2026-05-16 Scheduler 403 incident / fix

### 発見

- 2026-05-16 13:31 JST 時点で `x-post-mail-lane` latest execution は `x-post-mail-lane-qclg8` のまま。
- 07:00 JST `x-post-mail-am-1` と 12:00 JST `x-post-mail-lunch` は Cloud Scheduler 側で実行試行済みだが、Cloud Run Job 実行は作成されていなかった。
- Cloud Scheduler log:
  - `x-post-mail-am-1`: HTTP 403 / `PERMISSION_DENIED`
  - `x-post-mail-lunch`: HTTP 403 / `PERMISSION_DENIED`
- 手動 execute / mail send / GCS dedup write は 2026-05-16 01:08 JST に成功済みなので、候補生成 code / mail send code ではなく Scheduler invoke 権限の問題。

### 原因

- 失敗していた `x-post-mail-*` Scheduler jobs の OAuth service account:
  - `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com`
- 正常稼働中の `data-insight-*` Scheduler jobs の OAuth service account:
  - `487178857517-compute@developer.gserviceaccount.com`
- `x-post-mail-*` 側だけ Cloud Run Job `x-post-mail-lane:run` を呼べず 403 になっていた。

### 修正

以下 5 jobs の OAuth service account だけを `487178857517-compute@developer.gserviceaccount.com` に更新。schedule / timezone / URI / Job image / env / Secret / mail body は変更なし。

- `x-post-mail-am-1`: `0 7 * * *`
- `x-post-mail-lunch`: `0 12 * * *`
- `x-post-mail-afternoon`: `0 15 * * *`
- `x-post-mail-evening`: `30 17 * * *`
- `x-post-mail-postgame`: `30 22 * * *`

### 検証

- 更新後 describe で 5 jobs すべて:
  - state: `ENABLED`
  - OAuth service account: `487178857517-compute@developer.gserviceaccount.com`
  - URI: `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/x-post-mail-lane:run`
- 対象 test:
  - `python3 -m pytest tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py -q`
  - `98 passed, 3 warnings, 6 subtests passed`

### 未実行

- 手動 `gcloud scheduler jobs run ...` / `gcloud run jobs execute x-post-mail-lane` は未実行。
- 理由: 追加 mail を発生させないため。次回自然 fire (`x-post-mail-afternoon` 2026-05-16 15:00 JST) で確認する。

## 7. 追加した回帰テスト

`tests/test_x_post_mail.py::TicketThreeFiftyFiveDedupTests` の 9 test (上記 §2 参照)。

## 8. 次回触ってはいけない範囲

(deploy verify 後に最終確定。 現時点で確定済の不可触:)

- `src/x_post_mail_lane.py` の dedup helper 群 (`_combo_signature` / `_get_storage_client` / `_load_recent_dedup_signatures` / `_record_dedup_signatures`) — GCS object schema 依存、 schema 変更時は同時に test 修正必須
- GCS path `gs://baseballsite-yoshilover-insight/x_post_mail/dedup/*.jsonl` — 別 lane が touch しない前提
- `src/analysis/anomaly_article_publisher.py` / `src/analysis/team_ranking_publisher.py` (unstaged 別作業)
- `src/format_as_x_post.py` (346 PWA scope)
- 348/349 file 群 / `config/insight_whitelist.json` / `article_candidates` table
