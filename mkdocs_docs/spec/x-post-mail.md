# :material-twitter: X 投稿候補メール (x-post-mail)

!!! info "これは何のメール"

    「今日 X に投稿するならこの内容がおすすめです」 を user に提案するメール。
    公開通知ではなく、 ==user が手動で X 投稿するための材料== (タイトル / 本文 / 投稿ボタン) を 1 通にまとめて配信する。

## :material-clock-outline: 発火タイミング (JST)

スケジューラで時間ごとに起動する (`gcloud scheduler jobs list` 2026-05-27 実行結果)。

| スケジューラ | 発火タイミング |
| --- | --- |
| `x-post-mail-flush` | 6〜22 時の毎時 0 分 |
| `x-post-mail-flush-game-1` | 19,20 時の 15 / 30 / 45 分 |
| `x-post-mail-flush-game-2` | 21 時の 15 / 30 / 45 分 |

実行場所: Cloud Run job `x-post-mail-lane`。

候補が 0 件のときはメールを送らない (空メール抑止)。
最低候補数を下回るときは 24 時間 dedup を一時的に緩めて補充する fallback あり (`24h dedup left only ...` log)。

## :material-format-list-bulleted-type: 候補は 5 種類

`Candidate` dataclass (`src/x_post_mail_lane.py:859`) の `metric` フィールドで区別される。

=== ":material-chart-bar: 通常データ指標 (画像つき)"

    **metric**: AVG / OBP / SLG / OPS / ERA / WIN_PCT / K_per_9 / BB_per_9 / HR_per_9 / FIELDING_PCT / UZR_proxy / WAR / RISP

    DB のランキングから「巨人選手の数値が際立った瞬間」 を抽出。
    ==draft_text にランキング行を持つ== 唯一の種類 (`{rank}位 {name}（{team}）{value} 🟧巨人🟧` 形式)。 画像生成器が `_RANKING_ROW_PATTERN_V2` でこれを parse して PNG を作る。

=== ":material-newspaper-variant: GEMMA_BRANDING (画像あり、 2026-05-27 〜)"

    **metric**: `GEMMA_BRANDING` (`_GEMMA_BRANDING_METRIC` 定数、 `src/x_post_branding_gen.py:43`)

    報知 / サンスポ記事を Gemini で要約して「==ヨシラバー風コメント==」 X 投稿候補にしたもの。 voice prompt は ==`_SYSTEM_PROMPT_YOSHILOVER`== (`src/x_post_branding_gen.py:152`)。

    !!! info "438 で画像対応 (2026-05-27)"

        旧 GEMMA_BRANDING は text-only だったが、 ticket 438 で og:image fetch + X media attach に拡張。 詳細は本 section 末尾の 「438 画像添付」 を参照。

    生成 entry point は 2 つ:

    - **`build_gemma_branding_candidate`** (`src/x_post_branding_gen.py:1170`): Tavily REST 検索 → Gemini で生成。 player を caller が指定する。
    - **`build_x_post_from_article_info`** (`src/x_post_branding_gen.py:1473`): 報知 / サンスポ の article_info (queue 経由) を入力に、 Tavily を呼ばずに Gemini 生成。 player は title / summary から `_find_first_giants_player_in_text` で抽出。

    #### persona 自動選択 (`select_branding_persona`, `src/x_post_branding_gen.py:345`)

    | 条件 | persona | 性質 |
    | --- | --- | --- |
    | 試合日 + 18-21 時 JST | `kandume` (缶詰) | 試合中実況 voice、 当日 only |
    | 上記以外 (非試合日 / 時間外) | `fuuga` (フーガ) | 長文分析 voice、 直近 5 日 streak 拾える |

    !!! note "#95 統合"

        `_SYSTEM_PROMPT_KANDUME` / `_SYSTEM_PROMPT_FUUGA` は #95 で同一 prompt `_SYSTEM_PROMPT_YOSHILOVER` (180-280 字目安、 短文+改行、 3 軸圧縮) に統合済 (`src/x_post_branding_gen.py:256-262`)。 persona キーは履歴互換のため温存。

    #### 5 型分離 (`_POST_TYPES`, `src/x_post_branding_gen.py:365`)

    `flash` (速報) / `emotion` (感情) / `data` (データ) / `next` (展開予想) / `positive` (前向き締め) の 5 型から caller / 自動 select で選ぶ。

    #### 巨人 member gate (player + manager + coach、 2026-05-27)

    候補生成の入口で 「giants_roster.json の **active member**」 に該当しない人物を skip する。

    - 対象 role: `player` / `manager` / `coach` (active=True のみ、 ikusei / shihaikako は除外)
    - 実装: ==`_is_verified_full_giants_member_name`== (`src/x_post_mail_lane.py:390`) + `_load_giants_member_aliases` (`src/x_post_mail_lane.py:348`)
    - text 抽出: `_find_first_giants_player_in_text` (`src/x_post_branding_gen.py:1437`、 関数名は player のままだが内部で member aliases を使用)

    !!! info "2026-05-27 拡張"

        旧 gate は `_is_verified_full_giants_player_name` (role=player のみ) で、 阿部監督 / 橋上監督代行 / 川相コーチ 等のコメント記事を全件 skip していた。 user 明示「監督やコーチもいれていい、 巨人なら」 で member gate へ拡張。 NEWS_OPINION / COMMENT_DB は player gate 据え置き (DB 統計が選手のみのため)。

    #### postgame 救済 path (`is_postgame_team_wide`)

    `article_subtype` が `postgame` / `postgame_digest` / `team_roundup` の試合総括記事は、 個別 player gate を skip し player=「巨人」 でチーム視点として fuuga voice で生成する (`src/x_post_branding_gen.py:1519`)。

    #### よくある skip reason (log)

    | log line | 意味 |
    | --- | --- |
    | `article_info_branding_skip reason=no_giants_member_in_article` | title / summary に active member 該当が無い (gate 拡張前は `no_giants_player_in_article`) |
    | `gemma_branding_skip reason=not_verified_giants_member` | caller 指定 player が active member でない (gate 拡張前は `not_verified_giants_player`) |
    | `Gemma branding produced 0 candidates` | gate 通過 0 件 / Gemini error / validator drop |
    | `og_image_fetcher_skip reason=og_image_meta_missing` | source HTML に `<meta property="og:image">` が無い |
    | `pattern_b_skip reason=no_long_quote_found` | source HTML に 60-180 字「」 quote が無い (or speaker proximity 外) → Pattern A fallback |

    #### 438 画像添付 (2026-05-27)

    ticket 438 で GEMMA_BRANDING に **og:image 自動添付** + Pillow overlay (Pattern B) を追加。 既存の毎時 fire (x-post-mail-flush + game lane) 内に組込み、 **新規 Cloud Scheduler / Cloud Run job 一切作らない** lock 維持。

    ##### Pattern A (brand_opinion、 私の意見)

    - 反応元 article の og:image を ==そのまま attach== (Pillow overlay なし)
    - post_text: 既存 `_SYSTEM_PROMPT_YOSHILOVER` 生成 text (180-280 字)
    - 出典: image alt_text / post_text どちらにも入れない (user 仕様 2026-05-27、 `(出典 @handle)` 付与も停止 `src/x_post_branding_gen.py:1839-1846`)

    ##### Pattern B (brand_quote、 選手・コーチ literal 引用)

    Pattern A の上に Pillow で 「人物名 + 「long quote」」 を写真下半分に焼き込む。 成立条件不足時は Pattern A に fallback。

    | 項目 | 仕様 |
    | --- | --- |
    | 成立条件 | source HTML から 60-180 字「」 quote が抽出可 + speaker (focus_player) の roster alias が「 直前 40 文字以内に出現 (mis-attribution 防止) |
    | 60 字未満の quote | 不採用 (Pattern A fallback) |
    | 180 字超過 | 「。」 / 「、」 境界で truncate、 末尾「…」 禁止 (literal 引用 violation) |
    | ネスト『』 | 対象外、 外側「」 のみ |
    | post_text (B 時) | **人物名のみ** に切替 (image が long quote を持つため重複回避) |
    | 画像 overlay | white text + 黒 stroke、 枠 / band / brand mark / 引用元 一切なし (user 仕様) |

    ##### 主要 file (438)

    - `src/og_image_fetcher.py:64` `fetch_og_image()` — HTML から og:image / twitter:image 抽出 + 画像 bytes fetch (timeout 5s、 size 上限 5MB、 gzip auto-decompress)
    - `src/og_image_fetcher.py:55` `OgImageResult` — image_bytes / content_type / image_url / html_text (同一 fetch で本文も保持)
    - `src/long_quote_extractor.py:34` `extract_long_quote()` — HTML/plain → 「」 抽出 → speaker proximity check
    - `src/image_quote_overlay.py:37` `apply_quote_overlay()` — Pillow で 写真下半分に overlay (font は 437 の `_find_font`、 Noto Sans CJK JP)
    - `src/x_post_branding_gen.py:1437` `_try_fetch_og_image_for_candidate()` — twitter.com / x.com は login wall で silent skip
    - `src/x_post_branding_gen.py:1476` `_try_apply_pattern_b_quote_overlay()` — Pattern B 試行 + fallback
    - `src/x_post_branding_gen.py:1534` `_resolve_speaker_aliases()` — canonical name → roster の全 alias を逆引き (姓 / 姓名 / 役職付き)

    ##### log で pattern 判定

    `article_info_branding_candidate_built ... pattern=A` または `pattern=B`。 `og_image=yes` で画像 attach 成功。

    ##### commit chain (438)

    1. `b63888c` Phase 1 og:image fetch + attach
    2. `bdcba6a` gzip decompress bug fix (sanspo / hochi は gzip 配信)
    3. `6a59de6` Phase 2 Pattern B 引用 overlay
    4. `cae5066` speaker proximity check (mis-attribution 防止)
    5. `5a0729b` navigator.share / X intent で空 URL omit (iOS Safari 漏出 fix)
    6. `ea23382` post_text 末尾の `(出典 @handle)` 削除 (X 上で link 化問題)
    7. `bf56300` image alt_text の「引用元: 媒体名」 も削除 (user 仕様)

    ##### GCS lifecycle (share_x_cand prefix)

    438 で画像 PNG が累積するため、 2026-05-27 に bucket lifecycle 設定:

    ```json
    {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7, "matchesPrefix": ["share_x_cand/"]}}]}
    ```

    効果: `gs://baseballsite-yoshilover-insight/share_x_cand/` 配下のみ **作成 7 日経過で自動削除**。 他 prefix (archives / digest / fan_voice / daily_snapshot / insight.db) は影響なし。 soft_delete_policy 7 日と組合せで実質 14 日保持 (削除後 7 日復元可能)。 reflection は GCS の lifecycle scan (1 日 1 回) 経由で最大 24h ラグ。

    確認 cmd: `gsutil lifecycle get gs://baseballsite-yoshilover-insight`

=== ":material-comment-quote: NEWS_OPINION (画像なし)"

    **metric**: `NEWS_OPINION` (`_NEWS_OPINION_METRIC` 定数 = `"NEWS_OPINION"`、 `src/x_post_mail_lane.py:898`)

    RSS ニュース記事から「コメント案」 を抽出。

=== ":material-database-check: COMMENT_DB (画像なし)"

    **metric**: `COMMENT_DB` (`src/x_post_mail_lane.py:899`)

    NEWS_OPINION と DB の ==同一選手 + 同論点== を結合した複合候補。
    title フォーマット例: `DB照合済: フルネーム+論点一致｜コメント×DB｜{選手}｜{metric} {期間}`。

=== ":material-account-voice: FAN_VOICE (画像なし)"

    **metric**: `FAN_VOICE` (`src/x_post_mail_lane.py:900`)

    巨人ファン X 投稿を参考引用 (user メモ用、 literal コピー禁止)。
    title フォーマット例: `(参考) ファン投稿｜{handle or 匿名}｜{text preview 40字}`。

## :material-tag-text: メールヘッダーの label 切替

`_mail_header_label` (`src/x_post_mail_lane.py:3116`) が決定する。

判定: `_has_news_opinion_candidate` が 1 件でも True なら 「巨人Xポスト案」、 そうでなければ 「巨人データXポスト案」。

`_has_news_opinion_candidate` は ==news-derived 4 種== (NEWS_OPINION / COMMENT_DB / FAN_VOICE / GEMMA_BRANDING) のどれかが混入していれば True を返す (`src/x_post_mail_lane.py:3113`)。

!!! success "全候補が DB ランキング (画像つき) のみ"

    → ==「巨人データXポスト案」==

!!! note "ニュース派生が 1 件でも混ざる"

    → ==「巨人Xポスト案」==

「巨人データ」 = 「全部に画像あり」 という意味で使う仕様。

## :material-view-list: 候補 1 件あたりの表示

`_compose_html_body` (`src/x_post_mail_lane.py:3516`) が組み立てる。
候補ごとに以下の順で表示。

1. **候補タイトル** (`■ 候補 N: {title}`)
2. **画像** (`image_html_for_candidate`、 あれば inline 表示で cid embed)
3. **採用理由** (`selected_reason`)
4. **投稿テキスト** (`post_text` を pre 要素にコピペ用で出す)
5. **根拠データ** (折りたたみ details 要素、 draft_text が post_text と異なる時)
6. **投稿ボタン**:
    - **🐦 画像つきで X に投稿** (share-x-cand URL がある時、 黒地白文字)
    - **🐦 X で投稿** (share-x-cand URL が無い時、 黒地白文字)
7. **文字数表示** (`{N} / 280 字`、 280 超過なら警告色 `#b71c1c`)

## :material-image-multiple: 画像生成 (`_generate_candidate_image_png`)

`src/x_post_mail_lane.py:3375`。

1. `src/x_post_image_gen_v2.py` の `generate_png` を呼ぶ
2. candidate の `draft_text` から `_extract_ranking_rows_from_draft` でランキング行を parse
3. parse 行が 0 なら ==None を返して画像 skip==
4. `_select_template_and_data` で template を選択 (focus_player + 投手指標 → `pitcher_card`、 focus_player TOP1 → `player_spotlight`、 それ以外は round-robin で `ranking_table` / `chart_bars` / `data_sheet` / `monthly_summary` / `starting_lineup` / `12team_crown` / `12team_bar` / `scoreboard` / `standings` の 9 種類から index で選択)
5. PNG bytes 1080x1080 を生成

画像生成は Pillow + Noto Sans CJK JP Bold ベース (`x_post_image_gen_v2.py`)。 CJK tofu 事故対策として SVG ではなく TTF 直描画。

## :material-image-multiple: 画像つき X 投稿の仕組み (2 経路)

=== ":material-web: 経路 A: Web Share API (現状の mail ボタン)"

    フロー:

    1. mail のボタン押下
    2. fetcher の `/share-x-cand` ページが開く
    3. JS が GCS 上の PNG を fetch
    4. `navigator.share()` で X アプリに画像つき share

    必要 env: `ENABLE_SHARE_X_BUTTON` truthy + `INSIGHT_GCS_BUCKET` + `FETCHER_PUBLIC_BASE_URL`。

    !!! warning "端末次第"

        Web Share API が file 共有未対応の環境では text-only にフォールバックする。

    !!! info "URL 漏出 fix (2026-05-27, commit `5a0729b`)"

        iOS Safari は `navigator.share({files, text, url: ""})` で `url` key が存在する時、 空文字でも現在 page URL (share-x-cand の URL) を fallback で含めて共有する挙動。 X compose に fetcher 自身の https URL が貼り付く事故になっていた。

        修正: ==`url` key を 非空時のみ ペイロードに含める== (`src/share_x_handler.py` 内 `_build_share_cand_page_html` の JS block)。 X intent URL fallback (`_build_share_cand_x_intent_url`) も同様に空 URL を omit。

=== ":material-server: 経路 B: server-side X API (CLI 有り、 mail 未配線)"

    `src/tools/post_x_with_image.py` ツール経由で:

    1. 画像を `generate_png` で生成
    2. tweepy v1.1 の `media_upload` (`src/x_post_image_attach_x.py:attach_x_post_image`)
    3. tweepy v2 の `create_tweet(text=, media_ids=[...])` で投稿

    必要 env: X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET。

    端末に依存せず ==確実に画像つき投稿== になる (X API Free tier でも `media_upload` は使用可)。

    !!! note "現状"

        CLI のみ。 mail ボタンには未配線。

## :material-content-duplicate: 候補の重複抑止

- **per_mail_player_dedup**: 同じ選手 1 名につき同じメール内で ==1 候補まで== (`_DEFAULT_PLAYER_MAX_PER_MAIL=1`、 `src/x_post_mail_lane.py:897`)
- 過去 24 時間以内に同 signature を送っていれば skip
- 24h dedup で候補が空に近いときは relaxation して最低数を確保 (`dedup_fallback_player_skip_kept` log)

## :material-cog: 主な環境変数 (x-post-mail-lane ジョブ)

??? abstract "クリックで展開"

    出典: `gcloud run jobs describe x-post-mail-lane` 2026-05-27 実行結果。

    | env | 実値 | 用途 |
    | --- | --- | --- |
    | `INSIGHT_GCS_BUCKET` | `baseballsite-yoshilover-insight` | 候補 PNG の置き場 |
    | `FETCHER_PUBLIC_BASE_URL` | yoshilover-fetcher の URL | share-x-cand button の URL ベース |
    | `ENABLE_SHARE_X_BUTTON` | 1 | 候補 PNG を GCS upload + 画像つきボタン |
    | `X_POST_MAIL_FAN_VOICE_ENABLED` | 0 | 1 で FAN_VOICE 候補を append (19-23 時のみ) |

## :material-video: 動画候補 (x_buzz_post / 451) と鮮度ルール

2026-06-01 実装 (ticket 451 §9)。 巨人系 X account を自前 RSSHub (X→RSS、 X API 不使用) で
read-only 巡回し、 **動画つき投稿**を「引用RT / X公式『動画をポスト』」候補としてメールに出す。

### 動画 source (8 account)

`src/video_radar.py:_BUZZ_HANDLES`。 全ハンドル実 feed 検証済 (実在 / 鮮度 / 動画サムネ):

| handle | 主体 | 備考 |
| --- | --- | --- |
| `TokyoGiants` | 読売ジャイアンツ公式 | =「ジャイアンツ公式」(同一) |
| `hochi_giants` | スポーツ報知 巨人取材班 | |
| `Sanspo_Giants` | サンスポ 巨人 | 動画多 |
| `tospo_giants` | 東スポ 巨人担当 | |
| `SponichiGiants` | スポニチ 巨人担当 | |
| `koba_nikkan` | 小早川宗一郎 (日刊) | 練習動画 |
| `ntv_baseball` | DRAMATIC BASEBALL 2026 (日テレ巨人中継) | 動画最多 |
| `DAZNJPNBaseball` | DAZN ベースボール | |

旧 `yomiuri_giants` は RSSHub で死にデータ (1月の「@趣味」RT) を返す死にハンドルのため除外。

### 動画判定 (require_video)

`gather_buzz_posts(require_video=True)` 既定。 RSS description の動画サムネ/動画要素マーカー
(`amplify_video_thumb` / `ext_tw_video_thumb` / `tweet_video_thumb` / `<video` / `video/mp4`) を含む投稿のみ採用。
動画なし投稿では X 公式「動画をポスト」長押しが無意味なため。

### メール UI (動画候補)

- 「🐦 引用RTで X に投稿」ボタン (quote intent) + 「▶ 元の動画ポストを開く」リンク (`quote_url` 直リンク)。
- 緑の手順ボックス: ① 元ポストを開く ② 動画を長押し →「動画をポスト」③ コメントを貼って投稿。
  (X 公式「動画をポスト」= リポスト+引用のいいとこ取り、 元投稿に自動帰属、 転載でない)。

### 鮮度ルール (フェーズ別、 全ポスト統一)

`src/x_post_mail_lane.py:phase_freshness_max_age_hours(now)` (判定は `x_impression_timing_label`)。
「古いデータを出さない」「試合中は即、 試合前はその日」(user 2026-06-01) を全ポストに統一適用:

| フェーズ | 時刻 (JST) | max_age |
| --- | --- | --- |
| 試合中 (in_game_strong) | 19:00-21:45 | 30分 (直近のライブのみ、 15分発火に合わせ) |
| 試合後 (postgame_peak) | 21:45-23:30 | 6h |
| 試合前 / スタメン | 16:00-19:00 | 12h |
| 朝 / 昼 / 午後 / 通常 | その他 | 24h |

適用経路:

- 動画 (x_buzz): pubDate ベース gate。
- news_opinion RSS fallback: `run_x_post_mail._entry_published_dt` で公開日抽出 + gate。 **日付不明は strict skip**。
- tag_scrape: `max_age_days` 既定 1。
- fan_voice: `lookback_hours` フェーズ別。
- **対象外** (元々当日もの): gemma branding (当日 DB + Tavily 同日) / データ系候補 (当日 stats、 insight.db stale gate 済)。

## :material-folder-file: 関連 file

- メイン (候補組み立て + メール組み立て): `src/x_post_mail_lane.py`
- 動画候補 (RSSHub buzz + 動画判定 + 鮮度): `src/video_radar.py`
- 画像生成: `src/x_post_image_gen_v2.py` (Pillow + Noto Sans CJK)
- 画像→X 投稿アップロード: `src/x_post_image_attach_x.py`
- CLI 直接投稿ツール: `src/tools/post_x_with_image.py`
- ランキング → X-post format: `src/format_as_x_post.py`
- branding 候補生成: `src/x_post_branding_gen.py`
- fan_voice 候補: `src/tools/run_x_post_mail.py:_build_fan_voice_candidates`
