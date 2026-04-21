# 036 — Gemini 2.5 Flash 固定版レーン prompt contract hardening

**フェーズ：** 本文品質改善の upstream 固定
**担当：** Codex B
**依存：** 030, 032, 033, 034

---

## why_now

- 030 / 032 / 033 / 034 の validator は後段で fail を止める層である。
- 上流の Gemini 2.5 Flash 固定版レーン初稿 prompt が abstract lead / required block 欠落 / attribution 漏れを出し続けると、reroll と Codex repair のコストが膨らむ。
- 036 は validator の upstream で prompt contract を subtype ごとに締め、初稿の段階で fail を減らす。Codex repair は「全部書き直す」のではなく「悪いところだけ直す」minimum-diff 補修へ寄せる。

## purpose

- Gemini 2.5 Flash 固定版レーンの prompt contract を subtype 別に固定し、validator と整合させる。
- Codex repair rubric を minimum-diff に寄せ、正しい部分を温存しながら fail 箇所だけを直す。

## scope

### 対象 subtype

- `program`(番組情報)
- `notice`(公示 / transaction notice)
- `probable_starter`(予告先発)
- `farm_result`(二軍成績)
- `postgame`(試合結果、agent lane 経由でも fixed lane prompt contract を共通土台に使う)

### subtype 別 prompt contract 要素

- `required_fact_block`(032 body contract と整合する subtype 別必須 block)
- `title_body_coherence`(030 title rule と整合する subtype 別 title prefix と本文整合)
- `abstract_lead_ban`(033 fact kernel と整合する抽象 lead 禁止文言)
- `attribution_condition`(034 X attribution rule と整合する attribution 必須条件)
- `fallback_copy`(source が不足する場合の安全側 fallback 文面)

### minimum-diff repair rubric

- Codex repair は該当 block / 該当 sentence / 該当 attribution だけを対象にする。
- 正しい部分は温存し、全文再生成しない。
- 初稿 prompt と repair prompt は 1 builder 内で明示的に分岐させ、repair 側にのみ minimum-diff 注記を出す。

## success_criteria

- 観測窓で `thin_body` / `title_body_mismatch` / `abstract_lead` / `fact_missing` / `attribution_missing` の fail tag が有意に減少する。
- Gemini 2.5 Flash 初稿 -> Codex repair 1 サイクルで Draft が acceptance に近づく。
- subtype sample で required block が揃う。

## non_goals

- publish path 変更
- `status=draft` 解除
- source 拡張(037 側)
- Batch lane(023-026)前倒し
- 新 subtype 追加 / 新 source trust tier 追加
- `automation.toml` / scheduler / env / secret / mail 変更
- Gemini 以外 LLM 追加

## acceptance_check

- subtype sample で required block が揃う。
- Gemini 2.5 Flash 初稿 -> Codex repair 1 サイクルで Draft が acceptance 条件(validator pass)に近づく。
- 初稿 prompt と repair prompt の分岐が tests で観測できる。
- `git log --stat` / `git status --short` / tests pass / 追加 test file 実在で追認できる。

## TODO

【】5 subtype の `required_fact_block` を固定する
【】5 subtype の `title_body_coherence`(title prefix + 本文整合)を固定する
【】5 subtype の `abstract_lead_ban` 文言を固定する
【】5 subtype の `attribution_condition` を固定する
【】source 不足時の `fallback_copy` を固定する
【】Codex repair の `minimum-diff rubric`(該当 block / 該当 sentence / 該当 attribution のみ対象)を固定する
【】初稿 prompt / repair prompt を 1 builder 内で明示分岐すると明記する

## 成功条件

- 5 subtype の prompt contract が ticket 本文で固定されている。
- initial / repair 分岐と minimum-diff 方針が明記されている。
- validator の rule と矛盾しない。
- Codex B が prompt builder 実装と tests 追加へそのまま進める粒度になっている。
