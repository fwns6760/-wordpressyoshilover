# Release Gate — yoshilover

**目的**: publish 解放 / X 自動投稿解放 / rollback の **判断基準** を明文化する。Claude / Codex が独断で解放・撤退しないよう、user が判断に使う gate。

**運用**:
- 解放・撤退は必ず本 gate と照合してから実行
- threshold は保守値で開始、運用実績で user が調整（変更は `decision_log.md` に追記）
- 本ファイルは「解放条件」なので、実環境の現在値は書かない（`master_backlog.md §6 実環境スナップショット` 参照）

---

## 1. publish 解放条件（subtype 単位）

subtype ごとに publish を ON（`ENABLE_PUBLISH_FOR_<SUBTYPE>=1`）にする前に、以下を **すべて満たすこと**:

### 共通 DoD（全 subtype）

1. **事実誤記の事故率**
   - 過去 7 日の draft で fact_check 🔴 red が該当 subtype で **0 件**
   - audit-notify-6x の `title_body_mismatch` 件数が該当 subtype で **3 件/週 以下**

2. **アイキャッチ担保**
   - 過去 7 日の draft の 100% が featured_media > 0
   - `PUBLISH_REQUIRE_IMAGE=1` が有効

3. **一次情報リンク**
   - 該当 subtype の draft で `yoshilover-related-posts` div が **80% 以上** 挿入されている
   - 出典ブロック（ソース URL）が本文末に存在

4. **薄さ（thin_body）**
   - audit-notify-6x の `thin_body` 件数が該当 subtype で **3 件/週 以下**
   - 閾値: postgame / lineup = 280 字、manager / column = 350 字

5. **のもとけらしさ 3 要素**（Claude 週 1 sampling で C 軸監査）
   - 一次情報核があり（発言引用 / 公式情報リンク）
   - 転載要約で終わらない
   - ファン視点 1 段がある（chain of reasoning 反映後、MB-005）

6. **smoke deploy**
   - canary revision で 1〜2 記事生成 → WP で目視 OK
   - prod traffic 移行後、**24h 観察で事故 0 件**

### subtype 固有条件

| subtype | 追加条件 |
|---|---|
| postgame | スコア / 勝敗 / 試合経過が fact_check を通っている |
| lineup | スタメン表が正確（選手名の誤記 0）/ 相手先発 明記 |
| manager | 発言引用が一次情報（公式 / マスコミ記事）と一致 / 文脈が歪められていない |
| pregame | 先発予想が「予想である」旨が明記される / 確定情報との混同が無い |
| farm | 二軍試合結果・選手動向の事実が正確 |
| column | **Phase 1 では解放しない**（主観成分強、Phase 2 以降） |
| notice / recovery / social / player / general | **Phase 1 では解放しない**（Phase 2 parking lot） |

### 解放手順（Codex 実行）

1. user 判断で解放 subtype を決定
2. Claude が Codex inline prompt 起票（canary deploy → smoke → promote）
3. canary smoke clean → user 承認 → traffic 100% 移行
4. 24h 観察（audit-notify-6x で事故検知）
5. 事故 0 件 → 解放完了（master_backlog.md チェックを【×】に）
6. 事故 1 件以上 → rollback（§3 参照）

---

## 2. X 自動投稿解放条件（subtype 単位）

X 自動投稿（`AUTO_TWEET_ENABLED=1` + `ENABLE_X_POST_FOR_<SUBTYPE>=1`）を ON にする前に、以下を **すべて満たすこと**:

### 前提

- 該当 subtype の publish が既に稼働 **2 週間以上** 事故 0 件
- MB-005（chain of reasoning）が prod 適用済み

### 共通 DoD（全 subtype）

1. **publish の事実歪みゼロ**
   - 過去 14 日で該当 subtype の title_body_mismatch が **0 件**
   - fact_check 🔴 red が **0 件**

2. **誇張 / 煽り / 事故要素の排除**
   - 最近 10 記事を Claude が目視で確認、誇張表現 0
   - 感情先行で事実を歪める表現が無い

3. **X 運用側の制約遵守**
   - `X_POST_DAILY_LIMIT=10` を超えない
   - `AUTO_TWEET_REQUIRE_IMAGE=1` が有効
   - `AUTO_TWEET_CATEGORIES` が該当 subtype のカテゴリに限定

4. **smoke deploy（48h 観察）**
   - canary tag で 1 記事を X 投稿 → 文案 / 画像 / rate limit 確認
   - prod traffic 移行後、**48h** 観察で X 事故 0 件
     - X 事故 = 誇張 / 事実歪み / 削除要請 / rate limit 超過 / image 欠損

### subtype 固有条件

| subtype | 追加条件 |
|---|---|
| postgame | 勝敗 / スコアを煽らずに事実中心で書ける（ファン感情は記事本文に留める） |
| lineup | スタメン通知として機能（予想でなく確定情報のみ） |
| manager / pregame / farm | **Phase 1 では X 解放しない**（Phase 2 parking lot） |
| 他 | **Phase 1 では X 解放しない** |

### 解放手順

publish 解放と同じ（canary → smoke → promote）、観察期間のみ 48h に延長。

---

## 3. rollback 条件

以下のいずれかが発生した時点で **即 rollback** 検討。user 最終判断だが、**事故 1 件でも相談**。

### 即時 rollback（user に上げる前に AUTO_TWEET 止めてよい）

1. **X で炎上 / クレーム発生**
   - 即 `AUTO_TWEET_ENABLED=0`
   - 該当記事を `draft` に戻す
   - user に事後報告（時間との勝負で独断 OK）

2. **事実歪みの拡散**
   - X post が事実と明らかに異なる内容で既に投稿済み
   - 即 `AUTO_TWEET_ENABLED=0` + 該当 X post 削除（user 手動）
   - Cloud Run 前 revision に rollback

3. **選手プライバシー侵害 / 差別表現 / 著作権懸念**
   - 該当記事削除 + 全ての `ENABLE_PUBLISH_FOR_*=0`
   - user に即連絡

### user 相談 → rollback 判断

1. **事故率の急増**
   - audit-notify-6x の単一軸件数が 24h で **10 件以上**（従来の 3 倍以上）
   - 該当 subtype の `ENABLE_PUBLISH_FOR_*=0` 検討

2. **特定 subtype の連続事故**
   - 同一 subtype で 3 日連続 fact_check 🔴 red
   - 該当 subtype の publish 一時停止

3. **rate limit 超過常態化**
   - `X_POST_DAILY_LIMIT=10` に 3 日連続到達
   - `AUTO_TWEET_CATEGORIES` 絞り込み or subtype 単位で X off

4. **Cloud Run / Gemini API コスト急増**
   - 月次コストが user 想定の倍以上
   - prompt builder / retry loop / 2段階生成 混入疑い → 調査

### rollback 手順（Codex 実行）

1. user 判断で rollback 決定
2. Claude が Codex inline prompt 起票（前 revision に traffic 戻す / env 戻す）
3. Codex 実行、rollback 完了を確認
4. `decision_log.md` に rollback エントリ追記
5. 原因調査 → 改善 prompt 起票（継続監査ループへ）

### rollback 可能性の維持

- Cloud Run deploy は常に `--no-traffic` 経由 → 前 revision を残す
- master への不要な push を避ける（検証用空コミット禁止）
- env 変更は 1 項目ずつ（複数同時変更で原因不明化を避ける）
- canary tag を複数個運用する場合、どの canary がどの検証かを明示

---

## 4. gate を使う場面の例

### Phase 1 進行中の典型判断

- **MB-002/003/004 manager/pregame/farm 解放**: §1 共通 DoD + subtype 固有を確認、特に manager の発言引用一致、pregame の予想明記
- **MB-005 chain of reasoning promote**: §1 共通 DoD 5（のもとけらしさ）に直接効く改善。canary smoke で 3 要素が本文に入るか確認
- **MB-006/007 X 投稿 ON**: §2 全条件満たすこと、特に MB-005 prod 適用 2 週間以上事故 0 前提
- **MB-019 canary-team-stats promote/kill**: §1 DoD に抵触する回帰がなければ promote、あれば kill

### Phase 2 への昇格判断

- MB-P2-05〜09（notice / recovery / social / player / general publish 解放）: §1 column と同じ基準で延期
- MB-P2-10（manager / pregame / farm 等 X 解放）: §2 で column と同じ基準で延期

---

## 5. 未確定 threshold（user 調整余地）

以下は Claude が保守値で draft した初期値。運用実績 2〜4 週間見てから user が調整:

| 項目 | 初期値 | 備考 |
|---|---|---|
| 解放前 7 日事故ゼロ条件 | 7 日 | 短すぎれば 14 日に延長 |
| thin_body 週次許容 | 3 件 | 実績で調整 |
| title_body_mismatch 週次許容 | 3 件 | 実績で調整 |
| 関連記事挿入率 | 80% | 100% は strict 過ぎる可能性 |
| X 解放前 publish 事故ゼロ期間 | 14 日 | 保守的、短くする余地あり |
| 即時 rollback 閾値（24h 10 件） | 10 件 | 軸別 baseline 出たら再評価 |
| 連続事故日数 | 3 日 | 2 日でも厳しすぎず |

---

## 6. 関連

- MVP 成立条件: `CLAUDE.md §MVP 定義`
- Phase 1 リリース条件: `CLAUDE.md §MVP 定義 §Phase 1 リリース条件`
- 継続監査ループ（A/B/C 軸）: `master_backlog.md §継続監査ループ`
- 判断履歴: `docs/handoff/decision_log.md`
- 日次運用: `docs/daily_ops_checklist.md`
- 実環境スナップショット: `master_backlog.md §6`
