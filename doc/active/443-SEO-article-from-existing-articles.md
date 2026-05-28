# 443 SEO 記事 — 既存記事素材から SEO 強化 long-form を生成

## 1. ticket header

- **ticket id**: 443
- **status**: DRAFT (user 仕様確定待ち)
- **owner**: Claude Code
- **lane**: SEO / aggregation publisher
- **created**: 2026-05-28
- **priority**: P2 (まず方針確定、 実装は user GO 後)
- **github_issue**: PENDING
- **related**:
  - `project_site_direction_data_focus.md` (memory) — データサイト方向
  - `feedback_publish_forward_must_check_gate_reason.md` (memory) — yoshilover noindex 前提
  - `project_seo_404_to_410_gone_response.md` (memory) — 5/15 404→410 移行で ブランド検索 authority 回復方針
  - `438-XPOST-brand-opinion-and-quote-images.md` — Pattern B 引用 path (素材は重複)
  - `423-DATA-PUBLISH-RULES-CONSOLIDATED.md` — data publish 集約 SoT
- **spec doc**: `mkdocs_docs/spec/seo-article-generation.md`

## 2. 背景

- yoshilover には 既 publish 記事 ~73,000+ post が蓄積 (data-insight / 試合結果 / 選手コメント / column / digest 等)
- 個別記事は 検索流入が薄い (single-topic / 短文 / 同 source 媒体記事と競合)
- **既存記事を素材に SEO 強化 long-form (aggregation / 主題別まとめ) を生成**することで:
  - 検索 query (「岡本和真 ホームラン 一覧」「巨人 5月 試合結果」「戸郷翔征 防御率 推移」 等) に hit する long-form を充足
  - 内部 link で既存記事への流入経路を増やす
  - 巨人データサイト方向 ([[project_site_direction_data_focus]]) に整合
- 競合: のもとけ / 報知 / サンスポ等の検索結果。 yoshilover は noindex 前提 ([[feedback_publish_forward_must_check_gate_reason]]) のため、 まず **noindex 解除の user 判断** が前提

## 3. 案 (5 path)

| 案 | 内容 | コスト | SEO 効果 | 副作用 |
|---|---|---|---|---|
| A. **aggregation long-form** | 既存記事を主題別 (選手 × 期間 × event) で clustering → LLM で long-form 1 本生成 | Gemini 1 call/article、 中 | 高 (long-form は長尾 query に強い) | 既存記事との内部 dup 注意 |
| B. **title/meta enrichment** | 既存 publish 記事の title / meta description を SEO 最適化で書き換え | LLM 1 call/article × 大量、 高 | 中 (既存 indexed 記事の流入改善) | 大量 mutation = 既存 ranking 動揺 risk |
| C. **internal link injection** | 既存記事末尾に「関連記事」 link block を inject | LLM 不要 (related lookup のみ)、 低 | 中 (内部 PageRank 分散) | display 改変 = frontend テスト必須 |
| D. **keyword expansion (本文増強)** | 既存記事本文に関連 keyword paragraph を追加 | LLM 1 call/article × 大量、 高 | 中-高 (keyword density 向上) | 本文 dup penalty、 user の元意図 ずれ risk |
| E. **新規 SEO 記事 series** | keyword 起点で全く新規の long-form 生成 (既存記事は素材 reference のみ) | Gemini 多 call、 高 | 高 (新 URL で query 拡張) | scope 拡大、 既存記事との関係 微妙 |

## 4. 推奨 phase plan

**前提**: yoshilover の noindex 解除 (user 判断、 §11 領域 [SEO] に該当) が completed である / 解除して構わない方針が確定済

### Phase 1 (MVP): 案 A の限定 scope = 「選手別 月間まとめ」

- **対象**: 巨人 active player 上位 10 名 (打者 5 + 投手 5)
- **頻度**: 週 1 回 (週末日曜 21:00 JST)
- **素材**: 過去 7-30 日の 既存記事 (subject = 該当 player)
- **生成内容**: long-form 1500-3000 字、 構成 = 概要 + 試合別 highlight + 数字 summary + 関連記事 link block
- **URL pattern**: `yoshilover.com/seo/<player-slug>-monthly-<YYYYMM>`
- **featured_media**: 該当 player の保存 eyecatch (rule = [[project_437_phase1_live_phase2_xpost_pending]] と共通)
- **noindex**: 解除 (新 SEO 記事のみ index 対象、 既存記事は noindex 維持)
- **生成 lane**: 新 Cloud Run Job `seo-article-publisher` (Schedule: `0 21 * * 0` JST)
- **品質 gate**: 既存 `post_gen_validate` を流用、 fail 軸は draft 落とし

### Phase 2: 案 C (internal link block) を全既存記事に soft inject

- 既存 publish 記事末尾に「関連 SEO 記事」 link block を inject (Phase 1 で生成した SEO 記事 へ流入経路)
- LLM 不要 (player tag 検索 + 同一 player の Phase 1 SEO 記事を関連表示)
- 全 73,000 post 一括書き換え = WP REST batch、 1 回限り、 idempotent

### Phase 3: 案 A 拡張 = 「event-based aggregation」

- 「試合結果 まとめ」「ホームラン 一覧」「サヨナラ ヒット 一覧」 等 event 軸の long-form
- 頻度: 月 1 回

### Phase 4 以降 (user 判断後): 案 B (既存 title/meta 一括書き換え)、 案 D, E は scope 拡大要相談

## 5. open question (user 判断)

1. **noindex 解除**: yoshilover SEO 記事のみ index 解除する方針で OK?  全 site index 解除 vs 新 SEO 記事のみ index で URL 分離する path どっち?
2. **コスト**: Phase 1 で月 4 週 × 10 player = 40 long-form/月 = Gemini 40 call/月。  Gemini 3.1 Flash Lite で ¥10 程度想定、 OK?
3. **元記事の扱い**: SEO 記事に元記事内容を quote する場合、 引用 4 条件 (出典明記 / 主従関係 / 必要性 / 改変なし) 維持できる?  逆に paraphrase で済ます方が安全?
4. **competitor 比較**: のもとけ / 報知の SEO 戦略を真似る範囲。 のもとけは独自 column 系で勝負、 yoshilover は data 集約で差別化が方針 ([[project_site_direction_data_focus]]) で OK?
5. **公開 timing**: Phase 1 を試合シーズン中 (5月-10月) のみ、 オフシーズンは別 scope?

## 6. 触らない範囲

- 既存記事の本文 (Phase 2 の link block inject 以外、 本文 mutation なし)
- 既存記事の title / meta (Phase 4 以降の user 判断後のみ)
- publish-notice / x-post-mail-lane / fetcher / data-insight 既存 lane
- WP frontend display
- featured_media rule (元記事 → 保存選手写真 → team mark の 3 段 fallback 維持)

## 7. のもとけ (dnomotoke.com) benchmark 反映

2026-05-28 user 指示「dnomotoke.com を参考に」 で実 fetch 分析、 spec doc §13 に詳細追記。 要約:

- **のもとけ strategy** = 速報量産型 (1 日 15-25 本)、 セリフ抽出 / 動画 / 公示 / 監督発言、 long-form ゼロ、 構造化データ未対応
- **真似る pattern**: セリフ抽出反復 / タグベース関連 / 速報→詳報の段階化 / title 冒頭に日付+対戦+選手名
- **避ける pattern** = yoshilover の差別化機会:
  - ロング記事ゼロ → Phase 1 long-form で長尾 query 独占
  - セリフ抽出過度化 → SEO lane は質 (1500-3000 字 + data 分析) で勝負
  - ニュース転載感 → data-insight 結果を必ず内包
  - 構造化データなし → schema.org + JSON-LD で rich results 対応
- **差別化 strategy**: 「速報」 は既存 lane で 1 日 10-30 本維持、 「長期資産」 を SEO lane で週 10 本追加

## 8. next action

- (user 判断) §5 open question 5 件 + 追加 3 件 (動画 / 公示 / 速報 X-post 連動 — spec §14)
- (Claude 自律) ticket DRAFT lock 後、 spec doc [[seo-article-generation]] 詳細化、 implementation plan は別 ticket
