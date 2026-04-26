# 117 adsense-ad-unlock-policy-and-css-toggle

## meta

- number: 117
- alias: 087-A
- owner: **Claude-managed front-scope**(Front-Claude は不在、Claude 自身が front-scope を管理)
- type: front / ad policy / CSS toggle
- status: **BLOCKED_USER**
- priority: **P1.5**(105 公開 ramp より後、今すぐはやらない)
- lane: **either / front-scope**(本 repo backend lane = A/B 担当外、front-scope として Claude 管理)
- created: 2026-04-26
- parent: 087(`doc/087-front-ad-layout-and-adsense-ready-slots.md`、AdSense 「器」(slot 枠) 既設)
- source_of_truth(A/B/C 方針): `docs/handoff/ad_policy_memo_post_launch.md`
- blocked_by: user choice A/B/C + AdSense account 状態確認

## 目的

現在 `src/custom.css` で **全殺し**している AdSense / Google 広告 CSS を、公開後の方針(A/B/C)に合わせて **段階解除**できるようにする。

## 背景

- 087 = 広告枠の **器** だけ(CSS class `.yoshi-ad--*` 配備済、ad コード active 化なし)
- `docs/handoff/ad_policy_memo_post_launch.md` に **A/B/C 方針メモ**あり(本 ticket の正本)
- 実際の広告解除 ticket は **まだない** = 本 117 が起票
- **Front-Claude はいない** → front-scope は Claude 管理で扱う

## A/B/C 方針(本 ticket で正式化、詳細は `ad_policy_memo` 正本参照)

| pattern | 内容 | 対象範囲 |
|---|---|---|
| **A** | UI 優先、anchor / vignette 殺し、記事内広告最大 3 枠 | `src/custom.css` AdSense 殺し section の部分解除(anchor/vignette は維持殺し)|
| **B** | 自動広告フル解除 | `src/custom.css` AdSense 殺し section の **全削除**(Google 自動広告に委ねる)|
| **C** | 広告 OFF 維持 | 現状(全殺し維持)、本 ticket 解除なし |

## やること(user choice A/B/C 後)

1. user が A/B/C を明示
2. 対象 CSS 範囲(`src/custom.css` の AdSense 全殺し section)を **read-only で確認**
3. 選択された pattern に応じて CSS 部分解除 / 全削除 / 維持
4. 解除前後の表示確認項目を作成(mobile / desktop 両方、anchor/vignette 挙動含む)
5. 既存 front 表示が壊れていないか visual smoke check

## 不可触

- **user 判断なしの広告解除**(本 ticket は BLOCKED_USER 維持)
- AdSense publisher ID / ad unit ID **表示**(secret 級扱い、log にも出さない)
- AdSense 実コード **新規挿入**(本 ticket は CSS toggle のみ、実 ad コードは別 ticket / user op)
- backend Python(`src/`、PUB-002/004/005 等)変更
- publish runner / WP REST 変更
- X / SNS 投稿
- secret / env / `.env` 操作
- `RUN_DRAFT_ONLY` flip
- Cloud Run env 変更
- `git add -A` / `git push`(Claude が後で push)
- baseballwordpress repo

## acceptance

1. user が A/B/C のどれかを明示してから着手(本 ticket は BLOCKED_USER で fire しない)
2. 解除対象 CSS(`src/custom.css` 内 AdSense 全殺し section)が明確に特定済
3. mobile / desktop で広告が暴れない(visual smoke check pass)
4. anchor / vignette の扱いが選択方針通り
5. 既存 front 表示が壊れない(visual regression check)
6. backend 差分なし(`git diff src/` で AdSense 関連以外の変更ゼロ)

## 102 board 反映

```
117 = adsense-ad-unlock-policy-and-css-toggle
alias = 087-A
owner = Claude-managed front-scope
lane = either / front-scope
priority = P1.5
status = BLOCKED_USER
blocked_by = user choice A/B/C + AdSense account 状態
user_action_required = 「広告方針 A / B / C で」と明示
```

## stop 条件

- user 明示なしで CSS 解除を進めようとした → 即停止
- AdSense 実コード新規挿入を要望された → 別 ticket(本 ticket scope 外)
- `src/custom.css` 以外の front file(theme functions / template / JS 等)に範囲拡大 → 別 narrow ticket で扱う
- backend `src/` に影響(check で diff 検出)→ 即停止 + revert

## 関連 file

- `doc/087-front-ad-layout-and-adsense-ready-slots.md`(器 = AdSense slot 枠 既設)
- `docs/handoff/ad_policy_memo_post_launch.md`(A/B/C 方針 正本)
- `src/custom.css`(本 ticket の対象 CSS、AdSense 全殺し section)
- `doc/102-ticket-index-and-priority-board.md`(本 117 row 追加先)
