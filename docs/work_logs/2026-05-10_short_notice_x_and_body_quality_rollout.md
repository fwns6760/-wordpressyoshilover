# 2026-05-10 本文品質・表形式・X反応拡張 ログ

## 1. 概要

2026-05-10 JST は、記事の受け入れしやすさを上げるための narrow 改善を連続で進めた。

最優先で守った条件は次の 2 点。

- `mail / 自動公開 / scheduler / env / Cloud Run 設定` を壊さない
- X 追加や見た目改善が原因で記事生成を止めない

実装は、本文品質ガード・表形式・X reaction の 3 系統に限定し、publish 系の運用本線には触れていない。

## 2. 今日の完了項目

### 304-QA player / manager common quality guard

- player / manager 系に共通 guard を追加
- 主観文 lead の除去
- related player の strict 化
- 投手記事で野手向け当日成績表を出さない修正
- deploy 済み

### 305-QA featured media source priority

- アイキャッチ優先順を調整
- source eyecatch 最優先
- 既存 WP media に同一 source image がある時は再利用
- source 画像がない時だけ fallback
- deploy 済み

### 306-FRONT body emoji safe decoration

- 本文の絵文字装飾を cosmetic layer として整理
- 絵文字失敗時も元本文を返す safe wrapper を追加
- manual intake と renderer の stable heading に限定して反映
- deploy 済み

### 307-QA player stats table for batter and pitcher

- 選手記事の season stats を table 表示へ変更
- 打者: `打率 / 本塁打 / 打点 / 盗塁`
- 投手: `勝 / 敗 / 防御率 / 奪三振`
- source row がない時は無理に table を出さない
- deploy 済み

### 308-QA thin body audit and fix

- `65801` 型の scoreboard-only thin body を監査
- `postgame_scorecard_only` を thin-body STOP gate に追加
- 「薄いまま publish」ではなく stop 側へ寄せた
- commit 済み、deploy は未実施

### 309-QA postgame table and X reaction expansion

- postgame を表形式で厚くした
- `勝利投手 / 敗戦投手 / セーブ`
- `巨人スタメン / 相手スタメン`
- X reaction 上限を `3 -> 5` に拡張
- X 取得失敗でも記事を止めない safe wrapper を追加
- deploy 済み

### 310-QA player / manager X reaction expansion

- `選手情報 / 首脳陣` の X reaction を `2〜3件` へ拡張
- 姓一致だけの別選手や話題違いを避ける strict 条件を維持
- X なし / 取得失敗でも記事は止めない
- deploy 済み

### 311-QA short notice X reaction expansion

- `公示 / スタメン / 予告先発 / 短報` に X reaction を `1〜2件` 追加
- lineup / pregame / player_notice を short notice 専用 mode として切り出し
- opponent / venue / time / notice type を使った strict match を追加
- weak match は `0件` のまま
- X 取得失敗でも記事生成を止めない safe wrapper を追加
- deploy 済み

## 3. 実施した検証

- 各 ticket ごとに再現テストを先に追加し、赤確認後に修正
- 関連テスト green を確認
- full suite は ticket ごとに `python3 -m unittest discover -s tests` を確認
- sandbox で `test_manual_intake_service` の localhost bind 制約が出た便は、権限付き再実行で全件 green を確認

本日最後の `311-QA` では:

- 追加再現テスト: 修正前 `7 failures + 1 error`、修正後 `8 tests ... OK`
- 関連テスト: `287 tests ... OK`
- 全件テスト: `3344 tests ... OK`

## 4. deploy 実績

本日 deploy 済みの最終 revision:

- `yoshilover-fetcher-00291-86k`

この revision には `309 / 310 / 311` の X reaction 拡張が含まれる。

post-deploy safe 確認:

- `/health` = `OK`
- `guarded-publish` 自然実行 success
- `publish-notice` 自然実行 success
- revision `00291-86k` の `severity>=ERROR` は 0 件

## 5. 運用面の確認

本日繰り返し確認した結論:

- 今日の便は `publish / mail / scheduler / env / Cloud Run 設定` を触っていない
- `mail / 自動公開停止` を引き起こす変更は入っていない
- X reaction は全て non-blocking
- X が 0 件でも記事は出る

## 6. 残タスク

- `00291-86k` で新規公開された実記事 1 本の実物確認
  - 表が意図どおり出るか
  - X reaction が不自然でないか
  - 主観記事 / 空本文が出ていないか

補足:

- `308-QA` は commit 済みだが、deploy はまだ
- `309 / 310 / 311` は deploy 済み

## 7. 所感メモ

- AI 開発では「記憶から再構成」「silent skip」「自己評価 OK」が事故源になりやすい
- 今日は、変更範囲固定、赤テスト先行、diff 範囲固定、deploy 前後の確認項目固定が有効だった
- 受け入れ基準としては、本文品質の揺れより `mail / 自動公開停止` を最優先で避ける判断が妥当
