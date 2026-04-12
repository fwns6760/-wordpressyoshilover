# TASKS-1-dev.md — 開発タスク（Claude Code作業）

> Claude Codeが実装するタスク。共通基盤→フェーズ②→③→④→⑤の順に進める。
> 前のフェーズが安定してから次に進む。飛ばさない。
> 完了したら `☐` を `☑` に変える（HOW-TO.md のsedコマンド参照）。

---

## 共通基盤（最初に作る）

☐ ディレクトリ構成を作成
> src/ config/ data/ logs/ を作成

☐ .env.example を作成
> WP_URL / WP_USER / WP_APP_PASSWORD / X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET / X_CLIENT_ID / X_CLIENT_SECRET

☐ .gitignore を作成
> .env / logs/*.log / data/*.json / __pycache__/ を除外

☐ requirements.txt を作成
> requests / python-dotenv / feedparser / tweepy

☐ config/categories.json を作成
> カテゴリ名とWP IDのマッピング。WP IDはTASKS-0-prepで確認した値を記入。

☐ config/rss_sources.json を作成
> スポーツ報知・日刊スポーツ・スポニチ・東スポ・Yahoo!スポーツナビのRSSフィードURL一覧

☐ config/keywords.json を作成
> カテゴリ自動分類キーワードルール（AGENTS.md の「自動分類ルール」参照）

☐ data/posted_urls.json を空JSONで作成
> `{}` のみ記述。投稿済みURL履歴（重複防止用）。

☐ data/rss_history.json を空JSONで作成
> `{}` のみ記述。RSS取得済み記事URL履歴。

☐ logs/ ディレクトリを作成
> .gitkeep を置いてgit管理対象にする

---

## フェーズ② WP下書き自動生成（`src/wp_client.py` + `src/wp_draft_creator.py`）

### wp_client.py（共通クライアント）

☐ src/wp_client.py を実装
> WP REST API Basic認証クライアント。`create_draft()` / `get_post()` / `get_categories()` を実装。

☐ wp_client.py のユニットテスト作成
> `.env` の認証情報を使ったモックテスト。requests をモック化。

☐ wp_client.py の疎通テスト
> `python3 src/wp_client.py --test` でWP REST APIにGETリクエストを送ってカテゴリ一覧が返ることを確認。

### wp_draft_creator.py

☐ src/wp_draft_creator.py を実装
> XポストURLを受け取りoEmbedブロックHTMLを生成してWP下書きを作成するCLIスクリプト。

☐ 単一URL指定で下書き生成が動作する
> `python3 src/wp_draft_creator.py --url https://x.com/...` で下書きが生成される。

☐ --file オプションで複数URL一括処理が動作する
> `--file urls.txt` でファイル内のURLを1行1件として全件処理。

☐ --category オプションでカテゴリ指定が動作する
> `--category 試合速報` でカテゴリIDを自動解決して設定される。

☐ --title オプションでタイトル手動指定が動作する
> `--title "タイトル"` で任意のタイトルを設定できる。

☐ 重複チェック（posted_urls.json）が動作する
> 同じURLを2回渡しても2回目は投稿されず「スキップ済み」と表示される。

☐ oEmbedブロックHTMLが正しく生成される
> `<!-- wp:embed {"url":"..."} -->` 形式のGutenbergブロックが正しく組み立てられる。

☐ WP管理画面でXカードが正しく表示される
> 生成された下書きをWP管理画面で開き、XポストのカードUIが表示されることを実機確認。

---

## フェーズ③ RSS取得＋自動分類（`src/rss_fetcher.py`）

☐ RSSフィードURLの実在確認
> config/rss_sources.json に記入する各URLにcurlでアクセスしてXMLが返ることを確認。

☐ config/rss_sources.json を実在URLで更新
> 確認済みの正しいURLのみを記入する。

☐ src/rss_fetcher.py を実装
> feedparserで取得 → キーワードフィルタ → 重複チェック → カテゴリ分類 → wp_client経由で下書き生成。

☐ RSSフィード取得が動作する
> `python3 src/rss_fetcher.py --dry-run` で取得件数がログ出力される。

☐ 巨人キーワードフィルタが動作する
> 「巨人」「ジャイアンツ」「東京ドーム」を含まない記事がスキップされる。

☐ 重複チェック（rss_history.json）が動作する
> 一度取得した記事URLが2回目の実行でスキップされる。

☐ カテゴリ自動分類が動作する
> keywords.json のルールに従って各記事に正しいカテゴリが付与される。

☐ WP下書き生成（wp_client.py連携）が動作する
> RSS記事がWPに下書きとして投稿される（--dry-run なしで実行）。

☐ ログ出力が正しい
> logs/rss_fetcher.log に取得件数・スキップ件数・エラーが記録される。

☐ 著作権配慮
> 記事本文は取得せず、タイトル・URL・日時のみを記事に使う。本文欄はオリジナルコメント用プレースホルダーを入れる。

---

## フェーズ④ X文案生成（`src/x_post_generator.py`）

☐ src/x_post_generator.py を実装
> 記事タイトル・URL・カテゴリを受け取り140字以内のXポスト文面を生成するCLIスクリプト。

☐ --title / --url / --category 指定で文面生成が動作する
> `python3 src/x_post_generator.py --title "..." --url https://... --category 試合速報`

☐ --post-id 指定でWP REST APIから記事取得
> `--post-id 123` でWPから記事情報を取得して文面を生成。

☐ ハッシュタグ自動付与が動作する
> 必須（#巨人 #ジャイアンツ）＋カテゴリ別＋選手名検出が正しく動作する。

☐ 140字以内に収まっている
> URLを含む最終出力が必ず140字以内になるよう自動トリミングされる。

☐ stdout出力が正しい
> 出力がそのままコピペでXに投稿できる形式になっている。

---

## フェーズ⑤ X API連携（`src/x_api_client.py`）

> **注意：フェーズ①〜④が安定稼働してから着手すること。**

☐ src/x_api_client.py を実装
> tweepy を使ったX API v2クライアント。`post` / `collect` サブコマンドを実装。

☐ post サブコマンド（WP記事 → X自動投稿）が動作する
> `python3 src/x_api_client.py post --post-id 123` でXに投稿される。

☐ collect サブコマンド（巨人関連ポスト収集 → WP下書き）が動作する
> `python3 src/x_api_client.py collect` で巨人関連ポストを取得してWPに下書き生成される。

☐ コスト節約ルール
> 読み取り（GET）は1日2〜3回のみ。rss_history.json で履歴管理して重複APIコールを防ぐ。

☐ 月間コストが想定内
> 1週間運用後にX Developer Portal でコスト確認。$5チャージの範囲内であることを確認。
