# Lane V Giants Source Coverage Audit

| field | value |
|---|---|
| ticket | 288-INGEST-source-coverage-expansion |
| lane | V |
| mode | read-only audit / doc-only |
| scope | source coverage only; BUG-004+291 publish gate とは独立 |
| observed window | 2026-05-03 00:00 JST - 2026-05-03 21:33 JST |
| evidence base | `config/rss_sources.json` + repo docs + Cloud Logging (`gcloud logging read`) |
| explicit limits kept | no source add / no deploy / no scheduler / no env / no WP write / no live web fetch |

## 0. Executive Summary

- 5/3 の代表 miss は **source 未登録より downstream gate(D/E/F) が主因** だった。
- ただし source 側の実 gap もあり、最も強いのは **`スポーツ報知 巨人` RSS が active config のまま当日 0 件** だった点。
- 新規 source 候補では **NNN / スポニチWeb / サンスポWeb / 読売オンライン / 東スポ巨人** が mainline 未登録。
- 「今夜すぐ足せる new source」は、**repo-local evidence だけでは 0 件**。一方で、**既存 active source の dead feed 修理(`スポーツ報知 巨人`)の方が優先度は高い**。

## Step 1. 現行 source 一覧

### 1-1. Source inventory (`config/rss_sources.json`)

`disabled` フラグは config に無い。したがって status は全件 `active(config)` で、役割差分は `role` と当日実績で判定する。

| source | url | type | role | 巨人専門/球界全体 | status | 5/3 fetch total | notes |
|---|---|---|---|---|---|---:|---|
| 巨人公式X | `rsshub.../twitter/user/TokyoGiants` | `social_news` | `article_source`,`media_quote_pool` | 巨人専門(公式) | active | 3816 | raw feed items total; last run 19 |
| 読売ジャイアンツX | `rsshub.../twitter/user/yomiuri_giants` | `social_news` | `article_source`,`media_quote_pool` | 巨人専門(公式) | active | 193 | ほぼ 1件/run の低ボリューム |
| スポーツ報知巨人班X | `rsshub.../twitter/user/hochi_giants` | `social_news` | `article_source`,`media_quote_pool` | 巨人専門(番記者) | active | 3839 | high-volume |
| 日刊スポーツX | `rsshub.../twitter/user/nikkansports` | `social_news` | `article_source`,`media_quote_pool` | 球界全体 | active | 3681 | mixed sports / baseball |
| スポニチ野球記者X | `rsshub.../twitter/user/SponichiYakyu` | `social_news` | `article_source`,`media_quote_pool` | 球界全体 | active | 3840 | baseball-wide |
| サンスポ巨人X | `rsshub.../twitter/user/Sanspo_Giants` | `social_news` | `article_source`,`media_quote_pool` | 巨人専門(番記者) | active | 3628 | high-volume |
| スポーツ報知X | `rsshub.../twitter/user/SportsHochi` | `social_news` | `media_quote_only` | 球界全体 | active | 3795 | quote-only |
| 報知野球X | `rsshub.../twitter/user/hochi_baseball` | `social_news` | `media_quote_only` | 球界全体 | active | 3840 | quote-only |
| NPB公式X | `rsshub.../twitter/user/npb` | `social_news` | `media_quote_only` | 球界全体(公式) | active | 3840 | quote-only |
| 日刊スポーツ 巨人 | `nikkansports.com/.../giants.xml` | `news` | n/a | 巨人専門(tag feed) | active | 1920 | 10件/run で安定 |
| ベースボールキング | `baseballking.jp/feed` | `news` | n/a | 球界全体 | active | 3456 | wide-source |
| Full-Count 巨人 | `full-count.jp/tag/yomiuri-giants/feed/` | `news` | n/a | 巨人専門(tag feed) | active | 0 | **activeだが当日 zero-return** |
| スポーツ報知 巨人 | `hochi.news/rss/giants.xml` | `news` | n/a | 巨人専門 | active | 0 | **activeだが当日 zero-return** |

### 1-2. Step 1 interpretation

- **巨人専門 source**
  - `巨人公式X`
  - `読売ジャイアンツX`
  - `スポーツ報知巨人班X`
  - `サンスポ巨人X`
  - `日刊スポーツ 巨人`
  - `Full-Count 巨人`
  - `スポーツ報知 巨人`
- **球界全体 source**
  - `日刊スポーツX`
  - `スポニチ野球記者X`
  - `スポーツ報知X`
  - `報知野球X`
  - `NPB公式X`
  - `ベースボールキング`

### 1-3. Step 1 finding

- 当日 source 実績で見ると、**active config なのに 0 件だったのは `Full-Count 巨人` と `スポーツ報知 巨人`**。
- 特に `スポーツ報知 巨人` は、288 既存監査でも「error page 継続 / fallback なし」とされており、**source add より先に recovery 優先**の根拠になる。

## Step 2. 今日拾えなかった重要巨人ニュース example

### 2-1. Representative missed samples

下表は「5/3 に source では hit したが、新規 draft / publish に落ちなかったもの」か、「repo-local 288 audit で source gap が確定しているもの」に限定した。

| sample | source | evidence | WP outcome | primary bucket |
|---|---|---|---|---|
| 堀田賢慎 1軍合流 / NNN東京ドーム記事 | NNN + 報知web | `doc/waiting/288-INGEST-source-coverage-expansion.md` に `NO (報知 RSS error + NNN 未登録)` と明記 | 当日 source coverage gap 扱い | A+B |
| 山崎伊織 2球緊急降板 | スポーツ報知巨人班X / 報知系 | 21:21-21:33 JST の `rss_fetcher_flow_summary.comment_required_sample_titles` に `【巨人】山崎伊織が２球でファームリーグ緊急降板...`。関連 follow-up は `pregame_started_skip` | sampled variants で新規 post 化せず | D |
| 泉口友汰 5/4 1軍合流見込み | 日刊スポーツ系 | 21:21-21:33 JST の `comment_required_sample_titles` に `【巨人】泉口友汰が４日ヤクルト戦から１軍合流へ...` | sampled variant は新規 post 化せず | D |
| 橋上コーチ「まだです」(泉口/リチャード) | 日刊スポーツ | 21:31 JST `HIT` -> `title_template_selected` -> `article_skipped_post_gen_validate` (`close_marker`) | draft/publish なし | D |
| 5/4予告先発 戸郷翔征 vs 奥川恭伸 | スポーツ報知巨人班X | 21:30-21:32 JST `HIT` -> `draft_only_thin_source_allowed` -> `article_skipped_post_gen_validate` (`close_marker`) | draft/publish なし | D |
| 5/3予告先発 巨人 vs 阪神 | サンスポ巨人X | 00:00-00:35 JST 複数 run で `HIT` -> `pregame_started_skip` | draft/publish なし | D |
| 阿部監督「大竹に脱帽」 | 日刊スポーツ 巨人 | 21:26-21:33 JST `HIT` -> `article_skipped_post_gen_validate` (`postgame_strict_review`, `required_facts_missing:opponent_score`) | draft/publish なし | D |
| 雨天コールド完封負け 阿部監督 | 日刊スポーツ 巨人 | 21:31-21:33 JST `article_skipped_post_gen_validate` (`required_facts_missing:giants_score, opponent_score`) | draft/publish なし | D |
| 杉内投手チーフコーチ「球自体は本当によかった」 | 報知系 | 11:06-12:33 JST `history_duplicate_sample_titles` に `【巨人】井上温大、力投８Ｋも今季３敗目 杉内投手チーフコーチ...` | 新規 post は作られず duplicate 側へ | E |

### 2-2. Important non-miss note

- `堀田賢慎` については、「公示」記事は **拾えている**。
  - 06:10 JST `【3日の公示】阪神は井坪陽生、巨人は堀田賢慎を登録...` で `draft post_id=64361` を確認。
  - つまり **「堀田テーマ全体がゼロ」ではなく、特定記事(報知/NNN版)が落ちた**。

### 2-3. Step 2 finding

- 今日の miss は「source に無かった」より、**source で hit した後に `comment_required` / `pregame_started` / `post_gen_validate(close_marker or strict_review)` で落ちたものが多い**。
- 一方で **NNN 未登録 + `スポーツ報知 巨人` zero-return** のような純 source gap も存在する。

## Step 3. 拾えなかった理由 分類 (A-F)

### 3-1. A-F mapping

| bucket | meaning | 5/3 representative status |
|---|---|---|
| A | source 未登録 | **あり**。NNN / スポニチWeb / サンスポWeb / 読売オンライン / 東スポ巨人 は mainline 未登録 |
| B | RSS error / timeout / zero-return | **あり**。`スポーツ報知 巨人` は active config のまま 5/3 total 0 |
| C | keyword filter | **強い代表例は未確認**。重要 miss の主因には見えない |
| D | post_gen_validate / game-state gate / comment_required | **主因**。山崎、泉口、橋上、予告先発、阿部監督記事がここに集中 |
| E | duplicate / history | **あり**。杉内コーチ記事、山崎 follow-up、泉口 follow-up の一部 |
| F | subtype misclassify | **副次的にあり**。`泉口1軍合流` が `首脳陣/manager` に寄り、`堀田登録/又木抹消` が game-state に巻き込まれた形跡 |

### 3-2. Step 3 conclusion

- 代表 sample 9本の primary cause はおおむね以下。
  - `A+B`: 1本
  - `D`: 7本
  - `E`: 1本
- よって user 仮説「そもそも巨人ニュースの拾い方が弱い」は **一部当たり**だが、**当日 5/3 の dominant issue は source coverage より downstream gate** だった。

## Step 4. 追加候補 source 評価

`RSS 有無` は **repo-local evidence のみ**。live web fetch 禁止のため、repo 外の最新公開 feed の有無は断定しない。

| candidate | current state | RSS 有無 (repo-local evidence) | scraper 要否 | Gemini / article増見込み | mail増見込み | duplicate risk | rollback |
|---|---|---|---|---|---|---|---|
| NNN | 未登録 | **未確認**。288 doc は `news.ntv.co.jp .../feed` 探索候補のみ | RSS が無ければ要 | `+0〜3/day` | `+0〜3/day` | medium | config row remove + image rebuild/redeploy |
| スポニチWeb | web未登録。`スポニチ野球記者X` は active | **未確認** | RSS が無ければ要 | `+1〜4/day` | `+1〜4/day` | high | 同上 |
| サンスポWeb | web未登録。`サンスポ巨人X` は active | **未確認** | RSS が無ければ要 | `+1〜3/day` | `+1〜3/day` | high | 同上 |
| 巨人公式 | **official X は既に active** (`巨人公式X`,`読売ジャイアンツX`) | X mirror は **あり**。official web RSS は repo 未確認。別候補の official YouTube RSS は 288 doc に存在 | Xなら不要、webは未確定、YouTube RSSなら不要 | `+0〜2/day` | `+0〜2/day` | medium-high | 同上 |
| NPB公式 | **NPB公式X は既に active(quote-only)** | X mirror は **あり**。official web RSS は repo 未確認 | Xなら不要、webは未確定 | `+0〜2/day` | `+0〜2/day` | medium | 同上 |
| 読売オンライン | 未登録。`source_trust.py` は `yomiuri.co.jp` family 既知 | **未確認** | RSS が無ければ要 | `+0〜3/day` | `+0〜3/day` | medium-high | 同上 |
| 東スポ巨人 | 未登録。`src/x_api_client.py` に `from:tospo_giants` legacy seed あり | X mirror なら構造上は可能だが repo mainline未配線。web RSS は **未確認** | Xなら不要、webは高確率で要 | `+1〜3/day` | `+1〜3/day` | high | 同上 |

### 4-2. Candidate ranking by implementation certainty

- **確度が高い既存系**
  - `巨人公式X`
  - `読売ジャイアンツX`
  - `NPB公式X`
  - これらはすでに active なので、「追加候補」ではなく **現行 source の扱い見直し対象**。
- **low-certainty new web candidates**
  - `NNN`
  - `スポニチWeb`
  - `サンスポWeb`
  - `読売オンライン`
  - repo-local だけでは official RSS existence が確定していない。
- **higher-burden candidates**
  - `東スポ巨人`
  - duplicate / policy / trust-family 補強が重い。

## Step 5. 今夜すぐ足せるもの / 後日設計

### 5-1. 今夜すぐ足せるもの

- **new source としては 0 件**
  - 理由: user 禁則で live web fetch をしていないため、候補 source の official RSS existence を repo-local evidence だけで確証できない。
  - よって `config 1行追加 + 既存 fetcher で即 mainline` と断定できる候補は本 audit では出せない。

### 5-2. 今夜すぐ効くが、source add ではないもの

- **`スポーツ報知 巨人` RSS recovery / fallback**
  - new source add ではなく **既存 active source の復旧**。
  - 5/3 は total 0 のため、source coverage 改善インパクトは new source add より大きい可能性が高い。

### 5-3. 後日設計

- **official RSS existence 確認後に low-friction になり得る**
  - `NNN`
  - `スポニチWeb`
  - `サンスポWeb`
  - `読売オンライン`
- **policy / duplicate / trust-family 設計が必要**
  - `東スポ巨人`
  - `巨人公式` の web/YouTube 拡張
  - `NPB公式` の web拡張

### 5-4. Priority note

- 288-INGEST の観点では、**「new source add」より `スポーツ報知 巨人` dead feed 修理 + downstream gateの D/F 圧縮**の方が 5/3 coverage loss に直結している。

## Step 6. user OK が必要な live 変更一覧

### 6-1. Common approvals needed for any new source add

- `config/rss_sources.json` 編集 OK
- fetcher image rebuild / Cloud Run deploy OK
- Gemini budget review OK
- mail volume cap review OK
- source rollback 手順確認 OK

### 6-2. Usually not required for simple source add

- **Scheduler 変更は通常不要**
  - 現行 `POST /run` scheduler が source list 全体を舐めるため、simple source add は既存 schedule に乗る。
- **env 変更も通常不要**
  - ただし source kill-switch flag を別途導入したいなら env review が追加で必要。

### 6-3. Per-candidate OK/effect matrix

| candidate | user OK needed | expected effect if enabled |
|---|---|---|
| NNN | config edit + rebuild/deploy + Gemini/mail review | `+0〜3/day` candidates。source gap補完の価値はあるが RSS existence 未確認 |
| スポニチWeb | 同上 | `+1〜4/day`。ただし `スポニチ野球記者X` と高重複 |
| サンスポWeb | 同上 | `+1〜3/day`。ただし `サンスポ巨人X` と高重複 |
| 巨人公式(web/YouTube) | 同上 | `+0〜2/day`。official coverage 強化だが既存 official X と重なる |
| NPB公式(web) | 同上 | `+0〜2/day`。quote-only source の article化候補 |
| 読売オンライン | 同上 | `+0〜3/day`。読売系 coverage 補完、duplicate は中高 |
| 東スポ巨人 | 同上 + policy/duplicate review を強めに | `+1〜3/day`。coverage は増えるが noise/dup も増えやすい |

## Audit Conclusion

- 5/3 の source coverage audit だけを見ると、**dominant loss は D(`comment_required` / `pregame_started` / `post_gen_validate`)**。
- ただし **A+B も実在**しており、最優先の source-side corrective action は **`スポーツ報知 巨人` の dead feed 復旧**。
- new source add を次にやるなら、**live web fetch で official RSS existence を確定してから `NNN / スポニチWeb / サンスポWeb / 読売オンライン` を比較**するのが最短。
