# 244 baseball numeric fact consistency guard

- number: 244
- type: narrow implementation (publish blocker + X candidate suppress)
- status: CLOSED
- priority: P0.5
- owner: Codex B
- lane: B
- created: 2026-04-28
- updated: 2026-04-28 (scope: 監査 → 矛盾を publish 前 / X 候補表示前に止める実装修正)
- parent: 234 / 242 / MKT-008
- related: 242-B / 242-D2 / 234-impl-1 / 243

## purpose

**野球記事の数字を AI に考えさせない。数字は AI が書くものではなく、source/meta から抜いて使うもの。**

source / metadata / generated body / X candidate 間の **数字・主語・日付の矛盾を検出し、publish 前または X 候補表示前に止める narrow 実装**。
「監査して報告する」ではなく「矛盾を見つけたら publish させない / X 候補に出させない」修正。
LLM / Gemini / Web / 外部 API で補完しない。既存 record 内の title / source body / generated body / metadata / manual X candidate だけを使い、安い deterministic check (regex / marker / local parser) で守る。

## 記事タイプ別方針(2026-04-28 user 明示、follow-up 反映待ち)

| subtype 群 | 数字ガード | 不一致時 |
|---|---|---|
| **試合系**(postgame / farm_result / lineup / farm_lineup / pregame / probable_starter) | **必須**(strict) | concrete mismatch = **hard_stop**、ambiguity = **review** |
| **コメント/談話/コラム系**(manager_comment / player_comment / sns_topic / rumor_market) | **軽め**(lenient) | mismatch でも **review 止まり**、hard_stop に巻き込まない |
| **default / 不明** | 中程度(saw safe-side fallback) | mismatch = **review**、AI に本文をそれっぽく埋めさせない |

**現状(f2cc8a3)**: subtype 区別なし uniform 判定 → `244-followup` で subtype-aware severity 追加。

## scope

- 数字・スコア・勝敗・日付・選手名の **矛盾検出と publish/X 抑止**
- article body の concrete mismatch: **hard_stop / publishable=false**
- ambiguity / source facts 不足: **review/draft**(hard_stop に巻き込まない)
- X candidate だけの mismatch: **`x_post_ready=false` / candidate suppress**(article publish は維持)
- good postgame / good farm_result は止めない(false positive 厳禁)
- article body と X candidate の両方を独立に見る

## non-goals

- Gemini call 追加
- Web 検索
- 外部 API
- roster DB / NPB API / Yahoo API 新規参照
- heavy facts extractor
- prompt 全体改修
- H3 required 化
- 234 全 template 一括実装
- 242-B の entity contamination 全体実装との混線
- Cloud Run / Scheduler / env / Secret / traffic / WP live mutation

## implementation pre-check

Codex B は実装着手前に、以下の生成・検証経路を必ず inspect する(本 ticket の目的は監査ではなく、矛盾を見つけたら publish させない / X 候補に出させない narrow 修正)。

- 元記事 title / source body / summary / source_url が record のどこに入るか
- generated title / body / excerpt / metadata がどこで作られるか
- publishable / hard_stop / review flag がどこで決まるか
- manual X candidates / intent link / `x_post_ready` がどこで作られ、どこで抑止されるか
- existing tests / fixtures で numeric mismatch を守っているか

## required checks

### 1. score order consistency

対象表記:

- `1-11`
- `1－11`
- `1対11`
- `1 vs 11`
- `巨人1-11楽天`
- `巨人 1 - 11 楽天`

守ること:

- `1-11` を `19-1` のように結合・反転・桁誤変換しない
- source / title / metadata に明確な score がある場合、generated body / X candidate の score が一致すること
- source に複数 score がある、または home/away order が曖昧な場合は hard_stop ではなく review

hard_stop:

- source `1-11` に対して generated body or X candidate が `19-1`, `11-1`, `1-9`, `9-1` など明確に別 score
- score から導ける勝敗と本文の勝敗表現が矛盾

review:

- source score が複数候補で確定不能
- generated body に score がなく、postgame/farm_result として required facts が弱い

### 2. win/loss consistency

対象:

- `勝利`
- `敗れ`
- `黒星`
- `白星`
- `連勝`
- `連敗`
- `逆転勝ち`
- `完敗`

守ること:

- 巨人側 score が相手より低いのに「巨人が勝利」と書かない
- 巨人側 score が相手より高いのに「敗れた」と書かない
- score orientation が曖昧なら review

### 3. date consistency

対象:

- title / source body / metadata / publish_time / generated body / X candidate
- `4月28日`, `2026年4月28日`, `本日`, `きょう`, `昨日`

守ること:

- source / metadata に明確な game_date がある場合、generated body / X candidate の日付が矛盾しない
- relative date は publish_time JST を基準に解釈する
- 不明なら補完しない

### 4. pitcher stats vs team stats

対象:

- `被安打`
- `安打`
- `失点`
- `自責点`
- `○回`
- `○回○安打○失点`
- `チーム○安打`

守ること:

- 投手の `○回○安打○失点` と、チーム全体の `○安打` を混同しない
- `先発投手が11安打` と `チームが11安打` を誤って入れ替えない
- 投手名の近くにある stats と、チーム/打線/全体の stats を別 bucket として扱う

hard_stop:

- source で「チーム11安打」なのに generated body が「投手が11被安打」
- source で「投手 5回3安打2失点」なのに generated body が「チーム3安打2得点」のように主語を変える

review:

- source に stats はあるが主語が取れない
- generated body が stats を盛っている疑いはあるが concrete mismatch まで確定できない

### 5. player name consistency

対象:

- source title/body にある選手名
- generated title/body に出る選手名
- manual X candidate に出る選手名

守ること:

- generated body / X candidate に、source/title/metadata にない選手名を中心人物として追加しない
- 対戦相手の選手名と巨人選手名を取り違えない
- 242-B の他球団混入 detector と競合しない。244 は数字・主語・本文/X候補の整合性に限定する

review:

- source にない選手名が出たが、既存 related/meta 由来の可能性がある

hard_stop:

- source にない選手名が score / 勝敗 / 投手成績の主語になっている

## flags

Codex B は既存の evaluator / X candidate suppress mechanism に合わせ、最小の flag 名を選ぶ。

推奨 flag:

- `numeric_fact_mismatch`
- `score_order_mismatch`
- `win_loss_score_conflict`
- `pitcher_team_stat_confusion`
- `date_fact_mismatch`
- `x_post_numeric_mismatch`
- `x_post_unverified_player_name`

期待:

- article body の concrete mismatch: hard_stop / publishable=false
- article body の ambiguity: review/draft
- X candidate の concrete mismatch: article publish は維持可能でも `x_post_ready=false` / candidate suppress
- X candidate の ambiguity: candidate suppress

## implementation guidance

- regex / marker / local parser のみ
- score extraction は digit sequence を結合しないこと
- `1-11` は `(1, 11)` として保持し、文字列正規化時に `19-1` へ変換しない test を必ず置く
- source facts が取れない場合、LLMで補完せず review/draft
- 既存 template_key 判定は 100% 自動分類を狙わない。confidence high の場合のみ使う
- `farm_result` / `first_team_postgame` / `pregame` を優先し、default_review は自動 publish しない方針に寄せる

## candidate files

Primary:

- `src/guarded_publish_evaluator.py`
- `tests/test_guarded_publish_evaluator.py`

Possible X candidate path:

- `src/publish_notice_email_sender.py`
- `tests/test_publish_notice_email_sender.py`
- `src/x_draft_email_renderer.py`
- `src/x_draft_email_validator.py`

Codex B must inspect first and touch only the minimum path.

## tests

Required tests:

- `test_score_1_11_is_not_normalized_to_19_1`
- `test_score_mismatch_blocks_publish`
- `test_win_loss_conflict_blocks_publish`
- `test_ambiguous_score_is_review_not_hard_stop`
- `test_pitcher_hits_allowed_not_confused_with_team_hits`
- `test_team_hits_not_written_as_pitcher_hits_allowed`
- `test_date_mismatch_blocks_or_reviews`
- `test_x_candidate_score_mismatch_suppresses_x_only`
- `test_x_candidate_unverified_player_name_suppresses_x_only`
- `test_good_postgame_numeric_facts_pass`

Fixtures:

- bad score conversion: source `巨人1-11楽天`, generated `19-1`
- bad score reversal: source `巨人1-11楽天`, generated `巨人11-1楽天`
- bad win/loss: source score 巨人 1 / 楽天 11, generated `巨人が勝利`
- pitcher/team confusion: source `先発Aは5回3安打2失点`, team line `巨人11安打`, generated `Aが11被安打`
- X candidate mismatch only: body correct, X text wrong score
- good postgame/farm_result: score, date, player name, pitcher stats all consistent

## dry-run verification

- `python3 -m unittest tests.test_guarded_publish_evaluator`
- If X path touched: `python3 -m unittest tests.test_publish_notice_email_sender tests.test_x_draft_email_validator`
- `rg -n "numeric_fact_mismatch|score_order_mismatch|win_loss_score_conflict|pitcher_team_stat_confusion|x_post_numeric_mismatch" src tests`

## live verify

Live mutation is out of scope for this ticket.

After commit and accept, authenticated executor may rebuild/deploy separately, then verify:

- new mismatch examples produce hard_stop/review/suppress flags
- no Gemini call increase
- no Web/API access
- no change to scheduler/env/secret

## acceptance

- no LLM / Gemini / Web / external API added
- score parser preserves score order and digit boundaries
- concrete score mismatch blocks publish
- win/loss contradiction blocks publish
- pitcher stats and team stats are separated
- X candidate mismatch suppresses X candidate without unnecessary article publish regression
- ambiguous cases review/draft instead of hallucination
- good postgame/farm_result passes
- tests pass
- no broad template implementation
- no 242-B / 234-impl-1 scope expansion
