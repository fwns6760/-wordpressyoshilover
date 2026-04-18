# ロードマップ

詳細: [docs/roadmap.md](../roadmap.md)

## 今日（2026-04-18）のゴール

`postgame` / `lineup` の受け入れ試験を完了し、合格なら `ENABLE_PUBLISH_FOR_POSTGAME=1` / `ENABLE_PUBLISH_FOR_LINEUP=1` + `RUN_DRAFT_ONLY=0` への移行判断をする。

## 今週の想定スケジュール

| 日 | 作業内容 |
|----|---------|
| 04-18（土） | postgame/lineup 受け入れ試験、合格なら publish解放 |
| 04-19（日） | 試合日: publish後の実動作観察、manager/notice受け入れ |
| 04-20（月） | pregame/recovery/farm 受け入れ（オフ日） |
| 04-21〜 | social/player/general 順次受け入れ |
| 今週末 | X投稿段階（ENABLE_X_POST_FOR_XXX=1）移行開始 |

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
