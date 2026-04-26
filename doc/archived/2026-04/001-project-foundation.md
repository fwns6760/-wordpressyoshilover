# 001 — プロジェクト共通基盤

**フェーズ：** 全フェーズ共通（最初に作る）  
**担当：** Claude Code  
**依存：** なし（これが完了してから他チケットに進む）

---

## 概要

全スクリプトが共有するディレクトリ構成・設定ファイル・環境変数テンプレート・依存パッケージ定義を作成する。
一度作れば以後のチケットで使い回す土台。

---

## TODO

### ディレクトリ・ファイル骨格

【×】`src/` ディレクトリを作成  
【×】`config/` ディレクトリを作成  
【×】`data/` ディレクトリを作成  
【×】`logs/` ディレクトリを作成  
【×】`logs/.gitkeep` を作成（空ディレクトリをgit管理対象にする）  

### 環境変数

【×】`.env.example` を作成（下記テンプレートで）  
【×】`.env` は `.env.example` をコピーして手動記入（git管理対象外）  

### 依存パッケージ

【×】`requirements.txt` を作成  

### 除外設定

【×】`.gitignore` を作成  

### 設定ファイル

【×】`config/categories.json` を作成（カテゴリ名→WP IDマッピング。IDはWP管理画面で確認後に記入）  
【×】`config/rss_sources.json` を作成（RSSフィードURL一覧。実在確認後に記入）  
【×】`config/keywords.json` を作成（カテゴリ自動分類キーワードルール）  

### 履歴データ初期化

【×】`data/posted_urls.json` を `{}` で作成（投稿済みURL履歴・重複防止）  
【×】`data/rss_history.json` を `{}` で作成（RSS取得済み記事履歴）  

---

## 仕様詳細

### ディレクトリ構成

```
yoshilover/
├── .env.example
├── .env               ← gitignore対象
├── .gitignore
├── requirements.txt
├── config/
│   ├── categories.json
│   ├── rss_sources.json
│   └── keywords.json
├── data/
│   ├── posted_urls.json
│   └── rss_history.json
├── logs/
│   └── .gitkeep
└── src/
    ├── wp_client.py
    ├── wp_draft_creator.py
    ├── rss_fetcher.py
    ├── x_post_generator.py
    └── x_api_client.py
```

### .env.example

```dotenv
# WordPress
WP_URL=https://yoshilover.com
WP_USER=（管理者ユーザー名）
WP_APP_PASSWORD=（アプリケーションパスワード）

# X API（フェーズ⑤で追記）
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_CLIENT_ID=
X_CLIENT_SECRET=
```

### requirements.txt

```
requests
python-dotenv
feedparser
tweepy
```

### .gitignore

```
.env
logs/*.log
data/*.json
__pycache__/
*.pyc
```

### config/categories.json（初期テンプレート）

```json
{
  "試合速報": 0,
  "選手情報": 0,
  "首脳陣": 0,
  "ドラフト・育成": 0,
  "OB・解説者": 0,
  "補強・移籍": 0,
  "球団情報": 0,
  "コラム": 0
}
```

> WP管理画面 → 投稿 → カテゴリ で各カテゴリのIDを確認して `0` を実際のIDに書き換える。

### config/rss_sources.json（初期テンプレート）

```json
[
  {"name": "スポーツ報知（巨人）", "url": ""},
  {"name": "日刊スポーツ（巨人）", "url": ""},
  {"name": "スポニチ（巨人）",     "url": ""},
  {"name": "東スポ（巨人）",       "url": ""},
  {"name": "Yahoo!スポーツナビ",  "url": ""}
]
```

> URLは実在確認後に記入。`curl <url>` でXMLが返ればOK。

### config/keywords.json（初期テンプレート）

```json
{
  "試合速報":    ["スコア", "勝", "敗", "打席", "登板", "先発"],
  "選手情報":    ["成績", "打率", "防御率", "本塁打"],
  "首脳陣":      ["監督", "コーチ", "采配", "起用"],
  "ドラフト・育成": ["ドラフト", "育成", "2軍", "ファーム"],
  "OB・解説者":  ["OB", "解説"],
  "補強・移籍":  ["FA", "トレード", "移籍", "獲得", "外国人"],
  "球団情報":    ["チケット", "グッズ", "イベント", "東京ドーム"]
}
```

---

## 完了条件

- `src/` `config/` `data/` `logs/` が存在する  
- `.env.example` に全キーが記載されている  
- `requirements.txt` に4ライブラリが記載されている  
- `config/*.json` がパース可能な有効なJSONである  
