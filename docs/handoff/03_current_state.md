# 現在の本番状態（2026-04-18 朝時点）

## 稼働中revision

```
yoshilover-fetcher-00130-nxg
```

## 現在のenv（安全側・全フラグ0）

```
RUN_DRAFT_ONLY=1              ← 安全側。0にするとpublish可能になる
AUTO_TWEET_ENABLED=0          ← 安全側。1にするとX自動投稿開始
PUBLISH_REQUIRE_IMAGE=1       ← 画像なし記事はpublish禁止

# カテゴリ別publishフラグ（全0）
ENABLE_PUBLISH_FOR_POSTGAME=0
ENABLE_PUBLISH_FOR_LINEUP=0
ENABLE_PUBLISH_FOR_MANAGER=0
ENABLE_PUBLISH_FOR_NOTICE=0
ENABLE_PUBLISH_FOR_PREGAME=0
ENABLE_PUBLISH_FOR_RECOVERY=0
ENABLE_PUBLISH_FOR_FARM=0
ENABLE_PUBLISH_FOR_SOCIAL=0
ENABLE_PUBLISH_FOR_PLAYER=0
ENABLE_PUBLISH_FOR_GENERAL=0

# カテゴリ別X投稿フラグ（全0）
ENABLE_X_POST_FOR_POSTGAME=0
ENABLE_X_POST_FOR_LINEUP=0
ENABLE_X_POST_FOR_MANAGER=0
ENABLE_X_POST_FOR_NOTICE=0
ENABLE_X_POST_FOR_PREGAME=0
ENABLE_X_POST_FOR_RECOVERY=0
ENABLE_X_POST_FOR_FARM=0
ENABLE_X_POST_FOR_SOCIAL=0
ENABLE_X_POST_FOR_PLAYER=0
ENABLE_X_POST_FOR_GENERAL=0

# live_update（常時禁止）
ENABLE_PUBLISH_FOR_LIVE_UPDATE=0
ENABLE_X_POST_FOR_LIVE_UPDATE=0

# AI設定
ARTICLE_AI_MODE=gemini
X_POST_AI_MODE=gemini         ← Gemini AI有効
GEMINI_STRICT_MAX_ATTEMPTS=3
GEMINI_GROUNDED_MAX_ATTEMPTS=1
LOW_COST_MODE=1
STRICT_FACT_MODE=1
AI_ENABLED_CATEGORIES=試合速報,選手情報,首脳陣

# メール通知
FACT_CHECK_EMAIL_TO=fwns6760@gmail.com
FACT_CHECK_EMAIL_FROM=fwns6760@gmail.com
GMAIL_APP_PASSWORD_SECRET_NAME=yoshilover-gmail-app-password
```

## Scheduler稼働状況

| Job名 | スケジュール | 状態 |
|-------|-----------|------|
| `rss-fetcher-scheduled` | 07:00/12:00/17:00/22:00 JST | 稼働中 |
| `fact-check-morning-report` | 07:00/12:00/17:00/22:00 JST | 稼働中（2026-04-18朝から） |

## Secret Manager状態

| Secret名 | 状態 |
|---------|------|
| `yoshilover-gmail-app-password` | version 1 ENABLED（2026-04-18朝に登録済み） |
| WP認証系 / X API系 | 登録済み（詳細は `.env.example` 参照） |

確認コマンド:
```bash
gcloud secrets versions list yoshilover-gmail-app-password --project baseballsite
```

## テスト数

```
358テスト / 全PASS（2026-04-18朝時点）
```

確認コマンド:
```bash
cd /home/fwns6/code/wordpressyoshilover && python -m pytest --tb=short -q
```

## WordPress状態

- 既存記事はサブドメインへ301リダイレクト移行中
- 2026-04-17の事故で公開された4記事はdraftに戻し済み
- 現在はdraft生成のみ蓄積中（Phase C受け入れ待ち）

## Cloud Run確認コマンド

```bash
# 現在のrevision確認
gcloud run revisions list --service yoshilover-fetcher --project baseballsite --region asia-northeast1 --limit=5

# 現在のenv確認
gcloud run services describe yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --format='value(spec.template.spec.containers[0].env)'

# 直近のログ確認
gcloud logging read 'resource.type="cloud_run_revision"' \
  --project baseballsite \
  --limit=50 \
  --format=json
```
