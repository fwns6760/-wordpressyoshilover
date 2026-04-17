# Operation Logs

Cloud Run 運用で見るログの一覧です。目的は「異常の早期発見」と「下書き品質の変化を定量で追うこと」です。

## 追加した最小ログ

今回の整備で追加した run 単位のサマリは 2 本です。

| event | 目的 | 実装 |
|---|---|---|
| `rss_fetcher_run_summary` | 1回の実行で何件拾って何件作ったかを定量で見る | `src/rss_fetcher.py:6043` |
| `rss_fetcher_flow_summary` | skip理由、カテゴリ分布、公開/投稿スキップ理由をまとめて見る | `src/rss_fetcher.py:6064` |

これ以外の既存ログのフォーマットは変更していません。

## 構造化ログ一覧

| event | 発火条件 | 主な出力フィールド | 実装 | 観察目的 | 異常の目安 |
|---|---|---|---|---|---|
| `image_candidate_excluded` | 画像候補URLが除外条件に一致、または MIME が SVG | `reason`, `excluded_url`, `source_url` | `src/rss_fetcher.py:2942`, `src/wp_client.py:77` | アイキャッチ候補の不良入力を観察 | 同一ホストで連発、または `reason` が `emoji_svg_url` 以外に広がる |
| `title_collision_detected` | rewrite後 `title_norm` が履歴上の既存 `title_norm` と衝突 | `source_url`, `rewritten_title`, `title_norm`, `existing_post_url`, `existing_title` | `src/rss_fetcher.py:4754` | title rewrite の収束・衝突監視 | 同一 `rewritten_title` が短時間に複数回出る |
| `title_template_selected` | 下書きタイトル生成時にテンプレが確定 | `source_url`, `category`, `article_subtype`, `template`, `original_title`, `rewritten_title` | `src/rss_fetcher.py:5539` | どのテンプレが多用されているか把握 | 1つの `template` に偏る、または単一テンプレで衝突が増える |
| `sns_weak_rescued` | `SNS弱い` 判定を救済語で通した | `rescue_reason`, `source_url`, `title`, `matched_word`, `category`, `article_subtype` | `src/rss_fetcher.py:5280` | 公示系や 2軍系の取りこぼし救済を監視 | 救済件数が急増、または想定外カテゴリで多発 |
| `article_ai_route_override` | 通常の AI 経路から recovery/notice/farm のためルートを上書き | `original_category`, `effective_category`, `article_subtype`, `effective_ai_mode`, `title` | `src/rss_fetcher.py:3863` | safe fallback 対策がどこで効いているか確認 | `effective_category` が偏る、または特定 subtype に集中 |
| `manager_body_template_applied` | 首脳陣記事で専用本文テンプレを適用した post 作成後 | `post_id`, `title`, `quote_count`, `section_count`, `template_version` | `src/rss_fetcher.py:5758` | 首脳陣カテゴリの専用本文型が実際に載ったか確認 | `section_count < 4`、`quote_count=0` ばかり続く |
| `game_body_template_applied` | 試合前後記事で subtype 専用本文テンプレを適用した post 作成後 | `post_id`, `title`, `subtype`, `section_count`, `numeric_count`, `name_count`, `template_version` | `src/rss_fetcher.py:5798` | lineup / postgame / pregame の専用本文型が実際に載ったか確認 | `section_count` が期待値未満、`numeric_count=0` や `name_count=0` が続く |
| `farm_body_template_applied` | 2軍育成記事で subtype 専用本文テンプレを適用した post 作成後 | `post_id`, `title`, `subtype`, `section_count`, `numeric_count`, `is_drafted_player`, `template_version` | `src/rss_fetcher.py:7111` | farm / farm_lineup の専用本文型が実際に載ったか確認 | `section_count` が期待値未満、`numeric_count=0` が続く、`is_drafted_player=true` の記事で固有名詞が薄い |
| `notice_body_template_applied` | 公示・登録系記事で専用本文テンプレを適用した post 作成後 | `post_id`, `title`, `notice_type`, `section_count`, `has_player_name`, `has_numeric_record`, `template_version` | `src/rss_fetcher.py:6683` | 登録/抹消/合流/戦力外の本文型が実際に載ったか確認 | `has_player_name=false` や `has_numeric_record=false` が連続、`section_count < 4` |
| `recovery_body_template_applied` | 故障復帰記事で専用本文テンプレを適用した post 作成後 | `post_id`, `title`, `injury_part`, `return_timing`, `section_count`, `template_version` | `src/rss_fetcher.py:7107` | 故障部位と復帰見通しを含む本文型が実際に載ったか確認 | `injury_part` や `return_timing` が空のまま連続、`section_count < 4` |
| `social_body_template_applied` | social_news 由来の記事で専用本文テンプレを適用した post 作成後 | `post_id`, `title`, `final_category`, `source_type_indicator`, `section_count`, `quote_count`, `template_version` | `src/rss_fetcher.py:7451` | social_news 専用本文型が実際に載ったか確認 | `section_count < 4`、`quote_count=0` が続く、`source_type_indicator` が偏る |
| `media_xpost_evaluated` | news / social_news 記事の本文生成後、media X post selector の対象判定を記録 | `post_id`, `title`, `category`, `article_subtype`, `selector_type`, `is_target` | `src/rss_fetcher.py` | own_source / npb_notice / manager_media のどの selector が評価されたか把握 | `selector_type=none` が想定対象記事で増える、`is_target=true` の母数に対して `media_xpost_embedded` が極端に少ない |
| `media_xpost_skipped` | 対象記事で quote 埋め込みが 0 件、または 2件目が取れなかった post 作成後 | `post_id`, `title`, `category`, `article_subtype`, `skip_reason`, `pool_size_checked`, `best_candidate_score`, `best_candidate_handle`, `best_candidate_age_hours` | `src/rss_fetcher.py` | なぜ発動しなかったかを定量で追う | `pool_empty` が連発、`time_window_exceeded` が多発、`same_account_excluded` が偏る |
| `media_xpost_embedded` | social_news 記事の source tweet、または notice / manager 記事に紐付いた公式・報道ポストを本文冒頭に埋め込んだ post 作成後 | `post_id`, `title`, `source_type`, `media_handle`, `quote_account`, `media_url`, `embed_section_type`, `match_reason`, `match_score`, `quote_index`, `quote_count_in_article`, `position` | `src/rss_fetcher.py:7757` | source tweet / 公示ポスト / 報道ポスト埋め込みが本番記事に載ったか確認 | `social_body_template_applied` や `notice_body_template_applied` / `manager_body_template_applied` はあるのに出ない、`quote_count_in_article=2` が急増、`embed_section_type` や `match_reason` が想定外、`media_handle` が空で続く |
| `x_post_ai_generated` | draft 生成時に X 文面プレビューを組み立てた後 | `post_id`, `category`, `article_subtype`, `ai_mode`, `generated_length`, `fallback_used`, `preview_text` | `src/rss_fetcher.py` | Gemini が実際に使われたか、fallback 文面になったかを確認 | `fallback_used=true` が連発、`generated_length` が極端に短い、`preview_text` が単調 |
| `x_post_ai_failed` | Gemini プレビュー生成が失敗、または safety/daily limit で deterministic fallback に落とした時 | `post_id`, `category`, `article_subtype`, `error_type`, `fallback_used` | `src/rss_fetcher.py` | 失敗種別の切り分け | `timeout` / `request_error` / `daily_limit_reached` / `blocked_phrase:*` が連発 |
| `publish_disabled_for_subtype` | `RUN_DRAFT_ONLY=0` でもカテゴリ別 publish フラグが `0` のため draft 維持した時 | `post_id`, `title`, `article_subtype`, `category`, `skip_reason` | `src/rss_fetcher.py` | 段階公開でどの subtype が gate に止められたか確認 | 想定外 subtype で連発、受け入れOKカテゴリなのに出続ける |
| `live_update_publish_disabled` | `article_subtype=live_update` を publish 対象外として draft 維持した時 | `post_id`, `title`, `article_subtype`, `category`, `skip_reason` | `src/rss_fetcher.py` | live update が publish gate で止まっているか確認 | `RUN_DRAFT_ONLY=0` で live update が publish される、または本イベントが出ない |
| `featured_media_observation_missing` | `RUN_DRAFT_ONLY=1` 中でも featured_media 欠落を観測した時 | `post_id`, `title`, `article_subtype`, `category`, `observation_only` | `src/rss_fetcher.py` | draft-only 受け入れ試験中の画像欠落監視 | `featured_media_missing` が publish skip に出ないのに、本イベントも出ない |
| `x_post_subtype_skipped` | `AUTO_TWEET_ENABLED=1` かつカテゴリ許可済みでも subtype 別 X 投稿フラグが `0` のため投稿しなかった時 | `post_id`, `title`, `category`, `article_subtype`, `reason` | `src/rss_fetcher.py` | X 投稿の段階公開でどの subtype が gate に止められたか確認 | 受け入れ済み subtype なのに連発、または `x_skip_reason_counts.x_post_disabled_for_subtype` と乖離 |
| `rss_fetcher_run_summary` | 1 run 終了時 | `dry_run`, `draft_only`, `has_game`, `opponent`, `venue`, `entry_limit`, `total_entries`, `drafts_created`, `skip_duplicate`, `skip_filter`, `error_count`, `x_post_count`, `x_post_daily_limit`, `x_ai_generation_count`, `x_ai_generation_limit` | `src/rss_fetcher.py:6043` | run 単位のKPI監視 | `error_count > 0`、`drafts_created=0` が連続、`x_ai_generation_count` が上限張り付き |
| `rss_fetcher_flow_summary` | 1 run 終了時 | `skip_reasons`, `prepared_category_counts`, `prepared_subtype_counts`, `created_category_counts`, `created_subtype_counts`, `publish_skip_reason_counts`, `publish_observation_counts`, `x_skip_reason_counts`, `x_ai_generation_count`, `x_ai_generation_limit` | `src/rss_fetcher.py:6064` | どこで落ちているか、どのカテゴリが作られたかを見る | `social_too_weak` や `comment_required` が急増、`featured_media_missing` が急増、`publish_observation_counts.featured_media_observation_missing` が急増、`x_ai_generation_count` が上限張り付き。`x_skip_reason_counts.live_update_x_post_disabled` と `x_skip_reason_counts.x_post_disabled_for_subtype` は X 投稿 gate の想定値 |

## 重要なプレーンログ

構造化されていないが、運用上は重要なログです。

| ログ文言 | 発火条件 | 実装 | 観察目的 | 異常の目安 |
|---|---|---|---|---|
| `記事ガードレール発動:` | unverified number や禁止パターンで guardrail が fallback を返す | `src/rss_fetcher.py:2755` | 試合速報/成績記事の誤検知監視 | 同一カテゴリで連発 |
| `記事本文が空のため、安全フォールバック本文を使用` | Gemini本文が空 | `src/rss_fetcher.py:3942` | AI本文生成失敗の検知 | 新 revision で再増加したら要調査 |
| `記事本文が汎用表現に寄りすぎたため、安全版へ差し替え` | generic phrase validator に引っかかった | `src/rss_fetcher.py:3947` | 汎用文の混入検知 | 特定 prompt で集中 |
| `SUMMARY/STATS/IMPRESSIONブロックを破棄` | 英語プレースホルダ系ブロックが残った | `src/rss_fetcher.py:3954` | LLM 出力崩れ検知 | 1日で複数回出たら prompt/validator を確認 |
| `[HIT] ... → {category}` | 記事候補として採用 | `src/rss_fetcher.py:5788`, `5837`, `5846`, `5855` | 取り込み母数の確認 | run summary と乖離したら要確認 |
| `[下書き止め] post_id=... reason=...` | draft で止める条件に該当 | `src/rss_fetcher.py:4698`, `5960` | 公開停止理由の確認 | `featured_media_missing` が急増 |
| `[下書き維持] post_id=... reason=... image=...` | publish せず draft 維持 | `src/rss_fetcher.py:6028` | draft-only / publish skip の確認 | 想定外 reason が増える |
| `[公開] post_id=... image=...` | publish 成功、X はスキップ | `src/rss_fetcher.py:6025` | 公開経路の確認 | `image=なし` が増える |
| `[公開+X投稿] post_id=...` | publish と X 投稿成功 | `src/rss_fetcher.py:6018` | 公開とX自動化の成功確認 | 0件が続く、または日次上限に早く達する |
| `[X投稿失敗] post_id=...` | X API 投稿失敗 | `src/rss_fetcher.py:6020` | X 投稿障害監視 | 1件でも要確認 |
| `[X投稿スキップ] post_id=... reason=...` | X投稿しない条件に該当 | `src/rss_fetcher.py:6024` | X 側の skip 理由確認 | `daily_limit` や `missing_featured_media` が急増。`live_update_x_post_disabled` は `ENABLE_X_POST_FOR_LIVE_UPDATE=0`、`x_post_disabled_for_subtype` は subtype 別 X gate による意図的除外 |
| `publish_disabled_for_subtype` | subtype別 publish gate による draft 維持 | `src/rss_fetcher.py` | 段階公開の gate 監視 | `publish_skip_reason_counts.publish_disabled_for_subtype` と乖離する、または受け入れ済み subtype で連発 |
| `live_update_publish_disabled` | live_update の publish を強制停止 | `src/rss_fetcher.py` | publish 側 live_update 隔離の監視 | live_update 記事が publish される、または `publish_skip_reason_counts.live_update_publish_disabled` と乖離する |
| `featured_media_observation_missing` | draft-only 中の画像欠落観測 | `src/rss_fetcher.py` | 受け入れ試験中のアイキャッチ欠落監視 | `publish_observation_counts.featured_media_observation_missing` と乖離する、または画像欠落記事があるのに出ない |
| `x_post_subtype_skipped` | subtype別 X gate による X 投稿停止 | `src/rss_fetcher.py` | X 段階公開の gate 監視 | `x_skip_reason_counts.x_post_disabled_for_subtype` と乖離する、または受け入れ済み subtype で連発 |
| `x_post_ai_failed` | draft 生成時の Gemini プレビュー失敗 | `src/rss_fetcher.py` | X文面AIの失敗種別確認 | `timeout` / `request_error` / `blocked_phrase:*` が増える |
| `[WP] 画像アップロード開始` | 画像アップロード開始 | `src/wp_client.py:283` | 画像処理の入口確認 | 開始はあるのに成功/skip がない |
| `[WP] 画像ダウンロード Content-Type=...` | 画像取得後 | `src/wp_client.py:305` | MIME 判定の確認 | `text/html`, `application/*`, `image/svg+xml` が増える |
| `[WP] 画像アップロードskip:` | 画像候補を不採用にした | `src/wp_client.py:288`, `311` | アイキャッチ失敗理由の確認 | 同一URLパターンで連発 |
| `[WP] 画像アップロード media_id=...` | WP media 登録成功 | `src/wp_client.py:339` | アイキャッチ成功確認 | 開始件数に対して著しく少ない |
| `[WP] 画像アップロード失敗` | WP media API 失敗 | `src/wp_client.py:352` | WP 側 4xx/5xx 監視 | 1 run で複数件出たら要調査 |
| `=== rss_fetcher 開始 ===` / `=== 完了: ... ===` | run の開始 / 終了 | `src/rss_fetcher.py:5647`, `6036` | 実行ライフサイクル確認 | 完了ログがない、または error 増加 |

## Logs Explorer クエリ例

サービス名は `yoshilover-fetcher` 前提です。

注記:

- 現在の構造化イベントは `logger.info(json.dumps(...))` で出しているため、Logs Explorer では `jsonPayload.event` ではなく `textPayload:"event_name"` で引く。
- 以降のクエリはその前提でそのまま使える形にしている。

### 1. run サマリを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"rss_fetcher_run_summary"
```

### 2. flow サマリを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"rss_fetcher_flow_summary"
```

### 3. title 衝突だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"title_collision_detected"
```

### 4. title テンプレ使用状況を見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"title_template_selected"
```

### 5. SNS 救済だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"sns_weak_rescued"
```

### 6. AI ルート上書きだけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"article_ai_route_override"
```

### 7. 首脳陣テンプレ適用だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"manager_body_template_applied"
```

### 8. アイキャッチ候補除外だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"image_candidate_excluded"
```

### 9. 試合前後テンプレ適用だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"game_body_template_applied"
```

### 10. 公示テンプレ適用だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"notice_body_template_applied"
```

### 11. 2軍育成テンプレ適用だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"farm_body_template_applied"
```

### 12. safe fallback と guardrail を見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"記事本文が空のため、安全フォールバック本文を使用"
 OR textPayload:"記事ガードレール発動")
```

### 13. 故障復帰テンプレ適用だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"recovery_body_template_applied"
```

### 14. 画像アップロード失敗だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"[WP] 画像アップロード失敗"
```

### 15. social_news 本文テンプレ適用だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"social_body_template_applied"
```

### 16. source tweet 埋め込みだけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"media_xpost_embedded"
```

### 17. media X post selector の対象判定を見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"media_xpost_evaluated"
```

### 18. media X post の非発動理由だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"media_xpost_skipped"
```

### 19. X文面の Gemini プレビューを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"x_post_ai_generated"
```

### 20. X文面の Gemini fallback / failure を見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"x_post_ai_failed"
```

### 21. draft-only 中の画像欠落観測を見る

何が見えるか:

- 受け入れ試験中でもアイキャッチ欠落が発生している post を拾える

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"featured_media_observation_missing"
```

### 22. live_update の publish ブロックを見る

何が見えるか:

- live_update が publish gate で意図どおり止まっているか確認できる

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"live_update_publish_disabled"
```

### 23. subtype 別 publish gate を見る

何が見えるか:

- どの subtype が publish gate で止められたか確認できる

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"publish_disabled_for_subtype"
```

### 24. subtype 別 X gate を summary で見る

何が見えるか:

- `x_skip_reason_counts.x_post_disabled_for_subtype` が発生している run をまとめて見られる

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"rss_fetcher_flow_summary"
textPayload:"x_post_disabled_for_subtype"
```

### 25. subtype 別 X 投稿スキップの明細を見る

何が見えるか:

- どの post が `x_post_disabled_for_subtype` で止まったか明細で確認できる

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"x_post_subtype_skipped"
```

### 26. media X post の対象判定と非発動理由をまとめて見る

何が見えるか:

- B.5 の selector 判定と skip reason を並べて追える

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"media_xpost_evaluated" OR textPayload:"media_xpost_skipped")
```

### 27. media X post の埋め込み成功だけを見る

何が見えるか:

- 実際に本文へ埋め込まれた source tweet / 報道ポストだけを確認できる

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"media_xpost_embedded"
```

### 28. X 文面 AI の生成と失敗をまとめて見る

何が見えるか:

- `generated` と `failed` を同じ画面で見て、fallback 率を把握できる

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"x_post_ai_generated" OR textPayload:"x_post_ai_failed")
```

### 29. 画像の再取得と fallback 適用を見る

何が見えるか:

- 元記事再取得や fallback 画像投入がどこで発生したか追える

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"article_image_refetched" OR textPayload:"featured_image_fallback_applied")
```

### 30. 既存記事の featured_media 再利用を見る

何が見えるか:

- 既存 draft / post から featured_media を再利用して救済したケースを確認できる

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"featured_media_reused_from_existing_post"
```

## 受け入れ試験の観察テンプレ

### 朝の観察 5 項目

1. run 全体の結果

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"rss_fetcher_run_summary"
```

2. flow summary の詰まりどころ

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
textPayload:"rss_fetcher_flow_summary"
```

3. 画像欠落の観察

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"featured_media_observation_missing" OR textPayload:"featured_media_missing")
```

4. publish / X gate の止まり方

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"publish_disabled_for_subtype"
 OR textPayload:"live_update_publish_disabled"
 OR textPayload:"x_post_subtype_skipped")
```

5. X 文面 AI と B.5 の健康状態

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"x_post_ai_failed"
 OR textPayload:"media_xpost_skipped"
 OR textPayload:"media_xpost_embedded")
```

### scheduler 実行後の確認クエリ

1. 最新 run の summary

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
timestamp>="-15m"
(textPayload:"rss_fetcher_run_summary" OR textPayload:"rss_fetcher_flow_summary")
```

2. その run で作られた記事の gate / AI / media X 状態

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
timestamp>="-15m"
(textPayload:"publish_disabled_for_subtype"
 OR textPayload:"live_update_publish_disabled"
 OR textPayload:"featured_media_observation_missing"
 OR textPayload:"x_post_subtype_skipped"
 OR textPayload:"x_post_ai_generated"
 OR textPayload:"x_post_ai_failed"
 OR textPayload:"media_xpost_evaluated"
 OR textPayload:"media_xpost_skipped"
 OR textPayload:"media_xpost_embedded")
```

### 問題検知時の診断クエリ

1. publish されない理由を掘る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"publish_disabled_for_subtype"
 OR textPayload:"live_update_publish_disabled"
 OR textPayload:"featured_media_observation_missing"
 OR textPayload:"[下書き止め]")
```

2. X 投稿されない理由を掘る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"x_post_subtype_skipped"
 OR textPayload:"[X投稿スキップ]"
 OR textPayload:"x_post_ai_failed")
```

3. 画像処理だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"article_image_refetched"
 OR textPayload:"featured_image_fallback_applied"
 OR textPayload:"featured_media_reused_from_existing_post"
 OR textPayload:"[WP] 画像アップロード失敗")
```

4. B.5 だけを見る

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
(textPayload:"media_xpost_evaluated"
 OR textPayload:"media_xpost_skipped"
 OR textPayload:"media_xpost_embedded")
```

## ログ整合性チェック

現状コード上で、以下は矛盾ではありません。

1. `image_candidate_excluded` が出ているのに `featured_media` 付きで保存される
   - 候補URL単位の除外ログです。1記事に複数候補があり、1つを除外して別候補で成功することがあります。

2. `title_collision_detected` が出ているのに draft が作成される
   - このログは観察用 WARNING で、作成停止ロジックではありません。

3. `sns_weak_rescued` が出ているのにカテゴリが `コラム` や `ドラフト・育成` のまま
   - 救済は「取り込み可否」の上書きであり、カテゴリ自体は変更しません。

4. `article_ai_route_override` が出ているのに WPカテゴリは元のまま
   - AI本文生成ルートだけを上書きしており、WPカテゴリ保存ロジックは別です。

現時点で、コード上の明確な相互矛盾は見つかっていません。

## 運用でまず見る順番

1. `rss_fetcher_run_summary`
2. `rss_fetcher_flow_summary`
3. `title_collision_detected`
4. `image_candidate_excluded` と `[WP] 画像アップロード失敗`
5. `sns_weak_rescued`
6. `article_ai_route_override`
7. `記事本文が空のため、安全フォールバック本文を使用`
8. `farm_body_template_applied`
9. `social_body_template_applied`
10. `media_xpost_embedded`
11. `x_post_ai_generated`
12. `x_post_ai_failed`
