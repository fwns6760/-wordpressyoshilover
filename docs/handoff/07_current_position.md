# 今ここ（2026-04-18 朝の現在地）

## 朝の時点で完了していること

### Phase 3 段階1: スマホ通知稼働
- `acceptance_fact_check` CLIが実装済み
- `GET /fact_check_notify?since=yesterday` エンドポイントが本番稼働
- Gmail app password問題を解決（`GMAIL_APP_PASSWORD_SECRET_NAME` の柔軟化）
- 実メール送信成功（`fact_check_email_sent` ログ確認）
- Scheduler job `fact-check-morning-report` が稼働開始
- 毎日 7:00/12:00/17:00/22:00 JST にメールが届く

### インフラ
- 稼働revision: `yoshilover-fetcher-00130-nxg`
- 全env: 安全側（`RUN_DRAFT_ONLY=1`, 全publishフラグ=0）
- テスト354本: 全PASS

### Phase C準備
- カテゴリ別publish/X投稿フラグ20個が全て`0`で待機状態
- 受け入れ試験チェックリストが整備済み
- Phase C runbookが整備済み

## まだやっていないこと

### 受け入れ試験（今日から開始）
- `postgame` の受け入れ試験: **未実施**
- `lineup` の受け入れ試験: **未実施**
- その他全カテゴリも未実施

### Phase C本番
- `RUN_DRAFT_ONLY=0` への切り替え: **未実施**（受け入れ完了後）
- `ENABLE_PUBLISH_FOR_POSTGAME=1` 等の解放: **未実施**（受け入れ完了後）

### Phase 3 段階2〜4
- WP承認ワンクリック（スマホ対応）: **未着手**
- X投稿フレーズ選択（スマホ対応）: **未着手**

## Claude Opus（メインチャット）の状態

- 2026-04-18朝の作業（Gmail修正・メール通知実装）を完了した時点で一区切り
- 次の作業: よしひろさんが受け入れ試験を始める際に継続
- **env変更が必要な場合はこのチャット経由で行う**

## Codex の状態

- 最後の実装: revision `00130-nxg`（Gmail app password修正）
- 次の作業待ち: 受け入れ試験で差し戻しが出た場合、Claudeから指示書を受け取る
- quotaは節約中（受け入れ試験は人間+Claudeが主体）

## 朝の最初にやること

1. スマホで `【ヨシラバー】MM/DD 事実チェック結果` メールを確認
2. `🔴` がある場合: WP直リンクから該当draftを先に確認し、publish候補から除外
3. `python3 -m src.acceptance_fact_check --category postgame --limit 10` でlocal確認
4. WP管理画面でpostgameのdraftを10件開いて採点
5. 合格なら: `ENABLE_PUBLISH_FOR_POSTGAME=1` + `RUN_DRAFT_ONLY=0` のenv変更を既存Claudeチャットに依頼

## 現在地の一言

**Phase C受け入れ試験の入り口に立っている。スマホ通知も整い、あとはよしひろさんが試験を進めるだけ。**
