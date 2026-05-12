# 2026-05-12 eyecatch player photo 優先昇格 + 同 media 連発 dedupe(D 案)

## 1. 今回の目的

- 自動 RSS path の featured_media 選択ロジックを 2 段で恒久対応する:
  - **B(player photo 優先昇格)**: title に巨人選手が 1 人だけ確定し、その選手の photo が WP /media に存在する時は、source 記事画像より **その選手 photo を優先** する。
  - **C(同 media 連発 dedupe)**: 直近 1 時間以内に同じ `media_id` が既に featured_media として使われていたら、その media は今回スキップして候補リストの次へ送る。すべて捨てたら東京ドーム fallback。
- 対象は **今後の自動生成記事のみ**。過去 publish の WP 記事は一切触らない(user 方針)。
- user 体感事例:
  - id=66582「戸郷翔征、無失点投球」が `fm=66577`(source 記事 generic 画像)→ B で **戸郷の顔(66521)** にする。
  - id=66578 / 66580 / 66582 が同じ `fm=66577` 3 連発 → C で多様化、3 件全部同じを止める。

## 2. 今回触る範囲

- `src/rss_fetcher.py`
  - `_upload_featured_media_with_fallback` または直前段の featured_media 解決 path
  - 新規ヘルパー `_resolve_high_confidence_player_media_id(title, wp)` を rss_fetcher 側に追加(`player_eyecatch_resolver.resolve_eyecatch_from_title` を `allow_existing_person_media=True` で薄く wrap、cache miss 時の remote /media lookup も許可)
  - 新規ヘルパー `_recently_used_featured_media_ids(window_seconds)` を追加(WP REST `/posts?after=<window>&_fields=featured_media` を読んで直近 1h で使われた media id を Set で返す)
  - call site の featured_media 決定順を **「高信頼 player photo → source 候補(C で dedupe)→ 東京ドーム」** に並べ替え
- `src/tools/manual_intake.py` は **触らない**(本 ticket は自動 RSS path 限定)
- `src/player_eyecatch_resolver.py` は **触らない**(API はそのまま使う)
- 関連テスト
  - 新規 `tests/test_rss_fetcher_eyecatch_priority_and_dedupe.py`
- env 新規 1 つ(optional kill switch)
  - `EYECATCH_PLAYER_PRIORITY_DISABLED=1` で B を無効化(現状に戻す)
  - `EYECATCH_DEDUPE_RECENT_DISABLED=1` で C を無効化
- 作業ログ Markdown(本ファイル)

## 3. 今回触らない範囲

- 公開済み WP 記事の本文 / title / status / featured_media の修正
- WP 管理画面操作
- env / Secret / Scheduler / Cloud Run service 設定(env は新規追加のみ、既存変更なし、default OFF)
- publish / mail / X 投稿 gate
- フロント / CSS / theme / Plugin / AdSense
- アイキャッチ以外の path
- LLM (Gemini) prompt の構造変更
- `src/tools/manual_intake.py`
- `src/player_eyecatch_resolver.py` の resolve_eyecatch_from_title 本体
- `src/source_article_body_extractor.py`
- `nomotoke-source-excerpt` 系(別 ticket で完了済)
- `_source_excerpt_matches_context` guard(別 ticket で完了済)
- 305-QA で殺した `diversified_pool fallback`(復活させない)
- 東京ドーム fallback の `media_id=65953` 値
- unrelated dirty files / logs / data / build artifacts

## 4. 影響範囲

- 自動 RSS path で作られる今後の draft / publish の `featured_media` が以下のように決まる:
  1. **B 経路**: `detect_person(title)` が単独 giants 選手を返し、`resolve_eyecatch_from_title(allow_existing_person_media=True)` が cache hit する場合 → その player photo を即採用(source 候補を見ない)
  2. **source 経路**: B が無ければ、従来通り `_extract_source_article_image_urls` → `_filter_image_candidates` → `_upload_featured_media_with_fallback` のチェーンで source 候補を解決
  3. **C dedupe**: 上で候補が決まる前 / 決まった後に、直近 1h で同 media が使われていたら捨てて次へ
  4. **東京ドーム fallback**: 全部捨てたら `65953`(304-QA の現行 fallback)
- 望ましい影響:
  - 戸郷 / 岡本 / 丸 / 坂本 / 中山 / 浅野 / 大勢 / 山﨑 等、本日 41 人 pre-warm 済の主力選手記事は **その選手の顔** が貼られる
  - 同 source 由来の連続 publish で同じ source 画像が 3 連発する事象が消える
- 潜在的な副作用:
  - source 画像が「本来その記事に最適だった」case で player photo に置換されてしまう可能性
    - 例:選手復帰会見の生写真 vs cache 内の汎用 player photo → cache が古いと違和感
    - mitigation: cache 経路は `_is_unsafe_eyecatch_media_id` で既に 36062(一郎 mixed)等を除外、新規 unsafe 入れない
  - C の WP REST 呼び出しで 1 回追加リクエスト(`/posts?after=<1h>&_fields=featured_media&per_page=20`)
    - cost: 1 publish あたり 1 リクエスト追加、許容範囲
    - 失敗時 try/except で C は skip → 従来動作

## 5. 実行予定テスト

- 赤確認(red-first):
  - 戸郷 title + source 画像 url 渡したら、現コードでは source 画像が選ばれることを確認
  - 同 media_id が直近 publish に存在する状態を mock しても、現コードでは dedupe されないことを確認
- 追加テスト:
  - **B**: title「【巨人】戸郷翔征、無失点投球」+ cache hit (66521) → featured_media = 66521(source 候補無視)
  - **B negative**: title「巨人 vs 広島 試合速報」(選手単独確定なし)→ B 不発、従来 source 経路
  - **B negative**: title「【巨人】平山功太、ダイビングキャッチ」+ 平山 cache miss(photo なし)→ B 不発、source / 東京ドーム へ
  - **B kill switch**: `EYECATCH_PLAYER_PRIORITY_DISABLED=1` 設定下では B 不発
  - **C**: source 候補 [66577] + 直近 1h に fm=66577 既使用 → C 発動、東京ドームへ
  - **C dedupe + multi candidate**: 候補 [66577, 66491] + 66577 直近使用 → 66491 採用(dedupe で次へ)
  - **C kill switch**: `EYECATCH_DEDUPE_RECENT_DISABLED=1` で C 不発
  - **B + C 連動**: 戸郷 photo (66521) が直近 1h で別記事に使われていても B 内では使う(C は B path には適用しない、player photo は同選手記事間で被って OK)
- 関連テスト:
  - `python3 -m unittest tests.test_rss_fetcher_eyecatch_priority_and_dedupe`
  - `python3 -m unittest tests.test_featured_media_fallback`
  - `python3 -m unittest tests.test_featured_media_helpers`
  - `python3 -m unittest tests.test_player_eyecatch_resolver`
  - `python3 -m unittest tests.test_rss_fetcher_source_body_excerpt_auto`
- 全件:
  - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 公開済み記事の修正が必要になったら停止
- env / Secret / Scheduler / Cloud Run 設定変更が必要(新規追加 2 env 以外)になったら停止
- `_source_excerpt_context_terms` / `_maybe_insert_source_body_excerpt` / `extract_article_body_excerpt` の改修が必要になったら停止
- 305-QA で殺した diversified pool を復活させる設計が必要になったら停止
- `resolve_eyecatch_from_title` の API 改変が必要になったら停止
- C の WP REST 呼び出しが 1 publish あたり 2 リクエスト以上になる設計が必要になったら停止
- 全件 suite が今回差分起因で赤になり、原因が今回差分以外と切り分けられない場合は停止
- B が「player photo 優先で source 画像を全部捨てる」 broad path で manual_intake 側に副作用が出る場合は停止

## 7. 禁止事項

- 記憶から再構成しない
- silent skip しない
- 自己評価 OK で済ませない
- `git add -A` しない
- 指示外のファイルを触らない
- 公開済み WP 記事を直さない
- source 追加やソース方針変更に広げない
- title / publish gate / LLM prompt をついで修正しない
- 305-QA の `diversified_pool` を復活させない
- 東京ドーム fallback media_id 65953 を変えない
- `_is_unsafe_eyecatch_media_id` に新規 ID を追加しない
- manual_intake.py を触らない
- player_eyecatch_resolver.py の API 本体を変えない
- env / scheduler / secret / Cloud Run service 設定を変えない(env 新規追加 2 つは default OFF で apply)
- frontend / CSS / theme / Plugin を変えない
- 個別媒体名の blacklist / whitelist だけで済ませない

## 8. 想定されるデグレ

- B 適用で「source 由来の正しい生写真」が無視され、cache の generic player photo が貼られて違和感
  - mitigation: pre-warm 41 人は Wikipedia ja の選手 page og:image (CC-BY-SA) 由来で、一定の品質保証
- B 適用で複数選手が title に登場した時、`detect_person` が 1 番手選手だけを返す → 本当の主役と違う可能性
  - mitigation: detect_person は unique-surname / 完全一致を優先する設計、複数人時は None を返すケースも多い
- C で同 media を捨てた結果、東京ドーム連発が増える(平山功太 等 photo 不在選手記事で発生)
- C の WP REST 呼び出し失敗 → C 動かず、従来動作 (try/except で吸収)
- env kill switch を user が触り損ねた時、想定外の挙動になる(both default OFF で apply、後で env で ON する設計推奨)
- B の player photo lookup で WP /media remote search が起きると新規 record の publish 遅延が発生する可能性
  - mitigation: cache 41 人は本日 batch で WP /media に upload 済、cache file (config/player_eyecatch_map.json) にも保存済、再 search 不要
- 305-QA で殺した「unrelated player photo を選手 X 記事に貼る」回帰は B では起きない(detect_person 単独確定 + 同名 cache の組み合わせのため、別人の photo は付かない)

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-12 18:55 JST | 作業記録 Markdown 作成、user GO 待ち | 本ファイル作成のみ実施、code は一切触らず |
| 2026-05-12 19:00 JST | user GO 受領、red-first 11 test 投入 → 10 errors / 1 pass で red 確認 | TypeError と未実装で予想通り |
| 2026-05-12 19:02 JST | B / C 実装 + `WPClient.list_recent_featured_media_ids` 追加 | manual_intake / resolver 本体は無変更維持 |
| 2026-05-12 19:04 JST | targeted 117 test green + 全件 3603 件中 1 件 pre-existing fail のみ | 回帰 0 件、baseline diff = 0 |
| 2026-05-12 19:06 JST | commit `2d5c334` push、cloudbuild `:2d5c334` SUCCESS、revision `00393-fif` traffic 100% | `/health` 200、active image 確認済 |

## 10. Regression Memo欄

- これは 305-QA(eyecatch fallback narrow)→ 本日 ca3fcb9(cross-publisher filter)→ c64b8e7(高信頼 single-player path)→ Wikipedia pre-warm 41 人 → 1378a91(自動 RSS excerpt path)→ ce4116f(Giants CSS)→ 1810561(guard pollution URL detector)の延長線にある「最後の調整」ticket。
- B の核心: c64b8e7 で `wp_client.py` 側に入れた「detect_person で単独確定時のみ allow_existing_person_media=True」path を、rss_fetcher 側にも対応させ、**source 経路より優先する** ように順序入れ替え。
- C の核心: 同 source URL の異記事が複数連続 publish される時、WP /media が URL hash slug で同 media を再利用する path がある(`_upload_featured_media_with_fallback` line 13657 周辺)。これを「直近 1h で使われた media は別候補へ」guard する narrow 追加。
- 305-QA で殺した `diversified_pool` は **復活させない**。B は単独確定のみで diversified ではない、混同しない。
- 平山功太 / 石塚裕惺 / 小濱佑斗 等の photo 不在選手は B では救えない(cache miss 経路)、東京ドーム fallback で確定。今後 user が手 upload するか、新 wiki page ができた時に再 batch する。
- 関連 commit:
  - 305-QA(5/9-10): fallback narrow、東京ドーム fixed
  - ca3fcb9(5/12 17:00): cross-publisher news domain filter
  - c64b8e7(5/12 17:00): 高信頼 single-player path(wp_client 側)
  - 1378a91(5/12 17:50): 自動 RSS path に source body excerpt block 適用
  - ce4116f(5/12 17:52): Giants CSS for excerpt block
  - 1810561(5/12 18:15): excerpt guard に cross-publisher URL pollution detector
- 観察 plan: deploy 後 2-3 サイクル(scheduler 発火 2-3 回分)observe して、戸郷 / 岡本 / 丸 等の主力記事に正しく photo が貼られること、同 media 3 連発が消えていることを確認。

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `src/wp_client.py`
- `tests/test_rss_fetcher_eyecatch_priority_and_dedupe.py`(新規)
- `docs/work_logs/2026-05-12_eyecatch-player-priority-and-dedupe.md`(本ファイル)

manual_intake / player_eyecatch_resolver / source_article_body_extractor は touch せず。

### 2. diff概要

**`src/rss_fetcher.py`** に新規追加:

- `_detect_person_for_eyecatch_priority(title)` — `player_eyecatch_resolver.detect_person` の indirection ヘルパー(test patch 用)
- `_resolve_high_confidence_player_media_id(title, wp, logger)` — **B 本体**。`detect_person` で単独確定 + env kill switch OFF + resolver 経路で id 取得時のみ返す。例外 / cache miss / 検出失敗で 0 返却
- `_recently_used_featured_media_ids(wp, window_seconds, logger)` — **C 本体**。`wp.list_recent_featured_media_ids` を呼んで recent ids set を返す。env kill switch / 例外で空 set 返却
- `_upload_featured_media_with_fallback` に `recent_used: set[int] | None = None` kwarg 追加、候補の `existing_media_id` が `recent_used` にあれば log + continue で次候補へ
- call site(line 23275 周辺)を変更: B → C(recent set 取得)→ source path の順、`featured_media == 0 and _article_images` の時のみ source path に進む

**`src/wp_client.py`** に新規 method `list_recent_featured_media_ids(window_seconds=3600, per_page=30)` 追加 — `/posts?status=publish,draft&after=<window>&_fields=id,featured_media&per_page=N&orderby=date&order=desc` の 1 リクエストで recent ids list を返す。

新規 test 11 件追加(B 4 件 + C helper 3 件 + `_upload_featured_media_with_fallback` dedupe 4 件)。

deploy: commit `2d5c334`、image `:2d5c334`、revision `yoshilover-fetcher-00393-fif` traffic 100%。

### 3. 実行したテスト

1. 赤確認(red-first):
   - `python3 -m unittest tests.test_rss_fetcher_eyecatch_priority_and_dedupe` 実装前実行 → `Ran 11 tests ... FAILED (errors=10)`(TypeError `recent_used` 引数なし + 関数未定義)
2. 緑確認:
   - 同 test → `Ran 11 tests ... OK`
3. 関連 test 117 件:
   - `tests.test_rss_fetcher_eyecatch_priority_and_dedupe tests.test_featured_media_helpers tests.test_featured_media_fallback tests.test_player_eyecatch_resolver tests.test_rss_fetcher_source_body_excerpt_auto tests.test_wp_client` → `Ran 117 tests ... OK`
4. 全件:
   - `python3 -m unittest discover -s tests` → `Ran 3603 tests in 74.270s` `FAILED (failures=1)`
   - 1 件 fail: `test_main_passes_36_hour_window_for_postgame_skip_check`(これまでの ticket と同じ pre-existing failure、本変更と無関係)
5. deploy verify:
   - commit `2d5c334` push 成功
   - cloudbuild `:2d5c334` SUCCESS(1M56S)
   - `gcloud run deploy` + `update-traffic --to-latest` で revision `00393-fif` traffic 100% 確認
   - `/health` 200
   - active image: `:2d5c334` 確認

### 4. テスト結果

- 新規 11 test 全 PASS
- 関連 test 117 件全 PASS
- 全件 3603 件中 PASS 3602 / FAIL 1(pre-existing、本変更と無関係)
- deploy 健全(`/health` 200、active image 反映)

### 5. 残った懸念

- 平山功太 / 石塚裕惺 / 小濱佑斗 等 photo 不在選手の記事は B では救えない、東京ドーム fallback 確定。user が手 upload するか wiki page 待ち。
- C で「東京ドーム連発」が増える可能性(同 source 由来の複数記事 publish 時、source 画像を捨てると東京ドーム へ流れる)。観察必要。
- WP REST `/posts?after=` が 1 publish あたり 1 リクエスト追加、cost 微増(数 ms オーダー)。許容範囲。
- B で「source の生写真より cache の汎用 photo が出る」違和感の可能性。pre-warm 41 人は Wikipedia ja の CC-BY-SA og:image なので汎用性は許容範囲。
- `EYECATCH_PLAYER_PRIORITY_DISABLED` / `EYECATCH_DEDUPE_RECENT_DISABLED` の env kill switch は **default OFF で apply**、必要に応じて Cloud Run 側で `gcloud run services update --update-env-vars=...` で ON にできる。
- pre-existing failure `test_main_passes_36_hour_window_for_postgame_skip_check` は別 ticket で要追跡。

### 6. 新しく見つかったデグレ

- なし(回帰 0 件、305-QA 契約「無関係 player photo は単独確定記事に貼られない」維持確認)

### 7. 追加した回帰テスト

`tests/test_rss_fetcher_eyecatch_priority_and_dedupe.py`(11 test):

**HighConfidencePlayerPathTests(4 件)**
- `test_single_player_title_returns_player_media_id` — 戸郷 title → 66521 返却
- `test_no_player_in_title_returns_zero` — 「巨人 vs 広島 試合速報」→ 0、resolver 呼ばれない
- `test_player_without_photo_returns_zero` — 平山 title + cache miss → 0
- `test_kill_switch_disables_player_priority` — env ON → 0、resolver 呼ばれない

**RecentMediaDedupeTests(3 件)**
- `test_helper_returns_recent_ids_set` — `[66577, 66491, 65953, 0, 66577]` → set `{66577, 66491, 65953}`(0 除外、重複圧縮)
- `test_helper_returns_empty_on_failure` — RuntimeError → 空 set
- `test_helper_kill_switch_returns_empty` — env ON → 空 set、`list_recent_featured_media_ids` 呼ばれない

**UploadFeaturedMediaWithFallbackDedupeTests(4 件)**
- `test_dedupe_skips_recent_media_and_returns_next` — [a→66577(recent), b→66491] → 66491 採用
- `test_dedupe_returns_zero_when_all_candidates_recent` — 全 recent → 0、upload も呼ばれない
- `test_dedupe_empty_recent_set_is_no_op` — recent 空 → 通常動作
- `test_dedupe_default_arg_unchanged_when_omitted` — `recent_used` kwarg 省略 → 通常動作

### 8. 次回触ってはいけない範囲

- `_detect_person_for_eyecatch_priority` の indirection layer の本体(test patch 用、変更すると test が壊れる)
- `resolve_eyecatch_from_title` の API シグネチャ(本 ticket は kwarg 経由で呼ぶだけ)
- `_is_unsafe_eyecatch_media_id` の対象 id list(305-QA の安全契約)
- `WPClient.list_recent_featured_media_ids` の戻り値型(list[int]、空も OK)
- `EYECATCH_PLAYER_PRIORITY_DISABLED` / `EYECATCH_DEDUPE_RECENT_DISABLED` env 名 / 値解釈
- 305-QA の `diversified_pool` 殺し(復活させない)
- 東京ドーム fallback media_id 65953
- manual_intake.py / source_article_body_extractor.py
- LLM (Gemini) prompt 構造
- 公開済み記事の本文 / featured_media / title / status
- env / Secret / Scheduler / Cloud Run service 設定の他箇所(env 新規 2 つ default OFF 以外は触らない)
- frontend / CSS / theme / Plugin / AdSense
