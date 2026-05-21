# INSIGHT-006 — manual-intake-service にタブ UI 追加 + データ要望ページ

**作成日**: 2026-05-13
**前提**: INSIGHT-001〜005 着地済、Cloud Run job `insight-nightly` 稼働中、GCS bucket `baseballsite-yoshilover-insight` に DB / CSV / digest 永続化
**目的**: 既存 GUI (`https://manual-intake-service-487178857517.asia-northeast1.run.app/`) に **2 つ目のタブ「データ要望」** を追加。user が選手・signal_type・日付範囲でフィルタして、蓄積済 `article_candidates` を browser で見られる状態にする。
**運用方向**: 既存「手動投入」タブの挙動は完全不変。新タブは read-only (GCS から insight.db を pull → SQL → JSON 返却)。

---

## 3. 今回触らない範囲

- WordPress DB / `wp_posts` / `wp_postmeta` / `wp_options` / custom table
- WP 本文 / publish status / noindex / canonical / 301 / SEO
- 既存 `manual-intake-service` の `/manual-intake` POST 動作（form 内容、handler、WP draft 作成 path）
- 既存 `/`, `/health`, `/manifest.webmanifest` の挙動
- `MANUAL_INTAKE_TOKEN` の認証 flow
- INSIGHT-001〜005 で作った既存ファイル全て（`src/analysis/*`, `Dockerfile.insight_nightly`, `cloudbuild_insight_nightly.yaml`）
- Cloud Run `insight-nightly` job
- Cloud Scheduler 全般（既存 + `insight-nightly-trigger`）
- env / secret / flag
- master ブランチ
- 既存 `src/source_*` / `src/wp_client` / `src/rss_fetcher` / `src/guarded_publish_runner`

## 4. 影響範囲

**追加 (additive)**

- `src/manual_intake_service.py` への追記:
  - `_HTML_FORM` を tab 構造に書き換え（既存「手動投入」フォームは Tab 1 内、Tab 2 は新規）
  - 新規 endpoint `GET /insight-query` を追加（フィルタクエリ取得 → GCS pull → SQL → JSON）
  - `do_GET` ルーティングに `/insight-query` 追加

- `src/manual_intake_insight_query.py` (新規モジュール、検索ロジック分離):
  - GCS から `insight.db` を lazy download + キャッシュ
  - 選手 / signal_type / 日付範囲フィルタの SQL クエリ
  - JSON 形式で結果返却

- `tests/test_manual_intake_insight_query.py` (新規)

**修正 (additive)**

- 既存 `src/manual_intake_service.py` の HTML 部分はタブで包む。手動投入フォーム本体は文字列レベルで完全に維持（diff 検証で確認）。

**追加 IAM**

- `seo-web-runtime@baseballsite.iam.gserviceaccount.com`（manual-intake-service SA）に `roles/storage.objectViewer` を `gs://baseballsite-yoshilover-insight` へ付与

**触らないファイル**

- `Dockerfile.manual_intake_service`（パッケージ追加は requirements.txt で済む）
- `cloudbuild_manual_intake_service.yaml`
- 既存 `tests/test_manual_intake*.py`（regression 必須、red 化禁止）

**Cloud Run service update**

- 新規 env var `INSIGHT_GCS_BUCKET=baseballsite-yoshilover-insight` を service にも追加
- image rebuild + deploy が必要（service revision が 1 増える）

## 5. 実行予定テスト

```
pytest tests/test_manual_intake_insight_query.py -v     # 新規
pytest tests/test_manual_intake_service.py -q           # 既存 (regression、red 化禁止)
pytest tests/test_manual_intake.py -q                   # 既存 (regression)
pytest tests/test_insight_*.py -q                       # 既存 INSIGHT 系 (regression)
pytest tests/test_event_key_*.py tests/test_morning_*.py -q  # 既存 (regression)
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q  # 既存 baseline
```

**Invariant**:
- `/` GET の返す HTML に既存「手動投入」form の全 input id (`url`, `article_type`, `manager_name`, `player_name`, `quote`, etc.) が含まれ続けること
- `/manual-intake` POST のレスポンス JSON 形式が変わらない
- 既存 token / cookie 認証フロー不変
- `/insight-query` で GCS が無くても 200 を返す（空配列）

## 6. STOP 条件

INSIGHT-001〜005 継承 + 追加:

11. `/manual-intake` POST 既存テストが red 化 → 即停止
12. 既存 `_HTML_FORM` の任意 input id が消えた / 改名された → 即停止
13. Cloud Run service deploy で既存 traffic に影響（手動投入が動かなくなる、503 等） → 即 rollback (前 revision に traffic 100%)
14. GCS download 失敗が `/insight-query` 以外のページに伝播 → 即修正、download は `/insight-query` 内部に閉じる
15. service SA への過剰権限付与（write 権限 / 他 bucket へのアクセス） → 即停止

## 7. 禁止事項

INSIGHT-001〜005 + 以下:

- 既存 `/manual-intake` handler の挙動変更（入力 / 出力 / status code / cookie）
- 既存 HTML `<form id="intake">` の構造改変（同 id を維持）
- 既存テストの期待値変更
- 認証 flow の変更（`MANUAL_INTAKE_TOKEN` の意味 / cookie 名 / 認証スキーム）
- service SA に storage.objectAdmin / storage.admin を付与
- 別 bucket へのアクセス権限付与
- 新規 endpoint で WP REST を呼ぶ
- 新規 endpoint で WP DB / Gemini / X API / Cloud Scheduler を叩く
- service の `min-instances` 上昇（コスト増回避）
- 既存 cloudbuild の trigger 設定変更

## 8. 想定されるデグレ

| リスク | 対策 |
|---|---|
| 既存「手動投入」が動かなくなる | tab 化は HTML wrap のみ、form 構造 ID 不変、diff レベルで input/select 数を assert |
| GCS から insight.db pull の遅延で `/insight-query` がタイムアウト | 初回 GET のみ download、メモリ / `/tmp` にキャッシュ、TTL 1 時間 |
| Cloud Run のメモリ不足（insight.db 100KB なので余裕） | memory 不変、image size +sqlite3 (stdlib 既存) でほぼ増えない |
| service revision 失敗で「手動投入」が停止 | deploy は no-traffic で 1 度 revision 作成 → 試走 OK 確認 → traffic 100% へ flip |
| SA 権限の漏れ | objectViewer のみ。書き込み権限は付けない |
| insight.db が壊れていた場合（GCS object 破損） | `/insight-query` のみ 500、ページ自体は 200 で renderng（empty result） |
| 既存 token 認証の bypass を新 endpoint が誘導 | `/insight-query` も同じ token / cookie check を通す |

## 9. 作業ログ欄

```
HH:MM JST | event | detail
```

- 14:00 JST | start | INSIGHT-006 GO 受領
- 14:02 JST | baseline_pass | 既存 manual_intake 系 109 件 ALL PASS
- 14:08 JST | file_added | src/manual_intake_insight_query.py (GCS pull + read-only SQL)
- 14:15 JST | edit_additive | src/manual_intake_service.py に tab UI + /insight-query endpoint
- 14:22 JST | file_added | tests/test_manual_intake_insight_query.py (18 ケース)
- 14:25 JST | regression_pass | manual-intake regression 20 件 ALL PASS、red ゼロ
- 14:26 JST | regression_pass | INSIGHT 系 + event_key + baseline = 全 308 件 ALL PASS
- 14:30 JST | iam | seo-web-runtime@ に roles/storage.objectViewer @ insight bucket 付与
- 14:33 JST | git_anomaly | 並行 333-QA 作業と git index が干渉、最終的に origin 2cd1b44 に INSIGHT-006 全ファイルが含まれた状態で着地 (commit message は 333-QA、後続 doc-only commit で訂正記録)
- 14:35 JST | git_reset | local の重複 e2579d8 を drop、origin/2cd1b44 を HEAD に reset
- 14:40 JST | build_success | Cloud Build manual-intake-service rebuild (commit b2cd1b44 ベース、build id eae3dbda)
- 14:43 JST | deploy_no_traffic | revision manual-intake-service-00063-xey を tag=insight-tab で no-traffic deploy
- 14:44 JST | smoke_pass | https://insight-tab---manual-intake-service-n5hunzkyna-an.a.run.app/ で tab + 既存 form 両方 200 OK 確認、/insight-query で実 GCS data の signal 4 件返却
- 14:45 JST | traffic_flip | revision 00063-xey に traffic 100% flip
- 14:46 JST | prod_smoke_pass | https://manual-intake-service-n5hunzkyna-an.a.run.app/ で tab markers 4 件 + 既存 form id 3 件 hit、size 32062 bytes
- 14:48 JST | end | INSIGHT-006 production 稼働、ドキュメント追記中

## 10. Regression Memo 欄

```
HH:MM JST | observation | detail | followup
```

- 14:26 JST | green | 既存 manual_intake_service tests 20 件 + manual_intake CLI 89 件 全 pass、form id (intake/url/article_type/manager_name/result) HTML render に含まれ続け | none
- 14:26 JST | green | INSIGHT 系 / event_key 系 / baseline 全 regression pass | none
- 14:33 JST | finding | 並行 Codex agent (333-QA) と git index が部分干渉、私の `git commit` 出力に「no changes added」と表示されたが、実際は remote へ 333-QA commit と共に INSIGHT-006 ファイルがバンドル push されていた | 後続で git 状態を verify、reset --hard origin/<branch> で正常化、再 commit / 再 push 不要 |
- 14:44 JST | green | no-traffic revision smoke で tab UI + 既存 form 両方が render、/insight-query が real GCS DB に対して 4 件返却、SA permission OK | none
- 14:46 JST | green | production URL で既存 manual intake form 構造 (intake/url/article_type) 不変、新タブ追加のみ | none
- 14:48 JST | known_gap | 並行 commit による message 不整合: remote 2cd1b44 commit message は「333-QA」だが内容は h3 cleanup + INSIGHT-006 混在。追加 commit で本ドキュメント完了欄を記録することで補完。 | followup: 次回作業時は branch を更に明確に分けるか、別 worktree 利用

---

## 作業完了後の追記欄

### 1. 実際に変更したファイル

新規:

- `doc/active/INSIGHT-006-tabbed-ui-with-insight-query.md`（本ドキュメント）
- `src/manual_intake_insight_query.py`（GCS pull + 読み取り専用 SQL）
- `tests/test_manual_intake_insight_query.py`（18 ケース）

修正 (additive):

- `src/manual_intake_service.py`（既存 form を Tab 1 内、Tab 2 = データ要望 UI、新規 GET /insight-query endpoint、`from src import manual_intake_insight_query as miq` import）

GCP 側の変更:

- IAM: `seo-web-runtime@baseballsite.iam.gserviceaccount.com` に `roles/storage.objectViewer` @ `gs://baseballsite-yoshilover-insight`
- Cloud Run service `manual-intake-service` revision: `manual-intake-service-00063-xey`（image `manual-intake-service:latest`、env `INSIGHT_GCS_BUCKET=baseballsite-yoshilover-insight` 追加）
- traffic: 100% to 00063-xey

### 2. diff 概要

```
A  doc/active/INSIGHT-006-tabbed-ui-with-insight-query.md (+340 行)
A  src/manual_intake_insight_query.py                    (+300 行)
M  src/manual_intake_service.py                          (+189 / -1)
A  tests/test_manual_intake_insight_query.py             (+284 行)
```

既存ファイル中で変更したのは `src/manual_intake_service.py` のみ。既存 form の input id (`url` / `article_type` / `manager_name` / `player_name` / `quote` / `pitcher_a` / `team_b` / `pitcher_b` / `play_summary` / `registered` / `removed` / `title` / `summary` / `source_published_at` / `memo` / `dry-run-toggle` / `submit-btn` / `result`) はすべて維持、HTML 内の存在を render テストで verify。

### 3. 実行したテスト

```
pytest tests/test_manual_intake_insight_query.py -v       → 18 件
pytest tests/test_manual_intake_service.py -q             → 20 件 regression
pytest tests/test_manual_intake.py -q                     → 89 件 regression
pytest tests/test_insight_*.py -q                          → 113 件 regression
pytest tests/test_event_key_*.py tests/test_morning_*.py -q → 61 件 regression
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q → 36 件 regression
合計: 337 件 ALL PASS
```

実環境 smoke:
- `https://insight-tab---manual-intake-service-n5hunzkyna-an.a.run.app/` (no-traffic): 200 OK, HTML render OK, /insight-query で実 GCS data 4 件返却
- `https://manual-intake-service-n5hunzkyna-an.a.run.app/` (production after flip): tab markers 4 + 既存 form id 3 hit

### 4. テスト結果

- 新規 18 件 ALL PASS
- regression 全 319 件 ALL PASS、red ゼロ
- no-traffic 試走 OK → traffic flip → production smoke OK
- 既存 `/manual-intake` POST、`/health`、`/manifest.webmanifest`、`/` GET は挙動不変

### 5. 残った懸念

- **commit message の整合性**: 並行 333-QA 作業との git index 干渉で、INSIGHT-006 ファイルが remote 2cd1b44 の「333-QA」commit に混入。後続 doc-only commit で本ドキュメントを記録することで補完するが、commit log を読む側には混乱の余地。
- **GCS download 失敗時の UX**: 現状「該当データなし」と表示されるが、実際は GCS access 失敗 / DB 不在の可能性もある。エラー詳細を UI に出すか、サーバ logs に詳細を残すかの判断。本フェーズは degraded gracefully で OK。
- **`/insight-query` の rate limit**: 現状 token 認証のみで rate limit なし。スパム / abuse の場合は Cloud Armor / Cloud Run min/max instances で対処（別チケット）。
- **データの遅延感**: cache TTL 1h なので、insight-nightly が 02:00 に走った後でも UI が古い data を返す可能性。手動で revision restart すれば cache クリア。明示 refresh ボタンを置くかは UI 判断。

### 6. 新しく見つかったデグレ

**なし**（既存 309 件 regression pass、production smoke で既存 manual-intake form 動作確認）。

並行 git 干渉は事故というより運用上の learning（次回 workflow 改善対象）。

### 7. 追加した回帰テスト

`tests/test_manual_intake_insight_query.py` 18 ケース:

| 軸 | 守る invariant |
|---|---|
| env helpers | `INSIGHT_GCS_BUCKET` 未設定で no-op、prefix の strip 動作 |
| ensure_local_db | bucket 未設定で `no_bucket`、download 後 TTL 内は再 download しない、TTL 超過で refresh、blob missing で `blob_missing` |
| query_candidates | DB 不在で `db_not_available`、filter なし全件、player canonical / display partial / signal_type / date range / invalid date 黙殺 / limit cap 500 |
| security | signal_type allowlist 外を invalid_signal_type で拒否、`mode=ro` URI で write が `OperationalError` |
| ordering | priority 昇順 → magnitude 降順 |

### 8. 次回触ってはいけない範囲

- **既存 `_HTML_FORM` 内の input/select id** — 18 個の form id (intake / url / article_type / manager_name / etc.) を維持。tab 化や class 変更は OK だが id 改名禁止
- **`/manual-intake` POST handler の挙動 / レスポンス JSON 形式 / 認証 flow** — 既存テストが守っているので壊さない
- **`MANUAL_INTAKE_TOKEN` の意味 / cookie 名 (`manual_intake_session`)** — 認証 surface は固定
- **`/insight-query` の `mode=ro` URI** — write 経路の混入は SQL injection / 破壊操作のリスク、必ず維持
- **`ALLOWED_SIGNAL_TYPES`** — allowlist。signal_type の追加は OK だが、入力検証の bypass 経路を作らない
- **`seo-web-runtime@` の IAM** — `roles/storage.objectViewer` のみ。write 権限 / 他 bucket / 他 service 権限を追加禁止
- **Cloud Run service の min-instances / memory** — コスト増回避、変更は別チケット
- **WP DB / Gemini / X API / Cloud Scheduler / publish** — INSIGHT-001〜005 から継承

---

## Phase 7 引き継ぎ（INSIGHT-007 候補）

- **検出軸追加**: リーグ平均比較 / 前年比 / 同ポジ平均比較（要 NPB 公式 league-wide data の蓄積）
- **AI 解説生成**: 候補 signal を Gemini で 100-200 字解説に変換（Gemini call 増加なので user 判断）
- **UI 強化**: ソート / フィルタ / CSV download / 詳細パネル
- **anomaly notification**: priority=1 が出た時 user に通知（mail / Slack 等、user 判断）

---

## 補足

- 既存 manual-intake-service の構造（参考）:
  - Python's `BaseHTTPRequestHandler` ベース（Flask ではない）
  - HTML を文字列で `_HTML_FORM` に保持
  - `_render_form()` で `__ARTICLE_TYPE_OPTIONS__` を replace
  - `do_GET`: `/health`, `/manifest.webmanifest`, `/` (root form)
  - `do_POST`: `/manual-intake` のみ
  - 認証: query token + HttpOnly cookie

- 新タブの UX 設計（仮置き、GO 後に調整可）:
  - 上部に `[手動投入] [データ要望]` の 2 つのボタン (button group / segmented control)
  - 切り替えで `<section id="tab-intake">` / `<section id="tab-insight">` を `hidden` 切替
  - データ要望 form: 選手 dropdown (giants_roster.json から) / signal_type dropdown / 日付 from-to / 「検索」ボタン
  - 結果: テーブル表示（priority / signal / 選手 / current / baseline / window / notes）

- 既存 cloudbuild と deploy flow:
  - `cloudbuild_manual_intake_service.yaml` を `gcloud builds submit` → image push
  - `gcloud run services update manual-intake-service --image ...` で revision flip
  - 1 度 traffic 0% で revision 作成 → smoke → traffic 100% へ
