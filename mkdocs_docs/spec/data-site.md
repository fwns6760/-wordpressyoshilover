# 巨人選手データサイト (毎日更新 per-player 静的 page)

> **status**: READY (Phase 1.0 着手、 user GO 済 2026-05-28 PM)
> **正本 ticket**: `doc/active/443-DATA-SITE-daily-per-player-pages.md`
> **実装 ticket**: `doc/active/444-DATA-SITE-phase1-mini-impl.md`
> **rev**: rev2 (rev1 旧「既存記事 → SEO long-form」 案は廃止)

## 1. 何を作るか

巨人 active player ごとに 1 ページの **静的 data page** を `yoshilover.com/data/{player-slug}/` に作成、 **毎日 6:00 JST に同 URL 内容を upsert** (新 URL は作らない)。

**phase 1.0 MVP**: 3 player (岡本和真 / 戸郷翔征 / 坂本勇人) で先行、 2-3 週間観察。

## 2. のもとけ benchmark との差別化

dnomotoke.com を 2026-05-28 fetch 分析の結論:

| 軸 | のもとけ | yoshilover data-site |
|---|---|---|
| 速報 | 1 日 15-25 本 (試合別 / イベント別 URL 量産) | 既存 lane (rss_fetcher + x-post-mail) で並走、 本 lane では 触らず |
| player 軸 | タグ page (記事一覧のみ、 stats なし) | **per-player 静的 page (数字 + 試合 highlight + trend)** |
| 構造化データ | なし | **schema.org SportsPlayer + Person + BreadcrumbList + JSON-LD** |
| 長尾 query | 弱い (鮮度勝負) | **「○○選手 打率 / 防御率 / 推移」 等の long-tail を独占** |
| URL 戦略 | URL 増加型 (試合 / イベント別) | **URL 固定型 (player ごと 1 URL、 daily upsert)** ← SEO 評価集中 |

→ **「per-player baseline page + 構造化データ + 長尾 query」 を yoshilover の堀にする** 方針。

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

| 項目 | 値 |
|---|---|
| URL pattern | `yoshilover.com/data/{player-slug}/` (player ごと 1 URL、 datepath なし) |
| player-slug | roster の `name` を kebab-case + romaji 化 (例: 岡本和真 → `okamoto-kazuma`、 マルティネス → `martinez`) |
| index 設定 | `<meta name="robots" content="index, follow">` を 新 page のみで output、 既存記事は noindex 維持 |
| sitemap | `sitemap.xml` に `/data/{slug}/` を全件追加、 Google Search Console submit |
| canonical | self-canonical (`<link rel="canonical" href="https://yoshilover.com/data/{slug}/">`) |
| trailing slash | `/data/slug/` (slash あり) で固定、 slash なしは 301 で揃える |

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

| phase | 対象 | 数 | trigger |
|---|---|---|---|
| **Phase 1.0** (MVP-mini) | 岡本和真 / 戸郷翔征 / 坂本勇人 | 3 | user GO 済 (2026-05-28 PM) |
| Phase 1.5 | 一軍 active player | ~30 | Phase 1.0 SEO 流入確認 + 品質 OK |
| Phase 1 (full) | 全 active player + manager/coach | ~110 | Phase 1.5 観察 |
| Phase 2 | event-base aggregation (試合まとめ / HR 一覧 等) | +追加 | Phase 1 stable 後 |
| Phase 3 | column 風 long-form (rev1 旧案復活) | +追加 | data 基盤 stable 後 |

## 13. 評価指標

- Google Search Console: indexed page 数、 28d 流入 trend、 long-tail query CTR
- 月間 upsert 成功率 (target 99%、 fail は監視 alert)
- `post_gen_validate` fail 率 (短評 section)、 target ≤ 10%
- featured_media fallback 率 (target ≤ 30%、 高ければ写真 asset 追加)

## 14. 変更履歴

- 2026-05-28: rev1 初版 (旧「既存記事から SEO long-form aggregation」 案)
- 2026-05-28 PM: rev2 全面書き換え (user 「データサイト作って index からしてく。 毎日更新のデータ記事。 選手全員の」)
