# INSIGHT-002 — live fetch + 多試合 detector + lineup 履歴

**作成日**: 2026-05-13
**前提**: INSIGHT-001 着地 (`c897a0a`) — schema / fixture ETL / 単試合 detector / CSV / 21 件 tests
**目的（user GO「１２３とやって」）**:
  1. NPB 公式 box の polite live fetch（cache + rate limit）
  2. 多試合 detector（z-score / streak / 前年比 等）
  3. lineup 履歴蓄積 + 起用 anomaly skeleton

**スコープ**: design + 実装 + tests。**実 HTTP は本セッションで叩かない**。
**運用方向**: INSIGHT-001 と同じ namespace 隔離原則を継承（`src/analysis/` のみ）。

---

## 3. 今回触らない範囲

INSIGHT-001 と同じ。再掲:

- WordPress DB / `wp_posts` / `wp_postmeta` / `wp_options` / custom table
- WP 本文 / publish status / noindex / canonical / 301 / SEO
- X auto-post / X API / Gemini call
- 既存 pipeline (`rss_fetcher` / `guarded_publish_runner` / `wp_client` / 各 `source_*`) への edit
- 既存 `logs/*.jsonl`
- Cloud Run / Cloud Scheduler / env / secret / flag
- master ブランチ
- INSIGHT-001 で着地済の `src/analysis/insight_etl.py` の **既存 public API**（追加は OK、destructive な改名は不可）

## 4. 影響範囲

**新規追加**

- `src/analysis/insight_fetcher.py` — polite live fetch + cache（実 HTTP は CLI `--live` 明示時のみ）
- `src/analysis/insight_multi_game_detector.py` — 多試合 z-score / streak / trend
- `src/analysis/insight_lineup_history.py` — lineup ETL + slot change 検出
- `tests/test_insight_fetcher.py` — mock requests でロジック検証、**実 HTTP は呼ばない**
- `tests/test_insight_multi_game_detector.py` — 合成多試合 SQLite データで検証
- `tests/test_insight_lineup_history.py` — fixture + mock で検証
- `data/insight/raw_html/` — fetcher の cache 保存先（ディレクトリのみ、内容は `.gitignore`）

**触らないファイル**

- `src/source_*` / `src/wp_client` / `src/rss_fetcher` / `src/guarded_publish_runner`
- `src/analysis/insight_etl.py` の既存関数（拡張は新 module 経由）
- 既存テスト（regression のみ確認）

**import 方向**

- `src/analysis/insight_fetcher` → `requests`（vendor）+ `urllib.parse` + stdlib のみ
- `src/analysis/insight_multi_game_detector` → `sqlite3` + stdlib のみ
- `src/analysis/insight_lineup_history` → `src.source_npb_postgame_extractor`（fixture 解析のみ、live は fetcher 経由）
- `src/analysis/*` 間の循環依存禁止（各 module は単独 import 可）

## 5. 実行予定テスト

```
pytest tests/test_insight_fetcher.py -v           # 新規 (mock HTTP)
pytest tests/test_insight_multi_game_detector.py -v   # 新規 (合成データ)
pytest tests/test_insight_lineup_history.py -v    # 新規
pytest tests/test_insight_etl.py -v               # 21 件 regression
pytest tests/test_event_key_*.py tests/test_morning_*.py -q  # 61 件 regression
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q  # 36 件 regression
```

**実 HTTP が走らないこと** を test_insight_fetcher で **明示的に assert** する（`requests.get` を monkeypatch + spy で呼び出しゼロを確認）。

## 6. STOP 条件（INSIGHT-001 継承 + 追加）

INSIGHT-001 の 10 項目を継承し、さらに:

11. テスト中に **実 HTTP** が走った形跡を検出（例: `requests.get` モック spy のカウントが想定外） → 即停止
12. `data/insight/raw_html/` 配下を `git add` してしまう（cache を commit してはいけない） → 即修正、`.gitignore` に追加
13. `robots.txt` 確認 → NPB 公式が disallow している path に触ろうとした → 即停止
14. fetch interval が 5 秒未満になる実装が混入 → 即修正
15. 同一試合の重複 fetch（cache miss していないのに live fetch する経路）が混入 → 即停止、cache-first の徹底

## 7. 禁止事項

INSIGHT-001 と同じ + 以下:

- **本セッション中の実 HTTP**（CLI `--live` で user が明示実行する場合を除く、Claude は実行しない）
- `data/insight/raw_html/*.html` の commit
- UA を偽装（ブラウザ偽装ではなく yoshilover-insight/X.Y のような正直な UA を使う）
- 並列スクレイピング（1 プロセス、5 秒間隔以上）
- robots.txt の無視

## 8. 想定されるデグレ

| リスク | 対策 |
|---|---|
| 実 HTTP が tests に紛れる | mock + spy で呼び出しゼロ assert |
| cache miss 時の予期せぬ live fetch | 既定 cache-only、`--live` opt-in 必須 |
| NPB が rate limit / IP block | 1 日 1 試合、5 秒間隔、`If-Modified-Since` 利用、cache 永続化 |
| 多試合 detector の base 数不足で誤検出 | window_n < min_baseline_n のとき detector は skip（NULL return）|
| lineup parse mismatch | 既存 NPB box の lineup 抽出に依存、fixture で検証 |
| schema migration 必要時 | 本フェーズは INSIGHT-001 schema を **そのまま** 使う（拡張なし）。新カラム必要なら別チケット |
| INSIGHT-001 既存挙動への影響 | 既存 `insight_etl.py` の edit ゼロ、別 module として並列 |

## 9. 作業ログ欄

```
HH:MM JST | event | detail
```

- 13:30 JST | start | INSIGHT-002 GO 受領「１２３とやって」
- 13:32 JST | file_added | doc/active/INSIGHT-002-live-fetch-multi-game-lineup.md
- 13:40 JST | file_added | src/analysis/insight_fetcher.py (polite NPB box fetch + cache + robots, --live opt-in)
- 13:42 JST | smoke | cache-only CLI run → blocked (期待動作)、HTTP 0 件
- 13:55 JST | file_added | src/analysis/insight_multi_game_detector.py (z-score / streak / workload / rest_days 4 detector)
- 14:10 JST | file_added | src/analysis/insight_lineup_history.py (lineup ETL + slot_jump / first_appearance 2 detector)
- 14:20 JST | tests_added | tests/test_insight_fetcher.py / test_insight_multi_game_detector.py / test_insight_lineup_history.py
- 14:25 JST | test_pass_partial | 33 pass / 3 fail (test 期待値ミス、detector 自体は正常)
- 14:27 JST | fix | hot/cold streak test の baseline を variance > 0 に修正、first_appearance test の `evidence` 参照方法修正
- 14:30 JST | test_pass | 新規 36 件 ALL PASS (fetcher 14 + multi_game 14 + lineup 8)
- 14:32 JST | regression_pass | 既存 118 件 (INSIGHT-001 21 + event_key 系 61 + baseline 36) ALL PASS, red ゼロ
- 14:35 JST | end | INSIGHT-002 design + 3 module + tests 完了、commit 待ち

---

## 作業完了後の追記欄

### 1. 実際に変更したファイル

新規:

- `doc/active/INSIGHT-002-live-fetch-multi-game-lineup.md`（本ドキュメント）
- `src/analysis/insight_fetcher.py`
- `src/analysis/insight_multi_game_detector.py`
- `src/analysis/insight_lineup_history.py`
- `tests/test_insight_fetcher.py`
- `tests/test_insight_multi_game_detector.py`
- `tests/test_insight_lineup_history.py`

**触っていないことを明示**: `src/source_*` / `src/wp_client.py` / `src/rss_fetcher.py` / `src/guarded_publish_runner.py` / `src/analysis/insight_etl.py`（既存 public API）/ `config/*.json` / `logs/*` / `master` ブランチ。

### 2. diff 概要

```
A  doc/active/INSIGHT-002-live-fetch-multi-game-lineup.md
A  src/analysis/insight_fetcher.py                (+260 行)
A  src/analysis/insight_multi_game_detector.py   (+330 行)
A  src/analysis/insight_lineup_history.py        (+200 行)
A  tests/test_insight_fetcher.py                 (+170 行)
A  tests/test_insight_multi_game_detector.py     (+260 行)
A  tests/test_insight_lineup_history.py          (+150 行)
```

既存ファイル 1 行も edit せず（INSIGHT-001 の `insight_etl.py` の `resolve_canonical` / `_load_roster_aliases` / `insert_candidates` を import で再利用）。

### 3. 実行したテスト

```
pytest tests/test_insight_fetcher.py -v                 → 14 件
pytest tests/test_insight_multi_game_detector.py -v     → 14 件
pytest tests/test_insight_lineup_history.py -v          →  8 件
pytest tests/test_insight_etl.py -q                     → 21 件 (regression)
pytest tests/test_event_key_*.py tests/test_morning_*.py -q → 61 件 (regression)
pytest tests/test_player_eyecatch_resolver.py tests/test_draft_*.py -q  → 36 件 (regression)
```

### 4. テスト結果

- 新規 36 件 ALL PASS（fetcher 14 / multi_game 14 / lineup 8）
- regression 118 件 ALL PASS、red ゼロ
- **合計 154 件 PASS、約 2.2 秒**
- 実 HTTP は **1 回も発生せず** （mock injection、CLI cache-only block 動作確認）

### 5. 残った懸念

- **実 live HTTP の本番動作確認は本セッションで未実施**: CLI `--live` を user が手動で 1 回叩いて初取得を確認する必要あり。robots.txt が 200 OK なこと、`If-Modified-Since` heading が正しく動くことを user 環境で検証してから定期化を判断。
- **NPB の URL slug が変わった場合の挙動未確認**: 試合キャンセル / 振替で slug が日付からずれる可能性。試走 1-2 試合で実例を見てから対応決め。
- **多試合 detector の閾値は経験則**: `recent_n=5` / `baseline_min_n=10` / `z_threshold=1.5` / `pitch_threshold=150` 等は実データ蓄積後に調整必要。
- **lineup の代打/代走/守備固め等は本フェーズ対象外**: `is_sub=True` 行は無視、終盤起用パターンは次フェーズ。
- **守備指標**: schema にカラムは確保したが、NPB box の HTML 構造から守備機会数が取れていないため未充填。NPB が出している `fielding.html` などを別 source として追加するか、簡易代理指標で代用するか別チケットで判断。

### 6. 新しく見つかったデグレ

**なし**。既存 118 件 regression は全 pass、既存挙動に変化を観測せず。

導入過程で 3 件のテスト期待値ミスを修正（hot/cold streak の baseline variance / first_appearance の `evidence` 参照方法）。これは実装側ではなくテストの seed データ設計の問題で、その場で修正・全 pass 確認。

### 7. 追加した回帰テスト

| ファイル | 件数 | 主に守る invariant |
|---|---|---|
| `test_insight_fetcher.py` | 14 | (a) cache hit で HTTP 呼ばない、(b) cache miss + not-live は FetchBlocked、(c) robots disallow で fetch しない、(d) 5xx で例外、(e) CLI cache-only で exit code 2、(f) module import で side-effect なし |
| `test_insight_multi_game_detector.py` | 14 | (a) z_score の n<2 / 分散ゼロで None、(b) recent_n+baseline_min_n 未満で None、(c) hot/cold/streak/workload/rest_days 各 detector の正常検知、(d) `_finalize` 出力が `insert_candidates` に受け取れる shape |
| `test_insight_lineup_history.py` | 8 | (a) NPB box fixture から 9 lineup 抽出、(b) is_sub 除外、(c) slot_jump min_jump 閾値、(d) first_appearance の重複除外、(e) finalize 後 insert 可能 |

### 8. 次回触ってはいけない範囲（本フェーズ learning）

- **`tests/test_insight_fetcher.py` の HTTP 呼び出しゼロ assert を緩めない**: live HTTP の混入を防ぐ canary
- **`fetcher.cache_or_fetch` の `allow_live=False` default を変えない**: Claude が安全に呼べる cache-only モードの保証
- **`MIN_INTERVAL_SECONDS = 5.0` を下げない**: NPB に負荷をかけない polite 規律
- **multi_game detector の `recent_n + baseline_min_n` 閾値**: 緩めると n=3 程度で誤検出が増える。実データで調整する場合は対応する test を必ず更新
- **lineup_history の `is_sub` 除外ロジック**: 代打を lineup に含めると slot_change anomaly が誤検知だらけになる
- **`src/analysis/` 内 module 間の循環依存**: insight_etl ← lineup_history は OK、insight_etl → lineup_history は禁止（INSIGHT-001 の insight_etl が pipeline 起点なので、依存を膨らませない）
- **WP DB / Scheduler / env / deploy / X API / Gemini**: INSIGHT-001 STOP 条件をそのまま継承

---

### Phase 3 引き継ぎ（INSIGHT-003 草案）

次フェーズ候補:

1. **CLI 「nightly run」コマンド**: 前日分の slug を引数なしで決定 → cache_or_fetch → ETL → 多試合検知 → CSV 出力 を 1 コマンドで実行
2. **守備指標 source 追加**: NPB の fielding ページ（あれば）または Yahoo box の守備機会数を別 source で拾う
3. **lineup 出展 source 拡張**: 試合前のスタメン発表（Yahoo の lineup extractor 流用）も lineups に蓄積、出場前から signal 化
4. **CSV → markdown サマリ**: 朝の review 用に signal を category ごとにグループ化した markdown を生成
5. **同球団・同年代比較**: NPB team_stats 蓄積後、リーグ平均との比較 detector

INSIGHT-001 / 002 と同じ namespace 隔離・WP 非干渉・無料完結の原則を継承。
