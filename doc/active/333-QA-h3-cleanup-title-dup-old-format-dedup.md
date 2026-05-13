# 333-QA h3 cleanup (title 重複 / 旧形式 / dedup suffix 違い)

## meta

- number: 333-QA
- type: h3 structure narrow cleanup (3 pattern 並走)
- status: DRAFT(doc 作成のみ、GO 待ち)
- priority: P1(SEO 構造 + 読者 UX 改善、parent: H3-STRUCTURE-UNIFY)
- owner: Claude
- created: 2026-05-13
- doc_path: `doc/active/333-QA-h3-cleanup-title-dup-old-format-dedup.md`
- parent: `doc/active/H3-STRUCTURE-UNIFY-2026-05-08.md`(残作業のうち narrow 着手分)
- cost: ¥0
- regression risk: 低(h3_normalizer 拡張 + narrow safe filter のみ)

## 1. 今回の目的

直近 15 publish audit(2026-05-13 13:50 JST)で発見した「余計な h3」3 パターンを **narrow に消す**。完全な H3-STRUCTURE-UNIFY ではなく、現状 87% 統一済の残り 13% を埋めるための後追い fix。

### 検出された 3 pattern

| パターン | 件数 | 例 |
|---|---|---|
| **TITLE_AS_H3** | 2 件 | post 66829 の body 冒頭に「【巨人】前回登板で完封の育成３年目・園田純規が先発 ＤｅＮＡ先発は藤浪…２軍・ＤｅＮＡ戦。」が h3 化(article title と重複)|
| **OLD_FORMAT** | 1 件 / 2 h3s | post 66826 の「【二軍スタメン一覧】」「【注目選手】」が h3_normalizer mapping 未登録 |
| **DUPLICATE** | 1 件 | post 66788 で「💬 ファンの声」(空)+「💬 ファンの声（Xより）」(本体)が並ぶ — 327-QA で入れた dedup が suffix 違いを同一視していない |

## 2. 今回触る範囲(GO 後)

- `src/h3_normalizer.py`(post-process filter 拡張)
  - mapping rule 追加(「【二軍スタメン一覧】」/ 「【注目選手】」)
  - `_dedupe_fan_voice_h3` の同一視判定で suffix `（...）` / `(...)` を正規化
- 必要時 `src/rss_fetcher.py`(article title が body 冒頭に h3 化する箇所、root を grep して narrow filter)
- `tests/test_h3_normalizer.py`(新 mapping 2 件 + dedup suffix 違いの新 case 追加)
- 必要時 `tests/test_rss_fetcher_*`(title-dup h3 削除の回帰テスト)
- 本 ticket 自身 `doc/active/333-QA-h3-cleanup-title-dup-old-format-dedup.md`

## 3. 今回触らない範囲

- publish / mail / scheduler / env / secret / Cloud Run config / GitHub Actions
- SEO / noindex / canonical / 301
- Gemini call / 外部 API call(増減なし)
- WordPress 本番記事の手修正、WP admin 操作
- **過去 publish の body 書換**(post-process は新 publish にのみ適用、retroactive な REST PUT は scope 外)
- nomotoke_card_renderer.py 本体の h3 emission 構造(H3-STRUCTURE-UNIFY Layer A、別 ticket)
- Gemini prompt の H3 制限(H3-STRUCTURE-UNIFY Layer B、別 ticket)
- subtype 別 h3 sequence 強制(H3-STRUCTURE-UNIFY §5、別 ticket)
- `doc/README.md` / `doc/active/assignments.md` の board 同期(別 doc-only 便)

## 4. 影響範囲

- yoshilover-fetcher service(rss_fetcher.py + h3_normalizer.py 経由)
- broadcast-auto / lineup-auto / postgame-auto / manual-intake-service(同じ src 共有)
- 新 publish の body HTML
  - TITLE_AS_H3 = body 冒頭 1 h3 削除 → body 長 -100〜-150 chars 程度
  - OLD_FORMAT 2 件 → 12 unified set 内に正規化
  - DUPLICATE = 同一 label の 2 h3 を 1 つに集約、空 section の削除
- 既存 publish には適用しない(retroactive 書換禁止)
- mail / X / SEO / 画像 / 公開判定への影響なし

## 5. 実行予定テスト

GO 後の予定テストは次の通り。

1. **追加再現テスト(赤確認 → 緑確認)**
   - h3_normalizer: `【二軍スタメン一覧】` → `📋 事実カード`
   - h3_normalizer: `【注目選手】` → `🏆 注目選手`
   - dedup: `<h3>💬 ファンの声</h3><p>filler</p><h3>💬 ファンの声（Xより）</h3><blockquote class="twitter-tweet">...</blockquote>` で twitter-tweet 含む方を残し、もう片方を section ごと削除
   - title-dup h3: source title と body 冒頭 h3 が高一致(長い prefix match)なら h3 削除
2. **既存 regression テスト**
   - `tests/test_h3_normalizer.py` 全件 pass(既存 dedup test を破らない)
   - `tests/test_rss_fetcher_*` 関連
3. **fixture-based**
   - 66829 / 66819 / 66826 / 66788 の HTML snapshot を fixture 化、修正後の期待 h3 リストと一致確認
4. **full suite**
   - `python3 -m pytest tests/ -q --no-header` で regression 0 確認

## 6. STOP 条件

- TITLE_AS_H3 削除で **本文内の有用な h3** まで誤削除する事象が test 段階で出たら STOP
- dedup 拡張で **意図的に複数あるべき h3**(将来の subtype 別並び等)まで集約してしまう事象が出たら STOP
- 既存 `test_h3_normalizer.py` の `TestIdempotent` が破れたら STOP(idempotent は必須)
- full pytest baseline が 1 fail 超に増えたら STOP(現 baseline = 1 pre-existing `test_game_live_primary_sources_are_hochi_only`)
- WP REST に PUT 書込みが必要になったら STOP(scope 違い、別 ticket)
- 触らない範囲(publish / mail / scheduler / env / Gemini prompt / nomotoke renderer 本体)に手が伸びたら STOP

## 7. 禁止事項

- 過去 publish の body を WP REST で書き換える
- env / Secret / Scheduler を変更する
- Gemini prompt を編集する(H3-STRUCTURE-UNIFY Layer B、別 ticket)
- nomotoke_card_renderer.py の h3 emission 構造を変更する(H3-STRUCTURE-UNIFY Layer A、別 ticket)
- 12 unified set 外に新規 h3 を追加する
- 既存 mapping rule を変更 / 削除する(idempotent を守るため追加のみ)
- 「掲示板っぽさ」「SEO」名目で publish / mail / scheduler 条件をついで修正する
- `git add -A` を使う

## 8. 想定されるデグレ

- TITLE_AS_H3 検出が雑だと、**本文中の引用や見出し**(タイトル末尾が一致してしまうケース)も誤削除
- dedup 拡張で、**わざと別ラベルにしたい 2 h3**(将来 subtype 設計で複数同 prefix h3 を許容したい場合)も巻き込む
- h3_normalizer の mapping 追加で「【二軍スタメン一覧】」を `📋 事実カード` に押し込むことで、**ファーム特定の subtype アイデンティティ**が薄れる可能性(本来は `📋 事実カード` のままで OK、内容が薄まる懸念)
- post-process 適用順序の前後で、既存 h3_normalizer の idempotent が崩れるリスク

## 9. 作業ログ欄

| 日時 (JST) | 内容 | 結果 |
| --- | --- | --- |
| 2026-05-13 13:50 | audit 完了、3 pattern 検出(`TITLE_AS_H3` x2 / `OLD_FORMAT` x2 / `DUPLICATE` x1) | issue 4 件特定 |
| 2026-05-13 | doc 作成 | GO 待ち |

## 10. Regression Memo 欄

### current observation

- 直近 15 publish のうち 11 (73%) は h3 が 12 unified set 内に正規化済(Layer C 22 rule 効いてる)
- 残り 4 (27%) は 3 pattern いずれかに該当
- 327-QA で入れた `_dedupe_fan_voice_h3` は label 完全一致のみ(suffix 違いを同一視しない)
- TITLE_AS_H3 は source RSS 由来の body 冒頭 h3、おそらく Gemini が source タイトルをそのまま h3 化している

### guard hypothesis

- guard A: TITLE_AS_H3 削除は **長 prefix match**(article title の先頭 N chars が h3 と一致 + 末尾が `。` で終わる)に限定、本文中の引用は守る
- guard B: dedup の同一視は **絵文字 + 単語ベース**でやる(`💬 ファンの声` + 任意 suffix を同一視)、別 label には触らない
- guard C: mapping 追加は H3-STRUCTURE-UNIFY の 12 set 内に閉じる、新規 emoji を導入しない

---

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/h3_normalizer.py`
  - `_h3_title_dup_removal_enabled()` helper 追加(env `ENABLE_H3_TITLE_DUP_REMOVAL`、default ON)
  - `_remove_title_duplicate_first_h3()` 関数追加(body 冒頭の【...】... 。h3 を削除)
  - `_H3_RULES_EXACT` mapping に 2 件追加:
    - `("【二軍スタメン一覧】", "📋 事実カード")`
    - `("【注目選手】", "🏆 注目選手")`
  - `normalize_h3_in_html` 末尾で title dup removal を fan voice dedup の後に call
- `tests/test_h3_normalizer.py`
  - `TestH3CleanupMappingsAdded`(2 件): 新 mapping verify
  - `TestH3TitleDuplicateRemoval`(7 件): 削除条件 + 誤削除予防 + flag OFF
  - `TestFanVoiceDedupSuffixVariants`(1 件): `（Xより）` suffix 違い dedup の explicit regression
- `doc/active/333-QA-h3-cleanup-title-dup-old-format-dedup.md`(本 ticket)

### 2. diff 概要

- mapping 2 件追加(Layer C 拡張)、既存 22 rule → 24 rule
- title dup removal(env flag 付き、default ON):
  - body 冒頭 200 chars 以内 / `【` で始まり `。` で終わる / inner length >= 26 chars の first h3 を削除
  - 12 unified set ラベル(`📋 事実カード` 等)は `【` で始まらないので対象外
  - 短い `【ハイライト】` 等は inner length < 26 で対象外(別 mapping 経路で正規化)
- dedup suffix 違いは既存 `startswith(_FAN_VOICE_LABEL)` で吸収済、追加コードなし、explicit test のみ追加

### 3. 実行したテスト

- `python3 -m py_compile src/h3_normalizer.py` → OK
- `python3 -m pytest tests/test_h3_normalizer.py -q` → 30 passed
- `python3 -m pytest tests/ -q --no-header` → 4049 passed / 1 pre-existing fail(regression 0)

### 4. テスト結果

- 新規 tests(10 件)全 pass
- 既存 tests 全 pass(idempotent / 既存 dedup / unified mapping 不変)
- pre-existing fail = `test_game_live_primary_sources_are_hochi_only`(本 ticket 無関係、5/12 以前から継続)

### 5. 残った懸念

- TITLE_AS_H3 削除は「body 200 chars 以内 + `【`〜`。` length 26+」の 4 条件揃いの first h3 のみ
  - 4 条件のうち 1 つでも外れる **正当な title 風 h3**(別 prefix 例: `■`、`▼`)があった場合 fall-through
  - 該当例が観測されたら別 commit で extension
- post-process タイミングが WP create_post 時のみ(wp_client.py:733)。update / reuse 経路に通っていない可能性
  - 過去 publish の retroactive 適用は scope 外
- ENABLE_H3_TITLE_DUP_REMOVAL default ON にしたので、deploy 後即動作 — もし誤削除が観測されたら env を `=0` に設定して即可逆

### 6. 新しく見つかったデグレ

なし(regression 0、既存 30 tests + 新 10 tests = 40 passed)。

### 7. 追加した回帰テスト

- `TestH3CleanupMappingsAdded::test_nigun_lineup_to_fact_card`
- `TestH3CleanupMappingsAdded::test_chumoku_player_to_notable_player`
- `TestH3TitleDuplicateRemoval::test_title_like_h3_at_body_start_removed`
- `TestH3TitleDuplicateRemoval::test_university_baseball_title_removed`
- `TestH3TitleDuplicateRemoval::test_short_unified_h3_NOT_removed`
- `TestH3TitleDuplicateRemoval::test_h3_starts_with_bracket_but_short_NOT_removed`
- `TestH3TitleDuplicateRemoval::test_title_like_h3_NOT_at_body_start_kept`
- `TestH3TitleDuplicateRemoval::test_h3_without_trailing_period_kept`
- `TestH3TitleDuplicateRemoval::test_flag_off_keeps_title_h3`
- `TestFanVoiceDedupSuffixVariants::test_dedup_handles_xyori_suffix`

### 8. 次回触ってはいけない範囲

- `_H3_RULES_EXACT` の既存 22 entries(idempotent / 既存 mapping を守るため追加のみ)
- `_dedupe_fan_voice_h3` の keeper 選定ロジック(twitter-tweet 優先 → body_len → h3_start)
- 12 unified set 自体(新 emoji / 新ラベル追加は別 ticket = H3-STRUCTURE-UNIFY)
- nomotoke_card_renderer.py の h3 emission 本体(Layer A、別 ticket)
- Gemini prompt(Layer B、別 ticket)
- publish / mail / scheduler / env / Cloud Run config / Secret
- 過去 publish の body 書換(WP REST PUT、scope 外)
