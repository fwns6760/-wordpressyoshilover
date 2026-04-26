# 003 — フェーズ② wp_client.py（共通WPクライアント）

**フェーズ：** ②  
**担当：** Claude Code  
**依存：** 001（共通基盤）、002（カテゴリWP IDが確定していること）  
**ファイル：** `src/wp_client.py`

---

## 概要

全スクリプトから共通で呼び出すWP REST APIクライアントライブラリ。
認証・投稿・取得の共通処理をまとめる。
004〜007のスクリプトはすべてこのモジュールを `import` して使う。

---

## TODO

### 実装

【×】`src/wp_client.py` を作成  

【×】`create_draft(title, content, categories=None) -> int` を実装  
> WP REST API `POST /wp-json/wp/v2/posts` で下書き投稿。返り値は投稿されたpost_id。

【×】`get_post(post_id) -> dict` を実装  
> WP REST API `GET /wp-json/wp/v2/posts/{id}` で記事取得。

【×】`get_categories() -> list[dict]` を実装  
> WP REST API `GET /wp-json/wp/v2/categories` でカテゴリ一覧取得。`{id, name, slug}` のリストを返す。

【×】カテゴリ名→ID変換ヘルパー `resolve_category_id(name) -> int` を実装  
> `config/categories.json` を読み込んでカテゴリ名からIDを返す。

【×】`--test` オプションでCLI単体実行できるようにする  
> `python3 src/wp_client.py --test` でカテゴリ一覧を取得・表示。疎通確認用。

### テスト・確認

【×】ローカル環境で `python3 src/wp_client.py --test` が通ること  

【×】WP REST APIにGETリクエストが通り、カテゴリ一覧がJSON返ること  

【×】`create_draft()` でテスト下書きが生成されること  
> WP管理画面で下書きが生成されているか目視確認。確認後は削除してOK。

---

## 仕様詳細

### 認証方式

Basic認証（WPアプリケーションパスワード）  
`.env` の `WP_USER` と `WP_APP_PASSWORD` を使用。

```python
auth = (os.getenv("WP_USER"), os.getenv("WP_APP_PASSWORD"))
response = requests.post(url, json=payload, auth=auth)
```

### エンドポイント

| 操作 | メソッド | エンドポイント |
|------|---------|--------------|
| 下書き投稿 | POST | `/wp-json/wp/v2/posts` |
| 記事取得 | GET | `/wp-json/wp/v2/posts/{id}` |
| カテゴリ一覧 | GET | `/wp-json/wp/v2/categories?per_page=100` |

### 下書き投稿のリクエストボディ

```json
{
  "title":      "記事タイトル",
  "content":    "<!-- wp:embed ... -->",
  "status":     "draft",
  "categories": [カテゴリID]
}
```

### エラーハンドリング

- HTTP 401：認証失敗 → `.env` の認証情報を確認するよう案内
- HTTP 403：アクセス拒否 → パーマリンク設定を「投稿名」に変更するよう案内
- HTTP 404：エンドポイント不達 → WP_URLが正しいか確認するよう案内

---

## 完了条件

- `python3 src/wp_client.py --test` でカテゴリ一覧が返ること  
- `create_draft()` で下書きが生成されること  
- 他スクリプトから `from wp_client import WPClient` でインポートできること  
