# P1-mail-storm-hotfix-verify

## 1. Read-only verification

### 1.1 Access result for this run

This run could not complete the requested `gcloud` / `gsutil` readback because `gcloud` auth access failed before log reads started.

Failed command:

```bash
gcloud auth list --filter=status:ACTIVE --format='value(account)'
```

Observed error:

```text
WARNING: Could not setup log file in /home/fwns6/.config/gcloud/logs, (OSError: [Errno 30] Read-only file system: '/home/fwns6/.config/gcloud/logs/2026.05.01/09.44.06.305605.log'
ERROR: (gcloud.auth.list) Unable to create private file [/home/fwns6/.config/gcloud/credentials.db]: [Errno 30] Read-only file system: '/home/fwns6/.config/gcloud/credentials.db'
```

Per instruction, cloud reads were stopped after this failure. No further `gcloud logging read`, `gcloud run jobs describe`, or `gsutil cat` commands were executed in this run.

### 1.2 Requested cloud observations

Because the run stopped at `gcloud` auth, the following fields are `unknown - needs additional read access`:

| item | result |
|---|---|
| 5+ publish-notice trigger summaries from 2026-05-01 00:00:00 UTC onward | unknown - needs additional read access |
| Per-trigger `sent` / `suppressed` / `errors` / distinct emitted `post_id` count and range | unknown - needs additional read access |
| Presence of `REVIEW_RECENT_DUPLICATE` skip lines in cloud logs | unknown - needs additional read access |
| `publish-notice` job env live readback | unknown - needs additional read access |
| 289 `post_gen_validate` emit count, past 24h vs prior 24h | unknown - needs additional read access |

### 1.3 Gemini call delta

Result: `delta indeterminate`.

What should be searched once authenticated read access is available:

- resource filter:
  - `resource.type="cloud_run_revision"`
  - `resource.labels.service_name="yoshilover-fetcher"`
- comparison windows:
  - past 1h
  - prior 1h baseline
- text terms:
  - `gemini`
  - `GEMINI`
  - `google.genai`
  - `Gemini API`

No cloud log counts were obtained in this run.

### 1.4 Live env state requested by ticket

Requested verification target:

- `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org`
- `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1`
- `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS` absent

Result in this run: `unknown - needs additional read access`.

### 1.5 Established facts carried into this run

These are not newly verified here; they were provided as established context before this run:

- `2026-05-01 00:00 UTC`: `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` was applied on `publish-notice`.
- `00:05..00:30 UTC`: `publish-notice` `*/5` trigger sent `10` every run.
- `00:33 UTC`: env removed with `--remove-env-vars=PUBLISH_NOTICE_REVIEW_WINDOW_HOURS`.
- `00:35:57 UTC`: trigger still sent `10`; subject prefix `【要確認(古い候補)】`; `hold_reason=backlog_only`; `post_id` range `63186..63311`.
- `guarded_publish_history.jsonl` tail sample showed about `103` unique `post_id` values, each re-appended twice at `09:30:45 JST` and `09:35:47 JST`, all `status=skipped`, `judgment=yellow`, `hold_reason=backlog_only`.

### 1.6 Local code verification used for prediction and hotfix design

Read-only repo checks confirm the following:

- `src/publish_notice_scanner.py`
  - `_HISTORY_WINDOW = timedelta(hours=24)` for publish-notice post-id dedup.
  - `_REVIEW_NOTICE_WINDOW_HOURS_DEFAULT = 24.0`.
  - `_resolve_review_window_hours()` reads `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS`.
  - `_guarded_publish_subject_prefix()` maps `hold_reason == "backlog_only"` to `【要確認(古い候補)】`.
  - `scan_guarded_publish_history()` emits review notices from guarded ledger rows unless filtered or deduped.
- `scan()` behavior matters for hotfix choice:
  - guarded review notices run first.
  - `post_gen_validate` uses `remaining_review_cap = max(0, review_max - len(review_scan.emitted))`.
  - therefore `PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=0` would also suppress 289 `post_gen_validate`, and should not be used for this incident.

## 2. 24h cycle prediction

Prediction: `yes, recurrence is likely after the 24h dedup window expires`.

Reasoning:

- `publish-notice` dedups by `post_id` for 24h.
- `guarded-publish` appears to keep re-appending fresh `backlog_only` rows for the same backlog posts every `*/5`.
- That means the scanner keeps seeing the same posts as fresh review candidates, and the only thing holding mail volume down is the 24h dedup ledger in `publish-notice`.
- Once the oldest emitted `post_id` entries age out of that 24h dedup ledger, they become eligible again because the guarded ledger is still being refreshed.

Earliest re-emit window, based on the established send times:

- first recurrence window: `2026-05-02 00:05 UTC` onward for the first emitted batch
- observed storm-window recurrence range: approximately `2026-05-02 00:05 UTC` to `2026-05-02 00:35:57 UTC`
- if the same `~103` post backlog remains and cap stays `10/run`, the full replay window would likely continue for roughly `11` runs, or about `2026-05-02 00:05 UTC` to `00:55 UTC`

## 3. Minimal hotfix candidates

### Option A — recommended

Command:

```bash
gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --update-env-vars=PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=0
```

Expected effect:

- `scan_guarded_publish_history()` gets a zero-hour recent window and should emit `0` guarded-review mails.
- ordinary publish notices remain available.
- 289 `post_gen_validate` remains available because review max/cap is unchanged.

Rollback:

```bash
gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --remove-env-vars=PUBLISH_NOTICE_REVIEW_WINDOW_HOURS
```

Side effects:

- Team Shiny From: no change
- 289 `post_gen_validate`: expected no change
- Gemini calls: no increase expected
- scheduler frequency: no change
- publish-notice availability: remains available
- guarded-publish review notices: suppressed while env is set to `0`

### Option B — fallback

Command:

```bash
gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --update-env-vars=PUBLISH_NOTICE_GUARDED_PUBLISH_HISTORY_PATH=/tmp/publish_notice_guarded_publish_history.disabled.jsonl
```

Expected effect:

- guarded review scan reads an empty/nonexistent local ledger path and emits `0` guarded-review mails.
- ordinary publish notices remain available.
- 289 `post_gen_validate` remains available because the shared review cap is not zeroed out.

Rollback:

```bash
gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --remove-env-vars=PUBLISH_NOTICE_GUARDED_PUBLISH_HISTORY_PATH
```

Side effects:

- Team Shiny From: no change
- 289 `post_gen_validate`: expected no change
- Gemini calls: no increase expected
- scheduler frequency: no change
- publish-notice availability: remains available
- guarded-publish review notices: fully suppressed while this env override is present

### Do not use for this incident

Not recommended:

```bash
gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --update-env-vars=PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=0
```

Why not:

- local code shows the guarded-review cap is shared with 289 `post_gen_validate`.
- setting it to `0` would also suppress 289, which is out of scope.

## 4. Acceptance Pack draft

## Acceptance Pack: P1-mail-storm-hotfix-verify

- **Decision**: GO
- **Requested user decision**: `publish-notice` に `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=0` を入れる env-only hotfix を実施し、次の 2 trigger を監視するか
- **Scope**: `publish-notice` Cloud Run Job の env 1 個だけ更新。対象は `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=0`。job image / scheduler / secret / source / WP / Gmail account は触らない
- **Not in scope**: Team Shiny From 変更、289 無効化、scheduler 頻度変更、`publish-notice` 停止、image rebuild、290/293/282 変更、source 追加、Gemini 呼び出し増加
- **Why now**: 現在の guarded ledger 再評価ループが残る限り、24h dedup 失効後に同じ古い候補 mail storm が再開する見込み。最小の env-only で先に guarded review path を止める必要がある
- **Preconditions**: 認証済み executor が `gcloud run jobs update` を実行できること。実施後に `publish-notice` 次回 2 trigger のログ確認を行うこと。`MAIL_BRIDGE_FROM` と `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` は維持すること
- **Cost impact**: Gemini call 追加 `0` 想定。Cloud Run Job update 1 回のみ。`backlog_only` review mail は `0` に落ちる想定。289 は維持想定
- **User-visible impact**: `【要確認(古い候補)】` 系の mail は止まる。通常 publish notice と `【要review｜post_gen_validate】` は維持される想定
- **Rollback**: `gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --remove-env-vars=PUBLISH_NOTICE_REVIEW_WINDOW_HOURS`
- **Evidence**: 事前 evidence = 2026-05-01 00:05..00:35:57 UTC の storm 既知事実 + `src/publish_notice_scanner.py` の 24h dedup / review window / backlog subject mapping / shared review cap 読み取り。完了 evidence = 次の 2 trigger で `sent=0` for old-candidate path、289 件名が維持、errors=0
- **Stop condition**: 実施後も `【要確認(古い候補)】` が送られる、289 `post_gen_validate` が消える、errors > 0、または通常 publish notice まで止まる
- **Expiry**: `2026-05-02 00:05 UTC` まで。24h dedup の最初の失効前に判断が必要
- **Recommended decision**: GO
- **Recommended reason**: supported env 1 個の変更で guarded backlog path だけを止める狙いで、rollback は 1 行、Team Shiny From / 289 / scheduler / Gemini を変えない

User reply format: `GO` / `HOLD` / `REJECT`

## Completion report

- changed_files: [docs/handoff/codex_responses/2026-05-01_codex_a_storm_verify.md]
- commit_hash: reported in console/final response
- open_questions_for_claude: [Can an authenticated executor run the missing `gcloud logging read` and `gcloud run jobs describe` checks before applying the hotfix?, After hotfix apply, can Claude verify the next 2 `publish-notice` triggers for `old-candidate sent=0`, `post_gen_validate still present`, and `errors=0`?]
- next_action_for_claude: "review codex_a doc; decide hotfix selection or escalate"
