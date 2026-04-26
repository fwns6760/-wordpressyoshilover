# 062 — comment-first topic hub contract(のもとけ式巡回感の土台)

**フェーズ：** のもとけ型再訪導線の「巡回感」contract(047 の次、061 の前)
**担当：** Claude Code(contract owner、Codex 便なし)
**依存：** 047 accepted(postgame 連鎖 impl、Draft 本数増の土台)、060 SNS contract(並走)
**状態：** CONTRACT READY(doc-only、impl 便は 047 accept 後に別番号で切る)

---

## why_now

- 047 で postgame 連鎖を impl すると、1 試合から派生記事が複数出て Draft 本数は増える。しかし記事単体が増えるだけでは「のもとけ式の巡回感」は作れない。
- user 固定優先順位(2026-04-22): **047(記事の枝を増やす)→ 062(巡回感を作る)→ 060 並走 → 061 後ろ**。巡回感 = 「読者が 1 つの話題から別の話題へ自然に辿れる導線」。
- 現状のサイトは記事単体 + カテゴリ導線のみで、話題ハブ / コメント連動 / SNS 反応要約が無い。
- 本 ticket は impl ではなく **contract** として「何を hub とするか / コメントをどう扱うか / SEO をどう段階的に作るか / 独立掲示板をいつまで後回しにするか」の政策を先に固定する。
- impl 便は 062 accept + 047 accept 後に別番号で切る(062 を front 実装 ticket 化しない)。

## purpose

- **comment-first topic hub** の運用契約を固定する。
- トップ中央に「話題 hub(記事の話題を束ねる切り口)」を置き、記事 → hub → 他記事 → コメント の巡回導線を作る政策を決める。
- 記事下コメントを「記事ごとのスレ」として扱い、独立掲示板は後回しにする境界を固定する。
- SEO は段階制で、**本体記事が主役 / コメントは補助 UGC** の序列を確定する。
- 自動化 / impl / theme 書換は本 ticket 範囲外。impl 便は後続番号で切る。

## scope

### 1. comment-first の定義

- **コメント = 記事ごとのスレ**として扱う(記事と分離した独立掲示板にしない)
- コメントは記事の延長線で読まれる UGC、記事本体の fact と分離しない
- コメント内の fact 引用 / 出典言及は記事本体の trust 体系に従う(028 T1 / 037 pickup boundary)
- 記事下のコメント欄で 5 件以上の反応が積み上がった記事は、トップ中央 hub の候補に昇格する(次節)

### 2. トップ中央 topic hub の運用契約

- **位置**: トップページ中央、ヒーロー / カテゴリ一覧の下、最新記事リストの上
- **構成**: **話題切り口**(例: 「今週の主役 = 坂本勇人」「阿部監督の采配議論」「育成枠からの昇格」)を 3-5 件表示
- **話題の源泉**(segment by segment):
  - 047 で生成された派生記事群(主役選手 / 監督コメント / transaction / データ)のタグ集約
  - 記事下コメント反応の積み上げ(5 件以上)
  - 公式 X / 中の人 X の反応(`060` primary trust 条件合致時のみ、quote / reshare)
- **更新頻度**: **手動のみ**(Claude の weekly 観測 + user 裁量)。自動化は 062 非目標
- **SEO 狙い**: 話題 hub = サイト内循環の中継点であって、**hub 自体を SEO 主役にしない**(主役は本体記事)

### 3. 記事下 SNS 反応要約 + リンク

- **位置**: 記事下、コメント欄の上
- **構成**:
  - 公式 X(ヨシラバー公式)の該当 post リンク(`060` primary trust post のみ)
  - 中の人 X(user 個人)の該当 post リンク(published 記事のみ、Draft URL 禁止)
  - 外部 X(主要媒体 / ファン反応)の引用は **oEmbed のみ**(CLAUDE.md §18 準拠、コピー転載禁止)
- **要約**:
  - SNS 反応の要約文は Claude / Codex で自動生成しない(本 ticket では手動のみ)
  - 将来自動化するかは 062 accept 後の別 ticket で判断
- **表示条件**: 該当記事に公式 X / 中の人 X post が存在する時のみ表示(無い記事では空 block 表示しない)

### 4. 独立掲示板の後回し契約

- **位置づけ**: 独立掲示板(5ch 型 / なんJ 型の独立スレッド UGC)は **後回し**
- **後回しの理由**:
  - モデレーション負荷が user SPOF(1 人運営)に過大
  - 本体記事主役の SEO 序列を崩すリスク
  - 062 段階ではコメント 1 本で記事下スレとして運用できる
- **いつ解除するか**: **独立 contract(例えば 073 等)で後続起票**。062 では解除条件を決めない(先走り防止)
- **062 では実装 / 設計 / ticket 化しない**

### 5. SEO 段階制(本体記事主役 / コメント補助 UGC)

- **Phase 1(現在、Draft 中心期)**: SEO は本体記事のみ、コメント / hub は index 対象外
  - `noindex` or canonical 統制で hub / コメント領域を検索 index から外す
  - 本体記事の title / meta / 構造化データは既存 SWELL 設定を維持
- **Phase 2(published 週 10 記事 2 週連続達成時)**: トップ中央 hub を緩く index 許可
  - hub は本体記事への導線として、重複コンテンツ扱いにならない範囲で index
  - コメントは依然 `noindex`(UGC のため)
- **Phase 3(published + コメント反応が安定した時)**: コメントも一部 index 許可
  - ただし自動生成 / スパム / 短文の低品質コメントは自動 `noindex`
  - 判定基準は別 ticket(Phase 3 impl 時に固定)
- **Phase 4 以降**: 独立掲示板の判断を別 contract で(062 scope 外)

### 6. 047 / 060 / 061 との関係

- **047 との関係**: 047 で派生記事が増える = 062 hub の話題源泉が増える。047 accept が 062 impl の前提
- **060 との関係**: 060 SNS contract は公式 / 中の人 X の運用契約、062 は記事下 SNS 反応表示の運用契約。**非重複**
- **061 との関係**: 061 = published 自動投稿 X API 実装、062 = site 内 comment / hub。**独立並走**、互いの gate に影響しない

### 7. 不可触

- WordPress published 書込(Phase 4 まで禁止、本 ticket と独立)
- SWELL theme の構造変更(本 ticket は contract のみ、impl 便は後続番号)
- コメント欄の既存 SWELL 設定(Phase 1 では触らない)
- 028 T1 / 037 pickup / 046 first wave / 047 postgame chain impl(本 ticket は front 側契約、src 側に diff なし)
- 060 SNS 2 アカ contract(並走、062 は front 側)
- automation.toml / scheduler / env / secret / quality-*

## non_goals(2026-04-22 明示)

- **impl 便の起票**(062 は contract のみ、impl は後続番号で別便)
- **独立掲示板の設計 / 実装 / ticket 化**(後回し契約、別 contract で後続)
- **SNS 反応要約の自動生成**(Phase 1 は手動のみ、自動化は後続 ticket)
- **SWELL theme の書換**(Phase 1 は既存設定維持)
- **hub の自動生成 / 自動更新**(手動のみ、自動化は後続 ticket)
- **コメント欄の独立 DB 化 / forum 化**(WP native comment を使う、独立 backend を作らない)
- **SEO 自動最適化 / structured data 追加**(Phase 1 は既存 SWELL 設定のみ)
- **外部 SNS(Instagram / TikTok / YouTube / Bluesky / Threads)への拡張**(062 は X のみ、他 SNS は別 contract)

## success_criteria(3 点 contract)

**一次信号(accept 根拠)**

- **着地**: `doc/062-comment-first-topic-hub.md` が正本として working tree に存在(Claude 管理で commit は不要、60 と同じ運用)
- **挙動**: user が「何を hub に出すか / コメントをどう扱うか / SEO をどう段階で開けるか / 独立掲示板をいつ開けるか」を本 ticket 読むだけで判断可能
- **境界**: 047 / 060 / 028 / 037 / 046 / automation / published / SWELL theme に diff なし

**二次信号(事後記録、accept 根拠にしない)**

- 047 accept 後、062 contract に基づいて impl 便(例えば 063 等)を起票可能な状態になる

## acceptance_check(自己追認)

- `doc/062-comment-first-topic-hub.md` が存在
- comment-first の定義が 記事ごとのスレ = WP native comment と明記(独立掲示板否定)
- トップ中央 hub の構成(話題切り口 3-5 件 / 更新頻度手動)が明記
- 記事下 SNS 反応の表示条件(公式 / 中の人 X 存在時のみ)が明記
- SEO 段階制 4 Phase が明記
- 独立掲示板後回しの理由 + 解除は別 contract が明記
- non_goals で impl 便 / 独立掲示板 / 自動要約 / SWELL 書換 が明示否定
- 047 / 060 / 061 との関係が明記
- SWELL theme / published に diff なし

## 本 ticket の運用

- **Claude Code**: 本 contract の維持、047 accept 後に 062 impl 便(別番号)の起票可否を判断
- **user**: 本 contract に従って hub の話題切り口を weekly 手動更新、記事下 SNS 反応の掲載可否判断
- **Codex 便**: **なし**(本 ticket は doc-only、impl は後続番号で別便)
- **ChatGPT 役**: 会議室で SEO 段階制 / 独立掲示板解除条件の相談が必要な時だけ

## 旧 ticket との関係

- **017 home-game-hub**: トップ中央の今日の試合ブロック contract(E2)、062 と役割分離(017 = 試合ブロック / 062 = 話題 hub)
- **018 player-topic-navigation**: 選手タグ軸の回遊 contract、062 の話題 hub と補完(選手軸 vs 話題軸)
- **060 SNS contract**: 公式 / 中の人 X の運用契約、062 = 記事下 SNS 反応表示、**非重複**
- **061 自動投稿**(止め): 062 と独立並走、062 が先行
- **047 postgame chain impl**: 062 hub の話題源泉を供給、047 accept が 062 impl の前提

## fire 前提 / stop 条件

### fire 前提(contract ticket として)

- **047 accept**(47 postgame chain impl 便の 3 点 contract pass 後、別番号で 062 impl 便を切れる状態)
- **060 accept 継続**(SNS 反応表示が 060 contract 準拠で成立、並走)

### stop 条件

- 062 で impl / 自動化 / SWELL 書換に進もうとした時(contract のみに留める)
- 独立掲示板の設計 / 実装 / ticket 化に進もうとした時(別 contract まで後回し)
- 記事本体の SEO 主役序列を崩す hub 設計(本体記事主役を守る)
- Draft URL / preview URL / private URL の hub / コメント表示(060 contract 違反)
- 047 accept 前に 062 impl 便を起票する
