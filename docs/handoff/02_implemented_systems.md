# 実装済みシステム全量

## インフラ基盤

| コンポーネント | 詳細 |
|-------------|------|
| Cloud Run | `yoshilover-fetcher` (asia-northeast1), min-instances=0 |
| Cloud Scheduler | 1日4回 RSS発火 + 1日4回 fact check通知 |
| Secret Manager | WP認証/X API/Gmail appパスワード/RUN_SECRET |
| Artifact Registry | Dockerイメージ |
| GitHub Actions | push → Docker build → AR push → Cloud Run deploy |
| SSH deploy key | `~/.ssh/id_ed25519_yoshilover` (write access ON) |

## Phase A: draft品質担保

- `RUN_DRAFT_ONLY` フラグ制御（1=draft専用、0=publish可能）
- `PUBLISH_REQUIRE_IMAGE=1` で画像なし記事の公開ブロック
- smoke test強化: `RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` を deploy後必須確認
- `run_started` 構造化ログ

## Phase B本丸: 6カテゴリ本文型

以下のsubtypeに専用本文生成ロジックを実装済み:

| subtype | 内容 |
|---------|------|
| `postgame` | 試合後記事（スコア/本塁打/投手情報を構造化） |
| `lineup` | スタメン速報（打順・投手を表形式で） |
| `manager` | 監督コメント/采配記事 |
| `notice` | 公示（昇格/降格/入団/引退） |
| `pregame` | 試合前展望 |
| `recovery` | 故障・復帰情報 |

残りのsubtype（`farm`, `social`, `player`, `general`, `game_note`, `roster`）はfallback型。

## Phase B.5: マスコミ/公式X引用4パターン

以下の引用パターンを実装:

| パターン | 内容 |
|---------|------|
| `media_quote` | スポーツ紙記者のX引用 |
| `official_x` | 球団公式Xの引用 |
| `player_x` | 選手本人Xの引用 |
| `fan_reaction` | ファン反応Xの引用（上限: `FAN_REACTION_LIMIT=7`） |

Phase B.5の観察ログ:
- `media_xpost_evaluated`: 評価対象になったか
- `media_xpost_skipped`: スキップ理由
- `media_xpost_embedded`: 埋め込み成功

## Phase C準備: 段階制御機構

カテゴリ別の独立したON/OFFフラグ（全20個）:

**publish制御（10個）:**
```
ENABLE_PUBLISH_FOR_POSTGAME
ENABLE_PUBLISH_FOR_LINEUP
ENABLE_PUBLISH_FOR_MANAGER
ENABLE_PUBLISH_FOR_NOTICE
ENABLE_PUBLISH_FOR_PREGAME
ENABLE_PUBLISH_FOR_RECOVERY
ENABLE_PUBLISH_FOR_FARM
ENABLE_PUBLISH_FOR_SOCIAL
ENABLE_PUBLISH_FOR_PLAYER
ENABLE_PUBLISH_FOR_GENERAL
```

**X投稿制御（10個）:**
```
ENABLE_X_POST_FOR_POSTGAME
ENABLE_X_POST_FOR_LINEUP
ENABLE_X_POST_FOR_MANAGER
ENABLE_X_POST_FOR_NOTICE
ENABLE_X_POST_FOR_PREGAME
ENABLE_X_POST_FOR_RECOVERY
ENABLE_X_POST_FOR_FARM
ENABLE_X_POST_FOR_SOCIAL
ENABLE_X_POST_FOR_PLAYER
ENABLE_X_POST_FOR_GENERAL
```

**live_update専用制御:**
```
ENABLE_PUBLISH_FOR_LIVE_UPDATE=0  （常時0）
ENABLE_X_POST_FOR_LIVE_UPDATE=0   （常時0）
```

## Phase 3 段階1: スマホ通知（fact check メール）

- エンドポイント: `GET /fact_check_notify?since=yesterday`
- Scheduler job: `fact-check-morning-report`
- 発火時刻: `7:00 / 12:00 / 17:00 / 22:00 JST`
- 通知先: `FACT_CHECK_EMAIL_TO=fwns6760@gmail.com`
- メール件名: `【ヨシラバー】MM/DD 事実チェック結果（🔴X / 🟡Y / ✅Z）`
- `🔴` 最優先、WP直リンク付き、スマホ最適化フォーマット

## CLI ツール

```bash
# acceptance fact check（ローカル確認）
python3 -m src.acceptance_fact_check --category postgame --limit 10
python3 -m src.acceptance_fact_check --post-id 62538

# smoke test
bash scripts/cloud_run_smoke_test.sh
```

## observabilityイベント全量

### run系
- `run_started` — 実行開始
- `rss_fetcher_run_summary` — 実行サマリ
- `rss_fetcher_flow_summary` — フロー別サマリ（publish_skip_reason_counts, x_skip_reason_counts）

### publish系
- `publish_disabled_for_subtype` — カテゴリフラグ=0でスキップ
- `live_update_publish_disabled` — live_update専用スキップ

### 画像系
- `article_image_refetched` — 画像再取得
- `featured_image_fallback_applied` — fallback画像適用
- `featured_media_reused_from_existing_post` — 既存postから画像再利用
- `featured_media_observation_missing` — draft-only中の画像欠落観測

### X投稿系
- `x_post_ai_generated` — AI生成X文面
- `x_post_ai_failed` — AI生成失敗
- `x_post_subtype_skipped` — subtypeフラグ=0でスキップ

### Phase B.5系
- `media_xpost_evaluated`
- `media_xpost_skipped`
- `media_xpost_embedded`

### fact check系
- `fact_check_email_sent` — メール送信成功
- `fact_check_email_failed` — 送信失敗
- `fact_check_email_demo` — デモモード（app password未設定）
