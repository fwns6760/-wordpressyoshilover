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
| 028 | [028-fixed-lane-intake-route-memo.md](028-fixed-lane-intake-route-memo.md) | fixed lane の intake / trust / route を 027 注入用に短く固定 | Codex A | 011, 014, 019 |
| 029 | [029-quality-progress-digest-formalization.md](029-quality-progress-digest-formalization.md) | quality-gmail の進捗4行と閾値を正式化 | Codex B | 015, 027 |
| 030 | [030-title-assembly-rule.md](030-title-assembly-rule.md) | title assembly のルール固定と subtype-aware 生成 | Codex B | 010, 011, 014, A4, B2 |
| 031 | [031-027-canary-success-gate.md](031-027-canary-success-gate.md) | 027 canary success 判定と証跡チェックリストを固定 | Claude Code | 027, 028 |
| 032 | [032-subtype-body-contract.md](032-subtype-body-contract.md) | 本文ブロック順の正規化と subtype 別 body contract 固定 | Codex B | 011, A4, B3, B4, B5, B6, B7, B8, 030 |
| 033 | [033-postgame-fact-kernel-hardening.md](033-postgame-fact-kernel-hardening.md) | postgame の fact kernel を hardening する | Codex B | 011, B3, 032 |
| 034 | [034-official-x-attribution-rule.md](034-official-x-attribution-rule.md) | 公式 X / 公式媒体 X の attribution 付与ルールを正式化 | Codex B | 014, B8, 032 |
| 035 | [035-close-marker-formalization.md](035-close-marker-formalization.md) | close_marker 判定を条件付き reserve として正式化 | Codex B | 032, 033, 034 |
| 036 | [036-gemini25flash-fixed-lane-prompt-hardening.md](036-gemini25flash-fixed-lane-prompt-hardening.md) | Gemini 2.5 Flash 固定版レーン prompt contract hardening | Codex B | 030, 032, 033, 034 |
| 037 | [037-pickup-parity-expansion.md](037-pickup-parity-expansion.md) | pickup parity expansion と deferred_pickup route outcome | Codex A | 014, 023, 027, 028, 011, 019 |
| 038 | [038-article-quality-ledger-and-template-promotion.md](038-article-quality-ledger-and-template-promotion.md) | 記事品質 ledger と template / prompt promotion loop 正式化 | Claude Code | 015, 036 accepted |
| 039 | [039-quality-gmail-delivery-reliability.md](039-quality-gmail-delivery-reliability.md) | quality-gmail cron delivery reliability の切り分けと復旧 | Claude Code | 015, 現行 quality-gmail automation |
| 040 | [040-codex-repair-playbook.md](040-codex-repair-playbook.md) | Codex repair playbook(記事をどう直すかの正式ルール) | Codex B | 030, 032, 033, 034, 036 accepted |
| 042 | [042-local-runtime-reboot-recovery.md](042-local-runtime-reboot-recovery.md) | local runtime の reboot 監査と復旧手順固定 | Claude Code | 039, 現行 Codex automations |
| 041 | [041-structured-eyecatch-fallback.md](041-structured-eyecatch-fallback.md) | 画像無し記事の structured eyecatch fallback を正式化 | Codex A | 027, 037, 019 |
| 043 | [043-local-runtime-auto-recovery.md](043-local-runtime-auto-recovery.md) | local runtime の再起動後 auto recovery を正式化 | Claude Code | 042, 現行 Codex automations |
| 044 | [044-codex-startup-registration-and-reboot-smoke.md](044-codex-startup-registration-and-reboot-smoke.md) | Codex app startup 登録と reboot smoke 確認 | Claude Code | 039, 042, 043, 現行 Codex automations |
| 045 | [045-non-npb-collector-wiring.md](045-non-npb-collector-wiring.md) | non-NPB collector wiring を 037 intake に接続する | Codex A | 028 impl accepted, 037 accepted, 038 active |

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
- 028 は `027` に注入するための短メモ ticket。`collect wide / assert narrow`、4 family、`candidate_key`、`route outcome`、`読売ジャイアンツ` 親カテゴリ維持を固定する。
- 029 は `quality-gmail` を進捗報告に正式化する ticket。`027 canary success` 後に fire する。
- 030〜035 は DNS blocker と独立に前進する品質本線 / gate 在庫。
- 固定 fire 順は `031 -> 030 -> 032 -> 033 -> 034`(全着地済)。
- 027 canary は success 扱いで反映済(Draft 63175 / wp_post_dry_run=pass / duplicate_skip 再実行で観測)。
- `029` は 027 canary success で unblock、READY。
- `035` は `030〜034` 実施後も close_marker 系 fail が残った時だけ fire する dormant ticket。
- 036 は Gemini 2.5 Flash 固定版レーン prompt contract hardening。validator 着地済を前提に、初稿側で fail を減らし Codex repair を minimum-diff に寄せる。
- 037 は fixed lane runner の pickup parity expansion。028 の 4 family create path を維持したまま、pickup 層へ 5 parity family・10 source_kind・`deferred_pickup` を追加する。
- 038 は Claude Code 管理の運用 ticket。Draft ごとに品質 ledger を残し、再発 fail だけを 036 / 037 / 035 に昇格させる loop を固定する。
- 039 は Claude Code 管理の delivery 切り分け系 ticket。quality-gmail の cron fire → log read → mail send → 着信の 4 段階で delivery reliability を管理する。029(4 行の意味固定)とは独立で、本線 fire 順を止めない。
- 040 は Codex B の repair playbook。036 minimum-diff rubric を repair 手順として固定し、038 ledger の `repair_closed / escalated / accept_draft` と 1 対 1 で対応させる。fixed / agent 両 lane で同じ playbook を適用。
- 042 は Claude Code 管理の runtime 監査 ticket。reboot で止まる local automation と、Codex / Claude を再起動した時に何が戻るかを固定する。quality-gmail を含む local cron の復旧手順を明記し、次 tick 再開を前提にする。
- 041 は Codex A の補助 ticket。画像無し記事で共通 no-image を出さず、subtype ごとの情報から structured eyecatch を自動で組む(番組情報 / 公示 / 予告先発 / コメント / 怪我状況 / 試合結果 の 6 layout)。027 / 037 / 019 にぶら下がる補助で、本線 fire 順を止めない。
- 043 は Claude Code 管理の auto recovery 設計 ticket。042(手動復旧)を継承し、follow-up を `Codex app を Windows スタートアップフォルダへ配置する` 1 本に絞る。自動ログイン / Claude auto-start / missed run 自動補填は非対象。
- 044 は Claude Code 管理の 043 follow-up 実施 ticket。Codex app スタートアップ配置(user 手動 1 本)と reboot smoke(3 automation 次 tick 復帰判定)を本文に固定し、失敗時 routing を 039 / 042 / 043 に閉じる。本線 fire 順は変更しない。
- 045 は 037 の follow-up ticket(Codex A)。037 で pickup contract / candidate_key / deferred_pickup まで runner 層に固まったが、default fetch path は NPB roster 1 本固定のまま。**既存 local / repo 内 collector artifact** を 037 intake(`_normalize_intake_items`)に接続する optional intake path を追加し、fixed-lane 3 family(program_notice / probable_pitcher / farm_result)に live item を入れる。新外部 API / scraping は追加しない(blanket go 範囲外に広げない)。038 ledger の 2 件目以降の entry / 035 observation の空転防止がゴール。
- 更新 fire 順: `036 ✓ → [038 + 040 並走] → 029 → 028 impl → 037`(035 reserve 維持、039 delivery 切り分け / 041 eyecatch fallback / 042 手動復旧 / 043 auto recovery 設計 / 044 startup 登録 + smoke は独立並走)。
- 役割固定(2026-04-21): Claude = 027/028/029/038/039/040 管理・route・accept/hold/escalated 判定 / Codex A = 027/028/037 開発 / Codex B = 036/040 開発 / Gemini 2.5 Flash = fixed lane 初稿 / Gemini Flash = agent lane 初稿 / user = 最終判断のみ。

## Batch API 在庫(2026-04-21)

- 023〜026 は Gemini 2.5 Flash Batch API を固定版レーンへ補助導入するための在庫
- 対象は固定版レーンだけ
- AIエージェント版レーン、mail 設定、既存 automation は触らない
- 初期は `Batch 補助レーン` として扱い、既存同期パイプラインを消さない
