#!/usr/bin/env bash
# CARE LAND 発達障害・福祉ニュース版 デプロイ（baseballsite とは別の GCP プロジェクト）。
#
# 構成:
#   - Cloud Run Job:   取得 + AI判定(gemini-3.1-flash-lite) + 確認メール送信（draftのみ。自動公開なし）
#   - Cloud Scheduler: 1日3回 朝8時 / 12時 / 15時 (Asia/Tokyo)
#   - GCS:             重複防止 ledger を永続化（Job は揮発のため必須）
#
# 使い方:
#   export CARELAND_GCP_PROJECT=<careland専用プロジェクトID>
#   bash scripts/deploy_careland_news_sns.sh prereqs   # 初回のみ: API/AR/SA/IAM/Secret/Bucket
#   bash scripts/deploy_careland_news_sns.sh deploy     # ビルド + Job + Scheduler
#   bash scripts/deploy_careland_news_sns.sh test       # 手動実行(1回)
set -euo pipefail

PROJECT="${CARELAND_GCP_PROJECT:?set CARELAND_GCP_PROJECT}"
REGION="${REGION:-asia-northeast1}"
AR_REPO="${AR_REPO:-careland}"
JOB="${JOB:-careland-news-sns}"
BUCKET="${BUCKET:-${PROJECT}-careland-news}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/careland-news-sns:latest-job"
SA_NAME="${SA_NAME:-careland-news-sns}"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
MAIL_TO="${CARELAND_NEWS_MAIL_TO:-y.sebata@shiny-lab.org}"
MAIL_FROM="${CARELAND_MAIL_FROM:-fwns6760@gmail.com}"
# share-x-cand（図カードを画像つきでXへ）の公開サービス URL。これと bucket / flag /
# 署名secret を毎回 deploy に含めることで「再デプロイで share env が消える」事故を防ぐ。
SHARE_FETCHER_BASE="${CARELAND_FETCHER_BASE_URL:-https://careland-share-362305411163.asia-northeast1.run.app}"
CMD="${1:-deploy}"

prereqs() {
  echo "==> enable APIs"
  gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com cloudbuild.googleapis.com \
    secretmanager.googleapis.com storage.googleapis.com --project "${PROJECT}"

  echo "==> Artifact Registry repo"
  gcloud artifacts repositories create "${AR_REPO}" --repository-format=docker \
    --location "${REGION}" --project "${PROJECT}" 2>/dev/null || echo "(repo exists)"

  echo "==> GCS bucket for ledger"
  gcloud storage buckets create "gs://${BUCKET}" --location "${REGION}" \
    --project "${PROJECT}" 2>/dev/null || echo "(bucket exists)"

  echo "==> service account"
  gcloud iam service-accounts create "${SA_NAME}" --project "${PROJECT}" \
    --display-name "CARE LAND news sns" 2>/dev/null || echo "(sa exists)"

  echo "==> IAM: secret accessor + GCS + run invoker(self)"
  for ROLE in roles/secretmanager.secretAccessor roles/storage.objectAdmin roles/run.invoker; do
    gcloud projects add-iam-policy-binding "${PROJECT}" \
      --member "serviceAccount:${SA}" --role "${ROLE}" --quiet >/dev/null
  done

  echo "==> Secrets（値は対話で貼り付け。Ctrl-D で確定）"
  # 記事化フェーズ: gemini / gmail / wp-app-password。
  for S in careland-gemini-api-key careland-gmail-app-password careland-wp-app-password; do
    if ! gcloud secrets describe "${S}" --project "${PROJECT}" >/dev/null 2>&1; then
      echo "  -- ${S} の値を入力してください:"
      gcloud secrets create "${S}" --replication-policy=automatic --project "${PROJECT}" --data-file=-
    else
      echo "  (${S} exists)"
    fi
  done
  echo "prereqs done."
}

deploy() {
  echo "==> build image"
  gcloud builds submit --project "${PROJECT}" --config cloudbuild_careland_news_sns.yaml \
    --substitutions="_PROJECT_ID=${PROJECT},_AR_REPO=${AR_REPO},_REGION=${REGION}"

  echo "==> deploy Cloud Run Job"
  gcloud run jobs deploy "${JOB}" \
    --image "${IMAGE}" --region "${REGION}" --project "${PROJECT}" \
    --service-account "${SA}" \
    --set-env-vars "^|^GOOGLE_CLOUD_PROJECT=${PROJECT}|WP_URL=https://careland.org|WP_USER=yoshilover|RUN_DRAFT_ONLY=1|ENABLE_FAN_VOICE_ENSURE=0|CARELAND_WP_ADMIN_BASE=https://careland.org|CARELAND_NEWS_MAIL_TO=${MAIL_TO}|MAIL_BRIDGE_FROM=${MAIL_FROM}|MAIL_BRIDGE_SMTP_USERNAME=${MAIL_FROM}|CARELAND_NEWS_MAX_ITEMS_PER_SOURCE=60|GEMINI_PRIMARY_MODEL=gemini-3.1-flash-lite|GEMINI_FALLBACK_MODEL=gemini-3.1-flash-lite|CARELAND_NEWS_LEDGER_GCS_URI=gs://${BUCKET}/careland_news_ledger.jsonl|CARELAND_SHARE_GCS_BUCKET=${BUCKET}|CARELAND_FETCHER_BASE_URL=${SHARE_FETCHER_BASE}|ENABLE_SHARE_X_BUTTON=1" \
    --set-secrets "GEMINI_API_KEY=careland-gemini-api-key:latest,MAIL_BRIDGE_GMAIL_APP_PASSWORD=careland-gmail-app-password:latest,SHARE_X_CAND_TOKEN_SECRET=careland-share-x-token-secret:latest,WP_APP_PASSWORD=careland-wp-app-password:latest,PUBLISH_BUTTON_TOKEN_SECRET=careland-share-x-token-secret:latest" \
    --args="--no-create-drafts" \
    --max-retries 1 --task-timeout 600s
  # 記事化OFF（2026-06-27 ユーザー方針: ポスト(メール/X候補)だけ残し記事化はやめる）:
  # --no-create-drafts で WordPress 下書きを作らない。x_article 候補もメール上は投稿候補扱い。

  # 配信スケジュール: 既定は朝8時から3時間ごと5回 (08/11/14/17/20 JST) を 1 本で。
  # CARELAND_NEWS_SCHEDULE で cron を上書き可（例: 日中2.5h "0 8,13,18 * * *" + 別途:30本）。
  SCHED="${CARELAND_NEWS_SCHEDULE:-0 8,11,14,17,20 * * *}"
  NAME="${JOB}-daytime"
  echo "==> Cloud Scheduler 1本 (${NAME}: ${SCHED} JST)"
  RUN_URL="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB}:run"
  gcloud scheduler jobs create http "${NAME}" --project "${PROJECT}" --location "${REGION}" \
    --schedule "${SCHED}" --time-zone "Asia/Tokyo" \
    --uri "${RUN_URL}" --http-method POST --oauth-service-account-email "${SA}" 2>/dev/null || \
  gcloud scheduler jobs update http "${NAME}" --project "${PROJECT}" --location "${REGION}" \
    --schedule "${SCHED}" --time-zone "Asia/Tokyo" \
    --uri "${RUN_URL}" --http-method POST --oauth-service-account-email "${SA}"
  # 旧 08/12/15 の3本が残っていたら掃除（存在しなければ無視）。
  for H in 8 12 15; do
    gcloud scheduler jobs delete "${JOB}-at-${H}" --project "${PROJECT}" --location "${REGION}" --quiet 2>/dev/null || true
  done
  echo "deploy done."
}

test_run() {
  gcloud run jobs execute "${JOB}" --region "${REGION}" --project "${PROJECT}" --wait
}

# 公開サービス careland-share（share-x-cand ＋ yoshilover型 /publish-and-tweet 公開エンドポイント）。
# job と同じイメージを `python3 -m src.careland_share_server` で起動。WP認証＋token secret を投入。
# PUBLISH_BUTTON_TOKEN_SECRET は job 側と同一 secret を使う（token 署名鍵の一致が必須）。
# PUBLISH_BUTTON_X_BRAND_TAG="" ＝ careland は X 投稿に署名を付けない（署名なし方針）。
deploy_share() {
  echo "==> deploy careland-share service (share-x-cand + /publish-and-tweet)"
  gcloud run deploy careland-share \
    --image "${IMAGE}" \
    --region "${REGION}" --project "${PROJECT}" \
    --service-account "${SA}" \
    --allow-unauthenticated \
    --command python3 --args="-m,src.careland_share_server" \
    --set-env-vars "^|^CARELAND_SHARE_GCS_BUCKET=${BUCKET}|CARELAND_FETCHER_BASE_URL=${SHARE_FETCHER_BASE}|WP_URL=https://careland.org|WP_USER=yoshilover|PUBLISH_BUTTON_X_BRAND_TAG=" \
    --set-secrets "SHARE_X_CAND_TOKEN_SECRET=careland-share-x-token-secret:latest,WP_APP_PASSWORD=careland-wp-app-password:latest,PUBLISH_BUTTON_TOKEN_SECRET=careland-share-x-token-secret:latest"
}

# 手動記事化サービス careland-manual-intake（URLを貼って引用記事下書きを作る人手画面）。
# 自動記事化(job --no-create-drafts)は OFF のまま。記事化は「人が選んだURLだけ」手動で行う運用。
# job と同じイメージを `python3 -m src.careland_manual_intake_service` で起動。
# 認証: yoshilover と同じく既定はトークン無し＝開放（ログイン手順なし）。ロックしたい場合だけ
# CARELAND_MANUAL_INTAKE_TOKEN を Secret 経由で渡せば gate される。
deploy_manual_intake() {
  echo "==> deploy careland-manual-intake service (手動記事化)"
  gcloud run deploy careland-manual-intake \
    --image "${IMAGE}" \
    --region "${REGION}" --project "${PROJECT}" \
    --service-account "${SA}" \
    --allow-unauthenticated \
    --command python3 --args="-m,src.careland_manual_intake_service" \
    --set-env-vars "^|^WP_URL=https://careland.org|WP_USER=yoshilover|GEMINI_PRIMARY_MODEL=gemini-3.1-flash-lite|GEMINI_FALLBACK_MODEL=gemini-3.1-flash-lite|ENABLE_FAN_VOICE_ENSURE=0" \
    --set-secrets "WP_APP_PASSWORD=careland-wp-app-password:latest,GEMINI_API_KEY=careland-gemini-api-key:latest"
}

case "${CMD}" in
  prereqs) prereqs ;;
  deploy)  deploy; deploy_share; deploy_manual_intake ;;
  share)   deploy_share ;;
  manual)  deploy_manual_intake ;;
  test)    test_run ;;
  all)     prereqs; deploy; deploy_share; deploy_manual_intake; test_run ;;
  *) echo "usage: $0 {prereqs|deploy|share|manual|test|all}"; exit 1 ;;
esac
