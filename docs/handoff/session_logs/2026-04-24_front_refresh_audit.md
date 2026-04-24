# front_refresh 依頼書化便 (2026-04-24 JST)

read-only 実画面確認の上で、トップ圧強化 + sidebar 4 段の Codex 依頼書を作成。

## 実行内容

- `https://yoshilover.com/` と `https://yoshilover.com/62965` を curl（read-only）で取得
- `yoshi-*` クラスを DOM class attr と CSS rule で分離して実稼働状況を確認
- `docs/handoff/codex_responses/2026-04-24_063-V1-smoke.md` を読んで topic-hub の配置経緯を確認
- `src/yoshilover-063-frontend.php` の shortcode / hook 登録を grep で確認

## 確定事実（実画面）

- SWELL + `swell_child` が稼働（親テーマ直編集不要）
- トップ `w-frontTop` は `widget_text` → `yoshi-topic-hub`(「今週の話題」4件) → `widget_recent_entries` の順
- 記事詳細（62965）で稼働中の yoshi block: `yoshi-breaking-strip` / `yoshi-topic-hub` / `yoshi-dense-nav` / `yoshi-article-bundles` / `yoshi-sns-reactions` / `yoshilover-related-posts`
- DOM 0（未配線）の yoshi block: `yoshi-today-giants` / `yoshi-sidebar-rail` / `yoshi-front-card`

## 元提案から変えた点

- `yoshi-topic-hub` 常設化 → **撤回**（既に front_top widget で常設済）
- `yoshi-today-giants` 撤去 → **撤回**（そもそも未配線、触らない）
- `yoshi-breaking-strip` top 配置 → **本便スコープ外**（別便判断）
- `yoshi-front-card` 有効化 → **本便スコープ外**（別便、T-028 起票）
- 親テーマ `header.php` override → `swell_child/header.php` に変更（子テーマ確認済）

## 作った成果物

- `docs/handoff/codex_requests/2026-04-24_front_refresh.md`
  - header 圧強化 + cat-nav / tag-nav 追加 + topic-hub 見た目維持 + sidebar 4 段並べ直し
  - NG 一覧に validator / mail / X API / 記事生成 path / 親テーマ / 未配線 block 追加を明記
- `tickets/OPEN.md` に T-026 / T-027 / T-028 を追加
  - T-026: `yoshi-today-giants` 未配線
  - T-027: `yoshi-sidebar-rail` auto-inject 届いていない
  - T-028: `yoshi-front-card` density scope 未配線

## 次の 1 手

- よしひろさん合格判定後、依頼書を Codex に投げる
- T-026 は「使うか / 使わないか」のよしひろさん判断待ち
