# 045 — non-NPB collector wiring を 037 intake に接続する

**フェーズ：** 037 follow-up(pickup 接続)
**担当：** Codex A
**依存：** 028 impl accepted(c407415)、037 accepted(aac632c)、038 active(docs/handoff/ledger 運用開始済)

---

## why_now

- 037 は pickup contract / candidate_key / source_kind tracking / `deferred_pickup` route outcome まで runner 層に固めた。
- しかし `src/tools/run_notice_fixed_lane.py` の default fetch path は依然として NPB roster notice 1 本固定(`_fetch_latest_notice_candidate`)。
- このままでは 028 の 4 family(program_notice / transaction_notice / probable_pitcher / farm_result)と 037 の parity 5 family(lineup_notice / comment_notice / injury_notice / postgame_result / player_stat_update)は route だけ増えて live item が来ない。
- 結果として 037 の効果判定ができず、038 ledger が NPB 公示 1 件止まりになり observation が空転する。035 の判断材料も増えにくい。
- 観測を始める前に、**既存の local / repo 内 collector artifact** を 037 intake(`_normalize_intake_item` 以降の normalized intake item flow)に接続する follow-up を 1 本切る必要がある。
- なお 039 delivery は cron → log → mail → 着信の独立並走 ticket であり、045 の必要性には直接紐付けない。

## purpose

- `run_notice_fixed_lane` に NPB roster 直 fetch 以外の optional intake path を追加する。
- まず **fixed-lane family**(program_notice / probable_pitcher / farm_result)に実データが入る状態を作る。
- parity family(037 の 5 family)は artifact があるものだけ `deferred_pickup` で流せればよい。artifact が無い family は live 化しない。
- Draft 断定ルール(028 の T1 のみ)や pickup contract(037)は一切書き換えない。

## scope

### 入口(optional intake path)

- `run_notice_fixed_lane` に NPB 以外の intake 入口を追加する。
  - default no-arg 呼出は従来通り NPB roster fetch(不変)。
  - CLI flag または環境変数で **既存 local / repo 内 collector artifact**(normalized intake item の jsonl / json)を読み、normalized intake item flow(`_normalize_intake_item` 経路)に流す。
- artifact 形式は 037 の normalized intake item(candidate_key / subtype / source_bundle / trust tier / source_kind / lane_target 前提のフィールド)に準拠する。
- 新しい外部 fetcher / scraping / API client を書かない。**既存 artifact を読むだけ**。

### 優先順位

- 優先 family: **program_notice / probable_pitcher / farm_result**(fixed-lane 3 family)。
- parity 5 family は既存 artifact があるものだけ接続、無ければ deferred のままで構わない。
- `transaction_notice` は NPB roster fetch を既に持つので新規 wiring しない。

### route / duplicate contract

- 037 の `deferred_pickup` route outcome / candidate_key dedupe / source_bundle 吸収ロジックは書き換えない。呼び出すだけ。
- 028 の T1 assert narrow / 5 route outcome(fixed_primary / await_primary / duplicate_absorbed / ambiguous_subject / out_of_mvp_family)は書き換えない。呼び出すだけ。
- 親カテゴリ `読売ジャイアンツ` 維持(014/019 準拠)。

## non_goals

- 新しい外部 API 追加(X API / NPB 以外の web scraping / RSS 新規 fetcher)
- robots.txt / rate limit / 無料枠の新規判断が要る collector 追加
- default no-arg NPB roster fetch の挙動変更
- 041(structured eyecatch fallback)の実装
- push(12 commits DNS blocker)/ startup 配置 / DNS 解消
- X API 拡張 / SNS 文面自動生成
- AI lane 実装 / 新 source trust tier 追加
- automation.toml / scheduler / env / secret / mail / quality-gmail / quality-monitor / draft-body-editor の変更
- published 書込

## success_criteria

- NPB 以外の **1 family 以上**で `run_notice_fixed_lane` が live item を intake できる。
- fixed-lane family(program_notice / probable_pitcher / farm_result)で **1 件以上の Draft 生成** が観測できる。
- parity family は Draft を作らなくても `deferred_pickup` として route できる。
- 038 ledger が NPB 公示 1 件止まりにならない(2 件目以降の entry が発生する)。

## acceptance_check

- default NPB path(no-arg 実行)が壊れていない。
- injected / non-NPB intake path で fixed family の create path か parity family の deferred path が通る。
- duplicate key / route outcome / trust tier が 028 + 037 contract のまま(tests で観測)。
- external fetch を勝手に増やしていない(grep で新 API client / 新 scraper が無いこと)。
- tests 追加:
  - optional intake path から fixed-lane family の Draft が作られる
  - optional intake path から parity family が `deferred_pickup` として route される
  - default NPB path の既存 tests が引き続き pass

## TODO(起票時点)

【×】`run_notice_fixed_lane` に optional intake path(CLI flag or env)を追加する
【×】normalized intake item flow(`_normalize_intake_item` 経路)と 037 の route / duplicate contract を書き換えず呼び出すだけで intake する
【×】既存 local / repo 内 collector artifact の所在と形式を確認し、normalized intake item として読める最小 reader を書く
【×】優先 family(program_notice / probable_pitcher / farm_result)で 1 family 以上が intake できる状態にする
【×】default no-arg NPB roster fetch 挙動を不変に保つ
【×】新 external fetcher / scraper / API client を追加しない
【×】tests を追加し、optional intake path の fixed create / parity deferred / default NPB path pass を確認する
【×】038 ledger に 2 件目以降の entry が発生することを観測可能にする

## 成功条件

- 037 の open_question(non-NPB live collector wiring)がこの ticket で閉じる。
- 045 accepted 後、037 の効果判定 / 038 ledger の 2 件目以降蓄積 / 035 の判断材料確保が回せる(039 は独立並走、本便の射程外)。
- blanket go 範囲外(外部 API / robots / rate limit / 無料枠)に踏み込んでいない。

---

## 本便の scope 外(再掲、混線防止)

- 041 structured eyecatch fallback(Codex A 補助便、本便と独立)
- push 12 commits(DNS blocker、user 判断)
- 044 startup 登録 + reboot smoke(user 手元配置、隔離維持)
- 042 / 043(local runtime recovery 系、Claude 管理)
