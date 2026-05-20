# 414-X-POST-HALLUCINATION-PREVENTION-9AXIS: brand post hallucination 防止 + 2軍混入防止 + 試合中当日 only

## 1. ticket header

- **status**: DRAFT (user GO 待ち)
- **priority**: P1 (user 報告 2 件 hallucination 確認、 信頼性低下中)
- **owner**: Claude
- **lane**: Claude direct dev
- **parent**: 411 (LIVE_DEPLOYED 2026-05-20、 brand post lane 2 persona) の精度強化
- **設計 source**: 2026-05-20 chat lock — user 報告:
  - 「岸田の出塁率 28位」 = 実在しない順位の hallucination
  - 「山瀬 (2軍中心) が 1軍 ranking に出る」 = 1軍/2軍 区別不在
  - 「試合中ツイートは試合当日のみ、 古いデータひろわない」
- **依存**: 411 (`3dd89e5`)、 並走 394 (active P0) と同 file 触る予定で commit 直列

## 2. 背景 / user 報告 hallucination 事例

### 事例 1: 岸田の出塁率 28位
- 岸田 = 巨人 1軍捕手
- 「ランキング出塁率 28位」 = 実在しない順位を Gemma が捏造
- 原因仮説: prompt instruction で「順位を含めない」 と書いてあるが post-gen validator regex に未登録、 Gemma が prompt を破っても drop されず通過

### 事例 2: 山瀬慎之助 (2軍中心) が 1軍 ranking に
- 山瀬: `config/giants_roster.json` で `role=player`, `position=打者`, `active=true` (1軍/2軍 field 無し)
- `batting_logs` schema に 1軍/2軍 field 無し
- `games.source_kind` は `"npb_box" | "yahoo_box" | "fixture"` (1軍 NPB box 想定) だが cup-of-coffee (一時 1軍登録) で少サンプル ranking 上位に来る可能性
- 原因: ranking query (`src/analysis/ranking_article_publisher.py`) に 1軍 active filter 無し、 `min_sample` 緩い

### 事例 3: 試合中ツイートで古いデータ
- 缶詰 persona (試合中実況) は当日進行中の試合を語るべき
- 現状: `_tavily_search(same_day_only=False)` で前日+当日 snippet pull、 古い試合の話題を Gemma が拾うリスク
- `build_db_fact_line(streak_window=5)` で過去 5 試合 streak 含む

## 3. やること (9 axis)

### 3.1 src/x_post_branding_gen.py 改修 (axis 1-7, 9)

| # | 改修 | 場所 |
|---|---|---|
| 1 | `_GEMMA_BRANDING_FORBIDDEN_PATTERNS` に `re.compile(r"\d+位")` 追加 | L42-48 |
| 2 | 新規 helper `_extract_unverified_numbers(text, verified_text)`: 生成 text から `\d+` 抽出し verified_text (db_fact + Tavily content) に literal 出現するもの以外を返す。 1 件以上あったら `_gemma_branding_safety_check` で drop | new helper + L260 |
| 3 | `_GEMMA_BRANDING_FORBIDDEN_PATTERNS` に `re.compile(r"\d+\.\d{3}")` (打率/出塁率/OPS) と `re.compile(r"防御率\s*\d+\.\d{1,2}")` 追加 | L42-48 |
| 4 | `_SYSTEM_PROMPT_FUUGA` と `_SYSTEM_PROMPT_KANDUME` の制約 section に bad example 「『出塁率28位』『打率3位』『歴代5位』 のような 順位 / rate 数字は出力禁止、 違反したら出力全体破棄」 を明示 | L51 / L186 |
| 5 | `build_gemma_branding_candidate` の `temperature: float = 0.6` → `0.4` default | L987 |
| 6 | 新規 helper `_recent_published_within_days(results, days=7)`: published_date が 7 日超過の entry を context から drop (strict filter)。 `_format_tavily_context` 前段で呼ぶ | new helper + L1023 |
| 7 | `_gemma_branding_safety_check` で drop 時 WARNING log に `reason=...` + `matched_pattern=...` を 構造化 dict で吐く | L260-274 |
| 9 | `build_gemma_branding_candidate` 内 persona=`kandume` 検出時に `_tavily_search(same_day_only=True)` + `build_db_fact_line(streak_window=0)` を caller 側で適用 (持続: caller の引数で persona 決定済の枝分岐) | L1010-1023 / L766 |

### 3.2 src/x_post_mail_lane.py + src/analysis/ranking_article_publisher.py (axis 8)

| # | 改修 |
|---|---|
| 8 | 新規 helper `is_first_team_active(player_canonical, db_path, window_days=14, min_games=3)` を `src/analysis/active_roster_filter.py` (新規 file) に切り出し、 `pick_candidates` (x_post_mail_lane.py) と aggregate_* (ranking_article_publisher.py) から呼ぶ。 直近 `window_days` 日で `games` に `min_games` 試合以上出場した player のみ ranking 対象。 |

実 SQL (新 helper 案):
```sql
SELECT COUNT(DISTINCT bl.game_id) FROM batting_logs bl
JOIN games g ON bl.game_id = g.game_id
WHERE bl.player_canonical = ?
  AND g.game_date >= ?
  AND bl.team_name = '巨人'
```
N 以上なら active。 投手は pitching_logs 経由で同じ。

### 3.3 test 追加 (`tests/test_x_post_branding_gen.py` + 新 `tests/test_active_roster_filter.py`)

最低 14 件:
- axis 1: `\d+位` 含む text → safety_check False
- axis 1: `\d+位` 含まない text → True
- axis 2: verified set 内の数字のみ → True
- axis 2: verified set 外の数字含む → False
- axis 3: 打率 / 出塁率 / OPS 系数字含む → False
- axis 3: 数字なし → True
- axis 4: prompt 内 bad example 確認 (フーガ + 缶詰 両方)
- axis 5: build_gemma_branding_candidate default temperature 0.4
- axis 6: published_date 7日超 entry drop
- axis 6: published_date 当日 entry 残す
- axis 7: drop log に reason / pattern 含まれる
- axis 9: persona=kandume で same_day_only / streak_window=0 適用
- axis 9: persona=fuuga で既存挙動 (days=2 / streak=5)
- axis 8: is_first_team_active = True (直近 14 日 3 試合)
- axis 8: is_first_team_active = False (cup-of-coffee / 出場無し / window 外)

## 4. やらない範囲

- 既存 spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) の変更
- 既存 mail / Scheduler / Dockerfile / WP REST / X live posting
- live_update enable (§11 user 判断、 別 ticket)
- env / Secret 値変更
- `X_POST_MAIL_GEMMA_GEN_ENABLED` default 変更
- roster JSON schema 変更 (`tier` field 追加は別 ticket、 414 では filter のみ)
- NPB 公式 active list ingest (別 ticket、 414 は既存 DB から推定)

## 5. 実行予定テスト

- AST: `python3 -c "import ast; ast.parse(open('src/x_post_branding_gen.py').read())"`
- AST: 新 file `src/analysis/active_roster_filter.py`
- targeted: `pytest tests/test_x_post_branding_gen.py tests/test_active_roster_filter.py -q`
- full pytest baseline 比較 (baseline = `3dd89e5` HEAD の 5583 passed / 3 failed (8491fd8 由来) / 4 xfailed)
- regression 0 確認 (私の changes 単独で増加 0)

## 6. STOP 条件

- baseline pytest fail 数増加 (私の changes 単独で増加)
- 既存 `_build_branded_post_text` template / `build_fan_voice_candidate` 挙動変化
- `_GEMMA_BRANDING_FORBIDDEN_PATTERNS` 追加で既存 mail の brand post 候補数が **0 件になる** (= 過剰 drop)
- active 1軍 filter で巨人 1軍 全選手が ranking から消える (= filter ロジック誤り)
- persona=kandume の当日 only filter で **試合中時間帯 (18-21時) に Tavily 0 件** = brand post 0 件 (= filter 過剰)
- 並走 agent (403 chain) の commit と直接衝突 (`ranking_article_publisher.py`)
- spec 382 hard rule 違反が validator を抜けて mail に混入

## 7. 想定デグレ

| 項目 | リスク | mitigation |
|---|---|---|
| `\d+位` regex で「歴代5位」 等 narrative depth (412 案、 将来) が drop | 中 | 414 で「順位は出さない方針」 user lock、 narrative depth は別軸 (年/球団) で表現 |
| 数値 whitelist が strict すぎて全 candidate drop | 中 | verified_text に db_fact + Tavily content (snippet 含む) で広めに matching、 0 件時 log 確認 |
| temperature 0.4 で voice が硬く / 単調になる | 中 | persona prompt の few-shot 例 で voice 維持、 観察後必要なら 0.5 微調整 |
| published_date 7日超 drop で context 0 件 fire | 中 | 0 件時 caller silent skip (既存 fault-tolerance)、 朝 fire は前夜 試合記事 (1日前) が残るので OK |
| active 1軍 filter で 怪我復帰直後 / call-up 直後選手 が消える | 中 | window_days=14 / min_games=3 を初期値、 observation で調整 |
| kandume persona の当日 only で 試合前 brand post (17時前) が無効化 | 低 | persona 自動選択は 18-21時 + 試合日 = kandume なので、 17時前は fuuga 維持 (既存通り) |
| 並走 agent (`ranking_article_publisher.py` 触ってる) と commit 衝突 | 中 | commit 直列、 fire 前に git pull で sync |
| log 形式変更で既存 alert / dashboard 破損 | 低 | 追加 field のみ、 既存 field は維持 |

## 8. 受け入れ条件

- 9 axis 全実装、 全 test pass (≥ 14 件新規)
- pytest baseline regression 0 (私の changes 単独)
- 既存 mail の brand post 候補数が 0 にならない (観察で確認)
- 「岸田 28位」 type の hallucination が validator で drop される (test で再現)
- 山瀬 type の 2軍選手が ranking に出ない (test で再現)
- 缶詰 persona で当日以外の snippet が context に注入されない (test で確認)
- spec 382 hard rule 維持
- 既存 DB# 候補 / fan_voice_pool 候補挙動不変
- env / Secret / Scheduler / Dockerfile / WP / X 不変
- cost ¥0/post 維持

## 9. 関連

- 411 LIVE_DEPLOYED (`3dd89e5`、 brand post 2 persona base)
- 394 active P0 (hallucination fix、 同 file 触る、 commit 直列)
- 382 CLOSED (spec / mail / Scheduler 流用元)
- 397 (`build_fan_voice_candidate`、 並列で touch しない)
- 403 chain (parallel agent、 `ranking_article_publisher.py` 触る、 commit 直列必須)
