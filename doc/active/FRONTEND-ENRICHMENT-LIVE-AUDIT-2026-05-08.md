# FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08

| field | value |
|---|---|
| ticket_id | FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08 |
| priority | P1(品質改善、5/8 PM 監査で発見、5/7 enrichment 作業の検証) |
| status | READY_FOR_AUDIT |
| owner | Claude (audit) → Claude/Codex (narrow fix) |
| lane | QA / FRONTEND |
| created | 2026-05-08 |
| doc_path | doc/active/FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08.md |
| origin | 5/8 PM session、user 「昨日のセッションは本当にできてるか怪しい」「もっと深く見て」 |
| cost | ¥0(audit + narrow code fix のみ、Cloud Run/Gemini/API 増加なし) |
| regression risk | 0(read-only audit + 既に live にない block を追加するだけの narrow fix) |

## 1. 背景

2026-05-07 の session で manual-intake / RSS pipeline に Phase 1-3 enrichment(ToC / 関連記事 / 順位表 / 次戦 / X embed / share / tag chip / AI badge / 4-CTA / JSON-LD)を入れた:

- `8bce3d6 NOMOTOKE-INTAKE-READER-UX-001` — R1 ToC + R3 read-time + R4 name-link + R6 tag chips
- `06dd58c NOMOTOKE-INTAKE-FRESH-INFO-001` — A〜F 全施策 + roster 全選手追加
- `c4d47b3 NOMOTOKE-INTAKE-NEXT-GAME-001 / STANDINGS-001 / ROSTER-PHASE-2` — 次戦 + 順位表
- `28f36e9 NOMOTOKE-INTAKE-N1234-001` — AI 不使用 badge + JSON-LD schema + 当日他試合 + シリーズ
- `e5208be NOMOTOKE-INTAKE-NOMOTOKE-MATCH-001` — X 投稿埋め込み + シェアボタン
- `927ac2c NOMOTOKE-RSS-PIPELINE-ENRICHMENT-001` — RSS 自動 pipeline にも適用

しかし 2026-05-08 PM の live post 監査で、**ほとんどのブロックが live に出てない**ことを発見。

## 2. 監査結果(2026-05-08 PM、直近 15 件)

```
id=64851 | nomotoke=Y, X_embed=Y                                   | 1321 chars | postgame
id=65044 | nomotoke=Y, CTA=Y                                       | 1238 chars | broadcast
id=65043 | nomotoke=N, related=Y, X=Y                              | 4674 chars | RSS Gemini
id=65037 | nomotoke=N, related=Y, next_game=Y, X=Y                 | 7448 chars | RSS Gemini
id=65034 | nomotoke=N, related=Y, X=Y                              | 4482 chars | RSS Gemini
id=64800 | nomotoke=Y, none                                        |  602 chars | postgame
id=64802 | nomotoke=Y, X=Y                                         | 1417 chars | postgame
id=65006 | nomotoke=Y, CTA=Y                                       | 1200 chars | broadcast
id=64988 | nomotoke=N, related=Y, X=Y                              | 4590 chars | RSS Gemini
id=64850 | nomotoke=Y, none                                        |  622 chars | postgame
id=64922 | nomotoke=N, none                                        |  287 chars | RSS thin (duplicate)
id=64923 | nomotoke=N, none                                        |  287 chars | RSS thin (duplicate)
id=64995 | nomotoke=N, related=Y, X=Y                              | 8451 chars | RSS Gemini
id=65004 | nomotoke=N, none                                        |  443 chars | RSS thin
id=65002 | nomotoke=N, none                                        |  489 chars | RSS thin
```

**集計**(15 件中):

| block | 出現数 | 期待 | gap |
|---|---|---|---|
| nomotoke-card- marker | 7 | 全 RSS でも | RSS path 未統合 |
| ToC | **0** | nomotoke-Y で全部 | 100% gap |
| 関連記事 | 5(全部 nomotoke-N の RSS Gemini) | nomotoke-Y にも | nomotoke-Y で 100% gap |
| 順位表 | **0** | nomotoke-Y で出るはず | 100% gap |
| 次戦 | 1 | nomotoke-Y postgame で出るはず | ほぼ全部 gap |
| X embed | 8 | 多くで | 53% カバー |
| シェアボタン | **0** | nomotoke-Y で全部 | 100% gap |
| タグチップ | **0** | nomotoke-Y で全部 | 100% gap |
| AI 不使用 badge | **0** | 全部 | 100% gap |
| 4-CTA | 2(broadcast のみ) | 全 single post で | 87% gap |
| JSON-LD schema | **0** | 全部 | 100% gap |

## 3. 仮説(なぜ live で出てないか)

### 仮説 A: 3 auto jobs(broadcast / lineup / postgame)の image が古い

3 auto jobs の image = `manual-intake-service:b432801`(5/8 朝 build)。

- `b432801` は **5/8 朝の commit**、5/7 の enrichment commit(8bce3d6 / 06dd58c / c4d47b3 / 28f36e9 / e5208be)を **含む**ハズ
- にもかかわらず block が出てない → **enrichment コードはあるが render 条件が合わない / call されてない**

### 仮説 B: enrichment の各 helper が早期 return している

`apply_rss_pipeline_enrichment` の中で各 `_build_*_block` が呼ばれてるが、return 条件で空文字を返している可能性:

- `_build_toc_block` → body の見出し数が 2 未満で skip?
- `_build_related_articles_block` → query 結果が空で skip?
- `_build_standings_block` → npb_standings cache がない / fetch fail で skip?
- `_build_next_game_block` → 次戦 fetch fail / 試合終了で skip?
- `_build_share_buttons_block` → 何らかの env / settings gate で skip?
- `_build_tag_chip_block` → roster 名が body にない場合 skip?
- `_build_jsonld_article_schema` → schema 生成自体に必要な field 不足で skip?

### 仮説 C: enrichment コードは走ってるが post-process で剥がれている

- WP `wp_kses` で `<aside>` / `<script type="application/ld+json">` などを strip?
- `<article-foot>` などのテーマ frame 内に押し込まれて front から見えない?

### 仮説 D: nomotoke-N (RSS Gemini) path で marker 不在のため enrichment 全 skip

(これは parent ticket MANUAL-INTAKE-QUALITY-PARITY で既出)

### 仮説 E: 3 auto jobs image を再 build しないと反映されない

`b432801` ≠ 全 enrichment 反映済み。`b432801` の git tree が enrichment commits を含むか確認必要。

## 4. scope(narrow audit + narrow fix)

### Phase A: 受動 audit(¥0、外部 fetch なし)

1. `manual-intake-service:b432801` image の git tree が enrichment commits を含むか確認
   - `git log --oneline b432801` で 8bce3d6 / 06dd58c / c4d47b3 / 28f36e9 / e5208be を含むか check
2. `manual-intake-service:d34072a`(現 service)で同じ確認
3. live post の HTML を 5 本サンプリング、各 enrichment helper の出力痕跡を grep
   - `nomotoke-toc__list` / `nomotoke-related-posts__list` / `nomotoke-standings__label` / `nomotoke-next-game__label` / `nomotoke-share-x` / `nomotoke-tag-chips__row` / `nomotoke-ai-badge` / `application/ld+json`
4. wp_kses の影響確認(WP REST 取得時に `<script>` / `<aside>` が strip されてるか)

### Phase B: 仮説 B の検証(¥0、unit test fixture)

各 `_build_*_block` の return 条件を unit test fixture で再現:
- 入力: title / summary / body の典型 sample
- 期待: 各 block の HTML 出力 or 空文字
- 実態: pytest fixture で実行、ログから skip 理由を抽出

### Phase C: narrow fix(¥0、render 条件緩和)

audit 結果から、reasonable な条件緩和や bug fix を narrow に入れる。例:
- `_build_toc_block` の見出し数 threshold を 2 → 1 に下げる
- `_build_standings_block` で cache fetch fail 時に inline fallback HTML を出す
- `_build_share_buttons_block` の gate 解除 / nomotoke-Y で必ず出すよう変更
- 等

### Phase D: 3 auto jobs に最新 image を反映(必要なら別 ticket)

`manual-intake-service:d34072a` を 3 auto jobs に redeploy(現 `b432801`)。これは separate ticket(image rebuild scope、user 同意境界)で扱う。**本 ticket では deploy しない**。

## 5. 不可触

- env / Secret / Scheduler 変更しない
- WP publish / X 投稿 触らない
- Gemini call / 外部 API call 増やさない
- 既存 enrichment block の render を **悪く**する変更はしない(改善方向のみ)
- 3 auto jobs の image rebuild + redeploy は本 ticket scope 外

## 6. 成功条件

| Phase | 完了条件 |
|---|---|
| A | enrichment 各 block の live 出現率を数値化、root cause 候補を 3 つ以上 narrow |
| B | 各 `_build_*_block` の skip 理由を unit test で再現、何が現実的に直せるか 5 つ以上 narrow |
| C | unit test green、5 件以上の live post sample で改善方向の差分確認(narrow fix の数 × 各で) |

## 7. 次セッション着手手順

1. Phase A から開始(read-only audit、Claude が直接 / Codex narrow 便でも可)
2. user に root cause 候補と narrow fix 案を提示
3. user 判断で Phase B + C を実施
4. Phase D が必要なら別 ticket 起票

## 8. 関連

- 親: `doc/active/MANUAL-INTAKE-QUALITY-PARITY-2026-05-08.md`(parity gap の上位 ticket)
- 関連 commit: 8bce3d6 / 06dd58c / c4d47b3 / 28f36e9 / e5208be / 927ac2c
- src: `src/tools/manual_intake.py` の `_build_*_block` 系、`apply_rss_pipeline_enrichment`
- live post sample: WP REST `/wp-json/wp/v2/posts?per_page=15`
