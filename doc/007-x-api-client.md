# 007 — フェーズ⑤ x_api_client.py（X API連携）

**フェーズ：** ⑤  
**担当：** Claude Code  
**依存：** 001〜006すべて完了・安定稼働していること  
**ファイル：** `src/x_api_client.py`  
**期間目安：** 1〜2週

---

## 概要

フェーズ①〜④が安定した後に、X APIを接続してポスト収集・自動投稿を実現する。

> **注意：このフェーズは①〜④が安定稼働してから着手すること。先に手を出さない。**

tweepy（X API v2）を使用。`post` と `collect` の2つのサブコマンドを持つ。

---

## TODO

### 事前準備（手動・TASKS-0-prepで完了させておく）

【】X Developer Portal でプロジェクト・アプリを作成済みであること  

【】API Key / Secret を `.env` に記入済みであること  

【】Access Token / Access Token Secret を `.env` に記入済みであること  

【】Client ID / Client Secret を `.env` に記入済みであること  

【】$5 チャージ済みであること  

### 実装

【】`src/x_api_client.py` を作成  

【】tweepy クライアントの初期化処理を実装  
> `.env` から認証情報を読み込む。

【】`post` サブコマンドを実装（WP記事 → X自動投稿）  
> `python3 src/x_api_client.py post --post-id 123`  
> `x_post_generator.py` の文面生成ロジックを呼び出してXに投稿。

【】`collect` サブコマンドを実装（巨人関連ポスト収集 → WP下書き）  
> `python3 src/x_api_client.py collect`  
> X APIで巨人関連ポストを検索取得 → `wp_client.create_draft()` で下書き生成。

【】読み取り（GET）を1日2〜3回に制限する処理を実装  
> `data/rss_history.json` に最終実行時刻を記録して過剰実行を防ぐ。

【】同一ポストの24時間以内の再取得をスキップする処理を実装  

【】コスト管理ログを `logs/x_api.log` に出力する処理を実装  
> 1実行あたりのAPI呼び出し件数・推定コストを記録。

### 動作確認

【】`post` サブコマンドでXに実際に投稿されること（テスト投稿）  

【】`collect` サブコマンドで巨人関連ポストが収集されWP下書きが生成されること  

【】1週間後にX Developer Portalでコストが$5以内であることを確認  

---

## 仕様詳細

### X API料金（従量課金・2026年4月時点）

| 操作 | 単価 | 月間想定 | 月間コスト |
|------|------|---------|----------|
| ポスト投稿（Create） | $0.01/件 | 300件 | $3（約450円） |
| ポスト読み取り（Read） | $0.005/件 | 1,500件 | $7.5（約1,100円） |
| **合計（想定）** | | | **約1,550円/月** |

初期チャージ：$5（約800円）。残高ゼロで自動停止（追加請求なし）。

### コスト節約ルール

- 読み取り（GET）は1日2〜3回に絞る
- 同一ポストの24時間以内の再取得はカウントされない
- `data/rss_history.json` で履歴管理し、API経由の重複チェックを避ける

### CLIコマンド

```bash
# WP記事をXに自動投稿
python3 src/x_api_client.py post --post-id 123

# 巨人関連ポストを収集してWP下書きに変換
python3 src/x_api_client.py collect
```

### Cron設定（collectの自動実行）

```cron
# 1日2回（8時・20時）
0 8,20 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/x_api_client.py collect >> /home/（ユーザー名）/yoshilover/logs/x_collect.log 2>&1
```

### 認証情報（.env）

```dotenv
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_CLIENT_ID=
X_CLIENT_SECRET=
```

---

## 完了条件

- 記事公開時にXへ自動投稿されている  
- 巨人関連ポストが自動収集され、WP下書きに反映されている  
- 月間コストが$5以内に収まっている  
