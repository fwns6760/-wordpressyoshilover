# 210 primary source expansion plan(doc-only spec)

## meta

- number: 210
- type: spec / plan
- status: REVIEW_NEEDED
- priority: P0.5
- lane: Claude(spec)/ Codex(将来実装)
- created: 2026-04-27
- parent: 209-source-coverage-and-topic-sensor-audit

## background

209 audit(`7b1bb7d`)で、現行 main ingress は `social_news=9` / `news=4` と **X 偏重**であり、`giants.jp` と `npb.jp` の web 一次 source が main ingress に入っていないことが確認された。加えて、スポニチ / サンスポ / デイリー / 読売オンライン / Yahoo 配信元 family の web coverage 不足、`src/source_trust.py` と `config/rss_sources.json` と editor whitelist / attribution validator の family 定義 drift 疑い、`Full-Count` / `BaseballKing` の trust 薄さが残っている。

本票は **実装はまだしない**。primary / semi-primary web source を main ingress に広げるための候補整理、重複・デグレ対策、将来の sub-ticket 分解だけを行う doc-only plan である。

## 追加候補 source list

| source | 種別 | URL or feed | trust 想定 | 重複 risk | 実装 priority |
|---|---|---|---|---|---|
| giants.jp(球団公式) | web 一次 | https://www.giants.jp/ | high | low | P0 |
| npb.jp(NPB 公式) | web 一次 | https://npb.jp/ | high | low | P1 |
| スポニチ web | web 準一次 | https://www.sponichi.co.jp/ | mid | mid(SNS 既存) | P1 |
| サンスポ web | web 準一次 | https://www.sanspo.com/ | mid | mid | P1 |
| デイリー web | web 準一次 | https://www.daily.co.jp/ | mid | low | P2 |
| 読売オンライン | web 準一次 | https://www.yomiuri.co.jp/ | mid-high | low | P1 |
| Yahoo 配信元 family | web 集約 | https://news.yahoo.co.jp/ | mid | high(各社配信、dup 多) | P2 |

### 取得方法メモ

| source | 取得方法方針 | 推奨頻度 |
|---|---|---|
| giants.jp(球団公式) | 公式 RSS feed があれば feed URL を優先。無ければ HTML scrape を候補化し、ToS / robots.txt 確認後に narrow 実装 | `*/15` |
| npb.jp(NPB 公式) | 公式 RSS feed があれば feed URL を優先。無ければ HTML scrape を候補化し、規約順守で見出し / URL / 公開時刻のみ取得 | `*/15` |
| スポニチ web | RSS feed があれば feed URL を優先。無ければ HTML scrape を候補化し、本文取得は行わない | `*/15` |
| サンスポ web | RSS feed があれば feed URL を優先。無ければ HTML scrape を候補化し、見出し / URL / 日時だけ取得 | `*/15` |
| デイリー web | RSS feed があれば feed URL を優先。無ければ HTML scrape を候補化し、低頻度で運用 | `*/30` |
| 読売オンライン | RSS feed があれば feed URL を優先。無ければ HTML scrape を候補化し、読売 family として扱う | `*/15` |
| Yahoo 配信元 family | Yahoo 本体 feed / page を直接 main fact source にせず、可能なら配信元 source を first-class 扱い。やむを得ず集約面を使う場合は配信元 attribution を必須化 | `*/30` |

## 重複・デグレ対策

1. `rss_history.json` の `source_url` / `source_id` を使い、既処理 URL を source family をまたいで dedup する。
2. `src/source_trust.py` の family 定義を拡張し、新 source を既存 family(`giants`, `npb`, `hochi`, `nikkansports`, `sanspo`, `sponichi`, `daily`, `yomiuri`, `yahoo-distributor` など)へ正規化する。
3. editor whitelist と attribution validator を **同 commit で同期更新**し、ingress 追加後に editor / validator だけ reject する drift を防ぐ。
4. `title_key` / `game_key` で同日同試合の類似記事を束ね、135 freshness gate の duplicate / stale 判定と整合するようにする。
5. Yahoo 配信元は special handling とし、`Yahoo URL` と `配信元 URL` と `配信元 family` を切り分けて、Yahoo 本体重複と各社再配信重複を別々に抑止する。

## 実装手順(将来 ticket 化)

### 候補 sub-ticket

- `210a`: `src/source_trust.py` の family 定義拡張(spec -> impl)
- `210b`: `config/rss_sources.json` への新 feed 追加
- `210c`: editor whitelist + attribution validator の同期更新
- `210d`: web scraper 実装(API なし source 用)
- `210e`: 実 ingestion verify + duplicate 抑止 verify

### 実装順の考え方

1. まず `210a` で family 定義を先に整える。trust / family が曖昧なまま feed を足すと downstream drift を増やす。
2. 次に `210b` で RSS / feed ベースで取れる source を追加する。`giants.jp` を最優先、続いて `npb.jp` / `読売オンライン` / `スポニチ` / `サンスポ` を検討する。
3. `210c` で editor whitelist / attribution validator を同時同期し、source family の受け口を揃える。
4. feed が無い source だけ `210d` で HTML scrape narrow 実装を行う。本文取得はせず、見出し / URL / 日時のみ扱う。
5. 最後に `210e` で実 ingestion の run summary、duplicate 抑止、freshness gate 整合、Yahoo special handling の効きを検証する。

各 sub-ticket は **別 ticket 番号で起票**し、`210a` / `210b` などの表記は本 doc 内の便宜名に留める。

## acceptance(計画段階)

1. 7 source 候補が listed され、各 source に priority / trust 想定 / duplicate risk が付いている。
2. 重複・デグレ対策 5 項目が documented されている。
3. 実装段階の 5 sub-ticket outline が documented されている。

## non-goals

- **本便では実装しない。**
- 実 RSS feed 追加 / `config/rss_sources.json` 編集
- `src/source_trust.py` 編集
- web scraper 実装
- editor whitelist 編集
- WP REST 検証
- live deploy
- SNS / 5ch / YouTube 等 sensor 拡張(別 ticket、209 で reject 維持)

## リスクと判断保留

- スポニチ / サンスポ / デイリーの web ToS 確認が必要。`robots.txt` と API / 利用規約確認前に scrape 実装へ進まない。
- Yahoo 配信元の重複率は実測が必要。実 ingestion を流して dedup 効果を verify しないと想定だけでは足りない。
- 公式 RSS の有無確認が必要。feed があれば実装は単純化でき、HTML scrape の必要性が下がる。
- `Full-Count` / `BaseballKing` の trust 薄さは別 narrow ticket で扱う。本票では source 追加候補の整理に留める。
- `180 SNS topic intake lane separation` と整合し、SNS-origin 記事と primary web source の混在で publish gate を曖昧にしない。

## user 判断ポイント

- どの source から実装着手するか。推奨は `P0 = giants.jp` から開始。
- 取得頻度の方針を `*/15` 基本にするか、P2 source は `*/30` に落とすか。
- web scraping を許容するか。ToS / robots.txt / 実装コストを見て、feed 優先で進めるか判断が必要。

## next action

- user 確認後、最初の sub-ticket(例: source trust 拡張 spec)を別番号で起票する。
- 実装着手前に `config` / `src` / `tests` の baseline と write scope を再確認する。
- 実装段階は本便とは別の Codex 便で進める。
