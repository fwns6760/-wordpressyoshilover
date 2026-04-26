# 087 Front ad layout and adsense-ready slots

## meta

- owner: **front Claude**(front lane の実装担当、別 Claude session)
- type: **front impl ticket**(backend lane Claude は触らない)
- status: OPEN(着手は front Claude 側のタイミング)
- created_at: 2026-04-24 22:15 JST
- created_by: backend lane Claude(管理代行起票、実装は front owner)
- deps: 063 系 front 既存実装(plugin / additional CSS / front_top hub layout / Phase 1 noindex)
- non_blocker_for: backend lane(070-086)/ publish chain / mail chain / ledger
- non_blocker: AdSense account / 実 ad code 接続(scope 外)

## why_now

- AdSense は現在停止中
- ただし「広告が自然に見える画面構造」は ad off の今のうちに先に作れる
- のもとけ site の見え方は単純な 1 枠貼りではなく、sidebar 追従 / 記事下差し込み / collapse / 複数サイズ最適化が組み合わさっている
- AdSense 復活時に **慌てて HTML/CSS を設計し直さなくて済むよう、器だけ先に作る**
- backend lane(070-086)とは完全 disjoint、front Claude が単独で進められる

## purpose

- AdSense が停止中でも崩れず、再開した時にすぐ ad code を差し込める front の広告枠レイアウトを作る
- 今回は ad network 実接続ではなく、**広告の器(slot wrapper + placeholder + collapse-ready + fallback)** を front に実装する
- ad-off 時に大きな白箱を残さない
- 後で AdSense を差し込みやすい HTML/CSS 構造にする
- のもとけ風の「広告があるのに邪魔すぎない」見え方に寄せる

## non_goals

- AdSense 実コード(`ins.adsbygoogle` 等)の埋め込み
- Google Publisher Tag(GPT)接続
- AdSense account / publisher ID / ad unit ID の登録 or 露出
- secret(API key、auth token)に触る
- ad serving の cookie / consent 経路設計
- heavy ad stack(自動広告 / vignette / sticky anchor / interstitial)の完全再現
- backend lane / validator / mail chain / automation / publish / live post 全て
- baseballwordpress repo

## 最小実装(3 + 1 slot)

### slot 1: top sidebar 右カラム上部(desktop primary)

- 配置: front page の右 sidebar 最上部、breadcrumb の下あたり
- size: 300×250(MEDIUM RECTANGLE 想定、AdSense 標準)
- 挙動: sidebar scroll 追従(`position: sticky; top: <header offset>` 等、SWELL の `is-style-sticky-top` 系を流用可)

### slot 2: 記事詳細の本文下(both desktop + mobile)

- 配置: post detail の `the_content()` 直後、related posts の手前
- size: responsive(728×90 / 336×280 / 320×100 が ad off でも安定する形状)
- 挙動: ad-off 時は collapse(高さ 0 + margin 維持なし)、ad-on 時は responsive

### slot 3: mobile 本文途中(optional、必要時のみ)

- 配置: post detail の `<h2>` 2 個目の前後など、reading flow を切らない位置
- size: 300×250 or 320×100
- 挙動: mobile 限定表示(`@media (max-width: 768px)`)、desktop では非表示
- 任意: 1 記事 1 枠まで(複数挿入はスクロール体験を害する)

### slot 4: ad-off 時の自社導線置換(soft fallback)

- 各 slot で ad code が空 / failed のとき、**小さな自社導線**(関連記事 1 行 / X follow CTA / newsletter signup 等)に自然に置換
- 完全な空 div は出さない
- soft fallback は CSS-only で trigger 可能(`:empty + .yoshi-ad-fallback { display: block; }` 等)

## 触る front 要素(候補、front Claude が最終確定)

| 要素 | path | 想定 diff |
|---|---|---|
| CSS(slot wrapper / sticky / collapse / soft fallback) | `src/custom.css` | +50-100 行 |
| PHP(slot wrapper insert hook) | `src/yoshilover-063-frontend.php` | +30-60 行(`the_content` filter / `dynamic_sidebar` フック) |
| (任意)widget 登録 | `src/yoshilover-063-frontend.php` | sidebar 用 widget area 追加 1 件 |
| (任意)shortcode | 同上 | `[yoshi_ad_slot id="..."]` ad slot 配置用 shortcode |

不要な前提:
- 新規 PHP plugin の追加(既存 `yoshilover-063-frontend.php` 内で完結する想定)
- functions.php 直接編集(theme update で消える)

## CSS class 命名規則(後の AdSense 差し込みに備える)

```
.yoshi-ad                     /* slot 共通 wrapper */
.yoshi-ad--sidebar-top        /* slot 1 */
.yoshi-ad--article-bottom     /* slot 2 */
.yoshi-ad--article-inline     /* slot 3 (mobile) */
.yoshi-ad__placeholder        /* ad-off 時の placeholder */
.yoshi-ad__fallback           /* soft fallback (自社導線) */
.yoshi-ad--collapsed          /* JS 不要、CSS で空 slot を collapse */
```

`data-ad-slot-id` 属性で slot 識別(後で AdSense unit ID と紐付け):

```html
<div class="yoshi-ad yoshi-ad--sidebar-top" data-ad-slot-id="sidebar-top">
  <!-- AdSense 復活時にここに ins.adsbygoogle を差す -->
  <div class="yoshi-ad__placeholder" aria-hidden="true"></div>
  <div class="yoshi-ad__fallback">
    <!-- 自社導線(関連記事 / X follow / newsletter) -->
  </div>
</div>
```

## ad-off 時の見え方(default 状態、AdSense 復活前)

- **slot 1(sidebar top)**: 高さ 0 で完全 collapse、または 小さな X follow CTA(`yoshi-ad__fallback`)を表示
- **slot 2(article bottom)**: 高さ 0、related posts と本文の間に余分な余白を作らない
- **slot 3(mobile inline)**: mobile 表示時のみ、collapse(空)or 小さな関連 1 行
- **共通**: `:empty` selector で 空 placeholder を CSS で隠す(JS 不要)

ユーザー体験:
- ad off の今、site visitor は ad slot の存在に **気づかない**(白箱が残らない)
- ad on になった瞬間、自然な位置に広告が現れる(layout shift 最小)

## 後で AdSense を差し込む接続面(future ticket: 087-A)

将来 AdSense 復活時に必要になる作業(本 ticket では **やらない**):

| 段階 | 内容 | 担当(将来) |
|---|---|---|
| 087-A.1 | AdSense account 登録 / 審査 / publisher ID 取得 | user |
| 087-A.2 | ad unit ID を slot 1/2/3 ごとに発行 | user |
| 087-A.3 | `data-ad-slot-id` と AdSense unit ID の mapping を `wp_options` or front config に保存 | front Claude |
| 087-A.4 | `ins.adsbygoogle` snippet を slot wrapper 内に inject(PHP filter or shortcode) | front Claude |
| 087-A.5 | consent banner(GDPR / 個情報法)実装 | user 判断 + front Claude |
| 087-A.6 | privacy policy 更新 | user |
| 087-A.7 | live test 1 slot で 24h 観測 → fill rate / RPM 確認 | user |

→ 087-A は AdSense 復活判断時に別 ticket 起票。本 087 で作る wrapper / class 命名 / `data-ad-slot-id` 属性が **AdSense ad unit ID を紐付ける接続面** になる。

## acceptance(本 ticket、front 実装)

1. desktop で右カラム広告枠(slot 1)が自然に表示(ad off でも崩れない)
2. 記事下広告枠(slot 2)が本文 → related posts の流れを壊さない
3. mobile 390px で崩れない(slot 1 は隠れる、slot 2 は responsive、slot 3 は inline)
4. ad-off 時に **白い空箱を残さない**(`:empty` collapse or soft fallback で置換)
5. 063 系 front 非回帰(plugin live / 追加 CSS / front_top hub / Phase 1 noindex 維持)
6. 実 ad snippet なしでも site が成立する(`ins.adsbygoogle` 等を入れずに本 ticket close 可能)
7. CSS class 命名規則(`.yoshi-ad--sidebar-top` 等 + `data-ad-slot-id`)に準拠、後で AdSense ID を differential で差せる

## 不可触

- **backend lane 全部**(`src/` Python 全て、特に `rss_fetcher.py` / `run_notice_fixed_lane.py` / `draft_body_editor.py` / 070-086 系 module)
- **automation.toml** / scheduler / secret / env / X API
- **AdSense 実コード**(`ins.adsbygoogle` / GPT / 自動広告 snippet)
- account / publisher ID / ad unit ID(scope 外、087-A で扱う)
- consent / privacy policy(scope 外、087-A.5/.6)
- 060-086 contract 本体
- baseballwordpress repo
- backend lane Claude 担当の handoff doc(`docs/handoff/master_backlog.md` / `current_focus.md` / `session_logs/` 編集は backend Claude のみ)

## stop 条件

- AdSense 実コード / publisher ID / ad unit ID を実装に混ぜそうになった → stop、scope 外
- backend lane(`src/` Python)に diff が出る → stop、scope 違反
- 063 系 layout が壊れる兆候 → stop、回帰
- consent banner 議論が出る → 087-A に持ち越し

## 完了時の handoff

- front Claude 側で commit + push(本 ticket は front Claude owner)
- backend lane Claude 通知不要(disjoint scope)
- 087-A の起票判断は AdSense 復活時に user

## 補足: backend lane との分離

本 ticket は **完全に front lane 内で閉じる**。backend Claude(070-086 系の owner)は本 ticket の進捗を block しない / されない。並走可。
