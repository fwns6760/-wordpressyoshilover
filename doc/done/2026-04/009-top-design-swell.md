# 009 — TOPページデザイン SWELL実装

**参照モックアップ：** `yoshilover-top-mockup.html`  
**担当：** 手動（WP管理画面 + カスタマイザー）  
**依存：** 002（SWELL有効化・カテゴリ作成済み）

---

## 概要

`yoshilover-top-mockup.html` のデザインをSWELLテーマで再現する。  
巨人ニュースが時系列で並ぶまとめサイト（dnomotoke.com モデル）。

**完成形のポイント：**
- 黒ヘッダー（オレンジ下ボーダー）＋ロゴ＋Xハンドル
- カテゴリ別カラードットのナビバー（ヘッダー直下・横スクロール）
- 記事一覧リスト型（サムネ＋カテゴリバッジ＋時刻＋タイトル）
- 2カラムレイアウト（メイン＋300px サイドバー）
- サイドバー：Xバナー・カテゴリ・人気記事・prosportsリンク・アーカイブ

---

## TODO

### フロントページ・基本設定

【×】フロントページを「最新の投稿」に変更  
> WP管理画面 → 設定 → 表示設定 → 「最新の投稿」を選択して保存

【×】現在のTOPページ（12球団インデックス）を非公開に変更  
> WP管理画面 → 固定ページ → 該当ページを「非公開」に変更

### カスタマイザー設定

【×】メインカラーを `#F5811F` に設定  
> カスタマイザー → サイト全体設定 → メインカラー

【×】テキストカラーを `#333333` に設定  

【×】リンクカラーを `#003DA5` に設定  

【×】背景色を `#F5F5F0` に設定  

【×】ヘッダー背景色を `#1A1A1A` に設定  
> カスタマイザー → ヘッダー → 背景色

【×】ヘッダーレイアウトを「ロゴ左・ナビ下」に設定  
> カスタマイザー → ヘッダー → レイアウト  
> グローバルナビをヘッダー下に配置する設定

【×】記事一覧をリスト型に変更  
> カスタマイザー → トップページ → 記事一覧レイアウト → リスト

【×】1ページあたりの表示件数を確認・調整  
> WP管理画面 → 設定 → 表示設定 → 「1ページに表示する最大投稿数」→ 15〜20

### メニュー設定

【×】「カテゴリナビ」メニューを新規作成  
> WP管理画面 → 外観 → メニュー → 新しいメニューを作成  
> メニュー名：「カテゴリナビ」

【×】「すべて」リンクをトップに追加  
> カスタムリンク → URL: `/` ・リンク文字列: `すべて`  
> **CSS クラス**: `cat-all`（※表示オプションで「CSSクラス」を有効化してから入力）

【×】試合速報カテゴリを追加・CSS クラス `cat-jiai` を設定  

【×】選手情報カテゴリを追加・CSS クラス `cat-senshu` を設定  

【×】首脳陣カテゴリを追加・CSS クラス `cat-syuno` を設定  

【×】ドラフト・育成カテゴリを追加・CSS クラス `cat-draft` を設定  

【×】OB・解説者カテゴリを追加・CSS クラス `cat-ob` を設定  

【×】補強・移籍カテゴリを追加・CSS クラス `cat-hoko` を設定  

【×】球団情報カテゴリを追加・CSS クラス `cat-kyudan` を設定  

【×】コラムカテゴリを追加・CSS クラス `cat-column` を設定  

【×】このメニューを「グローバルナビ」に設定して保存  

### ウィジェット設定

【×】サイドバーの既存ウィジェットをすべて削除してリセット  
> WP管理画面 → 外観 → ウィジェット → サイドバー

【×】Xバナーウィジェットを追加（カスタムHTML・先頭）  
> 下記「ウィジェット用HTML」セクションのコードを貼り付け

【×】カテゴリウィジェットを追加  
> ウィジェット「カテゴリ」→ タイトル: `CATEGORY` → 投稿数を表示: ON

【×】人気記事ウィジェットを追加  
> 「人気記事」プラグイン（WordPress Popular Posts等）またはカスタムHTML  
> タイトル: `POPULAR`

【×】FAMILY STORIESウィジェットを追加（カスタムHTML）  
> 下記「ウィジェット用HTML」セクションのコードを貼り付け  
> タイトル: `FAMILY STORIES`

【×】アーカイブウィジェットを追加  
> ウィジェット「アーカイブ」→ タイトル: `ARCHIVE` → 投稿数を表示: ON

### 追加CSS

【×】カスタマイザー → 追加CSS に下記「追加CSS全文」を貼り付けて保存  

### 動作確認

【×】TOPページが記事一覧（最新の投稿）になっていること  

【×】カテゴリナビバーが表示され、各ドットに色がついていること  

【×】記事一覧がリスト型で表示されていること  

【×】記事にカーソルを当てると左にオレンジラインが出ること  

【×】サイドバーの5ウィジェットが正しく表示されること  

【×】スマホでカテゴリナビが横スクロールできること  

【×】スマホでサイドバーが記事一覧の下に来ること  

---

## 追加CSS全文

カスタマイザー → 追加CSS にそのまま貼り付け。

```css
/* ============================================================
   YOSHILOVER — 追加CSS
   モックアップ: yoshilover-top-mockup.html
   ============================================================ */

/* Google Fonts: Oswald（ロゴ・見出しフォント）読み込み */
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap');

/* CSS変数 */
:root {
  --orange:      #F5811F;
  --orange-light:#FFF3E8;
  --blue:        #003DA5;
  --black:       #1A1A1A;
  --dark-gray:   #333333;
  --mid-gray:    #666666;
  --light-gray:  #E8E8E8;
  --bg:          #F5F5F0;
  --white:       #FFFFFF;
  --red:         #E53935;
  --green:       #2E8B57;
  --purple:      #7B4DAA;
  --gold:        #F9A825;
}

/* ============================================================
   ヘッダー
   ============================================================ */

/* ヘッダー全体：黒背景・オレンジ下ボーダー・sticky */
.l-header {
  background: var(--black) !important;
  border-bottom: 4px solid var(--orange) !important;
  position: sticky !important;
  top: 0;
  z-index: 100;
}

/* ヘッダー内の文字色を白に */
.l-header a,
.l-header .c-logo__text,
.l-header .site-name-text {
  color: var(--white) !important;
}

/* ロゴテキスト：Oswald フォント */
.l-header .c-logo__text,
.l-header .site-name-text,
.l-header .p-logo__title {
  font-family: 'Oswald', sans-serif !important;
  font-weight: 700 !important;
  font-size: 20px !important;
  letter-spacing: 1px;
  color: var(--white) !important;
}

/* ロゴサブテキスト（サイトの説明文） */
.l-header .c-logo__desc,
.l-header .p-logo__desc {
  font-size: 10px !important;
  color: var(--orange) !important;
  font-weight: 400 !important;
  letter-spacing: 0;
}

/* ヘッダー右側のXリンク（カスタムHTMLで追加する場合） */
.header-x-link {
  color: var(--orange) !important;
  text-decoration: none;
  font-size: 13px;
  font-weight: 700;
}
.header-x-link:hover { opacity: 0.7; }

/* ============================================================
   カテゴリナビ（グローバルナビ）
   ============================================================ */

/* グローバルナビ全体：白背景・下ボーダー・横スクロール */
.c-gnav,
.l-gnav {
  background: var(--white) !important;
  border-bottom: 1px solid var(--light-gray) !important;
  overflow-x: auto !important;
  -webkit-overflow-scrolling: touch;
}
.c-gnav::-webkit-scrollbar,
.l-gnav::-webkit-scrollbar { display: none; }

/* ナビ内リスト：横並び・折り返しなし */
.c-gnav__list,
.l-gnav__list {
  display: flex !important;
  flex-wrap: nowrap !important;
  white-space: nowrap;
  padding: 0 8px;
}

/* 各ナビアイテム */
.c-gnav__item > a,
.l-gnav__item > a,
.c-gnav .menu-item > a {
  display: inline-flex !important;
  align-items: center;
  gap: 4px;
  padding: 10px 14px !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  color: var(--dark-gray) !important;
  text-decoration: none;
  border-bottom: 3px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
}
.c-gnav__item > a:hover,
.l-gnav__item > a:hover,
.c-gnav .menu-item > a:hover,
.c-gnav .current-menu-item > a,
.c-gnav .current_page_item > a {
  color: var(--orange) !important;
  border-bottom-color: var(--orange) !important;
  background: transparent !important;
}

/* カテゴリ別カラードット（::before 疑似要素） */
.c-gnav .menu-item > a::before,
.l-gnav .menu-item > a::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* 各カテゴリの色 */
.menu-item.cat-all     > a::before { background: var(--orange); }
.menu-item.cat-jiai    > a::before { background: #F5811F; }
.menu-item.cat-senshu  > a::before { background: #003DA5; }
.menu-item.cat-syuno   > a::before { background: #555555; }
.menu-item.cat-draft   > a::before { background: #2E8B57; }
.menu-item.cat-ob      > a::before { background: #7B4DAA; }
.menu-item.cat-hoko    > a::before { background: #E53935; }
.menu-item.cat-kyudan  > a::before { background: #F9A825; }
.menu-item.cat-column  > a::before { background: #1A1A1A; }

/* ドロップダウンを非表示 */
.c-gnav .sub-menu { display: none !important; }

/* ============================================================
   メインレイアウト（2カラム）
   ============================================================ */

.l-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 16px;
}

/* ============================================================
   記事一覧（リスト型）
   ============================================================ */

/* リスト全体 */
.-type-list .p-postList,
.p-postList.-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 各記事アイテム */
.-type-list .p-postList__item,
.p-postList.-list .p-postList__item {
  background: var(--white);
  border-left: 4px solid transparent;
  transition: background 0.2s, border-left-color 0.2s;
  animation: fadeInUp 0.4s ease forwards;
  opacity: 0;
  transform: translateY(10px);
}
.-type-list .p-postList__item:hover,
.p-postList.-list .p-postList__item:hover {
  background: var(--orange-light);
  border-left-color: var(--orange);
}

/* アニメーション遅延 */
.-type-list .p-postList__item:nth-child(1)  { animation-delay: 0.05s; }
.-type-list .p-postList__item:nth-child(2)  { animation-delay: 0.10s; }
.-type-list .p-postList__item:nth-child(3)  { animation-delay: 0.15s; }
.-type-list .p-postList__item:nth-child(4)  { animation-delay: 0.20s; }
.-type-list .p-postList__item:nth-child(5)  { animation-delay: 0.25s; }
.-type-list .p-postList__item:nth-child(6)  { animation-delay: 0.30s; }
.-type-list .p-postList__item:nth-child(7)  { animation-delay: 0.35s; }
.-type-list .p-postList__item:nth-child(8)  { animation-delay: 0.40s; }
.-type-list .p-postList__item:nth-child(9)  { animation-delay: 0.45s; }
.-type-list .p-postList__item:nth-child(10) { animation-delay: 0.50s; }

@keyframes fadeInUp {
  to { opacity: 1; transform: translateY(0); }
}

/* 記事リンク全体 */
.-type-list .p-postList__item a,
.p-postList.-list .p-postList__item a {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding: 16px 20px;
  text-decoration: none;
  color: inherit;
}

/* サムネイル */
.-type-list .p-postList__eyecatch,
.p-postList.-list .p-postList__eyecatch {
  width: 120px !important;
  height: 80px !important;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}
.-type-list .p-postList__eyecatch img,
.p-postList.-list .p-postList__eyecatch img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 本文エリア */
.-type-list .p-postList__body,
.p-postList.-list .p-postList__body {
  flex: 1;
  min-width: 0;
}

/* カテゴリバッジ */
.-type-list .p-postList__cats .c-cat-label,
.p-postList.-list .c-cat-label {
  font-size: 11px !important;
  font-weight: 700 !important;
  color: var(--white) !important;
  padding: 2px 8px !important;
  border-radius: 2px !important;
}

/* 投稿日時 */
.-type-list .p-postList__date,
.p-postList.-list .p-postList__date,
.-type-list .c-meta__date {
  font-size: 11px;
  color: var(--mid-gray);
}

/* タイトル */
.-type-list .p-postList__ttl,
.p-postList.-list .p-postList__ttl {
  font-size: 15px !important;
  font-weight: 700 !important;
  line-height: 1.5 !important;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-top: 4px;
  color: var(--dark-gray);
}

/* ============================================================
   サイドバー ウィジェット
   ============================================================ */

/* ウィジェットボックス */
.l-sidebar .widget {
  background: var(--white);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 20px;
}

/* ウィジェットタイトル（黒背景・Oswald・オレンジ左ボーダー） */
.l-sidebar .widget-title,
.l-sidebar .widgetTitle,
.l-sidebar .c-widget__title {
  background: var(--black) !important;
  color: var(--white) !important;
  font-family: 'Oswald', sans-serif !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  padding: 10px 16px !important;
  border-left: 4px solid var(--orange) !important;
  letter-spacing: 1px;
  margin: 0 !important;
}

/* ウィジェットリスト共通 */
.l-sidebar .widget ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.l-sidebar .widget ul li {
  border-bottom: 1px solid var(--light-gray);
}
.l-sidebar .widget ul li:last-child {
  border-bottom: none;
}
.l-sidebar .widget ul li a {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  text-decoration: none;
  color: var(--dark-gray);
  font-size: 13px;
  transition: background 0.2s;
}
.l-sidebar .widget ul li a:hover {
  background: var(--orange-light);
}

/* カテゴリウィジェット：投稿数を右寄せ */
.l-sidebar .widget_categories .cat-item a {
  justify-content: space-between;
}

/* ============================================================
   Xバナーウィジェット（カスタムHTMLで使用するクラス）
   ============================================================ */

.sidebar-x-banner {
  display: block;
  background: var(--black);
  color: var(--white);
  text-align: center;
  padding: 16px;
  text-decoration: none;
  transition: background 0.2s;
}
.sidebar-x-banner:hover { background: #333; }
.sidebar-x-banner .x-handle {
  font-family: 'Oswald', sans-serif;
  font-size: 16px;
  font-weight: 700;
  color: var(--orange);
}
.sidebar-x-banner .x-followers {
  font-size: 11px;
  color: #999;
  margin-top: 2px;
}
.sidebar-x-banner .x-cta {
  display: inline-block;
  margin-top: 8px;
  background: var(--orange);
  color: var(--white);
  padding: 6px 20px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 700;
}

/* ============================================================
   フッター
   ============================================================ */

.l-footer {
  background: var(--black) !important;
  border-top: 4px solid var(--orange) !important;
  color: #999 !important;
  margin-top: 40px;
}

.l-footer a {
  color: #999 !important;
  font-size: 12px;
  transition: color 0.2s;
}
.l-footer a:hover {
  color: var(--orange) !important;
}

/* フッターロゴ */
.l-footer .c-logo__text,
.l-footer .site-name-text {
  font-family: 'Oswald', sans-serif !important;
  font-weight: 700 !important;
  color: var(--white) !important;
}
.l-footer .c-logo__text span,
.l-footer .site-name-text span {
  color: var(--orange);
}

/* ============================================================
   見出しスタイル（記事内）
   ============================================================ */

.post_content h2,
.entry-content h2 {
  background: var(--black);
  color: var(--white);
  padding: 12px 16px;
  border-left: 6px solid var(--orange);
}

.post_content h3,
.entry-content h3 {
  border-bottom: 3px solid var(--orange);
  padding-bottom: 6px;
}

/* ============================================================
   レスポンシブ
   ============================================================ */

@media (max-width: 768px) {
  .-type-list .p-postList__eyecatch,
  .p-postList.-list .p-postList__eyecatch {
    width: 90px !important;
    height: 60px !important;
  }
  .-type-list .p-postList__ttl,
  .p-postList.-list .p-postList__ttl {
    font-size: 14px !important;
  }
  .-type-list .p-postList__item a,
  .p-postList.-list .p-postList__item a {
    padding: 12px 14px;
  }
}
```

---

## ウィジェット用HTML

### ① Xバナー（カスタムHTML）

```html
<a href="https://x.com/yoshilover6760" target="_blank" class="sidebar-x-banner">
  <div class="x-handle">@yoshilover6760</div>
  <div class="x-followers">8,500+ フォロワー</div>
  <div class="x-cta">𝕏 フォローする</div>
</a>
```

### ② FAMILY STORIES（カスタムHTML）

```html
<ul>
  <li><a href="https://prosports.yoshilover.com/giants-geneki-tsuma-kazoku/">🏠 巨人・現役選手の妻・家族まとめ</a></li>
  <li><a href="https://prosports.yoshilover.com/genekipurobaseballkazoku/">🏠 全球団・現役選手の家族まとめ</a></li>
  <li><a href="https://prosports.yoshilover.com/obmotopurobaseballkazoku/">🏠 OB・元選手の家族まとめ</a></li>
</ul>
```

---

## 注意事項

### メニューCSS クラスの設定方法
WP管理画面 → 外観 → メニュー を開いたとき、画面右上の「表示オプション」タブをクリックし、「CSSクラス」にチェックを入れる。そうしないとメニューアイテムにCSSクラスを入力する欄が表示されない。

### CSSセレクタのズレについて
SWELLのバージョンによって `.c-gnav` や `.p-postList` のクラス名が異なる場合がある。表示がおかしい場合は Chrome DevTools の検証ツールで実際のクラス名を確認して CSSのセレクタを修正する。

### カテゴリバッジの色
カテゴリバッジ（`.c-cat-label`）の背景色はSWELL側でカテゴリ設定した色が自動適用される。002チケットでカテゴリ色を正しく設定しておくこと。

---

## 完了条件

- TOPページが最新投稿の時系列一覧になっている  
- カテゴリナビバー（白背景・カラードット）がヘッダー直下に表示されている  
- 記事一覧がリスト型（サムネ＋カテゴリバッジ＋タイトル）で表示されている  
- ホバー時に記事左側にオレンジラインが出る  
- サイドバー5ウィジェットが正しく表示されている  
- スマホでカテゴリナビが横スクロールできる  
- 旧TOPページ（12球団インデックス）が非公開になっている  
