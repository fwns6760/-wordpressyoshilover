# 209 source coverage and topic sensor audit

## meta

- number: 209
- status: CLOSED
- priority: P0.5
- lane: Claude/Codex B
- created: 2026-04-27

## close note(2026-04-28)

- read-only source coverage audit is complete.
- follow-up planning lives in 210 / 180 / source expansion tickets.
- Codex-M is not an active dispatch lane in current operations.

## 既存確認結果

### 読んだ ticket / doc

- 必読: `doc/active/OPERATING_LOCK.md`, `doc/README.md`, `doc/active/assignments.md`
- 対象 13 ticket:
  - `doc/done/2026-04/005-rss-fetcher.md`
  - `doc/done/2026-04/014-source-trust-and-taxonomy.md`
  - `doc/done/2026-04/022-multisource-merge-template.md`
  - `doc/done/2026-04/064-x-source-three-tier-contract.md`
  - `doc/done/2026-04/080-social-video-notice-lane.md`
  - `doc/done/2026-04/081-x-source-notice-lane.md`
  - `doc/done/2026-04/089-editor-source-url-body-fallback.md`
  - `doc/done/2026-04/090-editor-primary-source-domains-x-extension.md`
  - `106` は board row 確認(`doc/README.md`)
  - `doc/done/2026-04/126-sns-topic-fire-intake-dry-run.md`
  - `doc/done/2026-04/127-sns-topic-source-recheck-and-draft-builder.md`
  - `doc/waiting/128-sns-topic-auto-publish-through-pub004.md`
  - `doc/active/180-sns-topic-intake-to-publish-lane-separation.md`
- 追加確認:
  - `126/127/128/180` の board row(`doc/README.md`)
  - `154 publish-policy` は board 参照のみ

### status / impl 整理

- `005`: CLOSED / 旧 main ingress の起点。doc は RSSHub 経由 X 4 source 前提だが、現行実装は `config/rss_sources.json` の feed 群へ拡張済み。
- `014`: CLOSED / source trust 方針 doc。X は secondary 扱いの設計だが、実装側は一部 drift あり。
- `022`: CLOSED / multi-source merge の整形テンプレ。source 拡張後も再利用可。
- `064`: CLOSED(doc contract) / X を `fact / topic / reaction` の 3 tier で分離する基準。今回の「SNS は話題センサーのみ」と整合。
- `080`: CLOSED / `social_video_notice` contract + validator + dry-run CLI 実装済。live intake ではない。
- `081`: CLOSED / `x_source_notice` contract + builder + validator + dry-run CLI 実装済。live intake ではない。
- `089`: CLOSED / editor の source URL body fallback。source capture 欠損の既知対策。
- `090`: CLOSED / editor primary-source whitelist に `x.com` / `twitter.com` を追加。X official 記事の editor unblock。
- `106`: CLOSED / `speech_seed_intake.py` dry-run 実装済。comment lane 候補化のみで live intake ではない。
- `126`: CLOSED。doc 本文の status は古いが、board row では `CLOSED`、impl commit `5bfe892`。
- `127`: CLOSED。doc 本文の status は古いが、board row では `CLOSED`、impl commit `2669faa`。
- `128`: PARKED。`src/sns_topic_publish_bridge.py` と CLI/tests まで repo 実装あり。live 接続は未再開。
- `180`: READY(doc-only)。SNS 入口 lane と X 出口 lane の境界整理はまだ board 上で未完了。

### 既存実装

- main ingress:
  - `src/rss_fetcher.py`
  - `config/rss_sources.json`
  - `src/wp_draft_creator.py`
  - `src/wp_client.py`
- source 判定 / attribution / recovery:
  - `src/source_trust.py`
  - `src/source_id.py`
  - `src/source_attribution_validator.py`
  - `src/missing_primary_source_recovery.py`
  - `src/tools/run_draft_body_editor_lane.py`
- SNS / topic sensor:
  - `src/sns_topic_fire_intake.py`
  - `src/sns_topic_source_recheck.py`
  - `src/sns_topic_publish_bridge.py`
  - `src/speech_seed_intake.py`
- social / X notice:
  - `src/social_video_notice_contract.py`
  - `src/social_video_notice_builder.py`
  - `src/social_video_notice_validator.py`
  - `src/x_source_notice_contract.py`
  - `src/x_source_notice_builder.py`
  - `src/x_source_notice_validator.py`
- dry-run CLIs:
  - `src/tools/run_sns_topic_fire_intake.py`
  - `src/tools/run_sns_topic_source_recheck.py`
  - `src/tools/run_sns_topic_publish_bridge.py`
  - `src/tools/run_speech_seed_intake_dry_run.py`
  - `src/tools/run_social_video_notice_dry_run.py`
  - `src/tools/run_x_source_notice_dry_run.py`

### 既存 publish ルート

- 現行 mainline:
  - `src/rss_fetcher.py`
  - `config/rss_sources.json` の各 feed を取得
  - Giants 関連 filter / stale filter / social strength filter
  - WP draft 作成
  - `resolve_publish_gate_subtype(...)`
  - `get_publish_skip_reasons(...)`
  - guarded publish / publish history / publish-notice / X preview へ接続
- SNS topic lane:
  - `126 intake` -> `127 source recheck` -> `128 PUB-004 bridge`
  - ただし `128` は PARKED、`180` も未完了なので main live source ではない
- `080/081`:
  - article contract と validator はある
  - live fetch / automation wiring はない

### 既存重複チェック

- `src/rss_fetcher.py`
  - `_is_history_duplicate(...)`
  - `_create_draft_with_same_fire_guard(...)`
  - `history_duplicate`, `stale_postgame`, `stale_player_status`, `pregame_started` などの skip
- `src/wp_client.py`
  - `_yoshilover_source_url` meta で既存 draft 再利用
- `src/source_id.py`
  - URL 正規化
  - `x.com` / `twitter.com` status URL の同一視
- `src/lineup_source_priority.py`
  - `game_id` 単位で Hochi 優先
  - `lineup_duplicate_absorbed_by_hochi`
- `src/guarded_publish_evaluator.py`
  - title duplicate cluster
  - lineup duplicate hard stop
  - freshness / stale / source_url date 推定
- `src/sns_topic_source_recheck.py`
  - `duplicate_news` route

## 現在の入口供給状況

### 根拠と制約

- `gcloud logging read` / `gcloud storage cat` は sandbox の `~/.config/gcloud` 書き込み不可で recent runtime の authoritative read に失敗。
- したがってこの section は以下の fallback で作成:
  - static config: `config/rss_sources.json`
  - local state proxy: `data/rss_history.json`, `logs/guarded_publish_history.jsonl`, `logs/rss_fetcher.log`
- user baseline:
  - 最新 publish は `2026-04-27 09:05 JST`, `post_id=63781`
- local proxy baseline:
  - `logs/guarded_publish_history.jsonl` の最終 `sent` は `2026-04-26 17:45 JST`, `post_id=63668`
  - よって live 最新状況の authoritative source ではなく、repo 側の参考値として扱う

### source 別件数

- 現行 `config/rss_sources.json`
  - total sources: `13`
  - `social_news`: `9`
  - `news`: `4`
  - `article_source` role あり: `6`
  - `media_quote_pool` role あり: `6`
  - `media_quote_only`: `3`
- 現行 main ingress source 一覧
  - `social_news`: 巨人公式X, 読売ジャイアンツX, スポーツ報知巨人班X, 日刊スポーツX, スポニチ野球記者X, サンスポ巨人X, スポーツ報知X, 報知野球X, NPB公式X
  - `news`: 日刊スポーツ 巨人, ベースボールキング, Full-Count 巨人, スポーツ報知 巨人
- local `data/rss_history.json` の historical 上位
  - `news.google.com`: `73`
  - `twitter.com/hochi_giants`: `40`
  - `twitter.com/tokyogiants`: `36`
  - `twitter.com/sanspo_giants`: `31`
  - `www.nikkansports.com`: `18`
  - `baseballking.jp`: `3`
- 監査上の意味:
  - 現行入口は明確に `X/social_news` 偏重
  - historical に `news.google.com` 由来が残るが、現行 `config/rss_sources.json` には無い

### 一次・準一次情報 source status

- `giants.jp`
  - status: `部分既設`
  - 根拠: `src/source_trust.py` では `primary`、fixed-lane docs でも primary
  - ただし `config/rss_sources.json` の main ingress には web source 不在
- `NPB`
  - status: `部分既設`
  - 根拠: `src/source_trust.py` では `primary`、`run_notice_fixed_lane.py` / `acceptance_fact_check.py` でも参照
  - ただし main ingress は `NPB公式X` が `media_quote_only` のみで、`npb.jp` web intake は不在
- `スポーツ報知`
  - status: `既設`
  - 根拠: `hochi.news` RSS + `hochi_giants` / `SportsHochi` / `hochi_baseball` 系が config に存在
- `日刊スポーツ`
  - status: `既設`
  - 根拠: `nikkansports.com` RSS + `nikkansports` X が config に存在
- `スポニチ`
  - status: `部分既設`
  - 根拠: `SponichiYakyu` X は config に存在
  - gap: `sponichi.co.jp` web source は main ingress 不在、`source_trust.py` でも未分類
- `サンスポ`
  - status: `部分既設`
  - 根拠: `Sanspo_Giants` X は config に存在、`sanspo.com` は trust 側 secondary
  - gap: `sanspo.com` web feed は main ingress 不在
- `デイリー`
  - status: `部分既設`
  - 根拠: editor whitelist / bridge labels / draft audit では認識
  - gap: config / `source_trust.py` main ingress 側は未接続
- `読売新聞 / 読売オンライン`
  - status: `部分既設`
  - 根拠: editor whitelist / docs では参照
  - gap: config / `source_trust.py` で family 未整備、main ingress 不在
- `Yahoo ニュース配信元`
  - status: `部分既設`
  - 根拠: draft audit / bridge labels / prompt references には存在
  - gap: 現行 `config/rss_sources.json` に source 不在
  - note: local `rss_history.json` に `news.google.com` historical residue はあるが、現行 route ではない
- `番組公式 / 公式動画 / GIANTS TV 相当`
  - status: `部分既設`
  - 根拠: `080 social_video_notice` artifact はある
  - gap: live fetch / intake / policy wiring は未設
- `設定あるが skip filter で全弾き` 判定
  - 現 repo の read-only 証跡だけでは source ごとの「全弾き」は authoritative に確定できない
  - 少なくとも `social_too_weak` / `comment_required` / stale 系 skip は code 上に存在し、X偏重 source ほど影響を受けやすい

### 話題センサー source status

- `X 巨人ファン反応`
  - status: `部分既設`
  - 根拠: `126` 実装済、`SNS is a signal, not a source of fact` を強制
  - gap: live sensor wiring は未実施
- `YouTube 動画テーマ`
  - status: `部分既設`
  - 根拠: `080 social_video_notice` で YouTube article schema/validator はある
  - gap: topic sensor / live fetch は未実施
- `5ch / まとめ系`
  - status: `未設`
  - 根拠: `127` で 2chまとめ風 article は non-goal、`062` でも独立掲示板は後回し
  - judgment: 今回 audit では追加候補に上げない
- `SNS トレンド一般`
  - status: `部分既設`
  - 根拠: `126` input sources に existing Yahoo realtime helper の記載あり
  - gap: repo 上は dry-run / fixture 主体で、live ingestion ではない
- `番組で出た話題`
  - status: `部分既設`
  - 根拠: `106 speech_seed_intake` が dry-run 実装済
  - gap: comment lane 候補化までで live topic source ではない

### skip 理由

- code 上の main ingress skip 理由
  - `history_duplicate`
  - `missing_published_at`
  - `not_giants_related`
  - `stale_postgame`
  - `stale_player_status`
  - `video_promo`
  - `live_update_disabled`
  - `comment_required`
  - `social_too_weak`
  - `thin_source_fact_block`
  - `body_contract_validate`
  - `post_gen_validate`
  - `pregame_started`
- local guarded publish history proxy の hold / skip 傾向
  - `hard_stop_injury_death`: `70`
  - `burst_cap`: `27`
  - `cleanup_failed_post_condition`: `13`
  - `daily_cap`: `11`
  - `hard_stop_stale_for_breaking_board`: `5`
  - `hard_stop_lineup_duplicate_excessive`: `5`
  - `hard_stop_lineup_no_hochi_source`: `3`
  - `hard_stop_ranking_list_only`: `2`

### draft 化件数

- authoritative な直近 24-48h `rss_fetcher_run_summary` は取得できず
- local `logs/rss_fetcher.log` の summary は 2026-04-21 までしか無い
- 参考値として残っている summary:
  - `2026-04-16 17:49:39`: `total_entries=124`, `drafts_created=22`, `skip_filter=102`
  - `2026-04-16 19:06:25`: `total_entries=126`, `drafts_created=16`, `skip_filter=110`
  - `2026-04-16 19:26:08`: `total_entries=126`, `drafts_created=11`, `skip_filter=115`
  - `2026-04-16 21:13:24`: `total_entries=186`, `drafts_created=13`, `skip_filter=113`
  - `2026-04-21 06:47:13`: `total_entries=0`, `drafts_created=0`
- 結論:
  - repo 内だけでは直近 24-48h の drafts_created authoritative count は再現不可
  - ただし log と config からは「入口数より filter/gate で多く落ちる」構造は確認できる

### publish 件数

- local `logs/guarded_publish_history.jsonl` proxy:
  - rows: `204`
  - `sent`: `68`
  - `refused`: `98`
  - `skipped`: `38`
- この local proxy は guarded-publish 側の履歴であり、repo 外 latest live state を完全反映しない
- Codex shadow 経路と guarded-publish 経路の authoritative split は今回の sandbox では取得不能

## 既存で足りているもの

- SNS / X を「事実 source」ではなく「signal / topic / reaction」で分ける contract は既にある
  - `014`, `064`, `126`, `127`, `180`
- raw SNS quote を本文に持ち込まない guard は既にある
  - `126`: post text / account / URL を出さない
  - `127`: confirmed non-SNS source が無いものは `draft_ready` に上げない
- duplicate / freshness 安全弁は既に複数段ある
  - RSS history duplicate
  - same-fire guard
  - source_url meta reuse
  - lineup Hochi 優先 dedup
  - publish gate title duplicate / freshness gate
- speech / social_video / x_source_notice の dry-run artifact は既にある
  - `106`, `080`, `081`
- `128` の publish bridge 自体は repo 実装まで存在し、raw SNS 直 publish は設計上 blocked

## 既存と重複するので作らないもの

- `212-topic-sensor-intake-dry-run`
  - `126` と重複。dry-run の topic intake はすでに実装済
- `213-topic-to-primary-source-recheck`
  - `127` と重複。source recheck + draft builder はすでに実装済
- 新しい「SNS 直 publish」ticket
  - `128` が既に存在し、かつ `180` 完了前は再開禁止
- 新しい `social_video_notice` / `x_source_notice` lane 作成 ticket
  - `080/081` が既に artifact を持つ
- generic な `215-freshness-gate-for-breaking-board`
  - 現状のままだと `src/rss_fetcher.py` / `src/guarded_publish_evaluator.py` の stale / freshness gate と重複が大きい

## 足りない差分

- main ingress に `giants.jp` / `npb.jp` の web source が無い
  - `src/source_trust.py` では `primary`
  - fixed lane docs でも primary 扱い
  - しかし `config/rss_sources.json` の main fetch path には未接続
- main ingress の non-X web reporting source が不足
  - `スポニチ`, `サンスポ`, `デイリー`, `読売オンライン`, `Yahoo配信元` の web source が不足または未接続
  - 現状 `スポニチ` / `サンスポ` は X handle 側に偏っている
- trust / whitelist drift が大きい
  - `src/source_trust.py` secondary domains: `hochi.news`, `sanspo.com`, `nikkansports.com` のみ
  - しかし他 module は `sponichi.co.jp`, `daily.co.jp`, `yomiuri.co.jp`, `sports.yahoo.co.jp`, `baseball.yahoo.co.jp`, `baseballking.jp`, `full-count.jp` を認識している
  - つまり config / trust / attribution / editor whitelist の source family 定義が一致していない
- `080/081` は contract / validator 止まりで live intake ではない
- `106/126/127` も live sensor 接続ではなく dry-run / mock / offline 前提
- 5ch / まとめ系は現状 non-goal / reject 側で、live sensor 実装はゼロ
- `180` 未完了のため、SNS由来記事の X autopost 境界が運用正本としてまだ固定されていない

## 後続 ticket 案

### 210-primary-source-expansion-plan

- 重複判定: **重複しない**
- 理由:
  - 既存 ticket は SNS signal 側の contract / dry-run が中心
  - main ingress の一次 / 準一次 source をどう増やすか、`config/rss_sources.json` と trust family をどう揃えるかの ticket が無い
- scope 推奨:
  - `giants.jp` / `npb.jp` / 報道 web source の追加順序決定
  - `config/rss_sources.json` / `src/source_trust.py` / editor whitelist / attribution validator の family 整合
  - `article_source` / `media_quote_pool` / `media_quote_only` の role 再設計

### 214-duplicate-safe-source-expansion

- 重複判定: **条件付きで重複しない**
- 理由:
  - duplicate guard 自体は既に多い
  - ただし source を増やすと「同一ニュースの web / X / Yahoo配信 / 公式お知らせ」の family dedupe が新たに必要
- 条件:
  - `210` の後続に限定
  - generic duplicate 改修ではなく、source family mapping と cross-source collision を narrow scope にする

### 215-freshness-gate-for-breaking-board

- 重複判定: **現状では重複が大きい**
- 理由:
  - `stale_postgame`, `stale_player_status`, `pregame_started`, `freshness_check`, `hard_stop_stale_for_breaking_board` が既に存在
- 例外:
  - 新 source を board / aggregation 系へ広げたあと、既存 freshness で吸えない feed が見つかった場合だけ narrow ticket 化

## 最初に Codex へ投げるべき 1 本

- `210-primary-source-expansion-plan`

理由:

- 供給不足の主因は「SNS sensor が無いこと」ではなく、「main ingress が X/social_news 偏重で、一次 / 準一次 web source が不足していること」
- `126/127` はすでにあり、`212/213` を切っても重複になる
- 先に `210` で source family と trust drift を正し、その後に必要なら `214` を narrow fire するのが最も安全

## 重複・デグレ対策

- `SNS / 5ch / YouTube` は本文 source ではなく topic sensor に固定する
- `source_trust.py` と `config/rss_sources.json` を同じ commit scope で揃える
  - source 追加だけ先行して trust 未整備、は避ける
- source family を先に定義する
  - `giants official web`
  - `giants official X`
  - `npb web`
  - `npb X`
  - `Hochi web/X`
  - `Nikkan web/X`
  - `Sponichi web/X`
  - `Sanspo web/X`
  - `Daily web`
  - `Yahoo syndication`
- 新 source は初期状態を `article_source` 固定にせず、必要に応じて `media_quote_pool` / `media_quote_only` で段階投入する
- 既存 guard を必ず再利用する
  - RSS history duplicate
  - source_url meta reuse
  - `source_id.py`
  - lineup Hochi dedupe
  - title duplicate cluster
  - freshness gate
- SNS由来記事の X autopost は `180` と PUB-005 側更新完了まで除外維持

## 判断保留

- `Yahoo ニュース配信元` を main ingress に戻すか
  - source family を配信元単位に戻せるなら有効
  - aggregator のまま増やすのは重複増の危険が高い
- `読売オンライン` を article_source にするか、recheck source に留めるか
- `GIANTS TV` 相当 / 番組公式 / 公式動画を live intake まで広げるか
  - `080` artifact はあるが、fetch / policy / quote境界の追加判断が要る
- `5ch` を将来でも実装対象にするか
  - 現時点では topic sensor 候補にも上げず、reject / non-goal 扱い維持を推奨

## 残リスク

- authoritative な 24-48h runtime log / GCS history を今回の sandbox では取れていない
- local `logs/guarded_publish_history.jsonl` は live 最新 publish (`2026-04-27 09:05 JST`, `post_id=63781`) を反映していない
- 供給不足は source coverage だけでなく publish gate / cleanup failure の影響も受ける
  - local proxy では `cleanup_failed_post_condition=13` が残る
- `Full-Count` / `BaseballKing` は config にはあるが `src/source_trust.py` では family 定義が薄く、source 評価 drift の原因になりうる
- `180` 未完了のまま SNS topic lane を live 化すると、X 出口境界のデグレが起きやすい
