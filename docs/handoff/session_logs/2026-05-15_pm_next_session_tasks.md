# 2026-05-15 PM → 次セッション 引き継ぎ task list

本日のセッションは 346/347/350/351 LIVE まで完走したが、context 疲労 + 判断 round trip 多で精度落ち、いくつか保留にした項目を fresh Claude session で対応する。

**読み順**: まず `2026-05-15_pm_x_post_mail_lane_buildout.md` (本日全体 handoff) を読んで現状把握、次に本 doc の task を順番に。

---

## 必読 prefix (毎 task 共通)

- AI 失敗 mode: 「記憶再構成 / silent skip / 自己評価 OK」が最大の事故源
  - claim 前に必ず `grep` / `pytest` / `gcloud describe` / log diff で **実 source verify**
  - memory に頼らず file を re-read
- 348 と完全 disjoint 維持 (`src/analysis/*.py` / `article_candidates` table / publish 経路 不可触)
- 346 PWA / 既存 publish-notice mail / X auto post lane 不可触
- LLM (Gemini / Codex / OpenAI) 呼出 一切なし
- 各 task は **doc 起票 → user GO → 実装** の protocol で進める

---

## Task 1: mail 実機 rendering 確認 (priority 高)

### 状況
- 本日 22:36 JST に execution `x-post-mail-lane-49m58` で実 mail 送信成功
- `fwns6760@gmail.com` に届いてるはず、件名: `[X 投稿候補 N件] 試合後 / 2026-05-15 22:36 JST`
- user が朝開いて HTML rendering / 🐦 X 投稿 button / column 等を目視確認する

### user 体感で出る判断

| 観察 | 対応 |
|---|---|
| HTML 全部正常に rendering | task 完了 |
| 🐦 X 投稿 button タップで X アプリ起動 / 本文プリフィル OK | task 完了 |
| HTML 崩れ / button 動かない / 文字化け | followup ticket で fix |
| column 表 (`順位｜選手｜チーム｜OPS`) が見づらい | format 圧縮 task (Task 3 と統合検討) |

### user feedback 受領後の action
1. 致命的問題なら即 followup ticket → 修正 → re-deploy
2. 軽微な改善案件は他 task と統合

---

## Task 2: X post format の改行追加 (priority 高、user 明示)

### 現状の format
```
セ・OPS ランキング 📊（5/1〜5/16・規定打席 30+）

1. 佐藤輝明（阪神）.945
2. 牧秀悟（DeNA）.932
...
```

### user 要望 (本日明示)
header の **期間部分を 2 行目に分けて視認性 up**:

```
セ・OPS ランキング 📊
期間: 5/1〜5/16・規定打席 30+

1. 佐藤輝明（阪神）.945
2. 牧秀悟（DeNA）.932
...
```

または

```
セ・OPS ランキング 📊
（5/1〜5/16・規定打席 30+）

1. 佐藤輝明（阪神）.945
...
```

### 実装場所
- `src/x_post_mail_lane.py` の `_format_one` 関数
- 現状 `lines[0]` 末尾に period_suffix を append してる箇所
- 1 行目 = ranking title (`セ・OPS ランキング 📊`)、2 行目 = period (`（5/1〜5/16・規定打席 30+）`) に分割
- 既存 test 期待値も更新必要 (`test_header_includes_date_range_and_sample_threshold` 等)

### scope
- code 修正: 数行
- test 期待値修正: 既存 5-6 test の文字列 assert を更新
- doc 352 起票 → user GO → cloudbuild → deploy → execute → mail で目視確認
- 工数: 30-60 分

### 衝突
- 348 と無関係
- 346 不可触 (`src/x_post_mail_lane.py` 内で完結)

---

## Task 3: 絵文字拡張の判断 (priority 中、本日保留)

### 現状
X post 本文中の絵文字は **2 種のみ**:
- 📊 (ranking header)
- ← (巨人 marker)

### 候補 (本日提示済、user 未決定)

| option | 内容 | brand 効果 |
|---|---|---|
| a | 現状維持 (📊 + ←) | データ感重視、信頼性 |
| b | header metric 別 (⚾打撃 / ⚡投手 / 🛡️守備) | 軽い差別化、type 一目で分かる |
| c | 派手目 (🔥 / 💪 / 📈 を末尾に) | インプ実験用、リーチ伸びる可能性 |

### 判断方法
- mail 実機を見て user 体感で「もう少し賑やか」「今で十分」を判断
- a なら何もしない (close)
- b なら `_format_one` で metric 種別判定 → 絵文字差替え、約 30 行追加
- c なら footer 直前に絵文字行追加、数行

### 工数
- a: 0
- b: doc + code + test + deploy = 半日
- c: doc + code + test + deploy = 半日

### 衝突
- 348 と無関係、x_post_mail_lane.py 内で完結

---

## Task 4: 直近 5 試合 / 10 試合 variation 追加 (priority 中、観察後)

### 状況
- 本日 351 で 22 combo に拡張したが、game-count base (直近 N 試合) は含めず
- 348 で実装予定の logic と重複するため scope 縛った
- ただし production 衝突 risk は ZERO (verify 済)

### 実装方針 (実装する場合)
- `src/x_post_mail_lane.py` に新 helper `_query_recent_n_games_date_range(n)` 追加
- `games` table に対し read-only SELECT:
  ```sql
  SELECT DISTINCT game_date FROM games
  WHERE game_date IS NOT NULL
  ORDER BY game_date DESC LIMIT 5;
  ```
- 取得した最古 date を since、最新 date を until として _MetricCombo に渡す
- combo pool に 直近 5 試合 / 10 試合 × OPS / AVG / ERA = 6 combo 追加 → pool 22 → 28

### 注意
- `games` table が **Giants-centric** (giants_score / opp_score / opponent column 持つ) という推定が本日付いた
- もし games が Giants game しか持ってない場合、「直近 5 試合 = 直近 5 巨人試合」の意味になる
- セ 全 6 球団の試合を直近 N 日 で取りたいなら、batting_logs.game_date を distinct する別 query が必要
- 実装前に games table の実 schema + 行内容を verify 必須 (pytest local で SELECT 試行)

### 衝突
- 348 と soft 重複 (logic を別 file で書く)、hard 衝突なし
- 348 ship 後に 348 helper に乗り換え可能 (refactor 別 ticket)

### 工数
- doc + code + test + deploy = 半日〜1 日

### 判断軸
- mail 1-2 週観察後、「同じ ranking ばかり」感あったら実施
- 351 の 22 combo で十分多様なら skip

---

## Task 5: 連日 dedup の検討 (priority 低、観察依存)

### 状況
- 1 日 5 通 mail で同 metric / 同 player が連続出る可能性
- 349 (publish lane の dedup) とは別 lane

### 実装方針 (実装する場合)
- 軽い 24h dedup を 347 lane 内 で実装
- mail 履歴を local file or GCS に記録、直近 24h 内に出した combo を skip
- 348 / 349 の dedup history table とは **別 storage** (衝突回避)

### 工数
- doc + code + test + deploy = 半日

### 判断軸
- user 体感で「同じ ranking ばかり」「飽きた」なら実施
- 351 shuffle で 22 pool 多様性あるので、不要かも

---

## Task 6: 指名検索「ヨシラバー」順位回復観察 (priority 中、user 作業)

### 状況
- 本日 410 化 + subdomain ブランド cleanup 完了
- Google 再クロールに 2-4 週
- GSC で「ヨシラバー」検索パフォーマンス を user が観察

### Claude にできる範囲
- なし (GSC は user 手動アクセス、Claude は触れない)
- user が「順位戻った」「戻らない」 feedback くれた時点で次の action 判断

### feedback 別 action
- 戻った → close、現状維持
- 戻らなかった → category index 解放を検討 (348/349 観察、これらは現状 noindex)

---

## Task 7: 348 / 349 user GO 来たら別 lane で着手 (priority 依存)

### 状況
- 348: insight whitelist + 直近 N 試合 aggregation + ranking 記事 publish、READY (user 数値 GO 待ち)
- 349: dedup-cooldown-cascade、READY (348 後)
- 両方 doc/active/ にある、scope は記事 publish lane 側

### Claude action
- user GO 受領 → doc 起票 ([348 / 349 既存 doc] base) → 実装 → 数値確定 → deploy → 観察
- 347 mail lane との衝突 0 (verify 済)、並行可

### 工数
- 348: 1-2 日
- 349: 0.5-1 日

---

## Task 進行順序の推奨

```
朝 (user mail 受領):
  → Task 1 (体感 OK / NG 判定)

午前 (user feedback ベース):
  → Task 2 (改行追加、軽い、即対応可)
  → Task 3 (絵文字、user 判断次第)

午後:
  → Task 6 (GSC 観察) ← user 単独
  → Task 7 (348/349 user GO 来たら)

1-2 週後 (観察フェーズ):
  → Task 4 (直近 5/10 試合 追加検討)
  → Task 5 (dedup 必要性判断)
```

---

## 重要な open question (user 判断必要)

1. **mail rendering OK?** (Task 1) — Gmail で目視確認
2. **改行 format どっち?** (Task 2) — `期間: M/D〜M/D` か `（M/D〜M/D）` の 2 行目
3. **絵文字 a/b/c?** (Task 3) — 体感判断
4. **直近 5/10 試合 追加するか?** (Task 4) — 観察後判断
5. **348 / 349 数値確定 / GO?** (Task 7) — user 数値 確定待ち

---

## 最重要 carry-over (絶対外さない)

1. **不可触範囲**: 348 file / 346 PWA / 既存 publish-notice / X auto post lane / LLM 呼出 全部
2. **AI failure mode** verify ベース必須
3. **scope 縛りすぎない**: 「期間 concrete化 + 規定打席 厳格化 + CLI default 揃える」を最初から含めて起票
4. **build 何回も走らせない**: cloudbuild 前に scope を全部 fix
5. **doc 起票 → GO → 実装** の protocol 維持

---

## 本日関連 commit (next session で参照)

- `934007a` 346 PWA insight to X post draft (LLM-free)
- `3fc973c` 347 セ・リーグ ranking X post mail lane (LLM-free / 348 disjoint)
- `925703b` 350 mail 精度改善 (date range + 規定打席 threshold)
- `2939448` 351 variation 拡張 (combo 10 → 22)
- `70d05de` chore(handoff): 2026-05-15 PM session log

---

(本 doc + `2026-05-15_pm_x_post_mail_lane_buildout.md` を fresh session で必読、その後 task 順に着手)
