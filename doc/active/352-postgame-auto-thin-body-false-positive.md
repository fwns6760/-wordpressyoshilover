# 352-postgame-auto-thin-body-false-positive

## 1. ticket header

- **status**: READY(user 確認待ち、原因仮説まで完了)
- **priority**: medium(自動 publish 4 日停止だが緊急度低、user 手動投稿で代替可)
- **owner**: Claude(実装) / user(GO 判断)
- **依存 (audit)**: `docs/handoff/session_logs/`(2026-05-15 348 step 3 verify 時に発見)
- **発見経路**: 2026-05-15 348 step 3 part 2 deploy verify 中、Cloud Run jobs executions list で `postgame-auto` の連続失敗 4 件を検知

## 2. 目的 / 背景

`postgame-auto` Cloud Run Job(Yahoo NPB schedule から auto-discover → 試合結果記事 publish)が **2026-05-12 22:30 JST から 4 日連続 NonZeroExitCode(exit 20 = EXIT_WP_FAILED)** で失敗中。

直近 success: `postgame-auto-6ngrb` @ 2026-05-11 23:56 JST
直近失敗: `postgame-auto-4qn98` @ 2026-05-15 22:30 JST(発見時の最新)
共通: exit code 20、log に `[WP] title polished: ...` の後 `Container called exit(20)` のみ、stack trace なし

5/11 → 5/12 の transition で何かが変わり、postgame 自動 publish 経路が破綻した。

### 影響範囲(production)

- **postgame_v1 試合結果記事の自動投稿が 5/12 から停止**
- user 手動投稿で代替可能だが、見落とすと公開漏れ
- 348 ticket(本日 deploy 完了)とは **完全に scope 外**、 別 lane の pre-existing 問題

## 2.5 原因仮説(1次 source 調査済)

### コード経路の特定(verified)

1. job 起動: `python -m src.tools.run_postgame_from_yahoo --auto-discover --mode publish`
2. Yahoo schedule → URL fetch → parse → render → `wp.create_post()`
3. `wp_client.py:715` で title polish ログ出力(これは log に記録あり ✅)
4. 次の処理で `thin_body_validator.is_thin_body()` を実行(`wp_client.py:748-768`)
5. **thin と判定 → `RuntimeError` を raise**
6. caller `run_postgame_from_yahoo.py:307-310` で `except Exception` catch → `return EXIT_WP_FAILED`(= exit 20)

### 真因仮説(高確度)

**`thin_body_validator._is_postgame_scorecard_only` が postgame card を false positive で reject している**

証拠:
- commit `11215f1` (2026-05-10) で `308: stop scoreboard-only postgame thin bodies` を導入
- `src/thin_body_validator.py:168-185` で postgame card の「score 表だけで打席/投手 detail なし」を thin 判定
- detection 条件 6 項目 AND 合致で thin:
  1. nomotoke card footer 存在
  2. CTA row 存在
  3. postgame score heading 存在
  4. **detail heading(打席結果 / 投手成績 / 相手打線 等)が無い** ← ここが疑い
  5. generic 終了句(「勝利！」等)
  6. text_chars < `_POSTGAME_SCORECARD_ONLY_MAX_TEXT_CHARS`
- 失敗 article の title は「【試合結果、**打席結果**】」を含むので detail heading が **存在するはず** だが、validator の regex が match していない可能性

### なぜ 5/12 から(複合)

- thin_body_validator は 5/10 から active
- 5/11 23:56 JST 最後の success(この時点では detail heading regex が match していた)
- 5/12 22:30 JST から連続失敗 = 5/12 deploy で postgame card の HTML 構造が変わり regex が外れた
- 該当する変更候補(git log で 5/12 周辺、後追い 1次 source 確認必要):
  - `2d5c334 fix(eyecatch): player photo priority + recent media dedupe`(5/12 12:42 JST)
  - Phase 2F-2I の table rendering changes(NPB box + Yahoo box の structure 変更)
  - 5/12 evening P0 incident `422220a docs(incident): publish 30 min 停止` 関連

### log で skip_reason JSON が見えない理由

`run_postgame_from_yahoo.py:308-310` で `print(json.dumps({"skip_reason": "wp_create_failed:RuntimeError", ...}))` を実行するはずだが Cloud Logging に出ていない。

候補:
- stdout flush タイミング(PYTHONUNBUFFERED=1 は Dockerfile 確認済、これは要因ではない)
- Cloud Logging が INFO severity を一部 drop
- 実行は最初の try block 内で別 path に escape している可能性

## 3. 今回触らない範囲

- **348 ticket scope の全 module**(insight_*.py / config/insight_whitelist.json / 関連 test)
- **insight-nightly Cloud Run Job**(348 deploy 済、本 ticket と無関係)
- **env / Secret / Scheduler**
- **WP REST 経由の content 削除 / 書き換え**(§11 user GATE)
- **既存 published 記事**(wOBA 5 件等の過去 post)
- **新規 detector / publisher の追加**

## 4. 影響範囲

### code 変更が入る file(推定)

| file | 変更内容 |
|---|---|
| `src/thin_body_validator.py` | `_is_postgame_scorecard_only` の detail-heading regex を実 HTML に合わせて修正、 もしくは「postgame_v1 card で本文 N chars 以上」を別軸で許可する例外路追加 |
| **新規** `tests/test_thin_body_validator_postgame_v1.py`(or 既存 file 拡張) | 実 production HTML(失敗 article)を fixture 化 → regress test |

### 直接触らない file

- `src/wp_client.py`(validator caller、 logic 不変)
- `src/tools/run_postgame_from_yahoo.py`(invocation 不変)
- `src/source_yahoo_boxscore_extractor.py`(parser 不変、 失敗は publish layer)
- `Dockerfile.manual_intake_service` / `cloudbuild_manual_intake_service.yaml`(後段 rebuild は code fix 後)
- 親 repo / 他 repo

## 5. 実行予定テスト

### 既存テスト(regression 防止)

```
pytest tests/test_thin_body_validator.py -v
pytest tests/test_wp_client.py -v
```

### 新規追加テスト

| file | 内容 |
|---|---|
| `tests/test_thin_body_validator_postgame_v1.py`(新規 or 既存拡張) | 5/15 失敗 article の実 HTML を fixture 化、 修正後 validator が is_thin=False を返すこと |
| 既存 narrow test(stop scoreboard-only thin) は維持 | regression 防止 |

### 実行コマンド

```
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_thin_body_validator.py tests/test_wp_client.py -v
```

### 実環境 verify(deploy 後)

- `gcloud run jobs execute postgame-auto --wait` を 1 回手動実行、 exit 0 + WP post 作成成功
- 翌日 22:30 JST の scheduler 自然 fire で連続 success 確認

## 6. STOP 条件

実装中に以下のいずれかを検出したら即停止 + user 報告:

1. 既存テスト regression(thin_body_validator narrow detection が崩れる)
2. fix が 5/11 以前の scorecard-only article まで通してしまう(thin body 流出回帰)
3. 別 publisher 経路(rss_fetcher / guarded_publish)への副作用検出
4. WP REST 側の問題と判明(validator 起因ではない場合は本 ticket 範囲外、 別 ticket へ escalate)
5. 失敗 article の rendered HTML 取得が不能(production DB / fixture アクセス path 確保失敗)
6. AI 事故源 trigger(記憶再構成 / silent skip / 自己評価 OK)

## 7. 禁止事項

- 348 ticket scope の file への変更
- `_is_postgame_scorecard_only` 自体を削除する(thin body 流出回帰 risk、 必要なら regex 修正で対応)
- env / Secret / Scheduler 変更
- WP REST 経由 既存 content 削除 / 書き換え / 新規 publish
- X / SNS 発信
- 親 repo `baseballwordpress` への変更
- DB schema 改修
- `git add -A`
- `--no-verify` 等 hook skip

## 8. 想定されるデグレ

### 高確率
- **regex 修正が広すぎて scorecard-only article(本来 stop すべき thin body)も通す**: 308 ticket の意図に反する、 5/11 以前の真の thin body が再流出
- **修正後も別 path で thin 判定**: thin_body_validator 内に複数の detection rule があり、 修正したものとは別 rule で reject される

### 中確率
- production HTML の取得不能 / fixture 化困難(WP REST で削除済 / 認証問題)
- 修正後の deploy 経路(`gcloud builds submit --config=cloudbuild_manual_intake_service.yaml`)で別 service の副作用

### 低確率
- thin_body_validator 自体が呼ばれていなかった(別 layer で reject)、 真因は別

## 9. 作業ログ欄

(実装中追記、 user GO 後に作業開始)

```
YYYY-MM-DD HH:MM JST | <event> | <step> | <task> | <next>
```

## 10. Regression Memo 欄

(実装中追記、 検知した regression / 回避策)

```
YYYY-MM-DD HH:MM JST | <test> | <regression> | <fix> | <test added>
```

---

# 作業後追記 (user GO 後、 完了時に埋める)

## 1. 実際に変更したファイル
(未記入)

## 2. diff 概要
(未記入)

## 3. 実行したテスト
(未記入)

## 4. テスト結果
(未記入)

## 5. 残った懸念
(未記入)

## 6. 新しく見つかったデグレ
(未記入)

## 7. 追加した回帰テスト
(未記入)

## 8. 次回触ってはいけない範囲
(未記入)
