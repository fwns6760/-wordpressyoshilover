# 399 — manual_intake の OG meta 抽出を React Helmet HTML に対応

## meta

- id: 399
- type: INGEST / narrow-fix
- priority: P2
- status: READY_FOR_IMPL
- owner: Claude Code
- lane: dev
- created: 2026-05-20
- ready_for: impl
- blocked_by: none
- doc_path: `doc/active/399-INGEST-manual-intake-react-helmet-meta-extract.md`

## 背景

manual-intake-service で `https://news.ntv.co.jp/category/sports/<id>` 形式の日テレ NEWS 記事 URL を `dry-run` / `draft` / `publish` どのモードでも処理しようとすると、`{"ok": false, "reason": "missing_title_or_summary"}` で 400 / EXIT 12 に落ちる。title と summary を operator が手動入力すれば通る(`title_override` / `summary_override` 経路)。

URL: `https://manual-intake-service-487178857517.asia-northeast1.run.app/`
再現 URL: `https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767`

## 原因

`src/tools/manual_intake.py` L187-198 の `_META_PATTERNS` 正規表現は `<meta\s+property=` / `<meta\s+name=` / `<meta\s+content=` のいずれかで始まる meta tag だけを想定している。

```python
_META_PATTERNS: tuple[tuple[str, str], ...] = (
    (r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', "title"),
    (r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']', "title"),
    (r'<meta\s+name=["\']twitter:title["\']\s+content=["\']([^"\']+)["\']', "title"),
    ...
)
```

NTV (news.ntv.co.jp) は React Helmet 出力で、全 meta tag の第一属性として `data-react-helmet="true"` が入る:

```html
<meta data-react-helmet="true" property="og:title" content="ナショナルズのウッドが激走で..."/>
<meta data-react-helmet="true" property="og:description" content="◇MLB ナショナルズ9-6メッツ..."/>
<meta data-react-helmet="true" property="og:image" content="https://news.ntv.co.jp/gimage/.../...jpg?w=1200"/>
<meta data-react-helmet="true" name="twitter:title" content="..."/>
<title data-react-helmet="true">ナショナルズのウッドが激走で...｜日テレNEWS NNN</title>
```

`<meta\s+property=` は `<meta\s+data-react-helmet=` にマッチしないので og:title / og:description / og:image / twitter:* すべて空。fallback の `<title>([^<]+)</title>` (L399) も属性付き `<title data-react-helmet="true">` には不発。結果 `_parse_og_meta` が `{"title": "", "summary": "", "image": ""}` を返し、L4494-4496 で `missing_title_or_summary` 確定。

再現 evidence(2026-05-20 JST):

```
$ curl -sS "https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767" -o /tmp/ntv.html
$ python3 -c "from src.tools.manual_intake import _parse_og_meta; \
  print(_parse_og_meta(open('/tmp/ntv.html').read()))"
{'title': '', 'summary': '', 'image': ''}

$ curl -sS -X POST "https://manual-intake-service-.../manual-intake" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://news.ntv.co.jp/.../5b63a75...","mode":"dry-run"}'
HTTP 400 — reason=missing_title_or_summary
```

なお NTV は `src/tag_page_scraper.py:1219`(巨人 tag page scraper)と `src/source_trust.py:121` の trust domain に登録済の主要 source。manual-intake 経路だけが拾えていない。

## 影響範囲

- 確認済み: news.ntv.co.jp 全記事
- 同型 React Helmet を使う他 source(調査必要、`data-react-helmet=` を含む meta を出す媒体は他にもある可能性)
- 影響しないこと:
  - 自動 RSS / tag scrape path(別経路、各 source の専用 extractor を経由)
  - 既存の plain HTML source(報知 / スポニチ / デイリー等、回帰なしを担保)

## ゴール

`_parse_og_meta` を属性順非依存にし、React Helmet 等の追加属性が meta / title tag の先頭に挟まる HTML でも og:title / og:description / og:image / `<title>` を抽出する。既存の plain HTML パターンの挙動は変えない。

## 実装(narrow fix)

1. `src/tools/manual_intake.py` L187-198 の `_META_PATTERNS` を attribute 順非依存に書き換える。各 tuple の regex を以下の形に変更:

```python
_META_PATTERNS: tuple[tuple[str, str], ...] = (
    (r'<meta\b[^>]*\sproperty=["\']og:title["\'][^>]*\scontent=["\']([^"\']+)["\']', "title"),
    (r'<meta\b[^>]*\scontent=["\']([^"\']+)["\'][^>]*\sproperty=["\']og:title["\']', "title"),
    (r'<meta\b[^>]*\sname=["\']twitter:title["\'][^>]*\scontent=["\']([^"\']+)["\']', "title"),
    (r'<meta\b[^>]*\sproperty=["\']og:description["\'][^>]*\scontent=["\']([^"\']+)["\']', "summary"),
    (r'<meta\b[^>]*\scontent=["\']([^"\']+)["\'][^>]*\sproperty=["\']og:description["\']', "summary"),
    (r'<meta\b[^>]*\sname=["\']description["\'][^>]*\scontent=["\']([^"\']+)["\']', "summary"),
    (r'<meta\b[^>]*\sname=["\']twitter:description["\'][^>]*\scontent=["\']([^"\']+)["\']', "summary"),
    (r'<meta\b[^>]*\sproperty=["\']og:image["\'][^>]*\scontent=["\']([^"\']+)["\']', "image"),
    (r'<meta\b[^>]*\scontent=["\']([^"\']+)["\'][^>]*\sproperty=["\']og:image["\']', "image"),
    (r'<meta\b[^>]*\sname=["\']twitter:image["\'][^>]*\scontent=["\']([^"\']+)["\']', "image"),
)
```

ポイント:
- `<meta\s+` → `<meta\b[^>]*\s`(`<meta` の後ろに任意属性を許容、ただし `>` を越えない)
- 各属性間 `\s+` → `[^>]*\s`(属性順自由 + 任意属性を許容)
- 二重引用符 / 単一引用符 / `IGNORECASE` の挙動は維持

2. `<title>` fallback (L398-401) を属性付き title tag にも対応:

```python
if not title:
    match = re.search(r"<title\b[^>]*>([^<]+)</title>", html_text, re.IGNORECASE)
    if match:
        title = html.unescape(match.group(1).strip())
```

## 不可触

- `_extract_context_matched_primary_og_meta`(別の context match 経路、本 fix の対象外)
- `_fetch_news_meta` 本体(HTTP 取得 / decode 部分は変えない)
- 自動 RSS / tag scrape path / 各 source 専用 extractor
- env / Secret / Scheduler / RUN_DRAFT_ONLY / WP 既存記事 / X / publish-notice / x-post-mail-lane / frontend
- `_META_PATTERNS` 以外の regex 配列
- 他 source(報知 / スポニチ / デイリー / Sports Hochi 等)の挙動

## tests

1. `tests/test_manual_intake.py` に新 case 追加(既存 file への append、新規 file は作らない):
   - `test_parse_og_meta_react_helmet_attribute_first`: `<meta data-react-helmet="true" property="og:title" content="..."/>` 形を入力し、title / summary / image が抽出されることを assert
   - `test_parse_og_meta_react_helmet_title_tag_with_attribute`: `<title data-react-helmet="true">...</title>` から fallback で title が拾えることを assert
   - `test_parse_og_meta_plain_html_regression`: 既存 plain HTML(属性 1 つ)で挙動不変
2. fixture HTML は実物の必要な 4 meta + title 5 行だけ inline(`/tmp/ntv_article.html` を repo に持ち込まない、size 800KB の生 HTML は不要)
3. `pytest tests/test_manual_intake.py -x -q` で green、既存 case の regression なし
4. `python -m py_compile src/tools/manual_intake.py`、`python -m compileall src/tools/manual_intake.py` で syntax error なし

## acceptance(本 ticket close 条件)

- pytest 上記 3 case + 既存 case 全 green
- 手動 verify: dry-run で NTV URL `https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767` を POST し、`{"ok": true, "title": "<extracted>", "category": "...", "subtype": "...", "validation_ok": true}` で 200 が返る(`missing_title_or_summary` が消える)
- 巨人関連 sample URL(報知 / スポニチ / デイリー / nikkansports / 等)で 1 件以上の dry-run が引き続き通り、回帰なし
- LIVE_DEPLOYED_OBSERVE: `cloudbuild_manual_intake_service.yaml` ビルド SUCCESS + `manual-intake-service` 新 revision 100% + `/health` OK
- env / Secret / Scheduler / RUN_DRAFT_ONLY / WP 既存記事 / X / publish-notice / x-post-mail-lane / frontend 全部不変

## 動作確認コマンド(deploy 後)

```bash
# 1. 失敗していた NTV URL — 成功するはず
curl -sS -X POST "https://manual-intake-service-487178857517.asia-northeast1.run.app/manual-intake" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767","mode":"dry-run"}'

# 2. 既存 source 回帰 — 引き続き通るはず
curl -sS -X POST "https://manual-intake-service-487178857517.asia-northeast1.run.app/manual-intake" \
  -H "Content-Type: application/json" \
  -d '{"url":"<報知 or スポニチの巨人記事 URL>","mode":"dry-run"}'

# 3. health
curl -sS "https://manual-intake-service-487178857517.asia-northeast1.run.app/health"
```

## 既知の関連

- `src/tag_page_scraper.py:1219` の NTV tag scraper は別経路で動いており、本 ticket と直接の関係なし(scraper 側は HTML を BeautifulSoup でパースしているなら本問題に当たらない、別途要検証)
- `src/source_trust.py:121` の trust domain には NTV 既登録、本 ticket で trust 設定は変えない
- `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08.md`(parity gap ticket)とは scope 別。あちらは marker gate / 装飾 enrichment 軸、本 ticket は meta 抽出 regex の narrow fix
