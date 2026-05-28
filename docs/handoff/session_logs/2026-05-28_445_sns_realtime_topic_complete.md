# 2026-05-28 — 445 SNS realtime topic 完了 + DISABLE_SOCIAL_NEWS_ARTICLES kill switch

## summary

巨人 SNS リアルタイム話題 page (Yahoo realtime 検索式) を 2 page 構成で実装、 deploy 完了。 翌日 (2026-05-29) は **observation 観察** + 未着手 follow-up の判断のみ。

## LIVE state (2026-05-28 20:23 JST)

- Cloud Run: `yoshilover-fetcher-00504-9hw` (image `disable-social-news-6609bae`、 100% traffic、 /health 200)
- env: `ENABLE_SNS_REALTIME_TOPIC=1` + `DISABLE_SOCIAL_NEWS_ARTICLES=1`
- 2 published page:
  - 一軍: <https://yoshilover.com/giants-sns-realtime-1gun/> (page_id=73959)
  - 二軍・三軍: <https://yoshilover.com/giants-sns-realtime-farm/> (page_id=73960)
- 自動 fire: 既存 fetcher Scheduler 相乗り、 10/13/17/21 JST × 4 回/日

## 達成 (本 session)

| feature | 状態 |
| --- | --- |
| 巨人専門 X 4 アカウント 24h 集約 (RSSHub 経由) | ✓ |
| 一軍 / 二軍三軍 page split + permanent URL | ✓ |
| トレンド section (全 136 名 aliases) + ranking chip | ✓ |
| 急上昇 marker (GCS state、 初日抑制) | ✓ |
| /data/ 内部リンク enrichment (444 連動) | ✓ |
| Giants brand design (hero / chip / card) | ✓ |
| 構造化 markup: CollectionPage + LiveBlogPosting + BreadcrumbList | ✓ |
| OGP / Twitter Card (excerpt 経由) | ✓ |
| sitemap 自動登録 (page-sitemap.xml) | ✓ |
| page type 採用で noindex 自動回避 | ✓ |
| 旧 per-X-post 記事化 kill switch (DISABLE_SOCIAL_NEWS_ARTICLES) | ✓ |
| 追加コスト ¥0 | ✓ |

## deploy 履歴 (7 commit / image / revision)

| commit | image / revision | 内容 |
| --- | --- | --- |
| `3811c4c` | doc only | spec + ticket + GH Issue #114 |
| `da588c8` | `sns-realtime-da588c8` / `00498-547` | impl 初版 (post type) |
| `7ba307d` | `sns-realtime-7ba307d` | permanent slug + 急上昇 + tag link |
| `7bed2dc` | `sns-realtime-7bed2dc` / `00500-b2b` | page split |
| `37f1c70` | `sns-realtime-37f1c70` / `00501-ksv` | post → page (noindex 自動回避) |
| `0d09e60` | `sns-realtime-0d09e60` / `00502-qdx` | Giants design + JSON-LD |
| `3cbe211` | `sns-realtime-3cbe211` / `00503-bxc` | A LiveBlog + B OGP + C /data/ link |
| `6609bae` | `disable-social-news-6609bae` / `00504-9hw` | DISABLE_SOCIAL_NEWS_ARTICLES kill switch (LIVE) |
| `3f7458f` | doc only | 仕様書 + ticket に kill switch 追記 |

## 翌日 (2026-05-29) の観察項目

### A. 自動 fire 動作確認 (高優先)
- **10:00 / 13:00 / 17:00 / 21:00 JST の 4 回**、 fetcher が自動で 2 page を update する
- Cloud Logging で確認:
  ```
  gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND textPayload:"sns_realtime_topic_result"' --limit 10 --freshness=1d --format='value(timestamp,textPayload)'
  ```
- 各 fire で `event=sns_realtime_topic_result, ran=true, results=[1gun, farm], save_counts_ok=true` が出るはず
- WP の 2 page の modified timestamp が 4 回更新されているか

### B. 急上昇 marker ↑+N badge の初動 (中優先)
- 10:00 fire 時点で 5/28 の GCS counts が前日として load される
- 5/29 のトレンド chip に ↑+N / ↓N badge が初めて表示される
- 確認: <https://yoshilover.com/giants-sns-realtime-1gun/> の chip に色つき delta が出てるか

### C. DISABLE_SOCIAL_NEWS_ARTICLES の効果検証 (中優先)
- 21:00 JST (今夜) の fire log で `event=social_news_sources_disabled, skipped_sources=15, remaining=32` 出るはず
- 翌日朝の draft / publish 結果で **新規 social_news 系 article がゼロ** なことを確認
  ```
  curl -s "https://yoshilover.com/wp-json/wp/v2/posts?after=2026-05-28T20:00:00&_fields=id,title,date&per_page=20" | python3 -m json.tool
  ```
- 旧 path で作られていた個別 X 投稿 article (例: 「【巨人公式X】〜」 タイトル) が出てこないか

### D. LiveBlogPosting rich snippet の Google indexing (低優先 / 数日後)
- Google Search Console で URL inspection 推奨 (2 URL を「インデックス登録をリクエスト」)
- 数日後に SERP で「LIVE」 badge 出るか観察 (Google 側の判断、 保証なし)

## 未着手 follow-up (別 ticket 候補、 user 判断)

| 項目 | scope | 工事 | 効果 |
| --- | --- | --- | --- |
| (D) ヨシラバー独自 commentary 挿入 | hero 直下に 100-200 字 編集部まとめ | 1.5h | E-E-A-T 強化、 Google content quality 評価 |
| (E) embed lazy load | IntersectionObserver で scroll で twitter widget load | 1h | Core Web Vitals LCP 改善 → ranking factor |
| 1軍 / 2軍 コーチ split | lineup data で per-team split | 2h | 分類精度向上 (現在は コーチ言及 全部 一軍) |
| 2軍3軍 公式 X 追加 | `TokyoGiantsFarm` 等 source 拡張 (存在確認必要) | 0.5h + 確認 | farm page の量増加 |
| 旧 social_news article cleanup | 既存 publish 済の per-X-post article を 410 にする | 別 ticket | SEO 整理 (現在 noindex なので低優先) |
| GSC URL inspection リクエスト | user 手動 | 5 min | 初回 crawl 加速 |

## 関連 doc / 必読 (2026-05-29 session 開始時)

1. **本 file** (2026-05-28 完了 record)
2. `mkdocs_docs/spec/sns-realtime-topic.md` (最新仕様)
3. `doc/active/445-SNS-realtime-topic-daily.md` (ticket、 status: LIVE_DEPLOYED_VERIFIED)
4. GH Issue #114
5. `doc/README.md` § 445 entry (priority board)
6. `doc/active/assignments.md` § 2026-05-28 session update

## 注意 (引き継ぎ忘れ防止)

- ==`AskUserQuestion` 等の 2 択質問は § §11 4 領域内のみ== ([[feedback_autonomous_deploy_no_2choice_2026_05_28]])
- ==仕様書執筆は 証拠 only==、 推測で埋めない ([[feedback_spec_doc_evidence_only_2026_05_27]])
- ==旧 73555 / 73558 / 73559 (post type) は trash 済==、 user 側で permanent delete 可
- ==env reset で kill switch 解除可==: `gcloud run services update yoshilover-fetcher --update-env-vars=DISABLE_SOCIAL_NEWS_ARTICLES=0`

## next session 推奨手順

1. 本 file を読む
2. `mkdocs_docs/spec/sns-realtime-topic.md` で仕様確認
3. Cloud Logging で 5/28 21:00 + 5/29 朝 10:00 fire 結果 verify (A + B + C)
4. WP の 2 page を browser でも視覚確認
5. 問題なければ follow-up (D, E, ...) の優先度を user に提示

## events

- 14:30 JST | session 開始 | user 要望 「SNS ページのコンテンツ増やしたい」 | 仕様確認
- 14:40 JST | spec / ticket / GH Issue 起票完了 (3811c4c) | 445 | mkdocs preview 確認
- 15:00 JST | impl 着手 GO | da588c8 (post type) | 23/23 unit tests PASS
- 15:31 JST | deploy 00498-547 | env ENABLE_SNS_REALTIME_TOPIC=1
- (中略) | 6 回の deploy iteration (permanent URL / page split / page type / design / SEO / kill switch)
- 20:23 JST | deploy 00504-9hw (LIVE) | DISABLE_SOCIAL_NEWS_ARTICLES=1 | kill switch 完了
- 20:40 JST | 仕様書 + ticket に kill switch 追記 (3f7458f) | 引き継ぎ準備
