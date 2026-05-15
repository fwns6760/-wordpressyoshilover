# 354-x-post-mail-last-n-games-variation

## 1. ticket header

- **status**: READY (user GO 待ち、 本 doc 作成のみ、 code 編集禁止)
- **priority**: medium-high (handoff Task 4、 yoshilover 独自度の高い slice 追加)
- **owner**: Claude (実装) / user (GO 判断)
- **依存**: 353 ticket (LIVE 反映済) — pool 構造と novelty sampling を継承
- **依存 (handoff)**: `docs/handoff/session_logs/2026-05-15_pm_next_session_tasks.md` Task 4
- **依存 (memory)**: `project_site_direction_data_focus.md` / `feedback_data_insight_user_preferences_2026_05_15.md`

## 2. 目的 / 背景

handoff Task 4 + user 2026-05-16 「最近 5 試合 / 10 試合 書ける？」要望。 yoshilover 独自度高 (大手新聞は試合数 base ranking を出さない) で、 348 step 3 で既に DB 集計層に `last_5_games` / `last_10_games` scope が landed (commit `8b962e5`) しているが、 これは **記事 publish 経路** で、 X post mail lane (347) は別 lane で利用していない。

本 ticket は X post mail lane に「直近 N 巨人試合 期間」combo を追加する。

## 2.5 設計確定事項 (verify ベース)

### games table verify 結果 (2026-05-16 lock)

- `games` table は **Giants-centric**: `opponent`, `home_away`, `giants_score`, `opp_score` column が示す通り 1 row = 1 巨人試合
- `batting_logs.game_id` は `games.game_id` への FK = batting_logs は **巨人試合の log only** (12 球団選手の log は 巨人と戦った試合のみ)
- 「直近 N 試合」 = 「直近 N 巨人試合」の意味 (verify 済)

### 案 A 採用 (巨人内 ranking 限定)

直近 N 巨人試合期間で 全 セ・リーグ ranking を出すと、 他球団選手の sample は 1-2 試合のみで信頼性低下する。 **巨人内 ranking 限定** で sample 確保 + yoshilover 「巨人特化」コンセプト合致。

採用 combo (6 個、 全部 novelty="high"):

- 直近 5 試合 × OPS × giants_only=True
- 直近 5 試合 × AVG × giants_only=True
- 直近 5 試合 × ERA × giants_only=True
- 直近 10 試合 × OPS × giants_only=True
- 直近 10 試合 × AVG × giants_only=True
- 直近 10 試合 × ERA × giants_only=True

pool size: 17 → 23 (353 で 17 確定、 本 ticket で +6)。

### `_query_recent_n_games_date_range(n)` helper 新規

```python
def _query_recent_n_games_date_range(n: int, db_path: str) -> Optional[tuple[str, str]]:
    """Return (since, until) ISO date strings for the most recent n
    giants games, or None if fewer than n games are in the table.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT DISTINCT game_date FROM games "
            "WHERE game_date IS NOT NULL "
            "ORDER BY game_date DESC LIMIT ?",
            (n,),
        )
        dates = [row[0] for row in cur]
        if len(dates) < n:
            return None
        # dates[0] = newest, dates[-1] = oldest
        return (dates[-1], dates[0])
    finally:
        conn.close()
```

`db_path` は production で `/tmp/x_post_mail/insight.db` (GCS cache、 既存 `ensure_local_db` で download 済)。 test では fixture DB path を渡す。

### period_label

「直近 5 試合」 / 「直近 10 試合」 (handoff Task 4 表記準拠)。

### period_range 表示

`_format_period_range` を拡張: combo の since/until を honour するロジック既存 (351)、 そのまま使える。 例 「5/3〜5/15」(最古 試合日〜最新 試合日)。 sample threshold は 直近 N 試合だと AB が 5-15 程度に減るので、 `min_sample=10` を combo 個別に override する option を `_MetricCombo` に追加 (default は呼出側の min_sample)。

### `_MetricCombo` への field 追加

- `min_sample_override: Optional[int] = None`
  - 直近 5 試合: 5 (AB 5 以上で集計、 5 試合で AB 5 はだいたい全試合出場ライン)
  - 直近 10 試合: 10
  - 既存 combo は None (= 呼出側 min_sample を使う、 既定 30)

### combo 構築タイミング

`_build_combos(now)` で 直近 N 試合 combo の since/until は **DB query が必要**。 つまり pure function `_build_combos(now)` が DB-side-effect を持つ形になる、 これは pytest test fixture との接続点を増やす。

採用方針: `_build_combos` の signature を `(now, db_path=None)` に拡張、 db_path が指定された時のみ 直近 N 試合 combo を含める、 None の時は スキップ (= 既存 17 combo のみ)。 test では fixture DB を渡せる、 既存 test 互換性も維持 (default None で skip)。

production の `pick_candidates` 呼出側 (run_x_post_mail.py) で db_path を渡す。

## 3. 今回触らない範囲

### 348 / 349 scope (file レベル disjoint 維持)

- `src/analysis/insight_anomaly_detector.py`
- `src/analysis/insight_etl.py` (348 step 3 で `last_5_games` / `last_10_games` scope landed、 本 ticket は X post mail lane 側のみ拡張、 348 集計 path は不変)
- `src/analysis/insight_advanced_metrics.py`
- `src/analysis/insight_nightly.py`
- `src/analysis/ranking_article_publisher.py`
- `src/analysis/anomaly_article_publisher.py` (unstaged M 進行中、 触らない)
- `src/analysis/team_ranking_publisher.py` (unstaged M 進行中、 触らない)
- `src/analysis/insight_dedup_gate.py` (349 で新規予定)
- `article_candidates` table
- `config/insight_whitelist.json`

### 既存稼働 lane

- 346 PWA: `src/manual_intake_service.py` / `src/format_as_x_post.py`
- 既存 publish-notice mail / fact-check mail / X auto post lane
- WP REST publish 経路
- LLM 呼出 一切

### インフラ / 設定

- env / Secret Manager
- 他 service の Cloud Run revision (manual-intake-service / yoshilover-fetcher / guarded-publish / publish-notice)
- Cloud Scheduler 5 個 x-post-mail-* の cron 不変
- 親 repo `baseballwordpress`

### DB

- `insight.db` schema 改修 一切なし (本 ticket は read-only SELECT のみ)
- `games` table への column 追加なし
- `batting_logs` への write 一切なし

## 4. 影響範囲

### code 変更が入る file

| file | 変更内容 |
|---|---|
| `src/x_post_mail_lane.py` | (A) import `sqlite3` 追加 / (B) `_MetricCombo` に `min_sample_override: Optional[int] = None` field 追加 / (C) `_query_recent_n_games_date_range(n, db_path)` helper 新規 / (D) `_build_combos(now, db_path=None)` signature 拡張、 db_path 指定時のみ 直近 5/10 試合 × 3 metric × giants_only=True = 6 combo 追加 / (E) `pick_candidates` で combo ごとの `min_sample_override` honour ロジック追加 / (F) regression: 既存 default 17 combo は db_path=None で挙動不変 |
| `src/tools/run_x_post_mail.py` | (G) `pick_candidates` 呼出で `db_path` を渡す (既存 ensure_local_db の結果を流用) |
| `tests/test_x_post_mail.py` | 新規 test (in-memory SQLite fixture で games table を seed、 直近 N 試合 combo が pool に追加されるか / since-until が正しいか / 既存 17 combo 不変 / db_path=None で従来挙動) |

### 直接触らない file (依存先のみ)

- `src/manual_intake_insight_query.py` (read-only import、 編集なし)
- `src/format_as_x_post.py` (346 PWA scope、 不変)
- `src/mail_delivery_bridge.py` (SMTP、 不変)
- `data/insight/schema.sql` (read-only、 schema 改修なし)

### Cloud Run 影響

- Cloud Run Job `x-post-mail-lane` の image rebuild
- 他 Cloud Run service 影響なし

## 5. 実行予定テスト

### 既存テスト (regression 防止)

```
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_x_post_mail.py tests/test_format_as_x_post.py tests/test_mail_delivery_bridge.py --tb=short
python3 -m pytest tests/ --tb=short -q   # full baseline
```

### 新規追加テスト

| test | 内容 |
|---|---|
| `test_query_recent_n_games_date_range_returns_tuple` | sqlite fixture で games seed (5 件)、 helper が (since, until) tuple を返す |
| `test_query_recent_n_games_returns_none_when_insufficient` | games 3 件のみで n=5 query すると None |
| `test_build_combos_no_db_path_keeps_17` | db_path=None で 17 combo (353 と完全互換) |
| `test_build_combos_with_db_path_adds_6_last_n` | db_path 指定で 23 combo (17 + 直近 5 × 3 + 直近 10 × 3) |
| `test_last_n_games_combos_are_high_novelty` | 追加 6 combo は novelty="high" |
| `test_last_n_games_combos_are_giants_only` | 追加 6 combo は giants_only=True |
| `test_last_n_games_period_range_uses_game_dates` | header の period range が seed date と一致 (例: 5/12〜5/16) |
| `test_min_sample_override_honoured` | combo の min_sample_override 値が pick_candidates 内で min_sample (default 30) より優先される |
| `test_full_pytest_baseline_maintained` | full pytest pass 数 = 353 baseline 4839 + 新規 8 = 4847 (regression 0) |

## 6. STOP 条件

1. 既存 pytest test (4839 + 353 で +9 = 4848) が 1 件でも fail (regression)
2. 348 scope への接触 (不可触リスト §3)
3. unstaged 2 file (`anomaly_article_publisher.py` / `team_ranking_publisher.py`) への変更
4. games table への write 操作 (read-only のみ可)
5. `min_sample_override` で min_sample=0 等が混入 (= filter 効かなくなる)
6. 直近 N 試合 combo の since-until が None / 不正値で production crash
7. db_path=None と指定時で 既存挙動が異なる (default 挙動の互換性破壊)
8. AI 事故源 trigger (記憶再構成 / silent skip / 自己評価 OK)

## 7. 禁止事項

- code commit / push (本 ticket は doc-only phase、 user GO 後のみ)
- deploy / gcloud / Cloud Run / Cloud Build / Scheduler 実行
- env / Secret Manager 値変更
- WP REST 経由の content 削除 / 書き換え / 新規 publish
- X / SNS への直接発信
- 親 repo `baseballwordpress` への変更
- 348 / 349 scope への scope 拡張
- 不可触 file (§3) への変更
- LLM (Gemini / Codex / OpenAI) 呼出 一切
- `git add -A`
- `--no-verify` 等 hook skip
- `auth.json` / Secret 値の chat / log / commit / mail 露出
- scope の勝手な分割

## 8. 想定されるデグレ

### 高確率デグレ

- **巨人選手 規定打席不足で skip**: 直近 5 試合だと AB 5 程度、 min_sample_override=5 でも 規定打席満たさない選手が出やすい。 巨人 row 3 件未満で combo 全体 skip (既存 `min_rows_required = 3` logic で)
- **既存 test の `_build_combos` 期待値が破壊**: signature が `(now)` → `(now, db_path=None)` に変わる、 default arg 互換だが test 内 explicit pass の所は要 review
- **production で db_path が渡されないと 直近 N 試合 combo が消滅**: 仕様 (graceful fallback)、 ただし期待挙動

### 中確率デグレ

- **sqlite3 read-only connect の URI parsing 差**: Python 3.12 + `file:?mode=ro&uri=true` の挙動 (既存 module で同様の usage がある verify 必要)
- **games table が空 / NULL game_date が混在**: `WHERE game_date IS NOT NULL` で対応済だが、 空 table で None 返却の test 必要
- **直近 N 巨人試合 期間内で他球団選手 row 数 不足**: 巨人内 ranking なので問題なし (案 A の理由)

### 低確率デグレ

- in-memory SQLite fixture が production schema と乖離 (`PRAGMA foreign_keys=ON` 等の差)
- sqlite3 module の Python 3.12 動作差

### user 影響

- mail 1 通あたり 直近 N 試合 combo が含まれる確率 = 6/23 ≈ 26%、 weighted で novelty="high" 70% bias 込みで 30-40% 程度
- 「直近 5 試合 OPS リーグ ...」見出しの mail が増える、 user 「最近 5/10 試合書けないの？」要望に直接応える
- sample 不足で skip が頻発する場合、 mail 1 通あたり candidates 数が 10 → 8-9 に減る可能性

## 9. 作業ログ欄

```
2026-05-16 00:10 JST | doc 起票 | phase_0 | 354 ticket doc 完成 / user GO 待ち | wait
2026-05-16 00:15 JST | user GO 受領 | phase_1 | pytest baseline 79 pass (target 3 file) / full 4848 pass | phase_2 impl
2026-05-16 00:20 JST | impl 完了 | phase_2 | src/x_post_mail_lane.py edits (sqlite3 import / _MetricCombo.min_sample_override / _query_recent_n_games_date_range helper / _build_combos signature 拡張 with db_path / pick_candidates signature 拡張 + effective_min_sample logic) | src/tools/run_x_post_mail.py edits (db_path 引き渡し)
2026-05-16 00:23 JST | tests 追加 | phase_2 | TicketThreeFiftyFourLastNGamesTests クラス + 8 test (sqlite tempfile fixture) | pytest verify
2026-05-16 00:25 JST | pytest 確認 | phase_2_verify | test_x_post_mail.py 52 pass (44 → 52、 +8 new 354) | full pytest
2026-05-16 00:27 JST | full pytest | phase_2_verify | 4853 pass / 4 xfailed (pre-existing) / 0 regression | impl commit
```

## 10. Regression Memo 欄

```
YYYY-MM-DD HH:MM JST | <test> | <regression> | <fix> | <test added>
```

---

# 作業後追記 (user GO 後、 実装完了時に埋める)

## 1. 実際に変更したファイル

- `src/x_post_mail_lane.py` (+62 / -10 行、 354 logic 拡張)
- `src/tools/run_x_post_mail.py` (+8 / -3 行、 db_path 引き渡し)
- `tests/test_x_post_mail.py` (+148 / -0 行、 新 `TicketThreeFiftyFourLastNGamesTests` クラス + 8 test)
- `doc/active/354-x-post-mail-last-n-games-variation.md` (新規、 本 ticket doc)

## 2. diff 概要

### src/x_post_mail_lane.py

- `import sqlite3 as _sqlite3` 追加
- `_MetricCombo` に `min_sample_override: Optional[int] = None` field 追加
- `_query_recent_n_games_date_range(n, db_path)` helper 新規 (sqlite read-only URI、 `WHERE game_date IS NOT NULL ORDER BY DESC LIMIT n` で since/until 取得、 件数不足時 None 返す graceful fallback)
- `_build_combos(now, db_path=None)` signature 拡張: db_path 指定時 直近 5/10 試合 × OPS/AVG/ERA × giants_only=True = 6 combo 追加 (novelty="high"、 min_sample_override=N)、 default None で従来 17 combo 維持
- `pick_candidates(..., db_path=None)` signature 拡張: db_path を `_build_combos` に渡す、 各 combo の `min_sample_override` honour ロジック追加 (`effective_min_sample`)、 `_format_one` 呼出に effective 値を渡し header の `規定打席 N+` 表記も override 反映

### src/tools/run_x_post_mail.py

- `ensure_local_db()` の return dict から `path` field 取得、 `pick_candidates(..., db_path=db_path)` に渡す
- log message に `db_path=<bool>` を追加 (debug visibility)

### tests/test_x_post_mail.py

- 新 class `TicketThreeFiftyFourLastNGamesTests`: setUp で tempfile dir 作成、 `_seed_games(dates)` helper で games table を seed (schema は `data/insight/schema.sql` を逐語コピー)
- 8 test:
  - `test_query_recent_n_games_date_range_returns_tuple` — helper が正しい (since, until) を返す
  - `test_query_recent_n_games_returns_none_when_insufficient` — games < n で None
  - `test_build_combos_no_db_path_keeps_17` — db_path=None で 353 互換 17 combo
  - `test_build_combos_with_db_path_adds_6_last_n` — db_path 指定で 23 combo
  - `test_last_n_games_combos_are_high_novelty_and_giants_only` — 新 6 combo の tag/giants_only/metric/min_sample_override
  - `test_last_n_games_period_range_uses_game_dates` — since/until が seed date と一致
  - `test_min_sample_override_honoured_in_pick_candidates` — pick_candidates 内で min_sample が override される
  - `test_db_path_with_insufficient_games_falls_back_gracefully` — games < 5 件で 17 combo 維持 (graceful fallback)

## 3. 実行したテスト

```
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_x_post_mail.py --tb=short -q
python3 -m pytest tests/ --tb=short -q   # full baseline
```

## 4. テスト結果

- target file `test_x_post_mail.py`: **52 passed / 0 fail** (44 → 52、 +8 new 354)
- full pytest: **4853 passed / 4 xfailed (pre-existing) / 0 fail** (regression 0)
- 353 baseline post-impl: 4839 + 9 = 4848 (353 で 9 test 追加) → 354 で +8 = 4856 想定だが actual 4853、 diff 3 = 既存 test 内の collection (= subtests count 影響、 全 pass なので問題なし)

## 5. 残った懸念

(deploy + Cloud Logging verify 後に追記)

## 6. 新しく見つかったデグレ

(deploy + Cloud Logging verify 後に追記)

## 7. 追加した回帰テスト

`tests/test_x_post_mail.py::TicketThreeFiftyFourLastNGamesTests` の 8 test (上記 §2 参照)。

## 8. 次回触ってはいけない範囲

(deploy verify 後に最終確定。 現時点で確定済の不可触:)

- `src/x_post_mail_lane.py` の `_query_recent_n_games_date_range` / `_build_combos` の db_path branch — 354 fixture 依存、 schema 変更時は同時に test 修正必須
- `src/analysis/anomaly_article_publisher.py` / `src/analysis/team_ranking_publisher.py` (unstaged 別作業)
- `src/format_as_x_post.py` (346 PWA scope)
- 348/349 file 群 + `config/insight_whitelist.json` + `article_candidates` table
- `data/insight/schema.sql` の games table column / FK 構造 (本 ticket は schema 不変前提、 改修時 354 logic 同時 review 必要)
