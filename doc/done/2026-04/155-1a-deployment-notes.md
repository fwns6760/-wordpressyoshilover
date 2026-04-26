# 155-1a deployment notes

## scope

Phase 1a covers image build preparation only.

- add `Dockerfile.draft_body_editor`
- add `cloudbuild_draft_body_editor.yaml`
- verify local YAML syntax
- document the Artifact Registry target and the Phase 1a handoff

Out of scope for 1a:

- `gcloud builds submit` execution
- Cloud Run Job creation
- Cloud Scheduler wiring
- Secret Manager wiring
- WSL cron disable

## target image

- project: `baseballsite`
- region: `asia-northeast1`
- Artifact Registry repo: `yoshilover`
- image name: `draft-body-editor`
- full image path: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:<tag>`

## Dockerfile summary

- base image: `python:3.12-slim`
- working directory: `/app`
- copied into image: `requirements.txt`, `requirements-dev.txt`, `src/`, `vendor/`
- runtime env baked into image: `PYTHONPATH=/app`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`
- runtime entrypoint: `python3 -m src.tools.run_draft_body_editor_lane`
- default command: `--max-posts 3`
- security posture: non-root user `appuser`

## Cloud Build summary

- config file: `cloudbuild_draft_body_editor.yaml`
- substitutions:
  - `_REGION=asia-northeast1`
  - `_PROJECT_ID=baseballsite`
  - `_IMAGE_NAME=draft-body-editor`
  - `_TAG=latest` by default, override on submit
- build step: `docker build -f Dockerfile.draft_body_editor`
- push step: `docker push asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:<tag>`
- timeout: `600s`
- machine type override: `E2_MEDIUM`

## Phase 1a verification

When Docker is available locally:

```bash
cd /home/fwns6/code/wordpressyoshilover
docker build -f Dockerfile.draft_body_editor -t draft-body-editor:local .
docker run --rm draft-body-editor:local --help
python3 -m pytest --collect-only -q | tail -3
python3 -c "import yaml; yaml.safe_load(open('cloudbuild_draft_body_editor.yaml'))" && echo "yaml OK"
```

Cloud Build handoff command for Phase 1b or later:

```bash
gcloud builds submit \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=cloudbuild_draft_body_editor.yaml \
  --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=draft-body-editor,_TAG=$(git rev-parse --short HEAD) \
  .
```

## expected outputs to confirm later

- local image tag: `draft-body-editor:local`
- remote image tag example: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:5c845a8`
- next ticket boundary: Phase 1b owns Cloud Run Job deploy and manual trigger smoke only after this image build path is confirmed
