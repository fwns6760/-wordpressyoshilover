# 060 — SNS 2 アカウント運用契約 + Draft 期 bridge 運用

**フェーズ：** MVP 前 SNS 運用開始 contract(Draft 中心期)
**担当：** Claude Code(contract owner、Codex 便なし)
**依存：** 006(legacy `x_post_generator.py` CLI 実装 reference)、007(legacy `x_api_client.py` tweepy API 実装 reference)、028 T1 trust tier、037 pickup parity 5 family、046 first wave 4 family accepted(`8ef8330` + `069daa6`)
**状態：** CONTRACT ACTIVE(doc-only、実装は 061 以降)

**正本優先順位**: **tone / account split / Draft 期 bridge / 061 gate は 060 を優先**。006 / 007 は単一アカウント前提の legacy 実装 reference で、2 アカ分離・Draft 期 bridge・published gate を含まないため、将来 061 実装時の CLI / API reference としてのみ参照する。060 と 006 / 007 で表現が競合した場合は 060 を正とする。

---

## why_now

- 記事はまだ Draft 中心で published が少ない。publish 100% 待ちで SNS 運用を止めると、アカウント育成機会を失う。
- user は SNS 運用を早く開始したい(2026-04-22 user 指示)。ただし **draft URL / private URL を外部に流すことは禁止**(MVP 成立条件を崩す)。
- 006 / 007 は初期フェーズの一般設計で、2 アカウント役割分担 / Draft 期 bridge 運用 / published gate を含んでいない。reference として残し、本 ticket を contract 正本に置く。
- 実装(X API / automation / 自動投稿)に進む前に、**「何を」「どのアカウントで」「何を言い」「何を言わないか」の contract** を先に固定する。実装 ticket(061)は本 contract accept 後。

## purpose

- ヨシラバー公式 X(@yoshilover 系)と user の中の人 X(@fwns6 系)の **役割分担 contract** を固定する。
- Draft 期(published 100% 前)の SNS **bridge 運用ルール**を固定する。具体的には「draft URL を流さない」「primary trust の短 post だけ許可」「published 後のリンク流入は別 phase」の 3 点。
- published 安定後に 061(自動投稿実装)へ進む **gate 条件**を固定する。
- SNS 運用の user 判断境界を下げる(relay 不要で Claude + user が閉じる)。

## scope

### 1. ヨシラバー公式アカウントの役割(野球の表アカウント + 記事導線)

- **定位**: **野球の表アカウント**。速報専用の無機質アカウントにはしない。野球ファンが follow して楽しめる熱量と事実精度を両立する
- **扱う対象**:
  - スタメン / 公示 / 予告先発 / 試合結果 / 試合中の確定イベント
  - 強いコメント(監督 / コーチ / 主力選手の球団公式発表)
  - **試合の流れに対する短い反応**(事実に紐づく軽い熱量まで)
  - 記事公開通知 / サイト導線(記事導線としての役割も兼ねる)
- **記事公開通知**: published 記事の title + canonical URL を short post(将来 061 で自動化)。Draft 期は手動 only
- **試合中速報**: 1 イニング単位の確定事実 short post(score / HR / 得点選手 / 交代 / 確定イベント)
- **試合の流れへの短い反応**: 事実に紐づく軽い熱量まで許可(例: `8 回裏の坂本 HR で逆転。痺れる展開` / `先発が 5 回 2 失点で粘った`)
- **サイト導線**: ホーム導線、カテゴリ導線、シーズン別 index 導線を月次 1-2 post
- **trust 層**: **primary trust(T1)のみ**(NPB 公式 / 球団公式 / 公式 X / 球団公式発表)
- **tone**: **事実 first + 軽い熱量**。ファンが自然に反応できる温度感は許可。最初の 1 行で「何が起きたか」が分かる
- **禁止事項**(公式アカウント):
  - 未確認情報の断定
  - 感情だけの煽り / 選手・関係者への断定的評価
  - 人格前面の長文雑談(公式は中の人ではない)
  - rumor / unknown / secondary trust の primary 扱い
- **対象 subtype**(Draft 期に公式アカウントで投稿可):
  1. `lineup_notice`(スタメン、球団公式 / 公式 X 発表時のみ)
  2. `fact_notice`(公示 / 昇降格、球団公式発表のみ)
  3. `probable_starter_notice`(予告先発、NPB 公式 / 球団公式のみ)
  4. `postgame_result`(試合結果、NPB 公式データのみ、score + 勝敗 + 勝ち投手 / 負け投手)
  5. `comment_notice`(**trust 条件を満たす強い**コメント、監督 / コーチ / 主力選手 / 球団公式発表のみ。主要紙引用のみのコメントは対象外)
  6. **試合中確定イベント**(`postgame_result` family の試合中 variant、score / HR / 交代 / 得点イニングの確定事実)
  7. **試合の流れに対する短い反応**(事実に紐づく軽い熱量、未確認 / 煽り / 断定評価は不可)

### 2. 中の人アカウントの役割(人柄でファンを作る、手動 only)

- **定位**: **人柄でファンを作る場**。公式アカウントのコピー運用にはしない。公式と独立の信頼資本を user 個人で積み上げる
- **領域**: 野球 / AI / マーケティング / 金融(4 分野、user 裁量)を**中の人の視点**で語る
- **運用モード**: **完全手動**(自動化しない、Claude 便も作らない、永続的に user 裁量)
- **扱ってよいもの**:
  - 運営の裏側、考え、試行錯誤、学び、日常の温度感
  - ファンとの会話 / リプライ / 雑談
  - 中の人の意見 / 観測 / 考察(野球 / AI / マーケ / 金融)
  - 公式アカウントの reshare / quote(必要時のみ、公式のコピーにはしない)
  - 記事導線(**published 後のみ**、必要時だけ混ぜる)
- **tone**: **人柄 first**。中の人の考え・試行錯誤・舞台裏・学びを出してよい
- **事実と意見の扱い**: 事実と意見を混ぜる時は、**事実部分を曖昧にしない**(出典 / 時系列 / 主語を落とさない)
- **公式アカウントとの差別化**:
  - プロフィール / 固定 post / bio で「中の人」ポジションを明示
  - 公式の短 post をコピーしない(公式は野球表アカ、中の人は人柄アカ、役割を混ぜない)
- **trust**: user 個人の責任、公式 trust 体系とは別

### 3. Draft 期の bridge 運用ルール(本 ticket の核)

**禁止**

- **draft URL を SNS に流さない**(wp-admin / 非公開 slug / preview URL / private URL 全て禁止)
- 未公開記事を暗示する投稿(「間もなく記事」「後で詳しく」等)は禁止
- rumor / unknown / secondary trust(主要紙引用のみ等)を primary trust として扱わない
- Gemini Flash / 2.5 Flash 生成文の原文転載(生成文が primary trust を超える表現で出る可能性)

**許可(公式アカウントのみ)**

- primary trust source に基づく **fact 短 post**(140 文字以内目安、AI tone 禁止)
- 試合中速報(score / 選手交代 / 得点 / HR 本塁打等の確定事実)
- published 記事の通知(Draft 期は手動 only、自動化は 061 以降)

**初期対象(公式アカウント、Draft 期)**

- スタメン(`lineup_notice`、球団公式 / 公式 X 発表時のみ)
- 公示 / 昇降格(`fact_notice`、球団公式発表のみ)
- 予告先発(`probable_starter_notice`、NPB 公式 / 球団公式のみ)
- 試合結果(`postgame_result`、NPB 公式データのみ、score + 勝敗 + 勝ち投手 / 負け投手)
- 強いコメント(`comment_notice`、trust 条件合致時のみ、監督 / コーチ / 主力選手の球団公式発表)
- 試合中の確定イベント(1 イニング単位の score / HR / 交代 / 得点イニング)
- 試合の流れに対する短い反応(**事実に紐づく軽い熱量まで**、未確認 / 煽り / 断定評価は不可)

**cadence**

- Draft 期は **手動のみ**、cadence は user 裁量
- 試合中速報は試合開始前 1 時間〜試合終了後 1 時間の window で user 手動
- 公式アカウントの tone drift は Claude が週次で観測(現在 ledger と digest の枠で吸収)

### 4. published 安定後に 061 自動投稿実装へ進む gate

以下 **4 条件すべて** pass で 061 fire(Claude 判断、user 明示 go なし)

1. **published 件数**: 週 10 記事以上が 2 週連続
2. **published 事故**: 直近 2 週で fact error / プライバシー事故 / 著作権事故 **0 件**
3. **公式 X 手動運用実績**: 本 ticket(060) accept 後の公式アカウント **manual post 最新 20 件** を対象に Claude が **manual review** を実施し、**red 0 件** を満たす
4. **trust 体系安定**: 028 T1 / 037 pickup boundary / 046 first wave に起因する **correction / delete が 2 週間 0 件**(ledger で confirm)

#### ③ manual review の red / yellow 定義(Claude が判定)

**red(0 件必須、1 件でも出たら gate pass しない)**

- Draft / preview / private URL の流出(送客 / 暗示含む)
- 未確認情報の断定(rumor / unknown を確定情報として扱う)
- rumor / secondary trust(主要紙引用のみ等)を primary 扱い
- 公式アカウントでの過剰な煽り / 罵倒 / 強い私見(選手・関係者への断定的評価含む)

**yellow(許容、ただし Claude が観測記録)**

- 境界 post(`痺れる` / `粘った` 等の軽い熱量で fact に紐づくが、読み手によってはグレー)
- 1-2 文の個人感想付きの fact post
- tone drift の予兆(反応が強くなっていく傾向)

**review 手順**

- 対象: 060 accept 日以降に公式アカウントで投稿した **最新 20 件**(reshare / quote 除く、自身の post のみ)
- 判定者: Claude Code(user は relay しない)
- 判定時期: 20 件到達時点 + その後週次で更新
- 記録: `session_logs/YYYY-MM-DD_060_manual_review.md` に red / yellow 件数 + 例を残す
- red 0 件継続 = ③ pass、red 1 件以上 = ③ fail、user 判断で tone 修正 or 061 起票保留

#### ④ correction / delete 0 件の定義

- 対象: 028 T1 assert narrow / 037 pickup boundary / 046 first wave 4 家族の route evidence に起因する published 記事の **訂正公開** または **削除**
- 計測期間: 直近 2 週(14 日連続)
- ledger `docs/handoff/ledger/YYYY-MM-DD.jsonl` で `fail_tag` 経由 correction / delete イベントを 0 件確認
- 028 / 037 / 046 起因ではない correction(typo / 手動修正 / CSS 等)は対象外

061 の scope(先行予告):

- published 記事の title + canonical URL の自動投稿(公式アカウントのみ)
- 試合中速報は 061 では自動化しない(次 phase、人間 in the loop)
- X API(公式 Developer API)経由、secret は user 手動登録
- 中の人アカウントの自動化は **非目標**(永続的に手動)

### 5. 文面原則(tone contract)

**公式アカウント(事実 first + 軽い熱量)**

- **最初の 1 行で「何が起きたか」が分かる**(冒頭 fact、遅延しない)
- 野球ファンが自然に反応できる温度感は許可(`痺れる` / `粘った` / `逆転` 等、事実に紐づく限り OK)
- 試合中の流れに対する短い反応(1-2 文)は、事実に紐づく限り OK
- **不可**: 煽り / 未確認断定 / 感情だけの長文 / 選手・関係者への断定的評価 / 人格前面の雑談
- 140 文字以内目安、AI 生成文の原文転載は禁止

**中の人アカウント(人柄 first)**

- 中の人の考え、試行錯誤、舞台裏、学びを出してよい
- **事実と意見を混ぜる時は、事実部分を曖昧にしない**(出典 / 時系列 / 主語を落とさない)
- 野球 / AI / マーケ / 金融の 4 分野は中の人の視点で語る(公式の tone でコピーしない)
- 文字数・形式は user 裁量(長文雑談 / スレッド / リプライ全て OK)

### 6. 不可触

- 006 / 007 の本文(reference として保持、本 ticket は新 contract 正本)
- 028 T1 assert narrow / 037 pickup boundary / 046 first wave route evidence(本 ticket は流用側、変更しない)
- automation.toml / scheduler / env / secret / quality-gmail / quality-monitor / draft-body-editor
- WordPress published 書込(Phase 4 まで禁止、本 ticket と独立)
- 中の人アカウントの運用方針(user 裁量、Claude 管理外)

## non_goals(2026-04-22 明示)

- **X API 実装**(061 以降)
- **automation.toml 変更**(SNS lane を追加しない、本 ticket は contract のみ)
- **両アカウント自動化**(中の人は永続手動、公式は 061 以降に限定自動化)
- **Draft URL 送客**(いかなる経路でも禁止)
- published 記事への X 投稿の自動リンク化(Phase 4 以降)
- 試合中速報の自動投稿(次 phase、人間 in the loop)
- SNS analytics / impression tracking / follower growth KPI(本 ticket は運用契約のみ)
- 他 SNS(Instagram / TikTok / YouTube / Bluesky / Threads)への拡張(非目標、MVP scope 外)

## success_criteria(3 点 contract、feedback_accept_3_point_contract.md 準拠)

**一次信号(accept 根拠)**

- **着地**: `doc/060-sns-dual-account-draft-era-bridge.md` が正本として commit 着地
- **挙動**: user が「公式で出してよい post / 出してはいけない post」を本 ticket 読むだけで判断可能
- **境界**: 006 / 007 に diff なし(reference として保持)、028 / 037 / 046 / automation / published に diff なし

**二次信号(事後記録、accept 根拠にしない)**

- Draft 期の手動 short post 実績が 061 gate に積み上がる(Claude 観測)

## acceptance_check(自己追認)

- `doc/060-sns-dual-account-draft-era-bridge.md` が存在
- 公式 = 野球の表アカウント / 中の人 = 人柄でファンを作る、と役割が分離明示されている
- 公式の tone が「事実 first + 軽い熱量」で固定、煽り / 未確認断定 / 長文雑談 / 人格前面が禁止と明記
- 中の人の tone が「人柄 first」で、事実と意見を混ぜる時は事実部分を曖昧にしないと明記
- Draft 期 bridge の 3 禁止ルール(draft URL / 未公開暗示 / rumor primary 扱い)が明記
- 初期対象(公式、Draft 期)7 項目(lineup / fact / probable / postgame / comment with trust / 試合中確定 / 試合の流れ短い反応)が明記
- 061 gate 4 条件が明記
- non_goals で X API / automation / 両アカ自動化 / draft URL 送客が明示否定
- 006 / 007 を reference として維持(diff なし)
- automation.toml / scheduler / env / secret / quality-* / published に diff なし

## fire 前提 / stop 条件

### fire 前提(contract ticket として)

- 046 accepted(達成、`8ef8330` + `069daa6`)
- 028 T1 / 037 pickup boundary 運用中(達成)
- user が SNS 運用を早く開始したい(2026-04-22 user 明言、本 ticket の起票契機)

### stop 条件

- draft URL 流出(即停止、user 判断)
- 公式アカウントの fact error / プライバシー事故 / 著作権事故
- 中の人アカウントが公式と混同される発信
- 061 gate 未達のまま自動投稿実装に進む
- X API / automation.toml / secret 変更を本 ticket 範囲で実施しようとした時

## 本 ticket の運用

- **Claude Code**: 本 contract の維持、publish 状況の週次観測、061 gate 4 条件の観測
- **user**: 本 contract に従って公式アカウント + 中の人アカウントを手動運用、061 gate 判定の最終確認
- **Codex 便**: **なし**(本 ticket は doc-only、実装は 061 以降)
- **ChatGPT 役**: 会議室で contract の細部相談が必要な時だけ(本体は Claude Code 管理)

## 旧 ticket との関係

- **006 / 007**: 初期フェーズの SNS 一般設計。reference として保持、本 ticket が新 contract 正本
- **061**(予定): published 安定後の自動投稿実装(X API / 公式アカウント title+URL 自動投稿)。本 ticket accept + 4 gate pass 後に起票
- **本 ticket と独立並走**: 046(accepted)/ 048(B 補修線 HOLD)/ 041 / 045 / 039 / 042 / 043 / 044
