# 165 gemini + wp-rest resilience(retry + exponential backoff + 429 handling)

## meta

- number: 165
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: quality / resilience / external API
- status: **READY**(155-1a と disjoint scope、即 fire 可)
- priority: P0.5(GCP 移行後の残リスク #1: Gemini API rate limit / WP REST 一時 outage)
- lane: B
- created: 2026-04-26
- parent: 155(GCP migration)の残リスク対策

## 背景

GCP 移行で PC 起因の停止は消えるが、**Gemini API rate limit / WP REST 一時 outage** は残る。現状の retry 実装に以下のギャップ:

### Gemini(`src/tools/draft_body_editor.py:252` `call_gemini`)

- `GEMINI_RETRY` + 即時 retry あり、ただし **backoff sleep なし**
- HTTPError **4xx を即時 fail**(429 rate limit も 4xx → retry されない)→ rate limit hit で即座に loose
- `Retry-After` header 未対応

### WP REST(`src/wp_client.py`)

- **retry / backoff 一切なし**
- transient network error / 5xx で即 fail、cron tick が無駄に
- 429 / 503 等で reconnect 機会なし

## ゴール

Gemini と WP REST の両方に **exponential backoff + 429/5xx 専用 retry** を入れる。一時 outage で cron tick が無駄に潰れないようにする。

## 仕様

### Gemini(`src/tools/draft_body_editor.py:call_gemini`)

1. HTTPError 分岐を以下に変更:
   - **400-428 / 430-499** → 即 fail(既存通り、不正 request 等)
   - **429**(rate limit)→ retry path、`Retry-After` header あれば respect、なければ exponential backoff
   - **5xx**(server error)→ retry path
   - URLError / TimeoutError → retry path(既存通り)
2. retry 間 sleep を追加: `sleep(min(2**attempt + random.uniform(0, 1), 60))`(jitter 付き、上限 60s)
3. retry 数は `GEMINI_RETRY`(既存定数)を尊重、default は変更しない
4. `Retry-After` header parse は秒数 int / HTTP-date 両対応(秒数優先、parse 失敗は exponential fallback)
5. 既存の 4xx 即 fail 挙動は 400-428 / 430-499 で維持(test 互換)

### WP REST(`src/wp_client.py`)

1. 共通 helper `_request_with_retry(method, url, ...)` を WPClient class 内に新規追加
2. helper 内で:
   - HTTPError **400-428 / 430-499** → 即 fail
   - **429** → retry、`Retry-After` 尊重
   - **5xx** → retry、exponential backoff
   - URLError / TimeoutError / ConnectionError → retry
3. 既存 method(`get_post` / `list_posts` / `update_post_status` / 他)は helper 経由に書き換え
4. retry 数 default = 3、間隔 = `min(2**attempt + jitter, 30)`
5. 429 / 5xx 以外の HTTPError は **挙動不変**(既存 caller test 互換)

## acceptance

1. Gemini 429 を mock した test で `Retry-After` 尊重 + retry 後 success
2. Gemini 5xx 連続 → exponential backoff + 最終 fail で `GeminiAPIError`
3. Gemini 4xx(429 以外)→ 既存通り即 fail(test 互換維持)
4. WP REST 429 mock → retry 後 success
5. WP REST 5xx 連続 → backoff + 最終 fail
6. WP REST 4xx(429 以外)→ 既存通り即 fail
7. WP REST URLError → retry 後 success
8. existing `tests/test_draft_body_editor.py` / `tests/test_wp_client.py`(あれば)pass 維持
9. pytest baseline 1338 → 1338+新 tests、pre-existing fail 0 維持
10. live publish / WP write / push: 全て NO

## 不可触

- `src/guarded_publish_evaluator.py` / `src/guarded_publish_runner.py`(135 系、別便で land 済)
- `src/tools/run_draft_body_editor_lane.py`(155-1a Dockerfile build 対象、scope 干渉避ける)
- `src/sns_topic_*.py` / `src/lineup_*.py` / `src/published_*.py`
- `automation*` / `scheduler` / `front` / `plugin` / `build`
- `requirements*.txt`(新 dependency 追加禁止、stdlib `time` / `random` / `email.utils` だけで実装)
- `.env` / secrets / `crontab`
- baseballwordpress repo
- WSL crontab(155 系)/ Codex Desktop automation
- WP / X / Cloud Run env / scheduler

## Fire-time baseline(2026-04-26 15:30 JST)

- repo: `/home/fwns6/code/wordpressyoshilover`
- branch HEAD: `5c845a8`
- pytest collect: 1338 / pre-existing fail 0(再確認: `cd ... && python3 -m pytest --collect-only -q | tail -3`)

## Hard constraints

- **触らない file**: 上記不可触全件 + 並走 task `ba56029xp`(155-1a)が touching する `Dockerfile.draft_body_editor` / `cloudbuild_draft_body_editor.yaml` / `doc/active/155-*`
- `git add -A` 禁止。stage は **`src/tools/draft_body_editor.py` + `src/wp_client.py` + `tests/test_draft_body_editor.py` + `tests/test_wp_client.py`(無ければ新規作成 OK)** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 一切触らない
- `git push` 禁止
- 新 dependency 追加禁止(`requirements*.txt` 触らない)
- `time.sleep()` で実時間待つ test は禁止(mock で `time.sleep` patch して秒数 assert)
- デグレなし lock: pytest pass 1338 + 新 tests。pre-existing fail 0 維持

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_draft_body_editor.py tests/test_wp_client.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

## Commit(stage 明示、push なし)

```bash
git add src/tools/draft_body_editor.py src/wp_client.py tests/test_draft_body_editor.py tests/test_wp_client.py
git status --short  # 上記 file のみ M/A、既存 dirty / untracked 触れていないこと確認
git commit -m "165: Gemini + WP REST resilience (exponential backoff + 429/5xx retry + Retry-After 尊重)"
```

`.git/index.lock` で commit 拒否時 → plumbing 3 段(write-tree / commit-tree / update-ref)で fallback。

## 完了報告(必須形式)

```
- changed files: <list>
- pytest collect: 1338 → <after>
- pytest pass: 1338 → <after>(pre-existing fail 維持: 0)
- new tests added: <count>
- commit hash: <hash>
- Gemini 429 retry: implemented yes/no
- Gemini Retry-After 対応: yes/no
- WP REST 429 retry: implemented yes/no
- WP REST 5xx retry: implemented yes/no
- 新 dependency 追加: NO 確認
- live publish / WP write / push: 全て NO
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- WP REST helper 化が既存 caller 多数 + test 影響大 → 即停止 + 報告(別 ticket で chunked rollout)
- pytest 1338 を割る → 即停止 + 報告、push しない
- write scope 外を触る必要 → 即停止 + 報告
- 新 dependency が必要(stdlib で済まない)→ 即停止 + 報告

## 残リスク tickets queue(本 ticket は #1)

| # | risk | ticket 番号予定 |
|---|---|---|
| #1 | Gemini API + WP REST retry / backoff | **165(本)** |
| #2 | Cloud Run Job failure alert(Pub/Sub → mail/Slack)| 166(155-1b deploy 後 fire)|
| #3 | GCP billing alert(月額 $X 超で notify)| 167(user op 主、SOP 化のみ)|
| #4 | RSS source health check(主 source 連続 fail 検知)| 168(low priority、後回し)|
| #5 | code bug rollback SOP | 169(doc-only) |
| #6 | GCP region outage(multi-region は overkill、graceful skip 設計)| 170(low priority)|
