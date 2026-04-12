# 005 — フェーズ③ rss_fetcher.py（X投稿自動取得＋WP下書き生成）

**フェーズ：** ③  
**担当：** Claude Code  
**依存：** 001（共通基盤）、003（wp_client.py）、004（wp_draft_creator.pyの重複管理ロジック）  
**ファイル：** `src/rss_fetcher.py`

---

## 概要

GCP Cloud Run上のRSSHub経由で巨人関連Xアカウント4件の投稿を自動取得し、
キーワードマッチでカテゴリを自動付与してWordPressに下書き生成する。
Cronで1日4回定期実行することで、人間の作業を「下書き確認→コメント追加→公開」だけにする。

### 取得ソース（config/rss_sources.json）

| アカウント | 内容 |
|-----------|------|
| @TokyoGiants | 巨人公式 |
| @hochi_giants | スポーツ報知巨人取材班 |
| @nikkansports | 日刊スポーツ |
| @Sanspo_Giants | サンスポ巨人 |

RSSHub URL: `https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/{account}`

---

## TODO

### 事前準備

【×】RSSHubをGCP Cloud Runにデプロイ済み  
【×】XアカウントのCookieをCloud Run環境変数に設定済み  
【×】config/rss_sources.json をRSSHub URLで更新済み  

### 実装

【×】`src/rss_fetcher.py` を作成  

【×】`config/rss_sources.json` からフィードURL一覧を読み込む処理を実装  

【×】feedparser で各RSSフィードを取得する処理を実装  

【×】巨人キーワードフィルタを実装  
> 「巨人」「ジャイアンツ」「東京ドーム」「Giants」のいずれかを含む投稿のみ通す。

【×】`data/rss_history.json` による重複チェックを実装  
> 取得済みURLは再度下書き生成しない。

【×】`config/keywords.json` によるカテゴリ自動分類を実装  
> キーワードマッチでカテゴリを決定。マッチなしは「コラム」にフォールバック。

【×】`wp_draft_creator.build_oembed_block()` でXカード埋め込みの下書きを生成する処理を実装  
> 本文はoEmbedブロック（Xカード）のみ。記事本文は取得しない。

【×】`--dry-run` オプションを実装  
> WPへの投稿をせず、取得・分類結果をログ出力するだけのモード。

【×】`logs/rss_fetcher.log` へのログ出力を実装  
> 実行日時・取得件数・スキップ件数・エラーを記録。

### 動作確認

【×】`python3 src/rss_fetcher.py --dry-run` で取得件数がログ出力されること  

【×】巨人キーワードを含まない投稿がスキップされること  

【×】一度取得した投稿URLが2回目の実行でスキップされること  

【×】カテゴリが正しく自動付与されること  

【】WP管理画面で下書きを開くとXカードが表示されること  

---

## 仕様詳細

### 処理フロー

```
1. config/rss_sources.json からURL一覧を読み込む
2. feedparser で各RSSHubフィードを取得
3. 「巨人」「ジャイアンツ」「東京ドーム」「Giants」でキーワードフィルタ
4. rss_history.json で重複チェック（既取得はスキップ）
5. keywords.json のルールでカテゴリ自動分類
6. oEmbedブロックでWP下書き生成
   - タイトル：投稿内容の先頭40字
   - 本文：Xカード（oEmbedブロック）のみ
   - カテゴリ：自動分類結果
7. rss_history.json に取得済みURLを追記
8. logs/rss_fetcher.log に結果を記録
```

### 自動分類ルール

| キーワード | カテゴリ |
|-----------|---------|
| スコア, 勝, 敗, 打席, 登板, 先発, 試合 | 試合速報 |
| 成績, 打率, 防御率, 本塁打, 選手 | 選手情報 |
| 監督, コーチ, 采配, 起用 | 首脳陣 |
| ドラフト, 育成, 2軍, ファーム | ドラフト・育成 |
| OB, 解説 | OB・解説者 |
| FA, トレード, 移籍, 獲得, 外国人 | 補強・移籍 |
| チケット, グッズ, イベント, 東京ドーム | 球団情報 |
| （上記に該当なし） | コラム |

### Cron設定（008-deployで登録）

```cron
# 1日4回（7時・11時・17時・21時）
0 7,11,17,21 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/rss_fetcher.py >> /home/（ユーザー名）/yoshilover/logs/rss_fetcher.log 2>&1
```

---

## 完了条件

- RSSHubから巨人関連X投稿が自動取得されている
- WP下書きにXカードが表示されている
- カテゴリが正しく自動付与されている
- 重複投稿が生成されない
- Cronで定期実行が安定動作している
