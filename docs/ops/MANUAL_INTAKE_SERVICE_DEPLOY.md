# MANUAL-INTAKE-GCP-001 — manual_intake mobile-GUI / API service

Cloud Run service that wraps `src/tools/manual_intake.py` so an operator
can submit a URL or X status URL from a phone and create a WordPress
**draft** (never `publish`).

## Hard contract

- The service NEVER calls `wp.publish` or upgrades a draft to publish.
- The service NEVER calls Gemini, the X API, or RSS sources.
- The service NEVER scrapes article bodies.
- `memo` is operator-only audit; it never reaches body, source_text, or any
  Gemini prompt.
- `article_type` is a classification override only — never a source fact.
- The service NEVER sends a category **name** to WP. Names are resolved to
  numeric category_ids via `config/categories.json` before WP write.

## Routes

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET    | `/`                       | none | Mobile-first single-screen form |
| GET    | `/health`                 | none | Liveness probe — returns `{"ok": true}` |
| GET    | `/manifest.webmanifest`   | none | Minimal PWA manifest |
| POST   | `/manual-intake`          | required | Submit a URL — returns `manual_intake` JSON |

### `POST /manual-intake`

Accepts `application/x-www-form-urlencoded` or `application/json`. Token
must be present via `X-Manual-Intake-Token` header **or** `token` field in
the body.

| Field | Required | Notes |
|-------|----------|-------|
| `url` | yes | News article URL or X status URL |
| `mode` | no (default `dry-run`) | `draft` actually creates a WP draft |
| `article_type` | no (default `auto`) | `auto` or one of: 試合結果 / 試合速報 / 予告先発 / 公示 / 監督談話 / 選手コメント / 動画 / 成績 / 番組情報 / コラム / ニュース |
| `title` | no | Override OG title |
| `summary` | no | Override OG description |
| `source_published_at` | no | ISO 8601 — naive treated as JST, Z/UTC normalized to JST. Written to WP meta `_yoshilover_source_published_at`. |
| `memo` | no | Operator audit text only — never enters body |
| `token` | yes (or via header) | Equality check against `MANUAL_INTAKE_TOKEN` |

Response status codes:

| Code | Meaning |
|------|---------|
| 200 | success — JSON has `ok: true`, `category_ids`, `post_id` (when draft) |
| 400 | missing/invalid input (`missing_url`, `invalid_mode`, `invalid_article_type`, `invalid_source_published_at`, etc.) |
| 403 | token mismatch / absent |
| 409 | duplicate (history match) |
| 413 | body too large (>32 KiB) |
| 429 | rate-limited (5 requests / 60 s — same throttle as the CLI) |
| 502 | OG fetch failed (news URL with no manual title/summary) |
| 503 | `MANUAL_INTAKE_TOKEN` not configured on the service |

## Environment variables

Values reflect the production yoshilover Cloud Run setup
(project: `baseballsite`, region: `asia-northeast1`).

| Name | Required | Source | Production value / secret name |
|------|----------|--------|-------------------------------|
| `MANUAL_INTAKE_TOKEN` | yes | Secret Manager | `yoshilover-manual-intake-token` (NEW — to be created at deploy time) |
| `WP_URL` | yes | env (literal) | `https://yoshilover.com` |
| `WP_USER` | yes | env (literal) | `user` |
| `WP_APP_PASSWORD` | yes | Secret Manager | `yoshilover-wp-app-password` (existing — reused) |
| `PORT` | no (default 8080) | Cloud Run injects automatically | — |

The service does NOT require any other env: no Gemini key, no X API key,
no GCS bucket, no scheduler config.

## Local smoke

```bash
# Run the service locally (no WP creds needed for dry-run)
MANUAL_INTAKE_TOKEN=local-dev-token \
WP_URL=https://example.com \
WP_USER=u WP_APP_PASSWORD=p \
PORT=8080 \
python3 -m src.manual_intake_service

# In another shell — health
curl http://127.0.0.1:8080/health

# Form (open in a phone-like browser)
open http://127.0.0.1:8080/

# dry-run via curl
curl -X POST http://127.0.0.1:8080/manual-intake \
  -H "X-Manual-Intake-Token: local-dev-token" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://hochi.news/articles/x.html","mode":"dry-run","title":"巨人 試合速報 0-5 ヤクルト","summary":"ヤクルト戦敗戦","article_type":"試合結果"}'
```

## Build (local)

```bash
docker build -f Dockerfile.manual_intake_service -t manual-intake-service:dev .
docker run --rm -p 8080:8080 \
  -e MANUAL_INTAKE_TOKEN=local-dev-token \
  -e WP_URL=https://example.com \
  -e WP_USER=u -e WP_APP_PASSWORD=p \
  manual-intake-service:dev
```

## Deploy to Cloud Run (USER GO required)

All values below match the production yoshilover Cloud Run setup. Run from
the repo root on a workstation that already has gcloud authenticated to
the `baseballsite` project. **Claude / Codex must NOT run these commands.
They are user-go gated.**

```bash
# Constants (already aligned with prod yoshilover-fetcher).
export PROJECT=baseballsite
export REGION=asia-northeast1
export REPO=asia-northeast1-docker.pkg.dev/${PROJECT}/yoshilover
export IMAGE_TAG=$(git rev-parse --short HEAD)
export IMAGE=${REPO}/manual-intake-service:${IMAGE_TAG}
export SERVICE=manual-intake-service
export RUNTIME_SA=seo-web-runtime@${PROJECT}.iam.gserviceaccount.com
export OPERATOR_EMAIL=fwns6760@gmail.com   # confirm with user before running
```

### 1. Create the new token secret (one-time)

```bash
# Generate a fresh long random token. NEVER paste the token into chat,
# logs, or commits — only into the gcloud stdin below.
TOKEN_VALUE=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")

printf '%s' "${TOKEN_VALUE}" | gcloud secrets create yoshilover-manual-intake-token \
  --project=${PROJECT} \
  --replication-policy=automatic \
  --data-file=-

# Allow the runtime SA to read the new secret.
gcloud secrets add-iam-policy-binding yoshilover-manual-intake-token \
  --project=${PROJECT} \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/secretmanager.secretAccessor

# Print TOKEN_VALUE to a private channel only (e.g. the operator's password
# manager). Do NOT echo it to a shared terminal session.
unset TOKEN_VALUE
```

### 2. Build the image with Cloud Build

The repo ships `cloudbuild_manual_intake_service.yaml` (mirrors the
publish-notice / draft-body-editor pattern). Run from the repo root:

```bash
gcloud builds submit \
  --project=${PROJECT} \
  --config=cloudbuild_manual_intake_service.yaml \
  --substitutions=_TAG=${IMAGE_TAG}
```

Result: `${REPO}/manual-intake-service:${IMAGE_TAG}` (and `:latest` from
the YAML default if `_TAG` is omitted).

### 3. Deploy the service

```bash
gcloud run deploy ${SERVICE} \
  --project=${PROJECT} \
  --region=${REGION} \
  --image=${IMAGE} \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account=${RUNTIME_SA} \
  --min-instances=0 \
  --max-instances=2 \
  --concurrency=4 \
  --timeout=60s \
  --memory=256Mi \
  --cpu=1 \
  --set-env-vars=WP_URL=https://yoshilover.com,WP_USER=user \
  --set-secrets=WP_APP_PASSWORD=yoshilover-wp-app-password:latest,MANUAL_INTAKE_TOKEN=yoshilover-manual-intake-token:latest
```

### 4. Grant the operator's Google account `run.invoker`

The service must NOT be publicly invokable. Cloud Run IAM is the primary
boundary; the token is a secondary safeguard so the form on a phone can
authenticate cheaply once the user is signed in to Google.

```bash
gcloud run services add-iam-policy-binding ${SERVICE} \
  --project=${PROJECT} \
  --region=${REGION} \
  --member=user:${OPERATOR_EMAIL} \
  --role=roles/run.invoker
```

### 5. Smoke check after deploy

```bash
SERVICE_URL=$(gcloud run services describe ${SERVICE} \
  --project=${PROJECT} --region=${REGION} \
  --format='value(status.url)')

# (a) Health is unauthenticated path → 200 with valid IAM auth header.
curl -sS -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${SERVICE_URL}/health"
# → {"ok": true}

# (b) Form HTML loads.
curl -sS -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${SERVICE_URL}/" | head -20

# (c) End-to-end dry-run with the new token (token value re-fetched here
# from Secret Manager so the operator never has to memorize it):
TOKEN=$(gcloud secrets versions access latest \
  --project=${PROJECT} --secret=yoshilover-manual-intake-token)
curl -sS -X POST "${SERVICE_URL}/manual-intake" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "X-Manual-Intake-Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://hochi.news/articles/x.html","mode":"dry-run","title":"巨人 試合速報 0-5 ヤクルト","summary":"ヤクルト戦敗戦","article_type":"試合結果"}'
# → {"ok": true, "mode": "dry-run", "category_ids": [663], "article_type": "試合結果", ...}
unset TOKEN
```

Once the three smokes return clean, open `${SERVICE_URL}/` from the
operator's phone (after Google sign-in to the same account that holds
`run.invoker`) and submit a real `dry-run` first, then a `draft`.

## Rollback

```bash
PREV=$(gcloud run revisions list --project=${PROJECT} --service=${SERVICE} \
  --region=${REGION} --format='value(metadata.name)' --limit=2 | sed -n '2p')
gcloud run services update-traffic ${SERVICE} \
  --project=${PROJECT} --region=${REGION} --to-revisions=${PREV}=100
```

The service has no Scheduler / cron, no DB, and no GCS coupling — rollback
is a single traffic shift.

## What this service does NOT do

- Bypass guarded-publish gates (drafts go through the existing pipeline).
- Add or modify RSS sources.
- Send mail.
- Touch publish / X-post lanes.
- Loosen any source-fact requirement — `article_type` and `memo` are
  classification / audit metadata only.
