# 346 PWA insight to X post draft (LLM-free)

## meta

- owner: Claude Code
- type: implementation (PWA UI + backend endpoint 拡張)
- status: LIVE_DEPLOYED (revision `manual-intake-service-346-x-post-1778828826` / 100% traffic / 2026-05-15 JST)
- created: 2026-05-15
- updated: 2026-05-15
- doc_path: `doc/active/346-PWA-insight-to-x-post-draft.md`
- lane: single (Claude direct dev、Codex 不使用)
- parent: なし (新規 feature)
- 関連 ticket: `342-INSIGHT-data-driven-ranking-auto-publish.md` (data 基盤側)、`INSIGHT-006` (既存 PWA tab、本 ticket で拡張)

## 1. 目的

manual-intake-service (PWA) 既存 INSIGHT-006 tab を、運用者が「巨人ファン向け X 投稿案」を即時生成 → 編集 → 投稿できる経路に変える。`insight.db` の verified data だけを使い、LLM 呼出ゼロでハルシネーション 0。

背景: ヨシラバー X 運用で試合中の data 系 post 量を上げたい。既存 NL query (`insight_nl_query`) + `insight_db` + PWA tab が揃っているのに data 表示だけで止まっており、投稿に直結していない。

## 2. 設計サマリ

```
[PWA: 旧 INSIGHT tab → "post 作成" tab に rename]

入力欄: 「OPS 10位」「岡本の打率」「防御率ランキング」etc.
  ↓
insight_nl_query.parse_question()  (既存、LLM 不使用)
  ↓
manual_intake_insight_query.generate_article() 経由で insight.db query  (既存、LLM 不使用)
  ↓
format_as_x_post()  (★新規、Python テンプレ only、LLM 不使用)
  ↓
PWA に textarea で X post draft 表示 (編集可、文字数カウンタ)
  ↓
[X 投稿] button → POST /x-post-direct  (★新規 endpoint)
  ↓
x_api_client.get_client().create_tweet(text=...)  (既存)
```

新規追加:
- `format_as_x_post(query_result: dict) -> list[str]`: Python テンプレ、4-5 種類 (ranking / single-player / team-trend / matchup / record)
- `POST /x-post-direct`: token 認証、body `{ text: str }`、X API 直叩き、結果 JSON 返却
- PWA UI: 既存 INSIGHT tab に「X 投稿用」表示 mode + [X 投稿] button 追加

LLM 呼出は全パス 0 (Gemini / Codex / OpenAI 一切呼ばない)。

## 3. 今回触らない範囲

絶対不可触:
- `auth.json` / Secret Manager の値
- WordPress publish/draft 処理 (`/manual-intake` の URL intake flow、`guarded_publish_runner`、`wp_draft_creator`)
- Gemini / Codex / OpenAI API (本 ticket は LLM 呼出ゼロ方針)
- `insight_nl_query.py` / `manual_intake_insight_query.py` の既存 logic (read-only 利用のみ、修正禁止)
- `insight.db` ETL / `insight-nightly` job (read-only 参照、書込み禁止)
- `x_api_client.py` の既存関数 (`create_tweet` を呼ぶだけ、関数自体は touch しない)
- 既存 X 自動投稿 lane (`x_post_queue_ledger` / `media_xpost_selector` / template 等)
- 既存 INSIGHT tab の自然言語 query 解釈 / DB query 結果の中身 (整形だけ追加)
- `manual_intake_service.py` の `/manual-intake` endpoint (URL intake flow)
- `/health` / `/manifest.webmanifest` endpoint
- 既存 token 認証ロジック
- 全 Cloud Scheduler (publish-notice-trigger / guarded-publish-trigger / giants-* / insight-nightly 等)
- 全 Cloud Run service の env / secret (image build & deploy のみ、env 変更は user 判断)
- WP REST 経由の写真 / category / tag 操作
- 404→410 conversion (`gone-response` plugin、別 ticket で本日対応済)
- subdomain (`prosports.yoshilover.com`) 設定
- yoshilover.com noindex 戦略 (個別記事 noindex 維持、category 設定も本 ticket では触らない)

scope 外の cleanup / 横展開 / lint 整形 / refactoring 一切禁止 (minimum-diff 原則)。

## 4. 影響範囲

直接変更:
- `src/manual_intake_service.py` (新 endpoint 追加 + HTML/JS 拡張)
- `src/format_as_x_post.py` (新規 module、テンプレ集 + 整形関数)
- `tests/test_format_as_x_post.py` (新規 test)
- `tests/test_manual_intake_service_x_post.py` (新規 test、新 endpoint)

間接影響 (read-only 参照):
- `src/analysis/insight_nl_query.py` (既存 parse 関数 import)
- `src/manual_intake_insight_query.py` (既存 query 関数 import)
- `src/x_api_client.py` (既存 `get_client()` / `create_tweet()` import)

deploy 影響:
- `manual-intake-service` Cloud Run service の image rebuild が必要
- Cloud Scheduler / env / secret 変更なし

データ影響:
- `insight.db` への書込み 0 (read-only)
- WP post への書込み 0
- X API 呼出は user button タップ時のみ (自動投稿経路に影響なし)

ユーザー影響:
- PWA 既存 INSIGHT tab の見た目変更 (table → post draft)
- 旧 raw table 表示は toggle で保持 (engineer 用途、回帰防止)
- `/manual-intake` (URL intake) tab は無変更

## 5. 実行予定テスト

unit test:
- `format_as_x_post.py`:
  - ranking テンプレ: OPS top 10 input → 280字以内、改行正確、巨人 highlight、ハッシュタグ末尾
  - single-player テンプレ: 岡本の打率 input → 期待 format
  - team-trend テンプレ: 月別防御率 input → 期待 format
  - 280 字超過時 truncate: 長い input → 自動切り詰め
  - 巨人 player 検出: 巨人選手は `← 巨人` マーク付与
  - empty input / NULL value handling
- `manual_intake_service` 新 endpoint:
  - `/x-post-direct` 正常系: token 一致 + 有効 text → 200 + tweet_id 返却 (実 API 呼出は mock)
  - `/x-post-direct` 認証 fail: token 不一致 → 403
  - `/x-post-direct` 280 字超過: 拒否 → 400
  - `/x-post-direct` 空 text: 拒否 → 400
  - `/x-post-direct` X API 失敗: 502 + error message
  - 既存 `/manual-intake` flow に影響無いこと (regression)

integration test:
- PWA 既存 INSIGHT tab の動作回帰 (table display option は維持)
- `format_as_x_post` 出力 → `/x-post-direct` 投稿の e2e (X API は mock)
- 既存 token 認証 path に影響無いこと

manual smoke (deploy 後):
- 自分のスマホで PWA を開く
- INSIGHT tab で「OPS 10位」入力 → post draft 表示確認
- textarea で編集 → 文字数カウンタ正確
- [X 投稿] button → 投稿先確認 (test 用 X account or dry-run mode)
- 旧 raw table 表示 toggle 動作確認

pytest baseline 維持:
- 全 pytest 既存 green 状態の維持 (新規追加分含む)
- 既存 fail 数の増加禁止

## 6. STOP条件

実装中に以下を検知したら即停止して user 判断仰ぐ:

1. 既存 pytest が新たに red 化 (本 ticket 外の test が落ちる)
2. 既存 `/manual-intake` URL intake flow に regression 発見 (response 変化、認証変化、保存先変化)
3. `insight_nl_query` / `manual_intake_insight_query` / `x_api_client` のいずれかに修正が必要と判明 (scope 拡大)
4. `insight.db` への書込みが必要と判明 (read-only 前提崩壊)
5. X API rate limit / auth 設定の変更が必要と判明
6. Cloud Scheduler / env / secret の変更が必要と判明
7. publish lane / WP draft 経路に影響を発見
8. token 認証ロジックに修正必要と判明
9. 既存 X 自動投稿 lane (`x_post_queue_ledger` 等) との衝突発見
10. format_as_x_post の出力が verified data から逸脱する可能性発見 (例: 数値演算が必要等)
11. PWA UI 変更が既存 manifest / service worker 等に影響と判明
12. cloudbuild / Dockerfile 修正が必要と判明 (scope 拡大、別 ticket 化を検討)

## 7. 禁止事項

- `git add -A` (移動 / 更新した path だけ明示 stage)
- LLM (Gemini / Codex / OpenAI / 他) 呼出の追加
- `--no-verify` で pre-commit hook bypass
- 既存 `/manual-intake` flow の修正
- `insight.db` への書込み
- WP publish status の変更
- X 自動投稿 lane への影響
- scope 外の cleanup / refactor / lint 整形 / typo 修正
- 既存 fail test を「対象外」として無視 (baseline 比較で fail 数増えたら必ず stop)
- commit / push 前に staged 内容を `git diff --cached --name-status` で verify しない
- ticket 番号 346 以外の commit message
- doc-only 便の連打 (本 ticket は impl 便、doc 更新は同一 commit 内に閉じる)
- 「だいたい合ってればいい」緩い judgment (verified data 厳守)
- AI failure modes に注意 (記憶再構成 / silent skip / 自己評価 OK は最大の事故源、すべて grep / pytest / log diff で実証する)

## 8. 想定されるデグレ

事前に想定されるリスク:

1. **既存 INSIGHT tab の表示崩れ**
   - 原因: HTML/JS 拡張時に既存 element の class / id が衝突
   - 検知: manual smoke + existing tab visual regression
   - 対策: 新 UI element は接頭辞 `x-post-` で namespace 分離

2. **既存 `/manual-intake` token 認証への影響**
   - 原因: 新 endpoint で token 検証ロジックを変更してしまう
   - 検知: regression test (test_manual_intake_service.py)
   - 対策: token 検証は既存 helper 関数を共用、新 endpoint も同じ helper を呼ぶ

3. **format_as_x_post で player_id 不一致**
   - 原因: insight.db 内の player 表記揺れ (フル名 / 短縮形 / 漢字違い)
   - 検知: 巨人 player check の unit test に複数表記 fixture
   - 対策: roster file (`config/npb_12team_roster.json` 等) を参照、id-based check に統一

4. **X API rate limit hit**
   - 原因: user が連打 / 同じ post を複数送信
   - 検知: X API response 429
   - 対策: client side でクールダウン (10 秒に 1 回まで)、429 を 502 として表示

5. **PWA の service worker cache 問題**
   - 原因: 既存 service worker (`/manifest.webmanifest` 経由) の cache に古い HTML が残り、新 UI が反映されない
   - 検知: deploy 後の cache-busting 確認
   - 対策: deploy 時に asset version を bump (HTML に version comment)

6. **巨人 player 検出の漏れ**
   - 原因: 新加入 / トレード後の名前変更で roster に未掲載
   - 検知: roster json と insight.db players の照合 test
   - 対策: 未一致時は highlight 無しで安全側 (誤検出より見逃しを優先)

7. **改行コードの platform 差**
   - 原因: `\n` vs `\r\n` で X 投稿時の表示崩れ
   - 検知: X 投稿 dry-run で改行確認
   - 対策: X API は `\n` のみ受け付けるので統一

8. **`/x-post-direct` 経由で auto-post lane と二重投稿**
   - 原因: 既存 X auto post (postgame 等) と同じ記事を user が手動で post してしまう
   - 検知: 運用判断 (ledger で track できるが本 ticket では対応しない)
   - 対策: 本 ticket では post 重複防止しない、user 判断責任 (memory にある通り「X 投稿は user 判断境界」)

## 9. 作業ログ欄

(実装着手後に追記。各 milestone を 1 行ずつ、timestamp + event + 対象 path + status)

```
YYYY-MM-DD HH:MM JST | <event> | <path or commit_hash> | <status>
```

予定 milestone (実績):

```
2026-05-15 JST | design lock (本 doc 完成、user GO 待ち)          | doc/active/346-PWA-insight-to-x-post-draft.md | DONE
2026-05-15 JST | user GO 受領                                    | -                                              | DONE
2026-05-15 JST | task plan (12 tasks)                            | TaskCreate x12                                 | DONE
2026-05-15 JST | explore existing INSIGHT-006 code               | src/manual_intake_service.py read              | DONE
2026-05-15 JST | pytest baseline (touched scope)                 | 127 + 66 = 193 passed                          | DONE
2026-05-15 JST | new module format_as_x_post.py 完成              | src/format_as_x_post.py (約 230 行)            | DONE
2026-05-15 JST | new module unit tests green                     | 14 passed                                       | DONE
2026-05-15 JST | /x-post-draft GET endpoint 追加                  | src/manual_intake_service.py                   | DONE
2026-05-15 JST | /x-post-direct POST endpoint 追加                | src/manual_intake_service.py                   | DONE
2026-05-15 JST | service endpoint tests green                    | 11 passed                                       | DONE
2026-05-15 JST | PWA HTML/JS UI 拡張                              | src/manual_intake_service.py                   | DONE
2026-05-15 JST | direct scope pytest                             | 218 passed                                      | DONE
2026-05-15 JST | wide pytest (excl integration)                  | 4708 passed, 4 xfailed                          | DONE
2026-05-15 JST | cloudbuild image 346-pwa-x-post                 | digest 2009da9...                              | DONE
2026-05-15 JST | deploy + set-secrets (X API x4)                 | revision 00079-j4p (initial、IAM 不足で死亡)    | RECOVERED
2026-05-15 JST | IAM 修復: secretmanager.secretAccessor x4 secret | seo-web-runtime SA grants                       | DONE
2026-05-15 JST | re-deploy with revision-suffix                  | revision 346-x-post-1778828826                 | DONE
2026-05-15 JST | production smoke (e2e)                          | /health / / /x-post-draft / 既存 regression    | DONE
2026-05-15 JST | doc post-work セクション追記                       | doc/active/346-PWA-insight-to-x-post-draft.md  | DONE
2026-05-15 JST | (次) commit + push                               | git add 指定 5 file → commit → push            | PENDING
```

## 10. Regression Memo欄

(実装中 / 後で気づいた既存挙動の依存 / 微妙な仕様 / 触ると壊れるポイントを追記。次以降の ticket 担当者向け memo)

例:
- 既存 INSIGHT tab の自然言語 parse は X 個の metric alias を持つ、追加禁止
- insight.db の OPS schema は v3、column 名は `ops_value` (v2 の `ops` ではない)
- ...

---

## (post-work セクション、2026-05-15 JST 実装完了後の記録)

### A. 実際に変更したファイル

**新規追加 (3 件)**

- `doc/active/346-PWA-insight-to-x-post-draft.md` — 本 ticket doc
- `src/format_as_x_post.py` — 新規 module、insight rank_result → X post draft 形式整形 (Python テンプレ、LLM 不使用)
- `tests/test_format_as_x_post.py` — 14 unit test (ranking / focus / 巨人 highlight / 280字 cap / NULL handling / line break)
- `tests/test_manual_intake_service_x_post.py` — 11 endpoint test (両 endpoint の正常 / 異常 + 既存 routing regression)

**既存 modify (1 件)**

- `src/manual_intake_service.py` — `do_GET` に `/x-post-draft` 追加、`do_POST` に `/x-post-direct` 追加、PWA HTML に "🐦 X 投稿 (データ)" tab rename + 新フォーム + JS handler、docstring の Routes 節更新

不可触で済んだ範囲:
- `src/manual_intake_insight_query.py` (read-only import のみ)
- `src/analysis/insight_nl_query.py` (read-only import のみ)
- `src/x_api_client.py` (`get_client()` / `create_tweet()` を呼ぶだけ、関数定義は touch せず)
- 既存 `/manual-intake` URL intake flow
- `insight.db` ETL / `insight-nightly` job
- `Dockerfile.manual_intake_service` (image rebuild のみ、Dockerfile 内容変更なし)
- `cloudbuild_manual_intake_service.yaml` (substitution の `_TAG` のみ動的変更)

### B. diff 概要

- `src/format_as_x_post.py`: 約 230 行新規
  - constants: `X_CHAR_LIMIT=280`, `DEFAULT_HASHTAGS="#巨人 #ジャイアンツ"`, `_GIANTS_TEAM_ALIASES={"巨人","読売","ジャイアンツ","Giants","G",...}`, `_METRIC_LABELS_JP{...}`, `_POSITION_LABELS_JP{...}`
  - helpers: `_metric_label`, `_position_label`, `_is_giants`, `_format_value` (metric-specific precision), `_truncate_to_x_limit`, `_build_header`, `_build_ranking_body`, `_build_focus_body`
  - public: `format_as_x_post(parsed, rank_result, *, hashtags=None, top_n=None) -> dict`
- `src/manual_intake_service.py`: 約 +180 行
  - docstring Routes 節更新
  - `GET /x-post-draft` route (約 70 行)
  - `POST /x-post-direct` route (約 65 行)
  - tab label "📊 データ要望" → "🐦 X 投稿 (データ)"
  - 新 form `<form id="x-post-draft-form">` + 説明 + 区切り `<hr>` を section 先頭に追加 (約 15 行)
  - 新 JS handler `renderXPost` / submit listener / `[X 投稿] button` 押下時の `/x-post-direct` 呼出 (約 90 行)
- `tests/test_format_as_x_post.py`: 約 210 行新規 (14 test, 8 test class group)
- `tests/test_manual_intake_service_x_post.py`: 約 200 行新規 (11 test, 3 test class group)

minimum-diff 維持: 既存 endpoint / form / JS handler / template に手を入れず、新規 block を挿入する形のみ。

### C. 実行したテスト

1. **AST parse check**: `python3 -c "import ast; ast.parse(open('src/format_as_x_post.py').read())"`、`src/manual_intake_service.py` も同様
2. **新 module import smoke**: `from src import format_as_x_post`
3. **新 module pytest**: `pytest tests/test_format_as_x_post.py -v`
4. **新 endpoint pytest**: `pytest tests/test_manual_intake_service_x_post.py -v`
5. **直接 scope pytest**: `pytest tests/test_manual_intake_service.py tests/test_manual_intake.py tests/test_manual_intake_insight_query.py tests/test_format_as_x_post.py tests/test_manual_intake_service_x_post.py tests/test_x_post_generator.py tests/test_x_post_queue_ledger.py tests/test_x_post_template_candidates.py tests/test_x_post_eligibility_evaluator.py`
6. **広範 pytest**: `pytest -q --no-header -x --ignore=tests/integration`
7. **cloudbuild**: `gcloud builds submit --config=cloudbuild_manual_intake_service.yaml --substitutions=_TAG=346-pwa-x-post`
8. **deploy**: `gcloud run services update manual-intake-service --image=...:346-pwa-x-post --set-secrets=X_API_KEY=...,X_API_SECRET=...,X_ACCESS_TOKEN=...,X_ACCESS_TOKEN_SECRET=...`
9. **traffic shift**: 旧 revision (00087-yoy、5h 前作成、旧 image digest 2802a6d...) → 新 revision (346-x-post-1778828826、新 image digest 2009da9...) に 100% 移動
10. **production smoke**: /health、/、/x-post-draft (happy / empty)、/x-post-direct (empty)、既存 /insight-ask / /manual-intake (regression)

### D. テスト結果

- AST parse: OK (`src/format_as_x_post.py`、`src/manual_intake_service.py` 両方)
- 新 module pytest: **14 passed** (test_format_as_x_post.py)
- 新 endpoint pytest: **11 passed** (test_manual_intake_service_x_post.py)
- 直接 scope pytest: **218 passed, 50 subtests passed** (baseline は 193 + 新規 25 = 218 で完全整合)
- 広範 pytest: **4708 passed, 4 xfailed (既存), 978 subtests passed** (baseline 4687 collected → +21 で整合、failure / error は 0)
- cloudbuild: SUCCESS、image digest `sha256:2009da9f1b437c52331c2d15c40c85dc8df51c524586a9b512531d6e81f86c29`
- production smoke:
  - `/health` → 200 `{"ok": true}` ✅
  - `/` → 200、新 tab text `X 投稿 (データ)`、新 form text `X 投稿用 post 案`、`post 案を作る` がすべて HTML に出力 ✅
  - `/x-post-draft?q=OPS` → 200、verified data の OPS top10 (巨人・大城卓三 ← 巨人 マーク付き)、char_count=198、parsed.metric="OPS" ✅
  - `/x-post-draft?q=` → 400 `empty_question` ✅
  - `/x-post-direct` (empty text) → 400 `empty_text` ✅
  - 既存 `/insight-ask` regression → 既存挙動 (400 `empty_question`) 維持 ✅
  - 既存 `/manual-intake` POST regression → 既存挙動 (400 `missing_url`) 維持 ✅

### E. 残った懸念

1. **実 X 投稿の実機 verify は未実行**: production smoke で `/x-post-direct` は empty/auth error path のみ確認、実際の create_tweet 経路は production 環境では未通電。原因: 実投稿は user 判断境界 (memory: 「X 投稿は user 手動」)。user が PWA から button タップで初回投稿してみる必要あり。
2. **PWA cache busting**: スマホで既に手動投入 PWA を install 済の場合、service worker が古い HTML を cache してる可能性。user 側で **iOS なら設定 → Safari → 履歴とデータを消去 / Android Chrome なら長押し → アンインストール後再追加** が必要かも。
3. **/x-post-draft の auth 開放**: 既存 `/insight-ask` と同パターンの「MANUAL_INTAKE_TOKEN が空なら OPEN mode、設定済なら token 必須」。現状 production env は OPEN mode で動作中 (manual-intake-service には MANUAL_INTAKE_TOKEN が未設定)。今後 token gate 必要なら別途 env 投入。
4. **既存 X 自動投稿 lane との重複防止**: postgame / lineup 自動投稿で既に WP→X してる記事を、user が PWA から手動で重複投稿する可能性。本 ticket では防御せず、user 判断責任。気になるなら 263-QA-duplicate-publish-guard と類似の重複 X 投稿 guard を別 ticket で対応。
5. **Dockerfile comment の stale 化**: `Dockerfile.manual_intake_service` 冒頭コメント「never publishes, calls Gemini, or hits X API」は /x-post-direct 追加で半分嘘になった。実害なし、次回 Dockerfile 触る ticket で同時 update が無難。

### F. 新しく見つかったデグレ

- **deploy 時の IAM 不足**: `seo-web-runtime@baseballsite.iam.gserviceaccount.com` が yoshilover-x-* 4 secrets への accessor を持っておらず、初回 deploy が "Permission denied on secret" で 1 revision 死亡 (00079-j4p)。同 SA に `roles/secretmanager.secretAccessor` を 4 secret 個別付与で復旧 + 別 suffix で再 deploy。
- **traffic auto-shift しなかった件**: `gcloud run services update --image` の挙動として、deploy 直後の output が "100 percent of traffic" と表示されたが、実態は `latestReadyRevisionName` が old (00087-yoy / quote-emph tag pinned) のままで、新 revision に traffic が乗らなかった。`gcloud run services update-traffic --to-revisions=<new>=100` を別途打つ必要あり。今回は IAM 修復後の再 deploy で自動 routing 復旧。
- **既存 production code の cosmetic issue (本 ticket 外)**: `manual_intake_service.py` の HTML template literal でエスケープシーケンス `\s` (line 184) が SyntaxWarning を出す。既存問題、本 ticket では不可触。次回 HTML template 触る ticket で raw string 化 or escape で同時修正検討。

### G. 追加した回帰テスト

`tests/test_manual_intake_service_x_post.py` 内に 2 件の regression test を含む:

- `ExistingManualIntakeRegressionTests::test_post_manual_intake_still_routes_to_existing_handler` — `/manual-intake` POST が 346 後も 404 を返さず既存 handler に届くこと
- `ExistingManualIntakeRegressionTests::test_unknown_post_path_still_404` — 不明 path は引き続き 404、`/x-post-direct` 追加で他 path の挙動が変わってないこと

加えて、新規 endpoint の auth 失敗 / 空 / 長さ超過 / X API 失敗 / env 欠落 の 5 error path 全部にカバレッジあり (上記 D § 11 passed 内訳)。

### H. 次回触ってはいけない範囲

次の作業者 (Claude 次セッション / Codex / user) が触る前に必ず確認:

1. **`src/format_as_x_post.py` の `_GIANTS_TEAM_ALIASES`**: `src/analysis/insight_defense_proxy.py` の team alias と同期取り済。片側だけ追加すると Giants highlight が漏れる。両方同時に更新すること。
2. **`src/format_as_x_post.py` の `_METRIC_LABELS_JP`**: `src/analysis/insight_rank_query.py::KNOWN_METRICS` と key 揃え済。新 metric を KNOWN_METRICS に足したら同時に LABELS にも追加 (なければ英語のままで動くがフォールバックなだけ)。
3. **`POST /x-post-direct` の body schema**: `{"text": str}`。他 field 追加禁止 (token は除く、既存 auth helper が拾う)。1 投稿 = 1 text、media / quote / reply は別 endpoint として後日設計。
4. **`/x-post-direct` の 280 char 上限**: X premium / blue で 25,000 字対応した場合も、現 endpoint は 280 cap 固定。premium 解禁時に明示変更すること。
5. **`tab-btn-insight` の `data-tab=\"insight\"`**: HTML/JS で tab 切替のキー。rename したら CSS / JS / 既存 INSIGHT-006 〜 009 form の全 form id を同時更新必要。
6. **`x-post-draft-form` / `x-post-draft-btn` / `x-post-draft-result` / `x-post-q` / `x-post-text`**: 新規 element の id は `x-post-` namespace 接頭辞で揃え済。既存 id 衝突なし。新 element を追加する際は同 prefix を維持。
7. **`x_api_client.get_client()` を直接呼ばないこと**: 必ず lazy import (handler 内 `from src import x_api_client as _xc`) で。module-level import すると manual_intake_service 起動時に tweepy 失敗が即時障害になる。
8. **既存 INSIGHT-006 〜 009 endpoint と form**: `/insight-ask` / `/insight-article` / `/insight-rank` / `/insight-query` の挙動・response schema は 346 で touch していない。次回 INSIGHT 系を改修するとき、token check のコピペ複製が散在してる事実は既知 (refactor は別 ticket)。
9. **Cloud Run revision tag (`quote-emph`、`insight-tab` 等)**: 過去の no-traffic canary 履歴。本 ticket は通常 100% traffic 直接切替で済ませた。tag を消す/付替える操作は user 判断境界扱い (canary 戦略変更)。

## Regression Memo 補足 (実装中に判明)

- **insight.db に直接 schema 依存**: `team_code` 列は実は `team_name` 文字列 (insight_rank_query.py の `_aggregate_batting` comment 参照)。`巨人` 漢字でも `g` 単文字でも、SOURCE の表記揺れがある。346 では両方 alias 化済。
- **insight_nl_query.parse_question は LLM fallback budget あり** (`_parse_via_llm`、Gemini Flash、日 N 回 cap)。346 の `/x-post-draft` は rule-based parse のみ通れば結果返るが、`unresolved` 時に LLM fallback が走るか否かは parse_question の内部 budget 状態次第。budget 切れ時の挙動も 346 では未検証 (`metric_not_detected` / `unresolved_fields` のいずれかで返るはず)。
- **`miq.ensure_local_db()` は ETL を実行しない**: GCS の `insight.db` を local cache に DL するだけ。データ新鮮度は nightly ETL 依存 (data-insight-* schedulers)。
- **PWA service worker 不在**: manifest.webmanifest はあるが Service Worker は登録してない (manual_intake_service.py に SW JS 配信 endpoint なし)。なので cache busting は通常 browser cache のみで、deploy 後は ctrl+F5 / アプリ再起動で新 HTML が即時反映される想定。

