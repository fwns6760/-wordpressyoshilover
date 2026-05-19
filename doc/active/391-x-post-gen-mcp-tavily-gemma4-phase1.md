# 391: 巨人 X 投稿案生成 — Tavily MCP (stdio 同梱) + Gemma 4 31B (Phase 1 CLI)

status: PLANNING (user GO 待ち)
owner: Claude Code
lane: (未確定、user 指示待ち)
priority: (未確定、user 指示待ち)
created: 2026-05-19 JST
github_issue: #66

---

## 1. 作業の目的

巨人関連トピックを web 検索しつつ X 投稿案を生成する CLI smoke を実装する。
Phase 1 範囲は **ローカル CLI で stdout 出力**のみ。 メール送信・ WP 書き込み・
X live posting は行わない。 Phase 2 (Cloud Run Job 化) は **別 ticket**。

## 2. やること (scope)

- `src/x_post_gen_mcp.py` (新規) — Tavily MCP stdio client + Gemini API
  Gemma 4 31B で post draft を生成する core。
- `src/tools/run_x_post_gen_mcp.py` (新規) — CLI entrypoint。 環境変数で
  API key を受け、 query を回し stdout に出す。
- `tests/test_x_post_gen_mcp.py` (新規) — mock-based unit tests。
- `requirements.txt` — `google-genai` と `fastmcp` を追加。
- 既存 `google-generativeai` は **削除しない** (他 lane が依存)。

Phase 1 段階では実 API 呼び出しは smoke run 時のみ。 CI / pytest では
mock を使い実 API に当たらない。

## 3. 今回触らない範囲

- `src/x_post_mail_lane.py` (382 multi-source shape B 改修中、別 ticket #5 で commit 待ち)
- `src/analysis/ranking_article_publisher.py` (387 改修ファイル、未 commit)
- `src/main.py` / `src/fetcher_*` / `src/draft_body_editor*` (記事生成 lane)
- `src/guarded_publish*` / `src/publish_notice*` (publish / mail lane)
- `automation/` / Codex automation 設定一式
- `Dockerfile*` / `cloudbuild*.yaml` (Phase 2 で別 ticket)
- Cloud Run Job (新規も既存も触らない)
- Cloud Scheduler (新規も既存も触らない)
- Secret Manager (新規 secret も追加しない、 Phase 1 はローカル env var)
- WordPress (REST / DB / plugin / theme 一切触らない)
- X / Twitter (live posting / OAuth / Hermes 一切触らない)
- 既存 mail lane (既存メール本文に混ぜない)

## 4. 影響範囲

- **コード**: 新規 file 3 本 (src/x_post_gen_mcp.py / src/tools/run_x_post_gen_mcp.py / tests/test_x_post_gen_mcp.py)。 既存 import しない。
- **依存**: requirements.txt に 2 line 追加 (`google-genai`, `fastmcp`)。 既存依存 (`google-generativeai`, `requests` 等) は変更しない。
- **設定**: env / secret / scheduler 変更なし。
- **実行系**: 既存 Cloud Run Job / Scheduler / mail / publish には影響なし。 新規 file は import されるまで dead code。
- **ローカル実行のみ** (WSL 内) — 本番 deploy は Phase 2。

## 5. 実行予定テスト

- `python3 -m py_compile src/x_post_gen_mcp.py src/tools/run_x_post_gen_mcp.py tests/test_x_post_gen_mcp.py`
- `python3 -m unittest tests.test_x_post_gen_mcp` (新 file 単独)
- `python3 -m unittest discover -s tests` (全 suite、 baseline 4461 OK を維持)
- `python3 -m src.tools.run_x_post_gen_mcp --dry-run` (credentials 不要、 queries echo)
- `python3 -m src.tools.run_x_post_gen_mcp --max-queries 2` (実 API smoke、 user が key 渡したら 1 回だけ)

mock tests の対象:
- `_generate_one_draft` の error path (Gemini Client 失敗時に PostDraft.error に詰める)
- `generate_post_drafts` の query 数 = output 数
- 空 query list で empty 返す
- ImportError handling

## 6. STOP 条件

以下のいずれかが満たされたら **即停止**して user 判断に上げる。

- pytest 全 suite で **regression** (4461 OK 数が減る)
- py_compile 失敗
- `google-genai` install で既存 `google-generativeai` と conflict
- 実 API smoke で **0 ドル制約超過の兆候** (Tavily credit が 1 run で 10+ 消費等)
- 実 API smoke で **spec 382 違反**な出力 (unverified 数字 / 引用 / 媒体名 / URL / hashtag が post 本文に混入)
- Tavily MCP server が npx -y で起動できない (Node.js 不在 等)
- Gemma 4 31B が rate limit で 429 連発 (free tier では使い物にならない判定)
- 既存 file に予期しない git diff が出る (scope leakage)

## 7. 禁止事項

- code edit 以外の `git add` / `git commit` / `git push` (Markdown commit も含めて user GO 前は禁止)
- 既存 `src/` file の編集 (382 / 387 改修対象も含めて触らない)
- Cloud Build / Cloud Run / Cloud Scheduler / Secret Manager の **API 呼び出し**
- env 変数の永続変更 (`.env` 編集 / Secret Manager versions add 等)
- WordPress への REST 呼び出し (GET も含めて Phase 1 では不要)
- X / Twitter API 呼び出し
- 既存 Cloud Run Job への env / image update
- automation.toml / `.codex/automations/` の編集
- `requirements.txt` で既存 line の削除 / version pin 変更
- 公開記事の削除 / 書き換え
- SNS / 新カテゴリ解放
- Gemini API の **paid tier** への切替 (free tier 維持必須、 0 ドル制約)
- Tavily API の **paid plan** 加入 (free 1000 credits/月のみ)

## 8. 想定されるデグレ

| 項目 | リスク | mitigation |
|---|---|---|
| `google-genai` install で `google-generativeai` と衝突 | 中 | install 前に `pip install --dry-run` で resolver 確認、 conflict 検出時は ticket で対処方針確認 |
| 新規 file が既存 test discover で import error 発生 | 低 | tests/test_x_post_gen_mcp.py で deps の有無を skipIf gate |
| fastmcp / google-genai が experimental で API 変更 | 中 | version pin 明示 (`fastmcp>=X,<Y` 等)、 mock-based test で実 API 依存を回避 |
| Tavily MCP stdio subprocess が WSL 上で broken pipe | 中 | timeout / retry / 例外を `_generate_one_draft` で catch、 error は PostDraft.error フィールドに格納 |
| Gemma 4 31B が日本語 baseball context で意味ない出力 | 高 (品質 unverified) | smoke run で user 目視確認、 NG なら Phase 2 中止 |
| Gemini API free tier rate limit でほぼ使えない | 中 | smoke で 429 観測したら STOP、 別 model (Gemini 2.5 Flash-Lite + grounding) 検討 |
| Tavily search が巨人以外の話題を引いて hallucination 助長 | 中 | query を「巨人」「ジャイアンツ」始まりで縛る、 system prompt で巨人外を除外 |

既存 lane (記事生成 / publish / mail / X post mail / data-insight 等) には
**file import されないため影響なし**。 dirty file として残るだけ。

## 9. 必要な API (user 追加要求)

Phase 1 smoke run には以下 2 つの API key が必要。 **両方とも完全無料 signup**
で credit card 不要。

| API | 用途 | 無料枠 | 取得先 |
|---|---|---|---|
| **Gemini API** | Gemma 4 31B 推論 | "Free of charge" (input/output/context caching) | https://ai.google.dev/ (Google account のみ) |
| **Tavily API** | web 検索 (MCP server 経由) | 1,000 credits/月 free | https://tavily.com/ (signup、credit card 不要) |

user 側 task:
1. 両 service で signup
2. 各 API key を発行
3. ローカルで env var として渡す:
   ```bash
   export GEMINI_API_KEY=...
   export TAVILY_API_KEY=...
   ```
4. CLI 実行:
   ```bash
   python -m src.tools.run_x_post_gen_mcp --max-queries 2
   ```

Phase 1 では **Secret Manager に登録しない**。 Phase 2 で Cloud Run Job 化する時に
別 ticket で Secret Manager に渡す。

### 必要 npm package (stdio 同梱前提)

ローカル smoke では npx 経由で on-the-fly install。 Node.js 20+ が WSL 内に
必要。

```bash
node --version   # v20 以上を確認
npx -y tavily-mcp@latest   # 起動確認 (Ctrl+C で抜ける)
```

Node.js 不在の場合は CLI 実行時に `FileNotFoundError` で run-time error
表示。 STOP 条件に該当。

### 必要 Python package

```
google-genai     # Gemini SDK (MCP 統合 experimental)
fastmcp          # MCP client (stdio transport 含む)
```

両方 pure Python。 既存 `google-generativeai` は別 package (旧 SDK) なので
coexist 可能。 ただし `pip install --dry-run` で resolver 確認必要。

## 10. 作業ログ欄

(post-work で append)

- (例) HH:MM JST | event | detail

## 11. Regression Memo 欄

(post-work で append)

- (例) 観測した予期しない挙動 / 追加 test case / future risk

---

## post-work sections (Markdown GO 後の work 完了時に追記)

### post-work 1. 実際に変更したファイル
(TBD)

### post-work 2. diff 概要
(TBD)

### post-work 3. 実行したテスト
(TBD)

### post-work 4. テスト結果
(TBD)

### post-work 5. 残った懸念
(TBD)

### post-work 6. 新しく見つかったデグレ
(TBD)

### post-work 7. 追加した回帰テスト
(TBD)

### post-work 8. 次回触ってはいけない範囲
(TBD)

---

## meta — process compliance

- 2026-05-19: user が「ちょっと。 チケットきってる?」と process 違反指摘
- 私が code 2 file (`src/x_post_gen_mcp.py` / `src/tools/run_x_post_gen_mcp.py`) を ticket 切らずに書いていた事実を認める
- 本 Markdown 作成までが許可された範囲、 code 編集 / commit / push / deploy / env / scheduler / GH Issue 作成は user GO 待ち
- 既に書いた 2 file は dirty として残置 (roll back せず、 Markdown GO 後に ticket scope と再 verify する)

## meta — 仕様継承

- spec 382 (`doc/done/2026-05/382-MKT-yoshilover-branding-post-planning-mail.md`) の
  hard rule を **post 本文生成にも適用**:
  - URL / hashtag / 「ヨシラバーで整理しました」を含めない
  - 未検証 score / rank / injury / roster / 打率 / 防御率 / OPS / inning / hit count / RBI / quote を含めない
  - DB 照合できない数字は generalize
  - ヨシラバー独自の framing、 記事タイトルのコピーは禁止
- spec 382 の representative shapes (shape A コメント+DB# / shape B 複数媒体) は
  Phase 1 では **system prompt で言及するに留め**、 厳密 enforce は post-gen
  validator で後追い (Phase 2 以降)。

## meta — 0 ドル制約 hard rule

- Gemini API は **free tier のみ**、 paid 切替禁止
- Tavily API は **1000 credits/月 以内**、 paid plan 加入禁止
- Cloud Run / Vertex AI / GPU self-host **全面禁止** (Phase 1 scope)
- Phase 2 で Cloud Run Job 化する時も **always-free 枠内** に量を絞る (1 run/日 × 5 query/run = 150 credits/月)
- 量増を user 判断するのは **§11 4 領域 (API 課金増)** に該当
