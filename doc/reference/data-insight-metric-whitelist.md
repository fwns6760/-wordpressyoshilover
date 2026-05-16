# data-insight metric/記事タイプ whitelist 正本

**status**: REFERENCE (恒久仕様、ticket ではない)
**lock 日**: 2026-05-16
**source of truth**: 本 file
**user 決定**: 全 metric / 記事タイプを ◯ (publish + mail 対象) / × (drop) で明示確定

---

## 適用範囲

本 whitelist は以下の全 layer に対する正本仕様:

- `src/analysis/insight_*.py` の detector / anomaly / ranking / publisher
- `src/manual_intake_insight_query.py`
- data-insight 起源の draft 生成 / publish / mail 通知 path
- 関連 prompt / template / X 投稿候補生成

実装側 (現状コード) が本 whitelist に違反している場合、本 file が正、code 側を修正する。

---

## 表記 rule

- user 向けの記事 title / 本文 / mail / 表示は **日本語表記** が原則
- 例外で英略号を含めて許容: **OPS / UZR**
- 内部コード (ERA / AVG / OBP / SLG / FIELDING_PCT / K_per_9 等) も 日本語 (防御率 / 打率 / 出塁率 / 長打率 / 守備率 / 奪三振率) で表示
- × 側 (FIP / xFIP / wOBA / BABIP / ISO / BB% / K% / WHIP / K/BB) は site 非表示。万一表示 fallback に来ても日本語説明へ寄せる

## title 例 (期間を必ず入れる)

期間 stat / チーム stat の title は、読者が「いつの成績か」を即判別できるよう末尾に期間を入れる。

- `【巨人データ】大城卓三 OPS .912、リーグ4位（直近5試合）`
- `【巨人データ】岡本和真 本塁打3本、チーム最多（直近10試合）`
- `【巨人データ】山崎伊織 防御率1.80、リーグ3位（今シーズン）`
- `【巨人データ】巨人 チーム打率.286（阪神3連戦）`

期間なし title は原則 NG。例外は試合後イベント / 記録達成 / 連勝連敗のように、試合日または「時点」が title に入るものだけ。

---

## ◯ (publish + mail 対象)

### counting stats 全部

user 2026-05-15「敗北奪三振など当たり前にあるだろ」

**投手 counting (25)**:
勝利 / 敗北 / セーブ / ホールド / 完投 / 完封 / 投球回 / 奪三振 / 与四球 / 与死球 / 敬遠 / 失点 / 自責点 / 被安打 / 被本塁打 / 登板試合 / 先発 / 救援登板 / ブローセーブ / クオリティスタート / 暴投 / ボーク / 被打席 / 球数 / 牽制死

**打者 counting (22)**:
打数 / 安打 / 単打 / 二塁打 / 三塁打 / 本塁打 / 打点 / 得点 / 盗塁 / 四球 / 死球 / 故意死球 / 三振 / 犠打 / 犠飛 / 失策出塁 / 打席 / 出場試合数 / 塁打 / 併殺打 / 進塁打 / 打撃妨害

**守備 counting (4)**:
失策 / 補殺 / 刺殺 / 併殺

### 標準率 (日本語表記)

打率 / 出塁率 / 長打率 / OPS / 防御率 / 守備率 / 勝率

### 投手 /9 系率 (日本語表記)

user 2026-05-15「奪三振率/被本塁打率/与四球率/WAR をいれて」(当初 × → ◯ に reverse)

奪三振率 / 与四球率 / 被本塁打率

### composite 指数

総合貢献度

### 守備指数

user 2026-05-16「FIPはいらない。UZRはいる」適用。

簡易UZR

### rolling 期間 slice (user 2026-05-15「5 試合や 10 試合もね」)

直近 5 試合 成績 / 直近 10 試合 成績

### 期間 slice (user 2026-05-15「月の成績」+「全部 OK」で reverse 確定)

月別 成績 / 週別 成績

### 球場 slice (user 2026-05-15「球場別の成績」+「全部 OK」で reverse 確定)

球場別 成績 (具体的な対象球場 list は user 未確定、実 data 可用性も未 verify)

### split metric の代表

得点圏打率

注: 代打打率 / 対左打率 / 対右打率 / 対戦相手別打率 / ホーム別打率 / アウェイ別打率 は user 未確定、本 file では × のまま

### 球団 ranking 全部

user 2026-05-15「全部 OK」

- 本塁打数 / 打率 / 防御率
- 球団 counting 系: 勝利数 / 奪三振数 / 安打数 / 盗塁数 / 失策数 など
- 球団 順位
- 球団 勝率 / ゲーム差 / 連勝 / 連敗 / 得失点差
- ホーム成績 / アウェイ成績
- 対戦カード別成績 (vs 阪神 / vs DeNA など)

### 試合後イベント系

打者活躍 / 投手成績 / 節目越え / 球団順位変動 / 大幅好成績 σ外れ値

### record / milestone

user 2026-05-15「全部 OK」

- サイクル安打 / ノーヒットノーラン / 完全試合
- 連続安打試合 / 連続出塁試合 / 連続試合本塁打
- 連続イニング無失点 / 連続奪三振
- 最年少 / 最年長 record

---

## × (drop、生成しない / publish しない / mail に出さない)

### 打者サバメトリクス指数

ISO / wOBA / BABIP / BB% / K%

### 投手サバメトリクス指数 (残り)

WHIP / K/BB / FIP / xFIP

### 守備サバメトリクス

守備RF

### split metric (得点圏 / 月別 / 週別 / 球場別 以外)

代打打率 / 対左打率 / 対右打率 / ホーム別打率 / アウェイ別打率 / 対戦相手別打率

注: 月別 / 週別 / 球場別 は 2026-05-15 user reverse で ◯ に移動済 (上記 ◯ section 参照)

---

## 判断 pattern (新規 metric 追加時の判定軸)

- ◯ = counting stats 全部 + 標準率 + 投手 /9 系率 + WAR + 簡易UZR + 得点圏打率 + 球団 ranking 全部 + 試合後イベント + record/milestone
- × = 残りのサバメトリクス指数 (FIP/xFIP/wOBA/BABIP/ISO/BB%/K%/WHIP/K/BB/守備RF) + 得点圏打率以外の split metric
- 表記: 日本語、ただし OPS / UZR は英略号 OK。UZR_proxy とは書かず「簡易UZR」と表示する。
- 新規 metric は **個別 user 確認** が default、推測 ◯/× しない

---

## 既知の現状コード状態 (2026-05-15 audit 時点)

**バグ / デグレ risk として記録** (本 whitelist と code の差異):

- `src/analysis/insight_advanced_metrics.py:281-298` の `all_batter_metrics()` / `all_pitcher_metrics()` は **× 側 metric も全部計算して返す** (ISO / wOBA / BABIP / K_per_9 / BB_per_9 / HR_per_9 / K_BB / FIP / xFIP)。計算自体は構わないが、publish/display layer が拾うと違反。
- `src/analysis/insight_nl_query.py:51-64` の metric alias 辞書に × 側も含む。clarification 必要。
- publish / display layer の whitelist gate は **未実装** (要 follow-up ticket)。

---

## 関連 / 経緯

- 前段 memo: `feedback_data_insight_user_preferences_2026_05_15.md` (AI memory 側、本 file が公式正本)
- 関連: `project_data_insight_aggressive_publishing.md` (閾値 publish policy)、`project_site_direction_data_focus.md` (データサイト方向)、`project_mail_schedule_alignment.md` (mail 5-35 分)
- 2026-05-15 中の reversal 経緯: K/9・BB/9・HR/9 は当初 × → user「奪三振率/与四球率/被本塁打率/WAR をいれて」で ◯ に変更
- 2026-05-16 reversal: user「FIPはいらない。UZRはいる」により、守備UZRは「簡易UZR」として ◯ に変更。
