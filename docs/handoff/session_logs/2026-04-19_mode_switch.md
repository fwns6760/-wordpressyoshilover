# 2026-04-19 運用モード切替まとめ

このセッションで確定した運用モード変更の記録。恒久ルールは `AGENTS.md` に反映し、ここには切替日と判断経緯のみ残す。

## 切替 1: レビュー待機モードへ

- 背景: batch で 6 本 (#11〜#16) の Codex 便を起票後、user が「前進よりも軌道修正を優先」と明示
- ルール:
  - Codex 完走待ち中は新便を追加起票しない
  - Codex 返答後は要約 + 残リスク + 次候補 1 本のみで返す
  - user の明示 go があるまで次便は流さない
- 適用時点: #11 (#9 + #15 合同 deploy) in-flight 中

## 切替 2: 公開較正モードへ

- 背景: user が「draft を増やすこと」ではなく「公開して判断できる状態を作ること」を主目的化
- 主 KPI: drafts_created → publishable_rate / published_count
- 優先 subtype: postgame / lineup を先に、manager / player / farm / social は後ろ
- 判定基準: 事実の核 / title-body 重心 / ファン視点 / 素材メモ感 の 4 項目
- 候補ゼロで返さない規律: 優先 subtype が 0 件なら他 subtype から最も公開に近い 1 本を選ぶ

## 切替 3: 62591 patch-only 便の起票判断

- 対象: post ID 62591「巨人スタメン 佐々木俊輔 先制ソロ」
- 判定: 4 項目中 1/4 該当 (ファン視点弱のみ) → patch then publish の最優先
- 決め手: lineup = 優先 subtype、日刊スポーツ一次情報で fact safety 高、title-body 重心一致
- Codex 便の scope: title 末尾補完 / テンプレ句削除 / ファン視点 1 行追加 の 3 点のみ
- status は draft 維持、publish 判断は user の最終 go 待ち
- patch 後 Claude は 4 点形式 (結論 / patch 後 title と本文要約 / 残リスク / publish now or hold) で返す

## 切替 4: ChatGPT 相談を標準フローに組み込み

- 背景: user の判断負荷を増やさずに第三者レビューを挟む
- 運用: Claude は毎回返答の最後に「ChatGPT相談用ブロック」を付ける
- user は当該ブロックをコピペするだけ、長文の整理は要求しない
- ChatGPT 返答が戻るまで新便は流さない
- ChatGPT 返答後は「結論 / 理由 / 次アクション」の 3 点で短く返す

## 切替 5: 役割分担を 4 者で固定

- 今日の確定方針:
  - Codex = 開発実行のみ
  - Claude Code = 監査 / queue / 起票
  - ChatGPT = 相談役
  - user = 最終の `go / stop / publish / hold`
- なぜそうしたか:
  - 実装判断と監査判断が混ざると、scope 拡張と独断進行が起きやすかった
  - user の判断負荷を減らしつつ、最終決裁点だけは user に残す必要があった
  - ChatGPT を相談役として分離すると、Claude Code が監査役に徹しやすい
- どこで迷ったか:
  - 恒久ルールの置き場を `CLAUDE.md` に置くか `AGENTS.md` に置くかで迷った
  - 結論として、Codex が参照し編集できる運用ルールは `AGENTS.md` に寄せ、`CLAUDE.md` は触らない方針に固定した

## 統合結果

次回以降の Claude 返答は以下 5 セクション構成:

1. 結論
2. 今日の publish candidate 最大 3 本 (または Codex 返答要約)
3. 最優先の 1 本 (または残リスク)
4. patch then publish の必要修正 最大 3 項目 (または publish now / hold 判定)
5. 次に流す候補便 1 本だけ
末尾: ChatGPT相談用ブロック

user への要求は原則 go / stop / publish / hold の 4 択に固定。

## ChatGPT 判断（2026-04-19 受領）

§29 の 7 原則のうち、実運用で最初に形骸化しそうな条項について ChatGPT に相談した結果。

形骸化リスク上位 2 点:

1. 「候補ゼロで返さない」
   - 弱い draft を無理に候補化する圧力になりやすい
   - 補正案: publish now が 0 本でもよい。ただし patch then publish の最有力 1 本、または today no publish の理由を必ず返す
2. 「ChatGPT相談用ブロックを毎回フルで付ける」
   - 相談自体は良いが、運用が重いと儀式化しやすい
   - 補正案: 2 段階化（通常時 = 短縮版、迷い大 = 詳細版）

運用方針（今週）:

- §29 は今週そのまま運用、CLAUDE.md は触らない
- 1 週間後に運用証拠を見て §29 改訂可否を判断

印ルール（この session log に追記していく）:

- 「無理に候補化した回」は ⚠ 印 + 日付 + post ID で残す
- 「相談ブロックが重かった回」は ⚠ 印 + 日付 + 対象で残す
- 印が 3 件以上溜まったら §29 改訂便を検討する

### 印ログ

(今週分、該当発生時に追記)

## 運用事故防止ルール: Codex patch 便 publish 検出時 stop

### 事故経緯（2026-04-19）

- 62591 patch-only 便を draft 前提で Codex に流した
- Codex fetch 時点で 62591 は既に `status=publish`（初回 publish = 2026-04-18T19:27:38）
- Codex は status 変更せず title/本文のみ update（HTTP 200）
- 結果として live の公開記事（https://yoshilover.com/62591）が user 最終 go を経ずに書き換わった
- ChatGPT 判断: 品質改善方向で revert 不要、ただし運用ルール側を修正

### 既定運用ルール（今週運用、1 週間後に §29 恒久化検討）

1. Codex patch 便の最初に WP REST GET で status を必ず確認する
2. `status=draft` のときだけ通常 patch を続行
3. `status=publish` を検出したら即 stop、Claude に報告して user 判断を待つ
4. publish 記事を触るのは user が明示 go したときだけ
5. ルール適用対象: WP 記事に PUT/POST する全 Codex 便

### Claude 側チェック

- patch 便起票時、対象 post の現 status を Claude が read-only で事前確認する
- status=publish なら便 scope を「publish 記事への変更」と明記し、user 判断を先に求める
- status=draft なら通常フロー

### 記録方針

- 運用事故は session log に事故経緯 + 採用ルールで残す
- §29 への恒久化は 1 週間の運用証拠を見てから判断
- 事故再発時は印 + 日付 + post ID で追記

## 2026-04-19 夜 postgame auto-publish 継続判断

- user 判断: go（今夜の postgame auto-publish は通常フロー継続）
- 範囲: 今夜は postgame のみ観察、他 subtype は広げない
- 停止条件: 明らかな title-body mismatch、または事故が出た時点で即 stop 切替
- 理由: 公開較正モードの主目的は「公開して判断できる状態を作ること」。ここを止めると今日の判断材料が増えない
- 前提: 62591 事故は read-only 事前 status 確認ルールで再発防止済、revert 不要（ChatGPT 判断）

## 2026-04-19 publish ON ルートの扱い（恒常化）

- 通常時: publish ON ルート（postgame / lineup）はそのまま回す。毎回 go / hold を user に聞かない
- Claude Code の responsibility: 事故・title-body mismatch・事実安全性の問題を検知した時だけ、その場で user に stop 判断を上げる
- 例外時のみ user に 1 件上げる（go / hold を並べない）
- Claude の通常返答 4 セクション: 結論 / publish ON ルートの状態 / 事故有無 / user 判断が必要な 1 件（ある時だけ）
