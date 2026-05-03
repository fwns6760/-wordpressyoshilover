# 2026-05-03 Lane Y hochi.news / 報知巨人X anchor stuck draft audit

作成: 2026-05-03 JST

## mode

- request type: read-only audit
- scope: hochi.news / `hochi_giants` / `SportsHochi` anchor の stuck draft scan と publish 候補抽出
- repo mutation: this doc only
- live mutation: 0
- WP REST write / mail send / history write / queue write: 0

## authoritative inputs

- latest guarded history mirror: `/tmp/guarded_publish_history_live_20260503.jsonl`
  - latest snapshot used for per-id status: **2026-05-03 19:15:37 JST**
- local draft backup set: `logs/cleanup_backup/*.json`
- subtype / source fact補助:
  - `docs/ops/preview_v0/*`
  - `/tmp/lane_y_preview_20260503/*.md`

Important limitation:

- per-post raw `title_template_selected` log line was not locally mirrored for all IDs.
- For the table below, `title` is the surviving draft title (`title.rendered`) and is used as the practical proxy for the selected rewritten title.
- `duplicate_target_post_id` / `duplicate_target_source_url` are **not** present in the latest history row for this Lane Y set. When a duplicate signal exists, it appears only as the hold gate `hard_stop_lineup_duplicate_excessive`.

## Step 1-2 counts

- latest unique posts in live mirror: **616**
- latest stuck posts (`status=refused|skipped`): **434**
- stuck posts with local backup recoverable in this sandbox: **14**
- recoverable posts matching Lane Y primary/optional source family: **11**
  - primary `hochi_giants` / `SportsHochi` / `hochi.news`: **7**
  - optional `nikkansports.com`: **4**
  - recovered direct `hochi.news/articles/...`: **0**
  - recovered `sponichi.co.jp` / `sanspo.com` / `yomiuri.co.jp` / `npb.jp` / `giants.jp`: **0**

Notes:

- The filtered 11 are all backlog-era items whose latest stuck record is fresh on **2026-05-03 JST**, but whose underlying article content is older (`modified` dates mostly `2026-04-20` to `2026-04-26`).
- `63331` and other non-Hochi X items were excluded because their source family was outside the Lane Y primary set and outside the optional domain list requested here.

## Step 3 per-id detail

| post_id | latest ts (JST) | title | subtype (best effort) | source_url(s) | hold_reason | duplicate signal | keyword hit | Giants relevance | bucket | note |
|---|---|---|---|---|---|---|---|---|---|---|
| `63101` | `2026-05-03 08:20:39` | `巨人DeNA戦 山口俊氏先発でどこを見たいか` | `postgame template drift / comment` | `https://www.nikkansports.com/baseball/news/202604190000914.html` | `hard_stop_lineup_duplicate_excessive` | gate only, target unknown | `comment` | yes | `B` | source is山口俊氏の戸郷評。title-body mismatchが強く、preview facts coverageも低い。 |
| `63103` | `2026-05-02 20:45:34` | `則本昂大は何を見せたか` | `postgame template drift` | `https://twitter.com/hochi_giants/status/2046080983909187996` / `https://twitter.com/SponichiYakyu/status/2046122778026541191` | `hard_stop_lineup_duplicate_excessive` | gate only, target unknown | none | surface yes / fact integrity NG | `B` | `巨人・則本昂大` は事実整合が取れず、本文にも `スコア -` placeholder が残る。 |
| `63109` | `2026-05-03 19:15:37` | `則本昂大「いいそばを見つけて食べたい」 実戦で何を見せるか` | `player_comment` | `https://www.nikkansports.com/baseball/news/202604200000891.html` | `backlog_only` | none | `comment` | surface yes / fact integrity NG | `B` | `読売ジャイアンツ所属の則本昂大` という本文核が破綻。publish候補から外す。 |
| `63118` | `2026-05-03 19:15:37` | `巨人DeNA戦 戸郷翔征先発でどこを見たいか` | `postgame template drift / comment` | `https://www.nikkansports.com/baseball/news/202604190000857.html` | `backlog_only` | none | `comment` | yes | `B` | sourceは山口俊氏の戸郷評。titleは試合前記事化しており drift が大きい。 |
| `63127` | `2026-05-03 19:15:37` | `山城京平「チャポンと入るようなイメージで…」 ベンチの狙いはどこか` | `manager / coach comment` | `https://twitter.com/hochi_giants/status/2046326487444312501` / `https://twitter.com/SportsHochi/status/2046326850067001408` | `backlog_only` | none | `コーチ`, `コメント` | yes | `A` | 報知巨人X + SportsHochi の二重 anchor。coach comment 系で source 核が明確。 |
| `63137` | `2026-05-03 19:15:37` | `先週のMVP＆今週の展望 坂本勇人得意の地方球場で300号だ 打率.290…` | `farm_result wrapper / weekly roundup` | `https://www.nikkansports.com/baseball/news/202604200001447.html` | `backlog_only` | none | `farm` | yes | `B` | `先週のMVP＆今週の展望` の週次 roundup。単発 publish 向きでなく、preview facts coverage も弱い。 |
| `63155` | `2026-05-03 19:15:37` | `ドラ１竹丸和幸は中１１日でフルパワー！「体力的に元気になった」 ３勝目懸け２…` | `player / farm note` | `https://twitter.com/hochi_giants/status/2046440814222483474` | `backlog_only` | none | `comment`, `farm` | yes | `C` | source核は明確だが、本文が `22日・中日戦へ` の stale next-start angle。publishするなら manual stale judgment が要る。 |
| `63203` | `2026-05-03 19:05:39` | `巨人中日戦 試合前にどこを見たいか` | `pregame / probable starter` | `https://twitter.com/hochi_giants/status/2046504553936552145` | `hard_stop_lineup_duplicate_excessive` | gate only, target unknown | none | yes | `B` | `あす4/22の予告先発` の古い pregame only。duplicate gate も付いており止める。 |
| `63232` | `2026-05-03 19:15:37` | `石塚裕惺、試合開始１分前に長野の球場到着→代打出場…負傷の泉口に代わり緊急昇…` | `roster_notice / injury-related farm rescue` | `https://twitter.com/hochi_giants/status/2046593087502188994` | `backlog_only` | none | `負傷`, `緊急昇格`, `roster` | yes | `A` | user priorityど真ん中。負傷起点の緊急昇格で、preview rescue も通る。 |
| `63274` | `2026-05-03 19:05:39` | `巨人ヤクルト戦 試合の流れを分けたポイント` | `postgame goods drift` | `https://twitter.com/hochi_giants/status/2046865012812046574` | `hard_stop_lineup_duplicate_excessive` | gate only, target unknown | none | yes | `B` | source核は `ウィットリー記念グッズ`。postgame 本文に `スコア -` が残り、body drift が強い。 |
| `63634` | `2026-05-03 19:15:37` | `戸郷翔征が「投手兼ＤＨ」で出場 １軍戦見据えて打席にも立つ予定 丸佳浩、中山…` | `farm important / lineup-adjacent` | `https://twitter.com/hochi_giants/status/2048240341006819675` | `backlog_only` | none | `farm` | yes | `A` | 4/26 source でこの母集団では比較的新しい。二軍・一軍接続のファーム重要情報として残す価値あり。 |

## Step 4 bucket summary

- `A fan-important publish candidate`: **3**
  - `63127`
  - `63232`
  - `63634`
- `B stop`: **7**
  - `63101`, `63103`, `63109`, `63118`, `63137`, `63203`, `63274`
- `C manual review`: **1**
  - `63155`

Bucket logic applied:

- `A`: source family fit + Giants relevant + duplicate target不明の hard gateなし + placeholder/body driftが決定的ではない + fan-interest軸が明確
- `B`: fact break, old pregame-only, roundup wrapper, goods/postgame drift, or duplicate gate付きの old lineup/pregame
- `C`: fan-interest はあるが stale angle が露骨で、publish now と stop の間に human judgment が必要

## Step 5 publish candidate list

Assumption for mail count:

- live publish lane で 1 post publish ごとに notice mail `+1`

| post_id | title | reason | 想定 mail | rollback hint |
|---|---|---|---:|---|
| `63127` | `山城京平「チャポンと入るようなイメージで…」 ベンチの狙いはどこか` | `hochi_giants` + `SportsHochi` の二重 anchor。`コーチ/コメント` hit。latest は `backlog_only` だけで duplicate target なし。 | `+1` | live publish 後に外すなら `post_id=63127` を WordPress で `draft` に戻す。 |
| `63232` | `石塚裕惺、試合開始１分前に長野の球場到着→代打出場…負傷の泉口に代わり緊急昇…` | `hochi_giants` anchor。`負傷` + `緊急昇格` + roster/injury 系。preview rescue evidence も strongest。 | `+1` | live publish 後に外すなら `post_id=63232` を WordPress で `draft` に戻す。 |
| `63634` | `戸郷翔征が「投手兼ＤＨ」で出場 １軍戦見据えて打席にも立つ予定 丸佳浩、中山…` | `hochi_giants` anchor。`farm` important info。4/26 source で this cohort 内では比較的新しい。 | `+1` | live publish 後に外すなら `post_id=63634` を WordPress で `draft` に戻す。 |

## Step 6 mail estimate

- expected mail delta if live lane publishes all `A` rows once: **`+3 mails`**

## recommended next action

- Lane Y itself remains **read-only complete**.
- If user wants actual publish, fire a separate live lane with this exact narrow set:
  - `63127`
  - `63232`
  - `63634`
- Keep `63155` out of blind publish; require manual stale judgment first.
