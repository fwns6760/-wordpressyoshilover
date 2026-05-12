# 2026-05-12 hochi fresh pregame backlog publish policy

> **v2 改訂(2026-05-12 PM)**: v1(11:30 着地)はデバッグで重要なバグが見つかったため scope を拡張・根本治療化して書き換え。v1 の dirty diff(`src/guarded_publish_runner.py` / `tests/test_guarded_publish_runner.py`)は temporary に残し、本 v2 と合わせて 1 commit にまとめる。v1 の作業内容は文末「v1 着地分(rolled into v2)」に保存。

## 1. 今回の目的

- 自動公開 `guarded-publish` で、試合前の新しい報知ソース候補が `backlog_only` 扱いだけで過剰に skip される可能性を潰す。
- 同時に、現状の実装で発生している「試合開始後でも報知ソースが新しければ自動公開してしまう」バグを根本から塞ぐ。
- 重複記事は増やさない。
- 試合前の新しい情報は、報知ソースを優先して自動公開候補に戻せるようにする(一軍・二軍とも)。
- 目標仕様:
  - 報知ソースであること。
  - **対象 subtype を以下に拡張**:
    - `lineup`(スタメン発表、控え選手含む)
    - `pregame`(試合前情報全般)
    - `probable_starter`(予告先発、開幕投手)
    - `farm_lineup`(二軍スタメン)
    - `roster`(公示・昇降格・登録抹消)
    - `comment`(試合前の監督・選手コメント)
    - `injury`(試合前の怪我・離脱情報)
    - `notice`(球団発表・お知らせ系)
  - 試合前かつ source 時刻が新しい場合は公開候補に戻すこと。
  - 同じ話題の既存記事がある場合は量産せず、既存の重複抑制・同話題抑制を維持すること。
  - **試合開始後は完全に止めること**(evaluator 側で hard_stop / red 化し、runner narrow gate に到達しない設計にする)。
  - source が古い場合は従来どおり skip すること。
- 対象に含める報知URL:
  - スポーツ報知 巨人タグ: `https://hochi.news/tag/%E5%B7%A8%E4%BA%BA`
  - スポーツ報知巨人班X: `https://x.com/hochi_giants`
  - スポーツ報知X: `https://x.com/SportsHochi`
  - 報知野球X: `https://x.com/hochi_baseball`

## 2. 今回触る範囲

- `src/guarded_publish_evaluator.py`
  - `expired_lineup_or_pregame` フラグを 2 つに分割:
    - `expired_lineup_or_pregame_game_started`(試合開始後由来)→ **hard_stop / red**(REPAIRABLE_FLAGS から外す、BACKLOG_ONLY_FRESHNESS_FLAGS からも外す)
    - `expired_lineup_or_pregame_age`(source age >= threshold 由来)→ **repairable / yellow / backlog_only**(現状維持)
  - `_evaluate_freshness` 内の lineup 系判定で、`now >= game_start` 経路と age threshold 経路で別フラグを emit する
- `src/guarded_publish_runner.py`
  - `BACKLOG_NARROW_HOCHI_PREGAME_SUBTYPES` を B 案に拡張:
    - `{"lineup", "pregame", "probable_starter", "farm_lineup", "roster", "comment", "injury", "notice"}`
  - 各 subtype の閾値は既存の `FRESHNESS_THRESHOLDS_HOURS` をそのまま利用(`lineup`/`pregame`/`probable_starter`/`farm_lineup` は 6h、`roster`/`injury`/`notice` は 24h、`comment` は 48h)
  - action map(`freshness_audit_only_no_op`)を 2 flag に対応
- `src/published_cleanup_proposals.py`
  - action map を 2 flag に対応
- 関連テスト
  - `tests/test_guarded_publish_evaluator.py`
  - `tests/test_guarded_publish_runner.py`
  - `tests/test_guarded_publish_backlog_narrow.py`
  - `tests/test_guarded_publish_runner_dedupe_idempotent.py`
  - 必要なら dedicated regression test file を追加
- 本作業記録 Markdown

## 3. 今回触らない範囲

- RSS source 追加・削除・URL変更
- `config/rss_sources.json` の変更
- Cloud Run env / Secret / Scheduler / GitHub Actions
- Cloud Run deploy
- publish / mail 全体条件の緩和
- X 投稿
- アイキャッチ処理
- 本文生成品質、本文抜粋、関連記事、ソース本文抽出
- 既存公開記事の修正
- 報知以外の媒体を今回の例外対象へ広げること
- `postgame` / `game_result` / `farm_result` 等、試合後系の subtype
- `farm_feature` / `program` / `manager` / `speech` / `off_field` 等、broadcast/feature 系の subtype
- `expired_game_context` / `stale_for_breaking_board` 等の他 freshness フラグ
- unrelated dirty files / logs / build artifacts

## 4. 影響範囲

- `guarded-publish` の自動公開候補選別
- 特に、以下を望ましい状態に戻す:
  - 試合前の報知発の新しい情報(8 subtype)が backlog 扱いだけで機械的に落ちない
  - 試合開始後の lineup / pregame / probable_starter / farm_lineup 系は evaluator が red 判定し、auto publish 経路に到達しない
  - 古い試合前情報は引き続き backlog 扱いで落ちる
  - 同一話題の重複量産は引き続き止まる
- 影響しない想定:
  - RSS取得件数
  - 下書き生成ルール
  - メール通知 job
  - publish-notice job
  - アイキャッチ選定

## 5. 実行予定テスト

- evaluator side:
  - 新規: 試合開始後の lineup → hard_stop / red、`expired_lineup_or_pregame_game_started` が hard_stop_flags に入る
  - 新規: 試合未開始だが age >= 6h の lineup → repairable / yellow、`expired_lineup_or_pregame_age` が repairable_flags、`backlog_only=True`
  - 既存: 既存 stale lineup test の assertion を `_age` 変種に更新
- runner side:
  - 既存 hochi narrow 7 件(現状の lineup / pregame / probable_starter)→ そのまま pass を確認
  - 新規: 報知 fresh `farm_lineup` → publish 候補に戻る
  - 新規: 報知 fresh `roster` → publish 候補に戻る(age < 24h)
  - 新規: 報知 fresh `comment` → publish 候補に戻る(age < 48h)
  - 新規: 報知 fresh `injury` → publish 候補に戻る(age < 24h)
  - 新規: 報知 fresh `notice` → publish 候補に戻る(age < 24h)
  - 新規: 報知 fresh の上記 subtype でも、age が threshold 到達なら skip
  - 新規: 報知 fresh の上記 subtype でも、`expired_lineup_or_pregame_game_started` を伴う場合(lineup/pregame/probable_starter/farm_lineup のみ該当)は runner publishable に到達しない
  - 既存 non-hochi pregame test → 引き続き blocked
  - 既存 duplicate ガード test → 引き続き有効
- 関連テスト:
  - `python3 -m unittest tests.test_guarded_publish_runner`
  - `python3 -m unittest tests.test_guarded_publish_backlog_narrow`
  - `python3 -m unittest tests.test_guarded_publish_evaluator`
  - `python3 -m unittest tests.test_guarded_publish_runner_dedupe_idempotent`
  - `python3 -m unittest tests.test_lineup_source_priority`
- 全件:
  - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 報知ソースかどうかを安全に判定できない場合
- 試合前/試合開始後の判定が既存データから取れず、推測で実装する必要がある場合
- 重複抑制を緩めないと実現できない場合
- env / Scheduler / Cloud Run 設定変更が必要になった場合
- source 追加が必要になった場合
- publish / mail 全体条件の緩和が必要になった場合
- アイキャッチや本文生成へ修正が広がる場合
- evaluator のフラグ分割で既存 test が想定外に大量に赤化する場合(narrow rewrite では収まらない兆候)
- 全件テストが赤で、今回差分との関係を切り分けられない場合

## 7. 禁止事項

- 記憶から再構成しない
- silent skip しない
- 自己評価 OK で済ませない
- `git add -A` しない
- 報知優先を理由に重複記事を増やさない
- 古い試合前情報を自動公開しない
- 試合開始後の lineup / pregame / probable_starter / farm_lineup を自動公開しない
- 報知以外の媒体へ勝手に緩和しない
- 試合後系・broadcast 系 subtype へ拡大しない
- source 追加、Scheduler変更、env変更、deploy をこの便に混ぜない
- 既存公開記事を直さない

## 8. 想定されるデグレ

- 判定を緩めすぎると、同じ試合前情報が複数本公開される
- 試合開始時刻の判定を誤ると、試合開始後に古いスタメン/予告先発記事が出る → v2 では evaluator 側で hard_stop 化することで根本的に止める
- 報知ソース判定を誤ると、非報知ソースまで通る
- 重複抑制より前で通してしまうと、代表1本化の意図が壊れる
- source 時刻が欠落している候補を通すと、古い候補が混ざる
- フラグ分割により既存 log 解析・dashboard が legacy 名 `expired_lineup_or_pregame` を参照していると壊れる → src/tests 以外で参照箇所がないことを grep で確認済み
- B 案 subtype 拡張により、`roster`/`comment`/`injury`/`notice` の重複検出が `lineup` ほど tight でない領域で重複量産が出る可能性 → tests で同一 source URL ガードが効くことを確認

## 9. 作業ログ欄

### 2026-05-12 AM(v1 着地、commit 未)

- user 指摘: 自動公開が止まっているのではなく skip されている可能性を確認
- `guarded-publish-trigger` は `ENABLED`、`*/30 * * * *`
- 11:00 JST 実行 `guarded-publish-8zzt7` は成功終了
- ただし候補は `status=skipped`、主な `hold_reason` は `stale_source_age` / `backlog_only` / `backlog_only_source_age`
- 現行テスト上、`lineup` / `pregame` / `probable_starter` / `farm_lineup` は backlog 扱いになると source が 1 時間前でも blocked
- user 方針: 重複は嫌だが、試合前の新しい報知情報は拾ってほしい
- v1 として `lineup` / `pregame` / `probable_starter` のみ narrow exception を runner 側に追加(`farm_lineup` 対象外)。tests 3445 件 OK で着地、commit / deploy 未実施

### 2026-05-12 PM(デバッグ + v2 改訂)

- Claude が v1 の dirty diff を独立検証 → tests は全 pass を再現確認
- ロジック追跡で **「試合開始後でも報知 source が新しければ runner 側で eligible=True を返す」** バグを特定:
  - evaluator が game_started 由来と age 由来を同じ `expired_lineup_or_pregame` フラグで処理
  - runner は `hard_stop_flag` / `freshness_reason` を payload に持たないため区別不能
  - 直接実行 probe で再現:`age=0.58h, game_start=14:00, now=14:30` で `eligible=True, narrow_kind=hochi_fresh_pregame` を返した
- user 確認:
  - 根本治療を希望(evaluator 側のフラグ分割で対応)
  - 試合前情報は一軍・二軍ともに対象、`farm_lineup` を含める
  - B 案 wide scope を採用(`lineup`/`pregame`/`probable_starter`/`farm_lineup`/`roster`/`comment`/`injury`/`notice`)

### 2026-05-12 PM 追加(scope 再判定 — 実装は narrower)

- `_backlog_narrow_publish_decision` の routing を再調査し、subtype ごとの probe を実行
- 結果(`age=1.0h`, hochi source 固定):

  | subtype | 現在の挙動 | 実装変更 |
  |---|---|---|
  | `lineup` / `pregame` / `probable_starter` | v1 で eligible 化済 (dirty diff) | 維持 |
  | `farm_lineup` | blocked (BACKLOG_NARROW_BLOCKED_SUBTYPES) | 要追加 |
  | `roster` / `comment` / `injury` / `notice` | **既に eligible** (BACKLOG_NARROW_ALLOWLIST 経由、age < threshold + 12h buffer) | 不要 |

- B 案 wide scope の趣旨(これらの subtype を試合前公開対象に含める)は **既に達成済み**。コード変更が必要なのは `farm_lineup` 追加のみ
- v2 実装の実体は (1) evaluator フラグ分割(バグ修正)+ (2) `farm_lineup` を `BACKLOG_NARROW_HOCHI_PREGAME_SUBTYPES` に追加 の 2 点
- `roster` / `comment` / `injury` / `notice` は既存動作確認のため regression test を追加して将来の破壊を防ぐ
- 本 work_log を v2 narrow scope で確定。これから bug 再現テスト → evaluator 分割 + farm_lineup 追加 → 既存 test 更新 → 全件確認の順で実装

## 10. Regression Memo欄

- これは RSS 取得停止の問題ではない
- これは mail 通知停止の問題でもない
- 問題候補は、`guarded-publish` の backlog narrow 判定が試合前の新鮮な候補まで止めすぎること、および試合開始後でも narrow exception が誤発火すること
- ただし、単純に backlog を緩めると重複記事が増えるため不可
- 正しい方向:
  - 報知ソースを優先
  - source 時刻を見る
  - 試合開始後判定は evaluator 側で hard_stop / red 化する(runner 側で重複ロジックを持たない)
  - 重複抑制は維持
  - 条件を満たす時だけ publish eligible に戻す
- `news/tag_scrape` のアイキャッチ修正とは別タスク

---

## v1 着地分(rolled into v2)

参考のため v1 で行った dirty diff の要約を残す。本 commit ではこの差分を baseline として上書きする。

### v1 で実際に変更したファイル

- `src/guarded_publish_runner.py`
- `tests/test_guarded_publish_runner.py`
- `docs/work_logs/2026-05-12_hochi-fresh-pregame-backlog-publish-policy.md`

### v1 diff 概要

- `guarded_publish_runner` の backlog narrow 判定に、報知ソースの新しい試合前候補だけを通す例外を追加
  - 対象 subtype は `lineup` / `pregame` / `probable_starter`
  - `farm_lineup` は対象外のまま
  - freshness threshold 未満だけ eligible
  - source URL / source name / source domain / lineup priority metadata を report entry から runner に渡す
  - 報知判定は既存 `lineup_source_priority.is_hochi_source()` を利用
- 同一 source URL の重複ガードは後段に残し、報知候補でも同一source既存公開があれば拒否する回帰テストを追加

### v1 テスト結果

- 追加テスト 7 件 OK
- `tests.test_guarded_publish_runner`: 109 件 OK
- `tests.test_lineup_source_priority`: 6 件 OK
- `tests.test_guarded_publish_evaluator`: 103 件 OK
- 全件: 3445 件 OK(sandbox 外)

### v1 残った懸念(v2 で解消する)

- `guarded-publish` 本番入力に source metadata が欠けている候補は、narrow 例外には乗らない → v2 でも同じ(根本問題ではない)
- **試合開始後判定が既存 evaluator の `expired_lineup_or_pregame` hard stop に依存していたが、runner 側では区別不可能だった** → v2 で evaluator 側のフラグ分割により根治
- deploy 未実施 → v2 でも user 判断境界、本 commit では deploy しない

### v1 で「次回触ってはいけない」とした範囲(v2 でも維持)

- この便の流れで RSS source 追加・削除・URL変更をしない
- この便の流れで `config/rss_sources.json` を触らない
- この便の流れで env / Secret / Scheduler / GitHub Actions を触らない
- この便の流れで重複抑制を緩めない
- この便の流れでアイキャッチ・本文生成・mail・X投稿を混ぜない

v2 では `farm_lineup` まで広げる(v1 の禁止解除)、および `roster` / `comment` / `injury` / `notice` まで広げる(B 案採用)。
