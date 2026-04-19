# yoshilover

読売ジャイアンツ特化の WordPress 記事生成リポジトリです。  
RSS と記者・球団 X アカウントを監視し、記事候補を作って `yoshilover.com` に下書きまたは公開投稿します。

## 現在の運用

- 本番は Cloud Run + Cloud Scheduler で動作
- 現在は `RUN_DRAFT_ONLY=1` で、`/run` 実行時は `下書き作成のみ`
- 品質調整が終わるまでは、人が下書きを見て公開判断する前提
- `PUBLISH_REQUIRE_IMAGE=1` により、`news` / `social_news` でアイキャッチが取れない記事は公開しない

## 何をするコードか

中心は [src/rss_fetcher.py](src/rss_fetcher.py) です。ざっくりこの流れで動きます。

1. RSS と `social_news` ソースを取得
2. 巨人関連記事だけに絞る
3. 重複チェック
4. カテゴリ分類
5. タイトルを整形
6. 記事画像を取得
7. WordPress に投稿
8. 条件を満たせば公開・X投稿

補助スクリプトは次です。

- [src/server.py](src/server.py): Cloud Run の `/run` エンドポイント
- [src/wp_client.py](src/wp_client.py): WordPress REST API クライアント
- [src/x_post_generator.py](src/x_post_generator.py): X 投稿文生成
- [src/wp_draft_creator.py](src/wp_draft_creator.py): 手動で X URL から下書き作成
- [src/x_api_client.py](src/x_api_client.py): X API 投稿 / 収集
- [src/manual_post.py](src/manual_post.py): 手動記事投稿

## ソースの考え方

`config/rss_sources.json` には 2 種類あります。

- `news`: 新聞社・メディアの RSS
- `social_news`: 球団公式や記者 X を RSSHub 経由で取得

今の方針はこれです。

- `news` は本文材料として比較的安定
- `social_news` は速報検知として有効
- ただし `social_news` はノイズが多いので、URL・ハッシュタグ・媒体名混入や動画プロモは落とす
- 記事品質を見ている間は `draft-only` で回す

## ディレクトリ

```text
.
├── config/
│   ├── keywords.json
│   └── rss_sources.json
├── data/
├── src/
│   ├── manual_post.py
│   ├── rss_fetcher.py
│   ├── server.py
│   ├── wp_client.py
│   ├── wp_draft_creator.py
│   ├── x_api_client.py
│   └── x_post_generator.py
├── tests/
├── Dockerfile
├── requirements.txt
└── .env.example
```

## 必要な環境変数

最低限これが必要です。

```env
WP_URL=https://yoshilover.com
WP_USER=
WP_APP_PASSWORD=
RUN_SECRET=change-this-to-a-long-random-secret
RUN_AUTH_MODE=secret
RUN_DRAFT_ONLY=0
LOW_COST_MODE=1
STRICT_FACT_MODE=1
ARTICLE_AI_MODE=gemini
OFFDAY_ARTICLE_AI_MODE=none
ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME=0
PUBLISH_REQUIRE_IMAGE=1
AUTO_TWEET_ENABLED=1
AUTO_TWEET_REQUIRE_IMAGE=1
ENABLE_X_COLLECT=0
```

Cloud Run では追加で次を使います。

```env
RUN_AUTH_MODE=cloud_run
RUN_OIDC_SERVICE_ACCOUNT=
RUN_OIDC_AUDIENCE=
GCS_BUCKET=yoshilover-history
```

補足:

- `RUN_DRAFT_ONLY=1`: Scheduler 実行で公開せず下書きだけ作る
- `PUBLISH_REQUIRE_IMAGE=1`: アイキャッチが取れない記事は公開しない
- `AUTO_TWEET_REQUIRE_IMAGE=1`: アイキャッチがない記事は X 自動投稿しない
- `ENABLE_X_COLLECT=0`: X API の収集を止め、read/search 課金を抑える
- `LOW_COST_MODE=1`: AI 呼び出しをかなり絞る
- `ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME=0`: postgame 向け structured-parts renderer の待機フラグ。本便では live path 未接続

## ローカル実行

依存インストール:

```bash
pip install -r requirements.txt
```

通常実行:

```bash
python3 src/rss_fetcher.py
```

公開せず結果だけ見る:

```bash
python3 src/rss_fetcher.py --dry-run
```

下書きだけ作る:

```bash
python3 src/rss_fetcher.py --draft-only
```

直近の下書きを source 別 / 記事型別に棚卸し:

```bash
python3 src/draft_audit.py --limit 15
```

件数を絞って確認:

```bash
python3 src/rss_fetcher.py --limit 3 --draft-only
```

X URL から手動で下書きを作る:

```bash
python3 src/wp_draft_creator.py --url https://x.com/... --category 試合速報
```

WP 投稿から X 文案を作る:

```bash
python3 src/x_post_generator.py --post-id 123
```

## テスト

日常的に見るべきものはこれで十分です。

```bash
python3 -m unittest tests.test_server tests.test_yahoo_realtime tests.test_wp_client tests.test_build_news_block
python3 -m py_compile src/server.py src/rss_fetcher.py src/wp_client.py src/x_post_generator.py
```

## Cloud Run

Cloud Run の `POST /run` は [src/server.py](src/server.py) から [src/rss_fetcher.py](src/rss_fetcher.py) を実行します。

- `RUN_DRAFT_ONLY=0`: 通常モード
- `RUN_DRAFT_ONLY=1`: `rss_fetcher.py --draft-only`

認証モード:

- `RUN_AUTH_MODE=secret`: `X-Secret` ヘッダを使う
- `RUN_AUTH_MODE=cloud_run`: OIDC トークンを検証する

本番では `cloud_run` を使う想定です。

## 本番デプロイ運用

受け入れ試験中の本番基準は次です。

- `RUN_DRAFT_ONLY=1`
- `AUTO_TWEET_ENABLED=0`
- `PUBLISH_REQUIRE_IMAGE=1`

本番デプロイ後は必ず smoke test を実行します。

```bash
bash scripts/cloud_run_smoke_test.sh
```

運用ルール:

- `RUN_DRAFT_ONLY=1` を維持したままデプロイする
- `RUN_DRAFT_ONLY=1` 以外の変更は事前承認必須
- smoke test が失敗した状態で Scheduler を継続稼働させない

意図しない変更が見つかった場合の復旧手順:

1. `gcloud run services describe yoshilover-fetcher --project baseballsite --region asia-northeast1`
2. `bash scripts/cloud_run_smoke_test.sh` で逸脱項目を確認
3. 直前の安全 revision に `gcloud run services update-traffic ... --to-revisions SAFE_REVISION=100` で戻す
4. `RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` / `PUBLISH_REQUIRE_IMAGE=1` を再確認
5. smoke test を再実行して成功を確認してから運用へ戻す

## デプロイ例

```bash
gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher:local-test

gcloud run deploy yoshilover-fetcher \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher:local-test \
  --region asia-northeast1 \
  --set-env-vars WP_URL=https://yoshilover.com,WP_USER=your_wp_username,GCS_BUCKET=yoshilover-history,RUN_AUTH_MODE=cloud_run,RUN_DRAFT_ONLY=1,RUN_OIDC_SERVICE_ACCOUNT=your-service-account,RUN_OIDC_AUDIENCE=https://your-service-url/run,LOW_COST_MODE=1,STRICT_FACT_MODE=1,ARTICLE_AI_MODE=gemini,OFFDAY_ARTICLE_AI_MODE=none,GEMINI_STRICT_MAX_ATTEMPTS=3,PUBLISH_REQUIRE_IMAGE=1,AUTO_TWEET_ENABLED=1,AUTO_TWEET_REQUIRE_IMAGE=1,ENABLE_X_COLLECT=0 \
  --set-secrets WP_APP_PASSWORD=yoshilover-wp-app-password:latest,RUN_SECRET=yoshilover-run-secret:latest,GEMINI_API_KEY=gemini-api-key:latest,GROK_API_KEY=yoshilover-grok-api-key:latest,X_API_KEY=yoshilover-x-api-key:latest,X_API_SECRET=yoshilover-x-api-secret:latest,X_ACCESS_TOKEN=yoshilover-x-access-token:latest,X_ACCESS_TOKEN_SECRET=yoshilover-x-access-token-secret:latest
```

## 今の品質課題

今見ているポイントはこの3つです。

- `social_news` のノイズをどこまで絞るか
- `試合速報` のテンプレ記事をどこまで減らすか
- コメント記事 / 1プレー深掘り / 起用整理の精度をどう上げるか

そのため、しばらくは `draft-only` で回し、下書きを見てソースと記事型を選別する運用にしています。
