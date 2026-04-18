# 役割分担と運用ルール

## 5者の役割

### よしひろさん（オーナー・最終判断者）
- 受け入れ試験の合否判断（publishするか/差し戻すか）
- Phase C各カテゴリのpublish/X投稿解放タイミング決定
- 戦略方針の決定
- 体力有限のため、判断は「合格/差し戻し」の2択で設計される

### Claude Opus（メインチャット・戦略パートナー）
- 日々の作業指示の起点
- よしひろさんとの対話・意思決定サポート
- ログ確認・品質監査・リスク指摘
- Codexへの指示書（プロンプト）作成
- **env変更もここ経由で実施**（最重要）

### Codex（実装担当）
- Claude Opusから渡された指示書に基づきコード実装
- テスト作成・修正・deploy（git push）まで完結
- 独断でenv変更しない
- 詳細は `AGENTS.md` を参照

### Claude Code（監査・ドキュメント・探索）
- 監査役の主担当
- ファイル作成・ドキュメント整備
- コードの確認・探索
- Codex依頼書の起票
- **env変更・コードの本番deploy系は行わない**

### Gemini CLI（監査待機・代行）
- 通常時は待機
- **Claude Code が停止・quota 枯渇・セッション断で止まったときだけ**監査役を代行
- 代行時は `CLAUDE.md` を起点に同じルールで読む
- 代行範囲は監査・探索・Codex依頼書ドラフト・handoff docs 更新まで
- **実装・deploy・env変更・git push は行わない**

## 体力減らしモード原則

よしひろさんの判断コストを最小化するための設計原則。

**やること:**
- Claude/Codexが選択肢を提示するとき、推奨を1つに絞る
- 「AとBどちらにしますか？」より「Aを推奨します。差し戻すならBも可能です」
- 受け入れ試験は1日2〜3カテゴリまで
- 30分区切り、ブロック間5分休憩推奨

**やらないこと:**
- 複数選択肢を並べてよしひろさんに選ばせる（体力消費大）
- 「どうしますか？」だけで終わる提示
- 1日に大量のreview/判断を要求する

**実例（失敗→改善）:**
- 失敗: タスクを細切れにして1つずつ確認を求めた
- 改善: 関連タスクを1つの指示書にまとめてCodexに一括投げ

## env変更ルール（最重要・事故教訓）

**ルール: env変更は必ず既存進行中のClaudeチャット経由で行う**

### なぜこのルールが存在するか
2026-04-17に、新規Claudeチャットから `RUN_DRAFT_ONLY=0` が設定された。
その結果、制御なしで4記事がpublishされた。意図しない公開だった。

### 具体的な手順
1. Claudeとのチャットで「○○のenvを○○に変更したい」と伝える
2. Claudeが現在のenv全量を確認した上で変更手順を示す
3. 変更内容をCodexの指示書に明示する
4. deployしたrevisionでsmoke testを実行する
5. `RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` の維持を確認する

### 禁止事項
- 新規チャットからCloudConsoleのenvを直接変更
- Claudeに「envを更新して」だけ言う（変更内容の確認なしに実行される可能性）
- `RUN_DRAFT_ONLY=0` の設定はPhase C受け入れ完了後のみ

## 協働フロー

```
よしひろさん
    ↓ 「今日の作業、何をやる？」
Claude Opus
    ↓ ログ確認 + 優先度提案（体力減らし）
よしひろさん
    ↓ 「OK、これをやる」
Claude Opus
    ↓ Codex指示書作成（詳細、env変更含む）
Codex
    ↓ 実装 → test → git push → deploy
Claude Opus
    ↓ smoke test確認 + 結果報告
よしひろさん
    ↓ 受け入れ判断（合格 or 差し戻し）
```

## Claude Code 停止時の代行フロー

```
Claude Code 停止
    ↓
Gemini CLI 起動
    ↓ `CLAUDE.md` を最初に読む
OPEN.md / 最新 session_log / 07_current_position / 01_roles_and_rules / 06_failure_patterns を順に確認
    ↓
監査・事実確認・Codex依頼書ドラフトだけ実施
    ↓
Claude Code 復帰後に監査役を戻す
```

## 重要な運用習慣

- **smoke testは毎deploy後**: `bash scripts/cloud_run_smoke_test.sh`
- **テスト354本**: 全変更後に `pytest` でグリーン確認（Codex担当）
- **git pushはCodex担当**: Claude Codeは基本的にpushしない
- **Gemini CLI も push しない**: 監査代行でも git 反映は Codex担当
- **ログはCloud Logging**: `docs/operation_logs.md` のクエリ集を使う
