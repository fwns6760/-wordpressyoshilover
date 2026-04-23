# 063 — 062 comment-first topic hub impl(front 実装在庫)

**フェーズ：** 062 contract の impl 便(063-V1/V2 close、063-V3 in progress)
**担当：** `Codex front lane`(2026-04-24、063-V2 live smoke pass 後に V3 着手)
**依存：** 062 accepted(contract doc 確定、2026-04-22)、047 accepted(`da692fc`、派生記事 emit 層着地、062 hub の話題源泉供給成立)
**状態：** `063-V1 ACCEPTED / CLOSE`(2026-04-24、deploy + WP 実機 smoke 5/5 pass)、`063-V2 ACCEPTED / CLOSE`(2026-04-24、一覧 density live 反映 + E-2 re-smoke pass)、`063-V3 IN PROGRESS`(トップ速報帯 + 記事下回遊束、local impl)

---

## 2026-04-24 V1 close memo

- plugin live 反映済み: `src/yoshilover-063-frontend.php`
- SWELL 追加 CSS 反映済み: `src/custom.css` の 063 セクション
- topic hub は `(a)` で確定: SWELL `front_top` = 「トップページ > 記事一覧上のコンテンツ」に `[yoshilover_topic_hub]` を配置
- 検証用 meta 投入後、WP 実機 smoke `E-1〜E-5` は **all pass**
- robots / noindex は `<meta name="robots">` 1 本に統合されることを実測確認
- 063-V2 は未着手のまま切り分け済み。次は **トップ一覧の情報密度強化** に進む

## next

- 063-V3 はトップ速報帯 + 記事下回遊束に限定する
- V1/V2 の配置方針 `(a)`、plugin live、追加 CSS、Phase 1 noindex、front density の挙動は維持する
- route / pickup / validator / automation / scheduler / env / secret / published 書込経路は引き続き不可触

## 2026-04-24 V2 implementation memo

- `src/yoshilover-063-frontend.php` に home/front 専用の front-density patch を追加
- 一覧カードに `subtype badge / phase / score / 要約 1 行` を後付けする
- `live_update` は同日・同対戦相手の並びを数え、`連投 n本` chip を補助表示する
- 判定は plugin 内に閉じ、`src` route / pickup / validator は不可触のまま維持
- `src/custom.css` に一覧カード向け V2 style を追加
- local verify は `php -l src/yoshilover-063-frontend.php` pass
- live deploy は **pending**。今回の環境では Xserver / plugin upload の自動経路が未確認

## 2026-04-24 V3 implementation memo

- `src/yoshilover-063-frontend.php` に `yoshilover_breaking_strip` shortcode を追加
- top front では `試合中 / スタメン / 公示 / 予告先発 / 試合後` の最新 5 件前後だけを高密度に束ね、空なら非表示
- `src/yoshilover-063-frontend.php` に `yoshilover_article_bundles` shortcode + `the_content` filter を追加
- 記事下は `同じ試合 / 同じ選手 / 同じ話題` の 3 束を最大 3 件ずつ出し、空束は描画しない
- 挿入順は `本文末尾(既存 related 含む) -> SNS block -> 回遊束 -> SWELL share/comments` を維持する
- `set_front_top_widget_stack` admin helper を追加し、`[yoshilover_breaking_strip]` と `[yoshilover_topic_hub]` を front_top に直列配置できるようにする
- `src/custom.css` は速報帯 / 回遊束 style を追加し、SWELL に馴染ませつつ情報密度だけ上げる
- `scripts/build_063_wp_admin_bundle.py` は plugin header version から `build/063-v3-wp-admin/` を自動生成するよう更新

---

## why_now

- 062 contract は doc-only で front に何も反映されない。hub / コメント運用 / 記事下 SNS 反応 / SEO 段階制は文書で固定済みだが、SWELL theme / front component / 記事 template に書換が 1 行も入っていない。
- 047 accept(`da692fc`)で派生記事 emit 層が着地、062 hub の話題源泉(主役選手 / 監督コメント / transaction / データ派生)が src レベルで生成できる状態になった。契約と impl の gap を front 側に残さない。
- user 固定優先順位 047→062→060→061(2026-04-22)に従い、047 accept 直後の impl 便在庫補充として本 ticket を起票。
- 062 自体の non_goals「impl 便の起票」は 062 contract 内の制約で、impl 便は別番号で切る運用。本 ticket は 062 §本 ticket の運用「Claude Code: 047 accept 後に 062 impl 便(別番号)の起票可否を判断」を履行する。
- 本 ticket は **起票は今やる、fire は owner / 実装経路が固まってから**(2026-04-22 user 指示)。fire 前提の「front 実装 lane 決定」までは QUEUED 維持。
- 2026-04-23 方針: **X 手動開始の前提にしない**。063 はのもとけ式の巡回感を強める後続デザイン改修であり、060 に基づく manual X 運用は 063 未実装でも開始できる。

## purpose

- 062 contract §2(トップ中央 topic hub)/ §3(記事下 SNS 反応表示)/ §5(SEO 段階制 Phase 1)を front 側に最小 impl で反映する在庫を確保する。
- owner 決定 + 実装経路確立(SWELL theme 書換 or front component 追加 or WP block 新設のいずれ)までは fire しない。doc として in-memory に持つ。
- Codex A / Codex B を無理に割り当てない。front 実装は src ではないため、既存 lane の scope 越境を避ける。
- X 投稿開始後の回遊導線を補強する。トップ中央 topic hub / 記事下 SNS 反応 block / Phase 1 noindex を優先し、コメント欄は既存 SWELL 設定を維持する。

## scope

### 1. トップ中央 topic hub(062 §2 impl)

- **位置**: トップページ中央、ヒーロー / カテゴリ一覧の下、最新記事リストの上
- **構成**: 話題切り口 3-5 件表示(例: 「今週の主役 = 坂本勇人」「阿部監督の采配議論」「育成枠からの昇格」)
- **源泉**: 047 派生記事群(`postgame_revisit_chain.py` emit)のタグ集約 + コメント反応 5 件+ 積み上げ + 公式/中の人 X primary trust post の 3 源泉
- **更新**: **手動のみ**(062 contract §2 準拠、Claude weekly 観測 + user 裁量)。自動化は本 ticket 非目標
- **実装候補**(owner 決定時に選択):
  - (a) SWELL theme の widget 追加(front lane だが SWELL 書換スキル必要)
  - (b) WordPress block editor 新規 block(front + WP block API)
  - (c) front 静的 component(theme template override、CSS+HTML 主体)
- **SEO**: 062 §5 Phase 1 に従い、Phase 1 期間中は `noindex` 維持、本体記事主役を崩さない

### 2. 記事下 SNS 反応表示(062 §3 impl)

- **位置**: 記事下、コメント欄の上
- **構成**:
  - 公式 X(ヨシラバー公式)の該当 post リンク(060 primary trust post のみ、oEmbed)
  - 中の人 X(user 個人)の該当 post リンク(published 記事のみ、Draft URL 禁止)
  - 外部 X 引用は oEmbed のみ(CLAUDE.md §18 準拠、コピー転載禁止)
- **表示条件**: 該当記事に公式 / 中の人 X post が存在する時のみ(無い記事では空 block 非表示)
- **要約**: 手動のみ(062 契約、自動生成は本 ticket 非目標)
- **実装候補**: article template 末尾の後置 block(SWELL theme hook or theme template override)

### 3. コメント欄(062 §1 = 記事ごとのスレ、独立掲示板否定)

- **実装**: 既存 SWELL コメント設定を維持(062 §7 不可触準拠、Phase 1 は触らない)
- **本 ticket 非目標**: 独立掲示板 / forum 化 / コメント独立 DB(062 §4 後回し契約)

### 4. SEO 段階制 Phase 1(062 §5 impl)

- hub / コメント領域を `noindex` or canonical 統制で検索 index から外す
- 本体記事の title / meta / 構造化データは既存 SWELL 設定を維持
- Phase 2 以降の index 許可は別 ticket(062 §5 Phase 2-4)

### 5. 不可触

- `src/**`(047 派生 emit / 046 first wave / 028 T1 / 037 pickup / Codex A/B 全領域、本 ticket は front 側のみ)
- `automation.toml` / scheduler / env / secret / quality-gmail / quality-monitor / draft-body-editor
- 028 T1 / 037 pickup / 046 first wave / 047 派生 / 040 repair / 036 prompt
- 060 SNS contract(並走)
- 062 contract 本体(本 ticket は 062 の impl、contract 側を書換えない)
- WP published 書込(Phase 4 まで禁止、本 ticket は theme / front 表示層のみ)
- 既存 SWELL コメント設定(062 §7 不可触準拠)

## non_goals(2026-04-22 明示)

- **fire(実装着手)**: owner / 実装経路が固まるまで QUEUED 維持
- **自動化 / 自動更新 / 自動生成**(hub 話題切り口 / SNS 反応要約 / コメント積み上げ判定、すべて手動)
- **独立掲示板の impl**(062 §4 後回し契約、別 contract で後続起票)
- **SEO 自動最適化 / structured data 追加**(Phase 1 は既存 SWELL 設定のみ)
- **外部 SNS(Instagram / TikTok / YouTube / Bluesky / Threads)への拡張**(062 §non_goals 準拠)
- **src 側の書換**(047 派生 emit / 046 first wave / 028 / 037 に diff を入れない)
- **Phase 2 以降の SEO index 許可 impl**(062 §5 Phase 2-4 は別 ticket)
- **新 external dep / 新 API client**(既存 SWELL + WordPress 標準機能で完結させる)
- **新 subtype / 新 route**(src 側不可触、062 contract で既に定義済みの概念のみ front 化)

## success_criteria(3 点 contract、fire 後に適用)

**一次信号(accept 根拠)**

- **着地**: `git log -1 --stat` で SWELL theme / front template / CSS / JS の追加のみ、`git status --short` clean。src/ 側に diff 0
- **挙動**: トップ中央 hub が 3-5 件手動表示される / 記事下 SNS 反応 block が公式 or 中の人 X post 存在時のみ表示される / Phase 1 `noindex` が hub + コメント領域に効いている
- **境界**: src/ / automation / 060 contract / 062 contract / 047 派生 emit / 046 first wave / 040 / 036 / WP published 書込すべて zero diff

**二次信号(事後記録、accept 根拠にしない)**

- 062 Phase 2 昇格条件(published 週 10 記事 2 週連続達成)観測時に本 ticket impl の `noindex` 解除を別 ticket で判断可能な状態になる

## acceptance_check(fire 後に自己追認)

- `git diff HEAD~1 -- src/` で差分 0(src 不可触)
- `git diff HEAD~1 -- automation.toml` で差分 0
- `git diff HEAD~1 -- doc/062-comment-first-topic-hub.md` で差分 0(contract 本体不可触)
- `git diff HEAD~1 -- doc/047-postgame-revisit-chain-impl.md` で差分 0(047 impl 不可触)
- `git diff HEAD~1 -- doc/060-sns-dual-account-draft-era-bridge.md` で差分 0(060 contract 不可触)
- WP published 書込経路が呼ばれていない(theme / front 表示層のみ)
- 3-5 件の hub 話題切り口が手動表示される動作確認
- 記事下 SNS 反応 block が条件付き表示(公式 or 中の人 X post 存在時のみ)される動作確認
- `noindex` が hub + コメント領域に効いていることを HTML meta で確認

## fire 前提 / stop 条件

### fire 前提(本 ticket は起票のみ、fire は owner 決定後)

- **owner 決定**: `front 実装 lane (TBD) / owner pending` → 具体的な実装 lane(SWELL 書換担当 / WP block 担当 / front component 担当 のいずれか)を user + Claude Code で固定
- **実装経路確立**: (a) SWELL widget / (b) WP block / (c) front 静的 component のどれで実装するか決定
- 062 accepted(達成)
- 047 accepted(`da692fc`、達成)
- 060 CONTRACT ACTIVE 継続(達成、並走)

### stop 条件

- 062 contract 本体への diff(contract 変更は別便)
- 047 派生 emit 経路への diff(src 不可触)
- 046 first wave / 028 T1 / 037 pickup / 040 / 036 への diff
- automation.toml / scheduler / cron 登録
- WP published 書込
- 独立掲示板の impl / forum 化 / コメント独立 DB
- Phase 2 以降の SEO index 許可 impl(本 ticket は Phase 1 のみ)
- 新 external dep / 新 API client

## TODO(起票時点、fire 後に進める)

【×】owner 決定(front 実装 lane specific name、user + Claude Code で固定)
【×】実装経路決定((a) SWELL widget / (b) WP block / (c) front static component)
【×】トップ中央 hub(3-5 件手動表示、Phase 1 `noindex`)の impl
【×】記事下 SNS 反応 block(公式 / 中の人 X oEmbed、条件付き表示)の impl
【×】SEO Phase 1 `noindex` の hub + コメント領域への適用
【×】src / automation / 062 contract / 047 impl / 060 contract 不可触の確認
【×】WP published 書込経路を触らない確認
【】063-V2: トップ一覧の情報密度強化(一覧カード / meta / 視認性の改善、V1 挙動維持、local impl 済 / live deploy pending)
【】doc/README.md に 063 行追加を cleanup commit で吸収

## 本 ticket の運用

- **Claude Code**: owner 決定まで QUEUED 維持、owner 決定後は fire 便 prompt を作成(本 ticket は contract + 在庫、impl 時に Codex / front 担当者へ prompt 化)
- **user**: owner 決定 / 実装経路選択 / fire 判断
- **Codex 便**: **未定**(front 実装が src ではないため、Codex A/B どちらも scope 外。front 実装 lane が固まった時点で Codex にするか、user 手動にするか、別 lane を立てるかを判断)
- **ChatGPT 役**: owner / 実装経路の選択で会議室相談が必要な時だけ

## 旧 ticket / 関連 ticket との関係

- **062 contract**: 本 ticket の親 contract。062 contract §2 / §3 / §5 を front 側に impl するのが 063 の scope
- **047 postgame 連鎖 impl**: 062 hub の話題源泉を src 側で供給(`da692fc` 着地)、本 ticket で front 化
- **060 SNS contract**: 公式 / 中の人 X 運用契約、本 ticket の記事下 SNS 反応表示の政策元
- **061 自動投稿**(止め): 062 / 063 と独立、060 gate pass まで止まる
- **046 first wave**: 4 家族 fixed_primary 昇格、062 hub の話題源泉の一部(postgame 以外)
- **048 repair playbook ledger 連携**: Codex B 補修線、本 ticket と独立
- **017 home-game-hub**: トップ中央の試合ブロック contract(E2)、062 / 063 と役割分離(017 = 試合ブロック / 063 = 話題 hub)
- **018 player-topic-navigation**: 選手タグ軸の回遊 contract、063 と補完(選手軸 vs 話題軸)
