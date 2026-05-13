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
