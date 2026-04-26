# 008 — エックスサーバーデプロイ

**フェーズ：** デプロイ・運用開始  
**担当：** 手動（SSH）  
**依存：** 001〜006（開発完了後）、TASKS-0-prepのSSH設定完了  
**参照：** TASKS-2-deploy.md

---

## 概要

開発完了したスクリプト一式をエックスサーバーに配置し、本番環境での動作確認・Cron設定・運用ペースの段階拡大を行う。

---

## TODO

### アップロード・セットアップ

【×】プロジェクト一式をエックスサーバーにアップロード  
> `scp -P 10022 -r ./yoshilover/ （ユーザー名）@（サーバー名）.xserver.jp:~/`

【×】`pip3 install --user -r requirements.txt` を実行  
> SSH接続後に実行。エラーが出た場合は `python3 -m pip install --user -r requirements.txt`。

【×】`.env` ファイルを作成して本番の認証情報を記入  
> `cp .env.example .env` → `nano .env` で記入。

【×】`logs/` ディレクトリが存在することを確認  
> `mkdir -p ~/yoshilover/logs`

### 動作確認（フェーズ②③④）

【×】`python3 src/wp_client.py --test` でWP REST API疎通テスト成功  

【】`python3 src/wp_draft_creator.py --url <テストURL>` でWP下書き生成テスト成功  

【】WP管理画面でXカードが正しく表示されること  
> 実機確認必須。確認後テスト下書きは削除。

【×】`python3 src/rss_fetcher.py --dry-run` でRSS取得テスト成功  

【】`python3 src/x_post_generator.py --post-id <テストID>` でX文案生成テスト成功  

### Cron設定

【×】rss_fetcher.py のCronを登録  
> エックスサーバー管理画面 → Cron設定 から登録（下記参照）。

【】Cron初回実行後のログを確認  
> `cat ~/yoshilover/logs/rss_fetcher.log` でエラーなく実行されているか確認。

【】翌日まで放置してCronが安定動作していることを確認  

### 運用開始（段階拡大）

【】初日：手動で5記事公開  
> WP管理画面 → 下書き確認 → 一言コメント追加 → 公開。

【】初日：x_post_generator.py でポスト文面を生成してXに手動投稿  

【】1週間：1日3〜5記事ペースで安定運用  

【】2週間：1日5〜10記事ペースに増加  

【】1ヶ月：RSS自動取得＋手動確認＋公開のフローが完全に定着  
> 毎朝5〜10分の作業で完結するフローになっていること。

### フェーズ⑤デプロイ（別途）

【】.env にX APIキーを記入  

【】`x_api_client.py` を配置  

【】`python3 src/x_api_client.py post --post-id <テストID>` でXへの投稿テスト成功  

【】`python3 src/x_api_client.py collect` でポスト収集テスト成功  

【】collect のCronを登録（1日2回：8時・20時）  

【】1週間後にX Developer Portalでコスト確認（$5以内であること）  

---

## 仕様詳細

### SSH接続コマンド

```bash
ssh -p 10022 （ユーザー名）@（サーバー名）.xserver.jp
```

### アップロードコマンド

```bash
scp -P 10022 -r ./yoshilover/ （ユーザー名）@（サーバー名）.xserver.jp:~/
```

### Cron設定（rss_fetcher.py）

```cron
# RSS自動取得（1日4回：7時・11時・17時・21時）
0 7,11,17,21 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/rss_fetcher.py >> /home/（ユーザー名）/yoshilover/logs/rss_fetcher.log 2>&1
```

### Cron設定（x_api_client.py collect）

```cron
# Xポスト収集（1日2回：8時・20時）
0 8,20 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/x_api_client.py collect >> /home/（ユーザー名）/yoshilover/logs/x_collect.log 2>&1
```

### 運用ペース目標

| 期間 | ペース | 状態 |
|------|--------|------|
| 初日 | 手動5記事 | 動作確認フェーズ |
| 1週間 | 1日3〜5記事 | フロー確立フェーズ |
| 2週間 | 1日5〜10記事 | 増量フェーズ |
| 1ヶ月 | フロー定着 | 毎朝5〜10分の作業のみ |
| フェーズ⑤以降 | X API自動投稿 | 完全自動化フェーズ |

---

## 完了条件

- 全スクリプトがエックスサーバーで正常動作している  
- Cronで定期実行が安定動作している  
- 毎朝「下書き確認→コメント追加→公開」のフローが定着している  
