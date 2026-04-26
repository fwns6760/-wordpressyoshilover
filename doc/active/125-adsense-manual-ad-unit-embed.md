# 125 adsense-manual-ad-unit-embed

## meta

- number: 125
- alias: 087-B(087 = 器、117 = unlock CSS toggle、本 ticket = 手動 ad unit embed)
- owner: Claude-managed front-scope(Front-Claude 不在、Claude が管理)
- type: front / ad unit embed / WP theme functions or template
- status: **BLOCKED_USER**(ad unit ID + AdSense Auto ads OFF 状態確認待ち)
- priority: P1.5(117 同列、105 公開 ramp と並走 OK、急がず)
- lane: either / front-scope
- created: 2026-04-26
- parent: 087(器、AdSense slot CSS class)/ 117(CSS unlock B 適用済 = `0555733`)
- source_of_truth(ad unit policy): `docs/handoff/ad_policy_memo_post_launch.md`
- blocked_by: **user op**(AdSense dashboard で Auto ads OFF + ad unit ID 生成)

## 目的

087 で AdSense **slot 枠(器)**は配備済(CSS class `.yoshi-ad--*` 等)。
117 で auto ads block を解除済(B = full CSS kill removal、`0555733`)。
本 ticket = **手動 ad unit code を 087 slot に embed** する。

「自動広告 OFF + 手動 only」運用の WP 側実装。AdSense dashboard 側 Auto ads OFF は user op、本 ticket は WP 側 embed 担当。

## 背景

- 087: AdSense slot 枠(`.yoshi-ad--*` CSS class)既設、ad コード未配置
- 117 B: CSS kill 全削除済(`0555733`)= auto / 手動 両方の広告 block 解除
- 現状: adsbygoogle script は WP `<head>` に embed 済(40 hits / homepage、user 確認済)
- 必要: AdSense Auto ads OFF + 各 slot に `<ins class="adsbygoogle" data-ad-client="ca-pub-XXX" data-ad-slot="YYYY">` 配置

## 重要制約

- **AdSense publisher ID(`ca-pub-XXX`)/ ad unit ID(`data-ad-slot=YYYY`)は user 提供必須**(secret 級扱い、私が値を表示しない)
- AdSense dashboard 操作(Auto ads OFF、ad unit 生成)= **user op**(外部アカウント、私から触れない)
- noindex 維持中は ad delivery 想定外可能性あり(Google's policy)
- backend Python(`src/*.py`)に **影響なし**(本 ticket = front theme / template / functions only)
- adsbygoogle script は既存(`<head>` 内)= 二重挿入禁止
- 1 page あたり ad unit 配置数は ad_policy_memo の方針に従う(A pattern: 記事内最大 3 枠 等)

## 不可触

- backend `src/*.py`(影響なし scope)
- AdSense API / Google account 設定
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- automation / scheduler / mail
- baseballwordpress repo
- X / SNS POST
- adsbygoogle script の `<head>` 内重複挿入(既存 = 1 度のみ)
- AdSense dashboard 自体の操作(user op)
- 117 で削除済の CSS kill section 復活
- `git add -A` / `git push`(Claude が後で push)

## write_scope(候補)

- WP theme functions(`functions.php`)or template part に ad unit code 挿入
- 087 の `.yoshi-ad--*` slot に対応する hook / shortcode / widget
- 配置数 = ad_policy_memo の選択 pattern 準拠
- 詳細 file path は WP theme 構造確認後に確定(本 ticket = doc-first、実装 fire 時に file 特定)

## acceptance

1. user が AdSense dashboard で Auto ads OFF 完了 + ad unit ID 提供
2. 087 の `.yoshi-ad--*` slot に対応する位置に ad unit code 配置
3. publisher ID / ad unit ID は doc / log / chat に **値を表示しない**(secret 級)
4. mobile / desktop で広告が暴れない(visual smoke check = user op)
5. anchor / vignette が方針通り(A pattern なら殺す、B pattern なら出る)
6. backend 差分なし(`git diff src/*.py` で 0)
7. adsbygoogle script は二重挿入なし(既存 `<head>` の 1 件のみ)

## test_command

- 静的 verify(grep で ad unit code 配置確認、actual ad render は user 目視)
- backend test 影響なし(`python3 -m unittest discover -s tests` baseline 維持)

## next_prompt_path

`/tmp/codex_125_impl_prompt.txt`(user `125-A go` + ad unit ID 受領後に Claude が用意)

## 実装順(本 ticket 完了後の見取り図)

1. user op: AdSense dashboard で Auto ads OFF
2. user op: ad unit ID 1〜N 個生成 + Claude へ提供(秘密扱い、私は値 echo しない)
3. **125-A** Codex便 / Claude 直: WP theme functions / template に ad unit code embed
4. user op: visual smoke check(mobile / desktop / 各 slot 表示)
5. 125 close + 125-B(配置調整) or 別 ticket(slot 追加 / pattern 変更)

## stop 条件

- AdSense Auto ads OFF 未完了で本 ticket 進行 → 二重広告 / 重複表示
- ad unit ID 未取得で実装 fire → blank ad code 配置で意味なし
- backend `src/*.py` を触る変更が必要 → 本 ticket scope 外
- adsbygoogle script を `<head>` に追加挿入 → 二重挿入 NG
- AdSense publisher ID / ad unit ID の値を log / commit message / chat に出力 → 即停止 + revert

## 関連 file

- `doc/087-front-ad-layout-and-adsense-ready-slots.md`(器 = AdSense slot 枠 既設)
- `doc/117-adsense-ad-unlock-policy-and-css-toggle.md`(CSS unlock B 適用済 `0555733`)
- `docs/handoff/ad_policy_memo_post_launch.md`(A/B/C 方針 + 配置数 正本)
- `src/custom.css`(117 B 適用後の状態)
- `doc/102-ticket-index-and-priority-board.md`(本 125 row 追加先)
