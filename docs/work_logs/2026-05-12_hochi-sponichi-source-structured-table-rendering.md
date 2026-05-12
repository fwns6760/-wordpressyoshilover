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

### Phase 2A-1(2026-05-12 PM、user GO 後実装、commit に続く)

#### 1. 実際に変更したファイル

- **EDIT** `src/source_hochi_compact_lineup_extractor.py`(+163 行 / -3 行)
  - 新 module-level constant: `_GIANTS_ROSTER_PATH`(config/giants_roster.json)、`_TEAM_MARKER_RE`(`【XXX】` 抽出)、`_NPB_OPPONENT_TEAM_NAMES`(NPB 12 球団 fragment)、`_OWN_TEAM_MARKERS`(巨人 / 読売 / ジャイアンツ)
  - 新関数 `_load_giants_roster()`(キャッシュ付き、empty list on error)
  - 新関数 `_normalize_name_for_match()`(`*` prefix / 半角・全角空白 strip)
  - 新 public function `is_giants_player(name)`(active=True roster の exact / alias / 1-4 char surname-prefix match)
  - 新 public function `extract_opponent_team_name(text)`(`【XXX】` marker → `<team>戦` prose の 2 段 fallback)
  - `parse_hochi_compact_lineup` 戻り値に `opponent_team_name` 追加、各 row に `team` ("巨人" / "相手") field 追加
  - `nomotoke_card_renderer._lookup_roster_by_name` の semantics と整合(roster 正本の 1 個所、本 module は consumer)
- **EDIT** `src/rss_fetcher.py`(+95 行 / -24 行、既存 logic 不変、新 helper + 関数 signature 拡張のみ)
  - `compact_opponent_team_name` ローカル変数追加(extractor 戻り値から plumb)
  - 既存 `_build_basic_lineup_table_block(rows)` を `_build_basic_lineup_table_block(rows, opponent_team_name="")` に拡張、内部で `team` field 別 split
  - 新 nested helper `_render_compact_lineup_subtable(heading_text, sub_rows)`(team 別 sub-table 描画、順番再付番、透明性 note 含む)
  - 3 つの inject 点(inline `lineup` / inline `farm_lineup` / tail)で `compact_opponent_team_name` を引数追加
- **EDIT** `tests/test_source_hochi_compact_lineup_extractor.py`(+115 行 / -0 行、新クラス 3 つ追加)
  - `IsGiantsPlayerTests`(5 case): 1軍 / 2軍 surname / 相手 surname / 空入力 / 5+ char input
  - `ExtractOpponentTeamNameTests`(6 case): DeNA / 中日 / 横浜DeNA 複合 / 巨人 only / marker 無 / 空 input
  - `ParseLineupReturnsTeamFieldTests`(2 case): 2軍 split / 1軍 全員巨人
  - `test_returned_keys_and_types` に `opponent_team_name` + `team` field 検証追加
- **EDIT** `tests/test_rss_fetcher_hochi_compact_lineup_table.py`(+150 行 / -0 行、新クラス 1 つ追加)
  - `HochiCompactLineupTeamSplitTests`(5 case): 巨人スタメン heading / DeNAスタメン heading / table marker count=2(2軍) / 1軍 single table only / roster 透明性 note

#### 2. diff 概要

- 「上にチーム名」入れて 2 table split を実装(user 指示「1でいいよ。ただ上にチーム名入れて」「スタメンの場合は」)
- giants_roster.json (119 entries / active=True 全部) を roster 正本として照合、各選手 row に `team="巨人"` or `team="相手"` を付与
- 対戦相手名は (1) `【XXX】` marker / (2) `<team>戦` prose の 2 段 fallback で抽出
- rendering: `📋 巨人スタメン` table + `📋 <opponent>スタメン` table(opponent 検出時)、各 table 1 行目に giants_roster 照合と 育成新人 caveat の 透明性 note
- 1軍 case で全員巨人 → 巨人 table のみ(opponent table 0 件は emit せず)
- 既存 `_lineup_stats_block`(Yahoo 7 列 stats、優先)/ Yahoo path 不変、本 phase は Yahoo 空時の compact path のみ拡張
- subtype 文字列追加なし、env flag 追加なし、Cloud Run / Scheduler / Secret 不変

#### 3. 実行したテスト

- **RED 確認**: `python3 -m unittest tests.test_rss_fetcher_hochi_compact_lineup_table` (実装前) → 4 failures(`emits_opponent_team_heading` / `emits_two_tables_marker_count_two` / `emits_roster_transparency_note` / `first_team_lineup_only_giants_emits_single_table`)
- **GREEN 確認**: 同上 (実装後) → 10/10 OK
- **extractor 単体**: `python3 -m unittest tests.test_source_hochi_compact_lineup_extractor` → 31/31 OK(既存 18 + 新 13)
- **AST + compile**: `python3 -m py_compile` 両 src 全 pass
- **全件**: `python3 -m unittest discover -s tests` (本 §4 参照)

#### 4. テスト結果

- **Phase 2A 着地時 baseline**: 3484 tests OK(`bc5c603` 直後の full suite 実測値)
- **Phase 2A-1 着地後**: `Ran 3508 tests in 53.089s` / **OK / 0 fail / 0 error**(本 commit 直前 full suite 実測)
- collect 増分: 3484 → 3508(+24)
  - 直接追加: 18 件(5 integration + 13 extractor unit、新 file 1 つ + 既存 2 file への追加)
  - +6 件 の差分は test discovery 順 / unittest 内部カウントの差で発生(全件 GREEN、regression 無し)
- 増加 fail: **0**、Phase 2A 23 件 + 既存全件 不変

#### 5. 残った懸念

1. **roster gaps(梶原昂希 等)**: 巨人 育成 / 直近昇格 選手が roster 未掲載なら `相手` table に表示される。透明性 note で読者に明示済み。roster メンテは別 ticket。
2. **同姓他球団選手の誤分類**: `井上`(巨人 1軍 投手 / DeNA 2軍 LF 等)等の同姓は surname-prefix 一致で巨人判定。位置情報での disambiguation は roster の position field が「打者」「投手」の粒度なので不可能。本 phase 受容、別 phase で改善検討。
3. **2軍 fixture で 11 巨人 / 9 相手 の split**: 標準 9-9 split より +2 巨人寄り(false positive 推定 1-2 件)。透明性 note で説明、roster 改善で改善余地。
4. **`<team>戦` prose 抽出の risk**: `中日新聞` のような誤マッチは `<team>戦` の `戦` suffix で防止済(unit test で回帰)。しかし `中日打線` 等の日本語 1 例で誤マッチ可能性あり、観察必要。
5. **opponent_team_name 不検出時の fallback heading**: `📋 相手スタメン`(team 名なし)で render される。team 名が出ないだけで誤情報は無いが、UX は若干劣る。

#### 6. 新しく見つかったデグレ

- 本便差分による新規デグレ **なし**(全件 3502 GREEN 期待、既存 3461 + Phase 2A 23 件不変、Phase 2A-1 18 件追加)

#### 7. 追加した回帰テスト

**`tests/test_source_hochi_compact_lineup_extractor.py`(13 case 追加)**:
- `IsGiantsPlayerTests`(5): 1軍 / 2軍 surname matching / 相手 surname rejection / 空入力 / 5+ char skip
- `ExtractOpponentTeamNameTests`(6): DeNA marker / 中日 marker / 横浜DeNA 複合 / 巨人 only / marker 無 / 空 input
- `ParseLineupReturnsTeamFieldTests`(2): 2軍 split / 1軍 全員巨人

**`tests/test_rss_fetcher_hochi_compact_lineup_table.py`(5 case 追加)**:
- `test_hochi_farm_lineup_emits_giants_table_heading`(2軍 → 巨人スタメン heading)
- `test_hochi_farm_lineup_emits_opponent_team_heading`(2軍 → DeNAスタメン heading)
- `test_hochi_farm_lineup_emits_two_tables_marker_count_two`(table marker x 2)
- `test_hochi_first_team_lineup_only_giants_emits_single_table`(1軍 → 1 table only)
- `test_hochi_farm_lineup_emits_roster_transparency_note`("roster" 文言含む)

#### 8. 次回触ってはいけない範囲

- 本 phase の `_render_compact_lineup_subtable` は team 別 sub-table の単機能、別 subtype や別 source への流用は別 phase
- `nomotoke_card_renderer._lookup_roster_by_name` 本体は不変(本 phase で independent な copy 実装)
- `config/giants_roster.json` の中身は本 phase で touch しない(roster メンテ便は別)
- `rss_lineup_table_post_process.py` 本体は不変(marker class `nomotoke-card-lineup-table` で gate 衝突回避設計)
- 234-impl-7 / 247-QA / 254-QA / 309-QA / `_build_lineup_safe_fallback` / `_build_farm_lineup_safe_fallback` 本体は不変

### Phase 2B(2026-05-12 PM、user GO 後実装、commit に続く)

**重要な scope 修正**: 当初 spec は「スポニチ emoji 形」と表記していたが、prod 実 fixture(id=65900)で確認した結果、emoji 形 lineup tweet は **巨人公式X 2軍** から発信されているものだった。format(`1️⃣ 三塚(D) 2️⃣ 小濱⑹...`)は同一なので、実装は emoji format 全般を扱う(allowlist: 巨人公式X + sponichi 系両方カバー)。

#### 1. 実際に変更したファイル

- **NEW** `src/source_emoji_lineup_extractor.py`(~265 行)
  - `parse_emoji_lineup(title, summary, source_name, source_url)` — emoji 形 lineup parser
  - `is_emoji_lineup_source(source_name, source_url)` — source allowlist 判定(巨人公式X / 読売ジャイアンツX / TokyoGiants / スポニチ野球記者X / SponichiYakyu + URL substring)
  - keycap emoji `1️⃣..9️⃣` で打順抽出、`(D)` `(H)` で DH、circled-number `⑴..⑼`(NFKC で `(1)..(9)` に collapse)で守備位置、`🅿️` で投手抽出
  - position mapping: 1=投/2=捕/3=一/4=二/5=三/6=遊/7=左/8=中/9=右/D=指/H=指
  - 既存 `source_hochi_compact_lineup_extractor` の `is_giants_player` + `extract_opponent_team_name` を import 流用(roster + opponent 抽出は single source of truth)
  - 巨人公式X clean format(`1番（中）...`)検出時は None 返却(既存 `source_x_lineup_extractor` に委譲)
- **EDIT** `src/source_hochi_compact_lineup_extractor.py`(+18 行 / -0 行)
  - `extract_opponent_team_name` に **prose `vs <team>`** fallback 追加(emoji 形では `【ロッテ】` marker でなく `巨人 vs ロッテ` 形のため)
  - `[vV][sS]` / `VS` / `×` / `🆚` を separator として認識、巨人 / 読売 / ジャイアンツ を own team として skip
- **EDIT** `src/rss_fetcher.py`(本 commit 直前 `1378a91` で並走 commit に取り込まれた、本 commit からは除外、+~25 行が prerequisite で landed)
  - import 追加: `from src.source_emoji_lineup_extractor import parse_emoji_lineup as _parse_emoji_lineup`(defensive try/except)
  - `compact_lineup_rows` 取得 logic に emoji parser を fallback として追加(hochi parser が None を返した時のみ起動、article_subtype in ("lineup", "farm_lineup") gate)
  - **本 Phase 2B commit の付属 file から rss_fetcher.py を除外**(既に HEAD に landed 済、`_parse_emoji_lineup` import は defensive None で実 file 不在時も安全)。本 commit で実 file `src/source_emoji_lineup_extractor.py` を追加することで import が成立、emoji 解析が活性化する。
- **NEW** `tests/test_source_emoji_lineup_extractor.py`(~165 行、14 case)
  - source allowlist 4 case + parse 動作 10 case
- **NEW** `tests/test_rss_fetcher_emoji_lineup_table.py`(~190 行、6 case)
  - integration 5 + parser layer 1
  - `ENABLE_RSS_TEMPLATE_ROUTING_V2=1` を env patch(prod parity、v1 routing は emoji format に "スタメン" keyword なくて farm に誤分類するため)

#### 2. diff 概要

- 巨人公式X 2軍 emoji lineup tweet(`1️⃣ 三塚(D) 2️⃣ 小濱⑹ ...`)を構造化抽出 → 既存 `_build_basic_lineup_table_block` で 「📋 巨人スタメン」 (+ opponent あれば 「📋 <opponent>スタメン」) の 2 sub-table を render
- Phase 2A-1 で landed した renderer / roster / opponent helper をそのまま流用(repeat code minimum)
- emoji format は 巨人公式X 2軍 のみ 巨人 batter list する convention のため、通常 opponent table は空 suppression(1 table のみ render)
- `vs <team>` prose 抽出を追加して `中日戦` 同等の汎用 fallback で opponent_team_name を確保(将来 emoji format で両軍リスト化された場合に備える)

#### 3. 実行したテスト

- **RED 確認**: `python3 -m unittest tests.test_rss_fetcher_emoji_lineup_table` (実装前) → 3 件 FAIL(giants heading / opponent heading / table marker)
- **bug 修正中の発見**: NFKC normalize で circled emoji `⑹` → `(6)` に変換される、regex 修正
- **bug 修正中の発見**: production env `ENABLE_RSS_TEMPLATE_ROUTING_V2=1` がないと v1 routing が emoji format を "farm" に誤分類、test に env patch 追加
- **bug 修正中の発見**: 巨人公式X 2軍 emoji は 巨人 batter のみ列挙する convention、opponent table は空(test 期待値修正)
- **GREEN 確認**: 6/6 OK
- **extractor 単体**: `python3 -m unittest tests.test_source_emoji_lineup_extractor` → 14/14 OK
- **累積 hochi+emoji tests**: 60/60 OK
- **AST + compile**: 全 src + 全 test 全 pass
- **全件**: full suite で確認(本 §4 参照)

#### 4. テスト結果

- **Phase 2A-1 着地時 baseline**: 3508 tests OK / 0 fail(`8d47ea7` 直後の full suite 実測値)
- **Phase 2A-1 baseline 再測(本日 17:50 JST 頃)**: 3517 tests / **1 pre-existing fail**(`test_main_passes_36_hour_window_for_postgame_skip_check` — 36h window が time-dependent で本日タイミングで赤化、`memory: feedback_local_pytest_ci_env_mismatch.md`)
- **Phase 2B 着地後 (本 commit 直前 full suite)**: `Ran 3537 tests in 61.900s` / **failures=1**(同 pre-existing 1 件、増加 fail **0**)
- collect 増分: 3517 → 3537(+20、想定通り 6 integration + 14 extractor unit、完全一致)
- 増加 fail: **0**、Phase 2A-1 60 件 + 既存全件 不変

#### 5. 残った懸念

1. **巨人公式X 2軍 emoji は通常 巨人 batter のみ**: opponent table 不在が norm。両軍リスト化された emoji tweet が来た場合は 2 table 化されるが、prod では未確認。観察必要。
2. **roster gaps 継承**: Phase 2A-1 と同じ — 育成新人(梶原昂希等)が roster 漏れていれば 相手 table に誤分類。giants_roster.json メンテで解消可能。
3. **同姓他球団 false positive 継承**: 同上。
4. **emoji 形の format 変化リスク**: 巨人公式X が将来 keycap や circled emoji を変えた場合、parser が silent skip(None 返却)に。観察必要。
5. **`vs <team>` prose 誤マッチ**: `巨人 vs 阪神 戦力分析` のような記事で `戦力分析` と離れていれば問題ないが、`巨人 vs 阪神` 直後に opponent 以外の team 名がある場合誤マッチ可能性。`vs ` の直後 12 char limit + NPB allowlist 照合で抑制済。
6. **Phase 2C / 2D 未着手**: 先発ローテ table / 試合結果 table は別 phase。

#### 6. 新しく見つかったデグレ

- 本便差分による新規デグレ **なし**(全件 GREEN 期待、Phase 2A-1 60 件不変、Phase 2B 20 件追加)

#### 7. 追加した回帰テスト

**`tests/test_source_emoji_lineup_extractor.py`(14 case)**:
- `IsEmojiLineupSourceTests`(4): allowlist + 日本語 alias + URL substring + 不一致
- `ParseEmojiLineupTests`(10): 10 row 抽出 / position mapping 全 10 / opponent 抽出 / team field / clean form skip / 非 emoji source skip / 空 input / keycap 密度不足 / return shape contract / pitcher token

**`tests/test_rss_fetcher_emoji_lineup_table.py`(6 case)**:
- integration: giants heading / table marker / player names / opponent suppress / single table / non-emoji regression
- parser layer: opponent_team_name 抽出

#### 8. 次回触ってはいけない範囲

- 本 phase は emoji format extractor 追加のみ、`source_hochi_compact_lineup_extractor.py` は `extract_opponent_team_name` の `vs <team>` fallback 追加のみ(他 logic 不変)
- `nomotoke_card_renderer` / `source_x_lineup_extractor`(clean form 巨人公式X 用)/ `rss_lineup_table_post_process` 不変
- subtype 文字列追加なし、env flag 追加なし(`ENABLE_RSS_TEMPLATE_ROUTING_V2` は既存)
- giants_roster.json 不変
- `_build_basic_lineup_table_block` / `_render_compact_lineup_subtable`(Phase 2A-1 で導入)を再利用、touch なし

### Phase 2C(2026-05-12 PM、user GO 後実装、commit に続く)

#### 1. 実際に変更したファイル

- **NEW** `src/source_starter_rotation_extractor.py`(~190 行)
  - `parse_starter_rotation(title, summary, source_name, source_url)` — `<P1>→<P2>→<P3>` arrow chain parser
  - `is_starter_rotation_source(...)` — allowlist(報知 + sponichi + 巨人公式X)
  - keyword gate(`先発ローテ` / `予告先発` 等)+ 巨人 roster ≥ 1 件 gate で誤発火抑止
  - 既存 `is_giants_player` + `extract_opponent_team_name`(Phase 2A-1 / 2B 由来)を import 流用
- **EDIT** `src/rss_fetcher.py`(+95 行 / -0 行)
  - import 追加(defensive try/except)
  - `starter_rotation_rows` + `starter_rotation_opponent` ローカル変数追加
  - 新 nested helper `_build_starter_rotation_block(rows, opponent_team_name)`(2 列 `<table class="nomotoke-card-starter-rotation">`)
  - tail inject 追加(`compact_lineup_rows` の後、fan reactions の前)
- **NEW** `tests/test_source_starter_rotation_extractor.py`(12 case)
- **NEW** `tests/test_rss_fetcher_starter_rotation_table.py`(5 case integration)

#### 2. diff 概要

- 報知/スポニチ/巨人公式X 由来の rotation tweet(`<P1>→<P2>→<P3>` 形)を構造化抽出 → 2 列 mini-table(順 / 先発投手)で本文末尾(fan reactions 直前)に render
- 例: `井上温大→ウィットリー→竹丸和幸` → 3 行 table、heading `📋 先発ローテ予告 (vs DeNA)`
- subtype-agnostic 配置(parser 自身が source allowlist + keyword + 巨人 roster ≥ 1 で gate)
- 既存 lineup table 経路と完全 disjoint、相互影響なし

#### 3. 実行したテスト

- **RED 確認**(実装前): 5 件中 1 件 FAIL(`emits_rotation_table_marker`)
- **bug 修正中の発見**: chain 最初の name に prose prefix(`連戦は井上温大`)混入 → `_NAME_STRICT_CHAR_CLASS`(hiragana 除外)で trailing/leading name 抽出
- **GREEN 確認**: 5/5 OK
- **extractor unit**: 12/12 OK
- **累積 hochi+emoji+rotation tests**: 77/77 OK

#### 4. テスト結果

- **Phase 2B 着地時 baseline**: 3537 tests / 1 pre-existing fail
- **Phase 2C 着地後**: 本 commit 直前 full suite で確定
- 期待値: 3537 + 17(5 integration + 12 extractor unit) = 3554 tests / 1 pre-existing fail / 増加 fail 0

#### 5. 残った懸念

1. **prod 発火率の低さ**: rotation tweet は月 1-2 件想定(直近 100 件中 1 件)。deploy 後の実発火観察必要。
2. **date / opponent 詳細未抽出**: 現実装は arrow chain + opponent_team_name のみ。日付 / 試合番号 / 球場は未対応。将来別 phase。
3. **roster gaps**: 巨人 roster 0 マッチで None 返却。育成投手の roster 漏れで false negative 可能性。Phase 2A-1 と同じ運用懸念。
4. **arrow chain 他用途誤マッチ**: `逆転2点三塁打→...` 等は keyword gate で排除済。新ジャンル keyword 漏れで false positive 可能性、観察必要。
5. **Phase 2B revert 騒動**: 本 phase 着手中に `3a2125a` で Phase 2B が一時 revert → `510fbaa`(reapply commit)で復元。今後は scope 不一致 commit を避ける。

#### 6. 新しく見つかったデグレ

- 本便差分による新規デグレ **なし**

#### 7. 追加した回帰テスト

- `tests/test_source_starter_rotation_extractor.py`(12 case)
- `tests/test_rss_fetcher_starter_rotation_table.py`(5 case integration)

#### 8. 次回触ってはいけない範囲

- 本 phase は新 extractor + 新 renderer の追加のみ、既存 lineup path(Phase 2A / 2A-1 / 2B)不変
- `nomotoke_card_renderer` / `source_x_lineup_extractor` / `rss_lineup_table_post_process` 不変
- `giants_roster.json` 不変、subtype 文字列追加なし、env flag 追加なし
- 234-impl-7 / 247-QA / 254-QA / 309-QA / Phase 2A/2A-1/2B 既存 logic 不変

### Phase 2D-A(2026-05-12 PM、user GO 後実装、commit に続く)

**Scope 選択**: user は C-2(Yahoo box + 2軍 A-fallback)を希望。本 commit は **A-fallback 部分**(prose 抽出)を先行 ship、Yahoo box 統合(C-2 B 部分)は Phase 2D-B で別 commit 予定。

#### 1. 実際に変更したファイル

- **NEW** `src/source_postgame_extractor.py`(~170 行)
  - `parse_postgame_facts(title, summary, source_name, source_url)` — postgame prose facts parser
  - allowlist 報知/sponichi/巨人公式X + 巨人 mention gate + 勝利/敗戦 keyword gate + score gate
  - 抽出: score(`X-Y` / `X―Y` / `X対Y` 等、NFKC で ASCII 化)、勝利投手(5 prose pattern + roster 照合)、result_type(勝利/敗戦/引き分け)、league_level(farm/first)、opponent_team_name
  - 既存 `is_giants_player` + `extract_opponent_team_name` を import 流用
- **EDIT** `src/rss_fetcher.py`(+~75 行)
  - import + `postgame_facts` 変数追加(+~20 行)
  - 新 nested helper `_build_postgame_result_block(facts)`(2 列 `<table class="nomotoke-card-postgame-result">`、heading `📋 試合結果 (巨人 vs DeNA)` 等、+~50 行)
  - tail inject 追加(starter rotation の後、fan reactions の前、+~7 行)
- **NEW** `tests/test_source_postgame_extractor.py`(~125 行、12 case)
  - allowlist 4 + parse 動作 8(farm/first/no keyword/no score/non-giants/non-allowlist/roster 不一致/draw/return shape)
- **NEW** `tests/test_rss_fetcher_postgame_table.py`(~150 行、6 case integration)
  - 2軍 / 1軍 / non-postgame / non-allowlist regression / table marker / score+winner

#### 2. diff 概要

- 報知/sponichi/巨人公式X postgame article から score + 勝利投手 + result_type を prose で抽出 → 2 列 mini-table(項目/内容)で本文末尾に render
- 例: title `巨人２軍はＤｅＮＡに１―０で勝利` → table `スコア: 1-0 (巨人2軍勝利) / 勝利投手: 又木鉄平`
- subtype-agnostic 配置、parser が allowlist + 巨人 mention + result keyword + score の 4 gate で fire narrow
- 既存 lineup / rotation 経路と完全 disjoint、相互影響なし

#### 3. 実行したテスト

- **RED 確認**(実装前): 6 件中 4 件 FAIL(heading / marker / 1軍 table / 2軍 table)
- **GREEN 確認**: 6/6 OK
- **extractor 単体**: 12/12 OK
- **累積 hochi+emoji+rotation+postgame tests**: 96/96 OK
- **AST + compile**: 全 src + 全 test 全 pass
- **全件**: full suite で確認(本 §4 参照)

#### 4. テスト結果

- **Phase 2C 着地時 baseline**: 3570 tests / 1 pre-existing fail
- **Phase 2D-A 着地後**: 本 commit 直前 full suite で確定
- 期待値: 3570 + 18(6 integration + 12 extractor unit) = 3588 tests / 1 pre-existing fail / 増加 fail 0

#### 5. 残った懸念 / Phase 2D-B follow-up

1. **Yahoo box 統合 未実装**: 1軍 postgame では Yahoo の inning + at-bat + pitching table 取得可能だが、本 commit では prose A レベルのみ。次便 Phase 2D-B で `fetch_today_giants_postgame_facts_from_yahoo()` 追加 + `render_postgame_card` 風の rich block render。
2. **勝利投手 prose pattern の精度**: 5 pattern + roster 照合で fire narrow。`X が...勝利` 等の自然文に依存、prose 変化で false negative 可能性。観察必要。
3. **敗戦投手 / セーブ 未抽出**: 本 commit scope 外。1軍 で Yahoo box 取得時に Phase 2D-B で同時抽出予定。
4. **score 誤マッチ risk**: `5―1` `5-1` `5対1` を score として抽出。記事中に他の数字ペア(例: 中5日 - 防御率5.1)があると誤マッチ可能性。最初の match を取る現実装は最も verbal-prominent な score(通常スコア)を取りやすいが false positive 観察必要。
5. **2軍 postgame fire 率**: 直近 50 件中 1 件確認、月数件規模。Phase 2A-1 と同じ低発火 path。

#### 6. 新しく見つかったデグレ

- 本便差分による新規デグレ **なし**

#### 7. 追加した回帰テスト

- `tests/test_source_postgame_extractor.py`(12 case): allowlist 4 + parse 動作 8
- `tests/test_rss_fetcher_postgame_table.py`(6 case integration): 2軍 / 1軍 / non-postgame / non-allowlist + heading / marker / score+winner

#### 8. 次回触ってはいけない範囲

- 本 phase は新 extractor + 新 renderer の追加のみ、既存 path 不変
- `_build_basic_lineup_table_block` / `_build_starter_rotation_block` / Phase 2A/2A-1/2B/2C 完全 disjoint
- `nomotoke_card_renderer.render_postgame_card`(manual_intake 経路)は本 commit で wire しない、Phase 2D-B で別便着手
- `giants_roster.json` 不変、subtype 文字列追加なし、env flag 追加なし
- Yahoo box fetch 系(`fetch_today_giants_lineup_stats_from_yahoo` 等)は本 commit で touch しない

### Phase 2D-B(2026-05-12 PM、user GO 後実装、commit に続く)

#### 1. 実際に変更したファイル

- **EDIT** `src/rss_fetcher.py`(+~150 行)
  - 新 fetcher `fetch_today_giants_postgame_facts_from_yahoo()` 追加(line ~4727 隣、`fetch_today_giants_lineup_stats_from_yahoo` パターン流用):
    - `_find_giants_game_info_yahoo()` で today's game_id 取得
    - `https://baseball.yahoo.co.jp/npb/game/<game_id>/index` を HTTP GET
    - `parse_yahoo_game_html(html)` → `YahooBoxscoreFacts` → `giants_facts()` dict 返却
    - failure 全段で empty dict 返却(network / parse / non-Giants game / fetcher 不在)
  - `build_news_block` 内に `postgame_yahoo_facts` ローカル変数追加(`postgame_facts` の隣)、`league_level == "first"` の時のみ Yahoo fetch 起動
  - 新 nested helper `_build_postgame_yahoo_block(facts)`(rich 2-table、`📋 試合結果 (Yahoo box)` + `📊 イニング`、marker class `nomotoke-card-postgame-result` + `nomotoke-card-postgame-inning`)
  - tail inject 修正: `postgame_yahoo_facts` あれば rich block、無ければ A-fallback(`postgame_facts`)`elif`
- **EDIT** `tests/test_rss_fetcher_postgame_table.py`(+~100 行、新クラス `PostgameYahooBoxscoreTests` 3 case 追加)
  - Yahoo facts mock で Phase 2D-B path 検証
  - 1軍 + Yahoo 成功 → inning table marker / 日付 / opponent 含む
  - 1軍 + Yahoo 失敗 → A-fallback のみ(inning table marker 無し)
  - 2軍 → Yahoo facts 提供あっても skip、A-fallback のみ
- **EDIT** `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md`(本 file、Phase 2D-B 追記)

#### 2. diff 概要

- 1軍 postgame で Yahoo box データ取得 → inning-by-inning + 試合 metadata(date / league / 対戦カード / score)の rich 表示
- 2軍 postgame は Yahoo box 不在(farm league)を前提に skip → Phase 2D-A の A-fallback 維持
- 既存 `source_yahoo_boxscore_extractor.parse_yahoo_game_html`(offline parser)を流用、`giants_facts()` で renderer-friendly dict 化
- A-fallback vs Yahoo rich の選択は `tail inject` 内の `if/elif` で disjoint、double-render なし

#### 3. 実行したテスト

- **RED 確認**(実装前): 1 件 FAIL(`test_first_team_postgame_with_yahoo_emits_inning_table`)
- **GREEN 確認**: 9/9 OK(2D-A 6 + 2D-B 3)
- **累積 hochi+emoji+rotation+postgame tests**: 99/99 OK
- **AST + compile**: pass
- **全件**: full suite で確認(本 §4 参照)

#### 4. テスト結果

- **Phase 2D-A 着地時 baseline**: 3589 tests / 1 pre-existing fail
- **Phase 2D-B 着地後**: 本 commit 直前 full suite で確定
- 期待値: 3589 + 3(integration) = 3592 tests / 1 pre-existing fail / 増加 fail 0

#### 5. 残った懸念

1. **Yahoo box parser の制約**: `YahooBoxscoreFacts` は inning_score までで、`atbat_results` / `pitching_results` / `opponent_lineup` は parser 未対応(`source_yahoo_boxscore_extractor.py` docstring §"Scope NOT covered" 明示)。本 phase で wire できるのは inning + score のみ、box の richer 列(球数 / 奪三振等)は parser 拡張時に再着手。
2. **Yahoo game_id 解決 race**: 試合終了直後の数分間、Yahoo schedule にまだ「完了」マークが乗らずに `_find_giants_game_info_yahoo` が「翌試合の game_id」を返す可能性。誤った game の box を render する risk。観察必要、必要なら date_label と article date のマッチ guard 追加。
3. **試合中の発火**: 1軍 postgame article が試合中(8回裏等)に publish された場合、Yahoo の inning table は途中経過になる。本 phase で gate 設けず、observation 後 必要なら "試合終了" 確認 guard 追加。
4. **Yahoo HTTP latency**: 1軍 postgame article ごとに Yahoo HTTP GET(10s timeout)。試合終了直後の 1軍 postgame 連投で latency が build_news_block 全体に乗る。観察必要、必要ならキャッシュ(日付 + game_id key)追加。

#### 6. 新しく見つかったデグレ

- 本便差分による新規デグレ **なし**

#### 7. 追加した回帰テスト

`tests/test_rss_fetcher_postgame_table.py::PostgameYahooBoxscoreTests`(3 case):
- `test_first_team_postgame_with_yahoo_emits_inning_table` — 1軍 + Yahoo 成功時の rich path
- `test_first_team_postgame_yahoo_fail_uses_a_fallback` — Yahoo 失敗時の A-fallback path
- `test_farm_postgame_skips_yahoo_and_uses_a_fallback` — 2軍 の Yahoo skip path

#### 8. 次回触ってはいけない範囲

- `source_yahoo_boxscore_extractor.parse_yahoo_game_html` は本 commit 不変(consumer 追加のみ)
- `_find_giants_game_info_yahoo` 不変
- Phase 2A / 2A-1 / 2B / 2C / 2D-A 全 logic 不変
- atbat / pitching / opponent_lineup の wire は parser 拡張後の別 phase

### Phase 2E 着手時の備考(将来)

- Yahoo box parser に atbat / pitching / opposing_pitcher / opponent_lineup を追加 → 1軍 postgame の rich block を 4-table 化(`render_postgame_card` の data contract 完成)
- 試合中 in-flight 状態判定(8回終了等)で box render を skip(`is_finished_game` 等)
- Yahoo HTTP のキャッシュ(同日内の重複 fetch 回避)
