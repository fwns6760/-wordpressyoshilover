# 455 DATA-SITE redesign — サイトマップ / トピクラ導線 / ワイヤーフレーム / UI-UX

作成: 2026-06-01 / 親: 443 DATA-SITE / GH Issue: #119 / 前提資料: `doc/reference/model-site-page-inventory.md`(モデル A=my-favorite-giants, B=baseballdata.jp 全ページ網羅目録)
目的: 「今はひどい」現行データサイトを、トピッククラスタ構造 + 鮮度 + 専用レイアウトで再設計する。本 doc は設計の正本。実装は phase 分けで別 ticket 化。

---

## 0. 現状診断(実取得 2026-06-01・推測なし)

- `/data/`(cluster索引): 専用レイアウト、パンくず、ポジション別 選手一覧テーブル(背番号順)、「毎朝6時更新」明記。**弱点**: 選手検索なし / ポジション・成績フィルタなし / スマホ折返し不明 / 多数の選手が成績「–」。
- `/data/sakamoto-hayato/`(pillar): **致命的** — 「box score 未確認」でデータ実質ゼロ、今季通算表すら空、split(打順/vs球団/イニング/直近5)全欠落、グラフ無し、写真1枚。**関連記事20件がデータより充実=逆転構造**。WP標準記事テンプレ流用に見える。
- → 問題は2層: (1) **データが populate していない**(data-insight/data-site lane、447 Phase A ETL が BLOCKED)。(2) **レイアウトが記事テンプレ流用**でデータが主役になっていない。**(1) が直らないとワイヤーは絵に描いた餅**。実装順は「データ供給の確立 → 専用レイアウト → split拡張」。

---

## 1. サイトマップ(IA ツリー)

```
/data/ ← データサイト HUB(玄関・検索・今日の注目)
│
├─[PILLAR] 選手ページ  /data/{slug}/         ← トピックの核(evergreen・SEO主役)
│    例 /data/sakamoto-hayato/
│
├─[CLUSTER索引] 選手一覧
│    ├─ /data/batters/     野手一覧(ポジション別)
│    ├─ /data/pitchers/    投手一覧(先発/中継ぎ/抑え)
│    └─ /data/farm/        2軍・育成
│
├─[TEAM] チーム
│    ├─ /data/standings/   セ・リーグ順位表(鮮度)        [454 ETL]
│    ├─ /data/team/        チーム打撃/投手/守備 集計       [454 ETL]
│    └─ /data/schedule/    日程・結果
│
├─[RANKING] 球団内ランキング
│    ├─ /data/ranking/             指標HUB
│    └─ /data/ranking/{metric}/    OPS / HR / 防御率 / 直近5試合HOT …
│
└─[読み物 CLUSTER] ファン訴求(yoshilover独自・モデルA由来)
     ├─ /data/walkoff/      サヨナラ本塁打DB(試合データ派生)
     ├─ /data/milestone/    節目記録(自動検知)
     └─ /data/glossary/     用語集
```

階層は2クリック以内: HUB → (cluster索引 / team / ranking / 読み物) → pillar。

---

## 2. トピッククラスタ導線(★最重要・今の最大の穴)

pillar(選手ページ)= topic hub。通常記事(postgame/lineup/data-insight)= cluster content。三方向の内部リンクで topical authority と回遊を作る。

```
        ┌─────────────────────────────────────┐
        │   PILLAR: /data/sakamoto-hayato/     │  1選手1ページ(恒久・SEO核)
        │   今季成績 / split / 直近5試合         │
        └──▲─────────────▲──────────────▲─────┘
           │             │              │
   ① 記事→Pillar    ② Pillar→記事    ③ Pillar⇄Pillar
           │             │              │
  ┌────────┴───┐  ┌──────┴──────┐  ┌────┴──────────┐
  │CLUSTER記事  │  │その選手の    │  │同ポジション    │
  │postgame/    │  │関連記事一覧  │  │/対戦相手選手   │
  │lineup/data  │  │(最新N件・下部)│  │のpillar       │
  │「坂本の…」  │  └─────────────┘  └───────────────┘
  └─────────────┘
        │
   記事の冒頭/末尾に固定リンク
   「📊 坂本勇人のデータを見る →」(entity→slug 自動挿入)
```

- **① 記事 → pillar(今切れている最大の穴)**: postgame 等の本文に、登場選手の pillar 固定リンクを entity→slug マップで自動挿入。
- **② pillar → 記事**: pillar 下部に「この選手の関連記事」最新N件。**ただしデータを上・記事を下**(今は逆転)。
- **③ pillar ⇄ pillar**: 同ポジション / 当日対戦相手の pillar へ横回遊(サイドバー)。
- 補助: cluster索引(/data/batters/)⇄ pillar(パンくず往復)、ranking → pillar。

---

## 3. ワイヤーフレーム

### 3-A. 選手 Pillar(PC)

```
┌────────────────────────────────────────────────────────────┐
│ [ロゴ]ヨシラバー    [全て][試合速報][選手情報][データ▾]      │ global nav
├────────────────────────────────────────────────────────────┤
│ HOME > データ > 内野手 > 坂本勇人       🕖 6/01 06:00更新    │ パンくず+更新日
├──────────────────────────────────┬─────────────────────────┤
│ [顔写真] 坂本 勇人 #6 遊撃手       │ ▌同じ内野手             │
│ 右投右打 / 1988-12-14 / 37歳       │  岡本/吉川/中山… →pillar│③横回遊
│ ────────────────────────────────  │ ▌対戦中の相手投手       │
│ 〔タブ〕通算│直近5│打順別│vs球団│ │ ▌球団内ランキング       │
│        球場別│イニング│vs左右     │ │  OPS3位/HR5位 →ranking  │
│ ────────────────────────────────  │ ▌用語(OPS/OPS+…)        │
│ ■今季通算(打撃)  標準列フル表      │                         │
│ ■直近5試合 ←鮮度・我々の強み       │                         │
│ ■打順別/vs球団/イニング別 split    │                         │
│ ■📊ひとことインサイト(自動生成)    │                         │
├──────────────────────────────────┴─────────────────────────┤
│ ▌坂本勇人の関連記事(最新8件) [もっと見る→]   ②Pillar→記事   │
│  ・[postgame] 坂本マルチ安打… ・[data] 坂本OPSリーグ3位…    │
├────────────────────────────────────────────────────────────┤
│ [Xでシェア][LINEで送る]   ←記事単位SNS導線(今欠落)          │
└────────────────────────────────────────────────────────────┘
```

### 3-B. 選手 Pillar(スマホ)

```
┌──────────────────┐
│ ☰ ヨシラバー   🔍 │
│ HOME>データ>内野手 │
│ 🕖6/01 06:00更新   │
├──────────────────┤
│   [顔写真]         │
│ 坂本勇人 #6 遊撃   │
│ 右投右打 37歳      │
├──────────────────┤
│[通算][直近5][打順] │ 横スクロールタブ
│[vs球団][球場][左右]│
├──────────────────┤
│■今季通算           │
│┌主要数値カード────┐│ 表でなく主要4指標を
││打率.290 OPS.820  ││ カード優先
││HR12  打点40      ││
│└──────────────────┘│
│[全成績を表で見る▾] │ 詳細表=アコーディオン
├──────────────────┤
│■直近5試合(横スク表)│
│■📊ひとこと         │
│関連記事(最新5)     │
│同ポジ選手 →→→     │
│[Xでシェア]         │
└──────────────────┘
```

### 3-C. /data/ HUB(cluster 索引)

```
┌────────────────────────────────────────────┐
│ HOME > データ           🕖 6/01 06:00更新    │
│ 巨人 選手データ 2026                          │
│ 🔍[ 選手名で検索______ ]      ←検索(今欠落)  │
├────────────────────────────────────────────┤
│ ▌今日の注目(鮮度・毎朝更新の目玉)            │
│  直近5HOT: 坂本.380 / 戸郷防御率1.20 …       │
├────────────────────────────────────────────┤
│ [野手][投手][2軍][チーム][ランキング]  ←cluster導線 │
├────────────────────────────────────────────┤
│ ■内野手  #6坂本 .290/.820 HR12 →[データ]     │
│ ■外野手/捕手/投手 … (ポジション別)            │
├────────────────────────────────────────────┤
│ ▌読み物: サヨナラHR / 節目記録 / 順位表       │
└────────────────────────────────────────────┘
```

### 3-D. チーム/順位(/data/standings/, /data/team/)[454 ETL 前提]

```
┌────────────────────────────────────────────┐
│ HOME>データ>チーム      🕖更新               │
│ ▌セ・リーグ順位 (鮮度)                        │
│  順位 球団 試 勝 敗 分 率 差  …巨人をハイライト│
│ ▌巨人 チーム成績                              │
│  [打撃] 打率/HR/OPS … [投手] 防御率/WHIP …    │
│  [守備] 失策/守備率 …                         │
│ ▌12球団比較(baseline) → 各選手pillarへ        │
└────────────────────────────────────────────┘
```

---

## 4. UI/UX 原則

1. **WP標準記事テンプレ脱却** → pillar/cluster/team で専用 data layout(現状は記事テンプレ流用で関連記事がデータを食う)。
2. **データ上・記事下**: pillar はデータが主役、関連記事は補助として下部。
3. **鮮度を first view に**: 更新日バッジ + 「今日の注目」 + 直近5試合を最上部。
4. **モバイル = 数値カード + アコーディオン + 横スクロール表**: 標準列フル表をそのまま出さない。
5. **空データの扱い**: 「集計中」を明示し、関連記事/前年成績(取得できれば)で空白を埋める(今は真っ白)。
6. **内部リンク三方向を自動生成**(§2)。
7. **全ページ パンくず + 記事単位SNSシェア**。
8. **モデル B から取り込む鮮度発想**: 「調子/最近5試合」列を一覧・pillar に常設(pitch-levelは射程外、§B8)。

---

## 5. データ可用性タグ(設計の現実・推測しない)

| セクション | source | 状態 |
|---|---|---|
| 今季通算・標準列 | batting_logs / advanced_metric_snapshots | ✅ ready(ただし populate 要確認) |
| 直近5試合 | 既存 | ✅ ready(同上) |
| 打順別 / vs球団 / イニング別 | 既存(447 一部 done) | 🟡 一部 ready |
| vs左右 / 球場別 / RISP / 守備 | at_bat_details ETL | ⛔ 447 Phase A BLOCKED |
| 年度別履歴 | 当季のみ | 🔨 **取得可**: NPB career page `bis/players/{id}.html` を scrape(467、「backfill無」は誤り) |
| プロフィール(生年月日/身長体重/経歴) | DB に無い | ❌ source 未確保 |
| チーム順位・成績 | games | 🟡 454 ETL |
| サヨナラHR / 節目記録 | 試合データ派生 | 🟢 新規実装可 |

**前提の前提**: 現 pillar が「box score 未確認」で空 = データ供給自体が止まっている疑い。レイアウト実装の前に **data-site/insight lane が選手ページにデータを流せているかを実機 verify** が最優先。

---

## 6. 実装 phase(案)

- **P0 データ供給確立**: pillar が空の原因(box score 未取得 / 447 ETL)を実機 verify・修復。これが無いと全部空。
- **P1 専用レイアウト + トピクラ導線**: pillar/cluster 専用テンプレ、§2 の三方向内部リンク自動生成、パンくず/更新日/SNSシェア。
- **P2 鮮度 first view**: HUB「今日の注目」、検索、直近5試合 上部固定。
- **P3 split 拡張**: 447 Phase A ETL 解除 → vs左右/球場/RISP/守備。
- **P4 チーム面**: 454 standings/team。
- **P5 読み物**: サヨナラHR / 節目 / 用語集。
- **P6 基本情報**: プロフィール source 確保 → 年度別履歴 backfill。

---

## 7. コンポーネント仕様(UI 部品)

| 部品 | 仕様 | 適用ページ |
|---|---|---|
| 更新日バッジ | `🕖 YYYY/MM/DD HH:MM 更新`。データ generation 時刻を表示。空データ時は `集計中` バッジに切替 | 全 data ページ |
| split タブ | PC=水平タブ / スマホ=横スクロール tab strip。データ未充足の tab は淡色 + `準備中` ラベル(非表示にしない=将来枠を見せる) | pillar |
| 主要数値カード | スマホ first view。打者=打率/OPS/HR/打点、投手=防御率/勝/S/WHIP の4枠。タップで詳細表へ scroll | pillar(mobile) |
| 詳細表アコーディオン | スマホで標準列フル表は折り畳み既定。`全成績を表で見る▾` で展開 | pillar(mobile) |
| 横スクロール表 | 標準列フル表は overflow-x:auto。1列目(項目/日付)を sticky 固定 | 全表(mobile) |
| ひとことインサイト | 自動生成1-2文。data-insight pipeline の既存文体を流用。事故防止のため数値は DB literal、感想は最小 | pillar |
| 関連記事リスト | pillar 下部、最新N件(既定8)。`postgame/lineup/data` の subtype バッジ付き | pillar |
| 横回遊カード | 同ポジション / 当日対戦相手の pillar への顔写真+名前リンク | pillar(side) |
| パンくず | `HOME > データ > {ポジション} > {選手}` 等、全 data ページ共通 | 全 data ページ |
| SNS シェア | 記事/ページ単位 [Xでシェア][LINEで送る]。今欠落 | 全 data ページ |
| 検索ボックス | HUB 上部。選手名(かな/漢字/英)インクリメンタル候補 | HUB |

## 8. SEO / メタ(モデル A の学び反映)

- **URL**: `/data/{romaji-slug}/`(現行踏襲)。意味的・恒久。
- **title 型**: `{選手名} 2026年 成績データ(打率/OPS/直近5試合)｜ヨシラバー` — 「選手名+成績+指標」で検索意図直撃(モデルA の `【歴代選手名鑑】選手名` を鮮度型に発展)。
- **h1**: `{選手名} #{背番号} {守備位置}`。**h2** = 各 section(今季通算/直近5試合/打順別…)で構造化。
- **meta description**: lead 文を本文先頭 = `{選手名}の2026年データ。直近5試合 {打率}、今季 {主要指標}。打順別・対戦球団別・イニング別の split を毎朝更新。`(SEO SIMPLE PACK は本文先頭から自動生成のため lead を先頭に置く=既知挙動 [[reference_seo_simple_pack_ogp_behavior]])
- **OGP image**: pillar = 選手 featured_media(`find_player_featured_media_id` 既存ロジック)。

## 9. トピクラ導線の実装規約(自動生成)

- **① 記事→pillar**: 記事本文の entity(登場選手)を slug に解決し、本文末(または先頭)に `📊 {選手名}のデータ → /data/{slug}/` を自動挿入。entity→slug マップは既存 roster(`config/npb_12team_roster.json` 系)を再利用。**未解決 entity はリンクを出さない**(誤リンク防止)。
- **② pillar→記事**: pillar の関連記事は entity tag / 選手名 一致でクエリ。**データ section より下**に固定配置(逆転構造の解消)。
- **③ pillar⇄pillar**: 同ポジション = roster の守備位置 group、当日対戦相手 = その日の games から相手先発等を解決。
- 不変条件: 既存 publish/mail/X lane は不可触。導線挿入は data-site/記事テンプレ層のみ。

## 10. 受け入れ条件(acceptance)

- [ ] P0: 任意の主力選手 pillar(例 坂本/岡本/戸郷)に **今季通算表 + 直近5試合表が実データで表示**される(空でない)。
- [ ] P1: pillar が **専用 layout**(記事テンプレ流用でない)で、データが上・関連記事が下。パンくず + 更新日バッジ + SNS シェアが全 data ページに存在。
- [ ] P1: postgame 記事に登場選手の `📊データ→` リンクが自動挿入され、pillar へ遷移できる(①導線)。
- [ ] P2: HUB に検索 + 「今日の注目(直近5HOT)」がある。
- [ ] mobile: pillar が主要数値カード + アコーディオン + 横スクロール表で破綻なく表示。
- [ ] split tab のうちデータ未充足分は `準備中` 表示(空表でも 500 でもない)。

## 12. 競合ギャップ分析「何が負けているか」(実スクレイプ 2026-06-01・推測ゼロ)

方法: yoshilover を3班で実スクレイプ(打者6名 / 投手11名 / 構造・ページ存在)。raw HTML(script/style 除去後)で ◯数値/△空/×無 を判定。モデル A/B は `doc/reference/model-site-page-inventory.md`(実クロール)と突き合わせ。

### 12-0. 確定した yoshilover の現状(正確な姿)

- **実在ページは3面のみ**: `/data`(索引・200)、`/data/team`(200・513KB)、`/data/schedule`(200・530KB)。**team/schedule は存在する**(内容は未verify)。`/data/{slug}/` 選手個別は 200。
- **404(面が無い)**: `/data/batters` `/pitchers` `/farm` `/standings` `/ranking` `/walkoff` `/milestone` `/glossary` 全て 404。→ **ランキング面・読み物面・順位面が存在しない**。
- **打者(有データ)**: 通算/直近5/打順別/vs球団/本拠ビジター/序中終盤(イニング3分割)/曜日別/月別/交流戦別 = **全◯**(吉川/丸/大城/中山/キャベッジで確認)。
- **投手(有データ)**: 通算 + 直近登板の **2表のみ**。split は**全部×**(先発救援/球場/vs球団/イニング/vs左右/QS率/被打率/K9 全て無)。戸郷ほか11投手で確認。
- **打者投手 共通で × (サイト全体未実装)**: vs左右 / 球場別 / 得点圏RISP / グラフ / プロフィール(生年月日身長体重出身経歴) / 年度別(過去年)履歴。
- **データ供給ムラ**: 索引 fill率 約70%(捕手50% / 内野56% が低い)、育成38名は数値なし。坂本=「box score未確認」で空、岡本/菅野=MLB離脱で散文のみ。
- **UX**: 検索/フィルタ/ソート 無し、「今日の注目」無し、WP標準ページに静的table流し込み(専用templateでない)、更新日は文言のみ(日付数値なし)。
- **トピクラ導線**: 索引→選手 ◯ / 選手→索引(パンくず)◯ / 選手→関連記事 ◯(縦)。**選手→同ポジ横リンク ×** / **通常記事→選手データ逆リンク ×(=片方向)** / **SNSシェア ×**。

### 12-1. itemized gap(yoshilover vs モデルA my-favorite-giants vs モデルB baseballdata.jp)

| データ軸 | yoshilover現状 | A(MFG) | B(BBD) | 判定 | 負けの種別 |
|---|---|---|---|---|---|
| 鮮度(毎朝更新/直近5試合) | ◯ | △(静的・年集計) | ◯(調子/最近5列) | **勝ち〜互角** | — |
| 打者 split(打順/vs球団/本拠ビジター/イニング/曜日/月/交流戦) | ◯(有データ打者) | ×(無) | ◯(より細かい) | **A に勝ち / B に互角** | — |
| 投手 split(先発救援/球場/vs球団/イニング) | ×全欠落 | △(年集計のみ) | ◯(個別ページ充実) | **負け** | 未実装 |
| vs左右(打者・投手) | × | △(限定) | ◯ | **負け** | 447 ETL BLOCKED |
| 球場別 / 得点圏RISP | × | ○(球場別勝敗等) | ◯ | **負け** | 447 ETL BLOCKED |
| 標準通算成績(打者/投手) | ◯(有データ) | ◯ | ◯ | 互角 | (fill率70%は要改善) |
| SABR(OPS+/wOBA/FIP/RC/XR/BABIP等20指標) | ×(OPS止まり) | ×(counting中心) | ◯(個別ランキング) | **B に負け** | 未実装 |
| pitch-level(配球/球種別/ゾーン/球速) | × | × | ◯(日次dashboard) | **B に負け** | source無(射程外) |
| 選球眼/得点差別/殊勲打 | × | × | ◯ | **B に負け** | 未実装 |
| プロフィール(生年月日/身長体重/出身/経歴) | ×(MLB離脱者の散文のみ) | ◯(全選手) | △ | **A に負け** | source無 |
| 年度別・通算の履歴(過去年) | ×(当季のみ) | ◯(1936-) | ◯(2011-) | **負け→取得可** | NPB career page で取得可(467、source確定済) |
| 球団内/リーグ ランキング面 | ×(/ranking 404) | ◯ | ◯ | **負け** | 面未実装 |
| チーム順位・成績・日程 | △(team/schedule は200・内容未verify) | ◯ | ◯ | 要verify | 454 |
| 歴史網羅(歴代在籍/ドラフト/タイトル/記録) | × | ◯(圧倒的) | △ | **A に負け** | 非スコープ(追わない) |
| 読み物(サヨナラHR/節目/トリビア/応援歌) | × | ◯(豊富) | ×(データのみ) | **A に負け** | 面未実装 |
| グラフ・可視化 | × | × | △(配球チャート) | **B にやや負け** | 未実装 |
| 検索/フィルタ/ソート UX | × | △(検索のみ) | ◯(指標別ソート) | **負け** | UX未実装 |
| トピクラ内部リンク(記事↔pillar双方向) | ×(片方向) | △(試合↔選手リンク切断) | △ | **両者とも弱いが我々も負け** | 導線未実装 |
| SNSシェア(記事単位) | × | × | × | 互角(全員弱い)→**先取りの好機** | — |

### 12-2. 「負けている」要点(優先度順)

1. **投手 split が丸ごと無い**(打者はあるのに投手は通算+直近のみ)= 最大の非対称な穴。**未実装、ETL前提でなく集計ロジックの横展開で解ける可能性**(打者 split が動いている=同型を投手へ)。
2. **vs左右 / 球場別 / RISP が打者投手とも無い** = 447 Phase A ETL(`batter_canonical`/`home_away`)BLOCKED が原因。B に明確に負け。
3. **ランキング面・読み物面・順位面が 404**(面が3つしか無い)= サイトとしての回遊先が薄い。A にも B にも負け。
4. **プロフィール・年度別履歴が無い**(source/backfill 無)= A(網羅型)に負け。「一般的な情報」の核が空。
5. **トピクラが片方向**(通常記事→選手データの逆リンク無し、横リンク無し)= 設計 §2 の①③が未実装。回遊・SEO 両方損。
6. **UX が WP標準テンプレ + 検索/フィルタ/今日の注目 無し** = B のソート/鮮度UX に負け。
7. **データ供給ムラ**(fill率70%、捕手50%、坂本空)= 勝っているはずの打者 split も「出ない選手」が一定数。
8. **SABR/pitch-level/選球眼/得点差別/殊勲打** = B に深さで負け(pitch-level は source 無で射程外、他は未実装)。

### 12-3. 逆に「負けていない/勝てる」点(過小評価しない)
- **鮮度**(毎朝更新・直近5試合)は A(静的)に明確に勝つ。
- **打者の split**(打順別/vs球団/本拠ビジター/イニング/曜日/月/交流戦)は A に無く、有データ打者では実際に出ている = ここは強み。
- **記事資産との連携**(関連記事は既にある)。逆リンクを足せば A の「試合↔選手リンク切断」を上回れる。
- **SNSシェア**は3サイトとも弱い → 先取りの好機。

---

## 13. 根本原因 + 修復コスト(コード/DB 1次source 深掘り 2026-06-01)

§12 の各 gap を実コード・実schema まで降りて根因と effort を確定。表面分析を2点訂正。

### 13-1. 投手 split が無い真因と effort【訂正: ETL問題でなく単なる未実装・安価】

- 真因: `src/data_site_template_pillar.py:823` `render_pillar_html()` が `_is_pitcher()`(L509)で分岐。**投手=2セクションのみ**(L841-845: `_build_pitching_season_html` / `_build_pitching_recent_html`)、**打者=10セクション**(L846-858、split 6種 + 打順別)。`src/data_site_query.py` に投手 split 計算関数が**1つも存在しない**(`fetch_pitching_stats_season` L1510 / `fetch_recent_pitching_games` L1578 の2つだけ)。query/dataclass/publisher/template の全層で未実装。設計どおり(query 冒頭コメント L7-9「Phase1.0=batting SUM、Phase1.5で pitching」)。
- effort: **vs球団/本拠ビジター/曜日/月/交流戦 = S(横展開・新ETL不要)**。`pitching_logs` は既に `JOIN games` 済(`fetch_recent_pitching_games` L1596-1597)、`giants_venue_from_game_id`/`_opp_code`/date parse は canonical非依存の汎用関数。集計指標を AB/H → IP/ER/K に差し替えるだけ。**打順別=投手は非該当**。**イニング相当=M〜L**(pitching_logs にイニング別生データがコード参照されておらず要確認 + 「序盤中盤終盤」は投手では別metric設計)。
- 結論: **最大の見た目gap(投手split)は最も安く直る**。

### 13-2. 447「vs左右/RISP が BLOCKED」の真因【訂正: 半分誤り・大半は既にLIVE】

- **チーム横断の vs左右/RISP/球場/イニングは既に nightly publish 稼働済**。`ranking_article_publisher.py` の `aggregate_giants_batter_vs_lr_strict`(L3726)/`aggregate_giants_batter_runner_state`(L2935)が **raw `batter`名 + `at_bat_details.runner_state` + `config/npb_pitcher_throws.json`(405投手の左右、scrape済)** で集計し、`insight_nightly.py`(L291/331/392)から毎晩出ている。球場別=447 `f1bd93f` で read-side LIVE、イニング=`7c792bd` LIVE。
- **真にBLOCKなのは個別選手 Pillar の vs左右/RISP だけ**。原因はカラム不在でなく、`src/analysis/insight_etl.py:470/475` が **upsert で `batter_canonical`/`pitcher_canonical` を `None` ハードコード**(コメントは「separate normalize step で埋める」だが、その step は存在しない=grep 0件)。`fill_canonical_team_aware()` は nightly で動くが対象が `batting_logs`/`pitching_logs` のみで `at_bat_details` 未適用(L981/990)。
- effort: **小**。(a) `fill_canonical_team_aware` を `at_bat_details` に拡張、または (b) Pillar query 側で venue/inning split が既にやっている read-side fuzzy match(`REPLACE(batter,' ','')=player`)を使えば **backfill 不要**。投手左右は throws.json で解決済=**別source不要**。447 の「3日(backfill+ingest修正+verify)」見積は過大。

### 13-3. /data/team・/data/schedule の実内容(200だが薄い)

- `/data/team`(`data_site_template_team.py` + `fetch_team_rankings` `data_site_query.py:1049`): **セ・リーグ 球団打率/本塁打/防御率 の3つの1値ランキング(各6行)のみ**(巨人 打率5位.231 / 本塁打3位35 / 防御率4位3.24)。日付なし。**欠落**: 順位表(順位/勝/敗/分/勝率/ゲーム差)、チーム打撃投手守備のフル集計列(得点/盗塁/出塁率/長打率 / 失点/WHIP/QS / 失策/守備率)、12球団・パ・リーグ view。
- `/data/schedule`(`fetch_giants_schedule` `data_site_query.py:1180`): **巨人の試合"結果"カレンダー(過去のみ)**、月別(新しい順)、列= 日付/勝敗/スコア/本拠ビジター/相手。月見出しに月間成績。**欠落**: 未来試合・予告先発・開始時刻・放送・box scoreリンク(`fetch_game_detail`/`game_slug` で `/data/game/` 生成コードは存在するが schedule 行からリンクしていない)。

### 13-4. fill率 70%(捕手50%)の真因【訂正: バグでなく出場機会】

- 真因: cluster fill は `data_site_publisher.py:263/318` が `fetch_batting/pitching_stats_season` 非None(=`batting_logs`/`pitching_logs` に該当名の game_id 行が1件以上、`data_site_query.py:706-743` の space-strip 名前一致)のときだけ数値表示。行ゼロ=`–`。
- **捕手50% = 2人制ローテ**(大城24g/岸田22g がほぼ全先発、他4捕手=先発0=行0)。6人中2人=50%。内野56%も固定スタメンで控え空。投手72%は登板で多くの体が回る。姓のバリアント全探索で該当0=**真の不在(name-mismatch でない)**。育成38名は意図的に名前のみ(`_build_ikusei_table_html` `data_site_template_cluster.py:258`)。
- 留保: fill率の実数値は local DB(05-24止まり・dev)由来。**production は新しい=実 fill率は production verify 必要**。
- 改善: (a) zero-row 行を cluster から抑制(thin-page SEO回避)、(b) ingest window 拡張。ただし**上限は出場機会で頭打ち**(2捕手制では6/6 は埋まらない)。
- **別の潜在バグ(fill率には無影響だが要follow-up)**: `batting_logs.team_role='giants'` が誤ラベル(対戦相手=佐藤輝明/菊池涼介等も含む、278試合中巨人は46のみ)。cluster fill と `fetch_team_leaders`(`data_site_query.py:1110`、`advanced_metric_snapshots.team_code='g'` で scope)は team_role に依存しないので現状無害だが、team_role='giants' を信じる処理があれば誤る。

### 13-5. effort 別 修復ロードマップ(深掘り反映)

| gap | effort | 前提 | 備考 |
|---|---|---|---|
| 投手 split 5種(vs球団/本拠ビジター/曜日/月/交流戦) | **S** | 既存 pitching_logs+games | 横展開、新ETL不要。最大の見た目改善 |
| Pillar vs左右/RISP | **S〜M** | read-side fuzzy match or at_bat canonical拡張 | backfill不要ルートあり。throws.json既存 |
| データ供給ムラ(坂本空等) | — | production ingest | 出場機会依存、根本対処は窓拡張のみ |
| /data/team を順位表+フル集計に | **M** | games/standings_snapshots | standings_snapshots table 既存 |
| /data/schedule に未来試合+予告先発 | **M** | games(未来分ingest要確認) | box link は game_slug 既存で接続可 |
| トピクラ逆リンク(記事→pillar) | **M** | entity→slug + 記事テンプレ | 設計§9 |
| 投手イニング split | M〜L | pitching生データ要確認 | metric設計も要 |
| SABR拡張(OPS+/wOBA/FIP等) | M | advanced_metric_snapshots(17指標既存) | snapshot に既にある指標は表示するだけ=一部S |
| プロフィール/年度別履歴 | **L** | 別source/backfill | 射程外寄り |
| pitch-level | — | 別source課金 | 非スコープ |

**深掘りの結論**: 「負けている」の中核(投手split / Pillar vs左右RISP)は**ETL大改修でなく既存ロジックの横展開・read-side fuzzy match で安価に解ける**。447 の見積は過大。高コストは プロフィール/年度別履歴/pitch-level のみで、これらは非スコープ寄り。**最小投資で B との差(split深度)と A との差(投手データ)を同時に詰められる**。

---

## 14. ★SEO 可視性 gap(実測 2026-06-01)— 最大の「負け」は機能でなく index

データサイトの真の負け = 「検索で見つけられない」。3サイト実測:

| 観点 | A my-favorite-giants | B baseballdata.jp | C yoshilover/data |
|---|---|---|---|
| indexed 規模感 | sitemap ~1,200 URL(千級) | sitemap index 子137本=**数万URL級**(1選手7-8ページ展開) | /data は page-sitemap ~150 URL。`site:yoshilover.com/data`=**0件**、target クエリ「吉川尚輝 2026 成績 打率」で**自ページ圏外** |
| 構造化データ JSON-LD | BreadcrumbList+Dataset | **無し** | **SportsPlayer+PropertyValue+Breadcrumb=3サイト中最厚** |
| sitemap | あり | あり(巨大) | あり(/data は page-sitemap 経由で submit済) |
| title/meta 検索意図 | 可(titleブランド寄り) | title良/desc定型で弱 | **3サイト中最良**(選手名先頭+成績/打率/2026+固有desc+og完備) |
| mobile meta | あり | あり | あり |

- **訂正(2026-06-01、当初の楽観を破棄)**: 「技術SEOが上だから勝てる」は**誤り**。検索順位は コンテンツの深さ・網羅・トピック権威・被リンク・滞在 で決まり、meta/JSON-LD は **hygiene であって順位の決定打ではない**。コンテンツが大敗(面3/列7/当季のみ §15)なら、同じクエリ(包括的選手成績)では **index されても順位で勝てない**。`site:` 0件 + 自クエリ圏外 は「未クロール」より **薄い+ドメイン権威不足の症状**と見るべき。
- **正しい因果**: SEO は**コンテンツと権威の結果**であって独立レバーでない。コンテンツ大敗 = SEO も負け。技術SEO(meta/JSON-LD/sitemap/mobile)が競合より整っているのは事実だが、それは出場資格であり勝因ではない。
- **純データサイトとしては A にも B にも勝てない**(広さ A・深さ B・index・権威の全てで大敗、追随は非現実的)。
- **唯一あり得る勝ち筋 = データ対決を降りる**: A=記事ゼロ/鮮度ゼロ、B=巨人編集/文脈/速報ゼロ。両者が持たない「**巨人特化 × 即日速報 × データを記事文脈に埋める媒体性**」だけが残された土俵。これは「データの網羅・深さで勝つ」話ではなく「巨人ファンが今日読みたい文脈付きデータ記事」で差別化する話。保証はなく、被リンク/権威/継続を要する長期戦。
- **含意**: 456-461(機能改善)も、index されなければ見られない。だが index/権威は **コンテンツ深化 + 媒体性 + 内部リンク + 継続**の結果としてしか付かず、**SEO 単体の近道は無い**。Search Console での実 index 確認は症状把握には有用だが、それで勝てるわけではない。
- **メモ**: memory「yoshilover noindex 運用」は /data には非適用の実測(robots 開放・canonical 自己参照)。[[project_seo_404_to_410_gone_response]] / 251-noindex は /data に非適用の可能性 → 要再確認。

## 15. 定量スコアボード(実測 2026-06-01)

| 指標 | A MFG | B BBD | C yoshilover | 判定 |
|---|---|---|---|---|
| データ面ページタイプ数 | ~90種 | ~40種 | **3面** | 大敗 |
| 1選手の指標カラム数 | 打24/投25 | 打24/投24 | **打7/投=2表のみ** | 大敗 |
| split 次元数 | 打0/投0(年集計) | 打~18/投~16 | **打7/投0** | A勝ち / B大敗 |
| 選手網羅数 | 現役+歴代数百 | 現役一軍中心 | 132名(fill率70%/捕手50%) | 互角〜やや負け |
| 年度カバレッジ | **1936-(90年)** | 2011-(16年) | **当季のみ** | 大敗 |
| 更新頻度 | 年集計+不定期 | 日次 | **毎朝6:00+試合後17:30/23:00** | **A明確勝ち / B互角〜やや勝ち** |
| セイバー/独自指標数 | 0〜少 | **~30** | 1〜数(snapshot17指標は未表示) | A互角〜勝ち / B大敗 |

- **勝ち=1指標のみ**(更新頻度、A比較)。**負け=5〜6指標**。「鮮度特化の巨人ニッチ」では勝つが、広さ(A)・深さ(B)の両軸で数値上は劣後。
- 負けの深刻度順: ①投手split(0 vs B16・最安修復) ②投手カラム数 ③面数(3 vs 90/40) ④年度(当季 vs 90年) ⑤セイバー(1 vs 30) ⑥打者split(7 vs 18) ⑦打者カラム数(7 vs 24)。
- **再確認**: 最も目立つ負け(投手split/vs左右RISP)が最も安く直る(§13)。高コストは年度履歴/プロフィール/pitch-level=非スコープ寄り。

## 16. データ記事生成エンジンの実態(深掘り 2026-06-01・コード1次source)

/data ページとは**別系統**で、`【巨人データ】`記事の量産エンジンが既に実装済み:
- 中核: `src/analysis/insight_nightly.py` `_run_data_insight_auto_publish`(L97-)+ publisher3本(`anomaly_article_publisher` / `ranking_article_publisher` / `team_ranking_publisher`)+ `insight_anomaly_detector` + `insight_dedup_gate`(349)+ `insight_quality_gate`(356)。
- **LIVE な角度**: z-score異常値 / 守備UZR / milestone・連続記録 / 順位変動 / OPS・ERA・AVG・K9・OBP・SLG ランキング / counting(安打HR打点盗塁奪三振)/ 本拠ビジター / vs球団 / vs左右 / イニング別 / 走者状況RISP / カウント別 / チームHR打率防御率連勝得失点差。
- **dedup(349)**: 7日cooldown + 同日ハードブロック + 選手2本/日cap + 値5%変化で再掲。**quality gate(356)**: 鮮度3日 / evidence4要素 / 表形式強制。生成能力 理論上限 ~30-40本/便、dedupで実発火半減。
- **阻害4点(コード事実)**: ①角度の約半分が `[]` 空固定で実生成されない(BABIP/FIP/HRペース/1試合hero/stat_delta/giants_top%、コメント「全部復活」とコードが矛盾) ②title が機械f-string で「発見/驚き」を表現できない ③全体が `ENABLE_DATA_INSIGHT_AUTO_DRAFT`(default 0)依存=**prod ON か要verify** ④サヨナラ/逆転/殊勲打 は `at_bat_details.result_text`+`inning_scores` で派生可能なのに**検知コードがゼロ**(grep 0件)。

## 17. 実装順序:parity(ライバルにあるもの)→ 差別化(上記)

user 方針(2026-06-01): **まずライバル2サイトにあるものを入れて土俵に立つ → それに差別化4点を乗せる**。

### Phase 1 — parity(ライバルにあるもの・実現可能な範囲)

| parity項目 | 持つライバル | 我々の状態 | チケット/対応 | effort |
|---|---|---|---|---|
| 投手 split(先発救援/球場/vs球団/曜日/月) | B | pillar 無 | 456 | S |
| pillar vs左右 / RISP(打者) | B | ranking記事はLIVE/pillar無 | 457(read-side, backfill不要) | S〜M |
| SABR指標(whitelist内: OPS+/wOBA一部/ISO/BB%/K%/FIP/WHIP等) | B | OPS止まり | 461(snapshot既存17指標を表示。whitelist×は除外) | S部分 |
| カウント別 / 球場別 を pillar 表示 | B | ranking laneに既存/pillar未配線 | 457拡張 | S〜M |
| チーム順位表 + 打撃投手守備フル集計 + 未来試合 | A | /data/teamは3指標のみ | 459(#123) | M |
| 球団内/リーグ ランキング面 | A・B | /ranking 404 | 462(#126) | M |
| 殊勲打 / 得点差別打率 | B | 未実装(派生可) | 463(#127) | M |
| サヨナラHR DB(読み物) | A | 無 | 463(#127) | M |
| 現役選手 網羅 fill 改善 | A | fill率70% | 460(zero-row整理+窓) | S〜M |

**parity 不可(明示・追わない)**: pitch-level(配球/球種/ゾーン)・選球眼SQG = 別source課金 / 歴史網羅(歴代/通算/年度別1936-)= backfill source無 / プロフィール(生年月日等)= source無 / 投手被打者左右 = 打者打席左右source未確保。これらはライバルにあっても**土俵を降りる**(§14 戦略)。

### Phase 2 — 差別化(上記4点を parity の上に乗せる)

| 差別化 | 内容 | 効果 |
|---|---|---|
| A 眠り角度の再活性化 | 空固定detector(BABIP/FIP/HRペース/1試合hero/stat_delta)を whitelist 準拠で起こす | 幅(角度数)を実数で増やす |
| B 新角度の追加 | サヨナラ/逆転/殊勲打 detector(result_text+inning_scores 派生)、通算◯本目 | A/Bに無いfresh角度=幅 |
| C title 発見ドリブン化 | 機械f-string → 驚き/発見を literal で表現(no-AI rule 維持しつつ「序盤.194→終盤.286」等の対比を title化) | 読ませる=CTR=長尾SEO |
| D 新鮮さ最適化 + verify | `ENABLE_DATA_INSIGHT_AUTO_DRAFT` prod ON verify、試合後即時生成の cadence 確認 | 新鮮さ=唯一の明確勝ち筋を実働化 |

**Phase2 チケット**: A 眠り角度=464(#128)/ B 新角度=463(#127)/ C title発見=465(#129)/ D 新鮮さverify=466(#130)。Phase1 既存=456(#120)/457(#121)/459(#123)/460(#124)/461(#125)、新規=462(#126)/463(#127)。

**順序の理由**: parity で「データ記事として最低限の幅」を揃えてから、差別化(発見・新角度・title・新鮮さ)で A/B が作れない領域に出る。parity 無しに差別化だけでは土俵に立てず、差別化無しに parity だけでは A/B の劣化版で終わる。

## 11. 非スコープ(明示)

- pitch-level(配球チャート/球種別球速/ゾーン別)= 別 source 課金が必要、射程外([[doc/reference/model-site-page-inventory.md]] §B8)。
- 歴史網羅(歴代在籍/通算ランキング/年度別1936-)= モデルA と正面衝突、当面追わない。
- pitch tracking / Statcast 系新規 ETL。
