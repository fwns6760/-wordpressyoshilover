# 2026-05-14 evening session handoff — 344-INGEST YouTube + 67319 / 67262 / mail unpublish + 残課題

**作成**: 2026-05-14 PM 後半 (本日 3 つ目の handoff、`_pm_336qa_chain_handoff.md` の続編)
**前任**: Claude Code (本 session、user 自律 GO mandate)
**次セッションへ**: 朝 06:00 fire 後の自然 verify + stale content-date skip 実装 + 67252 multi-player 設計 + 67372/67375 cross-family dedup 検討

---

## 1. 本 session 後半で完了した production 反映 (commit chain)

| commit | image / target | rev | tag |
|---|---|---|---|
| `e3d1f22` | yoshilover-fetcher | `00387-67x` | `r2-67262-e3d1f22` (Pattern R2 67262 fix) |
| `6bb2ebc` | yoshilover-fetcher | `00386-fp4` | `mlb-skip-6bb2ebc` (大谷 skip) |
| `5fa899a` ... `81223aa` | yoshilover-fetcher | `00388-r6p` | `yt-344-61b3ed5` (344-INGEST Phase 1a 7 commits) |
| `b2ee45c` | yoshilover-fetcher | `00389-5t6` | `fix67319-b2ee45c` (Pattern A fact-only / announcement guard) |
| `0c7d43b` | yoshilover-fetcher | `00390-tk8` | `unpublish-0c7d43b` (/unpublish endpoint) |
| `0c7d43b` | publish-notice (Cloud Run job) | image 更新 | mail HTML に「🚫 非公開にする」button |

---

## 2. 主要 feature 一覧

### 2-A. 344-INGEST Phase 1a (YouTube 字幕→draft、ただし policy flip で auto-publish + title prefix)

- 既存 11 YouTube ch (公式 1 + メディア 2 + 巨人 OB 8) で動作
- title filter (巨人 keyword + 現役巨人選手 + 元巨人 OB) で巨人 relevance 判定
- youtube-transcript-api で公開字幕を pull、本文末尾に「📺 字幕抜粋」section (600字 + 出典 + embed)
- title 先頭に「【YouTube】」prefix で mail / WP admin で識別容易
- LLM 不使用、cost ¥0/月

### 2-B. Mail 1-click 非公開 button (新規 user request)

- publish-notice mail HTML に「🚫 非公開にする」button 追加
- click → yoshilover-fetcher /unpublish endpoint → HMAC token 検証 → WP REST status=draft
- security: HMAC-SHA256(post_id, secret)、1 token 1 post 専用、推測不可
- secret: env `UNPUBLISH_TOKEN_SECRET` で override 可、未設定時は default constant
- WP guard 整合: `ENABLE_WP_PUBLISHED_REVERT_GUARD=1` ON だと block、503 + 説明返答

### 2-C. 67319 fix (Pattern A fact-only / announcement guard)

- 「グッズ販売告知」記事が `坂本勇人「通算300号本塁打」` と誤 title 化される問題
- `_FACT_ONLY_QUOTE_PATTERNS` (9 regex): `通算\d+号本塁打` / `\d+号サヨナラHR` / `サヨナラ系` / `完封` / `完投` 等
- `_ANNOUNCEMENT_KEYWORDS` (12 entries): `記念グッズ` / `販売開始` / `GIANTS STORE` 等
- 検出時 Pattern A skip → 別 pattern (B/F 等) に fall-through、記事 publish 維持

### 2-D. 67262 fix (Pattern R2、`、` separator + 任意 descriptor + を 任意)

- 反応 pattern が「subject、target の fact verb 「q1」「q2」」型を取り損ねていた問題
- 既存 R に R2 variant 追加、output 形式は `[A]が[B]の[fact]を[verb]「q1」「q2」` に正規化

### 2-E. 大谷 skip (非元巨人 MLB primary subject)

- 大谷翔平 / 山本由伸 / ダルビッシュ 等 13 名 + 元巨人 OB allowlist (菅野/岡本)
- entity gate 後段に skip 配線

---

## 3. 累計統計

- session 後半 commits: 約 15 (前半 13 + 後半 残)
- builds: 約 9 SUCCESS
- deploys: yoshilover-fetcher revs 00386-fp4 → 00390-tk8 + publish-notice job image 更新
- pytest: baseline 維持、累計新規 test +120 case 程度、0 regression
- LLM call 追加: **0 件** (literal extraction / regex / pure rule-based のみ)
- forward-only: 既存 published 記事の遡及修正 0 件

---

## 4. 残課題 (next session で着手判断)

### 4-A. stale content-date skip (新規、67369/67366 事例から)

- source RSS 配信は今朝でも、内容が前夜 / 前日 ならば skip
- memory: `feedback_stale_content_date_skip_required` (carry over 用)
- 実装規模: narrow regex 30-45 分

### 4-B. 67372/67375 cross-family same-event dedup

- 異媒体 2 社 (東スポ + スポニチ) が同 player + 同 event を翌朝配信 → 両方 publish
- 既存 #18 は same-family 限定、digest #22 は 3+ family 必要、2 family 時の dedup gap
- 案: source priority (報知 > 日刊 > スポニチ > サンスポ > デイリー > 東スポ) で上位 keep
- 実装規模: 30 分、ただし over-skip risk あり (event token specificity 注意)

### 4-C. 67252 multi-player title pattern

- 3+ 選手 postgame で `巨人戦 当日カードの試合前情報` generic fallback が誤発火
- 専用 multi-player template (例: `[event]に[N]選手貢献 [選手列挙]`) の設計が必要
- 実装規模: 中、別 ticket 起票推奨

### 4-D. 344-INGEST Phase 1b (26 ch 追加)

- `youtube_ob_sources.json` に 古田/里崎/田尾/片岡/高木豊/五十嵐 等 26 ch 段階追加
- channel_id verify 必要 (WebSearch ベース or user 提供)
- `max_age_days=2 / article_limit=5` 抑制 start で観察ベース

### 4-E. 朝 06:00 fire 後の本セッション fix の自然 verify

- `youtube_caption_section_appended` log
- `youtube_title_filter_skip` log
- `non_giants_mlb_primary_subject_skip` log
- `digest_hochi_excerpt_populated` log
- 67262 / 67319 fix の実 fire title 確認
- 1-click 非公開 button が mail で表示されるか (publish-notice 次 fire 後)

---

## 5. silent gap / 未 verify

| gap | timing |
|---|---|
| /unpublish endpoint の実 click 動作 (WP REST 経由 status=draft) | publish-notice 次 fire 後の mail で button click test |
| 344-INGEST 字幕 fetch の rate limit / IP block | YouTube 自然 fetch 後の log 観察 |
| 67319 fix が新規 announcement source で正しく動作 | 公式 X 次 グッズ告知 自然発火 |
| stale content-date 新 rule の実装 (本 session 未着手) | 別 session impl |

---

## 6. 触らないでほしいもの

- 本 session deploy 済 5 image (`e3d1f22` / `6bb2ebc` / `61b3ed5` / `b2ee45c` / `0c7d43b`) を user 確認なしに rollback しない
- `UNPUBLISH_TOKEN_SECRET` env を勝手に Secret Manager 登録しない (default constant でも動作、user 任意で強化)
- `ENABLE_WP_PUBLISHED_REVERT_GUARD` env (現 OFF と推定) を ON にすると mail 1-click 非公開が block される、現状維持
- master branch への direct push なし (`hotfix-eyecatch-hashtag` branch 維持)

---

## 7. 次 session 開始時の必読 (優先順)

1. 本 handoff doc
2. `2026-05-14_pm_336qa_chain_handoff.md` (本日 PM 前半)
3. `2026-05-14_session_handoff_343_INSIGHT_007_LIVE.md` (並走 session、INSIGHT chain LIVE)
4. `CLAUDE.md` § 11 (user 判断境界) / § 18 (yoshilover 不変制約)
5. memory: `feedback_ai_top_failure_modes_meta_rule.md` (全 claim 直前の 3 self-check)
6. memory: `feedback_stale_content_date_skip_required.md` (本 session 終盤起票の新 rule)
7. memory: `project_youtube_channel_expansion_candidates_2026_05_14.md` (Phase 1b 26 ch 候補)

---

## 8. 次 session 推奨アクション (優先順)

| Priority | task | 規模 |
|---|---|---|
| **1 (highest)** | 朝 fire 後の log + 公開記事観察 (本 session 多 fix の effective verify) | 1-2h read-only |
| 2 | stale content-date skip impl (67369/67366 系) | 30-45 分 narrow |
| 3 | 67372/67375 cross-family dedup 検討 + impl | 30-60 分 |
| 4 | 344-INGEST Phase 1b (26 ch 段階追加) | 1-2h (channel_id verify 含む) |
| 5 | 67252 multi-player title pattern 設計 | 中、別 ticket |

---

## 9. session 終わり時 GH Issue 状態

- #21 OPEN (342-INSIGHT、impl 残、data 蓄積 7-21 日待ち)
- #24 OPEN (344-INGEST、Phase 1a LIVE 完了、Phase 1b 残)
- #25 OPEN (DATA-INSIGHT-continuous、別 session 起票、user GO 待ち)

---

written by Claude Code, 2026-05-14 evening JST
