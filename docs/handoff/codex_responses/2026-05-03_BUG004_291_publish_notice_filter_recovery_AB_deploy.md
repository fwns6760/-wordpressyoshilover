# 2026-05-03 BUG-004+291 publish-notice filter recovery A/B deploy

作成: 2026-05-03 16:48 JST

## scope

- live ops only
- target: `publish-notice` Cloud Run Job
- code / tests / config change: 0
- force trigger: 0
- Scheduler change: 0

## Step A

### command

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_PUBLISH_ONLY_MAIL_FILTER
```

### pre-state

- `publish-notice` image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:a4a5de8`
- env present: `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
- latest pre-change execution: `publish-notice-6dfnj`
- pre-change log:
  - `2026-05-03T07:31:02.715978Z` `[summary] sent=0 suppressed=1 errors=0 reasons={"PUBLISH_ONLY_FILTER": 1}`
  - `2026-05-03T07:31:02.715852Z` `post_id=post_gen_validate:f042408a2a102f9d:postgame_strict:strict_insufficient_for_render status=suppressed reason=PUBLISH_ONLY_FILTER`

### post-update describe

- job generation: `53`
- env removed successfully:
  - `ENABLE_PUBLISH_ONLY_MAIL_FILTER` no longer present in `gcloud run jobs describe publish-notice`
- image unchanged in Step A:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:a4a5de8`

### natural-run observation

- Scheduler remained enabled: `publish-notice-trigger` = `*/5 * * * *` / `Asia/Tokyo`
- first natural post-change execution: `publish-notice-6cf6g`
- execution window:
  - created `2026-05-03T07:35:04.970523Z`
  - completed `2026-05-03T07:36:18.267495Z`
- log evidence:
  - `2026-05-03T07:35:59.385516Z` `[summary] sent=1 suppressed=1 errors=0 reasons={"BACKLOG_SUMMARY_ONLY": 1}`
  - `2026-05-03T07:35:59.371648Z` `post_id=post_gen_validate:f042408a2a102f9d:postgame_strict:strict_insufficient_for_render status=sent`
- conclusion:
  - Step A succeeded
  - filter removal immediately allowed mail send again
  - temporary re-expansion of review-class mail was observed as expected

## Step B

### B-1 release composition verify

Commands:

```bash
git log --oneline 62c9b6a -- src/publish_notice_email_sender.py src/publish_notice_scanner.py
git status --short -- src vendor Dockerfile.publish_notice cloudbuild_publish_notice.yaml requirements.txt requirements-dev.txt
```

Result:

- `005b9f5 bug-004-291: publish-only filter direct-publish bypass narrow impl (default OFF)` is included in commit history reachable from `62c9b6a`
- current branch tip moved during the live window to doc-only commit `43f208f`, but this did not change publish-notice build inputs
- input paths copied by `Dockerfile.publish_notice` had no local diff
- to avoid any mixed-context risk, build source was isolated from exact commit `62c9b6a` via:

```bash
builddir=/tmp/publish-notice-build-62c9b6a
git archive 62c9b6a | tar -x -C "$builddir"
```

### B-2 image build

Command:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud builds submit /tmp/publish-notice-build-62c9b6a \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=/tmp/publish-notice-build-62c9b6a/cloudbuild_publish_notice.yaml \
  --substitutions=_TAG=62c9b6a,_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=publish-notice
```

Build result:

| item | value |
|---|---|
| build id | `f555c842-16e6-4bdf-acff-7c62ab3f0e18` |
| status | `SUCCESS` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:62c9b6a` |
| digest | `sha256:7bbec87c8bea906b40a697b89dea81c1b3856f8ebe447c9887c1682c64cba266` |
| fully qualified digest | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice@sha256:7bbec87c8bea906b40a697b89dea81c1b3856f8ebe447c9887c1682c64cba266` |
| duration | `2M20S` |

### B-3 image update

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:62c9b6a
```

### B-4 env re-apply

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_PUBLISH_ONLY_MAIL_FILTER=1,ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1
```

### B-5 post-apply describe

- Cloud Run Job generation: `55`
- image:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:62c9b6a`
- env confirmed:
  - `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`
- note:
  - Cloud Run Job does not expose a service-style revision name
  - job generation `55` and execution names below are the runtime identifiers for this apply

### B-5 natural-run observation

#### first post-fix execution

- execution: `publish-notice-ct69z`
- window:
  - created `2026-05-03T07:40:05.173102Z`
  - completed `2026-05-03T07:41:24.646713Z`
- log evidence:
  - `2026-05-03T07:41:05.130525Z` `[summary] sent=1 suppressed=3 errors=0 reasons={"BACKLOG_SUMMARY_ONLY": 3}`
  - `2026-05-03T07:41:05.079088Z` `post_id=64100 status=sent reason=None subject='【要review】◇セ・リーグ公示（３０日） ...'`
- interpretation:
  - filter remained ON
  - a review-subject mail was sent on the direct-publish bypass path
  - this is the first live evidence after Step B that the bypass flag is working on the rebuilt image

#### follow-up execution

- execution: `publish-notice-mlhvb`
- window:
  - created `2026-05-03T07:45:05.268242Z`
  - completed `2026-05-03T07:47:18.206512Z`
- log evidence:
  - `2026-05-03T07:46:58.009792Z` `[summary] sent=0 suppressed=1 errors=0 reasons={"PUBLISH_ONLY_FILTER": 1}`
  - `2026-05-03T07:46:58.009741Z` `post_id=63985 status=suppressed reason=PUBLISH_ONLY_FILTER subject='【要review】◇セ・リーグ公示（２９日） ...'`
- interpretation:
  - non-bypass review mail suppression still works when the mail does not qualify for direct-publish bypass
  - no mail storm was observed

## targeted post-id observation

Recent affected IDs were checked directly in Cloud Logging:

- `64194` pre-fix evidence:
  - `2026-05-03T05:41:11.564610Z` `status=suppressed reason=PUBLISH_ONLY_FILTER`
- `64196` pre-fix evidence:
  - `2026-05-03T05:41:11.566789Z` `status=suppressed reason=PUBLISH_ONLY_FILTER`
- `64343` pre-fix evidence:
  - `2026-05-03T05:10:58.688935Z` `status=suppressed reason=PUBLISH_ONLY_FILTER`
- `64352` pre-fix evidence:
  - `2026-05-03T05:21:09.217485Z` `status=suppressed reason=PUBLISH_ONLY_FILTER`
- `64366` pre-fix evidence:
  - `2026-05-03T06:55:58.607573Z` `status=suppressed reason=PUBLISH_ONLY_FILTER`

No automatic re-send for those older IDs was observed during the Step B watch window. The live success proof after recovery is instead the new post-fix sent record for `post_id=64100`.

## mail send evidence

- Step A:
  - `2026-05-03T07:35:59.371648Z`
  - `post_id=post_gen_validate:f042408a2a102f9d:postgame_strict:strict_insufficient_for_render`
- Step B:
  - `2026-05-03T07:41:05.079088Z`
  - `post_id=64100`

## rollback

### Step A rollback

Re-add the original filter only:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_PUBLISH_ONLY_MAIL_FILTER=1
```

### Step B rollback

1. remove bypass flag and, if needed, remove filter again

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS
```

2. revert image to pre-fix tag

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:a4a5de8
```

3. if full pre-Step-A behavior is needed, re-add original filter on the reverted image

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-full-iOlyLk \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_PUBLISH_ONLY_MAIL_FILTER=1
```

## result

- Step A executed: yes
- Step B executed: yes
- build success: yes
- live image updated: yes
- live env updated: yes
- force execute used: no
- Scheduler changed: no
- source edited: no
