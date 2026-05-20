# 388-FRONT ヘッダー回遊ナビを選手名タグ 30 個に拡張

## meta

- status: REVIEW_NEEDED
- priority: P1 (回遊率 main 改善、 のもとけ模倣の中核)
- owner: Claude
- created: 2026-05-19
- updated: 2026-05-20 (user scope clarification + impl)
- parent_intent: のもとけ風サイト構造 (387-390 chain)
- depends_on: 387 (タグ付与率 100% が前提条件、 タグ空欄では nav から飛んでも 0 件 page) — user 判断 2026-05-20: 387 close (タグ付与は OK 扱い)、 当 ticket は UI のみで前進
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/63

## 2026-05-20 user scope clarification

- PC = 選手タグ 30 個 目安 (固定 8 + player 30 = 38 chip)
- mobile = 選手タグ 10-15 個 目安 (PC ほど多くなくてよい、 chip 数を絞って疎にする)
- 387 タグ付与率 100% は不要扱いで close、 UI 先行で進める

## 2026-05-20 impl

- `src/yoshilover-063-frontend.php`:
  - `yoshilover_063_get_top_player_tags()` の cap を 100 → 30
  - `yoshilover_063_sanitize_dense_nav_items()` の slice 上限を 150 → 50
  - plugin version 0.16.1 → 0.16.2
- `src/custom.css`:
  - `@media (max-width: 600px)` block を追加し、 `.yoshi-dense-nav__item:nth-child(n+19)` を `display: none` で隠す
  - mobile 可視 = 固定 8 + player 10 = 18 chip (水平スクロールは維持)

## user intent (2026-05-19 chat lock)

- 「回遊率を高めてユーザビリティと SEO に強くしたい」「のもとけ意識」

## 現状 (evidence)

post 69507 の HTML より:

```html
<nav class="yoshi-dense-nav" aria-label="回遊ナビ">
  <a href="/">HOME</a>
  <a href="/">全記事</a>
  <a href="/tag/阿部慎之助">監督</a>
  <a href="/category/kyudan-joho">球団情報</a>
</nav>
```

= **4 link のみ** (うち選手タグ 1)

## のもとけ (dnomotoke.com) との diff

- **dnomotoke**: 選手名タグ **40+ 個** + カテゴリ、 水平スクロール
- **yoshilover**: 4 link (選手 1)
- gap = **選手タグ 30+ 個追加**

## scope

### Phase 1: 選手 list 選定

- 候補 list: post count top 30 player tag (WP REST `/tags?orderby=count&order=desc` で取得)
- 巨人現役選手 only (`config/giants_roster.json` と intersection)
- 静的 list ではなく動的に毎週 / 月 更新する設計を検討 (post 数変動)

### Phase 2: yoshi-dense-nav 拡張

- yoshilover plugin (WP 側) の `yoshi-dense-nav` HTML 生成箇所を拡張
- 水平スクロール CSS 維持 (mobile 優先)
- カテゴリ ([球団情報] etc) と選手タグの 視覚区別 (色 / icon / chip 形)
- 各 link に `<a class="yoshi-dense-nav__link--player" data-player-tag-id="...">` 付与で CSS hookable に

### Phase 3: verify

- 全 device で水平スクロール動作
- 30 link 全部 click 可能 (404 0 件)
- mobile で overflow せず scroll 可
- 元の HOME / 全記事 / 監督 / 球団情報 リンクは維持

## 不可触

- カテゴリ構造 (CATEGORY-RESTRUCTURE 別 ticket)
- タグページ index policy (今は noindex 維持、 user 判断後 SEO 解放)
- WP DB の tag 自体は触らない (rename / delete しない)
- env / Secret / Scheduler / fetcher / publish / X / SNS は不可触

## 成功条件

- ヘッダー nav で 選手タグ 30 link + カテゴリ 2-3 link が水平スクロール表示
- mobile で overflow せず scroll
- 各 link click で tag/category archive page 200 OK
- regression: 既存 4 link の挙動不変

## 関連

- 387 (前提)
- 376 (person tag routing で WP に tag 付与済)
