# 392: ヨシラバー branding X 投稿案を Gemma 4 + Tavily HTTP REST + 任意 DB 参照で生成 (Phase 2、 382 rule / mail / Scheduler 流用)

status: PLANNING (user GO 後着手中)
owner: Claude Code
lane: (未確定、 user 指示待ち)
priority: (未確定、 user 指示待ち)
depends_on: 391 (Phase 1 commit `4a65a3a` / `b5f0da4`)
supersedes: 382 multi-source shape B 改修中 (`src/x_post_mail_lane.py` dirty、 未 commit) — 同 file の template-based 改修は 392 で **LLM 生成に置き換え**るため不要
created: 2026-05-19 JST
github_issue: #67

---

## 1. 作業の目的

ヨシラバー branding X 投稿案を **無料の Gemma 4 + Tavily HTTP REST API + 任意で
insight.db 参照** で生成し、 **既存 382 の rule (spec) / mail format /
Scheduler を守った状態**で user mail に流す。

user 明示 (2026-05-19 chat lock):

- 「いままで LLM がうまく使えなかった」 → 過去 (Gemini Flash 等で) hallucination / 数字事故 / コスト懸念で template-based に逃げていた
- 「無料のこの案 (Gemma 4 free tier + Tavily 1000 credits/月)」 で再挑戦
- 「文章をうまく作る」 = template flat な 382 multi-source 等を超える、 動的・hook あり・人間が「これは見たい」と思える copy
- 「ルールは 382 のやつだよ」 = spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止 / yoshilover framing / 巨人 specific) は不変
- 「データベース見てもよい」 = insight.db の DB 照合済み数値は post に入れて OK (RAG として活用可)
- **「回避策」 = stdio 同梱を諦め、 Tavily を HTTP REST で叩く** (既存 `Dockerfile.x_post_mail` の "Never Gemini" 設計と +100MB image / +5-15 秒 cold start を回避)

## 2. やること (scope)

### REPLACE

`src/x_post_mail_lane.py` 内の **template-based branding builder** を
Gemma 4 + Tavily REST + (任意) DB fact 経由の動的生成に **置き換える**:

- `_build_source_backed_post_text` の 4 template (comment / record / farm / default) → **Gemma 4 生成 1 candidate** に置き換え
- 私が dirty で残した multi-source shape B `build_multi_source_candidate` (382 改修中、 未 commit) → **不要**、 supersede され破棄

### KEEP

- **DB# データ候補** (`pick_candidates` 経由の OPS / ERA 等 ranking candidate) は branding ではない factual data として **そのまま保持**
- **mail compose / subject / recipients / Scheduler trigger** = 既存 `compose_mail` + 既存 5 x-post-mail-* triggers 完全流用
- **DB freshness gate / dedup / player diversity cap / 24h history** = 既存ロジック維持
- **既存 `Dockerfile.x_post_mail`** = 不変 (HTTP REST 経由で Node 追加 不要)

### ADD

- `src/x_post_mail_lane.py` に新 builder `build_gemma_branding_candidate`:
  - 入力: focus player (lineup / dedup history から)、 任意で DB 由来 fact line、 secret 経由の API keys
  - 動作:
    1. **Tavily REST API** (`POST https://api.tavily.com/search`) で巨人 + player 最新検索 (max_results=3、 search_depth=basic)
    2. (任意) `insight.db` から player の DB 照合済み数字を pull (`miq.query_rank` 等を再利用、 取れなければ skip)
    3. Gemma 4 31B (Gemini API free tier) に prompt 投入 (spec 382 hard rule + DB fact + Tavily 検索 snippet を RAG として context 注入)
    4. 280 字以内の post text を返す Candidate dataclass を返却
  - 失敗時は `None` 返却 → 既存 mail は止めない (silent skip、 fault tolerance hard rule)
- `src/tools/run_x_post_mail.py` の caller を変更:
  - 既存 `news_opinion_fallback` を 呼ばない (template-based 全部 OFF)
  - 代わりに Gemma 4 candidate を **1-3 件 / fire** 生成して mail に append
  - env flag `X_POST_MAIL_GEMMA_GEN_ENABLED` (default `0` = OFF) で gating、 OFF 時は既存挙動完全維持 (rollback 余地)
- `tests/test_x_post_mail.py` に 3-5 test 追加 (flag OFF で既存挙動 / flag ON で Gemma append / 例外 silent skip / spec 382 hard rule violation gate)

### post-gen validator (spec 382 hard rule)

Gemma 4 生成出力に対し以下を gate (1 つでも違反したら drop + WARNING log、 既存 mail は送信続行):

- URL 含む (regex `https?://`) → drop
- hashtag 含む (regex `#\S+`) → drop
- 「ヨシラバーで整理しました」「Xでは」「X上では」「みんなの声」 → drop
- 280 字超 → drop

## 3. 今回触らない範囲

- 既存 `src/x_post_mail_lane.py` の **DB# データ候補 builder** (`pick_candidates` / ranking 系) → 不変
- 既存 `src/x_post_mail_lane.py` の `compose_mail` / `_compose_text_body` / mail subject 構築 → 不変
- 既存 24h dedup / player diversity cap / 24h history / focus_player / context_label → 不変
- **`Dockerfile.x_post_mail`** → **不変** (HTTP REST のため Node 不要)
- 既存 `src/main.py` / `src/fetcher_*` / `src/draft_body_editor*` / `src/guarded_publish*` / `src/publish_notice*` / `src/analysis/*`
- `automation/` / `.codex/automations/`
- 既存 Cloud Run Job 群 (`yoshilover-fetcher` / `publish-notice` / `guarded-publish` / `insight-nightly` / etc) — `x-post-mail-lane` のみ image rebuild + Secret binding 追加
- Cloud Scheduler 全部 (既存 5 x-post-mail-* trigger をそのまま流用、 新規追加・既存変更なし)
- 既存 mail bridge config (`mail-bridge-from` / `mail-bridge-to` / `mail-bridge-gmail-app-password` 等) は再利用、 値変更なし
- 既存 Secret 値 (`gemini-api-key` / `TAVILY_API_KEY` / 他) は変更なし、 binding 追加のみ
- WordPress (REST / DB / plugin / theme 一切触らない)
- X / Twitter (live posting / OAuth / Hermes 一切触らない)
- GA4 / SEO / WP plugin

## 4. 影響範囲

- **コード**:
  - `src/x_post_mail_lane.py`: 新 builder 関数 1 つ + REST helper 1 つ追加 (~100-150 行)。 既存ロジック改変なし。
  - `src/tools/run_x_post_mail.py`: caller 切替 (~30-50 行 diff)。
  - `tests/test_x_post_mail.py`: 3-5 test 追加。
- **依存**: `requests` (既存)、 `google-generativeai` または `google-genai` (391 で追加済) を再利用。 **fastmcp は 392 で使わない** (391 local CLI 用に残置)。
- **Dockerfile**: **不変** (HTTP REST のため Node 不要、 image size 不変、 cold start 不変)
- **Cloud Run Job**: `x-post-mail-lane` の image rebuild (code 変更のみ) + Secret binding 追加 (`TAVILY_API_KEY`)。 `gemini-api-key` は既存 binding を確認(無ければ追加)。
- **Cloud Scheduler**: 触らない (既存 5 triggers をそのまま使う)。
- **Secret Manager**: 触らない (既存 secret に binding 追加のみ)。
- **mail**: subject / recipients / format 不変。 candidate 内訳が変わる (template → Gemma 4 + DB#)。

## 5. 実行予定テスト

- `python3 -m py_compile src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py`
- `python3 -m unittest tests.test_x_post_mail` (新 test 含む)
- `python3 -m unittest tests.test_x_post_gen_mcp` (391 既存 10 test、 regression 0 確認)
- `python3 -m unittest discover -s tests` (全 suite、 baseline 4471 維持 + 新 test 増分)
- Cloud Build smoke (image rebuild 成功、 既存 build 工程に変化なし)
- Cloud Run Job manual execute は **追加 mail 抑止のため実行しない**、 次回自然 fire で verify
- 自然 fire 後 Cloud Logging で:
  - flag OFF: 既存 mail 通常送信、 Gemma 関連 log 0 件、 既存 candidates 数不変
  - flag ON: Gemma INFO log 出現、 mail に Gemma candidate 1-3 件出現、 validator drop log 観測 (もしあれば)
  - 例外時 (Tavily 不到達 / Gemma 429 等): WARNING log のみ、 既存 mail は送信成功

## 6. STOP 条件

以下のいずれかが満たされたら **即停止**して user 判断に上げる。

- pytest 全 suite で regression (4471 OK 数が減る)
- py_compile 失敗
- flag OFF で既存 mail の挙動が変わる (subject / candidate count / format / 送信 status いずれか)
- 既存 DB# データ候補 builder のロジックを誤って改変
- Gemma 4 / Tavily REST の **0 ドル制約超過の兆候** (paid_tier 課金観測、 Tavily credit が 1 fire で 10+ 消費)
- flag ON で **既存 mail が止まる** (Gemma 例外で全 fire 失敗事故)
- spec 382 違反 output が validator を抜けて mail に混入 (URL / hashtag / 未検証数字 / 引用 / 媒体名)
- 既存 Cloud Run Job 群に予期しない影響
- Gemma 4 出力品質が user 目視で「精度悪い」 判定 → flag OFF に戻して別 model 検討

## 7. 禁止事項

- 既存 DB# データ候補 builder の **改変** (signature / 内部ロジック 不変)
- 既存 mail compose / subject / recipients 変更
- 既存 Scheduler の trigger 時刻変更 / job 追加 / job 削除
- 新 Cloud Run Job の作成 (既存 `x-post-mail-lane` 拡張のみ)
- **Dockerfile.x_post_mail の変更** (HTTP REST のため不要、 設計思想 "Never Gemini" は本 ticket で update する **コメント更新は許可**)
- WordPress REST / DB / X live posting / Hermes
- Gemini API の paid tier 切替 (free tier 維持必須)
- Tavily API の paid plan 加入 (free 1000 credits/月のみ)
- `RUN_DRAFT_ONLY` env / 既存 publish 系 env 変更
- 既存 Secret (`gemini-api-key` / `wp-app-password` / `mail-bridge-*` 等) の **値変更**

## 8. 想定されるデグレ

| 項目 | リスク | mitigation |
|---|---|---|
| Gemma 4 例外で既存 mail が止まる | **高** | builder を try/except で包む。 例外時 None 返却 + WARNING log のみ。 既存 candidates だけで mail 送信続行 (fault tolerance hard rule) |
| Gemma 出力に spec 382 違反 (URL / hashtag / 未検証数字) | 中 | system prompt + post-gen validator (regex) で gate、 violation 時は candidate drop |
| Gemma hallucination | 低 | Tavily 検索結果を context 注入することで factual ground 強化。 さらに任意で DB fact line も注入 (RAG)。 mail は user 手動投稿用 draft で reject 可能 |
| Tavily REST API timeout / 5xx | 中 | requests timeout=30 + try/except、 fail 時 None 返却 |
| Tavily 1000 credits/月 超過 | 低 | 5 fires/日 × 1-3 Gemma 候補 × 1 Tavily call = 150-450 credits/月 (free tier の 45% 以下) |
| Gemma 4 rate limit 16k tok/分 で 429 | 中 | 1 fire = 1-3 候補。 fire 間隔 1-5 時間で余裕。 Tavily 結果 context を `max_results=3` × `[:300] char` で抑制 |
| 既存 382 lane test (101 test) regression | 中 | 既存 builder 関数は削除せず caller 切替のみ、 既存 test は flag OFF default で従来挙動を継続検証 |
| 既存 mail に Gemma candidate が混ざることで user 体感悪化 | 中 | flag default OFF + smoke 確認後 user 判断で ON。 quality 悪ければ rollback 1 toggle |
| 漏れた `TAVILY_API_KEY` を production Job が使う | 低 | free tier 1000 credits/月のため金銭被害 0、 user の都合いい時に rotate |
| 「Never Gemini」 設計思想変更 | 低 | Dockerfile コメントを「LLM branding candidate 追加 (392)」 に更新、 image / Python deps 構造は不変 |

## 9. 必要な API / 既存資産

391 で既に揃っている、 **新規取得不要**:

| 資産 | 用途 | 状態 |
|---|---|---|
| Gemini API key | Gemma 4 31B 推論 | Secret Manager `gemini-api-key` (既存) |
| Tavily API key | web 検索 (HTTP REST 経由) | Secret Manager `TAVILY_API_KEY` (391 で登録、 version 1) |
| insight.db | DB 照合済み数字 (任意) | 既存 `miq.ensure_local_db()` + `miq.query_rank()` 経由で読める |
| Python deps | `requests` (既存)、 `google-genai` または `google-generativeai` (391 で追加済) | 不変 |
| mail bridge | mail 送信 | 既存 `mdb.send()` + 既存 secret `mail-bridge-*` |
| Cloud Run Job | 実行 runtime | 既存 `x-post-mail-lane` (image rebuild のみ、 Dockerfile 不変) |
| Cloud Scheduler | trigger | 既存 5 x-post-mail-* triggers |

新たに必要な infra 変更:
- `x-post-mail-lane` Cloud Run Job への Secret binding (`TAVILY_API_KEY`, `gemini-api-key`) 追加 (binding 設定のみ、 値変更なし)
- service account `seo-web-runtime@baseballsite.iam.gserviceaccount.com` (既存) に両 secret への `roles/secretmanager.secretAccessor` を grant (未付与なら追加)
- image rebuild (code 変更のみ、 Dockerfile / OS パッケージ 不変)

## 10. 作業ログ欄

(post-work で append)

## 11. Regression Memo 欄

(post-work で append)

---

## post-work sections (Markdown GO 後の work 完了時に追記)

### post-work 1. 実際に変更したファイル
(TBD)

### post-work 2. diff 概要
(TBD)

### post-work 3. 実行したテスト
(TBD)

### post-work 4. テスト結果
(TBD)

### post-work 5. 残った懸念
(TBD)

### post-work 6. 新しく見つかったデグレ
(TBD)

### post-work 7. 追加した回帰テスト
(TBD)

### post-work 8. 次回触ってはいけない範囲
(TBD)

---

## meta — user 明示制約 (2026-05-19 chat lock)

- **rules は 382 ticket** (`doc/done/2026-05/382-MKT-yoshilover-branding-post-planning-mail.md`) を継承:
  - URL / hashtag / 「ヨシラバーで整理しました」 / 媒体名 / site-induction copy / fabricated fan reaction を含めない
  - 未検証 score / rank / injury / roster / 打率 / 防御率 / OPS / inning / hit count / RBI / quote を含めない
  - DB 照合できない数字は generalize
  - ヨシラバー独自の framing、 記事タイトルのコピーは禁止
  - 巨人外の球団・MLB (元巨人 OB 以外) は除外
- **「いままで LLM がうまく使えなかった」**: 過去 Gemini Flash 等で hallucination / コスト懸念 → 今回は **Gemma 4 31B free tier + Tavily HTTP REST (検索 ground) + 任意 DB fact 注入 (factual ground)** で再挑戦
- **「無料のこの案で文章をうまくつくる」**: 0 ドル制約 hard rule (Gemini API free / Tavily 1000 credits/月 / 自前 host 禁止) 維持
- **「データベースをみてもよい」**: insight.db の DB 照合済み数値は post に入れて OK (382 spec の数値ルール準拠)
- **「回避策で行ける」 = HTTP REST 採用**: stdio 同梱 (Node 追加 + image +100MB + cold start +5-15 秒) を回避、 Tavily を直接 REST で叩く。 Python only、 既存 Dockerfile / image / cold start 全部不変。
- **mail format = 既存 382 mail と同じ** (`compose_mail` 再利用、 subject / format / recipients 不変)
- **Scheduler = 既存 5 x-post-mail-* triggers をそのまま流用**

## meta — 382 ticket との関係

- 382 (`doc/done/2026-05/382-MKT-yoshilover-branding-post-planning-mail.md`) は CLOSED、 LIVE 稼働中 (本日 07:00 JST 自然実行 SUCCESS)
- 382 の **spec / hard rule** は 392 でも継承 (rules-keep)
- 382 の **implementation (template-based builder)** は 392 で **LLM 生成に置き換え** (implementation-supersede)
- 私が 382 改修中で repo に dirty 残置していた multi-source shape B (`build_multi_source_candidate` + `_build_multi_source_priority` 等、 commit 待ち) は **不要、 supersede**。 working tree から消すか stash する判断は 392 着地後に決める。

## meta — 391 ticket との関係

- 391 (`doc/active/391-x-post-gen-mcp-tavily-gemma4-phase1.md`) で Tavily MCP stdio + Gemma 4 31B + CLI を実装済 (commit `4a65a3a` / `b5f0da4`)
- 391 の `src/x_post_gen_mcp.py` の `SYSTEM_PROMPT` は 392 で **再利用可** (同一 prompt で再生成)
- 391 の `fastmcp` 依存は 392 では不使用 (local CLI 用に残置、 production lane では HTTP REST direct)
- 391 で smoke 確認済の出力品質 (1 件サンプル、 spec 382 hard rule 違反 0、 hook あり、 戸郷投手の実状況と整合) を本番 lane で再現できるかが 392 の verify ポイント

## meta — 0 ドル制約 / billing 確認

- 391 smoke で観測: Gemini API 429 error message に `paid_tier_input_token_count` 表記。 ただし pricing 上 Gemma 4 は paid tier "Not available" (料金体系自体無い) → quota 名は内部命名規約、 課金可能性 0。
- 万一 paid 課金が観測されたら、 392 GO 前に Console billing reports で確認推奨: https://console.cloud.google.com/billing/013720-255D2B-75CA07/reports?project=baseballsite
- Tavily は free tier 1000 credits/月、 392 想定使用量 150-450 credits/月 で headroom 55%+ あり
- 既存 budget alert `yoshilover-budget-emergency` (7500 JPY/月、 50% threshold) が安全網

## meta — stdio 同梱 vs HTTP REST の判断 (2026-05-19)

| 軸 | stdio 同梱 | HTTP REST (採用) |
|---|---|---|
| 検索機能 | ✓ | ✓ |
| Gemma 4 生成 | ✓ | ✓ |
| spec 382 ルール遵守 | ✓ | ✓ |
| Dockerfile 変更 | **要 Node 追加** | **不要** |
| image size | +100MB | **不変** |
| cold start | +5-15秒 | **不変** |
| 既存 "Never Gemini" 設計 | **壊す** | **守る** |
| Python deps | fastmcp + google-genai | requests + google-genai (要 sync 化 or google-generativeai) |
| user 旧指示 (stdio 同梱) | ✓ | ✗ |
| user 新指示 (回避策で行く) | ✗ | ✓ |

→ user 後の指示「回避策でいける、 0 ドル維持」 を採用、 HTTP REST direct。
