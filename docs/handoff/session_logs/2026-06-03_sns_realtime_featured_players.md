# 2026-06-03 SNSリアルタイムページ 深化 — 注目選手カード(445 Tier1)

user GO: SNSリアルタイムページ(giants-sns-realtime-1gun/farm)に個人(選手別)を入れる。巨人特化×費用上がらない条件。試合中重視。

- 実装 commit e8b2c113: build_featured_players + render_featured_players。trend chips直後に「⭐注目選手(今日)」= 急上昇順top8、各選手に insight.db 今季成績1行(_player_batting/_player_pitching流用)、tag_resolverで/data/内部リンク。scoped style同梱(共有CSS非干渉)。
- コスト: Gemini不使用 / 更新頻度据え置き(10/13/17/21) / insight.db read-only graceful → 増加なし。
- test: 新規3 + 既存33 pass。preview 127.0.0.1:8141 で見た目確認。
- deploy: yoshilover-fetcher(本体、rss_fetcherがrun()呼ぶ)再ビルド image sns-featured-e8b2c11 → no-traffic rev 00508-t6q → /health smoke 200 → traffic 100%。
- 反映: 次の fire slot(13/17/21 JST)で 1gun/farm ページに出る。verify=?nc=でキャッシュ回避。

残注意: 本deployは前回(sharex-502)以降の全HEAD(並行 data-article 465/468-2 等)を同梱。
