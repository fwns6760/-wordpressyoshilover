# 411-X-POST-BRANDING-VOICE-PERSONA: Tavily whitelist 拡張 + 観戦記事 2 voice persona (フーガ / 缶詰) + 試合日 / 18時 gate

## 1. ticket header

- **status**: DRAFT (user GO 待ち)
- **priority**: P2 (392 / 394 系の brand post lane 個性付け、 ¥0/post 維持)
- **owner**: Claude
- **lane**: Claude direct dev
- **依存**: 392 (`d963d1d` 系の x_post_branding_gen.py) + 394 (active P0、 hallucination fix)
- **parent**: 382 (CLOSED) のブランディング post spec / 392 (CLOSED) の Gemma 4 + Tavily 基盤
- **設計 source**: 2026-05-20 chat lock (user 「Tavily で候補 URL 拾う / 公式 NPB 球団 主要スポーツ紙 優先 / answer 使わず URL本文・媒体名・日付見る / 野球観戦の記事 / フーガ風 + 缶詰風 voice / 観戦ツイートは 18 時以降だけ / 野球がある日 / それを調べる」)

## 2. 背景 / user 仕様 (chat 引用)

- 「Tavily で候補 URL を拾う」
- 「公式、 NPB、 球団、 主要スポーツ紙を優先」
- 「Tavily の answer は使わず、 URL 本文・媒体名・日付を見る」
- 「野球観戦の記事を書く」
- 「フーガ風 voice も」「缶詰も」 → フーガ (長文分析) + 缶詰 (試合中実況) 両方
- 「野球観戦のツイートは 18 時以降だけ」
- 「野球がある日。 土日は平日もある。 それを調べる」

模倣元 (`config/rss_sources.json` `type=fan_voice_pool`):
- フーガ (@EH87EazmV9D2eSw、 「巨人ファン長文分析」)
- 缶詰 (@kandume92、 「巨人ファン試合中実況」)

## 3. 現状 gap (実 file 引用)

`src/x_post_branding_gen.py`:

| L | 現状 | gap |
|---|---|---|
| 182 | `_TAVILY_INCLUDE_DOMAINS = ("sports.yahoo.co.jp", "hochi.news")` | **whitelist 狭い** — 公式 / NPB / 球団 / 他主要紙が抜け |
| 209-217 | Tavily request に `include_answer` 不指定 = answer 不使用設計済 | **OK** (confirm + コメント明示) |
| 723 (`_format_tavily_context`) | results の url/title/content を整形 | **`published_date` 未注入** — Gemma に 「いつの記事か」 渡らず |
| 175 (`_SYSTEM_PROMPT_BASE` / `_resolve_system_prompt`) | generic single prompt + `time_tone_hint` | **2 persona prompt 不在** (フーガ / 缶詰 voice 切替なし) |
| caller (`run_x_post_mail.py`) | 時間 gate / 試合日 gate なし | **観戦記事 voice fire 制御なし** |

## 4. やること (scope)

### 4.1 `_TAVILY_INCLUDE_DOMAINS` 拡張

`src/x_post_branding_gen.py:182` を以下に書き換え:

```python
_TAVILY_INCLUDE_DOMAINS = (
    # 公式 / 球団
    "giants.jp",
    "npb.or.jp",
    # 主要スポーツ紙
    "hochi.news",
    "sponichi.co.jp",
    "nikkansports.com",
    "sanspo.com",
    "daily.co.jp",
    "chunichi.co.jp",
    # ポータル (既存)
    "sports.yahoo.co.jp",
    "full-count.jp",
    "baseballking.jp",
)
```

(追加 domain は **whitelist 優先**、 `include_domains` の挙動で Tavily 側が優先取得)

### 4.2 Tavily `answer` 不使用 confirm

`_tavily_search` request body に `include_answer: False` を **明示** (今は不指定で default OFF だが、 spec lock として明示)。 コメントで 「user 仕様: answer 不使用、 URL 本文 / 媒体名 / 日付のみ」 と記す。

### 4.3 `published_date` を Gemma context に注入

`_format_tavily_context` (L723) を改修:

- 入力 `results` の各 entry から `published_date` (Tavily が返すなら) または `content` 内 日付テキストを抽出
- Gemma context format: `「[YYYY-MM-DD] [媒体名] <タイトル> — <抜粋300字>」`

### 4.4 観戦記事 2 voice persona prompt

`_SYSTEM_PROMPT_BASE` を 2 persona template に split:

#### persona A: フーガ風 (長文分析)
- 試合前 / 試合後 / 非試合中 (主に day 帯 + 21時以降 game後) で使用
- 特徴: 数字踏まえた長文分析、 因果 narrative、 「観戦して感じた点」 視点
- 例文 framing: 「今日の試合を見て一番気になったのは…」「数字としては…、 だが流れとしては…」

#### persona B: 缶詰風 (試合中実況)
- 試合中 (18-21時 + 試合日) のみ使用
- 特徴: 短文連投風 (ただし 1 post 280字内)、 リアルタイム実況視点、 「今◯回」「次の打席」 等の臨場感
- 例文 framing: 「◯回終わって…」「ここで◯◯が…」「この回しのげれば…」

両 persona とも spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) 遵守。

### 4.5 persona 自動選択 + 試合日 / 18時 gate

新規 helper `src/x_post_branding_gen.py` 内 (or 既存共通モジュール):

```python
def is_giants_game_day(now_jst, db_path) -> bool:
    """insight.db の games table で今日試合があるか判定."""
    # SELECT 1 FROM games WHERE game_date = ? LIMIT 1
    # 1 行返ったら試合日

def select_branding_persona(now_jst, is_game_day) -> str:
    """persona = 'kandume' if (18 <= hour <= 21 and is_game_day) else 'fuuga'."""
```

`build_gemma_branding_candidate` 内で:
- 試合日 + 18-21時 = 缶詰 persona prompt
- それ以外 = フーガ persona prompt
- **観戦記事を出すかどうかは別 flag** (= 観戦記事は試合日 18時以降のみ、 非試合日 / 18時前は フーガ 一般分析記事として 既存通り fire)

### 4.6 env flag

既存 `X_POST_MAIL_GEMMA_GEN_ENABLED` で gate (default OFF)。 411 では default を変えない。 新 flag は追加しない。

### 4.7 test

`tests/test_x_post_branding_gen.py` に追加:

- `test_tavily_include_domains_covers_official_and_papers` — whitelist に giants.jp / npb.or.jp / sponichi / nikkansports / sanspo / daily / chunichi が含まれる
- `test_tavily_search_does_not_request_answer` — request body に include_answer が指定なし or False
- `test_format_tavily_context_includes_published_date` — context に [YYYY-MM-DD] [媒体名] が含まれる
- `test_select_branding_persona_kandume_on_game_day_evening` — 試合日 18-21時 → 'kandume'
- `test_select_branding_persona_fuuga_on_non_game_day` — 非試合日 → 'fuuga'
- `test_select_branding_persona_fuuga_morning_even_on_game_day` — 試合日 11時 → 'fuuga'
- `test_is_giants_game_day_returns_true_when_games_row_exists` — mock games table
- `test_is_giants_game_day_returns_false_when_empty` — mock empty

## 5. やらない範囲

- 既存 spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) の変更
- 既存 mail / Scheduler / Dockerfile 変更
- 既存 DB# 候補 (`_build_branded_post_text` template-based) の挙動変更
- 既存 fan_voice_pool 候補 (397 `build_fan_voice_candidate`) の挙動変更
- live_update subtype enable (`ENABLE_LIVE_UPDATE_ARTICLES` env、 §11 user 判断)
- WordPress REST / X live posting / Hermes
- production deploy (本 ticket は code 着地 + dry-run まで、 deploy は別便)
- env / Secret 値変更
- `X_POST_MAIL_GEMMA_GEN_ENABLED` default 変更
- Cloud Build パラメータ変更
- 並走 ticket (394 hallucination fix) の logic 改変 (merge 効率は同 file 触る前提で commit 直列)

## 6. 実行予定テスト

- AST: `python3 -c "import ast; ast.parse(open('src/x_post_branding_gen.py').read())"`
- compile: `python3 -m py_compile src/x_post_branding_gen.py tests/test_x_post_branding_gen.py`
- targeted: `pytest tests/test_x_post_branding_gen.py -q` (新規 8 test + 既存 全 pass)
- full pytest baseline 比較 (baseline は 411 着手前に計測、 fail 増加 0)
- dry-run (任意): `X_POST_MAIL_GEMMA_GEN_ENABLED=1` + mock Tavily / Gemma で persona output 目視

## 7. STOP 条件

- baseline pytest fail 数増加 (1 件でも)
- 既存 `_build_branded_post_text` / `build_fan_voice_candidate` の挙動変化
- `_TAVILY_INCLUDE_DOMAINS` 追加 domain が free tier 内 credit 消費を超過 (1 fire = 1 credit を維持、 domain 数増やしても credit は不変なはず、 ただし observation)
- spec 382 violation が validator gate を抜けて mail に混入 (URL / hashtag / 媒体名)
- 試合日 gate が誤判定 (試合あるのに no-game / 試合ないのに has-game)
- persona prompt が prompt injection に脆弱 (Tavily content の literal が prompt 越境)
- Gemma 4 free tier 超過 (paid tier 課金)
- Cloud Run Job execute で latency 増 (現 ~10秒 → 30秒超)

## 8. 想定されるデグレ

| 項目 | リスク | mitigation |
|---|---|---|
| Tavily whitelist 拡張で 結果 0 件 (絞りすぎ) | 中 | `max_results=3` のまま、 0 件時は caller silent skip (既存 fault-tolerance 維持) |
| 公式 / NPB sub-domain 不一致 | 低 | observation で domain pattern 確認、 必要なら sub-domain 追加 |
| `published_date` 欠落 entry | 低 | None / 空文字なら 「[日付不明]」 表記でフォールバック (Gemma に 「日付不明」 と渡る) |
| persona prompt 切替で 出力品質劣化 | 中 | flag OFF default 維持 + dry-run で 各 persona 出力サンプル目視 |
| 缶詰 persona が試合中以外で発火 | 中 | `select_branding_persona` に gate 厳格化 (`is_game_day AND 18 <= hour <= 21`) |
| 試合日判定が DB スナップショット遅延で false negative | 中 | fallback として `sports_fetcher.get_today_game()` (Yahoo scrape) も検証、 ただし本 ticket では DB 優先 |
| time_jst が test 環境で UTC のまま判定 | 低 | `now_jst` 引数化、 caller で `ZoneInfo("Asia/Tokyo")` 明示 |
| 並走 394 (hallucination fix) と同 file 衝突 | 中 | commit 直列 ([[feedback_codex_supervision_rules]] D)、 fire 順は user 判断 |

## 9. 受け入れ条件

- whitelist 9 domain (giants.jp / npb.or.jp / hochi.news / sponichi.co.jp / nikkansports.com / sanspo.com / daily.co.jp / chunichi.co.jp / sports.yahoo.co.jp) を満たす
- Tavily request の include_answer が False or 不指定
- `_format_tavily_context` 出力に published_date が含まれる
- persona 2 軸 (フーガ / 缶詰) の prompt template が file 上に存在
- `select_branding_persona` が時間帯 + 試合日で正しく persona 切替
- 試合日 helper `is_giants_game_day` が games table row 有無で正しく返す
- 新規 8 test + 既存 全 pass
- pytest baseline regression 0
- spec 382 hard rule 全項目維持
- 既存 DB# 候補 / fan_voice_pool 候補の挙動不変
- env / Secret / Scheduler / Dockerfile / WP / X 不変

## 10. 関連

- 392 (CLOSED): Gemma 4 + Tavily 基盤 (`d963d1d`)
- 394 (active P0): hallucination fix (本 ticket と同 file 触る、 commit 直列)
- 382 (CLOSED): spec / mail / Scheduler (本 ticket 不変)
- 397 (`build_fan_voice_candidate`): フーガ / 缶詰 literal voice 取り込み (本 ticket と直交、 並列)
- 408 (LIVE_DEPLOYED_OBSERVE): OB classifier (フーガ persona の OB narrative で参照余地、 future Phase)
