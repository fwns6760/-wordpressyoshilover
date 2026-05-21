# 366-QA 引用記事（本文抜粋）の表示位置を正規化する恒久対応

## meta

- status: LIVE_DEPLOYED_OBSERVE
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/35
- triggers: post `68321` / draft `68622`

## 問題

`68321` では関連ポストの下ではなく、記事末尾付近に本文抜粋が出ていた。
`68622` は関連ポストがないにもかかわらず、本文抜粋が本文冒頭ではなく参照元付近まで下がっていた。

## 原因

本文抜粋を挿入する helper が、旧テンプレートの `<h3>🔗 出典記事</h3>` を anchor にしていた。
現在の RSS 生成本文にはこの anchor が無いことが多く、その場合 helper は抜粋 block を末尾へ append する。
その後に tag / badge / share などの enrichment が積まれるため、読者には引用記事が本文後半に見える。

## 方針

- AI 類似判定や記憶再構成は使わない。
- 本文抜粋を作る条件は変更しない。
- 生成済み HTML から `<aside class="nomotoke-source-excerpt">` を検出し、本文生成完了直前に正規 slot へ移動する。
- 関連ポストがある場合は、関連ポスト block の次に来る最初の本文見出し直前へ置く。
- 関連ポストがない場合は、最初の本文見出し直前へ置く。
- 見出し anchor が無い場合だけ、参照元 footer 直前へ fallback する。
- relocation / no-anchor skip は log に残し、silent skip にしない。

## 実装スコープ

触ってよい:

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_source_body_excerpt_auto.py`
- 本 ticket
- `doc/README.md`
- `doc/active/assignments.md`

触らない:

- Scheduler
- Cloud Run env
- Secrets
- X / SNS投稿
- mail 条件
- source 追加
- published WP post の本文更新

## 受け入れ条件

- 68321 型: 関連ポストがある場合、本文抜粋は関連ポスト後 / 本文見出し前に入る。
- 68622 型: 関連ポストがない場合、本文抜粋は本文見出し前に入る。
- 参照元 footer より下に本文抜粋が落ちない。
- 既存の本文抜粋生成可否は変えない。
- `source_excerpt_relocated` または `source_excerpt_relocation_skip` が observability に残る。
- `py_compile` / `compileall` / AST parse / targeted pytest が PASS する。
- Scheduler / env / Secret / X / SNS / mail 条件は変更しない。

## 実装結果

- `src/rss_fetcher.py` に `_relocate_source_excerpt_to_primary_slot` を追加。
- `<aside class="nomotoke-source-excerpt">` を検出し、最初の本文見出し前へ移動する。
- 見出しが無い場合は `📰 参照元` footer 直前へ fallback する。
- `_create_draft_with_same_fire_guard` の enrichment 完了直前で relocation を実行する。
- `tests/test_rss_fetcher_source_body_excerpt_auto.py` に 68321 型 / 68622 型 / fallback / draft 作成経路の regression を追加。
- draft `68622` は status=draft を確認後、保存済み raw content の本文抜粋位置だけを修正。更新後 `excerpt_pos < heading_pos < source_pos` を確認。
- published post `68321` は user 明示 go なしのため未更新。

## 検証

実行済み:

- `python3 -m py_compile src/rss_fetcher.py tests/test_rss_fetcher_source_body_excerpt_auto.py`
- `python3 -m pytest tests/test_rss_fetcher_source_body_excerpt_auto.py -q` -> 9 passed / 4 warnings
- `python3 -m compileall -q src/rss_fetcher.py tests/test_rss_fetcher_source_body_excerpt_auto.py tests/test_build_news_block.py`
- AST parse -> `AST_OK src/rss_fetcher.py,tests/test_rss_fetcher_source_body_excerpt_auto.py`
- `python3 -m pytest tests/test_rss_fetcher_source_body_excerpt_auto.py tests/test_build_news_block.py -q` -> 68 passed / 4 warnings
- `gcloud builds submit --project baseballsite --region asia-northeast1 --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:366-excerpt-placement-4021792 .` -> Cloud Build `593207f8-ad5d-4ddd-a5ea-cc56bb436772` SUCCESS
- image digest `sha256:e4bf5f00d105b1cb0d2f032c57f7d2a383f5282d79a63222dc1914ae815e99ff`
- `gcloud run deploy yoshilover-fetcher --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:366-excerpt-placement-4021792 --project baseballsite --region asia-northeast1 --quiet` -> revision `yoshilover-fetcher-00403-ssj`, traffic 100%
- `curl -sS https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/health` -> OK
- Cloud Run log: revision `yoshilover-fetcher-00403-ssj` startup TCP probe succeeded
- GitHub Issue evidence comment: https://github.com/fwns6760/-wordpressyoshilover/issues/35#issuecomment-4466572475

## 未完了

- natural fire / log evidence
- GitHub Issue #35 close
