# 2026-05-13 — eyecatch hashtag entity / mid-game pregame escape / entity-0 skip / dedupe OFF

> 本 file は 2026-05-13 evening session の作業記録。`yoshilover-fetcher` Cloud Run
> service への 3 件 fix landing + dedupe env apply + 1 件 deploy 事故検知 + rollback
> を 1 file に圧縮。明日朝の作業者がそのまま拾えるよう、commit / revision / digest /
> 残課題を明示。

## context

- user 起点 query「先ほどのアイキャッチで①そーすがでなかった ②坂本勇人の記事だが写真が出なくて
  ③ジャイアンツになったのは？」(post 66866)
- 進行中に「試合中の話題は外してるの？昨日まで取れてた」「報知でとんでくるの？」
  「Xはアイキャッチになるが、サイトはアイキャッチならない」 「のもとけモデルの title
  変じゃない？せめて選手名がないと」 と複数の品質事象が連鎖発見された
- protocol 強化:「AI は『記憶から再構成』『silent skip』『自己評価 OK』が最大の事故源」
  を 4 回 user reminder、これを契機に各 step で実 grep / 実 log / 実 digest verify を
  徹底

## 1. 検出した事象 / 真因 (実 data で確定)

### 1-A. post 66866 アイキャッチが Giants logo team_fallback

- 元 tweet (`sanspo_giants` X 2054452354175606825) には `#坂本勇人` が hashtag 形式
- WP 取込 body は `坂本勇人` 文字列 **0 件** (9160 char 全走査)
- Cloud Logging trace で `title_template_selected` の `original_title` 時点で
  `早出の時間帯から…体を動かしていた 選手` (entity 既消失)
- 真因 = `src/rss_fetcher.py:3015` `_clean_social_entry_text`
  - `clean = _re.sub(r'#[\w一-龯ぁ-ゔァ-ヴー々〆〤]+', '', clean)` で entity-bearing
    hashtag を空文字置換
  - `nomotoke_rss_router.sanitize_short_news_title` 側は `#word → word` plain 化を
    実装済だが、この path より前で entity が落ちる
- 副真因 = `GIANTS_PLAYER_ALLOWLIST` (34 名、投手中心) に **坂本勇人未登録**
  - hashtag を plain 化しても `detect_person` が None 返す → team_fallback 着地
  - 岡本和真 / 丸佳浩 / 戸郷翔征 / 菅野智之等 主力野手も同様未登録、roster 整備案件

### 1-B. 試合中話題 (則本昂大「N回まで無失点でスタート」) が pregame_started_skip

- post 66866 (sanspo) / post 66866 type 報知記事 (`hochi.news/articles/.../OHT1T51328.html`) が
  18:30 / 18:45 firing で `pregame_started_skip` 発動
- subtype 分類器 `_detect_article_subtype` の階段:
  1. `_has_explicit_confirmed_result` → postgame
  2. `_has_live_update_fragment` → live_update
  3. `SCORE_TOKEN_RE` → postgame
  4. `_has_lineup_core` → lineup
  5. `has_game` → **pregame (default)**
- 真因 = `LIVE_UPDATE_INNING_RE` の suffix が `(?:表|裏|終了|途中|で)` で **「まで」未対応**
  - 「２回まで無失点でスタート」が live_update fall-through、pregame 誤判定
  - game_state が試合中 → safety skip
- 注: 仮に subtype を live_update に直しても `ENABLE_LIVE_UPDATE_ARTICLES=0` で別 skip
  に流れる。最 narrow fix は `_should_skip_started_pregame_entry` の escape に
  mid-game marker を追加

### 1-C. hochi.news 直 source post の featured_media が Giants logo

- post 66969 (則本「２回まで」記事) の Cloud Logging trace 時系列:
  1. 10:15:38 `[WP] 画像アップロード開始 OHT1I51503-L.jpg`
  2. 10:15:39.055 `[WP] 画像アップロード media_id=66964`
  3. 10:15:39 post 66965 (X tweet 経由) publish、featured_media=66964 ✓
  4. 10:15:52 `featured_media_recent_dedupe` x 3、候補=同 image url、recent_used に
     既存 (66964 が含まれている) → 全 skip
  5. 10:15:53 post 66969 publish、featured_media=66813 (Giants logo)
- 真因 = `_upload_featured_media_with_fallback:14191-14208` の narrow-dedupe (2026-05-12
  導入、`EYECATCH-DUPLICATE-IMAGE-2026-05-08` ticket 系)
  - 同 firing 内で 1 度使った媒体は次以降 skip → team_fallback 流入
  - 順序依存: X 経由が先に処理 → 後の hochi.news 直は dedupe で落ちる
- user 指定 priority **1.source → 2.選手 → 3.巨人** と矛盾していた
- env kill switch (`EYECATCH_DEDUPE_RECENT_DISABLED=1`) は既存実装、apply で即無効化

### 1-D. promotional / umpire-only 投稿が記事化 (post 66951 / 66941)

- post 66951 「RT 【公式】ジャイアンツタウンスタジアム: ／ 締め切り間近！販売は5/1…」
  - source = `@TokyoGiants` 公式 X、subtype=farm として通過
- post 66941 「福井 セーレン・ドリームスタジアム 本日の審判団 球審 嶋田 一塁 土山 二…」
  - 試合運営情報、Giants 選手 0 名
- 真因 = title に Giants 選手/監督/コーチ entity 0 件でも `is_giants_related` を通過
  (source 文字列に「巨人/ジャイアンツ」brand keyword 含む)
- `feedback_title_quality_extended_requirements.md` の「対象者名必須」要件は既に
  認識されていたが、現実装の skip 条件には届いていなかった

## 2. 修正 (3 commits on `hotfix-eyecatch-hashtag` branch、prod 反映済)

| commit | label | 内容 | files |
|---|---|---|---|
| `bb205c9` | `[QA-eyecatch]` | `_clean_social_entry_text` で entity-bearing hashtag を plain text 化、汎用 hashtag (`巨人`/`ジャイアンツ`/`giants`/`サンスポ`/`報知`/`スポニチ`/`スポーツ報知`/`日刊スポーツ`/`熱闘撮って出し`) は stop list 削除維持 | `src/rss_fetcher.py` + `tests/test_yahoo_realtime.py` |
| `7f70343` | `[QA-pregame]` | `_should_skip_started_pregame_entry` の escape に mid-game marker (`回まで`/`回途中`/`回を投げ`/`回終了`/`回終わ`) 追加 | `src/rss_fetcher.py` + `tests/test_cost_modes.py` |
| `4220030` | `[QA-entity-gate]` | `_should_skip_no_entity_non_game` 新規追加: `detect_person` None かつ promotional marker (`販売`/`発売`/`予約`/`抽選`/`グッズ`/`ストア`/`セール`/`割引`/`プレゼント`/`受注`/`限定発売`/`締め切り`/`締切`/`チケット`/`ファンクラブ`/`申し込み`) または umpire marker (`球審`/`塁審`/`線審`/`審判団`/`審判員`/`本日の審判`) で skip。skip reason は `promotional_no_entity` / `umpire_info_no_entity` | `src/rss_fetcher.py` + `tests/test_cost_modes.py` |

ベースは prod `8f827c4` (eyecatch reorder fix)。3 fix の合計差分は `+184 / -1` 行。
原 branch `draft-body-editor-reject-streak-no-fail` (master から 131 commits 先行) は
触らず、専用 `hotfix-eyecatch-hashtag` branch で narrow deploy。

同 branch には user 自身が並走で commit した 2 件も含む (3 件一括 deploy に user GO):
- `7a2dec4` [source-excerpt] readability (heading / blockquote / 軽改行)
- `281cd88` [publish-notice] mail HTML 版 + ボタン

## 3. env 変更

| env | 旧 | 新 | 意図 |
|---|---|---|---|
| `EYECATCH_DEDUPE_RECENT_DISABLED` | unset | `1` | source 画像優先回復 |
| `EYECATCH_PLAYER_PRIORITY_DISABLED` | `1` | `1` (維持) | player priority が source を上書きするのを抑制、user 指定 chain (1.source→2.選手→3.巨人) と整合 |

その他 env (`ENABLE_LIVE_UPDATE_ARTICLES=0` / `RUN_DRAFT_ONLY=0` / `AUTO_TWEET_ENABLED=0`
等) は不変。

## 4. deploy 履歴 (digest verify 付き)

| revision | image tag | image digest | 状態 | 補足 |
|---|---|---|---|---|
| 00445-tug | `:eyecatch-reorder-8f827c4` | (前 prod) | rollback 用に traffic 0% で残存 | `eyecatchreorder` tag |
| 00353-6s9 | `:bb205c9` | be528a9d… | 経由 (hashtag fix) | |
| 00354-vzv | `:7f70343` | 95ce88cf… | 経由 (+ pregame fix) | |
| **(事故)** 00453-pet | `:7a2dec4` | 48c1a303… | rollback 済 | `gcloud run services update --update-env-vars` 単独実行で image が別 commit (`7a2dec4` source-excerpt) にすり替わった。protocol verify (image digest 比較) で発覚 |
| 00358-76f | `:7f70343` | 95ce88cf… | 経由 (env 正規 apply) | `gcloud run deploy --image :tag --update-env-vars=…` で復旧 |
| **00359-57d** | `:4220030` | **38f20dfe…** | **現 serving 100%** | 3 fix + 同梱 2 commit |

### 4-A. deploy 事故 retrospective

事故: `gcloud run services update --update-env-vars=EYECATCH_DEDUPE_RECENT_DISABLED=1`
を image 指定なしで実行 → Cloud Run が service spec template を見て自動で image を
解決、結果として **template が指していた別 commit** (`7a2dec4` の digest `48c1a303`) で
new revision を作成。

検知: revision deploy 完了直後に `gcloud run revisions describe <new> --format
"value(spec.containers[0].image)"` で digest を read、前 revision digest と比較、
mismatch 発覚 → 即 rollback (`update-traffic --to-revisions 00354-vzv=100`)。

学び: env 単独 update は使わない。env を変える時は必ず
`gcloud run deploy --image <explicit tag> --update-env-vars=…` で打つ。
image を明示しない update は image 別解決 risk あり。

## 5. verify 結果 (実 log)

### 5-A. `bb205c9` (hashtag entity 保持)

- 19:00 JST 発火直後の sanspo 系 tweet で `original_title` に entity 残存を確認
- 既存 5/7 dry-run log 比較で挙動同等

### 5-B. `7f70343` (mid-game pregame escape)

- 19:00 firing (deploy 前 revision): `pregame_started_skip` 件数 4 件、則本記事含む
- 19:15 firing (deploy 後 revision): `pregame_started_skip` 件数 2 件、**則本記事は外れた**
- post 66969 (則本「２回まで」hochi 記事) **publish 成功**、関連 4 件も追加 publish
  (66965 / 66967 / 66960 / 66953)

### 5-C. `EYECATCH_DEDUPE_RECENT_DISABLED=1` (dedupe OFF)

- env apply 後の firing で `featured_media_recent_dedupe` イベント **0 件**
- source 画像着地 path 復活 (実 verify は次 firing で hochi.news 直 source の
  featured_media が 66813 でないことを log で確認予定 — 別 wakeup で取る)

### 5-D. `4220030` (entity-0 skip) — 進行中

- 20:00 JST firing で publish 2 件着地 (66972 / 66974)
- `no_entity_non_game_skip` event は当該 firing の取込 entry に該当 type が無く 0 件
- 次 firing 以降 (20:15 / 20:30) で `promotional_no_entity` / `umpire_info_no_entity`
  の sample title 出現を継続観察

## 6. 残課題 / 未着手

| 項目 | 状態 | 優先 | 補足 |
|---|---|---|---|
| `GIANTS_PLAYER_ALLOWLIST` 拡充 | open | 高 | 坂本勇人 / 岡本和真 / 丸佳浩 / 戸郷翔征 / 菅野智之等主力野手未登録。roster 正本 source を user に確認後、別 commit。Claude が記憶で書くと事故源 |
| post 66866 個別救済 | open | 中 | publish 済の featured_media を 66813 → 実画像に差替、§11「公開記事の書き換え」 = user 判断 |
| post 66951 / 66941 既存記事の処理 | open | 低 | 既に publish 済、user 判断 (削除 or 放置) |
| X 動画 tweet thumbnail 不取得 | known | 低 | X 仕様、source 制約 (修正困難) |
| `4220030` 自然発火 verify 継続 | scheduled wakeup | 中 | 20:00 firing では該当 entry 0 件、20:15 以降で sample title 出現確認 |

## 7. protocol 学び

- `gcloud run services update --update-env-vars` 単独実行で image 別解決 risk
  → 必ず `gcloud run deploy --image :tag --update-env-vars=…` で打つ
- env apply / deploy 後は **必ず revision の image digest を tag の resolved digest と
  比較**、silent OK と判断しない
- protocol verify (実 grep / 実 log / 実 digest) で事故 1 件未然に detect、rollback
  まで 5 分以内
- doc-only / 大きい仮説からの再構成を避け、phase 1 grep を最初に固定するワークが
  scope expansion を抑える

## 8. 関連 file / 参照

- 修正対象 src:
  - `src/rss_fetcher.py:3012-3038` (`_clean_social_entry_text` + stop tokens + callback)
  - `src/rss_fetcher.py:4155-4197` (`_NON_PLAYER_*_MARKERS` + `_should_skip_no_entity_non_game` + `_PREGAME_STARTED_SKIP_MID_GAME_MARKERS`)
  - `src/rss_fetcher.py:22894-22918` (main loop 内 entity-skip 挿入点)
  - `src/rss_fetcher.py:14159-14260` (`_upload_featured_media_with_fallback` 内 narrow-dedupe)
- 修正対象 test:
  - `tests/test_yahoo_realtime.py` `SocialNewsNormalizationTests` (+ 2)
  - `tests/test_cost_modes.py` (+ 5: pregame escape 2 + entity-skip 4 のうち 1 件は新 class なし inline)
- 関連 doc:
  - `docs/work_logs/2026-05-12_eyecatch-player-priority-and-dedupe.md` (B+C 設計、今回 C を env OFF)
  - `feedback_title_quality_extended_requirements.md` (対象者名必須要件)

---

## 9. 追加 deploy (late session 22:00-23:00 JST 分)

session 後半に 5 件追加 commit + deploy。session log 初稿時点では未完。

### 9-A. allowlist roster 動的拡充 (`9afbe89`)

事象: post 66866 (坂本勇人) で `detect_person("坂本勇人") = None` を実走確認。
allowlist 静的 34 名に主力野手 (坂本/丸/戸郷/吉川/浅野/中山/門脇/内海/則本/
赤星 等) 未登録。

修正:
- `_GIANTS_PLAYER_ALLOWLIST_STATIC` (34 名、curated baseline) を残し、
  `_load_giants_roster_active_names()` で `config/giants_roster.json` の
  active=True player/coach/manager の canonical name を動的読込
- roster.json 不揃い (空白/`*` prefix) を loader で正規化
- union: 34 → 95 names (active 91 + 静的差分 4)

deploy: revision **00360-zlc**、image digest `c5e2c367…`

### 9-B. coach 11 名 roster 追加 (`7a42f62`)

Wikipedia 2026 シーズン Giants コーチ陣 28 名のうち、roster.json 既登録 8 名
(阿部慎之助/橋上/川相/村田/杉内/内海/亀井/石井) を除いた 1軍+2軍 新規 11 名
を追加:
- 1軍: ゼラス・ウィーラー / 李承燁 / 吉川大幾 / 實松一成
- 2軍: 金城龍彦 / 脇谷亮太 / 田口昌徳 / 大田泰示 / 鈴木尚広 / 山口鉄也 / 大竹寛
- 3軍 + 巡回 (会田/橋本/若林/市川/立岡/野上/西村/矢野/久保) は user scope
  外で追加せず

deploy: revision **00361-w8t**、image digest `b18bcf90…`

### 9-C. 試合中 postgame skip 恒久対策 (`ba41c51`)

事象: post 66993「巨人広島戦 則本昂大、試合での見せ場」 21:00 JST publish。
game state は 8 回 1-1 同点 (進行中) なのに、Gemini fallback template が
「巨人、競り勝って白星」narrative を生成。事実誤認 article。CLAUDE.md §18
「事実誤認は致命的 NG」該当。

修正:
- `_should_skip_started_pregame_entry` の対称関数 `_should_skip_unfinished_postgame_entry`
  を追加
- category=試合速報 + subtype=postgame + game_status.ended=False (game_status
  空も safety で skip) → `postgame_unfinished_skip`
- main loop の pregame_started_skip 直後に挿入
- LLM 経路には触らず、上流 (entry filter) で止める

deploy: revision **00362-qvn**、image digest `db31781b…`

### 9-D. title quality 3 件 narrow fix (`4a0dddc`)

事象: 直近 20 件 publish title audit で 4 件 weird:
- post 66931「探せ」(1 単語、source 元 RT 巨人軍 グッズの suffix 残骸)
- post 66939「平山功太「平山功太選手は...」」(entity 重複、報知 X tweet 自体
  format)
- post 66960「内海コーチ「状態非常に良い」」(主語抜き quote-only)
- post 66937「泉口友汰「3番・遊撃」」(lineup format、user 判断で OK 扱い)

修正:
- `_should_skip_too_short_title` (< 8 文字 skip → `title_too_short`)
- `_should_skip_quote_only_no_subject_title` (役職名「引用」だけ skip →
  `quote_only_no_subject`)
- `_dedupe_entity_in_title` (同 player name 2 回 → 1 回字句整形 →
  `title_entity_duplicate_deduped` event log)
- 4 件とも LLM ハルシネーションでなく source format / sanitize 過剰削除 /
  passthrough policy 由来 (実 log で確定済、`x_post_ai_failed` で Gemini は
  daily_limit、fallback template 経由)

deploy: revision **00363-jz2**、image digest `ef23cb9f…`

### 9-E. ヨシラバー voice prefix (`24694c7` + `2abe53b` narrative fix)

user 体感: yoshilover.com/66990 を webfetch、5 つの問題発見:
- 本文が極度に短い (「則本昂大投手（35）が...降板した。」のみ)
- 関連記事セクション過剰
- シェアボタン重複
- 「続きを読む」誘導 強調
- 広告・コメント欄配置不明確

user 指示「のもとけ風 title でいい」「大手新聞のあいだのサイトになっていて、
ヨシラバーらしさがない」「表あり、スクレイピング、文章も全部やる」を踏まえ、
postgame body の冒頭に **構造化 prefix** を prepend する narrow MVP。

prefix 構成 (3 section):
- **📊 試合まとめ (table)**: スコア / 投球回 / 球数 / 失点 / 被安打 / 奪三振
  を title/summary 内 regex 抽出して並べる
- **🔑 見どころ (箇条書き)**: summary 文を `key_play_markers` (本塁打/ソロ/
  打点/盗塁/好投/完投/勝利投手/サヨナラ/逆転/同点/決勝/先制) で filter、
  8-80 chars に絞り最大 3 件
- **📝 ヨシラバー的に (短い narrative)**: detect_person で主役 player 抽出、
  result keyword (勝利/敗戦/同点/中止) と組み合わせて deterministic template
  (LLM 不要、hallucination 0)

narrative 主役検出 bug (`24694c7` 初版):
- post 66990 preview で「翁田大勢 の好投が光った試合」と誤判定
- 真因: detect_person の alias_map ("大勢"→"翁田大勢") が title 検出前に
  summary 内 "大勢" に hit、主役逆転
- 修正 `2abe53b`: title から先に detect_person、見つからなければ text に
  fallback → 「則本昂大 の好投が光った試合」と正しい narrative

deploy:
- 24694c7 → revision **00364-bp5**、digest `91a448a4…`
- 2abe53b → revision **00365-whr**、digest `86152f4a…`

### 9-F. stale content 「昨日の記事」恒久対策 (`68f8d2d`)

事象: 22:01 JST publish で 67027「巨人・吉川が岐阜凱旋」+ 67024「巨人・佐々木
自身初サヨナラ弾」が出る。共に source URL 日付 = 5/13 (今日) だが content は
5/12 二軍試合 / 5/12 サヨナラ event の retrospective。大手新聞「翌朝に前夜
試合 report 出す」 format。

stale_source_guard は publish 時刻 base のため検出不能。content vs 今日の
試合状況 cross-check が必要。

修正 (2 段 narrow):
1. `_should_skip_prior_event_postgame` (keyword):
   - 「凱旋/昨夜/昨日/前日/前夜/先日/翌朝」が title/summary に出れば skip
   - 67027 type を catch
2. `_should_skip_mismatched_today_game` (yahoo cross-check):
   - 試合 ended=True + title に試合結果 marker (サヨナラ/完封勝/連勝/連敗
     等) + yahoo state にその marker 無し → `result_marker_mismatch`
   - 今日の opponent と異なる他球団 (阪神/中日/広島/DeNA/etc 11 球団) が
     title に出る → `opponent_mismatch`
   - yahoo state 空 or 試合中 → 既存挙動 (allow) 維持
   - 67024 type (サヨナラ弾 mismatch) を catch
- main loop の yahoo-aware filter (postgame_unfinished の直後) に挿入

deploy: revision **00366-dsz**、image digest `a91185c4…` (今夜 11 件目)

## 10. 最終 deploy chain サマリー (今夜 11 件)

| # | commit | revision | digest 先頭 | 内容 |
|---|---|---|---|---|
| 1 | bb205c9 | 00353-6s9 | be528a9d | hashtag entity 保持 (#坂本勇人 → 坂本勇人) |
| 2 | 7f70343 | 00354-vzv | 95ce88cf | mid-game pregame escape (回まで / 回途中 / 回終了) |
|   | (env)   | 00358-76f | 95ce88cf | EYECATCH_DEDUPE_RECENT_DISABLED=1 apply (image 維持) |
| 3 | 4220030 | 00359-57d | 38f20dfe | entity-0 + 販売 / 審判 keyword skip |
| 4 | 9afbe89 | 00360-zlc | c5e2c367 | GIANTS_PLAYER_ALLOWLIST roster.json 動的拡充 (34→95+) |
| 5 | 7a42f62 | 00361-w8t | b18bcf90 | coach 11 名追加 (Wikipedia 2026 1軍+2軍) |
| 6 | ba41c51 | 00362-qvn | db31781b | 試合中 postgame skip (「白星」hallucination 防止) |
| 7 | 4a0dddc | 00363-jz2 | ef23cb9f | title quality 3 件 (短すぎ/quote-only/重複 dedup) |
| 8 | 24694c7 | 00364-bp5 | 91a448a4 | ヨシラバー voice prefix (📊 / 🔑 / 📝) |
| 9 | 2abe53b | 00365-whr | 86152f4a | narrative 主役検出 bug 修正 (title 優先) |
| 10| 68f8d2d | 00366-dsz | a91185c4 | stale content 2 段 (prior_event keyword + yahoo cross-check) |

env (yoshilover-fetcher): `EYECATCH_DEDUPE_RECENT_DISABLED=1` apply 済。他不変。

## 11. 残課題 (今夜 deploy しない、明朝以降)

| 項目 | 種別 | 状況 |
|---|---|---|
| 過去 publish 済 weird/stale article cleanup | data | §11 user 判断、WP REST PUT で featured_media / status 書き換え |
| post 66866 個別救済 (アイキャッチ差替) | data | 同上 |
| ENABLE_* feature flag 50+ audit | observability | 別 session で個別 audit、no-op flag の処分判断 |
| WP_APP_PASSWORD rotation | security | **本日 chat に value 出てしまった** incident、user manual で rotation 推奨 |
| coach photo upload (Wikipedia commons) | data | password incident 経由で hold、license 確認 path 別 session |
| roster.json data 整理 (`*則本 昂大` + `則本 昂大` broken format dedup) | data | 動的 loader は正規化で吸収済、整理は別 commit 候補 |
| 本文短さの本格 redesign | feature | postgame 以外 (lineup/manager/farm/social) 用 prefix、Gemini 経路 OFF or 厳格 grounding 化、別 session |

## 12. protocol 学び (late session 追加分)

- env update `--update-env-vars` 単独実行は image 別解決の罠あり (検知済、
  即 rollback + redo)、必ず `--image :tag` 明示
- preview / 実 log で挙動確認するまで「直った」と書かない (narrative bug
  `24694c7` 初版を preview で検出 → 2abe53b で修正)
- user 「Gemini 使ってる？」「Gemini は意味がない」 への対応: 実 log で
  Gemini は daily_limit で呼ばれていない事実を提示、weird title は全部
  source / sanitize / passthrough 由来と確定 (記憶で説明せず実 data)
- 並走 commit (user manual commit が私の push 間に混入) 検知時、必ず内容
  を grep して user に明示 → silent に build/deploy しない
