# 182 post-cleanup prose_length verify 緩和(100 → 50)

## meta

- number: 182
- owner: Claude Code(設計 / 起票)/ Codex B(実装)
- type: dev / quality / config relax
- status: **READY → 即 fire**
- priority: P0.5(yellow draft 6 件 cleanup_failed_post_condition で hold、即 publish 復活)
- lane: B
- created: 2026-04-26

## 背景

22:20 JST 時点 `cron_eval.json` 観測:
- yellow 6 件 publishable=True / cleanup_required=True
- guarded-publish が cleanup 実行 → 全 6 件 `cleanup_failed_post_condition` で hold(160 smoke 同様、100% fail)
- 結果: 4.5 時間 publish 0 件継続、publish-notice mail 送信なし

## 原因

`src/guarded_publish_runner.py:225-232` の `_post_cleanup_check`:

```python
prose_chars = _prose_char_count(str(cleaned_record.get("body_text") or ""))
if prose_chars < 100:
    return False, "prose_lt_100"
```

cleanup で `site_component_mixed_into_body` 関連記事 sidebar 除去 → 本文短くなる → 100 文字未満で reject。

threshold 100 が厳しい(速報掲示板の短文記事 = 50 文字程度の lineup notice / brief update も含めたい)。

## ゴール

`_post_cleanup_check` の prose_length threshold を **100 → 50** に緩和。
他の verify(body_empty / title_subject_missing / source_anchor_missing / source_hosts)は **不変**(safety 維持)。

## 仕様

### 修正対象

`src/guarded_publish_runner.py` line 230-232:

```python
# before
if prose_chars < 100:
    return False, "prose_lt_100"
```

```python
# after
if prose_chars < 50:
    return False, "prose_lt_50"
```

(`prose_lt_100` → `prose_lt_50` に reason 名も変更、log / ledger で旧 threshold と区別可能化)

### env で override 可能化(任意、推奨)

```python
MIN_PROSE_AFTER_CLEANUP = int(os.environ.get("MIN_PROSE_AFTER_CLEANUP", "50"))
```

→ 将来 30 / 100 等に変更時、code 修正不要(env 上書きで rollback 可)。

### tests 修正

`tests/test_guarded_publish_runner.py`:
- `prose_chars < 100` を期待してた既存 test → `prose_chars < 50` に reverse
- 新 test: prose_chars=80 → publish 通る verify(従来 reject、新 OK)
- 新 test: prose_chars=40 → reject verify(新 threshold で reject)
- env override test: `MIN_PROSE_AFTER_CLEANUP=30` で prose=40 通る verify

## 不可触

- 他の post_cleanup_check verify(body_empty / title_subject_missing / source_anchor_missing / source_hosts)logic 不変
- 168 ledger schema 不変
- 165 retry/backoff 不変
- 170 fallback controller 不変
- 171/172/177/178 codex shadow / 本線昇格 logic 不変
- 181 readability fix(rss_fetcher full title)logic 不変
- WSL crontab(全行)
- Cloud Run Job env 直接編集(本 ticket は code のみ、env 設定は別 commit)
- automation.toml / .env / secrets / Cloud Run / Scheduler / Storage
- baseballwordpress repo
- WordPress / X
- requirements*.txt
- 並走 task: なし(現状 in-flight Codex 0)

## acceptance

1. `src/guarded_publish_runner.py` の threshold 100 → 50 + env override 対応
2. `tests/test_guarded_publish_runner.py` で:
   - prose_chars=49 → reject(新 threshold)
   - prose_chars=50 → publish 通る verify
   - prose_chars=80 → publish 通る verify(従来 reject、新 OK)
   - env `MIN_PROSE_AFTER_CLEANUP=30` で prose=40 通る verify
3. pytest baseline 1416(181 land 後)+ 新 tests
4. 既存挙動破壊なし(他 verify path 不変)
5. live publish / Cloud Run deploy / push: 全て NO

## Hard constraints

- 並走 task: なし
- `git add -A` 禁止、stage は **`src/guarded_publish_runner.py` + `tests/test_guarded_publish_runner.py`** だけ
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 1416 維持、pre-existing fail 0 維持
- 新 dependency 禁止
- 他の verify check 触らない(本 ticket は prose_length のみ緩和)
- 165 / 168-181 で land 済の挙動を一切壊さない

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_guarded_publish_runner.py -v 2>&1 | tail -20
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

## Commit

```bash
git add src/guarded_publish_runner.py tests/test_guarded_publish_runner.py
git status --short
git commit -m "182: post-cleanup prose_length verify 緩和 (100 → 50 + env MIN_PROSE_AFTER_CLEANUP override、yellow 6 件 publish 復活見込)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

- changed files
- pytest collect: 1416 → after
- new tests: count
- threshold change verify: 100 → 50
- env override verify: yes/no
- 既存 test 影響: 旧 prose_lt_100 test 数件を新 threshold 用に reverse(具体)
- 既存挙動破壊: なし
- live publish / Cloud Run deploy / push: 全て NO
- commit hash

## stop 条件

- 旧 prose_lt_100 test 修正で広範囲影響発覚 → 即停止 + 報告
- 他 verify check 修正が必要 → 即停止 + 報告
- pytest 1416 を割る → 即停止 + 報告
- write scope 外 → 即停止 + 報告

## 完了後の次便

- 次 guarded-publish tick(*/5)で yellow 6 件 cleanup → publish 復活見込
- publish-notice mail 復活見込
- 観察 24h、cleanup_failed_post_condition 件数推移確認
