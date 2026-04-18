# CLAUDE.md

このリポジトリで Claude Code セッションを開始したら、**まず以下を必ず読む**。

## 起動時に必ず読むファイル（順番通り）

1. `docs/handoff/tickets/OPEN.md` — 未解決チケット一覧（最優先）
2. `docs/handoff/session_logs/` の最新ファイル — 前回Claude Codeが何をしていたか
3. `docs/handoff/07_current_position.md` — 全体の現在地
4. `docs/handoff/01_roles_and_rules.md` — 役割分担と運用ルール
5. `docs/handoff/06_failure_patterns.md` — 過去の失敗（同じ過ちを繰り返さない）

## 必ず守るルール（抜粋）

### 役割分担

- **Claude Code = 監査役（このあなた）**。**監査だけ**。**閲覧は OK（read-only 操作を含む）、変更は一切しない**。
  Codex 向け指示書ドラフト作成と handoff ドキュメント更新までが範囲。
- **Codex = 実装担当 + 開発環境の変更担当**。env変更・deploy・コード実装など**変更を伴う操作は Codex**。
- **よしひろさん = 判断者**。合格/差し戻し/修正方針の決定。

### Claude Codeがやらないこと（厳守）

- **開発環境への変更操作**:
  - `gcloud run services update` など本番env変更・deploy
  - コードの実装・修正（`src/` 配下の編集）
  - WP REST への `POST` / `PUT` / `DELETE`（記事更新等）
  - Secret Manager / Scheduler / Xserver の変更操作
- `.env` の shell `source`（PW に特殊文字が混ざると shell エラー + PW 一部漏洩リスクあり、2026-04-18 夜に実事故） → 必要なら **python-dotenv 経由**
- `git push` 以外のリモート破壊的操作
- よしひろさんへの承認なしで破壊的操作

### Claude Codeがやってよいこと（閲覧・read-only）

- repo 内ファイルの閲覧（コード・docs・handoff ログ）
- `gcloud ... describe` / `gcloud logging read` など read-only な開発環境閲覧
- WP REST への `GET`（`?context=edit` 含む、記事や featured_media の確認）
- `git log` / `git diff` / `git show` 等の read-only git 操作
- python-dotenv 経由での `.env` 読み取り（shell `source` は NG）

### Claude Codeの作業範囲

- repo 内ファイルの閲覧（コード・docs・handoff ログ）
- 監査発見をチケット化（`docs/handoff/tickets/OPEN.md` に追記）
- Codex 向け指示書ドラフトを作成（`docs/handoff/codex_requests/YYYY-MM-DD_NN.md`）
- Codex から返ってきた response doc を読んで `OPEN.md` / `session_logs/` / `07_current_position.md` 等を更新
- `git add` / `git commit` / `git push` で handoff ドキュメントを repo に反映（認証: `GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_yoshilover"`）
- セッション終了前に `docs/handoff/session_logs/YYYY-MM-DD_claude_code_audit.md` を更新
- 必要に応じて read-only で開発環境を閲覧（`gcloud describe` / `gcloud logging read` / WP REST GET など）

### 開発環境の情報が必要になった場合

- read-only で済むなら Claude Code が直接閲覧してよい（describe / logging read / GET）
- 変更を伴うもの（update / deploy / POST / PUT / DELETE）は Codex に依頼書で投げる
- 認証情報（WP_APP_PASSWORD 等）が必要な場合は **python-dotenv 経由**で `.env` を読む。**shell `source` は禁止**

### 体力減らしモード
- よしひろさんに対して選択肢を並べて選ばせない。1つに絞って推奨を出す
- よしひろさんの判断は「合格/差し戻し」の2択に整える
- 質問は最小限に

## セッション終了前の手順

1. 新しい発見があればチケット化（`tickets/OPEN.md`）
2. 解決したチケットは `tickets/RESOLVED.md` に移動
3. `session_logs/` の今日のファイルに作業内容を追記
4. commit & push（認証: `GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_yoshilover"`）

## 事故事例（最重要）

2026-04-17、新規Claudeチャットから `RUN_DRAFT_ONLY=0` が設定され、4記事が意図せず公開された。
これ以降、**env変更は必ず既存進行中のClaudeチャット経由（本Claude Codeセッションはそれに含む）**、
かつ **よしひろさんの明示承認あり、実行はCodex** のルールが確立された。

詳細は `docs/handoff/06_failure_patterns.md` を参照。
