# BUG_INBOX_TRIAGE — BUG_INBOX処理ルール

最終更新: 2026-05-02 JST

## 目的

BUG_INBOXを正式ticketと混ぜずに処理する。userの違和感を消さず、番号乱立も防ぐ。

## 気づきメモを正式ticketにする条件

以下をすべて満たす場合だけ、正式ticket候補へ昇格する。

- 既存ticketに吸収できない。
- 影響がP1以上、または再発時の復旧が難しい。
- 現象、影響、再現方法、close条件が書ける。
- write scopeまたはread-only scopeを切れる。
- deploy / env / flag / source / Gemini / mail量などのリスク分類ができる。

番号はその時点で採番する。過去ticket番号の破壊的な振り直しは禁止。

## 既存ticketに吸収する条件

以下のどれかに当てはまる場合、新規ticketを切らず既存ticketへ吸収する。

- 同じsource file / runtime lane / acceptance packで扱える。
- 既存ticketの目的に自然に含まれる。
- すでにdefault OFF実装またはPackが存在する。
- close条件が既存ticketのclose条件と同じ。
- 追加作業がdoc/test/Pack補強で済む。

代表例:

- silent skip系 -> 289 / 291 / 292 / 293 / 288 Phase 1/2
- HOLD code混入 / 作業ゴミdeploy -> 294-PROCESS
- rollback target不足 -> ACCEPTANCE_PACK_TEMPLATE / POLICY / 294
- Gemini cache/cost雪崩 -> 229 / 293 / 改修 #1-#4
- mail cap/通知枠 -> 289 / publish-notice / 改修 #6
- pytest baseline -> 299-QA / 275-QA

## 新規ticket化する条件

- 既存ticketに吸収できない。
- user影響が明確。
- evidenceまたは再現確認の入口がある。
- close条件が書ける。
- 最初の作業がread-only / doc-only / test-onlyに切れる。

新規ticket化しても、既に使われた番号は消さない。必要ならalias mapで整理する。

## HOLDにする条件

- 証拠が不足している。
- 実装するとdeploy / env / source / Gemini / mail volumeなど外部影響が大きい。
- 既存ticketの完了待ち。
- user判断が必要だがAcceptance Packが未完成。
- 影響がP2以下で、P0/P1復旧を妨げる。

## DONEにする条件

- 既存ticketで修正・verify済み。
- post-deploy verifyまたはread-only evidenceがある。
- user-visibleな受け入れ条件を満たす。
- 残課題は別BUGまたは既存ticketへ移している。

## P0 / P1 / P2 / P3

| 優先度 | 判断基準 | 例 |
|---|---|---|
| P0 | 今まさに公開・通知・候補生成が止まっている、またはmail storm active | publish 0 + mail 0、mail storm active、公開状態の大量破損 |
| P1 | 再発すると公開状態・候補可視性・deploy安全性・rollback・Gemini費用に影響 | silent skip、HOLD code混入、作業ゴミdeploy、rollback不明、Gemini雪崩 |
| P2 | 品質・運用改善だが、今すぐ本番停止ではない | H3過多、Twitter/Xリンクノイズ、log retention、pytest表現 |
| P3 | 後回しでよい改善、または運用負担が勝つ | 週次digest等、現行方針で不要なもの |

## userに確認する条件

userに聞くのは次の場合だけ。

- userしか持っていない証拠が必要。
- WP記事の公開/非公開/修正判断が必要。
- env/flag/source/Gemini増/mail量増/cleanup mutationなどUSER_DECISION_REQUIREDに該当。
- Acceptance Packが完成し、Claude推奨GO/HOLD/REJECTを出せる。

禁止:

- UNKNOWNのままuser判断にする。
- 「どうしますか？」だけを投げる。
- BUG_INBOXの項目を理由に、いきなり大量ticket化する。

## user確認不要で進めてよい条件

- read-only確認
- doc-only整理
- test plan作成
- rollback plan作成
- Acceptance Pack補強
- 既存ticketへのsubtask吸収
- 証拠ログの収集

ただし、本番deploy / env / flag / Scheduler / SEO / source / Gemini / mail量 / cleanup mutationには進まない。
