# :material-email-multiple: メール lane の住み分け

!!! info "これは何"

    ヨシラバーには目的別にメール lane が複数走っている。
    どの mail がどの責務か整理する。

## :material-table: lane 一覧

`gcloud run jobs list` / `gcloud run services list` 2026-05-27 実行結果に基づく実在 lane。

| lane | 実行場所 | 発信契機 | 中身 |
| --- | --- | --- | --- |
| **publish-notice** (per_post) | publish-notice ジョブ + yoshilover-fetcher サービス内 | 記事の draft / publish 確定 | 1 記事 1 通の通知。 タイトル / 本文抜粋 / 編集 link / 「公開して X 投稿画面へ」 ボタン |
| **x-post-mail** | x-post-mail-lane ジョブ | 時間ごとにバッチ | その時間帯に貯まった X 投稿候補をまとめて配信 |
| **小林誠司名言** | kobayashi-meigen-mail-lane ジョブ | 朝 / 昼 / 夕方 / 夜のシリーズ | 小林誠司の名言を X 投稿候補として 1 件出す |
| **坂本勇人名言** | sakamoto-meigen-mail-lane ジョブ | 1 日 1 回 | 坂本勇人の名言を X 投稿候補として 1 件出す |

## :material-format-list-bulleted: 件名 prefix の使い分け

| prefix | 出すメール | 意図 |
| --- | --- | --- |
| 【緊急】 | publish-notice | 炎上 / 緊急ワード検知 |
| 【投稿候補】 | publish-notice | manual X 候補 (clean かつ safe subtype) |
| 【要確認】 | publish-notice | review reason 検知。 user judgment 必要 |
| 【下書き】 | publish-notice (draft 状態) | 下書き作成通知 |
| 【公開済】 | publish-notice (publish 状態) | 公開済み記事の通知 |
| 【まとめ】 | publish-notice (burst summary) | 一度に多発したとき集約 |
| (X-post 案ヘッダー: 「巨人データXポスト案」 / 「巨人Xポスト案」) | x-post-mail | 候補の中身による分岐 (詳細は [X 投稿候補メール](x-post-mail.md)) |

## :material-content-duplicate: dedup window

| lane | window |
| --- | --- |
| publish-notice (per_post) | 同 post_id を ==24 時間以内に 1 回== まで |
| x-post-mail | 同 signature (combo) を ==24 時間以内に 1 回== まで、 starvation 時は緩和 |
| 小林 / 坂本名言 | sent_cursor で過去送信履歴を持ち、 重複 archive 番号は除外 (`load_sent_cursor` / `append_sent_cursor`) |

## :material-cursor-pointer: 投稿ボタンの種類

mail に出るボタン (押すと X 投稿などに飛ぶ) には複数経路がある。

| ボタン | 飛び先 | 画像 | 確定動作 |
| --- | --- | --- | --- |
| 🚀 公開して X 投稿画面へ | `/publish-and-tweet?...` (HMAC token 24h) | なし | draft なら publish 化 + X compose 画面 |
| 📰 記事を見る | 記事 URL 直接 | (記事閲覧) | サイト本文を開く |
| 📱 画像つきで X に投稿 (おすすめ) | `/share-x?...` (Web Share API) | あり (端末対応時) | Web Share で X app に画像 + テキスト share |
| ✏️ WP 編集画面で確認 | `admin_edit_url` (WP 管理画面) | (編集画面) | WP 編集ページを開く |
| 🐦 X で投稿 (x-post-mail 内) | X intent URL 直接 | なし | テキストだけ X compose に渡す |
| 🐦 画像つきで X に投稿 (x-post-mail 内) | `/share-x-cand?...` (GCS PNG + Web Share) | あり (端末対応時) | x-post-mail 候補 PNG を Web Share で X app に直送 |

## :material-link: 関連 spec ページ

- [通知メール (publish-notice)](publish-notice.md)
- [X 投稿候補メール (x-post-mail)](x-post-mail.md)
