# Decision Log — yoshilover

**目的**: いつ / 何を / なぜ 決めたか / 誰が を 1 行で残す。過去判断の追跡性と、判断が覆るときの根拠再検証に使う。

**運用**:
- 新しい判断が出た時点で 1 エントリ追記（Claude が追記する）
- エントリは **時系列降順**（最新が上）
- 覆った判断は `[REVERSED: YYYY-MM-DD]` を付け、撤回理由を書く
- 既存 docs / CLAUDE.md / master_backlog の変更 commit とセット運用

---

## フォーマット

```markdown
### YYYY-MM-DD  判断タイトル

- **判断**: 何を決めたか（1〜2 行）
- **なぜ**: 根拠 / 代替案と比較した理由
- **誰が**: user / Claude / Codex / 共同
- **影響**: 関連 file / チケット / 環境変数など
```

---

## エントリ

### 2026-04-21  quality-gmail の source 読取を WSL 実行依存から UNC 直読みに切替

- **判断**: `quality-gmail` は `wsl.exe bash -lc` を使って source JSON を取りに行かず、Windows 側から `\\\\wsl.localhost\\Ubuntu\\...\\logs\\quality_monitor\\` を直接読んで 4 行メールを組み立てる。fresh は `[src:qm]`、stale は `[src:stale]`、usable log 不在時は `[src:none]` を subject に付け、無音失敗を避ける
- **なぜ**: automation 実行時に `Wsl/Service/CreateInstance/E_ACCESSDENIED` が発生し、source JSON 取得失敗の結果 Gmail が未送信になっていたため。Windows shell からの UNC 直読は同環境で成功を確認済み
- **誰が**: user 要請に対して Claude が修正
- **影響**: quality-gmail automation prompt、baseballwordpress `current_focus.md` / `master_backlog.md` / `runbooks/quality_monitor.md`、wordpressyoshilover `doc/029-quality-progress-digest-formalization.md`

### 2026-04-21  現場自走化のための ticket 在庫 031-035 と fire 順を固定

- **判断**: `031 / 030 / 032 / 033 / 034 / 035` を自走在庫として追加し、現場既定 fire 順を `031 -> 030 -> 032 -> 033 -> 034` に固定する。`029` は `027 canary success` 後 gate を維持し、`035` は residual fail が残る時だけ fire する条件付き reserve とする
- **なぜ**: `027 canary` の DNS blocker は user 判断に閉じている一方、本文品質改善は DNS と独立に前進できる。field manager が user relay なしで次便を決められるよう、gate ticket と品質本線 ticket を backlog として先に固定する必要があるため
- **誰が**: user 方針を Claude が具体化
- **影響**: wordpressyoshilover `doc/030-035*.md` / `doc/README.md`、baseballwordpress `docs/handoff/current_focus.md` / `docs/handoff/master_backlog.md`

### 2026-04-21  Claude/Codex 運用の accept 追認と commit 直列化を固定

- **判断**: Codex の JSON 報告は accept 根拠にせず、毎回 `git log --stat` / `git status --short` / 必要な grep または file check で追認する。minimum-diff を守るため不可触リストを毎 prompt に明示し、doc-only 便を連打せず実装便を必ず挟む。commit 便は常に直列で流す
- **なぜ**: staged 残留や scope drift、`.git/refs/heads/master.lock` 衝突の前例が出ており、Codex の自己申告だけでは accept と完了判定が甘くなるため
- **誰が**: Claude の現場反省を user が採用、ChatGPT役が整理
- **影響**: baseballwordpress `AGENTS.md` / `CLAUDE.md` / `docs/handoff/agent_operating_model.md` / `docs/handoff/current_focus.md`

### 2026-04-21  `go` を聞きすぎない、既定は Claude が前へ進める

- **判断**: docs-only / read-only / 可逆 / 既定方針内 / コスト増なしの便は、user に `go` を聞き直さず Claude が進める。user に上げるのは stop / hold / publish / rollback / 不可逆変更 / 方針分岐 / コスト増だけに寄せる
- **なぜ**: 会議室側には別の仕事があり、毎便 `go` を聞くと user が transport と確認装置に戻ってしまうため
- **誰が**: user 方針 + Claude 整理
- **影響**: baseballwordpress `AGENTS.md` / `CLAUDE.md` / `docs/handoff/agent_operating_model.md` / `docs/handoff/current_focus.md`

### 2026-04-21  会議室ループ禁止、次便は必ず現場便へ落とす

- **判断**: 同じ論点で docs-only / read-only 整理が 1 便続いたら、次便は必ず現場便(Codex 実装便 / automation 更新便 / read-only 観測便 / smoke run 便)にする
- **なぜ**: 会議室側で考え続けると runtime が動かず、user が「両方をうまく動かせない」と感じるため。自律運用は整理より現場の bounded action を優先する
- **誰が**: user 方針 + Claude 整理
- **影響**: baseballwordpress `AGENTS.md` / `CLAUDE.md` / `docs/handoff/agent_operating_model.md` / `docs/handoff/current_focus.md`

### 2026-04-21  Claude -> Codex exec bridge と commit 責任を恒久ルールとして固定

- **判断**: `go` 後の Claude -> Codex 実行は `codex exec --full-auto --skip-git-repo-check -C <主 workspace>` を既定とし、Claude は fire 後 block-wait せず short status で停止する。accept 後の `git add / commit / push` は Codex が担当し、runner 改修が automation prompt の既定値や意味に影響する場合は automation 更新便または観察理由の明記を必須とする
- **なぜ**: `go` の意味だけでは runtime まで届かず、ad-hoc 実行・commit・automation 反映 gap の責任境界が曖昧だったため。exec bridge を恒久ルール化して user relay を減らす
- **誰が**: user 方針 + Claude 整理
- **影響**: baseballwordpress `AGENTS.md` / `CLAUDE.md` / `docs/handoff/agent_operating_model.md` / `docs/handoff/current_focus.md`

### 2026-04-19  CODEX の独断依頼書起票を revert（ポリシー再確認）

- **判断**: CODEX が独断で作成した `docs/handoff/codex_requests/2026-04-19_36.md`（commit `36ae20a`）を `git revert`。revert commit `c4e17e8` を origin/master に push
- **なぜ**: 依頼書起票は Claude 専任、CODEX は実装のみ（3者体制の核）。CODEX に spec を書かせると判断の独立性が消える
- **誰が**: user 判断 + Codex 実行
- **影響**: `feedback_codex_no_request_drafts.md` に具体事例追記。以後 Q1-Q7 調査は Claude が inline prompt で書き直す

### 2026-04-19  記事構造監査（C 軸）を継続監査ループに追加

- **判断**: 継続監査を 2 軸（本文精度 / ポスト精度）から 3 軸へ拡張。C 軸は Claude が実記事を subtype ごとに sampling で読み、構造的妥当性を判定
- **なぜ**: 5 軸 audit（検出軸）では捕まえられない「記事の作り方そのものの適切性」を人間の目で見る必要がある
- **誰が**: user 指示 + Claude 実装
- **影響**: CLAUDE.md §継続監査ループ / master_backlog.md §継続監査ループ / memory `feedback_autonomous_improvement_proposals.md`

### 2026-04-19  CODEX 依頼は inline prompt が既定、formal file は必要時のみ

- **判断**: `docs/handoff/codex_requests/YYYY-MM-DD_NN.md` を毎回作らない。inline prompt を既定にするが、`go` の後は user relay ではなく Claude から Codex へ進める前提とする
- **なぜ**: 依頼書ファイル化のオーバーヘッドが大きく Claude Max5 消費が増える。チケット管理は `master_backlog.md` の 【】→【×】で十分
- **誰が**: user 指示 + Claude
- **影響**: CLAUDE.md §CODEX への指示 / memory `feedback_codex_prompt_inline.md`

### 2026-04-20  `go` の意味を Claude から Codex への進行許可に固定

- **判断**: `go` は Claude が Codex へ次の実行導線を進めてよい許可とする
- **なぜ**: `go` の意味を一つに固定し、運用を前へ進めやすくするため
- **誰が**: user 方針 + Claude
- **影響**: baseballwordpress `AGENTS.md` / `agent_operating_model.md` / wordpressyoshilover `AGENTS.md`

### 2026-04-20  Claude -> Codex の直接実行パス確認を quality-gmail 差し替えより先に置く

- **判断**: `quality-gmail` の prompt 差し替えより先に、`codex --help` / `codex exec --help` を read-only で確認し、Claude -> Codex の ad-hoc 直接実行パスを固定する
- **なぜ**: 直接実行パス自体は存在するが未使用で、forward の手動穴は ad-hoc 便だけ残っているため。ここを先に塞いだ方が以後の `go` が runtime まで届きやすい
- **誰が**: Claude 調査 + user 方針
- **影響**: baseballwordpress `current_focus.md` / `master_backlog.md`

### 2026-04-19  master_backlog.md を単一ソース化、OPEN.md は bug 台帳に再定義

- **判断**: release 総作業表を `docs/handoff/master_backlog.md` に集約（20 本 Phase 1 + 18 本 Phase 2 + 継続監査 + 既完了）。OPEN.md は発見 bug の台帳に限定、release 進捗判定には使わない
- **なぜ**: 3者体制に足りないのは「人」ではなく master backlog / 編集方針 / release gate の 3 仕組み。OPEN.md では bug と release blocker が混在し判定困難
- **誰が**: user 判断 + Claude 起票
- **影響**: master_backlog.md 新設 / CLAUDE.md §運用ルール §判断原則 / memory `project_operational_gaps.md` `feedback_master_backlog_first.md`

### 2026-04-19  3 者体制（Codex / Claude / user）明文化、user 責任範囲を列挙

- **判断**: user 責任範囲を列挙（MVP 定義確定 / 「今やらないこと」/ subtype 解放順 / promote-kill-hold / 本番反映権限 / publish・X 最終責任）
- **なぜ**: Claude / Codex が独断で release / X 解放を進めるのを防ぐ。user は「依頼者」ではなく「最終責任・判断役」
- **誰が**: user 明示
- **影響**: CLAUDE.md §役割分担 / memory `role_split.md` 2 者 → 3 者へ更新

### 2026-04-19  Phase 1 リリース条件を 7 項目に確定（perfect でなくていい、まず release）

- **判断**:
  1. publish 5 subtype（postgame / lineup + manager / pregame / farm）
  2. X 自動投稿 postgame / lineup のみ ON（`X_POST_DAILY_LIMIT=10` 維持）
  3. 一次情報リンク継続
  4. audit-notify-6x 稼働継続
  5. fact check pipeline 継続
  6. prompt 改善 1 本（no_opinion 対策）
  7. 運用 blocker 解消（T-001 / T-017 / T-024）
- **なぜ**: のもとけを 1 人+AI で再現する MVP 視点。機能単品でなく運用ループ閉鎖で判定。20-30 本/日は初期非現実、10 本/日から始める
- **誰が**: user 判断
- **影響**: CLAUDE.md §MVP 定義 §Phase 1 リリース条件 / master_backlog.md MB-001〜MB-020

### 2026-04-19  CLAUDE.md は policy / 運用ルール 専用、現在値は記載しない

- **判断**: CLAUDE.md に書くのは policy / 運用ルール / 判断基準 / 既定値 / 役割分担 / コスト制約 / MVP 定義。実環境の現在値（revision 番号 / env flag の現在の on/off）は書かない
- **なぜ**: 既定値と prod 実態が乖離しても（例: `ENABLE_ENHANCED_PROMPTS` 既定 0 / prod 1）、それは deploy 時判断の結果で CLAUDE.md 更新理由ではない
- **誰が**: user 明示
- **影響**: CLAUDE.md §CLAUDE.md の用途 / memory `feedback_no_claudemd_state_sync.md` / 実環境スナップショットは master_backlog.md §6 に集約

### 2026-04-18  第35便スコープ確定（`/audit_notify` + `audit-notify-6x` Cloud Scheduler）

- **判断**:
  - 軸 4+pipeline（`title_body_mismatch` / `thin_body` / `no_opinion` / `no_eyecatch` / `pipeline_error`）
  - `repetition` 軸は先送り
  - HTTP endpoint は `/audit_notify` 新設（`/fact_check_notify` 拡張でない）
  - 実行経路は Cloud Scheduler 専用 job（Remote Trigger / OIDC 案は破棄）
  - 1 日 6 回 JST 11/13/15/17/20/23（cron `0 2,4,6,8,11,14 * * *` UTC）
  - `AUDIT_OPINION_USE_LLM=0` 既定（ルールベース）
- **なぜ**: `/run` と同設計に乗せると OIDC 制約で詰まる。canary tag は deploy smoke 限定で本番定期実行に使わない。1 時間制約（Remote Trigger）の名残りは採用せず CLAUDE.md 当初方針の 6 回を維持
- **誰が**: user 判断 + Claude + Codex ヒアリング
- **影響**: 依頼書 `docs/handoff/codex_requests/2026-04-18_35.md` / Prod revision `00143-luj` / Scheduler `audit-notify-6x`

### 2026-04-18  ENABLE_ENHANCED_PROMPTS を prod で 1 に deploy

- **判断**: CLAUDE.md 既定 0 のまま、prod 環境のみ 1 に切り替え
- **なぜ**: deploy 時の判断。Flash prompt enhancement を本番適用することで記事品質改善を狙う。既定値と実態乖離は CLAUDE.md 更新理由にしない
- **誰が**: user + Codex
- **影響**: master_backlog.md §6 実環境スナップショット / CLAUDE.md は更新しない

### 2026-04-18  Flash prompt 3 点セット方針確定（cost 増なし）

- **判断**: 採用 3 点（全て cost 増ゼロ）:
  1. 材料境界明示（材料内は自由 / 材料外は推測禁止）
  2. chain of reasoning 強制（事実 → 解釈 → 感想）
  3. subtype 別 temperature
- **なぜ**: few-shot examples / 2 段階生成 / rejection+retry は cost 増 or SPOF で制約違反。cost 中立 3 点に絞る
- **誰が**: Claude 起案 + user 承認
- **影響**: MB-005（chain of reasoning）/ MB-P2-03（subtype 別 temperature）。材料境界明示は次便候補

### 2026-04-18  Gemini Pro 切り替え却下（Flash 維持）

- **判断**: API コスト理由で Pro 切替却下、Gemini Flash 維持
- **なぜ**: 無料枠優先の本体コスト制約
- **誰が**: user 判断
- **影響**: CLAUDE.md §本体コスト制約 / 以後の prompt 改善はすべて cost 中立縛り

---

## 未記録の過去判断（遡及候補）

必要に応じて Claude が拾う:

- T-022 週末 18-19 時 scheduler gap 解消（2026-04-18）
- T-023 平日 18-19 時 WONTFIX 根拠（2026-04-18）
- T-010 `source_reference_missing` 解消（過去）
- Xserver 鍵漏洩対応（未完、user 手動タスク）
