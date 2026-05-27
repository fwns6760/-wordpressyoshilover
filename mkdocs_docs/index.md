# :material-baseball: ヨシラバー仕様書

巨人 (読売ジャイアンツ) 特化 WordPress 自動運営 yoshilover の仕様書です。

!!! info "この site の方針"

    - 推測は書かない、 ==証拠 (grep / git / gcloud)== だけ
    - 最新仕様だけ書く、 過去の経緯は書かない
    - active ticket 状態はミラーしない (一次 source は GitHub Issues と `doc/`)

## :material-book-open-page-variant: 仕様 (Spec)

各サブシステムの仕様。

<div class="grid cards" markdown>

-   :material-pipe:{ .lg .middle } **[記事生成パイプライン](spec/article-pipeline.md)**

    ---

    RSS / 公式 source → 関連度判定 → subtype 分類 → 本文 / タイトル組み立て → WP 下書き作成 → guarded-publish

-   :material-email-fast:{ .lg .middle } **[通知メール (publish-notice)](spec/publish-notice.md)**

    ---

    記事 1 件ごとに届く通知メール。 件名 prefix の決まり方、 HTML body の構成、 dedup 仕様

-   :material-twitter:{ .lg .middle } **[X 投稿候補メール (x-post-mail)](spec/x-post-mail.md)**

    ---

    X 投稿候補をまとめたメール。 5 種類の候補、 画像生成、 share-x ボタン経路

-   :material-chart-bar:{ .lg .middle } **[データ記事 (data-insight)](spec/data-insight.md)**

    ---

    数字が際立った瞬間を自動記事化。 whitelist / 閾値 / 期間軸

-   :material-image-frame:{ .lg .middle } **[アイキャッチ (featured_media)](spec/eyecatch.md)**

    ---

    WP 記事のサムネイル決定ルール (3 段 fallback)

-   :material-email-multiple:{ .lg .middle } **[メール lane の住み分け](spec/mail-lanes.md)**

    ---

    どの lane がどの責務か、 件名 prefix のマトリクス

-   :rocket:{ .lg .middle } **[X インプ向上プラン (新規計画)](spec/x-impression-plan.md)**

    ---

    X (旧 Twitter) のインプレッション向上のための 12 施策プラン、 既存仕組み + 新規案 + 優先順位

</div>

## :material-wrench: 運用 (Operations)

deploy / env / scheduler / 運用ルール。

<div class="grid cards" markdown>

-   :material-account-group:{ .lg .middle } **[運用ルール](operations/policy.md)**

    ---

    user / Claude Code / Codex の役割分担、 報告フォーマット、 hard stop

-   :material-rocket-launch:{ .lg .middle } **[Deploy 手順](operations/deploy.md)**

    ---

    image / service or job 一覧、 build → deploy → verify、 rollback

-   :material-cog-outline:{ .lg .middle } **[Env / フィーチャーフラグ](operations/env-flags.md)**

    ---

    各 service / job の env 実値 (production 値)

-   :material-clock-time-eight:{ .lg .middle } **[Cloud Scheduler 一覧](operations/scheduler.md)**

    ---

    cron 全リスト + lane 別グループ

-   :material-monitor-dashboard:{ .lg .middle } **[Local Preview](operations/local-preview.md)**

    ---

    この mkdocs site のローカル起動 / systemd 常駐

</div>

## :material-folder-multiple: 既存 doc との関係

| 場所 | 用途 |
| --- | --- |
| `CLAUDE.md` | Claude Code の恒久行動規範 |
| `AGENTS.md` | Codex / 他 agent 用の恒久制約 |
| `doc/README.md` | チケット priority board (詳細) |
| `doc/active/assignments.md` | 1 page dashboard |
| `docs/handoff/master_backlog.md` | 現在地 / release readiness |
| `docs/handoff/session_logs/` | session ごとの記録 |
| `mkdocs_docs/` (この site) | 安定した仕様 doc |

この site は active ticket state を写さない。 一次 source は GitHub Issues と `doc/` 側。
