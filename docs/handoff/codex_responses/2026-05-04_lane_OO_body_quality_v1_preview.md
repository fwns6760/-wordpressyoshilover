# 2026-05-04 Lane OO body quality v1 preview

Method:

- fixture-based preview only
- no WP REST / publish / mail / scheduler / live trigger
- compared actual repo functions with flags OFF vs ON
- main functions used:
  - `src/rss_fetcher._rewrite_display_title_with_template()`
  - `src/rss_fetcher._apply_article_body_quality_sanitizer()`
  - `src/rss_fetcher._evaluate_post_gen_validate()`

Flags ON in preview:

- `ENABLE_FORBIDDEN_PHRASE_FILTER=1`
- `ENABLE_TITLE_GENERIC_COMPOUND_GUARD=1`
- `ENABLE_QUOTE_INTEGRITY_GUARD=1`
- `ENABLE_DUPLICATE_SENTENCE_GUARD=1`
- `ENABLE_ACTIVE_TEAM_MISMATCH_GUARD=1`

## Summary

| case | source URL | OFF result | ON result | flags hit | quality |
|---|---|---|---|---|---|
| `64432` | `https://twitter.com/sanspo_giants/status/2051101291485733322` | generic status title family | raw source title passthrough + review | `placeholder_body:empty_section` | `review_hold` |
| `64453` | `https://www.nikkansports.com/baseball/news/202605030000454.html` | publishable generic OB body | alumni/non-baseball review | `entity_mismatch:alumni_non_baseball_context` | `review_hold` |
| `64461` | `https://baseballking.jp/ns/694662/` | Blue Jays story rewritten into Giants return title | raw source title passthrough + review | `entity_mismatch:non_giants_team_prefix` | `review_hold` |
| `healthy` | `fixture://healthy_matsuura_emergency_relief` | clean postgame title/body | unchanged pass | none | `pass` |
| `grounding-strict` | `fixture://source_grounding_unverified_player` | repair body stays publishable | repair body forced to review | `source_grounding_unverified_entity` | `review_hold` |

## 64432

- source title:
  - `右アキレス腱炎からの復帰を目指す 投手がブルペン投球を実施`
- source URL:
  - `https://twitter.com/sanspo_giants/status/2051101291485733322`
- before title:
  - `選手、昇格・復帰 関連情報`
- after title:
  - `右アキレス腱炎からの復帰を目指す 投手がブルペン投球を実施`
- before body excerpt:
  - `【発信内容の要約】` empty
  - `【文脈と背景】 元記事の内容を確認中です。`
- after body excerpt:
  - `【投稿で出ていた内容】` empty
  - `【この話が出た流れ】 元記事の内容を確認中です。`
- flags:
  - OFF: pass
  - ON: `placeholder_body:empty_section`
- note:
  - incident row was `実施選手、昇格・復帰 関連情報`
  - current fixture reproduces the same generic-subject family and now routes it to review instead of keeping a publishable title

## 64453

- source title:
  - `元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘れるくらい」`
- source URL:
  - `https://www.nikkansports.com/baseball/news/202605030000454.html`
- before title:
  - raw-title fallback family
- after title:
  - raw-title fallback family
- before body excerpt:
  - `【ここに注目】 このコメントはファン必見です。`
- after body excerpt:
  - `【ここに注目】 このコメントは押さえておきたい内容です。`
- flags:
  - OFF: pass
  - ON: `entity_mismatch:alumni_non_baseball_context`
- quality:
  - non-baseball OB commentary is no longer treated as a normal Giants article candidate

## 64461

- source title:
  - `ブルージェイズ・岡本和真が3戦連発の9号2ラン 9回に反撃の一発放つも及ばず、勝率5割復帰お預け`
- source URL:
  - `https://baseballking.jp/ns/694662/`
- before title:
  - `ブルージェイズ・岡本和真、昇格・復帰 関連情報`
- after title:
  - `ブルージェイズ・岡本和真が3戦連発の9号2ラン 9回に反撃の一発放つも及ばず、勝率5…`
- before body excerpt:
  - recovery/notice body shape stayed publishable
- after body excerpt:
  - body text itself is not expanded
  - post-gen review stops the draft because raw source keeps a non-Giants active-team prefix
- flags:
  - OFF: pass
  - ON: `entity_mismatch:non_giants_team_prefix`

## healthy

- source title:
  - `巨人・松浦慶斗が緊急リリーフで無失点`
- source URL:
  - `fixture://healthy_matsuura_emergency_relief`
- before title:
  - `巨人阪神戦 松浦慶斗、試合での見せ場`
- after title:
  - same
- before body excerpt:
  - `【試合結果】 巨人が阪神に3-2で競り勝った。`
  - `【ハイライト】 松浦慶斗が緊急リリーフで流れを切った。`
- after body excerpt:
  - unchanged
- flags:
  - OFF: pass
  - ON: pass

## grounding-strict

- source title:
  - `巨人が阪神に3-2で勝利した`
- source URL:
  - `fixture://source_grounding_unverified_player`
- before repair excerpt:
  - `戸郷翔征が完投し、巨人が阪神に3-2で勝利した。`
- after repair excerpt:
  - unchanged text body
  - repair/numeric lane returns `source_grounding_unverified_entity`
- flags:
  - OFF: pass
  - ON: `source_grounding_unverified_entity`
- quality:
  - source にいない固有名詞を repair 経由で押し込む path を strict guard で止める

## No-new-fact check

- preview used source titles, fixture summaries, and direct post-process outputs only
- no branch added new player names, team names, numbers, or dates
- two contaminated cases (`64453`, `64461`) are stopped by review, not repaired with invented facts
- `64432` is also stopped at review because subject recovery is unsafe without explicit source support
