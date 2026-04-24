# front バシバシ便 (2026-04-24 夜 JST)

Claude Code = yoshilover front 専任 owner に役割変更。commit / push 権も Claude Code 側へ移管（よしひろさん明示指示）。
CSS-only で巨人オレンジ圧を複数ブロックに投入。

## 役割変更

- CLAUDE.md の「src/ 編集禁止 / commit/push は Codex」ルールを front スコープで override
- `/home/fwns6/.claude/projects/-home-fwns6-code-wordpressyoshilover/memory/user_role_front_owner.md` に保存
- deploy (SWELL 追加 CSS 貼り付け) のみよしひろさんが実施、他は Claude Code が完結

## push 済み commit

| hash | 内容 |
|---|---|
| `2ce3b9c` | topic-hub を巨人オレンジ hero strip (black panel + orange 5px + white cards + THIS WEEK ラベル) |
| `93b5864` | 最近の投稿 widget を card-list 化 / c-secTitle -widget を hero-lite / sidebar hover orange 左ボーダー / count Oswald pill / SNS reactions 巨人 3 色統一 |
| `67ccff2` | breaking-strip / article-bundles 外枠 5px + 見出し uppercase + orange 縦バー前置、breaking-strip 見出しに LIVE chip |

## 契約

- よしひろさん = WP admin → SWELL → カスタマイザー → 追加 CSS に `src/custom.css` 全文を貼って保存（30 秒）
- Claude Code = 他全部（編集 / git / smoke curl）

## smoke

- 貼り付け後、Claude Code が `curl https://yoshilover.com/` と `curl https://yoshilover.com/62965` を再取得
- inline `<style>` 内に新ルールの存在と回帰なしを確認
- mobile 390px は CSS 側の media query で担保

## 未対応（次の候補）

- T-028: `.is-yoshi-front-density` body-class 未配線 → `src/yoshilover-063-frontend.php` に `body_class` filter を足せば home 記事一覧のカード化が効く
- T-027: `yoshi-sidebar-rail` auto-inject 未着弾 → plugin 側の sidebar index 判定デバッグ
- T-026: `yoshi-today-giants` 使うか撤去か（よしひろさん判断待ち）

## 注意

- 巨人 3 色 (orange #F5811F / black #1A1A1A / white) を hero の外枠に統一
- カテゴリ色ラベル (`--blue` 選手情報 / `--purple` OB 等) は機能色として維持
- breaking-strip の subtype 色 (lineup=blue 等) も機能色として維持
