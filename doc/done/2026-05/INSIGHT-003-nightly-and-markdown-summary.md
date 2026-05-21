# INSIGHT-003 — nightly orchestrator + markdown digest

**作成日**: 2026-05-13
**前提**: INSIGHT-001 (`c897a0a`) + INSIGHT-002 (`08794ec`)
**目的**: 部品 (fetcher / ETL / multi-game / lineup) を 1 コマンドに束ねる + 朝レビュー用 markdown digest 出力。
**スコープ**: orchestrator + markdown export + 部品 1 件追加 (`etl_from_html`)。
**運用**: cache-first / dry-run safe / 実 HTTP は `--live` opt-in、Claude 自身は呼ばない。

---

## 3. 今回触らない範囲

- WordPress 全般（DB / 本文 / publish / SEO）
- 既存 pipeline (`rss_fetcher` / `guarded_publish_runner` / `wp_client` / `source_*`)
- `logs/*.jsonl`
- Cloud Scheduler / Cloud Run / env / secret / flag / deploy
- master ブランチ
- 既存 `src/analysis/insight_etl.py` の **public API シグネチャ**（破壊的改名禁止、**新関数の追加は許可**）
- INSIGHT-002 の `insight_fetcher` / `insight_multi_game_detector` / `insight_lineup_history` の挙動

## 4. 影響範囲

**新規追加**

- `src/analysis/insight_nightly.py` — 1 コマンドのオーケストレーション
- `src/analysis/insight_markdown_summary.py` — CSV → markdown digest
- `tests/test_insight_nightly.py`
- `tests/test_insight_markdown_summary.py`

**追加（既存 `insight_etl.py` への additive 変更）**

- `etl_from_html(html, game_id, ...) -> dict` — 新規 public 関数
- `etl_fixture(...)` は内部で `etl_from_html` を呼ぶように refactor（**public シグネチャ・戻り値 keys は維持**）
- 既存テストの期待値は変えない (regression must stay green)

**触らないファイル**: `src/source_*`, `src/wp_client`, `src/rss_fetcher`, `src/guarded_publish_runner`, INSIGHT-002 の 3 module, `config/*`, `logs/*`, `master`

## 5. 実行予定テスト

```
pytest tests/test_insight_nightly.py -v             # 新規
pytest tests/test_insight_markdown_summary.py -v    # 新規
pytest tests/test_insight_etl.py -v                 # 21 件 regression (etl_fixture 互換)
pytest tests/test_insight_fetcher.py -q             # 14 件 regression
pytest tests/test_insight_multi_game_detector.py -q # 14 件 regression
pytest tests/test_insight_lineup_history.py -q      # 8 件 regression
pytest tests/test_event_key_*.py tests/test_morning_*.py -q  # 61 件 regression
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q  # 36 件 regression
```

**Invariant**: nightly orchestrator のテストで実 HTTP を一切呼ばないことを spy で assert。

## 6. STOP 条件

INSIGHT-001 / 002 の STOP を継承 + 追加:

- `etl_fixture` の public 戻り値 keys が変わる（regression test の期待値が変わる必要がある状況）→ 即停止、refactor 設計し直し
- nightly orchestrator が cache miss 時にデフォルトで HTTP を呼ぶ実装になっている → 即停止
- markdown 出力が WP 本文を直接編集する経路を持つ → 即停止

## 7. 禁止事項

INSIGHT-001 / 002 を継承。本フェーズ固有:

- 既存 `etl_fixture` の戻り値 keys を消す / 改名する（追加は許可）
- nightly orchestrator から WP REST を呼ぶ
- markdown 出力を WP の本文として書き込む経路を作る
- 実 HTTP を test 中に走らせる
- 既存 `data/insight/insight.db` の destructive な `DROP TABLE` / `ALTER` を含むスクリプト追加

## 8. 想定されるデグレ

| リスク | 対策 |
|---|---|
| `etl_fixture` refactor で戻り値が変わる | regression test を緑のまま、戻り値 keys を維持する明示テストを足す |
| nightly が `--live` なしで実 HTTP 呼ぶ | `cache_or_fetch(allow_live=False)` を必ず経由、test で HTTP 0 件 assert |
| markdown summary が壊れたとき orchestrator が停止 | summary は best-effort、orchestrator は CSV まで担保したら成功扱い |
| 1 nightly で 複数試合 (DH 等) | 本フェーズは 1 nightly = 1 slug、複数試合は別 invocation |
| 旧 DB / 旧 CSV との混在 | schema は INSIGHT-001 のまま、`schema.sql` 変更しない |

## 9. 作業ログ欄

- 14:50 JST | start | INSIGHT-003 GO 受領「進めるよ」
- 14:52 JST | file_added | doc/active/INSIGHT-003-nightly-and-markdown-summary.md
- 14:55 JST | refactor | insight_etl.etl_from_html 追加 (additive), etl_fixture は wrapper 化、戻り値 keys 維持
- 14:57 JST | regression_pass | INSIGHT-001 既存 21 件 ALL PASS, refactor デグレなし
- 15:05 JST | file_added | src/analysis/insight_nightly.py (orchestrator, --slug / --live / --no-digest, fetched_html bypass)
- 15:08 JST | user_pivot | user 「コマンド打つの? 自動化のはず」→ 軌道修正: 今フェーズは parts 着地、auto-discovery + Scheduler は user GO 後の別フェーズと明示
- 15:15 JST | file_added | src/analysis/insight_markdown_summary.py (category 分類 / priority + magnitude 順 / table 出力 / 空入力ハンドリング)
- 15:25 JST | tests_added | tests/test_insight_nightly.py + test_insight_markdown_summary.py
- 15:30 JST | test_pass | 新規 22 件 ALL PASS (nightly 8 + markdown 14)
- 15:32 JST | regression_pass | 既存 154 件 + 新規 22 = 176 件 ALL PASS
- 15:34 JST | end | INSIGHT-003 着地, commit 待ち

## 10. Regression Memo 欄

- 15:30 JST | green | INSIGHT-001 21 + INSIGHT-002 36 + event_key 系 61 + baseline 36 = 154 件 regression PASS | none
- 15:30 JST | green | insight_etl.etl_fixture の戻り値 keys 不変、既存 test の期待値そのまま pass | none
- 15:30 JST | confirmed | 実 HTTP は本セッション 0 件、`test_nightly_does_not_invoke_http_when_cache_hits` で `requests.get` spy ゼロ確認 | none
- 15:30 JST | confirmed | WP REST / Gemini / X API 呼び出しゼロ、既存 logs/*.jsonl 書き込みゼロ | none
- 15:30 JST | confirmed | Cloud Scheduler / env / secret / deploy 全て不変 | none
- 15:33 JST | known_gap | --auto モード (slug auto-discovery from NPB daily schedule) は本フェーズ未着手。INSIGHT-004 で対応予定 | follow-up: NPB schedule URL 構造を実 HTTP で確認後、polite fetcher 拡張

---

## 作業完了後の追記欄

### 1. 実際に変更したファイル

新規:

- `doc/active/INSIGHT-003-nightly-and-markdown-summary.md`（本ドキュメント）
- `src/analysis/insight_nightly.py`
- `src/analysis/insight_markdown_summary.py`
- `tests/test_insight_nightly.py`
- `tests/test_insight_markdown_summary.py`

修正 (additive):

- `src/analysis/insight_etl.py` — `etl_from_html` 関数を追加、`etl_fixture` は薄い wrapper に refactor。public 戻り値 keys 不変。

**触っていない**: `src/source_*` / `src/wp_client` / `src/rss_fetcher` / `src/guarded_publish_runner` / INSIGHT-002 の 3 module / `config/*` / `logs/*` / `master`

### 2. diff 概要

```
A  doc/active/INSIGHT-003-nightly-and-markdown-summary.md
M  src/analysis/insight_etl.py                  (+40 / -25 = additive refactor)
A  src/analysis/insight_nightly.py              (+200 行)
A  src/analysis/insight_markdown_summary.py     (+180 行)
A  tests/test_insight_nightly.py                (+170 行)
A  tests/test_insight_markdown_summary.py       (+200 行)
```

### 3. 実行したテスト

```
pytest tests/test_insight_nightly.py -v             → 8 件
pytest tests/test_insight_markdown_summary.py -v   → 14 件
pytest tests/test_insight_etl.py -q                → 21 件 (regression、refactor 不変)
pytest tests/test_insight_fetcher.py -q            → 14 件 (regression)
pytest tests/test_insight_multi_game_detector.py -q → 14 件 (regression)
pytest tests/test_insight_lineup_history.py -q     → 8 件 (regression)
pytest tests/test_event_key_*.py tests/test_morning_*.py -q → 61 件 (regression)
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q → 36 件 (regression)
```

### 4. テスト結果

- 新規 22 件 ALL PASS（nightly 8 / markdown_summary 14）
- regression 154 件 ALL PASS、red ゼロ
- **合計 176 件 PASS、約 4.1 秒**
- 実 HTTP は本セッション 0 件（cache 経由 + requests.get spy で確認）

### 5. 残った懸念

- **slug auto-discovery 未着手**: `--auto` モード未実装。user は手動で `--slug 2026/0510/d-g-08` を渡す必要がある。NPB の daily schedule URL を確認できれば自動化可能、INSIGHT-004 で着手。
- **Cloud Scheduler 設定**: user 判断境界、未着手。
- **markdown digest の中身**: 単発 game date を引数取る形のため、複数日 review を 1 ファイルで欲しい場合は別フラグが要る (`--since-run-ts`)。
- **NPB の試合振替・延期** (slug が日付からずれる) への対応未検証。

### 6. 新しく見つかったデグレ

**なし**。refactor (`etl_fixture` 内部実装変更) も既存 21 件 regression が全 pass、戻り値 keys / smoke 出力に変化なし。

### 7. 追加した回帰テスト

| ファイル | 件数 | 守る invariant |
|---|---|---|
| `test_insight_nightly.py` | 8 | (a) slug → game_id / game_date 変換、(b) end-to-end 動作 (cache + fixture)、(c) cache miss + not-live で FetchBlocked、(d) fetched_html bypass モード、(e) `--no-digest` の動作、(f) `requests.get` spy がゼロ件（実 HTTP 不在の canary）、(g) CLI blocks / runs |
| `test_insight_markdown_summary.py` | 14 | (a) categorize / excerpt / format_evidence、(b) 空入力 / unknown signal の挙動、(c) game_date filter / since_run_ts filter、(d) write_digest が DB なしでも空ファイル生成、(e) priority + magnitude 順序保証 |

### 8. 次回触ってはいけない範囲

- **`insight_etl.etl_fixture` の戻り値 keys**（INSIGHT-001 test がこれに依存）
- **`insight_nightly.run_nightly` の `allow_live=False` default**
- **`tests/test_insight_nightly.py::test_nightly_does_not_invoke_http_when_cache_hits`** の `requests.get` spy ゼロ assert（実 HTTP 混入 canary）
- **`insight_markdown_summary.CATEGORY_LABELS` の構造**（test が表構造を assert）
- **WP DB / Scheduler / env / deploy / X API / Gemini** ※継承

---

### Phase 4 引き継ぎ（INSIGHT-004 草案）

- **slug auto-discovery**: NPB daily schedule から (date, Giants) → slug を自動解決
- **Cloud Run job 化 + Scheduler 設定**: 1 commit で job/cloudbuild、user 判断で Scheduler enable
- **lineup pregame source**: 試合前スタメンも `lineups` に蓄積（既存 `source_yahoo_lineup_extractor` 流用）
- **守備指標 source**: NPB fielding ページ等から PO/A/E/DP を埋める
- **csv → AI 解説**: 候補ごとに Gemini で 100-200 字解説を付与（Gemini call 増加なので user 判断境界、保留）
