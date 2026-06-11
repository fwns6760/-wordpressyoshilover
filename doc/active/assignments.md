# assignments — 現場担当と次アクション

最終更新: 2026-06-11 JST (データ角度v2 + カードバリエーション + 試合後鮮度チェーン)

## 2026-06-11 — データ角度v2: 驚き系3角度 + 話題選手連動 (user「全部やるgo」)

- **新角度** (`src/x_post_data_angles.py`、insight.db read-only、LLM不使用・新規課金なし、commit `d5994902`):
  - 勝利相関 (条件付き勝率): 「キャベッジ打点あり9勝2敗(.818)/なし14勝17敗(.452)」+ 新カード `win_split`
  - 対戦別split: 「対○○キラー」(対戦打率シーズン比+.080以上)
  - 歴代通算チェイス: OB878名+現役の通算ランキング「あと○本で△△に並ぶ」
  - 話題選手ブースト: RSSHub巨人系X言及数で候補先頭寄せ + why_now「🔥今夜の話題」
- **deploy**: Cloud Build `45cf959f`、image `data-angles-d5994902`、Job gen `175`、flag 3種 ON
- rollback = env flag 0 戻しのみ。詳細: `docs/handoff/session_logs/2026-06-11_data_angles_v2.md`
- needs-ticket: 年度別シーズン形比較 (OB年度別 scrape 必要)

## 2026-06-11 — 試合後データ鮮度チェーン (user「データを知りたいのは試合後」)

- **診断**: insight-nightly (ETL) 最終便 21:00 で、22時台の mail flush が試合中 stale データを配っていた。欠けは ETL 側のみ
- **最終形** (user 調整: 費用増なし / ETL 1日1回 / 23時は寝てる / 配信は減らさない):
  - 試合後 ETL = `data-insight-postgame-2150` (**21:50**、1日1回)。during-game 21:00 と試行した 21:55/22:40 は削除済
  - 夜: ETL 21:50 → **22:05 便**で当日確定データ着弾。長引いた試合は翌朝 05:00 ETL → **07:05 便** (通勤帯) で復習配信
  - `x-post-mail-flush` = `5 7,9,11,13,15,16,17,22,23` (23時便追加 + :05 シフトで 15/17時 ETL race 解消)。ETL 7 本/日でネットゼロ
- 詳細: `docs/handoff/session_logs/2026-06-11_postgame_data_schedule.md`。rollback = trigger delete + cron 戻し

## 2026-06-11 — X案カード画像バリエーション3種追加 (user「もっとバリエーションふやせる」)

- **user 指示**: 「ポストのデータカードは良くなったが、もっとバリエーションふやせる。」(6/10 刷新の続き)
- **対応**: `src/x_post_image_gen_v2.py` に新 template 3 種追加 (commit `c4871091`)。ranking rows 共通 schema のままなのでデータ抽出側は無変更。
  - `podium_top3`: TOP3 表彰台 (2位-1位-3位、台の高さ差 + メダル badge + 4-6位下部 strip)
  - `focus_duel`: 巨人 focus 選手 vs 隣接順位 rival の 1on1 (左 orange / 右 warm dark + VS 円 + 差分 chip「リード .015」等)
  - `dark_hero`: night 仕様 — warm dark 下地に hero 数字 orange glow + TOP3 mini list (brand lock 範囲内の別 mood)
- mail lane round-robin 9→12 種 (`_ROUND_ROBIN_TEMPLATES`)、router `TEMPLATE_KEYS` にも追加
- **test**: 新規 9 件含む image 系 81 passed。mail lane 系の既存 fail 5 件は worktree 上の別 WIP (469 source 効率化、reply handle 系) 由来で本件と無関係
- **サンプル**: `/tmp/cards/var_*.png`
- **deploy**: クリーン worktree (HEAD `c4871091`) から Cloud Build `535fefed` SUCCESS (1m35s)、image `x-post-mail-lane:card-variation-c4871091`、Job generation `174`。次回 flush 便から新 variation がローテに入る

## 2026-06-10 — X案カード画像デザイン刷新 (user「ださい」指摘対応)

- **user 指摘**: 「データ記事の絵だけどださい、これは君が作った。もっと洗練させることができないの？」
- **対応**: `src/x_post_image_gen_v2.py` の全 11 template を再設計 (commit `21deab6d`)。brand 色 lock (orange/gold/黒) は維持。
  - 行・セルを角丸カード化 (巨人 = orange gradient + soft shadow / 他 = 白カード + hairline border)、下地 warm off-white
  - rank を円バッジ化 (top3 = 金/銀/銅)、チーム名を選手名と同行 inline 配置 (旧: 行下で次行と衝突・潰れ)
  - hook 行を半透明黒 pill チップ化 (旧: 金 on orange 低コントラスト)、Noto Bold 環境で stroke 増し打ち全停止 (滲み解消)
  - footer 黒帯 + orange accent line、spotlight は白 hero カード集約、bar 系は丸端バー化、data_sheet は header帯+zebra
- **test**: image gen v2 / router / brand / overlay / integration 計 84 passed。cairosvg 系 (v1) のローカル失敗は未導入環境の既存事象で無関係。
- **サンプル**: `/tmp/cards/new_*.png` (旧版は `cur_*.png`)。
- **deploy**: クリーン worktree (HEAD `21deab6d`) から Cloud Build `e194e9b5` SUCCESS (2m5s)、image `x-post-mail-lane:card-design-21deab6d`、Job generation `172` に更新。本 image は鮮度ゲート (`f7c13c01`) も同梱。次回 flush 便 (試合中 15 分間隔) から新デザインのカードがメール添付される。

## 2026-06-10 — X案データポスト: 離脱中選手の「直近N試合」混入を鮮度ゲートで除外

- **user 報告**: データポスト候補の「OBP 直近10試合」に長期離脱中の平山功太が選出されていた（6/10 の 9:00/11:00/13:00 JST 便ログで alternate 選出を確認）。「データで指摘されるとブランディングが崩れる。データサイトをやっている以上、ポストは止めずに正確に」。
- **原因**: `advanced_metric_snapshots` の `last_N_games` scope は **選手ごとの rolling**（本人の最後のN試合、`insight_etl.py` `_player_last_n_game_window`）。離脱中の選手は怪我前の古い試合がいつまでも「直近」として残り、`x_post_mail_lane._query_rank_from_snapshots` に鮮度チェックがなかったため Top10 に載り続けた。
- **修正**: `_query_rank_from_snapshots` に鮮度ゲートを追加。batting_logs/pitching_logs の最終出場日が snapshot 日から **打者10日 / 投手14日** より古い選手を X 向け ranking から除外（除外は `snapshot_rank_stale_drop` で INFO ログ、432 の可視化方針準拠）。最終出場が特定できない選手は誤除外を避けて残す fail-open。snapshot テーブル・data site は不可触のまま、ポスト自体は出続ける。
- **test**: 新規 `SnapshotStaleFreshnessGateTests` 4件（stale打者除外 / fail-open / 投手14日閾値 / rank振り直し）。クリーン worktree（HEAD `af881ea3` + 本修正のみ）で test_x_post_mail.py **165 passed / 0 failed**。本体ツリーの既存2失敗（ReplyCandidateRuntimeConfigTests）は作業中の別変更による既存ずれで本件と無関係。
- **deploy**: 未コミットの作業中変更を巻き込まないため、クリーン worktree（HEAD `af881ea3` + 本修正のみ）からビルド。Cloud Build `57b41eb3` SUCCESS、image `x-post-mail-lane:stale-gate-af881ea3`（digest `sha256:d8c5ef5b…`）、Job generation `170` に更新。
- **live verify (19:30 JST 便 `x-post-mail-lane-ks7n8` SUCCESS)**: `snapshot_rank_stale_drop` 268 件発火。平山功太は `last_game=2026-05-22 cutoff=2026-05-31` で AVG/OPS の全 直近N試合 scope から除外を確認。データ候補は継続生成（`data_split appended total=4`、mail `status=sent`）= ポストは止まっていない。
- **残**: src/tests の変更は未コミット（commit/push は Codex 管轄）。in-flight の feat/377 作業と同居しているため、コミット時は本修正 hunk（`_SNAPSHOT_STALE_DAYS_*` / `_snapshot_last_game_dates` / `_query_rank_from_snapshots` 鮮度ゲート / `SnapshotStaleFreshnessGateTests`）を明示すること。

## 2026-06-10 — 連続試合安打の2試合遅れ解消 (data-insight 朝便 05:00 へ移動) LIVE

- **user 報告**: 試合中 TV「泉口 7試合連続ヒット」に対し /data 選手ページが 5試合表示（1試合遅れのはずが2試合遅れ）。
- **原因**: ナイトゲームは data-insight 最終便 21:00 に間に合わず翌朝 07:00 便で DB 取込。一方ページ再生成 (data-site-publisher) は 06:00 で取込より先に走るため、朝〜17:30 のページが恒常的に2試合前のまま。公開 HTML は page-cache 失効待ちでさらに遅れて見える。
- **対応**: user 承認（値段不変が条件）のもと、`data-insight-morning-trigger` の schedule を `0 7 * * *` → `0 5 * * *` (JST) に変更。トリガー数・実行回数は不変 = 課金不変。insight-nightly の実行時間は 1〜2 分のため 05:02 頃完了 → 06:00 publisher に間に合う。05:00 時点は `auto_target_jst_date()` で前日対象のため前夜試合を取込む。
- **効果**: 毎朝 06:00 の再生成で前夜試合まで反映 = 常時「1試合前」表示（非リアルタイムページの構造上の最小遅れ）。検討した代替案（publisher を 10:30 へ移動）は朝の閲覧者に古い表示が残るため不採用。
- **doc**: `mkdocs_docs/operations/scheduler.md` の data-insight-morning-trigger 行を 05:00 へ更新。
- **verify 予定**: 2026-06-11 朝、insight-nightly 05:00 実行 SUCCESS と 06:00 publisher 後の選手ページ streak 値を確認。

## 2026-06-09 — home starter rotation table LIVE_VERIFIED

- **トップUX追加**: user 指示「先発ローテ一覧 2007年〜2026年をスクレイピングして表に」「同じレベルでユーザビリティをあげて」を反映。トップの `巨人 選手データ・成績` 枠には `先発ローテ` カードを追加し、表本体は独立ブロック `🧭 先発ローテ一覧（2007年〜2026年）` として表示。
- **実装**: `yoshilover-063-frontend.php` version `0.21.10`。my-favorite-giants の `giants_data/rotation/{year}.htm` を 2026→2007 の20年分 `wp_remote_get()` で取得し、年別に先発投手を先発数順へ集計。WP option/transient `yoshi_starter_rotation_rows_2007_2026_v1` に保存。管理REST action `refresh_starter_rotation_rows` を追加。
- **表示仕様**: 2026→2007 の新しい年度順、年度ジャンプボタン、`20年分` / `新しい年度から表示` / `先発数順` pill、スマホ横スクロール、年度列 sticky。各年度は出典年別ページへリンク。
- **deploy / verify**: Cloud Build `c5b8f5a3-d4e0-4b52-aaf6-6e48678916fc` SUCCESS、image `wp-frontend-deploy:starter-rotation-0.21.10-170fc801-20260609011425` digest `sha256:c87d2f...`。Cloud Run Job `wp-frontend-deploy` generation `10`、execution `wp-frontend-deploy-nj7mx` SUCCESS。log: `replace_plugin status=ok written_bytes=237728`、`refresh_rotation row_count=20 failed_years=[]`、cache clear `wp_object_cache` / `wp_rocket`。
- **public validation**: Job 内 public fetch で top status `200`、`has_rotation_block=true`、`has_rotation_title=true`、`has_rotation_card=true`、`has_2026=true`、`has_2007=true`、`has_fetch_placeholder=false`、`has_source=true` を確認。
- **repo validation**: `php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest -q tests/test_front_home_data_links.py tests/test_front_adsense_scroll_ui.py` 10 passed、`git diff --check -- src/yoshilover-063-frontend.php tests/test_front_home_data_links.py` OK。

## 2026-06-08 — home legacy jersey toplink cleanup LIVE_VERIFIED

- **方針修正**: user 指摘「🔢 巨人 歴代背番号・永久欠番を見る これだけ 巨人 選手データ・成績 の枠に外れてあるのはおかしくない」を反映。トップのデータ枠内カード `歴代背番号` は残し、枠外に残っていた旧 `front_top` text widget の単独リンクだけを除去。
- **原因**: 以前の背番号導線追加時に `text-33` / `yoshi-jersey-toplink` の旧ウィジェットが残り、`yoshi-home-data` 内の新カードと重複していた。
- **front fix**: `yoshilover-063-frontend.php` を `0.21.8` に更新。`yoshilover_063_remove_legacy_jersey_toplink_widget()` を追加し、front page buffer で旧 `yoshi-jersey-toplink` widget wrapper を除去。fallback で inner div だけの残存も除去する。
- **deploy / verify**: Cloud Build `8bff574b-e6d6-460c-8da0-8cfc5247b0b0` SUCCESS、image `wp-frontend-deploy:jersey-toplink-clean-front-0.21.8-170fc801-20260608091353`。Cloud Run execution `wp-frontend-deploy-2k8nq` SUCCESS、log: `replace_plugin_status=ok`、`version=0.21.8`、`has_legacy_cleanup=true`、cache clear `wp_object_cache` / `wp_rocket`。
- **public validation**: Cloud Build public verify `f5bdb1a9-28c2-4024-a69d-26fafdd8717c` SUCCESS。top HTML: `legacy_text_count=0`、`legacy_class_count=0`、`jersey_url_count=1`、`has_jersey_card_title=true`。つまり枠外の旧リンクは消え、データ枠内カードだけが残る状態。
- **repo validation**: `php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest tests/test_front_home_data_links.py -q` 4 passed、`git diff --check -- src/yoshilover-063-frontend.php tests/test_front_home_data_links.py` OK。

## 2026-06-08 — /data 打撃/投手ランキング split LIVE_VERIFIED

- **方針修正**: user 指摘「打撃成績ランキングと投手成績ランキングが同じ」「残す必要あるの？Topページからの導線でいい」を反映。トップの2カードは同一 `/data/ranking/` ではなく、打撃 `/data/batting-ranking/`、投手 `/data/pitching-ranking/` へ直接リンク。
- **ページ分離**: `/data/batting-ranking/` は打率・本塁打・打点・安打・盗塁、通算/歴代の打撃系のみ掲載。`/data/pitching-ranking/` は防御率・勝利・奪三振、通算/歴代の投手系のみ掲載。旧 `/data/ranking/` は混在ランキング表を出さず、打撃/投手の2択案内だけに変更。
- **data hub 導線**: `/data/` の intro からも汎用「選手ランキング」リンクを外し、`打撃ランキング` / `投手ランキング` の直接リンクに分離。
- **deploy / verify**: data-site image `data-site-publisher:ranking-split-170fc801-20260608082959` (Cloud Build `9a114ff7-5d4b-4f7c-aa82-61f13a7e55f6`) を build。全体 execution は古い自動実行との競合回避で cancel し、同 image ベースの一時 ranking patch Job `data-site-ranking-split-patch-s774p` で `ranking` updated page_id `76423`、`batting-ranking` created page_id `86573`、`pitching-ranking` created page_id `86574`。一時Jobは削除済み。front plugin `0.21.7` は `wp-frontend-deploy-8z6sg` で self-update + cache clear、readback で新リンクあり/旧 child path なしを確認。
- **public validation**: Cloud Build public verify `c8160744-6654-474d-a7b8-d6ab410f929d` SUCCESS。top は `/data/batting-ranking/` / `/data/pitching-ranking/` を含み旧 `/data/ranking/batting|pitching/` を含まない。`/data/` は直接2リンクを含み `/data/ranking/` を含まない。打撃ページは `巨人 本塁打 ランキング` / `巨人 打率 ランキング` を含み `巨人 防御率 ランキング` / `通算勝利` を含まない。投手ページは `巨人 防御率 ランキング` / `巨人 勝利 ランキング` を含み `巨人 本塁打 ランキング` / `通算安打` を含まない。旧 `/data/ranking/` は2択案内のみ。
- **repo validation**: `python3 -m py_compile src/data_site_template_team.py src/data_site_template_cluster.py src/data_site_publisher.py` OK、`php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest tests/test_data_site_publisher.py tests/test_data_site_team.py tests/test_data_site_template_cluster.py tests/test_front_home_data_links.py -q` 54 passed、`compileall` / `git diff --check` OK。

## 2026-06-08 — /data 注目データ separate-page LIVE_VERIFIED

- **方針再修正**: user 指摘「トップページから選手個人ページと注目データが2つ同じだとおかしい」「注目データを新しくページをつくって誰の記録か分かるように」を反映。トップの `注目データ` は `/data/#ys-notable-data` ではなく独立ページ `/data/notable/` へ向ける。
- **ページ分離を固定**: user 追加指摘「注目データのSectionをかけるではなく、選手別個人成績とは違うページ」を反映。`/data/` は選手別個人成績ハブ専用に戻し、`id="ys-notable-data"` section / 注目データ teaser を出さない。`/data/notable/` だけが注目データ本文を持つ。
- **表示修正**: `/data/notable/` のカード見出しは「吉川尚輝の連続試合安打」のように、選手名 + 記録名 + 数値を先に出し、各カードから該当選手ページへ戻れるようにする。投手一覧 / 捕手一覧 / 内野手一覧 / 外野手一覧 / 育成選手一覧 / 監督・コーチ一覧は注目データ page に出さないテストを追加。
- **publisher 修正**: `python -m src.data_site_publisher --only-notable-data` は `/data/notable/` を upsert し、既存 `/data/` に残っている `id="ys-notable-data"` section は削除する。過去の `--retire-legacy-notable` は canonical page を誤って下書き化しない no-op に変更。さらに WP slug 予約の `notable-2` 再発防止として `_find_page_id_by_slug()` を `context=edit` + `status=any` に変更。
- **live deploy / verify**: Cloud Build `a36a7cda-58c8-4fdb-81e8-53620a3ec044` SUCCESS、image `data-site-publisher:notable-separate-slugfix-170fc801-20260608080707` digest `sha256:7d5f6293...`。Cloud Run Job `data-site-publisher-qx6nf` SUCCESS、log: `notable_page_id=86527 notable_action=updated action=updated items=8`。front plugin は `0.21.6` を `wp-frontend-deploy-j5qpm` で self-update + cache clear。旧 duplicate `/data/notable-2` は canonical fix Job `wp-frontend-deploy-9zgtb` で draft 化し、`/data/notable/` に統一。
- **public validation**: Cloud Build public verify `2129b476-76f9-460f-9f8b-d4f2b81bcb47` SUCCESS。top は `/data/notable/` を含み `/data/#ys-notable-data` を含まない。`/data/` は `id="ys-notable-data"` を含まず `/data/notable/` link を含む。`/data/notable/` は `この記録の選手` を含み、`投手 一覧` / `捕手 一覧` / `内野手 一覧` / `外野手 一覧` / `育成選手 一覧` / `監督・コーチ 一覧` を含まない。final URL は `/data/notable` で `notable-2` に redirect しない。
- **repo validation**: `python3 -m py_compile src/data_site_template_cluster.py src/data_site_publisher.py` OK、`php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest tests/test_data_site_template_cluster.py tests/test_data_site_publisher.py tests/test_front_home_data_links.py -q` 42 passed、`git diff --check` OK。

## 2026-06-08 — /data 注目データ only-mode LIVE_VERIFIED

- **方針修正**: user 指摘「注目データが選手データと重複」「試合日からを起点」「古いデータもある」を反映。`/data/notable/` の驚き・注目選手ページ生成は止め、トップ導線も `/data/#ys-notable-data` の注目データ anchor に固定。注目 section 内も個別選手ページリンクを出さず、データ項目だけを表示する。
- **更新範囲分離**: `python -m src.data_site_publisher --only-notable-data` を追加。既存 `/data/` の `id="ys-notable-data"` section だけを置換し、選手ページ / ランキング / ファーム / 背番号などの子ページ upsert は走らせない。
- **古いデータ混入防止**: `fetch_latest_giants_game_date()` と `fetch_player_latest_game_date()` を追加し、注目データは最新の巨人試合日と選手の最新出場日が一致するものだけ採用。最新試合日が取れない場合は live 更新を abort し、空データで `/data/` を上書きしない。
- **古い導線除去**: 既存 `/data/` 冒頭に残っていた `/data/notable/` / `驚き・注目選手` も only-mode の同一 `/data` content update 内で `#ys-notable-data` / `注目データ` に置換。公開HTMLで `/data/notable/` が残らないことを確認済み。
- **live deploy / verify**: Cloud Build `047d920a-b554-4b7a-ad1b-3870b2689fbb` SUCCESS、image `data-site-publisher:notable-data-only-linkfix-170fc801-20260608` digest `sha256:626ac753...`。Cloud Run Job `data-site-publisher` image 更新後、execution `data-site-publisher-hf8kb` SUCCESS。job log: `page_id=73526 action=updated items=8`。Cloud Build public verify `63566bba-6638-4986-b6a1-11403a84d715` SUCCESS: `id="ys-notable-data"` / `dataset-notable-data` / `注目データ（連続試合・好調指標）` / `基準日:` found、`/data/notable/` absent。top public verify `a023c1d7-7180-465c-b4f0-4011a5836749` SUCCESS: `/data/#ys-notable-data` / `注目データ` found、`/data/notable/` absent。
- **legacy page retired**: 過去生成の `/data/notable/` が `200` で残っていたため、`--retire-legacy-notable` を追加。Cloud Build `5ff15a09-415e-41fa-97fd-935683637d30` SUCCESS、image `data-site-publisher:notable-data-retire-legacy-170fc801-20260608` digest `sha256:c8ad5121...`。Cloud Run execution `data-site-publisher-c2c94` SUCCESS。job log: `mode=retire_legacy_notable action=updated page_id=86527`。Cloud Build public verify `727c4d42-d14e-4a73-b2d0-ec532eb3fcd8` SUCCESS: `/data/notable/` status `404`。
- **tests**: `python3 -m pytest tests/test_data_site_template_cluster.py tests/test_data_site_publisher.py tests/test_data_site_query.py tests/test_front_home_data_links.py -q` 88 passed。`py_compile` / `compileall` / AST parse / `php -l src/yoshilover-063-frontend.php` / `git diff --check` OK。

## 2026-06-08 — /data 注目データ + Dataset schema LIVE_DEPLOYED

- **/data 既存ページ強化 LIVE_DEPLOYED**: user「無駄なページは増やさなければ良い。構造化マークアップもいれて」を反映。新規URLは作らず、既存 `/data/` に `#ys-notable-data` セクションを追加。内容は「直近5/10」固定ではなく、ニュースで使いやすい `連続試合安打` / `連続得点関与` / `今季最長連続安打` を優先し、薄い日は短期OPS/防御率で補完する設計。
- **schema / トップ導線**: 表示データと一致する Schema.org `Dataset` + `ItemList` JSON-LD を `/data/` 本文に追加。トップ「巨人 選手データ・成績」カードは `注目データ` → `/data/#ys-notable-data` に差し替え。ページ数増加なし。
- **deploy / verify**: Cloud Build `eee60cb9-37f0-4801-9c53-d1377ba7a80b` SUCCESS、image `data-site-publisher:notable-data-schema-170fc801-20260608` digest `sha256:1f9cc345...`。Cloud Run execution `data-site-publisher-rs4xj` SUCCESS、cluster `/data` page_id `73526` updated。一時Job `notable-front-push-170fc801-8vp7f` SUCCESS、plugin readback `live_has_notable=True` / `version_0214=True`、cache clear `wp_rocket` / `wp_object_cache`。一時Jobは削除済み。Cloud Build public verify `86bfe06c-3685-41f2-b757-d94d429d0c08` SUCCESS: `/data/` の `id="ys-notable-data"` / `注目データ（連続試合・好調指標）` / `dataset-notable-data` / `"@type": "Dataset"`、トップの `/data/#ys-notable-data` / `注目データ` を確認。
- **tests**: `python3 -m py_compile src/data_site_template_cluster.py src/data_site_publisher.py` OK、`php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest tests/test_data_site_template_cluster.py tests/test_front_home_data_links.py -q` 28 passed、`python3 -m compileall -q src/data_site_template_cluster.py src/data_site_publisher.py` OK、AST parse OK、`git diff --check` OK。

## 2026-06-08 — /data/jersey-numbers 支配下/育成グループ化 LIVE_DEPLOYED

- **背番号ページ UX update LIVE_DEPLOYED**: user「背番号は育成と背番号をグループ分けて」を反映。`/data/jersey-numbers/` の番号別一覧を `支配下・永久欠番 背番号` と `育成背番号（3桁）` に分離。3桁番号は `001` のような先頭ゼロ付きも育成側として判定。検索 box はページ内 1 つに統一し、両グループ横断で検索できる。
- **deploy / verify**: Cloud Build `1614d5fd-26dd-4963-9d76-a67000c61a4d` SUCCESS、image `data-site-publisher:jersey-groups-170fc801-20260608`、Cloud Run execution `data-site-publisher-cq6mk` SUCCESS。job log: `jersey numbers upsert slug=jersey-numbers page_id=86346 action=updated rows=234`。Cloud Build public verify `afb68878-2d26-4fd7-85a6-d9e2fcd2d277` SUCCESS: `支配下・永久欠番 背番号` / `育成背番号（3桁）` / `支配下背番号` / `3桁番号を分離` / `ys-jersey-search` found。
- **tests**: `python3 -m py_compile src/data_site_template_jersey.py src/data_site_jersey_source.py src/data_site_publisher.py` OK、`python3 -m pytest tests/test_data_site_jersey.py -q` 3 passed。

## 2026-06-08 — /data/jersey-numbers 歴代背番号 topic cluster LIVE_DEPLOYED

- **歴代背番号ページ LIVE_DEPLOYED**: `/data/jersey-numbers/` を `/data/` 配下のヒストリー系 spoke として新規作成。my-favorite-giants の `backnumber.htm` / `retired_number.htm` を参照し、永久欠番カード・背番号検索・番号別変遷テーブル・関連トピクラ導線(`/data/` `/data/legends/` `/data/draft/` `/data/farm/`)を追加。Cloud Build `091fd0f4-e594-421b-9189-d5e584e6fa75` SUCCESS、image `data-site-publisher:jersey-numbers-170fc801-20260608`、Cloud Run execution `data-site-publisher-gwvvr` SUCCESS。WP page `/data/jersey-numbers/` page_id `86346` created、rows `234`。
- **トップページ導線 LIVE_DEPLOYED**: `yoshilover-063-frontend.php` version `0.21.3` に `歴代背番号` → `/data/jersey-numbers/` card を追加。Cloud Build 直RESTは XSERVER 403 のため、Cloud Run 一時Job `jersey-toplink-push-c54p6` で plugin self-update + `front_top` link + cache clear を実行。log readback: `replace_plugin_status=200`、`replace_plugin_written_bytes=222099`、`live_plugin_has_jersey=True`、`clear_cache_keys ['wp_object_cache', 'wp_rocket']`。
- **live verify**: Cloud Build public verify `5ccee559-1283-4e93-bf73-d6b1796f820a` SUCCESS。`/data/jersey-numbers/` は `巨人 歴代背番号一覧・変遷` / `永久欠番` / `ys-jersey-search` を確認。トップページは `歴代背番号` / `/data/jersey-numbers/` / `2軍試合日程・結果` を確認。
- **tests**: `python3 -m py_compile src/data_site_jersey_source.py src/data_site_template_jersey.py src/data_site_publisher.py` OK、`php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest tests/test_data_site_jersey.py tests/test_data_site_template_cluster.py tests/test_front_home_data_links.py -q` 28 passed。

## 2026-06-08 — mobile header duplicate fix LIVE_DEPLOYED

- **ヘッダー重複 fix LIVE_DEPLOYED**: mobile header でタイトル/サブタイトルが重なって見える原因だった `yoshi-headLogo__text` / `yoshi-headLogo__subtitle` の可視 DOM 注入を `yoshilover-063-frontend.php` から削除し、plugin version を `0.21.3` に更新。さらに `src/custom.css` に残っていた旧 388 header 用 CSS block も削除し、テーマ側ヘッダー表示に戻した。
- **deploy**: ローカル環境は `yoshilover.com` DNS 解決不可のため、Cloud Run Job `wp-frontend-deploy` で WP REST self-update を実行。Cloud Build `97e4301c-406c-438d-a896-2e16de53d852` は Cloud Build 直 WP REST が XSERVER 403 で失敗。迂回として image `wp-frontend-deploy:header-fix-0.21.3-css` を Cloud Build `b2bd08e3-8733-42a4-b518-93810afcd92f` で build、Cloud Run execution `wp-frontend-deploy-vswth` SUCCESS。
- **live verify**: Job log readback で `live_after_version 0.21.3`、`live_after_header_markers {'yoshi-headLogo__text': False, 'yoshi-headLogo__subtitle': False, '読売ジャイアンツ専門の速報＆データサイト｜試合結果': False}`、`update_custom_css_contains_marker True`、`clear_cache_keys ['wp_object_cache', 'wp_rocket']`、`deploy_status ok` を確認。
- **tests**: `php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest -q tests/test_front_home_data_links.py` 3 passed、`git diff --check -- src/yoshilover-063-frontend.php src/custom.css tests/test_front_home_data_links.py` OK。

## 2026-06-07 — 2軍ファーム topic cluster LIVE_DEPLOYED

- **/data/farm 複数ページ LIVE_DEPLOYED**: user「複数枚で作ってね」を反映。親 `/data/farm/` と子 `/data/farm/schedule/` `/data/farm/spring-education/` `/data/farm/autumn-education/` `/data/farm/team/` `/data/farm/players/` `/data/farm/titles/` `/data/farm/championship/` を作成。my-favorite-giants の 2軍導線(試合日程・結果 / 年度別教育リーグ / チーム成績 / 個人成績 / タイトルホルダー / ファーム日本選手権)を参考に、ヨシラバー側では親子構造・カード・検索・内部リンクで再整理。Cloud Build `30a851bb-a2cb-497a-83a7-49420a98de90` SUCCESS、image `data-site-publisher:farm-cluster-170fc801-20260607`、Cloud Run Job `data-site-publisher-nlr6n` SUCCESS。WP page: farm `85088`、child `85089`〜`85095` created。Cloud Build public verify `44d3ef7e-a9fb-4b09-a40a-81dc34d84720` SUCCESS: `/data/farm/` `/data/farm/schedule/` `/data/farm/players/` top card all expected text found。
- **トップページ導線 LIVE_DEPLOYED**: `yoshilover-063-frontend.php` version `0.21.2` に更新し、トップ「巨人 選手データ・成績」に `2軍試合日程・結果` → `/data/farm/` を追加。7カード化のため grid を `repeat(auto-fit,minmax(126px,1fr))` に変更。WP plugin self-update 成功、cache clear 済。WP REST readback: version `0.21.2`、`2軍試合日程・結果` / `/data/farm/` / `歴代ドラフト` present、`今日の注目選手` absent。
- **tests**: `python3 -m py_compile src/data_site_farm_source.py src/data_site_template_farm.py src/data_site_publisher.py` OK、`php -l src/yoshilover-063-frontend.php` OK、`python3 -m pytest tests/test_data_site_farm.py tests/test_data_site_template_cluster.py tests/test_front_home_data_links.py -q` 28 passed。

## 2026-06-07 — 469 X-post + SNS cost guard deploy

- **469 SNS realtime 21:15 fast path LIVE_IMAGE_UPDATED**: user「21時15分まで15分に一回でいい」を反映。SNSリアルタイムページは 18:00〜21:15 まで15分間隔。21:30 / 21:45 は `rss_fetcher_redundant_realtime_skip` で早期終了。試合中の :15/:30/:45 は SNS page upsert のみ実行し、RSS記事生成 / Gemini / 下書き作成へ進まない。Cloud Build `164dbed7-02ce-4507-92ee-37e959f21948` SUCCESS、image `yoshilover-fetcher:sns-2115-3edb27c3-20260607`、digest `sha256:9729d88c1a6aebe64eea499ff6a33c04df591913bfcb23aaee9cfd5e7d83774a`、Cloud Run service `yoshilover-fetcher` revision `yoshilover-fetcher-00512-qn6` 100% traffic、`/health` OK。Scheduler/env/Secret は不変。tests `tests/test_sns_realtime_topic.py` + `tests/test_sns_realtime_topic_classifier.py` 40 passed。
- **469 XPOST/SNS schedule efficiency LIVE_IMAGE_UPDATED**: user「朝は7時からでよい」「月曜日は試合がない」を反映。`run_x_post_mail.py` で 7:00 前は DB download 前に `exit 0`、月曜の試合前 / スタメン / 試合中 / 試合後 timing window も DB download / RSSHub / Gemini 前に `exit 0`。解除 env は `X_POST_MAIL_ALLOW_BEFORE_7AM=1` / `X_POST_MAIL_ALLOW_MONDAY_GAME_WINDOWS=1`。Cloud Build `cabf7277-35c8-4074-8f41-80c76fe6f959` SUCCESS、image `x-post-mail-lane:469-skip-ce38d111-20260607`、digest `sha256:f3844ffdae151afdb9b6052746316a082948800f5becbc8fb8915e72d24b43d7`、Cloud Run Job `x-post-mail-lane` generation `162`。Scheduler/env/Secret は不変。targeted test `MondayNoGameWindowTests` 5 passed。full `tests/test_x_post_mail.py` は既存 `BuildQuoteRtCommentTests.test_returns_comment_post_api` の voice_quality gate で 1 fail(今回変更外)。

## 2026-06-04 Phase 2 — /data/record 記録室ハブ(共有部品再利用)+ ⑤ defer

- **/data/record 記録室ハブ LIVE_VERIFIED**(設計§7.3「ライバル最大moat」): `build_record_room`(data_site_query)が共有部品 alltime_ranking を閾値filter。クラブ=名球会2000安打/300本塁打/1000打点/名球会200勝/2000奪三振。OB684+現役、現役★。cluster nav に 🏛記録室 追加。commit `c99689f9` / image `record-room-c99689f` / exec `data-site-publisher-cvcgq`。**page79935 verify**: 記録室h1/名球会2000安打/王貞治868本/金田200勝/坂本★現役/cluster nav 🏛記録室リンク 全✓。test 記録室2+data-site60 pass。
- **⑤ ホット&コールド = 実装(draft、user受入試験へ)**: user「自律で回して受入試験は後で」を受け、draft安全モードで実装。`hotcold_article.py` が既存 `detect_batter_recent_window_anomaly` を再利用(直近5 vs 過去全試合 打率z-score、再発明なし)。ファンサイトvoiceで **HOT(絶好調)のみ記事化**、COLD非記事化。title「{player} 直近5試合 打率.450、絶好調」。env `DATA_INSIGHT_HOTCOLD=1` gate・draft既定。**LIVE_VERIFIED**: image `hotcold-a48bc1a` / exec `insight-nightly-b9rcw` / draft `79938`「カナリオ 直近5試合 打率.450、絶好調」/ error0。今日のヒーロー(単一試合)とは別角度(直近トレンド)。受入試験で要否判断可。

## 2026-06-04 設計 ⑥ = データブロック(ここで自律停止)

⑥ 現役vsレジェンド対比(同年齢時点の通算比較)は **OB の年度別データが必須**だが、`ob_legends_full` は career総計のみ(years は文字列、年度別なし)。→ 684 OB の年度別 scrape が前提。fact精度critical(age計算誤り=致命的NG)+ 大scope(684 scrape)= quick loopでなくデータ基盤案件。設計も「年度別精度検証してから」と gate。**user 判断(着手するか/scope)待ちで停止**。
**設計 data-articles-no1 は ⑥(データブロック)を除き全項目 LIVE 完走。**

→ **作業タスク化済**: `doc/waiting/471-DATA-ARTICLE-legend-comparison-data-prereq.md`(status=BLOCKED_USER)。README board・仕様 §10 に着手手順(案A PoC=21名検証→684拡張→⑥実装)記載。次の判断=案A PoC に GO するか。
- **§16-B 漏れ修正**(user「ちゃんと直ってる?」指摘): 球団打率タイトル「巨人 4/6 位 0.215」の先頭0未除去を `fmt_stat` で `.215` に。commit `685b63c2` / image `team-avg-fmt-685b63c` deploy + prod db verify。「4/6位」は6球団分母有意で保持(別判断)。

## 2026-06-04 Phase 1先頭 — ② 節目カウントダウン(現役通算記録接近)

## 2026-06-04 Phase 1 — 全史ランキング計算(共有部品)+ ④ 通算ランキング変動

設計 §7.2「1度作って2用途」の共有部品 + ④記事。
- `src/analysis/alltime_ranking.py`: OB684 + 現役を横断し本塁打/安打/打点/勝利/奪三振の全史ランキング算出。OBは年度別不在で球団限定不可 → **NPB通算**で揃え正直表記(球団通算と誇張しない)。snapshot を GCS `alltime_rank_snapshot.json` 保存(④の前日比較用、google.cloud.storage=既存ingestと同方式)。
- `src/analysis/career_rank_change.py`(④): 前回snapshot比較で順位上昇検知(band[10,20,50,100]またぎ or today_rank<=50)。title「NPB通算{label}{value}、歴代{rank}位に浮上({抜いた相手}を抜く)」。初回はbaseline保存のみ記事0。env `DATA_INSIGHT_RANK_CHANGE=1` gate、既定draft、X§11。
- 実データ検証: 全史HR=王868..坂本300(19位)/丸291(20位)、丸301本シナリオで「丸佳浩 歴代19位に浮上(坂本勇人を抜く)」生成確認。
- commit `c8c9d727` / test 8 + 関連85 pass / regression 0。**LIVE_VERIFIED**: image `rank-change-c8c9d72`、env `DATA_INSIGHT_RANK_CHANGE=1`、exec `insight-nightly-vnbcl`、error0、baseline snapshot `alltime_rank_snapshot.json`(15.8KB）GCS保存=初回記事0(正しい挙動)。実順位変化で発火、生成はsim実証済。
- ~~既知gap: 岡本 career total 空~~ → **訂正(source確認)**: 岡本/菅野は2026 roster不在(MLB)でcurrent非収録が正、ob_legends_fullにOB収録済で全史HR22位248本に正常掲載。バグでない(parse失敗は誤診)。
- **/data/ranking 歴代(全史)タブ LIVE_VERIFIED**(共有部品の2用途目): `build_alltime_leaders`(data_site_query)→ render_ranking_html に3つ目section。OBレジェンド+現役横断、★現役マーカー。commit `4113ee74` / image `data-site-publisher:alltime-rank-4113ee7` / exec `data-site-publisher-plzdl`。page76423 verify: 歴代section/王貞治868本/金田正一/★現役凡例。data-site test 58 pass(画像smoke1 failは cairosvg未導入の既存事象・無関係)。
- **設計 Phase 1 完了**(②/共有部品/④/site全史タブ)。次=Phase 2: /data/record 記録室ハブ + ⑤ホット&コールド。

## 2026-06-04 設計Phase 1先頭 — ② 節目カウントダウン(現役通算記録接近)

設計 `data-articles-no1-design.md` §2②。現役の通算記録が節目に接近したら記事化。
- `src/analysis/career_milestone.py` 新規: npb_career cache(467）の通算total read(scrape不要・publish非ブロック）→ 次節目まで残り<=window(打者30/投手10）かつ>0を抽出。title case C「通算{value}{unit}、{milestone}{unit}まであと{n}」。
- dedup: titleに残り数を含めtitle再利用で「残り変化時のみ再掲」自然成立。env `DATA_INSIGHT_CAREER_MILESTONE=1` gate(default OFF)+ 既定draft。X解放§11。
- insight_nightly に③直後で配線。prod cache検証: **丸佳浩 本塁打291→300(あと9)/盗塁188→200(あと12)** が現候補。
- commit `e2992366` / test 8 + 関連99 pass / regression 0。
- **deploy LIVE_VERIFIED**: image `career-ms-e299236`、env `DATA_INSIGHT_CAREER_MILESTONE=1`、exec `insight-nightly-gqp2g`。draft `79867`(丸291本→300あと9）/`79868`(丸188盗→200あと12）生成、丸の顔写真eyecatch、error0、draft(公開影響ゼロ)。
- 次: Phase1続き = 全史ランキング計算(共有部品）→ /data/ranking通算タブ + ④ランキング変動(1部品2用途)。

## 2026-06-04 データ記事 Phase 0 再開 LIVE_VERIFIED

設計 `mkdocs_docs/spec/data-articles-no1-design.md`(6/3）の Phase0 を本線再開。
- **§16監査(read-only)**: 直近30本6軸集計。核心発見 = **6/3 commitの §16-B/C/D/E/F fix群が未deploy**(稼働image `1fd809ca` がfix前、検出崩れは全てfix前公開分=forward-only解決済）。
- **新規§16 fix 2件** commit `ffe1b091`: `setup/closer`英語token→中継ぎ/セットアップ/抑え、③本文の誇張「記録保持者だ」→「巨人OBだ」(test18 pass)。
- **③今日は何の日(OB)本番起動**: env `DATA_INSIGHT_OB_ANNIVERSARY=1`(status draft既定維持)。今後60日35日/50本(松井秀喜/張本勲等)、今日6/4は0本、初弾6/7岡崎郁。
- **deploy**: image `insight-nightly:ob-anniv-s16-ffe1b09`、job update + execute `insight-nightly-x6ctg` SUCCEEDED、error0。1 deployで「③起動 + 未deploy §16 fix群live + 本日2 fix」を集約。
- **LIVE verify**(新draft): `setup→セットアップ`反映確認(post79846)、dedup機能、AUTO_PUBLISH=0で公開影響ゼロ。
- 次パス observation: 球団系title「巨人 4/6 位 0.215」(.360/順位N/M が6チーム文脈で未適用、borderline)。
- handoff: parent `session_logs/2026-06-04_data_articles_phase0_s16_audit_and_ob_anniversary.md`。
- **user判断境界(未到来)**: ③ draft→publish昇格(6/7初弾draft確認後）/ ③ X投稿解放。
- **次の本線**: 設計Phase1 = ② 節目カウントダウン → 全史ランキング計算(共有部品)→ ④ランキング変動。

## 2026-06-03 cross-session lane 調整(重複回避)— 並走セッションへ

「ライバル(my-favorite-giants)にあるもの全部作る」= parity は `spec/data-site-rival-parity.md`(468 backlog)が正本。差別化(鮮度・発見・ファン記事)は post エンジン側(462-466)。lane を 1 本ずつに分けて二重作業を避けたい。

**このセッション(A)の lane 宣言** = データ記事 **post エンジン**:
- write scope: `src/analysis/anomaly_article_publisher.py` / `insight_anomaly_detector.py` / `insight_contrast_title.py` / `config/insight_whitelist.json` / `tests/test_insight_*`
- 着地済: 464 再活性化 / 465 v1 発見ドリブン title(commit `1fd809ca`, image `insight-nightly:case-e-contrast-1fd809ca`)
- 次候補: 463 サヨナラ/逆転/殊勲打 detector

**並走セッション(468 = data-site parity)へ 5 問**:
1. 今 in-flight と次の 1 本は?(468-1 通算ランキングは `[x]`。spec 順だと 468-2 ドラフトだが直近 commit は「468-2 通算節目」表記=spec 468-8 とズレ。実番号で何を作っているか)
2. post エンジン(`anomaly_article_publisher` / `insight_anomaly_detector` / `insight_whitelist.json`)を触る予定はあるか?(= A lane、触らないでほしい)
3. 書き込み先 file/dir は `data_site_*` 限定か?(disjoint なら並走OK、§31-B)
4. 463(サヨナラ/逆転/殊勲打 detector)を作る予定はあるか?(あれば A は別角度へ回る)
5. commit/push の cadence は?(§31-D commit便直列、同時 push 回避)

→ 回答は本節に追記 or session_log で。確定後、A は 463 着手 or 別角度へ。

## 2026-06-02 session update

### 460 — cluster 選手名検索box LIVE(検索sub-item、`<script>`保持懸念解消)

/data/ に client-side インクリメンタル検索。全テーブルの `/data/` リンク行を選手名で絞り込み(全角空白除去・部分一致・0件表示)。progressive enhancement(JS無効でも全リスト保持)。
`<script>`除去懸念は解消: publish ユーザ `unfiltered_html` で実行JSが**公開HTMLまで生存**を実ページ確認。
commit `bd7cdc64` / image `data-site-publisher:search-box-bd7cdc6` / execute SUCCESS。cluster+publisher 25 pass。
460 残: zero-row 抑制(user 判断)/ game-detail team_role 検証。doc: `doc/active/460-...md`。

### 464 — 眠り角度の再活性化(読者にわかりやすい4種を厳格gate付き)LIVE

検証で「眠り角度=事故ではなく全て日付つき user 指示で OFF」と判明。「わかりやすさ」基準で選別再活性化。
ON(whitelist◯): 今日のヒーロー打者(gate厳格化 H>=3/HR+RBI2/RBI3/マルチHR)/ 今日の好投(真QS IP>=6&ER<=2)/ 本塁打ペース / 連続マルチ安打。
据え置き(わかりにくい=whitelist×): BABIP / FIP-ERA / 変化率 / 規定外好調。
bug fix: pace_hr/multi_hit の `_resolve_team_code_from_name` 未import NameError(dormant で未顕在)を配線。
commit `00e795fa`(本体)+ `ecc6eb0e`(fix)/ image `insight-nightly:hero-reactivate-ecc6eb0`。
prod read-only 検証: pace_hr 巨人=1(キャベッジ26本ペース)/ 非巨人は priority<=2 gate で除外=乱発なし。
test 32 + insight/anomaly 917 pass / regression 0。doc: `doc/done/2026-06/464-...md`。次回 insight-nightly 発火で記事化。

### 467 — 選手pillarに年度別成績+通算+プロフィール(NPB公式 career scrape、網羅)LIVE_VERIFIED

user「467で情報量を網羅させる」。NPB career page の全情報を網羅取得・描画。
打者23列 / 投手24列 年度別+通算(移籍履歴含む)+ プロフィール(生年月日/身長体重/投打/経歴/ドラフト)。
commit `e0fa0c15` / image `data-site-publisher:career-history-e0fa0c1` / Job `data-site-publisher-4mzq5` SUCCEEDED。
cache = 別GCS object `npb_career.json`(284KiB、insight.db同梱は upload race 回避)、publisher内 staleness gate 20h で日次1回scrape、publish非ブロック。
LIVE verify(WP REST): `/data/togo-shosei`(投手24列+防御率+投球回)/ `/data/sakamoto-hayato`(打者23列+出塁率+併殺打)。
test: 新規9 + data-site全219 pass / regression 0。doc: `doc/done/2026-06/467-...md`、handoff: parent `session_logs/2026-06-02_data_site_467_career_history.md`。

## 2026-06-01 session update

### 447 — data-site metric #5 イニング別 (序盤/中盤/終盤 別打率) LIVE_DEPLOYED_VERIFIED

commit `7c792bd` / image `data-site-publisher:inning-split-7c792bd` / Job execution
`data-site-publisher-5sv85` SUCCESS。 `batting_logs.atbats_json` (index=イニング) を
read-side only で parse、 序盤(1-3回)/中盤(4-6回)/終盤(7-9回) の打率を pillar に追加。
ETL/backfill 不要・¥0。 classifier は production 全 5,652 行で AB/H 照合済 (誤分類ゼロ、
差分は同一回 collision のみ)。 live verify `/data/yoshikawa-naoki` 序盤 .194 / 中盤 .208 /
終盤 .286。 data-site test 62 passed。

447 で read-side only に解ける metric は #2 venue + #5 inning の 2 個で打ち止め。
残り #1 RISP / #3 vs左右 / #4 カウントは at_bat_details.batter_canonical backfill
(Phase A) 必須で BLOCKED 継続。 詳細 = parent `docs/handoff/session_logs/2026-06-01_data_site_447_inning_split.md`。
> ⚠️ 2026-06-01 PM 深掘りで訂正: 上記「backfill 必須で BLOCKED」は過大。チーム横断の vs左右/RISP は既に nightly LIVE、Pillar も read-side fuzzy match で backfill 不要(457 参照)。

### data-site 再設計 + 深掘り gap 分析 + 実装チケット6本(設計フェーズ完了)

user 「サイトマップとワイヤーフレームで UIUX」「トピクラ導線」「何が負けているか深く分析」。
- モデル2サイト(my-favorite-giants / baseballdata.jp)を11班で実クロール網羅 → `doc/reference/model-site-page-inventory.md`
- 設計正本(サイトマップ/トピクラ三方向導線/ワイヤーPC・スマホ/UIUX/コンポーネント/SEO/gap分析§12/根本原因+effort§13) → `doc/active/455-DATA-SITE-redesign-sitemap-wireframe-uiux.md`(GH #119)、spec `mkdocs_docs/spec/data-site.md` rev7
- 実装チケット(全て READY、設計のみ・未着手):
  - **456** 投手split横展開 (S, GH#120) — 最大の見た目改善・最安、ETL不要
  - **457** Pillar vs左右/RISP (S〜M, GH#121) — 447 re-scope、read-side で backfill不要
  - **458** 専用layout+トピクラ三方向導線 (M, GH#122)
  - **459** /data/team順位表+schedule未来試合 (M, GH#123) — 454包含
  - **460** cluster UX(検索/今日の注目/zero-row)+team_role bug (S〜M, GH#124)
  - **461** 既存snapshot SABR表示 (S部分, GH#125)
- 主要訂正3点: 投手split=未実装(ETL非該当・横展開S) / 447 BLOCKED=半分誤り(チーム横断既LIVE、Pillarはread-side) / fill率70%(捕手50%)=バグでなく出場機会。
- 留保: fill率実数値・投手イニング生データ・team/schedule内容深部は production verify 必要。

### データ記事 深掘り(生成エンジン実態)+ parity→差別化 実装順 + チケット462-466 追加

深掘りで判明: /data ページと別に **`【巨人データ】`記事の量産エンジンが実装済**(`insight_nightly.py`+publisher3本+detector+dedup349+gate356)。LIVE角度は広い(z-score/守備/連続記録/順位変動/各ランキング/counting/本拠ビジター/vs球団/vs左右/イニング/RISP/カウント/チーム系)が、**阻害4点**: ①角度の約半分が空固定で未生成 ②title機械f-stringで発見表現不可 ③`ENABLE_DATA_INSIGHT_AUTO_DRAFT`(default0)依存=prod ON要verify ④サヨナラ/逆転/殊勲打は派生可能だが検知コード0。

user 方針: **まず parity(ライバルにあるもの)→ それに差別化4点**。追加チケット(全READY・未着手):
- **462** ランキング面新設(parity, GH#126)
- **463** 状況系新角度detector サヨナラ/逆転/殊勲打/得点差別(parity+差別化, GH#127)
- **464** 眠り角度の再活性化(差別化A, GH#128)
- **465** title発見ドリブン化(差別化C, GH#129)
- **466** エンジンON verify+新鮮さ(P1/verify先行, GH#130)
parity不可(土俵を降りる): pitch-level・選球眼・歴史網羅・通算・年度別・プロフィール。
設計正本 455 §16(エンジン実態)/§17(parity→差別化順)、mkdocs `spec/data-site-redesign` 同期済。

## 2026-05-29 session update

### 445 — SNS リアルタイム title SEO 安定化 + 大手 source 追加 (LIVE_DEPLOYED 2026-05-29 10:20 JST)

2 件を 1 deploy で反映。 revision `yoshilover-fetcher-00505-56r` / image `sns-major-src-92aaac1` / `/health` 200。

1. **title 日付化** (commit `3234659`): 分単位時刻を title から除去、 `巨人 SNS リアルタイム (一軍) YYYY-MM-DD` へ。 1日4回 upsert でも同日内 title 不変 = SEO title churn 解消。 本文 hero banner の HH:MM 表示は鮮度シグナルとして維持。
2. **大手 source 追加** (commit `92aaac1` → `01e579b`): source を巨人専門 4 + 大手 general 5 の **計 9 アカウント**へ拡張。
   - 巨人専門 4 (全件通過、 不変): `TokyoGiants` (球団公式) / `yomiuri_giants` (読売) / `hochi_giants` (報知) / `Sanspo_Giants` (サンスポ)
   - 大手 general 5 (巨人 relevance filter 適用): `sponichiyakyuu` (スポニチ野球) / `nikkan_yakyuude` (日刊野球取材基地) / `Daily_Online` (デイリー) / `sponichiannex` (スポニチ公式) / `nikkansports` (日刊公式)
   - filter = `is_giants_relevant`: 巨人/ジャイアンツ keyword or 巨人 roster alias or **元巨人 OB MLB allowlist (岡本/菅野、 user 判断 2026-05-29)** を含む post のみ通過。 大谷翔平 等 非元巨人 MLB は roster/allowlist 不在で drop。
   - 追加コスト ¥0 (RSSHub 既存、 X API 不要、 LLM 不使用)。

deploy: image `sns-ob-mlb-01e579b` (Cloud Build `5605f621` SUCCESS) / revision `yoshilover-fetcher-00506-xcc` / `/health` 200。

tests: 33 passed (`is_giants_relevant` の keyword / OB allowlist / 大谷・阪神 drop を追加)。 実データ smoke (filter 後 kept): sponichiyakyuu 2 / nikkan_yakyuude 8 / Daily_Online 1 / sponichiannex 2 / nikkansports 1 = 計 ~14 件。

next: **13:00 JST 自然 fire** で (a) title が日付のみか、 (b) 一軍 page の post 件数が大手 source 分増えたか、 (c) 他球団・大谷ノイズ混入なしか、 (d) 岡本/菅野 OB post が拾えているか を Cloud Logging `event=sns_realtime_topic_result` で確認。

## 2026-05-28 session update

### 443 / 444 — 巨人選手データサイト Phase 1.5 完成 + back-link 注入 (LIVE_DEPLOYED 2026-05-28 PM4)

**状態**: Phase 1.0 → 1.5 + Phase 2 (back-link) 全完成、 live 稼働中、 user 受け入れ試験 pending。

**完了 phase**: Cluster (1) + Pillar (31) + 打順別 + vs 球団 + streak + 投手 stats + 既存 301 記事 back-link + daily cron + placeholder 具体化 + 8 player WP tag 修復

**live infra**: data-site-publisher Cloud Run Job (3 schedule: 6:00/17:30/23:00 JST) + data-site-backlink-daily (7:15 JST)、 cost ¥45/月

**受け入れ試験 URL**: `/data/` (Cluster) / `/data/yoshikawa-naoki/` (打者) / `/data/togo-shosei/` (投手) / `/data/sakamoto-hayato/` (placeholder) / `/73041/` (back-link aside)

**GH issues**: #115 (443 master) / #116 (444 impl) / #117 (447 defer = data-insight lane 修復) / #118 (446 defer = Phase 1 full)

**spec doc**: `mkdocs_docs/spec/data-site.md` rev5 §16 進捗 section に詳細

**defer (user 判断後)**: ticket 447 (data-insight lane 修復、 元 id 445 → 別 thread の 445-SNS 衝突回避で 447 rename) / 446 (Phase 1 full 拡大、 推奨 option D = 観察後) / noindex 適用 (Yoast REST 制約、 user 手動 5 分)

**handoff**: parent repo `docs/handoff/session_logs/2026-05-28_pm4_data_site_phase1_5_complete.md`

### 445 — 巨人 SNS リアルタイム話題 daily aggregation (READY 2026-05-28 PM、 user GO 済)

user 「SNSページをページにはしたいが、 コンテンツがたりない」 → Yahoo リアルタイム検索の **巨人専門 1軍/2軍/3軍 版** を作る方針 lock。

**スコープ確定の流れ (本 session 圧縮)**:
- 当初提案 = 公式アカウントの X 投稿を集約 (球団 + 報知 + サンスポ + ...)
- user 「数が多いので専門メディアだけ抽出」 → source 4 account (`yomiuri_giants` / `TokyoGiants` / `hochi_giants` / `Sanspo_Giants`) に絞り込み
- user 「トレンドの項目も置きたい。 出てきた選手名のタグを並べる、 一日のトップに」 → 記事最上部に トレンド section (上位 15 名、 言及 2 回以上)
- user 「コーチと監督もね」 → roster 全 136 名 (player 84 + coach 27 + manager 1 + shihaikako 1 + ikusei 23) を トレンド count 対象に
- user 「スケジュールを追加するとお金がかかるから今のスケジュールの時間帯に日別で追加」 → 既存 `giants-weekday-daytime` / `giants-realtime-trigger` に内部 time gate で相乗り (10/13/17/21 JST)
- user 「要は金がかからない方法」 → RSSHub 経由 (X API 不要、 LLM 不要、 oEmbed render) で **追加コスト ¥0** path 確定

**コスト** = ¥0 / 月 (新 Scheduler / Job / API call / LLM 全部なし)。

**実装 file 新規** (5):
- `src/sns_realtime_topic.py` (main、 fetch + 分類 + render + WP upsert)
- `src/sns_realtime_topic_classifier.py` (一軍 / 二軍 / 三軍 + roster alias match)
- `src/sns_realtime_topic_template.py` (jinja template)
- `tests/test_sns_realtime_topic.py`
- `tests/test_sns_realtime_topic_classifier.py`

**触らない**: 既存 article path / 既存 Scheduler 設定 / WP frontend CSS / X live posting / featured_media rule / 個人 X / 野球全般アカウント (`SponichiYakyu` / `nikkansports` / `npb`)。

doc: `doc/active/445-SNS-realtime-topic-daily.md` / spec: `mkdocs_docs/spec/sns-realtime-topic.md` (mkdocs nav 追加済、 `127.0.0.1:8000` で preview 200 OK 確認済)。

next: Claude 自律で 445 実装着手 (classifier → main → template → tests → fetcher hook → image rebuild → deploy)、 翌日 4 fire 観察で 受け入れ条件 verify。 GH Issue 作成は本 session で並行。

**実装完了 2026-05-28 15:00 JST**:
- impl commit `da588c8` (3 module 新規 + 5 test 新規 + fetcher hook、 23/23 unit tests PASS)
- Cloud Build `a3cfa6cc` SUCCESS (2m36s)、 image `sns-realtime-da588c8`
- Cloud Run revision `yoshilover-fetcher-00498-547` deploy 完了、 100% traffic、 `/health` 200
- env `ENABLE_SNS_REALTIME_TOPIC=1` 設定済
- 初回 fire = **2026-05-28 17:00 JST** (既存 `giants-realtime-trigger` の 17:00 fire に相乗り)
- smoke (local): 過去 24h 59 件 / 一軍 54 / 二軍 2 / 三軍 3 / トレンド 27 名

verify: 17:00 JST 以降 Cloud Logging で `event=sns_realtime_topic_result` 探す、 WP で slug `giants-sns-realtime-2026-05-28` の draft が作成されたか確認。

### 443 — 巨人選手データサイト (topical cluster 構造 / 毎日更新) (READY rev3 2026-05-28 PM2、 user GO 済)

rev 履歴:
- rev1 廃止: 既存記事 → SEO long-form 月 1 回案
- rev2: user 「データサイト作って index 化、 毎日更新、 選手全員」 で per-player static page 方式
- **rev3 (本版)**: user 「今あるDBから記事生成、 球団全体=クラスター、 選手=ピラー、 日々=速報トピック」 + 「コンセプトは大手メディアでは作れない」 で **topical cluster 3 階層 + 大手差別化 4 理由** を明文化

**rev3 採用案** = 3 階層 topical cluster:
- **Cluster** `/data/` (1 page、 全 player hub)
- **Pillar** `/data/{player-slug}/` (~110 page、 player ごと 1 URL、 daily 6:00 JST upsert)
- **Topic** 既存 ~73,000 + 新規 daily 速報 (Phase 2-3)、 Pillar back-link で authority 集中

**大手差別化 4 理由** (yoshilover の堀):
1. cost (110 名 daily = 人手不可、 AI Gemini で月 ¥30-50)
2. focus (大手は 12 球団分散、 yoshilover は巨人専門で一軍/二軍/育成まで)
3. fan voice (大手は事実中心、 yoshilover はファン感情寄り短評を AI で安全挿入)
4. 永続 baseline + cluster (大手は記事量産型、 yoshilover は per-player 永続蓄積 + 既存 73,000 に back-link 自動注入)

**phase 分け**: Phase 1.0 (Cluster 1 + Pillar 3 = 4 page、 **吉川尚輝 / 坂本勇人 / 丸佳浩**、 user 指定) → Phase 1.5 (一軍 30) → Phase 1 full (110) → Phase 2 (既存 73,000 に back-link 注入) → Phase 3 (日々の data 速報 Topic 自前産出) → Phase 4 (column long-form)。 Phase 1.0 着手は **user GO 済**、 初回 fire = 2026-05-29 (木) 6:00 JST 想定。

doc: `doc/active/443-DATA-SITE-daily-per-player-pages.md` (rev3) / `doc/active/444-DATA-SITE-phase1-mini-impl.md` (Phase 1.0 実装計画 rev3 反映) / spec: `mkdocs_docs/spec/data-site.md` (rev3、 mkdocs nav 更新済、 `127.0.0.1:8000` mkdocs serve で preview)。

コスト: Phase 1.0 ¥1-2/月、 Phase 1 full ¥30-50/月 (Gemini Flash Lite + Cloud Run 無料枠内)。

next: Claude 自律で 444 実装着手 (`src/data_site_publisher.py` + `data_site_template_cluster.py` + `data_site_template_pillar.py` + Dockerfile + cloudbuild + Scheduler `data-site-publisher-daily`)、 2026-05-29 6:00 初回 fire、 2-3 週間観察後 Phase 1.5 拡大判断を user に報告。

### 439 — DATA-INSIGHT publish queue restore 7 signals (LIVE_DEPLOYED_VERIFY_PENDING 2026-05-28 10:38 JST)

user 報告 「データ記事 (ポスト編) が同じネタばかり」 の真因 fix。 5/15 commit `f8c9e57` で `ALL_ANOMALY_SIGNALS` から drop されていた 7 種 detector (BABIP / FIP / GIANTS_TOP / PACE_HR / HIDDEN_OPS / HIT_STREAK / STAT_DELTA) を復活、 publish queue の signal mix を 8 → 15 entries に拡張。 commit `c413725` (5/27 landed)、 5/28 10:38 JST deploy: Cloud Build `9f055d05` 2m26s SUCCESS、 image `insight-nightly:signals-restore-c413725`、 Cloud Run Job `insight-nightly` gen=106→107。 Scheduler 10/12/17/20/21 JST ENABLED 維持、 次 fire = 12:00 JST。 next: 12:00 JST 以降 execution log で signal mix + publish 件数観察、 +1 day で BABIP / FIP / STAT_DELTA の whitelist block 状況確認 (block で 0 件なら whitelist 更新 follow-up 起票)。 推定 +30-50% draft 量、 detector 計算 cost 増無し、 publish 数増による Cloud Run guarded-publish / mail / WP REST 増 minor。 doc: `doc/active/439-DATA-INSIGHT-publish-queue-restore-7-signals.md`。

## 2026-05-27 session update

### 776252d — 監督・コーチ ヨシラバー voice 対象拡張 (CLOSED LIVE_DEPLOYED_VERIFIED 2026-05-27)

x-post-mail-lane の GEMMA_BRANDING / build_x_post_from_article_info gate を **active member (player + manager + coach)** へ拡張。 giants_roster.json に三軍 7 + 巡回 2 = 9 名追加、 73 橋上秀樹 を 監督代行 に更新 + alias 4 個、 阿部慎之助 に「阿部前監督」 alias 追加。 commit `776252d` / image `x-post-mail-lane:member-gate-776252d` (build `40f1cfab` 1m50s SUCCESS) / Cloud Run Job gen=83。 smoke `x-post-mail-lane-tqc6j` で実 build 4 candidates、 旧 skip 全件 verified=True。 spec doc `mkdocs_docs/spec/x-post-mail.md` 追記 (persona / member gate / 5 型 / postgame 救済 path)。

### 438 — X-post comment 候補 画像添付 brand_opinion + brand_quote (IN_FLIGHT, Phase 1+2 実装 deploy 済、 観察中)

scope: x-post-mail-lane の comment 系候補 (GEMMA_BRANDING / build_x_post_from_article_info) に毎時 fire で image 添付。 Pattern A=brand_opinion (反応元 og:image + ヨシラバー voice text)、 Pattern B=brand_quote (引用元 og:image + 「発言者名「literal 60-180 字長 quote」」)。 共通: source 画像 native aspect / 強制 crop なし、 画像内 brand mark なし、 出典は alt text。 post text は URL / ハッシュタグ / 媒体名 含めない (現 hard rule 維持)。 新規 Cloud Scheduler / Cloud Run job は作らない (¥10/月/job 削減 lock 維持)。 prerequisite=5/27 776252d (member gate)。 doc: `doc/active/438-XPOST-brand-opinion-and-quote-images.md`。

**実装 commit (5/27 - 5/28, 計 11 本 + 前段 1 本)**:
- 前段 `2049640` 若手 7 名 eyecatch scrape upload
- Phase 1 `b63888c` comment 系候補に og:image 自動添付
- fix `bdcba6a` og_image_fetcher gzip decompress bug (sanspo / hochi)
- Phase 2 `6a59de6` Pattern B 引用 overlay (人物名「long quote」)
- fix `cae5066` Pattern B speaker proximity check で mis-attribution 防止
- fix `5a0729b` navigator.share / X intent で空 URL を送らない (iOS Safari)
- fix `ea23382` post_text 末尾「(出典 @handle)」削除
- fix `bf56300` 画像 alt_text「引用元: 媒体名」削除 (user 仕様)
- docs `3184a91` Phase 1+2 + GCS lifecycle を `mkdocs_docs/spec/x-post-mail.md` に追記
- fix `38b0085` Android Chrome share-x-cand URL 漏出 fix (history.replaceState)
- fix `26b95db` Pattern B 成立率改善 (long_quote_extractor 閾値緩和)

**deploy 状況 (2026-05-28 10:32 JST 時点)**: image `pattern-b-relax-26b95db` (Cloud Build `4d0f3cd8` SUCCESS) / Cloud Run Job `x-post-mail-lane` gen=91。 5/28 doc backfill 直後の verify で `26b95db` 未 deploy 判明 → 同 session 内で rebuild + Job update 完了。

next: (1) 11:00 JST 以降の自然 fire で実 Pattern A / Pattern B 成立比率と speaker mis-attribution / URL 漏出 / overlay 可読性を観察、 (2) 24h `gcloud billing` 実測 verify (画像生成 + GCS upload で課金 ¥0 想定の追認)、 (3) 観察で問題なければ CLOSED に遷移 + doc を `doc/done/2026-05/` へ移動。 件名/scope 拡張 (本文中 `<img>` フォールバック等) は別 ticket 起票。

## 2026-05-23 session update

### 428 — XPOST branding requirements v2

| ticket | status | owner | 内容 |
|---|---|---|---|
| `doc/active/428-XPOST-branding-requirements-v2.md` / GH Issue #98 | USER_HEARING_CAPTURED | user / Claude / Codex | user hearing を反映。ヨシラバーは「データに強い巨人ファン」+「試合中の空気を拾う観戦仲間」。Source A は RSS 要約ではなく、180-280 字 / 2-3 行 / fact 1 + 観戦感 1 + ファン感情 1 / 次に見たい点へ着地するヨシラバー voice に再定義。Source B(418 case B) / Source C(specialized DB slices) は DB 表ポストとして Gemini 上書き禁止。415 の左右投手は DB がある例で、左右投手に固定しない。優先はファンが欲しいデータポスト。同一選手の重複回避 / player rotation も要件化。記事作成 policy 423 / metric whitelist / dedup / diversity rule は article version の材料として使い、記事 title / 本文の短縮ではなく X 用 post version の `post_text` へ変換する。Tavily REST 禁止。code / deploy / env / Scheduler / WP / X live post は不可触。 |

### 429-434 — XPOST branding v2 child tickets

| ticket | status | owner | 内容 |
|---|---|---|---|
| `doc/active/429-XPOST-source-b-db-ranking-fixed-table-player-rotation.md` / GH #99 | PARTIAL_REPO_IMPL_TESTED | Codex B | Source B(DB表) を final `post_text` に維持。X intent本文に `📊` / `TOP` / `巨人最上位` / `🟧巨人🟧` が残る。hashtag行は除外。未完: 同一選手 rotation / 24h player+metric+period の新規強化。 |
| `doc/active/430-XPOST-source-a-yoshilover-voice-validator.md` / GH #100 | PARTIAL_REPO_IMPL_TESTED | Codex B | Source A fallback とコメント×DBを、RSS要約ではなく 180-280字 / 3行 / 確定fact + 観戦感 + 次に見る点のヨシラバー voice に変更。未完: Gemini prompt本体、headline similarity、未確認数字 whitelist。 |
| `doc/active/431-XPOST-source-c-specialized-db-slices-fan-demand.md` / GH #101 | PARTIAL_REPO_IMPL_TESTED | Codex B | Source C specialized DB slice の初期 anomaly flags を追加。sample / 条件表示なしを hard flag。未完: 415 generator、fan-demand scoring、strict/approx実データ fixture。 |
| `doc/active/432-XPOST-source-mix-visibility-skip-reasons.md` / GH #102 | PARTIAL_REPO_IMPL_TESTED | Codex A | mail text/html に Source A/B/C 件数と flags を表示。未完: generation stage の skip reason logging / selected-before-after count。 |
| `doc/active/433-XPOST-post-text-regression-tests.md` / GH #103 | PARTIAL_REPO_IMPL_TESTED | Codex B | X intent URL の `text=` を decode し、mail body / draft_text ではなく final `post_text` を検証するテストを追加。Source B表維持と Source A 3行も確認。 |
| `doc/active/434-XPOST-anomaly-detection-phase1-flag-only.md` / GH #104 | PARTIAL_REPO_IMPL_TESTED | Codex B | Source A/B/C を分類し、短文、DB表崩れ、Source B比率不足、候補数不足、Source C条件不足を flag-only 表示。ML / 外部API / 自動dropは未実装。 |
| `doc/active/435-XPOST-branding-v2-safe-implementation-design.md` / GH #105 | LIVE_IMAGE_UPDATED | user / Codex | user GO 後、`src/x_post_mail_lane.py` / `tests/test_x_post_mail.py` に限定して初期実装。image `x-post-mail-lane:428-branding-v2-b9973f6` を Cloud Run Job `x-post-mail-lane` generation `67` へ反映。Scheduler / env / Secret / WP / X live post は未変更、追加メール回避で手動 execute 未実施。 |
| `doc/active/436-XPOST-top10-data-diversity-farm-sample-gate.md` / GH PENDING | LIVE_IMAGE_UPDATED | user / Codex B | 【Xポスト案 8件】のDB Top10表が同じ選手・同じ指標・同じ期間に偏る問題を、候補metadata / 1軍・2軍・3軍分離 / sample gate / duplicate flags で初期実装。Top10表は維持。2軍/3軍は通常X候補に混ぜない。短すぎるrate系 row は原則X候補から外し、候補が薄くなる場合だけ `参考値・通常目安=規定打席/投球回N以上` と明記してfallback採用する。`直近5試合` 打者は表示thresholdを `規定打席10以上` に引き上げ。follow-upで投手rateの表示を `規定投球回N以上` に統一し、候補不足時でも24h重複選手を戻すfallbackを廃止。tests: targeted 70 passed + follow-up 37 passed、compile/AST OK。Cloud Build `47b155de-8e7c-4cdb-8d4b-23f803329cf2` / `bb4f7c63-535e-447f-b2a4-0ea200586c00` SUCCESS、image `x-post-mail-lane:436-dedup-unit-fix-20260523-2122`、Cloud Run Job generation `69`。env / Secret / Scheduler / WP / X live post は未変更、手動 execute 未実施。 |

### 437 — WP eyecatch + X-post SVG 画像 動的生成

| ticket | status | owner | 内容 |
|---|---|---|---|
| `doc/active/437-WP-XPOST-eyecatch-svg-dynamic.md` / GH #112 | READY | Claude Code | 2026-05-25 PM scope 拡張: 3 → 12 style + format auto-routing + quality gate 10 項目 + 4 phase 構成。design sample 12 + variant `sample9b_3crown` を user desktop `C:\Users\fwns6\Desktop\yoshilover-x-design-samples\` に保存済 (brand: 白 bg / vivid orange `#FF6F00` + gradient / 黒 stripe / 金 ★ / hook line / drop shadow / tabular nums)。Phase 1 = sample1 (ranking) のみ production quality release (commit A: requirements + template + generator + tests / commit B: ranking_publisher 統合 + wp_client.upload_media / commit C: Dockerfile cairo lib + cloudbuild + canary deploy)。Phase 2 = sample2/4/6/9/9b/10 + `x_post_image_router.py` (crown_count / player_count routing)。Phase 3 = 残り 6 + GCS cache。Phase 4 = X media attach + monitoring + A/B (user GO 後)。コスト見積 ¥0/月 (Cloud Run free tier 0.8% / GCS 9% / Network 45%、 LLM 不使用)。post-deploy 24h `gcloud billing` 実測 verify mandatory。env / Secret / Scheduler / WP 既存記事 / X live post は不可触。 |

### 425 / 426 — GCP cost safe cleanup

| ticket | status | owner | 内容 |
|---|---|---|---|
| `doc/done/2026-05/425-OPS-gcp-expired-one-time-scheduler-cleanup.md` | CLOSED_EXECUTED_VERIFIED | Codex A | parent GH Issue #97。過去日 one-time Scheduler 2 件 (`publish-notice-extra-20260517-game`, `giants-game-extra-20260517-1400-1700`) を削除済み。Scheduler count `ENABLED 38 / PAUSED 18` → `ENABLED 36 / PAUSED 18`。通常 fetcher / publish-notice / x-post / fact-check は不変。想定削減は約 $0.20/month。 |
| `doc/active/426-OPS-artifact-registry-safe-cleanup-preflight.md` | PREFLIGHT_STOPPED | Codex A | Artifact Registry `yoshilover` 約 98-103GB の安全 cleanup 前監査。`publish-notice:prefilter-a32bd79` が live image だが cleanup keep tag list に入っていないため STOP。Artifact delete / cleanup policy update は未実施。次は live tag/digest を keep 条件へ追加してから削除候補を作る。 |
| `doc/active/427-OPS-publish-notice-skip-disabled-review-state-fetch.md` | REPO_IMPL_TESTED | Codex A | Cloud Run Jobs 最大 driver の `publish-notice` を、Scheduler 間引きなしで短縮する narrow fix。`DRAFT_ONLY_SCAN_MODE=1` / `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=0` 時に、使わない review 履歴の GCS fetch だけ省く実装 + tests 済み。mail 判定、scan window、env、本番 job は不変。Cloud Run deploy は未実施。 |

## 2026-05-22 session update

### 424 — X-post mail mode unification (IN_FLIGHT)

| ticket | status | owner | 内容 |
|---|---|---|---|
| `doc/active/424-X-POST-MAIL-MODE-UNIFICATION.md` | IN_FLIGHT | Claude Code | 16:00 fire が 2 件 only (queue 417 直結のみ) になった捻れを是正。 `_main_on_queue` を `_main_scheduled` に統合し 1 fire = 1 mail = data ranking + Gemma branding + team roundup + queue 417 を mix。 `--mode` 引数廃止、 旧 PAUSED schedule 5 本 delete。 queue 由来 candidate の unverified_numbers gate を弱 variant に分離して報知 literal 数字を活かす。 |

### 2026-05-22 evening: X-post branding model swap (DONE)

| ticket | status | owner | 内容 |
|---|---|---|---|
| `src/x_post_branding_gen.py:40` 他 (commit `4e8e038`) | DONE_DEPLOYED | Claude Code | X-post branding lane の生成 model を `gemma-4-31b-it` → `gemini-3.1-flash-lite` 切替。 image `x-post-mail-lane:gemini-flash-lite-4e8e038` deploy 済、 24h billing verify pending。 free tier 1,500 RPD / volume 25 req/日 = 1.7% 利用。 Cloud Run runtime 短縮副次効果 ¥1,000-1,500/月 節約見込。 |

### 423 — データ publish ルール集約 SoT (LOCK)

| ticket | status | owner | 内容 |
|---|---|---|---|
| `doc/active/423-DATA-PUBLISH-RULES-CONSOLIDATED.md` (GH Issue #96) | LOCK | Claude Code | データ post の 9 領域 rule (metric / 期間 / threshold / title / dedup / draft / mail / 表示 / site 方向) を 1 file 集約。 5/22 同日 landed した dedup gate 拡張 (commit `d724f0c`) / ERA 「低い順で」 削除 (commit `635cbd8`) / 【まとめ】mail 停止 (env `DISABLE_BURST_SUMMARY_MAIL=1`) / Gemma 4 revert (commit `2af8f0e`) も記載。 個別 rule 変更時は本 file 同 commit 更新する運用。 metric ◯/× SoT は `doc/reference/data-insight-metric-whitelist.md` を維持。 |

### #95 / 417 — ヨシラバー X-post branding 2 source mix + 試合中 15 分 schedule (全 scope 完了)

| ticket | status | owner | 内容 |
|---|---|---|---|
| GH Issue #95 / `doc/active/417-X-POST-MAIL-HOCHI-PRIORITY-PIGGYBACK.md` | DONE (close 候補) | Claude Code | 4 scope 全完了。 (1) Source A voice 統一 = ヨシラバー voice 180-280 字 (commit `9cc08b1`、 image `yoshilover-voice-9cc08b1` deploy 済)。 (2) Source B 維持 = 418 case B format (commit `6ab949f`)。 (3) schedule = 1h cycle (`x-post-mail-flush 0 6-22 *`) + 試合中 15 分 burst 2 本 (`flush-game-1 15,30,45 19-20 *` / `flush-game-2 15,30,45 21 *`)。2026-05-23 22:01 JST に user request で 21:45 を追加、Job target/env/Secret/WP/X live post は不変。 (4) Tavily 0 化 = 旧 5 cron (am-1 / lunch / afternoon / evening / postgame) PAUSE + 5/17 one-time cron DELETE → log verify 06:00 UTC 以降 Tavily call 0 件。 issue #95 comment 4516083275 で進捗報告済、 user 承認後 close。 |

## 2026-05-21 session update

### 418 — 日刊ゲンダイ本文抜粋が 55 文字 meta fallback になる問題

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/418-QA-nikkan-gendai-source-body-excerpt.md` | CLOSED LIVE_DEPLOYED_VERIFIED | post `70027` / `https://www.nikkan-gendai.com/articles/view/sports/387913` で本文 extractor が `extractor_len=0` となり、`meta_len=55` fallback が引用として入った。共通 `extract_article_body_excerpt` に `www.nikkan-gendai.com` 専用 fallback を追加し、手動投入 (`manual-intake-service`) と自動 RSS (`yoshilover-fetcher`) の両方へ deploy 済。既存 post 70027 は触らない。GitHub Issue は `api.github.com` 接続不可で PENDING。 |

## 2026-05-20 PM cleanup batch

user 方針「受け入れ NG はまた起票」+「一人開発で Active 多いと混乱」を反映、GH Issue は全 open close 済、repo doc は active/ から `doc/done/2026-05/` または `doc/waiting/` へ整理。下記の本文記述は historical 記録としてそのまま残す(path 表記のみ移動先に更新済)。

| ticket | 移動先 | 旧 GH Issue |
|---|---|---|
| 344-INGEST-youtube-caption-draft-expansion.md | `doc/done/2026-05/` (SUPERSEDED) | #24 (closed before 2026-05-20) |
| 317-QA-ob-youtube-review-only-intake.md | `doc/done/2026-05/` | #76 (closed 2026-05-20) |
| 381-INGEST-giants-general-source-expansion.md | `doc/done/2026-05/` | #55 |
| 384-INGEST-source-expansion-with-publish-time-fallback.md | `doc/waiting/` (PARKED) | #59 |
| 385-INGEST-youtube-caption-short-quote-summary.md | `doc/done/2026-05/` | #60 (closed 2026-05-20) |
| 389-FRONT-sidebar-popular-posts-widget.md | `doc/waiting/` (PARKED) | #64 |
| 390-FRONT-sidebar-search-monthly-archive.md | `doc/waiting/` (PARKED) | #65 |
| 391-x-post-gen-mcp-tavily-gemma4-phase1.md | `doc/waiting/` (PARKED) | #66 |
| 392-x-post-branding-mcp-phase2.md | `doc/done/2026-05/` | #67 |
| 393-OPS-price-neutral-fast-draft-judgment-mail.md | `doc/done/2026-05/` | #68 |
| 395-INGEST-official-youtube-titleless-intake.md | `doc/done/2026-05/` | #72 (closed 2026-05-20) |
| 398-INGEST-media-quote-evaluation-default.md | `doc/done/2026-05/` | #73 (closed 2026-05-20) |
| 399-INGEST-manual-intake-react-helmet-meta-extract.md | `doc/done/2026-05/` | (no GH) |
| 400-QA-source-body-excerpt-share-ui-strip.md | `doc/done/2026-05/` | (no GH) |

今日の deploy 系 ticket は 401 (max_chars 1200) / 402 (paywall meta fallback) 内容も含めて 400 の本文に統合済(LIVE_DEPLOYED_VERIFIED)。受け入れ NG 発生時は新規 ticket(403 以降)で対応する方針。

## 2026-05-20 session update

### 414 — X-POST brand voice quality framework (全 5 軸 A-E 完成、 CLOSED LIVE_DEPLOYED_VERIFIED 2026-05-21)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/414-X-POST-BRAND-VOICE-QUALITY-FRAMEWORK.md` | CLOSED LIVE_DEPLOYED_VERIFIED | 全 5 軸 landed: A 型分離 `7bb8682` / B persona `3dd89e5` (411) / C 精度 9 axis `c0ac71e` + C8 1軍 filter `02e3bb7` / D 炎上 6 check `faa7226` / E 試合前 7 テーマ `b3c80b0` + caller wire `47c8961` + E3/E7 caller wire `4beef83`。 image `x-post-mail-lane:414-e3e7-4beef83` gen 40 deploy 済、 2026-05-21 07:04 JST 自然 fire で axis C 動作確認 (`gemma_branding_drop unverified_numbers` ダルベック 「7」 drop)、 mail 8 candidates `status=sent`。 GH Issue #90 CLOSED。 |

### 411 — X-POST branding voice persona (CLOSED LIVE_DEPLOYED_VERIFIED 2026-05-21)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/411-X-POST-BRANDING-VOICE-PERSONA.md` | CLOSED LIVE_DEPLOYED_VERIFIED | commit `3dd89e5` (Tavily whitelist 2→9 / `_format_tavily_context` published_date 注入 / フーガ+缶詰 2 persona prompt / `is_giants_game_day` helper / `select_branding_persona`) landed + image `x-post-mail-lane:414-e3e7-4beef83` gen 40 deploy 済。 2026-05-21 07:04 JST 自然 fire で persona switch / 18時 gate (`fan_voice skip: not in fire window`) / Tavily 3 results / Gemma mail `status=sent` 動作確認。 GH Issue #88 CLOSED。 |

### 407 / 408 / 409 / 410 — OB subtype + farm 2軍/3軍 + WP front (CLOSED 2026-05-20、 全 Phase LIVE_DEPLOYED_OBSERVE)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/407-SUBTYPE-ob-and-farm-split-master.md` | LIVE_DEPLOYED_OBSERVE | 親 ticket。 子 408/409/410 全 Phase 完了、 production deploy 2 回 (`00459-44z`/`00460-tng`)、 GH Issue #80。 残: 自然 fire 1 週間観察 / 409 enable user 判断 / WP CSS user 判断。 |
| `doc/done/2026-05/408-SUBTYPE-ob-classifier-and-validator.md` | LIVE_DEPLOYED_OBSERVE | OB subtype 新設。 Phase 1 (`215abbf`) literal marker primary + 19 OB seed + 3 validator 登録、 Phase 2 (`afdfd5c`) name table secondary gate + 現巨人 role guard 13 件、 Phase 3 (`1cb561c`) name seed 32 名 + literal markers 15 拡充。 40 OB tests pass、 GH Issue #82。 |
| `doc/done/2026-05/409-SUBTYPE-farm-2gun-3gun-split.md` | LIVE_DEPLOYED_OBSERVE (flag OFF) | farm → farm2/farm3 分離。 Phase 1 (`64125cb`) `ENABLE_FARM_2GUN_3GUN_SPLIT` flag-gated (default OFF) + 4 新 subtype 登録 + 26 unit test。 backward-compat alias 維持で既存 farm test 全 pass。 GH Issue #83。 残: enable user 判断 + farm3_player narrative judge。 |
| `doc/done/2026-05/410-FRONT-ob-farm-category-display.md` | LIVE_DEPLOYED_OBSERVE | WP front 表示。 Phase 1 (`b46ffaa`) `src/subtype_display_format.py` (build_subtype_badge_html / build_source_attribution_block + 17 test)、 Phase 2 (`d963d1d`) `maybe_prepend_subtype_display` + `_create_draft_with_same_fire_guard` wire-in + 8 test。 GH Issue #84。 残: WP テーマ CSS 追加 (`.nomotoke-subtype-badge--ob/farm2/farm3`、 user 判断)。 |

### 403 — INSIGHT 期間 cut を日付 base から 試合数 / PA / 登板数 / IP base に全面切替 (Stage 1、 CLOSED LIVE_DEPLOYED_VERIFIED 2026-05-21)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/403-INSIGHT-period-window-game-count-switch.md` | CLOSED LIVE_DEPLOYED_VERIFIED | image `insight-nightly:415-vs-lr-mvp` gen 81、 2026-05-21 10:02 JST 自然 fire で新 scope の publish 6 件成功 (平山功太 長打率 / マルティネス 防御率 + 奪三振率 / 平山 + 大城 + キャベッジ 打点 ranking 打順別、 全 last_5_games)、 `skip_dedup_cooldown last_7d` / `insufficient_sample` 0 件、 5/20 12-17時 publish 0 件問題完全解消。 follow-up 412 (team_ranking last_5_games cutover) / 413 (投手 last_N_games min_sample fix) も同 image で landed + LIVE 動作確認済 → CLOSED。 GH Issue #77。 |

### 404 — INSIGHT Phase 2 ETL (PARTIAL_LIVE_DEPLOYED_OBSERVE、 登板 inning 別 LIVE / vs 左右 [[415]] split / デーゲーム drop)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/404-INSIGHT-period-window-phase2-etl.md` | PARTIAL_LIVE_DEPLOYED_OBSERVE | 登板 inning 別 = commit `159d491` schema/derive + `e2dd155` publisher/wire で LIVE_DEPLOYED (image `415-vs-lr-mvp`)、 inning 別 post の自然 fire 観察待ち (投手 appearance 蓄積 + dedup cooldown 経過後)。 vs 左右投手 = [[415]] (#91) に split out、 starter 限定 approx (`378249d`+`f621457`) landed PARKED。 デーゲーム / ナイター = marginal value で drop (年 10-15 試合のみ、 必要なら別 ticket で復活)。 GH Issue #79 OPEN (observe)。 |

### 405 — INSIGHT Phase 3 READY (free source NPB playbyplay.html 確保、 6-8h impl 待ち、 415 b strict と統合 scope)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/405-INSIGHT-period-window-phase3-ready.md` | READY | commit `f621457` で NPB 公式 `playbyplay.html` を free source として実 verify 済 (per-PA 走者状況 + カウント + 結果 + 投手交代 marker 全部 parse 可能、 paid API 不要)。 (1) 打席内カウント別 (初球/2 ストライク後/3 ボール後/投球数別) / (2) 走者状況別 (満塁/二塁単独/一三塁 等) / (3) 球場別 (本拠地以外、 甲子園/マツダ/ハマスタ 等)。 [[415]] (b) strict と同 source、 共通 parser + per-PA detail table で同時実装条件付き READY。 実装段階: playbyplay.html parser 新規 → per-PA detail table schema → aggregator × 3 cut + publisher × 3 cut → tests + build + deploy = 6-8h、 session 跨ぎ段階実装。 GH Issue #81 OPEN。 |

### 415 — INSIGHT vs 左右投手 split (a approx LIVE / b strict READY、 405 と統合 scope 着手条件付き)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/415-INSIGHT-vs-left-right-pitcher-split.md` | SPLIT_LIVE_OBSERVE | (a) approach starter 限定 approx で commit `378249d` (vs L/R split publisher + NPB throws scraper) + `f621457` landed、 image `insight-nightly:415-vs-lr-mvp` gen 81 deploy 済、 wire は `insight_nightly.py` L300-310 (last_10_games scope L/R loop)。 (b) strict は [[405]] と同 source `playbyplay.html` で per-PA pitcher 追跡可、 同時実装条件付き READY (工数 6-8h 統合)。 user 判断 pending: (a) approx 継続 / (b) strict 拡張。 GH Issue #91 OPEN。 |

### 406 — HR opponent / home_away split SQL bug fix (P1 narrow、 CLOSED 2026-05-20 PM)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/406-INSIGHT-hr-split-sql-bug-fix.md` (GH #78) | CLOSED (LIVE_DEPLOYED_VERIFIED) | 5/20 12:00 JST `insight-nightly-ndtvf` logs に `OperationalError:no such column: bl.HR` × 7 split。 原因 (audit 済): split 経路に HR dispatch 無く `SUM(bl.HR)` で OperationalError。 narrow fix: split 版に dispatch 追加 + split 対応 helper `aggregate_player_hr_from_atbats_split` 新規。 commit `5d72191` / Cloud Build `fd780627` / image `insight-nightly:406-hr-split-5d72191` / Job gen 72。 **verify (2026-05-20 20:00 JST fire)**: bl.HR error 過去 5 日 175 件 → 20:00 fire で **0 件** (完全消失)。 |



### 400 — 本文抜粋を「全文恒久」 clean (share UI + photo credit + copyright + lead heading、user 指摘「全文恒久対応でないの?」「アプリ以外も対応」「引用文をよみやすく」 2026-05-20、同日 LIVE_DEPLOYED_VERIFIED)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/400-QA-source-body-excerpt-share-ui-strip.md` | LIVE_DEPLOYED_VERIFIED | post 69888 (`https://yoshilover.com/69888`) の `nomotoke-source-excerpt__body` 内に share UI ボタン文字列 (ポスト/送る/シェア/ブックマーク/URLをコピー) + breadcrumb (スポーツ) + photo caption credit「(写真：AP/アフロ)」が流入していた。**Phase A (commit `512dbe5`)** で share / SNS UI 23 ラベルを `_BOILERPLATE_LINES` set に追加し strip。**Phase B (commit `0a29e7f`)** で `_PHOTO_CREDIT_LINE_RE` (行末 `[（(](写真\|撮影\|提供\|画像\|Photo)...[）)]`) + `_COPYRIGHT_LINE_RE` (行頭 ©/Ⓒ/(c)/Copyright/無断複写/無断転載/All Rights Reserved) で photo credit + copyright 行を drop、`_HEADING_PREFIXES` に `◇ ▽ ◎ □` 追加 (NTV/朝日/報知 試合速報リード「◇MLB ...」を `.nomotoke-source-excerpt__heading` style に整形)。`_strip_html_to_plain` と `_is_noise_line` 両 path で同 regex を check。ロジック改変なし、exact-line + 末尾 anchor で prose 内 substring (ポストシーズン/メールマガジン/シェアを伸ばす) は誤剥離しない。tests 計 5 case 追加 (share UI / false-positive / photo credit / copyright / diamond lead)、pytest 142 + manual_intake 93 = 全 235 passed (regression 0)。両 service (manual-intake-service + yoshilover-fetcher) が同 extractor + classifier を共有 (manual_intake.py:1440-1443 / rss_fetcher.py:20459-20460,27978) で **手動 app だけでなく自動 RSS 経路にも同等に効く**。deploy: Phase A Cloud Build `86d91583-...`/`b93eac22-...` → rev `00086-x62`/`00453-gnt`、Phase B Cloud Build `0c5328d0-c4f0-41bf-b408-dfb3c0dee61c` (manual-intake, 81s) + `b10db4be-2616-4980-9c4c-5cfbbe6ac56d` (fetcher, 68s) 両 SUCCESS、image tag `400-ext-readable-0a29e7f`、revision `manual-intake-service-00087-rfv` 100% + `yoshilover-fetcher-00455-lcf` 100%、両 `/health` OK、新 revision ERROR 0。live verify: live NTV HTML → 9/9 noise token (ポスト/送る/シェア/ブックマーク/URLをコピー/スポーツ/写真：/撮影：/Copyright) no_leak、リード「◇MLB ...」heading 化、本文 4 段落維持、photo caption「(写真：AP/アフロ)」も完全消失、新 draft post_id `69899` 作成成功。post 69888 は retroactive cleanup しない (user 判断で手動編集 or 再生成、edit_url=`https://yoshilover.com/wp-admin/post.php?post=69888&action=edit`)。env / Secret / Scheduler / RUN_DRAFT_ONLY / WP既存記事 / X / publish-notice / x-post-mail-lane / frontend / tag scrape path 全部不変。 |

### 399 — manual-intake が NTV React Helmet 記事を `missing_title_or_summary` で蹴る件 (user 報告 2026-05-20、同日 LIVE_DEPLOYED_VERIFIED)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/399-INGEST-manual-intake-react-helmet-meta-extract.md` | LIVE_DEPLOYED_VERIFIED | user 報告「`https://manual-intake-service-487178857517.asia-northeast1.run.app/` で `https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767` が記事化できない」。dry-run POST で `{"ok": false, "reason": "missing_title_or_summary"}` HTTP 400 を確認 → 原因 = `src/tools/manual_intake.py` L187-198 の `_META_PATTERNS` regex が `<meta\s+property=` を前提にしており、NTV の React Helmet 出力 `<meta data-react-helmet="true" property="og:title" content="..."/>` にマッチしない。`<title data-react-helmet="true">...</title>` も fallback regex (L399) に不発。narrow fix: regex を属性順非依存 `<meta\b[^>]*\sproperty=...[^>]*\scontent=...` 形に書き換え + title fallback を `<title\b[^>]*>` に拡張。`_META_PATTERNS` 11 entry + title fallback 1 行のみ。tests/test_manual_intake.py に `test_react_helmet_attribute_first_meta` / `test_react_helmet_title_tag_with_attribute` 2 case 追加、pytest 93 passed (regression 0)。commit `fbb388d`、Cloud Build `90d41bc9-b298-45d9-8a8e-7892b0a507ea` SUCCESS 1m16s、image digest `sha256:61460a15...`、revision `manual-intake-service-00085-s2m` 100%、`/health` OK、新 revision ERROR 0。live verify: NTV URL dry-run で HTTP 200 / `ok: true` / `validation_ok: true` / title 完全抽出 / `category="OB・解説者"` / `subtype="general"` / `template_key="nomotoke_card_short_news_url_v1"` / `article_type_guess="試合速報"` / `category_ids=[667]`。env / Secret / Scheduler / RUN_DRAFT_ONLY / WP既存記事 / X / publish-notice / x-post-mail-lane / frontend / 自動 RSS / tag scrape path 全部不変。次自然 fire 観察 = 不要 (manual-intake 経路は user 操作起点で deterministic、unit + live 両方 verified)。次 archive 便で `doc/done/2026-05/` へ移動候補。 |

### 317 — 巨人OB YouTubeを差別化用 review-only 記事候補にする

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/317-QA-ob-youtube-review-only-intake.md` (GH #76) | CLOSED | 巨人OB YouTube source を RSS 本線へ draft-only 接続済み。`giants_ob` source は weak title でも候補化し、`OB・解説者` category + YouTube embed で draft 作成、publish skip reason は `draft_only,youtube_review_source_draft_only`。quote-only guard により `youtube_review_notice` は字幕引用 block のみ、`要点` list なし。current live image `402-meta-fallback-671df22` は 317 / 401 descendant。user 判断により受け入れ観察は別 ticket 化し、GitHub Issue #76 close。 |
| `doc/done/2026-05/317-QA-ob-youtube-review-only-intake.md` / 401 runtime refresh | LIVE_DEPLOYED_VERIFIED | `1fd6a6c` で `youtube_review_notice` は字幕引用 block のみ (`要点` list なし) にし、CTA / 音楽・拍手 / URL 系ノイズを引用候補から除外。関連/本文抜粋は `src/tools/manual_intake.py` の `SOURCE_BODY_EXCERPT_MAX_CHARS = 1200` と `src/rss_fetcher.py` の `extract_article_body_excerpt(..., max_chars=1200)` で manual-intake-service / fetcher 両方 1200 字に統一。baseline: `git diff --check` OK、py_compile OK、compileall OK、AST `618` OK、sandbox外 full pytest `5398 passed, 1 xfailed, 3 xpassed`。deploy: manual-intake-service revision `00088-vn8` image `401-excerpt-1200-1fd6a6c` generation `101/101` 100% / `/health` OK / ERROR 0。fetcher clean archive `d1c5d7a`、Cloud Build `f9799b40-89b7-400d-9b21-2ba972e80189` SUCCESS、image `401-excerpt-quote-d1c5d7a` digest `sha256:8dcae877...`、revision `00457-pcr` 100%、generation `597/597` -> `599/599`、`/health` OK / ERROR 0。final current: 後続 402 deploy で fetcher `00458-2dq` / manual `00089-xtf`、image `402-meta-fallback-671df22`、generation `600/600` / `102/102` に進行。`671df22` は `1fd6a6c` / `d1c5d7a` descendant のため、1200 字化と quote-only guard は live 維持。両 `/health` OK / ERROR 0。env / Secret / Scheduler / RUN_DRAFT_ONLY / WP既存記事 / X / manual `/run` fire は未変更。 |

### 398 — media_quote_evaluation 未初期化エラーの再発防止

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/398-INGEST-media-quote-evaluation-default.md` (GH #73) | CLOSED | `media_quote_evaluation` / `media_quotes` safe default を各 entry 処理開始時に置く narrow fix。tests 27 OK、Cloud Build `14880fed-c77f-44a1-b168-b5705561bf12` SUCCESS、fetcher rev `yoshilover-fetcher-00452-glk` 100%、`/health` OK、新 revision ERROR 0。user 判断により受け入れ観察は別 ticket 化し、GitHub Issue #73 close。 |

### 395 — 公式 YouTube の弱いタイトルでも取り込む (user 要望「YouTube の取り込みも」)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/395-INGEST-official-youtube-titleless-intake.md` (GH #72) | CLOSED | 巨人公式 YouTube の weak-title / titleless pass を `official_video_source` ロールに限定して追加し、非公式 / OB / candidate YouTube は既存 title filter 維持。commit `43b101a` + priority follow-up `ffdb668` deploy 済み。手動 run で公式YouTube post_id `69846` draft 作成確認。user 判断により受け入れ観察は別 ticket 化し、GitHub Issue #72 close。 |

## 2026-05-19 session update

### 393 — 価格据え置きの本文付き公開判断メール即時化 / 大量時 Part 分割 (user GO 2026-05-19)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/393-OPS-price-neutral-fast-draft-judgment-mail.md` (GH #68) | LIVE_DEPLOYED_OBSERVE | repo commits `a626bda` / `bd0bb07` / `b495f6a`。本文抜粋・編集リンク・公開ボタン付き `judgment_batch` summary mode と fetcher inline draft notice を実装 / deploy 済み。publish-notice image `393-judgment-bd0bb07` Job generation `111`、fetcher image `393-inline-mail-b495f6a` revision `00445-zm7` 100%、`/health` OK。inline sent marker は GCS `publish_notice/queue.jsonl` に merge して後続 publish-notice の再送を止める。追加 Scheduler `publish-notice-peak-followup` は価格据え置きのため `PAUSED`。残 acceptance は次回自然 fetch の `fetcher_inline_draft_notice_result` と実 mail 本文確認。 |

### 394 — Gemma branding に insight.db 当日試合 / player log / 連勝記録の fact line 注入 (392 拡張、 user 明示「データベースは当日のきろくがいい」 2026-05-19)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/394-x-post-gemma-db-fact-line.md` | LIVE_DEPLOYED_OBSERVE | 22:30 fire 観察で 392 Gemma 出力に cheerleading + 古い snippet の現在化問題が見つかった対応。 同夜の 414d411 (tone tune) / 1a55d59 (same-day filter + 時間帯 hint) に加え、 本 commit `ef1e756` で `build_db_fact_line()` 追加: `insight.db` を read-only SELECT で叩き、 (1) games table から今日試合の opponent / score / 勝敗、 (2) batting_logs / pitching_logs JOIN games で player の今日 stat、 (3) 直近 N 試合 result から ○●△ streak、 を改行区切りの facts line に整形して Gemma context に注入。 既存 `_build_gemma_branding_candidates` に `db_path` 引数追加、 caller の既 download 済 insight.db cache を再利用 (追加 GCS access なし)。 Gemma は **DB fact 内 verified 数字のみ post 本文に使用可** (spec 382 hard rule、 Tavily snippet の数字は使ってはいけない、 system prompt + validator で gate)。 fault tolerance: build_db_fact_line 例外時は空 string → caller は lineup_fact fallback → 最終的に Tavily snippet のみ context、 既存 mail は止めない。 user 「勝ち負けは RSS で拾える?」 への回答 = 既存 ETL の `games.result` で取得済 + 直近 streak も計算済、 別途 RSS source 不要。 tests 24/24 + 関連 126/126 pass (regression 0)。 image `394-db-fact-ef1e756` build 後 Job update、 翌 07:00 JST am-1 fire で実 verify。 392 / 391 既存 commit は supersede しない、 機能拡張のみ。 |

### 392 — ヨシラバー branding X 投稿案 LLM 生成 Phase 2 (Gemma 4 + Tavily HTTP REST、 既存 382 mail/Scheduler 流用、 user GO 「GO」 2026-05-19)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/392-x-post-branding-mcp-phase2.md` (GH #67) | LIVE_DEPLOYED_OBSERVE | 391 Phase 1 CLI を本番 `x-post-mail-lane` に組み込み済 (commit `a15d852`)。 **22:30 fire 観察結果 (実 mail 確認済)**: Gemma 生成 2 件 (吉川尚輝 / 泉口友汰) は cheerleading 定型語 (ついに / 物語が / 核心に迫る) + Tavily 古い snippet (Wikipedia / 2024-2026年3月) の現在化で品質低下 → user 指摘「内容をあつく、 巨人ファンよりでない」「朝はまた違うがテンション昼もK」「これはインプがあるファン」 を受けて同夜 2 commit で改修: (1) commit `414d411` tone tune (cheerleading 定型語 ban + ファン自然 voice 許容 + 「巨人ファン向け」 framing 撤回) + Tavily news/days=7。 (2) commit `1a55d59` same-day filter (Tavily `days=1` + JST 当日 published_date filter post-process) + 時間帯 tone hint (朝 5-11 時は分析調、 昼以降はファン熱量 OK、 _build_system_prompt() で動的注入)。 実 API demo (戸郷翔征 22:46 JST / 22:50 JST) で 5 軸厚い post 生成、 cheerleading 0、 時系列ズレ 0 を確認。 image `392-tune-1a55d59` Job generation 28 deploy 済 (build d3b4a3bf SUCCESS 1m43s)。 env `X_POST_MAIL_GEMMA_GEN_ENABLED=1` (ON、 5 fire/日 × MAX=2) のまま観察継続、 翌 07:00 JST am-1 fire で改修版実 verify、 さらに 394 拡張 (DB fact line) が `394-db-fact-ef1e756` で同時 deploy 予定。 spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) 維持。 fault tolerance: silent skip on Tavily / Gemma error、 既存 mail は止めない。 0 ドル維持 (Gemini API free / Tavily ~300/月)。 GitHub Issue #67。 |

### 391 — 巨人 X 投稿案生成 (Tavily MCP stdio 同梱 + Gemma 4 31B、Phase 1 CLI、 user GO 「チケットGO」 2026-05-19)

| ticket | status | 内容 |
|---|---|---|
| `doc/waiting/391-x-post-gen-mcp-tavily-gemma4-phase1.md` (GH #66) | PLANNING / user GO 待ち (code 編集 stop) | user 要望 (2026-05-19 chat): 巨人関連を Tavily MCP (stdio 同梱、 `npx -y tavily-mcp@latest`) で web 検索 → Gemma 4 31B (Gemini API free tier) で X 投稿案を生成する CLI smoke を新設。 $0 制約 hard rule (Gemini API free / Tavily 1000 credits/月 / Cloud Run・Vertex AI 自前 host 禁止)。 Phase 1 scope = `src/x_post_gen_mcp.py` + `src/tools/run_x_post_gen_mcp.py` + `tests/test_x_post_gen_mcp.py` + `requirements.txt` に `google-genai` + `fastmcp` 追加、 出力 stdout のみ、 mail / WP / X 連携は Phase 2 (別 ticket)。 必要 API: Gemini key (https://ai.google.dev/) + Tavily key (https://tavily.com/)、 両方無料 signup credit card 不要。 不可触: 382 改修中 `src/x_post_mail_lane.py` / 387 改修中 `src/analysis/` / automation / scheduler / env / secret / WP / X / 既存 Cloud Run Job。 spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) 継承。 **process compliance**: 私が ticket 切らずに code 2 file (`src/x_post_gen_mcp.py` / `src/tools/run_x_post_gen_mcp.py`) を書いた事実を user が指摘、 本 ticket は後付け正規化。 既に書いた 2 file は dirty 残置 commit 待ち。 次 step: user が code 編集 GO を出したら、 tests/test_x_post_gen_mcp.py 追加 + requirements.txt 更新 + py_compile + pytest + commit / push。 |

### のもとけ風サイト構造 chain (387-390、 user GO 「A=phase ごと別 ticket」 + 「index はまだいらない」)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/387-FRONT-tag-attachment-coverage-100.md` (GH #62 CLOSED 2026-05-20) | CLOSED (user 判断) | user 判断 2026-05-20: タグ付与は OK 扱いで close、 UI (388) のみ前進。 doc は次 archive 便で `doc/done/2026-05/` 移動予定。 |
| `doc/active/388-FRONT-header-nav-player-tag-expansion.md` (GH #63) | REVIEW_NEEDED (2026-05-20) | user 判断 2026-05-20: PC 30 / mobile 10-15 目安に scope 確定。 impl 着地 = PHP cap 100→30 / plugin v0.16.1→0.16.2 / CSS `@media (max-width: 600px)` で `__item:nth-child(n+19)` 隠す。 deploy + live verify 待ち、 fetcher / env / Secret / Scheduler / publish / X / SNS は不可触。 |
| `doc/waiting/389-FRONT-sidebar-popular-posts-widget.md` (GH #64) | READY_FOR_IMPL | サイドバーに「直近3日 人気記事」 widget 30 件 list (のもとけ模倣)。 「人気」定義は user 判断 (GA4 / comment / 編集独自ランク / hybrid)、 cost ¥0 推奨は編集独自ランク。 5-15 min cache。 既存 widget (breaking-strip / topic-hub / AdSense slot) 削除禁止、 fetcher / env / Secret / Scheduler / publish / X / SNS は不可触。 |
| `doc/waiting/390-FRONT-sidebar-search-monthly-archive.md` (GH #65) | READY_FOR_IMPL | サイドバー 検索 widget (WP 標準 search form) + 月別アーカイブ widget (直近 12 ヶ月、 post 数 badge)。 フッター mirror は任意。 **タグページ index 解放は scope 外** (user 判断「index はまだいらない」)。 fetcher / env / Secret / Scheduler / publish / X / SNS / WP DB は不可触。 |

### 既存 5/19 着地

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/383-INGEST-youtube-source-articleize-fix.md` (GH #58) | CLOSED | 344 の YouTube 記事が出ない件。YouTube channel scraper だけ `media_quote_only` でも記事化 path へ進め、`youtube_ob_sources.json` の confirmed / candidate ch を runtime 展開。tests: 344/YouTube suite 68 OK、rss_fetcher + tag_page + YouTube integration 57 OK、compileall / AST / diff-check OK。Cloud Build `7ed5103a` SUCCESS、fetcher rev `yoshilover-fetcher-00436-7zq` 100%、`/health` OK、新 revision ERROR 0。2026-05-19 natural fire で `tag_page_entries_built source=youtube` と `youtube_title_filter_skip` を確認し、YouTube path log acceptance を満たしたため GitHub Issue #58 close。Scheduler / env / Secret / WP既存記事 / X / frontend は未変更。 |
| `doc/waiting/384-INGEST-source-expansion-with-publish-time-fallback.md` (GH #59) | DESIGN_LOCKED / READY_FOR_IMPL | user 要望「ソースをふやしたい、ガードに引っかからない」(2026-05-19 chat lock)。chat verify 結果: 5/19 9 時 cycle で 52 件 `source_time_missing_review` review 落ち = 既存 381 16 family にも meta なし媒体が混在している evidence (Full-Count / 週刊女性PRIME / 読売新聞は meta あり、朝日 / 毎日 / FRIDAY 等は root では meta なし)。新規候補 verify: 産経 (`<meta name="article:published_time">` あり、5/19 朝記事 age 4h) ✓、日刊SPA (`<meta property=...>` あり、search 最新 sort 要 verify) ✓、中日新聞・中日スポーツ (meta なし、SPA 構造) ✗、THE ANSWER (search SPA で article href 抽出不能) ✗。Phase 1 = 産経 + 日刊SPA 追加 (`config/rss_sources.json` + `source_trust.py` SourceProfile + `rss_fetcher.py` `_POST_GEN_VALIDATE_TOPIC_SOURCE_FAMILIES`)、Phase 2 = `tag_page_scraper.py` に publish-time fallback chain (property/name/modified_time/URL date/body 日付表記)、Phase 3 = 中日系追加 (Phase 2 effect ベース判断)、Phase 4 = THE ANSWER (SPA、別 ticket)。デグレ試験: 既存 16 family 挙動不変 + `STRICT_BREAKING_NEWS_THRESHOLDS` 閾値不変 + scraper `_is_ymd_within_window` で古い記事 2 重 guard。`_POST_GEN_VALIDATE_TRUSTED_FAMILIES` (full bypass) / numeric fact validator / close_marker / placeholder_body / hard-stop は不可触、env / Secret / Scheduler / X / SNS / WP既存記事も不可触。 |
| `doc/done/2026-05/385-INGEST-youtube-caption-short-quote-summary.md` (GH #60) | CLOSED | YouTube 字幕を LLM なし / 推測なしで短い引用 + 要点表示に寄せ、取得材料 window は 600→1500 chars に拡大。tests 63 OK、Cloud Build `82719b1a` SUCCESS、fetcher rev `yoshilover-fetcher-00441-xj8` 100%、`/health` OK、新 revision ERROR 0。user 判断により受け入れ観察は別 ticket 化し、GitHub Issue #60 close。 |
| `doc/done/2026-05/386-INSIGHT-no-game-day-normal-exit.md` (GH #61) | CLOSED | 2026-05-18(月) 試合なしで `insight-nightly` が `auto_resolve_all_failed` / exit 2 になった件。`status=no_game_day` / exit 0 修正を deploy / live verify 済み。follow-up で no-game 日でも DATA-INSIGHT publish/mail が出る path を追加。commits `a852abf` / `8454a21` / `0d09c10`。evidence: `insight-nightly:386-no-game-publish-8454a21` Job generation `68`、execution `insight-nightly-j4sbm` 成功、`【巨人データ】` post IDs `69545` / `69546` / `69547` publish。`publish-notice:data-insight-mail-0d09c10` Job generation `107`、execution `publish-notice-gm5tb` 成功、summary `sent=3`、per-post sent `69545` / `69546` / `69547`。 |

## 2026-05-18 session summary

### 着地 (Cloud Scheduler 3 jobs 追加、 repo code 不変)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/378-evening-peak-fetch-15min.md` (GH #52) | CLOSED (2026-05-19) | 試合後ピーク (20:00-22:00 JST) の `yoshilover-fetcher /run` fetch を 15min cadence 化、 22-23 時を 30min cadence 補強。 既存 `giants-realtime-trigger 0,30 17-21` `giants-postgame-catchup-am 0 22` は不変 (gcloud list で verify 済)、 新規 3 jobs ENABLED で着地 (`giants-realtime-peak-15min 15,45 20-21`, `giants-realtime-2230 30 22`, `giants-realtime-2300 0 23`)。 auth は既存 trigger と同じ `seo-web-runtime@baseballsite.iam.gserviceaccount.com` + oidcToken (5/16 x-post-mail 403 事故回避)。 guarded-publish-trigger `*/30` / publish-notice-trigger-evening `5,35 16-22` / WP / X / SNS / env / Secret 不変、 mail 仕様も不変。 cost +$0.30/月、 user confirm 済。 23:00 fetch の mail は翌朝 (`publish-notice-trigger 5 6-15`)、 判断サイクル完全 15min 化は別 ticket (guarded-publish + publish-notice 連動 15min 化、 +$0.30/月)。 |

### 起票 (DESIGN 段階、 377-OPS Phase 1C / Phase 2 完了後着手)

| ticket | status | 内容 |
|---|---|---|
| `doc/done/2026-05/377-OPS-...md` Phase 1C (GH #51) | CLOSED (2026-05-19) | mail に body_excerpt + admin_edit_url を populate。 commits `11128d5` (helper module + 39 tests) → `cb5b477` (scanner wiring + 15 tests) → `0467180` (dry-run tool + e2e integration 2 tests)。 Cloud Build `1aa5e4f2` SUCCESS、 image `publish-notice:377-phase1c-0467180` digest `sha256:e01bccd9e503...`、 Cloud Run Job update Ready=True (旧 image `classification-316cb03` rollback 用に保持)。 env (RUN_DRAFT_ONLY=0 維持) / Secret / Scheduler / WP / X / SNS 全て不変、 手動 execute は追加 mail 回避のため未実行。 publish_notice 系 12 files 340 tests pass、 regression 0。 次回自然 fire = 10:05 JST (publish-notice-trigger)。 本文 / admin link 目視 verify 待ち。 |
| `doc/done/2026-05/377-OPS-...md` Phase 2 (GH #51) | CLOSED (2026-05-19) | `RUN_DRAFT_ONLY=True` env apply。 yoshilover-fetcher service rev `00424-sc8` で全 subtype draft 化稼働開始。 既存 publish 済記事は touch せず forward-only、 rollback は env=False で 1 toggle。 |
| `doc/done/2026-05/379-mail-publish-x-intent-button.md` (GH #53) | CLOSED (2026-05-19) | 当日 10 commit fix chain (9fdbeca→38bfedc→be1cc62→4a85a8a→585a208→b9281a3→f3a961f→b998f0a→3c1612d→feb27e3)。 最終 deploy: fetcher `fix-team-label-3c1612d` (rev `00429-m9h` 100%) + publish-notice `dedup-24h-feb27e3`。 env final: RUN_DRAFT_ONLY=True / DRAFT_ONLY_SCAN_MODE=1 / ENABLE_POST_GEN_VALIDATE_NOTIFICATION=0 / ENABLE_PREFLIGHT_SKIP_NOTIFICATION=0 / ENABLE_PUBLISH_ONLY_MAIL_FILTER=0 / DEFAULT_DUPLICATE_WINDOW=24h。 **end-to-end first 完全動作確認 (15:05 fire)**: user が 69348/69349/69350 を 15:11-15:12 JST に mail 緑 button click → caller=mail_publish_and_tweet_endpoint で publish 化 (Cloud Logging `publish_button_publish_success` × 3 evidence)。 当日 事故 root cause = (1) 13:00 fetcher 0 件 = 「巨人」「ジャイアンツ」 を generic title block list に入れた、 commit `3c1612d` で除外修正、 (2) 14:05 fire 30 通中 20 通 再送 = dedup 30 分 default 短すぎ、 `feb27e3` で 24h に拡大。 様子見 point = 16:05 以降の自然 fire mail 量 baseline (5-10 通安定) / 再送 0 / 21:00-22:00 試合後ピーク fetch 15min cadence (378) / title 弱 case 別 ticket / 13:05 で STALE filter 効かなかった root cause (DRAFT_ONLY_SCAN_MODE 回避策で代用、 コード trace 未) は次 session 案件。 ticket 内に詳細記録 (10 fix log / 様子見 point / コスト試算 / 別 ticket 候補) 追記済。 |
| `doc/done/2026-05/380-x-post-mail-player-diversity-cap.md` (GH #54) | CLOSED (2026-05-19) | 2026-05-18 07:00 JST mail は `マルティネス` 3 件 / `岸田 行倫` 2 件、12:01 JST mail は浦田俊輔 3 件 / マルティネス 3 件、13:07 手動 mail でも浦田俊輔が再登場したため、user-visible acceptance は未達。follow-up 実装: GCS dedup JSONL に `focus_player / metric / period_label` を記録し、直近24h player history から既出 player を避ける。ranking 内に別の巨人 player があれば差し替え、無ければ `player_history_skip` を log して news/opinion fallback で別 player を補充する。tests: py_compile / compileall / AST PASS、pytest `94 passed, 3 warnings`、unittest `Ran 94 tests OK`。deploy: commit `157b26b` clean archive、Cloud Build `8dad3a83` SUCCESS、image `x-post-mail-lane:380-player-history-157b26b` digest `sha256:15cd067...`、Cloud Run Job generation `21` Ready=True。手動 execute は追加 real mail 回避で未実行、post-update user-visible acceptance は次回自然 fire 待ち。Scheduler / env / Secret / WP / X / SNS / production DB は変更しない。 |
| `doc/done/2026-05/381-INGEST-giants-general-source-expansion.md` (GH #55) | LIVE_DEPLOYED_OBSERVE | user 要望「巨人だけ総合」「データがなければニュース記事の意見」「読売新聞/朝日新聞/毎日新聞/週刊ベースボール/一般誌」。追加/修正 source: Full-Count 巨人 category feed、ベースボールチャンネル、朝日スポーツRSS、毎日スポーツRSS、週刊ベースボールONLINE、読売新聞オンライン プロ野球、日テレNEWS NNN、FRIDAY、Smart FLASH、週刊女性PRIME、文春、NEWSポストセブン、デイリー新潮、現代ビジネス、アサ芸。root cause: x-post-mail news/opinion fallback が tag_scrape を読まず、source limit 4 で新ソースまで届かなかった。修正後 evidence: fallback default limit 32 / loaded article sources 32 / positions 23-32 に読売・日テレ・一般誌まで到達。live scraper evidence: 読売3、日テレ5、Smart FLASH5、週刊女性PRIME5、NEWSポストセブン2、アサ芸3、FRIDAY0、文春0、デイリー新潮0、現代ビジネス0。ガード: tag_scrape は title/summary に `巨人`/`読売ジャイアンツ`/`ジャイアンツ` 必須、一般誌/新聞は limited topic bypass のみで full bypass / numeric fact / hard stop は不変。tests: unittest 170 OK、pytest 203 passed。deploy: commit `c791f52`、x-post-mail build `a8a5ea80` SUCCESS / image `x-post-mail-lane:381-general-sources-c791f52` / digest `sha256:a39a741...` / Job generation `22` Ready=True、fetcher build `2b60df25` SUCCESS / image `yoshilover-fetcher:381-general-sources-c791f52` / digest `sha256:ad8fd151...` / revision `yoshilover-fetcher-00431-vl9` 100% / `GET /health` OK。manual-intake-service も source 候補 tab + `/source-candidates` を追加 deploy 済み: build `9329593b` SUCCESS / image `manual-intake-service:source-candidates-202605181726` / digest `sha256:994eb392...` / revision `manual-intake-service-00084-bzv` 100% / live 読売 endpoint `count=3` / ERROR log 0。Scheduler / env / Secret / WP / X は未変更。追加 real mail 回避のため manual execute は未実行、post-update mail acceptance は次回自然 fire 待ち。 |
| `doc/done/2026-05/382-MKT-yoshilover-branding-post-planning-mail.md` (GH #56) | CLOSED | 既存 x-post-mail lane 内でブランディングXポスト案を実装 / deploy / 自然実行 verify 済み。commit `4507257` + full regression follow-up `1013716`、Cloud Build `1629e082` SUCCESS、image `x-post-mail-lane:382-branding-4507257`、Cloud Run Job generation 23 Ready=True、2026-05-19 07:00 JST 自然実行 `x-post-mail-lane-psp2s` SUCCESS / mail sent / ERROR 0。URLなし / hashtagなし / サイト誘導なし、未照合数値は本文から除外、DB照合済み数値のみ許可。Scheduler / env / Secret / WP / X live post は不変。git push は repo lock により未実施。GH #57 は user request により canceled close 済み。 |

## チケット管理方針(2026-05-14 EVENING lock)

- **正本 = repo doc 一本**(`doc/README.md` + 本 `doc/active/assignments.md`)
- **2026-05-16 user lock: 新規/修正 ticket は GitHub Issue も作る**
- GitHub Issue は日本語で、人間が読んで分かる題名・原因・直す内容・完了条件を書く
- Issue は作っただけで完了にしない。変更 diff、テスト、deploy / log 証跡、受け入れ条件の一致が揃った後に close する
- repo doc は引き続き正本。GitHub Issue は user が追いやすい外部台帳として同期する

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`
- `doc/active/assignments.md`
- **2026-05-14 最新 handoff (本日 3 session)**:
  - `docs/handoff/session_logs/2026-05-14_pm_336qa_chain_handoff.md` (PM、336-QA chain LIVE)
  - `docs/handoff/session_logs/2026-05-14_session_handoff_343_INSIGHT_007_LIVE.md` (PM 並走、343-INSIGHT-007 chain LIVE + 342 unblock)
  - `docs/handoff/session_logs/2026-05-14_session_handoff_DATA_INSIGHT_continuous_LIVE.md` (EVENING、342 LIVE 公開 + DATA-INSIGHT-continuous system 稼働 + SVG fix)
- **2026-05-08 緊急対応 (close 済)**: `doc/done/2026-05/RESTORE-2026-05-08-MORNING-RELIABILITY.md` + `docs/handoff/HANDOFF-2026-05-08-NEXT-SESSION.md`

## 2026-05-14 PM session summary

### close 済 (13 GH Issue、1 commit chain)

| 区分 | Issue | commit | 備考 |
|---|---|---|---|
| impl | #17 / 338-QA | `ef204c5` | 「無失点」を「失点」誤判定 fix |
| audit→fix | #19 / 340-OBSERVE → #22 / 341-FIX | `4487e77` | digest 不発 audit → schema adapter |
| impl | #8 / 335-QA Phase 3 | `ace4b64` | event token 重複圧縮 |
| impl | #16 / 337-INGEST Phase 3 | `21e4502` | sanspo balanced div extractor |
| impl | #18 / 339-INGEST | `6dd55f2` | X+Web 同 family dedup (default OFF) |
| impl | #10/#11/#12 / 336-QA Phase 1+2+3 | `e7a33bd` | 報知優先 parent + 600字 excerpt block |
| ops 移行 | #5 / 334-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| ops 移行 | #9 / 335-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| ops 移行 | #13 / 336-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| 並走 | #23 / 343-INSIGHT-007 | (並走 session) | Phase 1+2 LIVE deploy 完了で close |

deploy: yoshilover-fetcher rev 00380-dx7 → 00381-n9d → 00382-hqj → 00383-vtd → 00384-c2s → 00385-5xb (6 deploy、build digest = revision sha256 一致全件 verify)

## 2026-05-15 session summary

### close 済(本 session、 348 chain)

| 区分 | ticket | commit | image digest |
|---|---|---|---|
| impl + deploy | 348 step 1: × whitelist gate + config JSON | `86d4724` | `sha256:43aeb2b5...` |
| impl + deploy | 348 step 2: 勝率/守備率 + publisher 日本語 label | `bf010ba` | `sha256:e26ac26d...` |
| impl + deploy | 348 step 3 part 1: scope 拡張 (last_5/10_games / monthly / weekly) | `8b962e5` | `sha256:16129274...` |
| impl + deploy | 348 step 3 part 2: record detector + team ranking + counting helper | `7a10c6e` | `sha256:6e633c8b...` |

test: 382 passed (= 302 baseline + 35 step1 + 18 step2 + 14 step3p1 + 13 step3p2)、regression 0、schema migration 0

### 起票(本 session 発見、 user 確認後 着手判断)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/352-postgame-auto-thin-body-false-positive.md` | REVIEW_NEEDED | 2026-05-17 user GO で repo fix 完了。Yahoo minimal postgame は勝敗投手 table を本文に出し `【試合結果】` title へ補正、scorecard-only STOP は維持。朝 catchup は前日配信 postgame に当日朝の `見どころ` state を当てない。targeted tests green、live deploy 未実行 |

### user 判断 残

| 件 | 内容 |
|---|---|
| 既存 wOBA 5 件 post (68064-68068) | × metric が title 流出、 §11 GATE。 削除/書き換え/放置 のどれか |
| 352 着手 GO 判断 | 済。repo fix 完了、live deploy / 自然 fire 観察待ち |

### 翌日の verify gap

- 明朝 07:00 JST insight-nightly 自然 fire 後、 348 step 3 で導入した新 scope (last_5_games / last_10_games / monthly / weekly) で実 publish が出るか確認
- 「奪三振率 / 与四球率 / 被本塁打率」「勝率 / 守備率」の日本語 label が新規 publish title に反映されているか

## 2026-05-16 session summary

### repo 実装済、push は repo lock により未実行、deploy 状態は ticket ごとに記録

| ticket | status | 内容 |
|---|---|---|
| `348-INSIGHT` follow-up | LIVE_DEPLOYED_OBSERVE | `BABIP` / `FIP` が detector bypass や direct renderer から再流出しないよう二重防御。UZR は user 指示通り許可側維持 |
| `349-INSIGHT-dedup-cooldown-cascade` | LIVE_DEPLOYED_OBSERVE | 同じ subject + metric を期間違いでも 7 日 cooldown。例外は 5% 以上の値変化または順位 band 変化。title 期間 runtime guard も deploy 済み。schema migration なし、既存 `article_candidates` を ledger として利用 |
| `356-INSIGHT-data-quality-publish-gate` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #31 起票済み。sample不足 / ranking coverage不足 / stale snapshot / 本文根拠不足を publish 直前に止める data quality gate を `insight-nightly:ca03019` へ本番 deploy 済み。Cloud Build `19c2e97d-f4f9-48e9-8db4-7a303003892e` SUCCESS、digest `sha256:a71bbe0f...`、Job generation `46`。env / Scheduler / Secret / X / SNS は未変更、手動 execute 未実行 |
| `362-INSIGHT-queue-cleanup-and-metric-run-cap` | LIVE_DEPLOYED_OBSERVE | anomaly auto publish を 1 run 同一 metric 1 本までに制限し、古い NEW / 対象外 signal / metric cap 余剰を status 変更で掃除する実装を `insight-nightly:362-queue-80b87ea` へ deploy 済み。production DB copy smoke では `NEW 15938 -> 822`、UZR 3 件は 1 件 draft candidate + 2 件 cap drop。Scheduler / env / Secret / X / SNS は未変更、手動 execute 未実行 |
| `363-QA-same-fire-cross-source-title-duplicate-stop` | CLOSED | 68478/68480 型の別 source URL・同 generated title の連続 draft を、lineup / pregame / postgame / player quote など高確度 family に限って same-fire で止める。generic title collision は従来通り observe-only。py_compile PASS、lineup 周辺込み targeted pytest 79 passed / 3 xfailed。Cloud Build SUCCESS、`yoshilover-fetcher-00400-f29` へ deploy、`/health` OK。Scheduler / env / Secret / WP既存記事 / X / SNS は未変更。GitHub Issue #32 は日本語化して close |
| `364-QA-cross-family-same-event-dedup` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #33。報知 / スポニチ / デイリー等が同じ巨人ニュースを別タイトルで出す穴を、literal `phase + subject + player + event + day` key で止める repo 実装完了。X+雑誌/Web も対象、別主体コメントは保持、`cross_family_same_event_duplicate_skip` 構造化ログあり。targeted tests PASS。Cloud Build `440b7747-e8f4-4ca7-adc2-f0299ab3ddd5` SUCCESS、image `364-cross-family-4929278`、digest `sha256:c2f85e1a4bb2...`、revision `yoshilover-fetcher-00401-dxs` 100%、`/health` OK。Scheduler / env / Secret / WP既存記事 / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `365-QA-social-x-related-post-specificity` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #34。68489 型。SNS記事の「関連ポスト」が同一選手名だけで別話題Xを束ねる穴を、literal detail overlap 必須にして恒久修正。記憶再構成 / silent skip / 自己評価OKは禁止。`topic_detail_mismatch` を返す。py_compile / compileall / AST PASS。pytest: media selector 24 passed、media selector + build block 83 passed、duplicate guard 13 passed。Cloud Build `a46132b5-d25a-4bf0-b44f-6bb92b39fbff` SUCCESS、image `365-social-x-7440089`、digest `sha256:6161a8b640e5...`、revision `yoshilover-fetcher-00402-4vc` 100%、`/health` OK。Scheduler / env / Secret / WP既存記事 / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `366-QA-source-excerpt-placement` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #35。68321 / 68622 型。引用記事（本文抜粋）が関連ポストから離れたり参照元付近まで下がる穴を、生成済み HTML の relocation で恒久修正。関連ポストありならポスト直後、ポストなしなら最初の本文見出し前へ移動。記憶再構成 / silent skip / 自己評価OKは禁止。py_compile / compileall / AST PASS。pytest: source excerpt 9 passed、source excerpt + build block 68 passed。Cloud Build `593207f8-ad5d-4ddd-a5ea-cc56bb436772` SUCCESS、image `366-excerpt-placement-4021792`、digest `sha256:e4bf5f00d105...`、revision `yoshilover-fetcher-00403-ssj` 100%、`/health` OK。draft 68622 は status=draft 確認後に本文抜粋位置のみ修正済み。published 68321 は未更新。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `367-QA-farm-third-postgame-first-team-box-guard` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #36。68610 型。三軍 / 二軍の試合結果記事が `first` 誤判定で当日の一軍 NPB / Yahoo boxscore を取りに行く穴を、postgame 抽出器と rss_fetcher の二層 guard で止める。`三軍` は `league_level=third`、二軍 / ファームは `farm`。parser が first と誤返却しても farm / third marker・subtype・カテゴリで fetch を止め、fallback 表示は `巨人3軍` / `巨人2軍` にする。py_compile / compileall / AST PASS。pytest: postgame extractor + postgame table 33 passed、関連 build block 込み 92 passed。commit `6664e16`、Cloud Build `f321dc67-1491-49a3-87b3-077abf922a20` SUCCESS、image `367-farm-box-6664e16`、digest `sha256:9c6dcd9294d5...`、revision `yoshilover-fetcher-00404-kds` 100%、`/health` OK。published 68610 は未更新。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `368-QA-x-web-post-quote-dedupe-title` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #37。68628 / 68633 型。Xポスト + 引用記事を残し、Web-only duplicate を消費する方向へ修正。WP既存 post は 68628 / 68619 を publish のまま title + 本文構成補正、68633 は draft duplicate として trash。関連記事は X記事では literal detail overlap 必須にする。py_compile / compileall / AST PASS。関連 pytest 103 passed。commit `8b0b420`、Cloud Build `26d505cd-8fe3-43cd-a99b-aceb93cf7766` SUCCESS、image `368-x-web-8b0b420`、digest `sha256:d8414f326603...`、revision `yoshilover-fetcher-00405-t9l` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `369-QA-short-player-event-title-quality` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #38。68539 / 68608 型に加え、68795 型の短すぎる引用 title `菅野智之「阿部さん」` を追補。`選手名 + 薄いイベント語` / `選手名 + 短い引用` title を、同じX source本文内の literal な `2回適時打` / `3安打1打点猛打賞` / `日米通算150勝` などで補強する。68795 は title + JSON-LD headline を `菅野智之が日米通算１５０勝 ... 歴代捕手に感謝` に補正済み。follow-up commit `d3e2e9b`、Cloud Build `192a645c-1460-4d89-ba5d-b2a37845765a` SUCCESS、image `369-milestone-title-d3e2e9b`、digest `sha256:5873728c...`、revision `yoshilover-fetcher-00411-4xl` 100%、`/health` OK、新 revision ERROR logs 0。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `370-QA-staff-x-web-dedupe` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #39。68649 / 68653 型。368 の `player_name` 前提から漏れた杉内投手コーチなどの staff/manager/coach quote X+Web 重複を、staff subject + quote/event token で同 fire 消費する。WP既存 post は 68649 publish を X embed + source excerpt のまま title/headline 補正、68653 duplicate は trash 済み。py_compile / compileall / AST PASS、関連 pytest 104 passed。commit `e98bb8c`、Cloud Build `3df7fcf2-b845-46d4-84f5-a56e9bf307d1` SUCCESS、image `370-staff-x-web-e98bb8c`、digest `sha256:6189023b74d9...`、revision `yoshilover-fetcher-00407-h9v` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更。自然 fire / log evidence 後に Issue close |
| `371-QA-disable-game-live-source-policy` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #40。user 方針「絞らないでいい。重複だけがいや」。試合あり 17:00-21:30 JST の `game_live_source_policy` をデフォルト解除し、サンスポX/Webなど通常sourceも流す。重複は既存 same-fire / cross-family / X+Web dedupe gates で止める。py_compile / compileall / AST PASS、関連 pytest 41 passed。commit `639040e`、Cloud Build `dec33608-4335-40fe-8b63-9867d3e5f79d` SUCCESS、image `371-source-unlock-639040e`、digest `sha256:86370ac5b7e6...`、revision `yoshilover-fetcher-00408-l7b` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更、追加 publish/mail 回避のため手動 `/run` は未実行。自然 fire / log evidence 後に Issue close |
| `372-QA-human-readable-title-context-repair` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #41。68537 / 68622 型。`内海哲也投手コーチ、先発` / `井上温大「ミスドの券」` / `関連情報` / generic `選手「...」` のように人間に記事の核が伝わらない title を、source title / summary の literal context で恒久補正する。WP既存 post は 41 件の title + schema headline を status 確認後に補正済み、検証 `headline_mismatches=0`。py_compile / compileall / AST PASS、関連 pytest 104 passed + 3 xfailed + 16 subtests。commit `097c4c8`、Cloud Build `9faa589c-fa6d-40c9-930b-3c80e80fd076` SUCCESS、image `372-title-context-097c4c8`、digest `sha256:1f557f4c...`、revision `yoshilover-fetcher-00409-jkg` 100%、`/health` OK。Scheduler / env / Secret / X / SNS / mail 条件は未変更、手動 `/run` は未実行。自然 fire / log evidence 後に Issue close |
| `373-INSIGHT-defense-player-comparison-table` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #42。68665 型。守備系データ記事で title が選手主語なのに本文が球団順位表になる穴を、UZR / 守備率 article renderer で同ポジションの選手別比較へ変更。セ・リーグ選手名が十分なら `セ・リーグ選手別`、他球団 player rows が薄い場合も球団順位へ戻さず `巨人選手別` fallback。WP既存 post 68665 は status `publish` 確認後、title/content のみ更新済み、status 維持。py_compile / compileall / AST PASS、関連 pytest 103 passed。commit `3260e7a`、Cloud Build `afc27377-94d5-4756-9694-16daae910588` SUCCESS、image `insight-nightly:373-defense-player-3260e7a`、digest `sha256:7a3f569b...`、Cloud Run Job generation `52`。Scheduler / env / Secret / X / SNS / mail 条件は未変更、executionCount `40` 維持で手動 insight execute は未実行 |
| `374-x-post-mail-dedup-starvation-fallback` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #43。353〜355 の手動確認 mail が 24h dedup ledger を埋め、15:00 は 1 件、17:30 は 0 件で自然 mail が枯れた問題を修正。dedup は維持しつつ、dedup 後候補が default 3 件未満なら dedup-safe 候補を先頭に残して dedup なし候補で backfill。py_compile / compileall / AST PASS、x-post-mail 関連 pytest 107 passed。commit `c939b77`、Cloud Build `7a6ae843-f49c-4a23-90ed-af1d57831f30` SUCCESS、image `x-post-mail-lane:374-dedup-starvation-c939b77`、digest `sha256:739e16042fbb...`、Cloud Run Job generation `11`。Scheduler / env / Secret / WP / X / SNS は未変更、追加 mail 回避のため手動 execute は未実行。22:30 自然 fire は更新直前の旧 image で候補0件、次回 2026-05-17 07:00 JST 自然 fire で観察 |
| `375-QA-paper-layout-social-promo-skip` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #46。68812 型。`RT スポーツ報知 レイアウト担当: 5/17付 スポーツ報知` の紙面告知RTが `5連勝` / 選手語で social_news rescue され、半端な本文の記事になる穴を修正。`レイアウト担当` / `紙面レイアウト` / 日付付き新聞紙面告知は trusted social rescue / weak social rescue / template v2 / main intake で hard stop し、`paper_layout_social_promo_skip` を出す。py_compile / compileall / AST PASS、関連 pytest 113 passed。commit `ed237ea`、Cloud Build `3daeb97b-9252-4fb6-82d8-bc546ae46403` SUCCESS、image `375-paper-layout-ed237ea`、digest `sha256:3f2aff2f...`、revision `yoshilover-fetcher-00412-4kg` 100%、`/health` OK、新 revision ERROR logs 0。Scheduler / env / Secret / X / SNS / mail 条件は未変更 |
| `376-QA-person-tag-routing-and-noindex` | LIVE_DEPLOYED_OBSERVE | GitHub Issue #49。選手・首脳陣・OBの人物タグを事前作成し、RSS記事作成時は既存 WP tag ID にだけ自動付与する。2選手記事は2タグ、runtime tag新規作成なし、missing / ambiguous / no hit は log 化。py_compile PASS、person tag / WP tag / noindex / RSS integration 16 passed、WP client 66 passed、RSS related 41 passed / 3 xfailed。WP tag sync `ok_count=173` / `missing_count=0`、commit `a995071`、deploy source HEAD `242aab2` includes `a995071`、Cloud Build `43fb75f9-4f92-4b79-a204-08cc8d343d3d` SUCCESS、image digest `sha256:52ac886e...`、revision `yoshilover-fetcher-00421-vzd` 100%、`/health` OK、新 revision ERROR logs 0。WP plugin upload 後、tag archive `吉川尚輝` で `x-robots-tag: noindex, follow` と HTML robots noindex を確認。Scheduler / env / Secret / X / SNS は未変更。自然 RSS fire で実記事 tag 付与 evidence 待ち |

deploy: `insight-nightly:ca03019` / digest `sha256:a71bbe0f943c969349a61413da3a6addb016f8286e506229e0b3a3a0a76bc41f`。Cloud Build `19c2e97d-f4f9-48e9-8db4-7a303003892e` SUCCESS。Scheduler / env / Secret は未変更、手動 execute 未実行。

test: deploy 前 data-insight 関連 pytest 231 passed。full unittest は既存の `manual_intake_service` socket PermissionError、`manual_intake_service_x_post` 403 expectation、`duplicate_prevention_golden` logger call-count で赤のまま。

様子見リスク: 記事減りすぎ / まだ多い / mail過多 / 既存投稿 backfill 未実装 / title期間必須 runtime guard の live 観察待ち。次 action は次回 Scheduler 自然 fire のログ観察。

### x-post-mail scheduler 403 fix (2026-05-16 13:40 JST)

353〜355 の X投稿候補 mail lane は code / manual execute / mail send / GCS dedup write は成功していたが、07:00 / 12:00 の自然 Scheduler fire が HTTP 403 `PERMISSION_DENIED` で失敗。原因は `x-post-mail-*` Scheduler jobs の OAuth service account が `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com` になっていたこと。正常稼働中の `data-insight-*` と同じ `487178857517-compute@developer.gserviceaccount.com` へ 5 jobs だけ更新済み。schedule / env / Secret / Job image / mail body は未変更。手動 execute は追加 mail 回避のため未実行、次回自然 fire は 15:00 JST。

### 357 x-post-mail period 表示 tuning (2026-05-16 JST)

user 指示「日付だけでは分かりにくい」「直近5試合 / 直近10試合を前面」「7月成績のような月別は分かりやすい」「大手が出す全期間はいらない」を受け、`doc/active/357-x-post-mail-human-period-labels.md` を起票。repo 実装 + targeted tests 完了、status `REVIEW_NEEDED`。2026-05-16 follow-up で production GCS DB 更新状況を確認し、all-NPB DB 化後の直近5/10試合 window を `batting_logs` 巨人 row で絞る修正と、DB最新試合日が2日超古い場合に X 投稿候補 mail を候補生成前に止める freshness guard を追加。2026-05-16 14:35 JST `x-post-mail-lane:357-db-freshness-15ff032` deploy 済み、Job generation `9`。X / SNS live post、Scheduler、env、Secret、WP publish は未変更、手動 execute は追加 mail 回避のため未実行。

### insight-nightly same-day DB + no-season auto publish fix (2026-05-16 14:49 JST)

user 指示「DB当日更新はやらないの？」を受け、`--auto` target を 15:00 JST 以降は当日、朝/昼は前日に切替。auto publish に残っていた `season` split / vs opponent 経路を `weekly` / `last_7d` へ変更。commit `2949f98`、Cloud Build `a9574fbf-f26c-4a17-b977-cb56f7e94f72` SUCCESS、image `insight-nightly:358-sameday-auto-2949f98`、digest `sha256:3afff4dfe4e80791e833c149a41d3f973e9f005365f4033b599042feba8b707a`、Cloud Run Job generation `47`。Scheduler / env / Secret は未変更、手動 execute は追加 publish/mail 回避のため未実行。

### 358 local production DB pull tool (2026-05-16 JST)

DB 同士の「同期」はしない方針で決定。production source of truth は GCS `insight.db`、local `data/insight/insight.db` は生成物として扱う。ローカルが古いことによる誤判断だけを防ぐため、`src/tools/pull_insight_db_from_gcs.py` を追加し、default `/tmp/yoshilover-insight-latest.db` へ download-only pull + 最新試合日 / 巨人最新試合日 / row count を JSON 表示する。local Python に `google-cloud-storage` が無い場合は `gcloud storage cp` fallback。targeted pytest `34 passed`、production GCS read-only smoke は latest `2026-05-16` / Giants latest `2026-05-16` / staleness `0`。Cloud Run / Scheduler / env / Secret / GCS upload / WP publish / mail / X / SNS は未変更。

### 359 x-post-mail subject visibility (2026-05-16 JST)

user 指示「他の自動通知も来るから分からない」を受け、X 投稿候補 mail の件名を `📮【要確認：巨人データX投稿候補 N件】午後 2026-05-16 15:00 JST` 形式へ変更。本文冒頭にも「公開通知ではない」ことを明記。commit `902689c`、Cloud Build `a89b7e8e-b565-4c3f-aaab-40da89ec6611` SUCCESS、image `x-post-mail-lane:359-subject-902689c`、digest `sha256:b5c6aa968959351a691337c256f1d14671be4b539894c91db61ebd600824d120`、Job generation `10`。targeted pytest `69 passed`、関連 `105 passed`。候補生成 / DB / GCS dedup / SMTP 宛先 / Scheduler / env / Secret / WP publish / X / SNS は変更しない。手動 execute は追加 mail 回避のため未実行。

### 360 INSIGHT defense table comparison format (2026-05-16 JST)

user 指示「UZR は出したいが球団ごとの表形式比較が欲しい」「方針として全てが表形式」を受け、`doc/active/360-INSIGHT-defense-table-comparison-format.md` を起票。未来生成分の `anomaly_article_publisher` で、UZR / 守備率記事をセ・リーグ球団別 table 主体に変更。シンプルデータ記事の `## データ` も箇条書きから table 化。「全てが表形式」は数値・比較・根拠を table に寄せる方針として記録。production DB copy preview では `泉口友汰 / 遊撃守備` が `セ・リーグ球団別 遊撃守備の簡易UZR、巨人 6/6位 -0.088（直近30日）` と6球団表で出ることを確認。commit `269fd37`、Cloud Build `7cf61309-f315-4fb9-9a2f-5ec130c26c23` SUCCESS、image digest `sha256:0e2abc58b2704a03eb8f49481dae1f3a858986b068cd087854b38a1594af72c7`、Job generation `48`。関連 pytest `100 passed`。既存公開 post / WP update / Scheduler / env / Secret / X / SNS は触らない。手動 execute は追加 publish/mail 回避のため未実行。

### 361 INSIGHT permanent table body and title contract (2026-05-16 JST)

user 指示「恒久対応」「title は巨人の選手の名前と指数と何位と期間」「巨人サイトだから」を受け、`doc/active/361-INSIGHT-permanent-table-body-and-title-contract.md` を起票。UZR / 守備率 title を `泉口友汰の遊撃守備、巨人は簡易UZR -0.088でセ・リーグ6/6位（直近30日）` 型へ変更し、本文のセ・リーグ球団別表は維持。`insight_quality_gate` に table contract を追加し、`## データ` / `## このデータについて` / ranking / 比較 section が table でない記事、または `## データ` が bullet list に戻った記事を publish/draft 投入前に止める。py_compile / compileall / AST PASS、関連 pytest `102 passed`、production DB copy preview PASS。commit `a9b208e`、Cloud Build `b027f92a-b3f7-4aed-b448-cdded17740fb` SUCCESS、image digest `sha256:b2fb813a542a0ce7b79ea8c395f939fa3027001ce88f97bca123c2c65877ff69`、Job generation `50`。既存公開 post / WP update / Scheduler / env / Secret / X / SNS は触らない。手動 execute は追加 publish/mail 回避のため未実行。

## 2026-05-14 EVENING session summary

### close 済(本 session)

| 区分 | ticket | commit | 備考 |
|---|---|---|---|
| impl | 342-INSIGHT(=旧 GH #21) | 多数 | data-driven ranking 自動 publish 基盤 LIVE。本日 Giants 12 件 + 球団 5 件 + 異常値 5 件 publish |
| impl | DATA-INSIGHT-continuous(=旧 GH #25) | 多数 | 継続改善 system 稼働。異常値検出 8 種 + ランキング 4 軸 + 球団ランキング 7 軸 |
| ops | Cloud Scheduler 7 trigger 配備 | 設定 | 02/07/12/15/17/20/21 JST、`ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1` で Giants のみ auto publish |
| fix | SVG inline-style fix | `7da3956` | WP wpautop で `<style>` が `</p><p>` 分割していた bug、既存 17 記事一括 patch も済 |
| ci | xfail 4 pre-existing | `578a598` | baseline 一致 fail を unblock、regression 検知力は xfail で保持 |

### 残 open(別 actor lane)

| ticket | status | blocker |
|---|---|---|
| 344-INGEST(=GH #24) | CLOSED / SUPERSEDED | `doc/done/2026-05/344-INGEST-youtube-caption-draft-expansion.md`。親設計は 383 / 385 / 395 / 398 / 317 の実装済み chain に分割され、GH #24 は既に close。受け入れ観察は必要なら別 ticket。 |

### waiting(park、別 session 着手)

| ticket | status | next action |
|---|---|---|
| `doc/waiting/345-INSIGHT-fielding-and-equal-area-ratio.md` | PARKED | NPB box score の守備項目 audit、A path なら自律実装、B path なら user 判断 |

### close 済(旧)

| # | ticket | status | blocker |
|---|---|---|---|
| #21 | 342-INSIGHT | Phase 0 audit + Phase 1 spec done、impl 未着手 | last_30d batter snapshot 12 球団分 (各 5+ 選手) 蓄積待ち、想定 7-21 日後 |

next session: 朝 06:00 自然 fire 後の log 観察 (silent gap §5 in handoff doc) + #21 着手判断 (data 充足後)

## folder cleanup note(2026-05-02)

- Active folderから、明確な HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY / READY_FOR_AUTH_EXECUTOR を waiting へ移動。
- `205-COST` は done/2026-05 へ移動。
- READY / REVIEW_NEEDED で現場が拾う可能性のある ticket は勝手に close していない。

## いま active に残すもの(2026-05-13 lock)

| ticket | status | 判定 | 次 action |
|---|---|---|---|
| **303-rollback-2026-05-08-frontend-rich-body** | LIVE_VERIFIED (Tier 1+2 audit pass) | manual-intake-service / yoshilover-fetcher 両方 `d34072a` 反映済み | manual-intake の rich body 装飾を 5/8 朝 audit Tier 1+2 で 5 件 fix 反映済み。Tier 3 (49 件 doc-only) は別便、現場は live 観察のみ |
| **MANUAL-INTAKE-QUALITY-PARITY-2026-05-08** | DESIGN_REQUIRED | **user 判断待ち**: 「手動 vs 自動」のどの軸(本文長 / 装飾 / 自動化)を直すか | 5/8 PM session 調査済、apply_rss_pipeline_enrichment の nomotoke marker gate を発見、現状 RSS auto は marker 付与なしで装飾 skip。user に A/B/C/D 軸を提示済み、回答待ち |
| **FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08** | READY_FOR_AUDIT | 5/7 enrichment 装飾(ToC / 順位表 / share / tag chip / AI badge / JSON-LD 等)が live で 0% / 100% gap。¥0、デグレ 0 の audit + narrow fix | Phase A 受動 audit から開始、root cause 特定 → narrow fix → unit test。3 auto jobs の redeploy は別 ticket |
| **H3-STRUCTURE-UNIFY-2026-05-08** | READY_FOR_IMPL | H3 が 30+ 種類混在 → 12 set に統一、「📣 関連投稿」3 形式を「💬 ファンの声」に統一、Gemini prompt 自由生成禁止 | ¥0、4-6h、Phase A nomotoke renderer 統一から |
| **DIGEST-DAILY-MORNING-2026-05-08** | READY_FOR_IMPL | 朝まとめ 1 日 1 本(前日 + 翌日 + 順位 + ファン声 を集約)。既存 block 再利用 | ¥0、4-6h、giants-morning-catchup 内に組み込み |
| **SIDEBAR-WIDGETS-2026-05-08** | READY_FOR_IMPL | sidebar 5 widget(直近5試合 / 順位 / streak / 次戦 / 1年前の今日)。WP plugin 側 | ¥0、6-8h、phase 分割で順次 |
| **305-QA featured media source priority** | LIVE_DEPLOYED, USER_ACCEPTANCE_PENDING | source eyecatch を最優先し、同一 source image の WP media reuse を優先。source 不在時は東京ドーム写真 fallback。legacy Ichiro mixed media `36062` は unsafe として除外 | Codex B が repo-only で impl/test/deploy 完了。revision `00293-7lc`、`guarded-publish` / `publish-notice` success、deploy 後新規記事 0 件。次の自動生成 window で user が受け入れ判断。publish / mail / scheduler / env / Cloud Run 設定は追加変更なし |
| **319-QA fetcher topic dedup and slot fill** | REVIEW_NEEDED | 自動起動時に同じ話題の重複記事が10枠を消費する問題を narrow 修正する ticket。head/bat contact 事故の再現テスト赤→緑、related/full pytest green | diff review + commit 判断待ち。publish / mail / scheduler / env / Cloud Run / SEO / source追加は不可触 |
| **CATEGORY-RESTRUCTURE-2026-05-08** | DESIGN_REQUIRED | 「コラム」catch-all 解消、「試合中継」新 category 抽出、巨人 tag 化 | user 判断必要(WP admin で新 category 作成)、Claude は設計 + automation script |
| **EXTERNAL-MONITOR-APPS-SCRIPT** | READY_FOR_USER_SETUP | user 作業 10 分(GAS で完全独立 ping) | 明日朝 yoshilover infra 全死シナリオ用の独立 safety net、user 任意 |
| **334-QA-player-voice-multi-source-digest-subtype** | DESIGN_LOCKED / READY_FOR_PHASE_0_AUDIT | 2026-05-14 user chat lock。のもとけ風 multi-source digest subtype。title 3-token literal assembly(player「セリフ20-40字」event)、AI 禁止、player-agnostic、forward-only、複数 web 媒体サイト集約 | Phase 0 read-only audit から開始。`title_template_assembler.py` 追加位置 + `rss_fetcher.py` clustering hook + source extractor coverage を audit、結果 doc 追記。memory lock: `feedback_title_no_ai` / `project_multi_source_digest_subtype` |
| **OPERATING_LOCK** | ACTIVE_LOCK | **必要。常時参照** | 事故防止ルール。変更は慎重に、src 実装とは混ぜない |
| **assignments** | ACTIVE_BOARD | **必要。現在地** | 本ファイル。active を増やしすぎない |

## 認識しているが今 session 触らないもの(明日朝 06:00 検証 window 関与)

| 項目 | 状態 | 触らない理由 |
|---|---|---|
| **`guarded-publish:eb38006-job`** (job) | 5/8 朝 06:40 JST build、scheduler `*/30 * * * *` ENABLED、明朝 06:00/06:30 fire | 5/8 朝 emergency 10 commit 未反映で draft 昇格挙動が古い可能性。redeploy が必要だが scheduler / image 変更は user 同意境界(autonomous_scope_v2)。明日朝検証で挙動異常があれば次便で扱う |
| **3 auto jobs(broadcast / lineup / postgame)** | `manual-intake-service:b432801`、5/8 0bf8900 / d34072a 未反映 | 明日朝 06:00 検証 window 範囲外(11:30 / 17-18 / 22:30 fire)、検証直後の判断で OK |
| **`draft-body-editor:c796c77`** (job) | 5/2 build、scheduler `0 */3 * * *` 06:00 fire | 5/8 emergency 範囲外、観察のみ |

## done へ送ったもの

仕様変更後も役割は残るが、実装と live 反映が済んだため active から外した。

| ticket | close 判定 |
|---|---|
| **234-impl-1** farm_result / farm_lineup mail UX | `75d9407` で実装済み、後続 234-impl-6 で本文側も補強済み |
| **234-impl-2** first-team postgame / lineup mail UX | `9e98c96` で実装済み |
| **234-impl-3** program / roster notice mail UX | `dd158fb` で実装済み |
| **234-impl-4** injury_recovery / default_review mail UX | `ac23529` で実装済み |
| **234-impl-5** first-team postgame body hardening | `bc3b771` で実装済み、live image `cf8ecb9` へ反映済み |
| **234-impl-6** farm_result / farm_lineup body hardening | `7567e6f` で実装済み、live image `cf8ecb9` へ反映済み |
| **242 parent / 242-B** auto-publish incident + entity contamination | 子 ticket 実装済み。63844 型は `16304f2` + `cf8ecb9` で detector live |
| **243 emit observability** | `499966d` で実装済み、draft-body-editor / fetcher 系の observability lane に反映済み |
| **244 numeric guard** | `f2cc8a3` で実装済み、guarded-publish / X suppress の本線に反映済み |
| **244-B repair anchor** | `e04eee1` で実装済み、後続 wire 完了 |
| **244-followup subtype-aware severity** | `9074c8a` で実装済み |
| **244-B-followup stub to module wire** | `cf8ecb9` で実装済み、draft-body-editor image へ反映済み |
| **278-QA RT title cleanup** | `5a253a2` (TITLE-SEO-POLISH-001) で RT prefix 除去 + 末尾 filler trim 実装。yoshilover-fetcher / manual-intake-service / 3 auto jobs に live 反映済み |
| **279-QA mail subject clarity** | `6349995` (MAIL-SUBJECT-DETAIL-001) で件名 prefix を 公開済｜subtype / 要review｜reason / hold｜reason / 要確認(古い候補)｜subtype に拡張。publish-notice job 後段 rebuild(`b816f06-job`)に live 反映済み(2026-05-08 close) |
| **280-QA summary excerpt cleanup** | `74b0cec` (MAIL-MINIMAL-BODY-001) で本文を title+URL のみに簡素化したため summary を磨く意味なし。publish-notice job に live 反映済み |
| **304-QA player / manager common quality guard** | `6fb818a` で player / manager 共通品質 guard を実装し、Cloud Run revision `yoshilover-fetcher-00285-5bg` へ deploy 済み。post-deploy `/run` 完走、`guarded-publish` / `publish-notice` manual trigger success、運用継続可 |
| **246-viral-topic-detection** | 8 日 parked。SNS バズ検出 → 既存 RSS 裏取り → routing 構想は良いが、現フェーズ(noindex 検証 + 本文品質 + cost)と競合。再着手したくなれば doc/done/2026-05/ から復元 |
| **247-QA-postgame-strict-slot-fill-poc** | 8 日 parked。LLM JSON 抽出 + slot-fill POC は野心的だが LLM 本文生成に踏み込む変更で、現 policy(LLM 本文補完禁止)と衝突。再着手時は scope 再設計必要 |
| **254-QA-starter-innings-normalization** | 8 日 parked。投手回数表記揺れ統一 helper 構想。fact_consistency false negative の対策だが、現状観察で具体被害が顕在化していない。被害が見えたら再起 |
| **245 front hide auto-post category label** | 2026-05-07 audit で実装済 verify 完了。`yoshilover_063_is_internal_auto_post_category` helper + 11 callsite で sidebar/article-card/related に適用済 |
| **277-QA title player name backfill** | `src/title_player_name_backfiller.py` + rss_fetcher 統合済、prod live。tests pass |
| **229 Gemini cost governor + LLM call reduction** | `ENABLE_PER_POST_24H_GEMINI_BUDGET=1` + preflight gate ON 等、主要 sub 全部 prod 反映済 |
| **250-QA-1 manager_quote_zero_review** | rss_fetcher の `MANAGER_QUOTE_REVIEW_SUBTYPES` + event emit 実装済 |
| **250-QA-3 fetcher weak generated title** | `is_weak_generated_title` (title_validator.py) + 「前日コメント整理」「ベンチ関連の発言ポイント」phrase 入り |
| **275-QA github-actions tests failed audit** | CI 直近 3 run 全 SUCCESS、回復済 |
| **281-QA farm_result backlog allowlist** | guarded_publish_runner の `BACKLOG_NARROW_FARM_RESULT_SUBTYPES` + 24h cap 実装済 |
| **282-COST gemini preflight article gate** | `ENABLE_GEMINI_PREFLIGHT=1` prod env で ON 済(memory 282 CONDITIONAL_USER_GO 達成) |
| **289-OBSERVE post_gen_validate mail notification** | `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` ON、silent skip 解消済 |
| **290-QA weak title rescue backfill** | `weak_title_rescue.py` + `ENABLE_TITLE_GENERIC_COMPOUND_GUARD` 等 5 関連 ENABLE_* flag prod ON |
| **293-COST preflight skip visible notification** | `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1` ON |
| **297-OPS pause codex-shadow-trigger** | scheduler state = PAUSED、実行済 |
| **248-MKT-2/3a same-game articles linking + display matrix** | parked、現在の運用ループ閉鎖 priority より外。再開時は doc/done/2026-05/ から復元 |

## waiting へ送ったもの

| ticket | 理由 | 戻す条件 |
|---|---|---|
| **205 GCP runtime drift audit** | 必要だが、今の本文ハルシネ対策の実装ではない。定期監査として待機 | Cloud Run image / Scheduler / logs に不整合が疑われた時 |
| **238 night-draft-only + morning report** | 必要だが、まず 234/244 の本文品質を安定させる。夜間運用は次の運用改善 | 本文品質が落ち着き、夜間 publish/mail 抑制を入れる段階 |
| **246-MKT today giants fan guide** | HOLD。247-QA amend と postgame strict 試合日観察が先。現場に投げない | 246-MKT 判断後に、必要なら実装 ticket として個別に戻す |
| **255-MKT fan guide expansion + comment badge** | HOLD。248 系の既存 ticket と採番衝突しないよう 255 に採番 | 246-MKT 観戦ガイドが成立し、コメント/反応導線を検討してよい時 |
| **249-INGEST live game ingestion expansion** | HOLD。Cloud Run / Scheduler 影響が大きい構想 | user が live ingestion の負荷とリスクを理解して明示 GO した時 |
| **256-QA manager/player quote strict subset** | HOLD。250 系の既存 ticket と採番衝突しないよう 256 に採番 | 247-QA の試合日観察後、コメント系を短い事実記事として分ける価値がある時 |
| **260-MKT fan-original article types and templates** | HOLD / design only。RC / T1 / 262-QA / 263-QA observation 完了 + user 明示 GO 後に 261-MKT-PILOT 起動判断 | 大手新聞の後追いではない巨人ファン向け独自記事型 6 型のテンプレ設計、実装しない |
| **261-MKT-PILOT (予約)** | HOLD / 261-PILOT 起動条件 達成後 RESUMABLE | 260-MKT で設計した 6 型から手動/半自動で 3 型 pilot、3-5 本評価、実装ではない |
| **234-impl-7 probable_starter / pregame body hardening** | READY_FOR_AUTH_EXECUTOR。repo実装済みだが残りは live handoff / observation 判断のため waiting へ移動 | live反映が必要な時だけ、Acceptance Pack と rollback target を確認して戻す |
| **291-OBSERVE candidate terminal outcome contract** | WAITING_PARENT / subtask-9 + subtask-10b live apply 完了。fetcher image `e0a58bb` / revision `00186-9cl` へ更新し、`ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE=1` と `ENABLE_POSTGAME_STRICT_FACT_RECOVERY=1` を反映、既存 narrow flags 維持確認済み | 30-60min verify。Scheduler 次回 fire 以降で `weak_title_subtype_aware` / `postgame_strict_fact_recovery` event と scope-eligible postgame candidate の publish/review outcome を観測する。親 ticket 自体は waiting 維持、global gate 緩和はしない |
| **318-A..E social video full connect** | 318-C REVIEW_NEEDED / 318-A,B,D,E READY_DOC_ONLY。YouTube / Instagram / OB動画の完全接続を5本に分割。初期はreview/draft優先、publish/mail/scheduler/env/deploy/X/SEO不可触 | 318-C safe title fallback は repo実装 + full pytest PASS。次に進めるなら 318-A YouTube registry intake を小さく実装GO。 |
| **319-QA fetcher topic dedup and slot fill** | REVIEW_NEEDED。次の記事公開から重複話題で10枠を消費しないための narrow fix ticket | 再現テスト赤→緑、`src/rss_fetcher.py` 候補選別のみ修正済み。diff review + commit 判断待ち。deployは別GO |
| **320-FRONT scroll ads UIUX AdSense slot control** | READY_FOR_IMPL_AFTER_USER_GO。のもとけ型の scroll / sticky AdSense slot UIUX。dummy-only ではなく、既存または user 確認済み AdSense slot 前提 | まず Phase 0 read-only audit で repo / live DOM / WP 実設定を確認。記憶から再構成 / silent skip / 自己評価OKは禁止。publish/mail/scheduler/env/Cloud Run/GitHub Actions/SEO は不可触 |
| **323-QA source body excerpt clean truncation** | BLOCKED_USER_DIFF_REVIEW。`314-QA-rss-source-body-excerpt-followup` 関連。ブログ本文の `📖 本文抜粋` が600文字化後も途中切れ / UI・関連記事混入に見える問題を狭く扱う | repo local 実装 + 回帰テスト + full unittest OK。diff review と commit 判断待ち。publish / mail / scheduler / env / Cloud Run / X / SEO / featured_media は不可触 |
| **251/252/253/264/274/283/288/294/295/296** | HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY 系。active から waiting へ整理 | 各 ticket の解除条件または user GO が来た時 |

## いま動かす指示(2026-05-13 lock)

### close 済 (2026-05-13)

- **RESTORE-2026-05-08-MORNING-RELIABILITY**: LIVE_VERIFIED → `doc/done/2026-05/` 移動。5/13 朝 (06:01 / 07:01 / 08:01 JST) で投稿=9 / 2 / エラー=0、cron 安定稼働確認
- **2026-05-12 evening P0 UnboundLocalError incident**: hotfix `802511f` + `b8a7f01` 復旧確認済 (revision `00417-wuw` 100%、5/13 朝 publish 投稿=9/2 / エラー=0)。incident log は `docs/handoff/session_logs/2026-05-12_evening_INCIDENT_publish_unbound_local.md` (verify note 追記済)

### user 任意作業

- B 案 GAS 独立 ping 設定(10分): `doc/active/EXTERNAL-MONITOR-APPS-SCRIPT.md`
- 重複記事削除判断: 山野5勝 4本(64878/64879/64882/64883) / 5/6試合結果 2本(64983/64985) / 三塚二軍 2本(64861/64945)
- 若手 17人 eyecatch upload(WP media に upload で fallback 解消)

### 現場 (Claude / Codex) の不可触

- すでに deploy 済の 4 image を勝手に rollback しない
- 5/8 設定済 5 env flag を user 確認なしに変更しない
- `PUBLISH_NOTICE_BURST_THRESHOLD=-1` は user 同意済、変更しない
- 04-06時 publish-notice silence は user 同意済、戻さない
- giants-morning-catchup 04:30 schedule は user 同意済、戻さない

## 役割

| 略号 | 役割 | やること |
|---|---|---|
| **Claude** | 現場管理 / accept / push / live監視 | 開発しない。src/tests編集しない。commitしない |
| **Codex A** | ops / GCP / WP / mail / build / scheduler infra | live mutation は authenticated executor 境界を守る |
| **Codex B** | evaluator / validator / article quality / numeric / template | 234-impl-7 など品質系を narrow に実装 |
| **User** | 最終判断 | 重要な live mutation / WP記事判断 / scope拡張だけ判断 |

Codex C / Codex-M は使わない。

## ad hoc live ops

| lane / scope | status | 次 action |
|---|---|---|
| **Lane FF / BUG-004+291 replay-window dedup (Task 37)** | LIVE_APPLIED | `publish-notice` image `4231805` + `ENABLE_REPLAY_WINDOW_DEDUP=1` を反映済み。次の manual replay / scheduler overlap で `DUPLICATE_WITHIN_REPLAY_WINDOW` 観測を確認する |
| **Lane JJ / BUG-004+291 fetcher fan-important narrow exempt** | REPO_IMPL_READY | code commit `1ccda1b` 済み。次は authenticated executor が `yoshilover-fetcher` image `:1ccda1b` build/update + `ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT=1` apply、その後 5-15 分 fetcher cycle で `fetcher_fan_important_narrow_exempt` event と rescued draft/publish terminal state を観測する |
| **Lane KK / 64424-64461 incident ledger + publish-forward audit** | LEDGER_READY | 38件棚卸し完了。分類 `B4 / C2 / D6 / E23 / F3`、safe rescue `0`。`64437` / `64447` は publish-notice state drift で STOP lock、次は Claude が ledger review / push / follow-up 起票 |
| **Lane MM / 64437 publish-notice phantom publish marker narrow fix** | REPO_IMPL_READY | repo audit + strict-stamp fix + tests 完了。次は authenticated executor が `publish-notice` image build/update と `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP=1` apply、その後 `64437` / `64447` 再発有無と new history stamp を観測する |
| **Lane LL / BUG-003 64424 revert actor + WP revert guard** | REPO_IMPL_READY | `64424` は repo-visible evidence 上 true revert ではなく、`publish_notice` direct-publish seed による phantom publish marker。`src/wp_client.py` に `ENABLE_WP_REVERT_AUDIT_LEDGER` / `ENABLE_WP_PUBLISHED_REVERT_GUARD` を追加し、publish 済みから `draft/private` への repo-owned mutation を audit/block できる状態にした。`tests.test_wp_client` と `tests.test_guarded_publish_runner` pass。次は Claude が doc review / commit review / 必要なら authenticated executor へ build+env plan を handoff |
| **Lane NN / 64432-64461 quality NG 3件 audit + ticket assignment** | REPO_DOC_READY | `64432` は 277 insufficiency + 290未live、`64453` は元巨人OBの非野球 relevance 漏れ、`64461` は Blue Jays→Giants entity contamination と判定。次は Claude が ledger review / push / per-id live judgment(A/B/C) と follow-up ticket 起票 |
| **Lane PP / article body quality v1 active repair + per-id preview** | REPO_IMPL_READY | Lane OO guard維持のまま `ENABLE_H3_COUNT_GUARD` / `ENABLE_ENTITY_MISMATCH_REPAIR` を追加。preview runner と 5 candidate dry-run ledger を作成し、full pytest は `2246 pass / 4 pre-existing fail` で据え置き。次は Claude が preview ledger review / commit review / user preview judgment を進める |
| **Lane QQ / body template v2 narrow tune (related-post H4 + social tone cleanup)** | REVIEW_NEEDED | rollback 後の narrow fix として、v2 ON 時だけ `📌 関連ポスト` を `<h4>` へ降格し、`social_v2` fallback の「目を引きます」を除去。新規 preview test で live踏襲 3 sample の `H3<=2` / forbidden phrase 0 hit を確認済み。次は Claude が commit review / push / user preview judgment を進め、reflip は別便で扱う |
| **Lane B / RSS type classification narrow fixes (5 flags)** | REVIEW_NEEDED | `src/rss_fetcher.py` に 5 本の default-OFF flag を追加し、RSS 型 drift 修正を narrow 実装。`tests/test_rss_fetcher_type_routing_flags.py` を追加し、full pytest は `2315 pass / 4 pre-existing fail` で据え置き。次は Claude が commit review / push judgment を行う |
