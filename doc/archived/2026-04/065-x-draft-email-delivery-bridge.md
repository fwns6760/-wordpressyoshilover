# 065 — X下書きメール配送 bridge

**フェーズ：** delivery content contract(X 投稿下書きを mail で届ける content 側契約)
**担当：** Claude Code(contract owner、実装時は Codex B 主体)
**依存：** 039, 060, 064
**状態：** READY(doc-first。runtime resume 後の X 下書きメール候補。061 自動投稿は前倒ししない)

## 1. why_now

- user は疲れており、X 投稿文を毎回ゼロから作る負荷を下げたい。
- ただし自動投稿はまだ早い。事実事故 / 煽り事故 / 公式と中の人の混同が起きたら致命的。
- いま必要なのは「安全な下書きをメールで届ける」段階であり、「X へ自動投稿する」段階ではない。
- 039 は **delivery reliability**(cron fire / log read / mail send / 着信の 4 段切り分け)、065 は **delivery content contract**(メール本文に何を入れるか)。役割を明確に分ける。

## 2. purpose

- Giants 系ニュースをもとに、user が少し直せば投稿できる X 下書きをメールで届ける。
- 公式アカウント向けと中の人アカウント向けを混同しない。
- fact / topic / reaction の境界を守ったまま、投稿作成の疲労を下げる。

## 2.5 phased position(2026-04-23)

- 060 により X は手動で先に開始する。065 はその手動運用を楽にする **中間段階** として扱う。
- 065 は X に直接投稿しない。メールで `official_draft` / `official_alt` / `inner_angle` を届け、user が直して手動投稿する。
- fire 条件は runtime resume 後。046 / 047 の実データが見えるまで、doc と実装の乖離を避ける。
- 061 は published 安定 + 060 manual review gate pass 後の自動投稿 ticket。065 は 061 の代替でも前倒しでもない。

## 3. scope

- X へ直接投稿しない(X API / automation / 自動投稿経路を持たない)。
- user にメールで投稿候補文を届ける。
- user が修正して手動投稿する。
- Draft URL / preview URL / private URL は一切含めない(source_ref にも出さない)。

## 4. 対象題材

- ニュース系のみ。
- 初期対象は 6 類型:
  1. スタメン
  2. 公示・昇降格
  3. 予告先発
  4. 試合結果
  5. 強いコメント
  6. 故障・離脱状況
- 試合中速報や 1 球ごとの反応は対象外。
- live 運用は 060 の手動運用に残す。

## 5. メール 1 通のフォーマット

- subject:
  `[X下書き] Giants news drafts YYYY-MM-DD HH:mm`
- 1 通あたり最大 5 item。
- 各 item はこの順で固定:
  1. recommended_account
  2. source_tier
  3. safe_fact
  4. official_draft
  5. official_alt
  6. inner_angle
  7. risk_note
  8. source_ref

## 6. 各欄の意味

- **recommended_account**: `official` か `inner` のどちらか。どの口向けの下書きかを先頭で示す。
- **source_tier**: `fact` / `topic` / `reaction`(064 の 3 区分)。safe_fact / official_draft の断定許容範囲を決める根拠。
- **safe_fact**: 断定してよい事実だけを 1-2 文。未確認・推測・煽りは入れない。
- **official_draft**: 公式アカウント用。事実 first + 軽い熱量、120 字以内目安。060 の「事実 first + 軽い熱量」に従う。
- **official_alt**: 公式アカウント用の別案。事実は変えず言い回しだけ変える(順序・語尾・助詞・絵文字有無など)。
- **inner_angle**: 中の人向けの任意案。温度感は出してよいが、事実部分は曖昧にしない。不要なら空でもよい。
- **risk_note**: 断定不可 / 一次確認待ち / 言い過ぎ注意 などを 1 行。source_tier が fact 以外なら必ず risk_note を記す。
- **source_ref**: 元ソース名だけ(例: `球団公式 X` / `NPB 公式` / `主要媒体 A`)。公開ソースは可だが Draft URL は禁止。

## 7. source 境界

- **fact source** だけが safe_fact / official_draft の断定根拠になれる。
- **topic source** は candidate 化まではよいが、primary recheck 前に勝敗・公示・故障・予告先発を断定しない。該当時は official_draft の断定を外し、inner_angle に寄せるか送らない。
- **reaction source** は inner_angle の話題補助には使えても、事実断定には使わない。safe_fact / official_draft / official_alt の根拠にしない。
- X 単独で「勝った / 負けた / 試合があった / 抹消された / 故障した」を断定しない。fact source であっても一次発表が出ていない段階では official_draft に断定表現を入れない。

## 8. 公式 / 中の人の分離

- **official_draft** は 060 の公式契約に従う。
- 公式は「事実 first + 軽い熱量」まで。煽り / 未確認断定 / rumor 昇格 / 長文雑談 は NG。
- 中の人は「人柄 first」でよいが、事実部分は曖昧にしない。運営裏側・試行錯誤の温度感は許容。
- 1 item の中で、公式用文面と中の人用文面を必ず別欄に分ける(official_draft / official_alt と inner_angle が同じ欄に混ざらない)。
- 公式用欄(official_draft / official_alt)に中の人の私見が混ざっていたら、その item は不採用として送らない。

## 9. cadence

- delivery はニュース digest。速報即送はやらない。
- 初期 cadence は 1 日 2 便:
  - 昼便
  - 夜便
- 同一 candidate_key(064 / 037 の event_family + subtype + key)の重複送信は禁止。同日便間でも、翌日便跨ぎでも、同じ candidate_key を再掲しない。
- 該当 item が 0 の便は送らない(空メール送信禁止)。

## 10. non_goals

- X API 投稿。
- 自動投稿。
- 返信・リプライの自動生成。
- 試合中速報の自動化。
- Draft URL / preview URL の送信。
- 060 の manual 運用を飛ばして 061 に進むこと。
- 039 の delivery reliability(cron fire / log read / mail send / 着信)を本 ticket 内で再定義すること。

## 11. success_criteria

- user がメールを見て、そのまま少し直せば投稿できる状態になっている。
- 公式用(official_draft / official_alt)と中の人用(inner_angle)が混ざらない。
- fact / topic / reaction の誤用で断定事故を起こさない。
- 投稿のたたき台を考える疲労が減る。
- 060 の手動投稿前提と 064 の source 境界を壊さない。

## 12. acceptance_check

- ticket 本文だけで、何をメールに入れるかが決まっている。
- official_draft と inner_angle の分離が明記されている。
- safe_fact と risk_note が必須欄になっている(risk_note は source_tier が fact 以外で必須)。
- 速報自動投稿をやらないことが明記されている。
- 039 は delivery、065 は content contract と役割分離されている。
- 060 / 061 / 064 と競合しない(060 公式「事実 first + 軽い熱量」を上書きしない、061 自動投稿を前倒ししない、064 の 3 区分を再定義しない)。

## 13. fire 前提 / stop 条件

### fire 前提

- 060 契約を維持したまま X 投稿の省力化を進めたい。
- 064 の 3 区分(fact / topic / reaction)を守る。
- 039 は mail delivery reliability の別線として維持する(065 は content のみ、delivery 経路は 039 に委ねる)。
- runtime(pipeline)回復後に実装 fire を判断する。doc-first で今は起票のみ。

### stop 条件

- Draft URL が本文案や source_ref に混ざる。
- topic / reaction を fact のように断定する。
- 公式向け文面(official_draft / official_alt)に中の人の私見が混ざる。
- そのまま自動投稿してよいと誤読できる仕様(自動投稿フラグ / API 送信経路 / 予約投稿スロット)になる。
- いずれか観測で stop、即座に仕様側へ戻す。

## 14. 既存 ticket との関係

- `039` = **mail delivery reliability**(cron fire / log read / mail send / 着信の 4 段切り分け、経路の信頼性)。065 は delivery 経路を再定義しない。
- `060` = **SNS 2 アカ運用 contract**(公式 X / 中の人 X の手動運用と Draft 期 bridge)。065 は 060 の公式「事実 first + 軽い熱量」と中の人「人柄 first」の分離を上書きしない、従う。
- `061` = **published 安定後の公式自動投稿**(060 gate 通過後)。065 は 061 を前倒ししない。065 は自動投稿ではなく、mail で下書きを届ける中間段階。
- `064` = **X source 3 区分 contract**(fact / topic / reaction)。065 の source_tier 欄と source 境界は 064 を正本参照する、再定義しない。
- `065` = **X 下書きメール配送の content contract**(本 ticket)。mail 本文に何を入れるかの仕様、delivery 経路は 039 に委ね、運用 contract は 060、source 境界は 064 に委ねる。

## runtime 復旧 / 既存 fire 順との関係

- 本 ticket は doc-first contract。044 runtime 復旧 routing を止めない。
- 既存 fire 順(046 ✓ → 047 ✓ → [048 HOLD] → 060 並走 → 061 止め)を変更しない。
- 実装 fire は runtime 回復後に別途判断。061 を前倒ししない。
- automation.toml / scheduler / X API / 自動投稿経路は触らない。

## 15. B1 implementation status(2026-04-23)

- **B1(content / validator / dry-run)**: CONTENT ACTIVE / delivery 未接続。
- 実装済み: `src/x_draft_email_renderer.py` が 1 candidate あたり 8 欄(recommended_account / source_tier / safe_fact / official_draft / official_alt / inner_angle / risk_note / source_ref)を固定順で生成する。
- 実装済み: `src/x_draft_email_validator.py` が rule-first で hard fail 6 種(DRAFT_URL_LEAK / UNGROUNDED_OFFICIAL_FACT / OFFICIAL_INNER_CROSS_CONTAMINATION / MISSING_RISK_NOTE / CANDIDATE_KEY_DUPLICATE / OVER_LIMIT)と soft fail 3 種(OFFICIAL_ALT_IDENTICAL_TO_DRAFT / SAFE_FACT_EXCESS_LENGTH / SOURCE_REF_MISSING)を判定する。
- 実装済み: `src/x_draft_email_digest.py` が `candidate_key = (news_family, entity_primary, event_nucleus)` の NFKC 正規化、空白除去、重複排除、1 digest 最大 5 件制限を適用する。
- 実装済み: `src/tools/run_x_draft_email_dry_run.py` が fixture 入力だけで 1 digest body を stdout に出力する。`--format human|json` に対応し、hard fail は除外、soft fail は warning として同梱する。
- B1 は Gmail 送信、SMTP、API 呼び出し、`automation.toml`、Scheduler、Secret、X API、自動投稿経路に接続しない。
- **B2(mail delivery 接続)** は runtime evidence 復旧後の別便。対象は Gmail delivery 接続、cadence(昼便 / 夜便)、subject tag、recipient、空メール抑止、039 delivery reliability との接続確認に限定する。
