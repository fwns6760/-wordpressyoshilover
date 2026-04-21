# Daily Ops Checklist — yoshilover

**目的**: Phase 1 運用の 1 日を「スマホ 5〜10 分」で回す checklist。判断は「公開する / しない / rollback」の 3 択に絞る。

**前提**:
- publish は postgame / lineup + Phase 1 で manager / pregame / farm 解放
- X 自動投稿は postgame / lineup のみ（Phase 1）
- audit-notify メールは JST 11/13/15/17/20/23 着信（0 件時スキップ）
- Scheduler 稼働時間は平日 9-16 時 + 試合時間帯。18 時以降の試合中は自動発火対象

---

## 朝（JST 9:00〜10:00、5 分）

- [ ] **Gmail `[yoshilover]` メール確認**（23:00 分 / 11:00 分）
  - 0 件なら放置
  - 非 0 件: 軸別件数を 1 行メモ、post_id を控える
- [ ] **WP admin draft 件数**（スマホで `draft` タブ）
  - 深夜 〜 早朝に入った新 draft の有無確認
  - 明らかな事故（title 崩壊 / 空本文 / 他球団ネタ）があれば trash
- [ ] **試合日かどうか確認**
  - 試合日 → 夜の post 監視を念頭に置く
  - 非試合日 → column / farm 系のみ来る想定

**判断**:
- 通常運用なら触らない
- 事故 draft が 1 件でもあれば → user 判断で rollback 検討（当該 subtype の `ENABLE_PUBLISH_FOR_*=0` 戻し）

---

## 昼（JST 12:00〜14:00、2 分）

- [ ] **Gmail `[yoshilover]` 13:00 分確認**
- [ ] **試合日で lineup subtype 稼働時刻の記事 1 本だけ目視**
  - 平日: JST 16:50 / 17:10 / 17:20 / 17:40 / 17:50
  - 週末: JST 12:50 / 13:10-17:50 帯
  - lineup に欠員 / 相手先発 / 注目点 3 要素があれば OK

**判断**:
- lineup 構造崩れ 1 件 → X 自動投稿 OFF（postgame 側は維持）
- 2 件以上 → lineup publish 一時停止

---

## 夜（JST 20:00〜23:30、3 分）

- [ ] **Gmail `[yoshilover]` 20:00 / 23:00 分確認**
  - 20:00 分: 試合中 / postgame 量産ピークの問題集中
  - 23:00 分: その日の最終確認
- [ ] **試合日なら postgame 1〜2 本目視**
  - 事実 → 解釈 → 感想 の 3 段構造（MB-005 反映後）
  - 一次情報リンク `yoshilover-related-posts` の存在
  - アイキャッチの存在
- [ ] **X 自動投稿ログ確認**（Phase 1 で ON 後）
  - 誇張 / 煽り / 事実歪みが無いか
  - `X_POST_DAILY_LIMIT=10` 到達していないか

**判断**:
- postgame 事故 1 件 → user 判断、rollback 候補
- X post 事故 1 件 → 即 `AUTO_TWEET_ENABLED=0` 検討（炎上回避優先）

---

## 週 1（週末など落ち着いた時、15 分）

- [ ] **Scheduler 稼働確認**
  ```bash
  gcloud scheduler jobs list --project baseballsite --location asia-northeast1
  ```
  - `audit-notify-6x` / `giants-*` 群 / `fact-check-morning-report` が ENABLED
- [ ] **記事構造監査（C 軸）**（Claude 実施）
  - subtype ごとに 2〜3 件 sampling で読む
  - 「のもとけらしさ」3 要素を確認（一次情報核 / 転載要約で終わらない / ファン視点1段）
  - 異常発見 → master_backlog.md に新規 MB-NN 起票
- [ ] **audit trend 集計**
  - 過去 7 日の軸別件数を CLAUDE.md / master_backlog.md §継続監査ループ に反映

---

## 月 1（運用総括、30 分）

- [ ] **master_backlog.md 進捗レビュー**（【】→ 【×】の月次差分）
- [ ] **MVP 成立条件 7 項目の self-check**
- [ ] **Phase 2 parking lot（MB-P2-*）の昇格判断**（user）
- [ ] **decision_log.md 遡及**（抜けがあれば Claude 追記）
- [ ] **Cloud Run / Gemini / X API の請求額確認**（user、無料枠内か）

---

## 緊急対応（いつでも）

### 炎上 / クレーム / 事実誤記

1. **即 `AUTO_TWEET_ENABLED=0`**（X 拡散停止）
2. 該当記事を `draft` に戻す（WP admin から）
3. user → Codex rollback 依頼（Cloud Run 前 revision に戻す）
4. decision_log.md に rollback エントリ追加
5. 落ち着いたら原因調査（audit 追加軸 or prompt 改善）

### publish が全く回らない

1. `gcloud logging read` で `/run` error を確認
2. Scheduler 止まってないか確認
3. WP REST API 疎通確認
4. Xserver plugin（MB-001 関連）の影響がないか

### audit-notify メールが来ない

1. 対象 window 内に draft/publish が 0 件の可能性（通常運用）
2. Scheduler `audit-notify-6x` の稼働確認
3. `src/fact_check_notifier.py` の SMTP エラーログ確認
4. Gmail 側 spam / filter 確認

---

## 参考

- audit / scheduler / secret / endpoint 情報 → `CLAUDE.md §audit pipeline 稼働情報`
- 判断履歴 → `docs/handoff/decision_log.md`
- 未解決 bug → `docs/handoff/tickets/OPEN.md`
- release 進捗 → `docs/handoff/master_backlog.md`
