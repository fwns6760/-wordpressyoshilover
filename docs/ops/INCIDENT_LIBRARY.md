# YOSHILOVER INCIDENT LIBRARY(永続、P1 体感事故 post-mortem)

本 doc は **過去の P1 体感事故から再発防止 anchor を引き出す library**。
次の P1 hotfix 判断時、Claude は **本 doc を必ず参照**(POLICY §19 参照義務)。

事故定義(POLICY §19 体感事故): Gemini call 0 でも user 体感を直接壊す事象(mail 過多 / 通知無音 / publish 急減 / X 直撃 / WP front 大規模変動 等)。

---

## 2026-05-01 P1 mail storm(298)

### 1 行サマリ
guarded-publish の */5 trigger ごとの古い backlog post 再評価で 24h dedup expire 後に同じ pool が再 emit、env=168 hotfix が逆効果で storm 拡大、結果 user Gmail に 90 通直撃。

### timeline(JST)

| 時刻 | event |
|---|---|
| 09:00 | env=168(`PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`)apply、user 明示 GO |
| 09:05-09:50 | publish-notice */5 trigger sent=10 × 9 連続(累積 90 通)|
| 09:33 | env=168 削除、storm 継続 = env 単独原因ではない確定 |
| 09:55 | sent=0(自然終息、cap=10 × pool exhaustion)|
| 10:00- | Codex A/B 並行調査 → Phase 2 impl + push(`d44594a` + `ffeba45`)|

### 真因(root cause)

1. guarded-publish job が */5 trigger ごとに ~100 件の old backlog post を skip 評価し fresh ts record を append
2. publish-notice scanner は ts field で filter、ts が常に新しいため `recent_window=24h` 内に毎回 fall
3. 24h dedup window は 1 post_id につき 24h、expire 後に再 emit
4. cap=10 と pool ~100 件で第一波 ~10 trigger 50 min で完結
5. 24h 後に pool が再生 → 第二波 recurrent loop

### 判断ミス(Claude 反省)

- **env=168 hotfix が逆効果**: scan window 24h → 168h に拡大したことで、24h 内 emit 済 post に加えて **24-168h 範囲の未 emit pool が一気に解放** → cap=10 連続発火
- **真因仮説の確認不足**: ledger 28.81 MiB を tail のみで判断、source-side(guarded-publish 再評価)の頻度を初期に見ていなかった
- **第一波自然終息の確認に時間がかかった**: 09:35 sent=10 → 09:55 sent=0 まで 20 min、env=0 hotfix を急ぐべきか判断保留(結果的に正解だが、過程は手探り)

### 防いだもの(Claude 守った境界)

- Phase 1(env=0)を **実行しなかった** = real review path(yellow / cleanup_required / hold)を止めずに済んだ
- 不変方針 全部維持(Team Shiny / 289 / Scheduler / Gemini / X / live_update / code edit 0)
- silent skip 増加なし
- WP mutation なし

### 再発防止 anchor(次の P1 で参照)

1. **「scan window 拡大」hotfix は逆効果 risk あり**: 24h dedup と source-side ts 更新 loop の組合せでは、scan window 拡大 = pool 解放 = storm 拡大。次回類似 incident で window 拡大型 env を提案された場合、まず source-side の ts 更新頻度を確認
2. **真因不明な P1 で env hotfix を打つ前に、ledger sample(tail / pid 集計)で source 仕様を確認**: 28 MiB ledger でも `tail -200` + post_id group 集計で再評価 pattern 5 分で見える
3. **第一波自然終息の判定**: cap × N trigger で pool exhaustion する場合、env hotfix 不要(自然終息を待つ判断 OK)。判定基準: `(pool size) / (cap)` trigger で sent=0 が見えるかどうか
4. **mail 通知は Ops Board ではない**(POLICY §21): user に mail 大量送信される事故は user 体感を直接壊す = 即 P1。「通知システムが暴走している」事象は cost ではなく体感事故
5. **§14 8 条件 灰色境界**: 「既存通知全停止ではない」境界が灰色な hotfix(real review 影響あり)は、storm 継続中以外は実施しない。安全側 HOLD
6. **24h dedup 失効周期の予測**: 第二波 想定 timestamp を Acceptance Pack の Why now / Expiry に明記、recurrent 前 deploy で第二波防止
7. **MAIL_BUDGET 違反は P1**(POLICY §22): 30 通/h or 100 通/d 超過 = 即 P1 体感事故、§14 / Acceptance Pack 必須
8. **`PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` 再投入禁止**(POLICY §22): 本日逆効果確定、永続 禁止 env として記録
9. **`cap=10/run` 単独で safe 扱い禁止**(POLICY §22): pool 増加 + 24h dedup expire で 2880 通/d 可能性、4 重防御(cap × dedup × pool size 制限 × MAIL_BUDGET monitor)必須
10. **真因 fix 後回しの code(sink-side cutoff)は flag ON 維持で運用**(298-Phase3 + 300-COST 関係): flag 外したら storm 再発、source-side fix(300-COST)を deferred 起票して安定後に再評価

### 関連 commit
- `bc1e5c0`: Codex A storm verify report
- `0b64078`: Codex B 恒久対策設計 + 巻き込み混入 docs/ops/ 永続化
- `d44594a`: Codex Phase 2 impl(persistent sent ledger、flag default OFF)
- `ffeba45`: Codex Phase 2 deploy-ready Acceptance Pack 追加
- `5fe7fad`: POLICY §3 §14 v2 反映
- `66af52a`: 298-Phase1 HOLD 確定 / 自然終息
- `459c31c`: POLICY §16 doc commit/staging 規律 + RUNBOOK 反映 + 298-Phase1 done 移動

### 関連 ticket(本日起票)
- 299-QA(postgame_strict 3 pre-existing failures、OBSERVE 起票)
- 300-COST(source-side guarded-publish 再評価削減、deferred、Phase 3 安定後)

---

## template(次の P1 体感事故記録時、本 format で追記)

```markdown
## YYYY-MM-DD P1 <incident-id>(<ticket-id>)

### 1 行サマリ
<事象を 1 行で>

### timeline(JST)
<時刻 | event 表>

### 真因(root cause)
<番号付き list>

### 判断ミス(Claude 反省)
<番号付き list>

### 防いだもの(Claude 守った境界)
<番号付き list>

### 再発防止 anchor(次の P1 で参照)
<番号付き list、最重要 section>

### 関連 commit / ticket
<list>
```

---

## 関連 doc

- `docs/ops/POLICY.md` §14(P0/P1 自律 hotfix 8 条件)
- `docs/ops/POLICY.md` §19(P1 体感事故定義 + INCIDENT_LIBRARY 参照義務)
- `docs/ops/POLICY.md` §21(mail は Ops Board ではない)
- `docs/handoff/session_logs/<date>_p1_<topic>.md`(履歴)
