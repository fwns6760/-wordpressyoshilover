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

| Name | Required | Source | Notes |
|------|----------|--------|-------|
| `MANUAL_INTAKE_TOKEN` | yes | Secret Manager | Long random string. Distributed only to the operator's phone. |
| `WP_URL` | yes | env or Secret Manager | Existing yoshilover WP credential |
| `WP_USER` | yes | env or Secret Manager | Existing |
| `WP_APP_PASSWORD` | yes | Secret Manager | Existing |
| `PORT` | no (default 8080) | Cloud Run injects automatically | |

The service does NOT require any other env: no Gemini key, no GCS bucket,
no scheduler config.

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

The values below are placeholders — replace with the real project / region.
**Claude / Codex must NOT run these commands. They are user-go gated.**

1. Create the secret (one-time, replace the literal token):

   ```bash
   echo -n 'a-long-random-token' | gcloud secrets create manual-intake-token \
     --replication-policy=automatic --data-file=-
   ```

2. Build the image (Cloud Build):

   ```bash
   gcloud builds submit \
     --config=- \
     --substitutions=_IMAGE=gcr.io/$PROJECT_ID/manual-intake-service:$(git rev-parse --short HEAD) \
     . <<'YAML'
   steps:
     - name: gcr.io/cloud-builders/docker
       args: ['build', '-f', 'Dockerfile.manual_intake_service', '-t', '$_IMAGE', '.']
     - name: gcr.io/cloud-builders/docker
       args: ['push', '$_IMAGE']
   images:
     - '$_IMAGE'
   YAML
   ```

3. Deploy the service (require auth, low concurrency, min instances 0):

   ```bash
   gcloud run deploy manual-intake-service \
     --image=gcr.io/$PROJECT_ID/manual-intake-service:$(git rev-parse --short HEAD) \
     --region=$REGION \
     --platform=managed \
     --no-allow-unauthenticated \
     --min-instances=0 \
     --max-instances=2 \
     --concurrency=4 \
     --timeout=60s \
     --memory=256Mi \
     --cpu=1 \
     --set-env-vars=WP_URL=$WP_URL,WP_USER=$WP_USER \
     --set-secrets=WP_APP_PASSWORD=wp-app-password:latest,MANUAL_INTAKE_TOKEN=manual-intake-token:latest
   ```

4. Grant the operator's Google account `run.invoker` on the service. The
   service URL must NOT be publicly invokable: token alone is not the
   primary boundary — Cloud Run IAM is.

   ```bash
   gcloud run services add-iam-policy-binding manual-intake-service \
     --region=$REGION \
     --member=user:$OPERATOR_EMAIL --role=roles/run.invoker
   ```

5. Smoke check after deploy:

   ```bash
   TOKEN=$(gcloud auth print-identity-token)
   SERVICE_URL=$(gcloud run services describe manual-intake-service --region=$REGION --format='value(status.url)')
   curl -H "Authorization: Bearer $TOKEN" "$SERVICE_URL/health"
   # → {"ok": true}
   ```

   Then open `$SERVICE_URL/` from the operator's phone (after Google
   sign-in) and submit a `dry-run` first.

## Rollback

```bash
gcloud run services update-traffic manual-intake-service \
  --region=$REGION --to-revisions=<PREVIOUS_REVISION>=100
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
