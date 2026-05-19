# 378-OPS 夜間試合後ピーク fetch 15min 化 + 22-23時 30min 補強

## meta

- status: CLOSED (2026-05-19 user 判断 scope 縮小、 IMPL_IN_PROGRESS で停止)
- priority: P2 (運用改善、 既存壊さない可逆変更)
- owner: Claude
- created: 2026-05-18
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/52

## user intent (2026-05-18 chat lock)

- 「巨人は試合後に複数媒体・複数記事が短時間で大量に出る。 30 分に 1 回だと判断タイミングが粗く、複数段階の記事が混ざってしまう」
- 「20:00〜22:00 JST だけ判断タイミングを細かくしたい (15 分に 1 回)、 22:00〜23:00 JST は 30 分に 1 回、 それ以外は現行維持」
- user confirm: 「ひようがかからないならOK」「安全なのは案 A (3 jobs 追加、 既存 0 touch)」「GO」

## scope (今回)

候補 fetch (`yoshilover-fetcher /run`) の Cloud Scheduler trigger を 3 jobs 新規追加。

| 新規 job | cron | 発火時刻 (JST) | 月間 fire |
|---|---|---|---|
| `giants-realtime-peak-15min` | `15,45 20-21 * * *` | 20:15 / 20:45 / 21:15 / 21:45 | ~120 |
| `giants-realtime-2230` | `30 22 * * *` | 22:30 | ~30 |
| `giants-realtime-2300` | `0 23 * * *` | 23:00 | ~30 |

合計 +6 fire/日 = +180 req/月 (Cloud Run free tier 内、 無視範囲)。

### auth / 設定 (既存 `giants-realtime-trigger` に揃える、 verified)

- uri: `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run`
- httpMethod: POST
- body: `e30=` (`{}` base64)
- oidcToken.serviceAccountEmail: `seo-web-runtime@baseballsite.iam.gserviceaccount.com`
- oidcToken.audience: `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run`
- attemptDeadline: 180s
- timeZone: Asia/Tokyo
- location: asia-northeast1

## 不可触

- 既存 `giants-realtime-trigger` `0,30 17-21 * * *` (そのまま、 20:00/20:30/21:00/21:30 は引き続き発火)
- 既存 `giants-postgame-catchup-am` `0 22 * * *` (そのまま、 22:00 発火)
- 既存 `guarded-publish-trigger` `*/30 * * * *` (touch しない、 後段の draft 化は 30min cadence のまま)
- 既存 `publish-notice-trigger-evening` `5,35 16-22 * * *` (touch しない、 mail 発射は 30min cadence のまま)
- src / Cloud Run service / Cloud Run Job image / env / Secret / WP / X / SNS は全て不変

## 完了条件

1. 新規 3 jobs が `ENABLED` で `gcloud scheduler jobs list` に表示される
2. 既存 `giants-realtime-trigger` / `giants-postgame-catchup-am` の cron / state が変わっていない
3. Cloud Run / env / Secret / WP / X / SNS / mail 仕様が変わっていない
4. doc/active/assignments.md に 1 行追加されている
5. GitHub Issue が起票されている

## 既知の懸念 (user に明示済)

### 懸念 1: 判断サイクルは完全に 15min にならない (大、 受容)

今回 fetch だけ 15min 化。 後段が 30min のまま:
- `guarded-publish-trigger` = `*/30 * * * *`
- `publish-notice-trigger-evening` = `5,35 16-22 * * *`

実フロー:
- 20:15 fetch → DB に candidate 蓄積
- 20:30 guarded-publish → draft 化
- 20:35 mail → user 通知

結果: **fetch 鮮度は 15min 上がる (mail に出る記事が最大 15min 前)** が **mail 受信頻度は 30min のまま**。 user 元意図「判断タイミングを細かく」を完全達成するには guarded-publish と publish-notice も連動 15min 化が必要 (別 ticket 候補、 +$0.30/月相当)。

### 懸念 2: 23:00 fetch の mail は翌朝 (中、 受容)

- `publish-notice-trigger-evening 5,35 16-22` は **22:35 が最終発火**
- 23:00 fetch → 23:30 guarded-publish draft 化 → 次 mail は **翌朝 06:05** (`publish-notice-trigger 5 6-15`)
- 23:00 fetch を増やしても夜のうちに user 判断できない → 翌朝処理になる
- user は「mail は翌朝で OK」前提で 23:00 含めた

### 懸念 3: mail 本文が現状読めない可能性 (中、 別 ticket)

377-OPS Phase 1C 未着手。 `body_excerpt` field は dataclass にあるが scanner 側 populate コードが入っていない。 本件 scheduler 変更で「mail 件数増」「mail 鮮度向上」は起きるが、「本文が読める判断カード」は 377-OPS Phase 1C 完了まで実現しない。

### 懸念 4: IAM service account の 403 再発リスク (低、 緩和済)

memory: 5/16「x-post-mail scheduler 403 fix」前科 (別 service account を使い 403)。 今回は既存 `giants-realtime-trigger` の `oidcToken.serviceAccountEmail` (`seo-web-runtime@baseballsite.iam.gserviceaccount.com`) を verify 済で揃えるため、 同じ事故を避ける。

### 懸念 5: 22:30 timing 重複 (微、 受容)

新規 `giants-realtime-2230 30 22` と既存 `postgame-auto-daily 30 22` が同時刻発火。 ただし target が別 Cloud Run resource (`yoshilover-fetcher` service の `/run` vs `postgame-auto:run` Job)、 衝突なし。

## cost

- Cloud Scheduler: 3 jobs 追加 × $0.10/月 = **+$0.30/月 ≒ ¥45/月**
- Cloud Run: +180 req/月 (free tier 内)
- mail 配信: 既存 budget 300/日 / per-run 10件 cap / burst 50件 summary mode で頭打ち、 追加コスト 0
- LLM: 不使用 (今回 scheduler 変更のみ)

## rollback

各 job 独立に `gcloud scheduler jobs delete <name> --location=asia-northeast1 --project=baseballsite` で即削除可能。
既存 job は一切 touch しないため、 rollback は 3 jobs 削除のみ。

## verify protocol (本 ticket 着手前 / 完了時)

### 着手前 (済)

- [x] `giants-realtime-trigger` の full describe で auth 設定 verify (`seo-web-runtime@baseballsite.iam.gserviceaccount.com`, oidcToken, attemptDeadline 180s)
- [x] 既存 mail budget / dedup env を describe で verify (`PUBLISH_NOTICE_24H_BUDGET_LIMIT=300`, `PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=10`, `PUBLISH_NOTICE_BURST_THRESHOLD=50`, `ENABLE_REPLAY_WINDOW_DEDUP=1`)
- [x] 378 番号空きと doc/active/ / doc/waiting/ / doc/done/2026-05/ の重複なし確認
- [x] `RUN_DRAFT_ONLY=0` 確認 (377-OPS Phase 2 未 apply)
- [x] `ENABLE_X_POST_FOR_NOTICE=0` 確認 (X 自動投稿 OFF 維持)

### 完了時

- [ ] 3 jobs 新規作成、 list で `ENABLED` 表示
- [ ] 既存 `giants-realtime-trigger` の cron `0,30 17-21 * * *` 変化なし
- [ ] 既存 `giants-postgame-catchup-am` の cron `0 22 * * *` 変化なし
- [ ] `guarded-publish-trigger` `*/30 * * * *` 変化なし
- [ ] `publish-notice-trigger-evening` `5,35 16-22 * * *` 変化なし

## 次 action (本 ticket 完了後)

- 1-3 日観察 (mail 件数 / draft 件数 / dedup 弾き数 / 23:00 fetch 結果が翌朝 mail に出るか)
- user 判断「15min mail も欲しいか」 → 必要なら別 ticket で guarded-publish + publish-notice の 20-22時 15min 化 (+$0.30/月)
- 377-OPS Phase 1C 着手で「本文が読める判断カード」実現

## 関連 ticket / memory

- `[[377-OPS]]` (mail 本文 + admin link、 Phase 1C 未着手)
- `[[feedback_publish_forward_must_check_gate_reason]]` (公開境界、 X 投稿 user 手動)
- `[[feedback_publish_vs_xpost_3_gate]]` (公開と SNS 分離)
- 2026-05-15 memory `project_mail_schedule_alignment.md` (publish-notice mail は guarded-publish の 5 分後に整列、 :05 / :05,:35 / 深夜なし)
- 2026-05-16 assignments.md `x-post-mail scheduler 403 fix` (service account 事故事例)
