# 289-OBSERVE-post-gen-validate-mail-notification

| field | value |
|---|---|
| ticket_id | 289-OBSERVE-post-gen-validate-mail-notification |
| priority | **P0 equivalent**(silent skip = user 受け入れ NG) |
| status | REVIEW_NEEDED |
| owner | Claude(audit/draft) → Codex(別 lane、impl) |
| lane | OBSERVE |
| ready_for | Claude review / push 判断 |
| blocked_by | (なし、独立) |
| doc_path | doc/active/289-OBSERVE-post-gen-validate-mail-notification.md |
| created | 2026-04-30 |

## 1. 結論

`article_skipped_post_gen_validate` event(現在 logger 出力のみ)を **mail 通知対象に格上げ**する。
本日 audit:15:00 trigger で prepared 27 件 / post_gen_validate skip 22 件 / created 0 件。**22 件全部 user に通知されない silent skip** = user 体感「publish/mail 0」の真の原因。

## 2. 背景

### 現状の post_gen_validate skip flow(`src/rss_fetcher.py`)
- 7633: `_evaluate_post_gen_validate`(weak_subject_title / weak_generated_title / postgame_strict / close_marker / 等の検証)
- 7735-7755: `_log_article_skipped_post_gen_validate`(logger emit のみ、jsonl 等の永続 ledger 無し)
- 13753 / 13775 / 13820: 3 箇所で skip 確定 + skip_reason_counts インクリメント

### 通知 path(現状)
- `guarded-publish job` が draft を評価 → `guarded_publish_history.jsonl` に record
- `publish-notice job */5 trigger` が `guarded_publish_history.jsonl` scan → publish/review/hold mail emit
- **post_gen_validate skip は guarded-publish に到達せず**、`guarded_publish_history.jsonl` に書かれない
- → publish-notice が拾えない、mail 出ない、user silent

### 真因
- log には event 出ているが log 監視は user 体感対象外
- mail 経路に乗らない skip = user 視点 silent

## 3. Codex に渡す作業範囲

### 設計案(narrow integration)

**A. fetcher 側で skip ledger を emit**
- `src/rss_fetcher.py` の `_log_article_skipped_post_gen_validate` を拡張、または並走で:
  - 新 jsonl 出力: `post_gen_validate_history.jsonl`(GCS backup あり)
  - record 形式:
    ```json
    {
      "ts": "2026-04-30T15:00:00+09:00",
      "source_url": "https://...",
      "source_url_hash": "<hash>",
      "source_title": "<元 title>",
      "generated_title": "<rss_fetcher rewritten title>",
      "category": "<category>",
      "article_subtype": "<subtype>",
      "skip_reason": "weak_subject_title:related_info_escape",
      "fail_axis": ["weak_subject_title:related_info_escape"]
    }
    ```
- post_id は **未 publish なので無し**(user 要求通り source_url / source_title / generated_title / skip_reason で十分)

**B. publish-notice 側で新 ledger も scan**
- `src/publish_notice*.py` の scan logic に **post_gen_validate_history.jsonl** を追加
- 既存 guarded_publish_history scan は不変
- mail emit 処理は共通化、record_type=`post_gen_validate` で分岐

**C. mail subject prefix**
- 既存 prefix(`【公開済｜...】` / `【要review｜...】` / `【hold｜...】`)に **`【要review｜post_gen_validate】<source_title>`** を追加
- 本文に skip_reason mapping(279-QA 設計と整合):
  - `weak_subject_title:related_info_escape` → 「タイトルが『関連情報』『発言ポイント』だけ、人名/文脈が拾えなかったため」
  - `weak_generated_title:no_strong_marker` → 「タイトルが弱い表現で fail」
  - `weak_generated_title:blacklist_phrase` → 「タイトルに blacklist phrase 含む」
  - `postgame_strict:strict_validation_fail:required_facts_missing:...` → 「postgame strict template に必要な fact 不足」
  - `close_marker` → 「close marker 検出、後追い記事疑い」
  - その他 → 既存 reason そのまま

**D. 通知爆発防止**
- 1 run 上限: 既存 `max_per_run cap`(267-QA)を **共通 cap として post_gen_validate も対象**
- 重複抑制: `source_url_hash + skip_reason` 単位で **24h 以内に 1 度だけ**(同 fetcher 5min trigger で同 source 再生成しても 1 通)

**E. Team Shiny From / 通知導線維持**
- env / SMTP 設定 不変
- 既存 publish/review/hold mail は従来通り届く
- subject 固有 token 「| YOSHILOVER」維持

### 触ってよい file (write scope)

- `src/rss_fetcher.py`(post_gen_validate skip 直前で ledger 行追加 narrow integration、3 call site だが共通 helper 化推奨)
- `src/publish_notice*.py`(new ledger scan + record_type 分岐、subject prefix 追加)
- `tests/test_post_gen_validate_notification.py`(新規、デグレ試験 fixture)
- `doc/active/289-OBSERVE-*.md`(本 file、status 更新)

### 不可触 file

- `.github/workflows/**`
- `src/guarded_publish_runner.py`(281-QA scope 不変、guarded-publish 経路 touch しない)
- `src/sns_topic_publish_bridge.py`(pre-existing dirty)
- `src/title_player_name_backfiller.py`(277-QA scope)
- `src/gemini_preflight_gate.py`(282-COST scope)
- `src/gemini_cache.py` / `src/llm_call_dedupe.py`(229-COST 不変)
- automation / scheduler / env / secret / `.codex/automations/**`
- prosports / SEO / X 自動投稿 / Team Shiny From / WP REST 直接呼出
- 既存 `_evaluate_post_gen_validate` 判定 logic(本便で skip 条件は緩めない、290-QA で別便)

## 4. 実装前確認(Codex 必須)

- [ ] `_log_article_skipped_post_gen_validate` 関数 signature と 3 call site の context
- [ ] `guarded_publish_history.jsonl` の format / GCS upload pattern(参考用)
- [ ] publish-notice の scan logic と max_per_run cap、267-QA dedup logic
- [ ] 新 ledger file path 規約(/tmp/pub004d/ 等の既存 pattern)
- [ ] Team Shiny SMTP 設定の env 変数(touch 禁止、確認のみ)

## 5. 必須デグレ試験(`tests/test_post_gen_validate_notification.py`)

### 5-A. silent skip 解消(本 ticket 主目的)
- [ ] fixture: post_gen_validate skip 発生 → 新 ledger に record、publish-notice scan で拾われ mail emit
- [ ] fixture: 22 件 skip(本日 audit 再現)→ mail 21〜22 件 emit(max_per_run 内)
- [ ] fixture: silent skip 0(全 skip event が ledger に流れる assert)

### 5-B. mail 内容
- [ ] subject prefix `【要review｜post_gen_validate】<source_title>` 形式
- [ ] subject 固有 token 「| YOSHILOVER」維持
- [ ] 本文 skip_reason mapping 6 種(related_info_escape / no_strong_marker / blacklist_phrase / strict_validation_fail / close_marker / その他)それぞれ fixture
- [ ] post_id 無しで source_url / source_title / generated_title 表示

### 5-C. 通知爆発抑制
- [ ] 同 source_url_hash + 同 skip_reason 24h 以内 重複 mail 0(2 度目以降 dedup skip)
- [ ] 同 source_url_hash + 別 skip_reason → 別 mail で OK
- [ ] 1 run cap(既存 max_per_run と共通)を超えたら次 trigger に持ち越し

### 5-D. 既存通知導線維持(回帰禁止)
- [ ] publish 通知従来通り届く(267-QA 不変)
- [ ] review/hold 通知従来通り届く
- [ ] guarded_publish_history scan 不変
- [ ] cursor 前進 logic 不変

### 5-E. 環境不変
- [ ] Team Shiny From `env` 値不変(SMTP 設定 touch 0)
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/noindex/canonical/301 不変
- [ ] X 自動投稿 path 触らない

### 5-F. コスト
- [ ] Gemini call 0(本変更で LLM 呼出追加なし、ledger は metadata のみ)
- [ ] 同 source_url 再生成 0(229-COST 不変)

### 5-G. log・観察
- [ ] mail attempt / success / error が log に出る
- [ ] dedup_hit / cap_exceeded などの skip_reason も log に出る
- [ ] 24h で post_gen_validate mail 数集計可能(jsonPayload に skip_layer="post_gen_validate")

### 5-H. baseline pytest
```
cd /home/fwns6/code/wordpressyoshilover
python3 -m unittest tests.test_post_gen_validate_notification -v 2>&1 | tail -20
python3 -m unittest discover tests 2>&1 | tail -10
# baseline: 1845 tests / 7 pre-existing fails (282-COST push 後)
# 期待: 1845 + N 新規 / failures=7 不変 / errors=0
```

## 6. deploy 要否

- commit + push のみ(本便)
- 本番反映は **fetcher (yoshilover-fetcher) image rebuild + publish-notice job image rebuild** の **両方** 必要
- deploy 順序:
  1. fetcher rebuild(post_gen_validate ledger 出力源)
  2. publish-notice rebuild(新 ledger scan)
- どちらも別 fire、user 明示 GO 後
- env flag で OFF/ON 切替可能にすると rollback 簡素化(`ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` 推奨、default OFF)

## 7. rollback 条件

- commit revert で即時 rollback
- env flag(導入時)で実質無効化、image 戻し不要
- image rebuild 後問題発生時は前 image (fetcher `:27166c5` / publish-notice `:dc02d61`) に戻す

## 8. 完了条件(7 点 contract)

1. commit hash(289 impl)
2. pushed to origin/master
3. GH Actions Tests workflow = success
4. (deploy 便で)fetcher + publish-notice image 両方反映
5. (deploy 後)live log で post_gen_validate skip → mail emit 確認(本日 audit の 22 件 type が deploy 後 trigger で mail 化)
6. (deploy 後)既存 publish/review/hold mail デグレなし
7. (deploy 後問題時)rollback path 確認可能

## 9. 後続 ticket 連携

- **290-QA-weak-title-rescue-backfill**: post_gen_validate skip の中で `weak_subject_title:related_info_escape` を 277-QA 同等の backfill で救う(本 ticket は通知のみ、290 は救済)
- **288-INGEST-source-coverage-expansion**: NNN / スポニチ web / サンスポ web の追加(本 ticket scope 外)
- **291-QA-postgame-strict-soft-fallback**: postgame_strict required_facts_missing の hard skip → review fallback(本 ticket scope 外)

本 ticket は **silent skip の可視化のみ**、各 skip の救済は別 ticket。

## 不変方針(継承)

- live_update / ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- SEO/noindex/canonical/301 不変
- X 自動投稿 OFF 維持
- duplicate guard 全解除しない
- 新 subtype 追加なし
- Scheduler 頻度変更なし
- Team Shiny From 不変
- Gemini call 増加なし
- 既存 publish/mail 導線壊さない
