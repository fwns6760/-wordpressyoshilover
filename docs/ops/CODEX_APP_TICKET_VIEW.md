# CODEX_APP_TICKET_VIEW - user向けチケット見える化

最終更新: 2026-05-03 JST

## 目的

Codex App上で、userが今見るべきチケットだけを確認できるようにする。
これは全チケット一覧ではなく、user向けの入口。
詳細な仕分けは以下を正本にする。

- `docs/ops/ヨシラバーチケット管理.xlsx`
- `docs/ops/BUG_INBOX.md`
- `docs/ops/TICKET_OPERATION_RULES.md`
- `docs/ops/チケット棚卸し案_2026-05-02.xlsx`

## userが見るもの

原則、userが見るのは最大5件だけ。

1. ACTIVE最大2件
2. READY_NEXT最大3件
3. USER_DECISION_REQUIRED がある場合は最大1件

DONE / OBSERVE / HOLD の正常報告はここに載せない。
ACTIVE最大2件はuserが選ぶ2件ではなく、現場Claudeが同時実行する上限。
ACTIVEが完了 / OBSERVE / HOLD になったら、USER_DECISION_REQUIREDでない限りREADY_NEXTから自動昇格する。
userに「次どれにしますか？」とは聞かない。

## 今のACTIVE

| 優先 | ID | 内容 | user作業 |
|---|---|---|---|
| 1 | BUG-004 + 291 | publish=0原因分解 + narrow publish-path unlock。292 body_contract_fail durable ledger方針を解除条件として含む。 | なし |

## 全体横串ルール

品質改善と同時に、コスト削減も常に見る。

- Geminiに追加で考えさせない。
- 足りない事実をLLM/Codexに補完させない。
- source/metaにない数字・勝敗・選手名を書かせない。
- 重複source/contentで再生成しない。
- fail/review/holdをメール大量化させない。
- mail通知はYOSHILOVER対象だけに絞る。
- タイトル・本文・候補修正は、まずregex / marker / template / source slot-fillで済ませる。

## ACTIVE候補の解釈

### BUG-003

公開状態が勝手に変わる疑いはP1候補。
まず直近24〜72hのWP status mutation、WP REST更新、publish→draft/private変化をread-onlyで見る。
証拠なしだけでDONEにしない。
ただし、2026-05-03時点ではACTIVEから外し、P1_REVIEW / RECHECK_LATER 扱いにする。
今は publish=0 回収に集中する。

### BUG-004 + 291

候補ができたら、publish / review / hold / skip / error のどこかに必ず着地することを確認する。
さらに、user回答により以下を含める。

- YOSHILOVER対象外sourceのメールは完全に送らない。
- mail対象に出るなら、通知前にpublish判定へ戻す。
- ただし現状はpublish判定が曖昧なので、まずread-only auditで境界を固める。
- body_contract_validate fail は通常メール不要。ledger/logに残ればよい。
- publish=0 の原因を read-only で分解し、全体緩和ではなく高信頼候補だけを publish path に戻す。
- `292 body_contract_fail durable ledger方針` は独立ACTIVEにしない。BUG-004+291 の解除条件・必須サブタスクとして同時に扱う。

#### BUG-004+291 追加subtask: publish=0原因分解 + narrow publish-path unlock

目的は、publish gate を雑に緩めることではない。
公開ゼロの原因を分解し、品質条件を満たす候補だけを狭く公開pathへ戻す。

まず分解する原因:

- `277` title quality
- `289` post_gen_validate
- `290` weak title rescue 不発
- 4-tier分類の strict 判定
- duplicate / backlog / freshness
- body_contract
- subtype misclassify
- numeric guard / placeholder / source facts 不足

publish候補に戻してよい最小条件:

- YOSHILOVER対象
- source_urlあり
- subtype / template_key high confidence
- numeric guard pass
- body_contract pass
- placeholderなし
- silent skipなし
- titleが最低限「何の記事か分かる」
- review / hold 理由なし

2026-05-03 user-confirmed rescue targets:

- 試合結果記事: 当日 + 巨人対象 + 相手 + スコアが title / source / meta / body のどこかから取れる場合はpublish候補へ戻してよい。
- 先発投手成績: sourceに投手成績がないだけでは落とさない。ただしsourceにない投球回 / 被安打 / 失点 / 勝敗は本文に書かない。
- 監督・コーチコメント: 阿部監督だけでなくコーチコメントも救う。コメント全文でなく一部でもsourceが明確ならpublish候補。postgameへ雑分類しない。
- 選手コメント: 必須救済対象。選手名とコメント元が明確ならpublish候補。scoreがなくてもplayer_commentとして扱い、勝敗・成績を補完しない。
- 二軍結果: 必須救済対象。farm_resultは一軍postgameと分け、二軍 / 相手 / スコアが取れるならpublish候補。
- 二軍スタメン: 必須救済対象。farm_lineupはfarm_resultと分け、スタメン表 / 打順 / 選手名が取れるならpublish候補。
- pregame / 予告先発: 必須救済対象。probable_starter / pregame / lineupは救う。ただし試合後に古いpregameを出さない。
- 昇格・降格・復帰・二軍落ち・若手記事: 必須救済対象。一軍昇格、登録抹消、一軍から二軍に落ちた選手、復帰組、若手注目はnotice / roster_notice / injury_recovery_notice / farm_player_result等へ寄せる。

publish不可を維持するもの:

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
- 重複記事
- stale postgame
- weak titleのまま何の記事かわからないもの

弱いタイトル方針:

- 弱いタイトル対策は必須。
- 「何の記事かわからない」タイトルはpublishしない。
- ただしcoach_comment / player_comment / farm_result / farm_lineup / roster_noticeなど中身が明確ならdeterministic rescue候補にする。
- AIでタイトルを自由生成しない。source/metaから取れる選手名・記事タイプ・相手・スコアだけを使う。

重複方針:

- 報知 / 日刊 / スポニチ / 公式 / X由来などで同内容が複数来た場合、基本は1本だけ。
- duplicate guardは緩めない。
- 同じsource_url / content_hash / 同一内容はpublishしない。

やらないこと:

- publish gate 全体緩和
- 悪い記事を後で消す前提の大量公開
- noindex解除
- review thresholdを上げるだけのmail隠し
- user判断なしのSEO変更

このsubtaskは新規ticket化しない。
`BUG-004+291` のACTIVE内で扱う。

#### 292の吸収方針

`292 body_contract_fail durable ledger方針` は、独立ACTIVEではなく BUG-004+291 の解除条件として扱う。

目的:

- body_contract_fail が黙って消えない。
- 通常メールを増やさない。
- ledger / log で後から件数と理由を追える。
- BUG-004+291 の publish path unlock 設計時に、body_contract fail が解除条件として見える。

やらないこと:

- body_contract_fail を通常メール大量通知にする。
- 292を独立ACTIVEへ戻す。
- body_contractを雑に緩める。

#### BUG-004+291 subtask-7: guarded-publish gate reason audit

2026-05-03 の現場報告で、BUG-004+291 は次の層へ進んだ。

判明したこと:

- publish-only Gmail filter は有効。通常Gmailへの post_gen_validate / body_contract / skip / review 診断混入は止まった。
- narrow unlock は有効。whitelist限定で farm / player の draft が2件作成された。
- それでも publish=0 が継続している。
- つまり主因は fetcher ではなく、guarded-publish 後段 gate 側へ移った。

目的:

- draft化された2件が、なぜ guarded-publish で publish 化されなかったかを read-only で特定する。
- publish gate 全体緩和ではなく、高信頼候補だけを publish path へ戻す最小条件を決める。

見るもの:

- guarded_publish_history.jsonl
- guarded_publish_yellow_log.jsonl
- guarded-publish Cloud Run logs
- 対象2件の post_id / status / subtype / title / source_url / fail flags
- numeric guard
- placeholder / body_contract
- duplicate
- freshness / backlog_only
- publishable判定
- review / hold / hard_stop理由

禁止:

- publish gate 全体緩和
- postgame strict / stale / duplicate の雑な解放
- env/flag変更
- Gemini call増加
- mail量増加
- WP status変更
- 新規チケット化

報告条件:

- 2件がpublishされなかった理由を特定した時
- guarded-publish側に silent path があった時
- high-confidence候補をpublishへ戻すための最小条件が分かった時

#### BUG-004+291 read-only診断 snapshot(2026-05-02)

- ローカル `sports_fetcher.log` の直近 42 本の `rss_fetcher_flow_summary` は `prepared_total=2`、`created_total=0`、`stale_postgame=42/42`。
- `prepared_total=2` はどちらも `lineup` で、`2026-04-30 17:54:42` と `2026-04-30 18:16:38` に prepared のまま止まっている。
- 同期間の `postgame` 候補 `【巨人】阪神に3-2で勝利　岡田悠希が決勝打` は `strict_review_fallback:close_marker` / `strict_insufficient_for_render` / `strict_validation_fail:key_events` を反復し、duplicate 側でも `existing_publish_same_source_url` を 17 回踏んでいる。
- `weak_title_rescued` は 12 件あるが `blacklist_phrase_message` 1 pattern のみ。`title_player_name_unresolved` は `投手コメント整理` 24 件で残存。
- 現状の主因は「guard 全体が厳しすぎる」より、stale/duplicate と strict postgame fallback による upstream starvation。よって unlock は deterministic な non-postgame title rescue だけに狭く限定し、postgame strict / stale / duplicate は閉じたままにする。

## OBSERVE

| ID | 内容 | 報告trigger |
|---|---|---|
| 282-COST | flag ON後の preflight active rejection 観察。未発火は異常ではない。 | 実発火 / 誤停止疑い / silent skip / Gemini増 / mail storm |
| 298-Phase3 | 2026-05-03 19:35 JST の24h gate判定待ち。 | PASS / FAIL / rollback条件 |

## USER_DECISION_REQUIRED

| ID | 内容 | userが返すもの |
|---|---|---|
| 245 | WP plugin upload。画面上に「自動投稿」カテゴリが見える問題の本番反映。 | OK / HOLD / REJECT |

## 後回し

| ID | 扱い |
|---|---|
| 277 / 279 / 278 / 280 | title / mail / summary 系。BUG-004+291で必要な部分だけ参照し、独立ACTIVE化は後。 |
| 234 / 247 / 250 / 256 / 254 / 295 | 本文テンプレ・subtype系。publish=0回収後に順番。 |
| 246-MKT / 195 / 197 / 281 | マーケ・導線・二軍増加。記事供給回復後。 |
| 230 / 251 / 252 / 274 / 296 / 238 | HOLD / OBSOLETE寄り。今は触らない。 |
| 288-INGEST | source/topic expansion。BUG-004+291後のREADY_NEXT候補。東スポ巨人、東スポWEB、YouTube/GIANTS TV、Yahooバズkeywordを吸収検討。ただしsource追加はUSER_DECISION_REQUIRED。 |
| GCP Codex WP本文修正プレビュー v0 | 早くやりたい候補として保持。ただし今はBUG-004+291を優先。 |
| BUG-008 | mail送信path LLM混入read-only確認。**DONE 2026-05-03 (CLEAN)** — audit `docs/ops/bug008_mail_llm_audit.md` commit fba14e3、mail path LLM call 0、P1 昇格不要 |

## NEW_CANDIDATE: GCP Codex WP本文修正プレビュー v0

user希望により、早めにやりたい候補として保持する。
まだ正式番号は振らない。

目的:

- WordPress本文をいきなり変更せず、GCP Codexで修正文候補だけ作る。
- userが完全運用前に本文修正品質を早く確認できるようにする。
- 本文品質が低くてpublishできない記事を、出せる品質へ寄せられるか検証する。
- Gemini費用を増やさず、GCP Codex / deterministic rule / template / source-meta slot-fill中心で試す。

制約:

- preview-only。
- WP本文変更なし。
- publish状態変更なし。
- Gemini call 原則0。
- X投稿文は作らない。
- source/metaにない数字・勝敗・選手名・投手成績は補完しない。
- 最初から全subtypeに広げない。

最初の対象候補:

- `postgame`
- `farm_result`

やってよいこと:

- placeholder削除。
- 空見出し削除。
- sourceにないoptional section削除。
- 短文化。
- 低品質本文を固定テンプレへ寄せる。
- 元本文と修正文候補のdiff生成。
- source/meta由来fact一覧の表示。

やってはいけないこと:

- sourceにない数字・選手名・勝敗・コメント補完。
- 長文再作文。
- Gemini追加呼び出し前提の修正。
- WordPress本文の即時上書き。

ACTIVE化の考え方:

- 原則は `BUG-004+291` の後。
- ただし本文品質確認を急ぐ場合は、`BUG-003` と入れ替えてACTIVE候補化も可能。
- `247 / 234 / 295 / 290 / 254` と連動する。

## 残す方向の重要チケット

| ID | 扱い | 理由 |
|---|---|---|
| 229 / 282 / 293 | KEEP | Gemini費用削減は本線。282は293 FULL_EXERCISE後。 |
| 234 / 247 / 250 / 256 | KEEP | 本文テンプレ・postgame strict・監督/選手コメント strict は必要。 |
| 247 | KEEP | postgame strictでは先発投手成績を特に守る。 |
| 254 | KEEP | 投手回数・スターター表記の正規化は必要。 |
| 264 | ABSORB | 過去cleanupは不要。今後の重複削減を229/235/300/BUG-004へ吸収。 |
| 281 | KEEP | 大手が出さない巨人専門価値。復帰組・二軍スタメンを増やす。 |
| 283 | KEEP | 独自記事要件・regression contract は必要。 |
| 290 | KEEP | weak title rescue は必要。ただしまず検知優先。 |
| 295 | KEEP | subtype誤分類はハルシネーション防止のため重要。 |
| 294 | KEEP | release composition gate。deploy事故防止の親ticketとして残す。 |
| 195 / 197 | KEEP | 記事下の読者向けXシェア導線は必要。 |
| 246-MKT | KEEP | 今日の巨人ファン観戦ガイド。まずトップページだけ。 |

## HOLD / OBSOLETE候補

| ID | 扱い | 理由 |
|---|---|---|
| 230系 | HOLD | GCP runtime costは後で。安全な小額cleanupだけ候補。 |
| 238 | OBSOLETE候補 | 夜間draft-only / 朝レポートは捨てる。 |
| 248 / 255 / 260 | HOLD | マーケ拡張・コメントbadge・独自記事型は後回し。 |
| 251 | DONE/OBSOLETE候補 | SEO/noindexはもうできている。今後いじらない。 |
| 252 | OBSOLETE候補 | XはGPTs手動運用へ寄せたため不要寄り。 |
| 274 | OBSOLETE候補 | Gmail filterでありGitHub Actions赤の根本対応ではない。不要。 |
| 275 | ABSORB/DONE候補 | GitHub Actions赤は今出ていない。299に吸収し、緑確認でclose候補。 |
| 288 | KEEP / READY_NEXT候補 | source追加・取得元拡張。210系と246 viral topicを吸収検討。東スポ巨人、東スポWEB、YouTube/GIANTS TV、Yahooリアルタイム検索・ニュースランキングをPhase 0 read-only/dry-runで棚卸しする。source追加はuser GOまでHOLD。 |
| 296 | OBSOLETE候補 | codex-shadow再設計は不要。 |

## 299 / 201 / 275 の扱い

pytest / CI / flaky整理は必要。
ただし役割を分ける。

- 299-QA: 親として残す。
- 201: time-dependent flaky。299へ吸収候補。
- 275: GitHub Actions赤は現状なし。299へ吸収し、緑確認後close候補。

## 現場Claudeへ渡す1文

```text
BUG_INBOX初回棚卸しでは、ACTIVE候補は BUG-003 WP status mutation audit と BUG-004+291 silent skip / 候補消失 / YOSHILOVER対象外メール / 自動公開判定整理の2件だけです。他のP1候補は一括ACTIVE化しないでください。291は対象外sourceメールを完全に送らない方針、mail対象ならpublish判定へ戻す方針ですが、publish判定境界が曖昧なのでまずread-only auditで確認してください。292は通常メール不要、ledger/log確認に寄せてください。
```

## 現場Claudeへ渡す品質改善プロンプト

詳細版は `prompts/ops/bug004_291_publish_zero_narrow_unlock_prompt.md` を正本にする。

```text
BUG-004+291 の中で publish=0原因分解 + narrow publish-path unlock を実施してください。
新規ticket化しないでください。

目的は publish gate の全体緩和ではありません。
公開ゼロの原因を read-only で分解し、高信頼条件を満たす候補だけ publish path に戻す設計にしてください。

分解対象:
- 277 title quality
- 289 post_gen_validate
- 290 weak title rescue不発
- 4-tier分類strict
- duplicate / backlog / freshness
- body_contract
- subtype misclassify
- numeric guard / placeholder / source facts不足

publish候補に戻してよい条件:
- YOSHILOVER対象
- source_urlあり
- subtype/template_key high confidence
- numeric guard pass
- body_contract pass
- placeholderなし
- silent skipなし
- titleが最低限「何の記事か分かる」
- review/hold理由なし

やらないこと:
- publish gate全体緩和
- 悪い記事を後で消す前提の大量公開
- noindex解除
- review thresholdを上げるだけのmail隠し
- user判断なしのSEO変更

報告triggerは、原因分解完了、narrow unlock設計完了、P1異常、rollback必要、USER_DECISION_REQUIREDのみ。
正常系の定期報告は不要です。
```

## 現場Claudeへ貼る完成文(2026-05-03)

```text
方針確認済み。

現場Claudeは、BUG-004+291を中心に進めてください。
今回「publish=0原因分解 + narrow publish-path unlock」はBUG-004+291へ正式吸収します。
新規チケット化はしません。

292 body_contract_fail durable ledger方針は、独立ACTIVEではなく、BUG-004+291の解除条件・必須サブタスクとして扱ってください。
つまり、BUG-004+291を進める中で292相当の方針も同時に整理してください。

ACTIVE:
- BUG-004+291 publish=0原因分解 + narrow publish-path unlock
  - 含む: 292 body_contract_fail durable ledger方針

OBSERVE:
- 282-COST flag ON後のpreflight active rejection観察
- 298 5/3 19:35 JST 24h gate判定

USER_DECISION_REQUIRED:
- 245 WP plugin uploadのみ

後回し:
- 277/279/278/280 title/mail/summary系
- 234/247/250/256/254/295 本文テンプレ・subtype系
- 246-MKT/195/197/281 マーケ・導線・二軍増加
- 230/251/252/274/296/238 HOLD/OBSOLETE寄り

禁止:
- publish gate全体緩和
- postgame strict / stale / duplicateの雑な解放
- noindex解除
- review thresholdを上げるだけのmail隠し
- 新規チケット追加
- body_contract_fail を通常メール大量通知にすること

目的:
高信頼条件を満たす候補だけ、狭くpublish pathへ戻す。

publish候補へ戻してよい条件:
- YOSHILOVER対象
- source_urlあり
- subtype / template_key high confidence
- numeric guard pass
- body_contract pass
- placeholderなし
- silent skipなし
- titleが最低限「何の記事か分かる」
- review / hold理由なし

まずはread-onlyで、publish=0の理由を分類し、どの条件で狭くunlockできるかを証拠付きで出してください。
あわせて、body_contract_fail が黙って消えず、通常メールを増やさず、ledger/logで後から件数と理由を追える設計も出してください。

報告は以下だけでよいです。
- publish=0原因分解完了
- narrow unlock設計完了
- 292相当のledger方針完了
- P1異常
- USER_DECISION_REQUIRED
```

## 現場Claudeへ渡す完成文

```text
ACTIVE最大2件はuserが選ぶ2件ではなく、現場Claudeが同時実行する上限です。今回のACTIVEは 1) BUG-003 WP status mutation audit、2) BUG-004+291 silent skip / 候補消失 / YOSHILOVER対象外メール / 自動公開判定整理 の2件です。READY_NEXTは 1) GCP Codex WP本文修正プレビュー v0、2) BUG-008 mail送信path LLM混入read-only確認、3) 245 front自動投稿カテゴリ非表示確認 です。ACTIVEが完了 / OBSERVE / HOLD になったら、USER_DECISION_REQUIREDでない限りREADY_NEXTから自動昇格してください。やってよいことはread-only audit、doc-only整理、test plan、rollback plan、Acceptance Pack補強、preview-only設計です。やってはいけないことは本番本文変更、publish状態変更、env/flag/Scheduler/SEO/source変更、Gemini call増加、mail量増加、チケット番号振り直し、新規ticket大量発行です。user判断が必要なのはflag ON、挙動変更deploy、Gemini/mail/source/SEO/Scheduler変更、rollback不能変更だけです。報告triggerはACTIVE完了、P1相当異常、rollback必要、USER_DECISION_REQUIRED、新たなP0/P1証拠のみです。userに「次どれにしますか？」と聞かないでください。
```

## 報告ルール

Codex / Claude がuserへ出すのは以下だけ。

- ACTIVE完了
- P1相当の異常
- rollback必要
- USER_DECISION_REQUIRED
- 新たにP0/P1へ昇格すべき証拠

出さないもの。

- cycle silent
- 異常なしの定期報告
- 次wake予定
- monitorなし
- user返答不要の正常系報告
- 長いlog貼り付け
- HOLD / OBSERVE / DONE の正常報告

## 更新ルール

- 新しい違和感は、userがチャットに貼るだけ。
- CodexがBUG_INBOXへ反映し、このviewには最大5件だけ載せる。
- チケット番号は振り直さない。
- 新規ticket候補は番号を振らず、候補のまま保持する。
