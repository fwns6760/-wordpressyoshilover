# 389-FRONT サイドバー人気記事 widget (直近3日 30件)

## meta

- status: READY_FOR_IMPL
- priority: P2 (回遊率改善、 のもとけ模倣)
- owner: Claude
- created: 2026-05-19
- parent_intent: のもとけ風サイト構造 (387-390 chain)
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/64

## user intent

- 「回遊率を高めてユーザビリティと SEO に強くしたい」「のもとけ意識」

## のもとけ参照

- サイドバー「最近3日間の人気記事」セクション、 約 30 件 list

## 現状 (evidence)

post 69507 HTML より、 サイドバー widget 存在:

- `custom_html-9` (`yoshi-dense-nav`)
- `yoshi-breaking-strip` (速報帯)
- `yoshi-topic-hub` (今週の話題)
- `swell_ad_widget-12` (AdSense)

= **人気記事 widget なし**

## scope

### Phase 1: 「人気」の定義決定

- 選択肢:
  - (a) GA4 page view (直近3日) — 外部 API 必要、 cost 微増
  - (b) WP DB comment 数 / 視点数 (plugin に counter があれば)
  - (c) 公開順 + 編集独自ランク (subtype 重み付け、 巨人選手主役 など)
  - (d) hybrid (a) + (b)
- (a) 最ものもとけ風だが GA4 API cost / 認証必要
- (c) 一番安い、 編集判断ベース、 cost ¥0

### Phase 2: widget 実装

- WP 側 plugin で popular_posts query function 追加
- sidebar widget 登録 (`yoshi-popular-posts` class)
- 30 件 cap、 直近 3 日 window
- 各 entry: タイトル + 日付 + 小サムネ

### Phase 3: cache + cost 試算

- query を毎 request 走らせず、 5-15 min cache (WP transient API)
- (a) 採用時の GA4 API cost 試算 (¥0 想定だが verify)

### Phase 4: verify

- sidebar に widget 表示
- 30 件正しく出る
- click 各 link 200 OK
- 既存 widget (speed-strip / topic-hub) 挙動不変

## 不可触

- 既存 widget の削除 / 改名
- env / Secret / Scheduler / fetcher / publish / X / SNS は不可触
- AdSense slot 配置は触らない (320-FRONT 別 ticket)

## 成功条件

- sidebar に 30 件人気記事 widget 表示
- query は cache、 全 page で page load 増 < 100ms
- regression 0

## 関連

- 320-FRONT-scroll-ads-uiux (AdSense slot、 sidebar 隣接)
- SIDEBAR-WIDGETS-2026-05-08 (5 widget design、 人気記事は含まれてないので追加)
