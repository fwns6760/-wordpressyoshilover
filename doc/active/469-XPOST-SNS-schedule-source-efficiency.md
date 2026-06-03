# 469 — X-post / SNS スケジュール & ソース効率化 + 全スケジューラ棚卸し

- status: DESIGN (user 確認待ち、実装前)
- owner: Claude
- created: 2026-06-03
- 目的: Gemini 叩き(コスト)を減らしつつ、試合中はリアルタイム性を保つ。発火を「巨人のネタが動く時間 + user が起きている時間」に集約。SNS リアルタイムページは鮮度UP(Gemini不使用なのでコスト増なし)。
- 関連: 445 (SNS realtime page) / 451 (X-buzz radar) / x-post-mail-lane / rss_fetcher

---

## 0. user 確定事項(2026-06-03 対話)

- 試合中 = **15分に1回**(リアルタイム)。
- 試合外 = **2時間に1回**でよい。
- SNSリアルタイムページ = **15時くらいから毎時**。
- 試合中のソースは **スポニチ + 報知の2つでよい**。
- **朝の起床は7時** → 7時前の user-facing draft 発火は無駄(寝ている)。
- コスト方針: Gemini は最安 flash-lite だが**従量課金**(¥40/日実績、98%が x-post)。叩きを減らす。SNSページは Gemini 不使用なので頻度UPしても¥ほぼ増えない。

---

## 1. x-post 下書きメール(LLM=コスト源)新スケジュール

| 区分 | cron(JST) | ソース | 備考 |
| --- | --- | --- | --- |
| 試合外(日中) | `0 7,9,11,13 * * *` | 全ソース | 2時間毎、7時起床に合わせ開始 |
| スタメン前後 | `0 16,17 * * *` | 全ソース | 先発/スタメン |
| 試合中 | `0,15,30,45 18-21 * * *` | **報知 + スポニチ巨人 のみ** | 15分毎リアルタイム、2ソースで安く |
| 試合直後 | `0 22 * * *` | 全ソース | ヒーロー/速報 |

- 発火: 現状 ~35回 → **~23回**(うち試合中16は2ソースで軽量)。
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
| 午後〜夜 毎時 | 15,16,17,18,19,20,21,22 | 鮮度UP(リアルタイム性) |

- 現状 `FIRE_SLOTS={10,13,17,21}`(4回)→ 上記(~10回)。
- Gemini 不使用 → **¥ほぼ増えず鮮度だけ向上**(RSSHub + Cloud Run のみ、無料枠内見込み)。
- 実装: `sns_realtime_topic.FIRE_SLOTS` 修正 + rss_fetcher トリガ(giants-realtime系)が該当時刻に発火するよう整合。

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

- x-post 叩き(Gemini): 現状 ~460/日 → 発火集約(35→23)+ 試合中2ソース + 上限8 + 空振りskip で **~80〜120/日 見込み**(大幅減)。
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

## 6. 確認したい点(user)

- 試合中ソース「報知+スポニチ」に **TokyoGiants公式** も足す?(ハイライト動画が多い)それとも2つで十分?
- A群 `fact-check-morning-report` 毎時24回は意図的? 朝数回でよい?
- B群(publish-notice / guarded-publish の過密)は今回触る? それとも publish 系は別途 user 判断?
