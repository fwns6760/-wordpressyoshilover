# 2026-05-03 291 subtask-8 guarded-publish deploy record

作成: 2026-05-03 12:37 JST

## scope

- runtime apply only
- code / tests / config change: 0
- target: `guarded-publish` Cloud Run Job

## release composition verify

- `git log --oneline 9e9302f..HEAD -- src/guarded_publish_runner.py`
  - `b57a50a 291: subtask-8 duplicate target integrity strict (default OFF, exact source_url_hash match, no silent drop)`
- `HEAD = 25d48cc`
  - top commit is doc-only (`288-INGEST: Phase 0 source/topic coverage read-only audit`)
- conclusion:
  - guarded-publish source delta since live image `:9e9302f` is `b57a50a` only

## build

| item | value |
|---|---|
| build id | `6ebfcc3b-afb1-475f-b78b-aa3bd6b86822` |
| build status | `SUCCESS` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc` |
| image digest | `sha256:4dd013483046aa349385493d8f62743ab256f7aa6afed0161a0d2d9ad3d8040f` |
| build duration | `3M47S` |

Note:

- `cloudbuild_guarded_publish.yaml` uses `_TAG`, so the live build ran with `_TAG=25d48cc`.
- sandbox workaround only: `CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish3` copied from read-only `~/.config/gcloud` so `gcloud` could write local state. No runtime env / secret changed by this workaround.

## live apply

### pre-apply

- job generation: `19`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:9e9302f`
- `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT`: absent

### applied

1. image update
   - `gcloud run jobs update guarded-publish --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc --region=asia-northeast1`
2. env apply
   - `gcloud run jobs update guarded-publish --update-env-vars=ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1 --region=asia-northeast1`

### post-apply describe

- job generation: `21`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc`
- env confirmed:
  - `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`

## post-deploy verify

- first post-update execution:
  - name: `guarded-publish-pvgdr`
  - create: `2026-05-03T03:35:05.309149Z`
  - complete: `2026-05-03T03:36:38.265772Z`
  - status: `EXECUTION_SUCCEEDED`
- log evidence after update:
  - `2026-05-03T03:36:26.319409Z`
  - event: `duplicate_target_integrity_check`
- observed scope remained narrow:
  - no Scheduler change
  - no new source
  - no Gemini/mail policy expansion
  - no WP/body mutation in this task

## rollback

- env rollback:
  - `gcloud run jobs update guarded-publish --remove-env-vars=ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT --region=asia-northeast1`
- image rollback:
  - `gcloud run jobs update guarded-publish --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:9e9302f --region=asia-northeast1`
- source rollback:
  - `git revert b57a50a00eacc2793bac724c9f8383ba71280990`

## result

- deploy executed: yes
- src changed: no
- tests rerun in this task: no (repo already had CLAUDE_AUTO_GO precondition that tests were passing before runtime apply)
