# ロードマップ

詳細: [docs/roadmap.md](../roadmap.md)

## 今日（2026-04-18）のゴール — 達成状況

当初のゴールは「`postgame` / `lineup` の受け入れ試験 → 合格なら Phase C 解放判断」だったが、
実態は以下のとおり:

- T-001 / T-002 / T-003 / T-007 / T-011 / T-012 / T-013 / T-015 / T-016 / T-018 の解決・修正に丸1日を使用
- 新 parser で publish 全量 fact_check 監査を実施 → **red 0件**
- T-001 コード修正完了（本番反映は第18便で Xserver 情報入手後）
- Phase C 解放判断のゲートに到達（実施は明日以降でも可）

詳細は `07_current_position.md` と `08_next_steps.md` を参照。

## 今週の想定スケジュール

| 日 | 作業内容 |
|----|---------|
| 04-18（土） | **完了** — 品質修正群 + 全量監査 + T-001 コード修正 |
| 04-19（日） | 試合日: Phase C 解放判断 → 解放後の実動作観察（or `postgame` / `lineup` のみ先行解放） |
| 04-20（月） | manager / notice 受け入れ（オフ日で落ち着いて確認） |
| 04-21〜 | pregame / recovery / farm / social / player / general 順次解放 |
| 今週末 | X投稿段階（`ENABLE_X_POST_FOR_XXX=1`）移行開始 |

## Phase 3 スマホ完結運営（段階1〜4）

| 段階 | 内容 | 状態 |
|-----|------|------|
| 段階1 | 朝のfact checkメール | **完了（2026-04-18朝）** |
| 段階2 | WP承認ワンクリック（スマホ）| **Phase C全カテゴリ安定後に着手** |
| 段階3 | X投稿フレーズ選択（スマホ）| **Phase C全カテゴリ安定後に着手** |
| 段階4 | 完全スマホ完結運営 | **段階2・3完了後** |

段階2〜4はPhase C（全カテゴリのpublish+X投稿が安定した状態）が完了してから着手する。
Phase Cが終わる前に段階2以降に手をつけない。

## Phase C 運用フェーズの課題

受け入れ順序（優先度順）:

1. `postgame` / `lineup` — 最優先（情報量多、品質安定）
2. `manager` / `notice` — 優先（専用型安定）
3. `pregame` / `recovery` / `farm` — 慎重（粒度差大）
4. `social` / `player` / `general` — 慎重（範囲広）
5. `live_update` — 保留（publish禁止継続）

X投稿は各カテゴリのpublishが数日安定した後に解放する。

詳細手順: [docs/phase_c_runbook.md](../phase_c_runbook.md)

## Phase D: アンテナサイト登録・SEO強化

- 流入導線増加（アンテナサイト登録）
- カテゴリページ改善
- title / description / internal linkの見直し
- Search Console / GA4観察導線整備

## Phase E: コンテンツ監査（6〜12ヶ月後）

- のもとけ型の選別的インデックス戦略を実行
- 低品質 / 重複 / 流入ゼロ記事の抽出
- noindex候補の棚卸し
- カテゴリ別の「残す / 畳む」判断

## Phase F: AI時代の差別化（長期）

- 選手・首脳陣・公示・二軍のニッチ深掘り自動化継続
- AI向け引用されやすい要約構造の強化
- 反応ログと読者行動を使った記事改善ループ
