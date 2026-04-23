# 2026-04-24 063-V2 front-density local impl

## summary

- 063-V1 close 後の次便として、トップ一覧の情報密度強化に着手
- write scope は `src/yoshilover-063-frontend.php` / `src/custom.css` / `doc/063-comment-first-topic-hub-impl.md` / `doc/README.md`
- `src` route / pickup / validator / automation / scheduler / env / secret / published 書込経路は不可触を維持

## implemented

- home/front 専用の front-density patch を 063 plugin に追加
- 一覧カードへ `subtype badge / phase / score / 要約 1 行` を client-side で後付け
- `live_update` は同日・同対戦相手の並びを数え、`連投 n本` chip を補助表示
- 一覧カード向け V2 CSS を追加

## local verify

- `php -l src/yoshilover-063-frontend.php` => pass

## pending

- live deploy: plugin upload 経路未確認
- WP 実機 smoke: deploy 後に別途
