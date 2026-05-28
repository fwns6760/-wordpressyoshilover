# 巨人選手データサイト (topical cluster 構造 / 毎日更新)

> **status**: READY (Phase 1.0 着手、 user GO 済 2026-05-28 PM)
> **正本 ticket**: `doc/active/443-DATA-SITE-daily-per-player-pages.md`
> **実装 ticket**: `doc/active/444-DATA-SITE-phase1-mini-impl.md`
> **rev**: rev3 (rev2 までは per-player page 単独設計、 rev3 で topical cluster 構造 + 大手差別化 4 理由 を明文化)

## 1. 何を作るか — topical cluster SEO 構造

既存 DB (insight.db + WP 既存記事) から **3 階層の SEO topical cluster** を構築:

```
┌─────────────────────────────────────────────────────────────┐
│ Cluster page  /data/                                         │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ 巨人選手全員 hub (110 名 list + 全体 ranking 表)     │  │
│   │ → 各 Pillar page への internal link (110 link)       │  │
│   └──────────────────────────────────────────────────────┘  │
│            ↓ internal link                                   │
│ Pillar page  /data/{player-slug}/                            │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ 該当選手の永続 包括 data page (毎日 6:00 upsert)     │  │
│   │ - 当日試合 / 直近 5 試合 / 月間 / season / vs 他球団 │  │
│   │ - 関連 player 比較 / 関連 Topic 記事 link 10-20      │  │
│   │ - schema.org SportsPlayer + Person + JSON-LD         │  │
│   └──────────────────────────────────────────────────────┘  │
│            ↑ back-link                ↓ internal link        │
│ Topic page  既存 ~73,000 + 日々の新規 data 速報              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ - 既存記事 (試合別 / event 別、 既存 lane で publish) │  │
│   │ - 新規 daily data 速報 (Phase 3 で追加生成)          │  │
│   │ - 末尾に「{player} データに戻る」 link (Pillar back) │  │
│   └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**SEO 上の意義** (Google topical authority):
- Cluster → Pillar (110 link) → Topic (10-20/pillar) → Pillar back の **internal link 流量** で「巨人選手」 topic の authority を集中させる
- 1 URL ごと shallow content にせず、 cluster 全体で **topical depth** を Google に示す
- 既存 ~73,000 記事 (現在 noindex) を Topic として cluster に組み込む = 既存資産を活かす

**phase 1.0 MVP**: Cluster page 1 + Pillar page 3 (**吉川尚輝 / 坂本勇人 / 丸佳浩**) で先行、 2-3 週間観察。

## 2. のもとけ benchmark との差別化 + 大手メディアに作れない 4 理由

dnomotoke.com を 2026-05-28 fetch 分析の結論:

| 軸 | のもとけ | yoshilover data-site |
|---|---|---|
| 速報 | 1 日 15-25 本 (試合別 / イベント別 URL 量産) | 既存 lane (rss_fetcher + x-post-mail) で並走、 本 lane では 触らず |
| player 軸 | タグ page (記事一覧のみ、 stats なし) | **per-player Pillar page (数字 + 試合 highlight + trend)** |
| 構造化データ | なし | **schema.org SportsPlayer + Person + BreadcrumbList + JSON-LD** |
| 長尾 query | 弱い (鮮度勝負) | **「○○選手 打率 / 防御率 / 推移」 等の long-tail を独占** |
| URL 戦略 | URL 増加型 (試合 / イベント別) | **URL 固定型 (Pillar = player ごと 1 URL、 daily upsert)** ← SEO 評価集中 |
| topical cluster | タグ依存 (Cluster の概念なし) | **Cluster → Pillar → Topic の 3 階層構造で authority 集中** |

### 大手メディア (報知 / 日刊スポーツ / 東スポ / 朝日 等) に真似できない 4 理由

| # | 理由 | 大手の制約 | yoshilover の優位 |
|---|---|---|---|
| 1 | **cost** | 110 名 daily update は記者人件費で不可能 | Gemini Flash Lite で月 ¥30-50、 AI が回す |
| 2 | **focus 範囲** | 大手は 12 球団分散、 巨人だけに紙面割けない | **巨人専門で深掘り** (一軍 + 二軍 + 育成まで個別 Pillar) |
| 3 | **fan voice** | 編集者距離 / 事実中心、 感情入れたら炎上 | **ファン感情寄り短評** (「ここで打って欲しかった」 等) を AI で安全に挿入 |
| 4 | **永続 baseline + cluster** | 記事 (URL 量産型 / 速報) で蓄積、 既存記事に back-link 注入する文化なし | **per-player 1 URL に永続蓄積 + 既存 73,000 記事に back-link 自動注入** (Phase 2) で topical authority 構築 |

→ 「**topical cluster + 永続 Pillar + AI 大量自動化**」 が yoshilover の堀。 大手は cost / focus / culture の 3 つで構造的に同等のものを作れない。

## 3. 既存 lane との関係

```
┌────────────────────────────────────────────────────────────────────┐
│ 既存 lane (本 spec scope 外、 触らない)                            │
│  rss_fetcher → draft body editor → guarded-publish → publish-notice│
│       ↓                                                            │
│   既存記事 ~73,000+ (noindex 維持)                                 │
│                                                                     │
│  data-insight (anomaly 439 ticket)                                 │
│       ↓                                                            │
│   試合別 / event 別 anomaly 記事 (既存 publish path)              │
│                                                                     │
│  x-post-mail-lane                                                  │
│       ↓                                                            │
│   X-post 候補 mail (試合中 15 分おき)                              │
├────────────────────────────────────────────────────────────────────┤
│ 新 lane (本 spec)                                                  │
│  data-site-publisher (Cloud Run Job、 0 6 * * * JST)               │
│       ↓                                                            │
│   yoshilover.com/data/{player-slug}/ × 110 page (Phase 1 full)    │
│   index=true, schema.org SportsPlayer, daily upsert               │
│       ↑                                                            │
│   素材: 既存 publish 記事 + insight.db (read-only query)          │
└────────────────────────────────────────────────────────────────────┘
```

- 既存 lane は **触らない**
- 新 lane は既存 publish 記事 + `insight.db` を **read-only query**
- 出力先 URL は完全新規 (`/data/...`)、 既存 URL と分離

## 4. URL / sitemap / index

| 階層 | URL pattern | 数 (Phase 1 full) |
|---|---|---|
| **Cluster** | `yoshilover.com/data/` (固定 1 URL) | 1 |
| **Pillar** | `yoshilover.com/data/{player-slug}/` (player ごと 1 URL) | ~110 |
| **Topic** | 既存 publish 記事 URL (例: `yoshilover.com/73041/`) + 新規 daily 速報 URL (Phase 3) | ~73,000 + 追加 |

| 項目 | 値 |
|---|---|
| player-slug | roster の `name` を kebab-case + romaji 化 (例: 岡本和真 → `okamoto-kazuma`、 マルティネス → `martinez`、 吉川尚輝 → `yoshikawa-naoki`) |
| index 設定 | Cluster + Pillar は `<meta name="robots" content="index, follow">`、 既存 Topic 記事は noindex 維持 (Phase 2 で back-link 注入時に index 解除検討) |
| sitemap | `sitemap.xml` に `/data/` + `/data/{slug}/` 全件追加、 Google Search Console submit |
| canonical | self-canonical (`<link rel="canonical" href="https://yoshilover.com/data/{slug}/">`) |
| trailing slash | `/data/` + `/data/slug/` (slash あり) で固定、 slash なしは 301 で揃える |

### 内部 link 流量設計 (topical authority 構築)

| from | to | 数 | 用途 |
|---|---|---|---|
| Cluster | 全 Pillar | 110 link | Pillar への authority 流入 |
| Pillar | 関連 Topic | 10-20 link/Pillar | Topic への authority 流入 (該当 player tag の既存記事) |
| Topic | 1 Pillar | 1 link/Topic | Pillar への back link (Phase 2 で 73,000 記事に自動注入) |
| Pillar | Cluster | 1 link/Pillar (breadcrumb) | Cluster への back link |
| Pillar | 関連 Pillar | 3-5 link (同 pos / 同 lineup) | Pillar 間 cross link、 cluster 内 PageRank 分散最適化 |

## 5. 内容構成 (静的 page)

```
┌───────────────────────────────────────────────────────┐
│ {player 名} ({pos} / 背番号 {jersey})                 │  ← H1
│ [featured_media 写真 (保存写真 or team mark)]          │
├───────────────────────────────────────────────────────┤
│ 当日試合 結果                                          │  ← H2 (試合あれば)
│   [打席 / 投球 結果 table、 出典 link]               │
├───────────────────────────────────────────────────────┤
│ 直近 5 試合 stats                                      │  ← H2
│   [打率 / OPS / HR / etc table、 試合ごと行]         │
├───────────────────────────────────────────────────────┤
│ 月間 / season summary                                  │  ← H2
│   [今月 / 今 season の累計、 traditional + advanced]  │
├───────────────────────────────────────────────────────┤
│ vs 他球団 split                                        │  ← H2
│   [対戦相手別 stats]                                  │
├───────────────────────────────────────────────────────┤
│ 関連 player 比較                                       │  ← H2
│   [同 pos / 同 lineup 内の player との比較]           │
├───────────────────────────────────────────────────────┤
│ {player 名} 関連記事 (yoshilover 既存)                │  ← H2
│   [既存 publish 記事 link 5-10 本]                    │
├───────────────────────────────────────────────────────┤
│ schema.org JSON-LD (hidden)                            │
│   SportsPlayer, Person, BreadcrumbList                 │
└───────────────────────────────────────────────────────┘
```

## 6. データ源

| 項目 | source |
|---|---|
| player roster | `config/giants_roster.json` (active=True、 role in {player, manager, coach}) |
| 試合 stats | `insight.db` (既存 data-insight が更新する SQLite、 yoshilover GCS バケット上) |
| 関連記事 | WP REST `/wp/v2/posts?tags={player_tag_id}` (person_tag_router で routing 済 tag) |
| 写真 | 保存 player 写真 51 名 + team mark (`/wp-content/uploads/...` 既存)、 437 phase1 rule 共通 |

## 7. 生成 trigger

| job | schedule | 用途 |
|---|---|---|
| `data-site-publisher-daily` | `0 6 * * *` JST | 全対象 player の page upsert |

Cloud Run Job 新設、 既存 scheduler に追加せず別 job。 Phase 1.0 は 3 player のみ実行、 Phase 1.5 で 30 名、 Phase 1 で 110 名。

## 8. LLM 使用範囲

- データ表 / table の構成は **LLM 不要** (insight.db クエリ + jinja template で render)
- LLM (Gemini 3.1 Flash Lite) は **短評 200-500 字** のみ:
  - 「直近 5 試合の傾向 (打撃 / 投球)」
  - 「月間 highlight」
  - 「season summary 1-2 文」
- prompt 契約: 既存 [[x-post-mail.md]] の voice rule (URL / hashtag / 媒体名 含めない / 数字捏造禁止) 流用
- 出力品質 gate: 既存 `post_gen_validate` を流用、 fail 時は短評 section だけ skip (data 表は表示)

## 9. featured_media

- rule (437 phase1 と共通):
  1. 該当 player の 保存写真 (`config/player_eyecatch_map.json` 51 名 + Phase 1.5 で追加予定)
  2. team mark (`巨人マーク` media_id 63578)
- 写真未保存 player は team mark で fallback、 thin content にしない為 ALT text に「{player}（写真は team mark）」 明示

## 10. 品質 gate

| gate | 内容 |
|---|---|
| schema.org 必須 | JSON-LD 不在は publish skip |
| data 表 必須 | insight.db query が 0 件 の場合 skip (data なしの thin page 作らない) |
| 短評 LLM fail | `post_gen_validate` fail なら短評 section omit、 data 表のみで publish (page 自体は出す) |
| 関連記事 link 必須 | WP tag query 0 件 なら skip (player tag 未付与 = thin content risk) |

## 11. コスト

| 項目 | Phase 1.0 (3 player) | Phase 1 full (110 player) |
|---|---|---|
| Gemini Flash Lite | 3 call/day × 30 = 90 call/月 ≈ ¥1 | 110 × 30 = 3,300/月 ≈ ¥30-50 |
| Cloud Run Job | 0.5 min/day × 30 ≈ ¥0 | 30 min/day × 30 ≈ ¥0 (free tier) |
| GCS / Logging | 既存 bucket 流用 | 同左 |
| WP REST POST/PUT | 同 site への upsert、 ¥0 | 同左 |
| **合計** | **¥1-2/月** | **¥30-50/月** |

## 12. ロールアウト

| phase | scope | URL 数 | trigger |
|---|---|---|---|
| **Phase 1.0** (MVP-mini) | Cluster `/data/` 1 + Pillar `/data/{slug}/` × 3 (**吉川尚輝 / 坂本勇人 / 丸佳浩**) | 4 | **user GO 済 (2026-05-28 PM)** |
| Phase 1.5 | Cluster 更新 + 一軍 active Pillar 30 | 31 | Phase 1.0 SEO 流入確認 + 品質 OK |
| Phase 1 (full) | Cluster 完成 + 全 active Pillar 110 (player + manager + coach) | 111 | Phase 1.5 観察 |
| Phase 2 | 既存 ~73,000 Topic 記事に Pillar back-link 自動注入 (大手差別化主軸の 4 番目) | mutation 73,000 | Phase 1 full stable 後 |
| Phase 3 | 日々の data 速報 page 新規生成 (Topic 自前産出、 試合別 / event 別) | +追加 daily | Phase 2 完了後 |
| Phase 4 | column 風 long-form (rev1 旧案復活) | +追加 | data 基盤 stable 後 |

## 13. 評価指標

- Google Search Console: indexed page 数、 28d 流入 trend、 long-tail query CTR
- 月間 upsert 成功率 (target 99%、 fail は監視 alert)
- `post_gen_validate` fail 率 (短評 section)、 target ≤ 10%
- featured_media fallback 率 (target ≤ 30%、 高ければ写真 asset 追加)

## 14. 変更履歴

- 2026-05-28: rev1 初版 (旧「既存記事から SEO long-form aggregation」 案)
- 2026-05-28 PM: rev2 全面書き換え (user 「データサイト作って index からしてく。 毎日更新のデータ記事。 選手全員の」)
- 2026-05-28 PM2: rev3 topical cluster 構造 + 大手差別化 4 理由 + 内部 link 流量設計 を明文化 (user 「今あるデータベースから色々な記事をつくる。 球団の選手全体をクラスターページ。 選手をピラーページ。 日々の記事を速報ページでとぴくらをつくりたい」 + 「コンセプトは大手メディアではわからない」)。 Phase 1.0 player を 吉川尚輝 / 坂本勇人 / 丸佳浩 に変更 (user 指定)、 scope に Cluster page 追加 (4 page)
- 2026-05-28 PM3: rev4 「大手にない data」 metric pack を §15 で明文化、 Phase 1.0a/b/c 段階追加 (user 「大手に乗らないデータとかない? データとして弱い」)

## 15. 大手にない data metric pack (rev4 追加)

「大手 (報知 / 日刊 / サンスポ / 朝日) が紙面 / web で常時表示しない、 ファンが本当に知りたい data」 を 3 段階で Pillar に追加。

### Phase 1.0a (即実装、 batting_logs SUM のみで取得可)

| # | data | sample (吉川尚輝) | source |
|---|---|---|---|
| 1 | 打順別 打率 | 1番 .083 / 2番 .250 / 3番 .167 / 7番 .333 / 8番 .400 | `batting_logs.slot_order` GROUP BY |
| 2 | vs 各球団 打率 | 中日 .500 / DeNA .250 / ヤクルト .111 / 阪神 .176 / 広島 .167 / ソフトバンク .222 | `batting_logs` JOIN `games.opponent` |

### Phase 1.0b (continuous、 1.0a 観察後)

| # | data | source |
|---|---|---|
| 3 | 球場別 (本拠地 vs ビジター) | `games.source_url` → 球場 抽出 |
| 4 | イニング別 (序盤 1-3 / 中盤 4-6 / 終盤 7-9) | `at_bat_details.inning_no` |
| 5 | 守備機会 + 失策 | `defense_opportunities` + `fielding_logs` |
| 6 | vs 左右投手 打率 | `at_bat_details.current_pitcher` + pitcher hand JOIN |
| 7 | count split (初球 / 2 strike 後) | `at_bat_details.count_balls / count_strikes` |
| 8 | 連続安打 / 出塁 streak | `batting_logs` 順次 scan |
| 9 | 打席あたり投球数 | `at_bat_details` 集計 |

### Phase 1.0c (BLOCKED、 ticket 445 で先に修復)

| # | data | block 理由 |
|---|---|---|
| 10 | 得点圏打率 (RISP) | `at_bat_details.batter_canonical` NULL (raw `batter` column のみ 「吉川」「代打・ 吉川」 形式)、 data-insight lane の batter canonical 補完 修復必要 |
| 11 | 走者状況別 (満塁 / 2塁等) | 同上 |

### advanced sabermetric (insight.db 既存)

advanced_metric_snapshots table に 17 metric (BABIP / wOBA / ISO / BB_pct / K_pct / OBP / SLG / OPS / FIP / xFIP / WHIP 等) + 9 scope (season / monthly / weekly / last_*) + **league_rank / position_rank** が available。 Phase 1.0a で 打順別 + vs 球団 を出した後、 Pillar に「サバメトリクス (大手未掲載)」 section として並走表示する案も検討 (Phase 1.0a に含めるか別 phase は user 指示待ち)。
