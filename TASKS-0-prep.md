# TASKS-0-prep.md — 事前準備タスク（手動作業）

> フェーズ①の手動作業。Claude Codeが開発を始める前にすべて完了させる。
> 完了したら `☐` を `☑` に変える（HOW-TO.md のsedコマンド参照）。

---

## WP設定

☐ WPアプリケーションパスワードを発行
> WP管理画面 → ユーザー → プロフィール → アプリケーションパスワード

☐ REST API疎通確認（ブラウザ）
> ブラウザで `https://yoshilover.com/wp-json/wp/v2/posts` にアクセスしてJSONが返るか確認

☐ REST API疎通確認（エックスサーバー外部アクセス）
> SSH接続後、`curl https://yoshilover.com/wp-json/wp/v2/posts` を実行してJSONが返るか確認。スクリプトから叩けることを保証する。（P5前提条件）

☐ WPカテゴリ8種を作成
> 投稿 → カテゴリ。試合速報 / 選手情報 / 首脳陣 / ドラフト・育成 / OB・解説者 / 補強・移籍 / 球団情報 / コラム

☐ カテゴリに色を設定
> 各カテゴリ編集画面でカラーコードを設定。試合速報:#F5811F / 選手情報:#003DA5 / 首脳陣:#555555 / ドラフト・育成:#2E8B57 / OB・解説者:#7B4DAA / 補強・移籍:#E53935 / 球団情報:#F9A825 / コラム:#1A1A1A

☐ 各カテゴリのWP IDをメモ
> WP管理画面 → 投稿 → カテゴリ → 各カテゴリのIDをconfig/categories.jsonに記録

☐ REST APIが403の場合
> WP管理画面 → 設定 → パーマリンク → 「投稿名」に変更して保存

---

## SWELL設定

☐ SEO SIMPLE PACK をインストール
> WP管理画面 → プラグイン → 新規追加 → 「SEO SIMPLE PACK」で検索 → インストール → 有効化（SWELL推奨SEOプラグイン）

☐ SEO SIMPLE PACK の初期設定
> サイト名・ディスクリプション・OGP設定・noindex設定（固定ページなど）を行う

☐ SWELLテーマに切り替え
> WP管理画面 → 外観 → テーマ → SWELLを有効化

☐ メインカラー設定
> カスタマイザー → サイト全体設定 → `#F5811F`

☐ テキストカラー設定
> カスタマイザー → サイト全体設定 → `#333333`

☐ リンクカラー設定
> カスタマイザー → サイト全体設定 → `#003DA5`

☐ 背景色設定
> カスタマイザー → サイト全体設定 → `#F5F5F0`

☐ ヘッダー背景設定
> カスタマイザー → ヘッダー → `#1A1A1A`（ヘッダー下ボーダー `#F5811F` 4px）

☐ 追加CSSを記述
> カスタマイザー → 追加CSS → AGENTS.md の「追加CSS」セクションをコピペ

☐ 記事一覧をリスト型に変更
> カスタマイザー → 記事一覧リスト → リスト型を選択

☐ 固定ページ作成
> プライバシーポリシー / 免責事項 / お問い合わせ の3ページを作成・公開

☐ テスト記事を3〜5本手動投稿
> 各カテゴリに1本ずつ、Xポスト埋め込みを含む記事を手動で作成

☐ スマホ表示が崩れていないか確認
> Chrome DevTools または実機で確認。8カテゴリが色付きで表示されているか確認。

---

## SSH設定（エックスサーバー）

☐ SSH設定をONにする
> エックスサーバー管理画面（Xserverアカウント） → SSH設定 → ONにする

☐ SSH鍵ペアを生成してサーバーに登録
> ローカルで `ssh-keygen -t ed25519 -C "yoshilover"` → 公開鍵をXserver管理画面に登録

☐ SSH接続テスト成功
> `ssh -p 10022 （ユーザー名）@（サーバー名）.xserver.jp` で接続確認

☐ Python3のバージョン確認
> SSH接続後 `python3 --version` を実行。3.8以上であれば問題なし。

☐ pip3が使えるか確認
> `pip3 --version` を実行。使えない場合は `python3 -m pip --version` で確認。

---

## X Developer Portal設定（フェーズ⑤の準備）

☐ developer.x.com にログイン
> @yoshilover6760 でログイン

☐ プロジェクト作成
> 新規プロジェクト＋アプリを作成（App名：yoshilover）

☐ API Key / Secret 取得
> Consumer Keys セクションからコピー → `.env` に控えておく

☐ Access Token / Secret 取得
> Authentication Tokens セクションから生成してコピー → `.env` に控えておく

☐ Client ID / Client Secret を取得
> OAuth 2.0 用の認証情報。X Developer Portal → アプリ設定 → Keys and tokens → OAuth 2.0 Client ID and Client Secret → `.env` の X_CLIENT_ID / X_CLIENT_SECRET に記入（P8 フェーズ⑤導入手順 step3）

☐ Credits メニューから $5 チャージ
> フェーズ⑤に入るまでチャージしなくてもよい。準備だけしておく。

---

## 301リダイレクト・記事移行

☐ yoshilover.com の下書きゴミ箱記事を整理
> 不要な下書き・ゴミ箱記事を削除してから移行作業を開始

☐ 残り170記事をXMLエクスポート
> WP管理画面 → ツール → エクスポート → 「すべてのコンテンツ」

☐ prosports側にXMLインポート
> prosports側WP管理画面 → ツール → インポート → WordPress

☐ インポート後すぐに全記事を「下書き」に変更
> 一括編集機能を使ってインポートした記事をすべて下書きに変更（誤公開防止）

☐ リライト完了した記事から1本ずつ公開
> 下書きを確認・リライト・SEO確認してから1本ずつ公開していく
