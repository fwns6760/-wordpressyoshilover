# 順位表・ドラフト・トップの鮮度回復

Status: CLOSED / LIVE_DEPLOYED_VERIFIED

User: 2026-11-09「直して」「自動化にならんの」、中断後「とまった。再開できる？」。

## 原因と修正範囲

- rotation-updater が年俸用 canonical insight.db 取得中に512MiBでOOM。順位表まで到達せず、8月9日時点で停止。既存 compact data_site.db のみ使用し、128MiB上限・取得後削除。順位表・ドラフトを先に実行。
- ドラフトは baked 2025年データだけだった。既存公開hubへNPB公式当年結果を反映し、履歴・他section保持。年度/球団/連続巡目/欠落を検証し、失敗時はWP保持。次年度以降はbaked以降の年度も取得。
- data-site-publisher によるbaked draft上書きを削除。daily refreshを更新責任者にする。
- トップの新着fallbackに7日制限。今日枠は当日限定で週次話題から補充しない。古いmanual optionへ戻さない。順位表保存時にトップcache破棄。

## 不可触

実行回数・512MiB・Scheduler・env・Secret・IAM・X・mail変更なし。過去記事本文は変更しない。dirtyな主repo全体buildはしない。既存本番digestに限定COPYするoverlayのみ。

## 検証

- 新規回帰＋daily refresh＋standings: 30 passed。
- publisher＋home links: 27 passed、既存version固定テスト1 failure。変更前HEADでも0.23.9期待に対し0.24.9で同じ失敗を再現。scope外test修正はしない。
- PHP lint、実関数読み込みによるhome期間制限テスト、compileall、AST、diff check成功。
- 公式HTMLの実取得preview: 6球団143試合、2026支配下6人・育成5人。
- Cloud Build 27eb5a08-29ee-4e6c-99a2-250d6b11b7f7 SUCCESS。
- deploy/live証跡はbaseballwordpress/implementations/freshness-recovery-20261109/。

## rollback

同証跡deployment-plan.jsonのbefore_imagesへ各Jobのimageだけ戻す。frontendは戻したJobをexecuteして以前のpluginを再配布する。WP本文before snapshotを保存。

## 本番検証完了

- 初回overlayの本番ではbs4未導入を検出。書込前skipを確認し、標準HTMLParserへ変更。修正版873a8055-b8ed-4628-b9ab-3e0ae9a82017でコンテナ内import＋公式fixtureテスト成功。
- rotation-updater-lvlx4: Completed=True、21.9秒、OOM/ERROR=0。standings92627・draft82351 updated、salary-valueも成功。旧runはOOMで順位表/ドラフト0件、修正版は2件更新。
- wp-frontend-deploy-v4k7f: Completed=True。3Jobはimage以外の実行設定不変。
- 公開RESTと正規URLで6球団143試合、巨人76勝64敗3分・2位、2026ドラフト支配下6/育成5、当日/週次旧記事card0を確認。ID/slug/URL/parent/status/公開日時保持。
- PC1280/スマホ390の表示チェック＋画像目視完了。
- rotation-updater-daily: ENABLED、30 7 * * *、Asia/Tokyo。変更なし。翌朝自然発火の観測は未到来。
- 明示的な本番手動復旧を2回実行。通常ジョブ内のsalary-value/injured更新も走行。他lane追加実行なし。
