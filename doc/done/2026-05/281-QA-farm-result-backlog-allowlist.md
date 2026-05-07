# 281-QA-farm-result-backlog-allowlist

| field | value |
|---|---|
| ticket_id | 281-QA-farm-result-backlog-allowlist |
| priority | P1 (昼帯コンテンツ充実) |
| status | REVIEW_NEEDED |
| owner | Claude (review/push) |
| lane | QA |
| ready_for | Claude review + push 判断 |
| blocked_by | (なし、独立) |
| doc_path | doc/active/281-QA-farm-result-backlog-allowlist.md |
| created | 2026-04-30 |

## 1. 目的

二軍試合結果(`farm_result`)を **昼帯 publish 対象** に追加する。ただし古い二軍結果の放出は避けるため、`farm_result` は age 制限を **24h 厳しめ固定** にする(他 ALLOWLIST subtype が threshold + 12h buffer なのに対し、独自の hard cap)。

## 2. 背景

### 現状(本日 audit、`src/guarded_publish_runner.py` 31-65 行)

| set | 二軍関連 | 結果 |
|---|---|---|
| `BACKLOG_NARROW_GAME_CONTEXT_SUBTYPES` | (twoarm 該当なし) | `farm_result` が **未登録** |
| `BACKLOG_NARROW_QUOTE_COMMENT_SUBTYPES` | `farm_feature` | OK |
| `BACKLOG_NARROW_BLOCKED_SUBTYPES` | `farm_lineup` | 試合直前情報、backlog で出さない設計 |
| 暗黙 hold | **`farm_result`** | ALLOWLIST 漏れで全部 backlog_only hold |

### 影響

- 本日 ledger 17228 records / sent 5 件、`farm_result` の sent 0
- 二軍試合結果は「fresh path」のみで publish 可能、backlog 経由は全 hold
- 昼帯(9-16時)に 1 軍 fresh が無いタイミングで二軍試合結果コンテンツが出ない
- `hard_stop_farm_result_placeholder_body` 15 件 = 「中身空 stub」を弾く安全機構は維持(これは正しい)

### 編集方針(user 確定)

- `farm_result` fresh = publish 対象(現状維持)
- `farm_result` backlog **24h 以内** = eligible(緩和)
- `farm_result` backlog **24h 超** = hold/backlog_only(維持)
- `farm_lineup` backlog = BLOCKED 維持(変更なし)
- placeholder body = hard_stop 維持(変更なし)
- `live_update` ON 禁止(変更なし、ENABLE_LIVE_UPDATE_ARTICLES=0 維持)

## 3. Codex に渡す作業範囲(write scope)

### 実装内容

**`src/guarded_publish_runner.py`**:

A. 新定数追加(31-58 行付近):
```python
BACKLOG_NARROW_FARM_RESULT_SUBTYPES = frozenset({"farm_result"})
BACKLOG_NARROW_FARM_RESULT_AGE_LIMIT_HOURS = 24
```

B. `_backlog_narrow_publish_context` (1267 行) に分岐追加:
- subtype が `BACKLOG_NARROW_FARM_RESULT_SUBTYPES` の場合
- age_hours < 24 なら eligible context return(reason="farm_result_age_within_24h" など)
- age_hours >= 24 なら return None(hold)
- ALLOWLIST / BLOCKED の他分岐より前に判定(disjoint scope のため順序問わず動くが、明示的に narrow 分岐)

C. 既存 ALLOWLIST / BLOCKED 定義は **変更しない**(farm_lineup BLOCKED 維持、他 game_context / quote_comment 維持)

### 触ってよい file (write scope)

- `src/guarded_publish_runner.py` (上記 A + B の narrow fix のみ)
- `tests/test_guarded_publish_backlog_narrow.py` (新規 file、デグレ試験 fixture)
- `doc/active/281-QA-farm-result-backlog-allowlist.md` (status 更新、本 file)

### 不可触 file(絶対触らない)

- `.github/workflows/**`
- `src/publish_notice*` / `src/yoshilover_fetcher*` / `src/draft_body_editor*`
- `src/sns_topic_publish_bridge.py` (pre-existing dirty)
- `src/title_player_name_backfiller.py` (277-QA scope)
- automation / scheduler / env / secret / `.codex/automations/**`
- `BACKLOG_NARROW_GAME_CONTEXT_SUBTYPES` 既存 set(touchの代わりに新 SET 追加)
- `BACKLOG_NARROW_QUOTE_COMMENT_SUBTYPES` 既存 set
- `BACKLOG_NARROW_BLOCKED_SUBTYPES` 既存 set(farm_lineup BLOCKED 維持)
- `BACKLOG_NARROW_AGE_BUFFER_HOURS = 12` 定数(他 ALLOWLIST 用)
- prosports 関連 / SEO / X 自動投稿 path
- WP REST 直接呼び出し path
- doc/done/**
- doc/active/270-* / 271-* / 273-* / 263-* / 267-* / 277-*

## 4. 実装前 Codex 必須確認

- [ ] `_backlog_narrow_publish_context` の現行分岐順を読み、新分岐位置を決定
- [ ] `is_backlog=True` の path だけ通ること(fresh path に副作用なし)
- [ ] `entry["subtype"]` の正規化(lower/strip)が既存と同じ
- [ ] `age_hours` 算出 logic が既存と同じ(`now - entry["created_at"]` 等)
- [ ] hard_stop_farm_result_placeholder_body は前段で trip するため本変更で素通りしないことを確認

## 5. 必須デグレ試験(`tests/test_guarded_publish_backlog_narrow.py`)

### 5-A. farm_result 公開導線
- [ ] fixture: `farm_result` fresh(`is_backlog=False`) → publish path 維持(本便で挙動変化なし)
- [ ] fixture: `farm_result` backlog age=12h → **eligible**(新挙動)
- [ ] fixture: `farm_result` backlog age=23.5h → **eligible**(境界内)
- [ ] fixture: `farm_result` backlog age=24h → **hold**(境界外、`hold_reason=backlog_only` emit)
- [ ] fixture: `farm_result` backlog age=72h → hold

### 5-B. farm_lineup BLOCKED 維持
- [ ] fixture: `farm_lineup` backlog age=2h → **hold**(BLOCKED 維持、新便で eligible 化禁止)
- [ ] fixture: `farm_lineup` fresh → publish path 維持

### 5-C. 他 ALLOWLIST 不変
- [ ] fixture: `postgame` backlog → 既存挙動維持(farm_result 追加で副作用なし)
- [ ] fixture: `comment` backlog → 既存挙動維持
- [ ] fixture: `default` backlog age=20h → eligible(unresolved 24h 維持)

### 5-D. 安全系
- [ ] fixture: 一軍/二軍混線(タイトル「巨人 4-2」+本文「二軍」)→ publish しない or review 経路維持
- [ ] fixture: `hard_stop_farm_result_placeholder_body` 該当 → 本便でも refused 維持
- [ ] fixture: 同 source_url duplicate → refused 維持(263-QA 不変)
- [ ] fixture: スコア矛盾 → hard_stop_win_loss_score_conflict 維持

### 5-E. mail 通知(integration)
- [ ] farm_result publish → publish-notice mail 経路に流れる(post_id record)
- [ ] farm_result hold(age 超) → hold mail 経路に流れる(`hold_reason=backlog_only` emit、267-QA 不変)
- [ ] farm_result review → review mail 経路に流れる
- [ ] Team Shiny From を本便で touch しない(env 不変 assert)

### 5-F. live_update 禁止
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 を本便で touch しない(diff に live_update token 無し assert)
- [ ] live_update path から farm_result publish に流入しない

### 5-G. コスト
- [ ] Gemini call 数 増加なし(本変更は分岐 1 個追加、LLM 呼び出し 0)
- [ ] 同 source_url/content_hash 再生成なし(229-COST cache_hit ratio 維持)
- [ ] publish-notice / guarded-publish 無限再処理なし

### 5-H. 禁止事項 diff assert
- [ ] SEO/noindex/canonical/301 の token diff になし
- [ ] prosports 関連 file 触らず
- [ ] X 自動投稿 path 触らず
- [ ] 新 subtype を勝手に作らない(`farm_result` は既存)
- [ ] duplicate guard 全解除しない
- [ ] default/other 24h 制限維持

### 5-I. 必須コマンド
```
cd /home/fwns6/code/wordpressyoshilover
python3 -m unittest tests.test_guarded_publish_backlog_narrow -v 2>&1 | tail -20
python3 -m unittest discover tests 2>&1 | tail -10
# baseline (master HEAD before): 1820 + 6 = 1826 tests, failures=0 errors=0
# 期待 (281-QA 後): 1826 + N 新規 tests, failures=0 errors=0 (local env 差で 7 pre-existing fails あれば baseline と差分なし)
```

## 6. deploy 要否

- commit + push のみ(本便で deploy なし)
- 本番反映は **guarded-publish job image rebuild + update** が必要
- deploy 便は別 fire(本 ticket 完了 + GH Actions green 後、user GO で起動)
- guarded-publish のみ deploy(他 job/service 触らない)

## 7. rollback 条件

- 本 ticket commit を revert すれば即時 rollback
- 本番 image rebuild 後の問題発生時は前 image (`guarded-publish:a175f24`) に job revision 戻す
- rollback コマンド:
```
gcloud run jobs update guarded-publish --region=asia-northeast1 --project=baseballsite \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:a175f24
```
- env flag 新規追加しない(rollback 簡素化)

## 8. 優先順位

- 全体: P0 観察 / CI 緑 維持より下
- 277-QA observation 並走可(scope disjoint = guarded-publish src vs fetcher src)
- 279-QA より優先(昼帯コンテンツ復活が編集方針上重要)

## 9. 今 vs 後

- 今: ticket 起票 + Codex narrow 実装 + tests + commit + push + GH Actions verify
- 後: guarded-publish image rebuild + job update(別便、user 明示 GO 後)
- HOLD 条件:
  - live_update / ENABLE_LIVE_UPDATE_ARTICLES 触る
  - SEO / noindex / canonical / 301 触る
  - X 自動投稿
  - duplicate guard 全解除
  - default/other 無制限公開
  - 新 subtype 追加(farm_result は既存)
  - Scheduler 頻度変更
  - Team Shiny From 変更

## 完了条件(7 点 contract、`feedback_completion_contract_7_point.md` 準拠)

1. commit hash(本 ticket impl)
2. pushed to origin/master
3. GH Actions Tests workflow = success
4. (deploy 便で)guarded-publish job image = `:<new>`
5. (deploy 便で)live log: backlog 古い farm_result hold + 新鮮 farm_result eligible/sent 確認
6. (deploy 後)昼帯 sample で farm_result 二軍試合結果 publish 実績
7. (deploy 後問題時)rollback path 確認可能
