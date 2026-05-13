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

（着手で追記、user GO 後）

```
HH:MM JST | event | detail
```

## 10. Regression Memo 欄

（着手で追記）

```
HH:MM JST | observation | detail | followup
```

---

## 作業完了後の追記欄

### 1. 実際に変更したファイル
（TBD）

### 2. diff 概要
（TBD）

### 3. 実行したテスト
（TBD）

### 4. テスト結果
（TBD）

### 5. 残った懸念
（TBD）

### 6. 新しく見つかったデグレ
（TBD）

### 7. 追加した回帰テスト
（TBD）

### 8. 次回触ってはいけない範囲
（TBD）

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
