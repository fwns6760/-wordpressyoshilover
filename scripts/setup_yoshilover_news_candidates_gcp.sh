#!/usr/bin/env bash
set -euo pipefail

# Build and wire the YOSHILOVER Giants news candidate mail lane.
# This script performs live GCP mutation. Run only from an authenticated shell.

PROJECT_ID="${PROJECT_ID:-baseballsite}"
REGION="${REGION:-asia-northeast1}"
REPOSITORY="${REPOSITORY:-yoshilover}"
IMAGE_NAME="${IMAGE_NAME:-yoshilover-news-candidates}"
TAG="${TAG:-yoshi-news-candidates-$(git rev-parse --short HEAD)}"
JOB_NAME="${JOB_NAME:-yoshilover-news-candidates-mail}"
SCHEDULER_NAME="${SCHEDULER_NAME:-yoshilover-news-candidates-9-12-15}"
SCHEDULER_SA="${SCHEDULER_SA:-487178857517-compute@developer.gserviceaccount.com}"
SCHEDULE="${SCHEDULE:-0 9,12,15 * * *}"
LEDGER_GCS_URI="${LEDGER_GCS_URI:-gs://yoshilover-history/news_candidates/ledger.jsonl}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${TAG}"

echo "project=${PROJECT_ID}"
echo "region=${REGION}"
echo "image=${IMAGE_URI}"
echo "job=${JOB_NAME}"
echo "scheduler=${SCHEDULER_NAME}"
echo "schedule=${SCHEDULE}"

gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config=cloudbuild_yoshilover_news_candidates.yaml \
  --substitutions="_REGION=${REGION},_PROJECT_ID=${PROJECT_ID},_IMAGE_NAME=${IMAGE_NAME},_TAG=${TAG}"

COMMON_ENV="YOSHILOVER_NEWS_CANDIDATE_LEDGER_GCS_URI=${LEDGER_GCS_URI},YOSHILOVER_NEWS_MAX_CANDIDATES=18,YOSHILOVER_NEWS_MAX_ITEMS_PER_SOURCE=8"
COMMON_SECRETS="MAIL_BRIDGE_TO=mail-bridge-to:latest,MAIL_BRIDGE_SMTP_USERNAME=mail-bridge-smtp-username:latest,MAIL_BRIDGE_FROM=mail-bridge-from:latest,MAIL_BRIDGE_GMAIL_APP_PASSWORD=mail-bridge-gmail-app-password:latest"

if gcloud run jobs describe "${JOB_NAME}" --project="${PROJECT_ID}" --region="${REGION}" >/dev/null 2>&1; then
  gcloud run jobs update "${JOB_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --image="${IMAGE_URI}" \
    --update-env-vars="${COMMON_ENV}" \
    --update-secrets="${COMMON_SECRETS}"
else
  gcloud run jobs create "${JOB_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --image="${IMAGE_URI}" \
    --tasks=1 \
    --max-retries=0 \
    --set-env-vars="${COMMON_ENV}" \
    --set-secrets="${COMMON_SECRETS}"
fi

SCHEDULER_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"
if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --project="${PROJECT_ID}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --schedule="${SCHEDULE}" \
    --time-zone="Asia/Tokyo" \
    --uri="${SCHEDULER_URI}" \
    --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_SA}" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
    --attempt-deadline=180s
else
  gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --schedule="${SCHEDULE}" \
    --time-zone="Asia/Tokyo" \
    --uri="${SCHEDULER_URI}" \
    --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_SA}" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
    --attempt-deadline=180s
fi

gcloud run jobs describe "${JOB_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="table(name,template.template.containers[0].image)"

gcloud scheduler jobs describe "${SCHEDULER_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --format="table(name,schedule,timeZone,state)"
