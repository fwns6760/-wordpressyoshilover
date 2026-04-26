# 066 — project one-pager と anti-repeat memo の固定

**フェーズ：** session 復元の短縮 / 同じ迷いの再発防止
**担当：** Claude Code(contract owner、doc-only)
**依存：** 既存 handoff 群(current_focus / master_backlog / decision_log / session_logs / CLAUDE.md / AGENTS.md)
**状態：** READY(doc-only、実装 fire なし)

## why_now

- 新 session 起動時に、現在地(current_focus)と全体道筋(master_backlog)と採用判断(decision_log)が並んでいるが、**「このプロジェクトは何か」**を 1 枚で復元する紙がない。
- 同じ種類の迷い(メール来ない → WSL 全停止と誤診 / 044 と 042 の主因取り違え / 「全部止まっている」と「一部経路障害」の混同 / MD にある内容を user に再確認 / 軽い迷いを user に上げすぎる)が session をまたいで再発している。
- user が毎回「それ MD にある」と補正する負荷をなくしたい。同じ迷いを復元する健忘録を 1 枚固定する。

## purpose

- プロジェクトの 1 枚要約を残す(session 復元の最短化)。
- 同じ迷いを繰り返さないための健忘録を残す(過去の症状 → 実主因 → 最初に見る場所)。
- user が「それ MD にある」と補正しなくてよい状態を作る。

## scope

### deliverable 1: `docs/handoff/project_one_pager.md`

- 1 ページ相当、箇条書き中心。
- 項目固定(7 節):
  1. プロジェクトの目的
  2. 成功条件
  3. 役割固定
  4. 不可侵ルール
  5. 現在の本線
  6. 後回しにしているもの
  7. 現在の主ボトルネック
- current_focus のコピーにしない。「このプロジェクトは何か」を最短で復元する紙にする。
- 「現在の本線」「主ボトルネック」は session ごとに古くなる前提で、**最小限の更新で再生できる**粒度に留める。

### deliverable 2: `docs/handoff/runbooks/anti_repeat_memo.md`

- 形式固定(1 entry = 5 節):
  - 症状
  - 最初に勘違いしたこと
  - 実際の主因
  - 次回いちばん最初に見る場所
  - user に聞いてよい条件
- 最初に入れる candidate 5 件:
  1. メールが来ない
  2. 044 と 042 の主因取り違え
  3. 「全部止まっている」と「一部経路障害」の混同
  4. MD にある内容を user に再確認してしまう
  5. internal な悩みを user に上げすぎる

### 既存 handoff との境界

- `current_focus.md` = 今の状態
- `master_backlog.md` = 全体道筋
- `decision_log.md` = 採用判断
- `session_logs/` = 当日の詳細
- `project_one_pager.md` = このプロジェクトは何か
- `anti_repeat_memo.md` = 次回どこから見れば同じ迷いを防げるか

## success_criteria

- 新 session で「このプロジェクトは何か」を 1 枚で復元できる(project_one_pager を読めば足りる)。
- 過去に詰まった 5 症状について「次回最初に見る場所」が anti_repeat_memo で即参照できる。
- user が「それ MD にある」と補正する回数が減る。
- handoff 道具箱の役割が 6 枚で重複しない(current_focus / master_backlog / decision_log / session_logs / project_one_pager / anti_repeat_memo)。

## non_goals

- 大きい新設計 doc
- automation / scheduler / env / secret の変更
- 実装経路変更
- blame 用の障害報告書
- docs の量産(本 ticket は 2 枚だけに抑える)

## acceptance_check

- `docs/handoff/project_one_pager.md` が 7 項目すべて箇条書きで読める。
- `docs/handoff/runbooks/anti_repeat_memo.md` が 5 候補について 5 節(症状 / 最初の勘違い / 実主因 / 次回最初に見る場所 / user に聞いてよい条件)で読める。
- `new_chat_bootstrap.md` に 2 枚への導線が 1 行ずつ追加されている。
- 6 枚の役割分担が本 ticket 本文で読める。
- 既存 handoff(current_focus / master_backlog / decision_log / session_logs)の内容を重複コピーしていない。

## fire 前提 / stop 条件

### fire 前提

- doc-only、実装 fire なし。2 枚を作って handoff に 1 行導線を足すのみ。

### stop 条件

- 2 枚のどちらかが長文化した(1 ページ相当を超えた)。
- current_focus / master_backlog / decision_log の内容を 2 枚に丸コピした。
- blame 用の障害報告書に化けた。
- 大設計 doc に拡張された。
- いずれか観測で stop、短い 2 枚へ戻す。

## 既存 ticket との関係

- 実装 / automation / scheduler / X API / delivery / content contract には一切触らない。
- 044 / 042 / 039 / 064 / 065 の routing / fire 条件を変更しない。
- 新規 ticket 起票トリガーにもしない(anti_repeat_memo は「次回最初に見る場所」を指すだけで、修正指示ではない)。
