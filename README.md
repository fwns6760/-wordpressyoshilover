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
```

## セットアップ

```bash
# 依存パッケージ
pip install -r requirements.txt

# ローカル実行
python3 src/rss_fetcher.py

# ドライラン（WP投稿なし）
python3 src/rss_fetcher.py --dry-run
```

## GCP / Cloud Run デプロイ

```bash
# Docker ビルド & Cloud Run デプロイ
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher
gcloud run deploy yoshilover-fetcher \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/fetcher \
  --region asia-northeast1 \
  --set-env-vars "$(cat .env | tr '\n' ',')"
```

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
