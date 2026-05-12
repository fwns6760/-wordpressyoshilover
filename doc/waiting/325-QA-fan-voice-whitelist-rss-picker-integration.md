# 325-QA fan voice whitelist RSS picker integration

## meta

- number: 325-QA
- type: fan voice / picker integration / ENABLE flag default off
- status: BLOCKED_USER
- priority: P1
- owner: user GO 待ち
- implementation_owner: Codex after GO
- lane: B
- created: 2026-05-12
- doc_path: `doc/waiting/325-QA-fan-voice-whitelist-rss-picker-integration.md`
- blocked_by: 324-QA landed + 観察 OK + user GO
- note: 本便はこの Markdown 新規作成のみ。code edit、commit、push、deploy、env / scheduler / Cloud Run / X API 変更は GO 後まで保留

## 1. 今回の目的

324-QA で登録した `fan_voice_pool` bucket を、`fetch_fan_reactions_*` picker の **前段** primary candidate として使う統合を行う。

- whitelist で `fan_reaction_limit` 充足したら Yahoo / Grok は呼ばない
- 不足分のみ既存 Yahoo / Grok 経路で補欠 fill
- `ENABLE_FAN_VOICE_WHITELIST=0` **既定 off** の flag gate、可逆性確保
- flag flip(本番 ON 切替)は本 ticket では行わない(別便で canary)

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/rss_fetcher.py`(`fetch_fan_reactions_from_yahoo` 前段に whitelist primary 経路を追加、`ENABLE_FAN_VOICE_WHITELIST` 読み取り)
- 必要なら whitelist picker helper 1 file
- 関連 test(`tests/test_rss_fetcher*` に whitelist primary + flag off 時 no-op の unit test 追加)
- 本 ticket 自身 `doc/waiting/325-QA-fan-voice-whitelist-rss-picker-integration.md`

## 3. 今回触らない範囲

- `config/rss_sources.json`(324 担当、本便は読み取りのみ)
- RSSHub fetch ループ本体(324 担当)
- publish / mail / scheduler / env / Cloud Run / Secret Manager
- **X API plan** 切替(禁止、user §11 判断境界)
- WordPress 本番(REST GET 以外)
- `fetch_fan_reactions_with_grok` の Grok API call 形式
- oEmbed 形式 / X カード描画
- 309-QA / 310-QA / 311-QA(件数拡張)の picker 挙動
- 既存 Yahoo focus_score / opinion_score / commentary_score / similarity dedupe ロジック

## 4. 影響範囲

- flag ON 時のみ: 記事 body の `💬 ファンの声` block に whitelist handle 由来の reaction が出る
- flag OFF 時(本 ticket landed 直後 = 既定): 記事 body は完全に不変
- 本番 ON 切替は本 ticket scope 外(別便で canary)

## 5. 実行予定テスト

1. 追加再現テスト(赤確認 → 緑確認)
   - flag OFF: 出力 diff = 0(既存 Yahoo 経路のみ)
   - flag ON + whitelist 充足: Yahoo / Grok を呼ばない
   - flag ON + whitelist 不足: Yahoo / Grok で補欠 fill、合計が `fan_reaction_limit` 以内
   - flag ON + whitelist 内に topic match なし: 既存 strict match ロジックで除外
   - flag ON + 別試合 / 別カード / 別日付の whitelist post を混ぜない
2. related unit tests
   - `tests/test_rss_fetcher*`
   - `tests/test_yahoo_realtime*`
   - `tests/test_nomotoke_card_renderer*`
3. full suite
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 324-QA が landed していない / 観察未完なら本 ticket 着手しない
- flag OFF 時に出力 diff が 0 にならない(可逆性破綻)場合 STOP
- whitelist primary の topic match が既存 Yahoo の strict match より弱い場合 STOP(精度回帰)
- 309-QA / 310-QA / 311-QA と picker 挙動が衝突する場合は scope 切り直しで STOP
- X API plan 切替の議論が出たら STOP
- 全件テスト green を満たせない場合 STOP

## 7. 禁止事項

- `ENABLE_FAN_VOICE_WHITELIST` の **既定値 ON** 化(本 ticket では既定 0 のみ)
- 本番 flag flip(別便で canary)
- handle curation の編集(324 担当)
- 既存 Yahoo / Grok 経路のロジック改変(picker 前段への追加のみ)
- X API 課金 plan に手を出さない
- scheduler / env / Cloud Run / WP 本番への変更

## 8. 想定されるデグレ

- flag ON 時、whitelist 内に topic 一致が弱い post が紛れる(strict match で除外する想定だが、誤適用リスク)
- 感情の偏り(curation 次第、user 判断で curation 修正)
- whitelist 内の handle が削除 / private 化した時の挙動(空 list 扱い、Yahoo 補欠 fill に落ちる想定)

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-12 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |

## 10. Regression Memo欄

### current observation

- 現状 picker は Yahoo Realtime → focus_score / opinion_score / strict source match の 3 段で絞っているが、別人混入が漏れる
- 324 で source 確定後、本 ticket で picker 前段に whitelist primary を入れることで、別人混入を 0 にできる

### guard hypothesis

- guard A: 既定 0 で flag gate、可逆性確保
- guard B: whitelist 充足したら Yahoo 不要 / 不足は補欠 fill、件数を犠牲にしない
- guard C: 既存 strict match ロジックを壊さない(picker 前段への追加のみ)

## 11. 関連 ticket

- **324-QA-fan-voice-whitelist-rss-source-registration**(本 ticket の前提、source registration、本 ticket は picker 統合のみ)
- 309-QA / 310-QA / 311-QA(X reaction 件数拡張、picker 中の挙動を触る、本 ticket の write scope と衝突しうるので順序調整必要)

## 12. flag flip rollout(別便で扱う)

本 ticket では `ENABLE_FAN_VOICE_WHITELIST=0` 既定 off のみ。本番 ON 切替は別便で canary。

canary 判断軸:

- 324 landed 後 1〜2 週間の RSSHub 健全性観察 OK
- 本 ticket landed 後 fixture-based 全件 green
- user 明示 GO
