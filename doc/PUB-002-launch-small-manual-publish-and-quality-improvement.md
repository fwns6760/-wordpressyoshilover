# PUB-002 少量手動公開と記事品質改善レーン

## priority

P0.5 / P1 HIGH

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

## purpose

YOSHILOVER を段階公開へ進める。
一括公開や自動公開ではなく、1 記事ずつ選び、良い記事だけを少量手動公開する。
4/17 事故と同質のリスクを避けながら、公開運用を止めずに文章品質を上げる。

## launch_priority_order

1. **PUB-002**: 少量手動公開と記事品質改善レーン
2. HALLUC-LANE-002: Gemini 実検出の追加
3. 093: cron tick recovery
4. 095: publish-notice cron activation
5. 073/074/075 dotenv load 横展開
6. `RUN_DRAFT_ONLY=False` 検討
7. front / plugin 改修

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

## workflow

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

## publish_volume

- HALLUC-LANE-002 までは 1 日 1 本、多くても 3 本まで
- 376 drafts 一括 publish 禁止
- 自動 publish 禁止
- `RUN_DRAFT_ONLY=False` 禁止

## user_interface

user に広く聞かない。
候補を複数並べて選ばせない。
Claude が候補を 1 本に絞り、user には以下だけ聞く。

```text
次の公開候補は post_id=XXXXX です。
判定: Green / Yellow / Red
理由: <1-3行>
公開するなら publish、止めるなら hold と返してください。
```

(本 ticket 受領時の user 提供 template、user_interface 節は上記までで原文準拠)

## acceptance(本 ticket、launch runbook)

1. PUB-002 が公開開始の主線として明記され、093 / 095 / HALLUC-LANE-002 / front / plugin より優先順位が上
2. 1 日の publish_volume(1〜3 本)が固定
3. workflow 10 step が固定
4. article_judgment Green / Yellow / Red の 3 段階基準が固定
5. user_interface が「候補 1 本 + Green/Yellow/Red 判定 + 1 ワード返答」に固定
6. 4/17 事故と同質リスクを Red として明示禁止

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
