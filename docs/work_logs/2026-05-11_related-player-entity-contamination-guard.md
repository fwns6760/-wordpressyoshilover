# 2026-05-11 関連選手・タグ混入防止 作業記録

## 1. 今回の目的

のもとけ型へ寄せる前提として、まず記事の信頼性を固める。

直近 live 確認で post `66380` の関連選手 block に、同姓別人らしき `田中瑛斗` が混入している疑いを確認した。公開済み記事は修正せず、今後の生成で同姓別人・他球団・元巨人混入を防ぐ恒久 guard と回帰テストを入れる。

## 2. 今回触る範囲

GO 後に触る候補は以下に限定する。

- 関連選手抽出 / player stats block / roster matching 周辺
- 関連タグ生成で選手名を扱う箇所
- post `66380` 型の再現テスト
- 必要な work log 追記

この Markdown 作成時点では、許可する変更は本 Markdown の新規作成のみ。

## 3. 今回触らない範囲

- 公開済み WP 記事本文の修正
- WP post status 変更
- publish 条件
- mail 通知
- Cloud Run env
- Scheduler
- Secret Manager
- GitHub Actions
- X API / X 自動投稿
- AdSense / 320-FRONT / scroll UI
- SEO / noindex / canonical / 301
- source 追加
- Gemini / Grok / LLM call 増加
- アイキャッチ fallback policy
- 本文抜粋 guard
- unrelated dirty files

## 4. 影響範囲

GO 後の想定影響範囲は、新規生成される記事の以下。

- 関連選手 block
- player stats block
- 関連タグ
- 選手別回遊導線
- 関連記事 / タグ検索の精度

公開済み記事 `66380` は観測対象であり、直接修正しない。

## 5. 実行予定テスト

GO 後、実装内容に応じて以下を実行する。

- 関連箇所の grep / rg
  - `田中将大`
  - `田中瑛斗`
  - `related player`
  - `player stats`
  - `roster`
  - `tag`
- post `66380` 型の再現テストを追加
- 対象 unit test
- 変更 Python の `py_compile`
- 変更 Python の AST parse
- `python3 -m unittest discover -s tests`
- 必要時のみ full suite を sandbox 外権限で再実行

## 6. STOP条件

以下の場合は停止する。

- 公開済み記事修正が必要になった場合
- 姓だけ一致でしか判定できない場合
- 現所属 / 元巨人 / 他球団の区別を安全にできない場合
- roster source が不明で記憶補完になりそうな場合
- 関連選手を消しすぎて主要選手まで落とす場合
- publish / mail / scheduler / env / Secret に触る必要が出た場合
- LLM call 増加が必要になった場合
- unrelated dirty files を巻き込みそうな場合
- full suite が赤のまま原因説明できない場合

## 7. 禁止事項

- 記憶から選手所属を再構成する
- 姓だけ一致で関連選手を採用する
- 自己評価 OK で終わる
- silent skip で理由を残さない
- 公開済み WP 記事を直す
- `git add -A`
- ついで修正
- env / scheduler / deploy 変更
- source 追加
- X API 使用

## 8. 想定されるデグレ

- 正しい同姓選手まで落とす
- 選手 stats block が出なくなる
- 関連タグが減りすぎる
- 元巨人記事の回遊が弱くなる
- ファーム選手や育成選手が拾えなくなる
- 汎用ニュースで player block が空になる
- 既存 fixture の期待 HTML が変わる

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-11 JST | work log作成 | user 確認「まず1からやろうか？」に対し、優先度1「信頼性」の最初の対象を `66380` 型の関連選手混入防止と定義。コード編集・commit・push・deploy・env変更・scheduler変更は未実施。 |
| 2026-05-11 22:53 JST | 実装開始 | 運用ロック / board / assignments / dirty tree を確認。対象を `src/tools/manual_intake.py` の関連選手 scan / player stats block に限定。 |
| 2026-05-11 22:53 JST | 赤テスト確認 | `python3 -m unittest tests.test_manual_intake.PlayerStatsTableBlockTests` で 3 failures を確認。姓だけの `田中` から `田中将大` / `田中瑛斗` が同時採用されることを再現。 |
| 2026-05-11 22:54 JST | 実装修正 | roster scan の surname-prefix 採用を廃止し、full name / configured alias の正規化一致だけに変更。stats lookup も短い prefix の曖昧一致を拒否。 |
| 2026-05-11 23:01 JST | テスト完了 | targeted / manual_intake / compileall / AST / full unittest を実行。sandbox の socket 制限による full suite 失敗は権限付き再実行で OK。 |

## 10. Regression Memo欄

- のもとけ型へ寄せる前に、まず信頼性を壊す混入を止める。
- post `66380` の観測では、田中将大の記事に関連選手として同姓別人らしき `田中瑛斗` が出た疑いがある。
- 公開済み記事は修正しない。今後の生成 guard と regression test に限定する。
- 選手名は surname だけで採用しない。
- 現巨人 / 元巨人 / 他球団 / 同姓別人を分ける。
- roster / stats source が取れない場合は安全側に倒して block を出さない。
- silent skip せず、テスト名またはログで理由を追える形にする。

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/tools/manual_intake.py`
- `tests/test_manual_intake.py`
- `docs/work_logs/2026-05-11_related-player-entity-contamination-guard.md`

### 2. diff概要

- `src/tools/manual_intake.py`
  - `_scan_giants_player_names_in_text()` から姓2〜3文字の自動候補化を削除。
  - roster 名 / alias は空白差分を吸収した full-name / alias exact match のみに変更。
  - `*田中 瑛斗` のような roster marker は match 用に除去し、同一選手は正規化名で dedupe。
  - `_lookup_player_stats_info()` を追加し、stats prefix fallback は 3 文字以上かつ一意のときだけ許可。
- `tests/test_manual_intake.py`
  - `田中` 姓だけでは関連選手を採用しない回帰テストを追加。
  - `田中将大` 文脈で `田中瑛斗` を混ぜない回帰テストを追加。

### 3. 実行したテスト

- 赤確認:
  - `python3 -m unittest tests.test_manual_intake.PlayerStatsTableBlockTests`
- 修正後:
  - `python3 -m unittest tests.test_manual_intake.PlayerStatsTableBlockTests`
  - `python3 -m unittest tests.test_manual_intake`
  - `python3 -m compileall -q src/tools/manual_intake.py tests/test_manual_intake.py`
  - `python3 -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'), filename=p) for p in ['src/tools/manual_intake.py','tests/test_manual_intake.py']]; print('AST OK')"`
  - `python3 -m unittest tests.test_source_npb_team_stats_extractor tests.test_manual_intake.PlayerStatsTableBlockTests`
  - `python3 -m unittest discover -s tests`

### 4. テスト結果

- 赤確認:
  - `PlayerStatsTableBlockTests`: 7 tests / 3 failures
  - failure 内容: `田中` 姓だけで `田中将大` / `田中 将大` / `田中 瑛斗` が採用され、`田中将大` 文脈の block に `田中 瑛斗` が混入。
- 修正後:
  - `PlayerStatsTableBlockTests`: 7 tests OK
  - `tests.test_manual_intake`: 77 tests OK
  - `compileall`: OK
  - `AST`: OK
  - `tests.test_source_npb_team_stats_extractor + PlayerStatsTableBlockTests`: 16 tests OK
  - full suite sandbox 内: `tests/test_manual_intake_service.py` の HTTPServer bind で 3 errors (`PermissionError: [Errno 1] Operation not permitted`)
  - full suite sandbox 外: 3428 tests OK

### 5. 残った懸念

- 姓だけの記事タイトル / 本文では関連選手 block が出なくなる。これは同姓別人混入を避けるための意図した安全側挙動。
- `config/giants_roster.json` には `田中将大` / `田中 将大`、`*田中 瑛斗` / `田中 瑛斗` の重複が残る。今回は roster data 自体は触らず、scan 側で dedupe した。
- 公開済み post `66380` は修正していない。

### 6. 新しく見つかったデグレ

- なし。

### 7. 追加した回帰テスト

- `PlayerStatsTableBlockTests.test_scan_giants_player_names_does_not_use_surname_only_for_tanaka`
- `PlayerStatsTableBlockTests.test_scan_giants_player_names_keeps_full_tanaka_entity_only`
- `PlayerStatsTableBlockTests.test_build_player_stats_block_does_not_mix_tanaka_same_surname`

### 8. 次回触ってはいけない範囲

- 公開済み WP 記事本文 / status
- publish / mail / scheduler / env / Secret / Cloud Run 設定
- X API / X 自動投稿
- SEO / noindex / canonical / 301
- アイキャッチ fallback policy
- 本文抜粋 guard
- unrelated dirty files
