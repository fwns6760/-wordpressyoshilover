# ヨシラバーブランディング post 仕様 (x-post-mail-lane)

date: 2026-05-20
scope: x-post-mail-lane の post 候補生成 全体仕様
status: spec draft (一部未実装 = TODO 明示)

## 1. 目的

user が 1 日数回受け取る mail に **巨人 X 投稿案** を並べる。user は mail を見て、気に入った案を 1-3 件選んで自分で X 投稿する。

目的は 2 つ:
- **ヨシラバー (yoshilover.com) のブランディング**: 巨人特化メディアとして X 上で存在感を出す
- **巨人ファン視点の voice**: 「のもとけ」 / フーガ / 缶詰 のような ファン目線の voice で書く (媒体目線の俯瞰中立 NG)

## 2. 配信 schedule (全 5 便/日)

| 便                     | cron (JST)     | 試合との関係                |
|------------------------|---------------|----------------------------|
| x-post-mail-am-1       | 07:00          | 前夜試合の振り返り              |
| x-post-mail-lunch      | 12:00          | 試合前 (デーゲーム前 / ナイター前) |
| x-post-mail-afternoon  | 15:00          | デーゲーム中 / ナイター前展望     |
| x-post-mail-evening    | 17:30          | ナイター直前 / 試合中            |
| x-post-mail-postgame   | 22:30          | 試合直後                      |

各便で mail 1 通、候補 8-10 件 / 通。

## 3. 候補 source の 4 種類

### 3.1 data ranking (main、insight.db ベース)

**何を出すか**: 巨人 player の metric ranking から「数字で語る」post 案。

**生成元**: `gs://baseballsite-yoshilover-insight/insight.db` の `batting_logs` / `pitching_logs` / `fielding_logs` などから query。

**metric × period の組み合わせ** (8 × 6 = 48 combo、samplesize filter で実質 10-15 combo):
- batting: AVG / OBP / SLG / OPS
- pitching: ERA / K_per_9 / BB_per_9 / HR_per_9
- fielding: 守備系 (data-insight whitelist で確定済、別 ticket 系)
- period: 直近 5 試合 / 直近 10 試合 / 直近 1 週間 / 今週 / 今月

**選出ロジック**:
- 各 combo で Giants top の player を 1 件 candidate 化
- `min_sample` (AB / IP / 守備機会 等の最低数) を満たす player のみ
- `lineup_focus` (今日のスタメン) 優先 mode

**dedup**:
- 24h 以内に出した signature `metric|period_label|focus_kind|None` は skip (signature-level dedup)
- 1 通あたり同一 player 上限 `_DEFAULT_PLAYER_MAX_PER_MAIL` (default 2、**TODO #71 で 1 に下げる**)
- **TODO #71**: starvation fallback で dedup を緩める時、**player-level dedup は維持** (signature だけ解除して同一 player を再採用しない)

**コスト**: 0 (insight.db 読み込みのみ)。

### 3.2 Gemma branding (ヨシラバー独自 voice、Tavily + Gemma 4)

**何を出すか**: Tavily で巨人関連 web 情報を集めて、Gemma 4 31B (Gemini API 経由 free tier) でヨシラバー voice の post を 1 件生成。

**code 位置**: `src/x_post_branding_gen.py:733` `build_gemma_branding_candidate`、`src/tools/run_x_post_mail.py:506` `_build_gemma_branding_candidates`

**flow**:
1. player を選ぶ (lineup_focus / 直近活躍 / news topic から)
2. Tavily で `"巨人 {player} 最新"` を web search (max 3 results、include_domains = `sports.yahoo.co.jp`, `hochi.news`)
3. insight.db から DB fact line (今日 / 直近 stat) を取得
4. Gemma 4 31B に system prompt + few-shot 例 + DB fact + Tavily snippet を渡して post 本文 1 件生成
5. spec 382 hard rule validator で safety check (URL / 媒体名 / 未検証数字 / hashtag 禁止)

**system prompt の構成** (`src/x_post_branding_gen.py:51` `_SYSTEM_PROMPT_BASE`):
- 「あなたは熱心な巨人ファンとして X 投稿案を書きます」
- hard rule (媒体名 / URL / hashtag / 未検証数字 全禁止、280 字以内、非元巨人 MLB NG)
- トーン規定 (本物の巨人ファンらしく、煽り定型語 NG: 「ついに」「我が軍」「いよいよ」等)
- **few-shot 例 2 件**: フーガ + 缶詰 のリアル post から合成した例 (試合後祝杯 / 試合前展望)
- **時間帯 tone hint** (実装済、`_build_system_prompt`):
  - 5-11 時 (朝便): softer、余韻、「噛み締めながら〜」
  - 11-17 時 (lunch / afternoon): 落ち着いた期待感
  - 17-22 時 (evening): ワクワク前のめり、「今夜は〜」
  - 22-5 時 (postgame): 祝杯 / 悔しさ全開、「完勝!」「ガチ凄い」

**env flag**:
- `X_POST_MAIL_GEMMA_GEN_ENABLED=1` (prod ON)
- `X_POST_MAIL_GEMMA_GEN_MAX=2` (default、便あたり 2 件)
- `GEMINI_API_KEY` / `TAVILY_API_KEY` (Secret Manager binding)

**silent skip 条件** (どれか hit したら None 返却、log は出る):
- player 不正 / 巨人 roster 不一致
- API key 不足
- Tavily 結果 0 件 (factual ground 無し → hallucination 抑制で生成しない)
- Gemma 失敗 (rate limit / network 等)
- spec 382 safety_check 失敗

**コスト**:
- Gemini API Gemma 4 31B: **free tier**
- Tavily API: 1,000 credits/月、現状 5 便 × 2 件 = 10 query/日 = 300 query/月 (限度内)

**TODO 検討中**:
- Tavily query にファン視点 keyword 追加 (`巨人 {player} 反応 ファン` 等)
- few-shot 例に「試合中 LIVE 実況」型 (缶詰の voice) を追加

### 3.3 fan_voice (試合時間帯のみ、新規、TODO)

**何を出すか**: 人気巨人ファンアカウント (フーガ + 缶詰、user 追加可) の **リアルツイートそのもの** を「参考」candidate として mail に並べる。Gemma 生成ではなく literal copy + 出典明記。

**目的**: 試合中の **ファンの熱量** を user に届ける。user はそれを見て自分の post を書く参考にする。

**source**:
- フーガ `@EH87EazmV9D2eSw` — 長文分析系、試合後振り返り voice
- 缶詰 `@kandume92` — 試合中 LIVE 実況系、連呼 voice
- 追加候補は user 判断

**取得経路**:
- RSSHub (prod Cloud Run service `rsshub-487178857517...`) の `twitter/user/<handle>` endpoint
- cache TTL 5 分
- 1 feed あたり最新 19 件
- yoshilover-fetcher が定期 fetch、`source_type="fan_voice_pool"` で GCS jsonl に永続化

**発動条件** (2 条件 AND):
1. 便が `x-post-mail-evening` (17:30) または `x-post-mail-postgame` (22:30)
2. 当日試合あり (insight.db `games` table で `game_date = today` の row 存在)

**選出ロジック** (TODO 詳細):
- 直近 24h 以内のツイート
- 巨人選手名 NER で 1 つ以上含む (roster 照合)
- 文字数 20-280
- emotion gate (感情語含む or like 数推定 proxy)
- 1 mail あたり 1-2 件、handle 多様性 (フーガ + 缶詰 から 1 件ずつ理想)

**mail 表示 format**:
```
## (参考) 巨人ファン X 投稿
「俺たちの坂本勇人!!! サヨナラホームラン!!!」
@kandume92 (5/19 22:43 JST)
→ https://x.com/kandume92/status/...
→ この voice を参考に、独自表現で post 案を書く
```

**著作権 / 配慮**:
- 私的閲覧 (user の mail) のみ literal 表示 OK
- WP / X に literal 転載は NG。user が手動で X 投稿する時は **引用元 @user 明示 + 自分の独自表現** で書く
- 過度な類似 / 連続引用は避ける (1 mail 1-2 件 cap)

**コスト**: 0 (RSSHub + GCS、既存 infra 内)。

**配管 status** (verify 済):
- RSSHub: alive、`twitter/user` 動作確認済
- `source_type="fan_voice_pool"` 取り込み code: 実装済 (`rss_fetcher.py:2554`)
- in-process cache: 実装済 (`_FAN_VOICE_POOL_CACHE`)
- **GCS 永続化**: **未実装 (TODO)**
- **x-post-mail 側 fan_voice 読込**: **未実装 (TODO)**
- **試合有無判定**: **未実装 (TODO)**

**env flag** (TODO):
- `X_POST_MAIL_FAN_VOICE_ENABLED` (default OFF、smoke 後 ON 切替)

### 3.4 news_opinion (data 枯れ時 fallback、既存)

**何を出すか**: 巨人関連ニュース記事の opinion 段落を引用、player 名を含む post 候補化。

**生成元**: rss_sources.json の媒体記事 (sponichi / hochi / sanspo / tokyo_sports / nikkansports 等)。

**発動条件**: data ranking 候補が `<3` まで枯れた時 (Gemma OFF route の場合)、または news_priority_count 設定時。

**現状の役割**: data 系の補完。Gemma が enable された path では基本走らない (Gemma が news_fallback を代替)。

## 4. 全体の合成 (1 mail の中身)

| 便       | data | Gemma | fan_voice | news (fallback) | 合計目標 |
|----------|------|-------|-----------|-----------------|---------|
| 07:00    | 4-6  | 2     | -          | 枯れ時のみ        | 8-10    |
| 12:00    | 4-6  | 2     | -          | 枯れ時のみ        | 8-10    |
| 15:00    | 4-6  | 2     | -          | 枯れ時のみ        | 8-10    |
| 17:30    | 4-6  | 2     | **1-2 (試合あり日)** | 枯れ時のみ | 8-10 |
| 22:30    | 4-6  | 2     | **1-2 (試合あり日)** | 枯れ時のみ | 8-10 |

`X_POST_MAIL_MAX_CANDIDATES` (default 10) で 上限制御。

## 5. dedup ルール

### 5.1 signature-level dedup (既存)

- 24h 以内に mail に出した signature `metric|period_label|focus_kind|None` は skip
- signature は data / Gemma / fan_voice 共通 (gemma は hash 別、fan_voice は tweet URL hash)
- 永続化先: `gs://baseballsite-yoshilover-insight/x_post_mail/dedup/<date>.jsonl`

### 5.2 player-level dedup (新規、#71 で実装予定)

- starvation fallback (24h dedup で候補 <3 まで枯れた時) で signature dedup を OFF にする時、**player は維持**
- 24h 以内に mail に出た player は fallback でも skip (ranking 2-3 位の player を採用)
- 0 candidates まで完全に枯れた時のみ、最後の手段として player dedup も OFF (今と同じ最後の砦)

### 5.3 player cap (新規、#71 で 2→1 に下げる)

- 1 mail あたり同一 player 上限: 2 → **1** に変更
- `X_POST_MAIL_PLAYER_MAX_PER_MAIL` で override 可 (postgame で戸郷複数 metric 出す用途は残せる)

## 6. 時間帯条件 (試合の有無)

### 6.1 試合有無判定 (新規、TODO)

`insight.db` の `games` table から `game_date = today (JST)` の row が存在するか確認。

- 試合あり日 → fan_voice 発動条件の 1 つを満たす
- 試合無し日 (火曜定休 / 移動日) → fan_voice 発動しない、data + Gemma + news のみ

### 6.2 fan_voice 発動マトリクス

| 便       | 試合あり日 | 試合無し日 |
|----------|-----------|-----------|
| 07:00    | -          | -          |
| 12:00    | -          | -          |
| 15:00    | -          | -          |
| 17:30    | **○**       | -          |
| 22:30    | **○**       | -          |

## 7. failure modes / silent skip 可視化

### 既知の silent skip

| source       | 主な silent skip 条件             | 現状の log                          |
|--------------|----------------------------------|-------------------------------------|
| data         | sample 不足 / 24h dedup 当たり    | INFO `dedup skip combo ...` / `Too few rows ...` |
| Gemma        | roster 不一致 / Tavily 0 件 / safety 失敗 | INFO `gemma_branding_skip reason=...` |
| fan_voice    | (未実装、TODO)                     | (未実装)                            |
| news_opinion | player_history で過去採用 / 鮮度切れ | INFO `news_opinion_fallback_player_history_skip ...` |

### 0 件回避ロジック (Starvation fallback)

`run_x_post_mail.py` L833-867:

```
24h dedup left only N candidates (<3); retrying without dedup
  → relaxed pick で candidate 再構築
  → 結果を _backfill_dedup_starved_candidates で merge
```

TODO #71: この path に **player-level dedup を追加**。

## 8. コスト hygiene

- Gemini API: free tier 厳守 (Gemma 4 31B のみ、Pro 切替禁止)
- Tavily API: 1,000 credits/月 厳守 (paid plan 加入禁止)
- Cloud Run: 既存 service 内 (新規 service 追加なし)
- GCS: x_post_mail/dedup + fan_voice/pool で 数 MB / 月

§11 4 領域 (法務・著作権・プライバシー・金銭・外部 API 課金増) に該当するのは:
- Gemini Pro 切替 (NG)
- Tavily paid plan (NG)
- X API 課金 (NG、$200/月)
- Grok x_search (env 未配線、$0 制約で見送り中)

## 9. 関連 issue / ticket

- **#70 (396)** [CLOSED]: 浦田 / ダルベック 頻出原因 evidence 調査 (本 spec の前提となる調査)
- **#71 (397)** [OPEN]: starvation fallback の player-level dedup 欠落 (Fix 1、本 spec §5.2 / 5.3)
- **#66 (391)** [OPEN]: 巨人 X 投稿案生成 — Tavily MCP + Gemma 4 (本 spec §3.2 の前身、CLI smoke)
- **(新規予定)**: fan_voice 配管 + 試合時間帯条件発動 (本 spec §3.3)

## 10. 段階 fire roadmap

| Step | 内容 | priority |
|------|------|----------|
| 1 | #71 着地 (player-level dedup + player_max 2→1) | P1 |
| 2 | fan_voice config (rss_sources に フーガ / 缶詰 追加、`source_type=fan_voice_pool`) | P2 |
| 3 | fan_voice GCS 永続化 (yoshilover-fetcher → upload jsonl) | P2 |
| 4 | x-post-mail に fan_voice 読込 + 試合有無判定 + 17:30/22:30 便のみ candidate 出力 | P2 |
| 5 | flag `X_POST_MAIL_FAN_VOICE_ENABLED=1` で smoke、OK なら維持 | P2 |
| 6 | Gemma 品質改善 (Tavily query にファン視点 keyword、few-shot 拡張) | P3 (観察後) |
| 7 | fan_voice account 追加 (user が「この人」と気づいた時) | 随時 |

## 11. 未解決 / 検討中

- fan_voice の emotion gate / 選出 logic の詳細
- fan_voice candidate を Gemma の context に注入するか (mail に literal 表示するだけか)
- 試合中 (LIVE) と 試合直後 (post) で fan_voice の出し方を分けるか
- Gemma の hashtag / 絵文字 policy (現状 hashtag 禁止、絵文字 policy 未定義)
- mail subject 行の改善 (試合あり日 / 無し日 / 連勝中 等で subject 出し分け)
