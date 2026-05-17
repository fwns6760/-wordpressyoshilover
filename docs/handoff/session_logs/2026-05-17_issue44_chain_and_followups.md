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

## 追加で着地(午後 session)

### 344-INGEST 全 phase ship

| commit | 内容 |
|---|---|
| `63ee65a` | 344 Phase 1b: 25 ch (OB / 団体 / メディア) を youtube_ob_sources.json に追加 (12 → 37) |
| `0f07b9c` | 344 NPB公式 + J SPORTS 野球 ch (37 → 39) |
| `2423587` | 344 Phase 2: OB roster 拡充 (31 → 46 names) |

deploy: yoshilover-fetcher revision `00416-7lc` → `00417-5jw` → `00418-q2c`、 全 /health 200。

注: Phase 1a (caption / title filter / OB roster / draft enforcement) は 2026-05-14 既着地、 本日は 1b + 2 を追加 ship。

### Issue #44 E (週別)（週別) 二重 fix

| commit | 内容 |
|---|---|
| `c10b9e7` | insight_title_guard `_PERIOD_KEYWORD_RE` に「週別\|月別」追加、 半角 `(週別)` 検出して全角 `（週別）` 再 append を防ぐ |

bug 再現 verify 済 (post 68505 / 68571 / 68644 / 68946 等 5 件 publish 観測)、 fix 後 ensure_title_period が title 不変で no-op 返す。

deploy: insight-nightly `44e-period-dedup-c10b9e7` + yoshilover-fetcher revision `00419-b8b`。

### Issue #44 F (同 title 重複 publish) → 自然解消確認

- 5/16 朝の 5 連発 bug (post 68283/68296/68314/68316/68318 等) は 5/16 16:00 deploy の `362-INSIGHT-queue-cleanup-and-metric-run-cap` (metric_cap=1) で止まっている
- 5/17 today verify: 同値連発 0 件、 値変動した別記事のみ正常 publish (+5 → +6 等)
- **本日 F の追加 fix 不要、 明朝 07:00 JST 自然 fire 観察で再発無ければ CLOSE**

## チケット 344 / Issue #44 最終状態

| ticket | 状態 |
|---|---|
| 344-INGEST Phase 1a / 1b / 2 | 全 LIVE_DEPLOYED |
| Issue #44 A / B / C / D / G / H / **E** | LIVE_DEPLOYED |
| Issue #44 F | LIVE_OBSERVE (362 で自然解消、 明朝再観察) |
| Issue #44 4 (quality_gate N 行/複数球団) | 未着手 (次 session) |
| 68872 merge bug 根本 fix | observation log 着地、 明朝の prod log で merge point pinpoint |
| 352 postgame-auto auto-publish 復旧 | 自然解消済 (88de487 で landed、 5/14-16 連続 success) |

## 翌朝 (2026-05-18) の受け入れ観測 1 リスト

1. data-insight publish の title に `(週別)` / `(月別)` が **1 回だけ**
2. weekly/monthly data 記事の同値連発が 0 件
3. 二軍記事に相手 lineup が出ない (巨人スタメンのみ)
4. 「…」末尾 title が完結文に変換されている
5. YouTube ch 39 ch から OB 名 (山口俊 / 陽岱鋼 / 鈴木尚広 等) を含む動画が draft 化されてる
6. `event=media_primary_attach_decision` 構造化 log を grep して 68872 merge bug の発生 path を pinpoint
