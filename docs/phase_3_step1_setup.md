# Phase 3 段階1セットアップ

明日の朝に、`acceptance_fact_check` の結果を Gmail で受け取るための最短手順です。スマホで見ても追えるように、1ステップを短くしています。

## 0. 今夜の時点で終わっていること

- Cloud Run revision は `yoshilover-fetcher-00128-hdh` 以降で `/fact_check_notify` を持っている
- Scheduler job `fact-check-morning-report` は登録済み
- `FACT_CHECK_EMAIL_TO` / `FACT_CHECK_EMAIL_FROM` / `GMAIL_APP_PASSWORD_SECRET_NAME` は本番へ反映済み
- Gmail app password だけ未設定でも、デモモードで本文はログに出る

## 1. Gmail app password を取る

所要時間: 5分

1. Google アカウントを開く
2. `セキュリティ` を開く
3. `2段階認証プロセス` が OFF なら ON にする
4. `アプリ パスワード` を開く
5. `アプリを選択` は `メール`
6. `デバイスを選択` は `その他`
7. 名前に `Cloud Run` と入れて生成
8. 表示された 16 桁をコピーする

注意:

- スペースが入って見えても、そのままコピーで問題ありません
- この画面は閉じると再表示できないので、そのまま次の手順へ進みます

## 2. Secret Manager に登録する

所要時間: 3分

PC で次を実行します。

```bash
printf '%s' 'ここに16桁のapp password' | \
gcloud secrets versions add yoshilover-gmail-app-password \
  --project baseballsite \
  --data-file=-
```

確認:

```bash
gcloud secrets versions list yoshilover-gmail-app-password --project baseballsite
```

`ENABLED` の version が 1 件以上あれば OK です。

## 3. Cloud Run の環境変数を確認する

所要時間: 2分

今回の実装では、Cloud Run 側はすでに `GMAIL_APP_PASSWORD_SECRET_NAME=yoshilover-gmail-app-password` を持っています。通常は追加作業不要です。

確認だけします。

```bash
gcloud run services describe yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --format='value(spec.template.spec.containers[0].env)'
```

見るポイント:

- `FACT_CHECK_EMAIL_TO=fwns6760@gmail.com`
- `FACT_CHECK_EMAIL_FROM=fwns6760@gmail.com`
- `GMAIL_APP_PASSWORD_SECRET_NAME=yoshilover-gmail-app-password`

もし未反映なら、次で追加します。

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars FACT_CHECK_EMAIL_TO=fwns6760@gmail.com,FACT_CHECK_EMAIL_FROM=fwns6760@gmail.com,GMAIL_APP_PASSWORD_SECRET_NAME=yoshilover-gmail-app-password
```

## 4. 手動実行で最初の1通を確認する

所要時間: 1分

Scheduler を待たずに、まず 1 回だけ手動で起動します。

```bash
gcloud scheduler jobs run fact-check-morning-report \
  --project baseballsite \
  --location asia-northeast1
```

その後に確認するもの:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND textPayload:"fact_check_email_"' \
  --project baseballsite \
  --limit=20
```

期待する結果:

- 本物送信なら `fact_check_email_sent`
- 未設定や認証失敗なら `fact_check_email_failed`
- app password 未設定なら `fact_check_email_demo` / `fact_check_email_demo_ready`

## 5. メールの見え方を確認する

所要時間: 1分

スマホの Gmail アプリで件名を確認します。

件名:

- `【ヨシラバー】MM/DD 事実チェック結果（🔴X / 🟡Y / ✅Z）`

見るポイント:

- `🔴` セクションが一番上
- `WPで開く` リンクが押せる
- `✅ 公開候補` が最後にまとまっている

## 明日朝の最短ルート

1. app password を取る
2. Secret Manager に追加
3. `gcloud scheduler jobs run fact-check-morning-report ...`
4. Gmail を開く
5. `🔴` から先に対応する
