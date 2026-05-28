# 443 巨人選手データサイト — 毎日更新 per-player 静的 page

## 1. ticket header

- **ticket id**: 443
- **status**: READY (rev2 2026-05-28 PM、 user GO 済 Phase 1.0 着手可)
- **owner**: Claude Code
- **lane**: data-site / per-player publisher
- **created**: 2026-05-28
- **priority**: P1 (SEO 基盤、 のもとけ差別化主軸)
- **github_issue**: PENDING
- **rev 履歴**:
  - rev1 (廃止): 「既存記事から SEO long-form aggregation」 方向
  - rev2: user 「データサイト作って index からしてく。 毎日更新のデータ記事。 選手全員の」 で方向転換 (per-player static page 採用)
  - **rev3 (本版)**: user 「今あるデータベースから色々な記事をつくる。 球団の選手全体をクラスターページ。 選手をピラーページ。 日々の記事を速報ページでとぴくらをつくりたい」 + 「コンセプトは大手メディアではわからない」 で **topical cluster 構造 + 大手差別化 4 理由** を本 ticket と spec に明文化、 Phase 1.0 player を 吉川尚輝 / 坂本勇人 / 丸佳浩 に変更、 scope に Cluster page 追加 (合計 4 page)
- **related**:
  - [[project_site_direction_data_focus]] (memory) — データサイト方向
  - [[project_data_insight_aggressive_publishing]] (memory) — 既存 anomaly base、 本 lane と並走
  - [[project_data_insight_final_whitelist_2026_05_15]] (memory) — metric whitelist
  - [[project_437_phase1_live_phase2_xpost_pending]] (memory) — featured_media rule 3 段 fallback
  - [[feedback_publish_forward_must_check_gate_reason]] (memory) — yoshilover noindex 前提 (本 ticket で新 section のみ解除)
  - 439 ticket (data-insight 7 signal restore) — anomaly highlight lane
  - 437 ticket (eyecatch) — 写真 asset 共通
- **spec doc**: `mkdocs_docs/spec/data-site.md` (rev2 で rename)
- **implementation ticket**: 444 (Phase 1.0 着手 plan、 別 file)

## 2. 背景 / why

- yoshilover の検索流入が薄い、 既存記事 ~73,000 は noindex 前提で SEO 資産になっていない
- のもとけ benchmark (2026-05-28 fetch): **速報量産型、 player 別 baseline page なし** → ここが差別化機会
- yoshilover の data-insight asset (anomaly 検知 + 数字基盤) を活かし、 **全 active player の数字を永続 indexed page にする** ことで:
  - 「岡本和真 打率」「戸郷翔征 防御率」 等の常時 hit ページ群を持つ
  - のもとけ が薄い「per-player baseline」 を独占
  - 既存 anomaly data-insight (ticket 439) は highlight 通知、 本 lane は baseline daily 蓄積

## 3. 何を作るか — topical cluster 3 階層

```
[Cluster] /data/   (1 page、 巨人選手全員 hub)
    ↓ link 110
[Pillar] /data/{player-slug}/   (player ごと 1 page、 daily upsert)
    ↓ link 10-20/pillar    ↑ back link 1/topic (Phase 2)
[Topic] 既存記事 ~73,000 + 新規 daily 速報 (Phase 3)
```

| 階層 | URL | 数 (Phase 1 full) | 役割 |
|---|---|---|---|
| Cluster | `/data/` | 1 | 全 player hub、 全体 ranking 表、 Pillar への link 110 |
| Pillar | `/data/{player-slug}/` | ~110 | 永続 包括 data page (当日 / 直近 / 月間 / season / vs 他球団 / 関連 player / 関連 Topic link) |
| Topic | 既存記事 + 新規 daily 速報 | ~73,000 + α | 試合別 / event 別記事、 末尾に Pillar back link (Phase 2 で 73,000 件 batch 注入) |

| 項目 | 設計 |
|---|---|
| 更新頻度 | Pillar 毎日 6:00 JST upsert、 Cluster 同時更新 (同 URL 上書き、 新 URL 増加なし) |
| 構造化データ | Cluster = `CollectionPage` + `ItemList`、 Pillar = `SportsPlayer` + `Person` + `BreadcrumbList`、 全 JSON-LD |
| index 設定 | Cluster + Pillar = `index, follow`、 既存 Topic は noindex 維持 (Phase 2 で再評価) |
| featured_media | Pillar = 該当 player 保存写真 (437 phase1 rule 3 段 fallback)、 Cluster = team mark |
| 公開 trigger | 新 Cloud Run Job `data-site-publisher`、 Cloud Scheduler `0 6 * * *` JST |

## 3.5 大手メディアに作れない 4 理由 (yoshilover の堀)

user 明示 2026-05-28 PM 「コンセプトは大手メディアではわからない」 を明文化:

| # | 理由 | 大手の制約 | yoshilover の優位 |
|---|---|---|---|
| 1 | **cost** | 110 名 daily update は記者人件費で不可能 | Gemini Flash Lite で月 ¥30-50、 AI 自動化 |
| 2 | **focus 範囲** | 大手は 12 球団分散、 巨人だけに紙面割けない | **巨人専門で深掘り** (一軍 + 二軍 + 育成 + 監督・コーチまで個別 Pillar) |
| 3 | **fan voice** | 編集者距離 / 事実中心、 感情入れたら炎上 risk | **ファン感情寄り短評** (「ここで打って欲しかった」 等) を AI で安全に挿入 |
| 4 | **永続 baseline + cluster** | 記事 URL 量産型 / 速報蓄積、 既存記事に back-link 注入する文化なし | **per-player 1 URL に永続蓄積 + 既存 73,000 記事に back-link 自動注入** (Phase 2) で topical authority 構築 |

→ 大手は cost / focus / culture の 3 つで構造的に同等のものを作れない、 これが yoshilover の堀。

## 4. のもとけ との差別化

| 軸 | のもとけ | yoshilover data-site (本 ticket) |
|---|---|---|
| 速報 | 1 日 15-25 本 (試合中 30 分単位) | 既存 lane (rss_fetcher + x-post-mail) で並走、 本 lane は触れず |
| player base | タグ page (記事一覧のみ、 stats なし) | **静的 page (数字 + 試合 highlight + trend)** ← 差別化主軸 |
| 構造化データ | なし | schema.org SportsPlayer/Event + JSON-LD ← 差別化 |
| 長尾 query | 弱い | **「岡本和真 5月 打率」「戸郷翔征 防御率 推移」 等を狙う** |
| 更新 | 試合別 / イベント別記事 (URL 増加型) | **同 URL 毎日 upsert (URL 固定型)** ← SEO 評価集中 |

## 5. phase 分け

| stage | scope | URL 数 | trigger | 期間 |
|---|---|---|---|---|
| **Phase 1.0 (MVP-mini)** | Cluster `/data/` 1 + Pillar `/data/{slug}/` × 3 (**吉川尚輝 / 坂本勇人 / 丸佳浩**) | 4 | **user GO 済 (2026-05-28 PM)** | 2-3 週間観察 |
| Phase 1.5 | Cluster 更新 + 一軍 active Pillar 30 | 31 | Phase 1.0 SEO 流入 + 品質 OK | 1 ヶ月観察 |
| Phase 1 (full) | Cluster 完成 + 全 Pillar 110 (player + manager + coach) | 111 | Phase 1.5 観察 OK | 継続運用 |
| Phase 2 | 既存 ~73,000 Topic 記事に Pillar back-link 自動注入 (大手差別化 4 番目) | mutation 73,000 | Phase 1 full stable 後 | — |
| Phase 3 | 日々の data 速報 Topic 自前産出 (試合別 / event 別) | +追加 daily | Phase 2 完了後 | — |
| Phase 4 | column 風 long-form (旧 rev1 SEO long-form 案を復活) | +追加 | data 基盤 stable 後 | — |

## 6. 触らない範囲

- 既存記事 (~73,000 post) の本文 / title / noindex
- 既存 lane: rss_fetcher / draft body editor / guarded-publish / publish-notice / x-post-mail-lane / data-insight (anomaly 439)
- WP frontend display (既存 path)
- featured_media rule (元記事 → 保存写真 → team mark 3 段 fallback 維持)
- 動画転載 (著作権 NG、 既存 YouTube link 経路で対応)
- 公示 (既存 sports_fetcher で対応済)

## 7. open question (user 判断 解消済 含む)

| # | 質問 | 解消 / 推奨 |
|---|---|---|
| 1 | noindex 解除 | ✅ **新 data/ section のみ解除、 既存 noindex 維持** (user OK) |
| 2 | コスト | ✅ ¥30-50/月 (Phase 1 full 想定、 Phase 1.0 mini = ¥1-2/月)、 Gemini Flash Lite free tier 1,500 RPD で吸収 |
| 3 | 引用 | ✅ paraphrase 優先 + 引用は補助的 (40-60字、 1 page 1-2 quote)、 出典 link 必須 |
| 4 | 差別化方向 | ✅ data 深掘り + 構造化データ + 長尾 query |
| 5 | オフシーズン | 12-3 月 = 「○○の年間振り返り」 系に static page 内容を切替、 daily upsert 継続 |
| 6 | 速報 X-post 連動 | ✅ 既存 x-post-mail-lane で代用 (本 lane 触れず) |
| 7 | 動画クリップ | ✅ scope 外、 既存 YouTube link 経路 |
| 8 | 公示まとめ | ✅ 既存 sports_fetcher (rss_fetcher.py:22218) で OK |
| 9 (new) | 出場無い player (二軍 / 怪我中) の page | data 表示 + 「直近の出場記録」 + 「次の試合予定」 を表示、 thin content にしない為 出場ゼロ player は週 1 更新に頻度 落とす (Phase 1.5 以降) |

## 8. next action (Phase 1.0 着手)

- (Claude 自律) implementation ticket 444 起票 (Phase 1.0 plan)
- (Claude 自律) spec doc `mkdocs_docs/spec/data-site.md` 仕様詳細化
- (Claude 自律) `src/data_site_publisher.py` + `Dockerfile.data_site_publisher` + `cloudbuild_data_site_publisher.yaml` 実装
- (Claude 自律) Cloud Scheduler `data-site-publisher-daily` (`0 6 * * *` JST) 作成
- (Claude 自律) 初回 fire = 2026-05-29 (木) 6:00 JST、 3 player 分の page 生成 + WP REST POST
- (user 判断 後追い) Phase 1.0 観察 OK で Phase 1.5 拡大

## 9. 受け入れ条件 (Phase 1.0)

- [ ] Cluster `/data/` 1 page 作成 (3 player のみ表示、 Phase 1.5 で拡大予定)
- [ ] Pillar `/data/{slug}/` × 3 (`yoshikawa-naoki` / `sakamoto-hayato` / `maru-yoshihiro`) 作成
- [ ] Cluster → 各 Pillar への internal link 3 本
- [ ] 各 Pillar → 関連 Topic (既存記事) link 10-20 本
- [ ] Cluster page に `CollectionPage` + `ItemList` JSON-LD
- [ ] Pillar page に `SportsPlayer` + `Person` + `BreadcrumbList` JSON-LD
- [ ] `<meta name="robots" content="index, follow">` (Cluster + Pillar のみ)
- [ ] featured_media: Cluster = team mark / Pillar = 該当 player 保存写真
- [ ] daily 6:00 JST upsert で 4 URL 内容更新 (新 URL 増加なし)
- [ ] Google Search Console submit (sitemap.xml に 4 URL 追加)
- [ ] 2-3 週間後 indexed 確認 + 流入 trend
- [ ] コスト ¥1-2/月 (Phase 1.0 mini で実測)
