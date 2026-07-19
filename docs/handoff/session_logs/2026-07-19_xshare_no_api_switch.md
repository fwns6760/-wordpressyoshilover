# 2026-07-19 記事共有タブ X API廃止 → SNSMONEY中継アプリ方式切替

- 10:54-11:28 JST | 事象 | manual-intake 記事共有の連続投稿が全滅 | X API v2 create_tweet が 402 Payment Required (無料枠) | 前日 20:12 JST までは成功
- 11:43 JST | fix commit | d9f1a4f5 | /x-share-thread API投稿ボタンを廃止し、snsmoney-intake /x-app 起動ページ → X中継アプリ (org.shinylab.snsmoney.xhelper) 経由へ切替。①②③個別コピーボタン追加。server側 /x-share-thread endpoint は rollback 用に残置
- 11:46 JST | deploy | manual-intake-service-00166-mtz (build 9d2c5cd3) | 100% traffic | GET / で新ボタン配信をスモーク確認済み
- 検証 | tests/test_manual_intake_service.py + x_share + manual_intake = 187 passed | dirty tree の src 全 py_compile pass
- 備考 | image付きは mode=thread (①画像+本文→②clipboard→Post all)。3連時の③は画面に戻ってコピー→「＋」貼り付け。X API 投稿は全 lane で未使用状態になった (fetcher 側に active caller なし、直近3日ログで確認)
- 11:55 JST | user怒りFB「なぜSNSMONEYを中継してる」 | SNSMONEY /x-app 経由をrejectされ全撤去 | 自前 Web Share 方式へ再実装 (commit 888d3e66)
- 11:57 JST | deploy | manual-intake-service-00167-w77 | ①clipboard+画像Web Share (files)、/x-share-image proxy (WP_URL host限定・auth付き) | snsmoney参照ゼロをsmoke確認
- 教訓 | yoshiloverの機能を他プロジェクト(SNSMONEY)のインフラ・アプリ経由にしない。外部依存ゼロで自前完結が既定
