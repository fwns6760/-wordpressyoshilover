# TASKS-2-deploy.md — デプロイ・運用開始タスク

> TASKS-1-dev.md の実装が完了してから進める。
> エックスサーバーへの配置 → 動作確認 → Cron設定 → 運用ペース段階拡大の順。
> 完了したら `☐` を `☑` に変える（HOW-TO.md のsedコマンド参照）。

---

## エックスサーバーへの配置

☐ プロジェクト一式をエックスサーバーにアップロード
> `scp -P 10022 -r ./yoshilover/ （ユーザー名）@（サーバー名）.xserver.jp:~/`

☐ pip3 install --user -r requirements.txt 完了
> SSH接続後、`cd ~/yoshilover && pip3 install --user -r requirements.txt`

☐ .env ファイルを作成し、本番の認証情報を記入
> `cp .env.example .env` → nanoで本番のWP_URL / WP_USER / WP_APP_PASSWORDを記入

☐ logs/ ディレクトリ作成
> `mkdir -p ~/yoshilover/logs`

---

## 動作確認（フェーズ②③④）

☐ wp_client.py 疎通テスト成功
> `python3 src/wp_client.py --test` でカテゴリ一覧が返ること

☐ wp_draft_creator.py テスト成功
> XポストURLを1本渡してWPに下書きが生成されること

☐ WP管理画面でXカードが正しく表示
> 生成された下書きをWP管理画面で開いてXポストカードが表示されること

☐ rss_fetcher.py テスト成功
> `python3 src/rss_fetcher.py --dry-run` で取得件数がログに出力されること

☐ x_post_generator.py テスト成功
> `python3 src/x_post_generator.py --post-id （テスト記事ID）` で文面が出力されること

---

## Cron設定

☐ crontab にrss_fetcher.pyの定期実行を登録
> エックスサーバー管理画面 → Cron設定 に以下を登録：
> ```
> 0 7,11,17,21 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/rss_fetcher.py >> /home/（ユーザー名）/yoshilover/logs/rss_fetcher.log 2>&1
> ```

☐ Cron実行後のログ確認
> 翌朝7時以降に `cat ~/yoshilover/logs/rss_fetcher.log` でエラーなく実行されているか確認

☐ 翌日まで放置して自動実行が安定しているか確認
> 1日4回のCron実行が正常に動作し、WPに下書きが蓄積されていることを確認

---

## 運用ペース段階拡大

### 初日（手動確認フローの確立）

☐ 初日：手動で5記事公開
> WP管理画面の下書き一覧を開き、Xカード表示確認 → 一言コメント追加 → 公開

☐ 初日：x_post_generator.pyでポスト文面生成
> 公開した記事のIDで `python3 src/x_post_generator.py --post-id （ID）` → Xに手動コピペ投稿

### 1週間（フロー安定化）

☐ 1週間：1日3〜5記事ペースで安定運用
> 朝：RSS自動生成された下書きを確認 → コメント追加 → 公開 → x_post_generator.pyで文面生成 → 投稿

### 2週間（増量）

☐ 2週間：1日5〜10記事ペースに増加
> フローが安定したらRSS取得頻度を増やすか、手動でXポストURLを追加投稿

### 1ヶ月（フロー定着）

☐ 1ヶ月：RSS自動取得＋手動確認＋公開のフローが定着
> 人間の作業は「朝に下書き確認→一言コメント追加→公開ボタン」のみになっている

---

## フェーズ⑤ X API デプロイ（TASKS-1-dev完了後）

☐ X Developer Portalの設定完了
> developer.x.com でプロジェクト作成・$5チャージ済み（TASKS-0-prep参照）

☐ .env にX APIキーを記入
> X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET を記入

☐ x_api_client.py をデプロイ
> SCP or 手動コピーでサーバーに配置

☐ post サブコマンドのテスト成功
> `python3 src/x_api_client.py post --post-id （ID）` でXに実際に投稿されること

☐ collect サブコマンドのテスト成功
> `python3 src/x_api_client.py collect` で巨人関連ポストが収集されWP下書きが生成されること

☐ Cron にcollectの定期実行を追加
> `0 8,20 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/x_api_client.py collect >> /home/（ユーザー名）/yoshilover/logs/x_collect.log 2>&1`

☐ 1週間の月間コスト確認
> X Developer Portal でコスト確認。$5チャージの範囲内であることを確認。
