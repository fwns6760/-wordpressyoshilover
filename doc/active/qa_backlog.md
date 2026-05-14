# QA / 事実防衛 backlog (一覧管理)

**目的**: 事実ミス対策 ticket / SEO / マーケ / ingestion 系の HOLD・BACKLOG を一覧管理。
HOLD という曖昧 status を使わず、必ず「状態 / 解除条件 / owner / 次確認 / 関連 file / cost」を明示する。

**更新ルール**:
- 状態: `not-now` / `backlog` / `blocked` / `ready` のいずれか
- 各項目は個別 ticket doc 起票必須(本 file はインデックス、詳細は ticket 側)
- 解除されたら状態を `ready` に変更し、本 file から外す or 状態のみ更新

---

## QA(事実防衛) backlog

| ticket | 状態 | 概要 | 解除条件 | owner | 次確認 | 関連 file | cost |
|---|---|---|---|---|---|---|---|
| **254-QA** starter innings normalization | **READY(本日 fire 中)** | 投手回数表記揺れ吸収(`6` / `6.0` / `6.1` / `6回1/3` 等)、244 検出力強化 | 本日 Codex B fire 完了で解除 | Codex B / Claude | 本日完了通知後 | src/baseball_numeric_fact_consistency.py + tests | 0 |
| **252-QA** X 候補単独 fact check | backlog | x_post_generator 単独 path で check_consistency 呼ぶ narrow 追加(現状 publish_notice 経由のみ) | X 候補で数字/選手名ミス実例検出、または 247-QA 観察後判断 | Codex B(後段) | 254-QA 完了後 + 247-QA flag ON 観察後 | src/x_post_generator.py + src/baseball_numeric_fact_consistency.py + tests | 0(post-check のみ、Gemini 増なし) |
| **253-QA** mail summary fact check | not-now | mail summary 内 source 断片の contains check(現状 truncate のみ) | 編集者が summary 由来で誤判断した実例 検出 | Codex B(後段) | 編集者報告 / 247-QA 観察 / 254-QA 完了後 | src/publish_notice_email_sender.py + tests | 0(false positive 抑制 narrow) |

## SEO 系 backlog

| ticket | 状態 | 概要 | 解除条件 | owner | 次確認 | 関連 file | cost |
|---|---|---|---|---|---|---|---|
| **251-SEO** default noindex 部分解放戦略 | not-now | yoshilover-post-noindex.php の default noindex を選択的に index 解放(postgame strict 成功記事 / 編集者推奨 等) | 247-QA 観察結果 + 248-MKT-2 効果確認 + GSC 連携状態確認 | Claude(起票) / 後段 user 相談 | 247-QA 観察 + のもとけ型 段階展開後(数週間 単位) | src/yoshilover-post-noindex.php / SEO plugin | SEO 影響観察必要 |

## マーケ / 回遊 backlog

| ticket | 状態 | 概要 | 解除条件 | owner | 次確認 | 関連 file | cost |
|---|---|---|---|---|---|---|---|
| **248-MKT-3b** default_review / 弱 title 記事 noindex 拡張 | not-now | 既存 noindex policy への追加(対象拡大) | 251-SEO 戦略確定 + GSC 観察 | Codex A(後段) | 251-SEO 解除後 | src/yoshilover-063-frontend.php | 0 |
| **250-QA** manager / player_comment subtype strict 展開 | not-now | 247-QA strict slot-fill pattern を manager_comment / player_comment subtype に展開 | 247-QA flag ON 観察 + fact error rate 改善確認 | Codex B(後段) | 247-QA 1-2 試合日 観察後 | src/postgame_strict_template.py 拡張 + src/rss_fetcher.py narrow | 0(同 1 Gemini call) |

(248-MKT-4 / 248-MKT-5 は本ファイル「即実装(本日 active)」へ移動 — commit `bb68e21` で着地済、production rendering 確認 2026-05-14。)

## ingestion 系 backlog

| ticket | 状態 | 概要 | 解除条件 | owner | 次確認 | 関連 file | cost |
|---|---|---|---|---|---|---|---|
| **249-INGEST** 試合中 live ingestion 強化 | not-now | Yahoo realtime / sponichi RSS 試合中速報、live_update narrow enable | 247-QA / 248-MKT 安定 + cost 余力(現 ¥80/day base から +N$ 受容判断) | user 専決 | のもとけ型 量増ステージ(数ヶ月) | src/rss_fetcher.py / Cloud Run / Scheduler | **大**(Gemini call 増・Cloud Run 実行回数増) |

## コメント系 backlog

| ticket | 状態 | 概要 | 解除条件 | owner | 次確認 | 関連 file | cost |
|---|---|---|---|---|---|---|---|
| **コメント数 badge** | not-now | 各記事 thumbnail に WP comment_count badge 表示 | コメント数が増えてから(現状 0 多く逆効果) | Codex A(後段) | 数ヶ月後 / X embed 強化後 | src/yoshilover-063-frontend.php | 0 |
| **WP / Disqus コメント本格化** | not-now | 内部コメント機能 enable + moderation 体制 | コメント badge 効果確認 + moderation 体制構築可能 user 判断 | user 専決 | のもとけ型 安定 + moderation 体制後 | WP 設定変更 | **moderation コスト大** |
| **X embed (oEmbed) 強化** | not-now | Twitter ファン反応 / 公式 quote 自動表示 | 248-MKT-2 / 248-MKT-3a 完了後 | Codex A(後段) | 数週間後 | src/yoshilover-063-frontend.php | 0 |

## 即実装(本日 active)

| ticket | 状態 | 概要 | commit |
|---|---|---|---|
| 247-QA postgame strict slot-fill | DONE(default OFF) | LLM 自由作文抑止、JSON 抽出 + slot-fill | `deb7c58` |
| 247-QA-amend strict failure review | DONE | strict 失敗 → review sentinel(legacy 戻さない) | `b80c7c7` |
| 248-MKT-2 same-game articles | DONE | single 記事下部「この試合の関連記事」 | `04309ae` |
| 248-MKT-3a wrapper helper + matrix doc | DONE | 表示判定 4 helper 集約 + subtype × 表示先 matrix | `f339692` |
| 248-MKT-3c shortcode placement runbook | DONE(handoff doc only) | editor 用 shortcode 配置手順書 | (ambient untracked、user side 後段 commit) |
| 248-MKT-4 同選手回遊 + 248-MKT-5 同カテゴリ | DONE | article_bundles で same_player / same_topic group 表示(2026-05-14 production rendering 確認) | `bb68e21` |
| 254-QA innings normalization | IN_PROGRESS(Codex B b47yvlyjx) | 投手回数表記揺れ吸収 | (進行中) |

## 本日 fire 順位ロック(参考)

1. 事実核(247-QA / 244 / 234-impl-* / 254-QA)
2. 観戦導線(246-MKT v0)
3. 記事下回遊(248-MKT-2)
4. 表示品質土台(248-MKT-3a / 3c)
5. 後段:のもとけ型展開 / index 解放 / コメント / ingestion

---

## 更新履歴

- 2026-04-29: Claude 初回起票(254-QA fire 開始 + 252/253-QA backlog 起票 + 251-SEO HOLD 解除条件明文化)
