# 238 night-draft-only mode + morning decision report

## meta

- number: 238
- type: design + plan
- status: WAITING
- priority: P0.5
- parent: -
- related: 230-A / 230-A1 / 230-D / 229-A / 232 / 235 / 236-A / 227 / 113-A
- lane: A / Claude
- created: 2026-04-28
- mode: read-only audit + new doc 1 file only

## background

2026-04-29 queue triage:

- still useful for reducing night-time user burden
- moved out of `active/` because 234 / 244 template and numeric hallucination hardening is the immediate quality lane
- bring back after body quality stabilizes and the next step is night publish/mail suppression

GCP budget が 1,500 円帯に到達したため、夜間 23:00-07:00 JST は「公開・通知・外部露出」を止め、朝に 1 枚の判断レポートで `GO / HOLD / STOP` を返せる運用へ寄せる。night-draft-only の狙いは、速報取り込みと draft 候補化は止めず、publish / mail / X / 非本線 WP mutation を夜間から切り離すことにある。

本票は実装ではなく、read-only audit と実装分解までを固定する。`src/` / `tests/` / `config/` / GCP live / Scheduler / Cloud Run / WP / X / mail / Gemini API 実 call には触らない。

### night-draft-only contract(v1)

- 夜間に **残す** もの: RSS/news 取得、draft 新規作成、subtype 推定、duplicate skip、cost ledger、structured log、shadow ledger
- 夜間に **止める** もの: WP publish、WP delete、noindex 変更、mail fan-out、X live post、既存 draft への修復 PUT
- 例外として許容する WP write: `yoshilover-fetcher /run` による **new draft create** のみ

### observed state(2026-04-28 JST read-only)

- 実行コマンド:
  - `gcloud scheduler jobs list --project=baseballsite --location=asia-northeast1`
  - `gcloud run jobs list --project=baseballsite --region=asia-northeast1`
  - `gcloud run services list --project=baseballsite --region=asia-northeast1`
  - `gcloud scheduler jobs describe <name> ...`
- 観測結果:
  - Scheduler jobs total: **28**
  - Cloud Run Jobs total: **8**
  - Cloud Run Services total: **8**
  - `publish-notice-trigger` は **2026-04-28 JST 時点でも `*/5`**。`230-A1` は runbook であり、live apply はまだ入っていない
  - `fact-check-morning-report` は **2026-04-28 JST 時点でも `0 * * * *`**。日次 morning report 専用化は未実施
  - `audit-notify-6x` は **PAUSED**
  - active scheduler / Cloud Run Job inventory では **X 自動投稿 lane は観測されなかった**

## Step 1. publish-side scheduler / Job 棚卸し

night-mode に直接関係する subset だけを抽出する。`230-D` で確認された通り、`giants-*` non-realtime 14 本はすべて `POST /run` で `giants-realtime-trigger` と scheduler-visible contract が同一なので、本票では group 扱いにする。

| name | current schedule / state | endpoint / Job | side effect 種類 | 夜間扱い |
|---|---|---|---|---|
| `guarded-publish-trigger` | `*/5 * * * *` / `ENABLED` | Cloud Run Job `guarded-publish` | **WP publish 状態変更**(`draft -> publish`)、cleanup backup/history 更新 | **止める** |
| `publish-notice-trigger` | `*/5 * * * *` / `ENABLED` | Cloud Run Job `publish-notice` | **mail 送信**、manual X candidate mail 生成 | **止める**。朝 1 通へ集約 |
| `draft-body-editor-trigger` | `2,12,22,32,42,52 * * * *` / `ENABLED` | Cloud Run Job `draft-body-editor` | **WP draft content PUT**、repair ledger | **止める推奨**。draft-only は「新規 draft create のみ許容」と解釈する |
| `codex-shadow-trigger` | `*/5 * * * *` / `ENABLED` | Cloud Run Job `codex-shadow` | shadow 学習、ledger only、WP write なし | **維持** |
| `giants-realtime-trigger` | `*/5 * * * *` / `ENABLED` | Cloud Run Service `yoshilover-fetcher` `POST /run` | **RSS/news 取得 + new draft create** | **維持** |
| `giants-* overlay set` | various / mostly `ENABLED` | Cloud Run Service `yoshilover-fetcher` `POST /run` | `giants-weekday-post` / `giants-postgame-catchup-am` / weekend lineup/post windows。いずれも **draft create + candidate accumulation** | **維持**。overlap 整理は `230-D` 別便 |
| `audit-notify-6x` | `0 10-23 * * *` / `PAUSED` | Cloud Run Service `yoshilover-fetcher` `GET /audit_notify?window_minutes=60` | **mail 送信**(audit 通知) | **夜間は止める**。現状 PAUSED を維持、再開時も day-only 前提 |
| `fact-check-morning-report` | `0 * * * *` / `ENABLED` | Cloud Run Service `yoshilover-fetcher` `GET /fact_check_notify?since=yesterday` | **mail 送信**(fact-check report) | **朝判断へ寄せる**。238 では 07:00 JST の専用 morning report を別実装推奨 |

### inventory notes

- Cloud Run Jobs observed: `codex-shadow`, `draft-body-editor`, `family-fetch-gsc`, `fetch-gsc`, `guarded-publish`, `prosports-crawl-internal-links`, `prosports-fetch-gsc`, `publish-notice`
- Cloud Run Services observed: `fetcher`, `ga4-traffic-analyzer`, `gijiroku`, `rsshub`, `seo-analyzer-sample`, `seo-analyzer-web`, `seo-rank-tracker-web`, `yoshilover-fetcher`
- night-mode の主対象は **8 scheduler groups**。このうち publish/mail/audit 系は 4、fetch/shadow 系は 4

## Step 2. 止める処理 / 残す処理 / 朝判断へ回す処理

| class | flow | current source | policy | note |
|---|---|---|---|---|
| 止める | WP publish 状態変更 | `guarded-publish-trigger` | **OFF** | 23:00-07:00 JST は publish 0 件が原則 |
| 止める | WP delete / noindex 変更 | active scheduler では未観測 | **OFF** | 将来 path が増えても quiet-hours では禁止対象 |
| 止める | mail fan-out / burst summary / urgent / warning | `publish-notice-trigger`, `audit-notify-6x`, existing review mail lanes | **OFF** | 夜間 mail を朝 1 通の summary に集約 |
| 止める | 既存 draft の修復 PUT | `draft-body-editor-trigger` | **OFF 推奨** | draft-only の例外は new draft create のみ |
| 止める | X live post | active GCP inventory では未観測 | **OFF** | 自動 X が将来追加されても quiet-hours では禁止 |
| 残す | RSS/news 取得 | `giants-realtime-trigger`, `giants-* overlay set` | **ON** | realtime 本線は止めない |
| 残す | new draft create | `yoshilover-fetcher /run` | **ON** | 朝の候補母集団を確保する |
| 残す | subtype 推定 / duplicate skip / no-op skip / rule-based skip | fetcher / repair lane logs | **ON** | 朝 report の診断材料を夜間に蓄積する |
| 残す | shadow ledger / cost ledger / structured logs | `codex-shadow-trigger`, `llm_cost` emit | **ON** | 可観測性は維持する |
| 朝判断 | publish 実行 | guarded publish lane | **07:00 以降に GO/HOLD/STOP** | quiet-hours 中は 0 件が期待値 |
| 朝判断 | X candidate review | publish-notice candidate aggregation | **07:00 以降** | 夜間は候補化まで、投稿はしない |
| 朝判断 | review mail flush | publish-notice / morning report | **07:00 以降** | 1 通に圧縮して送る |

### design decision

`draft-body-editor` は publish ではないが、night-draft-only を「**draft create は許すが、既存 post/draft の content mutation は止める**」と定義すると OFF 側に入る。これにより、夜間に残る WP mutation は `yoshilover-fetcher /run` の new draft create だけになる。

## Step 3. night_mode 実装案比較

| 案 | 内容 | 利点 | 欠点 | rollback コスト |
|---|---|---|---|---|
| A. Scheduler 時間帯で止める | `guarded-publish-trigger` / `publish-notice-trigger` / `audit-notify-6x` を `7-22` hour range へ絞る。strict 版では `draft-body-editor-trigger` も同様 | 物理的に起動しない。Cloud Run startup cost も減る。意図が明快 | Scheduler 変更が live mutation。設定漏れで終日停止 risk | 低。cron string を戻すだけ |
| B. runner 側で JST time gate | runner / endpoint 冒頭で `23:00-07:00 JST` を判定し、night なら `exit 0` + structured `night_skip` emit | Scheduler 不変。設定ミス時の安全網になる。night skip を log で追える | Scheduler は発火し続けるため cost 削減は A より弱い | 低。コード rollback or gate bypass |
| C. env / arg で night_mode を渡す | Scheduler から `NIGHT_MODE_HOURS=23-7` などを runner に渡す | 動的制御がしやすい。将来の時間帯変更に柔軟 | Scheduler と runner の二重実装が必要。複雑度が上がる | 中。env / schedule 両方の戻しが要る |

### 推奨

**A + B のハイブリッド**を推奨する。

- **A = 主防御**: quiet-hours 中に Cloud Run Job 自体を起動させず、cost を直接削る
- **B = 安全網**: Scheduler 設定ミスや後発ジョブ追加時でも quiet-hours で side effect を出さない
- **C = 不採用**: 初期実装としては複雑度に見合う便益が小さい

### scope split

- `238-impl-1`: runner 側 JST time gate(B)
- `238-impl-2`: Scheduler time-band apply(A)
- `238-impl-3`: morning report mail 集約
- `238-impl-4`: STOP 条件の即時 alert

## Step 4. morning decision report 設計

### mail contract

- send time: **07:00 JST** daily
- report window: **前日 23:00 JST - 当日 07:00 JST**
- mail purpose: user が 1 通で `GO / HOLD / STOP` を決める
- subject contract:
  - `【GO判断】night draft-only morning report`
  - `【HOLD判断】night draft-only morning report`
  - `【STOP判断】night draft-only morning report`

### required fields(v1 fixed, 13 fields)

| # | field | source | display format | note |
|---:|---|---|---|---|
| 1 | 報告期間 | scheduler trigger 時刻から固定算出 | header | `2026-04-27 23:00 JST -> 2026-04-28 07:00 JST` |
| 2 | 作成 draft 数 | WP REST `status=draft` + `after/before` window count | integer | total draft backlog ではなく **window 内新規作成数** |
| 3 | 公開候補数 | guarded-publish history `status=ready` count | integer | 朝に publish 判断へ回せる件数 |
| 4 | hold 数 | guarded-publish history `status=hold` + `hold_reason` aggregate | integer + top 3 reasons | `backlog_only`, `cleanup_failed_post_condition` などを集計 |
| 5 | error 数 | Cloud Logging `severity>=ERROR` grouped by job/service | integer + by job | runner fail / endpoint fail の可視化 |
| 6 | Gemini 推定費用 | `jsonPayload.event=\"llm_cost\"` の `estimated_cost_jpy` SUM | JPY + top 3 lanes | `229-A` の ledger をそのまま利用 |
| 7 | 重複 skip 数 | `jsonPayload.event=\"duplicate_news_pre_gemini_skip\"` count | integer | `235` duplicate suppress 効果の可視化 |
| 8 | no-op skip 数 | `jsonPayload.event=\"no_op_skip\"` count | integer | `232` no-op guard / quiet-hours skip の可視化 |
| 9 | rule-based skip 数 | `jsonPayload.event=\"rule_based_subtype_skip_gemini\"` count | integer | `236-A` short-circuit 効果の可視化 |
| 10 | X 候補数 | publish-notice aggregate の `manual_x_post_candidates` | integer + top 5 URLs/post IDs | mail body parse ではなく queue/history から取る方が望ましい |
| 11 | 要確認記事数 | publish-notice aggregate `mail_class=review` | integer + top 5 post IDs | 朝 review 対象の山を見せる |
| 12 | 危険 hard_stop 検知 | guarded-publish history `hard_stop_*` or grave hold reasons | integer + reasons | `unsupported_named_fact`, `obvious_misinformation`, `injury_death` など |
| 13 | publish 系変更検知 | WP REST publish count in quiet-hours **or** guarded-publish `status=sent` in quiet-hours | warning / integer | quiet-hours 中 0 件が期待値。1 件でも異常 |

### field design notes

- `publish 系変更検知` の v1 は **runtime signal 優先**とする
  - primary: quiet-hours 中の WP published count delta
  - secondary: guarded-publish history の `status=sent`
  - repo config drift は morning runtime report の責務から外す
- `X 候補数` と `要確認記事数` は publish-notice の既存 classification/queue 出力を再利用する
- `Gemini 推定費用` は **lane 別**を出す。`rss_fetcher`, `draft_body_editor`, その他のどこが夜間コストを食っているかを朝に判定できるようにする

### GO / HOLD / STOP conditions(initial thresholds)

閾値はまず 3-7 日の運用で調整するが、初期値は以下で固定する。

| decision | condition |
|---|---|
| GO | `error=0` または全件 retryable / `Gemini cost < daily budget x 0.7` / grave `hard_stop=0` / skip 系の異常増加なし / mail send failure 0 / quiet-hours publish change 0 |
| HOLD | 原因未確定 error が 1 件以上 / `Gemini cost` が日次 budget の 70%-90% / `review >= 10` / duplicate/no-op/rule-based skip が直近 24h 平均の 2x 超 / mail send failure 1-2 件 |
| STOP | grave `hard_stop >= 1` / `Gemini cost >= daily budget x 0.9` / error が直近 1h で 10 件以上または通常の 5x / yellow/red quality anomaly multi-hit / mail send failure 3 連続以上 / quiet-hours publish change > 0 |

### morning action mapping

- `GO`: 朝以降の publish / mail / X review を通常運転で再開
- `HOLD`: publish は止め、review queue と cost/error の原因切り分けを優先
- `STOP`: publish / mail fan-out / X review を明示解除まで停止し、grave hard-stop と quiet-hours breach を先に調べる

## Step 5. 実装 ticket 分解

| ticket 候補 | scope | priority | risk |
|---|---|---|---|
| `238-impl-1: runner 側 JST time gate` | `guarded-publish runner` / `publish-notice runner` / `audit_notify` path の main 冒頭で `23:00-07:00 JST` check、structured `night_skip` emit | P0.5 | 低。early return のみで既存 business logic を壊しにくい |
| `238-impl-2: scheduler 時間帯絞り` | `guarded-publish-trigger` / `publish-notice-trigger` / `audit-notify-6x` を `7-22` 系へ変更。strict draft-only を採るなら `draft-body-editor-trigger` を follow-up で追加 | P0.5 | 中。schedule 戻し忘れで終日停止 risk |
| `238-impl-3: morning report 集約 mail` | new `morning_decision_reporter` 相当、Cloud Logging + WP REST + publish-notice aggregate を 07:00 JST で 1 通へ圧縮 | P0.5 | 中。新規 mail path と query 実装が必要 |
| `238-impl-4: STOP 条件監視 alert` | grave hard-stop / Gemini budget / error burst / quiet-hours publish breach を即時 alert | P1 | 中。noise control が必要 |

### 推奨実装順

1. `238-impl-1`
2. `238-impl-2`
3. `238-impl-3`
4. `238-impl-4`

理由:

- `238-impl-1` は repo 内の early-return だけで安全網を先に置ける
- `238-impl-2` は live mutation だが、`impl-1` の safety net を先に入れておけば運用事故を減らせる
- `238-impl-3` は read-only report だが新規 path なので、night gate が落ち着いてから入れる方が安全
- `238-impl-4` は alert tuning が必要で、最後に回すのが妥当

## 既存 ticket 接続

| ticket | connection point | 238 での使い方 |
|---|---|---|
| `229-A` | `llm_cost` structured event / estimated cost ledger | morning report の `Gemini 推定費用` |
| `232` | `no_op_skip` 可視化 | quiet-hours 中の無駄実行や skip 異常を朝に検知 |
| `235` | duplicate suppress / `duplicate_news_pre_gemini_skip` | 重複 skip の異常増加を HOLD/STOP 判定へ使う |
| `236-A` | `rule_based_subtype_skip_gemini` | LLM を呼ばずに済んだ件数を朝に可視化 |
| `227` | burst control / backlog_only / freshness pressure | hold 増加や backlog 側への倒し込みを morning report で見る |
| `113-A` | HALLUC / grave hard-stop 系の将来入力 | grave hard-stop を STOP candidate として扱う設計面の受け皿 |
| `230-A` | runtime cost governor の観測基盤 | quiet-hours に止める lane の優先順位付け |
| `230-A1` | scheduler cadence apply runbook | scheduler side time-band 変更の母体 |
| `230-D` | `giants-*` overlap audit | fetcher `/run` mainline は止めず、overlap 整理は別便に維持 |

### policy reference

- `154 publish-policy-current` の hard-stop 定義は morning report の `危険 hard_stop 検知` に直接使える
- ただし `238` は publish gate 緩和ではなく、**quiet-hours に publish を出さない運用境界**を追加する ticket である

## 想定運用効果(directionally)

night 8h を quiet-hours 化した場合、少なくとも以下のランタイム削減が見込める。

| lane | current cadence sample | 8h quiet-hours で避けられる runs/day | sample runtime | avoided runtime/day |
|---|---|---:|---:|---:|
| `guarded-publish` | `*/5` | 96 | 31.86s | about **51.0 min/day** |
| `publish-notice` | `*/5` | 96 | 30.48s | about **48.8 min/day** |
| `draft-body-editor` | 6 runs/hour | 48 | 17.09s | about **13.7 min/day** |

合計は **about 113.5 min/day** の avoided runtime で、`230-A` が監査した high-frequency main jobs 548.3 min/day の **約 20.7%** に相当する。金額換算は billing export 未導入のため概算に留めるが、Cloud Run 起動、mail fan-out、quiet-hours repair、publish-side history churn の削減には直接効く。

追加効果:

- 夜間 mail fan-out を **1 通の morning report** へ圧縮できる
- `publish-notice` の no-op / review / urgent mail が深夜に飛ばない
- `Gemini cost` は fetcher mainline 分を残しつつ、publish/repair 側の余計な夜間消費を抑えやすい
- quiet-hours 中の `publish count > 0` が即異常指標になるため、運用 breach の発見が簡単になる

## non-goals

- 本票で Scheduler を update すること
- 本票で Cloud Run Job / Service を update すること
- 本票で `RUN_DRAFT_ONLY` を変更すること
- 本票で `src/`, `tests/`, `config/`, `Dockerfile`, `cloudbuild` を触ること
- 本票で WP / X / mail / Gemini API を live 実行すること
- `230-D` の overlap apply を同時に進めること
- publish gate を緩和すること
- README / assignments / 既存 ticket doc を編集すること

## next

次便は **`238-impl-1: runner 側 JST time gate`** から着手するのが最も安全。quiet-hours 中に side effect を出さない safety net を先に入れ、その後に authenticated executor が `238-impl-2` で Scheduler 側の time band を絞る二段構えがよい。
