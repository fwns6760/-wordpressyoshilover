# Editorial Policy — yoshilover

**目的**: 何を記事化するか / 何を捨てるか / のもとけらしさをどう担保するか を言語化する。selection rule / subtype × category matrix / 「のもとけらしさ」3 要素 を一本に統合。

**運用**:
- Flash prompt / 選別ロジック / audit 軸すべてこの方針に従う
- 方針変更は `decision_log.md` に追記
- 実装の閾値・語彙リストは本方針に **従う側**。本方針を更新せずに実装だけ変えない

---

## 1. 選別ルール — 何を拾う / 何を捨てる

### 1.1 拾う（記事化候補）

- **巨人関連**: タイトル or 本文に巨人 / 読売ジャイアンツ / Giants 明示
- **選手 / 首脳陣 名**: 巨人現役選手 or 首脳陣 の名前が一次情報として出てくる
- **公式・マスコミ一次情報**: 発言 / 通達 / 試合結果 / スタメン / 二軍情報
- **カテゴリ適合**: 試合速報 / 選手情報 / 首脳陣 / ドラフト・育成 / 補強・移籍 / コラム のいずれかに該当

### 1.2 捨てる（skip / reject）

- **巨人非関連**: 他球団単独話題、海外球界（MLB 単独）
- **歴史参照偏重**: 過去の話題を現在進行の発言と誤認する恐れ
- **SNS 汚染**: ファン個人の投稿・憶測で一次情報性が薄い
- **重複**: 同一事象を既に 24h 以内に取り上げ済み
- **マスコミ長文引用**: 著作権懸念。引用は oEmbed のみ
- **弱ネタ**: `match_score` による低スコア判定（数値閾値 reject ではなく品質総合判断）
- **プライバシー侵害 / 差別表現 / 著作権懸念**: 致命的 NG、即 skip

### 1.3 のもとけらしさ 3 要素（全記事必須）

1. **一次情報核**: 発言引用 / 公式情報リンク を本文中核に据える
2. **転載要約で終わらない**: マスコミ記事を要約するだけで終わらせない、独自解釈を 1 段足す
3. **ファン視点 1 段**: 率直な感情・応援視点を 1 文以上（chain of reasoning 反映後は MB-005 で強制）

### 1.4 方針（要約）

**のもとけを 1 人+AI で再現**、20-30 本/日（のもとけ）→ 10 本/日（yoshilover Phase 1）を目標。量より「運用ループ閉鎖」。

---

## 2. subtype × category マトリクス

### 2.1 現行 subtype 一覧（`src/rss_fetcher.py:45-57`）

| subtype | env flag | 主カテゴリ | Phase 1 解放 | X 解放 |
|---|---|---|---|---|
| `postgame` | `ENABLE_PUBLISH_FOR_POSTGAME` | 試合速報 | ✅ 済 | 🔵 MB-006 |
| `lineup` | `ENABLE_PUBLISH_FOR_LINEUP` | 試合速報 | ✅ 済 | 🔵 MB-007 |
| `manager` | `ENABLE_PUBLISH_FOR_MANAGER` | 首脳陣 | 🔵 MB-002 | Phase 2 |
| `pregame` | `ENABLE_PUBLISH_FOR_PREGAME` | 試合速報 | 🔵 MB-003 | Phase 2 |
| `farm` | `ENABLE_PUBLISH_FOR_FARM` | 選手情報 | 🔵 MB-004 | Phase 2 |
| `farm_lineup` | `ENABLE_PUBLISH_FOR_FARM` | 選手情報 | 🔵 同上 | Phase 2 |
| `notice` | `ENABLE_PUBLISH_FOR_NOTICE` | 補強・移籍 / 選手情報 | ⏸ Phase 2 | Phase 2 |
| `recovery` | `ENABLE_PUBLISH_FOR_RECOVERY` | 選手情報 | ⏸ Phase 2 | Phase 2 |
| `social` | `ENABLE_PUBLISH_FOR_SOCIAL` | コラム | ⏸ Phase 2 | Phase 2 |
| `player` | `ENABLE_PUBLISH_FOR_PLAYER` | 選手情報 | ⏸ Phase 2 | Phase 2 |
| `general` | `ENABLE_PUBLISH_FOR_GENERAL` | コラム / 補強・移籍 / その他 | ⏸ Phase 2 | Phase 2 |
| `game_note` | `ENABLE_PUBLISH_FOR_GENERAL`（共用） | 試合速報 / コラム | ⏸ Phase 2 | Phase 2 |
| `roster` | `ENABLE_PUBLISH_FOR_GENERAL`（共用） | 補強・移籍 | ⏸ Phase 2 | Phase 2 |

### 2.2 subtype 別の記事構造（C 軸監査で確認）

| subtype | 必須構造 |
|---|---|
| `postgame` | 導入 / 試合経過 / 勝敗分岐 / 選手コメント / 一次情報リンク |
| `lineup` | スタメン表 / 相手投手 / 注目選手 / 一次情報リンク |
| `manager` | 発言引用 / 発言の文脈 / 解釈 / 一次情報リンク |
| `pregame` | 試合前提 / 先発予想（予想と明記）/ 注目点 / 一次情報リンク |
| `farm` / `farm_lineup` | 2 軍結果 / 選手動向 / 一次情報リンク |

Phase 2 subtype の構造 spec は解放前に本書に追記する。

### 2.3 primary_category 一覧

- 試合速報
- 選手情報
- 首脳陣
- ドラフト・育成
- 補強・移籍
- コラム

`classify_category()` (`src/rss_fetcher.py:8209`) が語彙順序で決定する。順序変更は影響範囲大のため、CLAUDE.md §コード変更制約 に準拠。

---

## 3. Flash prompt 方針（cost 中立縛り）

CLAUDE.md §本体コスト制約に従い、cost 増なしの 3 点で品質改善:

1. **材料境界明示**: 材料内は自由 / 材料外は推測禁止
2. **chain of reasoning 強制**: 事実 → 解釈 → 感想（MB-005）
3. **subtype 別 temperature**: Phase 2 MB-P2-03

NG（cost 増 or SPOF リスク）:

- few-shot examples per-article
- 2 段階生成（draft → refine）
- rejection + retry loop

---

## 4. audit 軸との対応

| audit 軸 | 本方針との対応 |
|---|---|
| `title_body_mismatch` | §1.3 のもとけらしさ 1 (一次情報核) が崩れた状態 |
| `thin_body` | §2.2 subtype 別必須構造の欠落 |
| `no_opinion` | §1.3 のもとけらしさ 3 (ファン視点 1 段) 欠落 → MB-005 で対策 |
| `no_eyecatch` | 記事要件の形式欠落（CLAUDE.md `PUBLISH_REQUIRE_IMAGE=1`） |
| `pipeline_error` | 生成 / 投稿の技術エラー、本方針は無関係（運用側） |

---

## 5. X 自動投稿の文案方針（Phase 1 解放後）

- 事実ベースで煽らない
- `AUTO_TWEET_REQUIRE_IMAGE=1` 遵守（画像必須）
- `X_POST_DAILY_LIMIT=10` 範囲内
- 炎上・誤爆 1 件で即 `AUTO_TWEET_ENABLED=0`（`release_gate.md §3`）
- oEmbed のみ、マスコミ記事の長文引用 NG

---

## 6. 未確定項目（user 調整余地）

- Phase 2 subtype（notice / recovery / social / player / general）の必須構造 spec
- `classify_category` の語彙順序見直しの要否
- `match_score` の reject 閾値（現状は数値閾値 reject ではない）
- コラム subtype の Phase 2 昇格基準

---

## 7. 関連

- MVP 成立条件 / Phase 1 リリース条件: `CLAUDE.md §MVP 定義`
- 解放 / 撤退条件: `docs/release_gate.md`
- 日次運用: `docs/daily_ops_checklist.md`
- 継続監査ループ（C 軸 = 構造監査）: `master_backlog.md §継続監査ループ`
- 判断履歴: `docs/handoff/decision_log.md`
- Flash prompt 位置: `src/rss_fetcher.py:2996`, `:3262`, `:3413`
