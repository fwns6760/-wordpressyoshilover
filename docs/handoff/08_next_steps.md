# ここから進める具体的な一歩

## 直近の次の一手

**postgame の受け入れ試験を実施する。**

```bash
# Step 1: fact check CLIでpostgameの事実チェック
python3 -m src.acceptance_fact_check --category postgame --limit 10

# Step 2: WP管理画面でpostgame drafts上位10件を人間が目視確認
# URL: https://yoshilover.com/wp-admin/edit.php?post_status=draft&post_type=post

# Step 3: 合格なら（重大欠陥0、8割以上OK）:
# → 既存Claudeチャットに「postgame受け入れ合格。ENABLE_PUBLISH_FOR_POSTGAME=1に切り替えたい」と伝える
```

## 今日のゴール: postgame/lineup受け入れ

| subtype | 試験状態 | 目標 |
|---------|---------|------|
| postgame | 未実施 | 受け入れ試験→合格→publish解放 |
| lineup | 未実施 | 受け入れ試験→合格→publish解放 |

両方合格した場合のenv変更（既存Claudeチャット経由）:
```
ENABLE_PUBLISH_FOR_POSTGAME=1
ENABLE_PUBLISH_FOR_LINEUP=1
RUN_DRAFT_ONLY=0
```

## 今日やらないこと

- manager/notice以降の受け入れ試験（まずpostgame/lineupに集中）
- X投稿の解放（publish安定後に別段階で実施）
- Phase 3 段階2〜4の実装（今日は段階1の実動作確認）
- コードの新機能追加（受け入れ試験フェーズは実装なし）

## 体力配分

- 朝: メール確認（5分） + postgame受け入れ（30分）
- 午前: lineup受け入れ（30分）
- 午後: 試合中の実動作観察（publishが解放されていれば）
- 夜: fact checkメール確認（5分）

**1日30〜60分の判断作業。それ以上はやらない。**

## 差し戻しが出た場合

1. 差し戻し記事のpost IDと問題点をClaudeチャットに伝える
2. ClaudeがCodex向け指示書を作成
3. Codexが修正 → deploy
4. 翌日以降に再受け入れ

## 受け入れ合格後の手順（Phase C本格開始）

```
受け入れ合格
    ↓
既存Claudeチャットに「合格」を報告
    ↓
Claudeが env変更手順を提示
    ↓
Codexがenv変更+deploy（or gcloud runコマンドを実行）
    ↓
smoke test実行
    ↓
次のScheduler発火（〜1時間以内）で実際のpublishを確認
    ↓
WP公開一覧に想定subtypeのみ出ているか確認
    ↓
問題なければ → 同じ手順でlineupも解放
```

## 明日以降の進行

- 04-19（日）: 試合日にpublish後の実動作観察、manager/noticeの受け入れ
- 04-20〜: pregame/recovery/farm の受け入れ（慎重に）
- 今週末目標: X投稿段階への移行開始

## Phase C公開完了後の次の山

**Phase D: アンテナサイト登録・SEO強化**

Phase Cで全カテゴリのpublishが安定したら:
1. 主要アンテナサイトへの登録申請
2. カテゴリページのSEO改善
3. Search Console / GA4の観察導線整備
4. のもとけ型の選別的インデックス戦略開始（低品質記事のnoindex判断）
