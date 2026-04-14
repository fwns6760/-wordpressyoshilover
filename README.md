# yoshilover — 読売ジャイアンツ 自動記事生成システム

読売ジャイアンツの最新ニュースを RSS で収集し、Grok AI（Web検索＋X検索）で記事・ファン反応を自動生成して WordPress に投稿するシステムです。

## システム構成

```
RSS フィード / NPB公式
        ↓
  rss_fetcher.py
  ├─ 試合日チェック（オフ日スキップ）
  ├─ 重複除去（GCS: yoshilover-history）
  ├─ 記事画像スクレイピング（最大3枚）
  └─ Grok Responses API
       ├─ Web検索（最新ニュース）
       ├─ X検索（当日ファン反応 15件）
       └─ 記事生成（要約・記録・感想）
              ↓
        wp_client.py
        WordPress REST API
              ↓
       yoshilover.com
              ↓
    x_post_generator.py
        X（Twitter）投稿
```

## 記事レイアウト

1. グラデーションバナー（媒体名バッジ＋記事タイトル・巨人カラー紺→赤）
2. OGP写真（ソース記事から1枚目）
3. 今日のジャイアンツ要約（3〜4文・ですます調）
4. 📊 今日の記録（箇条書き 8〜12項目）
5. 💬 コメントボタン①（小さめ・アウトライン）
6. 💬 ファンの声（Xより）（Xカード形式・15件・感情多様）
7. ⚾ 今日の感想（300文字・ですます調）+ 記事内画像 2〜3枚
8. 💬 コメントボタン②（オレンジ塗り #F5811F）
9. 出典（NPB公式・スポーツナビ・元記事）

## 主な機能

- **オフ日スキップ**: NPB公式の日程ページを確認し、巨人戦がない日は記事生成をスキップ
- **重複除去**: GCS バケット `yoshilover-history` で処理済み URL を管理
- **画像スクレイピング**: ソース記事から OGP 画像＋本文画像を最大3枚取得
- **Grok AI**: Web検索＋X検索（当日のみ）でリアルタイム情報を取得
- **ファン反応15件**: 多様な感情（喜び・驚き・批判・期待など）を15件収集
- **ニックネーム検索**: 芽ネギ・大王・たけまる・マタ など巨人選手のニックネームでX検索

## 環境変数（`.env`）

```env
WP_URL=https://yoshilover.com
WP_USER=your_wp_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
GROK_API_KEY=xai-xxxxxxxxxxxxxxxx
X_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxx
X_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxx
X_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxx
X_ACCESS_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxx
GCS_BUCKET=yoshilover-history
RUN_SECRET=change-this-to-a-long-random-secret
RUN_AUTH_MODE=secret
RUN_OIDC_SERVICE_ACCOUNT=
RUN_OIDC_AUDIENCE=
ENABLE_TEST_GEMINI=0
LOW_COST_MODE=1
STRICT_FACT_MODE=1
AI_ENABLED_CATEGORIES=試合速報,選手情報,首脳陣
ARTICLE_AI_MODE=gemini
OFFDAY_ARTICLE_AI_MODE=none
X_POST_AI_MODE=none
X_POST_AI_CATEGORIES=試合速報,選手情報,首脳陣
X_POST_DAILY_LIMIT=5
FAN_REACTION_LIMIT=5
AUTO_TWEET_ENABLED=0
```

ローカルや単純な HTTP 実行では `RUN_AUTH_MODE=secret` と `RUN_SECRET` を使います。Cloud Run 本番は `RUN_AUTH_MODE=cloud_run` にして、`RUN_OIDC_SERVICE_ACCOUNT` と `RUN_OIDC_AUDIENCE` で Cloud Scheduler の OIDC トークンを検証します。`/test-gemini` はデフォルトで無効で、使う場合だけ `ENABLE_TEST_GEMINI=1` を設定してください。
`LOW_COST_MODE=1` では、既定で `試合速報 / 選手情報 / 首脳陣` だけ記事AIを有効にし、オフ日は記事AIを止め、X投稿文もテンプレート運用に落とします。`STRICT_FACT_MODE=1` を有効にすると、元記事タイトルと要約にない数字・スコア・出典っぽい記述を検出した場合に、安全な定型記事へ自動フォールバックします。

## セットアップ

```bash
# 依存パッケージ
pip install -r requirements.txt

# ローカル実行
python3 src/rss_fetcher.py

# ドライラン（WP投稿なし）
python3 src/rss_fetcher.py --dry-run

# WordPress 品質確認用: 下書きだけ作って記事AIを Grok に固定
python3 src/rss_fetcher.py --limit 1 --draft-only --article-ai-mode grok
```

## GCP / Cloud Run デプロイ

```bash
# Docker ビルド & Cloud Run デプロイ
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher
gcloud run deploy yoshilover-fetcher \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher \
  --region asia-northeast1 \
  --set-env-vars WP_URL=https://yoshilover.com,WP_USER=your_wp_username,GCS_BUCKET=yoshilover-history,RUN_AUTH_MODE=cloud_run,RUN_OIDC_SERVICE_ACCOUNT=seo-web-runtime@baseballsite.iam.gserviceaccount.com,RUN_OIDC_AUDIENCE=https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run,ENABLE_TEST_GEMINI=0,LOW_COST_MODE=1,STRICT_FACT_MODE=1,AI_ENABLED_CATEGORIES=試合速報\\,選手情報\\,首脳陣,ARTICLE_AI_MODE=gemini,OFFDAY_ARTICLE_AI_MODE=none,X_POST_AI_MODE=none,X_POST_AI_CATEGORIES=試合速報\\,選手情報\\,首脳陣,X_POST_DAILY_LIMIT=5,FAN_REACTION_LIMIT=5,AUTO_TWEET_ENABLED=0 \
  --set-secrets WP_APP_PASSWORD=yoshilover-wp-app-password:latest,RUN_SECRET=yoshilover-run-secret:latest,GEMINI_API_KEY=gemini-api-key:latest,GROK_API_KEY=yoshilover-grok-api-key:latest,X_API_KEY=yoshilover-x-api-key:latest,X_API_SECRET=yoshilover-x-api-secret:latest,X_ACCESS_TOKEN=yoshilover-x-access-token:latest,X_ACCESS_TOKEN_SECRET=yoshilover-x-access-token-secret:latest
```

Cloud Run では `.env` をそのまま `--set-env-vars` に流さず、秘密情報は必ず Secret Manager 経由で渡します。
Cloud Scheduler から `/run` を叩くときは、`oidc-service-account-email` と `oidc-token-audience` を付けて Cloud Run IAM で認証します。

### Cloud Scheduler ジョブ

| ジョブ名 | スケジュール | 用途 |
|---------|-------------|------|
| giants-weekday-night | 平日 18:00〜23:30（30分ごと） | 平日ナイター対応 |
| giants-weekend-day   | 土日 11:00〜17:30（30分ごと） | デーゲーム対応 |
| giants-weekend-night | 土日 20:00〜23:30（30分ごと） | 土日ナイター対応 |

## RSSソース

- スポーツ報知 / 日刊スポーツ / サンスポ / 東スポ
- ベースボールキング / Full-Count / 産経
- Google News（巨人・ジャイアンツ・読売）
- RSSHub 経由 X アカウント（@TokyoGiants 等）

## ディレクトリ構成

```
.
├── Dockerfile
├── requirements.txt
├── publish_post.sh
├── src/
│   ├── rss_fetcher.py       # メイン記事生成
│   ├── server.py            # Cloud Run HTTP サーバー
│   ├── x_post_generator.py  # X投稿生成
│   ├── wp_client.py         # WordPress REST API クライアント
│   └── wp_draft_creator.py  # 下書き作成ユーティリティ
└── config/
    ├── rss_sources.json     # RSSソース定義
    └── keywords.json        # キーワード設定
```

## Grok API 仕様

- エンドポイント: `https://api.x.ai/v1/responses`
- モデル: `grok-4-1-fast-reasoning`
- ツール: `web_search` + `x_search`（当日のみ `from_date=today`）
- レスポンス解析: `output[]` → `type=="message"` → `content[0].output_text.text`
