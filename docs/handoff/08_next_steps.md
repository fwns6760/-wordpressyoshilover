# ここから進める具体的な一歩（2026-04-18 夜時点）

## 次の大きな判断: Phase C 公開解放

**現状**: publish 全量 fact_check 監査で red 0件、新parser 稼働中（`00135-rpc`）。
朝時点の「T-001 調査 → T-003 解決 → T-002 判断 → postgame/lineup 試験」は**すべて解決済み**。
受け入れ試験の代替として publish 全量監査を実施し、品質基準は実質クリア。

**次の一手**: `postgame` / `lineup` の publish を解放する env 変更を判断する。

### 解放時の env 変更（Codex 実行）

```bash
gcloud run services update yoshilover-fetcher \
  --region asia-northeast1 \
  --project baseballsite \
  --update-env-vars ENABLE_PUBLISH_FOR_POSTGAME=1,ENABLE_PUBLISH_FOR_LINEUP=1,RUN_DRAFT_ONLY=0
```

解放前に確認すべきこと:
- [ ] T-004 / T-006 の Gmail 朝メール確認（よしひろさん側）
- [ ] 今日一日のドキュメント引き継ぎが最新（本ファイル + `07_current_position.md`）
- [ ] 2026-04-19（日）は試合日。解放直後に実動作観察できるタイミングで解放するのがベスト

解放後の観察ポイント:
- 次の Scheduler 発火（毎時）で publish が実際に起きるか
- 1時間おき fact_check メールに publish が反映されるか
- WP 公開一覧に `postgame` / `lineup` のみ出ているか（他カテゴリは `ENABLE_PUBLISH_FOR_*=0` 維持）

### 解放しない選択肢

今すぐ解放しない場合の代替:
- **T-001 第18便**: Xserver SSH 情報を手に入れて WP 反映 → 実機で `?status=draft` が機能することを確認 → T-001 RESOLVED
- **T-010 A=5 / T-014 4件**: WONTFIX 判断で閉じるか、狭い抽出ルール追加で片付けるか判断
- **T-017 観察**: 2-3 日継続して 07:00 JST に demo 落ちが出ないことを確認

## 直近ですぐ Codex に投げられるタスク

| タスク | 依頼書 | 前提 |
|---|---|---|
| T-001 WP 反映（第18便） | 未作成 | Xserver SSH 接続情報 or WP admin 権限 |
| Phase C `postgame` / `lineup` 解放 | 未作成 | よしひろさん判断 |
| T-010 A=5 除外ルール (c) 実装 | 未作成 | 仕様合意 |
| T-014 4件の subject 抽出ルール調整 | 未作成 | WONTFIX か修正か判断 |

## 今日やらないこと

- manager / notice 以降の受け入れ（postgame / lineup 安定後に段階的に）
- X投稿の解放（publish 数日安定後に別段階）
- Phase 3 段階2〜4（Phase C 全カテゴリ安定後に着手）
- 新機能追加（Phase C 期間中は実装タスクを増やさない）

## 差し戻しが出た場合（解放後）

1. 差し戻し記事の post ID と問題点を Claude Code に伝える
2. Claude Code が Codex 向け指示書を作成（`docs/handoff/codex_requests/YYYY-MM-DD_NN.md`）
3. Codex が修正 + deploy
4. 翌日以降に再観察

## 明日以降のルート

- **04-19（日）試合日**: Phase C 解放済なら publish 後の実動作観察 / manager / notice の受け入れ
- **04-20（月）**: pregame / recovery / farm の受け入れ（オフ日で落ち着いて確認）
- **04-21〜**: social / player / general 順次解放
- **今週末**: X投稿段階（`ENABLE_X_POST_FOR_*=1`）移行開始

## Phase C 完了後の次の山

**Phase D: アンテナサイト登録・SEO 強化**
1. 主要アンテナサイトへの登録申請
2. カテゴリページの SEO 改善
3. Search Console / GA4 の観察導線整備
4. のもとけ型の選別的インデックス戦略（低品質記事の noindex 判断）

## 体力配分の目安

- 朝: fact_check メール確認（スマホで5分）
- 午前 / 午後: 必要があれば Codex 依頼書作成判断（10-30分）
- 夜: その日の結果確認（10分）

**1日30〜60分の判断作業。それ以上はやらない。**
