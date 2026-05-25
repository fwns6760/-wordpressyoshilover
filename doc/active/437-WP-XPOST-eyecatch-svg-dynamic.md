# 437 WP eyecatch + X-post 添付 用 SVG 画像 動的生成

## 1. ticket header

- **ticket id**: 437
- **status**: READY
- **owner**: Claude Code (2026-05-12 user 切替で Claude が dev + deploy 全権)
- **lane**: data-image
- **created**: 2026-05-25
- **updated**: 2026-05-25 (PM scope 拡張: 3 → 12 style + format auto-routing + quality gate)
- **priority**: P1
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/112
- **parent**: なし (新規 lane)
- **related**:
  - 423 (DATA-PUBLISH rules consolidated) — data 記事 publish の SoT
  - 430 (XPOST Source A voice) — voice text 側との並行
  - 436 (XPOST Top10 data diversity) — ranking 表との関連
  - 428 (XPOST branding requirements v2) — text post 側 branding と画像 branding の整合

## 2. purpose

WP data 記事 (ranking / spotlight / chart / scoreboard / standings 等) に **動的生成画像 (eyecatch + body 内画像)** を添付。 X-post でも同画像を添付し、 視覚 hook で インプ向上 + ブランド統一を狙う。

design 確定済 (2026-05-25 user 確認、白背景 + ジャイアンツカラー + brand guide lock):
- **背景**: 白 #ffffff (読みやすさ最優先、 オレンジ bg 禁止)
- **primary orange**: `#FF6F00` (vivid Giants orange) + gradient `#FF8C00 → #E65100`
- **黒**: `#000000` (Giants 第 2 色 / 締め / brand stripe)
- **金 ★ marker / hook line**: `#FFD700`
- **巨人ロゴ 不使用**
- **1080x1080** (X 正方形 post + WP eyecatch 兼用)
- **font**: 'Yu Gothic', 'Hiragino Sans', 'Noto Sans CJK JP'
- **数値強調**: font-weight 900 + 黒 stroke + tabular nums (桁揃え)
- **drop shadow**: 巨人 row / hero number に立体感 (SVG filter)
- **hook line**: 左上に金 1 行 (例: 「🔥 巨人選手 2 名 トップ 10 入り」、 インプ up)

**design sample 12 種 + variant** (Claude が user desktop に保存済): `C:\Users\fwns6\Desktop\yoshilover-x-design-samples\sample1-12 + sample9b_3crown.svg`

## 3. scope

| 項目 | 内容 |
|---|---|
| 対象 path | (a) `ranking_article_publisher` (WP data 記事) (b) `anomaly_article_publisher` (WP individual highlight) (c) postgame draft (d) lineup draft (e) `x_post_mail_lane` (X-post candidate) |
| 出力 | 1080x1080 PNG file (< 500KB) |
| 生成方式 | SVG template (Jinja2) + cairosvg → PNG 変換 |
| WP 添付 | `wp_client` で media upload → featured_media (eyecatch) 設定 |
| X 添付 | tweepy media upload + post media_ids 指定 (Phase 4) |
| データ source | 既存 publisher の rows / focus_player / metric を流用 |
| **template 数** | **12 base style + 3 variant** (3crown / 6crown / 1hero 等) |
| **format auto-routing** | データ条件 (crown_count / margin / player_count) で template を Python が自動選択。 LLM 呼び出し 0 |
| **選手 mix 方針** | **巨人多め** (= 巨人選手を上位 row で highlight)、 但し他球団も table に並べる (user 2026-05-25「巨人だけに頼らないでもいい」)。 = 現状の `find_all_giants_in_candidates` 経由 ranking と整合 |
| **中立画像方針 (2026-05-25 PM user 確定)** | 巨人選手が TOP 8 に居る時 → orange row + 金 ★ + 「🔥 巨人 N 名 トップ X 入り」 hook。 居ない時 → 純粋な TOP 8 中立 ranking + 「📊 セ・リーグ {metric} ranking」 hook、 **巨人下位を強制押し込まない**。 ML 不使用、 純 Python の if/else 判定。 重複は既存 dedup_gate / player_daily_cap=2 / 24h dedup で抑制済 (画像 layer は判定に触れない)。 |

## 4. acceptance criteria (品質 gate 10 項目)

- [ ] SVG template 忠実度: sample との diff 5% 以内 (色 / font size / layout)
- [ ] 日本語 font 描画: CJK 文字化け 0、 Yu Gothic / Noto Sans JP fallback verify
- [ ] 数値強調: font-weight 900 + 黒 stroke が PNG 化後も保持
- [ ] 巨人 row highlight: orange gradient + 金 ★ が thumbnail size でも判別可
- [ ] 画像 spec: 1080x1080 / < 500KB / sRGB
- [ ] 生成時間: 1 PNG あたり < 3 秒 (Cloud Run timeout 余裕)
- [ ] WP media upload: featured_media 設定後、 記事 preview で画像表示確認
- [ ] format auto-routing: crown_count / player_count 条件で正しい template が選ばれる
- [ ] 失敗 fallback: 画像生成失敗時も post 自体は publish される
- [ ] post-deploy 24h `gcloud billing` 実測 = ¥0 increase 確認 ([[project_2026_05_22_gemini_flash_cost_revert]] の教訓)

## 5. do not touch

- Source A Gemini prompt (430 ticket scope)
- ranking_article_publisher の publish loop logic
- Cloud Scheduler
- env / Secret
- 巨人ロゴ素材 (使わない、 user 明示)
- 既存 publisher の generation stage logic / dedup logic (画像生成は post-generation の attach のみ)

## 6. tests

| カテゴリ | 件数 (目安) | 内容 |
|---|---|---|
| SVG template render fixture | 12+ | 各 template に mock data 流し込み、 期待 string が含まれる確認 |
| cairosvg PNG 変換 fixture | 4 | 1080x1080 / < 500KB / 日本語 font 描画 / drop shadow 保持 |
| format router fixture | 6 | crown_count / player_count / margin 別に正しい template_key 返却 |
| WP media upload mock | 2 | featured_media id 設定 + 失敗時 fallback |
| X media upload mock | 2 | media_ids 添付 (Phase 4) + 失敗時 text only fallback |
| fallback fixture | 4 | 画像生成失敗 (font missing / cairosvg error / timeout / size 超) で post 自体は通る |
| integration smoke | 1 | 実 DB で 1 件 ranking 記事 draft 生成 → WP 管理画面で eyecatch 表示 |

## 7. STOP conditions

- cairosvg deploy で他 lib 衝突 (= image gen 部分のみ revert)
- X API Free tier で media attach が rate limit hit (Phase 4)
- font 描画事故 (日本語 font 不在で 文字化け)
- 1 post あたり 画像生成時間 が 5 秒超 (= Cloud Run timeout risk)
- 画像 file size が 500KB 超 (= X / WP 帯域圧迫)
- post-deploy 24h で `gcloud billing` 増額 観測 (= ¥0 前提の見積もりと乖離)

## 8. work log

- 2026-05-25 AM JST: user 発議「アイキャッチ入れるなら、 チケット作れる?」 で 437 起票 (commit `295bbea`)。 design 3 案は user 確認済。 sample SVG は user desktop 保存済。
- 2026-05-25 PM JST: user iteration で design + scope 大幅拡張:
  - **(1)** 「インプ向上 + 図種拡充」 → 試合速報 / 打順表 / 順位表 / 投手成績 / 月間集計 / @chikupn2896 系 (12 球団比較系) を追加 (3 → 8 sample)
  - **(2)** 「数値を強調」 → font-weight 900 + sizes +30-50% + 黒 stroke
  - **(3)** 「鮮やかな色 + ジャイアンツカラー」 → palette を `#F39800` → vivid `#FF6F00` + gradient + 金 ★ + 黒 stripe
  - **(4)** 「@chikupn2896 を意識」 → 12 球団比較 マトリクス系 4 案 追加 (8 → 12 sample)
  - **(5)** 「白背景 + ユーザビリティ + ブランド + インプ up」 → 全 sample 白 bg 化 + hook line + brand guide lock
  - **(6)** 「品質上げて」 → drop shadow filter / tabular nums / editorial metadata / 数値 size up
  - **(7)** 「もっと わかりやすく」 → 編集 metadata 削除 / 英文 header 削除 / 情報絞り / 3 秒理解設計
  - **(8)** 「format 切替できる?」 → data 条件で template 自動 routing 確認、 sample9b (3 crown variant) 追加
  - **(9)** 「Cloud Run コスト」 → ¥0 / 月 (free tier 0.8% 使用) 確認
  - **(10)** 「ticket 更新」 → 本 doc 更新 (scope 3 → 12 style + 4 phase + 品質 gate 10 項目)
- 2026-05-25 evening JST: Phase 1 (WP eyecatch) live deploy 完了:
  - **commits**: 1A `8c42f42` (base) / 1B `c0a19f8` (12 templates + router) / 1C `29b699c` (publisher 統合) / 1F `562c4d5` (slug dedup) / `158dbe8` (insight-nightly Dockerfile 修正) / `285d548` (.dockerignore !templates) / `33886d9` (doc 中立画像方針)
  - **images**: `yoshilover-fetcher:437-dedup-562c4d5` (revision `00645-kiy` 100% traffic) + `insight-nightly:latest-job` (build `f0c74916` SUCCESS)
  - **smoke**: insight-nightly execution `insight-nightly-jc7r6` 手動 fire → **3 件 PNG upload 成功** (media_id 71992 / 71995 / 71998、 filename `437eyc-{hash}.png` で slug dedup 動作確認)
  - **次セッション TODO**: (1) 24h billing verify (5/26 18:30 JST `gcloud billing`)、 (2) **Phase 2 = X-post media attach 実装** (user 2026-05-25 evening 明示「ポストのブランディングだから X に上げる」)、 (3) Phase 1 WP draft 群の eyecatch 視覚品質を WP 管理画面で確認

## 9. implementation plan (4 phase、 production quality release)

**Phase 1 framing は MVP ではなく「1 style だけ本番品質で先行 release」**。 各 Phase で同じ品質 gate (§4 10 項目) を全 style に通す。

### Phase 1 (commit 3 本直列、 ranking 1 style production-quality)

| commit | 内容 | 検証 |
|---|---|---|
| **A** | `requirements.txt` に `cairosvg` 追加 + `templates/x_post_ranking_table.svg` (sample1 Jinja2 化) + `src/x_post_image_gen.py` 新規 + unit test 4 件 | local pytest pass / cairosvg PNG 出力 1080x1080 < 500KB / 日本語 font 描画 OK |
| **B** | `ranking_article_publisher.py` 統合 + `wp_client.upload_media()` 拡張 + integration test (mock WP) | local pytest pass / mock WP media upload 成功 |
| **C** | `Dockerfile` に cairo system lib (`libcairo2`) 追加 + cloudbuild → `gcloud builds submit` → `gcloud run deploy` (no-traffic canary) → smoke → traffic 100% | canary で 1 件 draft 生成 → WP preview で eyecatch 表示確認 → revision tag 付与 |

Phase 1 終了 gate:
- 12 unit + 4 integration test 全 pass
- 実 DB で 1 件 ranking 記事 draft 生成、 WP 管理画面で eyecatch 表示
- 画像生成失敗 fallback 動作確認
- post-deploy 24h `gcloud billing` 実測 = ¥0 increase 確認
- 本 doc work_log に commit hash + revision + verify 結果記録

### Phase 2 (X-post media attach、 brand 本命、 user 2026-05-25 明示 GO 待ち)

**位置づけ**: WP eyecatch (Phase 1) は **副次成果**、 本来の目的は **X-post の画像添付** によるインプ向上 + brand 露出。 user 2026-05-25 evening 確認「ポストのブランディングだから X に上げる」。

実装内容:
- `tweepy.API.media_upload(png_bytes, file_type='image/png')` で X に upload → `media_id_string` 取得
- `create_tweet(text=..., media_ids=[media_id_string])` で post に添付
- `src/x_post_mail_lane.py` (X-post 候補配信 lane) で attach 呼び出し統合
- 失敗時は text-only fallback (rate limit / network error で X 投稿は止めない)
- 既存 `attach_ranking_image()` の PNG bytes を再利用 (新規生成不要、 CPU 増加 0)
- `templates/x_post_image_gen.py` は変更不要 (PNG 生成は既存 path、 添付先だけ追加)

cost (memory `reference_x_api_tier_free_writeonly.md` 整合):
- X API Free tier media upload: 1500/日まで free、 yoshilover 1 日数十件で余裕
- 追加 GCP コスト: ¥0 (Cloud Run / Network 既に無料枠内、 PNG 再利用で CPU 増加 0)
- LLM 呼び出し 0、 新 GCP service 不要

user 判断境界 (§11、 memory `feedback_publish_forward_must_check_gate_reason.md` 整合):
- X 自動投稿の画像添付解放は **user GO 必要** (SNS 投稿は user 判断 lane)
- live deploy 前に user 明示 GO 取得、 deploy 後は X-post lane が live で画像添付開始

実装規模: 1-2 時間。 commits 想定:
- **2A**: `src/x_post_image_attach_x.py` (or extend `x_post_image_gen.py`) 新規 helper `attach_x_post_image(twitter_client, png_bytes) → media_id_string` + tests
- **2B**: `src/x_post_mail_lane.py` 統合 + integration test (mock tweepy)
- **2C**: Cloud Run job (x-post-mail-lane) image rebuild + Job update + canary execute

### Phase 3 (5 template + format auto-routing、 旧 Phase 2)

- 追加 template: sample2 (player_spotlight) / sample4 (scoreboard) / sample6 (standings) / sample9 (6crown_grid) / sample9b (3crown_row) / sample10 (data_sheet)
- `src/x_post_image_router.py` 新規: `select_template(data) → style_key` (crown_count / player_count / margin で routing)
- `anomaly_article_publisher.py` / postgame builder 統合
- 同じ品質 gate (§4) を全 template に通す
- commit 3 本程度

### Phase 3 (残り 6 template + GCS cache)

- 追加 template: sample3 (chart_bars) / sample5 (lineup) / sample7 (pitcher_card) / sample8 (monthly_summary) / sample11 (spray_chart) / sample12 (12team_bar)
- GCS bucket cache: 重複 PNG 再利用 (key: `{style}_{data_hash}_{date}`)
- commit 2-3 本程度

### Phase 4 (X media attach + monitoring + A/B)

- `x_post_mail_lane.py` に tweepy media upload 統合 (Phase 4 は user GO 後、 X live post 不可触解除が前提)
- 画像生成失敗 alert (Cloud Logging metric → email)
- 画像 A/B test (color / template variant) — optional
- commit 2-3 本程度

## 10. user 判断境界 (§11 4 領域)

- **公開記事の削除 / 書き換え**: 該当なし (画像追加は append-only、 既存記事の本文書き換えなし)
- **X 投稿解放 / 新カテゴリ解放**: Phase 4 で X media attach 着手前に user GO 取得
- **MVP scope 拡張 / 縮小**: 本 doc の 4 phase scope 拡張は user 既 GO (2026-05-25 PM)
- **法務 / 著作権 / プライバシー / 金銭・外部 API 課金増**: 巨人ロゴ不使用 + 全 mock data / LLM 不使用 / Cloud Run 無料枠内 → 該当なし

Claude 自律実行範囲 (§3, §19): code/test/commit/push/cloudbuild/deploy 全 Claude 直接、 user 報告のみ。

## 11. 補足

- design sample 詳細: `C:\Users\fwns6\Desktop\yoshilover-x-design-samples\README.md` 参照 (brand guide / palette / publisher path 対応表)
- cost 見積もり: Cloud Run vCPU 0.8% / GCS 9% / Network 45% (全 free tier 内、 月 ¥0)
- format auto-routing 例: 岡本 6 冠時 → sample9 (3x2 grid) / 3 冠時 → sample9b (1x3 + その他 list) / 1 冠時 → sample2 (single hero card) / 0 冠時 → sample1 (ranking)
