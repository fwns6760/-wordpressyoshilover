# PUB-002 少量手動公開と記事品質改善レーン

## 後継 ticket(2026-04-25 21:55 update)

本 ticket は **少量手動公開フェーズ** の起点 ticket。完了後の自動化は以下に分岐:

- **PUB-004 guarded-wordpress-publish-runner**: WordPress publish の autonomous runner(Red 以外 publish、Yellow も改善ログ付きで publish、daily 10 / burst 3、user 確認原則不要)
- **PUB-005 x-sns-post-gate**: X / SNS POST の strict gate(Green only + user 確認 fixed、autonomous POST なし)
- **PUB-002-B/C/D**: Green/Yellow 候補を増やす品質改善(missing-source / subtype-unresolved / long-body)、PUB-004 安定後の品質 uplift

WordPress publish と X / SNS POST は **lane 分離**(同 draft でも厳しさ違う)。判定 contract は PUB-002-A、適用厳しさは PUB-004 / PUB-005 で別管理。

## 現運用(2026-04-25 21:55 以降、本 ticket は **親 runbook**)

本 ticket は **親 runbook**(段階公開フェーズの起点)。
**現在の実行 ticket は PUB-004 / PUB-005**。

| 適用先 | 現運用 ticket | 主要パラメータ |
|---|---|---|
| **WordPress publish** | **PUB-004** | daily cap 10 / burst cap 3 / Red のみ refuse / Green+Yellow publish / user 確認原則不要 |
| **X / SNS POST** | **PUB-005** | Green only + 追加 X-side strict / user 確認 fixed / autonomous POST なし |

判定 contract = `PUB-002-A`(WP / X で適用厳しさ別)。
本 ticket 内の `publish_volume` / `workflow` / `user_interface` 節は **旧手動運用フェーズの記録**(参考、現在の運用は PUB-004 / PUB-005 を見ること)。

## priority

P0.5 / P1 HIGH(本日 publish 8 件 達成、今後 PUB-004 へ移行)

## priority_reason

088 により 1 本目の公開と publish-notice メール着信は成功済み。
次の本線は「自動公開」ではなく、「良い記事だけを少量手動公開しながら品質を上げること」。
ここを決めないと、現場が 093 / 095 / HALLUC-LANE / CI / front などに分散し、公開開始の優先順位が曖昧になる。

PUB-002 は公開開始の主線であり、093 cron 復旧や 095 cron 化より優先して扱う。
093 は重要だが、手動公開は 093 なしでも進められる。
095 と `RUN_DRAFT_ONLY=False` は PUB-002 が数日安定してから。

## owner

Claude Code

## type

ops / launch runbook / editorial quality gate

## status

READY after 088 smoke success(2026-04-25 10:15 JST 達成)

## current_state

- 63405 は publish 済み
- public URL は 200(`https://yoshilover.com/63405`)
- 088 publish-notice smoke は sent
- Gmail 着信を user が確認済み(2026-04-25)
- HALLUC-LANE-001 は着地済み
  - extract
  - detect-stub
  - approve YAML
  - backup
  - apply dry-run
- HALLUC-LANE-002 は未実装(Gemini 実検出はまだ無い)
- 093 cron tick recovery は watch 中 / pending
- 095 publish-notice cron activation は 088 + 093 後のみ
- `RUN_DRAFT_ONLY` は維持(自動公開はまだしない)

## purpose(初版、2026-04-25 12:00 起票時点)

YOSHILOVER を段階公開へ進める。
**(初版当時)**「一括公開や自動公開ではなく、1 記事ずつ選び、良い記事だけを少量手動公開する」。
4/17 事故と同質のリスクを避けながら、公開運用を止めずに文章品質を上げる。

→ **現在(2026-04-25 21:55 以降)**: 「自動公開ではなく」「1 記事ずつ」は **旧フェーズの方針**。
「Red 以外は autonomous WP publish(PUB-004、daily 10 / burst 3)」「X / SNS は Green only + user 確認(PUB-005)」へ移行済。

## launch_priority_order(2026-04-25 21:55 以降)

1. **PUB-004 guarded-wordpress-publish-runner**(WP publish 主線、Red 以外 publish、daily 10 / burst 3、autonomous)
2. **PUB-005 x-sns-post-gate**(X / SNS lane、Green only + user 確認 fixed、本 ticket 完了は doc-first まで)
3. HALLUC-LANE-002: Gemini 実検出の追加(LLM 判定で G3/G7/G8 完全 verify)
4. PUB-002-B / C / D: 品質改善(missing-source / subtype-unresolved / long-body)、PUB-004 安定後
5. 093: cron tick recovery(user op = app restart)
6. 095-E: WSL cron reboot resilience(user op = PC reboot)
7. 073/074/075 dotenv load 横展開(各 sender live 化時)
8. `RUN_DRAFT_ONLY=False` 検討(最後)
9. front / plugin 改修(別 Claude owner)

補足:
- 093 は重要だが、手動公開開始の絶対ブロッカーではない
- 095 は 088 + 093 の後
- `RUN_DRAFT_ONLY=False` は最後
- front / plugin は別 Claude owner

## keep_good_parts

- fact-first title 方針
- スタメン表、打順、守備位置、選手名
- 参照元リンク / source block
- publish-notice メール通知
- draft-first 運用
- HALLUC-LANE-001 の extract / approve YAML / backup / apply dry-run 土台

## improve_parts

- 根拠が怪しい数字、スコア、打率、日付
- source にない引用や断定
- `どう見る？` / `本音は？` など本文で浮く見出し
- AI っぽい一般論
- 関連記事やサイト部品が本文に混ざって見える状態
- source と本文の対応が弱い記事

## article_judgment

### Green: 公開可

- title と body が一致
- source URL がある
- 数字・選手名・引用・スコアが怪しくない
- 冒頭だけで何の記事か分かる
- 参照元が本文の主張を支えている

### Yellow: 修正後公開可

- 記事の核は正しい
- 文章が薄い
- 見出しが浮く
- 数字確認が必要
- 軽い修正で公開できる

### Red: 公開しない

- source にない具体事実
- 別記事混入
- 未確認引用
- 試合結果 / 選手状態 / 故障 / 登録抹消が怪しい
- 4/17 事故と同質リスク

---

## 旧手動運用 (PUB-004 移行前、2026-04-25 21:55 以前、参考用)

以下 3 節(`workflow` / `publish_volume` / `user_interface`)は **旧フェーズの記録**。
現在の WP publish 運用は **PUB-004**、X / SNS POST 運用は **PUB-005** を見ること。

### workflow(旧、参考)

1. Claude が次の公開候補を 1 本だけ選ぶ
2. HALLUC-LANE-001 extract で title / body / source を確認
3. title / source / 数字 / 引用 / 冒頭を確認
4. Green / Yellow / Red 判定を作る
5. user には候補 1 本だけ提示し、Green / Yellow / Red の最終判断だけ求める
6. Green は WP admin で手動 publish
7. Yellow は軽く修正してから publish
8. Red は hold
9. publish-notice メール着信を確認
10. 気になった悪い型を記録し、template / prompt 改善へ回す

→ 現在は **PUB-004-A dry-run evaluator** + **PUB-004-B guarded live publish** が autonomous で同 flow をバッチ処理(Step 1-9 を Claude / runner 自動化、Step 10 = Yellow 改善ログを `logs/guarded_publish_yellow_log.jsonl` に記録)。

### publish_volume(旧、参考)

- (旧) HALLUC-LANE-002 までは 1 日 1 本、多くても 3 本まで
- (旧) 376 drafts 一括 publish 禁止
- (旧) 自動 publish 禁止
- (旧) `RUN_DRAFT_ONLY=False` 禁止

→ 現在は **PUB-004 daily cap 10 / burst cap 3 / mail burst 5 通超で分割 / Red のみ refuse**。
`RUN_DRAFT_ONLY=False` 禁止 / 376 drafts 一括禁止 は引き続き有効。

### user_interface(旧、参考)

(旧) user に候補 1 本提示 + `publish` / `hold` 1 ワード判断。

→ 現在は **PUB-004 で user 確認原則不要**(Red 以外 autonomous publish)。
user 判断が必要なのは Red に近い危険記事 publish 時のみ(本 runner は Red を refuse するので通常発生しない)。
**X / SNS POST だけは PUB-005 で user 確認 fixed**(approve / reject 1 ワード)。

## acceptance(本 ticket、親 runbook)

(2026-04-25 21:55 update)本 ticket は **親 runbook として完了済**、現在の実行 ticket は PUB-004 / PUB-005。

1. ✓ PUB-002 が公開開始の起点 ticket として完了、後継 PUB-004 / PUB-005 起票済
2. ✓ 旧手動運用フェーズ(1〜3 本 / 日)は本日 publish 8 件達成で次フェーズへ移行
3. ✓ workflow 10 step は PUB-004-A/B が autonomous 化
4. ✓ article_judgment Green / Yellow / Red は PUB-002-A に正本化、適用厳しさは PUB-004 / PUB-005 で別管理
5. ✓ user_interface は PUB-004 で「原則不要」、PUB-005 で「user 確認 fixed」に分離
6. ✓ 4/17 事故同質リスクは PUB-002-A R8 として固定、PUB-004 で refuse

## stop 条件

- HALLUC-LANE-001 apply dry-run で抽出できない異常な draft が連続したら、別 narrow ticket(PUB-002-A 等)で extract 改善を起票
- Yellow 修正候補で source の追加取得が必要な場合は、user 判断 1 件で進める
- Red を user が誤って publish しようとした場合は、Claude 側で「Red 警告」を 1 行で返し再判断を促す
- 1 日 3 本超の publish 要求が来たら本 ticket scope 外として escalate

## 関連 file

- `/home/fwns6/code/wordpressyoshilover/doc/088-publish-notice-real-send-smoke-and-mail-gate-activation.md`(088 smoke、本 ticket の前提)
- `/home/fwns6/code/wordpressyoshilover/doc/093-automation-tick-recovery-and-workspace-reattach.md`(cron 復旧、本 ticket の後続)
- `/home/fwns6/code/wordpressyoshilover/doc/095-publish-notice-cron-activation.md`(095 cron 化、本 ticket 安定後の判断)
- `/home/fwns6/code/wordpressyoshilover/src/tools/run_pre_publish_fact_check.py`(HALLUC-LANE-001 lane CLI)
- `/home/fwns6/code/baseballwordpress/docs/handoff/session_logs/2026-04-25_088_publish_notice_smoke_close_candidate.md`(088 close 記録)

## 不可触

- automation.toml / scheduler / .env / secrets
- WP admin の追加 publish(本 ticket workflow Step 6 以外)
- `RUN_DRAFT_ONLY` flip
- front / plugin / build artifacts
- HALLUC-LANE-002(別 ticket、本 ticket は 001 dry-run 土台のみで運用開始)
