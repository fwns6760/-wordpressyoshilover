# 423 DATA-PUBLISH rules consolidated (データ記事 publish ルール集約)

## 1. meta

- **ticket id**: 423
- **GH Issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/96
- **owner**: Claude Code (session 2026-05-22)
- **priority**: P1 (運用 SoT / source of truth)
- **status**: LOCK (恒久 rule book、 個別 fix は別 ticket 起票)
- **lane**: data-insight publish policy
- **created**: 2026-05-22
- **related reference**: `doc/reference/data-insight-metric-whitelist.md` (metric 単独 SoT、 本 ticket は それを含む全 publish rule の集約)
- **related memory**: project_data_insight_final_whitelist_2026_05_15 / project_data_insight_period_scope_2026_05_20 / project_data_insight_aggressive_publishing / project_site_direction_data_focus / project_mail_schedule_alignment / feedback_title_polisher_cap_policy

## 2. 背景

データ post に関する rule が複数の場所に散在:

- `doc/reference/data-insight-metric-whitelist.md` (metric ◯/×)
- memory file 7 本以上 (期間 / dedup / mail / title 等)
- commit 履歴 (415 / 417 / 418 / 422 / 423 / 5-22 dedup)
- src/config 各所

user 「データを出すルールを ticket にして」 (2026-05-22)。 → **1 file** で全 rule を見渡せる SoT を確立、 新規 rule 追加・既存 rule 変更時はここを更新する責務とする。

本 ticket は **実装変更を伴わない doc-only**。 個別の rule 違反修正は別 ticket 起票。

## 3. SCOPE (rule 9 領域)

### A. 何を出すか (metric whitelist)

**正本**: `doc/reference/data-insight-metric-whitelist.md`

要約:
- **◯**: counting stats 全部 (投手 25 / 打者 22 / 守備 4) + 標準率 (打率/出塁率/長打率/OPS/防御率/守備率/勝率) + 投手 /9 系率 (奪三振率/与四球率/被本塁打率) + WAR + 簡易UZR + 得点圏打率 + 球団 ranking 全部 + 試合後イベント + record/milestone
- **×**: ISO / wOBA / BABIP / BB% / K% / WHIP / K/BB / FIP / xFIP / 守備RF / split metric (得点圏 以外)
- **表記**: 日本語、 例外 OPS / UZR の英略号 OK
- 新規 metric 追加は user 個別確認、 推測 ◯/× 禁止

### B. いつの期間で集計するか (period scope)

**lock 日**: 2026-05-20 (user 「今後でいい、 恒久的に」)
**memory**: project_data_insight_period_scope_2026_05_20

- **日付 base 廃止** (last_7d / last_30d / weekly 等は使わない)
- **試合数 base** へ全面切替、 default = `last_5_games`
- 打者 cut: 3 試合 / 5 試合 / 10 試合 + 30 打席 / 50 打席 / 100 打席
- 投手 cut: 3 登板 / 5 登板 / 10 登板 + 5 投球回 / 10 投球回 / 20 投球回
- 既存 publish 済 post は書き換えない (forward-only)

### C. どの強度で publish するか (threshold / volume)

**lock 日**: 2026-05-15 (user 「閾値超えたものは全部出す」 「データサイト方向」)
**memory**: project_data_insight_aggressive_publishing / project_site_direction_data_focus

- 閾値 = 1.5σ
- counting TOP 10 (打者) / TOP 5 (投手) — whitelist 個別 lock 参照
- 閾値超え record 件数 cap **なし** (max_per_run = 無制限)
- 巨人選手のみ (元巨人 OB 含む、 非元巨人 MLB は除外、 [[project_mlb_player_inclusion_policy]])
- 12 球団 baseline で 順位 / band 算出

### D. どんな title にするか (title format)

**code**: `src/analysis/insight_article_generator.py` / `src/analysis/team_ranking_publisher.py` / `src/title_polisher.py`

- 形式: `【巨人データ】{選手名} {metric} {value} {順位}（{期間}）`
- 例: `【巨人データ】大城卓三 OPS .912、リーグ4位（直近5試合）`
- **期間 token 必須** (title 末尾、 期間なし title は原則 NG)
- 例外: 試合後イベント / 記録達成 / 連勝連敗 で「時点」 が title に入る系
- **「低い順で」 等の説明 prefix 禁止** (2026-05-22 commit `635cbd8`)
  - ERA / 防御率 等 lower-is-better metric も他 metric と同じ `N/6 位` 表記
  - 「低いほど良い」 hint は table label / explain 段のみ、 title には出さない
- title cap = 200 文字 (DB safety net、 trim 発火時は WARN log、 [[feedback_title_polisher_cap_policy]])
- SNS / mail display 用に 50 等への reverse 禁止

### E. 重複をどう抑えるか (dedup)

**code**: `src/analysis/insight_dedup_gate.py` (caller 13 sites、 signature 不変)
**config**: `config/insight_whitelist.json` の `dedup:` block
**lock 日**: 2026-05-22 (commit `d724f0c`)

判定順序:
1. **Type B: player daily cap** (player 単位、 subject が `team:` で始まらない場合)
   - default `player_daily_cap = 2` (config `dedup.player_daily_cap` で override 可)
   - 同 player の当日 publish 数 >= cap → block (reason=`player_daily_cap`)
2. **Type A + C: same-day block** (同 (player, metric) or 同 (team:g, TEAM_METRIC) が同 JST 日付に既 publish)
   - value_delta / rank_band 変化を無視して hard block (reason=`same_day_block`)
3. **cooldown 7 日** (config `dedup.cooldown_days`)
   - prev publish が 7 日以上前 → 通る (reason=`cooldown_expired`)
4. **value_delta bypass** (config `dedup.delta_ratio = 0.05`、 翌日以降のみ有効)
   - 値変化 >= 5% → 通る (reason=`value_delta`)
5. **rank_band 変化 bypass** (top_1pct / top_5pct / top_10pct / top_30pct / field 等)
   - band 跨ぎ → 通る (reason=`rank_band_changed`)

ledger: `article_candidates` table、 `signal_type=data_insight_dedup_history`、 status=`DRAFTED`/`PUBLISHED`

### F. publish status (draft vs publish)

**lock 日**: 2026-05-21 (commit `4fcf9e8` 「422: force data insight articles to draft」)

- data-insight 起源の全 post は **draft** で作成 (auto publish しない)
- user 手動 publish 判断 (WP admin)
- 例外: 球団 ranking 系も draft 統一 (現状)
- 修正したい場合は別 ticket で user 判断

### G. mail 通知 (per-post / batch / schedule)

**code**: `src/publish_notice_email_sender.py`
**memory**: project_mail_schedule_alignment

- **per-post 下書き mail** (`【要確認｜summary｜...】`、 1 post 1 mail): 通常 flow
- **【まとめ】直近10件** (burst_summary): **停止** (2026-05-22 env `DISABLE_BURST_SUMMARY_MAIL=1` on `publish-notice` job)
- **【公開判断まとめ X/Y】** (judgment_batch、 fetcher service の >100 fetch 用 safety net): fetcher service 側で env 未 set のため維持
- **【朝サマリー】**: 1 日 1 回、 06:06 JST、 publish-notice 24h budget 集計
- **schedule**: daytime :05 (6-15 JST) / evening :05,:35 (16-22 JST) / 夜間なし
- mail = guarded-publish 5 min 後に整列
- daily cap = 300 通 / soft threshold 240 / hard threshold 285

### H. dedup と表示の関連 rule

- 同 player x 同 day で max 2 件 = 主役 player の inbox 占有率 抑制 (5/22 実測 base で 44% → 30% 圧縮見込み)
- 主役 player (浦田/キャベッジ/平山/大城/ダルベック 等) 5 件/日 → 2 件/日に cap
- 補助 player (田和/堀田/井上/泉口 等) は cap 影響受けず、 出現比率増
- 球団 ranking 6 metric は team:g subject で cap 対象外、 但し同 metric 同日 2 回は same_day_block で停止

### I. 公開 site の方向性 (data focus)

**memory**: project_site_direction_data_focus

- yoshilover = 巨人データサイト
- data 記事の **量** と **多様性** が KPI
- 報知模倣系より上位
- 守備含めて幅広く
- SEO 評価しない (現フェーズ noindex、 [[project_current_phase_quality_not_seo]])
- 外部流入は user 手動 X のみ、 自動 SNS なし

## 4. 不可触 (本 rule book 編集時の禁則)

- 個別 metric の ◯/× 変更は **このファイルではなく** `doc/reference/data-insight-metric-whitelist.md` を編集する (whitelist が SoT)
- 1.5σ 閾値 / 5 試合 default / cap 2 等の数値変更は **config / src を編集して deploy**、 ここは追従更新のみ
- 「データ取得 path (DB ingestion)」 「LLM 関連」 は 本 ticket scope 外、 別 reference を当てる
- 既存 publish 済 post の遡及書き換えは別 ticket、 §11 user 判断境界 (content)

## 5. acceptance / 完了条件

- [x] 本 file commit (LOCK 状態で active 入り)
- [x] README index に 423 行追加
- [x] assignments.md に 423 行追加
- [ ] 既存 rule 変更時は本 file 同 commit で更新する運用が定着 (継続)

## 6. 関連 commit / image

- ERA title prefix 削除: `635cbd8` / insight-nightly image `era-no-low-prefix-635cbd8` (2026-05-22)
- dedup gate 拡張: `d724f0c` / 同 insight-nightly image `dedup-same-day-cap-d724f0c` (2026-05-22)
- batch summary mail 停止: publish-notice job env `DISABLE_BURST_SUMMARY_MAIL=1` (2026-05-22、 deploy 不要)
- data insight draft 強制: `4fcf9e8` (2026-05-21)
- title cap 200: yoshilover-fetcher image `title-cap-1c3e1f8` (2026-05-21)
