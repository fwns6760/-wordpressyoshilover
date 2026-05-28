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
  - **rev2 (本版)**: user 「データサイト作って index からしてく。 毎日更新のデータ記事。 選手全員の」 で方向転換
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

## 3. 何を作るか

| 項目 | 設計 |
|---|---|
| URL | `yoshilover.com/data/{player-slug}/` 静的 page (例: `/data/okamoto-kazuma/`)、 player ごと 1 URL |
| 数 | active player (一軍 + 二軍) ~83 名 + manager/coach 数名 = ~110 page |
| 更新頻度 | **毎日 1 回** (朝 6:00 JST upsert)、 同 URL 上書き |
| 内容構成 | (1) 当日試合 打席/投球結果 (2) 直近 5 試合 stats (3) 月間 trend (4) season summary (5) vs 他球団 split (6) 関連 player 比較 (7) 元記事 link block |
| 構造化データ | `SportsPlayer` + `SportsEvent` + `Person` schema.org JSON-LD、 BreadcrumbList |
| index 設定 | 新 `data/` section のみ `index, follow` (`<meta name="robots">` override)、 既存記事は noindex 維持 |
| featured_media | player 保存写真 (rule = 既存 437 phase1 と同じ 3 段 fallback) |
| 公開 trigger | 新 Cloud Run Job `data-site-publisher`、 Cloud Scheduler `0 6 * * *` JST |

## 4. のもとけ との差別化

| 軸 | のもとけ | yoshilover data-site (本 ticket) |
|---|---|---|
| 速報 | 1 日 15-25 本 (試合中 30 分単位) | 既存 lane (rss_fetcher + x-post-mail) で並走、 本 lane は触れず |
| player base | タグ page (記事一覧のみ、 stats なし) | **静的 page (数字 + 試合 highlight + trend)** ← 差別化主軸 |
| 構造化データ | なし | schema.org SportsPlayer/Event + JSON-LD ← 差別化 |
| 長尾 query | 弱い | **「岡本和真 5月 打率」「戸郷翔征 防御率 推移」 等を狙う** |
| 更新 | 試合別 / イベント別記事 (URL 増加型) | **同 URL 毎日 upsert (URL 固定型)** ← SEO 評価集中 |

## 5. phase 分け

| stage | 対象 | 数 | trigger | 期間 |
|---|---|---|---|---|
| **Phase 1.0 (MVP-mini)** | star player 3 名 (岡本和真 / 戸郷翔征 / 坂本勇人) | 3 page | **user GO 済** | 2-3 週間観察 |
| Phase 1.5 | 一軍 active player | ~30 page | Phase 1.0 SEO 流入確認 | 1 ヶ月観察 |
| Phase 1 (full) | 全 active player + manager/coach | ~110 page | Phase 1.5 観察 OK | 継続運用 |
| Phase 2 | event-base aggregation (試合まとめ / HR 一覧 etc) | +追加 | Phase 1 stable 後 | — |
| Phase 3 | column 風 long-form (旧 rev1 SEO long-form 案を復活) | +追加 | data 基盤 stable 後 | — |

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

- [ ] 3 player の static page が `/data/{slug}/` に作成される
- [ ] 各 page に schema.org JSON-LD (SportsPlayer + Person) 埋め込み
- [ ] `<meta name="robots" content="index, follow">` (新 page のみ)
- [ ] featured_media = 該当 player 保存写真
- [ ] daily 6:00 JST upsert で同 URL 内容更新 (新 URL 増加なし)
- [ ] Google Search Console submit (sitemap.xml に新 URL 追加)
- [ ] 2-3 週間後 indexed 確認 + 流入 trend
- [ ] コスト ¥1-2/月 (Phase 1.0 mini で実測)
