# BUG_INBOX — 正式ticket化前の違和感受け皿

最終更新: 2026-05-02 JST

入力元: `C:/Users/fwns6/Downloads/yoshilover_degre_kaishu_memo_format.xlsm`

管理Excel: `docs/ops/ヨシラバーチケット管理.xlsx`

運用:

- userは現場報告・違和感・ログをチャットにそのまま貼るだけ。
- userはExcelを編集しない。仕分けしない。優先度を細かく考えない。ticket番号を作らない。
- Codexはuserが貼った現場報告から必要なBUG_INBOX行を抽出し、Excelの `01_BUG_INBOX` に追記する。
- Codexは新規行を仕分け、既存ticketに吸収できるものは吸収する。
- 新規ticket候補は番号を振らず、候補のまま保持する。
- `02_P1` / `03_Absorb` / `04_NewCandidate` / `05_HOLD` / `06_DONE` / `00_Summary` は仕分けビュー。
- 次にACTIVEへ上げるのは最大2件だけ。
- 現時点のACTIVE候補は `BUG-003 WP status mutation audit` と `BUG-004 silent skip / 候補消失の可視化確認`。
- 他のP1候補は `P1_REVIEW` のまま保持し、ACTIVEに上げない。
- 現場ClaudeはACTIVE最大2件だけ実行し、OBSERVE / HOLD / DONEの正常報告をしない。
- state到達、異常、rollback、USER_DECISION_REQUIREDだけ報告する。

毎回の報告形式:

1. BUG_INBOXへ追加したもの
2. 既存ticketに吸収したもの
3. ACTIVE候補 最大2件
4. user判断が必要なもの
5. 現場Claudeへ渡す1文

## 目的

userが感じた「変なバグ」「動いていないもの」「忘れたくない違和感」を、正式ticketと混ぜずに管理する。

- チケット番号の破壊的な振り直しは禁止。
- Excelだけを正本にしない。
- まずBUG_INBOXで受け、既存ticketに吸収できるものは吸収する。
- 紐付かないものだけ新規ticket候補にする。
- 正式ticket化前に、影響・再現性・close条件を書く。

## P1候補として軽く扱わないもの

- 公開状態が勝手に変わる
- 候補が消える
- メールに出ないskip
- 止めているticketのコードがbuildに混ざる
- 作業ゴミがdeployに混ざる
- rollback targetが曖昧
- mail送信pathにLLM呼び出しが追加される
- cache_hit 99%雪崩をsteadyと誤認する

## Inbox

| inbox_id | 現象 | 影響 | 分類 | 関連ticket候補 | 処理方針 | owner | 次の一手 | close条件 | evidence |
|---|---|---|---|---|---|---|---|---|---|
| BUG-001 | H3にいらないものが多い、本文が見出しで膨らむ | 記事品質低下、材料なしsectionをAIが埋める | 品質 / 改修 | 234 / 234-impl-* / 283-MKT | 既存ticketに吸収 | Claude -> Codex候補 | 具体post_idまたはfixtureを紐付ける | 234系で吸収可否が決まり、再発防止testがある | Excelメモ行:「Ｈ３にいらないものが多い（本文）」 |
| BUG-002 | 通知メールにTwitter/Xリンクがある | GPTs運用と重複、mail本文ノイズ | 通知 / X | 279-QA / publish-notice mail body hygiene候補 | 新規ticket候補 | Claude | mail本文のどのfieldかread-only確認 | 消すリンク種別と残すリンク種別が決まる | Excelメモ行:「通知メールにtwitterリンクがある。」 |
| BUG-003 | mailが飛んで来たら全公開が非公開になったように見えた | 公開状態が勝手に変わる疑い。信頼性P1 | デグレ | 298-Phase3 / guarded-publish / WP status mutation audit候補 | 新規ticket候補 | Claude | 該当時刻のWP status mutation、guarded-publish、publish-notice、cleanup logをread-only照合 | publish->draft等のmutation有無と原因が確定する | Excelメモ行:「ｍａｉｌが飛んで来たら全公開が非公開になった」 |
| BUG-004 | メールに出ないskip、候補が消える事故源 | userから候補が見えない。受け入れ条件違反 | デグレ防止 / observe | 289 / 291 / 292 / 293 / 288 Phase 1/2 | 既存ticketに吸収 | Claude / Codex | silent skip pathごとにmail/ledger/log/user-visible経路を確認 | publish/review/hold/skip通知のどれかで見える | Excelメモ行:「メールに出ない skip(候補が消える事故源)を deploy 前 grep」 |
| BUG-005 | 止めているticketのコードがbuildに混ざる | HOLD中機能の暗黙carryで本番挙動が変わる | デグレ防止 / release | 294-PROCESS | 既存ticketに吸収 | Claude | target image commit一覧とHOLD ticketをdeploy前gateへ吸収 | 294またはPackにHOLD commit混入検出が入る | Excelメモ行:「止めてる ticket のコードが build に混ざらないか確認」 |
| BUG-006 | 作業ゴミ(untracked / 想定外 modified)がdeployに混ざる | 意図しないコード・ログ・fixtureがimageへ入る | デグレ防止 / release | 294-PROCESS / POLICY / ACCEPTANCE_PACK_TEMPLATE | 既存ticketに吸収 | Claude | deploy前dirty gateをPackへ入れる | tracked diff / staged diff / untracked allowlist確認が必須化される | Excelメモ行:「作業ゴミ(untracked / 想定外 modified)が混ざらないか」 |
| BUG-007 | デプロイ直前、作業中ゴミが紛れ込む経路がある | build context汚染、再現不能な本番差分 | デグレ防止 / release | 294-PROCESS / build hygiene候補 | 既存ticketに吸収 | Claude | build contextとignoreをread-only点検 | build contextチェックがdeploy前verifyに入る | Excelメモ行:「デプロイの直前、作業中ゴミが紛れ込む経路がある」 |
| BUG-008 | mail送信pathにLLM呼び出しが追加されていないか | 通知だけでGemini/LLM費用が増える危険 | コスト / 通知 | 229 / 293 / 279-QA / publish-notice no-LLM invariant候補 | 新規ticket候補 | Claude / Codex | publish-notice / mail sender pathのLLM import/call grep | mail pathのGemini/LLM call 0証拠が残る | Excelメモ行:「mail 送信 path に LLM 呼び出しが追加されてないか」 |
| BUG-009 | rollbackの戻し先3種(env / image / GitHub)が全部記録されているか | rollback不能、復旧遅延 | 運用 / release | POLICY / ACCEPTANCE_PACK_TEMPLATE / 294 | 既存ticketに吸収 | Claude | env/image/GitHub 3次元rollback targetをPack必須化確認 | UNKNOWNならHOLDになる | Excelメモ行:「rollback の戻し先 3 種(env / image / GitHub)全部記録されてるか」 |
| BUG-010 | cache_hit 99%雪崩をsteadyと誤認しないか | Gemini費用急増の早期警戒漏れ | コスト | 229 / 293 / 改修 #1 #2 | 既存ticketに吸収 | Claude / Codex | cache_hit率だけでなくmiss率とGemini deltaを見る | cache miss avalanche alert条件がPackまたはpolicyに入る | Excelメモ行:「cache_hit 99% 雪崩(料金 100x 跳ね)を『これ steady じゃない』と明文化」 |
| BUG-011 | cache効果をexact / cooldown / dedupeに分けて見たい | 雪崩予兆の切り分けができない | コスト / observe | 改修 #1 cache_hit split metric | 既存ticketに吸収 | Claude | 改修 #1のdeploy/flag判断Packへ吸収 | metric分割がlog/ledgerで見える | Excelメモ行:「cache 効果を種類別に見られるよう分離」 |
| BUG-012 | cache外れすぎ時の自動ブレーキが必要 | Gemini call急増の防波堤 | コスト / guard | 改修 #2 cache miss circuit breaker | 既存ticketに吸収 | Claude / Codex | default OFF実装があるならflag ON判断Packへ | miss率閾値超過時にreview/holdへ倒す設計とrollbackが揃う | Excelメモ行:「cache 外れすぎた時の自動ブレーキ」 |
| BUG-013 | 1記事24hでGemini何回までの上限が必要 | retry/fallbackで同一postに課金集中 | コスト / guard | 改修 #3 per-post 24h Gemini budget | 既存ticketに吸収 | Claude | 改修 #3のdefault OFF実装・flag ON Packへ吸収 | post単位上限がdefault OFFで実装済み、ON条件がPack化される | Excelメモ行:「1 記事 24h で Gemini 何回まで、の上限」 |
| BUG-014 | prompt構造 / cache key変更をdeploy gateでcost reviewしたい | 無自覚なcache雪崩・費用増 | コスト / release | 改修 #4 prompt-id cost review gate / 294 | 既存ticketに吸収 | Claude | Pack templateにprompt/cache key変更欄を必須化 | Gemini delta見積もりが必須になる | Excelメモ行:「prompt 構造 / cache key 変更を deploy gate」 |
| BUG-015 | 古いpostの永久ledgerにTTLが必要 | ledger肥大化、古い候補再通知・保守負担 | 運用 / コスト | 改修 #5 old_candidate ledger TTL | HOLD | Claude / Codex | cleanup mutationを避け、default OFF設計に限定 | TTL pruneがdefault OFFで実装され、削除対象見積もりが出る | Excelメモ行:「古い post の永久 ledger に TTL(30/60/90d)」 |
| BUG-016 | メール枠cap=10にclass別最低保証が必要 | 重要通知が古い候補等に押し出される | 通知 / デグレ防止 | 改修 #6 mail cap class reserve / 289 | 既存ticketに吸収 | Claude | 改修 #6のdefault OFF実装・ON判断Packへ吸収 | real review / 289 / errorの最低枠が設計される | Excelメモ行:「メール枠 cap=10 の class 別最低保証」 |
| BUG-017 | GCP log保持期間設定を確認したい | 障害時に証拠が残らない / 費用も不明 | 運用 / コスト | 230 / 205 runtime drift audit / 新規候補 | 新規ticket候補 | Claude | read-onlyでLogging retentionと費用影響を確認 | retention現状、費用、変更要否が出る | Excelメモ行:「GCP の log 保持期間設定(GCP console)」 |
| BUG-018 | pytest baseline表現を1箇所に統一したい | CI赤/既存fail/新規failの混乱 | QA / 運用 | 299-QA / 275-QA | 既存ticketに吸収 | Claude | 299または275へ吸収、baseline表記テンプレ化 | test reportでbaseline/new failure/out-of-scope表現が統一される | Excelメモ行:「pytest baseline 表現を 1 箇所に統一(doc 整理)」 |

## 運用原則

BUG_INBOXは正式ticketではない。ここから直接実装・deploy・env/flag変更をしない。
