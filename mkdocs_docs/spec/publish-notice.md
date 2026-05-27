# :material-email-fast: 通知メール (publish-notice)

!!! info "これは何のメール"

    WordPress に記事が ==1 件== 作られたり公開されたりした時に、 user の Gmail に届く通知メール。
    WP 管理画面を毎回見にいかなくても、 メールでタイトル / 本文抜粋 / 編集 link を確認できる。

## :material-source-fork: 送信元 (2 か所)

=== ":material-fast-forward: fetcher サービス"

    記事の下書きを作った直後、 サービス内部から ==そのまま 1 件分== のメールを送る (即時通知)。

    - 実装: `src/rss_fetcher.py` 内の `_build_inline_draft_notice_request` / `_send_fetcher_inline_draft_notices`
    - request に付ける印: `notice_origin="fetcher_inline_draft_notice"`、 `record_type="draft_notice"`
    - 実行場所: Cloud Run service `yoshilover-fetcher`

=== ":material-clock-outline: publish-notice ジョブ"

    スケジューラで時間ごとに起動して、 まだ通知していない記事を ==まとめて== メール送信する。

    - 実装: `src/publish_notice_scanner.py` + `src/publish_notice_email_sender.py`
    - 実行場所: Cloud Run job `publish-notice`
    - スケジュール (JST):

    | スケジューラ | 発火タイミング |
    | --- | --- |
    | `publish-notice-trigger` | 6〜15 時の毎時 5 分 |
    | `publish-notice-trigger-evening` | 16〜22 時の 5 分 / 35 分 |
    | `publish-notice-trigger-burst-tail` | 7,10,12,15,17,20,21 時の 10 分 |

!!! warning "両方リデプロイ必須"

    送信ロジック本体は 1 つのファイル (`src/publish_notice_email_sender.py`) だが、 fetcher サービスと publish-notice ジョブで Docker image が別々。
    ==コードを直したら両方リデプロイしないと挙動が揃わない==。

## :material-tag: 件名の【○○】の決まり方

メールの件名は必ず先頭に「【○○】」が付く。 6 種類。
判定は `_per_post_mail_state` 関数 (`src/publish_notice_email_sender.py:1906`)。

### :material-flash: 早期 return

`notice_kind == "post_gen_validate"` の時 → ==【要確認】 (review) で即決定==。 (`reason=post_gen_validate`)

### :material-numeric-1-circle: 初期判定 (上から順に)

| 順 | 条件 | mail_class | reason |
| --- | --- | --- | --- |
| 1 | title / summary に urgent keyword 検出 | **urgent** | `urgent_keyword_detected` |
| 2 | manual X candidate が綺麗で安全 subtype | **x_candidate** | `manual_x_candidates_clean` |
| 3 | suppression_reason == `roster_movement_yellow` | **review** | `roster_movement_yellow_x_blocked` |
| 4 | suppression_reason == `sensitive_content_x_blocked` | **review** | `sensitive_content_x_blocked` |
| 5 | article_type が cautious subtype | **review** | `cautious_subtype_review` |
| 6 | title / summary に sensitive 語 | **review** | `sensitive_gate_review` |
| 7 | raw_summary あり、 かつ summary_fallback | **review** | `summary_dirty_review` |
| 8 | manual_x_candidate が dirty | **review** | `candidate_copy_review` |
| 9 | (上記いずれにも該当しない) | **publish** | `publish_notice_default` |

### :material-numeric-2-circle: 後段 flip (publish / x_candidate のみが review に格上げ)

| flip 条件 | reason |
| --- | --- |
| first_team_subtype_review_reason | `first_team_postgame_review` / `first_team_lineup_review` |
| program_notice_review_reason | (各 reason) |
| roster_notice_review_reason | (各 reason) |
| injury_recovery_notice_review_reason | (各 reason) + `x_post_ready=false` |
| default_review_reason | (各 reason) + `x_post_ready=false` |
| farm_subtype_review_reason | (各 reason) |

### :material-numeric-3-circle: 最終 flip (publish のみが draft に振替え)

`_is_draft_notice_request(request)` が True かつ mail_class が `publish` の時 → **draft** (`draft_notice_default`)。

`_is_draft_notice_request` の判定:

- `record_type == "draft_notice"` であれば True
- もしくは `notice_origin in {"fetcher_inline_draft_notice"}` であれば True

## :material-format-list-bulleted: 6 種類の mail_class と prefix

【緊急】 (urgent)
:   炎上ワード検出時。 priority urgent。

【投稿候補】 (x_candidate)
:   X 投稿候補として綺麗、 かつ安全な subtype の時。 priority normal。

【要確認】 (review)
:   要約崩れ / sensitive 語 / 一軍試合結果 / 二軍結果 / 番組 / 起用 / 故障復帰 など。 priority high。

【下書き】 (draft)
:   下書き状態の記事。 priority normal。

【公開済】 (publish)
:   上記いずれにも該当しない default。 priority normal。

【まとめ】 (summary)
:   burst 多発時にまとめて送る集約メール。 priority low。

prefix の literal とその他の設定値は `_MAIL_CLASS_CONFIGS` (`src/publish_notice_email_sender.py:243`)。

## :material-form-textbox: 件名の組み立て

```
{prefix}[｜{subtype}]{追加タグ}{title} | YOSHILOVER
```

- **prefix**: 上の mail_class 由来 (【緊急】等)
- **subtype**: postgame / lineup / manager / pregame / farm / summary など (該当無しなら省略)
- **追加タグ**: review reason がある時 (例:【要review｜post_gen_validate】)
- **title**: WP 記事タイトル、 80 字超なら trim (`_SUBJECT_BODY_LIMIT=80`)
- **suffix**: ` | YOSHILOVER` 固定

件名が古くなる閾値は `PUBLISH_NOTICE_SUBJECT_STALE_HOURS` (default ==24 時間==、 `_SUBJECT_STALE_HOURS_DEFAULT=24.0`)。

## :material-view-list: HTML メール body の中身 (上から順)

`build_body_html_per_post` 関数 (`src/publish_notice_email_sender.py:2757`) が組み立てる。 11 要素を上から順に並べる。

1. **brand header band** (オレンジグラデ、 「🐰 ヨシラバー / ⚾ 読売ジャイアンツ速報掲示板」)
2. **「📝 新規 下書き」 chip** (literal 固定)
3. **記事タイトル** (`safe_title`)
4. **記事 URL** (`🔗 safe_url`)
5. **本文抜粋ブロック** (`body_excerpt_html_block`、 body_excerpt があれば。 「📄 本文(抜粋)」 ラベル + 緑左ボーダー)
6. **アイキャッチ画像 preview** (`image_preview_html`、 `ENABLE_SHARE_X_BUTTON=1` かつ publish_button_url がある時)
7. **📰 記事を見る ボタン** (常時、 青、 `safe_url` へ遷移)
8. **📱 画像つきで X に投稿 (おすすめ) ボタン** (`share_x_button_html`、 ENABLE_SHARE_X_BUTTON が truthy かつ publish_button_url がある時、 オレンジ、 `/share-x?` 経由)
9. **🚀 公開してX投稿画面へ ボタン** (`publish_button_html`、 publish_button_url がある時、 緑、 `/publish-and-tweet?` 経由)
10. **✏️ WP編集画面で確認 ボタン** (`admin_edit_button_html`、 admin_edit_url がある時、 白底に紺ボーダー)
11. **footer** (グレー、 「🐰 ヨシラバー / ⚾ 読売ジャイアンツ速報掲示板 ｜ 新規 下書き 自動通知」)

!!! note "notice_kind が post_gen_validate の時は HTML を返さない"

    `build_body_html_per_post` は早期 return で None を返し、 text-only fallback になる。

## :material-shield-check: 重複の防ぎ方

- 同じ post_id を ==24 時間以内に 1 回== まで送信
- 過去の送信記録は `logs/publish_notice_history.json` に保存

## :material-clock-alert: STALE skip (古いものを送らない)

scanner 側で 24 時間を超えた古い entry は STALE として skip する。

| skip 対象 | skip reason | 場所 |
| --- | --- | --- |
| review entry が 24h 超過 | `STALE_REVIEW` | `publish_notice_scanner.py:2073` |
| reject entry が 24h 超過 | `STALE_POST_GEN_VALIDATE` | `publish_notice_scanner.py:2321` |
| preflight skip が 24h 超過 | `STALE_PREFLIGHT_SKIP` | `publish_notice_scanner.py:2538` |

これにより、 古い記事の時間差通知 (今になって 4 月の記事が【要確認】 mail で来る等) を防ぐ。

## :material-cog: 主な環境変数 (publish-notice ジョブ)

??? abstract "クリックで展開"

    出典: `gcloud run jobs describe publish-notice` 2026-05-27 実行結果。

    | env | 実値 | 用途 |
    | --- | --- | --- |
    | `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP` | 1 | 送信 + WP status 確認後だけ history stamp |
    | `ENABLE_PUBLISH_NOTICE_TWO_PHASE` | 1 | scan を direct / review 2 phase に分離 |
    | `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` | 1 | 古い候補は 1 度だけ通知 |
    | `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL` | 1 | old candidate ledger の TTL 有効 |
    | `ENABLE_PUBLISH_NOTICE_CLASS_RESERVE` | 1 | mail class 別の最低発火枠 |
    | `ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR` | 1 | 24h budget soft/hard threshold |
    | `ENABLE_PUBLISH_NOTICE_JUDGMENT_BATCH` | 1 | judgment batch mail |
    | `ENABLE_PUBLISH_ONLY_MAIL_FILTER` | 0 | 1 で【公開済】を抑制 |
    | `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS` | 1 | direct publish 経路は filter 例外 |
    | `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS` | 1 | backlog は filter 例外 |
    | `ENABLE_SHARE_X_BUTTON` | 0 | 1 で画像つき X ボタン |
    | `PUBLISH_NOTICE_SUBJECT_STALE_HOURS` | (default 24.0) | 件名 STALE 閾値 |

## :material-folder-file: 関連 file

- 送信ロジック本体: `src/publish_notice_email_sender.py`
- 走査側: `src/publish_notice_scanner.py`
- fetcher 内の inline 経路: `src/rss_fetcher.py` (`_build_inline_draft_notice_request` / `_send_fetcher_inline_draft_notices`)
- HTML body builder: `src/publish_notice_email_sender.py:2757` `build_body_html_per_post`
- mail_class 判定: `src/publish_notice_email_sender.py:1906` `_per_post_mail_state`
- mail_class config: `src/publish_notice_email_sender.py:243` `_MAIL_CLASS_CONFIGS`
- draft 判定: `src/publish_notice_email_sender.py:2036` `_is_draft_notice_request`
