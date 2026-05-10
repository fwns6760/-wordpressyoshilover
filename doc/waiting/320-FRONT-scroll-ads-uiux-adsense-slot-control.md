# 320-FRONT-scroll-ads-uiux-adsense-slot-control

| field | value |
|---|---|
| ticket_id | 320-FRONT-scroll-ads-uiux-adsense-slot-control |
| priority | P1 |
| status | READY_FOR_IMPL_AFTER_USER_GO |
| owner | Codex |
| lane | FRONTEND / WP plugin |
| created | 2026-05-11 |
| doc_path | doc/waiting/320-FRONT-scroll-ads-uiux-adsense-slot-control.md |
| cost | Yen 0 repo work. AdSense revenue/serving behavior depends on existing Google AdSense setup. |
| regression risk | Low/Medium if limited to existing or user-confirmed AdSense slots and isolated from publish/mail/scheduler/env. |

## 1. 今回の目的

のもとけ型を参考に、yoshilover.com の記事閲覧中に自然に出入りする AdSense 広告/関連記事 UIUX を作る。

初回から「AdSense の広告枠」を前提にする。ただし、実装は既存または user が明示した AdSense 広告ユニット/コードを安全な wrapper に載せる形に限定し、AdSense 管理画面設定や自動広告設定は触らない。

- スクロールに応じて広告枠が出る/消える
- 記事本文やリンクを押し下げない
- モバイルで誤タップを誘発しない
- フッター付近やコメント欄付近で邪魔にならない
- 既存の自動公開・メール・scheduler・Cloud Run に影響しない
- AdSense policy 上危ない表示にならない

## 2. 今回触る範囲

候補。実装前に repo 内の実ファイルを grep して確定する。

- `src/yoshilover-063-frontend.php`
- frontend plugin に紐づく CSS / JS source が存在する場合はその範囲
- 必要最小限の frontend/plugin test
- 本 ticket Markdown

## 3. 今回触らない範囲

- publish 条件
- mail 通知
- scheduler
- Cloud Run env
- Cloud Run service/job 設定
- Secret Manager
- GitHub Actions
- RSS source 追加
- X 投稿
- SEO/noindex/canonical/301
- Gemini / LLM 記事生成
- WordPress 記事本文生成ロジック
- user 未確認の新規 AdSense 広告コード生成
- AdSense 管理画面設定
- AdSense 自動広告設定

## 4. 影響範囲

直接影響:

- single post / article page の閲覧 UI
- AdSense slot wrapper の表示/非表示
- mobile bottom AdSense slot
- sidebar / in-feed / article-bottom の AdSense placement

間接影響:

- CLS / layout shift
- 記事可読性
- スマホの誤タップリスク
- Core Web Vitals の体感

影響しない想定:

- 自動公開
- publish-notice mail
- RSS fetcher
- guarded-publish
- Cloud Scheduler
- Cloud Run runtime env

## 5. 実行予定テスト

実装時に最低限実行する。

- 触る前の targeted `rg`
- `AdSense`
- `adsense`
- `adsbygoogle`
- `googletag`
- `広告`
- `sticky`
- `IntersectionObserver`
- `yoshilover-063`
- PHP 変更時
  - `php -l <touched php files>`
- JS 変更時
  - 構文チェック可能なら `node --check <touched js files>`
- CSS/HTML 変更時
  - 表示崩れ確認
  - mobile / desktop の viewport 確認
- 既存 baseline
  - repo で frontend/plugin baseline が定義されていれば実行
  - 定義がない場合は実行不可理由を記録
- live fire 後
  - deploy した場合のみ、表示確認 + ERROR log + 数値 diff
  - deploy しない場合は N/A と理由を記録

## 6. STOP 条件

- 既存または user 確認済みの AdSense slot / code が特定できない
- AdSense の新規広告ユニット発行や管理画面操作が必要になる
- AdSense policy 上の危険が見える
- publish / mail / scheduler / env / Cloud Run へ波及する
- 既存 plugin の責務が読めない
- SWELL / WordPress 側 hook の影響範囲が広すぎる
- mobile で本文・リンク・コメント導線を隠す
- layout shift が大きい
- 既存 dirty diff と混線する
- テストや構文確認ができない

## 7. 禁止事項

- 記憶から UI / AdSense 配置を再構成しない
- repo / live DOM / WP 実設定を確認せずに「あるはず」で進めない
- silent skip しない。AdSense slot が特定できない場合は必ず STOP して報告する
- 自己評価だけで OK にしない。実DOM / screenshot / log / diff の事実で確認する
- user 未確認の AdSense code を入れない
- user 未確認の Google Publisher Tag を入れない
- 誤クリックを誘う表示にしない
- 広告を記事本文と誤認させない
- close button を押しにくくしない
- sticky 広告で記事本文を隠さない
- publish / mail / scheduler / env / Cloud Run / GitHub Actions に触らない
- 指示外の source 追加をしない
- 指示外の SEO 変更をしない
- ついで refactor をしない

## 8. 想定されるデグレ

- mobile bottom AdSense slot が本文やボタンを隠す
- sticky AdSense slot がフッター/コメント欄にかぶる
- in-feed AdSense slot で記事一覧の間隔が崩れる
- JS error で表示制御が動かない
- CSS specificity が SWELL / 既存 plugin と衝突する
- close 状態が保持されず、毎ページ邪魔になる
- CLS が増える
- AdSense が no-fill のときに空枠が目立ち、サイト品質が下がる

## 9. 実装方針

### Phase 0: read-only audit

- 既存 plugin / theme hook / CSS を grep
- 既存 AdSense code / `adsbygoogle` / `googletag` / 広告 shortcode / widget の有無を確認
- のもとけ型で必要な UI 要素を yoshilover 用に分解
- 実装対象 hook を確定
- 既存枠が repo 外の WP 管理画面にある場合は、user に広告ユニット/配置方式の確認を求める

### Phase 1: AdSense slot wrapper

- article page のみで user 確認済み AdSense slot を出す
- 表示位置候補:
  - 記事本文下
  - 記事一覧の間
  - mobile bottom fixed slot
  - desktop sidebar sticky slot
- `IntersectionObserver` で footer/comment 付近では hide
- close button を付ける
- session 単位で閉じた状態を保持する

### Phase 2: safety polish

- CLS を抑えるため、広告枠の高さを固定
- mobile では safe-area を考慮
- `prefers-reduced-motion` 時は animation を止める
- JS なしでも本文閲覧が壊れないようにする

### Phase 3: deploy decision ticket

実装が green になっても、本番反映は別 GO とする。

AdSense 管理画面側の新規広告ユニット作成や自動広告設定変更はさらに別 ticket で扱う。

## 10. 成功条件

- AdSense slot UI が article page で表示される
- scroll により出る/消える動作が確認できる
- mobile / desktop の両方で本文を隠さない
- close できる
- footer/comment 付近で邪魔にならない
- publish/mail/scheduler/env/Cloud Run/GitHub Actions に触っていないことを diff で確認できる
- user 確認済みではない AdSense code が入っていないことを diff で確認できる

## 11. Regression Memo

- 目的は広告収益 UIUX の土台作りであり、記事生成品質や publish/mail には触れない。
- 初回から AdSense slot 前提。ただし user 確認済みの既存/指定枠だけを扱い、AdSense 管理画面設定は触らない。
- 自動公開とメールが最重要。少しでも波及が見えたら停止する。
- AI事故源として、記憶から再構成 / silent skip / 自己評価 OK を禁止する。
- 実装時の OK 判定は、実ファイル diff、実DOM、mobile/desktop 表示、ERROR log、publish/mail 不干渉の事実で行う。

## 12. 作業ログ

- 2026-05-11: user request により ticket 作成。実装・commit・push・deploy は未実施。
- 2026-05-11: user clarification により、dummy-only ではなく AdSense slot 前提へ修正。未確認 AdSense code / 管理画面設定は不可触。
- 2026-05-11: user safety rule を追記。記憶から再構成 / silent skip / 自己評価 OK を禁止。
- 2026-05-11: Phase 0 read-only audit。repo内に既存 `.yoshi-ad` wrapper はあるが real ad unit ID は入っていないことを確認。live DOM では SWELL の `widget_swell_ad_widget` / `adsbygoogle` / `pagead2.googlesyndication.com` が既存 AdSense 枠として出ていることを確認。
- 2026-05-11: 新規 AdSense code / ad unit ID は追加せず、既存 SWELL AdSense widget だけを対象にする scroll UI controller を `src/yoshilover-063-frontend.php` に追加。
- 2026-05-11: sandbox の DNS 制限で最初の live DOM curl が失敗。権限付き read-only curl で live DOM を確認。
- 2026-05-11: sandbox の socket 制限で最初の full pytest は `LiveServerSmokeTest` 3件のみ PermissionError。権限付きで同一 full pytest を再実行し green。
- 2026-05-11: user clarification により、のもとけ投稿ページの scroll 連動 AdSense 表示を再観察。desktop は sidebar 内広告 block が scroll 追従して記事末尾で停止、mobile は sidewinder ではなく本文下/コメント付近の既存広告枠がスクロールで出る構造と確認。
- 2026-05-11: 追加再現テストを先に追加し、現行実装では `setupSidewinder` / mobile inline class 不足で targeted pytest が赤になることを確認。
- 2026-05-11: desktop sidebar の既存 AdSense widget に sidewinder controller を追加。mobile では既存 AdSense widget を inline scroll 表示に寄せ、fixed overlay は追加しない実装へ更新。

## 13. 作業後追記欄

実装後に追記する。

- 実際に変更したファイル:
  - `src/yoshilover-063-frontend.php`
  - `tests/test_front_adsense_scroll_ui.py`
  - `doc/waiting/320-FRONT-scroll-ads-uiux-adsense-slot-control.md`
  - `doc/README.md`
  - `doc/active/assignments.md`
- diff 概要:
  - single post のみで既存 SWELL AdSense widget を検出する inline CSS / JS を追加。
  - `.widget_swell_ad_widget` かつ `adsbygoogle` / `pagead2` を含む既存広告枠だけに `yoshi-adsense-slot` class を付与。
  - `IntersectionObserver` で in-view / active class を切り替え、scroll に合わせて自然に表示する。
  - desktop sidebar 内の既存 AdSense widget は sidewinder 化し、scroll 中は fixed、記事末尾では absolute に切り替えて止める。
  - mobile の既存 AdSense widget は inline 表示のまま、スクロールで浮き上がる見え方にする。
  - 新規 AdSense code / `data-ad-client` / `data-ad-slot` は追加しない。
  - close overlay は入れない。AdSense 上に操作UIを重ねない。
- 実行したテスト:
  - `php -l src/yoshilover-063-frontend.php`
  - `python3 -m py_compile tests/test_front_adsense_scroll_ui.py`
  - `python3 -m compileall tests/test_front_adsense_scroll_ui.py`
  - `python3 -m ast tests/test_front_adsense_scroll_ui.py`
  - `python3 -m pytest tests/test_front_adsense_scroll_ui.py`
  - `git diff --check -- src/yoshilover-063-frontend.php tests/test_front_adsense_scroll_ui.py doc/waiting/320-FRONT-scroll-ads-uiux-adsense-slot-control.md doc/README.md doc/active/assignments.md`
  - `python3 -m pytest`
- テスト結果:
  - `php -l`: pass
  - `py_compile`: pass
  - `compileall`: pass
  - `ast`: pass
  - targeted pytest: `5 passed, 3 warnings`
  - `git diff --check`: pass
  - full pytest sandbox: `3576 passed / 3 failed`。失敗は sandbox socket 制限による `LiveServerSmokeTest` 3件の `PermissionError`
  - full pytest 権限付き再実行: `3579 passed, 3 warnings`
- 残った懸念:
  - 未deployのため、実ブラウザ screenshot / CLS / mobile scroll の実機確認は未実施。
  - AdSense no-fill 時の見え方は live deploy 後に確認が必要。
  - 実際の収益影響は AdSense 側の配信状況に依存する。
- 新しく見つかったデグレ:
  - なし。repo test 上は検出なし。
- 追加した回帰テスト:
  - `tests/test_front_adsense_scroll_ui.py`
  - 既存 SWELL AdSense widget だけを対象にすること
  - 新規 `data-ad-client` / `data-ad-slot` / `<ins class="adsbygoogle">` を追加しないこと
  - single post のみで動くこと
  - `IntersectionObserver` を使うこと
  - desktop sidewinder が main content 範囲で fixed / absolute を切り替えること
  - mobile は inline 表示のまま fixed overlay にしないこと
  - close / dismiss overlay を入れないこと
- 次回触ってはいけない範囲:
  - publish 条件
  - mail 通知
  - scheduler
  - Cloud Run env
  - Cloud Run service/job 設定
  - Secret Manager
  - GitHub Actions
  - RSS source 追加
  - X 投稿
  - SEO/noindex/canonical/301
  - AdSense 管理画面設定
  - user 未確認の新規 AdSense 広告コード生成
