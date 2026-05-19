# 387-FRONT タグ付与率を 100% にする

## meta

- status: READY_FOR_IMPL
- priority: P1 (回遊率の前提条件、 タグ未付与だと chip 出ない = 内部リンク 0)
- owner: Claude
- created: 2026-05-19
- parent_intent: のもとけ風サイト構造への移行 (387-390 chain)
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/62

## user intent (2026-05-19 chat lock)

- 「回遊率を高めてユーザビリティと SEO に強くしたい」「のもとけ意識」
- タグは既に 180 件 WP DB に存在、 SWELL theme が post page / homepage / category archive で `c-tagList` chip 表示済
- ただし 5/19 14:00 JST 時点で **最新 10 post のうち 5 件 (50%) が tags=[]** → chip 出ない、 内部リンク 0

## evidence

```
post_id | tag count | date              | title
69537   |  0 tags   | 2026-05-19T13:48  | 巨人・阿部監督...
69529   |  3 tags   | 2026-05-19T12:50  | 岡本和真...
69525   |  2 tags   | 2026-05-19T12:49  | エキサイティング...
69524   |  0 tags   | 2026-05-19T12:48  | スタジアム...
69523   |  4 tags   | 2026-05-19T12:47  | 【三軍】巨人 vs 西武...
69522   |  0 tags   | 2026-05-19T11:30  | テレビ番組情報...
69515   |  2 tags   | 2026-05-19T11:06  | マルティネス...
69512   |  0 tags   | 2026-05-19T10:53  | 山岡泰輔...
69510   |  0 tags   | 2026-05-19T10:50  | 戸郷フォーム改造...
69507   |  8 tags   | 2026-05-19T10:07  | 阿部監督...
```

5 件 OK / 5 件 NG = 50% 付与率

## 仮説 (検証必要、 root cause 未確定)

- 376 で実装した person tag routing は player_name 検出依存、 player 名が明確でない subtype (テレビ番組情報 / 一般 article) で tag 0 になる可能性
- 376 で「既存タグだけ自動付与」と書かれているが、 detection logic が複数 subtype で機能してない疑い
- placeholder tag (subtype tag / 球団タグ) の fallback がない

## scope

### Phase 1: root cause 特定

- post_id 69537/69524/69522/69512/69510 の生成 path を src/rss_fetcher.py / src/wp_client.py で trace
- 376 person tag routing の current state を grep + log evidence で確認
- 「tag 付与関数がそもそも呼ばれてない」/「呼ばれてるが detection 0 件」のどちらかを確定

### Phase 2: fix

- 全 post が最低 **1 tag** 付与される設計
  - player 検出: 既存 376 path 維持
  - player 検出 0: subtype tag (`postgame` / `lineup` / `manager` / `live_update` 等) 付与
  - subtype tag も 0: 「速報」or「巨人」 fallback tag 付与
- tag 0 post は **publish しない** (review にして mail で user 通知) も検討

### Phase 3: verify

- deploy 後 24h の新規 post の付与率 100% 確認
- 既存 50% post の retroactive backfill は別 ticket

## 不可触

- WP plugin / theme
- 既存タグの rename / delete
- env / Secret / Scheduler
- publish 済記事の retroactive 編集 (forward only)
- X / SNS / WP 既存 publish 設定

## 成功条件

- deploy 後 24h の新規 publish post で tag count >= 1 の割合 100%
- regression: 既存 376 person tag 検出が落ちない (同 subtype の tag 検出件数 baseline 比較)
- pytest 全 PASS
