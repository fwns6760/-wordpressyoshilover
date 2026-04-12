# AGENTS.md — ヨシラバー サイトリニューアル 設計書

> Claude Code 用設計書。PDF「サイトリニューアル要件定義書兼設計書 v1.0 MVP」(2026-04-08) の内容をエージェントが読める形式に変換。

---

## 設計思想：のもとけモデルを1人＋AIで再現する

dnomotoke.com（中日ドラゴンズまとめ）は2〜3人のチームで以下を運営している：

| のもとけの仕組み | このプロジェクトでの対応 |
|----------------|----------------------|
| スポーツ紙ニュースをRSSで自動収集 | フェーズ③ `rss_fetcher.py` で完全自動化 |
| Xポスト埋め込みが記事の核コンテンツ | フェーズ② `wp_draft_creator.py` でoEmbed下書き自動生成 |
| 試合中スコア変化を自動ツイート | フェーズ⑤ `x_api_client.py` で自動投稿 |
| Xポスト文面を自動生成して投稿 | フェーズ④⑤ `x_post_generator.py` + X API |
| コメント欄でファンのたまり場 | MVP後にwpDiscuzで対応（Phase 6以降） |

**ゴール：AI＋自動化スクリプトで1人で同等の運用を実現する。**

### 人間がやることを最小化する設計

```
【毎朝の作業（5〜10分）】
1. WP管理画面を開く
2. 自動生成された下書き一覧を確認
3. 各下書きに一言コメントを追加（オリジナリティ・差別化）
4. 公開ボタンを押す
5. x_post_generator.py の出力をコピーしてXに投稿

【完全自動（人間不要）】
- RSS取得 → キーワードフィルタ → カテゴリ分類 → WP下書き生成（Cron 1日4回）
- フェーズ⑤以降：WP公開 → X自動投稿（x_api_client.py）
```

---

## プロジェクト概要

| 項目 | 内容 |
|------|------|
| サイト | yoshilover.com（読売ジャイアンツ特化ニュースまとめ） |
| 参考モデル | dnomotoke.com（中日ドラゴンズまとめ）の巨人版 |
| CMS | WordPress（稼働中） |
| テーマ | SWELL（インストール済み） |
| サーバー | エックスサーバー |
| SEOプラグイン | SEO SIMPLE PACK（SWELL推奨） |
| Xアカウント | @yoshilover6760（8,500+フォロワー） |
| X API | 従量課金（$5チャージ、フェーズ⑤で導入） |
| 開発言語 | Python 3.x |
| 核コンテンツ | Xポスト埋め込み |
| 現在の状況 | 既存記事をサブドメインへ301リダイレクト移行中 |

---

## 実装ロードマップ（5フェーズ）

**原則：小さく始めて順番に積む。各フェーズが安定してから次に進む。飛ばさない。**

| # | フェーズ | やること | 担当 |
|---|---------|---------|------|
| ① | SWELL＋カテゴリ固定 | テーマ切り替え、巨人カラー設定、カテゴリ作成、固定ページ作成 | 手動 |
| ② | WP下書き自動生成 | WP REST APIでXポストURL入りの下書き記事を自動生成するスクリプト | Claude Code |
| ③ | RSS取得＋自動分類 | スポーツ紙RSSから巨人記事を自動取得、キーワードでカテゴリ自動付与 | Claude Code |
| ④ | X文案生成 | 記事公開時のXポスト文面を自動生成（ハッシュタグ含む） | Claude Code |
| ⑤ | X API連携 | X API従量課金でポスト収集・自動投稿を接続 | Claude Code |

**MVP対象外（後回し）：** X APIでの自動収集、wpDiscuz、試合速報ウィジェット、LINE通知、AI要約、選手名鑑、AdSense

---

## ディレクトリ構成

```
yoshilover/               ← このリポジトリ
├── AGENTS.md             ← 本ファイル（設計書）
├── TASKS-0-prep.md       ← 事前準備タスク（手動）
├── TASKS-1-dev.md        ← 開発タスク（Claude Code）
├── TASKS-2-deploy.md     ← デプロイ・運用タスク
├── TASKS-3-prosports.md  ← prosportsサイド作業タスク
├── HOW-TO.md             ← コマンド手順書
├── .env.example          ← 環境変数テンプレート
├── .env                  ← 実際の認証情報（gitignore対象）
├── .gitignore
├── requirements.txt
├── config/
│   ├── categories.json   ← カテゴリ名とWP IDのマッピング
│   ├── rss_sources.json  ← RSSフィードURL一覧
│   └── keywords.json     ← カテゴリ自動分類キーワード
├── data/
│   ├── posted_urls.json  ← 投稿済みURL履歴（重複防止）
│   └── rss_history.json  ← RSS取得済み記事履歴
├── logs/
│   └── .gitkeep
└── src/
    ├── wp_client.py          ← WP REST API クライアント（共通）
    ├── wp_draft_creator.py   ← フェーズ②：下書き自動生成
    ├── rss_fetcher.py        ← フェーズ③：RSS取得＋自動分類
    ├── x_post_generator.py   ← フェーズ④：X文案生成
    └── x_api_client.py       ← フェーズ⑤：X API連携
```

---

## 環境変数（.env）

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

---

## フェーズ① SWELL＋カテゴリ固定（手動作業）

### カラー設定

| 設定項目 | 値 |
|---------|---|
| メインカラー | `#F5811F`（ジャイアンツオレンジ） |
| テキストカラー | `#333333` |
| リンクカラー | `#003DA5`（ジャイアンツブルー） |
| 背景色 | `#F5F5F0` |
| ヘッダー背景 | `#1A1A1A`（ブラック） |
| ヘッダー下ボーダー | `#F5811F` 4px |

### カテゴリ（8種）

| カテゴリ | 色 | 内容 |
|---------|---|------|
| 試合速報 | `#F5811F` | 試合結果・スコア |
| 選手情報 | `#003DA5` | 個別選手ニュース |
| 首脳陣 | `#555555` | 監督・コーチ発言 |
| ドラフト・育成 | `#2E8B57` | ドラフト・ファーム |
| OB・解説者 | `#7B4DAA` | OB発言まとめ |
| 補強・移籍 | `#E53935` | FA・トレード |
| 球団情報 | `#F9A825` | イベント・グッズ |
| コラム | `#1A1A1A` | 独自分析記事 |

### 追加CSS

```css
/* ヘッダー下オレンジライン */
.l-header { border-bottom: 4px solid #F5811F; }

/* h2：黒背景＋オレンジ左線 */
.post_content h2 {
  background: #1A1A1A; color: #FFF;
  padding: 12px 16px; border-left: 6px solid #F5811F;
}

/* h3：オレンジ下線 */
.post_content h3 { border-bottom: 3px solid #F5811F; padding-bottom: 6px; }

/* フッター上オレンジライン */
.l-footer { border-top: 4px solid #F5811F; }

/* 記事一覧ホバー */
.-type-list .p-postList__item:hover {
  background: #FFF3E8; transition: background 0.2s;
}
```

---

## フェーズ② WP下書き自動生成

### スクリプト：`src/wp_draft_creator.py`

**入力：** XポストURLのリスト（テキストファイル or 引数）  
**出力：** WordPressに「下書き」記事を自動生成

**処理フロー：**
1. XポストURLを受け取る（`--url` 単体 or `--file` 複数）
2. oEmbed用ブロックHTMLを生成
   ```
   <!-- wp:embed {"url":"https://x.com/..."} -->
   <figure class="wp-block-embed">...</figure>
   <!-- /wp:embed -->
   ```
3. 記事タイトルを仮生成（URLから抽出 or `--title` で手動指定）
4. WP REST API（`POST /wp-json/wp/v2/posts`）で下書き投稿
   - `status: "draft"`
   - `content:` oEmbedブロック
   - `categories:` 指定があれば（`--category`）
5. 投稿後、`data/posted_urls.json` にURLを記録（重複防止）

**CLIオプション：**
```
python src/wp_draft_creator.py --url https://x.com/...
python src/wp_draft_creator.py --file urls.txt --category 試合速報
python src/wp_draft_creator.py --url https://x.com/... --title "巨人が開幕3連勝"
```

---

## フェーズ③ RSS取得＋自動分類

### スクリプト：`src/rss_fetcher.py`

**取得ソース：**

| ソース | 種別 | 備考 |
|--------|------|------|
| スポーツ報知（巨人） | RSS | 読売系、最速 |
| 日刊スポーツ（巨人） | RSS | 番記者取材が豊富 |
| スポニチ（巨人） | RSS | 選手コメント充実 |
| 東スポ（巨人） | RSS | 独自ネタ・話題性 |
| Yahoo!スポーツナビ | RSS | 各社記事の集約 |

**処理フロー：**
1. `config/rss_sources.json` からフィードURL一覧を読み込む
2. feedparser で各RSSフィードを取得
3. キーワードフィルタ（「巨人」「ジャイアンツ」「東京ドーム」等）
4. 重複チェック（`data/rss_history.json` で管理）
5. カテゴリ自動分類（`config/keywords.json` のルールでマッチ）
6. `wp_client.py` 経由でWP下書き生成
7. Cronで1日3〜4回定期実行

**自動分類ルール（`config/keywords.json`）：**

| キーワード | カテゴリ |
|-----------|---------|
| スコア, 勝, 敗, 打席, 登板, 先発 | 試合速報 |
| 個人名, 成績, 打率, 防御率 | 選手情報 |
| 監督, コーチ, 采配, 起用 | 首脳陣 |
| ドラフト, 育成, 2軍, ファーム | ドラフト・育成 |
| OB, 解説, 〇〇さん | OB・解説者 |
| FA, トレード, 移籍, 獲得, 外国人 | 補強・移籍 |
| チケット, グッズ, イベント, 東京ドーム | 球団情報 |

**著作権配慮：** 記事本文は取得しない。タイトル・URL・日時のみ使用。本文はオリジナルコメントを追記して差別化。

---

## フェーズ④ X文案生成

### スクリプト：`src/x_post_generator.py`

**入力：** 記事タイトル、カテゴリ、記事URL（または `--post-id` でWP REST APIから取得）  
**出力：** Xポスト用テキスト（stdout）

**処理フロー：**
1. 記事タイトルを取得
2. カテゴリに応じたハッシュタグを付与
3. 記事URLを整形
4. 140字以内に収める
5. stdoutに出力（コピペ用）

**ハッシュタグルール：**
```
必須：#巨人 #ジャイアンツ
任意：#プロ野球 #NPB #セリーグ
選手別：記事タイトルから選手名を検出して自動付与
```

**出力例：**
```
巨人、広島に3-2で勝利！ウィットリーが7回2失点の好投
https://yoshilover.com/archives/xxxxx
#巨人 #ジャイアンツ #プロ野球
```

**CLIオプション：**
```
python src/x_post_generator.py --title "タイトル" --url https://... --category 試合速報
python src/x_post_generator.py --post-id 123
```

---

## フェーズ⑤ X API連携

### スクリプト：`src/x_api_client.py`

**注意：フェーズ①〜④が安定稼働してから着手すること。**

**X API料金（従量課金・2026年4月時点）：**

| 操作 | 単価 | 月間想定 | 月間コスト |
|------|------|---------|----------|
| ポスト投稿（Create） | $0.01/件 | 300件 | $3（約450円） |
| ポスト読み取り（Read） | $0.005/件 | 1,500件 | $7.5（約1,100円） |
| **合計（想定）** | | | **約1,550円/月** |

初期チャージ：$5（約800円）。残高ゼロで自動停止（追加請求なし）。

**サブコマンド：**
```
python src/x_api_client.py post --post-id 123   # WP記事→X自動投稿
python src/x_api_client.py collect              # 巨人関連ポスト収集→WP下書き
```

**コスト節約ルール：**
- 読み取り（GET）は1日2〜3回に絞る
- 同一ポストの24時間以内の再取得はカウントされない
- `data/rss_history.json` で履歴管理し、API経由の重複チェックを避ける

---

## 共通ライブラリ：`src/wp_client.py`

全スクリプトから呼び出すWP REST APIクライアント。

**提供する関数：**
```python
create_draft(title, content, categories=None) -> post_id
get_post(post_id) -> dict
get_categories() -> list[dict]  # {id, name, slug}
```

**認証：** Basic認証（WPアプリケーションパスワード）

---

## 技術スタック

```
Python 3.x
requests        # WP REST API 呼び出し
python-dotenv   # 環境変数管理
feedparser      # RSS パース（フェーズ③）
tweepy          # X API クライアント（フェーズ⑤）
```

---

## エックスサーバーへのデプロイ手順

### 1. SSH接続設定

1. エックスサーバー管理画面 → SSH設定 → ONにする
2. ローカルでSSH鍵ペアを生成：
   ```bash
   ssh-keygen -t ed25519 -C "yoshilover"
   ```
3. エックスサーバー管理画面で公開鍵を登録
4. 接続テスト：
   ```bash
   ssh -p 10022 （ユーザー名）@（サーバー名）.xserver.jp
   ```

### 2. ファイルをアップロード

```bash
# SCPでプロジェクト一式を転送
scp -P 10022 -r ./yoshilover/ （ユーザー名）@（サーバー名）.xserver.jp:~/
```

### 3. サーバー上でセットアップ

```bash
# Python確認
python3 --version

# pip確認
pip3 --version

# 依存パッケージのインストール
cd ~/yoshilover
pip3 install --user -r requirements.txt

# .envを作成（.env.exampleをコピーして記入）
cp .env.example .env
nano .env

# logsディレクトリ作成
mkdir -p logs
```

### 4. 動作テスト

```bash
# WP REST API疎通テスト
python3 src/wp_client.py --test

# 下書き生成テスト（XポストURLで試す）
python3 src/wp_draft_creator.py --url https://x.com/yoshilover6760/status/XXXXX

# RSS取得テスト
python3 src/rss_fetcher.py --dry-run

# X文案生成テスト
python3 src/x_post_generator.py --title "テスト記事" --url https://yoshilover.com/ --category 試合速報
```

### 5. Cron設定

エックスサーバー管理画面 → Cron設定 から登録：

```cron
# RSS自動取得（1日4回：7時・11時・17時・21時）
0 7,11,17,21 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/rss_fetcher.py >> /home/（ユーザー名）/yoshilover/logs/rss_fetcher.log 2>&1
```

---

## 運用ペース（段階拡大）

| 期間 | ペース | 内容 |
|------|--------|------|
| 初日 | 手動5記事 | wp_draft_creator.py で下書き生成→確認→公開 |
| 1週間 | 1日3〜5記事 | RSS自動取得＋手動確認＋公開フロー確立 |
| 2週間 | 1日5〜10記事 | フローが安定したら増量 |
| 1ヶ月 | フロー定着 | RSS自動取得＋手動確認＋公開が日課に |
| フェーズ⑤以降 | X API導入 | 自動投稿・ポスト収集を追加 |

---

## 注意事項・ルール

- **フェーズは順番に進める。飛ばさない。**
- **著作権**：記事本文は取得しない。タイトル・URL・日時のみ。本文はオリジナルコメントを追記する。
- **X APIコスト**：残高ゼロで自動停止するため追加請求は発生しない。初期$5チャージで始める。
- **REST APIが403の場合**：WP管理画面 → 設定 → パーマリンク → 「投稿名」に変更して保存で解決することが多い。
- **各カテゴリのWP IDのメモ**：`config/categories.json` に設定後、WP管理画面で実際のIDを確認して更新すること。
