# 430 XPOST Source A Yoshilover voice prompt + validator

## 1. ticket header

- **ticket id**: 430
- **status**: PARTIAL_REPO_IMPL_TESTED
- **owner**: Codex B
- **lane**: B
- **created**: 2026-05-23
- **priority**: P1
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/100
- **parent**: `doc/active/428-XPOST-branding-requirements-v2.md`

## 2. purpose

Source A(RSS/Gemini) を RSS要約ではなく、ヨシラバー voice の観戦ポストに変換する。

## 3. scope

| 項目 | 内容 |
|---|---|
| 対象 | RSS / Gemini 由来の文章 candidate |
| 文字数 | **100-180字** (2026-05-25 user 確定で 180-280→100-180 短文化)。60字未満 hard NG、100字未満 warn |
| 行数 | 2-3行、1行1観点 |
| 必須軸 | fact 1つ、観戦感 1つ、ファン感情 1つ |
| 着地 | 次に見る点 / 改善ポイント / 巨人ファンとして期待したい点 |
| fact ground | DB fact があれば最大1つ。なければ RSS 内の確定情報 |
| 選手名表記 | **フルネーム (姓+名)、 敬称なし**。 例「坂本勇人」「戸郷翔征」「岡本和真」。 「さん / 君」 禁止。 nickname は ring name (大勢 等) のみ |
| 同一選手出現 | **1 post 内 最高 2 回まで** (3 回以上の連発 NG)。 流れにより 1-2 回 自然に |

## 4. acceptance criteria

- Source A は RSS見出しの言い換えで終わらない。
- DB / RSS にない数字を作らない。
- URL / hashtag / 媒体名を含めない。
- `ついに` / `我が軍` / `戦犯` / `限界` / `終わった` / `不要` / `使うな` / `詰み` を含めない。
- ネガティブ表現を使う場合は、批判で終わらず次に見る点へ着地する。
- 試合中 / 試合後の明確なイベント時だけ Source A 比率を上げられる。

## 5. do not touch

- Source B DB表 format
- Source C DB schema
- Cloud Run deploy
- Cloud Scheduler
- env / Secret
- WP投稿
- X live post
- Tavily REST

## 6. tests

- 180-280字 / 2-3行 validator。
- fact presence validator。
- banned phrase validator。
- headline rewrite similarity fixture。
- unverified number fixture。
- negative-but-next-view fixture。

## 7. STOP conditions

- fact ground が取れず、数字や具体情報を推測する必要がある場合。
- Gemini 生成だけで validator が通らないが、自動補正で事実が変わりそうな場合。
- Tavily REST を使わないと成立しない設計になる場合。

## 8. work log

- 2026-05-23 JST: 428 から child ticket として作成。
- 2026-05-23 JST: `build_news_opinion_candidate()` の Source A fallback 文面を、RSS見出しの短い言い換えではなく 180-280字 / 3行 / 確定情報だけを使うヨシラバー voice に変更。
- 2026-05-23 JST: `build_comment_numeric_candidate()` のコメント×DB候補を、DB fact 1つ + 観戦感 + 次に見る点の3行構成に変更。
- 2026-05-23 JST: Source A の文字数・行数を `_candidate_anomaly_flags()` で検査。140字未満は hard、180字未満は warn として可視化。
- 2026-05-23 JST: Gemini prompt 本体の改修、RSS見出し類似度、未確認数字 whitelist までは未実装。
- 2026-05-25 JST: user 確定 spec 改定: (a) 文字数 180-280 → **100-180**、 (b) 選手名 **フルネーム + 敬称なし**、 (c) **同一選手名 最高 2 回まで**、 (d) 試合中 17-22 時 hint 熱量 ramp up。 prompt (`x_post_branding_gen.py`) + validator (`x_post_mail_lane.py:_source_a_voice_flags` 140→60 hard / 180→100 warn) deploy 済 (commit e09af39 + 追加 commit、 image tag `xpost-fix-*`)。
