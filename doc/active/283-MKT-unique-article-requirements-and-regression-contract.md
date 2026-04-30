# 283-MKT-unique-article-requirements-and-regression-contract

| field | value |
|---|---|
| ticket_id | 283-MKT-unique-article-requirements-and-regression-contract |
| priority | P1 (個性的記事の土台、既存テンプレ崩さず定義) |
| status | DESIGN_ONLY (実装なし、要件定義のみ) |
| owner | Claude(管理 / 要件定義) |
| lane | MKT |
| ready_for | user 確認 → 必要なら 284-287-MKT 子 ticket 起票 |
| blocked_by | (なし) |
| doc_path | doc/active/283-MKT-unique-article-requirements-and-regression-contract.md |
| created | 2026-04-30 |

## 結論

YOSHILOVER は **大手スポーツ紙の後追いではなく、巨人ファンが毎日見たくなる小さな変化を拾うサイト**として位置付ける。
本 ticket は **要件定義のみ**(実装・deploy・Gemini call 増・新 subtype 追加 全禁止)。

直近のデグレ群(publish 停止 / mail 停止 / backlog_only 過剰 hold / subtype 不明 / Gemini 再生成コスト増 / タイトル人名抜け / RT 始まり / CI 赤)を踏まえ、**既存テンプレを崩さない範囲**で個性的記事を増やす土台を定義する。

## 1. 現行テンプレ一覧

### strict template(`src/fixed_lane_prompt_builder.py`、5 種)

| key | subtype | title 例 | validator_subtype |
|---|---|---|---|
| `program` | program | `[番組名]「[内容]」([日付][時刻]放送)` | fact_notice |
| `notice` | notice | `巨人、[選手名]を[対象]に[事象]` | fact_notice |
| `probable_starter` | probable_starter | `4月X日(曜)の予告先発が発表される！！！` | pregame |
| `farm_result` | farm_result | `巨人二軍 [選手名]、[事象]！！！` | farm |
| `postgame` | postgame | `巨人・[選手名]、[事象]！！！` | postgame |

各 contract: `title_template` / `required_blocks` / `title_body_coherence` / `abstract_lead_ban` / `fallback_copy` を持つ → **既存テンプレを崩さない土台**。

### rule-based(strict 外、live)subtype 一覧(`x_post_generator.py` `VALID_ARTICLE_SUBTYPES` + 派生)

`pregame / postgame / lineup / manager / notice / recovery / farm / farm_lineup / social / player / live_update / general` + 派生(`comment / speech / manager_comment / player_comment / coach_comment / roster / injury / registration / player_notice / player_recovery / farm_feature / fact_notice / game_result / off_field / default / other`)

### 不変方針

- 新 subtype 追加 **絶対禁止**(本 ticket 内 + 子 ticket 全部)
- `VALID_ARTICLE_SUBTYPES` set / strict 5 contract text / `validator_subtype` mapping 全部不変
- 既存 rule-based path も挙動不変

## 2. subtype × template_key × article_angle 対応表

`article_angle` / `topic_angle` は明示構造体としては存在せず、**subtype + body slot** で実質表現。

| subtype | strict template? | backlog 取扱(現行) | 主用途 / 想定 angle |
|---|---|---|---|
| `lineup` | NO(rule-based) | BLOCKED | 一軍スタメン速報 |
| `farm_lineup` | NO | BLOCKED | 二軍スタメン |
| `pregame` | NO | BLOCKED | 試合前情報 |
| `probable_starter` | YES | BLOCKED | 予告先発 |
| `postgame` | YES | ALLOWLIST(game_context) | 試合後・選手 |
| `farm_result` | YES | 24h cap ALLOWLIST(281-QA で追加) | 二軍試合結果 |
| `notice` / `roster` / `registration` / `injury` / `recovery` / `player_notice` / `player_recovery` | notice strict / others rule-based | ALLOWLIST(game_context) | 公示・登録・復帰 |
| `program` | YES | ALLOWLIST(quote_comment) | 番組出演 |
| `manager` / `comment` / `speech` / `off_field` / `farm_feature` | NO(rule-based) | ALLOWLIST(quote_comment) | コメント・小ネタ・グッズ |
| `default` / `other` | NO | UNRESOLVED 24h cap | 分類不能 |
| `live_update` | NO | OFF(env=0) | 試合中実況(disabled) |
| `social` | NO | (未整理) | X/5ch 候補 lane の流用候補 |
| `general` | NO | (未整理) | フォールバック汎用 |

## 3. マニアック記事候補を既存テンプレに載せる案(新 subtype なし)

| 記事型(user 希望) | 既存 subtype 流用 | template | publish 経路 | 注意 |
|---|---|---|---|---|
| 二軍スタメン | `farm_lineup` | rule-based | fresh のみ publish | backlog BLOCKED 維持 |
| 二軍試合結果 | `farm_result` | strict | 24h cap allowlist(281-QA) | placeholder hard_stop 維持 |
| 若手/復帰組ウォッチ | `recovery` / `player_recovery` | rule-based | ALLOWLIST、backlog で出る | speaker・選手名取得必須 |
| 一軍起用変化 | `lineup` / `manager` | rule-based | fresh のみ | backlog BLOCKED 維持、混線禁止 |
| 守備位置変更 | `lineup` / `comment` | rule-based | fresh / コメント引用なら quote_comment 流入 | 数字捏造禁止 |
| 打順変更 | `lineup` / `comment` | rule-based | fresh / コメント版 | 同上 |
| ベンチ入り/外 | `roster` / `notice` | notice strict | ALLOWLIST、backlog で出る | 公式 anchor 必須 |
| 監督・コーチ・選手コメント小ネタ | `manager` / `comment` / `speech` | rule-based | ALLOWLIST、backlog で出る | speaker 必須、273-QA 統制 |
| 番組出演 | `program` ← **user 最優先要件** | program strict | ALLOWLIST、backlog で出る | 286-MKT で個別 audit 推奨 |
| 公式動画/テレビ発言メモ | `notice` / `manager` / `speech` | strict / rule-based | source_kind=official_video の trust 整理 | 動画タイムスタンプ取り扱い |
| 登録/抹消・一軍昇格 | `registration` / `roster` / `notice` | notice strict | ALLOWLIST | 球団発表 anchor 必須 |
| 怪我/復帰(安全表現厳格) | `injury` / `recovery` / `player_recovery` | notice strict / rule-based | ALLOWLIST + 266-QA hard_stop | 死亡/重傷 token は hard_stop trip |
| X/5ch 話題候補 | `social` 流用検討(記事化しない、候補通知のみ) | **テンプレ不使用** | publish しない、別 mail lane で候補通知 | 284-MKT design ticket |
| グッズ/イベント | `off_field` | rule-based | 現状 publish | **本フェーズ優先しない**(現状把握のみ、278-QA で title 整形) |

**結論**: 13 記事型のうち **新 subtype 追加 0、既存 subtype + 既存テンプレ範囲で全部対応可能**。

## 4. X/5ch 話題検知の安全な扱い

### 現状(audit 確認済)
- 5ch / 2ch source は **src 内に存在しない**(`grep src/ → 0 hits`)
- X 由来は公式・記者系を「事実 source」として既に使用
- viral_topic_detector(`src/viral_topic_detector.py`)は 246 ticket で HOLD/design_only
- `social` subtype は VALID 内、現状活用方針未確定

### 設計指針(本 ticket は実装しない)
- X/5ch 由来 keyword は **候補 list** として収集(設計のみ、284-MKT で着手判断)
- 出力は **記事 draft ではなく**、user 用 review mail のみ
- Gemini 呼び出し **禁止**(282-COST preflight gate `unofficial_source_only` skip 適用)
- subtype は `social`(既存)流用、新 subtype 追加禁止
- 公式・スポーツ紙確認が **追って取れた時のみ** 別 source path で記事化候補に格上げ

### 安全 condition
- **publish しない**(`unofficial_source_only` で skip / review)
- **本文化しない**(LLM 呼び出し禁止、source 不足のため)
- **断定しない**(候補通知の表現は「話題候補」と分かる文体、事実扱いしない)
- **噂・怪我・家庭・移籍などの未確認情報は記事化しない**

## 5. Gemini を呼ぶ / 呼ばない条件(282-COST 反映後の整理)

### 呼ぶ(記事化対象)
- 一軍スタメン(`lineup` fresh)
- 二軍スタメン fresh(`farm_lineup` fresh)
- 二軍試合結果 24h 以内(`farm_result` + age cap)
- 試合結果(`postgame`)
- 監督/コーチ/選手コメント(`manager`/`comment`/`speech` + speaker 取得済)
- 登録/抹消(`registration`/`roster`/`notice`)
- 怪我/復帰(`injury`/`recovery`/`player_recovery` + hard_stop 通過後)
- 若手/復帰組ウォッチ(`recovery`/`player_recovery`)
- 番組出演(`program`)
- 公式 X / 球団公式 / スポーツ紙 / 公式動画 / テレビ発言で **巨人関連明確** な source

### 呼ばない(282-COST preflight skip 対象)
- 完全重複(`existing_publish_same_source_url`)
- source_url_hash / content_hash 既処理(229-COST cache_hit)
- 巨人関係弱い(`not_giants_related`)
- live_update 対象(`live_update_target_disabled`、env=0)
- 古すぎる backlog(allowlist 外 + age 超 / `farm_lineup_backlog_blocked` / `farm_result_age_exceeded`)
- placeholder body(`placeholder_body`)
- hard_stop 予定の危険系(`expected_hard_stop_death_or_grave`)
- X/5ch 単独 + 公式裏取り無し(`unofficial_source_only`)
- review/hold 通知だけで足りる(候補 list lane、本文不要)
- default/other で記事化根拠弱い

## 6. publish / review / hold 条件

### publish 条件(全部 AND)
- 巨人関連 token 明確
- source = 公式 / 球団公式 / スポーツ紙 / 公式 X / 記者 X / 公式動画 / テレビ発言 のいずれか
- 選手名 / チーム / 日付 / 試合 / 一軍/二軍 が混線していない
- 事実確認可能(score / opponent / decisive_event 等の slot 充足)
- noindex 維持下の品質検証として公開可能(SEO 解放はしない)
- publish mail 飛ぶ(267-QA notification 維持)
- hard_stop 該当しない
- 完全重複ではない(263-QA 維持)

### review に回す条件(候補は残すが要確認 mail)
- 人名取れない(`title_player_name_unresolved`、277-QA)
- 一軍/二軍曖昧
- source 弱い(T1 anchor 不足)
- X/5ch 起点で公式裏取り未完了
- title 弱い(generic noun head、278-QA で改善予定)
- summary 薄い(280-QA で改善予定)
- 事実非危険だが人間確認必要
- subtype 不明 + age 24h 以内(273-QA UNRESOLVED window)

### hold 条件(出さない、reason 必須 emit)
- 死亡 / 重傷 / 救急搬送 / 意識不明(266-QA hard_stop)
- 明確な事実ミス疑い(244-numeric guard / 234-impl-7 score fabrication)
- スコア矛盾(`hard_stop_win_loss_score_conflict`)
- 一軍/二軍混線(混線 fixture で publish しない)
- 巨人無関係(`not_giants_related`)
- 完全重複(263-QA same_source_url)
- live_update 対象(env=0 で全部 hold)
- 古すぎる backlog(allowlist 外 / age 超)
- 噂を裏取りなしに事実化
- X/5ch 単独で危険情報含む

## 7. 必須デグレ試験一覧(子 ticket 全部に共通契約)

### 7-1. 既存テンプレ不変
- [ ] strict 5 template の `title_template` / `required_blocks` / `fallback_copy` 不変 assert(diff text 比較)
- [ ] `VALID_ARTICLE_SUBTYPES` set 不変(新 subtype 追加なし assert)
- [ ] rule-based subtype path(lineup / manager / comment 等)挙動不変 fixture

### 7-2. publish/mail 不停止
- [ ] publish 対象 → publish or review 通知 fixture
- [ ] publish → publish mail 到達 fixture(post_id 一致)
- [ ] review/hold → review/hold mail 到達 fixture(267-QA 維持)
- [ ] silent draft / silent backlog / silent hold = 0(reason 必須 emit)
- [ ] 通知対象 0 時に理由 log 出る

### 7-3. Gemini call 増禁止
- [ ] Gemini stub 呼出回数 baseline 比較、増えたら fail
- [ ] 同 source_url / content_hash 再生成 0(229-COST cache_hit 維持、75% 前後)
- [ ] 282-COST preflight gate と競合せず(skip / cache_hit / cache_miss / call_made の 4 状態 log 区別)
- [ ] X/5ch 候補検知 path で Gemini 呼ばない fixture

### 7-4. 事実安全
- [ ] スコア矛盾 fixture → publish しない(hard_stop_win_loss_score_conflict)
- [ ] 一軍/二軍混線 fixture → publish しない
- [ ] 選手名ミス fixture → review 経路 or fail
- [ ] 死亡/重傷/救急搬送/意識不明 token fixture → hard_stop trip
- [ ] duplicate guard 維持(263-QA 解除しない)
- [ ] same_source_url 完全解除しない

### 7-5. タイトル品質
- [ ] 「選手」「投手」「チーム」だけの title fixture → backfill 試行 or review reason emit(277-QA)
- [ ] 人名取れる場合 title 補完 fixture
- [ ] RT 始まり title fixture → 整形 or review(278-QA、本 ticket scope 外で別便)
- [ ] 「コメント整理」「関連情報」だけ fixture → review reason emit
- [ ] 補完できない場合捏造禁止(`feedback_no_degradation_role_assignment` 準拠)

### 7-6. メール通知
- [ ] publish 通知届く fixture
- [ ] review/hold 通知届く fixture
- [ ] 古い候補通知届く fixture
- [ ] **Team Shiny / y.sebata@shiny-lab.org 系 From 維持**(env 不変 assert)
- [ ] From / To 変更しない
- [ ] GitHub noreply 通知巻き込まない(subject 「| YOSHILOVER」固有 token assert)

### 7-7. 禁止事項 diff assert
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] live_update ON 化なし
- [ ] SEO/noindex/canonical/301 token 不在
- [ ] X 自動投稿 path 不変
- [ ] Team Shiny From 不変
- [ ] Scheduler 頻度変更なし
- [ ] duplicate guard 全解除しない
- [ ] default/other 無制限公開しない
- [ ] 新 subtype 追加なし

### 7-8. X/5ch 安全
- [ ] X/5ch 単独 source fixture → publish しない
- [ ] 未確認情報 fixture → 本文に書かない(source/meta にない token 不在 assert)
- [ ] 話題候補 mail の表現が「話題候補」と判別可能(subject prefix で識別)
- [ ] 噂/怪我/家庭/移籍の未確認情報 fixture → 記事化しない

## 8. user GO 必須になる危険変更(本 ticket では発生しない、子 ticket で出る可能性)

| 変更 | GO 必須 reason |
|---|---|
| 新 subtype 追加 | VALID_ARTICLE_SUBTYPES 拡張は影響大、絶対 user 判断 |
| live_update / ENABLE_LIVE_UPDATE_ARTICLES=1 | 試合中実況解禁、運用負荷大 |
| SEO / noindex 解放 / canonical / 301 | 公開影響大、フェーズ変更 |
| X 自動投稿 ON | 法務 / 著作権境界 |
| duplicate guard 全解除 | 重複公開 risk |
| default/other 無制限公開 | 品質低下 risk |
| Scheduler 頻度変更 | コスト + 負荷影響 |
| Team Shiny From 変更 | mail 受信側設定影響 |
| Gemini call 増加(prompt 拡張等) | コスト増 |
| X/5ch 話題候補を **記事化** に格上げ | 事実 source 格付け変更 |
| マニアック記事「最優先」確定 | user 判断、AI が決めない |

## 9. Codex へ切る場合のチケット案(全部 design only から開始、impl は別 fire)

| ticket | scope | priority | impl 必要か |
|---|---|---|---|
| **284-MKT-topic-candidate-detection-design** | X/5ch 話題候補検知の設計 docのみ。記事化しない、別 mail lane 設計、social subtype 流用可否整理 | P2 | NO(design のみ) |
| **285-MKT-template-angle-mapping** | 既存 subtype + template_key + article_angle 的な整理を doc 化、新 subtype 追加なし | P2 | NO(design のみ) |
| **286-MKT-program-article-lane** | program(番組出演)の現行 backlog 動作 audit + 必要なら narrow 調整。strict template `program` 不変 | P1 | YES(impl narrow) |
| **287-MKT-farm-and-young-player-watch** | 二軍 / 若手 / 復帰組ウォッチの運用設計、既存 recovery/player_recovery/farm_feature 流用、281-QA 効果測定込み | P1 | NO(運用設計、impl は派生 ticket で) |

各子 ticket fire 条件:
- 283-MKT(本 ticket)を user が確認
- 必要な ticket だけ起票(「全部切る」は禁止、user judgment で選別)
- 各 ticket は 7-1 〜 7-8 のデグレ試験を継承

## 10. 最小実装単位(子 ticket impl 想定、本 ticket は実装なし)

各子 ticket の impl 想定:

- **284-MKT**: src 変更 0、doc のみ → 実装フェーズで別便(`src/topic_candidate_detector.py` 新規 + 別 mail lane 設計)
- **285-MKT**: src 変更 0、doc のみ → mapping 表として doc 化
- **286-MKT**: 既存 `src/guarded_publish_runner.py` の program subtype が ALLOWLIST(quote_comment)既登録、確認のみで src 変更 0 の可能性。必要なら age 調整 narrow
- **287-MKT**: 281-QA + 277-QA の運用観察、運用 doc + KPI 設計、src 変更 0

= **多くの user 希望機能は doc-only で土台が組める**。impl が出るのは実際に narrow 調整が必要と判定したときだけ。

## 11. deploy 要否

- **本 ticket(283-MKT)**: deploy なし(doc only、src 変更 0)
- **284-MKT**: deploy なし(design only)
- **285-MKT**: deploy なし(mapping doc)
- **286-MKT**: 必要なら guarded-publish image rebuild + job update(別 fire、user GO 後)
- **287-MKT**: deploy なし(運用設計)

deploy が出るのは impl 派生 ticket のみ、いずれも user 明示 GO 後。

## 12. rollback 条件

- 本 ticket(283-MKT)は doc only、rollback = `git revert` で即時可
- 子 ticket の rollback は ticket 内で個別定義
- 共通方針:
  - env flag を新設するなら default OFF + flag toggle で rollback 簡素化(282-COST pattern 参考)
  - image rebuild 後の rollback は前 image tag 戻し
  - duplicate guard / hard_stop / live_update / Team Shiny From は **絶対** 触らない

## 完了条件(本 ticket)

1. user が本 ticket(`doc/active/283-MKT-*.md`)を確認
2. 子 ticket(284-287)のうち必要なものを user 判断で選別 + 起票
3. 各子 ticket は本 ticket の 7-1 〜 7-8 デグレ試験を継承
4. 実装 fire は子 ticket 単位、本 ticket では発生しない
5. 新 subtype / live_update / SEO / X 自動投稿 / Team Shiny From 触らない原則を子 ticket でも維持

---

## 不変条項(子 ticket 全部に継承)

- Claude = 管理 / 要件定義 / Codex 指示 / push、commit はしない
- Codex = 実装担当、commit
- user = 最終判断(deploy / publish 拡張 / rollback / 危険変更)
- ChatGPT = 方針 / GO/HOLD 判断
- 新 subtype 追加 **絶対禁止**
- live_update / ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- Team Shiny From 不変
- 既存テンプレ text 不変
- 229-COST / 263-QA / 267-QA / 270-QA / 271-QA / 273-QA / 277-QA / 281-QA / 282-COST の挙動を壊さない
