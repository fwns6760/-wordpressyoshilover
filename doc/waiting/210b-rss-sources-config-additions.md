# 210b RSS source config additions(repo-only audit)

## meta

- number: 210b
- type: config / rss source audit
- status: REVIEW_NEEDED
- priority: P0.5
- lane: Codex
- created: 2026-04-27
- parent: 210-primary-source-expansion-plan

## background

210a / 210c により、`giants_official` / `npb_official` / `sponichi` / `sanspo` / `daily` / `yomiuri_online` / `yahoo_news_aggregator` の 7 family は downstream 側で認識可能になった。

本便 210b の目的は、`config/rss_sources.json` に **確実に存在する公式 RSS feed** だけを追加することだった。ただし本便では live web fetch を行わず、repo 内の既存 config / doc / test / 実装コードに出てくる URL だけを根拠に判断する。

## repo-only evidence

### 既存 config に入っている news feed

- `https://www.nikkansports.com/rss/baseball/professional/atom/giants.xml`
- `https://hochi.news/rss/giants.xml`
- `https://baseballking.jp/feed`
- `https://full-count.jp/tag/yomiuri-giants/feed/`

### 7 family について repo 内で確認できたこと

- `src/source_trust.py` / `src/source_attribution_validator.py` / `tests/test_source_attribution_validator.py` には、7 family の domain / article URL recognition は追加済み。
- ただし repo 内で **RSS feed URL として明示的に確認できた** のは、上記既存 config の `nikkansports` / `hochi` のみ。
- `giants.jp` / `npb.jp` / `sponichi.co.jp` / `sanspo.com` / `daily.co.jp` / `yomiuri.co.jp` / `news.yahoo.co.jp` については、記事 URL や通常 page URL の根拠はあるが、repo 内に feed URL の確証はない。

## family verdict

| family | current state | repo-only RSS evidence | decision | notes |
|---|---|---|---|---|
| `giants_official` | config に official X のみ | なし | 210d / 後続 verify 待ち | `giants.jp` 記事 URL は tests にあるが、公式 RSS feed URL は repo に出てこない |
| `npb_official` | config に official X のみ | なし | 210d / 後続 verify 待ち | `npb.jp` 記事 / 試合 URL は多くあるが、RSS feed URL は repo にない |
| `sponichi` | config に X / web RSS なし | なし | 210d / 後続 verify 待ち | article URL recognition はあるが feed URL の根拠なし |
| `sanspo` | config に X / web RSS なし | なし | 210d / 後続 verify 待ち | article URL recognition はあるが feed URL の根拠なし |
| `daily` | config に web RSS なし | なし | 210d / 後続 verify 待ち | family 認識のみ、feed URL の根拠なし |
| `yomiuri_online` | config に web RSS なし | なし | 210d / 後続 verify 待ち | article URL recognition はあるが feed URL の根拠なし |
| `yahoo_news_aggregator` | config に RSS なし | なし | 210d / 210e policy verify 待ち | 210 plan 上、Yahoo 本体は配信元 family 優先で扱う前提。直接 RSS 追加は見送り |

## classification summary

### 既設

- `nikkansports` giant feed は既設
- `hochi` giant feed は既設

### 追加

- なし

### 210d 待ち

- `giants_official`
- `npb_official`
- `sponichi`
- `sanspo`
- `daily`
- `yomiuri_online`
- `yahoo_news_aggregator`

## config result

- `config/rss_sources.json` の変更は **なし**
- 理由: 7 family のうち、repo 内証拠だけで「確実に存在する公式 RSS feed URL」と言い切れるものがなかったため
- 既存 RSS feed URL の削除 / 変更も **なし**

## non-goals

- live web fetch / live RSS existence check
- web scraping
- `src/` / `tests/` の変更
- Yahoo 集約面の policy 変更

## verification notes

- 本便の判断は repo-only evidence に限定した
- `config/rss_sources.json` は read-only 確認のみ
- 210d 以降で live verify または scraper 方針が固まるまで、7 family の新規 config 追加は行わない
