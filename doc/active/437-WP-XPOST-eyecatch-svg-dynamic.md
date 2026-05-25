# 437 WP eyecatch + X-post 添付 用 SVG 画像 動的生成

## 1. ticket header

- **ticket id**: 437
- **status**: READY
- **owner**: Claude Code (2026-05-12 user 切替で Claude が dev + deploy 全権)
- **lane**: data-image
- **created**: 2026-05-25
- **priority**: P1
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/112
- **parent**: なし (新規 lane)
- **related**:
  - 423 (DATA-PUBLISH rules consolidated) — data 記事 publish の SoT
  - 430 (XPOST Source A voice) — voice text 側との並行
  - 436 (XPOST Top10 data diversity) — ranking 表との関連

## 2. purpose

WP data 記事 (ranking / spotlight / chart) に **動的生成画像 (eyecatch + body 内画像)** を添付。 X-post でも同画像を添付し、 視覚 hook で インプ向上 + ブランド統一を狙う。

design 確定済 (2026-05-25 user 確認):
- 配色: 白 bg + orange (#F39800) accent + 黒線
- 巨人ロゴ 不使用
- 1080x1080 (X 正方形 post + WP eyecatch)
- 3 style:
  - (1) ranking table — TOP 10 表、 巨人 row を orange highlight
  - (2) player spotlight — 1 選手 大数字 + 順位 + 前期比
  - (3) chart bars — 試合推移 / trend

design sample: `/mnt/c/Users/fwns6/Desktop/yoshilover-x-design-samples/sample[1-3]_*.svg` (Claude が user desktop に保存済)

## 3. scope

| 項目 | 内容 |
|---|---|
| 対象 path | (a) ranking_article_publisher (WP data 記事) (b) anomaly_article_publisher (WP individual highlight) (c) x_post_mail_lane (X-post candidate) |
| 出力 | 1080x1080 PNG file |
| 生成方式 | SVG template (Jinja2 / f-string) + cairosvg → PNG 変換 |
| WP 添付 | wp_client で media upload → featured_media (eyecatch) 設定 |
| X 添付 | tweepy media upload + post media_ids 指定 |
| データ source | 既存 ranking_article_publisher / anomaly_article_publisher の rows / focus_player / metric を流用 |
| **選手 mix 方針** | **巨人多め (= 巨人選手を上位 row で highlight)、 但し他球団も table に並べる** (user 2026-05-25 確定「巨人だけに頼らないでもいい」)。 = 現状の find_all_giants_in_candidates 経由 ranking と整合 |

## 4. acceptance criteria

- ranking 表 SVG template に DB data を流し込んで PNG 生成、 WP draft に eyecatch 設定できる
- X-post に同 PNG を添付できる (X API Free tier 内で動作)
- 巨人 row が orange highlight + 白文字で出る、 他球団 row は白 bg + 黒文字
- 画像生成失敗時は post 自体は publish される (image なし fallback)
- 画像 file は GCS bucket に保存、 重複生成回避 (= 同 metric × scope × date は cache)

## 5. do not touch

- Source A Gemini prompt (430 ticket scope)
- ranking_article_publisher の publish loop logic (今日 deploy 済の改修維持)
- Cloud Scheduler
- env / Secret
- 巨人ロゴ素材 (使わない、 user 明示)

## 6. tests

- SVG template render fixture: 巨人選手 1-2 名 highlight 確認
- cairosvg PNG 変換 fixture: 1080x1080 出力サイズ確認
- WP media upload mock: featured_media id 設定確認
- X media upload mock: media_ids 添付確認
- fallback fixture: 画像生成失敗時 post 自体は通る

## 7. STOP conditions

- cairosvg deploy で他 lib 衝突 (= image gen 部分のみ revert)
- X API Free tier で media attach が rate limit hit
- font 描画事故 (日本語 font 不在で 文字化け)
- 1 post あたり 画像生成時間 が 10 秒超 (= Cloud Run timeout risk)
- 画像 file size が 5MB 超 (= X / WP の制限)

## 8. work log

- 2026-05-25 JST: user 発議「アイキャッチ入れるなら、 チケット作れる?」 で 437 起票。 design 3 案は user 確認済 (背景白 + orange + 黒線、 巨人ロゴなし)。 sample SVG は user desktop 保存済 (`yoshilover-x-design-samples/`)。

## 9. implementation plan (MVP → 段階)

### Phase 1 (MVP、 1 commit)

- `src/x_post_image_gen.py` 新規:
  - `generate_ranking_table_png(rows, metric, scope, focus_players) → png_bytes`
  - `generate_player_spotlight_png(player, metric, value, rank) → png_bytes`
  - `generate_chart_bars_png(games, date_range) → png_bytes`
- SVG template は `templates/x_post_*.svg` (Jinja2)
- `requirements.txt` に `cairosvg` 追加 (lightweight)
- WP integration: `wp_client.create_post()` に `featured_media_id` 渡す path 追加 (既存 media upload は 416-eyecatch / 067-068 ticket 関連で済み の場合 流用)
- ranking 1 path だけ MVP fire (sample1 ranking table)

### Phase 2 (Phase 1 観察後)

- spotlight (sample2) を anomaly publisher path に
- chart (sample3) を 試合後 catchup post に
- X-post 側 (x_post_mail_lane) にも image 添付

### Phase 3 (改善)

- font 改善 (日本語 font 同梱)
- 画像 cache (GCS bucket)
- 画像 A/B test (orange vs 別配色)

## 10. user 判断境界 (今 ticket 内で発生し得るもの)

- §11 4 領域:
  - 公開記事の削除 / 書き換え → 該当なし
  - X 投稿解放 → image 添付は既存 X-post path 内、 解放枠は不変
  - MVP scope 拡張 → image 追加自体は scope 拡張、 user 既 GO
  - 法務 / 著作権 → 巨人ロゴ不使用 + 全 mock data → 該当なし
- Claude 自律実行範囲 (§3, §19): code/test/commit/push/cloudbuild/deploy 全 Claude 直接、 user 報告のみ
