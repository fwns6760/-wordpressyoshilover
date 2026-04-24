# 086 Title assembly contract implementation

## meta

- owner: **Codex B**(品質改善 lane の実装便)
- type: **impl ticket**(085 doc-first の後続実装)
- status: BLOCKED on 085 close(085 §3 contract 確定 + 本 ticket への転記完了が前提)
- created_at: 2026-04-24 22:05 JST
- deps: 085(title style analysis and contract refresh、本 ticket の入力 contract)/ 030(title assembly base rule)/ 067(comment lane title)/ 080 / 081 / 071(title-body nucleus validator)
- target_repo: `/home/fwns6/code/wordpressyoshilover`

## why_now

- 085 で確定した上位 title policy(subtype 横断の base contract)を、現実の prompt builder と validator に反映しないと editorial contract が紙のまま
- 030 / 067 / 080 / 081 の subtype 別 contract は維持するが、085 §3 の **subtype 横断 base 型 / 禁止形** を generation 側 + validation 側に注入する必要がある
- 067 で確認済の通り、editorial 判断を Codex に委ねると hallucination / generic tone に流れる → 085 で Claude が contract を固定 → 086 で Codex が rule-based に enforce

## purpose

- 085 §3 で確定した subtype 別 base 型 / 許容形 / 禁止形 を以下に反映:
  - **prompt builder**(title 生成 prompt の文言)
  - **validator**(085 §3 禁止形を hard fail で検知)
  - **tests**(各 subtype の base 型 / 禁止形を網羅)
- 030 / 067 / 080 / 081 / 071 の既存 contract は **import only / 連携**、本体 touch しない
- 既存 suite green を維持

## 反映する title contract(085 §3 から転記、2026-04-24 確定)

> 本節は **085 close 時の必須条件 #6**。完了済(2026-04-24 22:50 JST)。
> /tmp/codex_086_prompt.txt 内の同名節と完全同期。`doc/085-title-style-analysis-and-contract-refresh.md` §3 が正本、本節は写しの可読性確保用。

正本: `doc/085-title-style-analysis-and-contract-refresh.md` §3(共通 8 rule + 10 subtype 別 contract)
fire 用 prompt: `/tmp/codex_086_prompt.txt` (`## 反映する title contract` 節に同内容を転記済)

reason_code 5 種(validator 側で hard fail):
- `TITLE_STYLE_SPECULATIVE` — 確定事項への speculative phrase(`どう見たいか` `何を見せるか` 等)
- `TITLE_STYLE_GENERIC` — 067 既存 14 phrase + AI generic phrase(`真相` `本音` `振り返りたい` 等)
- `TITLE_STYLE_CLICKBAIT` — 煽り(`驚愕` `衝撃` `ヤバい` 等)
- `TITLE_STYLE_OUT_OF_LENGTH` — subtype 別 文字数逸脱
- `TITLE_STYLE_FORBIDDEN_PREFIX` — `【速報】` `【LIVE】` `【巨人】` 等

## scope(編集対象、最小 diff)

> **本節は 085 close 時に確定する**。下記は scope 候補(085 §3 完成度に応じて絞る or 拡げる)。

候補 file:

- `src/fixed_lane_prompt_builder.py`(または title 組立を担う module、085 §1 で実態確認後に確定)
  - 085 §3 base 型を prompt 文言に反映
  - 禁止形を「Don't generate ...」 instruction に追加
  - subtype 別 variation を switch case 形で
- `src/title_body_nucleus_validator.py`(071 拡張)or **新規 `src/title_style_validator.py`**
  - 085 §3 禁止形を hard fail として検知(speculative / generic / clickbait phrase)
  - 既存 reason_code(SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI)と disjoint な reason_code を追加(`TITLE_STYLE_SPECULATIVE` / `TITLE_STYLE_GENERIC` / `TITLE_STYLE_CLICKBAIT` 等)
- `tests/test_title_style_validator.py`(新規 or `test_title_body_nucleus_validator.py` 拡張)
  - 各 subtype × base 型 pass / 禁止形 reject を網羅
- `doc/086`(本 file、Final report 時に【×】 mark を付ける)

## 不可触(staged file 全てで diff 0、§31-B)

- `src/rss_fetcher.py`(creator 主線、085 §3 で「prompt builder のみ touch、creator 本体は維持」を確定済前提)
- `src/tools/run_notice_fixed_lane.py`(route 層)
- `src/tools/draft_body_editor.py` / `src/tools/run_draft_body_editor_lane.py`(083/084 で touch 済、本 ticket では不可触)
- `src/title_body_nucleus_validator.py` の **既存** reason_code logic(本 ticket は **拡張のみ**、既存 SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI 判定は touch しない)
- `src/source_trust.py` / `src/source_id.py` / `src/game_id.py`
- `src/postgame_revisit_chain.py` / `src/first_wave_promotion.py`
- `src/eyecatch_fallback.py` / `src/repair_playbook.py` / `src/fact_conflict_guard.py`
- `src/x_post_generator.py` / `src/x_published_poster*.py`
- `src/mail_delivery_bridge.py` / `src/morning_analyst_email_sender.py` / `src/x_draft_email_*.py` / `src/ops_status_email_sender.py` / `src/publish_notice_email_sender.py` / `src/publish_notice_scanner.py`(072-076)
- `src/nucleus_ledger_adapter.py` / `src/nucleus_ledger_emitter.py`(078/079)
- `src/social_video_notice_*` / `src/x_source_notice_*`(080/081 contract、本 ticket は import only / 不可侵)
- `src/article_parts_renderer.py`
- `src/wp_client.py`
- `automation.toml` / scheduler / secret / env / X API credentials
- `doc/030` / `doc/067` / `doc/080` / `doc/081` / `doc/071` 本体(本 ticket は連携、これらは touch しない)
- `doc/060`-`doc/085` 本体(本 ticket は新規 doc/086 のみ追加可)
- WP 書込 / published / WP DB
- baseballwordpress repo
- front lane 全部(別 Claude 担当)

## acceptance(本 ticket、impl)

- 085 §3 base 型を prompt builder に反映済(subtype 別 variation 確認)
- 085 §3 禁止形を validator で hard fail 検知(reason_code 追加、各 subtype × 禁止 phrase 1 case 以上 test pass)
- 071 既存 logic / 030 / 067 / 080 / 081 contract / 不可触 list 全 diff 0
- pytest suite green 維持(現在 1014、想定 +15-30 tests = 1029-1044)
- 1 commit に閉じる

## 進め方

> **詳細は 085 close 時に Codex prompt(`/tmp/codex_086_prompt.txt`)に書き出される**。下記は 085 close 前の固定 outline。

1. 085 §3 contract を 086 doc(本 file)の `## 反映する title contract` 節に転記済か確認
2. `/tmp/codex_086_prompt.txt` の `[FILL FROM 085 §3]` placeholder が全て埋まっているか確認
3. 上記 2 つが満たされていれば `codex exec --full-auto --skip-git-repo-check -C /home/fwns6/code/wordpressyoshilover < /tmp/codex_086_prompt.txt > /tmp/codex_086_run.log 2>&1` で fire
4. 完了後 Claude が 3 点 contract で追認、shadow gitdir 利用なら Claude host 再 commit + push

## stop 条件

- 085 §3 contract が contract として弱い(具体性不足、禁止形が抽象的すぎる)→ 085 を再 open して §3 補強
- prompt builder が想定 file ではなく別 module だった場合(rss_fetcher 内 inline 等) → user 判断、scope 設計をやり直す
- validator 拡張が 071 既存 reason_code と衝突する場合 → 新規 validator module に分離(`src/title_style_validator.py`)
- 既存 test 多数 fail → 085 §3 禁止形が過剰、085 §3 を緩和

## 完了通知

086 close 後、085 と 086 の sequence で title contract が紙 → 実装まで一気通貫した状態を session_log に 1 行記録。後続 087(validator extension の更なる強化)/ 088(subtype-specific fallback rotate)は observation 結果次第で別途判断。
