# 195 article footer 手動 X 投稿シェアコーナー(B1)

- priority: P0.5
- status: READY_FOR_AUTH_EXECUTOR
- owner: Codex / Claude follow-up
- lane: Front-Claude
- parent: 190 / 191 / 176 / B1

## Background

- user 明示: 「リアルタイム掲示板を作る」「mail(A) で X 候補は乗ってる」「記事側にも乗せたい(B1)」
- `1ac710b` で公開通知メール向けの手動 X 候補生成が land 済み
- B2 / B3(他者 X oEmbed / 試合中 X stream) は X API 課金境界があるため今回対象外
- B1 は X API 不要、手動コピペ前提、frontend plugin 内で完結させる

## Scope

- `src/yoshilover-063-frontend.php`
- `doc/waiting/195-article-footer-manual-x-share-corner.md`
- `doc/README.md`
- `doc/active/assignments.md`

## Non-Goals

- Python backend / publish notice mail logic の変更
- WP REST write / live deploy / Cloud Run / Scheduler / Secret Manager
- SWELL theme dir 直接編集
- 他者 X post oEmbed / 試合中 stream / X API live post

## Placement

- target: published single post page のみ
- insertion point: `the_content` filter で本文末尾に append
- existing article footer stack の中では `article_bundles` の後、`x_follow_cta` の前に追加
- enable=false のときは従来 layout を維持

## Render Contract

- heading: `この記事を X でシェア`
- card count: 3 fixed
- each card:
  - candidate label
  - readonly textarea(コピペ元)
  - `コピー` button
  - `Xで開く` intent link(`https://twitter.com/intent/tweet?text=...`)
- copied / intent text always includes:
  - article permalink
  - `#巨人 #ジャイアンツ`
  - subtype-specific extra hashtag(任意追加)

## Subtype Mapping

Frontend 側では既存の `yoshilover_063_resolve_front_density_subtype()` を土台にしつつ、share corner 用に `lineup / postgame / farm / notice / program / default` へ丸める。

| subtype | candidate labels | text direction |
|---|---|---|
| lineup | 更新 / ファン視点 / 試合前注目 | スタメン更新、反応フック、試合前チェック |
| postgame | 更新 / 試合観 / 後で見直し | 試合結果更新、試合観、見返しポイント |
| farm | 更新 / ファン視点 / 動向 follow | 二軍更新、反応フック、継続ウォッチ |
| notice | 更新 / 動向 / 後効き | 公示整理、動向整理、後から効く観点 |
| program | 更新 / ファン視点 / 見逃し注意 | 番組更新、ファン目線、見逃し防止 |
| default | 更新 / ファン視点 / 見逃せない | 汎用巨人ニュース |

確認元:

- `src/publish_notice_email_sender.py`
  - `_manual_x_article_type()`
  - `_manual_x_article_intro_lead()`
  - `_manual_x_fan_reaction_lead()`
  - `_manual_x_inside_voice()`

今回の frontend 実装は mail 側 189 の「最大 4 本」ではなく、user 指定どおり 3 fixed に揃える。

## Toggle

- WP option: `yoshilover_063_manual_x_share_corner`
  - `enabled` default true
  - `heading` override 可
- env override: `YOSHILOVER_063_MANUAL_X_SHARE_CORNER`
  - falsey: `0 / false / off / no / disable / disabled`
  - truthy: `1 / true / on / yes / enable / enabled`
- precedence: env override > WP option > default

## HTML / CSS / JS

- HTML namespace: `.yoshi-x-share-corner`
- CSS: plugin 内 inline style
  - subtype accent color
  - 3 card grid
  - mobile 1 column
  - SWELL 既存 color var (`--orange`) と整合
- JS: plugin 内 inline script
  - Clipboard API 優先
  - fallback は textarea select + `document.execCommand('copy')`
  - 成功時は button label と status text を短時間更新

## Verification

- `php -l src/yoshilover-063-frontend.php`
- result: syntax error なし
- `src/publish_notice_email_sender.py` の subtype/article-type helper を read-only で照合し、`lineup / postgame / farm / notice / program / default` の丸めが崩れていないことを確認

## Guardrails Held

- Python backend touched: NO
- tests/ Python touched: NO
- WP write: NO
- Cloud Run deploy: NO
- git push: NO
