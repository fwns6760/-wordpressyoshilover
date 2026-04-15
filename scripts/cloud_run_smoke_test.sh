#!/usr/bin/env bash
set -euo pipefail

SERVICE="${SERVICE:-yoshilover-fetcher}"
REGION="${REGION:-asia-northeast1}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
EXPECTED_REVISION="${EXPECTED_REVISION:-${1:-}}"
LOG_WINDOW_MINUTES="${LOG_WINDOW_MINUTES:-30}"

if [[ -z "${PROJECT}" ]]; then
  echo "ERROR: PROJECT is empty. Set PROJECT or run: gcloud config set project <project-id>" >&2
  exit 1
fi

echo "Cloud Run smoke test"
echo "service=${SERVICE}"
echo "region=${REGION}"
echo "project=${PROJECT}"

service_json="$(gcloud run services describe "${SERVICE}" \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --format=json)"

latest_ready="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", {}).get("latestReadyRevisionName", ""))' <<<"${service_json}")"
image="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["spec"]["template"]["spec"]["containers"][0].get("image", ""))' <<<"${service_json}")"
run_draft_only="$(python3 -c 'import json,sys; data=json.load(sys.stdin); env=data["spec"]["template"]["spec"]["containers"][0].get("env", []); print({item.get("name"): item.get("value", "") for item in env}.get("RUN_DRAFT_ONLY", ""))' <<<"${service_json}")"
traffic_revision="$(python3 -c 'import json,sys; data=json.load(sys.stdin); traffic=data.get("status", {}).get("traffic", []); print(next((item.get("revisionName", "") for item in traffic if item.get("percent") == 100), ""))' <<<"${service_json}")"

echo "latest_ready_revision=${latest_ready}"
echo "traffic_100_revision=${traffic_revision}"
echo "image=${image}"
echo "RUN_DRAFT_ONLY=${run_draft_only}"

if [[ -z "${latest_ready}" ]]; then
  echo "ERROR: latest ready revision is empty" >&2
  exit 1
fi

if [[ -n "${EXPECTED_REVISION}" && "${latest_ready}" != "${EXPECTED_REVISION}" ]]; then
  echo "ERROR: expected revision ${EXPECTED_REVISION}, got ${latest_ready}" >&2
  exit 1
fi

if [[ "${traffic_revision}" != "${latest_ready}" ]]; then
  echo "ERROR: 100% traffic revision (${traffic_revision}) does not match latest ready revision (${latest_ready})" >&2
  exit 1
fi

if [[ "${run_draft_only}" != "1" ]]; then
  echo "ERROR: RUN_DRAFT_ONLY must remain 1, got '${run_draft_only}'" >&2
  exit 1
fi

cutoff="$(date -u -d "${LOG_WINDOW_MINUTES} minutes ago" '+%Y-%m-%dT%H:%M:%SZ')"
log_filter="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${SERVICE}\" AND resource.labels.revision_name=\"${latest_ready}\" AND timestamp>=\"${cutoff}\""
logs="$(gcloud logging read "${log_filter}" \
  --project "${PROJECT}" \
  --limit=20 \
  --format='value(timestamp,textPayload,jsonPayload.message)')"

if [[ -z "${logs}" ]]; then
  echo "ERROR: no recent logs found for revision ${latest_ready} since ${cutoff}" >&2
  exit 1
fi

echo
echo "recent logs for ${latest_ready}:"
echo "${logs}"
echo
echo "OK: Cloud Run revision is serving, RUN_DRAFT_ONLY=1, and recent logs exist."
