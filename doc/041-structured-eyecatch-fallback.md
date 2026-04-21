# 041 — 画像無し記事の structured eyecatch fallback を正式化

**フェーズ：** 画像が無い記事の一覧再訪性改善
**担当：** Codex A
**依存：** 027, 037, 019

---

## why_now

- 固定 no-image 画像は記事一覧での再訪性を落とす(どれも同じ見た目になり、内容が想像できない)。
- のもとけ型に寄せるには、画像が無い記事でも **何の記事か一瞬で分かる情報型サムネ** が必要。
- 記事数を増やす 037 pickup expansion の前に、fallback を意味のある形にしておかないと、pickup 拡張でサイトが「同じサムネの記事だらけ」に見える副作用が出る。
- 041 は補助 ticket として 027 / 037 にぶら下げ、本線 fire 順を崩さない。

## purpose

- 元画像が無い記事で、共通 no-image を使わず、**subtype ごとの記事情報から structured eyecatch を自動で構成する**。
- 「画像の代用品」ではなく「記事情報で組むサムネ」として扱い、source にない情報はサムネにも入れない。
- 毎回人が画像を選ばない設計にする(運用負荷を上げない)。

## scope

### 発動条件

- **画像が無い時だけ** fallback を発動する(既存 eyecatch / OGP 画像があれば fallback は発動しない)。
- 発動判定は Draft の featured_image / eyecatch metadata 未設定を見る(published 側は触らない)。

### 対象 subtype と表示要素

各 subtype は 1 layout(最小構成)。表示要素は **source 由来の fact のみ**。

- **番組情報** (`subtype=fact_notice` / `tag=番組`)
  - ラベル: `番組情報`
  - 番組名
  - 放送日時
- **公示** (`subtype=fact_notice` / `tag=公示`)
  - ラベル: `公示`
  - 選手名
  - 公示種別
  - 日付
- **予告先発** (`subtype=pregame` / `tag=予告先発`)
  - ラベル: `予告先発`
  - 対戦カード
  - 先発投手
- **コメント** (037 parity expansion `comment_notice`)
  - ラベル: `コメント`
  - 話者名
  - 短い見出し(source から取れる範囲で)
- **怪我状況** (037 parity expansion `injury_notice`)
  - ラベル: `故障情報`
  - 選手名
  - 状況ラベル(球団公式発表 / 監督・コーチコメントまで、主要紙報道は対象外)
- **試合結果** (037 parity expansion `postgame_result`)
  - ラベル: `試合結果`
  - 対戦
  - スコア

### 1 subtype 1 layout 原則

- subtype ごとに 1 つの layout を固定する(A / B バリエーションを持たない)。
- layout 変更は必ず新 ticket で扱う(本便で複数案を持たない)。
- 見た目より、**何の記事か一瞬で分かること** を優先。

### 不可触

- **共通 no-image 画像の使用**(使わない方針、041 で廃止相当の fallback に置換)
- **AI 画像生成**(041 では使わない、運用コスト / hallucination 両面で非目標)
- **毎回の人による画像選定運用**(自動組み立てが前提)
- **OGP 全面改修**(041 は eyecatch に閉じる)
- **published 記事のサムネ修復**(Draft / 新規経路のみ)
- **published 書き込み / automation.toml / scheduler / env / secret / mail 変更**
- **reserve ticket の前倒し**(020 / 021 / 023-026 / 035)

### source と integrity

- 表示要素は全て **既存 source / metadata だけで組める** 範囲に限定する。
- source にない情報はサムネにも入れない(本文と同じ assertability ルール)。
- 怪我状況は 037 pickup boundary と同じ制約(球団公式 + 監督・コーチコメントまで)を守り、主要紙報道は fallback 対象に含めない。
- コメント系は「誰が / どこで / 何を言ったか」のうち source から取れるものだけ表示する。

### パフォーマンス

- fixed lane の Draft 作成速度を落とさない(fallback 組立は軽量、画像生成 API は呼ばない)。
- サムネ画像は server-side レンダリング(SVG / PNG)で十分、外部 API 依存を作らない。

## success_criteria

- 元画像が無い記事でも **共通 no-image が出ない**。
- 番組情報 / 公示 / 予告先発 / コメント / 怪我状況 / 試合結果 の 6 subtype で **何の記事か** が一覧で一瞬で分かる。
- 記事情報から **自動で** サムネが組まれる(人の介入なし)。
- 記事量産(037 pickup expansion / 25 Draft/day)を止めない。
- `git log --stat` / `git status --short` / tests pass / 追加 test file 実在で追認できる。

## non_goals

- OGP 全面改修
- 毎回の画像選定運用
- AI 画像生成
- published 記事のサムネ修復
- reserve ticket の前倒し
- 新 subtype の layout 追加(6 subtype 以外は後続 ticket)

## acceptance_check

- 画像無し記事で structured fallback が出る(共通 no-image に戻らない)。
- 6 subtype の代表 sample で見分けがつく(ラベル + 主要要素で一意に識別可)。
- 既存 source / metadata だけで組める(source 追加取得は発生しない)。
- fixed lane の速度を落とさない(Draft 作成 latency baseline を維持)。

## 041 と 027 / 037 の接続

- **027 補助**: 027 fixed lane Draft 作成経路の eyecatch が未設定の時だけ 041 fallback が走る。027 の subtype(fact_notice / pregame / farm)に対応する 3 layout は 041 の 6 layout の一部。
- **037 補助**: 037 pickup expansion で追加される `comment_notice` / `injury_notice` / `postgame_result` の 3 layout は 037 fire 前に 041 で先行準備できる(Codex A が同じ owner なので順序制御しやすい)。
- **019 準拠**: 固定版カード仕様(doc/019)の tag / category と整合させる(親カテゴリ `読売ジャイアンツ` 維持、細分類 tag)。

## fire 順での位置

- **補助 ticket として独立並走**(039 と同じ位置づけ)。
- 本線 `036 ✓ → [038 + 040 並走] → 029 → 028 impl → 037` は動かさない。
- 041 は 027 着地済 / 037 spec 確定済の状態で **Codex A が手が空いた時にいつでも fire 可**。ただし 028 impl と同じ Codex A なので、028 impl fire 中は直列で待つ。

## TODO

【】発動条件(元画像が無い時だけ)を固定する
【】6 subtype(番組情報 / 公示 / 予告先発 / コメント / 怪我状況 / 試合結果)の layout を固定する
【】各 subtype のラベル + 表示要素を固定する
【】1 subtype 1 layout 原則を明記する
【】表示要素は source 由来の fact のみと明記する
【】共通 no-image を使わない方針を明記する
【】AI 画像生成を使わない方針を明記する
【】毎回の人による画像選定運用を作らない方針を明記する
【】OGP 全面改修 / published 記事のサムネ修復を非目標として明記する
【】怪我状況の表示範囲(球団公式 + 監督・コーチコメントまで)を 037 pickup boundary と整合させる
【】コメント系の表示は「誰が / どこで / 何を言ったか」のうち source から取れる範囲と明記する
【】fixed lane の速度を落とさないことを非機能要件として明記する
【】041 が 027 / 037 / 019 の補助 ticket であり、本線 fire 順を崩さないことを明記する

## 成功条件

- Codex A が src + tests で structured eyecatch fallback を実装できる粒度
- 6 subtype それぞれ 1 layout で、sample 記事から見分けがつくことを test で確認できる
- 共通 no-image が出るケースが無いことを test で確認できる
- 037 pickup expansion 時に新 subtype が増えた時の追加ルール(新 ticket 起票)が 041 本文で読める
