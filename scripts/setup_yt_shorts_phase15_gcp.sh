#!/usr/bin/env bash
set -euo pipefail

# Build and wire the YouTube Shorts Phase 1.5 semi-automatic publish flow.
# This script performs live GCP mutation. Run only from an authenticated shell.
# It does not print secret values; it only binds Secret Manager secret names.

PROJECT_ID="${PROJECT_ID:-baseballsite}"
REGION="${REGION:-asia-northeast1}"
REPOSITORY="${REPOSITORY:-yoshilover}"

YT_IMAGE_NAME="${YT_IMAGE_NAME:-yt-shorts-gen}"
YT_JOB_NAME="${YT_JOB_NAME:-yt-shorts-gen}"
FETCHER_SERVICE="${FETCHER_SERVICE:-yoshilover-fetcher}"
FETCHER_IMAGE_NAME="${FETCHER_IMAGE_NAME:-yoshilover-fetcher}"

SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || printf 'manual')"
STAMP="$(date -u +%Y%m%d%H%M%S)"
TAG="${TAG:-yt-shorts-${SHORT_SHA}-${STAMP}}"
FETCHER_TAG="${FETCHER_TAG:-yt-shorts-approval-${SHORT_SHA}-${STAMP}}"

YT_IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${YT_IMAGE_NAME}:${TAG}"
FETCHER_IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${FETCHER_IMAGE_NAME}:${FETCHER_TAG}"

FETCHER_PUBLIC_BASE_URL="${FETCHER_PUBLIC_BASE_URL:-https://yoshilover-fetcher-n5hunzkyna-an.a.run.app}"
YT_SHORTS_GCS_BUCKET="${YT_SHORTS_GCS_BUCKET:-baseballsite-yoshilover-insight}"
YT_SHORTS_YOUTUBE_CATEGORY_ID="${YT_SHORTS_YOUTUBE_CATEGORY_ID:-17}"
YT_SHORTS_VOICEVOX_SPEAKER="${YT_SHORTS_VOICEVOX_SPEAKER:-13}"

BUILD_IMAGES="${BUILD_IMAGES:-1}"
UPDATE_FETCHER="${UPDATE_FETCHER:-1}"
UPDATE_YT_JOB="${UPDATE_YT_JOB:-1}"
EXECUTE_LIVE_SMOKE="${EXECUTE_LIVE_SMOKE:-0}"
CREATE_SCHEDULER="${CREATE_SCHEDULER:-0}"

SCHEDULER_NAME="${SCHEDULER_NAME:-yt-shorts-gen-daily}"
SCHEDULER_SA="${SCHEDULER_SA:-487178857517-compute@developer.gserviceaccount.com}"
SCHEDULE="${SCHEDULE:-30 7 * * *}"

YT_SECRET_MAP="YT_SHORTS_YOUTUBE_CLIENT_ID=yt-shorts-youtube-client-id:latest,YT_SHORTS_YOUTUBE_CLIENT_SECRET=yt-shorts-youtube-client-secret:latest,YT_SHORTS_YOUTUBE_REFRESH_TOKEN=yt-shorts-youtube-refresh-token:latest,YT_SHORTS_APPROVAL_TOKEN_SECRET=yt-shorts-approval-token-secret:latest"
MAIL_SECRET_MAP="MAIL_BRIDGE_TO=mail-bridge-to:latest,MAIL_BRIDGE_SMTP_USERNAME=mail-bridge-smtp-username:latest,MAIL_BRIDGE_FROM=mail-bridge-from:latest,MAIL_BRIDGE_GMAIL_APP_PASSWORD=mail-bridge-gmail-app-password:latest"
YT_JOB_SECRET_MAP="${YT_SECRET_MAP},${MAIL_SECRET_MAP}"

YT_JOB_ENV="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCP_PROJECT=${PROJECT_ID},YT_SHORTS_GCS_BUCKET=${YT_SHORTS_GCS_BUCKET},FETCHER_PUBLIC_BASE_URL=${FETCHER_PUBLIC_BASE_URL},YT_SHORTS_APPROVAL_BASE_URL=${FETCHER_PUBLIC_BASE_URL},YT_SHORTS_YOUTUBE_PRIVATE_UPLOAD=1,YT_SHORTS_YOUTUBE_INITIAL_PRIVACY=private,YT_SHORTS_YOUTUBE_CATEGORY_ID=${YT_SHORTS_YOUTUBE_CATEGORY_ID},YT_SHORTS_EMBEDDED_VOICEVOX=1,YT_SHORTS_VOICEVOX_SPEAKER=${YT_SHORTS_VOICEVOX_SPEAKER}"
FETCHER_ENV="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCP_PROJECT=${PROJECT_ID},FETCHER_PUBLIC_BASE_URL=${FETCHER_PUBLIC_BASE_URL}"

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

require_gcloud() {
  if ! command -v gcloud >/dev/null 2>&1; then
    echo "gcloud is required" >&2
    exit 1
  fi
  if ! gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q .; then
    echo "No active gcloud account. Run gcloud auth login first." >&2
    exit 1
  fi
}

echo "project=${PROJECT_ID}"
echo "region=${REGION}"
echo "yt_image=${YT_IMAGE_URI}"
echo "fetcher_image=${FETCHER_IMAGE_URI}"
echo "yt_job=${YT_JOB_NAME}"
echo "fetcher_service=${FETCHER_SERVICE}"
echo "fetcher_public_base_url=${FETCHER_PUBLIC_BASE_URL}"
echo "yt_shorts_gcs_bucket=${YT_SHORTS_GCS_BUCKET}"
echo "create_scheduler=${CREATE_SCHEDULER}"
echo "execute_live_smoke=${EXECUTE_LIVE_SMOKE}"

require_gcloud

if [[ "${BUILD_IMAGES}" == "1" ]]; then
  run gcloud builds submit \
    --project="${PROJECT_ID}" \
    --config=cloudbuild_yt_shorts.yaml \
    --substitutions="_REGION=${REGION},_PROJECT_ID=${PROJECT_ID},_IMAGE_NAME=${YT_IMAGE_NAME},_TAG=${TAG}" \
    --quiet \
    .

  run gcloud builds submit \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --tag="${FETCHER_IMAGE_URI}" \
    --quiet \
    .
fi

if [[ "${UPDATE_FETCHER}" == "1" ]]; then
  if ! gcloud run services describe "${FETCHER_SERVICE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" >/dev/null 2>&1; then
    echo "Cloud Run service not found: ${FETCHER_SERVICE}" >&2
    exit 1
  fi

  run gcloud run services update "${FETCHER_SERVICE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --image="${FETCHER_IMAGE_URI}" \
    --update-env-vars="${FETCHER_ENV}" \
    --update-secrets="${YT_SECRET_MAP}" \
    --quiet
fi

if [[ "${UPDATE_YT_JOB}" == "1" ]]; then
  job_common_flags=(
    "--project=${PROJECT_ID}"
    "--region=${REGION}"
    "--image=${YT_IMAGE_URI}"
    "--tasks=1"
    "--parallelism=1"
    "--max-retries=0"
    "--cpu=2"
    "--memory=4Gi"
    "--task-timeout=1800s"
    "--args=--live,--youtube-private-upload"
  )
  if [[ -n "${JOB_SERVICE_ACCOUNT:-}" ]]; then
    job_common_flags+=("--service-account=${JOB_SERVICE_ACCOUNT}")
  fi

  if gcloud run jobs describe "${YT_JOB_NAME}" --project="${PROJECT_ID}" --region="${REGION}" >/dev/null 2>&1; then
    run gcloud run jobs update "${YT_JOB_NAME}" \
      "${job_common_flags[@]}" \
      --update-env-vars="${YT_JOB_ENV}" \
      --update-secrets="${YT_JOB_SECRET_MAP}" \
      --quiet
  else
    run gcloud run jobs create "${YT_JOB_NAME}" \
      "${job_common_flags[@]}" \
      --set-env-vars="${YT_JOB_ENV}" \
      --set-secrets="${YT_JOB_SECRET_MAP}" \
      --quiet
  fi
fi

if [[ "${EXECUTE_LIVE_SMOKE}" == "1" ]]; then
  echo "Executing one live smoke. This may create one private YouTube upload and send one approval mail."
  run gcloud run jobs execute "${YT_JOB_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --wait
else
  cat <<EOF

Live smoke was not executed.
After confirming the service/job update, run one manual private-upload smoke from an authenticated shell:

  gcloud run jobs execute ${YT_JOB_NAME} --project=${PROJECT_ID} --region=${REGION} --wait

EOF
fi

if [[ "${CREATE_SCHEDULER}" == "1" ]]; then
  SCHEDULER_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${YT_JOB_NAME}:run"
  if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --project="${PROJECT_ID}" --location="${REGION}" >/dev/null 2>&1; then
    run gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
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
    run gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
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
else
  echo "Scheduler skipped. Set CREATE_SCHEDULER=1 only after the private upload + mail + publish button smoke passes."
fi

run gcloud run jobs describe "${YT_JOB_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="table(name,template.template.containers[0].image,template.template.containers[0].args)"

run gcloud run services describe "${FETCHER_SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="table(metadata.name,status.latestReadyRevisionName,spec.template.spec.containers[0].image)"

if [[ "${CREATE_SCHEDULER}" == "1" ]]; then
  run gcloud scheduler jobs describe "${SCHEDULER_NAME}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --format="table(name,schedule,timeZone,state)"
fi
