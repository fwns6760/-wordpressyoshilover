# 新規Claudeチャット移行手順

## いつ移行するか

- Claude Opusのコンテキストが限界に近づいたとき（応答が遅くなる、過去の文脈を忘れ始める）
- 新しいトピック（Phase D開始等）で別のセッションを開始するとき
- 事故対応で緊急的に新しいチャットを開くとき

**原則: できるだけ既存のチャットを継続する。移行コストは高い。**

## 移行時の必須手順

### 1. 引き継ぎ書を貼る
新規チャットを開いたら最初に:
```
このファイルを読んでください: docs/handoff/README.md
その後、以下の順で読んでください:
1. docs/handoff/00_project_overview.md
2. docs/handoff/03_current_state.md
3. docs/handoff/07_current_position.md
4. docs/handoff/01_roles_and_rules.md
5. docs/handoff/06_failure_patterns.md
```

または引き継ぎ書のテキストを直接コピペする。

### 2. 現在のenv状態を確認する
```bash
gcloud run services describe yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --format='value(spec.template.spec.containers[0].env)'
```
この出力を新規チャットに貼る。

### 3. 最新のrevisionを伝える
```bash
gcloud run revisions list \
  --service yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --limit=3
```

### 4. 現在のテスト数を確認する
```bash
python -m pytest --tb=short -q 2>&1 | tail -5
```

## 移行時に絶対確認すること

- **env変更ルールを新規チャットに必ず伝える**
  - 「env変更は必ずClaudeチャット経由。新規チャットからgcloud run services updateを直接実行しない」
- **現在のPhaseを明示する**
  - 「現在はPhase C受け入れ試験フェーズ。RUN_DRAFT_ONLY=1。全publishフラグ=0」
- **体力減らしモードを明示する**
  - 「選択肢は1つに絞って推奨する。複数案を並べてYoshihiroに選ばせない」

## 移行時に絶対やってはいけないこと

- 新規チャットからenvを変更する（事故の再現）
- `RUN_DRAFT_ONLY=0` を新規チャットから設定する
- 引き継ぎ書を読まずにCodexへの指示書を書く

## 緊急移行テンプレート

急いでいるときはこれをコピペ:

```
ヨシラバー開発の引き継ぎです。

【今の状態】
- revision: yoshilover-fetcher-00130-nxg
- RUN_DRAFT_ONLY=1（安全側）
- 全publishフラグ=0
- テスト354本PASS
- Phase C受け入れ試験中（postgame/lineup待ち）

【最重要ルール】
- env変更は必ずこのチャット経由
- 新規チャットから絶対にenvを変更しない
- 受け入れ試験合格→既存チャットで env変更指示→Codexがdeploy
- 体力減らしモード: 選択肢は1つに絞る

詳細: docs/handoff/README.md の順で読んでください
```

## Codex移行時の注意

Codexは毎回新規セッションなので、必ず `AGENTS.md` の先頭を読ませること。
特に以下を確認させる:
- SSH設定（`git@github-yoshilover:...`）
- 現在の本番revision
- テストがPASSしているか
