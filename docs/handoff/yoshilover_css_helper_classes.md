# yoshilover CSS helper class index (2026-04-24 時点)

`src/custom.css` に shipping 済の helper class 一覧。
DOM 側で該当 class を付けたら巨人色で即表示される。

## 運用

- `src/custom.css` = source of truth
- live 反映 = Claude Code が `PUT /wp-json/yoshilover/v1/custom-css` で自動
- よしひろさんの手作業は **ゼロ**

## Body class modes (body に class 付けたら発動)

| body class | 挙動 |
|---|---|
| `yoshi-reader-focus` | 広告 / sidebar / footer / nav 全消し + 本文 17/1.95 (読書モード) |
| `yoshi-chapter-number` | 記事 h2 に 01/02/03 orange 番号 prefix |
| `yoshi-sticky-pager` | モバイル前後ナビを底 sticky |
| `yoshi-header-translucent` | header 半透明 + blur |
| `yoshi-auto-dark` | OS ダーク時のみ dark 発動 |
| `yoshi-dark` | 強制 dark |
| `yoshi-no-dark` | auto-dark を opt-out |
| `yoshi-unpublished` | 🚧 非公開プレビューバー (赤) |
| `yoshi-draft-mode` | DRAFT 赤 badge 右上 |
| `yoshi-mobile-simple` | モバイル超簡素化 (lead 非表示等) |
| `yoshi-theme-soft` | topic-hub 黒 panel → white に softer |
| `yoshi-font-large` | 本文 17px / 1.9 |
| `yoshi-font-xlarge` | 本文 18px / 1.95 |

## Top-level helper blocks

| class | 用途 |
|---|---|
| `.yoshi-home-ribbon` | ホーム hero strip (orange 5px + label + text) |
| `.yoshi-top-banner` | 画面上 sticky banner (試合日限定) |
| `.yoshi-game-strip` | orange gradient 帯 (試合予定) |
| `.yoshi-game-today` | 試合日 hero (黒 + orange top + 時刻) |
| `.yoshi-next-game` | 「⚾ 次の試合」予告 box |
| `.yoshi-result-panel` | 試合結果 (巨人 xx-yy 対戦相手) 大スコア |
| `.yoshi-x-follow-cta` | X フォロー CTA bar |
| `.yoshi-newsletter` | メルマガ登録 box |
| `.yoshi-cat-banners` + `.yoshi-cat-banner` | カテゴリタイル grid |
| `.yoshi-summary-box` | SUMMARY ラベル付き まとめ box |

## Content / 本文 helper

| class | 用途 |
|---|---|
| `.yoshi-lead-info` | INFO label 付きリード段落 |
| `.yoshi-notice` + `.-danger/-dark/-success/-warn` | 各種 notice box |
| `.yoshi-ribbon-box[data-label="..."]` | 左上にリボンラベル付き box |
| `.yoshi-vertical-tag` | 縦書きラベル (記念号等) |
| `.yoshi-source-box` / `.p-source-box` | 引用元 / 出典 |
| `.yoshi-icon-heading` + `__icon` | icon 付き段落見出し |
| `.yoshi-faq` dl | FAQ (Q/A 円 pill) |
| `.yoshi-interview` | 対談 / インタビュー 形式 |
| `.yoshi-chat` + `__msg.-right` | チャット吹き出し |
| `.pull-quote` | 引用強調 (上下 orange 3px) |

## Data display

| class | 用途 |
|---|---|
| `.yoshi-score` (+ `__team / __num / __sep`) | スコア大表示 (巨人 3-1 阪神) |
| `.yoshi-counter` (+ `__value / __label`) | 数字カウンター (Oswald orange 大) |
| `.yoshi-counter-up.is-animating` | カウントアップアニメ (JS で toggle) |
| `.yoshi-stat-card` (+ `__label / __value / __sub`) | 単発スタッツカード |
| `.yoshi-stat-bar` (+ `__item / __num / __label`) | スタッツ横並び bar |
| `.yoshi-player-card` | 選手プロフィールカード |
| `ol.yoshi-ranking` | #1-#5 ランキング (金銀銅 + orange) |

## Label / chip / badge

| class | 用途 |
|---|---|
| `.yoshi-pill` + `.-dark/.-outline` | 汎用 pill label |
| `.yoshi-tag-badge` + `.-live/.-hot/.-new/.-pr` | 角バッジ (見出し横) |
| `.yoshi-yg-mark` | YG ロゴ風角マーク |
| `.yoshi-brand-logo` (+ `__text/__badge`) | 巨人ブランドロゴ |
| `.yoshi-read-time` / `.c-postTimes__readtime` | ⏱ 読了時間 pill |
| `.yoshi-live-dot` | LIVE 赤丸パルス |
| `.yoshi-pulse` | 汎用パルスアニメ class |

## UX helper

| class | 用途 |
|---|---|
| `.yoshi-fab` | 右下 floating action button |
| `.yoshi-fav-btn` (+ `.is-faved`) | ★ お気に入りボタン |
| `.yoshi-cta-strong` / `.yoshi-follow-cta` | 強調 CTA pill |
| `.yoshi-back` / `.yoshi-back-to-cat` / `.yoshi-back-to-top-link` | 戻り link |
| `.yoshi-spinner` | ローディング spinner |
| `.yoshi-toast` + `.-success/.-error` | 右上通知 |
| `.yoshi-modal` + `__panel/__title/__close` | モーダル |
| `.yoshi-tilt-card` | 3D tilt hover (desktop only) |
| `.yoshi-slider` | scroll-snap 横スライダー |
| `.yoshi-skeleton` + `.-title/.-line/.-thumb` | lazy loader skeleton |
| `.yoshi-skip-link` | a11y skip to content |
| `[data-yoshi-tooltip="xxx"]` | ホバーツールチップ |
| `details.yoshi-collapse > summary` | 折りたたみ |

## SWELL 実 DOM override

| class (SWELL default) | 私の override |
|---|---|
| `.l-header` | 黒 + orange 4-5px bottom + モバイル 40-48px 高さ |
| `.l-header__logo` | padding 4px (SWELL default 16px を潰す) |
| `.l-header__spNav` / `.p-spHeadMenu` | 非表示 (運営者/問合せ swiper 消去) |
| `.l-mainContent`, `.l-articleBottom`, `l-articleBottom__title` | 巨人色適用 |
| `.c-postTitle` | hero 化 (orange 5px + padding) |
| `.c-postTitle__ttl` | clamp(20, 4.4vw, 26) 800 黒 |
| `.c-pageTitle` | 黒 bg + orange 6px 左 + clamp(18, 3.4vw, 22) |
| `.c-pageTitle__subTitle` | Oswald orange chip |
| `.c-secTitle:not(.-widget)` | 18 Oswald uppercase + orange 5px 左 |
| `.c-catchphrase` | モバイル非表示 |
| `.c-gnav` / `.l-gnav` | 横スクロール + item hover orange |
| `.p-breadcrumb` | ▸ orange separator |
| `.p-articleThumb` / `.p-entryEyeCatch` | orange 下辺 + hover zoom + mobile 38vh cap |
| `.p-articleMetas.-top` | flex wrap gap |
| `.p-articleMetas__termList .c-categoryList__link` | Oswald uppercase pill |
| `.p-toc` | orange 4px top + Oswald 見出し + ▸ list |
| `.p-commentArea` | gradient bg + COMMENTS ribbon pill |
| `.p-relatedPosts` / `.c-relatedPosts` | grid minmax 220 + hero-lite title + desktop 3col |
| `.p-pagerPosts` / `.c-pagerPosts` / `.p-postNav` | 2col grid + orange-light hover |
| `.c-shareBtns` | pill btn + Oswald SHARE prefix + X 黒 copy orange |
| `.yoshilover-related-posts` (inline-style) | !important 上書きで巨人 4px top + black link + orange hover |
| `.yoshi-sns-reactions` | orange 4px left + black 3px top + ribbon |
| `.yoshi-breaking-strip` | 黒 + orange 5px + LIVE chip |
| `.yoshi-article-bundles` | orange 5px + hero heading |
| `.p-spMenu` / `.p-searchModal` / `.p-indexModal` | 黒 bg + orange + blur |
| `.c-modal` / `.c-overlay` / `.c-urlcopy` | orange accent |
| `.c-fixBtn` / `.c-iconBtn` / `.c-iconList` | orange + Oswald |
| `.wp-block-button .wp-block-button__link` / 全 CTA | orange pill + Oswald + hover translateY |
| `.wp-block-quote` / `blockquote` | orange 4px left + ❝ ダブルクォート |
| `.wp-block-table` / table | 黒 Oswald th + zebra + orange-light hover + モバイル横 scroll hint |
| `.wp-block-image` | radius 3 + hover shadow + saturate |
| `.wp-block-gallery` | desktop 3-4col / mobile 1-2col |
| `.wp-block-embed-youtube` | red 3px top + 16:9 |
| `.wp-block-embed-twitter` / `.twitter-tweet` | orange 3px left |
| `.wp-block-code` / `pre` | 黒 + orange 4px 左 + eee text |
| `.wp-block-more` | orange dashed + READ MORE |
| `.swell-block-button` | orange pill (CTA 統一) |
| `.swell-block-capbox` / `.is-style-capbox` | orange top 4 + label pill |
| `.swell-block-faq` / `.-accordion` | orange 左 + hover orange-light |
| `.swell-block-balloon` + `.is-style-speech/think` | 丸 orange border avatar + speech bg |
| `.swell-block-blogCard` | orange 4px 左 + hover 浮き + Oswald label |
| `.swell-block-step` | number orange + body 左 orange |

## カテゴリ別 accent (body.category-<slug>)

| slug | 色 |
|---|---|
| shiai-sokuho | `#F5811F` (orange) |
| senshu-joho | `#003DA5` (blue) |
| syuno | `#555` (dark-gray) |
| draft-ikusei | `#2E8B57` (green) |
| ob-kaisetsusha | `#7B4DAA` (purple) |
| hoko-iseki | `#E53935` (red) |
| kyudan-joho | `#F9A825` (gold) |
| column | `#1A1A1A` (black) |

h2 / c-pageTitle / c-postTitle / eyecatch / postList item の border / background が自動で該当色に切り替わる。

## 広告 kill (非公開時の全殺し)

- `ins.adsbygoogle` / `.adsbygoogle` / `[data-ad-client]` / `[data-ad-slot]`
- `body > [id^="aswift_"]` / `body > [id^="google_ads_"]`
- `iframe[src*="googleads"]` / `[src*="doubleclick"]` / `[src*="googlesyndication"]` / `[src*="adservice.google"]`
- `.google-auto-placed` / `[data-google-query-id]` / `[data-anchor-status]` / `[data-adbreak-test]`
- `.google-vignette` / `body.google-vignette-active`
- `[aria-label="Advertisement"]` / `[aria-label="広告"]` / `[aria-label*="sponsored"]`
- z-index MAX (2147483647 / 2147483) 系 overlay
- fixed top:0 / bottom:0 系

## Animation / interaction

- `@keyframes yoshiloFadeInUp / yoshiloFadeInUpSoft` (item 出現)
- `@keyframes yoshiloPulse / yoshiloLivePulse` (LIVE ドット)
- `@keyframes yoshiloShimmer` (lazy loader)
- `@keyframes yoshiloSpin` (spinner)
- `@keyframes yoshiloToastIn / yoshiloModalIn` (UX)
- `@keyframes yoshiloCountBounce` (数字アニメ)
- `@keyframes yoshiloSwipeHint` (table 横 scroll 暗示)
- `@keyframes yoshiloBodyFade` (body fade-in)
- `@keyframes yoshiloFadeIn` (overlay)
- `@keyframes yoshiloWiggle` (tap feedback)

## CSS 変数 (body 上で runtime 調整可)

- `--yoshi-article-max` (default 860px)
- `--yoshi-sidebar-max` (default 340px)
- `--yoshi-gutter` (default 16px)
- `--yoshi-progress` (scroll progress、JS で動かす)
- `--yoshi-body-size` (font-large mode 用)

## 運用コマンド

```bash
# CSS 編集
vim src/custom.css

# plumbing commit (codex 干渉なし)
IDX=/tmp/myidx_$$
GIT_INDEX_FILE=$IDX git read-tree HEAD
GIT_INDEX_FILE=$IDX git update-index --add src/custom.css
TREE=$(GIT_INDEX_FILE=$IDX git write-tree)
COMMIT=$(echo "front(...): ..." | git commit-tree "$TREE" -p HEAD)
git update-ref refs/heads/master "$COMMIT" HEAD
git push origin master

# REST 反映 (Python one-liner)
python3 -c "..." # → PUT /wp-json/yoshilover/v1/custom-css
```
