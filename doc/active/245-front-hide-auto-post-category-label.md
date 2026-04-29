# 245 front hide internal auto-post category label

- number: 245
- type: front / category display hardening
- status: READY
- priority: P0.5
- owner: Codex A or front-scope Codex
- lane: A / front-scope
- created: 2026-04-29
- related: 063, 087, 195, 197, 244

## 背景

画面上にカテゴリ名として **「自動投稿」** が出るのは不自然。

`自動投稿` / `auto-post` / category id `673` は内部処理用のカテゴリであり、ユーザー向け front 画面のカテゴリ導線・カテゴリ chip・記事 meta・関連記事 context へ出すべきではない。

既に X posting 側では `AUTO_POST_CATEGORY_ID = 673` を special case として扱っているが、frontend plugin 側では sidebar / front density / article context で category terms をそのまま使っている箇所がある。

## 目的

- front 画面から内部カテゴリ `自動投稿` を隠す
- WP 側のカテゴリ付与や既存記事の category は変更しない
- 記事公開 / X / Gemini / Cloud Run には一切触らない

## 現状の候補箇所

`src/yoshilover-063-frontend.php`

- `yoshilover_063_get_sidebar_category_links()`
  - 現状除外: `uncategorized`, `old-articles`
  - 追加除外: `auto-post`, `auto_post`, name `自動投稿`, term_id `673`
- `yoshilover_063_get_post_term_names()`
  - article card / front density / article context で category 名を返す
  - taxonomy が `category` の時だけ内部カテゴリを除外
- `yoshilover_063_front_density_primary_player()`
  - `get_the_category()` を player/token 候補として見る
  - `自動投稿` を player/tag 文脈に混ぜない

## 実装方針

### 1. helper 追加

`src/yoshilover-063-frontend.php` に internal category 判定 helper を追加する。

```php
function yoshilover_063_is_internal_auto_post_category( $term ) {
    if ( ! ( $term instanceof WP_Term ) ) {
        return false;
    }

    $term_id = (int) $term->term_id;
    $name    = trim( (string) $term->name );
    $slug    = trim( (string) $term->slug );

    return $term_id === 673
        || $name === '自動投稿'
        || in_array( $slug, array( 'auto-post', 'auto_post' ), true );
}
```

### 2. 表示側から除外

以下で helper を使って skip する。

- `yoshilover_063_get_sidebar_category_links()`
- `yoshilover_063_get_post_term_names()` の `category` taxonomy のみ
- `yoshilover_063_front_density_primary_player()` の category group

### 3. 触らないもの

- WP category 自体の削除
- 既存 post の category 付け替え
- `AUTO_POST_CATEGORY_ID` backend logic
- X live post
- Cloud Run / Scheduler / env / Secret
- publish gate
- Gemini / LLM

## tests / verify

PHP unit が無い場合は最小 smoke でよい。

- `php -l src/yoshilover-063-frontend.php`
- grep で helper と call site を確認
  - `grep -n "yoshilover_063_is_internal_auto_post_category" src/yoshilover-063-frontend.php`
- 可能なら local PHP fixture または static inspection:
  - sidebar category links で `自動投稿` を skip
  - post term names で category `自動投稿` を skip
  - tag taxonomy は影響なし

## live verify

live deploy は別判断。

deploy 後:

- top / category / single post の画面に `自動投稿` category label が出ない
- 他カテゴリの label / chip / sidebar は消えていない
- fatal error なし
- layout 崩れなし

## acceptance

- `自動投稿` / `auto-post` / term_id `673` が front category display に出ない
- 他カテゴリはそのまま表示
- internal category assignment は維持
- Python backend / GCP / WP publish status / X / Gemini に diff なし
- `php -l` pass
- explicit path stage、`git add -A` 禁止
