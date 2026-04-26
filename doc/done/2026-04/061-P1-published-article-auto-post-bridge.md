# 061-P1 — published article auto-post bridge for official X(teaser + canonical URL only)

**フェーズ：** 061 自動投稿 gate 通過前の狭い先行自動化(published 記事通知のみ)
**担当：** Claude Code(contract owner、impl 時は Codex A or B)
**依存：** 060(公式 X tone / 061 gate)、064(fact / topic / reaction 3 tier)、065-B1(X 下書きメール bridge、本 ticket は別経路)、028 T1 trust tier、037 pickup parity、046 first wave、047 postgame revisit chain、041 eyecatch fallback
**状態：** CONTRACT DRAFT(doc-only、2026-04-23 起票、impl 便は本 contract accept 後)

**正本優先順位**: **tone / account split / Draft 期 bridge / 061 全面 gate は 060 を優先**。本 ticket は 060 の manual 運用を上書きせず、**published 記事通知だけ先行自動化する狭い path** を固定する。061 全面(試合 state 系 7 項目)は gate 4 条件まで止め続ける。061-P1 と 061 は別 lane として共存する。

---

## why_now

- user 意図: 「**公開したものは自動ポスト**」。published article の canonical URL + teaser 短文は「事実かつ既公開」で事故リスクが最も低いため、061 全面 gate を待たずに先行自動化してよい。
- 060 manual 運用 + 065-B1 手動メール下書きを毎回 user が手で流す構造は relay 役を増やす。user を relay にしないため、狭い自動化を 1 本足す。
- 061 全面(lineup / fact / probable / postgame / trust comment / 試合中確定イベント / 試合の流れへの短い反応)は **試合 state ベース** の trigger で、published event ベースの本 ticket とは軸が違う。同じ ticket に混ぜると scope 肥大 + fact 短文 / 試合中速報の自動化を引き込む risk がある。**分離する**。
- MVP 公開条件 7(公開後の拡散導線)に直結、かつ 060 の「Draft URL 禁止」「私見禁止」を崩さない範囲で閉じる。

## purpose

- **published 記事の canonical URL + teaser 短文だけ**を公式 X に自動ポストする狭い bridge を固定する
- teaser は **fact first + 軽い熱量**(060 公式声)、**私見禁止**、**誇張禁止**、**click-bait 禁止**
- hard fail 条件で Draft / preview / private URL の流出を structural に止める
- 実装 phase を pure Python / dry-run / 外部接続の 3 段に分けて、autonomous 範囲と user 判断範囲を分離する

## 0. 061 全面との分離線

| 軸 | 061 全面 | 061-P1 |
|---|---|---|
| trigger | 試合 state(lineup / probable / postgame / 確定イベント 等) | WordPress publish event(post_status → publish) |
| payload | 事実短文(60-120 字) | teaser 短文 + canonical URL |
| source 区分 | fact source + 強いコメント | **published 記事本体**(既に fact 断定済) |
| gate | 060 gate 4 条件 | **本 P1 専用 gate**(後述) |
| 優先度 | 高(ただし gate 待ち) | 中(published 量に比例) |
| fire タイミング | gate 4 条件通過後 | user 明示 go 後、P1 gate 単独判定 |
| 試合中 | fact 短文 / 試合中速報 自動化 | **対象外**(fact 短文 / 試合中速報は引き続き手動) |

061-P1 が 061 全面に吸収されることはない。公開後も別 lane として共存し、published event path と試合 state path を分けて管理する。

## 1. scope(対象 / 非対象)

### 対象
- `post_status = publish` のヨシラバー記事
- canonical URL(`https://<site>/<slug>/` 等、WordPress の permalink)が取得可能なもの
- 記事本体の title + 第一段落 or excerpt field から teaser 生成可能なもの
- fixed lane 経由で生成された published 記事(自動 pipeline 経由で品質ゲートを通過したもの)

### 非対象(本 ticket scope 外、禁止)
- **fact 短文 自動化**(引き続き 060 手動運用 + 061 全面 gate 待ち)
- **試合中速報 自動化**(引き続き 060 手動 + 061 全面 gate 待ち)
- **中の人 X 自動化**(060 で手動 only 明記、本 ticket でも非対象)
- **自動返信 / リプライ生成**(060 / 061 いずれの scope 外)
- **draft / preview / private URL の送出**(hard fail)
- **teaser 内 LLM 私見 / 煽り / 誇張**(060 公式声違反)
- **065-B1 mail 下書き経路の置換**(並走経路として残す、065-B1 は news 系 6 類型の人力レビュー用、本 ticket は published event の自動化)

### adjacent(本 ticket で触らない既存 path)
- 065-B1 mail 下書き(human-review 前提、対象 = news 系 6 類型)
- 060 manual X 運用(user 手元操作、対象 = primary trust fact 短 post)
- 061 全面解放(gate 4 条件まで止め)

## 2. teaser 生成ルール(deterministic / LLM 不使用)

teaser は **published 記事の title + 第一段落** から deterministic に抽出する。LLM を呼ばない(060 私見禁止 / 067 generic title 禁止 / 040 bounded repair 思想の延長)。

### 2.1 入力
- `title: str`(WP `post_title`)
- `excerpt: str`(WP `post_excerpt`、空なら第一段落を抽出)
- `canonical_url: str`(WP permalink)
- `published_at: datetime`
- `article_id: int`

### 2.2 生成 step(順番固定)
1. **excerpt 優先**: WP `post_excerpt` が空でなく 40-120 chars なら excerpt を teaser 候補に採用
2. **第一段落 fallback**: excerpt が空または閾値外なら、記事本文から第一段落(最初の `<p>...</p>`)を抽出、text 化 → 40-120 chars に trim
3. **title only fallback**: 第一段落も抽出失敗なら、title をそのまま teaser に採用(ただし全体 post が title + URL だけの最短形になる)
4. **post 組立**: `{teaser}\n{canonical_url}` の 2 行 or `{teaser} {canonical_url}` の 1 行(どちらか 1 形を contract に固定、推奨は 2 行)

### 2.3 文字数 constraint
- teaser 単体: 40-120 chars(半角 140 chars 目安、日本語全角で teaser 部 40-60 字程度)
- 全体 post(teaser + 改行 + URL): **140 chars 以内**(X の legacy 字数制限を意識して安全側。t.co URL 短縮考慮で実用 180 chars 上限でも良いが、teaser 部は 120 chars で止める)

### 2.4 禁止語 / 禁止表現(hard fail で post skip)
- 060 公式声違反語: 「どう見る」「本音」「思い」「語る」「コメントまとめ」「試合後コメント」「ドラ1コンビ」「X をどう見る」「X がコメント」「X について語る」「注目したい」「振り返りたい」「コメントに注目」「コメントから見えるもの」「選手コメントを読む」(067 禁止語リストと同期)
- 誇張語: 「史上最高」「圧倒的」「神」「ヤバい」「優勝確定」「間違いなく」「断言」
- 未確認断定語: 「〜と判明」「〜が決定」「〜が確定」で source が published 記事本体でない場合
- 煽り疑問形: 「〜か?」「〜なのか?」「〜とは?」で記事本体に結論が明示されていない場合

### 2.5 teaser 生成の acceptance
- 80% 以上の published 記事で excerpt path で生成成功
- 残りも第一段落 or title fallback で生成成功(失敗は hard fail)
- 禁止語 hit は 0 件(published 記事自体が 067 / 068 / 040 を通過している前提、入口で再 validate)

## 3. hard fail 条件(post skip)

以下に該当する場合、**post を emit しない**(silent skip + ledger 1 行ログ)。

1. `post_status != publish`
2. `canonical_url` が空 / None
3. `canonical_url` に `?preview=` / `?p=` without published / `_private` / `/draft/` / 非 https / 社内ドメイン のいずれか
4. teaser 生成が 2.2 step 全て失敗
5. teaser に 2.4 禁止語 hit
6. teaser が 2.3 文字数 constraint を外れる(120 chars 超 / 10 chars 未満)
7. `published_at` が現在時刻より未来 / 2 年以上前(schedule ミス防止)
8. 同一 `article_id` で直近 24h 以内に post 履歴あり(duplicate guard)

hard fail 時は **silent skip** し、skip 理由を ledger / stdout に 1 行記録。エラー throw はしない(pipeline stop を避ける)。

## 4. 060 / 064 / 061 / 065-B1 接続境界

### 060(公式 X tone / Draft 期 bridge)
- **継承**: 「事実 first + 軽い熱量」「Draft URL 禁止」「私見禁止」「primary trust のみ」
- **非抵触**: 060 は Draft 期 manual 運用を contract 化、本 ticket は published event の自動化 → 異なる phase / trigger なので競合しない
- **gate 継承**: 060 manual review 20 件 red 0 件 観測済 を本 ticket の gate 条件に **引き継ぐ**(必須)

### 064(fact / topic / reaction 3 tier)
- **継承**: published 記事本体は既に fixed lane or repair playbook を通過した「fact 断定済」の content
- **validator**: teaser 生成結果が fact tier 以外(topic / reaction 由来の断定語)を含まないか、入口で再 validate
- **非目標**: 064 tier 判定を本 ticket で拡張しない

### 061 全面
- **分離**: 061-P1(published event path)と 061(試合 state path)は別 lane、独立 fire / 独立 gate
- **非吸収**: 061-P1 が成功しても 061 全面は 4 条件 gate を継続
- **scope 重複**: postgame_result の published 記事は 061-P1 対象(canonical URL あり)、同じ試合の試合中速報は 061 全面対象(gate 待ち)。軸が違うので重複しない

### 065-B1(X 下書きメール)
- **並走**: 065-B1 = news 系 6 類型の手動レビュー用 mail 下書き(runtime resume 後 fire 予定)、本 ticket = published event 自動化
- **teaser ルール共有**: 本 ticket の teaser generator は 065-B1 の `official_draft` 生成ルールを参照 / 流用可(同じ公式声 contract に揃える)
- **非置換**: 065-B1 は published 前 news item の下書き、本 ticket は published 後の post、タイミングが違う

## 5. 実装 phase 分解(autonomous 範囲と user 判断範囲の分離)

### P1.0 — contract 起票(本 doc)
- owner: Claude Code
- status: **本 turn で着地**(本 doc、2026-04-23 起票)
- user 確認: **不要**(user 明示 go で 061-P1 ticket 化指示済み)

### P1.1 — pure Python impl + teaser generator + validator + dry-run CLI
- owner: Codex A or B(impl 時)
- scope:
  - `src/x_published_poster.py`(新規、pure Python、stdlib only、外部 API 非接続)
    - `generate_teaser(article: PublishedArticle) -> str | None`(deterministic、LLM 不使用)
    - `validate_post(article, teaser, canonical_url) -> ValidationResult`(hard fail 8 条件)
    - `build_post(article) -> PostPayload | None`(組立、hard fail 時 None)
  - `src/tools/run_x_published_poster_dry_run.py`(新規、CLI、stdout で post 候補を 5 件表示、mail / X API 送信なし)
  - `tests/test_x_published_poster.py`(新規、teaser 生成 + validator + skip 条件 + 禁止語 + 文字数)
- 不可触:
  - src/x_post_generator.py(既存 manual path、060 手動運用)
  - src/run_notice_fixed_lane.py(route 層)
  - src/postgame_revisit_chain.py / src/first_wave_promotion.py / src/source_trust.py / src/source_id.py / src/game_id.py
  - src/eyecatch_fallback.py / src/repair_playbook.py / src/fact_conflict_guard.py
  - automation.toml / scheduler / secret / env / X API credentials
  - 060 / 061 / 064 / 065 / 067 / 068 contract doc
  - WP published 書込(本 ticket は read-only、WP からの event / post data 取得のみ)
  - 中の人 X / 自動返信 / fact 短文 / 試合中速報 の path
- autonomous fire: **可**(pure Python / tests で閉じる / 外部接続なし / 新規 dep 不要 / published 書込なし)
- §31-C 一体化: doc 参照 + src + tests を 1 commit

### P1.2 — WordPress publish event trigger / scheduler integration
- owner: Codex A or B(impl 時)
- scope:
  - publish event 取得経路(WP webhook / scheduler scan / post_status transition hook のいずれか)
  - automation.toml に lane 追加 or scheduler entry 追加
  - dry-run から live emit への切替(ただし X API は P1.3 まで接続しない、mail / file dump で観測)
- autonomous fire: **不可**(**automation.toml / scheduler 変更 = user 判断 8 類型**)

### P1.3 — X API credentials / live post
- owner: Codex A or B(impl 時)
- scope:
  - X API credentials(OAuth / Bearer token)
  - live post emit
  - rate limit / quota / error handling
- autonomous fire: **不可**(**secret / env / API key / 外部費用 = user 判断 8 類型**)

## 6. P1-gate(P1.1 impl fire 前提 / P1.2 進行前提)

### P1.1 dry-run 実装 fire 前提
- 本 doc(061-P1)が Claude accept 済
- Codex A / B のいずれかに空き(local 未 push ≤ 4 本)
- test suite green(現在 809/0)

### P1.2 trigger 実装(automation.toml / scheduler 変更)前提 — **user 判断**
1. P1.1 dry-run stdout で **10 件以上** の published article に対して teaser 生成成功 + hard fail validator 全 pass
2. 060 manual review **20 件 red 0 件** 観測済(060 継承 gate、必須)
3. published 週 **10+ が 2 週連続**(061 全面 gate と同条件、published 量の担保)
4. 事故 0 件 2 週(061 全面 gate と同条件)

### P1.3 live post 実行前提 — **user 判断**
- P1.2 dry-run tick 経由で **100 件以上** emit 成功(mail / file dump 観測)
- X API credentials 発行 / cost 見積(user 判断)
- user 明示 go

## 7. accept 5 点(P1.1 impl 便時)

1. **着地**: `src/x_published_poster.py` + `src/tools/run_x_published_poster_dry_run.py` + `tests/test_x_published_poster.py` の 3 file が新規、doc/061-P1 への参照 commit、他 file 差分 0
2. **挙動**: teaser 生成 pass(excerpt / 第一段落 / title fallback の 3 path)/ hard fail 8 条件全 test pass / 禁止語 hit reject / 文字数 constraint pass / dry-run CLI stdout に 5 件以上 post 候補表示 / 既存 suite 809 passed → 820+ passed
3. **境界**: 不可触 list 全 diff 0(x_post_generator.py / run_notice_fixed_lane.py / route 層 / source_* / game_id / automation.toml / secret / 060 / 064 / 065 / 067 / 068 contract)
4. **安全**: WP published 書込なし、X API 接続なし、mail 送信なし、secret 読取なし
5. **doc 整合**: 本 doc / 060 / 064 / 065 の tone 継承、私見語 / 煽り語 / 誇張語 の入口 validator が機能、Draft / preview / private URL の hard fail が機能

## 8. 非目標(本 ticket では絶対にやらない)

- X API 直接実装(P1.3 で別)
- WordPress webhook / scheduler 変更(P1.2 で別、user 判断)
- 中の人 X 自動化
- fact 短文 自動化(061 全面 gate 待ち)
- 試合中速報 自動化(061 全面 gate 待ち)
- 自動返信 / リプライ / エンゲージメント生成
- teaser の LLM 生成(deterministic 固定)
- teaser A/B test / 新規 analytics 実装(scope 外)
- user 手元判断を増やす運用(relay 増加 = 禁止)

## 9. 不可触(§31-B、毎 prompt 明示)

- `src/x_post_generator.py`(既存 manual X post path、060 手動運用)
- `src/run_notice_fixed_lane.py` route 層 / `src/postgame_revisit_chain.py` / `src/first_wave_promotion.py`
- `src/source_trust.py` / `src/source_id.py` / `src/game_id.py`
- `src/eyecatch_fallback.py` / `src/repair_playbook.py` / `src/fact_conflict_guard.py`
- 065 / 067 / 068 validator 本体、040 repair playbook 本体
- `automation.toml` / scheduler / secret / env / X API credentials
- `doc/060` / `doc/061` / `doc/064` / `doc/065` / `doc/067` / `doc/068` contract 本体(本 doc 起票以外は touch 不可)
- WP published 書込 / WP DB 書込
- 中の人 X 経路 / 自動返信 経路 / fact 短文 経路 / 試合中速報 経路
- ambient untracked / modified(本 ticket 1 doc 新規 + P1.1 impl 3 file 新規以外に git add しない)

## 10. stop 条件(実装便中、本 ticket から外れる兆候)

- 不可触 file に diff 出そう
- X API / secret / credentials を読もうとする
- automation.toml / scheduler を touch しようとする
- LLM call が混入
- 060 / 064 contract を拡張 / 書換する必要が出る
- teaser で LLM 生成 / A/B test / 新規 analytics が必要になる
- fact 短文 / 試合中速報 / 中の人 X 経路が混入する
- 既存 test(067 / 068 / 041 / 046 等)が fail する
- published 書込 / WP 書込 が必要になる

## 11. open question(user 判断持ち越し、本 ticket accept 時に明示)

- Q1: P1.2 trigger 実装の取り方(WP webhook / scheduler scan / post_status transition hook の 3 候補、どれが user の WP / runtime 構成と親和するか)
- Q2: teaser 1 行 / 2 行のどちらを最終固定にするか(推奨 2 行: teaser\ncanonical_url、ただし X 側 preview card の寄せ方で検討可)
- Q3: P1.2 以降の live emit 先(mail / file dump / X API)で、observability をどこに寄せるか(039 quality-gmail 相乗 or 070 ops secretary 相乗)

Q1-Q3 は本 doc accept 時 / P1.2 fire 時に決着。P1.1 dry-run 段階では不要。

---

## meta

- last_updated: `2026-04-23`
- version: `v0.1`(contract draft)
- 親 tickets: 060 / 061 / 064 / 065-B1
- 子 / 派生: P1.1(pure Python impl、autonomous 可)/ P1.2(trigger 接続、user 判断)/ P1.3(live X post、user 判断)
