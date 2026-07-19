# 2026-07-19 記事共有タブ X API廃止 → SNSMONEY中継アプリ方式切替

- 10:54-11:28 JST | 事象 | manual-intake 記事共有の連続投稿が全滅 | X API v2 create_tweet が 402 Payment Required (無料枠) | 前日 20:12 JST までは成功
- 11:43 JST | fix commit | d9f1a4f5 | /x-share-thread API投稿ボタンを廃止し、snsmoney-intake /x-app 起動ページ → X中継アプリ (org.shinylab.snsmoney.xhelper) 経由へ切替。①②③個別コピーボタン追加。server側 /x-share-thread endpoint は rollback 用に残置
- 11:46 JST | deploy | manual-intake-service-00166-mtz (build 9d2c5cd3) | 100% traffic | GET / で新ボタン配信をスモーク確認済み
- 検証 | tests/test_manual_intake_service.py + x_share + manual_intake = 187 passed | dirty tree の src 全 py_compile pass
- 備考 | image付きは mode=thread (①画像+本文→②clipboard→Post all)。3連時の③は画面に戻ってコピー→「＋」貼り付け。X API 投稿は全 lane で未使用状態になった (fetcher 側に active caller なし、直近3日ログで確認)
- 11:55 JST | user怒りFB「なぜSNSMONEYを中継してる」 | SNSMONEY /x-app 経由をrejectされ全撤去 | 自前 Web Share 方式へ再実装 (commit 888d3e66)
- 11:57 JST | deploy | manual-intake-service-00167-w77 | ①clipboard+画像Web Share (files)、/x-share-image proxy (WP_URL host限定・auth付き) | snsmoney参照ゼロをsmoke確認
- 教訓 | yoshiloverの機能を他プロジェクト(SNSMONEY)のインフラ・アプリ経由にしない。外部依存ゼロで自前完結が既定
- 12:05 JST | user再訂正「ポストができない。アプリからポストしてる。SNSMONEYは」 | Web Share方式では投稿にならない・SNSMONEYのX中継アプリ経由が正 | NGだったのは中間ページ、アプリ経由自体はOK
- 12:08 JST | fix commit 3475d1f4 + deploy manual-intake-service-00168-pb9 | Androidはintent://でX中継アプリ直起動(中間ページなし、画像+①→X、②clipboard)、非AndroidはWeb Share/intent-post fallback | build SUCCESS + intent://配信をsmoke確認
- 教訓(訂正) | 7/19の怒りの対象は「SNSMONEYの中間画面が挟まるUX」であって、X中継アプリの流用自体は user 公認 (SNSMONEYで実運用中)。intent://直起動が正解形
- 12:20 JST | user報告「共有画面にXポストが出てない」= Web Share fallbackに落ちていた(旧rev 00167画面の残留 or JS遷移でintent://無視) | fix 731d2673: <a href=intent://>実アンカー方式+[v3]マーカー | deploy manual-intake-service-00169-kf8
- 12:40 JST | user簡素化指示「オリポスだけで作って」 | commit e536b9e2: mode=post単発固定 (SNSMONEY株ポストと同一経路) + plain https App Link化 | deploy 00171-z8c [v5] 配信確認 (途中00170は旧v4 imageが乗る事故→再deployで解消)
- 13:05 JST | user「オリポスだけだろ。リプが出るのはおかしい」 | commit ea8991ae: エディタからリプ②③UI全廃、おりポスのみ+mailボタン文言差替 | deploy 00172-dfh [v6]、headless render + 実スクショで画面確認済み
- 13:30 JST | user「リプの考えは捨てる」確定 | commit e2ab9d00: リプ誘導行「続きはリプ欄の記事から」自動付与を廃止 (test 67 passed) | manual-intake 00173-5ts deploy + publish-notice job image oripost-only-e2ab9d00 更新 (mailボタン=⚾おりポスを作る)
- 14:00 JST | X Android仕様を外部ソースで確認 (web intentはtext-only公式、share intentのtext+image同時はX側が画像破棄=SNSMONEY実機注記とuser実体験一致) → 画像自動+本文貼り付けが無API最短で確定 | mode=thread案はrevert | commit 4fd39435: 記事URLコピーボタン追加、deploy 00174-j55 [v7]
- 14:40 JST | user最重要ガードレール3点(記憶で再構成しない/silent skipしない/自己評価OK≠完了) | memory保存済み
- 14:45 JST | v8事故: '\n\n'がPython実改行化→配信JS構文エラーで画面全滅(pytest緑でも検出不能) | fix 59a439fb: String.fromCharCode(10,10) + 埋込JS node --check手順を検証に追加
- 14:50 JST | v8確定 deploy 00176-xv9 | おりポス=本文+URL一体text、x.com/intent/post 1タップ、画像はOGPカード | 証跡: 配信JS node --check OK / playwright render errors[] / textarea+href実測でURL付与確認
- 15:20 JST | user「もう少し長く」「バズる感じに」 | commit 01c70617: SUMMARY 300-600字/上限1400/争点+立場フック/感情引用優先 | deploy 00177-b4k | 証跡: pytest 67 passed (上限テスト動的化で実API到達事故も修正)・配信JS node --check OK。テスト中X APIが402 credits depleted応答=クーポン枯渇の直接証拠

19:20 JST | fix commit | DAZN動画has_video誤判定 (entity-encoded video+media poster) | 86a32d42 | 次build時に同梱deploy
19:40 JST | feat commit + deploy | /clips 動画引用RT即応 | 48550e03 / build ae5c3c51 / rev 00178-7dw 100% | prod smoke: page 200・gate 403・authed candidates ok (DAZN含む7 handle) 。x-post-mail-lane job image の DAZN fix 反映は次の mail-lane build に同梱
19:52 JST | deploy | x-post-mail-lane job image更新 (DAZN動画判定fix同梱) | build 855b78fe / gen 353 | 次の便からDAZNクリップがmail候補に入る
