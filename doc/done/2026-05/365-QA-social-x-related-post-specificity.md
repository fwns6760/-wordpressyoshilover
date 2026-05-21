# 365-QA SNS記事の関連ポスト混線を止める恒久対応

## meta

- status: LIVE_DEPLOYED_OBSERVE
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/34
- trigger: published post `68489` mixed two unrelated Sakamoto X posts into one article

## 問題

`68489` は報知Xの「坂本勇人選手と田中将大投手がキャッチボール / 昆陽里タイガース」が主題だった。
しかし本文の「関連ポスト」に、同じ坂本勇人を含む別のX投稿も同列で入り、読者には2つの関係ないポストを混ぜた記事に見えた。

## 原因

`social_news` の2本目 media quote selection が、主に topic alias（選手名）一致で候補を通していた。
X投稿は短いため、選手名だけでは同一話題の根拠にならない。

## 方針

- AI 類似判定は使わない。
- 記憶から再構成しない。
- 選手名一致だけでは2本目のX投稿を許可しない。
- source tweet と候補 tweet の title / summary に、具体 detail token が literal に重なる場合だけ許可する。
- 具体 token 例: `キャッチボール`, `昆陽里`, `こやのさと`, `伊丹`, `合流`, `昇格`, `登録`, `抹消`, `スタメン`, `先発`, `サヨナラ`, `ホームラン`。
- 2本目を入れない場合は silent skip にせず、`skip_reason=topic_detail_mismatch` を出す。
- 自己評価OKにせず、`68489` 型 fixture test で固定する。

## 実装スコープ

触ってよい:

- `src/media_xpost_selector.py`
- `src/rss_fetcher.py`
- `tests/test_media_xpost_selector.py`
- 本 ticket
- `doc/README.md`
- `doc/active/assignments.md`

触らない:

- Scheduler
- Cloud Run env
- Secrets
- WP既存記事の自動修正 / 削除
- X / SNS投稿
- mail 条件
- source 追加

## 受け入れ条件

- 坂本勇人という名前だけが一致する別話題X投稿は「関連ポスト」に入らない。
- `キャッチボール` / `昆陽里` などの具体 detail が一致するX投稿は2本目として許可される。
- 拒否理由は `topic_detail_mismatch` として observability に残る。
- `68489` 型 fixture-backed test が PASS する。
- 既存の公示 / 監督コメント / social own source quote の回帰がない。
- Scheduler / env / Secret / WP既存記事 / X / SNS / mail 条件を変更しない。

## 実装結果

- `social_news` の secondary media quote に concrete detail overlap gate を追加。
- 選手名や source 名など generic fragment は detail 判定から除外。
- source tweet の `title` / `summary` を selector に渡すよう `rss_fetcher` の呼び出し payload を補強。
- 同一 detail がない場合は `topic_detail_mismatch` を返す。

## 検証

実行済み:

- `python3 -m py_compile src/media_xpost_selector.py src/rss_fetcher.py tests/test_media_xpost_selector.py`
- `python3 -m pytest tests/test_media_xpost_selector.py -q` -> 24 passed / 3 warnings
- `python3 -m compileall -q src/media_xpost_selector.py src/rss_fetcher.py tests/test_media_xpost_selector.py`
- AST parse -> `AST_OK src/media_xpost_selector.py,src/rss_fetcher.py,tests/test_media_xpost_selector.py`
- `python3 -m pytest tests/test_media_xpost_selector.py tests/test_build_news_block.py -q` -> 83 passed / 4 warnings
- `python3 -m pytest tests/test_rss_fetcher_duplicate_guard.py -q` -> 13 passed / 3 warnings
- `gcloud builds submit --project baseballsite --region asia-northeast1 --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:365-social-x-7440089 .` -> Cloud Build `a46132b5-d25a-4bf0-b44f-6bb92b39fbff` SUCCESS
- image digest `sha256:6161a8b640e53d2eb0312d38cfcf15ead2953ac6c4240659c531099465eb911b`
- `gcloud run deploy yoshilover-fetcher --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:365-social-x-7440089 --project baseballsite --region asia-northeast1 --quiet` -> revision `yoshilover-fetcher-00402-4vc`, traffic 100%
- `curl -sS https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/health` -> OK
- Cloud Run log: revision `yoshilover-fetcher-00402-4vc` startup probe succeeded, `/health` 200

## 未完了

- 自然 fire 後の `media_xpost_skipped` / `topic_detail_mismatch` または問題なく完走した evidence
- GitHub Issue #34 close
