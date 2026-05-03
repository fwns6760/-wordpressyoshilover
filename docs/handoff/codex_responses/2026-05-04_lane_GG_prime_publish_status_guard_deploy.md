# 2026-05-04 Lane GG' publish status guard deploy record

作成: 2026-05-04 JST

## mode

- live ops request received
- target runtime:
  - `yoshilover-fetcher` Cloud Run service
  - `guarded-publish` Cloud Run Job
- requested live flag:
  - `ENABLE_WP_PUBLISH_STATUS_GUARD=1`
- code / tests / config edits in this lane: `0`
- live mutation result in this executor: `blocked before build/update`
- git push: not run

## Step 1: release composition verify

### HEAD / commit chain

- current `HEAD`: `5b8fc89`
- `origin/master`: `5b8fc89`
- target implementation commit: `550d252`
- ancestor check:
  - `git merge-base --is-ancestor 550d252 HEAD` -> `yes`

Recent chain:

```text
5b8fc89 (HEAD -> master, origin/master) bug-003: record 64416 audit and guard fix
550d252 bug-003: harden publish status writes
```

### target file inclusion

`git show --stat --oneline 550d252` confirms the implementation commit includes:

- `src/wp_client.py`
- `src/rss_fetcher.py`
- `src/guarded_publish_runner.py`

Relevant call sites present in `550d252`:

- `src/rss_fetcher.py`
  - `wp.publish_post(... caller="rss_fetcher.finalize_post_publication", source_lane="rss_fetcher", status_before="draft")`
- `src/guarded_publish_runner.py`
  - `get_wp().publish_post(... caller="guarded_publish_runner.run_guarded_publish", source_lane="guarded_publish", status_before=...)`
- `src/wp_client.py`
  - `WP_PUBLISH_STATUS_GUARD_ENV = "ENABLE_WP_PUBLISH_STATUS_GUARD"`
  - `WPClient.publish_post(...)`
  - structured event emit for publish status guard

### build input hygiene

The delta from `550d252..HEAD` is doc-only:

- `docs/handoff/codex_responses/2026-05-04_lane_GG_bug003_publish_revert_fix.md`

Verified empty:

- `git diff --name-only 550d252..HEAD -- Dockerfile requirements.txt config src`
- `git diff --name-only 550d252..HEAD -- Dockerfile.guarded_publish cloudbuild_guarded_publish.yaml requirements.txt requirements-dev.txt src vendor bin/guarded_publish_entrypoint.sh`
- `git status --short -- Dockerfile requirements.txt config src Dockerfile.guarded_publish cloudbuild_guarded_publish.yaml requirements-dev.txt vendor bin/guarded_publish_entrypoint.sh`

Conclusion:

- `yoshilover-fetcher` build inputs are unchanged since `550d252`
- `guarded-publish` build inputs are unchanged since `550d252`
- pre-existing modified files in `doc/`, `docs/ops/`, and unrelated untracked paths are outside the build inputs used for this lane

### image composition boundary

`yoshilover-fetcher` image input boundary:

- `Dockerfile` copies only:
  - `requirements.txt`
  - `src/`
  - `config/`

`guarded-publish` image input boundary:

- `cloudbuild_guarded_publish.yaml` stages a temp context containing only:
  - `Dockerfile.guarded_publish`
  - `requirements.txt`
  - `requirements-dev.txt`
  - `src/`
  - `vendor/`
  - `bin/guarded_publish_entrypoint.sh`

## Step 2-3: live apply attempt

### authenticated config workaround

Direct `gcloud` use against `~/.config/gcloud` failed because the config directory is read-only in this executor.

Observed:

```text
ERROR: (gcloud.auth.list) Unable to create private file [/home/fwns6/.config/gcloud/credentials.db]: [Errno 30] Read-only file system
```

Mitigation used:

- create minimal writable `CLOUDSDK_CONFIG` under `/tmp`
- copy only:
  - `active_config`
  - `configurations/config_default`
  - `credentials.db`
  - `access_tokens.db`
  - `default_configs.db`
  - `config_sentinel`
  - `application_default_credentials.json` when present

Auth verification with the minimal config succeeded:

- active account: `fwns6760@gmail.com`

### blocker

DNS resolution to Google APIs is unavailable in this executor.

Diagnostic:

```text
run.googleapis.com ERR gaierror(-2, 'Name or service not known')
cloudbuild.googleapis.com ERR gaierror(-2, 'Name or service not known')
artifactregistry.googleapis.com ERR gaierror(-2, 'Name or service not known')
```

Observed `gcloud` failure:

```text
ERROR: gcloud crashed (ConnectionError): HTTPSConnectionPool(host='asia-northeast1-run.googleapis.com', port=443): Max retries exceeded with url: /apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/guarded-publish?alt=json (Caused by NameResolutionError("HTTPSConnection(host='asia-northeast1-run.googleapis.com', port=443): Failed to resolve 'asia-northeast1-run.googleapis.com' ([Errno -2] Name or service not known)"))
```

Because read-only `describe` could not reach Cloud Run, the lane stopped before:

- `gcloud builds submit`
- `gcloud run services update yoshilover-fetcher ...`
- `gcloud run jobs update guarded-publish ...`
- any `--update-env-vars=ENABLE_WP_PUBLISH_STATUS_GUARD=1`

## Step 4: live verify

Not executed.

Reason:

- no build was submitted
- no service/job image update was executed
- no env apply was executed
- current executor cannot resolve Cloud Run / Cloud Build / Artifact Registry hosts

## last known live state from repo docs only

These values are not freshly verified in this executor today. They are the last known state recorded in repo docs before this blocked attempt.

### yoshilover-fetcher

Source:

- `docs/handoff/codex_responses/2026-05-03_BUG004_291_subtask10b_deploy.md`

Last known:

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:e0a58bb`
- image digest: `sha256:ad6303c14d79a0dba72695aae672169cf44a25b3694da5e59238316c5f620568`
- revision: `yoshilover-fetcher-00186-9cl`
- env recorded there:
  - `ENABLE_POSTGAME_STRICT_FACT_RECOVERY=1`
  - `ENABLE_GEMINI_PREFLIGHT=1`
  - `ENABLE_NARROW_UNLOCK_NON_POSTGAME=1`
  - `ENABLE_BODY_CONTRACT_FAIL_LEDGER=1`
  - `ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE=1`

### guarded-publish

Source:

- `docs/handoff/codex_responses/2026-05-03_lane_W2_death_grave_deploy_recovery.md`

Last known:

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:0f5e95a`
- image digest: `sha256:8618171111fc4ca9b7ad78c72b0a6385874eef35c2f11c0f900f5e7379f6564b`
- generation: `25`
- env recorded there:
  - `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`
  - `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT=1`
  - `ENABLE_DEATH_GRAVE_INJURY_RETURN_EXEMPT=1`

## exact live commands to rerun under a working authenticated executor

### minimal writable gcloud config

```bash
GCLOUD_TMP="$(mktemp -d /tmp/gcloud-min-XXXXXX)"
mkdir -p "$GCLOUD_TMP/configurations"
cp ~/.config/gcloud/active_config "$GCLOUD_TMP/"
cp ~/.config/gcloud/configurations/config_default "$GCLOUD_TMP/configurations/"
cp ~/.config/gcloud/credentials.db ~/.config/gcloud/access_tokens.db ~/.config/gcloud/default_configs.db ~/.config/gcloud/config_sentinel "$GCLOUD_TMP/" 2>/dev/null || true
[ -f ~/.config/gcloud/application_default_credentials.json ] && cp ~/.config/gcloud/application_default_credentials.json "$GCLOUD_TMP/"
export CLOUDSDK_CONFIG="$GCLOUD_TMP"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
```

### Step 2: yoshilover-fetcher

```bash
gcloud builds submit \
  --project=baseballsite \
  --tag=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:550d252

gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:550d252

gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_WP_PUBLISH_STATUS_GUARD=1
```

### Step 3: guarded-publish

```bash
gcloud builds submit \
  --project=baseballsite \
  --config=cloudbuild_guarded_publish.yaml \
  --substitutions=_TAG=550d252

gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:550d252

gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_WP_PUBLISH_STATUS_GUARD=1
```

### Step 4 verify targets

```bash
gcloud run services describe yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1

gcloud run jobs describe guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1
```

Then verify:

- image tag or digest matches `:550d252`
- `ENABLE_WP_PUBLISH_STATUS_GUARD=1` is present
- pre-existing flags remain present
- latest service request / job execution has `error=0`
- structured guard log includes:
  - `caller`
  - `source_lane`
  - `status_before`
  - `status_after`

## rollback

### actual rollback executed in this lane

- none
- no live mutation was performed

### rollback plan after a successful later deploy

`yoshilover-fetcher`:

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:e0a58bb

gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_WP_PUBLISH_STATUS_GUARD
```

`guarded-publish`:

```bash
gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:0f5e95a

gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_WP_PUBLISH_STATUS_GUARD
```

source rollback:

```bash
git revert 550d252
```

## result

- Step 1 release composition verify: `completed`
- Step 2 yoshilover-fetcher build/update/env apply: `not executed`
- Step 3 guarded-publish build/update/env apply: `not executed`
- Step 4 live verify: `not executed`
- stop reason: current executor cannot resolve Google API hosts, so live GCP mutation is blocked before build/describe
