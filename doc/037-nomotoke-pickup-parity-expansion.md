# 037 — のもとけ比 pickup parity expansion

**フェーズ：** pickup 条件の parity 拡張
**担当：** Codex A
**依存：** 028 impl, 029, 036 accepted, 038 accepted

---

## why_now

- のもとけ比で fixed lane の pickup が弱く、Draft candidate 発火源が限定されている。
- 036 (prompt hardening) と 038 (ledger / promotion loop) が先に整うことで、pickup を広げても「何を直すか」が ledger で可視化され、collect wide / assert narrow の境界が運用で保てる。
- 028 impl が 4 family の fixed lane intake を通した後、037 は parity expansion を加える。

## purpose

- `collect wide / assert narrow` を pickup 条件に落とし込み、のもとけ比で弱い candidate 発火を改善する。
- 広く拾い、T1 でだけ Draft を断定し、duplicate は candidate_key で抑え、rumor / unknown は fixed lane に直接入れない。

## scope

### pickup source 種

- 広く拾う: `official web` / `npb.jp` / `major RSS` / `team X` / `reporter X` / `program table` / `farm info` / `TV・ラジオ発言` / `comment quote` / `player stats feed`
- 028 の T1-T3 trust tier を維持し、断定は T1 のみで行う。

### parity expansion 用 family 候補

- 028 の 4 family に加えて、次の family 候補を parity expansion 対象にする。
  - `lineup_notice`
  - `comment_notice`
  - `injury_notice`
  - `postgame_result`
  - `player_stat_update`
- ただし、family を増やしても fixed lane に直接入るのは trust / subtype 条件を満たすものだけとする。

### event_family と candidate_key

- 028 の 4 family (`program_notice` / `transaction_notice` / `probable_pitcher` / `farm_result`) を土台に、parity expansion 用 family 候補を追加する。
- family 別 `candidate_key` は 028 と disjoint で追加し、既存 key のフォーマットを壊さない。

### duplicate 抑制

- 同一 `candidate_key` の別 source は新規 Draft を作らず、evidence bundle に吸収する。
- daily duplicate rate は 10% 未満を目標とする。

### trust + subtype route

- trust tier と subtype の組で fixed lane / agent lane を振り分ける。
- `rumor` / `unknown` は fixed lane に直接入らない(必要なら agent lane 経由のみ、本便 scope では route のみ定義)。
- parity expansion 用 route outcome `deferred_pickup`(pickup 成功 + Draft 未生成)を追加する。

### pickup boundary

- `comment_notice`
  - fixed lane に入れてよいのは `公式 source` / `主要媒体引用` / `TV・ラジオ発言` までとする。
  - 本文先頭近くに `誰が / どこで / 何を言ったか` を必ず明示する。
- `injury_notice`
  - fixed lane で断定してよいのは `球団公式発表 + 監督・コーチコメントまで` とする。
  - `主要紙報道` は pickup してよいが、fixed lane 断定には使わず agent lane 候補へ回す。
- `player_stat_update`
  - 毎日量産しない。
  - `記録更新` / `昇格圏` / `再訪理由あり` の時だけ Draft 候補にする。
- `lineup_notice` / `postgame_result`
  - 試合中心の再訪性を支える primary family とし、Phase 1 で優先して pickup を厚くする。

### taxonomy

- 親カテゴリ `読売ジャイアンツ` を維持する。
- 細分類は tag で持つ(014 / 019 準拠)。

## success_criteria

- baseline より日次 Draft candidate 数が有意に増加する。
- day-level の目標は `25 Draft candidates / day` とする。
- daily duplicate rate が 10% 未満。
- `rumor` / `unknown` は fixed lane に直接入らない。
- replay で candidate 数増加、`candidate_key` で duplicate 抑制、route が一意であることが観測できる。

## non_goals

- reserve 前倒し(020 / 021 / 023-026 / 035)
- publish path 変更
- 新 subtype 追加 / 新 source trust tier 追加
- AI lane 実装 / X API 実装 / SNS 文面自動生成
- `automation.toml` / scheduler / env / secret / mail 変更
- Gemini 以外 LLM 追加

## acceptance_check

- replay で candidate 数が baseline より増加する。
- `candidate_key` で duplicate が抑制される。
- route が一意(同一 candidate に対して fixed / agent / deferred_pickup のどれか 1 つ)。
- `git log --stat` / `git status --short` / tests pass / 追加 test file 実在で追認できる。
- 037 fire 時点で 036 / 038 / 028 impl / 029 が全て accepted であることを追認する。

## TODO

【】pickup source 種(official / npb.jp / major RSS / team X / reporter X / program / farm)を固定する
【】028 の 4 family に加え、parity expansion 用 family 候補を固定する
【】`TV・ラジオ発言` / `comment quote` / `player stats feed` を pickup source に追加する
【】`lineup_notice` / `comment_notice` / `injury_notice` / `postgame_result` / `player_stat_update` を family 候補として固定する
【】family 別 `candidate_key` を 028 と disjoint で追加する
【】comment / injury / stat の pickup boundary を固定する
【】`comment_notice` は `誰が / どこで / 何を言ったか` を本文先頭近くに明示する方針を明記する
【】`injury_notice` は `球団公式発表 + 監督・コーチコメントまで` を fixed lane 断定範囲と明記する
【】`player_stat_update` は `記録更新 / 昇格圏 / 再訪理由あり` の時だけ候補化すると明記する
【】daily duplicate rate 10% 未満を目標として固定する
【】day-level 目標 `25 Draft candidates / day` を固定する
【】trust tier + subtype の route 判定ルールを固定する
【】`deferred_pickup` route outcome を追加する
【】`rumor` / `unknown` を fixed lane に直接入れない方針を明記する
【】親カテゴリ `読売ジャイアンツ` 維持と細分類 tag を明記する

## 成功条件

- pickup source 種と candidate_key が ticket 本文で固定されている。
- duplicate 抑制と route 一意性が明記されている。
- Codex A が pickup 層実装と tests 追加へそのまま進める粒度になっている。
- 037 fire 条件(036 / 038 / 028 impl / 029 accepted)が ticket 単体で読める。
