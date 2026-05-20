# 390-FRONT サイドバー検索 + 月別アーカイブ widget

## meta

- status: READY_FOR_IMPL
- priority: P3 (回遊率改善 part 3、 のもとけ模倣の最終 piece)
- owner: Claude
- created: 2026-05-19
- parent_intent: のもとけ風サイト構造 (387-390 chain)
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/65
- note: タグページ index 解放は **scope 外** (user 判断: 「index はまだいらない」 2026-05-19)

## user intent

- 「回遊率を高めてユーザビリティと SEO に強くしたい」「のもとけ意識」
- ただし「index (タグページ noindex 解放) はまだいらない」 → SEO は内部リンク強化に留め、 SERP 流入解放は後日

## のもとけ参照

- サイドバー: 「最近1年間の記事タイトル検索」 + カテゴリ + 月別アーカイブ
- フッター: カテゴリ + 月別アーカイブ

## 現状 (evidence)

- yoshilover サイドバー: 検索 widget なし、 月別アーカイブ widget 未確認 (要 verify)

## scope

### Phase 1: サイドバー検索 widget

- WP 標準の search widget 利用 (`<?php get_search_form(); ?>`)
- placeholder「タイトルで検索」
- 検索結果 page の表示 (default WP `search.php` でも OK、 SWELL theme search 結果 page を verify)

### Phase 2: 月別アーカイブ widget

- WP 標準 archives widget 利用 (`wp_get_archives`)
- 直近 12 ヶ月のみ (累積で長くなり過ぎ防止)
- 各月の post 数 badge 表示

### Phase 3: フッター (任意)

- フッターに カテゴリ + 月別アーカイブ link を mirror
- これは Phase 2 完了後判断 (やらなくても致命的でない)

### Phase 4: verify

- 検索 widget 表示 + 検索動作
- 月別アーカイブ widget 表示 + click で各月 archive page 200 OK
- regression 0

## 不可触

- タグページ index 解放 (user 判断、 別 ticket)
- 既存 widget の削除 / 改名
- env / Secret / Scheduler / fetcher / publish / X / SNS / WP DB は不可触

## 成功条件

- サイドバーに 検索 + 月別アーカイブ widget 表示
- 各 page で widget 機能動作
- regression 0

## 関連

- 387 (タグ付与率 100%)
- 388 (ヘッダーナビ拡張)
- 389 (人気記事 widget)
- 別 ticket 案: タグページ index 解放 (今は noindex 維持)
