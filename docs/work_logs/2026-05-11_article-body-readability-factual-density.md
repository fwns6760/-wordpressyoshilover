# 2026-05-11 記事本文の読み切り感・事実密度改善 作業記録

## 1. 今回の目的

読む人が一目で内容を理解できる記事本文にする。

現状の問題意識は、LLMっぽさではない。本文生成は LLM ではなく template / rule-based だが、記事によって読むために必要な情報量が足りず、結果として途中で終わったように見えることがある。

今回の目的は、推測や水増しをせず、取得済みの事実だけで以下を改善すること。
過去に良かった本文の型、既存で通っている文字数ルール、既存テンプレートの良い部分は変えない。今回扱うのは、必要情報が足りないケースへの狭い補強だけ。

- 冒頭で「何が起きたか」を言い切る
- 確認できる事実を 2〜4 点入れる
- 必要な情報が欠けたまま終わったように見える本文を出さない
- 既存の文字数ルールの範囲内で、情報が取れている記事の情報密度を上げる
- 情報が薄い記事でも、最低限「何の話か」「誰 / いつ / どこ」「出典」が分かる形にする
- 関連記事 / 関連選手 / タグだけが目立ち、本文本体が薄い状態を減らす

この Markdown 作成時点では、許可する変更は本 Markdown の新規作成のみ。
既存の本文文字数ルール、上限 / 下限、validation threshold、prompt 内の文字数指定は今回変更しない。

## 2. 今回触る範囲

この時点で触る範囲は、この作業記録 Markdown の新規作成のみ。

- `docs/work_logs/2026-05-11_article-body-readability-factual-density.md`

GO 後の実装候補は、以下に限定する。

- 記事本文生成のうち、必要情報 / 事実密度 / 読み切り感に関わる箇所
- `manual-intake-service` 経路の記事本文テンプレート
- 必要に応じた renderer / helper の narrow 修正
- 「必要情報が足りない」「途中で終わったように見える」「事実が足りない」ことを検出する回帰テスト
- 既存で良い出力をしている fixture / template を変えないための保持テスト
- 既存の文字数ルールを維持したまま本文構造を整えるテスト
- dry-run での本文確認
- 本 Markdown への作業後追記

初回実装は、対象を広げすぎないため `manual-intake-service` 経路を優先する。調査の結果、主原因が RSS fetcher / draft-body-editor / frontend 表示側だった場合は、勝手に広げず STOP して報告する。

## 3. 今回触らない範囲

- 公開済み WP 記事本文の修正
- WP post status 変更
- publish 条件
- mail 通知量
- Cloud Run env
- Scheduler
- Secret Manager
- GitHub Actions
- X API / X 自動投稿
- source 追加
- Gemini / Grok / LLM call 追加
- 既存の本文文字数ルール / threshold / prompt 文字数指定
- 画像 / アイキャッチ fallback policy
- 関連選手の同姓別人 guard
- 本文抜粋 context-drift guard
- noindex / canonical / 301
- AdSense / 320-FRONT / scroll UI
- WP frontend CSS / plugin UI
- unrelated dirty files

## 4. 影響範囲

GO 後に実装する場合の想定影響範囲は、新規生成される記事本文。

- 冒頭 lead 文
- 事実説明の行数 / 順序
- 出典表示の前後文脈
- 関連選手 / 関連タグ / 関連記事の前にある本文本体
- postgame / lineup / broadcast / manual intake 系の dry-run 出力
- publish 前の validation / review 判定

公開済み記事は観測対象に留め、直接修正しない。

## 5. 実行予定テスト

GO 後、実装内容に応じて以下を実行する。

- 実装前 grep / rg
  - `manual_intake`
  - `nomotoke_card_renderer`
  - `fact-card`
  - `本文`
  - `source excerpt`
  - `validation_ok`
  - `thin_body`
- 再現テスト赤
  - 必要情報が足りないケース
  - 情報不足で途中で終わったように見えるケース
  - 関連 block はあるが本文本体の事実が足りないケース
  - 既存の文字数ルールが変わっていないことの確認
- 修正後 targeted test
- 関連 test
- 変更 Python の `compileall`
- 変更 Python の AST parse
- `python3 -m unittest discover -s tests`
- 必要時のみ権限付き full unittest 再実行
- deploy が必要になった場合のみ、別 GO 後に以下を確認
  - Cloud Run revision
  - job dry-run success
  - ERROR log
  - 実出力 dry-run
  - publish / mail が止まっていないこと

## 6. STOP条件

以下の場合は停止する。

- 取得済み事実だけでは必要情報を補えず、推測が必要になる場合
- 読み切り感改善のために既存の文字数ルール変更が必要になる場合
- 元記事本文の長いコピーで文字数を増やす必要がある場合
- LLM call 追加が必要になる場合
- source 追加が必要になる場合
- publish / mail / scheduler / env / Secret に触る必要が出た場合
- 公開済み記事修正が必要になった場合
- 主原因が frontend 表示 / CSS / WordPress theme 側と判明した場合
- 主原因が RSS fetcher / draft-body-editor 側で、今回の write scope を超える場合
- `323-QA-source-body-excerpt-clean-truncation` と衝突する場合
- 必要情報を補った結果、事実誤認 / 所属誤認 / 同姓別人混入が起きる場合
- 既存の良い出力や既存ルールを置き換えないと実装できない場合
- Codex 側の新しい独自ルールで既存テンプレートを上書きしそうな場合
- full suite が赤のまま原因説明できない場合
- unrelated dirty files を巻き込みそうな場合

## 7. 禁止事項

- 記憶から事実を再構成する
- 取れていないコメント / 成績 / 所属 / 日程を補う
- 一般論や感想文で水増しする
- 元記事本文を長く転載する
- 既存の文字数ルール / threshold / prompt 文字数指定を変える
- 過去の良い出力パターンを Codex 側の新ルールで置き換える
- 既存テンプレート全体を再設計する
- LLM を追加して本文を補完する
- silent skip で理由を残さない
- 自己評価 OK で終わる
- 公開済み WP 記事を直す
- `git add -A`
- ついで修正
- env / scheduler / Secret / GitHub Actions 変更
- source 追加
- X API 使用
- AdSense / frontend UI 変更

## 8. 想定されるデグレ

- 情報補完が過剰になり、のもとけ型の短文テンポを失う
- 取得済み事実の並べ替えで重複表現が増える
- 出典前後の文がくどくなる
- 情報が薄い記事で無理に文章を増やし、素材メモ感が逆に強まる
- postgame / lineup / broadcast の既存テンプレートが崩れる
- 関連記事 / 関連選手 block との重複が増える
- validation が厳しすぎて生成記事が減る
- validation が緩すぎて必要情報不足の本文が残る
- 既存 fixture の期待 HTML が変わる
- full suite の広い snapshot / string test が落ちる

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-11 JST | work log 作成 | user 指示「品質上げて。急がず、省略せず、手順通り」に従い、まず作業記録 Markdown のみ作成。コード編集・commit・push・deploy・env変更・scheduler変更は未実施。 |
| 2026-05-11 JST | 起点整理 | 問題は LLM 由来ではなく、template / rule-based 本文で読むための必要情報が足りず、途中で終わったように見えること。 |
| 2026-05-11 JST | user 追加制約 | 既存の文字数ルールは変更しない。読み切り感改善は現行ルールの範囲内で行う。 |
| 2026-05-11 JST | user 追加制約 | 文字数ではなく情報量不足を扱う。短いこと自体を問題にしない。 |
| 2026-05-11 JST | user hard rule | AI は「記憶から再構成」「silent skip」「自己評価 OK」が最大の事故源。実装時はこの3点を禁止事項として扱う。 |
| 2026-05-11 JST | user 追加制約 | 過去の良いところは変えない。Codex の新ルールで既存テンプレートを勝手に置き換えない。 |

## 10. Regression Memo欄

- 「読みやすくする」は、推測で長文化することではない。
- 文字数ではなく、読者が「何の記事か」「確認できる事実は何か」「出典はどこか」を判断できることを重視する。
- 既存の文字数ルールは変えない。情報が取れている記事も、現行ルールの範囲内で構造と完結感を改善する。
- 過去の良い出力は保持する。今回の修正は、必要情報が足りないケースだけを狭く補強する。
- Codex が新しい本文ルールを勝手に作って、既存テンプレート全体を置き換えない。
- 情報が薄い記事は、無理に長くせず、最低限の事実と出典で完結させる。
- 本文が短いこと自体は問題ではない。必要情報が欠けて途中で終わったように見えること、本文本体より関連 block が目立つことを防ぐ。
- 公開済み記事は直さない。今後の生成に対する恒久 guard / template 改善 / regression test に限定する。
- AI 事故源として、記憶から再構成 / silent skip / 自己評価 OK を禁止する。
- 実装時は、再現テスト赤 → 修正 → 追加テスト緑 → 関連緑 → 全件緑の順に進める。

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/tools/manual_intake.py`
- `tests/test_manual_intake.py`
- `docs/work_logs/2026-05-11_article-body-readability-factual-density.md`

### 2. diff概要

- `src/tools/manual_intake.py`
  - sparse な title / summary だけでは必要情報が足りない場合に、同一記事と判断できる source page の `og:description` を renderer に渡す helper を追加。
  - 既存の文字数ルール、summary 値、validation threshold、prompt 文字数指定は変更なし。
  - `og:description` は既存の source excerpt context guard に通る場合だけ採用。別記事 HTML の混入時は使わない。
  - `short_news_url` は context-matched OG meta がある場合だけ renderer を通し、それ以外は従来 fallback を維持。
- `tests/test_manual_intake.py`
  - title / summary が薄く、同一記事の `og:description` に score / opponent / venue があるケースを赤→緑で追加。
  - unrelated な `og:description` が本文に混ざらない regression を追加。
- 本 Markdown
  - 実施内容、テスト、残懸念を追記。

### 3. 実行したテスト

- 赤確認:
  - `python3 -m unittest tests.test_manual_intake.ManualIntakeSourceOgDescriptionDensityTests`
- 修正後:
  - `python3 -m unittest tests.test_manual_intake.ManualIntakeSourceOgDescriptionDensityTests`
  - `python3 -m unittest tests.test_manual_intake.ManualIntakeSourceOgDescriptionDensityTests tests.test_manual_intake.RunManualIntakeTests tests.test_manual_intake.SourceBodyExcerptExpansionTests`
  - `python3 -m unittest tests.test_nomotoke_card_renderer.ShortNewsUrlBodyFixTests tests.test_nomotoke_card_renderer.BodyFix2FactExtractorTests tests.test_nomotoke_card_renderer.FactsOgDescriptionScanTests tests.test_nomotoke_card_renderer.RendererPhase2AOgWiringTests`
  - `python3 -m unittest tests.test_manual_intake`
  - `python3 -m compileall -q src/tools/manual_intake.py tests/test_manual_intake.py`
  - `python3 -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'), filename=p) for p in ['src/tools/manual_intake.py','tests/test_manual_intake.py']]; print('AST OK')"`
  - `python3 -m unittest discover -s tests`

### 4. テスト結果

- 赤確認:
  - `ManualIntakeSourceOgDescriptionDensityTests`: 2 tests / 1 failure
  - failure 内容: `og:description` にある `巨人は5-2でヤクルトに勝利。` / `東京ドーム` / `<td>5-2</td>` が本文に出ず、fallback body が `試合速報` だけで終わる。
- 修正後:
  - `ManualIntakeSourceOgDescriptionDensityTests`: 2 tests OK
  - manual intake related 22 tests OK
  - short_news renderer related 48 tests OK
  - `tests.test_manual_intake`: 79 tests OK
  - `compileall`: OK
  - `AST`: OK
  - full suite sandbox 内: `tests/test_manual_intake_service.py` の HTTPServer bind で 3 errors (`PermissionError: [Errno 1] Operation not permitted`)
  - full suite sandbox 外: 3430 tests OK

### 5. 残った懸念

- 今回は `manual-intake-service` 経路だけの narrow fix。RSS fetcher / draft-body-editor 側の本文情報不足は今回の scope 外。
- `short_news_url` の renderer は、context-matched `og:description` がある場合だけ通す。既存 fallback を全面置換していないため、情報不足が source OG に無い記事は従来どおり。
- 別記事 HTML 混入を避けるため context guard を通している。title / summary が極端に汎用的で context term が作れない場合、OG は使わず fallback する。
- deploy は未実施。deploy する場合は `manual-intake-service` 本線を触る便として扱う。

### 6. 新しく見つかったデグレ

- なし。

### 7. 追加した回帰テスト

- `ManualIntakeSourceOgDescriptionDensityTests.test_matching_og_description_supplies_missing_news_facts`
- `ManualIntakeSourceOgDescriptionDensityTests.test_unrelated_og_description_is_not_used_for_news_facts`

### 8. 次回触ってはいけない範囲

- 公開済み WP 記事本文 / status
- 既存の本文文字数ルール / threshold / prompt 文字数指定
- 既存テンプレート全体の再設計
- publish / mail / scheduler / env / Secret / GitHub Actions
- source 追加
- LLM call 追加
- アイキャッチ fallback policy
- 関連選手の同姓別人 guard
- 本文抜粋 context-drift guard
- noindex / canonical / 301
- AdSense / frontend UI
- unrelated dirty files
