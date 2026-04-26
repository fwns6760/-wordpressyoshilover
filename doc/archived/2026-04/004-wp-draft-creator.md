# 004 — フェーズ② wp_draft_creator.py（下書き自動生成）

**フェーズ：** ②  
**担当：** Claude Code  
**依存：** 001（共通基盤）、003（wp_client.py）  
**ファイル：** `src/wp_draft_creator.py`

---

## 概要

XポストURLを入力として受け取り、oEmbedブロックHTMLを生成してWordPressに下書き記事を自動投稿するCLIスクリプト。
Claude Codeが開発する最初のスクリプト。

---

## TODO

### 実装

【×】`src/wp_draft_creator.py` を作成  

【×】`--url` オプションを実装（単一XポストURL指定）  
> `python3 src/wp_draft_creator.py --url https://x.com/...`

【×】`--file` オプションを実装（URLリストファイル指定・一括処理）  
> `python3 src/wp_draft_creator.py --file urls.txt`  
> ファイルは1行1URL形式。

【×】`--category` オプションを実装（カテゴリ名で指定）  
> `python3 src/wp_draft_creator.py --url ... --category 試合速報`  
> カテゴリIDは `wp_client.resolve_category_id()` で解決。

【×】`--title` オプションを実装（タイトル手動指定）  
> 省略時はURLから仮タイトルを自動生成（例：「X投稿 2026-04-11」）。

【×】oEmbedブロックHTMLの生成処理を実装  

【×】投稿後に `data/posted_urls.json` へURLを記録する処理を実装  

【×】起動時に `data/posted_urls.json` を読み込んで重複URLをスキップする処理を実装  

### 動作確認

【×】単一URL指定で下書きが生成されること  
> WP管理画面 → 投稿 → 下書き一覧で確認。

【×】複数URL一括処理が動作すること  

【×】`--category` 指定でカテゴリが正しく設定されること  

【×】同じURLを2回渡しても2回目はスキップされること  

【】WP管理画面で下書きを開くとXカードが正しく表示されること  
> 実機確認必須。oEmbedが展開されない場合はブロック形式を見直す。

---

## 仕様詳細

### 処理フロー

```
1. --url / --file からXポストURLを受け取る
2. posted_urls.json を読み込んで重複チェック
3. oEmbed用ブロックHTMLを生成
4. wp_client.create_draft() で下書き投稿
5. 投稿成功後、posted_urls.json にURLを追記
```

### oEmbedブロックHTML

```html
<!-- wp:embed {"url":"https://x.com/user/status/XXXXX","type":"rich","providerNameSlug":"twitter"} -->
<figure class="wp-block-embed is-type-rich is-provider-twitter wp-block-embed-twitter">
  <div class="wp-block-embed__wrapper">
    https://x.com/user/status/XXXXX
  </div>
</figure>
<!-- /wp:embed -->
```

### posted_urls.json 構造

```json
{
  "https://x.com/user/status/111": "2026-04-11T07:00:00",
  "https://x.com/user/status/222": "2026-04-11T08:30:00"
}
```

### CLIオプション一覧

| オプション | 説明 | 例 |
|-----------|------|---|
| `--url` | XポストURL（単体） | `--url https://x.com/...` |
| `--file` | URLリストファイルパス | `--file urls.txt` |
| `--category` | カテゴリ名 | `--category 試合速報` |
| `--title` | 記事タイトル手動指定 | `--title "巨人が開幕3連勝"` |

---

## 完了条件

- XポストURLを渡すとWPに下書き記事が自動生成される  
- WP管理画面で下書きを開くとXカードが正しく表示される  
- カテゴリを指定して下書き生成ができる  
- 重複URLはスキップされる  
