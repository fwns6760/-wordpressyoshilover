# preview_v0 next steps

`preview_v0` を実装・運用側へ広げる前の、preview-only 前提 subtask 整理。

## scope lock

- この文書は `doc-only`
- 今回は `新サンプル生成なし`
- `WP write = 0`
- `Gemini call = 0`
- `deploy = 0`

## preview 品質 acceptance gate

数値 threshold は `v0 provisional`。10 sample 前後の観測後に再調整してよい。

### mandatory

1. `source/meta` にない `数字 / 選手名 / 勝敗 / 投手成績` の新規混入が `0件`
2. placeholder 残存が `0件`
3. 適用 `rule list` が sample ごとに明示されていること
4. diff 出力が unified format であること
5. preview 実行中の `WP write = 0` かつ `Gemini call = 0`

### desirable

1. 修正文長 `<= 元本文長`
2. section 数 `<= 元本文の section 数`
3. source-meta facts カバー率 `>= 80%`

### 補助定義

- `facts カバー率`:
  - 分母 = 元本文内に現れていた `source/meta` 裏取り済み facts
  - 分子 = 修正文に残った同 facts
- `section 数`:
  - 正規化本文で見出しとして扱う `h2/h3` 相当ブロック数
- desirable は失敗しても preview 自体は保存できるが、`recommend_for_apply` 判定には使わない

## 次 preview 対象 3 件

既存 5 件と failure pattern が重なりすぎないものを優先した。

| candidate post_id | subtype | 想定 failure pattern | source 抽出方法 | note |
|---|---|---|---|---|
| `63466` | `postgame` | `subtype_unresolved`, anonymous `投手/選手` placeholder, loss game の inning narrative 過積載, speculative title | `logs/guarded_publish_history.jsonl` の `post_id=63466` 行から `backup_path` を引き、`logs/cleanup_backup/63466_20260426T012330.json` を読む。補助 flags は `logs/guarded_publish_yellow_log.jsonl` の `post_id=63466` 行 | 現行 3 sample にない「敗戦 + 匿名 player slots + subtype drift」の組み合わせ |
| `63464` | `farm_result` | anonymous `投手/選手` placeholder, loss-side farm summary, repeated body loop, `missing_primary_source` | `logs/guarded_publish_history.jsonl` の `post_id=63464` 行から `backup_path` を引き、`logs/cleanup_backup/63464_20260426T012330.json` を読む。補助 flags は `logs/guarded_publish_yellow_log.jsonl` の `post_id=63464` 行 | 既存 `farm_result` 2 件より匿名 slot が強く、preview gate の厳しさを試しやすい |
| `63509` | `manager` | quote article に対する `title_body_mismatch_partial`, heading sentence-as-section, fan voice contamination, optional section overgrowth | `logs/guarded_publish_history.jsonl` の `post_id=63509` 行から `backup_path` を引き、`logs/cleanup_backup/63509_20260426T012330.json` を読む。補助 flags は `logs/guarded_publish_yellow_log.jsonl` の `post_id=63509` 行 | 別 subtype の拡張耐性を見る 1 本。delete-first ルールの限界確認向け |

## lineup を次 3 件に入れない理由

- `lineup` は delete-first rule の再利用だけでは足りない
- `logs/draft_body_editor/2026-04-26.jsonl` では `post_id=63475` と `post_id=63499` が `heading sequence mismatch` で `guard_b` reject されている
- これは section 削除ではなく `構造保持 + スタメン表/先発表の再構成` が要る失敗モードで、preview v0 の最小拡張としては scope が広い

## 実装へ進める場合の最小 subtask

### CLAUDE_AUTO_GO 判定ルール

- `✅ eligible`: doc/script-only、`WP write` なし、`Gemini` なし、production integration なし
- `⚠️ user GO 後`: fetcher / publish-notice / live observation へ繋ぐ段階
- `❌ out of scope`: `WP REST PUT`、publish 状態変更、SEO 変更、live env/deploy 変更
- `scope disjoint` は path ownership で担保する。`subtask-1` は orchestration のみ、`subtask-2..4` はそれぞれ専用 module/doc のみを持ち、同じ file を共同編集しない

| subtask | scope | disjoint write scope | acceptance | rollback target | CLAUDE_AUTO_GO |
|---|---|---|---|---|---|
| `subtask-1 preview generator script 化` | backup JSON から `元本文 / source-meta facts / 修正文候補 / diff / rule list` を再生成する CLI を作る | `scripts/preview_v0_generate.py`, `docs/ops/preview_v0/generated/` | 既存 5 sample と同等の構成を再現でき、network/WP/Gemini に触れない | script と generated doc を削除するだけで戻せる | `✅` |
| `subtask-2 deterministic rule library 化` | `placeholder削除 / 空見出し削除 / optional section削除 / template寄せ` を単独 module 化する | `scripts/lib/preview_rules.py` | rule ごとに `applied/not_applied` が判定でき、rule 名が出力へ載る | module と import を外せば戻せる | `✅` |
| `subtask-3 source-meta facts extractor` | `candidate metadata -> facts list` 変換を独立させ、preview と acceptance の分母を統一する | `scripts/lib/preview_facts.py` | `source_url / source_label / score / opponent / player / pitching_line` などの抽出結果が deterministic に並ぶ | extractor module を外すだけで戻せる | `✅` |
| `subtask-4 diff/output format 統一` | unified diff、rule list、facts coverage、gate 判定の出力 contract を固定する | `scripts/lib/preview_render.py`, `docs/ops/preview_v0/FORMAT.md` | diff header と hunk 形式が固定され、5 sample で同じ render contract を出せる | renderer と format doc を外すだけで戻せる | `✅` |

## eligibility の境界

- 上の 4 subtask は、`read-only input + local script/doc output` に閉じればすべて `CLAUDE_AUTO_GO eligible`
- ここから先で `実 fetcher への組み込み`、`guarded publish notice`、`live observation hook` を入れるなら `⚠️ user GO 後`
- `preview をそのまま WP 本文へ apply` は `❌`。この ticket の次段でも別 scope に切る

## 次拡張の主なリスク

- `postgame` は unknown player/name slot が多く、delete-first を強めすぎると facts coverage が 80% を割りやすい
- `manager` は quote 整理が主題で、`試合メモ` テンプレを流用すると title-body mismatch を別の形で残しうる
- `lineup` は heading/table structure が本文価値そのものなので、`postgame/farm_result` の rule をそのまま再利用すると壊れる
- `guarded_publish_history` に `backup_path` がない候補は、preview の再現性が落ちる

## rollback path

- preview doc を消す
- preview 専用 script/module を消す
- production code, `WP`, `deploy`, `env`, `scheduler` には触れない
- したがって production 影響は `0`
