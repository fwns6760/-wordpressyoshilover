# doc/ — チケット一覧

AGENTS.md の機能をチケットに分割したもの。
実装順序に番号を振ってある。**番号順に進める。飛ばさない。**

TODOの状態：`【】` 未着手 → `【×】` 完了

---

## チケット一覧

| # | ファイル | 内容 | 担当 | 依存 |
|---|---------|------|------|------|
| 001 | [001-project-foundation.md](001-project-foundation.md) | プロジェクト共通基盤（ディレクトリ・設定ファイル） | Claude Code | なし |
| 002 | [002-swell-category-setup.md](002-swell-category-setup.md) | フェーズ① SWELL＋カテゴリ固定 | 手動 | なし |
| 003 | [003-wp-client.md](003-wp-client.md) | フェーズ② wp_client.py（共通WPクライアント） | Claude Code | 001, 002 |
| 004 | [004-wp-draft-creator.md](004-wp-draft-creator.md) | フェーズ② wp_draft_creator.py（下書き自動生成） | Claude Code | 001, 003 |
| 005 | [005-rss-fetcher.md](005-rss-fetcher.md) | フェーズ③ rss_fetcher.py（RSS取得＋自動分類） | Claude Code | 001, 003, 004 |
| 006 | [006-x-post-generator.md](006-x-post-generator.md) | フェーズ④ x_post_generator.py（X文案生成） | Claude Code | 001, 003 |
| 007 | [007-x-api-client.md](007-x-api-client.md) | フェーズ⑤ x_api_client.py（X API連携） | Claude Code | 001〜006すべて |
| 008 | [008-deploy-xserver.md](008-deploy-xserver.md) | エックスサーバーデプロイ・運用開始 | 手動 | 001〜006 |
| 009 | [009-top-design-swell.md](009-top-design-swell.md) | TOPページデザイン SWELL実装 | 手動+Claude Code | 002 |
| 010 | [010-giants-lane-routing.md](010-giants-lane-routing.md) | 巨人版の固定版レーン / AIエージェント版レーンの分離設計 | Claude Code | 001〜009 |
| 011 | [011-fixed-lane-templates.md](011-fixed-lane-templates.md) | 固定版レーンの対象記事・テンプレート固定 | Claude Code | 010 |
| 012 | [012-game-id-state-model.md](012-game-id-state-model.md) | game_id / source_id 束ねと試合前中後の状態管理 | Codex A | 010 |
| 013 | [013-agent-lane-review-loop.md](013-agent-lane-review-loop.md) | AIエージェント版レーンの review / repair ループ | Codex B | 010, 011, 012 |
| 014 | [014-source-trust-and-taxonomy.md](014-source-trust-and-taxonomy.md) | source trust・カテゴリ・タグ設計 | Claude Code | 010 |
| 015 | [015-observation-and-acceptance.md](015-observation-and-acceptance.md) | Observation Ticket と受け入れ基準 | Claude Code | 010, 013, 014 |
| 016 | [016-agent-role-split.md](016-agent-role-split.md) | Claude Code / Codex A / Codex B のチケット分担表 | Claude Code | 010〜015 |
| 017 | [017-home-game-hub.md](017-home-game-hub.md) | ホーム上部の「今日の試合」ハブ | Codex A | 012, 014 |
| 018 | [018-player-topic-navigation.md](018-player-topic-navigation.md) | 選手タグ / 話題タグの回遊導線 | Codex A | 014, 017 |
| 019 | [019-fixed-lane-program-notice-cards.md](019-fixed-lane-program-notice-cards.md) | 番組情報 / 公示 / 予告先発の固定版カード | Codex B | 011, 014 |
| 020 | [020-postgame-revisit-chain.md](020-postgame-revisit-chain.md) | 1試合から複数の再訪理由を作る postgame 連鎖 | Codex B | 012, 013 |
| 021 | [021-farm-roster-loops.md](021-farm-roster-loops.md) | 公示 / 昇降格 / 二軍の 3 ループ接続 | Codex A | 012, 014, 019 |
| 022 | [022-multisource-merge-template.md](022-multisource-merge-template.md) | 複数 source 統合記事の agent テンプレ | Codex B | 013, 014, 020 |
| 023 | [023-fixed-lane-batch-routing.md](023-fixed-lane-batch-routing.md) | Gemini 2.5 Flash Batch API に流す固定版記事の境界 | Codex A | 011, 014, 019 |
| 024 | [024-gemini25flash-batch-jsonl-builder.md](024-gemini25flash-batch-jsonl-builder.md) | Batch 投入用 JSONL 生成 | Codex A | 023 |
| 025 | [025-gemini25flash-batch-result-loader.md](025-gemini25flash-batch-result-loader.md) | Batch 結果の Draft 取り込み | Codex A | 023, 024 |
| 026 | [026-batch-lane-observation-and-cutover.md](026-batch-lane-observation-and-cutover.md) | Batch レーンの観測と段階切替 | Codex B | 023, 025 |
| 027 | [027-fixed-lane-draft-mvp.md](027-fixed-lane-draft-mvp.md) | 固定版レーン MVP の Draft 作成経路を実装 | Codex A | 011, 014, 019 |

---

## TODOの完了マーク方法

ファイルをエディタで開いて `【】` を `【×】` に書き換える。

```bash
# 例：003のTODOをひとつ完了にする
sed -i 's/【】`src\/wp_client.py` を作成/【×】`src\/wp_client.py` を作成/' doc/003-wp-client.md
```

## 各チケットの未完了TODOを確認

```bash
grep '【】' doc/001-project-foundation.md
grep '【】' doc/003-wp-client.md
# 全チケット一括
grep -rn '【】' doc/
```

## 全体の進捗確認

```bash
for f in doc/0*.md; do
  total=$(grep -c '【】\|【×】' "$f" 2>/dev/null || echo 0)
  done=$(grep -c '【×】' "$f" 2>/dev/null || echo 0)
  echo "$(basename $f): $done / $total 完了"
done
```

## 追加在庫(2026-04-21)

- 017〜022 は会議室側で補充した次在庫
- のもとけ型の運用ルール
  - カテゴリは粗く
  - タグは細かく
  - 1試合から複数の再訪理由を作る
  - 一軍試合 / 公示・故障・昇降格 / 二軍・若手の 3 ループ
  に寄せている
- Claude Code はこれらを queue 在庫として管理し、依存が解けたら user 指示待ちに戻らず順次 fire する
- 027 は固定版レーン MVP の Draft 作成経路。Draft が積みあがらない根本原因への対応として追加。

## Batch API 在庫(2026-04-21)

- 023〜026 は Gemini 2.5 Flash Batch API を固定版レーンへ補助導入するための在庫
- 対象は固定版レーンだけ
- AIエージェント版レーン、mail 設定、既存 automation は触らない
- 初期は `Batch 補助レーン` として扱い、既存同期パイプラインを消さない
