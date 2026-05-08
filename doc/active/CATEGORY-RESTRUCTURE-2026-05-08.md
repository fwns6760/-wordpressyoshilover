# CATEGORY-RESTRUCTURE-2026-05-08

| field | value |
|---|---|
| ticket_id | CATEGORY-RESTRUCTURE-2026-05-08 |
| priority | P2(navigation 改善、user 判断境界含む)|
| status | DESIGN_REQUIRED(user 判断必要) |
| owner | user(WP category 操作)→ Claude/Codex(再 route logic)|
| lane | FRONTEND(WP plugin)/ INGEST(category 自動付与)|
| created | 2026-05-08 |
| doc_path | doc/active/CATEGORY-RESTRUCTURE-2026-05-08.md |
| cost | ¥0(WP 内 category 操作 + plugin 修正のみ)|
| regression risk | 中(既存 article の category 移動に伴う navigation 変化)|
| 工数 | 3-5h |

## 1. 背景

2026-05-08 PM の audit で、現 11 category の問題発覚:

- **コラム(56% = 主力)が catch-all 化**: broadcast / lineup / postgame / X embed 系すべてが「コラム」に流入
- **巨人(172件 = ほぼ全 publish)が無意味**: 全部に付くので tag 化、category として navigation 用ではない
- 自動投稿(673)/ 旧記事(672) はすでに sidebar 隠し済み(245)、適切

## 2. あるべき category 構成(現 11 → 12)

| # | category | 状態 | 用途 |
|---|---|---|---|
| 1 | 試合速報 | 維持 | postgame / lineup / pregame_pitcher |
| 2 | **試合中継** 🆕 | 新規 | broadcast(コラムから抽出)|
| 3 | 選手情報 | 維持 | player_* 全般 |
| 4 | 首脳陣 | 維持 | manager / coach |
| 5 | 球団情報 | 維持 | official_notice / 球団発表 |
| 6 | ドラフト・育成 | 維持 | farm / 2軍 |
| 7 | 補強・移籍 | 維持 | trade / 外国人 / 契約 / 引退 |
| 8 | OB・解説者 | 維持 | OB / commentator |
| 9 | コラム | scope 縮小 | 連載 / 特集 / digest 系のみ |
| 10 | **ファン反応** 🆕 | 新規(任意)| X curate / 雑学(将来用、今は保留可)|
| 11 | 巨人(meta tag)| sidebar 隠し | tag 化 |
| 12 | 自動投稿 / 旧記事 | sidebar 隠し済 | internal |

## 3. 移行作業

### Step 1: WP admin で 2 新 category を作成

- 「試合中継」(slug: shiai-chukei)
- (任意)「ファン反応」(slug: fan-reaction)

### Step 2: 既存 publish の re-categorize

- コラム category 内の broadcast 記事(中継予定 H3 を含む) → 試合中継 へ移動
- WP REST PUT で category 変更、または admin bulk edit

**規模感**: コラム 56 件中、broadcast 系は 10-20 件と推定。WP REST で自動分類可能。

### Step 3: 自動 routing 修正

`src/tools/manual_intake.py` の `MANUAL_ARTICLE_TYPE_OVERRIDES`:

```python
# Before
"番組情報": ("コラム", "program", "nomotoke_card_short_news_url_v1"),

# After
"番組情報": ("試合中継", "program", "nomotoke_card_short_news_url_v1"),
"試合放送": ("試合中継", "broadcast", "nomotoke_card_broadcast_v1"),
```

`src/rss_fetcher.py` の category 自動判定 logic も同様に修正。

### Step 4: WP plugin sidebar 修正(必要なら)

245 で auto-post / 旧記事 は隠し済、巨人 tag は表示中なので「巨人」の sidebar 隠しを追加(or non-display tag 化)。

## 4. 制約 / 不可触

- 既存 publish の category は **削除しない**(追加 / 移動のみ)
- 旧記事 / 自動投稿 / 巨人 の WP category そのものは削除しない(tag 化 / 隠し)
- env / Secret / Scheduler 変更しない
- 新規 publish の挙動を急激に変えない(段階的 routing 修正)

## 5. user 判断必要事項

- WP admin で **新 category 2 つ作成**(user 操作)
- 既存 publish の **re-categorize 手順承認**(自動 / 手動 / 段階的)
- 「ファン反応」category を作るか保留か

→ 本 ticket は user 判断待ち、Claude / Codex は **設計 + automation script 提案** まで。

## 6. 成功条件

- [ ] 「試合中継」category 作成、broadcast 系 10-20 件 re-categorize
- [ ] manual_intake / rss_fetcher の routing 修正
- [ ] live で「コラム」category が連載 / 特集 / digest 系のみになる
- [ ] sidebar nav が清潔になる
- [ ] regression test:既存 publish の link 不動、404 出ない

## 7. phase 分割

1. **Phase 1**: 設計確認 + WP admin 操作手順 doc 化(本 ticket、Claude)
2. **Phase 2**: user による「試合中継」category 作成
3. **Phase 3**: re-categorize automation script(Codex narrow impl、1-2h)
4. **Phase 4**: routing 修正(manual_intake + rss_fetcher、Codex narrow impl、1-2h)
5. **Phase 5**: image rebuild + redeploy(別判断)

## 8. 親 / 関連

- 親: `doc/active/H3-STRUCTURE-UNIFY-2026-05-08.md`(category 整合で H3 整合性も上がる)
- 関連: `doc/active/SIDEBAR-WIDGETS-2026-05-08.md`(sidebar nav 整理)
- 関連: `doc/done/2026-05/245-front-hide-auto-post-category-label.md`(既存 sidebar 隠し)
