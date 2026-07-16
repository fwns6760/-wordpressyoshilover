# 2026-07-16 /live スマホ usability 改善

user 報告: スマホで画面を閉じて戻ると生成内容が消える / X に飛ぶと観戦モードへ戻れない。

対応 (src/manual_intake_service.py, commit af3ac51c):

1. 状態永続化 — 入力欄3つ + 生成カード (文面編集・投稿済み状態・再作成 origin) を
   localStorage `yl_live_v1` に保存、タブ破棄後の再オープンで自動復元。12h expiry。
2. X リンク別タブ化 — /friends・候補・🔗データページ添付 の x.com リンクに
   target=_blank rel=noopener。元タブ (観戦モード) が失われない。
3. PWA 化 — /live-manifest.webmanifest + /live-icon.png (base64 埋め込み 1.3KB) 追加、
   apple-mobile-web-app メタ。ホーム画面に追加すると standalone アプリとして起動、
   X へ飛んでも in-app ブラウザで閉じるだけで戻れる。

検証: pytest manual_intake 系 78 passed / node --check JS OK /
jsdom で save→タブ破棄→restore round-trip + 12h expiry テスト green /
ローカル起動で /live・manifest・icon 200 確認。

## log

- 18:13 JST | commit | live-mobile-usability | af3ac51c | Cloud Build fire
- 18:15 JST | build SUCCESS | 9bcd1708 (1m23s) | deploy fire
- 18:17 JST | deploy | manual-intake-service-00165-bcd 100% | prod smoke: /live・manifest・icon 200 green | user へ「ホーム画面に追加」案内
