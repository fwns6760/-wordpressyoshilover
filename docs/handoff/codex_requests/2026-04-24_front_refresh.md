# 2026-04-24_front_refresh — トップ画面の圧強化 + sidebar 4 段

## 目的

- のもとけ風の「圧」をトップに足す(header 黒 + orange 4px / cat-nav / tag-nav / topic-hub 見た目強化)
- sidebar を 4 段固定にして、読む順を整える
- 既存の稼働中 block(`yoshi-topic-hub` = front_top widget で常設 / `yoshi-breaking-strip` `yoshi-article-bundles` `yoshi-sns-reactions` = 記事詳細で稼働中)は触らない
- 未配線 block(`yoshi-today-giants` / `yoshi-sidebar-rail` / `yoshi-front-card`)は本便では追加配線しない

## 実画面の前提(2026-04-24 read-only 確認済)

- SWELL + `swell_child` あり(親テーマ直編集 NG、子テーマで override する)
- トップ `w-frontTop` の現状: `widget_text` → `yoshi-topic-hub`(今週の話題 4件) → `widget_recent_entries`
- `yoshi-today-giants` / `yoshi-sidebar-rail` / `yoshi-front-card` は DOM 0(= 未配線、今回は触らない)
- sidebar は `-sidebar-on` / `-frame-on-sidebar`。widget は現状薄い

## 対象ファイル / 対象リソース

- `src/custom.css`(SWELL 「追加 CSS」にデプロイされる経路を踏襲。既存と同じフロー)
- `src/yoshilover-063-frontend.php`(cat-nav / tag-nav 追加 shortcode + `wp_body_open` 出力)
- `swell_child/header.php`(新規 override。親 `swell/header.php` をコピーしてロゴ横に巨人 badge + `@yoshilover6760` 差し込み)
- WP 側 widget 並べ直し(`sidebar`(primary)に X banner / POPULAR(`yoshi_sidebar_popular` shortcode)/ CATEGORY / FAMILY / ARCHIVE の順)

## やること

### CSS (`src/custom.css`)

- header 用に `.yoshi-site-header`(新規) クラスを追加
  - 背景 `var(--black)`、下辺 `4px solid var(--orange)`、sticky top:0
  - ロゴは Oswald 22px 白、orange の「巨人」badge、orange の `@yoshilover6760` テキストリンク、検索アイコン
- `.yoshi-cat-nav`(新規): 白背景 1 段、横スクロール、active は `border-bottom 3px var(--orange)` + `color var(--orange)`、カテゴリ色ドット `.dot`(既存 color palette 流用)
- `.yoshi-tag-nav`(新規): `#F0EEE8` 背景、chip 横スクロール、`hot` chip は `var(--orange-light)` + `var(--orange)` 文字
- `.yoshi-topic-hub` は既存踏襲。**見た目だけ**圧強化(見出し Oswald + 左 4px orange bar を現行維持。背景 `var(--white)` のまま、上辺 `3px solid var(--orange)` を維持)
- 既存 `.l-sidebar .widget` の見た目を 4 段固定前提で整える(widget-title 黒背景 + orange 4px 左 border、`.widget_categories` 行 count 右寄せ、`.widget_archive` 同様)
- mobile 390px ガード: cat-nav / tag-nav は横スクロール維持。タップ領域最小 44×44

### Plugin (`src/yoshilover-063-frontend.php`)

- 新規 shortcode `[yoshilover_cat_nav]`
  - 固定カテゴリ順: `shiai-sokuho` / `senshu-joho` / `syuno` / `draft-ikusei` / `ob-kaisetsusha` / `hoko-iseki` / `kyudan-joho` / `column`
  - 各項目にカテゴリ色ドット
  - 現在地(is_category / is_home)で active 付与
- 新規 shortcode `[yoshilover_tag_nav]`
  - 選手タグ(最大 10)+ 話題タグ(最大 4)
  - `hot` は管理画面の option(新規 `yoshilover_063_tag_nav_hot`)で指定。フォールバック無し(空なら `hot` なし)
- `wp_body_open` hook で header 直下に `[yoshilover_cat_nav]` + `[yoshilover_tag_nav]` を出力
  - ただし front_top widget の前に出るよう order を調整
  - 無限ループ防止のため `is_admin()` / REST / feed / embed を除外

### 子テーマ (`swell_child/header.php`)

- 親 `swell/header.php` を子にコピーして override(親テーマ直編集しない)
- ロゴ `<a class="c-siteBrand__logo">` の直後に以下を差し込む:
  - `<span class="yoshi-logo-badge">巨人</span>`
  - `<a class="yoshi-header-x" href="https://x.com/yoshilover6760" rel="nofollow">@yoshilover6760</a>`
- 既存 SWELL の header ノード class は破壊しない(JS hook 互換維持)

### Widget 並べ直し(WP admin / wp-cli)

- primary sidebar の widget 順序を次の 5 段に固定:
  1. X banner(text widget に既存 HTML)
  2. `[yoshilover_sidebar_popular]`(既存 shortcode、plugin 側で実装済)
  3. `widget_categories`(Count 表示 ON)
  4. FAMILY STORIES(text widget、prosports 3 本)
  5. `widget_archive`(Count 表示 ON)
- 他の widget は全部外す(sidebar 重複解消のため)
- 変更前に WP admin の widget 状態を `wp option get widget_text` / `wp option get sidebars_widgets` で記録

## NG(触らないもの)

- `src/rss_fetcher.py` / `src/wp_client.py` / validator 系(body / title / fact / source / nucleus / comment / social 系)
- `automation.toml` / scheduler / Cloud Run revision
- `src/mail_delivery_bridge.py` / `src/*_email_sender.py` / `src/*_email_*.py`
- X API / `src/x_*.py` / `src/media_xpost_selector.py`
- 記事生成 path(`src/*_prompt_builder.py` / `src/first_wave_promotion.py` / `src/postgame_revisit_chain.py`)
- 親テーマ `wp-content/themes/swell/*` の直接編集
- 既に稼働中の block の DOM 出力変更(`yoshi-topic-hub` の出力内容 / `yoshi-breaking-strip` 記事詳細版 / `yoshi-article-bundles` / `yoshi-sns-reactions` / `yoshilover-related-posts`)
- 未配線 block(`yoshi-today-giants` / `yoshi-sidebar-rail` / `yoshi-front-card`)の新規配線(= 別便判断)

## smoke

- `https://yoshilover.com/` を curl して以下を確認:
  - `yoshi-site-header` クラスが DOM に出ている
  - `yoshi-cat-nav` / `yoshi-tag-nav` が header 直下に出ている
  - `yoshi-topic-hub` が今まで通り「今週の話題」4件で出ている(回帰なし)
  - sidebar の widget が X banner → POPULAR → CATEGORY → FAMILY → ARCHIVE の順
- `https://yoshilover.com/62965` を curl して以下を確認:
  - 記事詳細の `yoshi-breaking-strip` / `yoshi-article-bundles` / `yoshi-sns-reactions` / `yoshilover-related-posts` が回帰なしで出ている
  - header 圧強化が記事詳細にも反映されている
- mobile emulation(Chrome devtools 390×844)で:
  - cat-nav / tag-nav が横スクロール
  - sidebar が main の下に回り込む
  - タップ領域 44×44 以上

## commit / push

- 子テーマ `swell_child/header.php` 新規
- `src/custom.css` 追記(既存セクションを壊さない、末尾追記 or 既存 header/nav セクション新設)
- `src/yoshilover-063-frontend.php` 追記(cat-nav / tag-nav shortcode + `wp_body_open` hook)
- `build/063-v8-wp-admin/` を新規生成し `manifest.json` 更新

```
git add src/custom.css src/yoshilover-063-frontend.php swell_child/header.php build/063-v8-wp-admin/
git commit -m "063-v8: top header bold + cat/tag nav + sidebar 4-tier (non-breaking)"
git push origin master
```

## 成果物 / response doc

- `docs/handoff/codex_responses/2026-04-24_front_refresh.md` に以下を記載:
  - smoke 結果(curl 出力抜粋 + mobile 確認有無)
  - 変更ファイルの diff サマリ
  - 親テーマに触れていないことの確認
  - 既存稼働 block の回帰なし確認

## 監査側で別起票するもの(Codex 作業対象外)

- T-026: `yoshi-today-giants` 未配線(plugin に shortcode あるが widget にも出力 hook にも入っていない)
- T-027: `yoshi-sidebar-rail` auto-inject 未着弾(`dynamic_sidebar_before` に登録済だが DOM 0)
- T-028: `yoshi-front-card` の `.is-yoshi-front-density` scope 未配線(CSS 定義あるが body/wrapper に class が付いていない)
