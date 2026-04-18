# 2日間の作業履歴

詳細な日次ログ: [docs/daily_logs/2026-04-17.md](../daily_logs/2026-04-17.md)

## 2026-04-16: Phase A/B/B.5完了まで

### Phase A完了
- `RUN_DRAFT_ONLY` フラグ制御実装
- `PUBLISH_REQUIRE_IMAGE` で画像なし公開ブロック
- smoke test強化

### Phase B本丸（6カテゴリ専用本文型）実装
- `postgame` / `lineup` / `manager` / `notice` / `pregame` / `recovery` の専用本文生成
- 各カテゴリに対応したoEmbed引用構造

### Phase B.5（マスコミ/公式X引用4パターン）実装
- `media_quote` / `official_x` / `player_x` / `fan_reaction` の4パターン
- B.5観察ログ: `media_xpost_evaluated` / `media_xpost_skipped` / `media_xpost_embedded`

### 到達revision
`yoshilover-fetcher-00116-ztl`（Phase B.5完了時点）

---

## 2026-04-17: 13 revision（事故対応からPhase C準備まで）

詳細は [docs/daily_logs/2026-04-17.md](../daily_logs/2026-04-17.md)

### 朝（観察フェーズ初日）
- revision `00115-sqd` で観察開始
- title collision残存
- featured_media欠落残存
- Phase B.5の非発動理由が見えにくかった

### 事故発生（revision 00117-kes付近）
- 新規Claudeチャットから誤って `RUN_DRAFT_ONLY=0` を設定
- 結果: 4記事がpublishされた（意図しない公開）
- 止血: 4記事をdraftに戻す、`RUN_DRAFT_ONLY=1` に戻す
- 再発防止: 「env変更は既存Claudeチャット経由」ルール確立

### 各revisionの主な改善
| revision | 主な内容 |
|---------|---------|
| 00117-kes | smoke test強化、`run_started` ログ追加 |
| 00118-94p | title collision修正（rewrite多様化） |
| 00119-zzn | featured_media fallback/再利用補強 |
| 00120-4p8 | Phase B.5観察ログ強化 |
| 00121-xcx | X文面にsubtype専用分岐追加 |
| 00122-v8z | Phase B.5/280字/AIテスト強化 |
| 00123-zk7 | Gemini preview本番観察モード有効化 |
| 00124-nvr | `ENABLE_X_POST_FOR_LIVE_UPDATE=0` 追加 |
| 00125-dmq | カテゴリ別publish/X投稿フラグ20個実装 |
| 00126-fqd | Phase C観察ログ強化 |
| 00127-98x | 🔴live_update→general漏れ修正、featured_media観測修正 |

### docs仕上げ
- `docs/operation_logs.md` クエリ集追加
- `docs/phase_c_runbook.md` 運用向け補強
- `docs/acceptance_test_checklist.md` 新規作成
- `docs/roadmap.md` 新規作成

### X休眠明け復活活動（夕方）
- 泉口・大城・ダルベック・勝利ポストなどの試合当日Xポスト
- @yoshilover6760のエンゲージメント再開を確認

### のもとけ戦略深掘り（夜）
- dnomotoke.comの1,642ページ発見（想定より少ない）
- 選別的インデックス仮説の立案
- 「巨人版もページ数より品質密度を狙う」方針確定

---

## 2026-04-17深夜: acceptance fact check CLI実装

- `python3 -m src.acceptance_fact_check` CLIを実装
- `--category` / `--post-id` / `--limit` オプション
- 事実差分チェック（タイトル・本文・引用の整合性）

---

## 2026-04-18朝: メール通知稼働開始

- Gmail app password問題（secret projectの違い）を解決
- `GMAIL_APP_PASSWORD_SECRET_NAME` で秘密名前を柔軟化
- 実メール送信成功確認（`fact_check_email_sent` ログ確認）
- Scheduler job `fact-check-morning-report` が稼働開始
- revision `yoshilover-fetcher-00130-nxg` で安定

### Phase 3段階1の達成
- スマホで `【ヨシラバー】MM/DD 事実チェック結果` が届く状態
- `🔴` 記事がWP直リンク付きで優先表示
- これで「毎朝スマホ確認→WP管理画面」の動線が完成
