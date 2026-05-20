# x-post-mail 固定スタメン頻出原因 evidence 調査 (GH Issue #70 / 396)

date: 2026-05-20 JST
scope: read-only investigation only (DB read / GCS read / Cloud Run log read)
trigger: user 指摘「浦田 / ダルベック が毎回入っている、朝便だけではない」

## 結論 (TL;DR)

真因は **2 つの設計**:

1. **starvation fallback が dedup を完全 OFF にして re-pick する** (`run_x_post_mail.py` L833-867)
2. **fallback path に player-level dedup が無い** (`_backfill_dedup_starved_candidates` は signature dedup のみ、player は見ていない、L402-425)

候補 pool が 24h dedup + sample-size filter で `<3 candidates` まで枯れると、code は `pick_candidates(dedup_set=None)` で再実行し、結果を merge する。dedup signature `OBP|今月|False|None` のような既出 signature だけは seen_signatures で再除外されるが、**同一 player の別 metric (例: AVG|直近10試合) は素通り**。

加えて `_DEFAULT_PLAYER_MAX_PER_MAIL = 2` (`x_post_mail_lane.py:840`) で 1 通あたり同一 player 2 candidates まで許容しているため、starvation fallback 経由で構造的 top player (浦田) が 1 通に 2 candidates 入る。

連日同じ player が出るのは、浦田が **本当に巨人 batting metric の構造的 top** であるため (insight.db 再現で AVG|今月 0.375 #1 / AVG|直近10試合 0.458 #1)。

## Step 1: 5/19 + 5/20 dedup jsonl 便別分解

source: `gs://baseballsite-yoshilover-insight/x_post_mail/dedup/2026-05-{18,19,20}.jsonl`

注意: 5/18 までは jsonl に `focus_player` field なし。5/19 から player 情報が記録される。

### 5/19 (全 5 便 + extra 1 = 6 fires)

| ts (JST)   | entries | players (count)                                                                                     |
|------------|---------|-----------------------------------------------------------------------------------------------------|
| 07:01      | 10      | 坂本, ルシアーノ, 森田, 園田, 岡田悠希, 岸田, 則本, **浦田**, 佐々木, 増田 (NEWS_OPINION 5 + data 5)        |
| 12:01      | 10      | 荒巻, 中田, 松本剛, 中山, 長野, 平山, キャベッジ, **浦田**, マルティネス, 吉川                                 |
| 15:00      | 10      | 鈴木, 田和, 大勢, 丸, 甲斐, 平山, 岸田, マルティネス, 則本, **浦田**                                          |
| 17:30      | 10      | 船迫, 宮原, 小林, 西川, 田村, 平山, **浦田**, マルティネス, キャベッジ, 岸田                                  |
| 22:30      | 8       | 戸郷×3 (ERA直近10 / K_per_9直近10 / K_per_9直近5), **浦田×2** (AVG今月 / OBP今月), 平山, 吉川(gemma), 泉口(gemma) |
| 23:42      | 5       | 戸郷×2 (ERA直近5 / BB_per_9直近10), 大城, 吉川(gemma), 泉口(gemma)                                       |

### 5/20 (am-1 のみ、調査時点 09:41 JST)

| ts (JST) | entries | players (signature)                                                                                                   |
|----------|---------|-----------------------------------------------------------------------------------------------------------------------|
| 07:00    | 6       | **浦田×2** (OBP直近10 / AVG直近10), 井上温大×2 (SLG直近10 / gemma_branding), **ダルベック×1** (OPS今月), (roundup)×1 (team_roundup) |

## Step 2: 5/20 07:00 + 5/19 22:30 Cloud Run log 取得

### 5/20 07:00 JST log (Cloud Run job `x-post-mail-lane`)

```
22:00:27 Loaded 24h dedup set: 43 signatures
22:00:27 Loaded 24h player history: 32 players, 53 appearances
22:00:27 Picking candidates (max=10, min_sample=30, db_path=True, dedup=43)…
22:00:39 dedup skip combo OBP/直近10試合 (signature=OBP|直近10試合|False|None)
22:00:39 dedup skip combo OPS/直近10試合 ...
22:00:39 dedup skip combo OBP/今月 ...
22:00:39 dedup skip combo SLG/直近10試合 ...
22:00:39 dedup skip combo OBP/直近5試合 ...
22:00:39 dedup skip combo SLG/直近5試合 ...
22:00:39 dedup skip combo OPS/今月 ...
22:00:39 dedup skip combo AVG/直近10試合 ...
22:00:39 dedup skip combo AVG/今月 ...
22:00:39 dedup skip combo OPS/直近5試合 ...
22:00:39 dedup skip combo SLG/今月 ...
22:00:39 dedup skip combo AVG/直近5試合 ...
22:00:39 WARNING 24h dedup left only 0 candidates (<3); retrying without dedup to avoid starving scheduled mail.
22:00:39 player_diversity_alternate_selected metric=SLG period=直近10試合 skipped_player=大城卓三 selected_player=井上温大
22:00:39 player_diversity_alternate_selected metric=OPS period=今月 skipped_player=浦田俊輔 selected_player=ダルベック
22:00:39 player_diversity_duplicate_fallback metric=AVG period=直近10試合 player=浦田俊輔 count_before=1 cap=2
22:00:39 Dedup fallback backfilled candidates: 0 -> 4
22:02:41 Recorded 6 dedup signatures (ok=True)
```

key signal:
- 通常 dedup pre-pass は 0 candidates まで枯れた
- starvation fallback (`dedup_set=None`) で 4 candidates 再構築
- 浦田は OPS|今月 で alternate (ダルベック) に振替えられたが、AVG|直近10試合 で `duplicate_fallback` (1 通 2 件目) として再採用

### 5/19 22:30 JST log (postgame fire、ほぼ同じ pattern)

```
13:30:33 Loaded 24h dedup set: 38 signatures
13:30:35 dedup skip combo K_per_9/直近5試合 ...
13:30:35 dedup skip combo AVG/今月 ...
13:30:35 dedup skip combo SLG/今月 ...
13:30:35 dedup skip combo OBP/今月 ...
... (16 件 dedup skip)
13:30:35 player_diversity_duplicate_fallback metric=K_per_9 period=直近10試合 player=戸郷翔征 count_before=1 cap=2
13:30:35 WARNING 24h dedup left only 2 candidates (<3); retrying without dedup ...
13:30:35 player_diversity_duplicate_fallback metric=OBP period=今月 player=浦田俊輔 count_before=1 cap=2
13:30:35 player_diversity_duplicate_fallback metric=ERA period=直近10試合 player=戸郷翔征 count_before=1 cap=2
13:30:35 Dedup fallback backfilled candidates: 2 -> 6
```

同 pattern 確認。

## Step 3: 浦田 / ダルベック metric ranking 再現 (insight.db)

source: `gs://baseballsite-yoshilover-insight/insight.db` (latest_game_date=2026-05-19)

### 巨人 今月 AVG (2026-05-01 以降、AB>=30、SUM(H)/SUM(AB))

| rank | player    | g  | AB  | H  | AVG   |
|------|-----------|----|-----|----|-------|
| 1    | **浦田俊輔**  | 10 | 32  | 12 | **.375** |
| 2    | 平山 功太     | 9  | 35  | 12 | .343  |
| 3    | 大城卓三      | 12 | 39  | 11 | .282  |
| 4    | **ダルベック** | 15 | 53  | 14 | **.264** |
| 5    | 増田陸       | 10 | 35  | 9  | .257  |

### 巨人 直近10試合 AVG (AB>=5)

| rank | player    | g | AB | H  | AVG    |
|------|-----------|---|----|----|--------|
| 1    | **浦田俊輔**  | 7 | 24 | 11 | **.458** |
| 2    | 岸田 行倫     | 2 | 7  | 3  | .429   |
| 3    | 平山 功太     | 6 | 24 | 10 | .417   |
| 4    | 吉川尚輝      | 7 | 27 | 10 | .370   |
| 5    | 大城卓三      | 7 | 25 | 9  | .360   |
| 8    | ダルベック     | 9 | 34 | 8  | .235   |

結論: **浦田は本物の構造的 #1** (今月 / 直近10試合 ともに巨人 batting AVG top)。連日採用は signal として正しい。ダルベックは AVG 系では top でないが、AB 多い (53) で OPS|今月 系で上位の可能性高 (HR 等 power 数値要確認だが、構造的に regular top 圏内)。

## Step 4: 5/19 cross-fire 採用回数 ranking (Giants regulars)

| player    | fires (out of 5+1) | fire ts                                       |
|-----------|--------------------|-----------------------------------------------|
| **浦田俊輔** | **5/5 (100%)**     | 07:01 / 12:01 / 15:00 / 17:30 / 22:30           |
| 平山 功太   | 4/5                 | 12:01 / 15:00 / 17:30 / 22:30                   |
| 岸田 行倫    | 3/5                 | 07:01 / 15:00 / 17:30                          |
| マルティネス  | 3/5                 | 12:01 / 15:00 / 17:30                          |
| 吉川尚輝     | 3/5                 | 12:01 / 22:30 / 23:42 (gemma)                   |
| 則本昂大     | 2/5                 | 07:01 / 15:00                                  |
| キャベッジ    | 2/5                 | 12:01 / 17:30                                  |
| 戸郷翔征     | 2/6                 | 22:30 (3 cand) / 23:42 (2 cand)                |
| 泉口友汰     | 2/6                 | 22:30 / 23:42 (両方 gemma)                       |

「毎便」状態は **浦田だけ**。「ほぼ毎便」が平山。**ダルベックは 5/19 0 件 / 5/20 朝便 1 件のみ** で「毎便」ではない (user 指摘の頻度感はバイアスあり)。

## Step 5: 仮説 A-E 切り分け

| 仮説 | 内容 | 判定 |
|------|------|------|
| A | dedup signature が `metric|period_label|focus_kind|None` で player を含まない | 仕様通り (player は別 field)、これ自体は問題ない |
| B | 24h history avoid (`recent_player_counts`) が weak | 真。fallback path で `recent_player_counts` 渡しても player cap=2 で甘い |
| C | combo pool 8 metric × 6 期間 + 固定スタメン構造 | 真 (背景要因)、巨人 regulars が日替わりに動かないため top 同じ player に集中する |
| D | `_DEFAULT_PLAYER_MAX_PER_MAIL = 2` | 真。5/20 朝便で浦田が 1 通 2 candidates、5/19 22:30 で戸郷 3 candidates |
| **E** | **便間 cross-fire dedup 無効化** | **真因**。`_backfill_dedup_starved_candidates` は **signature dedup のみ**、player dedup は無い。starvation fallback で同一 player 別 metric が素通り |

## Step 6: narrow fix issue 起票方針

3 段階で起票予定 (priority 順):

### Fix 1 (最強): starvation fallback の player-level dedup
- `_backfill_dedup_starved_candidates` に player-level seen set を追加
- 24h dedup 履歴から `recent_player_counts >= 1` の player は fallback でも skip
- ただし 0 candidates まで枯れた時のみ最終 fallback として player dedup も緩和

### Fix 2: `_DEFAULT_PLAYER_MAX_PER_MAIL` を 1 に下げる
- 1 通あたり同一選手 1 candidate を default に
- 環境変数で override 可能のまま (postgame で戸郷複数 metric 出したい時用)

### Fix 3 (予防): combo pool 拡張 or news_opinion 比率引き上げ
- data 系 combo が枯れる構造を緩和 (lineup_focus_min_candidates 調整、または news_opinion ratio を増やす)
- ただし Fix 1 で十分かどうか観察してから着手

## 副作用確認

read-only investigation only:
- DB / WP / Scheduler / Cloud Run / mail に書き込み 0
- GCS は `gs://baseballsite-yoshilover-insight/x_post_mail/dedup/*.jsonl` と `insight.db` を **download のみ** (upload なし)
- Cloud Run logs は `gcloud logging read` のみ (delete / write なし)
