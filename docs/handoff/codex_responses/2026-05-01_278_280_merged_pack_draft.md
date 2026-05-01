# 278-280 merged quality improvement Pack draft

Date: 2026-05-01 JST  
Lane: Codex A round 3 (doc-only)  
Scope: merged Pack draft only, no `src/` / `tests/` / env / gcloud / WP / scheduler mutation

## 1. 統合背景

- 既存の運用正本では、`docs/ops/OPS_BOARD.yaml` に `future_user_go.278-279-280-QA-deploy` があり、`next_action` は **`290 deploy + 24h + 統合 impl 完遂後に Pack`** で固定されている。
- 同じく `docs/ops/OPS_BOARD.yaml` の `autonomous_preparation.278-279-280-design-merge` は **`DOC_ONLY+BOARD_COMPRESSION`** で、note は **`283-MKT 配下子化、親 ticket 統合`** になっている。
- `docs/ops/CURRENT_STATE.md` でも `278/279/280 deploy` は **FUTURE_USER_GO** として保持され、提示 timing は **`290 deploy + 24h + 統合 impl 完遂`** に固定されている。
- `docs/ops/POLICY.md` §10 により、この品質改善群で新規 ticket を増やすのは非推奨で、**既存 ticket への追記と親 Pack 化を優先**するのが正道。
- user-facing merged scope は **title backfill / RT cleanup / mail subject-excerpt cleanup** の 3 本で、運用上は **親 ticket 1 + subtask 3** に畳むのが目的。
- そのため本 Pack は、**278 / 279 / 280 を別々に再起票せず、283-MKT 配下の quality child cluster として 1 親 + 3 phase に圧縮するための draft** として扱う。

### 番号正規化メモ(2026-05-01 時点)

- repo 実体の active docs は `277=title player-name backfill`, `278=RT cleanup`, `279=mail subject clarity`, `280=summary excerpt cleanup`, `290=weak title rescue`。
- 一方で user-facing merge 意図は **「title backfill / RT cleanup / mail subject-excerpt cleanup の 3 本を 1 Pack にする」** で一貫している。
- 本 draft ではこのズレを明示したうえで、**新規 ticket は作らず**、以下の 3 phase に正規化する:
  - **phase 1**: title backfill / weak-title rescue 補完(277/290 隣接領域、単独 ticket 増設しない)
  - **phase 2**: RT cleanup(278 実体)
  - **phase 3**: mail subject + summary/excerpt cleanup(279+280 bundle)

### deferred 条件

- 本 Pack は **即 fire しない**。
- 発火条件は **290 deploy 完了 + 24h 安定観察 + merged impl 完遂**。
- それ以前は `HOLD` のまま据え置く。

## 2. read-only 解析

### 2-1. phase 1(title backfill) と 290 の重複 / 補完関係

- `277-QA-title-player-name-backfill.md` は、**source title / body / summary / metadata から人名を補完できるなら補完し、無理なら `title_player_name_unresolved` を emit** する方針。
- `290-QA-weak-title-rescue-backfill.md` は、`src/rss_fetcher.py` の `_maybe_apply_weak_title_rescue(...)` で **`weak_subject_title:*` / `weak_generated_title:*` を env flag 付きで narrow rescue** する実装まで進んでいる。
- 290 の rescue は `src/weak_title_rescue.py` と `src/title_validator.py` を使う **後段 rescue** であり、`related_info_escape` / `blacklist_phrase` / `no_strong_marker` の限定救済に責務がある。
- したがって phase 1 を別 ticket として独立実装すると、**277/290 と title 系責務が三重化**しやすい。
- 正しい整理は、phase 1 を **「290 で意図的に救わなかった残差の補完 path」** とし、以下を守ること:
  - 290 の `is_weak_generated_title` / `is_weak_subject_title` 本体を再設計しない
  - 既存 `ENABLE_WEAK_TITLE_RESCUE` の意味を壊さない
  - `RT` / `off_field` / `promotion-first` のような **phase 2 側で処理すべき題材**を phase 1 に混ぜない
  - `publish_notice` 側の見え方問題を phase 1 に持ち込まない

### 2-2. phase 2(RT cleanup) の想定 logic path

- 現物 repo では、social source の一次整形は `src/rss_fetcher.py` の `_clean_social_entry_text(...)` に寄っている。
- `source_type == "social_news"` の entry はここで URL / hashtag / handle / 末尾媒体名を掃除されるが、**RT prefix 自体を意味的に正規化する責務はまだ弱い**。
- その後の title 生成は同じく `src/rss_fetcher.py` の `_rewrite_display_title_with_template(...)` で行われ、ここで:
  - `〜昇格・復帰 関連情報`
  - `〜コメント整理 ベンチ関連の発言ポイント`
  - `〜関連発言`
  といった generic / template-first なタイトルが作られる。
- 290 の rescue は **この後段**にぶら下がるので、RT cleanup を 290 に混ぜると責務が崩れる。
- read-only で見た限り、phase 2 の第一候補 path は以下:
  - `src/rss_fetcher.py` の `_clean_social_entry_text(...)`
  - `src/rss_fetcher.py` の social ingest block(`source_type == "social_news"`)
  - `src/rss_fetcher.py` の `_rewrite_display_title_with_template(...)`
- `doc/active/278-QA-rt-title-cleanup.md` が書いている `src/sns_topic_publish_bridge.py` は **pre-existing dirty** 指摘があるため、merged Pack でも **原則 fetcher 側だけで narrow に閉じる**のが安全。
- phase 2 の固有 risk は **WP front のタイトル面が直接変わること**で、mail だけの変更ではない。ゆえに scope を広げず、**RT prefix / goods/event head / non-Giants RT fallback** に限定すべき。

### 2-3. phase 3(mail subject + excerpt cleanup) の想定 logic path

- 現物 repo では、mail の classifier / subject / body は **`src/publish_notice_email_sender.py` に集中**している。
- subject 系の中核は:
  - `_classify_mail(...)`
  - `_subject_prefix_for_classification(...)`
  - `build_subject(...)`
- body / summary / excerpt 系の中核は:
  - `_format_next_action_line(...)`
  - `_format_summary_lines(...)`
  - `build_body_text(...)`
- `279-QA-mail-subject-clarity.md` と `280-QA-summary-excerpt-cleanup.md` が別 ticket になっていても、**実コードの ownership はほぼ同じ file / 同じ job**。
- そのため phase 3 は `279` と `280` を bundle して、
  - subject prefix の判別性改善
  - `summary: (なし)` / `summary_excerpt:` / review reason の具体化
  を **1 回の publish-notice 側 narrow 改修**として扱うのが最も自然。
- この bundle により:
  - rebuild 回数を増やさない
  - `MAIL_BUDGET` 観測を 1 phase に閉じる
  - subject と body の classification drift を防ぐ
  という利点がある。

## 3. 統合 impl 順序

### phase 1: title backfill(290 補完)

- 前提:
  - 290 deploy 済
  - 24h 安定観察済
  - rescue candidate の残差が read-only で確認できる
- 役割:
  - `277/290` で救いきれない **weak title 残差**だけを追加救済する
  - **新しい title engine は作らない**
  - 290 の guardrail / Gemini 0 増 / cache 不変を継承する
- 実装の狙い:
  - `weak_title_rescue` 不可な candidate の追加 path
  - review reason の明示補強
  - disappearance を増やさず、むしろ減らす方向
- deploy 面:
  - fetcher 側 build/deploy 1 回
  - rollback は env or image revert

### phase 2: RT cleanup(fetcher narrow)

- 前提:
  - phase 1 が安定
  - 290 / 277 の title path と責務分離ができている
- 役割:
  - RT prefix を落とす
  - goods / event / official X 断片を title 先頭で読みやすくする
  - 巨人無関係 RT は review / off_field fallback に流す
- scope 制約:
  - **WP front 大規模変動 risk** があるため narrow scope 固定
  - `publish_notice` 側は触らない
  - front plugin / category label / CSS 変更禁止
- deploy 面:
  - fetcher 側 build/deploy 1 回
  - rollback は image revert

### phase 3: mail subject cleanup + summary/excerpt cleanup

- 前提:
  - phase 2 までの title surface が安定
  - `MAIL_BUDGET` の phase 別定量予測が取れている
- 役割:
  - 件名だけで `publish / review / hold / old candidate / X suppress` を判別できるようにする
  - summary / excerpt を判断可能な形に整える
  - subject と body の理由表現をずらさない
- scope 制約:
  - `src/publish_notice_email_sender.py` 中心の bundle
  - Team Shiny From / dedup / SMTP / recipient 変更禁止
  - `MAIL_BUDGET` を必ず観測する
- deploy 面:
  - publish-notice 側 build/deploy 1 回
  - rollback は image revert

### 順序をこの並びにする理由

- phase 1 を先に置くことで、**290 が救えるもの / 救えないもの**の境界を明示できる。
- phase 2 は fetcher/title surface の narrow change で、mail routing を触らない。
- phase 3 は `MAIL_ROUTING_MAJOR` に該当しうるため最後に置き、`POLICY.md` §22 `MAIL_BUDGET` を phase 単位で監視できる形にする。

## 4. Acceptance Pack 18 項目 final draft

## Acceptance Pack: 278-279-280-QA-deploy

- **Decision**: `HOLD`
- **Requested user decision**: `278-280-MERGED` quality pack を phase 1(fetcher title 補完) → phase 2(RT cleanup) → phase 3(publish-notice subject/excerpt cleanup) の順で実装・deploy してよいか
- **Scope**:
  - phase 1: `277/290` 隣接の title backfill/rescue 補完、fetcher build/deploy 1 回
  - phase 2: RT cleanup の narrow fetcher fix、fetcher build/deploy 1 回
  - phase 3: `src/publish_notice_email_sender.py` 中心の subject + summary/excerpt cleanup、publish-notice build/deploy 1 回
  - 合計: **Cloud Build 1 回/phase**、max 3 phase
- **Not in scope**: Scheduler / Secret / Team Shiny From / SMTP / recipient / SEO / noindex / canonical / 301 / X 自動投稿 / live_update / new subtype / front plugin / `src/sns_topic_publish_bridge.py` cleanup / source 追加 / Gemini call site 追加
- **Why now**: 278 / 279 / 280 を別々に扱うと Pack・deploy・観測が分散し、`POLICY.md` §10 の「既存追記優先」に反する。283-MKT 配下の quality child cluster として 1 親 + 3 phase に圧縮してから進める方が、観測・rollback・user 判断の粒度が揃う
- **Preconditions**:
  - `290-QA` deploy 完了
  - `290-QA` deploy 後 **24h 安定**
  - merged impl(phase 1-3) 完遂
  - phase 3 の mail volume 増分を `POLICY.md` §22 `MAIL_BUDGET` 基準で定量化
  - 既存 silent skip / Team Shiny From / duplicate / cache の baseline が崩れていないこと
- **Cost impact**: Gemini call `0` 増、token `0` 増、**Cloud Build 1 回/phase**。mail emit は publish/review 可視化が改善する分だけ **微増** の可能性あり。特に phase 3 は `MAIL_BUDGET 30/h・100/d` の中で phase 別予測が必要
- **User-visible impact**: title の弱さ・RT 由来ノイズ・mail 件名/summary の読みにくさが段階的に改善する。phase 1/2 は candidate rescue と front title 品質、phase 3 は mail 判別性の改善が主
- **Rollback**:
  - phase 1: env rollback or fetcher image revert
  - phase 2: fetcher image revert
  - phase 3: publish-notice image revert
  - 原則として **phase 別 env or image revert** で戻せる形を維持する
- **Evidence**:
  - 事前 evidence:
    - `OPS_BOARD.yaml future_user_go.278-279-280-QA-deploy`
    - `OPS_BOARD.yaml autonomous_preparation.278-279-280-design-merge`
    - `CURRENT_STATE.md` FUTURE_USER_GO row
    - `283-MKT`, `277-QA`, `278-QA`, `279-QA`, `280-QA`, `290-QA` docs
    - 実体 path: `src/rss_fetcher.py`, `src/weak_title_rescue.py`, `src/title_validator.py`, `src/publish_notice_email_sender.py`
  - 完了時に必要な evidence:
    - phase ごとの tests green
    - phase ごとの deploy evidence
    - 24h 観測で silent skip 増加なし
    - `MAIL_BUDGET` violation なし
    - Team Shiny From 不変
- **Stop condition**: silent skip 増 / Gemini call delta `> 0` / Team Shiny From 変 / WP front 大規模変動 / `MAIL_BUDGET 30/h・100/d` 接近または violation
- **Expiry**: `290 deploy 後 24h`。その時点で merged impl が未完なら Pack refresh、phase 3 の定量予測が無い限り GO へ上げない
- **Recommended decision**: `HOLD`
- **Recommended reason**: 283 配下の統合方針と 3 phase 順序は固まったが、現時点では `290 deploy + 24h` が未達で、phase 3 の `MAIL_BUDGET` 定量も無い。今 GO にすると `MAIL_ROUTING_MAJOR` judgment を前倒ししすぎる
- **Gemini call increase**: `NO`
- **Token increase**: `NO`
- **Candidate disappearance risk**: `NO`(逆方向、disappearance 減少)
- **Cache impact**: `NO`
- **Mail volume impact**: `YES`(微増。phase 別の定量予測が必要)

User reply format: `GO` / `HOLD` / `REJECT` のみ

## 5. Claude next action

1. `docs/ops/OPS_BOARD.yaml` の `future_user_go.278-279-280-QA-deploy` 表記を、必要なら **`278-280-MERGED` 前提の 1 Pack 表現**へ寄せる。
2. `290 deploy + 24h 安定` 到達後に、この draft を basis に **user-facing Pack** を refresh する。
3. 実装 fire は phase 1 → phase 2 → phase 3 の順に 1 本ずつ切り、途中で `MAIL_BUDGET` / front title regression / silent skip を観測してから次に進む。
