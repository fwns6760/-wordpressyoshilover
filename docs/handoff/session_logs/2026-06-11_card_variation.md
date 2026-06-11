# 2026-06-11 X案カード画像バリエーション3種追加

user「ポストのデータカードは良くなったが、もっとバリエーションふやせる。」(6/10 刷新 `21deab6d` の続き)

- 12:30 JST | commit | カード variation 3種 (podium_top3 / focus_duel / dark_hero) | `c4871091` | build へ
- 12:33 JST | build | Cloud Build `535fefed` SUCCESS 1m35s | image `x-post-mail-lane:card-variation-c4871091` | job update へ
- 12:34 JST | deploy | Job `x-post-mail-lane` generation `174` に更新 | 次回 flush 便で新 variation 確認 | done

## 設計メモ

- 3 種とも ranking rows 共通 schema (`build_ranking_data`) で動くため、mail lane のデータ抽出・選択 cascade (pitcher_card / spotlight 優先) は無変更。round-robin tuple へ編入しただけ (9→12)
- dark 系 palette (`COLOR_NIGHT_*`) は brand lock (orange/gold/黒) の範囲内で下地を warm dark に振ったもの
- focus_duel の rival は「focus 巨人選手の 1 つ上の順位」(focus が先頭なら 1 つ下)。差分 chip は両値が数値解釈できる時のみ、focus 優位なら「リード」表記
- ローカル test: image 系 81 passed。mail lane 系 5 fail は worktree 上の別 WIP (469 reply handle 系) 由来で本件と無関係 (要: 469 担当 session で回収)

## 残課題

- 469 WIP (x_post_mail_lane.py の動画ポスト文字数 cap / handle 変更) が未 commit のまま worktree に残存。本件 commit は該当 hunk のみ partial stage で分離済
