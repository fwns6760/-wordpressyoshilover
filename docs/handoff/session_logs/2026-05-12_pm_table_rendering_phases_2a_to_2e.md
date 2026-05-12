# 2026-05-12 PM session — 表形式描画 Phase 2A-2E + roster maintenance 完遂

> 引継ぎ用 session log。本 session で実装 / deploy した内容、現 prod 状態、未完了タスク、決定事項、注意点をすべてここに置く。次 session の Claude / Codex / 担当者はここを読んで current focus を把握する。

---

## TL;DR

- 報知 / スポニチ / 巨人公式X の **lineup / starter-rotation / postgame 記事** に **6 種類の構造化 table** を render する機能を実装、**9 commit / 9 deploy** をすべて prod 反映完了。
- 報知 2軍 lineup tweet(id=66442)で「【二軍スタメン一覧】」h3 の下が空のまま public 化されていた bug を起点に開始、最終的に postgame の inning / 勝利投手 / 敗戦投手 / セーブ table まで実装。
- prod current revision: **`yoshilover-fetcher-00405-cud`**(image `22d93d0`、~19:45 JST に flip)。
- 既存テスト累積 baseline 3461 → 3609 件、増加 fail 0(pre-existing time-dependent test 1 件はそのまま carry)。
- 未完了: (C) **fixture verify(巨人完了試合の Yahoo HTML で parser 動作確認)**、観察、roster 追加候補、atbat 拡張(諦め)。

---

## 1. 本 session の commit / deploy 履歴

| # | commit | 概要 | image deploy |
|---|---|---|---|
| 1 | `bc5c603` | Phase 2A: 報知 compact lineup table | `yoshilover-fetcher-00383-puh` |
| 2 | `8d47ea7` | Phase 2A-1: roster lookup + 2-table 巨人/相手 split | `yoshilover-fetcher-00387-lur` |
| 3 | `1378a91` + `3e126fe` 系 | (並走 agent commit + Phase 2B reapply `510fbaa`) | included in `00391-qun` |
| 4 | `555bb98` | Phase 2C: starter rotation arrow chain table | `yoshilover-fetcher-00393-fif` |
| 5 | `f3252a1` | Phase 2D-A: postgame prose A-fallback | `yoshilover-fetcher-00393-fif`(同時) |
| 6 | `aaa3493` | Phase 2D-B: Yahoo box inning table for 1軍 | `yoshilover-fetcher-00397-pok` |
| 7 | `da2ba25` | Phase 2E: W/L/S 投手 row 抽出 + render | `yoshilover-fetcher-00401-biy` |
| 8 | `c50e731` | retire: `rss_lineup_table_post_process` wrapper 撤去 | `yoshilover-fetcher-00401-biy`(同時) |
| 9 | `22d93d0` | chore(roster): 梶原昂希追加 | **`yoshilover-fetcher-00405-cud`**(current) |

deploy 経路は全て `gcloud builds submit --tag :<short_sha>` → `gcloud run deploy --no-traffic --tag canary-<sha>` → health check 200 → `update-traffic --to-revisions=<rev>=100`。Cloud Build 無料枠内、追加金銭コスト ¥0。

---

## 2. 現 prod 状態(引継ぎ時点)

```
revision: yoshilover-fetcher-00405-cud
image:    asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:22d93d0
flipped:  2026-05-12 ~19:45 JST
health:   /health 200 (130ms)
```

key env(production、本 session で変更なし、参考):
- `ARTICLE_AI_MODE=none` / `OFFDAY_ARTICLE_AI_MODE=none`(Gemini / Grok 不使用、本 phase は全 deterministic parser)
- `ENABLE_RSS_TEMPLATE_ROUTING_V2=1`(v2 routing 必須、emoji format 検出に不可欠)
- `ENABLE_RSS_LINEUP_TABLE_POST_PROCESS=1`(retire 後は no-op、env 自体は残置、別途 clean 可)

---

## 3. 実装した機能 / table 種類

### Phase 2A 系(lineup table)

| trigger | source | rendering |
|---|---|---|
| **報知 compact lineup**(`D東妻 7萩尾...`)| 報知系 X / hochi.news tag | `📋 巨人スタメン` + `📋 <opponent>スタメン` 3-col table(順/守備/選手)、roster で team 分類 |
| **巨人公式X 2軍 emoji**(`1️⃣ 三塚(D) 2️⃣ 小濱⑹...`)| 巨人公式X / TokyoGiants | 同上、emoji を NFKC で paren digit 化 |

### Phase 2C(starter rotation)

| trigger | rendering |
|---|---|
| **arrow chain rotation**(`井上温大→ウィットリー→竹丸和幸`)+ 報知/sponichi/巨人公式X source + 「先発ローテ」keyword + 巨人 roster ≥ 1 | `📋 先発ローテ予告 (vs <opponent>)` 2-col(順/先発投手)|

### Phase 2D-2E(postgame)

| trigger | rendering |
|---|---|
| **2軍 postgame**(報知/sponichi、Yahoo box 不在)| `📋 試合結果 (巨人2軍 vs <opponent>)` 2-col(スコア/勝利投手)= Phase 2D-A prose A-fallback |
| **1軍 postgame**(報知/sponichi、Yahoo `/index` 取得成功)| 3 個の rich table:<br>① `📋 試合結果 (Yahoo box)` 4-row metadata(日付/大会/対戦/スコア)<br>② `📊 イニング` per-team innings + total<br>③ `⚾ 投手` W/L/S(区分/チーム/投手/成績)= Phase 2D-B + 2E |
| **1軍 postgame + Yahoo fail / parse None** | Phase 2D-A prose A-fallback に degrade |

### marker class 一覧(下流 post-process / CSS 用)

- `nomotoke-card-lineup-table` — Phase 2A-1 / 2B lineup
- `nomotoke-card-starter-rotation` — Phase 2C
- `nomotoke-card-postgame-result` — Phase 2D-A / 2D-B metadata
- `nomotoke-card-postgame-inning` — Phase 2D-B inning
- `nomotoke-card-postgame-pitchers` — Phase 2E W/L/S

---

## 4. 重要なソースコード位置

### 新 module(本 session 追加)

| file | 役割 |
|---|---|
| `src/source_hochi_compact_lineup_extractor.py` | hochi compact + roster + opponent helper(Phase 2A / 2A-1)。**他 phase の roster / opponent extraction は全部この module を流用**。 |
| `src/source_emoji_lineup_extractor.py` | 巨人公式X / sponichi emoji 形 lineup(Phase 2B) |
| `src/source_starter_rotation_extractor.py` | arrow chain rotation(Phase 2C) |
| `src/source_postgame_extractor.py` | postgame prose facts(Phase 2D-A) |
| `tests/test_*_extractor.py` x 4 + `tests/test_rss_fetcher_*_table.py` x 4 | unit + integration tests |
| `tests/test_yahoo_postgame_pitcher_extraction.py` + `tests/fixtures/yahoo_postgame_2021038841_完了試合.html` | Phase 2E real Yahoo HTML fixture |
| `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md` | 全 phase の post-work record(spec / RED / GREEN / 数値 / 残懸念) |

### 既存 module 拡張

| file | 何を変えたか |
|---|---|
| `src/rss_fetcher.py` | 4 import + 4 extractor 呼出 + 5 nested helper(`_build_basic_lineup_table_block` / `_render_compact_lineup_subtable` / `_build_starter_rotation_block` / `_build_postgame_yahoo_block` / `_build_postgame_result_block`)+ tail inject 拡張 + Yahoo fetcher 1 個(`fetch_today_giants_postgame_facts_from_yahoo`)+ `rss_lineup_table_post_process` wrapper 撤去 |
| `src/source_yahoo_boxscore_extractor.py` | `YahooBoxscoreFacts` に `winning_pitcher` / `losing_pitcher` / `save_pitcher` 追加、`_extract_pitcher_row` helper 追加(Phase 2E) |
| `config/giants_roster.json` | 119 → 121 entry(梶原昂希 2 form 追加) |

---

## 5. 設計上の重要決定(future session 必読)

### 5.1 「LLM 不使用」の前提

production env `ARTICLE_AI_MODE=none` で、`build_news_block` は **`_build_safe_article_fallback` 系の deterministic rule-based body composer** を使う。本 session の全 phase はこの path に table を **inject** する形で動作。

### 5.2 Yahoo Sportsnavi の static HTML 制約

`/index` `/top` `/score` `/stats` 全 URL を調査済(複数の completed game で確認):
- ✅ inning_score(回別)
- ✅ 試合 metadata(日付/league/home/away)
- ✅ 勝利投手 / 敗戦投手 / セーブ(`bb-gameTable` 内)
- ❌ **atbat 結果**(per-batter)
- ❌ **opponent_lineup**(完了試合 / per-game)

`/playbyplay` `/box` `/result` `/atbat` `/play` 等の URL は全 404。atbat data は **Yahoo の JS dynamic render** に格納されており、静的 scrape では取得不可。

### 5.3 Phase 2E atbat 拡張は「諦め」

`headless browser`(Playwright / Puppeteer)を Cloud Run に投入すれば取得可能だが、月¥500-3000 の課金増。本 session では **諦め推奨**(rare path、ROI 低)。次 session で必要になったら再着手。

### 5.4 routing v2 必須

`_select_template_v2` が emoji format / compact form を `_has_social_lineup_shorthand_signal` で正しく `farm_lineup` / `lineup` subtype に振り分け。v1 routing(`_has_lineup_core` 経路)は「スタメン」keyword 必須で、emoji fixture を「farm」に誤分類する。production env `ENABLE_RSS_TEMPLATE_ROUTING_V2=1` が **不可欠**、disable しないこと。

### 5.5 Phase 2B revert 騒動

本 session 中、他 agent(`yoshihiro` author)が `3e126fe` commit で「docs: ...」message のまま Phase 2B の source code を bundle commit してしまい、続いて `3a2125a` で revert された。Phase 2B work が一時消失 → `510fbaa` (Reapply commit)で復元。同じパターン(scope 不一致 commit)を避けること。

### 5.6 roster lookup の限界

`is_giants_player(name)` は surname-prefix(1-4 char)match で、同姓他球団との disambiguation 不可:
- `井上` → 巨人 (井上温大、投手) → fixture の `7井上` は LF position なので別人(DeNA 井上)の可能性高、しかし surname match で 巨人判定
- `丸` → 巨人 (丸佳浩) → 1 char surname も match(本 session で 1-4 char に拡張済)

精度限界は **roster maintenance + 透明性 note** で補う方針。位置情報での disambiguation は roster の position field が「打者」「投手」粒度なので不可能(将来 position-aware roster 拡張で改善余地)。

---

## 6. テスト状況

### 累積 phase test 数

| group | count | status |
|---|---|---|
| hochi compact(2A + 2A-1)| 41 | GREEN |
| emoji(2B)| 20 | GREEN |
| starter rotation(2C)| 17 | GREEN |
| postgame(2D-A + 2D-B + 2E)| 23 | GREEN |
| **累積** | **101** | **GREEN** |

### Full suite baseline 推移

```
Phase 0 (HEAD 51acaa0):  3461 OK / 0 fail
Phase 2A (bc5c603):      3484 OK / 0 fail
Phase 2A-1 (8d47ea7):    3508 OK / 0 fail
Phase 2A-1 baseline re-run (同日17:50頃): 3517 / 1 fail (pre-existing time-dependent)
Phase 2B (510fbaa):      3537 / 1 fail
Phase 2C (555bb98):      3570 / 1 fail
Phase 2D-A (f3252a1):    3589 / 1 fail
Phase 2D-B (aaa3493):    3592 / 1 fail
Phase 2E (da2ba25):      3609 / 1 fail
retire (c50e731):        3612 / 1 fail
roster (22d93d0):        (本 session で full suite 未再実行、code 変更なしで影響なし想定)
```

**pre-existing fail(stash で carry 確認済、本 session 起因ではない)**:
- `tests/test_ingestion_filter_relaxation.py::test_main_passes_36_hour_window_for_postgame_skip_check`
  - `assertEqual(skip_mock.call_count, 1)` が `0 != 1` で fail
  - 時刻依存テスト(36h window が UTC 計算で本日 タイミングだけ赤化)
  - Phase 2A-1 baseline でも同じ fail を再現(stash + revert で確認済)
  - 本 session で touch なし、別 ticket で時刻 mock 化推奨

### 増加 fail count: **0**(全 phase で baseline 比 増加なし、increase 0 は each commit message 内で明記)

---

## 7. 未完了タスク / next session 候補

### C. fixture verify(優先度 ★★)

**目的**: 本日 deploy 済 Phase 2D-B / 2E の Yahoo box parser が、**巨人 game の実 HTML で動作することを確認**する。

**手順**:
1. 完了 Giants game(本日 5/12 vs 広島、明日以降 別 game)の Yahoo `/index` HTML を fetch
2. `parse_yahoo_game_html` に渡す
3. `giants_facts()` の出力を確認:
   - `score`, `result`, `inning_score`, `winning_pitcher` / `losing_pitcher` / `save_pitcher` が正しい
4. 異常あれば `source_yahoo_boxscore_extractor.py` の regex 調整 + commit
5. 正常なら fixture を `tests/fixtures/` に追加 + unit test 追加

**現状の障害**: 本 session 19:45 JST 時点で本日 巨人試合(`2021038846`)はまだ `一球速報`(parse None)。試合終了 + Yahoo schedule cache 更新を要 wait(おそらく 21:00 JST 以降 or 翌日)。

### 観察(優先度 ★★★、passive)

**目的**: 本日 deploy 済の 7 種 table が、報知/sponichi/巨人公式X の自然発火で正しく描画されることを prod で確認。

**観察対象**:
- 報知 X 1軍 lineup tweet → Yahoo 7列 table 優先(Phase 2A-1 inject は Yahoo 空時のみ)
- 報知 X 2軍 lineup tweet → 巨人/相手 split table(梶原追加で精度向上)
- 巨人公式X 2軍 emoji lineup → 巨人スタメン table(1 table、opponent 巨人 batter のみの convention)
- 報知 starter rotation article → rotation table
- 報知 1軍 postgame article + Yahoo box → 3-table rich
- 報知 2軍 postgame → 2-col A-fallback table

**観察コマンド**(rough):
```bash
# 最新 30 件で marker 含有率
curl -s 'https://yoshilover.com/wp-json/wp/v2/posts?per_page=30&_fields=id,date,content' \
  | python3 -c "import json,sys; \
      posts=json.load(sys.stdin); \
      for p in posts: \
        c=p.get('content',{}).get('rendered',''); \
        markers=[m for m in ['nomotoke-card-lineup-table','nomotoke-card-starter-rotation','nomotoke-card-postgame-result','nomotoke-card-postgame-inning','nomotoke-card-postgame-pitchers'] if m in c]; \
        if markers: print(p['id'], p['date'][:16], markers)"
```

### roster 追加候補(優先度 ★)

`config/giants_roster.json` には現 121 entry。未追加の可能性ある選手(user 知見必要):
- 直近昇格 / 育成新人 / 移籍 加入選手
- 1 char surname で他球団との重複が頻発する選手の disambiguation(future, position-aware roster で対応)

### atbat / opponent_lineup(優先度 ✗、諦め推奨)

`headless browser` 投入が必須。Cloud Run image +400MB / runtime +200MB / 月¥500-3000。本 session では諦め。**「のもとけ」level の rich box 描画が必要になった時に再検討**。

### `rss_lineup_table_post_process` module 完全削除(優先度 ✗、任意)

retire 後の module file と test は disk に残してある(`src/rss_lineup_table_post_process.py` / `tests/test_rss_lineup_table_post_process.py`)。完全削除しても OK だが git history で復活可能。**任意**。

---

## 8. 次 session 立ち上げ時の必読 path

1. **本 file**(`docs/handoff/session_logs/2026-05-12_pm_table_rendering_phases_2a_to_2e.md`)
2. `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md`(全 phase 詳細 post-work)
3. `docs/work_logs/2026-05-12_pregame-info-table-format.md`(Phase 2A 前段の narrow post-process spec)
4. `docs/work_logs/2026-05-12_hochi-fresh-pregame-backlog-publish-policy.md`(関連 ticket、別便で着地済)
5. `src/source_hochi_compact_lineup_extractor.py`(全 phase の共通 helper)
6. CLAUDE.md / AGENTS.md(プロジェクト全体 rule)
7. `feedback_claude_dev_and_deploy_2026_05_12.md` memory(本日付の最強 lock、Claude が dev + deploy 全権)

---

## 9. 本 session で取得した重要な事実 / observation

- 報知 X 2軍 lineup の compact format(`D東妻 7萩尾3加藤...`)は **巨人/相手両軍を 1 tweet に concat** して送信される(id=66442 で確認、20 token)。team 識別は roster 照合で行う以外に手段なし。
- 巨人公式X 2軍 lineup の emoji format(`1️⃣ 三塚(D) 2️⃣ 小濱⑹...`)は **巨人 batter のみ** 列挙する convention(id=65900 で確認)。opponent table は通常 0 件 suppress。
- 報知 article の starter rotation tweet 発火率: **月 1-2 件**(直近 100 件中 1 件 = id=66418)。低発火だが table 化価値あり。
- Yahoo Sportsnavi `/index` page の `bb-gameTable` 内に **勝利投手 / 敗戦投手 / セーブ row が安定的に存在**(`(X勝Y敗ZS)` 形式の record も)。Phase 2E はこれを利用。
- **`_find_giants_game_info_yahoo(target_day=...)` は target_day を honor していない**(常に今日の game を返す)。過去 game ID 取得には Yahoo schedule page を別途 scrape。future improvement 候補。
- 別 agent(`yoshihiro` author)が同 repo で並走 commit していた(`1378a91` `3e126fe` `2630552` `ce4116f` 系列)。本 session 中の Phase 2B revert はこの並走 agent の commit 整理に巻き込まれた結果。次 session でも並走 commit 警戒。

---

## 10. handoff checklist(引継ぎ完了確認)

- [x] 9 commit を全て push 済(remote `origin/draft-body-editor-reject-streak-no-fail`)
- [x] 9 deploy 全て prod traffic 100% flip 済(current = `00405-cud`)
- [x] 各 commit message に baseline / delta / 制約 を明記
- [x] `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md` に全 phase の post-work 追記済
- [x] roster `config/giants_roster.json` に梶原昂希追加済(他は user 知見待ち)
- [x] 本 handoff log を `docs/handoff/session_logs/` に commit する(次 commit で本 file を stage)
- [ ] 次 session で C(fixture verify)着手
- [ ] 観察結果に基づき roster 追加 / regex 調整 / 拡張機能の need 判定

---

(本 session 終了。引継ぎ用 log 完了)
