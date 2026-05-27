# 438 X-post コメント候補に画像添付 (brand_opinion + brand_quote)

## 1. ticket header

- **ticket id**: 438
- **status**: IN_FLIGHT
- **owner**: Claude Code (2026-05-12 user 切替で Claude が dev + deploy 全権)
- **lane**: x-post-image
- **created**: 2026-05-27
- **updated**: 2026-05-27
- **priority**: P1
- **github_issue**: (起票後追記)
- **parent**: なし (新規 lane)
- **related**:
  - 437 (WP eyecatch + X-post 添付 SVG 動的生成) — 別系統 (ranking 系)、 本 ticket は comment 系
  - 430 (XPOST Source A voice validator) — ヨシラバー voice text の供給元
  - 428 (XPOST branding requirements v2) — text post 側 branding 仕様
  - 5/27 完了 commit `776252d` — 監督・コーチ member gate 拡張 (本 ticket の前提)

## 2. purpose

x-post-mail-lane の comment 系候補 (GEMMA_BRANDING / build_x_post_from_article_info path) に **画像を毎回添付** し X 投稿時の impression を boost する。

user 仕様 (2026-05-27 lock):

- 候補生成 path は既存 (毎時 x-post-mail-flush + game lane) に **毎回 image gen を内包**
- **新規 Cloud Scheduler / Cloud Run job は作らない** (¥10/月/job 削減 lock)
- 既存 x-post-mail-lane image rebuild + 切替で deploy
- 既存 share-x-cand 経路 (Web Share API) でそのまま投稿可

## 3. scope

### 3.1 Pattern A (brand_opinion、 私の意見)

| 項目 | 内容 |
|---|---|
| 候補 metric | GEMMA_BRANDING (既存) |
| 画像 base | 反応元 article の `og:image` 1 枚のみ (HTML から `<meta property="og:image">` 抽出) |
| サイズ | source native aspect / size をそのまま使用、 強制 crop なし。 X media spec (5MB / 8192px) 超過時のみ等比縮小 |
| 画像 overlay | **なし** (写真そのまま、 text 焼き込み一切なし) |
| post text 本文 | 既存 `_SYSTEM_PROMPT_YOSHILOVER` 生成の voice text (180-280 字、 短文連投 2-4 行) |
| URL/ハッシュタグ/媒体名 | post text に含めない (現 hard rule 維持) |
| alt text | 「引用元: {媒体名}」 (出典担保、 visible 要素なし) |

### 3.2 Pattern B (brand_quote、 選手・コーチ literal 引用)

| 項目 | 内容 |
|---|---|
| 候補 metric | GEMMA_BRANDING (Pattern A と同じ pool、 B 成立時優先) |
| 画像 base | 引用元 article の `og:image` 1 枚のみ |
| サイズ | Pattern A と同 |
| 画像 overlay | **人物名 + 「literal 60-180 字 long quote」** を写真下半分に焼き込み (white text + drop shadow / stroke、 枠 / brand mark / 引用元 一切なし) |
| post text 本文 | 空 または 人物名のみ (image 側が主、 重複回避) |
| URL/ハッシュタグ/媒体名 | post text に含めない |
| alt text | 「引用元: {媒体名}」 |
| fallback | Pattern B 成立条件 (quote ≥ 60 字 / 発言者 verified member) を満たさない時は Pattern A へフォールバック |

### 3.3 共通仕様

- 出力 format: PNG (1.5MB 程度上限、 JPEG fallback 可)
- GCS bucket: 既存 `baseballsite-yoshilover-insight` を再利用 (新 bucket 不要)
- GCS path prefix: `x-post-images/{date}/{hash}.png`
- 既存 ranking PNG (437 Phase 1) と並列、 干渉なし
- post text は **URL / ハッシュタグ / 媒体名 を含めない hard rule 維持** (`_SYSTEM_PROMPT_YOSHILOVER` の制約)
- 出典は alt text のみで担保

## 4. 触らない範囲

- env / Secret Manager / Cloud Scheduler / traffic
- 既存 ranking PNG 生成 (437 Phase 1) / WP eyecatch 経路
- draft_body_editor / publish-notice / guarded-publish / insight-nightly / quality-* / WP 側設定
- 5/27 完了の member gate (`_load_giants_member_aliases` / `_is_verified_full_giants_member_name`)
- NEWS_OPINION / COMMENT_DB / FAN_VOICE 候補 (画像なしのまま、 GEMMA_BRANDING のみ画像化)
- 既存 `_SYSTEM_PROMPT_YOSHILOVER` voice prompt (改変禁止)
- Cloud Scheduler job 一切追加禁止 (¥10/月/job 削減 lock)

## 5. Phase 分け

### Phase 1: brand_opinion (Pattern A) 単体

scope:
- og:image fetch helper (HTML → meta property og:image 抽出、 timeout 5s)
- `x_post_image_gen_v2.py` に `brand_opinion_card` template 追加
- `build_gemma_branding_candidate` / `build_x_post_from_article_info` の Candidate に `image_bytes` / `image_url` / `alt_text` を載せる
- GCS upload (既存 bucket 再利用)
- alt text passing (share-x-cand handler 側 / X media_upload alt_text 設定)

acceptance:
- 既存 pytest 全 pass
- Pattern A 候補がメールで画像付きで届く
- alt text に「引用元: {媒体名}」 が入る
- 課金 ¥0 (24h verify)

### Phase 2: brand_quote (Pattern B)

scope:
- long quote extractor (source HTML body / RSS summary から 60-180 字「」 quote を抽出、 同一発言者連続なら連結、 truncate 時末尾「…」 禁止)
- 発言者特定 (「（発言者名）」 + roster member gate verify)
- `brand_quote_card` template
- Pattern B 成立判定 + Pattern A フォールバック

acceptance:
- Phase 1 と同条件
- Pattern B 成立記事で 「発言者名「長 quote」」 形式の画像が生成される
- 不成立記事は Pattern A にフォールバック (skip しない)

## 6. risk / open question

- **risk**: 報知 / サンスポ等の媒体写真直接 attach は user 判断 (§11 著作権) で OK 判定済。 alt text に 引用元 を必ず入れることで 引用 4 条件「出典明記」 を最低限担保
- **open**: og:image が無い article の扱い → Phase 1 で「og:image なし → 候補自体 skip」 (簡易) で start、 必要なら Phase 2.5 で本文中 `<img>` フォールバック検討
- **open**: 同 article から複数候補が出る場合 (Pattern A / B 両方成立) → Pattern B 優先で 1 件にまとめる方針 (Phase 2 で確定)

## 7. log / status

- 2026-05-27: 起票、 user 仕様 lock 完了、 Phase 1 着手予定
