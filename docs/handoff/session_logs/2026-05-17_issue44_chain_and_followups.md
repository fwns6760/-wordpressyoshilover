# 2026-05-17 session handoff — issue #44 insight chain + follow-ups

## 概要

issue #44「データ記事を全て ranking 表形式にする」chain で 6 commit + 6 deploy
を ship。 その後 user feedback 経由で 3 件の post 別 fix を追加 ship。

## 着地済

### Issue #44 本流 (insight-nightly, Job generation 57 → 63)

| # | commit | renderer | image tag |
|---|---|---|---|
| 1 | `c6e4470` | stat_delta | 本文セ・リーグ ranking 表 + case A title (rank phrase) | `44b1-stat-delta-c6e4470` |
| 2 | `d884006` | UZR + 守備率 | player_comparison fallback に team_comparison 挟む | `44b2-defense-fb-d884006` |
| 3 | `2060063` | HR pace | title 期間末尾括弧 + 「本塁打」日本語化 | `44b3-hr-pace-2060063` |
| 4 | `9e18d0d` | hidden 規定未満 | 「今シーズン」prefix 廃止 → 末尾括弧 | `44b4-hidden-title-9e18d0d` |
| 5 | `8be68aa` | hit_streak_run | milestone consecutive と統一表記 | `44b5-streak-8be68aa` |
| 6 | `c881313` | standings_shift | セ・リーグ 6 球団順位表 helper + case D「チーム」prefix | `44b6-standings-c881313` |

deploy 経路: 各 commit ごとに `cloudbuild_insight_nightly.yaml` で build → `gcloud run jobs update insight-nightly`、 generation = 57 → 63。 Scheduler / env / Secret は未変更、 手動 execute は追加 publish/mail 回避のため未実行。

test: pytest insight 系 126 passed、 既存退行 0。 backward compat (conn=None / snapshot 不在) 全 case green。

### follow-up (yoshilover-fetcher Cloud Run service)

| commit | 内容 | revision | post |
|---|---|---|---|
| `feaf88f` | media primary attach 観察 log (post 68872 merge bug 診断、 挙動不変) | `00413-rpn` | 68872 |
| `3f688ed` | 二軍 article は巨人スタメンのみ (相手 lineup suppress、 1軍 は不変) | `00414-s68` | 68856 |
| `eb02d8e` | title "…" 末尾を summary 第一文で再構成 (RT/emoji prefix 剥がし) | `00415-w4c` | 68870 |

deploy 経路: 各 commit ごとに root `Dockerfile` から `gcloud builds submit --tag` で build → `gcloud run services update yoshilover-fetcher`、 /health 200 確認。

test: pytest 関連系 (lineup/farm/title/media/social) 計 1000+ passed。 既存 test 2 件 (hochi compact lineup farm 用) を新挙動 (table 1 個 / 相手 heading 無) に合わせて修正。

## 受け入れ観測ポイント (明日朝以降)

### Issue #44 本流

- **07:00 JST 自然 fire**: `insight-nightly:44b6-standings-c881313` 実行
- 新規 publish の data 系記事で:
  - stat_delta / 守備系 / standings_shift の本文に **セ・リーグ ranking 表** が出る
  - title が case A/C/D spec (「リーグ N 位」「継続中」「チーム」prefix + 末尾括弧) 準拠
  - HR pace / hidden 規定未満 の title が期間末尾括弧 + 日本語表記
- 残作業観察 (Issue #44 内、 別 commit):
  - E「(週別)（週別)」二重付与
  - F 同 title 重複 publish (dedup_gate key bug)
  - 4 quality_gate の N 行/複数球団 check

### follow-up

- **68872 型 (media primary attach mismatch)**: `event=media_primary_attach_decision` 構造化 log を Cloud Logging で grep。 entry.title vs source_url の content 不一致を upstream で pinpoint してから surgical fix へ。 本 session では観察のみ、 挙動不変
- **68856 型 (二軍 lineup)**: 新規二軍 draft で「📋 巨人スタメン」だけ出る、 「📋 XXXスタメン」(相手) は出ない。 1軍 lineup は両 team table 維持 (退行無)
- **68870 型 (title "…" 末尾)**: 新規 draft で末尾 `…` player-only title が **player + 動作** の完結文に変わる。 構造化 log `event=title_ellipsis_recovered` が出る (発火数の観測)

## 未着手 / 持ち越し

- Issue #44 残作業 (E/F/4): 観察優先、 surgical fix は別 session
- post 68872 merge bug の根本 fix: 観察 log の 1 日 data を見てから upstream 修正
- post 68872 自体の削除: §11 GATE、 user 判断 (Claude 触らない)

## メモリ更新

- `feedback_user_acceptance_only_2026_05_17.md` 新規保存: 「user は受け入れ試験のみ、 実装 mode (Phase / commit 分割 / A/B/C 進行) は Claude 判断、 mode 選択肢を user に出さない」
