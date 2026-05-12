# 2026-05-12 報知 / スポニチ source の構造化情報を表形式で描画する

> **チケット種別**: 本文描画形式の structural 改修(`2026-05-12_pregame-info-table-format.md` の続編 / 上位スコープ。あちらの narrow post-process(`68e836d`)は今回 scope 内で再評価する)
> **現状ステータス**: SPEC ONLY / NOT YET IMPLEMENTED / **追加調査必要**
> **本commitで許可される変更**: 本Markdown作成・追記のみ。コード編集 / commit / push / deploy / env / scheduler 変更は禁止
> **本Markdown作成時点の事実**:
> - 公開記事 id=66442(報知 X 2軍 lineup、`D東妻 7萩尾3加藤...` compact 形)で table 描画されないことを実 body 取得で確認
> - `ENABLE_RSS_LINEUP_TABLE_POST_PROCESS=1` は production env で確認(2026-05-12 の deploy)
> - 既存 narrow post-process の regex は `<p>N番 守備 選手</p>` 8 行連続を要件にしており、報知/スポニチ compact 形(1 行 / 圧縮) には構造的に match しない
> - production の body 合成経路は **`nomotoke_card_renderer` 経由ではない**(rss_fetcher.py に renderer 呼び出しなし)。`_select_template_v2` 系の subtype 別 body builder が実体(調査中)

---

## 1. 今回の目的

報知 / スポニチ / その他外部 RSS source の試合関連記事のうち、**構造化可能な情報を `<table>` で描画**して情報密度と視認性を上げる。具体対象:

- スタメン(1軍 / 2軍 両方)
  - 報知 compact 形(`D東妻 7萩尾3加藤 9皆川...`)
  - スポニチ emoji 形(`1️⃣ 三塚(D)2️⃣ 小濱⑹...`)
- 先発投手予告 / 先発ローテ(`井上温大→ウィットリー→竹丸和幸` 等の prose)
- 試合結果(勝利投手 / 敗戦投手 / セーブ / box score / inning スコア / 打席結果 等)

LLM(Gemini) は本経路で使用していないため、source 文字列を deterministic な構造抽出 → table HTML へ変換する。

ゴール画像は既存の `manual_intake` flow が `nomotoke_card_renderer` 経由で出している table 描画(打順 / 守備 / 選手 / 打率 等の 5 列形式)を、RSS auto-publish 経路にも適用すること。

## 2. 今回触る範囲(Phase 0 完了後の **確定** リスト、Phase 2A のみ)

> Phase 0(read-only 調査) **完了済**(§9 の Phase 0 調査結果参照)。本節は Phase 2A の確定 write scope。Phase 2B-D は Phase 2A 着地後に同様に確定する。

**Phase 2A 確定 write scope(全 4 file、minimum-diff、subtype 文字列追加なし、env flag 追加なし)**:

1. **NEW** `src/source_hochi_compact_lineup_extractor.py`(~150-250 行)
   - public function: `parse_hochi_compact_lineup(title: str, summary: str, source_name: str) -> Optional[Dict[str, Any]]`
   - 戻り値: `{"lineup": [{"order": "1", "position": "指", "name": "東妻"}, ...], "keyword": "...", "raw_position_count": N}` または `None`
   - 報知 compact 形(`D東妻 7萩尾3加藤 9皆川...`)を構造化
   - `D=指`(DH)/ `P=投`(投手)/ `1-9=投捕一二三遊左中右` の position mapping
   - キーワード(`スタメン` / `ファーム・リーグ` / `Ｇタウン` 等)で gate
   - row 数 < 8 で `None`(silent skip ではない、明示的 None)
   - 公式X clean 形(`1番（中）ヘルナンデス`)が混在していたら本 parser は `None` を返す(既存 `source_x_lineup_extractor` に委ねる)
   - source_name allowlist: `スポーツ報知巨人班X` / `hochi_giants` / `hochi_baseball` / `スポーツ報知 巨人` / `SportsHochi` / `スポーツ報知X` 等

2. **EDIT** `src/rss_fetcher.py`(narrow、+~40 行 / -0 行 想定、既存行不変)
   - **追加 import**: `parse_hochi_compact_lineup`
   - **新 nested helper** `_build_basic_lineup_table_block(rows: list[dict]) -> str`(`build_news_block` の `_lineup_stats_block` 直前あたりに配置、3 列 `<table class="nomotoke-card-lineup-table">` を `<!-- wp:html -->` ブロックで描画)
   - **`build_news_block` 内、`lineup_stat_rows` 取得直後の補完**:
     ```
     if not lineup_stat_rows and source_type == "x_post":
         hochi_lineup = parse_hochi_compact_lineup(title, summary_clean, source_name)
         if hochi_lineup and hochi_lineup.get("lineup"):
             compact_lineup_rows = hochi_lineup["lineup"]
     ```
   - **inject 点**: `_lineup_stats_block` 呼出の同位置(line 16184 / 16298)に「`compact_lineup_rows` があれば `_build_basic_lineup_table_block(compact_lineup_rows)`」を OR で追加(`lineup_stat_rows` と double-render しない)
   - **`farm_lineup_short` 用**: `_build_farm_lineup_safe_fallback` の caller(line 15416)で同 extractor を起動、`_build_farm_lineup_safe_fallback` に新引数 `lineup_rows: list[dict] | None = None` を追加、関数内の「【二軍スタメン一覧】」heading 直後に rows があれば `_build_basic_lineup_table_block(rows)` を inject(`<!-- wp:html -->` 形式)
   - 既存 `_lineup_stats_block` / `_lineup_watch_block` / `_build_lineup_safe_fallback` 本体は **1 行も touch しない**

3. **NEW** `tests/test_source_hochi_compact_lineup_extractor.py`(~10-15 case)
   - 1軍 lineup 報知 compact 形 fixture → 9 row 構造化
   - 2軍 lineup 報知 compact 形 fixture(id=66442 の実 body)→ 9 row 構造化
   - DH(`D東妻`)を `指` 行として認識
   - 投手(`P又木`)を `投` 行として認識
   - キーワード欠如 → `None`
   - row 数 < 8 → `None`
   - 公式X clean 形 → `None`
   - 空文字 / 空白のみ / HTML タグだけ → `None`
   - 全角 / 半角 空白混在 → 同等処理
   - source_name allowlist 外(`yahoo_news` 等)→ `None`

4. **EDIT** `tests/test_rss_fetcher_*` の **新規 file**(既存 test の case 追加だと scope 拡大の risk があるので、本 ticket 用に新規 file `tests/test_rss_fetcher_hochi_compact_lineup_table.py`、~5-8 case)
   - hochi 報知 X 2軍 lineup 入力 → body に `<table class="nomotoke-card-lineup-table">` 含む
   - hochi 報知 X 1軍 lineup 入力(Yahoo 失敗想定)→ 同 table 含む
   - hochi 報知 X 1軍 lineup + Yahoo stats あり → **Yahoo の 7 列 table のみ**(double-render なし)
   - hochi 以外の source(Yahoo 等) → 既存 path で unchanged
   - extractor 失敗 → 既存 prose body unchanged

5. **EDIT** `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md`(本 file、post-work 追記)

**Phase 2A の commit 単位**:
- 1 commit = `1 + 2 + 3 + 4 + 5` を一括(extractor + caller + tests + 作業記録)、minimum-diff。各 file の追加行を staged content で verify 後 commit
- `git add -A` 禁止、明示 path のみ stage(`feedback_git_diff_cached_verify_strict.md`)

**Phase 2B / 2C / 2D の write scope**: Phase 2A 着地 + observation 後、同様の Phase 0 調査を経て確定。本 commit では未確定のまま。

## 3. 今回触らない範囲

- **`guarded-publish` 公開ゲート / backlog narrow 判定 / freshness threshold**(別 ticket: `2026-05-12_hochi-fresh-pregame-backlog-publish-policy.md` で扱う)
- **`src/guarded_publish_runner.py` / `src/guarded_publish_evaluator.py`**(公開可否判定)
- **`src/publish_notice_email_sender.py` / `src/publish_notice_scanner.py`**(mail 通知)
- **Cloud Run env / Secret / Scheduler / GitHub Actions / Cloud Run deploy**(本便で apply しない)
- **`config/rss_sources.json`**(source 追加・削除・URL 変更)
- **WordPress 側設定 / 既存公開済記事の retrofit**(本 ticket は新規生成記事のみ対象)
- **アイキャッチ選定 / featured media**(`305-QA-featured-media-source-priority` で別途扱い)
- **X 自動投稿 / X カード描画**(noindex + 手動 X 運用方針、本 ticket scope 外)
- **SEO / schema / sitemap / noindex policy**(`251-SEO` で別途)
- **Gemini prompt / LLM 呼び出し追加**(本経路は LLM 不使用、deterministic に組む)
- **Cloud Run cost / Gemini call 回数増 を伴う変更**(本 fix で増えない設計を厳守)
- **既存 `nomotoke_card_renderer.py` の renderer signature / output 互換**(consumer 追加のみ、既存 manual_intake / postgame_yahoo flow は不変)
- **`source_x_lineup_extractor.py` / `source_yahoo_lineup_extractor.py` / `source_yahoo_boxscore_extractor.py`**(既存 extractor の挙動)
- **`nomotoke_rss_router.py` の `route_rss_entry_to_nomotoke_card` 関数**(production で使われていないことを Phase 0 で確認できた場合は触らない)
- **subtype 文字列の追加**(既存 subtype の routing path に table HTML を差し込むのみ)
- **AdSense / sidebar widget / sticky scroll**
- **H3 構造の根本変更**(`H3-STRUCTURE-UNIFY-2026-05-08` で別途)
- **既存 `rss_lineup_table_post_process.py`**(2A 着地時に役割が完全に重複したら GO 取得後に default OFF or 削除を別便で。本便では不変)
- **234-impl-7(probable_starter / pregame body hardening)で追加した validator**(disjoint scope)
- **247-QA(postgame strict slot-fill) / 254-QA(innings normalization)** の既存 logic
- **309-QA(postgame table for manual_intake) で landed した manual_intake 経路**(本便は RSS auto 経路、disjoint)

## 4. 影響範囲

**直接影響**:
- 新規生成される `lineup` / `farm_lineup` / `pregame` / `postgame` subtype の WP 記事 body HTML に `<table>` block が追加される
- 影響対象 source: 報知系(`スポーツ報知巨人班X` / `hochi_giants` / `hochi_baseball` / `スポーツ報知 巨人` / `SportsHochi` 等)+ スポニチ系(`SponichiYakyu` / `スポニチ野球記者X` 等)
- 影響対象 subtype: 上記 4 subtype × 該当 source × 該当 body pattern を満たすもの

**影響しない想定(検証必要)**:
- publish 判定の通る/通らない(評価 logic 不変)
- RSS 取得件数(取得経路不変)
- mail 通知(送信経路不変)
- X 投稿(オフライン人手運用、本便不変)
- 既存 publish 済記事(retrofit しない、新規生成のみ)
- Yahoo / 巨人公式X source の lineup 描画(既存 path 不変、別経路)
- manual_intake flow(既存 path 不変、別経路)
- 234-impl-7 validator(disjoint subtype/scope)

**望ましい副次効果**:
- 報知/スポニチ source の試合関連記事の情報密度が上がる
- 「【二軍スタメン一覧】」h3 の下が空のまま放置されている現状(id=66442 で確認)が解消される

**検証必要なリスク**:
- structured 抽出後の table HTML が production WP REST 保存で壊れない
- mobile narrow viewport で table が崩れない(theme CSS 依存)
- 同話題重複 guard の representative text が変わって誤動作しない
- 報知/スポニチ source の body pattern が時期/担当者で変わる可能性(false negative 許容、silent skip でない warning log)

## 5. 実行予定テスト

**Phase 0(調査、read-only、コード変更なし)**:
- `git status --short`(dirty 確認)
- `git log --oneline -20`(直近 commit の context)
- `grep -nE` で `_select_template_v2` 経路を全 trace
- `python3 -c "import ast; ast.parse(open('src/rss_fetcher.py').read())"` で syntax 整合確認(read のみ)
- `python3 -m unittest discover -s tests` で **fire-time baseline** 取得(commit 数 / pass 数 / fail 数を記録、以後の diff 比較用)

**Phase 2A 実装後(GO 取得後のみ)**:

1. **新規 unit test(`tests/test_source_hochi_compact_lineup_extractor.py`)**:
   - 1軍 lineup 報知 compact 形 → 9 row 構造化 dict 出力
   - 2軍 lineup 報知 compact 形(id=66442 の実 body をそのまま fixture 化)→ 9 row 構造化 dict 出力
   - DH 表記(`D東妻`)を `指名打者` 行として認識
   - 投手表記(`P又木` / `Pマタ`)を `投` 行として認識
   - キーワード(`スタメン` / `ファーム・リーグ` 等)欠如時 → `None`(skip)
   - row 数不足(< 8)→ `None`(silent skip でなく明示的 None)
   - 公式X clean 形(`1番（中）ヘルナンデス`)→ `None`(double-extract 防止、既存 extractor に委ねる)
   - 空文字 / 空白のみ / HTML タグだけ → `None`
   - 全角空白 / 半角空白混在 → 同等処理

2. **router/composer 統合 test(対象関数を Phase 0 で特定後)**:
   - hochi 2軍 lineup body → table HTML 含む output
   - hochi 以外の source(Yahoo 等) → 既存 path で unchanged
   - extractor 失敗 → 既存 prose body unchanged(silent skip でなく audit log 出力)

3. **既存テスト regression**:
   - `tests/test_rss_fetcher*` 全件 pass(影響有無確認)
   - `tests/test_nomotoke_card_renderer.py` 全件 pass(consumer 追加のみ、既存テスト不変)
   - `tests/test_nomotoke_rss_router.py` 全件 pass(本便で router 触らない場合)
   - `tests/test_rss_lineup_table_post_process.py` 全件 pass(本便で post-process 触らない場合、9 件)

4. **全件**: `python3 -m unittest discover -s tests` で fire-time baseline と pass 数 / fail 数 diff、新規追加分以外の **増加 fail = 0** 確認

5. **AST + compile**:
   - 編集した全 .py を `python3 -m py_compile` で compile 通過確認
   - `python3 -c "import ast; ast.parse(open('<file>').read())"` で syntax 確認

6. **output spot-check**(GO 取得後の deploy 前に repo 内 fixture で出力 HTML を目視):
   - 報知 1軍 compact 形 fixture → 期待 HTML
   - 報知 2軍 compact 形 fixture(id=66442 同型)→ 期待 HTML
   - HTML 内の `<table>` `<thead>` `<tbody>` `<tr>` `<td>` のみ(JS / inline style / `<script>` なし)

7. **deploy 後 verification(GO + deploy 取得後のみ、本 spec 段階では実施なし)**:
   - `gcloud logging read` で extractor 発火 log 確認
   - WP REST GET で deploy 後の最初の hochi 2軍 lineup 記事を取得し、`<table class="nomotoke-card-lineup-table">` が含まれることを byte 確認
   - 数値 diff(直前 24h の hochi 2軍 lineup 記事数 vs deploy 後 24h の table 含有率)

## 6. STOP 条件

- Phase 0 調査で production body 合成経路が **3 経路以上** に分岐していて narrow hook が組めない場合
- structured field が安全に抽出できず、推測補完が必要になった場合(silent skip でなく実装中止、user 報告)
- HTML `<table>` を含む本文が WordPress REST API 経由で保存できない場合
- mobile viewport で table が崩れる、theme CSS で意図せず非表示になる場合
- 既存 prose 描画 path に副作用が出て、対象外 subtype(manager / player / notice / video / official_notice / 公式X lineup / Yahoo lineup / manual_intake)まで影響する場合
- LLM 呼び出しを追加しないと回らない設計に行き着いた場合(deterministic で組めない場合)
- 全件テストが赤で、今回差分との関係を切り分けられない場合
- env / Scheduler / Cloud Run / deploy / Secret 変更が必要になった場合
- 公開済み既存記事の retrofit に scope が広がった場合
- `_select_template_v2` 系の subtype 切替 logic を変更しないと組めない場合(branch 増加は禁止、subtype 文字列追加禁止)
- 234-impl-7 / 247-QA / 254-QA / 309-QA / `rss_lineup_table_post_process.py` のいずれかと衝突する場合
- 「これくらいなら scope 拡げて良いかな」が浮かんだ場合(STOP して user 判断)

## 7. 禁止事項

- 記憶から再構成しない(全 path は grep / Read で実 file 確認)
- silent skip しない(extractor 失敗は warning log + audit、無音で消さない)
- 自己評価 OK で済ませない(必ず baseline diff の数値を出す)
- `git add -A` / `git add .` を使わない(明示 path のみ stage)
- Gemini / LLM に table HTML を生成させない(deterministic に renderer 側で組む)
- HTML に inline `style` 属性 / JS / `<script>` を入れない
- 公開済み記事を遡って書き換えない(retrofit 禁止)
- comment / injury / notice / video / official_notice / 公式X lineup / Yahoo lineup を本便で触らない
- env / Scheduler / Cloud Run / Secret / GitHub Actions を本便に混ぜない
- source 追加 / 削除 / URL 変更を本便に混ぜない
- 別 ticket(`2026-05-12_hochi-fresh-pregame-backlog-publish-policy` / `H3-STRUCTURE-UNIFY-2026-05-08` / `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08`)の差分と本便を 1 commit に混ぜない
- AdSense / sidebar / H3 統一など他 ticket の scope を引き込まない
- 表 fallback 失敗を silent skip にせず、prose で必ず描画する
- subtype 文字列を追加しない(`farm_lineup` / `lineup` / `pregame` / `postgame` 等の既存 subtype を維持)
- 「これは pre-existing fail だから無視」を pytest 結果の根拠にしない(必ず fire-time baseline と diff し、増減 0 を確認)
- Codex 報告 / 自分の予想を accept 根拠にしない(file 実在 + collect 数 + fail 数 の数値追認)
- Phase 2A の commit に 2B / 2C / 2D の差分を 1 byte でも混ぜない(phase 直列、minimum-diff)

## 8. 想定されるデグレ

- table HTML がテーマ CSS と衝突して画面崩れ(font-size / border / overflow)
- mobile narrow viewport で table が overflow し、横スクロール / 折り返しが効かない
- 公開済み prose 記事と新規 table 記事の混在で読者に違和感(retrofit 禁止のため恒久併存)
- structured 抽出 logic が prose 抽出と分岐し、long-term の整合が壊れる
- 同話題重複検出が table 化前後で representative text が変わり duplicate guard が誤動作
- table 中身に同姓選手の誤マッチが入り、`23fa8d5`(related_player same-surname guard)の保護が間接的に弱まる
- ベンチ控え 7-8 名の長い行が table に入ると、モバイルで縦長すぎる
- 報知/スポニチ source の body pattern 変化(球団担当者交代等)で extractor が silent fail し、後で prose も table も無い空 body になる(→ 必ず prose fallback + warning log)
- 既存 narrow `rss_lineup_table_post_process` と新 extractor が **両方** 同じ body に対して発火する double-decoration(対策: extractor 経路では既に table 化されているか確認してから既存 post-process を skip、または gate 条件で disjoint)
- `nomotoke_card_renderer.render_lineup_card` の data contract に新規 consumer が依存し、後で renderer が変わると本便も壊れる(逆方向の依存)
- Phase 2A → 2B → 2C → 2D の各 phase で、前 phase の hook 点を後 phase が拡張する際に副作用が出る
- 234-impl-7 の `_validate_pregame_anchor` が table HTML を「source に無い数字」と誤判定する可能性(対策: validator scope は HTML タグ除去後の text、Phase 0 で確認)
- 247-QA postgame strict slot-fill が table HTML を「LLM 自由作文」と誤判定する可能性(対策: strict 経路は postgame subtype のみ、本便は RSS auto path、Phase 0 で経路確認)
- 「ファーム・リーグ（Ｇタウン）スタメン【DeNA】 【巨人】」のような prefix を table 化対象に含めるか除外するかの判定で誤抽出
- 公式X 形式と報知 compact 形が混在する body での誤抽出(優先順位: 公式X 既存 extractor を先に走らせ、それが失敗した時のみ本便 extractor)
- 1 article 内に複数 lineup(自軍 + 相手軍)が出る場合の分離失敗
- DH(`D東妻`)/ 投手(`P又木`)を batting order の 9 番目に詰めるか別表記するかの判定誤り

## 9. 作業ログ欄

### 2026-05-12 PM(spec only、本 Markdown 作成のみ、user 指示)

- user 指示: 「まずチケットを作る。repo 内に作業記録 Markdown 作成。本 commit ではコード編集 / commit / push / deploy / env / scheduler 変更禁止」
- user 指示の前段(同 session 内): 「表にできるものは表」「LLM は今は使ってない」「2軍もだけど」「先発投手とか試合結果も」「2(本筋: nomotoke renderer wiring)で進める」
- user 運用方針: noindex + 手動 X 運用なので、最終 gate は user 判断。記事品質に致命傷があれば user 側で post せず止める前提
- 本 Markdown 作成、scope / 触らない範囲 / テスト / STOP / 禁止事項 / 想定デグレを定義
- **Phase 0(調査)未完了**: `_select_template_v2` 系の production body 合成経路の全 trace は本 Markdown 作成時点で未完。GO 前に Phase 0 を完走し、§2(触る範囲)を実 path に基づき確定する
- 既存 narrow `rss_lineup_table_post_process.py`(`68e836d`、ENABLE_RSS_LINEUP_TABLE_POST_PROCESS=1 で prod 稼働中)は本便 scope 内で再評価 / 重複時の整理は別便
- code 変更 / commit / push / deploy / env / scheduler 変更は本 commit で禁止、user GO 後別便で着手

### 2026-05-12 PM 調査メモ(Markdown 作成中に判明した事実、追記)

- production routing は `nomotoke_rss_router.route_rss_entry_to_nomotoke_card` ではなく、**`rss_fetcher._select_template_v2` 系統**(grep 結果より)
- `nomotoke_rss_router.RSS_ONLY_BLOCKED_TEMPLATES` は documentation/dry-run 用で、production では不使用の可能性が高い(確定は Phase 0 で)
- `nomotoke_card_renderer.render_*_card` は `rss_fetcher.py` から呼ばれていない(grep 結果より)。manual_intake / run_postgame_from_yahoo 等の tool 経路のみ
- 本 ticket の真の hook 点は `rss_fetcher.py` 内の subtype 別 body composer(`_select_template_v2` の各 elif 分岐の下流)
- subtype 別 body composer の特定は Phase 0 で実施

### 2026-05-12 PM Phase 0 調査結果(確定、grep + Read で実 file 確認)

**fire-time baseline**:
- HEAD: `51acaa0` (`docs: append v1 post-work facts to pregame-info-table-format work_log`)
- `python3 -m unittest discover -s tests` → **3461 tests, OK**(0 fail)
- 以後の diff 比較 anchor

**production env 確定**(`gcloud run services describe yoshilover-fetcher` より):
- `ARTICLE_AI_MODE=none` / `OFFDAY_ARTICLE_AI_MODE=none` → **Gemini / Grok 不使用**(user 言の確認)
- `LOW_COST_MODE=1` / `STRICT_FACT_MODE=1` / `RUN_DRAFT_ONLY=0`
- `ENABLE_RSS_TEMPLATE_ROUTING_V2=1` / `ENABLE_BODY_TEMPLATE_V2=1` / `ENABLE_FARM_SHORT_POST_TEMPLATE=1`
- `ENABLE_RSS_LINEUP_TABLE_POST_PROCESS=1`(narrow post-process 既稼働、本 ticket と重複範囲)

**production body composition の確定 path**(LLM disabled 時、`build_news_block` 経由):
1. `build_news_block`(line 15035)
2. `article_ai_mode == "none"` 分岐(line 15263) → `ai_body = ""`
3. `if not ai_body:`(line 15316) → `_build_safe_article_fallback(...)`(line 15318、dispatcher)
4. dispatcher で subtype 別分岐:
   - `category=="試合速報" and article_subtype=="lineup"` → 後続 `_build_game_safe_fallback` 経由 → `_build_lineup_safe_fallback`(line 10559、`lineup_rows` 引数あり)
   - `category=="ドラフト・育成" and article_subtype=="farm_lineup"` → `_build_farm_lineup_safe_fallback`(line 10993、**`lineup_rows` 引数なし、prose-only fallback**)
5. 同 outer function `build_news_block` 内の後続で:
   - `_lineup_stats_block(lineup_stat_rows)` 呼び出し(line 16184, 16298) → 7 列 HTML `<table class="...yoshilover-lineup-stats..."` 描画
   - `lineup_stat_rows = fetch_today_giants_lineup_stats_from_yahoo()`(line 15099) → **Yahoo only / 1軍 only**

**id=66442(報知 X 2軍 lineup)の現状**:
- routing: `farm_lineup_short` → `_build_farm_lineup_safe_fallback`
- `lineup_rows` 引数なし、Yahoo fetch 経路もなし
- 結果: 「【二軍スタメン一覧】」H3 の下が空(本日確認の bug)

**id=65897(Yahoo 1軍 lineup)で table が出る理由**:
- routing: `lineup_short` → `_build_lineup_safe_fallback`
- `lineup_stat_rows = fetch_today_giants_lineup_stats_from_yahoo()` で Yahoo HTML 経由 stats 取得成功
- `_lineup_stats_block(lineup_stat_rows)` で 7 列 HTML table 描画

**id=66005(報知/サンスポ 1軍 lineup compact 形)で table が出ているように見えた理由**:
- 同 `lineup_short` → Yahoo 経由 lineup_stat_rows が並行取得されていれば table 出る
- 報知 compact source 自体が table 化に寄与しているわけではない(Yahoo に依存)

**Phase 2A の確定 hook 点(narrow、minimum-diff)**:
- 新 extractor `src/source_hochi_compact_lineup_extractor.py`(報知 compact `D東妻 7萩尾3加藤 9皆川...` を `[{"order","position","name"}, ...]` に構造化)
- 新 helper(`_build_basic_lineup_table_block(rows)` のような 3 列 HTML table)を `build_news_block` の nested function として追加(`_lineup_stats_block` と同 pattern、3 列固定)
- `build_news_block` で `lineup_stat_rows` が空のときのみ extractor を起動し、結果が非空なら新 helper を `_lineup_stats_block` 同位置に inject
- `farm_lineup_short` 経路: `_build_farm_lineup_safe_fallback` の caller(line 15416)で同 extractor を起動、戻り値を新引数 `lineup_rows` で渡し、`_build_farm_lineup_safe_fallback` に「rows があれば table HTML を中段に inject」する分岐を **narrow** 追加
- 既存 `rss_lineup_table_post_process.py`(`68e836d`)とは「prose 後 post-process」と「source 直接 extract」で経路が disjoint。**double-decoration を避けるため**、本 extractor が rows を返した場合は `nomotoke-card-lineup-table` marker 付きで inject(post-process が detect して skip する)
- 既存 `_lineup_stats_block`(7 列、Yahoo stats 必須)は不変。本 extractor は 3 列 minimal table、Yahoo stats が無い時の代替(意味的 disjoint)
- subtype 文字列追加なし(`lineup` / `farm_lineup` 既存維持)
- env flag 追加なし(本 helper の挙動は extractor の戻り値だけで gate、勝手に発火しない)

(以降、phase 完了ごとに append)

## 10. Regression Memo 欄

- これは公開ゲートの問題ではない(別 ticket: `2026-05-12_hochi-fresh-pregame-backlog-publish-policy.md`)
- これは RSS 取得 / mail 通知 / X 投稿の問題でもない
- 表形式化は **新規生成記事のみ** 対象、公開済み記事は触らない
- 表データに欠損がある時は prose fallback で必ず描画(silent skip 禁止、warning log 必須)
- LLM に HTML を組ませない(deterministic renderer / extractor で組む、prompt drift 防止)
- noindex + 手動 X 運用フェーズなので、SEO 観点での評価軸は本 ticket では持たない
- 表 hook 点は subtype 別に narrow 配置、既存 subtype 文字列を変えない
- 既存 narrow `rss_lineup_table_post_process.py` との二重描画 guard を実装
- Phase は 2A → 2B → 2C → 2D の 4 段階、各 phase は独立 commit + 独立 image rebuild + 独立 revision flip(rollback 単位)
- Phase 2A + 2B は scope disjoint なら並行可、ただし commit は直列(`.git/index.lock` 衝突防止 + 234-impl-7 の commit 直列原則)
- 関連 ticket:
  - `2026-05-12_pregame-info-table-format.md`(narrow post-process、本 ticket の前段、`68e836d` 着地済)
  - `2026-05-12_hochi-fresh-pregame-backlog-publish-policy.md`(公開ゲート、別便)
  - `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08`(手動 vs 自動の品質差、本 ticket と部分重複、Phase 0 で重複整理)
  - `H3-STRUCTURE-UNIFY-2026-05-08`(H3 構造統一、別便)
  - `FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08`(enrichment 装飾の live audit、別便)
  - `309-QA-postgame-table-and-x-reaction-expansion`(postgame table for manual_intake、本ticket は RSS auto 経路、disjoint)

---

## 作業後追記欄

### Phase 2A(2026-05-12 PM、user GO 後実装)

#### 1. 実際に変更したファイル

- **NEW** `src/source_hochi_compact_lineup_extractor.py`(177 行、報知 / スポニチ X compact 形 lineup parser、`parse_hochi_compact_lineup` + `is_hochi_sponichi_source` public API)
- **NEW** `tests/test_source_hochi_compact_lineup_extractor.py`(18 case、source allowlist + parse 動作 + edge case)
- **NEW** `tests/test_rss_fetcher_hochi_compact_lineup_table.py`(5 case、bug 再現 integration test。fix 前 RED 2 件、fix 後 全 GREEN)
- **EDIT** `src/rss_fetcher.py`(+105 行 / -0 行、5 箇所 narrow addition、既存行 1 行も touch せず)
  - import block(line 149-154、6 行追加)
  - `build_news_block` 内 `compact_lineup_rows` 初期化 + extractor 呼出(line 15109-15134、26 行追加)
  - nested helper `_build_basic_lineup_table_block`(line 15745-15793、49 行追加)
  - `_flush_section` 内 inject branch 2 件追加(line 16268-16285、18 行追加、`elif` で既存 `lineup_stat_rows` branch と排他、新 `farm_lineup` branch 独立)
  - 末尾 inject elif 追加(line 16400-16405、6 行追加、`lineup_stat_rows` の後段 fallback)
- **EDIT** `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md`(本 file、post-work 追記)

#### 2. diff 概要

- LLM 不使用の現 production 環境(`ARTICLE_AI_MODE=none`)で、報知 / スポニチ X 由来の compact 形 lineup tweet(`D東妻 7萩尾3加藤 9皆川...`)を構造化抽出 → 3 列 HTML `<table class="nomotoke-card-lineup-table">`(打順 / 守備 / 選手) として `build_news_block` 出力に inject
- 1軍 (`article_subtype=="lineup"`):「【試合概要】」h3 直後に inject(Yahoo `lineup_stat_rows` がある時は既存 7 列 table 優先、無い時のみ compact 由来 3 列 table)
- 2軍 (`article_subtype=="farm_lineup"`):「【二軍スタメン一覧】」h3 直後に inject(Yahoo path 元々無し)
- ガード: source は 報知/スポニチ family のみ(allowlist + URL substring)、lineup keyword 必須、巨人公式X clean format 検出時は既存 `source_x_lineup_extractor` に委ね skip、min 8 token、`(position, name)` で dedupe、cap 22
- 既存 `_lineup_stats_block` / `_lineup_watch_block` / `_build_lineup_safe_fallback` / `_build_farm_lineup_safe_fallback` / `nomotoke_card_renderer.py` / `nomotoke_rss_router.py` / `rss_lineup_table_post_process.py` 本体は **1 行も touch しない**
- subtype 文字列追加なし、env flag 追加なし、Cloud Run / Scheduler / Secret 不変

#### 3. 実行したテスト

- **RED 確認**: `python3 -m unittest tests.test_rss_fetcher_hochi_compact_lineup_table` (実装前) → 5 件中 2 件 FAIL(`test_hochi_farm_lineup_compact_body_contains_lineup_table`, `test_hochi_first_team_lineup_compact_renders_table_when_yahoo_empty`)、3 件 PASS(player_names 含有 / Yahoo case / non-hochi regression)
- **GREEN 確認**: `python3 -m unittest tests.test_rss_fetcher_hochi_compact_lineup_table` (実装後) → 5/5 OK
- **新 unit 確認**: `python3 -m unittest tests.test_source_hochi_compact_lineup_extractor` → 18/18 OK
- **AST + compile**: `python3 -c "import ast; ast.parse(...)"` + `python3 -m py_compile` 両 src + 両 test 全 pass
- **全件**: `python3 -m unittest discover -s tests`(下記 §4 参照)

#### 4. テスト結果

- **fire-time baseline (HEAD `51acaa0` / Phase 0)**: 3461 tests OK / 0 fail (`Ran 3461 tests in 68.888s`)
- **Phase 2A 着地後 (本 commit 直前 full suite)**: `Ran 3484 tests in 73.065s` / **OK / 0 fail / 0 error**
- collect 増分: 3461 → 3484(+23 = 5 integration + 18 extractor unit、想定通り完全一致)
- 増加 fail: **0**、既存 3461 件は全件不変

#### 5. 残った懸念

1. **2軍 fixture の team 識別未実装**: 報知 ファーム lineup は DeNA + 巨人 の 2 チーム lineup が 1 tweet に concat されている。現実装は 20 行を単一 table で出すため、読者が「どっちが巨人か」を判定できない。Phase 2A の初期版としてはまず table を出すことを優先(empty H3 解消)。team 識別 + 2 table split は後続 ticket(Phase 2B 着地後 or 別便)。
2. **Phase 2B 未着手**: スポニチ emoji 形(`1️⃣ 三塚(D)2️⃣ 小濱⑹...`) は本便 scope 外、別 phase。
3. **Phase 2C / 2D 未着手**: 先発投手 / 試合結果 の table 化は別 phase。
4. **prod 実環境観察未実施**: 本便着地後の実 RSS 流入で extractor が想定通り発火するかは deploy 後 verification(user 判断境界)で確認する。
5. **既存 `rss_lineup_table_post_process.py`(`68e836d`、`ENABLE_RSS_LINEUP_TABLE_POST_PROCESS=1`) との重複**: 本便 inject の table HTML は `nomotoke-card-lineup-table` marker class を含むため、同 post-process の gate(line 128-129、marker 既存時 skip)で短絡され double-decoration は起きないと設計上判断。本便で post-process は 1 行も touch しない。実環境の double-render 有無は deploy 後観察で確認。

#### 6. 新しく見つかったデグレ

- 本便差分による新規デグレ **なし**(全件 3484 GREEN、既存 3461 件 fail 0 不変)
- 既存 path(Yahoo lineup_stat_rows / 巨人公式X / manual_intake / nomotoke_card_renderer 経由 manual flow)は flag/condition gate により本便 inject 経路に到達しない
- production 既存挙動は source allowlist 外(Yahoo / 巨人公式X 等)で本便 byte-identical

#### 7. 追加した回帰テスト

**`tests/test_source_hochi_compact_lineup_extractor.py`(18 case)**:
- `IsHochiSponichiSourceTests`(4 case): known names / japanese aliases / URL substring / unknown rejected
- `ParseHochiCompactLineupTests`(14 case):
  - `test_2gun_both_teams_extracts_all_unique_rows`(20 行)
  - `test_2gun_does_not_misparse_dena_team_label`(DeNA 誤抽出防止)
  - `test_1gun_solo_team_extracts_nine_rows`(9 行 + position mapping 全数)
  - `test_dh_letter_d_maps_to_kanji_shi`(DH = 指)
  - `test_official_x_clean_format_returns_none`(double-extract 防止)
  - `test_non_hochi_source_returns_none`(allowlist gate)
  - `test_keyword_missing_returns_none`(keyword gate)
  - `test_too_few_tokens_returns_none`(< 8 row gate)
  - `test_empty_or_whitespace_returns_none`(空 input)
  - `test_html_tags_stripped_before_parse`(HTML 除去)
  - `test_full_width_digits_normalised`(NFKC 全角→半角)
  - `test_url_only_admit_when_name_missing`(URL 経由 allowlist)
  - `test_rows_are_deduped_by_position_and_name`(`(pos, name)` dedupe)
  - `test_returned_keys_and_types`(return shape contract)

**`tests/test_rss_fetcher_hochi_compact_lineup_table.py`(5 case)**:
- `test_hochi_farm_lineup_compact_body_contains_lineup_table`(2軍 bug 再現、fix 前 RED)
- `test_hochi_farm_lineup_compact_body_contains_player_names`(player names presence、prose path でも GREEN だが table path で reinforce)
- `test_hochi_first_team_lineup_compact_renders_table_when_yahoo_empty`(1軍 + Yahoo 空、fix 前 RED)
- `test_hochi_first_team_lineup_with_yahoo_stats_keeps_yahoo_table_only`(double-render 防止 regression)
- `test_non_hochi_source_lineup_unchanged_when_yahoo_empty`(allowlist 外 regression)

#### 8. 次回触ってはいけない範囲

- **`src/nomotoke_card_renderer.py`**: 本便は consumer 追加のみで renderer 本体は不変。Phase 2C/2D で `_render_starter_rotation_table` 追加時は別便 + 別 commit。
- **`src/nomotoke_rss_router.py`**: production 不使用の dry-run/documentation file。`route_rss_entry_to_nomotoke_card` は本便不変、`RSS_ONLY_BLOCKED_TEMPLATES` は production 経路と関係なし。
- **`src/source_x_lineup_extractor.py` / `src/source_yahoo_lineup_extractor.py` / `src/source_yahoo_boxscore_extractor.py`**: 本便は新 extractor 追加のみ、既存 extractor は不変。
- **`src/rss_lineup_table_post_process.py` + `ENABLE_RSS_LINEUP_TABLE_POST_PROCESS` env**: 本便で touch せず。重複時の整理(default OFF or 削除)は別便で user 判断後。
- **`src/build_news_block` の他の段(intro / `_lineup_watch_block` / `_postgame_result_block` / `_livegame_result_block` / `_player_daily_stat_block` / `_player_confirmed_fact_block` / 関連記事 / fan reaction)**: 本便 inject は新 helper の追加のみ、既存段の動作は不変。
- **`src/_select_template_v2` / `_resolve_rss_story_type_context_v2`**: subtype 判定 logic は本便不変。
- **`src/guarded_publish_runner.py` / `src/guarded_publish_evaluator.py` / `src/publish_notice_email_sender.py` / `src/publish_notice_scanner.py`**: 公開ゲート / mail 通知、本便完全不変。
- **`config/rss_sources.json`**: source 追加 / 削除 / URL 変更なし。
- **Cloud Run env / Secret / Scheduler / GitHub Actions / build / deploy**: 本便で apply しない。
- **234-impl-7 `_validate_pregame_anchor` / 247-QA postgame strict slot-fill / 254-QA innings normalization / 309-QA postgame manual_intake table**: 全て disjoint scope、本便不変。

### Phase 2B / 2C / 2D 着手時の備考

- 本 §2A の hook pattern(extractor → `compact_lineup_rows` 経路 + `_build_basic_lineup_table_block`-style helper + narrow inject)を再利用可能。
- 2B(スポニチ emoji 形)は extractor 追加のみで `compact_lineup_rows` を流用、helper 共有。1 commit 想定。
- 2C(先発ローテ)は新 extractor + 新 helper(`_build_starter_rotation_table_block`)+ 新 inject 点(pregame body composer)。renderer 追加伴う場合は別便分離。
- 2D(試合結果)は postgame body composer に同 pattern で hook、`render_postgame_card` の data contract(yahoo_boxscore extractor 互換)を target に extractor 出力。
