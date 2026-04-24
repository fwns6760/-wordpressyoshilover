# front バシバシ便 v3 (2026-04-24 深夜 JST、REST 自動 deploy 運用)

Claude Code = yoshilover front 専任 owner として CSS を連続投入。
commit/push も plumbing (`GIT_INDEX_FILE=/tmp/myidx`) で codex 干渉なし、
deploy は REST PUT で手作業 0 回。

## 運用モード確定

- ユーザー = backend で別作業中、GO 入力しない
- Claude Code = 常に次 cycle へ自動進行（「続けますか?」禁止、「常に GO」）
- 停止条件 = ユーザーが明示的に「やめて/違う方向/ここ変」と言う時のみ

## このラウンドの着地点

- `src/custom.css` = **216KB / 7,000+ lines**（初期 43KB → 5 倍）
- 最新 commit = `7cd1df5`
- live 反映 = **230KB** / 全 rule inline `<style>` に deploy 済

## 追加したカテゴリ別

### 広告関連 (非公開前提で全殺し)
- AdSense ins.adsbygoogle / data-ad-client / google-auto-placed 全滅
- iframe[src*=googleads/doubleclick/googlesyndication] 全滅
- anchor-top / anchor-bottom / vignette / aswift_ 全滅
- z-index MAX (2147483647) 系全滅
- data-google-query-id / data-ad-slot 全滅

### モバイル compact (のもとけ風)
- header SWELL `.l-header__logo { padding: 16px 0 }` を潰し 40-48px に
- body contrast 完全黒 (#1a1a1a)、本文 link 常時 underline
- topic-hub 黒 panel → white + orange 左 simplify
- drop cap / strong orange marker mobile 無効
- post-list flat (border-bottom のみ、のもとけ風 list)
- font 15px / line 1.82 / iOS 16px zoom 防止
- 記事末 tag/share/meta 超 compact

### CTA / UI
- 全 CTA (outline / fill / #respond / submit / search) → orange pill + Oswald + hover translateY
- pagination pill 38x38
- comment form おしゃれ (gradient bg, ribbon, floating labels)
- X embed frame orange 3px
- sp-head swiper 「運営者/問合せ」非表示

### Helper class 群 (将来 DOM 注入用)
- `.yoshi-game-strip` / `.yoshi-game-today` (試合日 hero)
- `.yoshi-pill` / `.yoshi-pill.-dark` / `.yoshi-pill.-outline`
- `.yoshi-score` (巨大数字)
- `.yoshi-counter` / `.yoshi-ranking` ol
- `.yoshi-faq` dl + Q/A pill
- `.yoshi-ribbon-box` / `.yoshi-vertical-tag`
- `.yoshi-notice` / `.-danger/-dark/-success/-warn`
- `.yoshi-lead-info` (INFO pill)
- `.yoshi-yg-mark` (YG logo)
- `.yoshi-x-follow-cta` (X follow bar)
- `.yoshi-summary-box` (SUMMARY labeled)
- `.yoshi-home-ribbon` (hero strip)
- `.yoshi-cat-banners` + `.yoshi-cat-banner` (カテゴリタイル)
- `.yoshi-slider` (scroll-snap 横)
- `.yoshi-spinner` / `.yoshi-toast` / `.yoshi-modal` (UX helper)
- `.yoshi-pulse` / `.yoshi-live-dot` (放送中)
- `.yoshi-read-time` (⏱ pill)
- `.yoshi-tilt-card` (3D tilt hover)
- `.yoshi-source-box` (引用元)

### body class mode
- `body.yoshi-reader-focus`: 広告/sidebar/footer/nav 全消し + 本文 17/1.95 (読書モード)
- `body.yoshi-chapter-number`: h2 に 01/02/03 orange 番号
- `body.yoshi-sticky-pager`: モバイル前後ナビを底 sticky
- `body.yoshi-header-translucent`: header 半透明 + blur
- `body.yoshi-auto-dark`: OS ダーク時のみ dark 発動
- `body.yoshi-dark`: 強制 dark
- `body.yoshi-unpublished`: 🚧 非公開プレビューバー
- `body.yoshi-draft-mode`: DRAFT 赤 badge 右上
- `body.yoshi-mobile-simple`: モバイル超簡素化

### カテゴリ別 accent
- body.category-<slug> で h2/pageTitle/eyecatch/postList item の border を 8 カテゴリ色に分岐
- tag/author/date アーカイブも色分岐

### その他
- `::selection` orange
- focus-visible orange ring
- スクロール progress bar (single-post, CSS var `--yoshi-progress`)
- `html, body { overscroll-behavior-x: none }`
- ol/ul にカスタム marker (orange 丸番号 / orange ひし形)
- blockquote::before で ❝ + cite Oswald orange uppercase
- figcaption Oswald uppercase
- hr を orange 36px linear-gradient
- mark を orange ハイライト 60%
- read-more/more-link に › arrow (hover で滑る)
- print mode refine (pt 単位、広告/nav/sidebar 非表示)
- prefers-reduced-motion 尊重
- dark mode auto / opt-in
- admin bar 黒+orange
- tap-highlight orange 0.2

## 次にやると効きそうな候補

- **DOM 注入系** (PHP 編集、yoshilover-063-frontend.php 更新):
  - `.yoshi-x-follow-cta` を the_content filter で記事末注入
  - `.yoshi-game-today` を試合日 home 上部注入
  - `.yoshi-read-time` を記事 meta に注入
  - これらは plugin 更新 → 再 deploy が必要で、CSS-only の自動化圏外
- **JS 注入系** (plugin に `<script>` 追加):
  - scroll progress bar の `--yoshi-progress` 更新
  - `.yoshi-toast` 汎用 JS
  - modal open/close
  - yoshi-sticky-pager 自動判定

## live 反映確認 (最新)

- `curl https://yoshilover.com/62911` → inline style 229KB、22 検証ルール OK
- 回帰 (topic-hub/breaking-strip/article-bundles/sns/related) 0
- モバイル header 高 80px超 → 48px に圧縮済

## 関連 commit (v3 便、約 30 本)

```
7cd1df5 front(admin-bar+spinner+toast+modal+category-font)
998a45e front(header-pattern+tap-highlight+yg-mark+read-more)
5e8d1f2 front(source+faq+dl+ribbon-box+vertical-tag)
1c8b2e1 front(game-today+tilt+cat-banner+pulse+live-dot)
2441bfe front(dark-mode+snap+chapter-num+back-top)
ed20282 front(notice+tap+emoji+infoBar)
3e72166 front(progress+collapse+ranking+info+gallery)
60abe1c front(draft-mode+swell-ad-slots+writer-info+related-3col)
7e3ec89 front(ad-full-kill+mobile-wrap+unpublished-bar)
2df6b7b front(helpers): yoshi-game-strip / yoshi-pill / yoshi-score
1b3b870 front(mobile-comment-stack+ios-zoom+ad-final)
deeffea front(mobile-final-compact)
feae815 front(mobile-card-flat+xl-cap+print)
206a361 front(mobile-readable+reader-focus)
5a819bf front(mobile-nomoteke-ultra)
911b0a7 front(mobile-nomoteke-simple)
46d3096 front(ad-aggressive-kill): MAX z-index
e7647f8 front(ad-sticky-broad-kill)
77a7be1 front(anchor-bottom-kill+inline-ad-cap)
(前便からの継続)
```
