# 368-QA Xポスト＋引用記事の重複と title 劣化を止める恒久対応

## meta

- status: LIVE_DEPLOYED_OBSERVE
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/37
- triggers: published post `68628` / draft `68633` / published post `68619`

## 問題

`68628` と `68633` は同じ報知記事を、X ポスト側と Web 記事側で二重に作っていた。
残すべき形は X ポストを主素材にし、その直後に引用記事（本文抜粋）を置く形である。

`68628` と `68619` は source URL が別なので重複ではないが、関連記事ブロックが同カテゴリや選手名だけで混線し、読者には関係ない記事が混ざって見えた。
title も `関連発言` 型に劣化し、記事の核が分かりにくかった。

## 原因

- `same_family_x_web_dedup` は default OFF で、本番では X+Web の二重 draft を止められていなかった。
- 既存の同 family X+Web 統合は Web 記事を親にし、X 投稿を消費する設計だったため、ユーザーが求める「X ポスト + 引用記事」構成と逆だった。
- 関連記事検索は X 記事でも同カテゴリ・同選手名だけで候補を出し、引用句や具体イベントの一致を要求していなかった。
- X 側 title が `関連発言` 型に劣化しても、Web 側の具体 title / summary を X 側へ寄せる仕組みがなかった。

## 方針

- 記憶から再構成しない。
- silent skip にしない。
- 自己評価 OK で終わらせない。
- 同じ媒体 family の X+Web が同じ選手・同じ出来事なら、X 側を残し Web-only 側を消費する。
- Web 側の title / summary / history_url を X 側へ引き継ぎ、title 劣化と後続重複を止める。
- X 記事の関連記事は、引用句や具体イベント（猛打賞、ブルペン等）の literal overlap がある時だけ表示する。
- 既存 post は status を確認してから、公開済みは公開のまま title/content だけ補正する。

## 実装スコープ

触ってよい:

- `src/rss_fetcher.py`
- `tests/test_related_posts.py`
- `tests/test_rss_fetcher_same_family_x_web_dedup.py`
- 本 ticket
- `doc/README.md`
- `doc/active/assignments.md`

触らない:

- Scheduler
- Cloud Run env
- Secrets
- X / SNS 投稿
- mail 条件
- source 追加
- unrelated front / logs / generated artifacts

## 受け入れ条件

- `68628` は公開のまま、X ポストと本文抜粋が残り、title が具体化され、関連記事混線が消える。
- `68619` は別記事として公開のまま、X ポストと本文抜粋が残り、title が具体化され、関連記事混線が消える。
- `68633` は重複 draft として公開候補から外れる。
- future X+Web 同 family 同 event は X 側を残し、Web-only 側は同 fire 内で消費される。
- X 記事の関連記事は同選手名だけでは出ず、literal detail overlap が必要になる。
- `py_compile` / `compileall` / AST parse / targeted pytest が PASS する。
- Scheduler / env / Secret / X / SNS / mail 条件は変更しない。

## 実装結果

- WP 既存 post:
  - `68628`: status=publish を確認後、title を `マルティネス「ブルペンは家族」巨人リリーフ陣の“家族構成”` へ更新。X embed と本文抜粋を保持し、関連記事ブロックを削除。
  - `68619`: status=publish を確認後、title を `浦田俊輔「いとこが見に来ていたので打ってやろうと」今季3度目の猛打賞` へ更新。X embed と本文抜粋を保持し、関連記事ブロックを削除。
  - `68633`: status=draft を確認後、同一報知 URL の重複 draft として trash。
- `src/rss_fetcher.py`:
  - X 記事の関連記事選定に `_social_related_has_topic_detail_overlap` を追加。
  - same-family X+Web dedup を default ON にし、X 側を親、Web 側を consumed に変更。
  - Web title / summary / history_urls を X 側へ投影し、`関連発言` 型 title 劣化と後続重複を抑止。
- tests:
  - `tests/test_related_posts.py` に X 記事の literal detail overlap 必須 regression を追加。
  - `tests/test_rss_fetcher_same_family_x_web_dedup.py` に X 親 / Web consumed regression と quote event regression を追加。

## 検証

実行済み:

- WP verify: `68628` publish / X embed true / source excerpt true / related posts false / schema headline title一致
- WP verify: `68619` publish / X embed true / source excerpt true / related posts false / schema headline title一致
- WP verify: `68633` trash
- `python3 -m pytest tests/test_related_posts.py tests/test_rss_fetcher_same_family_x_web_dedup.py -q` -> 20 passed / 4 warnings
- `python3 -m py_compile src/rss_fetcher.py tests/test_related_posts.py tests/test_rss_fetcher_same_family_x_web_dedup.py`
- `python3 -m compileall -q src/rss_fetcher.py tests/test_related_posts.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_build_news_block.py tests/test_media_xpost_selector.py`
- AST parse -> `AST_OK src/rss_fetcher.py,tests/test_related_posts.py,tests/test_rss_fetcher_same_family_x_web_dedup.py`
- `python3 -m pytest tests/test_related_posts.py tests/test_rss_fetcher_same_family_x_web_dedup.py tests/test_build_news_block.py tests/test_media_xpost_selector.py -q` -> 103 passed / 4 warnings
- `git diff --check -- src/rss_fetcher.py tests/test_related_posts.py tests/test_rss_fetcher_same_family_x_web_dedup.py doc/README.md doc/active/assignments.md doc/active/368-QA-x-web-post-quote-dedupe-title.md`
- Cloud Run env read-only check: `ENABLE_SAME_FAMILY_X_WEB_DEDUP` explicit overrideなし（code default ON が有効）
- commit `8b0b420` (`368: keep x quote articles and dedupe web copies`)
- `gcloud builds submit --project baseballsite --region asia-northeast1 --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:368-x-web-8b0b420 .` -> Cloud Build `26d505cd-8fe3-43cd-a99b-aceb93cf7766` SUCCESS
- image digest `sha256:d8414f326603d22caa514d10c5b12c63dc849e29f6b5e7cd70d206112d685596`
- `gcloud run deploy yoshilover-fetcher --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:368-x-web-8b0b420 --project baseballsite --region asia-northeast1 --quiet` -> revision `yoshilover-fetcher-00405-t9l`, traffic 100%
- `curl -sS https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/health` -> OK
- Cloud Run log: revision `yoshilover-fetcher-00405-t9l` Ready condition true、startup TCP probe succeeded
- GitHub Issue evidence comment: https://github.com/fwns6760/-wordpressyoshilover/issues/37#issuecomment-4466671286

未実行:

- natural fire / log evidence

## 未完了

- natural fire / log evidence
- GitHub Issue #37 close
