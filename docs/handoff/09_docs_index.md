# 重要docs一覧

## このdocs/handoff/配下以外の重要ファイル

| ファイル | 内容 | 使うとき |
|---------|------|---------|
| [docs/daily_logs/2026-04-17.md](../daily_logs/2026-04-17.md) | 2026-04-17の詳細作業ログ | 4/17の経緯を詳細に追いたいとき |
| [docs/phase_c_runbook.md](../phase_c_runbook.md) | Phase C運用手順書（本番操作の正） | publish解放/X投稿解放/緊急止血 |
| [docs/acceptance_test_checklist.md](../acceptance_test_checklist.md) | 受け入れ試験チェックリスト | 各subtypeの受け入れ試験時 |
| [docs/operation_logs.md](../operation_logs.md) | Cloud Loggingクエリ集 | ログ確認コマンドを探すとき |
| [docs/phase_3_step1_setup.md](../phase_3_step1_setup.md) | メール通知セットアップ手順 | Gmail app passwordの再設定など |
| [docs/roadmap.md](../roadmap.md) | Phase D〜Fロードマップ | 中長期の計画を確認するとき |
| [AGENTS.md](../../AGENTS.md) | Codex向け設計書（全体設計の正） | Codexへの指示書を書くとき |

## ルートの重要ファイル

| ファイル | 内容 | 使うとき |
|---------|------|---------|
| [README.md](../../README.md) | プロジェクト概要 | 初めてこのrepoを見るとき |
| [HOW-TO.md](../../HOW-TO.md) | コマンド手順書 | デプロイ・テスト等のコマンドを確認するとき |
| [.env.example](../../.env.example) | 環境変数テンプレート（秘密情報なし） | env変数の全量を確認するとき |

## src/配下の主要ファイル

| ファイル | 内容 |
|---------|------|
| `src/rss_fetcher.py` | メインのRSS取得〜WP下書き生成フロー |
| `src/wp_client.py` | WordPress REST APIクライアント |
| `src/x_post_generator.py` | X投稿文面生成 |
| `src/x_api_client.py` | X API連携 |
| `src/acceptance_fact_check.py` | 受け入れ事実チェックCLI |

## テスト

```bash
# 全テスト実行
python -m pytest --tb=short -q

# 特定ファイル
python -m pytest tests/test_rss_fetcher.py -v

# 特定テスト
python -m pytest tests/ -k "test_postgame" -v
```

## Cloud Loggingの基本クエリ

詳細は [docs/operation_logs.md](../operation_logs.md) を参照。

```bash
# 直近の実行サマリ
gcloud logging read \
  'resource.type="cloud_run_revision" AND jsonPayload.event="rss_fetcher_run_summary"' \
  --project baseballsite --limit=5 --format=json

# publish状況
gcloud logging read \
  'resource.type="cloud_run_revision" AND jsonPayload.event="publish_disabled_for_subtype"' \
  --project baseballsite --limit=20 --format=json

# fact checkメール送信確認
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"fact_check_email_"' \
  --project baseballsite --limit=20
```
