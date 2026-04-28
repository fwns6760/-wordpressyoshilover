# 206 mail-delivery four-stage read-only audit

- priority: P0.5
- status: CLOSED
- owner: Codex / Claude follow-up
- lane: Claude
- created: 2026-04-27
- scope: read-only audit only

## Close note(2026-04-28)

Later 241 / 240-v5 work fixed the notification path and confirmed PC/mobile Gmail notifications. This audit is kept as historical evidence in done.

## Purpose

メールが来ない原因を、RSS/source -> fetcher -> guarded-publish -> publish-notice/mail の4段階で切り分ける。

This ticket intentionally does not update `doc/README.md` or `doc/active/assignments.md`, to avoid collision with the in-flight 202-205 doc sync.

## Conclusion

**E: mail送信側、または送信結果の証跡不足が最も疑わしい。**

理由:

- Aではない: WordPress public REST上、2026-04-27 00:00 JST以降の publish は50件以上見えている。
- Bではない: `giants-realtime-trigger` は `*/5 * * * *` / `ENABLED` で、直近 attempt も HTTP 200。
- Cではない: `guarded-publish-trigger` は `*/5 * * * *` / `ENABLED` で、直近 Cloud Run Job execution は成功。
- Dではない: `publish-notice` のGCS historyに最新 publish `63781` が記録されており、scannerは少なくとも該当postを拾っている。
- E寄り: `publish-notice` execution自体は成功しているが、queue fileはGCS永続化対象外で、送信結果の確定証跡をGCSから追えない。Cloud LoggingのtextPayload詳細取得は重く、今回のaudit中に安定取得できなかった。

## A-E Classification

| code | meaning | verdict |
|---|---|---|
| A | RSS/sourceが静か | NO |
| B | fetcherが動いていない | NO |
| C | draftは増えているが guarded-publish がpublishしていない | NO |
| D | publishはあるが publish-notice が拾っていない | NO |
| E | mail送信側の問題 | LIKELY |

## Evidence

### 1. RSS / ingestion

Read-only command:

```bash
gcloud scheduler jobs describe giants-realtime-trigger \
  --project=baseballsite \
  --location=asia-northeast1
```

Observed:

- schedule: `*/5 * * * *`
- timeZone: `Asia/Tokyo`
- state: `ENABLED`
- lastAttemptTime: `2026-04-27T02:25:16.955540Z`
- Cloud Scheduler execution log showed HTTP 200 for `giants-realtime-trigger`.

Interpretation:

- fetcher trigger is not paused.
- This does not prove every RSS source has new items, but it disproves "trigger stopped" as the immediate cause.

### 2. guarded-publish

Read-only commands:

```bash
gcloud scheduler jobs describe guarded-publish-trigger \
  --project=baseballsite \
  --location=asia-northeast1

gcloud run jobs describe guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1
```

Observed:

- schedule: `*/5 * * * *`
- state: `ENABLED`
- latest execution observed: `guarded-publish-6fgkk`
- prior described execution `guarded-publish-pvndr` completed successfully in 36.56s
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:26c6ae2`

Interpretation:

- guarded-publish itself is being triggered and recent executions complete successfully.

### 3. publish-notice

Read-only commands:

```bash
gcloud scheduler jobs describe publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1

gcloud run jobs describe publish-notice \
  --project=baseballsite \
  --region=asia-northeast1

gcloud storage cat gs://baseballsite-yoshilover-state/publish_notice/cursor.txt \
  --project=baseballsite

gcloud storage cp gs://baseballsite-yoshilover-state/publish_notice/history.json /tmp/history206.json \
  --project=baseballsite --quiet
```

Observed:

- schedule: `*/5 * * * *`
- state: `ENABLED`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:23853cd`
- latest execution observed: `publish-notice-9csvx`
- prior described execution `publish-notice-j887b` completed successfully in 32.71s
- GCS cursor: `2026-04-27T11:25:30.342670+09:00`
- GCS history includes:
  - `63781`: `2026-04-27T09:05:38+09:00`
  - many earlier 2026-04-27 morning posts

Interpretation:

- publish-notice is not stuck on the old `cbc335f` image.
- publish-notice scanner did see the latest public post `63781`.
- If Gmail did not receive the corresponding notice, the failure is after scan detection.

### 4. WordPress public state

Read-only source:

```text
https://yoshilover.com/wp-json/wp/v2/posts?status=publish&per_page=20&orderby=date&order=desc&_fields=id,date,modified,title
```

Observed recent publish examples:

| post_id | date JST | title head |
|---|---|---|
| 63781 | 2026-04-27T09:05:38 | 本日4月27日は巨人鈴木尚広2軍外野守備兼走塁コーチの48歳の誕生日... |
| 62102 | 2026-04-27T08:25:48 | 巨人育成ドミニカンが２軍戦猛打＆Ｖ２号... |
| 62118 | 2026-04-27T08:25:47 | ドラフト４位・皆川岳飛が今季初めて１軍合流... |
| 62120 | 2026-04-27T08:25:45 | 選手「プロ初安打」 実戦で何を見せるか |

The same public REST check with `after=2026-04-27T00:00:00` returned at least 50 published posts.

Interpretation:

- The "no new publish" explanation is not correct for this audit window.
- There is at least one newer post after 09:05 JST, and publish-notice history has recorded it.

## Important finding

`src.cloud_run_persistence.run_publish_notice_entrypoint()` only persists:

- `cursor.txt`
- `history.json`

It does **not** persist the `queue_path` file to GCS.

Therefore, even when publish-notice scans a post and attempts send, GCS state alone cannot prove:

- `status=sent`
- `status=suppressed`
- `reason=NO_RECIPIENT`
- `reason=GATE_OFF`
- SMTP bridge failure

The only immediate evidence for send result is Cloud Logging textPayload / Firestore or local ephemeral queue, and the Cloud Logging detailed query was unstable during this audit.

## Risk

The current system can appear healthy because:

- scheduler returns HTTP 200
- Cloud Run Job execution completes successfully
- scanner cursor/history advance

But the user may still not receive mail if `send()` returns a suppressed result. The CLI returns 0 after printing the result, so job success does not necessarily mean Gmail delivery.

## Minimal follow-up ticket

Create a narrow implementation ticket:

**207-publish-notice-send-result-persistence-and-alert**

Scope:

- Persist publish-notice `queue_path` or send-result summary to GCS.
- Include per-post result:
  - post_id
  - publish_time_iso
  - status
  - reason
  - subject
  - recorded_at
  - notice_kind
- If scan emitted > 0 and all send results are not `sent`, emit a clear alert log line.
- Do not change SMTP credentials, scheduler, WP write, or X behavior.

Acceptance:

- After each Cloud Run execution, GCS has a durable send-result artifact.
- A read-only audit can answer "sent / suppressed / reason" without relying on heavy Cloud Logging queries.
- Existing publish-notice send behavior is preserved.

## Guardrails held

- GCP live change: NO
- Scheduler change: NO
- WP write: NO
- mail real-send: NO
- X post: NO
- secret display: NO
- git reset: NO
- `git add -A`: NO
- README / assignments edit: NO
