# BUG-004+291 publish=0原因分解 + narrow publish-path unlock prompt

現場Claudeへ。

BUG-004+291 の中で、`publish=0原因分解 + narrow publish-path unlock` を実施してください。
これは新規ticketではありません。
BUG-004+291 のACTIVE内サブタスクとして扱ってください。

`292 body_contract_fail durable ledger方針` は独立ACTIVEではありません。
BUG-004+291 の解除条件・必須サブタスクとして同時に整理してください。

## 目的

現状の問題は、publish gate を緩めるか維持するかの二択ではありません。
公開ゼロの原因を分解し、高信頼条件を満たす候補だけを狭く publish path に戻すことです。

旧状態も正常ではありませんでした。
したがって rollback や現状維持を最終正解にせず、候補が見える状態を保ちながら品質条件を満たす記事だけ公開候補へ戻してください。

## まず read-only で分解する原因

- `277` title quality
- `289` post_gen_validate
- `290` weak title rescue 不発
- 4-tier分類の strict 判定
- duplicate / backlog / freshness
- body_contract
- subtype misclassify
- numeric guard
- placeholder
- source facts 不足
- 292 body_contract_fail durable ledger 方針

## publish候補に戻してよい最小条件

- YOSHILOVER対象
- source_urlあり
- subtype / template_key high confidence
- numeric guard pass
- body_contract pass
- placeholderなし
- silent skipなし
- titleが最低限「何の記事か分かる」
- review / hold 理由なし

## 2026-05-03 user-confirmed rescue targets

以下はBUG-004+291の正式な回収対象です。
これらを救うために、publish gate全体緩和ではなくdeterministicなnarrow unlockを設計してください。

### publish候補へ戻してよい記事タイプ

- 試合結果記事
  - 当日記事
  - 巨人対象
  - 相手チームが取れる
  - スコアが title / source / meta / body のどこかから取れる
  - numeric guard pass
  - 先発投手成績がsourceにない場合、それだけで落とさない
  - ただしsourceにない投手成績は本文に書かない
- 監督・コーチコメント
  - 阿部監督コメント記事
  - コーチコメント記事
  - コメント全文でなく一部でもよい
  - sourceが明確ならpublish候補
  - postgame扱いに雑分類しない
  - score / 勝敗 / 投手成績を補完しない
- 選手コメント
  - 必須救済対象
  - 選手名とコメント元が明確ならpublish候補
  - scoreがなくてもplayer_commentとして扱う
  - 試合結果記事に寄せない
  - 数字・勝敗・成績はsourceにあるものだけ使う
- 二軍結果
  - 必須救済対象
  - farm_resultは一軍postgameと分ける
  - 二軍であること、相手、スコアが取れるならpublish候補
- 二軍スタメン
  - 必須救済対象
  - farm_lineupはfarm_resultと分ける
  - スタメン表 / 打順 / 選手名が取れるならpublish候補
  - 結果記事として扱わない
- pregame / 予告先発
  - 必須救済対象
  - probable_starter / pregame / lineupはpublish候補
  - 試合開始後の扱いは厳しすぎない
  - ただし試合後に古いpregameを出すのは不可
- 昇格・降格・復帰・二軍落ち
  - 必須救済対象
  - 一軍昇格
  - 登録抹消
  - 一軍から二軍に落ちた選手
  - 復帰組
  - 若手選手記事
  - subtypeはnotice / roster_notice / injury_recovery_notice / farm_player_result等へ寄せる
  - defaultやpostgameへ雑に落とさない
- 若手選手記事
  - 必須救済対象
  - 二軍成績、復帰、昇格候補、若手注目はpublish候補
  - sourceが弱い場合はreview
  - 数字や成績はsource由来のみ

### publish不可を維持するもの

- live update断片
- 「九回表」「先頭の選手」「適時打」だけの実況断片
- placeholder本文
- 「先発の 投手」
- 「選手の適時打」
- 空見出し
- body_contract fail
- numeric guard fail
- YOSHILOVER対象外
- source_urlなし
- subtype不明
- review / hold理由あり
- 重複記事
- stale postgame
- weak titleのまま何の記事かわからないもの

### 弱いタイトル方針

- 弱いタイトル対策は必須
- 「何の記事かわからない」タイトルはpublishしない
- ただしcoach_comment / player_comment / farm_result / farm_lineup / roster_noticeなど中身が明確ならdeterministic rescue候補にする
- AIでタイトルを自由生成しない
- source/metaから取れる選手名・記事タイプ・相手・スコアだけ使う

### 重複方針

- 報知 / 日刊 / スポニチ / 公式 / X由来などで同内容が複数来た場合、基本は1本だけ
- duplicate guardは緩めない
- 同じsource_url / content_hash / 同一内容はpublishしない

## 292の吸収条件

body_contract_fail は通常メールで大量通知しないでください。
ただし、黙って消してはいけません。

必要な状態:

- body_contract_fail の件数が後から確認できる
- fail理由が ledger / log / state row のどこかに残る
- publish=0原因分解の中で body_contract fail がどれだけ効いているか見える
- 通常メール量を増やさない

## やってよいこと

- read-only 原因分解
- ledger / log / state row 確認
- candidate terminal state 確認
- fixture / test plan / Acceptance Pack 補強
- narrow unlock 設計
- rollback plan / stop condition 明文化

## やってはいけないこと

- publish gate 全体緩和
- 悪い記事を後で消す前提の大量公開
- noindex解除
- review thresholdを上げるだけのmail隠し
- user判断なしのSEO変更
- source追加
- Gemini call増加
- mail量増加
- WP本文変更
- publish状態変更
- env / flag / Scheduler変更
- body_contract_fail の通常メール大量通知
- 292の独立ACTIVE化

## 報告trigger

報告してよいのは以下だけです。

- publish=0原因分解完了
- narrow unlock設計完了
- 292相当の durable ledger 方針完了
- P1相当の異常
- rollback必要
- USER_DECISION_REQUIRED
- 新たにP0/P1へ昇格すべき証拠

正常系の定期報告、cycle silent、長いlog貼り付け、user返答不要の実況は不要です。

## 完了条件

- publish=0 の主因が ticket / guard / reason 単位で分解されている
- 高信頼候補だけ publish path に戻す条件が明文化されている
- 292相当の body_contract_fail durable ledger 方針が同じ設計内に入っている
- 全体緩和をしていない
- noindex / SEO に触っていない
- silent skip を増やしていない
- Gemini call / mail量を増やしていない
- rollback target と stop condition が明確
