# 改修 #4 — prompt-id cost review gate design

Date: 2026-05-02 JST
Scope: doc-only
Files: `docs/ops/POLICY.md`, `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`, this design note

## 1. Background

現状の cost review は ticket ごとの Acceptance Pack に存在するが、review 粒度は ticket 単位に寄っている。

そのため、以下が ticket 横断で揃っていない。

- どの prompt change が Gemini call 増加を作るのか
- どの prompt path が新規 mail path を生むのか
- token / API call / Cloud Run execution の上限が prompt ごとに切れているか
- `prompt_template_id` 変更と、それ以外の fallback/rescue prompt 追加が同じ gate で見られているか

`POLICY.md` §19.6 は `prompt_template_id` 変更時の cost review 必須化を既に示しているが、Pack template 側に prompt-id 分解 field が無いため、運用上は ticket summary に吸収されやすい。

## 2. Current problem

散在状態のままだと、以下のズレが起きやすい。

1. Gemini delta が ticket summary にしか書かれず、どの prompt-id が増加要因か残らない
2. mail volume impact が phase/ticket 単位で書かれ、prompt 由来の新規通知 path が埋もれる
3. token / API / Cloud Run execution の cost upper bound が per-prompt で切れず、後続 ticket と比較しにくい
4. 同一 ticket 内の「prompt change」と「non-prompt change」が混ざると、どこに Pack を当てるべきか曖昧になる

結果として、Gemini call 増加、mail 量増加、cost impact の判定基準が ticket ごとにぶれ、review quality が再現不能になる。

## 3. Proposal

### 3.1 Summary

prompt に影響する change は、ticket 単位ではなく **prompt-id 単位**で cost review を必須化する。

対象は `prompt_template_id` だけに限定しない。fixed-lane prompt、fallback prompt、rescue prompt、cache key 上の prompt variant を含む。

### 3.2 prompt-id definition

`prompt-id` は、prompt 変更の cost / mail / API / execution 影響を追跡するための安定識別子とする。

対象:

- `prompt_template_id`
- fallback / rescue / strict / relaxed などの prompt variant ID
- 明示 ID が未実装でも prompt behavior を変える path

明示 ID が無い場合も review 免除にはしない。Pack 上で provisional ID を置く。

例:

- `postgame_strict_slotfill_v1`
- `fixed_lane:weak_title_rescue`
- `src/foo.py:maybe_regenerate_summary`

### 3.3 Required per-prompt review items

各 prompt-id ごとに、最低でも以下を固定する。

- prompt-id
- activation path / touched path
- baseline Gemini calls/day
- Gemini delta upper bound/day
- prompt-id 由来 mail path
- mail volume estimate/hour
- mail volume estimate/day
- external API call estimate/day
- cost upper bound:
  - tokens/day
  - external API calls/day
  - Cloud Run executions/day

これにより、ticket-level summary は残しつつ、増減要因を prompt-id に帰属できる。

## 4. Evaluation matrix

4 軸 × 3 段階で評価する。

| stage | prompt-id attribution | Gemini delta | mail volume | cost upper bound |
|---|---|---|---|---|
| `PASS` | touched prompt-id が全部列挙済み | baseline/day と delta upper bound/day が数値で固定されている | prompt-id 由来 mail path と volume が数値で固定されている | tokens/API/Cloud Run executions の上限が数値で固定されている |
| `REVIEW` | 列挙は済みだが新規 prompt path が追加される | 増加方向だが上限は確定済み | 増加方向だが MAIL_BUDGET 内で上限は確定済み | 増加方向だが上限は確定済み、Pack 上の reason/rollback/observe plan が必要 |
| `STOP` | prompt-id 未記載、複数 prompt-id を ticket summary へ丸めた、または provisional ID すら置けない | baseline 不明、delta 不明、上限なし | mail path 不明、volume 不明、storm 上限が引けない | tokens/API/Cloud Run のいずれか不明、unbounded、または他 field と不整合 |

運用判定:

- 全 axis `PASS`: 通常 classification へ進行可
- `REVIEW` 含む: Prompt-ID Cost Review field を含む Acceptance Pack 完成まで GO しない
- `STOP` 含む: `HOLD`。user に投げず Claude が UNKNOWN 解消

## 5. Pack template injection point

注入位置は `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` の Required Fields 内、既存 `7. Gemini / Cost Impact` の直後。

追加 field 名:

- `7a. Prompt-ID Cost Review`

役割分担:

- `7. Gemini / Cost Impact`
  - ticket 全体の summary
  - 全 prompt-id 行を合算した最終値
- `7a. Prompt-ID Cost Review`
  - prompt-id ごとの分解
  - 増加要因 / 新規 mail path / API path をここで固定

必須記入項目:

- prompt-id
- Gemini delta estimate
- mail volume estimate
- API call estimate
- cost upper bound

`cost upper bound` には tokens/day、external API calls/day、Cloud Run executions/day を含める。

## 6. POLICY candidate

新設位置は `docs/ops/POLICY.md` の末尾、既存最終 section `§20` の次。

候補番号:

- `§21 Prompt-ID Cost Review Gate`

採用理由:

- `§19.6` と `§19.7` が既に cost-change review を扱っている
- ただし `§19` は audit-derived guard と設計メモ寄りで、Pack 運用の必須 field までは固定していない
- `§21` として独立させると、policy rule と Pack linkage を 1 箇所で読める

`§21` に入れるべき要素:

- prompt-id 定義
- per-prompt required fields
- 4 軸 × 3 段階 matrix
- `PASS / REVIEW / STOP` の判定規則
- violation 時の `HOLD` / GO 禁止
- Pack template の `7a` との接続

## 7. Expected effect

この改修は doc-only であり、今日の production behavior は変えない。

ただし今後の Acceptance Pack では、以下が統一される。

- Gemini call は prompt-id ごとに baseline/day と delta upper bound/day を持つ
- mail 量は prompt-id 由来 path ごとに見積もる
- token / API call / Cloud Run execution は ticket summary の前に per-prompt 上限がある
- `prompt_template_id` change と fallback/rescue prompt 追加が同じ gate で扱われる

## 8. Non-goals

この改修では行わない。

- production code change
- env / Scheduler / secret / Cloud Run mutation
- Gemini / mail runtime behavior change
- 既存 Acceptance Pack field の意味変更
- historical Packs の retroactive rewrite

## 9. Implementation note

この design は今後の Pack 起票ルールを補強するもので、今日中の運用には影響しない。

次アクションは Claude 側で、今後の Pack 起票時に `7a. Prompt-ID Cost Review` を埋める運用へ切り替えること。
