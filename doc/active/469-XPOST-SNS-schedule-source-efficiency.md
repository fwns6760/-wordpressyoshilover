# 469 — X-post / SNS スケジュール & ソース効率化 + 全スケジューラ棚卸し

- status: LIVE_IMAGE_UPDATED (step4b SNS 21:15 fast path + step5 early skip guard deployed 2026-06-07)
- owner: Claude
- created: 2026-06-03
- 目的: Gemini 叩き(コスト)を減らしつつ、試合中はリアルタイム性を保つ。発火を「巨人のネタが動く時間 + user が起きている時間」に集約。SNS リアルタイムページは鮮度UP(Gemini不使用なのでコスト増なし)。
- 関連: 445 (SNS realtime page) / 451 (X-buzz radar) / x-post-mail-lane / rss_fetcher

---

## 0. user 確定事項(2026-06-03 対話)

- 試合中 = **15分に1回**(リアルタイム)。
- 試合外 = **2時間に1回**でよい。
- SNSリアルタイムページ = **15時くらいから毎時**、試合中は **18:00〜21:15まで15分に1回**。
- 試合中のソースは **スポニチ + 報知の2つでよい**。
- **朝の起床は7時** → 7時前の user-facing draft 発火は無駄(寝ている)。
- 2026-06-07 追加: **月曜日は試合がない** → 月曜の試合前 / スタメン / 試合中 / 試合後 window は runner 側で早期 skip。
- コスト方針: Gemini は最安 flash-lite だが**従量課金**(¥40/日実績、98%が x-post)。叩きを減らす。SNSページは Gemini 不使用なので頻度UPしても¥ほぼ増えない。

---

## 1. x-post 下書きメール(LLM=コスト源)新スケジュール

| 区分 | cron(JST) | ソース | 備考 |
| --- | --- | --- | --- |
| 試合外(日中) | `0 7,9,11,13 * * *` | 全ソース | 2時間毎、7時起床に合わせ開始 |
| スタメン前後 | `0 16,17 * * *` | 全ソース | 先発/スタメン |
| 試合中 | `0,15,30,45 18-21 * * *` | **報知 + スポニチ巨人 + TokyoGiants公式** | 15分毎リアルタイム、3ソースで安く |
| 試合直後 | `0 22 * * *` | 全ソース | ヒーロー/速報 |

- 発火: 現状 ~35回 → **24回**(うち試合中16は3ソースで軽量)。
- **7時前(04:30 catchup / 06:00)の user-facing 発火は撤去**。
- 既存ガード併用: per-fire LLM上限8(`X_POST_MAIL_MAX_LLM_PER_RUN`)+ 同一選手dedup + 空振りskip(新規)。
- 試合中ソース絞り: `hochi_giants` + `SponichiGiants`(両方 RSSHub 実在・鮮度検証済 `video_radar.py:22-31`)。

### ②空振りskip(新規・小コード)
試合外/試合無し日で「新鮮バズ無し + 新規キュー無し」を先に判定し、LLM 生成自体をスキップ。出力ロス無し(元々0)、無駄叩き削減。

---

## 2. SNSリアルタイムページ(公開WP・Gemini不使用)新スケジュール

| 区分 | 発火(JST) | 備考 |
| --- | --- | --- |
| 朝 | 10:00, 12:00 | 朝の話題 |
| 午後〜試合前 | 15:00, 16:00, 17:00 | 鮮度UP(リアルタイム性) |
| 試合中SNS | 18:00〜21:15 の 15分間隔 | SNSページのみ。:15/:30/:45 はRSS記事生成/Geminiに進まず早期終了 |
| 試合後 | 22:00 | 試合後の話題 |

- 現状 `FIRE_SLOTS={10,13,17,21}`(4回)→ 上記。
- Gemini 不使用 → **¥ほぼ増えず鮮度だけ向上**(RSSHub + Cloud Run のみ、無料枠内見込み)。
- 実装: `sns_realtime_topic` の time gate 修正 + `rss_fetcher` に SNS専用 fast path を追加。21:30 / 21:45 は `rss_fetcher_redundant_realtime_skip` で早期終了。

---

## 3. 全スケジューラ棚卸し(2026-06-03 実機 44ジョブ)

### A. 明らかに疑わしい / 要修正候補
| ジョブ | cron | 問題 | 推奨 |
| --- | --- | --- | --- |
| `fact-check-morning-report` | `5 * * * *` | 名前は"morning"だが**毎時24回/日**発火 | 朝1回 or 数回へ? 要確認(誤設定疑い) |
| `giants-weekday-daytime` | `0 6-16` | "weekday"名だが曜日制限なし=毎日、**毎時11回**の昼間ブランケット | 2時間毎へ間引き |
| `giants-morning-catchup` | `30 4` | 04:30、user 起床前(draft系なら無駄) | 用途確認、user-facing なら7時へ |

### B. 重複 / 過密(集約候補)
| 群 | 重複内容 |
| --- | --- |
| giants-realtime系 | `giants-realtime-trigger`(0,30 17-21)+`giants-realtime-peak-15min`(15,45 18-21)=18-21は15分毎を2ジョブで実現。+`giants-realtime-2230`/`-2300`/`giants-postgame-catchup-am`(0 22)が夜に重複気味 → 1〜2ジョブへ集約可 |
| publish-notice系 | `publish-notice-trigger`(5 6-15)+`-evening`(5,35 16-22)+`-burst-tail`(10 7,10,12,15,17,20,21)≈ **31回/日**。burst-tail が他2つと重複疑い |
| guarded-publish | `*/30 * * * *` = **48回/日**(深夜0-5時含む)。深夜帯は publish ネタ無し → 稼働時間帯に絞れる可能性 |

### C. 高頻度だが意図的の可能性(要確認・勝手に触らない)
- `data-insight-*` 7回/日(morning/1000/noon/1500/pregame/2000/during-game)= データサイト方針。各metric別なら妥当。
- meigen mails(kobayashi 3回 / sakamoto 1回)= 別プロダクト。
- 06:00 集中の daily 群(fetch-gsc / data-site-publisher / ga4 / digest / external-ping / prosports)= backend prep、user-facing でないので朝早くてOK。

### 不可触 / 要 user 判断(§11)
- `guarded-publish` / `publish-notice` 系は **公開・通知パイプライン**。頻度変更は publish 挙動に影響 → 触る前に user 判断 + ledger/idempotency 確認。
- 他プロダクト(meigen / data-site / seo / prosports)の scheduler は本チケット scope 外。洗い出しのみ、変更は各 owner 判断。

---

## 4. コスト効果(概算)

- x-post 叩き(Gemini): 現状 ~460/日 → 発火集約(35→24)+ 試合中3ソース + 上限8 + 空振りskip で **~80〜120/日 見込み**(大幅減)。
- SNSページ: 頻度UP するが Gemini 不使用 → **¥ほぼ不変**、鮮度向上。
- A群修正(fact-check 毎時 / 昼間ブランケット)で Cloud Run 実行回数も削減。

※ 確定 ¥ は billing(Console SKU別 or BigQuery export)で実測 verify する。free-tier 主張は鵜呑みにしない。

---

## 5. 実装手順(GO 後)

1. **x-post scheduler 書き換え**: 既存 `x-post-mail-flush` / `-game-1/2` / `-lineup` を上記4区分へ再構成(即・可逆)。
2. **試合中ソース絞り**(コード): phase=試合中 のとき buzz/queue ソースを報知+スポニチに限定(phase 判定は既存流用)。
3. **空振りskip**(コード): 新鮮ネタ無し時は LLM 生成 skip。
4. **SNSページ**: `FIRE_SLOTS` 修正 + rss_fetcher トリガ整合。
5. A群(fact-check / giants-weekday-daytime / morning-catchup)は **用途確認後**に修正(本線とは別 step、誤設定なら即修正)。
6. B群(realtime集約 / publish-notice / guarded-publish)は **user 判断 + 各 owner 確認後**(§11 publish 系含むため慎重)。
7. deploy 後、翌日の発火を実ログで verify(叩き回数 / 出力候補数 / メール頻度)。

---

## 6. user 決定(2026-06-03 確定)

1. **試合中ソース = 報知 + スポニチ巨人 + TokyoGiants公式 の3つ**(`hochi_giants` + `SponichiGiants` + `TokyoGiants`)。
2. **`fact-check-morning-report`** = `/fact_check_notify?since=yesterday` を毎時24回叩く誤設定だった → **朝7:05の1回に修正済(DONE 2026-06-03)**。
3. **publish系(publish-notice / guarded-publish)も今回 scope に含めて触る**(過密集約)。ただし公開・通知パイプラインなので ledger/idempotency 確認の上で慎重に。

### 実装順序(進捗)
- step1 ✅ **DONE** fact-check → 朝7:05のみ(毎時24→1)
- step2 ✅ **DONE** 試合中3ソース絞り(commit 82f15035、image game3src-82f15035 deploy済、test pass)
   - ※ 空振りskip は per-fire budget(8)が既に waste を cap するため後回し(follow-up)
- step3 ✅ **DONE** x-post scheduler 再構成:
   - `x-post-mail-flush` = `0 7,9,11,13,15,16,17,22`(全ソース・8発火)
   - `x-post-mail-flush-game-1` = `0,15,30,45 18-21`(試合中15分・narrowing窓と整合・16発火・3ソース)
   - `x-post-mail-flush-game-2` = PAUSED(`15,30,45 21-22`、集約)
   - 合計 35→**24発火/日**(うち16は3ソース)
- step4 ✅ **DONE** SNSページ `FIRE_SLOTS`=10,12,15-22(commit 3edb27c3、fetcher rev 00511-hps、/health 200、traffic 100%)
- step4b ✅ **LIVE_IMAGE_UPDATED** SNS 15分更新を 18:00〜21:15 に限定。:15/:30/:45 は SNS page upsert だけ実行して RSS記事生成 / Gemini / 下書き作成へ進まない。21:30 / 21:45 は scheduler が来ても早期 skip。Cloud Build `164dbed7-02ce-4507-92ee-37e959f21948` SUCCESS、image `yoshilover-fetcher:sns-2115-3edb27c3-20260607` digest `sha256:9729d88c1a6aebe64eea499ff6a33c04df591913bfcb23aaee9cfd5e7d83774a`、Cloud Run service `yoshilover-fetcher` revision `yoshilover-fetcher-00512-qn6` 100% traffic、`/health` OK。旧 image rollback: `yoshilover-fetcher:sns-hourly-3edb27c3`。
- step5 ✅ **LIVE_IMAGE_UPDATED** 早期 skip guard: `run_x_post_mail.py` で 7:00 前は DB download 前に `exit 0`(`X_POST_MAIL_ALLOW_BEFORE_7AM=1` で解除可)。月曜の試合系 timing window も DB download / RSSHub / Gemini 前に `exit 0`。祝日等の月曜開催は `X_POST_MAIL_ALLOW_MONDAY_GAME_WINDOWS=1` で解除可。Cloud Build `cabf7277-35c8-4074-8f41-80c76fe6f959` SUCCESS、image `x-post-mail-lane:469-skip-ce38d111-20260607` digest `sha256:f3844ffdae151afdb9b6052746316a082948800f5becbc8fb8915e72d24b43d7`、Cloud Run Job `x-post-mail-lane` generation `162`。旧 image rollback: `x-post-mail-lane:fanreply-3465be06`。
- step6 ⏭ giants-weekday-daytime(昼間毎時11)間引き + giants-realtime重複集約
- step7 ⏭ publish-notice / guarded-publish 過密集約(§11、idempotency確認後)
