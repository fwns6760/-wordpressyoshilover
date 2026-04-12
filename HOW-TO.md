# HOW-TO.md — コマンド手順書

> タスクファイルの確認・完了変更・進捗サマリーのワンライナー集。

---

## タスク確認

### 未完了タスク一覧を表示

```bash
# TASKS-0-prep.md の未完了タスク
grep '☐' TASKS-0-prep.md

# TASKS-1-dev.md の未完了タスク
grep '☐' TASKS-1-dev.md

# TASKS-2-deploy.md の未完了タスク
grep '☐' TASKS-2-deploy.md

# TASKS-3-prosports.md の未完了タスク
grep '☐' TASKS-3-prosports.md

# 全ファイルの未完了タスク
grep -rn '☐' TASKS-*.md
```

### 完了タスク一覧を表示

```bash
grep '☑' TASKS-0-prep.md
grep '☑' TASKS-1-dev.md
grep '☑' TASKS-2-deploy.md
grep '☑' TASKS-3-prosports.md
grep -rn '☑' TASKS-*.md
```

### 特定キーワードのタスクを検索

```bash
grep 'SSH' TASKS-0-prep.md
grep 'RSS' TASKS-1-dev.md
grep 'Cron' TASKS-2-deploy.md
```

---

## 進捗サマリー

### 各ファイルの完了数 / 全体数

```bash
for f in TASKS-*.md; do
  total=$(grep -c '[☐☑]' "$f")
  done=$(grep -c '☑' "$f")
  echo "$f: $done / $total 完了"
done
```

### 全体の進捗を一行で確認

```bash
echo "未完了: $(grep -rh '☐' TASKS-*.md | wc -l) / 完了: $(grep -rh '☑' TASKS-*.md | wc -l)"
```

---

## タスクを完了に変更（sedコマンド）

### 書式

```bash
sed -i 's/☐ タスク名/☑ タスク名/' TASKS-X-xxx.md
```

---

## TASKS-0-prep.md のタスクを完了にする

```bash
sed -i 's/☐ WPアプリケーションパスワードを発行/☑ WPアプリケーションパスワードを発行/' TASKS-0-prep.md
sed -i 's/☐ REST API疎通確認（ブラウザ）/☑ REST API疎通確認（ブラウザ）/' TASKS-0-prep.md
sed -i 's/☐ REST API疎通確認（エックスサーバー外部アクセス）/☑ REST API疎通確認（エックスサーバー外部アクセス）/' TASKS-0-prep.md
sed -i 's/☐ WPカテゴリ8種を作成/☑ WPカテゴリ8種を作成/' TASKS-0-prep.md
sed -i 's/☐ 各カテゴリのWP IDをメモ/☑ 各カテゴリのWP IDをメモ/' TASKS-0-prep.md
sed -i 's/☐ REST APIが403の場合/☑ REST APIが403の場合/' TASKS-0-prep.md
sed -i 's/☐ SEO SIMPLE PACK をインストール/☑ SEO SIMPLE PACK をインストール/' TASKS-0-prep.md
sed -i 's/☐ SEO SIMPLE PACK の初期設定/☑ SEO SIMPLE PACK の初期設定/' TASKS-0-prep.md
sed -i 's/☐ SWELLテーマに切り替え/☑ SWELLテーマに切り替え/' TASKS-0-prep.md
sed -i 's/☐ メインカラー設定/☑ メインカラー設定/' TASKS-0-prep.md
sed -i 's/☐ テキストカラー設定/☑ テキストカラー設定/' TASKS-0-prep.md
sed -i 's/☐ リンクカラー設定/☑ リンクカラー設定/' TASKS-0-prep.md
sed -i 's/☐ 背景色設定/☑ 背景色設定/' TASKS-0-prep.md
sed -i 's/☐ ヘッダー背景設定/☑ ヘッダー背景設定/' TASKS-0-prep.md
sed -i 's/☐ 追加CSSを記述/☑ 追加CSSを記述/' TASKS-0-prep.md
sed -i 's/☐ 記事一覧をリスト型に変更/☑ 記事一覧をリスト型に変更/' TASKS-0-prep.md
sed -i 's/☐ 固定ページ作成/☑ 固定ページ作成/' TASKS-0-prep.md
sed -i 's/☐ テスト記事を3〜5本手動投稿/☑ テスト記事を3〜5本手動投稿/' TASKS-0-prep.md
sed -i 's/☐ スマホ表示が崩れていないか確認/☑ スマホ表示が崩れていないか確認/' TASKS-0-prep.md
sed -i 's/☐ SSH設定をONにする/☑ SSH設定をONにする/' TASKS-0-prep.md
sed -i 's/☐ SSH鍵ペアを生成してサーバーに登録/☑ SSH鍵ペアを生成してサーバーに登録/' TASKS-0-prep.md
sed -i 's/☐ SSH接続テスト成功/☑ SSH接続テスト成功/' TASKS-0-prep.md
sed -i 's/☐ Python3のバージョン確認/☑ Python3のバージョン確認/' TASKS-0-prep.md
sed -i 's/☐ pip3が使えるか確認/☑ pip3が使えるか確認/' TASKS-0-prep.md
sed -i 's/☐ developer.x.com にログイン/☑ developer.x.com にログイン/' TASKS-0-prep.md
sed -i 's/☐ プロジェクト作成/☑ プロジェクト作成/' TASKS-0-prep.md
sed -i 's/☐ API Key \/ Secret 取得/☑ API Key \/ Secret 取得/' TASKS-0-prep.md
sed -i 's/☐ Access Token \/ Secret 取得/☑ Access Token \/ Secret 取得/' TASKS-0-prep.md
sed -i 's/☐ Client ID \/ Client Secret を取得/☑ Client ID \/ Client Secret を取得/' TASKS-0-prep.md
sed -i 's/☐ Credits メニューから \$5 チャージ/☑ Credits メニューから \$5 チャージ/' TASKS-0-prep.md
sed -i 's/☐ yoshilover.com の下書きゴミ箱記事を整理/☑ yoshilover.com の下書きゴミ箱記事を整理/' TASKS-0-prep.md
sed -i 's/☐ 残り170記事をXMLエクスポート/☑ 残り170記事をXMLエクスポート/' TASKS-0-prep.md
sed -i 's/☐ prosports側にXMLインポート/☑ prosports側にXMLインポート/' TASKS-0-prep.md
sed -i 's/☐ インポート後すぐに全記事を「下書き」に変更/☑ インポート後すぐに全記事を「下書き」に変更/' TASKS-0-prep.md
sed -i 's/☐ リライト完了した記事から1本ずつ公開/☑ リライト完了した記事から1本ずつ公開/' TASKS-0-prep.md
```

---

## TASKS-1-dev.md のタスクを完了にする

```bash
sed -i 's/☐ ディレクトリ構成を作成/☑ ディレクトリ構成を作成/' TASKS-1-dev.md
sed -i 's/☐ .env.example を作成/☑ .env.example を作成/' TASKS-1-dev.md
sed -i 's/☐ .gitignore を作成/☑ .gitignore を作成/' TASKS-1-dev.md
sed -i 's/☐ requirements.txt を作成/☑ requirements.txt を作成/' TASKS-1-dev.md
sed -i 's/☐ config\/categories.json を作成/☑ config\/categories.json を作成/' TASKS-1-dev.md
sed -i 's/☐ config\/rss_sources.json を作成/☑ config\/rss_sources.json を作成/' TASKS-1-dev.md
sed -i 's/☐ config\/keywords.json を作成/☑ config\/keywords.json を作成/' TASKS-1-dev.md
sed -i 's/☐ data\/posted_urls.json を空JSONで作成/☑ data\/posted_urls.json を空JSONで作成/' TASKS-1-dev.md
sed -i 's/☐ data\/rss_history.json を空JSONで作成/☑ data\/rss_history.json を空JSONで作成/' TASKS-1-dev.md
sed -i 's/☐ logs\/ ディレクトリを作成/☑ logs\/ ディレクトリを作成/' TASKS-1-dev.md
sed -i 's/☐ src\/wp_client.py を実装/☑ src\/wp_client.py を実装/' TASKS-1-dev.md
sed -i 's/☐ wp_client.py のユニットテスト作成/☑ wp_client.py のユニットテスト作成/' TASKS-1-dev.md
sed -i 's/☐ wp_client.py の疎通テスト/☑ wp_client.py の疎通テスト/' TASKS-1-dev.md
sed -i 's/☐ src\/wp_draft_creator.py を実装/☑ src\/wp_draft_creator.py を実装/' TASKS-1-dev.md
sed -i 's/☐ 単一URL指定で下書き生成が動作する/☑ 単一URL指定で下書き生成が動作する/' TASKS-1-dev.md
sed -i 's/☐ --file オプションで複数URL一括処理が動作する/☑ --file オプションで複数URL一括処理が動作する/' TASKS-1-dev.md
sed -i 's/☐ --category オプションでカテゴリ指定が動作する/☑ --category オプションでカテゴリ指定が動作する/' TASKS-1-dev.md
sed -i 's/☐ --title オプションでタイトル手動指定が動作する/☑ --title オプションでタイトル手動指定が動作する/' TASKS-1-dev.md
sed -i 's/☐ 重複チェック（posted_urls.json）が動作する/☑ 重複チェック（posted_urls.json）が動作する/' TASKS-1-dev.md
sed -i 's/☐ oEmbedブロックHTMLが正しく生成される/☑ oEmbedブロックHTMLが正しく生成される/' TASKS-1-dev.md
sed -i 's/☐ WP管理画面でXカードが正しく表示される/☑ WP管理画面でXカードが正しく表示される/' TASKS-1-dev.md
sed -i 's/☐ RSSフィードURLの実在確認/☑ RSSフィードURLの実在確認/' TASKS-1-dev.md
sed -i 's/☐ config\/rss_sources.json を実在URLで更新/☑ config\/rss_sources.json を実在URLで更新/' TASKS-1-dev.md
sed -i 's/☐ src\/rss_fetcher.py を実装/☑ src\/rss_fetcher.py を実装/' TASKS-1-dev.md
sed -i 's/☐ RSSフィード取得が動作する/☑ RSSフィード取得が動作する/' TASKS-1-dev.md
sed -i 's/☐ 巨人キーワードフィルタが動作する/☑ 巨人キーワードフィルタが動作する/' TASKS-1-dev.md
sed -i 's/☐ 重複チェック（rss_history.json）が動作する/☑ 重複チェック（rss_history.json）が動作する/' TASKS-1-dev.md
sed -i 's/☐ カテゴリ自動分類が動作する/☑ カテゴリ自動分類が動作する/' TASKS-1-dev.md
sed -i 's/☐ WP下書き生成（wp_client.py連携）が動作する/☑ WP下書き生成（wp_client.py連携）が動作する/' TASKS-1-dev.md
sed -i 's/☐ ログ出力が正しい/☑ ログ出力が正しい/' TASKS-1-dev.md
sed -i 's/☐ 著作権配慮/☑ 著作権配慮/' TASKS-1-dev.md
sed -i 's/☐ src\/x_post_generator.py を実装/☑ src\/x_post_generator.py を実装/' TASKS-1-dev.md
sed -i 's/☐ --title \/ --url \/ --category 指定で文面生成が動作する/☑ --title \/ --url \/ --category 指定で文面生成が動作する/' TASKS-1-dev.md
sed -i 's/☐ --post-id 指定でWP REST APIから記事取得/☑ --post-id 指定でWP REST APIから記事取得/' TASKS-1-dev.md
sed -i 's/☐ ハッシュタグ自動付与が動作する/☑ ハッシュタグ自動付与が動作する/' TASKS-1-dev.md
sed -i 's/☐ 140字以内に収まっている/☑ 140字以内に収まっている/' TASKS-1-dev.md
sed -i 's/☐ stdout出力が正しい/☑ stdout出力が正しい/' TASKS-1-dev.md
sed -i 's/☐ src\/x_api_client.py を実装/☑ src\/x_api_client.py を実装/' TASKS-1-dev.md
sed -i 's/☐ post サブコマンド（WP記事 → X自動投稿）が動作する/☑ post サブコマンド（WP記事 → X自動投稿）が動作する/' TASKS-1-dev.md
sed -i 's/☐ collect サブコマンド（巨人関連ポスト収集 → WP下書き）が動作する/☑ collect サブコマンド（巨人関連ポスト収集 → WP下書き）が動作する/' TASKS-1-dev.md
sed -i 's/☐ コスト節約ルール/☑ コスト節約ルール/' TASKS-1-dev.md
sed -i 's/☐ 月間コストが想定内/☑ 月間コストが想定内/' TASKS-1-dev.md
```

---

## TASKS-2-deploy.md のタスクを完了にする

```bash
sed -i 's/☐ プロジェクト一式をエックスサーバーにアップロード/☑ プロジェクト一式をエックスサーバーにアップロード/' TASKS-2-deploy.md
sed -i 's/☐ pip3 install --user -r requirements.txt 完了/☑ pip3 install --user -r requirements.txt 完了/' TASKS-2-deploy.md
sed -i 's/☐ .env ファイルを作成し、本番の認証情報を記入/☑ .env ファイルを作成し、本番の認証情報を記入/' TASKS-2-deploy.md
sed -i 's/☐ logs\/ ディレクトリ作成/☑ logs\/ ディレクトリ作成/' TASKS-2-deploy.md
sed -i 's/☐ wp_client.py 疎通テスト成功/☑ wp_client.py 疎通テスト成功/' TASKS-2-deploy.md
sed -i 's/☐ wp_draft_creator.py テスト成功/☑ wp_draft_creator.py テスト成功/' TASKS-2-deploy.md
sed -i 's/☐ WP管理画面でXカードが正しく表示/☑ WP管理画面でXカードが正しく表示/' TASKS-2-deploy.md
sed -i 's/☐ rss_fetcher.py テスト成功/☑ rss_fetcher.py テスト成功/' TASKS-2-deploy.md
sed -i 's/☐ x_post_generator.py テスト成功/☑ x_post_generator.py テスト成功/' TASKS-2-deploy.md
sed -i 's/☐ crontab にrss_fetcher.pyの定期実行を登録/☑ crontab にrss_fetcher.pyの定期実行を登録/' TASKS-2-deploy.md
sed -i 's/☐ Cron実行後のログ確認/☑ Cron実行後のログ確認/' TASKS-2-deploy.md
sed -i 's/☐ 翌日まで放置して自動実行が安定しているか確認/☑ 翌日まで放置して自動実行が安定しているか確認/' TASKS-2-deploy.md
sed -i 's/☐ 初日：手動で5記事公開/☑ 初日：手動で5記事公開/' TASKS-2-deploy.md
sed -i 's/☐ 初日：x_post_generator.pyでポスト文面生成/☑ 初日：x_post_generator.pyでポスト文面生成/' TASKS-2-deploy.md
sed -i 's/☐ 1週間：1日3〜5記事ペースで安定運用/☑ 1週間：1日3〜5記事ペースで安定運用/' TASKS-2-deploy.md
sed -i 's/☐ 2週間：1日5〜10記事ペースに増加/☑ 2週間：1日5〜10記事ペースに増加/' TASKS-2-deploy.md
sed -i 's/☐ 1ヶ月：RSS自動取得＋手動確認＋公開のフローが定着/☑ 1ヶ月：RSS自動取得＋手動確認＋公開のフローが定着/' TASKS-2-deploy.md
sed -i 's/☐ X Developer Portalの設定完了/☑ X Developer Portalの設定完了/' TASKS-2-deploy.md
sed -i 's/☐ .env にX APIキーを記入/☑ .env にX APIキーを記入/' TASKS-2-deploy.md
sed -i 's/☐ x_api_client.py をデプロイ/☑ x_api_client.py をデプロイ/' TASKS-2-deploy.md
sed -i 's/☐ post サブコマンドのテスト成功/☑ post サブコマンドのテスト成功/' TASKS-2-deploy.md
sed -i 's/☐ collect サブコマンドのテスト成功/☑ collect サブコマンドのテスト成功/' TASKS-2-deploy.md
sed -i 's/☐ Cron にcollectの定期実行を追加/☑ Cron にcollectの定期実行を追加/' TASKS-2-deploy.md
sed -i 's/☐ 1週間の月間コスト確認/☑ 1週間の月間コスト確認/' TASKS-2-deploy.md
```

---

## TASKS-3-prosports.md のタスクを完了にする

```bash
sed -i 's/☐ 導入文の重複を修正/☑ 導入文の重複を修正/' TASKS-3-prosports.md
sed -i 's/☐ 砂川リチャードのセクションが入っているか確認/☑ 砂川リチャードのセクションが入っているか確認/' TASKS-3-prosports.md
sed -i 's/☐ 竹丸和幸のセクション追加/☑ 竹丸和幸のセクション追加/' TASKS-3-prosports.md
sed -i 's/☐ 田和廉のセクション追加/☑ 田和廉のセクション追加/' TASKS-3-prosports.md
sed -i 's/☐ 吉川尚輝の実家家族記事リンク確認/☑ 吉川尚輝の実家家族記事リンク確認/' TASKS-3-prosports.md
sed -i 's/☐ FAQセクション追加/☑ FAQセクション追加/' TASKS-3-prosports.md
sed -i 's/☐ 各個別記事の末尾に巨人クラスターへの内部リンク追加/☑ 各個別記事の末尾に巨人クラスターへの内部リンク追加/' TASKS-3-prosports.md
sed -i 's/☐ 現役ハブページに「球団別で詳しく見る」セクション追加/☑ 現役ハブページに「球団別で詳しく見る」セクション追加/' TASKS-3-prosports.md
sed -i 's/☐ 巨人クラスターページへのブログカードリンク設置/☑ 巨人クラスターページへのブログカードリンク設置/' TASKS-3-prosports.md
sed -i 's/☐ OBハブページに同様のセクション追加/☑ OBハブページに同様のセクション追加/' TASKS-3-prosports.md
sed -i 's/☐ 巨人OBクラスターページの投稿テキスト作成/☑ 巨人OBクラスターページの投稿テキスト作成/' TASKS-3-prosports.md
sed -i 's/☐ WordPress投稿・公開（スラッグ：giants-ob）/☑ WordPress投稿・公開（スラッグ：giants-ob）/' TASKS-3-prosports.md
sed -i 's/☐ OBハブページから巨人OBクラスターへのリンク設置/☑ OBハブページから巨人OBクラスターへのリンク設置/' TASKS-3-prosports.md
sed -i 's/☐ 各OB個別記事の末尾に巨人OBクラスターへの内部リンク追加/☑ 各OB個別記事の末尾に巨人OBクラスターへの内部リンク追加/' TASKS-3-prosports.md
sed -i 's/☐ ソフトバンク現役クラスターページ作成/☑ ソフトバンク現役クラスターページ作成/' TASKS-3-prosports.md
sed -i 's/☐ 阪神現役クラスターページ作成/☑ 阪神現役クラスターページ作成/' TASKS-3-prosports.md
sed -i 's/☐ 広島現役クラスターページ作成/☑ 広島現役クラスターページ作成/' TASKS-3-prosports.md
sed -i 's/☐ その他球団まとめページ作成/☑ その他球団まとめページ作成/' TASKS-3-prosports.md
sed -i 's/☐ 岡本和真/☑ 岡本和真/' TASKS-3-prosports.md
sed -i 's/☐ 大勢（翁田大勢）/☑ 大勢（翁田大勢）/' TASKS-3-prosports.md
sed -i 's/☐ 門脇誠/☑ 門脇誠/' TASKS-3-prosports.md
sed -i 's/☐ 浅野翔吾/☑ 浅野翔吾/' TASKS-3-prosports.md
sed -i 's/☐ 吉川尚輝（実家家族）/☑ 吉川尚輝（実家家族）/' TASKS-3-prosports.md
sed -i 's/☐ 赤星優志/☑ 赤星優志/' TASKS-3-prosports.md
sed -i 's/☐ 湯浅大/☑ 湯浅大/' TASKS-3-prosports.md
```

---

## ファイル内容の確認

```bash
# ファイル全体を表示
cat TASKS-0-prep.md
cat TASKS-1-dev.md
cat TASKS-2-deploy.md
cat TASKS-3-prosports.md

# セクションを確認（例：フェーズ③部分）
grep -A 20 'フェーズ③' TASKS-1-dev.md

# ログ確認
cat ~/yoshilover/logs/rss_fetcher.log
tail -50 ~/yoshilover/logs/rss_fetcher.log
```
