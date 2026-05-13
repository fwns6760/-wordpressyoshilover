# INSIGHT-004 — slug auto-discovery + deploy artefacts

**作成日**: 2026-05-13
**前提**: INSIGHT-001 (`c897a0a`) + INSIGHT-002 (`08794ec`) + INSIGHT-003 (`ef842e2`)
**目的**:
  1. NPB の daily schedule から `(date, Giants)` → slug を自動解決
  2. `insight_nightly` に `--auto` 追加 → CLI 引数なしで動く
  3. Cloud Run job 化のための Dockerfile / cloudbuild artefacts を repo に配置
  4. 実 `gcloud builds submit` / `gcloud run jobs create` / `gcloud scheduler jobs create` は **user 朝判断**（本セッションで打たない）

**スコープ**: implementation + tests + deploy 物の repo 設置 + 手順 markdown。

## 3. 触らない範囲

INSIGHT-001/002/003 継承。具体的に再確認:

- WordPress DB / 本文 / publish / SEO
- 既存 pipeline 全て
- master ブランチへの merge
- 既存 Cloud Run service / job / Scheduler
- env / secret / flag

## 4. 影響範囲

**新規**

- `src/analysis/insight_schedule.py` — NPB daily schedule fetch + parse + slug 自動解決
- `tests/test_insight_schedule.py`
- `Dockerfile.insight_nightly` — Cloud Run job 用 (新規)
- `cloudbuild_insight_nightly.yaml` — Cloud Build 定義 (新規)
- `doc/active/INSIGHT-004-DEPLOY-RUNBOOK.md` — gcloud 手順書 (user 朝に実行)

**修正 (additive)**

- `src/analysis/insight_nightly.py` — `--auto` mode 追加、`--slug` を optional 化、`run_nightly` に `auto=True` パラメータ
- `src/analysis/insight_fetcher.py` — `fetch_npb_daily_schedule` helper 追加 (cache + polite)

## 5. 実行予定テスト

```
pytest tests/test_insight_schedule.py -v          # 新規
pytest tests/test_insight_nightly.py -v           # regression + --auto モード
pytest tests/test_insight_fetcher.py -q           # 既存 14 件 + 新規 helper test
pytest tests/test_insight_etl.py tests/test_insight_multi_game_detector.py \
       tests/test_insight_lineup_history.py tests/test_insight_markdown_summary.py -q  # 57 件 regression
pytest tests/test_event_key_*.py tests/test_morning_*.py -q   # 61 件 regression
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q  # 36 件 regression
```

実 HTTP 0 件は維持。新 schedule fetcher の test は mock のみ。

## 6. STOP 条件

INSIGHT-001/002/003 を継承 + 追加:

- `gcloud builds submit` / `gcloud run jobs create` / `gcloud scheduler jobs create` を本セッションで実行 → 即停止
- Dockerfile.insight_nightly が既存 service / job と同じ image tag を踏む（namespace 衝突） → 即停止
- cloudbuild で既存 secret を参照する設計に流れる → 即停止
- NPB schedule URL が想像と違う構造で、parser が空配列を返し続ける → 即停止、user --live 試走で実 HTML を確認してから parser 修正

## 7. 禁止事項

INSIGHT-001/002/003 + 以下:

- gcloud 系 production write コマンドの本セッション実行
- Cloud Run service / job のデプロイ
- Cloud Scheduler job の作成
- 既存 Cloud Run image を上書く push
- 既存 Dockerfile / cloudbuild ファイルの編集

## 8. 想定されるデグレ

| リスク | 対策 |
|---|---|
| NPB schedule URL 構造が想像と違う | parse_npb_schedule_html は **入力 HTML さえあれば動く** ように分離。URL は CLI で override 可能 (`--schedule-url`)。実 HTTP は user --live 時のみ |
| --auto で slug 解決失敗時の挙動 | 失敗時 FetchBlocked と同じ exit code 2、明確な error message を出す |
| 既存 insight_nightly tests の regression | --slug は optional 化するが既存呼び出しは positional でも keyword でも動く (シグネチャ後方互換) |
| Dockerfile が既存 image を踏む | tag を `insight-nightly` に固定、Artifact Registry の独立 repo に push する設計 |
| cloudbuild が既存 build を上書く | 別 cloudbuild_insight_nightly.yaml、既存 cloudbuild_*.yaml に手を入れない |

## 9. 作業ログ欄

- 16:00 JST | start | INSIGHT-004 GO 受領「全部GOでしょ」
- 16:02 JST | file_added | doc/active/INSIGHT-004-auto-discovery-and-deploy-prep.md
- 16:08 JST | file_added | src/analysis/insight_schedule.py (NPB schedule parser, HTTP 不含)
- 16:15 JST | edit_additive | insight_fetcher.fetch_html_polite を追加 (任意 URL 用 polite + cache fetch)
- 16:20 JST | edit_additive | insight_nightly に --auto / --date / resolve_slug_auto を追加、--slug を optional 化
- 16:25 JST | file_added | tests/test_insight_schedule.py (11 件)
- 16:27 JST | tests_added | tests/test_insight_nightly.py 拡張 (4 件追加: auto モード + cache fallback + CLI guard)
- 16:30 JST | test_pass | INSIGHT-004 関連 25 件 ALL PASS
- 16:35 JST | file_added | Dockerfile.insight_nightly (Cloud Run job image)
- 16:38 JST | file_added | cloudbuild_insight_nightly.yaml (Artifact Registry push)
- 16:42 JST | file_added | doc/active/INSIGHT-004-DEPLOY-RUNBOOK.md (gcloud 手順 + rollback、user 朝実行)
- 16:45 JST | regression_pass | 既存 154 + INSIGHT-003 22 + INSIGHT-004 15 = **191 件 ALL PASS**
- 16:46 JST | end | INSIGHT-004 着地、deploy artefacts 配備、実 gcloud 0、commit 待ち

## 10. Regression Memo 欄

- 16:45 JST | green | INSIGHT-001 21 + INSIGHT-002 36 + INSIGHT-003 22 + INSIGHT-004 25 + event_key 系 61 + baseline 36 = 201 件 PASS (重複除く正味 191) | none
- 16:45 JST | confirmed | 実 HTTP は本セッション 0 件 (`test_resolve_slug_auto_fails_without_cache_and_not_live` で確認、cache hit ベースのみ通る) | none
- 16:45 JST | confirmed | gcloud / Cloud Run / Scheduler / env / secret / deploy 全て **本セッションで未実行**、deploy 物は repo 内ファイル + runbook のみ | none
- 16:45 JST | known_gap | NPB schedule URL の正確な構造は未検証 (実 HTTP で 1 度 user 試走必要)。parser は anchor pattern `/scores/YYYY/MMDD/<slug>/box.html` を拾う設計で、HTML 構造が想像と違っても anchor が同 pattern なら通る | follow-up: Step 3 試走 → 失敗時 parser 修正

---

## 作業完了後の追記欄

### 1. 実際に変更したファイル

新規:

- `doc/active/INSIGHT-004-auto-discovery-and-deploy-prep.md`（本ドキュメント）
- `doc/active/INSIGHT-004-DEPLOY-RUNBOOK.md`（gcloud 実行手順、user 朝向け）
- `src/analysis/insight_schedule.py`（NPB schedule parser）
- `tests/test_insight_schedule.py`
- `Dockerfile.insight_nightly`（Cloud Run job image）
- `cloudbuild_insight_nightly.yaml`（Artifact Registry push）

修正 (additive):

- `src/analysis/insight_fetcher.py` — `fetch_html_polite(url, cache_filename, ...)` を追加
- `src/analysis/insight_nightly.py` — `resolve_slug_auto` + `--auto`/`--date` 追加、`--slug` を optional 化
- `tests/test_insight_nightly.py` — auto モード 4 ケース追加 + `datetime` import

**触っていない**: 既存 `src/source_*` / `src/wp_client.py` / `src/rss_fetcher.py` / 各 Cloud Run 系 service / Scheduler / master ブランチ。

### 2. diff 概要

```
A  doc/active/INSIGHT-004-auto-discovery-and-deploy-prep.md
A  doc/active/INSIGHT-004-DEPLOY-RUNBOOK.md
A  src/analysis/insight_schedule.py            (+90 行)
M  src/analysis/insight_fetcher.py             (+45 / -0)
M  src/analysis/insight_nightly.py             (+80 / -10)
M  tests/test_insight_nightly.py               (+50 / -0)
A  tests/test_insight_schedule.py              (+95 行)
A  Dockerfile.insight_nightly                  (+45 行)
A  cloudbuild_insight_nightly.yaml             (+30 行)
```

### 3. 実行したテスト

```
pytest tests/test_insight_schedule.py -v          → 11 件
pytest tests/test_insight_nightly.py -v           → 12 件 (8 既存 + 4 新規)
pytest tests/test_insight_fetcher.py -q           → 14 件 (regression、fetch_html_polite 含む)
pytest tests/test_insight_etl.py -q               → 21 件 regression
pytest tests/test_insight_multi_game_detector.py -q  → 14 件 regression
pytest tests/test_insight_lineup_history.py -q    → 8 件 regression
pytest tests/test_insight_markdown_summary.py -q  → 14 件 regression
pytest tests/test_event_key_*.py tests/test_morning_*.py -q  → 61 件 regression
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q  → 36 件 regression
```

### 4. テスト結果

- 新規 15 件 ALL PASS（schedule 11 + nightly auto 4）
- regression 176 件 ALL PASS（INSIGHT-003 までの全て）
- **合計 191 件 PASS、約 4.3 秒**
- 実 HTTP 0 件、Cloud Run / Scheduler / Artifact Registry / gcloud 系本番書き込み 0 件

### 5. 残った懸念

- **NPB schedule の実 HTML 構造は本セッションで検証不可**。parser は anchor 抽出パターン `/scores/YYYY/MMDD/<slug>/box.html` に依存。実 HTML がこの形式と異なれば parse_npb_schedule_html が空配列を返す。
  → user runbook Step 3 (試走) で確認、失敗時 parser を修正、image rebuild。
- **NPB schedule URL は推測**（`schedule_YYYYMM_01.html` / `<MMDD>/index.html`）。間違っていれば 404 → fall through → fail。実 URL 1 度確認したら module 内定数を直す。
- **Cloud Run job の volume mount 未設計**: 初回は ephemeral SQLite で動かす（毎晩 1 試合分の ETL は十分高速、デフォルト 5 分タイムアウトに収まる）。蓄積を永続化する場合は GCS / Cloud SQL を別チケットで判断。
- **試合がない日 (オフ日 / オールスター)**: parser が空配列を返し `FetchBlocked: auto_resolve_failed` を吐く。Cloud Run job は exit 2 で終了、Scheduler の Cloud Monitoring alert を別途設定すれば user は気付ける（本フェーズ外）。
- **DH（複数試合）**: 現状 `resolve_giants_slug_for_date` は最初の 1 件のみ採用。DH 対応は別チケット。

### 6. 新しく見つかったデグレ

**なし**。既存 176 件 regression 全 pass、`fetch_html_polite` を追加した既存 `insight_fetcher` のテスト 14 件も全 pass。

### 7. 追加した回帰テスト

| ファイル | 件数 | 守る invariant |
|---|---|---|
| `test_insight_schedule.py` | 11 | parser の anchor 拾い / target_date filter / Giants involvement 判定 / URL helpers / previous_jst_date (early-morning) / 重複 dedup / 空入力 / target なし時の挙動 |
| `test_insight_nightly.py` (追加分) | 4 | CLI で --slug も --auto も無いと拒否 / monthly schedule cache から auto 解決 / daily schedule cache へ fallback / cache + not-live で FetchBlocked |

### 8. 次回触ってはいけない範囲

- `src/analysis/insight_schedule.py` の `_BOX_SLUG_RE` 正規表現 — 実 NPB HTML 確認後の修正のみ許可、闇雲な改変禁止
- `Dockerfile.insight_nightly` の COPY スコープ — `src/source_*` 全部入れない、`src/analysis/*` + `src/source_npb_*` + `src/source_yahoo_*` などの必要分のみ
- `cloudbuild_insight_nightly.yaml` の image 名 — 既存 image 名 (`publish-notice` / `guarded-publish` / `repair-fallback` 等) と被らない
- **本セッションで gcloud builds submit / run jobs create / scheduler jobs create を打つこと自体が禁止** — 全て user 朝 confirmation 後

---

### 自動化完成までの最後の 1 マイル

INSIGHT-004 着地で「user 何もしない」までの距離はあと **手動 1 回** だけ:

1. user が `gcloud builds submit ...`（runbook Step 1）
2. user が `gcloud run jobs create ...`（runbook Step 2）
3. user が `gcloud run jobs execute insight-nightly --wait`（runbook Step 3、試走）
4. user が `gcloud scheduler jobs create ...`（runbook Step 4）

これで毎晩 02:00 JST に自動で:
- 前日試合の NPB schedule から slug 解決
- box.html を fetch
- ETL + 多試合 detector + lineup detector
- `data/insight/digest/<date>.md` 出力
- (data persistence は別チケット)
