# 081 X Source Notice Lane

## Purpose

X (旧 Twitter) の投稿を `x_source_notice` subtype の独立記事として扱うための contract / builder / validator / dry-run CLI を追加する。

064 の X source 3 tier (fact / topic / reaction) を前提とし、本 lane は **fact source と topic source のみ** を対象に、狭く断定できる X 投稿を 1 source = 1 nucleus = 1 article で記事化する狭い path を固定する。reaction source はこの lane の対象外(064 のとおり記事下 SNS 反応 / hub 話題補助にだけ使う)。

## Boundary

- 対象 platform は `x` のみ
- 080 (Instagram / YouTube) とは **別 lane** として共存し、payload / validator / output を混ぜない
- 064 の 3 tier 分類を前提に、対象は `fact source` と `topic source` に限定する
- `reaction source` は本 lane の対象外(本文 fact に使わない、記事候補化しない)
- account allowlist はこの段階では持ち込まない
- 1 source = 1 nucleus = 1 article を固定する
- 061 全面 gate の試合 state trigger とは独立(本 lane は X source 投稿 event ベース、試合 state ベースではない)
- 061-P1 (published article auto-post bridge) とも独立(本 lane は draft era の記事化、P1 は published 後の teaser auto-post)

## Supported Platforms

- `x`

## Source Tier (064 基準)

`source_tier` は 064 の 3 区分に揃える。

- `fact` — 球団公式 / NPB 公式 / 球団一次発表に準ずる明確な公式 X / 公式コメント主体が確認できる一次 X
- `topic` — 主要媒体 X / 記者 X / TV・ラジオ発言を要約した報道 X / メディア速報ポスト / 話題化の起点になる報道アカウント投稿
- `reaction` — (本 lane 非対象、validator で hard fail)

## Payload Schema

`XSourceNoticePayload`

- `source_platform` (固定値 `x`)
- `source_url`
- `source_account_name`
- `source_account_type` (`team_official` / `league_official` / `press_major` / `press_reporter` / `press_misc`)
- `source_tier` (`fact` / `topic`)
- `post_kind` (`post` / `quote` / `reply` の 3 種、`repost` は除外)
- `post_text`
- `published_at`
- `supplement_note`

## Article Schema

`XSourceNoticeArticle`

- `subtype` (固定値 `x_source_notice`)
- `title`
- `body_html`
- `badge`
- `nucleus_subject`
- `nucleus_event`
- `source_platform`
- `source_url`
- `source_account_name`
- `source_account_type`
- `source_tier`
- `post_kind`
- `published_at`

## Body Layout

`body_html` は次の 2〜3 行で構成する。

1. 出典行 (アカウント名 + tier badge + canonical X URL)
2. `post_text` 由来の事実要約 1 文
3. `supplement_note` がある場合だけ補足 1 文

embed HTML / oEmbed / thumbnail / avatar は持ち込まず、link-based article として成立させる。マスコミ X の引用は 064 / CLAUDE.md §18 の「oEmbed のみ」制約を破らない(本 lane は embed を使わないので自動的に準拠)。

## Validator Hard Fail

- `SOURCE_MISSING`
- `UNSUPPORTED_PLATFORM` (platform が `x` 以外)
- `UNSUPPORTED_TIER` (`source_tier = reaction` 等)
- `UNSUPPORTED_POST_KIND` (`repost` 等)
- `SOURCE_BODY_MISMATCH`
- `MULTIPLE_NUCLEI`
- `OPINION_LEAK`
- `TITLE_BODY_MISMATCH`
- `TOPIC_TIER_AS_FACT` (`source_tier = topic` を title 断定 / fact 断定に使おうとしている)

## Tier 別挙動

- `fact` → title の断定文 / 本文冒頭 fact block / fixed lane の事実根拠に使ってよい
- `topic` → candidate 化のみ。title / body fact への昇格は primary recheck 済 flag がない限り validator で `TOPIC_TIER_AS_FACT` を返す
- `reaction` → `UNSUPPORTED_TIER` で hard fail、本 lane では記事化しない

## Badge Metadata

一覧向け metadata として `badge = {"platform": "x", "source_tier": ..., "post_kind": ..., "account_type": ...}` を article に保持する。front 側で tier / account_type 表示を分岐できるようにする。

## 071 Reuse

title / body nucleus 一致判定は ticket 071 の `validate_title_body_nucleus(...)` を再利用する。`MULTIPLE_NUCLEI` はそのまま返し、`SUBJECT_ABSENT` と `EVENT_DIVERGE` は `TITLE_BODY_MISMATCH` に写像する。

## 060 / 064 / 061 / 080 接続境界

### 060 (公式 X tone / Draft 期 bridge)

- 060 が定める「Draft URL 禁止」「私見禁止」「中の人 X 自動化禁止」は本 lane でも維持する
- 本 lane が生成する article は draft era の notice lane 産物であり、060 の 061 全面 gate とは独立に draft として蓄積される

### 064 (fact / topic / reaction 3 tier)

- 本 lane は 064 の 3 tier を正本として前提にする
- 064 の「X 単独で勝敗・試合有無・公示・予告先発・故障を断定しない」制約はそのまま validator に写像する (`TOPIC_TIER_AS_FACT`)
- `reaction source` の扱いは 064 のとおり、本 lane では非対象、062 (記事下 SNS 反応) lane へ回す

### 061 全面 / 061-P1

- 本 lane は X source 投稿 event ベース、061 全面 (試合 state ベース) と軸が違う、混ぜない
- 061-P1 (published 後 teaser auto-post) とも軸が違う、本 lane は draft era の記事化

### 080 (Instagram / YouTube)

- platform 列は disjoint (`x` vs `instagram` / `youtube`)、payload / validator / article schema は独立
- 本 lane に `instagram` / `youtube` 投稿を混ぜない、080 lane に X 投稿を混ぜない
- 共通化は 071 validator 再利用のみ、code 本体は分離する

## Non-Goals

- front consumption の配線
- account allowlist
- embed HTML / oEmbed / thumbnail / avatar
- 他 platform 向け lane
- automation wiring
- 実 X API fetch
- publish 経路
- mail chain 連携
- eyecatch 連携
- repost の記事化 (`UNSUPPORTED_POST_KIND`)
- reaction tier の記事化 (`UNSUPPORTED_TIER`)
- primary recheck ロジックの実装 (topic tier 昇格は呼び出し側の責務、本 lane は flag を尊重するだけ)

## 成功条件

- Claude / Codex が同じ X 投稿を見た時、`fact` / `topic` / `reaction` の振り分けを 064 基準で一致して判断できる
- `fact` tier のみで title 断定 / 本文 fact を生成できる
- `topic` tier は candidate のみで、primary recheck flag なしでは fact block に上げられない
- `reaction` tier は validator で hard fail し、記事化されない
- 080 との lane 分離が contract 読解で成立する (`x` / `instagram` / `youtube` が disjoint)
- CLAUDE.md §18 の「マスコミ X 引用は oEmbed のみ」制約を破らない (本 lane は embed を使わない)

## acceptance_check

- ticket 単体で X source 3 tier の分類と hard fail 9 種が読める
- 080 / 064 / 060 / 061 / 061-P1 との境界が 1 段落ずつ読める
- reaction tier / repost が hard fail 対象であることが明記されている
- `TOPIC_TIER_AS_FACT` の存在と意味 (topic を fact へ昇格する時の安全弁) が読める
- `draft era の notice lane` として 061 全面 / 061-P1 と独立 lane であることが明記されている

## runtime 復旧 / 既存 fire 順との関係

- 本 ticket は doc-only contract。044 runtime 復旧 routing を止めない
- 既存 fire 順 (046 ✓ → 047 ✓ → [048 HOLD] → 060 並走 → 061 止め → 080 ✓ → 081) を変更しない
- 実装副作用なし。route / `src/source_trust.py` / X API / automation は触らない
- 080 artifacts は触らない (disjoint lane)
