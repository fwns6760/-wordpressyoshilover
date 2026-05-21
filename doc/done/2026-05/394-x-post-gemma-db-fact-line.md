# 394: Gemma branding に insight.db 由来の当日試合 / player log / 連勝記録を fact line として注入

status: LIVE_DEPLOYED_OBSERVE (commit `ef1e756`、 image `394-db-fact-ef1e756` deploy 後)
owner: Claude Code
lane: (392 と同じ x-post-mail-lane 拡張)
priority: high (392 出力品質 上げ、 hallucination 抑制)
depends_on: 392 (commit `a15d852` / `414d411` / `1a55d59`)
extends: 392 (置換ではなく機能拡張)
created: 2026-05-19 JST
github_issue: (未起票、 後付け正規化予定)

---

## 1. 作業の目的

392 で組んだ Gemma 4 + Tavily REST 経路の **コンテキスト品質を上げる**。
22:30 fire 観察で以下の問題が出た:

- Tavily の relevance ranking で **古い (2024-2026 年 3 月の) Wikipedia / 開幕直後 / 復帰前** snippet が context に混入 → Gemma が「これから復帰する」「ついにその時が」 と現在進行形・直近形で hallucinate
- DB fact line は 392 で path だけ用意してあったが、 caller が empty を渡していたため Gemma に **当日の具体数字が一切渡らず**、 内容が generic / 古い情報の現在化に流れた

user 明示 (2026-05-19 chat):

- 「データベースは当日のきろくがいい、 試合前と試合中」
- 「勝ち負けは RSS で拾える?」 (= 試合結果は既存 ETL の games table で取れるので別途 RSS 不要)
- 22:30 mail の Gemma post 2 件 (吉川尚輝 / 泉口友汰) は両方 cheerleading + 時系列ズレで NG

## 2. やること (scope)

### ADD

- `src/x_post_branding_gen.py` に新関数 `build_db_fact_line(player_canonical, db_path, target_date=None, streak_window=5)`:
  - SQLite read-only (`file:db?mode=ro`) で SELECT only、 mutation しない
  - games table から今日試合 (`WHERE game_date = today_jst`) → opponent / score / 勝敗
  - batting_logs JOIN games で player の今日打撃 stat (AB/H/R/RBI/SB)
  - pitching_logs JOIN games で player の今日投球 stat (IP/R/ER/K/BB/H_allowed/result_mark)
  - games table から直近 N 試合 result → ○●△ marks + 集計 (X 勝 Y 敗 Z 分)
  - 該当 record が無ければ 該当 line を skip、 全 line 無ければ空 string 返却
  - 例外時は空 string 返却 (fault tolerance、 mail 止めない)
- `src/tools/run_x_post_mail.py` の `_build_gemma_branding_candidates` に `db_path` 引数追加
  - 既存 caller の db_path (insight.db cache、 既に download 済) を再利用、 追加 GCS access なし
  - player ごとに `build_db_fact_line()` 実行
  - empty なら `_pick_gemma_branding_players` 由来の lineup_fact を fallback
- 既存 `build_gemma_branding_candidate(db_fact_line=...)` 引数にそのまま渡す
- tests: `BuildDbFactLineTests` 5 件 追加 (temp SQLite seed)

### KEEP

- 既存 392 経路 (Tavily REST + Gemma 4 + safety validator + silent skip)
- Tavily call (days=1 + JST 当日 filter、 1a55d59 で実装済)
- 時間帯 tone hint (414d411 / 1a55d59 で実装済)
- Cheerleading 定型語 ban (414d411 で実装済)
- 既存 Cloud Run Job 群、 Dockerfile.x_post_mail、 Scheduler、 Secret、 WP、 X

### fact line 形式 (改行区切り、 facts のみ、 narrative なし)

```
- 今日(YYYY-MM-DD) 巨人 vs OPP: GS-OS (勝利/敗戦/引分)
- PLAYER 打撃 (今日): X打数Y安打 Z打点 W得点 V盗塁
- PLAYER 投球 (今日): X.Y回 Z失点 K奪三振 W四球 被安打H (○/●/H/S/-)
- 直近N試合: ○●○●○ (X勝Y敗Z分)
```

Gemma の system prompt 内「DB 照合済み数字 (使ってよい数字): {db_fact_line}」 section にそのまま流れる。 Gemma は **DB fact 内の数字のみ verified 数字として post 本文に使ってよい** (spec 382 hard rule)、 Tavily snippet の数字は使ってはいけない (検証されていない)。

## 3. 触らない範囲

- 既存 Cloud Run Job 群 (`yoshilover-fetcher` / `publish-notice` / `guarded-publish` / `insight-nightly` / etc) — image / env / schedule 全部不変
- `Dockerfile.x_post_mail` — Node なし、 image / cold start 不変
- `insight.db` schema / ETL pipeline — read-only SELECT のみ、 schema 変更なし
- `src/x_post_mail_lane.py` の既存 DB query (data candidates 用) は不変
- Scheduler / Secret / WP / X live posting — 不変
- 392 / 391 既存 commit は supersede しない、 機能拡張のみ

## 4. 影響範囲

- `src/x_post_branding_gen.py` (+ build_db_fact_line)
- `src/tools/run_x_post_mail.py` (+ db_path arg + caller)
- `tests/test_x_post_branding_gen.py` (+ 5 test)
- 既存 24 test も継続 pass、 関連 lane 含めて 126/126 pass (regression 0)

## 5. test

- `py_compile` OK (新 file なし、 既存 file 修正のみ)
- `pytest tests/test_x_post_branding_gen.py tests/test_x_post_mail.py` → 126/126 pass
- Cloud Build SUCCESS、 image `394-db-fact-ef1e756` deploy 後 自然 fire で観察

## 6. STOP / rollback

- flag `X_POST_MAIL_GEMMA_GEN_ENABLED=0` で機能 OFF (392 path ごと OFF)
- env `X_POST_MAIL_GEMMA_GEN_MAX=0` で件数 0 (rebuild 不要)
- 旧 image (`392-tune-1a55d59` or `392-gemma-branding-a15d852`) に Job 戻せば 394 完全 rollback (1 分)

## 7. 禁止

- 392 spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) は維持
- DB fact line で渡せる数字は **insight.db に存在する verified 値のみ**。 LLM 側で水増し禁止 (Gemma prompt で hard rule 化済)
- 公開済み記事 / X live post には触らない (user mail だけ)

## 8. 必要 API

- 既存 Gemini API (free tier) + Tavily REST (1000 credits/月) のまま
- 新規 API なし

## 9. 作業ログ

- 2026-05-19 23:00 JST: build_db_fact_line 実装 + caller 改修 + 5 test 追加
- 2026-05-19 23:10 JST: pytest 126/126 pass (regression 0)
- 2026-05-19 23:15 JST: commit `ef1e756` push、 Cloud Build fire (`by3fbdtiy`)
- 翌 07:00 JST am-1 自然 fire で初実 verify 予定

## 10. post-work (deploy 完了後追記予定)

- image digest:
- Job generation:
- 07:00 fire 結果:
- DB fact 注入有無 / 数:
- 観察 mail subjective evaluation:

## 11. Regression Memo

- 392 で fire していた既存 candidates (DB# データ候補) は完全不変
- Gemma 候補だけが拡張対象、 DB fact が空でも従来挙動 (Tavily snippet のみ context) と同じ
- 旧 image rollback 経路あり (Job image update 1 コマンド)
