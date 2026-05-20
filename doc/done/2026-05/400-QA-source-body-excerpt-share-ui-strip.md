# 400 — source body excerpt から share / SNS UI ボタン文字列を恒久 strip

## meta

- id: 400
- type: QA / narrow-fix
- priority: P1(本文以外の文字列が公開記事に混入)
- status: READY_FOR_IMPL
- owner: Claude Code
- lane: dev
- created: 2026-05-20
- ready_for: impl
- blocked_by: none
- doc_path: `doc/active/400-QA-source-body-excerpt-share-ui-strip.md`

## 背景

post 69888 (`https://yoshilover.com/69888`) で `nomotoke-source-excerpt__body` ブロックの先頭に share UI ボタン文字列が連続して並んでいた:

```html
<aside class="nomotoke-source-excerpt" id="toc-excerpt">
<p class="nomotoke-source-excerpt__label">📖 本文抜粋</p>
<blockquote class="nomotoke-source-excerpt__body">
<p>スポーツ</p>                          ← breadcrumb noise
<p>ナショナルズのウッドが激走で…マーク</p>  ← title 重複
<p>ポスト</p>                            ← X 投稿ボタン label
<p>送る</p>                              ← 送信ボタン label
<p>シェア</p>                            ← share ボタン label
<p>ブックマーク</p>                       ← bookmark ボタン label
<p>URLをコピー</p>                       ← copy URL ボタン label
<p>2026年5月20日 12:59</p>               ← (date は既存 _DATE_LINE_RE で剥がれる)
<p>ナショナルズのウッド選手が…(写真：AP/アフロ)</p>
<p>◇MLB ナショナルズ9-6メッツ(日本時間20日、ナショナルズ・パーク)</p>
... real body
</blockquote>
```

source URL: `https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767`

user 指摘「引用の部分に、ポスト、送る、シェア、ブックマークなど記事以外の情報がある」「恒久的に直して、日本テレビ以外でも」。

## 原因

`src/source_article_body_extractor.py` の `_BOILERPLATE_LINES` set (L204-219) には現状 `"通知ON" / "通知OFF" / "PR" / "広告" / "ホーム" / "野球" / "ニュース" / "RSS" / "プロ野球" / "拡大" / "続きを見る" / "野球スコア速報" / "編集者のオススメ記事" / "読売ジャイアンツ（巨人）"` の 14 件しか入っていない。

React-rendered ニュースサイト(NTV / `news.ntv.co.jp` が代表例)は記事 container 内に share UI を `<p>` / `<button>` 等の単独 sibling として emit するため、`_strip_html_to_plain` で line 分解した結果が 1 行 1 ラベル(`ポスト` / `送る` / `シェア` / `ブックマーク` / `URLをコピー`)になり、boilerplate set に当たらず本文として通過 → `📖 本文抜粋` ブロックに流入する。

NTV 固有問題ではない。同型 share UI を出す媒体(NHK / 朝日 / 産経 等 React / Next.js 系)全部に同じ穴がある。

## ゴール

`_BOILERPLATE_LINES` set に share / SNS UI / breadcrumb の Japanese label を追加し、`extract_article_body_excerpt` 経由 で生成される全本文抜粋から **どの媒体でも** share UI を恒久的に剥がす。本文の prose に substring として現れる場合(例: 「ポストシーズン」「メールマガジン」「シェアを伸ばす」)は **誤剥離しない**(boilerplate set は exact-line match なので false positive は構造的に起きない)。

## 実装(narrow fix)

`src/source_article_body_extractor.py` L204-219 の `_BOILERPLATE_LINES` set に以下の 23 ラベルを追加。set 追加のみ、ロジック改変なし:

```python
# Share / SNS UI button labels that React-rendered news sites
# (e.g. news.ntv.co.jp) emit as separate sibling <p>/<button>
# nodes inside the article container. Each label only ever
# appears alone on its own line in the chrome; real article
# prose never reduces to a single one of these words.
"スポーツ",
"ポスト",
"ツイート",
"送る",
"シェア",
"ブックマーク",
"コピー",
"URLをコピー",
"リンクをコピー",
"クリップボードにコピー",
"クリップボードにコピーしました",
"シェアする",
"保存",
"保存する",
"もっと見る",
"いいね",
"メール",
"印刷",
"LINEで送る",
"Facebookでシェア",
"Xでシェア",
"Twitterでシェア",
"はてブ",
"Pocket",
```

## 不可触

- `_strip_html_to_plain` / `_drop_leading_boilerplate` / `_is_noise_line` 等のロジック本体
- `_DATE_LINE_RE` / `_IMAGE_CAPTION_RE` 等の既存 regex
- substring match に切り替える(false positive が出る)
- 各 source 専用 selector(`_extract_hochi_*` 等の site-specific 経路は全部不変)
- env / Secret / Scheduler / RUN_DRAFT_ONLY / WP既存記事(post 69888 含む、retroactive cleanup はしない)/ X / publish-notice / x-post-mail-lane / frontend / 自動 RSS 経路 / tag scrape path
- 399 で書き換えた `_META_PATTERNS`

## tests

`tests/test_source_article_body_extractor.py` の `LeadingBoilerplateTests` 末尾に 2 case 追加:

1. `test_share_ui_buttons_dropped_from_react_helmet_body`: NTV 風 HTML(post 69888 を最小化)で `スポーツ / ポスト / 送る / シェア / ブックマーク / URLをコピー / 2026年5月20日` が全部剥がれ、本文(`ナショナルズ9-6メッツ` / `ウッド選手`)は維持されることを assert
2. `test_share_ui_substring_in_prose_preserved`: `ポストシーズン` / `メールマガジン` / `シェアを伸ばす` の prose 内 substring が誤剥離されないことを assert(false positive 防止 regression)

pytest 既存 44 case + 新 2 case = 46 case + 関連 manual_intake 93 case = 計 139 passed (regression 0)。

## acceptance(本 ticket close 条件)

- pytest `tests/test_source_article_body_extractor.py` + `tests/test_source_article_body_extractor_balanced_div.py` 46 passed
- broader pytest(manual_intake 含む)で regression 0
- `cloudbuild_manual_intake_service.yaml` ビルド SUCCESS + `manual-intake-service` 新 revision 100% + `/health` OK
- `cloudbuild_yoshilover_fetcher.yaml`(or equivalent)ビルド SUCCESS + `yoshilover-fetcher` 新 revision 100% + `/health` OK
- live verify: NTV URL を manual-intake に投げ直して新 draft を作り、本文抜粋に「ポスト / 送る / シェア / ブックマーク / URLをコピー / スポーツ」が 1 つも残らないことを目視確認
- env / Secret / Scheduler / RUN_DRAFT_ONLY / WP 既存記事 69888 含む / X / publish-notice / x-post-mail-lane / frontend / 自動 RSS / tag scrape path 全部不変

## 既存記事への影響

post 69888 は **既存 publish 状態のままで自動 cleanup されない**。本 fix は今後生成される draft / publish にのみ効く。69888 を直したい場合は user 判断で WP admin で本文編集 or 削除 + manual-intake で再生成。

## 動作確認コマンド(deploy 後)

```bash
# 1. NTV URL を manual-intake で再生成 (draft)
curl -sS -X POST "https://manual-intake-service-487178857517.asia-northeast1.run.app/manual-intake" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767","mode":"draft"}'

# 2. 出来た post_id の本文を取って share UI が残ってないか grep
curl -sS "https://yoshilover.com/wp-json/wp/v2/posts/<new_post_id>?context=view" \
  | python3 -c "import json,sys; c=json.load(sys.stdin)['content']['rendered']; \
    [print('LEAK:', t) for t in ['ポスト','送る','シェア','ブックマーク','URLをコピー','スポーツ'] \
     if f'<p>{t}</p>' in c]" \
  || echo "no_leak"
```

## 既知の関連 / 限界

- `323-QA-source-body-excerpt-clean-truncation.md`(waiting): 抜粋の途中切れ / UI 混入の親 ticket。400 はそのうち share UI 軸を切り出して narrow に着地させる位置づけ
- 同じ run 内で見える他 noise(photo credit `(写真：AP/アフロ)` の行 / breadcrumb `スポーツ` 直後の title 重複 / 等)は scope 別。再発するなら 401 / 402 として別途切り出し
- 各 source の本文 selector を磨く path(NTV 専用 selector を `_extract_*` に追加する等)は本 ticket では取らない。`_BOILERPLATE_LINES` 拡張で全媒体に効く方が ROI 高い
