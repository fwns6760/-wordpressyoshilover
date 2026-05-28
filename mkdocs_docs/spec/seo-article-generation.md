# SEO 記事生成 (既存記事 → SEO 強化 long-form)

> **status**: DRAFT (ticket [443](https://github.com/fwns6760/-wordpressyoshilover/issues?q=443) で仕様確定中、 本 spec は phase 1 = 「選手別 月間まとめ」 を前提に書く)
> **正本 ticket**: `doc/active/443-SEO-article-from-existing-articles.md`

## 1. 何を作るか

既存 publish 記事 (yoshilover ~73,000+ post) を素材に、 SEO 検索流入を狙う **long-form aggregation 記事** を新規生成する lane。

**phase 1 MVP**: 巨人 active player の **「選手別 月間まとめ」** long-form を週 1 回生成。

## 2. 既存 lane との関係

```
┌──────────────────────────────────────────────────────────────────┐
│ 既存                                                             │
│ ┌─────────────┐  ┌────────────┐  ┌──────────────┐  ┌────────┐ │
│ │ rss_fetcher │→│ draft body │→│ guarded-     │→│ publish │ │
│ │             │  │ editor      │  │ publish     │  │ -notice│ │
│ └─────────────┘  └────────────┘  └──────────────┘  └────────┘ │
│         ↓                                                ↓     │
│   既存記事 ~73,000+ post (noindex 前提)                        │
│                                                                  │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ 新規 lane (本 spec)                                      │   │
│ │ ┌──────────────────────┐    ┌──────────────────────┐  │   │
│ │ │ seo-article-publisher │ → │ Phase 1 SEO long-form │  │   │
│ │ │ (新 Cloud Run Job)    │    │ index=true、 新 URL  │  │   │
│ │ └──────────────────────┘    └──────────────────────┘  │   │
│ │       ↑ 素材として既存記事を query / cluster              │   │
│ └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

- 既存 lane (rss_fetcher → draft body editor → guarded-publish → publish-notice) は **触らない**
- 新 lane (seo-article-publisher) が **既存 publish 記事を read-only で query**、 LLM で long-form 生成 → 新 URL で publish
- 既存記事の noindex / 本文は不変

## 3. 生成 trigger / schedule

| schedule | 用途 |
|---|---|
| `0 21 * * 0` JST (週 1 回、 日曜 21:00) | phase 1 selesai: 選手別 月間まとめ生成 |
| `(後追加)` 月 1 回 | phase 3: event-based aggregation (試合結果まとめ / HR 一覧 等) |

Cloud Scheduler job 名: `seo-article-publisher-weekly` (新規追加、 既存 scheduler に追加せず別 job)。

## 4. 入力 (素材取得)

### 4.1 player query

```python
# 巨人 active player 上位 10 名 (打者 5 + 投手 5)
TARGET_PLAYERS = ["岡本和真", "坂本勇人", "丸佳浩", "大城卓三", "キャベッジ",
                  "戸郷翔征", "山﨑伊織", "田中将大", "マルティネス", "西舘勇陽"]
```

選定基準:
- `giants_roster.json` active=True かつ role=player
- 直近 30 日の WP 既存記事 hit 数 が多い順 (top 10)
- (要 user 判断: 監督・コーチも含めるか?)

### 4.2 source 記事 query

WP REST `/wp-json/wp/v2/posts` で:
- `tags=<player_tag_id>` (該当 player tag、 person_tag_router で routing 済)
- `after=<YYYY-MM-01>T00:00:00`
- `before=<YYYY-MM-30>T23:59:59`
- `status=publish`
- `per_page=100, orderby=date desc`

→ 該当 player の月内 publish 記事を全件取得 (推定 10-50 post/player)。

## 5. 生成 (LLM)

- model: `gemini-3.1-flash-lite` (既存 x-post-mail-lane / draft body editor と共通、 コスト 抑える)
- prompt:
  - 役割: 「巨人専門ライター、 SEO 強化 long-form を書く」
  - 入力: player 名、 月、 既存記事 title + 抜粋 (1 article 200 字程度に summarize 済)
  - 出力 contract:
    - title: `{player}の{YYYY年MM月}まとめ — {hook 1-2 句}` (例: `岡本和真の2026年5月まとめ — ホームラン量産で打線を牽引`)
    - 本文 構成:
      1. 概要 (200-300 字、 月間 highlight 3-5 個)
      2. 試合別 highlight (5-10 件、 各 100-200 字、 出典 link 付き)
      3. 数字 summary (打率 / HR / OPS / WAR 等、 既存 data-insight 結果を流用可)
      4. 関連記事 link block (該当 player の既存 publish 記事 link 5-10 本)
    - 本文 長さ: 1500-3000 字
    - hashtag / 媒体名 / 「ヨシラバーで整理しました」 含めない (既存 voice rule 維持)
- temperature: 0.3 (factual 寄り)

## 6. 品質 gate

既存 `post_gen_validate` (`src/rss_fetcher.py:_evaluate_post_gen_validate`) を **流用**:
- `close_marker` / `intro_echo` / `placeholder_body` / `entity_mismatch` 等 全軸 check
- fail 時: status=draft 維持、 `【要review｜post_gen_validate】` ではなく `要review-post_gen_validate` tag (5/28 fix [438] 経由) で marker

追加 gate (SEO 専用):
- title 長さ 30-60 字 (Google SERP 表示 limit)
- 本文 word count 1500-3000 (range 外は再生成 or skip)
- 既存記事との literal 重複 ≤ 20% (n-gram diff、 既存 `find_duplicate_sentence` 流用)
- player 名 言及 ≥ 5 回 (keyword density 担保、 ただし connector keyword で水増し禁止)

## 7. URL / featured_media / publish

| 項目 | 値 |
|---|---|
| URL slug | `seo/{player-slug}-monthly-{YYYYMM}` (例: `seo/okamoto-kazuma-monthly-202605`) |
| status | `publish` (SEO 記事は index 対象、 noindex 解除前提) |
| categories | 既存 `data-insight` / `選手情報` を流用、 加えて新 `SEO まとめ` category |
| tags | 該当 player tag + 「月間まとめ」 tag |
| featured_media | 該当 player の保存 eyecatch (438 rule = 元記事 → 保存写真 → team mark の 3 段 fallback 共通) |
| `<meta name="robots">` | `index, follow` (SEO 記事のみ override、 既存記事は noindex 維持) |
| schema.org | `Article` + `author` + `datePublished` (Google rich results 用) |

## 8. dedup

- 同 player × 同 月 の SEO 記事は 1 本のみ (URL slug = unique key)
- 再生成は手動 (`?regenerate=1` query) のみ、 cron では skip
- 過去月 の SEO 記事は更新せず、 月変わりで新 URL 生成

## 9. コスト想定

| 項目 | 月次 cost |
|---|---|
| Gemini API call | 10 player × 4 週 = 40 call/月 (本文 ~3000 token) ≈ ¥10-15/月 |
| Cloud Run Job | 週 1 回 × 10 player × 30s = 5 min/月 ≈ ¥0 (free tier 内) |
| GCS / Logging | 既存 bucket 流用、 ¥0 追加 |
| **合計** | **¥10-15/月** |

## 10. ロールアウト

| phase | 内容 | trigger |
|---|---|---|
| Phase 1 | 選手別 月間まとめ (本 spec scope) | ticket 443 user GO 後 |
| Phase 2 | 既存記事末尾に SEO 記事への internal link 注入 | Phase 1 で 1-2 ヶ月分 SEO 記事蓄積後 |
| Phase 3 | event-based aggregation (試合結果 / HR 一覧 等) | Phase 1 観察 + SEO 評価 後 |
| Phase 4+ | 既存 title/meta enrichment / keyword expansion 等 | 別 ticket、 user 判断 |

## 11. 評価指標

- Google Search Console 流入 (新 URL のみ、 28d trend)
- 月間 SEO 記事 publish 数 (target 40 本/月、 Phase 1)
- 内部 link CTR (Phase 2 以降)
- `post_gen_validate` fail 率 (≤ 10% 目標、 高ければ prompt 改善)

## 12. open question (ticket 443 §5 と共通)

1. yoshilover noindex 解除方針 (新 SEO 記事のみ vs 全 site)
2. コスト ¥10-15/月 妥当
3. 元記事 quote の引用 4 条件維持 vs paraphrase
4. 競合差別化方向 (data 集約で勝負)
5. オフシーズン 12-3 月 の scope

## 13. ベンチマーク: のもとけ (dnomotoke.com) 分析

CLAUDE.md ゴール「巨人版『のもとけ』 を MVP として成立させる」 を基点に、 2026-05-28 時点で `https://dnomotoke.com/` の構造を fetch 分析した。

### のもとけ の strategy (速報量産型)

- **記事 type**: 試合速報 / 選手コメント抽出 / 数値データ / 動画クリップ / 公示まとめ / 監督発言 Q&A
- **title format**: `[日付] [対戦]「試合型」【形式】結果` / `[選手名]「セリフ literal」` / 感動詞 (！！！) 多用で拡散性重視
- **公開頻度**: 1 日 15-25 本ペース、 試合中は 30 分-1 時間単位の reaktiver 速報
- **内部 link**: タグベース横展開 (選手単位)、 速報→結果→ハイライト動画 の段階化
- **構造化データ / schema.org**: 確認できず

### 真似るべき pattern

| pattern | のもとけ実装 | yoshilover への適用 |
|---|---|---|
| **セリフ抽出の反復** | 1 試合から 15+ 記事 (倍増ネタ化) | 既存 lane で既に同等 (rss_fetcher → draft body) ✓ |
| **タグベース関連記事** | 選手単位 tag で過去コメント自動接続 | Phase 2 で internal link block 注入 (selesai) |
| **速報→詳報 の段階化** | 「速報」→「結果」→「全打席」 3 記事で検索層化 | 既存 lane + 本 spec long-form で「速報→詳報→月間まとめ」 3 層化 |
| **title 冒頭に日付 + 対戦カード + 選手名** | 検索 volume 確保 | Phase 1 SEO title pattern に反映 (例: `2026年5月 岡本和真 まとめ`) |

### 避けるべき pattern (差別化ポイント)

| のもとけ の弱点 | yoshilover で差別化 |
|---|---|
| **ロング記事ゼロ** (深掘り 0) | **Phase 1 で長尾 query を独占** — 1500-3000 字 long-form で「ホームラン 一覧」「月間 まとめ」 query 拾う |
| **セリフ抽出過度化** で薄記事量産に見える | 既存 lane (rss_fetcher) の量は維持しつつ、 SEO lane は「month aggregation」 にして質で勝負 |
| **ニュース転載感** (報知/サンスポ間接引用が多くオリジナル弱) | data-insight ([[project_site_direction_data_focus]]) を素材に **独自 data 分析 section** を SEO 記事内に必ず含める |
| **構造化データなし** | Phase 1 から `<script type="application/ld+json">` で `Article` + `SportsEvent` schema 埋め込み (Google rich results 対応) |

### 結論 (差別化 strategy)

| 軸 | のもとけ | yoshilover (本 spec) |
|---|---|---|
| 量 | 1 日 15-25 本 (速報) | 既存 lane で 1 日 10-30 本維持、 SEO lane は 週 1 回 10 本追加 |
| 質 | 速報 / セリフ literal | **long-form 1500-3000 字 + data 分析 + schema.org** |
| 検索 戦略 | **鮮度勝負** (短期 traffic) | **長期資産 + 長尾 query** (月間まとめ / 選手別 history) |
| 内部 link | タグ依存 (散らばり) | Phase 2 で 速報→月間まとめ への構造化 link |

→ 「のもとけ が手薄な long-form + data 深掘り + 構造化」 で SEO 流入を補完、 速報部分は既存 lane で並走。

## 14. open question 追加 (のもとけ 分析 由来)

6. のもとけ 同等の **速報 X-post 連動** (試合中 15-30 分毎 publish) を 既存 x-post-mail-lane lane で代用する? それとも別 SEO 速報 lane 立てる?
7. 動画クリップ (の もとけ 「【動画】 ...」 type) は yoshilover scope 外で OK? それとも YouTube channel link 経由で対応?
8. 公示まとめ (「【公示】 5月26日のプロ野球公示」 type) は既存 lane で対応済 (sports_fetcher.py)、 SEO scope 拡張不要で OK?

---

**変更履歴**

- 2026-05-28: 初版 (ticket 443 起票と同時)
- 2026-05-28: のもとけ (dnomotoke.com) ベンチマーク section 追加 (user 指示「dnomotoke.com を参考に」)
