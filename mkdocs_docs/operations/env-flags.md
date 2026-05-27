# :material-cog-outline: 環境変数 / フィーチャーフラグ

ヨシラバーは挙動の多くを環境変数で切り替えている。
ここでは ==production の実値== を 2026-05-27 時点 (`gcloud run services/jobs describe`) で確認した範囲で記載する。

!!! danger "Secret は実値を書かない"

    Secret Manager に置いた値 (API key / app password など) は `valueFrom.secretKeyRef.name` だけ参照し、 ==実値は chat / log / commit / メールに貼らない==。

## :material-server: yoshilover-fetcher サービス

### :material-database: WP / GCS / 認証

| env | 実値 |
| --- | --- |
| `WP_URL` | `https://yoshilover.com` |
| `WP_USER` | `user` |
| `WP_APP_PASSWORD` | Secret: `yoshilover-wp-app-password` |
| `GCS_BUCKET` | `yoshilover-history` |
| `RUN_AUTH_MODE` | `cloud_run` |
| `RUN_SECRET` | Secret: `yoshilover-run-secret` |
| `RUN_OIDC_SERVICE_ACCOUNT` | `seo-web-runtime@baseballsite.iam.gserviceaccount.com` |
| `RUN_OIDC_AUDIENCE` | `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run` |
| `GOOGLE_CLOUD_PROJECT` | `baseballsite` |
| `INSIGHT_GCS_BUCKET` | `baseballsite-yoshilover-insight` |

### :material-robot: AI / コスト

| env | 実値 | 用途 |
| --- | --- | --- |
| `ARTICLE_AI_MODE` | none | 記事生成 LLM mode (現在は LLM 不使用) |
| `OFFDAY_ARTICLE_AI_MODE` | none | 試合のない日も LLM 不使用 |
| `X_POST_AI_MODE` | gemini | X 投稿テキスト生成は Gemini |
| `LOW_COST_MODE` | 1 | Gemini 呼び出しを抑制 |
| `STRICT_FACT_MODE` | 1 | 事実 gate を厳格化 |
| `GEMINI_STRICT_MAX_ATTEMPTS` | 3 | Gemini 厳格 mode 再試行 |
| `GEMINI_GROUNDED_MAX_ATTEMPTS` | 1 | Gemini grounded mode 再試行 |
| `ENABLE_ENHANCED_PROMPTS` | 1 | 拡張 prompt を使う |
| `ENABLE_GEMINI_PREFLIGHT` | 1 | Gemini 呼び出し前の preflight チェック |
| `ENABLE_PER_POST_24H_GEMINI_BUDGET` | 1 | 24h あたり 1 post の Gemini 呼び出し予算管理 |
| `GEMINI_API_KEY` | Secret: `gemini-api-key` |
| `GROK_API_KEY` | Secret: `yoshilover-grok-api-key` |

### :material-publish: 公開 / X 投稿

| env | 実値 | 用途 |
| --- | --- | --- |
| `RUN_DRAFT_ONLY` | True | Cloud Run 上で publish に flip しない |
| `PUBLISH_REQUIRE_IMAGE` | 1 | アイキャッチ無しの publish 禁止 |
| `AUTO_TWEET_ENABLED` | 0 | 自動 X 投稿停止 |
| `AUTO_TWEET_REQUIRE_IMAGE` | 1 | 画像無しの X 投稿禁止 |
| `X_POST_DAILY_LIMIT` | 10 | X 投稿の 1 日上限 |
| `FAN_REACTION_LIMIT` | 7 | ファン反応 記事の 1 日上限 |
| `AUTO_TWEET_CATEGORIES` | 試合速報,試合結果,…等 | 自動投稿対象カテゴリ |

### :material-toggle-switch: subtype 別 publish gate (=1 で公開対象)

| env | 実値 |
| --- | --- |
| `ENABLE_PUBLISH_FOR_POSTGAME` | 1 |
| `ENABLE_PUBLISH_FOR_LINEUP` | 1 |
| `ENABLE_PUBLISH_FOR_MANAGER` | 1 |
| `ENABLE_PUBLISH_FOR_NOTICE` | 1 |
| `ENABLE_PUBLISH_FOR_PREGAME` | 1 |
| `ENABLE_PUBLISH_FOR_RECOVERY` | 1 |
| `ENABLE_PUBLISH_FOR_FARM` | 1 |
| `ENABLE_PUBLISH_FOR_SOCIAL` | 1 |
| `ENABLE_PUBLISH_FOR_PLAYER` | 1 |
| `ENABLE_PUBLISH_FOR_GENERAL` | 0 |

### :material-toggle-switch-off: subtype 別 X-post gate (現在全部 =0)

`ENABLE_X_POST_FOR_POSTGAME` / `LINEUP` / `MANAGER` / `NOTICE` / `PREGAME` / `RECOVERY` / `FARM` / `SOCIAL` / `PLAYER` / `GENERAL` 全部 `0`。
==X 自動投稿は subtype レベルで全部停止==、 X 投稿は user 手動運用。

### :material-image: アイキャッチ

| env | 実値 |
| --- | --- |
| `EYECATCH_PLAYER_PRIORITY_DISABLED` | 1 |
| `EYECATCH_DEDUPE_RECENT_DISABLED` | 1 |

### :material-shield: 品質 gate flag (全部 =1)

??? abstract "クリックで展開"

    | env | 用途 |
    | --- | --- |
    | `ENABLE_BODY_CONTRACT_FAIL_LEDGER` | body contract 失敗の ledger |
    | `ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE` | subtype-aware narrow unlock |
    | `ENABLE_NARROW_UNLOCK_NON_POSTGAME` | postgame 以外の narrow unlock |
    | `ENABLE_POSTGAME_STRICT_FACT_RECOVERY` | postgame 厳格事実 recovery |
    | `ENABLE_WP_PUBLISH_STATUS_GUARD` | WP publish status のガード |
    | `ENABLE_WP_REVERT_AUDIT_LEDGER` | WP revert 監査 ledger |
    | `ENABLE_TITLE_GENERIC_COMPOUND_GUARD` | タイトル generic compound ガード |
    | `ENABLE_ACTIVE_TEAM_MISMATCH_GUARD` | 球団 mismatch ガード |
    | `ENABLE_ENTITY_MISMATCH_REPAIR` | 人物 mismatch 修復 |
    | `ENABLE_DUPLICATE_SENTENCE_GUARD` | 重複文ガード |
    | `ENABLE_BODY_TEMPLATE_V2` | 本文 template v2 |
    | `ENABLE_BODY_DUP_REDUCTION` | 本文重複削減 |
    | `ENABLE_BODY_LEAD_PARAPHRASE_GUARD` | リード文 paraphrase ガード |
    | `ENABLE_GENERIC_TITLE_REPAIR` | generic title 修復 |
    | `ENABLE_TITLE_HASHTAG_NAME_RECOVERY` | タイトル hashtag/name 回復 |
    | `ENABLE_QUOTE_INTEGRITY_GUARD` | 引用整合性ガード |
    | `ENABLE_H3_COUNT_GUARD` | H3 数ガード |
    | `ENABLE_FORBIDDEN_PHRASE_FILTER` | 禁止フレーズフィルタ |
    | `ENABLE_SOURCE_GROUNDING_STRICT` | source grounding 厳格 |
    | `ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR` | grounding drift 修復 |
    | `ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR` | 短 source の body 短縮修復 |
    | `ENABLE_SHORT_SOURCE_NARROW_TEMPLATE` | 短 source narrow template |
    | `ENABLE_FETCHER_STALE_SOURCE_GUARD` | stale source ガード |
    | `ENABLE_STALE_RSS_TRUSTED_BYPASS` | stale RSS の trusted bypass |
    | `STALE_RSS_WINDOW_TRUSTED_HOURS` | 48 (trusted bypass window) |
    | `ENABLE_RSS_SUBTYPE_CONSISTENCY_GUARD` | RSS subtype 整合性ガード |
    | `ENABLE_FARM_SUBTYPE_SPLIT` | farm subtype 分割 |
    | `ENABLE_FARM_CATEGORY_NARROW_FIX` | farm カテゴリ narrow fix |
    | `ENABLE_FARM_SHORT_POST_TEMPLATE` | farm 短 post template |
    | `ENABLE_PLAYER_VOICE_DIGEST_DETECTION` | player_voice digest 検知 |

### :material-email: メール送信 (mail bridge)

| env | 実値 |
| --- | --- |
| `MAIL_BRIDGE_SMTP_HOST` | `smtp.gmail.com` |
| `MAIL_BRIDGE_SMTP_PORT` | 465 |
| `MAIL_BRIDGE_SMTP_USERNAME` | `y.sebata@shiny-lab.org` |
| `MAIL_BRIDGE_FROM` | `y.sebata@shiny-lab.org` |
| `MAIL_BRIDGE_REPLY_TO` | `fwns6760@gmail.com` |
| `MAIL_BRIDGE_TO` | `fwns6760@gmail.com` |
| `MAIL_BRIDGE_GMAIL_APP_PASSWORD` | Secret: `yoshilover-shiny-lab-gmail-app-password` |
| `FACT_CHECK_EMAIL_TO` | `fwns6760@gmail.com` |
| `FACT_CHECK_EMAIL_FROM` | `fwns6760@gmail.com` |
| `GMAIL_APP_PASSWORD_SECRET_NAME` | `yoshilover-gmail-app-password` |

### :material-fast-forward: fetcher 内 inline draft notice

| env | 実値 |
| --- | --- |
| `ENABLE_FETCHER_INLINE_DRAFT_NOTICE` | 1 |
| `FETCHER_INLINE_DRAFT_NOTICE_INDIVIDUAL_LIMIT` | 5 |
| `FETCHER_INLINE_DRAFT_NOTICE_PART_SIZE` | 20 |
| `ENABLE_FETCHER_INLINE_DRAFT_NOTICE_REMOTE_QUEUE` | 1 |
| `FETCHER_INLINE_DRAFT_NOTICE_STATE_BUCKET` | `baseballsite-yoshilover-state` |
| `FETCHER_INLINE_DRAFT_NOTICE_STATE_PREFIX` | `publish_notice` |

### :material-cellphone-link: share-x ボタン

| env | 実値 |
| --- | --- |
| `ENABLE_SHARE_X_BUTTON` | 1 (fetcher 側) |

### :material-twitter: X API (Secret)

| env | Secret 名 |
| --- | --- |
| `X_API_KEY` | `yoshilover-x-api-key` |
| `X_API_SECRET` | `yoshilover-x-api-secret` |
| `X_ACCESS_TOKEN` | `yoshilover-x-access-token` |
| `X_ACCESS_TOKEN_SECRET` | `yoshilover-x-access-token-secret` |

X API tier は ==Free / write-only==。 投稿 (write) と media upload は可、 他人 timeline / search の read は 401。

## :material-cog: publish-notice ジョブ

| env | 実値 |
| --- | --- |
| `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP` | 1 |
| `ENABLE_PUBLISH_NOTICE_TWO_PHASE` | 1 |
| `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` | 1 |
| `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL` | 1 |
| `ENABLE_PUBLISH_NOTICE_CLASS_RESERVE` | 1 |
| `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR` | 1 |
| `ENABLE_PUBLISH_NOTICE_JUDGMENT_BATCH` | 1 |
| `ENABLE_PUBLISH_ONLY_MAIL_FILTER` | 0 |
| `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS` | 1 |
| `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS` | 1 |
| `ENABLE_SHARE_X_BUTTON` | ==0== (2026-05-27 user 判断で OFF) |

## :material-cog: x-post-mail-lane ジョブ

| env | 実値 |
| --- | --- |
| `INSIGHT_GCS_BUCKET` | `baseballsite-yoshilover-insight` |
| `FETCHER_PUBLIC_BASE_URL` | `https://yoshilover-fetcher-n5hunzkyna-an.a.run.app` |
| `ENABLE_SHARE_X_BUTTON` | 1 |
| `X_POST_MAIL_FAN_VOICE_ENABLED` | 0 |

## :material-console: 値の確認 / 変更コマンド

### 確認

```bash
# Cloud Run service の env
gcloud run services describe yoshilover-fetcher \
  --region=asia-northeast1 --project=baseballsite \
  --format="value(spec.template.spec.containers[0].env)" \
  | tr ';' '\n'

# Cloud Run job の env
gcloud run jobs describe publish-notice \
  --region=asia-northeast1 --project=baseballsite \
  --format="value(spec.template.spec.template.spec.containers[0].env)" \
  | tr ';' '\n'
```

### 変更 (image rebuild なし)

```bash
# job
gcloud run jobs update <JOB_NAME> \
  --region=asia-northeast1 --project=baseballsite \
  --update-env-vars=KEY=VALUE --quiet

# service
gcloud run services update <SERVICE_NAME> \
  --region=asia-northeast1 --project=baseballsite \
  --update-env-vars=KEY=VALUE --quiet
```

新 env は ==次回 execution から== 適用。

## :material-alert: 注意

- `.env` を shell で `source` しない (特殊文字で漏れる)。 `python-dotenv` 経由で扱う
- Secret 値は chat / log / commit / メールに貼らない
- `auth.json` の内容は絶対に出さない
