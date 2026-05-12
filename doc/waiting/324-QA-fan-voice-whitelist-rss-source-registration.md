# 324-QA fan voice whitelist RSS source registration

## meta

- number: 324-QA
- type: fan voice / RSSHub whitelist / source registration only / no body change
- status: BLOCKED_USER
- priority: P1
- owner: user GO 待ち
- implementation_owner: Codex after GO
- lane: B
- created: 2026-05-12
- doc_path: `doc/waiting/324-QA-fan-voice-whitelist-rss-source-registration.md`
- blocked_by: handle curation 別便で user 提供待ち(10〜20 件)
- note: 本便はこの Markdown 新規作成のみ。code edit、commit、push、deploy、env / scheduler / Cloud Run / X API 変更は GO 後まで保留

## 1. 今回の目的

`💬 ファンの声` 取得経路の precision を、Yahoo リアルタイム検索の語彙フィルタ依存から、**handle whitelist による provenance 確定** に切り替えるための **source registration を行う**。

本 ticket(324)では **記事 body には一切流し込まない**。`config/rss_sources.json` への登録、RSSHub fetch 経路の bucket 化、parse 層までで止める。picker 統合は **325-QA(picker integration)** の別 ticket で扱う。

分離理由:

- 324 単独で「RSSHub が 15 fan handle を 503 連発せず捌けるか」を観察可能
- 325 を流す前に source 健全性を確定させる
- 万一 RSSHub 不調なら 325 検討停止、cost risk(X API 課金 plan)に近づかない

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `config/rss_sources.json`(新 type `fan_voice_pool` で handle entry 追加、handle 一覧は user curation 反映)
- `src/rss_fetcher.py`(RSSHub fetch ループで `type=="fan_voice_pool"` を別 bucket に格納するだけ、`fetch_fan_reactions_*` 本体は不可触)
- 関連 test(`tests/test_rss_fetcher*` への source registration / bucket 分離 unit test 追加)
- 本 ticket 自身 `doc/waiting/324-QA-fan-voice-whitelist-rss-source-registration.md`

## 3. 今回触らない範囲

- `fetch_fan_reactions_from_yahoo()` 本体(picker は 325 担当)
- `fetch_fan_reactions_with_grok()` 本体
- 記事 body / `💬 ファンの声` block / oEmbed 形式
- publish / mail / scheduler / env / Cloud Run / Secret Manager / Cloud Run job image
- **X API plan**(無料 scrape のみ、課金 plan 切替は禁止、user §11 判断境界)
- WordPress 本番(REST GET 以外)
- 309-QA / 310-QA / 311-QA(件数拡張 ticket)の picker ロジック
- 既存 14 media RSSHub handle の挙動

## 4. 影響範囲

- 登録された fan handle の RSSHub fetch が走る(RSSHub Cloud Run の CPU 秒微増、月 ¥10〜30 オーダー想定)
- 内部 bucket `fan_voice_pool` が新規に存在する
- 記事 body / publish / X 自動投稿 / mail / SEO への影響 **ゼロ**(picker 不変)

## 5. 実行予定テスト

1. 追加再現テスト(赤確認 → 緑確認)
   - `config/rss_sources.json` に `type=fan_voice_pool` の entry を追加すると `rss_fetcher` が media RSSHub と分けて bucket 格納する
   - `fetch_fan_reactions_from_yahoo()` が呼ばれた時、`fan_voice_pool` の存在は picker 挙動を **変えない**(出力 diff = 0)
   - RSSHub 503 / empty が一部 handle で発生しても、他 handle の fetch / 全体 publish 経路が止まらない
2. related unit tests
   - `tests/test_rss_fetcher*`
3. full suite
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- handle 一覧が curation 未確定の間は実装フェーズに進まない
- RSSHub fetch で 503 連発 / 半数以上の handle が empty なら 325 検討停止 → 別便で RSSHub 健全性調査
- picker 経路 / 記事 body / oEmbed 形式に変更が混入したら STOP
- X API plan 切替の必要が議論に上がったら STOP(user §11 判断境界)
- 既存 14 media handle の fetch 挙動が変わったら STOP
- 全件テスト green を満たせない場合 STOP

## 7. 禁止事項

- handle curation を Claude / Codex 側で勝手に増減しない
- 記事 body に `fan_voice_pool` を流し込まない(325 担当)
- X API 課金 plan に手を出さない
- scheduler / env / Cloud Run config を触らない
- 309-QA / 310-QA / 311-QA の picker ロジックを巻き込まない

## 8. 想定されるデグレ

- RSSHub Cloud Run の総 fetch 量増加で 503 率上昇(handle 数 × poll 頻度)
- handle が消えた / private 化した時の fetch error が他 source の fetch を巻き込む
- bucket 分離が media handle にも誤適用される(strict type 判定で防ぐ)

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-12 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |

## 10. Regression Memo欄

### current observation

- 現在の fan voice は Yahoo リアルタイム検索の語彙フィルタ依存で、別人 / bot / 別試合の混入が漏れることがある
- RSSHub は既に 14 media handle で稼働、追加 cost は微小

### guard hypothesis

- guard A: handle 確定 → 別人混入を 0 にできる
- guard B: 記事 body に流す前に source 健全性を観察したい(324 で source 分離、325 で picker 統合)
- guard C: X API 課金 plan には手を出さない、scrape 経路で完結する範囲のみ

## 11. 関連 ticket

- **325-QA-fan-voice-whitelist-rss-picker-integration**(本 ticket の後段、picker 統合、`ENABLE_FAN_VOICE_WHITELIST=0` 既定 off)
- 309-QA / 310-QA / 311-QA(X reaction 件数拡張、picker 中の挙動を触る、325 と scope 衝突しうるので順序に注意)
