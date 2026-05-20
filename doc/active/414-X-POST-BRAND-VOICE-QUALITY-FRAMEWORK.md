# 414-X-POST-BRAND-VOICE-QUALITY-FRAMEWORK: A-E 5 軸 (型分離 + voice + 精度 + 炎上防止 + 試合前テーマ)

## 1. ticket header

- **status**: DRAFT (user GO 受領、 実装着手中)
- **priority**: P1 (user 報告 hallucination 2 件 + brand voice 全体品質課題)
- **owner**: Claude
- **lane**: Claude direct dev
- **parent**: 411 (LIVE_DEPLOYED `3dd89e5`、 brand post 2 persona base)
- **依存**: 並走 agent (403 chain) と `ranking_article_publisher.py` 衝突 risk、 commit 直列必須
- **設計 source (確実根拠)**:
  - 2026-05-20 chat user 直接提示 (A 型分離、 D 炎上 check、 E 試合前テーマ)
  - 411 LIVE_DEPLOYED 実 file (B voice persona)
  - user hallucination 報告 2 件 (岸田 28位、 山瀬 2軍混入) + 「試合中は当日 only」 (C 精度)
- **GH Issue**: #90 (元 9 axis を A-E 5 軸に再構成)

## 2. 背景

414 は元々 brand post の hallucination 防止 9 axis として起票。 chat 進行で user が複数の追加 spec を提示し、 brand voice quality framework に scope 拡張:

- 「型を分けるのが大事」 (5 型: 速報 / 感情 / データ / 次の展開 / ポジティブ)
- 「炎上・ズレ防止 check」 (6 check: 批判 / 断定 / 雑批判 / 監督批判 / 誤字 / 煽り)
- 「試合前の注目テーマ自動セット」 (7 軸: 先発 / 昨日の流れ / 注目 / 打順 / 昇格 / 相性 / ファン反応)
- 「試合中は当日 only」 (古いデータひろわない)

これらを 411 の 2 persona base 上に積む。

## 3. やること (5 軸)

### 軸 A: 型分離 5 種 (新)

5 型 + 自動選択 logic:

| 型 | 中身 | 主な精度要件 |
|---|---|---|
| 速報系 | 事実中心 (選手名 / 回 / スコア) | 事実厳格チェック (DB / Tavily 照合) |
| 感情系 | 巨人ファン気持ち代弁 | persona prompt の voice 強化 |
| データ系 | 過去成績 / 直近傾向 | DB 照合済のみ、 順位禁止 (= 軸 C と整合) |
| 次の展開系 | 采配 / 継投 / 追加点 / 守備固め | 試合状況前提、 試合日のみ |
| ポジティブ系 | 若手 / 二軍 / 復帰選手 | OB / 育成 / 復帰 narrative |

実装:
- `src/x_post_branding_gen.py` に `_POST_TYPE_ENUM = ("flash", "emotion", "data", "next", "positive")`
- 5 型別 prompt template (system prompt の上に「今回の type は ◯◯ なので…」 を overlay)
- 自動選択 logic `select_post_type(now_jst, is_game_day, db_fact, tavily_results) -> str`:
  - 試合日 + 18-21時 = `next` (次の展開系) 優先、 fallback `emotion`
  - 試合日 + 21-23時 (試合後) = `emotion` + `data` (1 fire で 2 型混在 OK)
  - 非試合日 + 朝 = `data` + `positive`
  - 非試合日 + 昼夜 = `emotion` + `positive`
- 型 と voice persona (軸 B) は直交 overlay

### 軸 B: voice persona (411 既実装、 維持)

- フーガ (長文分析、 default)
- 缶詰 (試合中実況、 試合日 18-21時 + 当日 only)
- 軸 A の型と直交 overlay (例: 缶詰 voice + 次の展開系 / フーガ voice + データ系)

### 軸 C: 精度 9 axis (新、 hallucination 防止)

| # | 改修 | 場所 |
|---|---|---|
| C1 | `\d+位` forbidden regex 追加 (岸田 28位 type 防止) | x_post_branding_gen.py |
| C2 | 数値 whitelist (`_extract_unverified_numbers`、 verified set 外 drop) | x_post_branding_gen.py |
| C3 | `\d+\.\d{3}` / `防御率\d+\.\d{1,2}` forbidden regex (率系) | x_post_branding_gen.py |
| C4 | prompt 強化 (bad example: 出塁率28位 / 打率3位 等) | x_post_branding_gen.py |
| C5 | temperature default 0.6 → 0.4 | x_post_branding_gen.py |
| C6 | published_date 7日超 drop strict (`_recent_published_within_days`) | x_post_branding_gen.py |
| C7 | drop 時 構造化 dict log (reason / matched_pattern) | x_post_branding_gen.py |
| C8 | 1軍 active filter (`src/analysis/active_roster_filter.py` 新規、 直近 14 日 3 試合) + caller 注入 | new file + x_post_mail_lane.py / ranking_article_publisher.py |
| C9 | persona=kandume で `_tavily_search(same_day_only=True)` + `build_db_fact_line(streak_window=0)` (当日 only) | x_post_branding_gen.py |

### 軸 D: 炎上・ズレ防止 6 check (新)

post-gen review として safety_check 拡張:

| # | check | 実装 |
|---|---|---|
| D1 | 選手批判が強すぎる | NG 語 ban (`使えない` `戦犯` `クビ` `最悪` `酷い` `論外` `引退しろ` `辞めろ`) regex |
| D2 | 事実と感想混在 | 数字隣接の主観表現 (`◯位だから ダメ`) を drop |
| D3 | 断定しすぎ | `絶対` `間違いなく` `確実に` `100%` `必ず` を warning + 文脈で drop |
| D4 | 采配批判が雑 | 監督名 + 強批判語の隣接 (`阿部監督 無能` 等) を drop |
| D5 | 誤字 / 選手名ミス | roster 名 literal 照合 (`config/giants_roster.json` aliases match)、 generic 「打者A」 等 drop |
| D6 | 他球団 / 相手ファン煽り | 煽り語 (`雑魚` `カモ` `負け犬` `三流` `論外`) regex drop |

実装: `_gemma_branding_safety_check` を拡張、 drop 時 軸 C7 の構造化 log で reason 明示。

### 軸 E: 試合前 注目テーマ 7 軸 (新)

7 テーマ自動集約 + Gemma prompt 注入:

| # | テーマ | source / 取得方法 |
|---|---|---|
| E1 | 今日の先発 | `src/sports_fetcher.py get_today_game()` + Tavily `giants.jp/npb.or.jp` |
| E2 | 昨日の流れ | `insight.db games WHERE game_date = yesterday` + inning_scores + winning_pitcher |
| E3 | 注目選手 | `pick_candidates` ranking pool (軸 C8 1軍 filter 後) + fan_voice_pool (397) |
| E4 | 打順変更 | lineup history compare (前日 vs 今日)、 **新規 helper** `lineup_history_compare` |
| E5 | 昇格選手 | roster.json `active` field 変動 (前日 snapshot)、 **新規 helper** `roster_active_diff` |
| E6 | 相手投手との相性 | `insight.db pitching_logs` vs `batting_logs`、 巨人打者の対投手 stat |
| E7 | 巨人ファン反応話題 | `fan_voice_pool` (397) + (将来) Yahoo Realtime Search |

実装:
- 新規 `src/analysis/pregame_themes.py`: 7 テーマを dict として返す `build_pregame_themes(now_jst, db_path) -> dict[str, str]`
- caller: `build_gemma_branding_candidate` の prompt に 「今日の注目テーマ」 section として 注入 (試合日 17時前まで = 試合前 windows)
- E4 / E5 は history snapshot 必要、 `data/insight/` 配下に daily snapshot file 追加 (新規 schema、 既存 DB 不変)

## 4. やらない範囲

- spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) 変更
- 既存 mail / Scheduler / Dockerfile / WP REST / X live posting
- live_update enable (§11 user 判断、 別 ticket)
- env / Secret 値変更
- `X_POST_MAIL_GEMMA_GEN_ENABLED` default 変更
- 既存 `_build_branded_post_text` template (DB# 候補) の挙動
- 既存 `build_fan_voice_candidate` (397) 挙動
- roster JSON schema 変更 (tier field 追加は別 ticket)
- NPB 公式 active list ingest (別 ticket)
- mascot persona name / brand identity / 視覚装飾 / A/B 検証 / engagement 取り込み (memory 起点軸 F-Z は 414 scope 外)

## 5. 実装計画 (commit 段階)

| commit | scope |
|---|---|
| 1 | 414 ticket rewrite (本 file) + assignments + README + GH Issue 更新 |
| 2 | 軸 C 完成 (C1-C7 + C9 in x_post_branding_gen.py、 C8 は別 commit) + 新規 test 15+ |
| 3 | 軸 D (6 check in safety_check 拡張) + test 6+ |
| 4 | 軸 C8 (active_roster_filter.py 新規 + caller wire) + test 4+ |
| 5 | 軸 A (5 型 prompt template + selector) + test 10+ |
| 6 | 軸 E (7 テーマ pregame_themes.py 新規 + caller wire) + test 14+ |
| 7 | 統合 dry-run + Cloud Build + Cloud Run deploy |

各 commit 後 push + pytest baseline 比較。

## 6. STOP 条件

- baseline pytest fail 数増加 (私の changes 単独で増加)
- 既存 `_build_branded_post_text` / `build_fan_voice_candidate` 挙動変化
- 既存 mail の brand post 候補数が 0 件になる (= 過剰 drop)
- 軸 C8 1軍 filter で巨人 1軍 全選手消える (= filter 誤り)
- 軸 D regex で 既存通常 post まで drop (= 過剰 ban)
- 軸 E 7 テーマ build で latency 急増 (現 ~10秒 → 30秒超)
- 並走 agent (403) と `ranking_article_publisher.py` 衝突
- spec 382 hard rule 違反混入

## 7. 受け入れ条件

- 全 軸 A-E 実装、 全 test pass (≥ 50 件新規)
- pytest baseline regression 0 (私の changes 単独)
- 「岸田 28位」 type の hallucination が drop (test 再現)
- 「山瀬 2軍混入」 が ranking から消える (test 再現)
- 缶詰 persona で当日以外 snippet が context に入らない (test 確認)
- 5 型自動選択が時間帯 / 試合日で動作 (test 確認)
- 6 炎上 check が NG 語含む post を drop (test 確認)
- 試合前 7 テーマが prompt に注入される (test 確認)
- 既存 mail 候補数 が 維持される (観察)
- env / Secret / Scheduler / Dockerfile / WP / X 不変
- cost ¥0/post 維持

## 8. 関連

- 411 LIVE_DEPLOYED (`3dd89e5`、 2 persona base)
- 394 active P0 (hallucination fix、 同 file 触る、 commit 直列)
- 382 CLOSED (spec / mail / Scheduler 流用元)
- 397 (`build_fan_voice_candidate`、 軸 E7 ファン反応 source)
- 403 chain (parallel agent、 ranking_article_publisher.py 触る、 軸 C8 衝突 risk)
- 408 LIVE_DEPLOYED (OB classifier、 軸 A 「ポジティブ系」 で OB voice 連動余地)

## 9. memory 起点軸の取り扱い (記憶からの再構成防止)

軸 F-Z (timing / thread / A/B / 多 source / 装飾 / 季節 / engagement / block / mascot / 透明性 / 競合 / 法務 / 多言語 / audit / cost / 観戦micro / 育成 / quota / segmentation / incident / source追加) は私の memory brainstorm。 414 scope **外**。 user が明示的に 提示 or 実 log で観測されてから別 ticket で扱う。
