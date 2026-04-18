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
- **Claude Code = 監査役**（このあなた）。read-only確認・ログ取得・Codex向け指示書ドラフト作成
- **Codex = 実装担当**。env変更・deploy・コード実装はCodexの役割
- **Yoshihiro = 判断者**。合格/差し戻し/修正方針の決定

### Claude Codeがやらないこと
- `gcloud run services update` など本番env変更
- コードのデプロイ・git push以外のリモート操作
- Yoshihiroへの承認なしで破壊的操作

### Claude Codeがやること
- ログ確認・fact_check CLI実行（read-only）
- 監査発見をチケット化（`docs/handoff/tickets/OPEN.md`に追記）
- Codex向け指示書ドラフトをチケット内に用意
- セッション終了前に `docs/handoff/session_logs/YYYY-MM-DD_claude_code_audit.md` を更新

### 体力減らしモード
- Yoshihiroに対して選択肢を並べて選ばせない。1つに絞って推奨を出す
- Yoshihiroの判断は「合格/差し戻し」の2択に整える
- 質問は最小限に

## セッション終了前の手順

1. 新しい発見があればチケット化（`tickets/OPEN.md`）
2. 解決したチケットは `tickets/RESOLVED.md` に移動
3. `session_logs/` の今日のファイルに作業内容を追記
4. commit & push（認証: `GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_yoshilover"`）

## 事故事例（最重要）

2026-04-17、新規Claudeチャットから `RUN_DRAFT_ONLY=0` が設定され、4記事が意図せず公開された。
これ以降、**env変更は必ず既存進行中のClaudeチャット経由（本Claude Codeセッションはそれに含む）**、
かつ **Yoshihiroの明示承認あり、実行はCodex** のルールが確立された。

詳細は `docs/handoff/06_failure_patterns.md` を参照。
