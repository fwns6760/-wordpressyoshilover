# AGENTS.md — ヨシラバー サイトリニューアル 設計書

> 重要: この repo は **実装 repo**。役割定義の正本は `/home/fwns6/code/baseballwordpress/AGENTS.md`、`/home/fwns6/code/baseballwordpress/CLAUDE.md`、`/home/fwns6/code/baseballwordpress/docs/handoff/current_focus.md` です。
> このファイル単独で Claude Code / Codex の役割や current state を判断しないでください。
> このファイル内の古い計画文と現在の体制が食い違う場合は、`/home/fwns6/code/baseballwordpress/CLAUDE.md`、`/home/fwns6/code/baseballwordpress/docs/handoff/agent_operating_model.md`、`/home/fwns6/code/baseballwordpress/docs/handoff/current_focus.md` を正とする。
> 現在の正しい役割分担は **Codex = 実装 / テスト / 必要時 deploy**、**Claude Code = 監査 / queue / 起票 / read-only 観測** である。
> **runtime trigger の親は役割文ではなく `automation.toml` / scheduler 定義で確認する。**

## 実装 Codex の運用ルール(2026-04-26 lock)

- **実装前に `doc/102-ticket-index-and-priority-board.md` を確認する**(現行 dispatch board)
- assigned ticket の **write_scope / acceptance / 不可触**を守る
- **102 範囲外の ticket を勝手に実装しない**(他 ticket は Claude が次便として fire する)
- **`git push` 禁止**(commit までで終わる、push は Claude が外部から実行)
- **`git add -A` 禁止**(明示 path のみ stage)
- front / log / env / secrets / `.env` / Cloud Run env / `RUN_DRAFT_ONLY` flip は **絶対に巻き込まない**
- X / SNS POST / X API call も禁止(本 repo の Codex は WP write までで止まる、X 系は別 lane = PUB-005)
- `.git/index.lock` 衝突時は plumbing 3 段 fallback(`git write-tree` / `git commit-tree` / `git update-ref`)
- 本 repo の Codex 2 lane(A / B)分担は 102 board の `lane` 列で確認
- **Ticket archive rule**(2026-04-26 PM 第 5 次 final): status 変更時、同 commit で folder mv:
  - READY / IN_FLIGHT / REVIEW_NEEDED → `doc/active/`
  - BLOCKED_USER / BLOCKED_EXTERNAL / PARKED → `doc/waiting/`
  - CLOSED → `doc/done/YYYY-MM/`
  - doc/ root = `doc/README.md`(旧 102 board)のみ
  - 優先度はフォルダでなく README の `priority` / `next_action` で判別
- **assignments.md 常時 maintain**(2026-04-26 PM lock): `doc/active/assignments.md` を ticket × 担当者 matrix の **単一 visible 状態 file** として維持。ticket fire / accept / status 変更 / commit のたびに **同 commit で更新**(または直後に doc-only 更新 commit)。user が 1 page で「誰が何やる / 何待ち / 何完了」を即把握できる single source として運用。README(詳細台帳)+ assignments.md(概要 dashboard)の両建て。

> Claude Code 用設計書。PDF「サイトリニューアル要件定義書兼設計書 v1.0 MVP」(2026-04-08) の内容をエージェントが読める形式に変換。

---

## Git Push 環境（Codex用、2026-04-17確立）

- origin URL: `git@github-yoshilover:fwns6760/-wordpressyoshilover.git`
- SSH鍵: `~/.ssh/id_ed25519_yoshilover`（パスフレーズなし）
- GitHub deploy key ID: `148826814`（write access ON）
- `ssh-agent` 不要。agent 空で `git fetch` / `git push` 動作確認済み

### セッション復帰時の確認コマンド

```bash
ssh -T git@github-yoshilover
# "Hi fwns6760/-wordpressyoshilover!" が出れば正常
```

### トラブルシューティング

- `Permission denied` が出たら、まず `gh api repos/fwns6760/-wordpressyoshilover/keys` で deploy key の存在と `read_only: false` を確認する
- deploy key が存在しなければ、`cat ~/.ssh/id_ed25519_yoshilover.pub` の公開鍵を GitHub deploy key として再登録する
- 旧鍵 `~/.ssh/id_ed25519`（パスフレーズ保護）は通常運用では使わない

---

## 設計思想：のもとけモデルを1人＋AIで再現する

dnomotoke.com（中日ドラゴンズまとめ）は2〜3人のチームで以下を運営している：

| のもとけの仕組み | このプロジェクトでの対応 |
|----------------|----------------------|
| スポーツ紙ニュースをRSSで自動収集 | フェーズ③ `rss_fetcher.py` で完全自動化 |
| Xポスト埋め込みが記事の核コンテンツ | フェーズ② `wp_draft_creator.py` でoEmbed下書き自動生成 |
| 試合中スコア変化を自動ツイート | フェーズ⑤ `x_api_client.py` で自動投稿 |
| Xポスト文面を自動生成して投稿 | フェーズ④⑤ `x_post_generator.py` + X API |
| コメント欄でファンのたまり場 | MVP後にwpDiscuzで対応（Phase 6以降） |

**ゴール：AI＋自動化スクリプトで1人で同等の運用を実現する。**

### 人間がやることを最小化する設計

```
【毎朝の作業（5〜10分）】
1. WP管理画面を開く
2. 自動生成された下書き一覧を確認
3. 各下書きに一言コメントを追加（オリジナリティ・差別化）
4. 公開ボタンを押す
5. x_post_generator.py の出力をコピーしてXに投稿

【完全自動（人間不要）】
- RSS取得 → キーワードフィルタ → カテゴリ分類 → WP下書き生成（Cron 1日4回）
- フェーズ⑤以降：WP公開 → X自動投稿（x_api_client.py）
```

### GitHub運用ルール

- このリポジトリの開発作業は、原則として `変更 -> テスト -> git commit -> git push` までを1セットで完了扱いにする。
- 「修正だけしてpushしない」は例外扱いとし、ユーザーが明示的に止めた場合を除き、作業完了時はGitHubへ反映する。
- GitHub接続はHTTPSではなくSSHを標準とする。
- このリポジトリの通常運用は deploy key `~/.ssh/id_ed25519_yoshilover` を使う。origin は `git@github-yoshilover:fwns6760/-wordpressyoshilover.git` を維持する。
- origin の repo 名 `-wordpressyoshilover` は typo ではなく **GitHub 上の実 repo 名**。`github-yoshilover` は SSH host alias であり、repo 名ではない。
- deploy key は GitHub deploy key ID `148826814` に対応し、write access を有効化済み。
- `ssh-agent` は必須ではない。agent が空でも `git fetch` / `git push` が通ることを確認済み。
- 旧鍵 `~/.ssh/id_ed25519` は通常運用では使わない。deploy key 障害時の一時退避経路としてのみ扱う。
- `.github/workflows/*` を含む変更は、現在の push 経路だと GitHub 側で `workflow` scope 不足により reject されることがある。通常修正と workflow 変更は分けて扱う。

---

## 開発者向けセッション復帰メモ（2026-04-18 追記）

### 役割分担（2026-04-19 更新、4 者体制）

- **Codex**: 開発専任。実装、テスト、Cloud Run / Scheduler 反映、必要な docs 更新、`git commit` / `git push`
- **Claude Code**: 監査、queue 管理、依頼書 / inline prompt 起票、docs/handoff 配下ドキュメント整備
- **ChatGPT**: 相談役。方針の壁打ち、判断材料の整理、第三者レビュー
- **user（よしひろさん）**: 最終の `go / stop / publish / hold` 判断
- **Codex は開発専任**: `docs/handoff/codex_requests/*.md` の起票はしない。依頼書案・方針案・spec も書かない（独断起票は revert 対象、2026-04-19 実例あり）
- **Codex は `CLAUDE.md` を編集しない**: 監査運用や Gemini 向け指示であっても `CLAUDE.md` は対象外

### Codex 依頼の形式（2026-04-19 更新）

依頼は 2 形式、毎回 formal file を作る義務はない:

1. **inline prompt（既定）**: Claude Code が次便 prompt を確定し、`go` が出たら Claude Code から Codex へ進める。チケット管理は `master_backlog.md` の 【】 → 【×】 で一元化
2. **formal 依頼書 file（必要時のみ）**: `docs/handoff/codex_requests/YYYY-MM-DD_NN.md`。長大 prompt / 大型調査 / handoff 固定が必要な場合のみ
- **Gemini CLI 向けの運用指示は `AGENTS.md` に書く**: `CLAUDE.md` には Gemini 用の待機/代行ルールを書かない
- **Gemini CLI の監査代行ルール**: Claude Code が停止した場合のみ起動し、監査・事実確認だけを行う。コード修正、deploy、env変更、Scheduler変更、`git commit`、`git push` はしない

### セッション再開時に最初に読むファイル（2026-04-19 更新）

1. `docs/handoff/master_backlog.md`（release 総作業表、単一ソース）
2. `docs/handoff/decision_log.md`（過去判断の追跡）
3. `docs/daily_ops_checklist.md`（朝/昼/夜の見るもの）
4. `docs/handoff/tickets/OPEN.md`（bug 台帳、release backlog ではない）
5. `docs/handoff/tickets/RESOLVED.md`（解決済アーカイブ）
6. `docs/handoff/codex_responses/2026-04-18_35.md`（`/audit_notify` 実装）

旧 Phase C 前提の `08_next_steps.md` は master_backlog への誘導スタブ化済み。Phase C 3 段階は `PHASE-C-RUNBOOK.md` に保全。

### セッション再開時の確認コマンド

```bash
cd /home/fwns6/code/wordpressyoshilover
git status --short
gcloud run services describe yoshilover-fetcher --project baseballsite --region asia-northeast1
gcloud scheduler jobs list --project baseballsite --location asia-northeast1
python3 -m unittest discover -s tests
```

### 作業ツリーの注意

- `git add -A` / `git add .` は原則禁止。`.codex` と `data/` は untracked のまま残っている前提で扱う。
- セッション切断直後は `git status --short` で **想定外 modified** がないか先に確認する。
- `docs/handoff/tickets/OPEN.md` は Claude Code 側で未コミット差分を持っていることがある。勝手に整形しない。

### 現在の運用事実（2026-04-18 夜時点）

- Cloud Run service は `yoshilover-fetcher`、project は `baseballsite`、region は `asia-northeast1`
- 既存の定期実行は GCP 側で運用しており、`fact-check-morning-report` は Cloud Scheduler job
- `fact-check-morning-report` は `0 * * * *` / `Asia/Tokyo` / `GET /fact_check_notify?since=yesterday`
- 既存 HTTP 認証の共通 env は `RUN_SECRET`。header は `X-Secret`
- 既存メール送信 util は `src/fact_check_notifier.py` の `send_email(...)`
- Gmail app password は `GMAIL_APP_PASSWORD_SECRET_NAME=yoshilover-gmail-app-password` を再利用する

### 記事品質改善の現在地

- **T-021 第1弾**: 関連記事ブロックは実装・deploy 済み
  - 実装: `src/rss_fetcher.py` の `_find_related_posts_for_article()` / `_build_related_posts_section()`
  - 本文には `<div class="yoshilover-related-posts">` が入る
- **T-021 第2弾**: `ARTICLE_INJECT_TEAM_STATS` の canary 検証まで実施
  - production revision は維持、canary tag は `canary-team-stats`
  - `article_team_stats_injected` ログは出たが、本文に stats block が出ないため promote 未実施
- **T-024 / 第35便予定**: `/audit_notify` は未実装
  - 既存 endpoint は `GET /health`、`GET /test-gemini`、`GET /fact_check_notify`、`POST /run` のみ
  - `thin_body` 用の「`<div class="yoshilover-related-posts">` を除外してコア本文の実文字数を返す helper」は **未実装**
  - 既存で流用できるのは `src/rss_fetcher.py` の `_strip_html()`、`src/acceptance_fact_check.py` の `_strip_html_text()`
  - T-024 spec 上の監査対象は `draft + publish`、window 既定は直近 60 分
  - `AUDIT_OPINION_USE_LLM` は Gemini Flash 想定、既定 OFF

### T-024 実装時の扱い

- `OPEN.md` に `repetition` 軸の記述があるが、戻り値 schema の `by_axis` には含まれていない。未確定仕様として扱う。
- 新しい監査 endpoint は `/fact_check_notify` 拡張ではなく、`/audit_notify` の **新設** を優先する。
- 新しい定期実行は `giants-*` job 群とは分離する。
- 2026-04-18 セッション時点の運用判断では、`/audit_notify` の cron 実行元は **Anthropic Remote Trigger ではなく GCP Cloud Scheduler** を優先する。

### 既知の地雷

- tag 付き canary URL への直接 `curl` は OIDC 制約で失敗しうる。第32便では一時 Cloud Scheduler job を作って smoke した。
- GitHub Actions は `pytest` ではなく `python -m unittest discover -s tests` ベース。pytest 専用 test を足すだけでは CI に乗らない。
- WP 取得は DB 直読ではなく REST API 経由。`src/wp_client.py` の `WPClient.list_posts()` / `get_post()` を使う。
- Cloud Run deploy で env を触る場合、`--set-env-vars` は既存 env を壊しうるので使わない。env 変更が必要な便だけ `--update-env-vars` を使い、deploy-only の便では env / Secret / Scheduler を変えない。

---

## プロジェクト概要

| 項目 | 内容 |
|------|------|
| サイト | yoshilover.com（読売ジャイアンツ特化ニュースまとめ） |
| 参考モデル | dnomotoke.com（中日ドラゴンズまとめ）の巨人版 |
| CMS | WordPress（稼働中） |
| テーマ | SWELL（インストール済み） |
| サーバー | エックスサーバー |
| SEOプラグイン | SEO SIMPLE PACK（SWELL推奨） |
| Xアカウント | @yoshilover6760（8,500+フォロワー） |
| X API | 従量課金（$5チャージ、フェーズ⑤で導入） |
| 開発言語 | Python 3.x |
| 核コンテンツ | Xポスト埋め込み |
| 現在の状況 | 既存記事をサブドメインへ301リダイレクト移行中 |

---

## 実装ロードマップ（5フェーズ）

**原則：小さく始めて順番に積む。各フェーズが安定してから次に進む。飛ばさない。**

| # | フェーズ | やること | 担当 |
|---|---------|---------|------|
| ① | SWELL＋カテゴリ固定 | テーマ切り替え、巨人カラー設定、カテゴリ作成、固定ページ作成 | 手動 |
| ② | WP下書き自動生成 | WP REST APIでXポストURL入りの下書き記事を自動生成するスクリプト | Codex |
| ③ | RSS取得＋自動分類 | スポーツ紙RSSから巨人記事を自動取得、キーワードでカテゴリ自動付与 | Codex |
| ④ | X文案生成 | 記事公開時のXポスト文面を自動生成（ハッシュタグ含む） | Codex |
| ⑤ | X API連携 | X API従量課金でポスト収集・自動投稿を接続 | Codex |

**MVP対象外（後回し）：** X APIでの自動収集、wpDiscuz、試合速報ウィジェット、LINE通知、AI要約、選手名鑑、AdSense

---

## ディレクトリ構成

```
yoshilover/               ← このリポジトリ
├── AGENTS.md             ← 本ファイル（設計書）
├── SESSION-LOG-2026-04-14.md ← 直近セッションの作業ログ・再開メモ
├── TASKS-0-prep.md       ← 事前準備タスク（手動）
├── TASKS-1-dev.md        ← 開発タスク（Codex）
├── TASKS-2-deploy.md     ← デプロイ・運用タスク
├── TASKS-3-prosports.md  ← prosportsサイド作業タスク
├── HOW-TO.md             ← コマンド手順書
├── .env.example          ← 環境変数テンプレート
├── .env                  ← 実際の認証情報（gitignore対象）
├── .gitignore
├── requirements.txt
├── config/
│   ├── categories.json   ← カテゴリ名とWP IDのマッピング
│   ├── rss_sources.json  ← RSSフィードURL一覧
│   └── keywords.json     ← カテゴリ自動分類キーワード
├── data/
│   ├── posted_urls.json  ← 投稿済みURL履歴（重複防止）
│   └── rss_history.json  ← RSS取得済み記事履歴
├── logs/
│   └── .gitkeep
└── src/
    ├── wp_client.py          ← WP REST API クライアント（共通）
    ├── wp_draft_creator.py   ← フェーズ②：下書き自動生成
    ├── rss_fetcher.py        ← フェーズ③：RSS取得＋自動分類
    ├── x_post_generator.py   ← フェーズ④：X文案生成
    └── x_api_client.py       ← フェーズ⑤：X API連携
```

---

## 環境変数（.env）

```dotenv
# WordPress
WP_URL=https://yoshilover.com
WP_USER=（管理者ユーザー名）
WP_APP_PASSWORD=（アプリケーションパスワード）

# X API（フェーズ⑤で追記）
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_CLIENT_ID=
X_CLIENT_SECRET=
```

---

## フェーズ① SWELL＋カテゴリ固定（手動作業）

### カラー設定

| 設定項目 | 値 |
|---------|---|
| メインカラー | `#F5811F`（ジャイアンツオレンジ） |
| テキストカラー | `#333333` |
| リンクカラー | `#003DA5`（ジャイアンツブルー） |
| 背景色 | `#F5F5F0` |
| ヘッダー背景 | `#1A1A1A`（ブラック） |
| ヘッダー下ボーダー | `#F5811F` 4px |

### カテゴリ（8種）

| カテゴリ | 色 | 内容 |
|---------|---|------|
| 試合速報 | `#F5811F` | 試合結果・スコア |
| 選手情報 | `#003DA5` | 個別選手ニュース |
| 首脳陣 | `#555555` | 監督・コーチ発言 |
| ドラフト・育成 | `#2E8B57` | ドラフト・ファーム |
| OB・解説者 | `#7B4DAA` | OB発言まとめ |
| 補強・移籍 | `#E53935` | FA・トレード |
| 球団情報 | `#F9A825` | イベント・グッズ |
| コラム | `#1A1A1A` | 独自分析記事 |

### 追加CSS

```css
/* ヘッダー下オレンジライン */
.l-header { border-bottom: 4px solid #F5811F; }

/* h2：黒背景＋オレンジ左線 */
.post_content h2 {
  background: #1A1A1A; color: #FFF;
  padding: 12px 16px; border-left: 6px solid #F5811F;
}

/* h3：オレンジ下線 */
.post_content h3 { border-bottom: 3px solid #F5811F; padding-bottom: 6px; }

/* フッター上オレンジライン */
.l-footer { border-top: 4px solid #F5811F; }

/* 記事一覧ホバー */
.-type-list .p-postList__item:hover {
  background: #FFF3E8; transition: background 0.2s;
}
```

---

## フェーズ② WP下書き自動生成

### スクリプト：`src/wp_draft_creator.py`

**入力：** XポストURLのリスト（テキストファイル or 引数）  
**出力：** WordPressに「下書き」記事を自動生成

**処理フロー：**
1. XポストURLを受け取る（`--url` 単体 or `--file` 複数）
2. oEmbed用ブロックHTMLを生成
   ```
   <!-- wp:embed {"url":"https://x.com/..."} -->
   <figure class="wp-block-embed">...</figure>
   <!-- /wp:embed -->
   ```
3. 記事タイトルを仮生成（URLから抽出 or `--title` で手動指定）
4. WP REST API（`POST /wp-json/wp/v2/posts`）で下書き投稿
   - `status: "draft"`
   - `content:` oEmbedブロック
   - `categories:` 指定があれば（`--category`）
5. 投稿後、`data/posted_urls.json` にURLを記録（重複防止）

**CLIオプション：**
```
python src/wp_draft_creator.py --url https://x.com/...
python src/wp_draft_creator.py --file urls.txt --category 試合速報
python src/wp_draft_creator.py --url https://x.com/... --title "巨人が開幕3連勝"
```

---

## フェーズ③ RSS取得＋自動分類

### スクリプト：`src/rss_fetcher.py`

**取得ソース：**

| ソース | 種別 | 備考 |
|--------|------|------|
| スポーツ報知（巨人） | RSS | 読売系、最速 |
| 日刊スポーツ（巨人） | RSS | 番記者取材が豊富 |
| スポニチ（巨人） | RSS | 選手コメント充実 |
| 東スポ（巨人） | RSS | 独自ネタ・話題性 |
| Yahoo!スポーツナビ | RSS | 各社記事の集約 |

**処理フロー：**
1. `config/rss_sources.json` からフィードURL一覧を読み込む
2. feedparser で各RSSフィードを取得
3. キーワードフィルタ（「巨人」「ジャイアンツ」「東京ドーム」等）
4. 重複チェック（`data/rss_history.json` で管理）
5. カテゴリ自動分類（`config/keywords.json` のルールでマッチ）
6. `wp_client.py` 経由でWP下書き生成
7. Cronで1日3〜4回定期実行

**自動分類ルール（`config/keywords.json`）：**

| キーワード | カテゴリ |
|-----------|---------|
| スコア, 勝, 敗, 打席, 登板, 先発 | 試合速報 |
| 個人名, 成績, 打率, 防御率 | 選手情報 |
| 監督, コーチ, 采配, 起用 | 首脳陣 |
| ドラフト, 育成, 2軍, ファーム | ドラフト・育成 |
| OB, 解説, 〇〇さん | OB・解説者 |
| FA, トレード, 移籍, 獲得, 外国人 | 補強・移籍 |
| チケット, グッズ, イベント, 東京ドーム | 球団情報 |

**著作権配慮：** 記事本文は取得しない。タイトル・URL・日時のみ使用。本文はオリジナルコメントを追記して差別化。

---

## フェーズ④ X文案生成

### スクリプト：`src/x_post_generator.py`

**入力：** 記事タイトル、カテゴリ、記事URL（または `--post-id` でWP REST APIから取得）  
**出力：** Xポスト用テキスト（stdout）

**処理フロー：**
1. 記事タイトルを取得
2. カテゴリに応じたハッシュタグを付与
3. 記事URLを整形
4. 140字以内に収める
5. stdoutに出力（コピペ用）

**ハッシュタグルール：**
```
必須：#巨人 #ジャイアンツ
任意：#プロ野球 #NPB #セリーグ
選手別：記事タイトルから選手名を検出して自動付与
```

**出力例：**
```
巨人、広島に3-2で勝利！ウィットリーが7回2失点の好投
https://yoshilover.com/archives/xxxxx
#巨人 #ジャイアンツ #プロ野球
```

**CLIオプション：**
```
python src/x_post_generator.py --title "タイトル" --url https://... --category 試合速報
python src/x_post_generator.py --post-id 123
```

---

## フェーズ⑤ X API連携

### スクリプト：`src/x_api_client.py`

**注意：フェーズ①〜④が安定稼働してから着手すること。**

**X API料金（従量課金・2026年4月時点）：**

| 操作 | 単価 | 月間想定 | 月間コスト |
|------|------|---------|----------|
| ポスト投稿（Create） | $0.01/件 | 300件 | $3（約450円） |
| ポスト読み取り（Read） | $0.005/件 | 1,500件 | $7.5（約1,100円） |
| **合計（想定）** | | | **約1,550円/月** |

初期チャージ：$5（約800円）。残高ゼロで自動停止（追加請求なし）。

**サブコマンド：**
```
python src/x_api_client.py post --post-id 123   # WP記事→X自動投稿
python src/x_api_client.py collect              # 巨人関連ポスト収集→WP下書き
```

**コスト節約ルール：**
- 読み取り（GET）は1日2〜3回に絞る
- 同一ポストの24時間以内の再取得はカウントされない
- `data/rss_history.json` で履歴管理し、API経由の重複チェックを避ける

---

## 共通ライブラリ：`src/wp_client.py`

全スクリプトから呼び出すWP REST APIクライアント。

**提供する関数：**
```python
create_draft(title, content, categories=None) -> post_id
get_post(post_id) -> dict
get_categories() -> list[dict]  # {id, name, slug}
```

**認証：** Basic認証（WPアプリケーションパスワード）

---

## 技術スタック

```
Python 3.x
requests        # WP REST API 呼び出し
python-dotenv   # 環境変数管理
feedparser      # RSS パース（フェーズ③）
tweepy          # X API クライアント（フェーズ⑤）
```

---

## エックスサーバーへのデプロイ手順

### 1. SSH接続設定

1. エックスサーバー管理画面 → SSH設定 → ONにする
2. ローカルでSSH鍵ペアを生成：
   ```bash
   ssh-keygen -t ed25519 -C "yoshilover"
   ```
3. エックスサーバー管理画面で公開鍵を登録
4. 接続テスト：
   ```bash
   ssh -p 10022 （ユーザー名）@（サーバー名）.xserver.jp
   ```

### 2. ファイルをアップロード

```bash
# SCPでプロジェクト一式を転送
scp -P 10022 -r ./yoshilover/ （ユーザー名）@（サーバー名）.xserver.jp:~/
```

### 3. サーバー上でセットアップ

```bash
# Python確認
python3 --version

# pip確認
pip3 --version

# 依存パッケージのインストール
cd ~/yoshilover
pip3 install --user -r requirements.txt

# .envを作成（.env.exampleをコピーして記入）
cp .env.example .env
nano .env

# logsディレクトリ作成
mkdir -p logs
```

### 4. 動作テスト

```bash
# WP REST API疎通テスト
python3 src/wp_client.py --test

# 下書き生成テスト（XポストURLで試す）
python3 src/wp_draft_creator.py --url https://x.com/yoshilover6760/status/XXXXX

# RSS取得テスト
python3 src/rss_fetcher.py --dry-run

# X文案生成テスト
python3 src/x_post_generator.py --title "テスト記事" --url https://yoshilover.com/ --category 試合速報
```

### 5. Cron設定

エックスサーバー管理画面 → Cron設定 から登録：

```cron
# RSS自動取得（1日4回：7時・11時・17時・21時）
0 7,11,17,21 * * * /usr/bin/python3 /home/（ユーザー名）/yoshilover/src/rss_fetcher.py >> /home/（ユーザー名）/yoshilover/logs/rss_fetcher.log 2>&1
```

---

## 運用ペース（段階拡大）

| 期間 | ペース | 内容 |
|------|--------|------|
| 初日 | 手動5記事 | wp_draft_creator.py で下書き生成→確認→公開 |
| 1週間 | 1日3〜5記事 | RSS自動取得＋手動確認＋公開フロー確立 |
| 2週間 | 1日5〜10記事 | フローが安定したら増量 |
| 1ヶ月 | フロー定着 | RSS自動取得＋手動確認＋公開が日課に |
| フェーズ⑤以降 | X API導入 | 自動投稿・ポスト収集を追加 |

---

## 注意事項・ルール

- **フェーズは順番に進める。飛ばさない。**
- **著作権**：記事本文は取得しない。タイトル・URL・日時のみ。本文はオリジナルコメントを追記する。
- **X APIコスト**：残高ゼロで自動停止するため追加請求は発生しない。初期$5チャージで始める。
- **REST APIが403の場合**：WP管理画面 → 設定 → パーマリンク → 「投稿名」に変更して保存で解決することが多い。
- **各カテゴリのWP IDのメモ**：`config/categories.json` に設定後、WP管理画面で実際のIDを確認して更新すること。
- **GitHub運用**：通常作業は `git commit` と `git push` まで含めて完了とする。接続はSSH固定、鍵は `~/.ssh/id_ed25519` を使う。

---

## 4 者運用モデルと公開較正モード（2026-04-19 恒久化）

### 役割分担（4 者）

- **Codex** = 開発実行のみ（実装 / test / deploy / WP REST PUT）
- **Claude Code** = 監査 / queue / 起票（仕様レベルで依頼、コードは書かない）
- **ChatGPT** = 相談役（Claude の判断に第三者レビューを挟む）
- **user** = 最終決裁（`go / stop / publish / hold` の 4 択）

### 既定モード: 公開較正

主 KPI は `publishable_rate` と `published_count`。`drafts_created` は補助指標。

原則:

1. 改善案の量産を前進と見なさない
2. 最優先 1 本の公開候補を出すことを優先する
3. 候補ゼロで返さない。優先 subtype (postgame / lineup) が 0 件でも、他 subtype から現時点で最も公開に近い 1 本を選ぶ
4. 公開候補は 4 項目で判定する
   - 事実の核が 1 つに見えるか
   - title-body の重心がズレていないか
   - 最低限のファン視点があるか
   - 素材メモ感が強すぎないか
5. 0〜1 個該当なら publish now、2 個なら patch then publish、3 個以上なら hold

### ChatGPT 相談フロー

1. ChatGPT 相談は毎回の標準フローに含める
2. Claude は毎回返答の最後に「ChatGPT相談用ブロック」を必ず付ける
3. ChatGPT 返答が戻るまで、新便は user の明示 go があるまで流さない
4. ChatGPT 相談待ち中は queue 更新は可、実行提案は 1 本に絞る

ChatGPT相談用ブロックの固定形式:

- 現在の結論候補: go / stop / publish / hold
- いま見ている対象: 便名 or post ID
- 事実 3 点
- 残リスク最大 2 点
- ChatGPT に聞きたいこと: 1 文
- あなたの推奨: 1 文

### user インターフェース

- user に求める返答は原則として go / stop / publish / hold の 4 択
- user に長文の説明や整理を求めない
- 本文全文を user に見せるのは publish 前のみ

### 暴走防止

- 1 バッチの範囲は以下 3 点までに固定する
  - read-only で現在の draft / publish 候補を観測
  - publish candidate を最大 3 本まで選別
  - 必要なら次の Codex 便を 1 本だけ提案
- 1 テーマ 1 便、同時に複数便を流さない
- 公開較正を 1 回見てから次便を決める

### Codex patch 便の事前 status チェック（2026-04-19 運用事故防止）

1. WP 記事に PUT/POST する Codex 便は、最初に WP REST GET で対象 post の status を確認
2. `status=draft` のときだけ通常 patch を続行
3. `status=publish` を検出したら即 stop、Claude に報告して user 判断を待つ
4. publish 記事を触るのは user が明示 go したときだけ
5. 事故経緯と運用ルールの詳細は `docs/handoff/session_logs/2026-04-19_mode_switch.md` を参照
